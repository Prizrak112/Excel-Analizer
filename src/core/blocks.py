"""
Модель блоков отчёта.
Содержит логику рендеринга всех типов блоков в HTML, включая продвинутые графики Plotly
(по столбцам и по строкам с выбором конкретных столбцов), условия фильтрации и срезы.
"""

from collections import OrderedDict
import json
import math
import re
import threading
import weakref
from dataclasses import dataclass, field
import numpy as np
import pandas as pd


def _ensure_series(obj) -> pd.Series:
    """Если из-за дублирующихся имён колонок вернулся DataFrame, выбирает колонку с наибольшим числом непустых данных."""
    if isinstance(obj, pd.DataFrame):
        if obj.shape[1] == 0:
            return pd.Series(dtype="object")
        best_col = obj.iloc[:, 0]
        best_cnt = best_col.notna().sum()
        for i in range(1, obj.shape[1]):
            cand = obj.iloc[:, i]
            cnt = cand.notna().sum()
            if cnt > best_cnt:
                best_col = cand
                best_cnt = cnt
        return best_col
    return obj


class DataMemoryCache:
    """
    Оперативное хранилище (In-Memory Cache) с авто-освобождением памяти
    через weakref.finalize, лимитами LRU и потокобезопасностью.
    """
    _lock = threading.RLock()
    _sheet_df_cache: OrderedDict = OrderedDict()
    _dedup_cache: OrderedDict = OrderedDict()
    _num_series_cache: OrderedDict = OrderedDict()
    _str_series_cache: OrderedDict = OrderedDict()
    _month_series_cache: OrderedDict = OrderedDict()
    _unique_vals_cache: OrderedDict = OrderedDict()
    _filter_df_cache: OrderedDict = OrderedDict()
    _render_html_cache: OrderedDict = OrderedDict()

    _MAX_SHEETS = 16
    _MAX_DEDUP = 16
    _MAX_SERIES = 64
    _MAX_UNIQUE = 64
    _MAX_FILTER_DF = 8
    _MAX_RENDER_HTML = 24

    @classmethod
    def _put_lru(cls, cache: OrderedDict, key, value, max_size: int, owner_obj=None):
        with cls._lock:
            cache[key] = value
            cache.move_to_end(key)
            while len(cache) > max_size:
                cache.popitem(last=False)
            if owner_obj is not None:
                try:
                    token = value
                    weakref.finalize(
                        owner_obj,
                        cls._safe_evict,
                        cache,
                        key,
                        token,
                    )
                except TypeError:
                    pass

    @classmethod
    def _safe_evict(cls, cache: OrderedDict, key, expected_val):
        with cls._lock:
            cur = cache.get(key)
            if cur is expected_val:
                cache.pop(key, None)

    @classmethod
    def df_key(cls, df: pd.DataFrame) -> tuple[int, int, int]:
        if df is None or not hasattr(df, "columns"):
            return (0, 0, 0)
        return (id(df), len(df), len(df.columns))

    @classmethod
    def invalidate_file(cls, file_name: str = "", sheet_name: str = ""):
        """Полностью сбрасывает кэш файла/листа и все производные серии без «осиротевших» записей."""
        f_clean = str(file_name or "").strip()
        s_clean = str(sheet_name or "").strip()

        if not f_clean and not s_clean:
            cls.clear_all()
            return

        with cls._lock:
            to_del = [
                k for k in list(cls._sheet_df_cache.keys())
                if (isinstance(k, tuple) and len(k) == 3 and k[1] == f_clean and (not s_clean or k[2] == s_clean))
                or k == (f_clean, s_clean)
            ]
            for k in to_del:
                cls._sheet_df_cache.pop(k, None)

            # Чистим все производные кэши, чтобы не оставалось битых/осиротевших серий
            cls._dedup_cache.clear()
            cls._num_series_cache.clear()
            cls._str_series_cache.clear()
            cls._month_series_cache.clear()
            cls._unique_vals_cache.clear()
            cls._filter_df_cache.clear()
            cls._render_html_cache.clear()
        print(f"[DataMemoryCache] Кэш для файла '{f_clean}' (лист: '{s_clean}') сброшен.")

    @classmethod
    def clear_all(cls):
        with cls._lock:
            cls._sheet_df_cache.clear()
            cls._dedup_cache.clear()
            cls._num_series_cache.clear()
            cls._str_series_cache.clear()
            cls._month_series_cache.clear()
            cls._unique_vals_cache.clear()
            cls._filter_df_cache.clear()
            cls._render_html_cache.clear()

    @classmethod
    def dedup_df(cls, df: pd.DataFrame) -> pd.DataFrame:
        if df is None or not hasattr(df, "columns"):
            return df
        # Если дублей колонок нет — возвращаем исходный df без хранения сильной ссылки в кэше
        if not df.columns.duplicated().any():
            return df
        key = cls.df_key(df)
        with cls._lock:
            cached = cls._dedup_cache.get(key)
            if cached is not None:
                cls._dedup_cache.move_to_end(key)
                return cached
        clean_cols = {col: _ensure_series(df[col]) for col in dict.fromkeys(df.columns)}
        res = pd.DataFrame(clean_cols, index=df.index)
        cls._put_lru(cls._dedup_cache, key, res, cls._MAX_DEDUP, owner_obj=df)
        return res

    @classmethod
    def get_dataframe(cls, manager, file_name: str = "", sheet_name: str = "", fallback_df: pd.DataFrame | None = None) -> pd.DataFrame | None:
        f_clean = str(file_name or "").strip()
        s_clean = str(sheet_name or "").strip()
        if s_clean == "— Авто (первый лист) —":
            s_clean = ""

        if not f_clean and not s_clean and manager is not None:
            if hasattr(manager, "get_default_file_and_sheet"):
                try:
                    df_f, df_s = manager.get_default_file_and_sheet()
                    f_clean = str(df_f or "").strip()
                    s_clean = str(df_s or "").strip()
                except Exception:
                    pass
            elif hasattr(manager, "get_files_dict"):
                try:
                    f_dict = manager.get_files_dict()
                    if f_dict:
                        f_clean = next(iter(f_dict.keys()))
                        s_clean = f_dict[f_clean][0] if f_dict[f_clean] else ""
                except Exception:
                    pass

        mgr_id = id(manager) if manager is not None else 0
        cache_key = (mgr_id, f_clean, s_clean)

        # 1. Проверяем слабую ссылку на загруженный DataFrame (мгновенно, без утечек)
        if (f_clean or s_clean):
            with cls._lock:
                entry = cls._sheet_df_cache.get(cache_key)
                if entry is not None:
                    df_ref, dedup_copy = entry
                    orig = df_ref()
                    if orig is not None:
                        cls._sheet_df_cache.move_to_end(cache_key)
                        return dedup_copy if dedup_copy is not None else orig
                    cls._sheet_df_cache.pop(cache_key, None)

        # 2. Запрашиваем DataFrame у FileManager и кэшируем через weakref
        if manager is not None and hasattr(manager, "get_dataframe") and (f_clean or s_clean):
            try:
                loaded_df = manager.get_dataframe(f_clean, s_clean)
                if loaded_df is not None:
                    deduped = cls.dedup_df(loaded_df)
                    entry = (weakref.ref(loaded_df), None if deduped is loaded_df else deduped)
                    cls._put_lru(cls._sheet_df_cache, cache_key, entry, cls._MAX_SHEETS, owner_obj=loaded_df)
                    return deduped
            except Exception as e:
                print(f"[DataMemoryCache] Ошибка чтения листа {f_clean} / {s_clean}: {e}")

        # 3. Запасной вариант
        if fallback_df is not None:
            return cls.dedup_df(fallback_df)

        if manager is not None and hasattr(manager, "get_all"):
            entries = manager.get_all()
            if entries:
                first_df = getattr(entries[0].data, "dataframe", None)
                if first_df is not None:
                    return cls.dedup_df(first_df)

        return None

    @classmethod
    def get_str_series(cls, df: pd.DataFrame, col_name: str) -> pd.Series:
        key = (id(df), len(df), str(col_name))
        with cls._lock:
            cached = cls._str_series_cache.get(key)
            if cached is not None:
                cls._str_series_cache.move_to_end(key)
                return cached
        s = _ensure_series(df[col_name])
        res = s.fillna("").astype(str).str.strip()
        cls._put_lru(cls._str_series_cache, key, res, cls._MAX_SERIES, owner_obj=df)
        return res

    @classmethod
    def get_unique_values(cls, df: pd.DataFrame, col_name: str, limit: int = 100) -> list[str]:
        if df is None or col_name not in df.columns:
            return []
        key = (id(df), len(df), str(col_name), int(limit))
        with cls._lock:
            cached = cls._unique_vals_cache.get(key)
            if cached is not None:
                cls._unique_vals_cache.move_to_end(key)
                return cached
        s = cls.get_str_series(df, col_name)
        vals = [v for v in s.unique().tolist() if v and v != "nan" and v != "None"][:limit]
        cls._put_lru(cls._unique_vals_cache, key, vals, cls._MAX_UNIQUE, owner_obj=df)
        return vals

    @classmethod
    def get_filter_payload(cls, key):
        with cls._lock:
            val = cls._filter_df_cache.get(key)
            if val is not None:
                cls._filter_df_cache.move_to_end(key)
            return val

    @classmethod
    def set_filter_payload(cls, key, value, owner_obj=None):
        cls._put_lru(cls._filter_df_cache, key, value, cls._MAX_FILTER_DF, owner_obj=owner_obj)

    @classmethod
    def get_render_html(cls, key: str, expected_sig: str) -> str | None:
        with cls._lock:
            entry = cls._render_html_cache.get(key)
            if entry is not None and entry[0] == expected_sig:
                cls._render_html_cache.move_to_end(key)
                return entry[1]
            return None

    @classmethod
    def set_render_html(cls, key: str, sig: str, html: str, owner_obj=None):
        cls._put_lru(cls._render_html_cache, key, (sig, html), cls._MAX_RENDER_HTML, owner_obj=owner_obj)


def _dedup_dataframe_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Убирает дубликаты названий столбцов в DataFrame через оперативный кэш."""
    return DataMemoryCache.dedup_df(df)


def _to_num_series(s: pd.Series) -> pd.Series:
    """Переводит серию в конечные числа (без NaN/Inf) с авто-очисткой кэша."""
    s = _ensure_series(s)
    cache_key = (id(s), len(s), str(getattr(s, "name", "")))
    with DataMemoryCache._lock:
        cached = DataMemoryCache._num_series_cache.get(cache_key)
        if cached is not None:
            DataMemoryCache._num_series_cache.move_to_end(cache_key)
            return cached

    if pd.api.types.is_numeric_dtype(s):
        res = s.replace([np.inf, -np.inf], 0).fillna(0)
    else:
        cleaned = (
            s.astype(str)
            .str.replace("\u00a0", "", regex=False)
            .str.replace(" ", "", regex=False)
            .str.replace(",", ".", regex=False)
        )
        res = pd.to_numeric(cleaned, errors="coerce").replace([np.inf, -np.inf], 0).fillna(0)

    DataMemoryCache._put_lru(DataMemoryCache._num_series_cache, cache_key, res, DataMemoryCache._MAX_SERIES, owner_obj=s)
    return res


def _to_float(val) -> float:
    if pd.isna(val):
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).replace("\u00a0", "").replace(" ", "").replace(",", ".").strip()
    try:
        return float(s)
    except Exception:
        return 0.0


def _evaluate_macros(text: str, df: object) -> str:
    """Ищет в тексте классические макросы count(), sum(col), mean(col), оставляя логические переменные для ParagraphBlock."""
    if not isinstance(text, str) or "{{" not in text:
        return text

    def replace_match(match):
        expr = match.group(1).strip()
        try:
            if expr.lower() == "count()":
                if df is None or not hasattr(df, "columns"):
                    return "0"
                return f"{len(df):,}".replace(",", " ")

            m_sum = re.match(r"^sum\((.*?)\)$", expr, re.IGNORECASE)
            if m_sum:
                if df is None or not hasattr(df, "columns"):
                    return "0"
                col = m_sum.group(1).strip().strip("'\"")
                if col in df.columns:
                    val = _to_num_series(df[col]).sum()
                    return f"{val:,.2f}".replace(",", " ")
                return f"[Колонка '{col}' не найдена]"

            m_mean = re.match(r"^mean\((.*?)\)$", expr, re.IGNORECASE)
            if m_mean:
                if df is None or not hasattr(df, "columns"):
                    return "0"
                col = m_mean.group(1).strip().strip("'\"")
                if col in df.columns:
                    val = _to_num_series(df[col]).mean()
                    return f"{val:,.2f}".replace(",", " ")
                return f"[Колонка '{col}' не найдена]"

            # Оставляем все динамические переменные ({{ group }}, {{ fact }}, {{ if(...) }}) для _eval_paragraph_template_py
            return match.group(0)
        except Exception:
            return match.group(0)

    return re.sub(r"\{\{(.*?)\}\}", replace_match, text)


# ============================================================
# Базовый блок
# ============================================================

@dataclass
class Block:
    """Базовый блок отчёта."""
    id: str
    type: str
    title: str = ""

    width: int = 100
    margin_top: int = 0
    margin_bottom: int = 14
    min_height: int = 0

    def render(self) -> str:
        return f"<!-- block {self.id}: {self.type} -->"

    def wrap_layout(self, inner_html: str) -> str:
        width = self.width
        style = (
            f"flex: 0 0 {width}%; "
            f"max-width: {width}%; "
            f"width: {width}%; "
            f"margin-top: {self.margin_top}px; "
            f"margin-bottom: {self.margin_bottom}px; "
            f"box-sizing: border-box;"
        )
        if self.min_height and self.min_height > 0:
            style += f" min-height: {self.min_height}px;"
            style += " display: flex; flex-direction: column;"

        return f'<div class="layout-item" style="{style}">{inner_html}</div>'


# ============================================================
# Текстовые блоки
# ============================================================

@dataclass
class SectionTitleBlock(Block):
    type: str = "section_title"
    raw_html: bool = False
    font_size: int = 24
    text_align: str = "left"

    def render(self) -> str:
        if self.raw_html:
            title = _extract_body(self.title)
        else:
            title = _escape(self.title)
        
        style = f"font-size: {self.font_size}px; text-align: {self.text_align}; margin: 0;"
        inner = f'<h1 class="section-title" id="{self.id}" style="{style}">{title}</h1>'
        return self.wrap_layout(inner)


def _eval_paragraph_template_py(template_str: str, ctx_vars: dict) -> str:
    """Вычисляет макросы {{ ... }}, включая логические выражения if(...) / если(...) и математику."""
    if not isinstance(template_str, str) or "{{" not in template_str:
        return template_str

    def _fmt_num(v: float) -> str:
        if abs(v - round(v)) < 1e-6:
            return f"{int(round(v)):,}".replace(",", " ")
        return f"{v:,.2f}".replace(",", " ")

    def _if_func(cond, true_val, false_val=""):
        return str(true_val) if bool(cond) else str(false_val)

    env = {
        "__builtins__": {},
        "if": _if_func,
        "IF": _if_func,
        "если": _if_func,
        "ЕСЛИ": _if_func,
        "abs": abs,
        "round": round,
        "min": min,
        "max": max,
        "str": str,
        "float": float,
        "int": int,
        "A": float(ctx_vars.get("raw_fact", 0.0)),
        "B": float(ctx_vars.get("raw_norm", 0.0)),
        "raw_fact": float(ctx_vars.get("raw_fact", 0.0)),
        "raw_norm": float(ctx_vars.get("raw_norm", 0.0)),
        "raw_diff": float(ctx_vars.get("raw_diff", 0.0)),
        "pct": float(ctx_vars.get("raw_pct", 0.0)),
        "процент": float(ctx_vars.get("raw_pct", 0.0)),
        "abs_pct": str(ctx_vars.get("abs_pct", "0.00")),
        "fact": str(ctx_vars.get("fact", "0")),
        "факт": str(ctx_vars.get("fact", "0")),
        "norm": str(ctx_vars.get("norm", "0")),
        "норматив": str(ctx_vars.get("norm", "0")),
        "diff": str(ctx_vars.get("diff", "0")),
        "разница": str(ctx_vars.get("diff", "0")),
        "abs_diff": str(ctx_vars.get("abs_diff", "0")),
        "count": int(ctx_vars.get("raw_count", 0)),
        "колво": int(ctx_vars.get("raw_count", 0)),
        "group": str(ctx_vars.get("group", "Все категории")),
        "тип_тс": str(ctx_vars.get("group", "Все категории")),
        "month": str(ctx_vars.get("month", "Весь период")),
        "месяц": str(ctx_vars.get("month", "Весь период")),
        "top_name": str(ctx_vars.get("top_name", "—")),
        "лидер": str(ctx_vars.get("top_name", "—")),
        "top_pct": str(ctx_vars.get("top_pct", "0.00")),
        "top_diff": str(ctx_vars.get("top_diff", "0")),
    }

    def _replace(match):
        raw_expr = match.group(1)
        # Убираем HTML-теги и раскодируем HTML-сущности (&gt;, &lt;, &quot;, &#39;), если текст редактировали в RichTextDialog
        clean_expr = re.sub(r"<[^>]+>", "", raw_expr)
        clean_expr = (
            clean_expr.replace("&gt;", ">")
            .replace("&lt;", "<")
            .replace("&amp;", "&")
            .replace("&quot;", '"')
            .replace("&#39;", "'")
            .replace("&nbsp;", " ")
            .replace("«", '"')
            .replace("»", '"')
            .strip()
        )
        if not clean_expr:
            return ""
        low = clean_expr.lower()
        if low in ("pct", "процент"):
            return str(ctx_vars.get("pct", "0.00"))
        if low in ("count", "колво"):
            return str(ctx_vars.get("count", "0"))
        if clean_expr in env and isinstance(env[clean_expr], str):
            return env[clean_expr]
        if low in env and isinstance(env[low], str):
            return env[low]

        py_expr = clean_expr.replace(";", ",")
        py_expr = re.sub(r"\b(if|IF|если|ЕСЛИ)\s*\(", "_if_call(", py_expr)
        env["_if_call"] = _if_func
        try:
            val = eval(py_expr, {"__builtins__": {}}, env)
            if isinstance(val, float):
                return _fmt_num(val)
            return str(val)
        except Exception:
            return ""

    return re.sub(r"\{\{([\s\S]*?)\}\}", _replace, template_str)


@dataclass
class ParagraphBlock(Block):
    type: str = "paragraph"
    text: str = ""
    raw_html: bool = False
    font_size: int = 14
    text_align: str = "left"

    def _build_dynamic_matrix(self, df: pd.DataFrame, cfg: dict, report_obj) -> dict | None:
        """Строит матрицу значений (Группа ТС × Месяц) для синхронизации текста со срезами."""
        if df is None or len(df) == 0:
            return None

        target_chart_id = cfg.get("target_chart", "")
        chart_cfg = {}
        if report_obj and hasattr(report_obj, "sections"):
            for sec in report_obj.sections:
                for b in _iter_all_report_blocks(sec.blocks):
                    b_type = b.get("type") if isinstance(b, dict) else getattr(b, "type", "")
                    b_id = b.get("id") if isinstance(b, dict) else getattr(b, "id", "")
                    if b_type == "plotly_chart":
                        c_cfg = b.get("config", {}) if isinstance(b, dict) else (getattr(b, "config", {}) or {})
                        if target_chart_id and b_id == target_chart_id:
                            chart_cfg = c_cfg
                            break
                        elif not chart_cfg and (c_cfg.get("fact_col") or c_cfg.get("parent_group_col")):
                            chart_cfg = c_cfg
                if target_chart_id and chart_cfg:
                    break

        p_col = cfg.get("parent_group_col") or chart_cfg.get("parent_group_col") or chart_cfg.get("x_col") or ""
        m_col = cfg.get("model_col") or chart_cfg.get("model_col") or chart_cfg.get("x_col") or ""
        d_col = cfg.get("date_col") or chart_cfg.get("date_col") or ""
        f_col = cfg.get("fact_col") or chart_cfg.get("fact_col") or ""
        n_col = cfg.get("norm_col") or chart_cfg.get("norm_col") or ""

        work = DataMemoryCache.dedup_df(df).copy()
        cols_str = [str(c) for c in work.columns]

        # Автоподстановка колонок из таблицы, если они не заданы явно
        if not p_col or p_col not in work.columns:
            for cand in cols_str:
                if "тип" in cand.lower() or "групп" in cand.lower() or "категор" in cand.lower():
                    p_col = cand
                    break
            if not p_col and cols_str:
                p_col = cols_str[0]

        if not m_col or m_col not in work.columns:
            for cand in cols_str:
                if "марк" in cand.lower() or "модел" in cand.lower() or "авто" in cand.lower():
                    m_col = cand
                    break
            if not m_col:
                m_col = p_col

        if not d_col or d_col not in work.columns:
            for cand in cols_str:
                if "дат" in cand.lower() or "месяц" in cand.lower() or "период" in cand.lower():
                    d_col = cand
                    break

        if not f_col or f_col not in work.columns:
            for cand in cols_str:
                if "факт" in cand.lower():
                    f_col = cand
                    break

        if not n_col or n_col not in work.columns:
            for cand in cols_str:
                if "норм" in cand.lower() or "план" in cand.lower() or "реглам" in cand.lower():
                    n_col = cand
                    break
        # Если параграф привязан к графику, применяем умный фильтр этого графика
        if chart_cfg and (chart_cfg.get("filter_col") or chart_cfg.get("custom_query") or chart_cfg.get("filter_from_chart")):
            try:
                dummy_c = PlotlyChartBlock(
                    id=target_chart_id or "linked",
                    type="plotly_chart",
                    parent_group_col=p_col,
                    x_col=chart_cfg.get("x_col", ""),
                    filter_from_chart=chart_cfg.get("filter_from_chart", ""),
                    filter_col=chart_cfg.get("filter_col", ""),
                    filter_op=chart_cfg.get("filter_op", ">"),
                    filter_val=chart_cfg.get("filter_val", ""),
                    custom_query=chart_cfg.get("custom_query", ""),
                )
                dummy_c._report_ref = report_obj
                dummy_c._file_manager = getattr(self, "_file_manager", None)
                work = dummy_c._apply_smart_filter(work)
            except Exception:
                pass
        work["_f"] = _to_num_series(work[f_col]) if (f_col and f_col in work.columns) else 0.0
        work["_n"] = _to_num_series(work[n_col]) if (n_col and n_col in work.columns) else 0.0
        work["_grp"] = DataMemoryCache.get_str_series(work, p_col) if (p_col and p_col in work.columns) else "Все категории"
        work["_sub"] = DataMemoryCache.get_str_series(work, m_col) if (m_col and m_col in work.columns and m_col != p_col) else work["_grp"]

        if d_col and d_col in work.columns:
            m_names, m_nums = _extract_month_info(work[d_col])
            work["_m_name"] = m_names
            work["_m_num"] = m_nums
            months_list = (
                work[work["_m_name"] != ""][["_m_num", "_m_name"]]
                .drop_duplicates()
                .sort_values(by=["_m_num", "_m_name"])["_m_name"]
                .tolist()
            )
        else:
            work["_m_name"] = "Весь период"
            months_list = []

        def _fmt(v: float) -> str:
            return f"{v:,.2f}".replace(",", " ")

        def _calc_cell(sub_df: pd.DataFrame, grp_label: str, m_label: str, sub_col_key: str) -> dict:
            cnt = int(len(sub_df))
            f_sum = float(sub_df["_f"].sum()) if cnt > 0 else 0.0
            n_sum = float(sub_df["_n"].sum()) if cnt > 0 else 0.0
            diff_val = f_sum - n_sum
            pct_val = ((f_sum - n_sum) / n_sum * 100.0) if abs(n_sum) > 1e-9 else 0.0

            top_name = "—"
            top_pct = 0.0
            top_diff = 0.0
            if cnt > 0 and sub_col_key in sub_df.columns:
                grp_s = sub_df.groupby(sub_col_key, sort=False)[["_f", "_n"]].sum()
                if len(grp_s) > 0:
                    grp_s["_d"] = grp_s["_f"] - grp_s["_n"]
                    grp_s["_abs_d"] = grp_s["_d"].abs()
                    best_row = grp_s.sort_values(by="_abs_d", ascending=False).iloc[0]
                    top_name = str(best_row.name)
                    top_diff = float(best_row["_d"])
                    b_n = float(best_row["_n"])
                    top_pct = (( float(best_row["_f"]) - b_n) / b_n * 100.0) if abs(b_n) > 1e-9 else 0.0

            return {
                "group": grp_label,
                "month": m_label,
                "raw_fact": round(f_sum, 4),
                "raw_norm": round(n_sum, 4),
                "raw_diff": round(diff_val, 4),
                "raw_pct": round(pct_val, 2),
                "raw_count": cnt,
                "fact": _fmt(f_sum),
                "norm": _fmt(n_sum),
                "diff": f"{diff_val:+,.2f}".replace(",", " "),
                "abs_diff": _fmt(abs(diff_val)),
                "pct": f"{pct_val:+.2f}",
                "abs_pct": f"{abs(pct_val):.2f}",
                "count": f"{cnt:,}".replace(",", " "),
                "top_name": top_name,
                "top_pct": f"{top_pct:+.2f}",
                "top_diff": f"{top_diff:+,.2f}".replace(",", " "),
            }

        matrix = {"ALL": {}}
        matrix["ALL"]["ALL_MONTHS"] = _calc_cell(work, "Все категории", "Весь период", "_grp")
        for m_name in months_list:
            m_df = work[work["_m_name"] == m_name]
            matrix["ALL"][m_name] = _calc_cell(m_df, "Все категории", m_name, "_grp")

        top_groups = [g for g in work["_grp"].value_counts().head(50).index.tolist() if g]
        for g_name in top_groups:
            g_df = work[work["_grp"].str.lower() == g_name.lower()]
            matrix[g_name] = {}
            matrix[g_name]["ALL_MONTHS"] = _calc_cell(g_df, g_name, "Весь период", "_sub")
            for m_name in months_list:
                gm_df = g_df[g_df["_m_name"] == m_name]
                matrix[g_name][m_name] = _calc_cell(gm_df, g_name, m_name, "_sub")

        return matrix

    def render(self, dataframe=None) -> str:
        report_obj, own_cfg = _find_report_and_config(self)
        if report_obj is not None:
            self._report_ref = report_obj
        for k, v in own_cfg.items():
            if hasattr(self, k) and k not in ("id", "type", "dataframe", "width", "margin_top", "margin_bottom", "min_height"):
                setattr(self, k, v)

        manager = getattr(self, "_file_manager", None)
        if not manager and report_obj and hasattr(report_obj, "file_manager"):
            manager = report_obj.file_manager

        source_file_name = own_cfg.get("source_file_name", "")
        source_sheet = own_cfg.get("source_sheet", "") or own_cfg.get("source_file", "")
        df_work = DataMemoryCache.get_dataframe(manager, source_file_name, source_sheet, fallback_df=dataframe)

        # Сначала вычисляем классические макросы count(), sum(col), mean(col)
        base_text = _evaluate_macros(self.text, df_work)
        dyn_matrix = self._build_dynamic_matrix(df_work, own_cfg, report_obj) if "{{" in base_text else None

        if dyn_matrix and "ALL" in dyn_matrix and "ALL_MONTHS" in dyn_matrix["ALL"]:
            rendered_text = _eval_paragraph_template_py(base_text, dyn_matrix["ALL"]["ALL_MONTHS"])
        else:
            rendered_text = base_text

        if self.raw_html:
            content = _extract_body(rendered_text)
            if not content.strip():
                content = "<p></p>"
        else:
            safe = _escape(rendered_text)
            paragraphs = [
                f"<p style='margin-bottom: 8px;'>{p.strip()}</p>"
                for p in safe.split("\n\n")
                if p.strip()
            ]
            content = "".join(paragraphs) if paragraphs else "<p></p>"

        para_id = f"ea-para-{self.id}"
        dyn_script = ""
        if dyn_matrix:
            matrix_json = json.dumps(dyn_matrix, ensure_ascii=False)
            raw_tpl_json = json.dumps(base_text, ensure_ascii=False)
            is_raw_flag = "true" if self.raw_html else "false"
            dyn_script = f"""
            <script type="application/json" id="{para_id}-matrix">{matrix_json}</script>
            <script type="application/json" id="{para_id}-tpl">{raw_tpl_json}</script>
            <script>
            if (typeof window.syncDynamicParagraphs === 'undefined') {{
                window._eaActiveGroup = window._eaActiveGroup || 'ALL';
                window._eaActiveMonth = window._eaActiveMonth || 'ALL_MONTHS';

                window._evalEaParagraph = function(tpl, ctx) {{
                    return tpl.replace(/\\{{\\{{([\\s\\S]*?)\\}}\\}}/g, function(full, rawExpr) {{
                        var expr = rawExpr.replace(/<[^>]+>/g, '')
                                          .replace(/&gt;/g, '>')
                                          .replace(/&lt;/g, '<')
                                          .replace(/&amp;/g, '&')
                                          .replace(/&quot;/g, '"')
                                          .replace(/&#39;/g, "'")
                                          .replace(/&nbsp;/g, ' ')
                                          .trim();
                        if (!expr) return '';
                        var low = expr.toLowerCase();
                        if (low === 'pct' || low === 'процент') return String(ctx.pct);
                        if (low === 'count' || low === 'колво') return String(ctx.count);
                        if (Object.prototype.hasOwnProperty.call(ctx, expr)) return String(ctx[expr]);
                        if (Object.prototype.hasOwnProperty.call(ctx, low)) return String(ctx[low]);

                        try {{
                            var jsExpr = expr.replace(/;/g, ',');
                            jsExpr = jsExpr.replace(/\\b(if|IF|если|ЕСЛИ)\\s*\\(/g, '_IF(');
                            var fn = new Function(
                                '_IF', 'abs', 'round', 'A', 'B', 'pct', 'процент', 'abs_pct',
                                'fact', 'факт', 'norm', 'норматив', 'diff', 'разница', 'abs_diff',
                                'count', 'колво', 'group', 'тип_тс', 'month', 'месяц',
                                'top_name', 'лидер', 'top_pct', 'top_diff',
                                'return (' + jsExpr + ');'
                            );
                            var res = fn(
                                function(c, t, f) {{ return c ? (t !== undefined ? t : '') : (f !== undefined ? f : ''); }},
                                Math.abs,
                                function(v, d) {{ var p = Math.pow(10, d || 0); return Math.round(v * p) / p; }},
                                Number(ctx.raw_fact || 0),
                                Number(ctx.raw_norm || 0),
                                Number(ctx.raw_pct || 0),
                                Number(ctx.raw_pct || 0),
                                String(ctx.abs_pct || '0.00'),
                                String(ctx.fact || '0'),
                                String(ctx.fact || '0'),
                                String(ctx.norm || '0'),
                                String(ctx.norm || '0'),
                                String(ctx.diff || '0'),
                                String(ctx.diff || '0'),
                                String(ctx.abs_diff || '0'),
                                Number(ctx.raw_count || 0),
                                Number(ctx.raw_count || 0),
                                String(ctx.group || 'Все категории'),
                                String(ctx.group || 'Все категории'),
                                String(ctx.month || 'Весь период'),
                                String(ctx.month || 'Весь период'),
                                String(ctx.top_name || '—'),
                                String(ctx.top_name || '—'),
                                String(ctx.top_pct || '0.00'),
                                String(ctx.top_diff || '0')
                            );
                            return res !== undefined && res !== null ? String(res) : '';
                        }} catch (e) {{
                            return full;
                        }}
                    }});
                }};

                window.syncDynamicParagraphs = function(groupOverride, monthOverride, targetPlotId) {{
                    document.querySelectorAll('.ea-dynamic-paragraph').forEach(function(el) {{
                        var boundPlotId = el.getAttribute('data-target-plot') || '';
                        if (targetPlotId && boundPlotId && boundPlotId !== targetPlotId) {{
                            return;
                        }}
                        if (groupOverride !== undefined && groupOverride !== null) {{
                            el._activeGroup = groupOverride;
                        }}
                        if (monthOverride !== undefined && monthOverride !== null) {{
                            el._activeMonth = monthOverride;
                        }}
                        var curG = el._activeGroup || 'ALL';
                        var curM = el._activeMonth || 'ALL_MONTHS';

                        var pid = el.getAttribute('data-para-id');
                        var matEl = document.getElementById(pid + '-matrix');
                        var tplEl = document.getElementById(pid + '-tpl');
                        if (!matEl || !tplEl) return;
                        try {{
                            var mat = JSON.parse(matEl.textContent);
                            var tpl = JSON.parse(tplEl.textContent);
                            var grpObj = mat[curG];
                            if (!grpObj && curG !== 'ALL') {{
                                var normG = String(curG).trim().toLowerCase();
                                Object.keys(mat).forEach(function(k) {{
                                    if (String(k).trim().toLowerCase() === normG) grpObj = mat[k];
                                }});
                            }}
                            if (!grpObj) grpObj = mat['ALL'];
                            if (!grpObj) return;
                            var cell = grpObj[curM] || grpObj['ALL_MONTHS'];
                            if (!cell) return;

                            var evaluated = window._evalEaParagraph(tpl, cell);
                            if (el.getAttribute('data-raw-html') === 'true') {{
                                el.innerHTML = evaluated;
                            }} else {{
                                var parts = evaluated.split(/\\n\\n+/).filter(function(p) {{ return p.trim().length > 0; }});
                                el.innerHTML = parts.map(function(p) {{
                                    var safe = p.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\\n/g, '<br>');
                                    return "<p style='margin-bottom: 8px;'>" + safe + "</p>";
                                }}).join('') || '<p></p>';
                            }}
                            el.classList.remove('ea-anim-refresh');
                            void el.offsetWidth;
                            el.classList.add('ea-anim-refresh');
                        }} catch (err) {{}}
                    }});
                }};
            }}
            </script>
            """

        style = f"font-size: {self.font_size}px; text-align: {self.text_align};"
        dyn_cls = "paragraph ea-dynamic-paragraph" if dyn_matrix else "paragraph"
        is_raw_attr = "true" if self.raw_html else "false"
        target_plot_attr = f"ea-plotly-{own_cfg.get('target_chart', '')}" if own_cfg.get("target_chart") else ""
        inner = (
            f'<div class="block">'
            f'<div class="block-card" style="{style}">'
            f'<div class="{dyn_cls}" id="{para_id}" data-para-id="{para_id}" '
            f'data-target-plot="{target_plot_attr}" data-raw-html="{is_raw_attr}">{content}</div>'
            f'</div>{dyn_script}</div>'
        )
        return self.wrap_layout(inner)


@dataclass
class ListBlock(Block):
    type: str = "list"
    items: list[str] = field(default_factory=list)
    html: str = ""
    raw_html: bool = False
    font_size: int = 14
    text_align: str = "left"

    def render(self) -> str:
        if self.raw_html and self.html.strip():
            content = _extract_body(self.html)
        else:
            items_html = "".join(
                f"<li>{_escape(item)}</li>" for item in self.items
            )
            content = f'<ul class="block-list">{items_html}</ul>'

        style = f"font-size: {self.font_size}px; text-align: {self.text_align};"
        inner = (
            f'<div class="block">'
            f'<div class="block-card" style="{style}">'
            f'<div class="list-rich">{content}</div>'
            f'</div></div>'
        )
        return self.wrap_layout(inner)


@dataclass
class DividerBlock(Block):
    type: str = "divider"

    def render(self) -> str:
        return '<div class="section-divider"></div>'


# ============================================================
# KPI-блоки
# ============================================================

@dataclass
class KpiCard:
    label: str
    value: str
    accent: bool = False


@dataclass
class KpiRowBlock(Block):
    type: str = "kpi_row"
    cards: list[KpiCard] = field(default_factory=list)

    def render(self) -> str:
        cards_html = []
        for card in self.cards:
            accent_class = " accent" if card.accent else ""
            cards_html.append(
                f'<div class="kpi-card">'
                f'<div class="kpi-value{accent_class}">{_escape(card.value)}</div>'
                f'<div class="kpi-label">{_escape(card.label)}</div>'
                f'</div>'
            )
        inner = (
            f'<div class="block">'
            f'<div class="kpi-row">{"".join(cards_html)}</div>'
            f'</div>'
        )
        return self.wrap_layout(inner)


# ============================================================
# Таблица данных (Реестр путевых листов с хэш-индексом и скроллами)
# ============================================================

@dataclass
class DataTableBlock(Block):
    type: str = "data_table"
    dataframe: object = None
    source_file_name: str = ""
    source_sheet: str = ""
    title: str = "Таблица данных"
    max_rows: int = 20
    visible_columns: list[str] | None = None
    preview_limit: int = 0

    def render(self) -> str:
        import hashlib

        report_obj, own_cfg = _find_report_and_config(self)
        if report_obj is not None:
            self._report_ref = report_obj
        for k, v in own_cfg.items():
            if hasattr(self, k) and k not in ("id", "type", "dataframe", "width", "margin_top", "margin_bottom", "min_height"):
                setattr(self, k, v)

        manager = getattr(self, "_file_manager", None)
        if not manager and report_obj and hasattr(report_obj, "file_manager"):
            manager = report_obj.file_manager

        df = DataMemoryCache.get_dataframe(
            manager, self.source_file_name, self.source_sheet or own_cfg.get("source_file", ""), fallback_df=self.dataframe
        )
        if df is None or len(df) == 0:
            return self.wrap_layout(self._render_empty())

        if self.visible_columns is None:
            cols = [str(c) for c in df.columns]
        else:
            cols = [str(c) for c in self.visible_columns if c in df.columns]
        if not cols:
            return self.wrap_layout(self._render_empty())

        total_rows = len(df)
        hard_cap = self.preview_limit if self.preview_limit and self.preview_limit > 0 else 100000
        truncated = total_rows > hard_cap

        # 1. Вычисляем хэш источника данных и настроек блока
        raw_df_sig = f"{id(df)}_{total_rows}_{'|'.join(cols)}_{hard_cap}_v2"
        data_hash = hashlib.md5(raw_df_sig.encode("utf-8")).hexdigest()[:16]

        block_render_sig = f"{self.id}_{data_hash}_{self.title}_{self.max_rows}_{self.width}_{self.min_height}"
        html_cache_key = f"dt_html_{self.id}"

        cached_html = DataMemoryCache.get_render_html(html_cache_key, block_render_sig)
        if cached_html is not None:
            return cached_html

        # 2. Берём готовый хэш-пакет данных из RAM-кэша или строим его 1 раз
        payload_cache_key = ("dt_hash_payload", data_hash)
        payload_json = DataMemoryCache.get_filter_payload(payload_cache_key)

        if payload_json is None:
            work_df = df[cols].head(hard_cap) if truncated else df[cols]

            formatted_cols = []
            for col in cols:
                s = work_df[col]
                if pd.api.types.is_float_dtype(s):
                    formatted_cols.append(
                        [
                            "—" if pd.isna(v) else (f"{v:.4f}".rstrip("0").rstrip(".") if abs(v) < 1 and v != 0 else f"{v:,.2f}")
                            for v in s.tolist()
                        ]
                    )
                elif pd.api.types.is_integer_dtype(s) and not pd.api.types.is_bool_dtype(s):
                    formatted_cols.append(["—" if pd.isna(v) else f"{int(v):,}" for v in s.tolist()])
                else:
                    formatted_cols.append(["—" if pd.isna(v) else str(v).strip() for v in s.tolist()])

            rows_matrix = [list(r) for r in zip(*formatted_cols)] if formatted_cols else []

            # Таблица приведения латинских букв к кириллическим для безошибочного поиска госномеров
            lat_to_cyr = str.maketrans("abekmhopctyx", "авекмнорстух")

            def _norm_key(s_val: str) -> str:
                return s_val.lower().translate(lat_to_cyr)

            # Строим хэш-индекс (ключ -> список индексов строк) по всем текстовым/ключевым колонкам
            hash_index: dict[str, list[int]] = {}
            key_col_indices = []
            for idx_c, c_name in enumerate(cols):
                c_low = c_name.lower()
                if any(w in c_low for w in ("гос", "номер", "грз", "марк", "модел", "тип", "месяц", "гараж", "колон", "заявк", "ТС")):
                    key_col_indices.append(idx_c)
            if not key_col_indices:
                key_col_indices = list(range(len(cols)))

            for r_idx, row_vals in enumerate(rows_matrix):
                for c_idx in key_col_indices:
                    val_str = row_vals[c_idx]
                    if val_str and val_str != "—":
                        for k_cand in (val_str.lower(), _norm_key(val_str)):
                            bucket = hash_index.get(k_cand)
                            if bucket is None:
                                hash_index[k_cand] = [r_idx]
                            elif bucket[-1] != r_idx:
                                bucket.append(r_idx)

            payload_json = json.dumps(
                {
                    "hash": data_hash,
                    "cols": cols,
                    "rows": rows_matrix,
                    "hash_index": hash_index,
                    "total_rows": total_rows,
                    "loaded_rows": len(rows_matrix),
                    "truncated": truncated,
                    "hard_cap": hard_cap,
                },
                ensure_ascii=False,
            )
            DataMemoryCache.set_filter_payload(payload_cache_key, payload_json, owner_obj=df)

        tbl_id = f"ea-tbl-{self.id}"
        max_rows_val = int(self.max_rows) if self.max_rows is not None else 20
        vis_rows = min(max_rows_val, 30) if max_rows_val > 0 else 18
        max_window_h = 44 + vis_rows * 33 if max_rows_val > 0 else 560
        if max_window_h < 180:
            max_window_h = 180

        info = f"Всего записей в реестре: {total_rows:,}.".replace(",", " ")
        if truncated:
            info = f"⚠ В хэш-реестр загружены первые {hard_cap:,} из {total_rows:,} записей.".replace(",", " ")

        title_html = ""
        if self.title and str(self.title).strip():
            title_html = (
                f'<div style="font-weight:700; font-size:13.5px; color:#003F0B; margin-right:12px;">'
                f'📋 {_escape(str(self.title).strip())}</div>'
            )

        thead_ths = ['<th class="ea-reg-num-th">№</th>'] + [
            f"<th>{_escape(str(c))}</th>" for c in cols
        ]

        style_css = f"""
        <style>
        #{tbl_id}-wrap {{
            width: 100%;
            max-width: 100%;
            max-height: {max_window_h}px;
            overflow-x: auto !important;
            overflow-y: auto !important;
            border-top: 1px solid #e2e8f0;
            border-bottom: 1px solid #e2e8f0;
            background: #ffffff;
            position: relative;
            scrollbar-width: auto;
            scrollbar-color: #94a3b8 #f1f5f9;
        }}
        #{tbl_id}-wrap::-webkit-scrollbar {{
            width: 11px;
            height: 11px;
        }}
        #{tbl_id}-wrap::-webkit-scrollbar-track {{
            background: #f1f5f9;
            border-radius: 6px;
        }}
        #{tbl_id}-wrap::-webkit-scrollbar-thumb {{
            background: #94a3b8;
            border-radius: 6px;
            border: 2px solid #f1f5f9;
        }}
        #{tbl_id}-wrap::-webkit-scrollbar-thumb:hover {{
            background: #87C800;
        }}
        #{tbl_id}-wrap::-webkit-scrollbar-corner {{
            background: #f1f5f9;
        }}
        .ea-reg-table {{
            width: max-content;
            min-width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            font-size: 12.5px;
            color: #1e293b;
        }}
        .ea-reg-table th, .ea-reg-table td {{
            border-right: 1px solid #e2e8f0;
            border-bottom: 1px solid #e2e8f0;
            padding: 6px 12px;
            white-space: nowrap;
            text-align: left;
        }}
        .ea-reg-table thead th {{
            position: sticky;
            top: 0;
            z-index: 4;
            background: #f8fafc;
            color: #334155;
            font-weight: 700;
            box-shadow: inset 0 -1px 0 #cbd5e1;
        }}
        .ea-reg-table th.ea-reg-num-th,
        .ea-reg-table td.ea-reg-num-td {{
            position: sticky;
            left: 0;
            z-index: 3;
            background: #f8fafc;
            color: #64748b;
            text-align: center;
            font-weight: 600;
            width: 46px;
            min-width: 46px;
            box-shadow: inset -1px 0 0 #cbd5e1;
        }}
        .ea-reg-table thead th.ea-reg-num-th {{
            z-index: 5;
        }}
        .ea-reg-table tbody tr:nth-child(even) td:not(.ea-reg-num-td) {{
            background: #fcfdfd;
        }}
        .ea-reg-table tbody tr:hover td {{
            background: #f1f8e9 !important;
        }}
        </style>
        """

        inner = f'''
        <div class="block" style="min-width:0; max-width:100%;">
            {style_css}
            <div class="block-card" style="padding:0; min-width:0; max-width:100%; overflow:hidden;">
                <div class="ea-table-toolbar"
                     style="padding: 10px 14px; background: #fafafa; display: flex; flex-wrap: wrap;
                            align-items: center; gap: 8px;">
                    {title_html}
                    <button type="button"
                            class="ea-table-search-btn"
                            data-target="{tbl_id}"
                            style="background: #fff; color: #333;
                                   border: 1px solid #d5d5db;
                                   border-radius: 6px; padding: 5px 12px;
                                   font-size: 12px; cursor: pointer;
                                   font-weight: 600;">
                        🔍  Поиск по таблице
                    </button>
                    <input type="text"
                           class="ea-table-search-input"
                           id="{tbl_id}-inp"
                           data-target="{tbl_id}"
                           placeholder="Поиск по значению, ID, категории или периоду..."
                           style="display:none; flex:1; min-width:220px;
                                  padding:5px 10px; font-size:12px;
                                  border:1px solid #87C800;
                                  border-radius:6px;
                                  outline:none; background:#fff;" />
                    <span id="{tbl_id}-badge"
                          style="display:none; background:#e9f5e9; color:#003F0B; border:1px solid #87C800;
                                 border-radius:6px; padding:4px 10px; font-size:12px; font-weight:700;">
                    </span>
                    <button type="button"
                            id="{tbl_id}-clear"
                            style="display:none; background:#fff1f2; color:#e11d48; border:1px solid #fecdd3;
                                   border-radius:6px; padding:4px 10px; font-size:11.5px; font-weight:600; cursor:pointer;">
                        ✕ Сбросить фильтр
                    </button>
                </div>
                <div id="{tbl_id}-wrap" class="ea-reg-scroll-wrap">
                    <table class="ea-reg-table" id="{tbl_id}">
                        <thead><tr>{"".join(thead_ths)}</tr></thead>
                        <tbody id="{tbl_id}-tbody"></tbody>
                    </table>
                </div>
                <div id="{tbl_id}-info"
                     style="padding:8px 14px; font-size:12px; color:#64748b;
                            background:#fafafa; font-weight:500;">
                    {info}
                </div>
            </div>
        </div>
        <script type="application/json" id="{tbl_id}-payload">{payload_json}</script>
        <script>
        (function() {{
            var wrapEl = document.getElementById("{tbl_id}-wrap");
            var tbodyEl = document.getElementById("{tbl_id}-tbody");
            var payloadEl = document.getElementById("{tbl_id}-payload");
            if (!wrapEl || !tbodyEl || !payloadEl) return;

            // Кэшируем распакованный реестр в глобальном JS-хэше по сигнатуре данных
            window._eaRegistryHashStore = window._eaRegistryHashStore || {{}};
            var rawPayload = JSON.parse(payloadEl.textContent);
            var storeKey = rawPayload.hash || "{tbl_id}";
            if (!window._eaRegistryHashStore[storeKey]) {{
                window._eaRegistryHashStore[storeKey] = {{
                    cols: rawPayload.cols || [],
                    rows: rawPayload.rows || [],
                    hashIndex: rawPayload.hash_index || {{}},
                    totalRows: rawPayload.total_rows || 0,
                    queryCache: {{}},
                    rowSearchStrings: null
                }};
            }}
            var store = window._eaRegistryHashStore[storeKey];
            payloadEl.textContent = ""; // Освобождаем память DOM

            var PAGE_SIZE = 150;
            var activeIndices = null; // null означает все строки
            var renderedCount = 0;

            function escHtml(s) {{
                return String(s)
                    .replace(/&/g, "&amp;")
                    .replace(/</g, "&lt;")
                    .replace(/>/g, "&gt;");
            }}

            function getTotalActive() {{
                return activeIndices === null ? store.rows.length : activeIndices.length;
            }}

            function renderNextBatch(reset) {{
                if (reset) {{
                    tbodyEl.innerHTML = "";
                    renderedCount = 0;
                    wrapEl.scrollTop = 0;
                }}
                var totalAct = getTotalActive();
                if (totalAct === 0) {{
                    if (reset) {{
                        tbodyEl.innerHTML = '<tr><td colspan="' + (store.cols.length + 1) + '" style="text-align:center; padding:24px; color:#94a3b8;">Записей по данному запросу не найдено</td></tr>';
                    }}
                    return;
                }}
                if (renderedCount >= totalAct) return;

                var endIdx = Math.min(renderedCount + PAGE_SIZE, totalAct);
                var htmlParts = [];
                for (var i = renderedCount; i < endIdx; i++) {{
                    var rowIdx = activeIndices === null ? i : activeIndices[i];
                    var rowArr = store.rows[rowIdx];
                    if (!rowArr) continue;
                    var tds = ['<td class="ea-reg-num-td">' + (i + 1) + '</td>'];
                    for (var c = 0; c < rowArr.length; c++) {{
                        tds.push('<td>' + escHtml(rowArr[c]) + '</td>');
                    }}
                    htmlParts.push('<tr>' + tds.join('') + '</tr>');
                }}
                tbodyEl.insertAdjacentHTML("beforeend", htmlParts.join(""));
                renderedCount = endIdx;
            }}

            // Подгрузка следующих строк при прокрутке вертикального скролла вниз
            wrapEl.addEventListener("scroll", function() {{
                if (wrapEl.scrollTop + wrapEl.clientHeight >= wrapEl.scrollHeight - 80) {{
                    renderNextBatch(false);
                }}
            }});

            var btn = document.querySelector('.ea-table-search-btn[data-target="{tbl_id}"]');
            var inp = document.getElementById("{tbl_id}-inp");
            var badge = document.getElementById("{tbl_id}-badge");
            var clearBtn = document.getElementById("{tbl_id}-clear");
            var infoEl = document.getElementById("{tbl_id}-info");

            function normPlateStr(s) {{
                var map = {{'a':'а','b':'в','e':'е','k':'к','m':'м','h':'н','o':'о','p':'р','c':'с','t':'т','y':'у','x':'х'}};
                return String(s || '').toLowerCase().replace(/[abekmhopctyx]/g, function(ch) {{ return map[ch] || ch; }});
            }}

            function lookupIndicesByHash(rawQLow) {{
                var qLow = normPlateStr(rawQLow);
                // 1. Мгновенная проверка в кэше выполненных запросов O(1)
                if (Object.prototype.hasOwnProperty.call(store.queryCache, qLow)) {{
                    return store.queryCache[qLow];
                }}
                if (Object.prototype.hasOwnProperty.call(store.hashIndex, rawQLow)) {{
                    store.queryCache[qLow] = store.hashIndex[rawQLow];
                    return store.hashIndex[rawQLow];
                }}
                // 2. Мгновенный поиск точного ключа (например, госномера О201ЕР136) в хэш-индексе O(1)
                if (Object.prototype.hasOwnProperty.call(store.hashIndex, qLow)) {{
                    var exactRes = store.hashIndex[qLow];
                    store.queryCache[qLow] = exactRes;
                    return exactRes;
                }}
                // 3. Проверка вхождения подстроки по ключам хэш-таблицы (быстрый поиск по части госномера/марки)
                var hashKeys = Object.keys(store.hashIndex);
                var matchedSet = {{}};
                var foundInHashKeys = false;
                for (var k = 0; k < hashKeys.length; k++) {{
                    var hk = hashKeys[k];
                    if (hk.indexOf(qLow) !== -1) {{
                        foundInHashKeys = true;
                        var arr = store.hashIndex[hk];
                        for (var a = 0; a < arr.length; a++) {{
                            matchedSet[arr[a]] = true;
                        }}
                    }}
                }}
                if (foundInHashKeys) {{
                    var resList = Object.keys(matchedSet).map(Number).sort(function(a, b) {{ return a - b; }});
                    store.queryCache[qLow] = resList;
                    return resList;
                }}
                // 4. Запасной полнотекстовый поиск с сохранением в хэш-кэш
                if (!store.rowSearchStrings) {{
                    store.rowSearchStrings = store.rows.map(function(r) {{
                        return r.join(" ").toLowerCase();
                    }});
                }}
                var fullRes = [];
                for (var i = 0; i < store.rowSearchStrings.length; i++) {{
                    if (store.rowSearchStrings[i].indexOf(qLow) !== -1) {{
                        fullRes.push(i);
                    }}
                }}
                store.queryCache[qLow] = fullRes;
                return fullRes;
            }}

            function applyTableFilter(rawQuery, fromPivot) {{
                var q = String(rawQuery || "").trim();
                var qLow = q.toLowerCase();

                if (!qLow) {{
                    activeIndices = null;
                    renderNextBatch(true);
                    if (badge) badge.style.display = "none";
                    if (clearBtn) clearBtn.style.display = "none";
                    if (infoEl) {{
                        infoEl.textContent = "Всего записей в реестре: " + store.totalRows.toLocaleString("ru-RU") + ".";
                    }}
                    if (!fromPivot && inp) inp.value = "";
                    return;
                }}

                activeIndices = lookupIndicesByHash(qLow);
                renderNextBatch(true);

                if (badge) {{
                    badge.textContent = (fromPivot ? "🔗 Фильтр из сводной: " : "🔍 Фильтр: ") + q + " (найдено: " + activeIndices.length + ")";
                    badge.style.display = "inline-block";
                }}
                if (clearBtn) clearBtn.style.display = "inline-block";
                if (infoEl) {{
                    infoEl.textContent = "Показано записей: " + activeIndices.length + " из " + store.totalRows.toLocaleString("ru-RU") + " (хэш-отбор по «" + q + "»).";
                }}
                if (fromPivot && inp) {{
                    inp.value = q;
                    btn.style.display = "none";
                    inp.style.display = "inline-block";
                }}
            }}

            window._eaTableControllers = window._eaTableControllers || {{}};
            window._eaTableControllers["{tbl_id}"] = {{
                filter: applyTableFilter
            }};

            if (typeof window.filterEaDataTable === "undefined") {{
                window.filterEaDataTable = function(targetTblId, queryStr, fromPivot) {{
                    var ctrls = window._eaTableControllers || {{}};
                    if (targetTblId && targetTblId !== "__ALL__") {{
                        var fullId = targetTblId.indexOf("ea-tbl-") === 0 ? targetTblId : ("ea-tbl-" + targetTblId);
                        if (ctrls[fullId]) ctrls[fullId].filter(queryStr, fromPivot);
                    }} else {{
                        Object.keys(ctrls).forEach(function(k) {{
                            ctrls[k].filter(queryStr, fromPivot);
                        }});
                    }}
                }};
            }}

            btn.addEventListener("click", function() {{
                btn.style.display = "none";
                inp.style.display = "inline-block";
                inp.focus();
            }});
            inp.addEventListener("input", function() {{
                applyTableFilter(inp.value, false);
            }});
            inp.addEventListener("keydown", function(e) {{
                if (e.key === "Escape") {{
                    inp.value = "";
                    applyTableFilter("", false);
                    inp.style.display = "none";
                    btn.style.display = "inline-block";
                }}
            }});
            clearBtn.addEventListener("click", function() {{
                inp.value = "";
                applyTableFilter("", false);
                inp.style.display = "none";
                btn.style.display = "inline-block";
            }});

            // Первичная отрисовка первой порции строк
            renderNextBatch(true);
        }})();
        </script>
        '''
        final_html = self.wrap_layout(inner)
        DataMemoryCache.set_render_html(html_cache_key, block_render_sig, final_html, owner_obj=df)
        return final_html

    def _render_empty(self) -> str:
        return '''
        <div class="block">
            <div class="block-card" style="text-align:center; padding: 60px 20px;">
                <p style="color:#888; font-size: 14px;">Нет выбранных колонок</p>
            </div>
        </div>
        '''

    @staticmethod
    def _format_value(val) -> str:
        try:
            if pd.isna(val):
                return "—"
        except Exception:
            pass
        if isinstance(val, float):
            if abs(val) < 1:
                return f"{val:.4f}".rstrip("0").rstrip(".")
            return f"{val:,.2f}"
        if isinstance(val, int) and not isinstance(val, bool):
            return f"{val:,}"
        return str(val)


# ============================================================
# Сводная матрица (Pivot Matrix) с мульти-столбцами, формулами, поиском и Drill-Down
# ============================================================
@dataclass
class PivotMatrixBlock(Block):
    type: str = "pivot_matrix"
    dataframe: object = None
    source_file_name: str = ""
    source_sheet: str = ""
    title: str = "Сводная матрица"
    row_group_col: str = ""
    row_level2_col: str = ""
    row_level3_col: str = ""
    col_group_col: str = ""
    value_col: str = ""
    agg_func: str = "sum"
    show_totals: bool = True
    top_n: int = 30
    color_calc_enabled: bool = False
    color_calc_scope: str = "calc_and_dev"
    neg_color: str = "#16a34a"
    pos_color: str = "#dc2626"
    color_calc_bg: bool = True
    sticky_header: bool = True
    sticky_first_col: bool = True
    max_table_height: int = 520
    show_search: bool = True
    target_table: str = ""
    value_cols: list[str] = field(default_factory=list)
    calc_cols: list[dict] = field(default_factory=list)

    @staticmethod
    def _eval_pivot_formula(formula_str: str, vals_list: list[float], col_names: list[str]) -> float:
        """Вычисляет математическую формулу для ячейки сводной таблицы по агрегированным значениям столбцов."""
        import math
        if not formula_str or not str(formula_str).strip():
            return 0.0

        expr = (
            str(formula_str)
            .strip()
            .replace(",", ".")
            .replace("−", "-")
            .replace("–", "-")
            .replace("×", "*")
            .replace("÷", "/")
            .replace(";", ",")
        )

        def _if_fn(cond, t_val, f_val=0.0):
            return float(t_val) if bool(cond) else float(f_val)

        env = {
            "__builtins__": {},
            "abs": abs,
            "ABS": abs,
            "round": round,
            "ROUND": round,
            "min": min,
            "MIN": min,
            "max": max,
            "MAX": max,
            "sqrt": math.sqrt,
            "SQRT": math.sqrt,
            "if": _if_fn,
            "IF": _if_fn,
            "если": _if_fn,
            "ЕСЛИ": _if_fn,
        }

        en_letters = ["A", "B", "C", "D", "E", "F", "G", "H"]
        ru_letters = ["А", "Б", "В", "Г", "Д", "Е", "Ж", "З"]

        for idx, val in enumerate(vals_list):
            f_val = float(val) if not pd.isna(val) else 0.0
            env[f"C{idx + 1}"] = f_val
            env[f"c{idx + 1}"] = f_val
            if idx < len(en_letters):
                env[en_letters[idx]] = f_val
                env[en_letters[idx].lower()] = f_val
            if idx < len(ru_letters):
                env[ru_letters[idx]] = f_val
                env[ru_letters[idx].lower()] = f_val

        indexed_cols = sorted(enumerate(col_names), key=lambda x: len(str(x[1])), reverse=True)
        for idx, c_name in indexed_cols:
            c_clean = str(c_name).strip()
            if c_clean:
                token = f"__COL_{idx}__"
                f_val = float(vals_list[idx]) if idx < len(vals_list) and not pd.isna(vals_list[idx]) else 0.0
                env[token] = f_val
                expr = expr.replace(f"[{c_clean}]", token).replace(c_clean, token)

        expr = re.sub(r"\b(if|IF|если|ЕСЛИ)\s*\(", "_if_call(", expr)
        env["_if_call"] = _if_fn

        try:
            res = eval(expr, {"__builtins__": {}}, env)
            res_f = float(res)
            if math.isnan(res_f) or math.isinf(res_f):
                return 0.0
            return res_f
        except ZeroDivisionError:
            return 0.0
        except Exception:
            return 0.0

    @staticmethod
    def _compile_pivot_formula(formula_str: str, col_names: list[str]):
        """Компилирует формулу сводной таблицы один раз перед циклом по ячейкам."""
        if not formula_str or not str(formula_str).strip():
            return None, ()
        expr = (
            str(formula_str)
            .strip()
            .replace(",", ".")
            .replace("−", "-")
            .replace("–", "-")
            .replace("×", "*")
            .replace("÷", "/")
            .replace(";", ",")
        )
        used_toks = []
        indexed_cols = sorted(enumerate(col_names), key=lambda x: len(str(x[1])), reverse=True)
        for idx, c_name in indexed_cols:
            c_clean = str(c_name).strip()
            if c_clean:
                token = f"__COL_{idx}__"
                if f"[{c_clean}]" in expr or c_clean in expr:
                    expr = expr.replace(f"[{c_clean}]", token).replace(c_clean, token)
                    used_toks.append((idx, token))
        expr = re.sub(r"\b(if|IF|если|ЕСЛИ)\s*\(", "_if_call(", expr)
        try:
            return compile(expr, "<pivot_formula>", "eval"), tuple(used_toks)
        except Exception:
            return None, ()

    @staticmethod
    def _eval_compiled_pivot_formula(code_obj, used_toks: tuple, vals_tuple) -> float:
        if code_obj is None:
            return 0.0

        def _if_fn(cond, t_val, f_val=0.0):
            return float(t_val) if bool(cond) else float(f_val)

        env = {
            "__builtins__": {},
            "abs": abs, "ABS": abs,
            "round": round, "ROUND": round,
            "min": min, "MIN": min,
            "max": max, "MAX": max,
            "sqrt": math.sqrt, "SQRT": math.sqrt,
            "if": _if_fn, "IF": _if_fn,
            "если": _if_fn, "ЕСЛИ": _if_fn,
            "_if_call": _if_fn,
        }
        en_l = ("A", "B", "C", "D", "E", "F", "G", "H")
        ru_l = ("А", "Б", "В", "Г", "Д", "Е", "Ж", "З")
        for idx, val in enumerate(vals_tuple):
            f_val = 0.0 if (val is None or (isinstance(val, float) and math.isnan(val))) else float(val)
            env[f"C{idx + 1}"] = env[f"c{idx + 1}"] = f_val
            if idx < 8:
                env[en_l[idx]] = env[en_l[idx].lower()] = f_val
                env[ru_l[idx]] = env[ru_l[idx].lower()] = f_val
        for idx, tok in used_toks:
            val = vals_tuple[idx] if idx < len(vals_tuple) else 0.0
            env[tok] = 0.0 if (val is None or (isinstance(val, float) and math.isnan(val))) else float(val)
        try:
            res = float(eval(code_obj, {"__builtins__": {}}, env))
            return 0.0 if (math.isnan(res) or math.isinf(res)) else res
        except Exception:
            return 0.0

    @staticmethod
    def _hex_to_rgba(hex_color: str, alpha: float = 0.12) -> str:
        h = str(hex_color or "").strip().lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        if len(h) != 6:
            return "transparent"
        try:
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            return f"rgba({r}, {g}, {b}, {alpha:.2f})"
        except Exception:
            return "transparent"

    def render(self) -> str:
        report_obj, own_cfg = _find_report_and_config(self)
        if report_obj is not None:
            self._report_ref = report_obj
        for k, v in own_cfg.items():
            if hasattr(self, k) and k not in ("id", "type", "dataframe", "width", "margin_top", "margin_bottom", "min_height"):
                setattr(self, k, v)

        manager = getattr(self, "_file_manager", None)
        if not manager and report_obj and hasattr(report_obj, "file_manager"):
            manager = report_obj.file_manager

        df = DataMemoryCache.get_dataframe(
            manager, self.source_file_name, self.source_sheet or own_cfg.get("source_file", ""), fallback_df=self.dataframe
        )
        if df is None or len(df) == 0:
            return self.wrap_layout('<div class="block-card" style="padding:40px; text-align:center; color:#888;">Нет данных для сводной матрицы</div>')

        cols = [str(c) for c in df.columns]
        num_cols = [str(c) for c in df.select_dtypes(include="number").columns]
        str_cols = [c for c in cols if c not in num_cols]

        # 1. Определяем основной уровень строк (Уровень 1 — например, Тип ТС)
        if not self.row_group_col or self.row_group_col not in df.columns:
            for cand in str_cols:
                if any(w in cand.lower() for w in ("тип", "групп", "категор", "марк")):
                    self.row_group_col = cand
                    break
            if not self.row_group_col:
                self.row_group_col = str_cols[0] if str_cols else cols[0]

        lvl1_col = self.row_group_col

        # 2. Определяем Уровень 2 (Марка / Модель) и Уровень 3 (Гос. номер) для раскрытия по клику
        lvl2_col = ""
        if self.row_level2_col == "__NONE__":
            lvl2_col = ""
        elif self.row_level2_col and self.row_level2_col in df.columns and self.row_level2_col != lvl1_col:
            lvl2_col = self.row_level2_col
        else:
            for cand in str_cols:
                if cand != lvl1_col and cand != self.col_group_col:
                    if any(w in cand.lower() for w in ("марк", "модел", "авто", "наимен")):
                        lvl2_col = cand
                        break

        lvl3_col = ""
        if self.row_level3_col == "__NONE__":
            lvl3_col = ""
        elif self.row_level3_col and self.row_level3_col in df.columns and self.row_level3_col not in (lvl1_col, lvl2_col):
            lvl3_col = self.row_level3_col
        else:
            for cand in cols:
                if cand not in (lvl1_col, lvl2_col, self.col_group_col):
                    if any(w in cand.lower() for w in ("гос", "номер", "грз", "гараж", "вин", "vin")):
                        lvl3_col = cand
                        break

        # 3. Собираем все выбранные числовые столбцы для расчета
        val_cols: list[str] = []
        if self.value_col and self.value_col in df.columns:
            val_cols.append(self.value_col)

        raw_extra = self.value_cols or own_cfg.get("value_cols", [])
        if isinstance(raw_extra, str):
            raw_extra = [x.strip() for x in raw_extra.split(",") if x.strip()]
        for vc in raw_extra:
            if vc in df.columns and vc not in val_cols:
                val_cols.append(vc)

        if not val_cols:
            for cand in cols:
                if any(w in cand.lower() for w in ("факт", "расход", "сумм", "норм")):
                    val_cols.append(cand)
                    break
            if not val_cols:
                val_cols = [num_cols[0] if num_cols else cols[-1]]

        self.value_col = val_cols[0]

        # 4. Собираем список вычисляемых столбцов (математические функции / формулы)
        raw_calcs = self.calc_cols if isinstance(self.calc_cols, list) else (own_cfg.get("calc_cols") or [])
        active_calc_cols: list[dict] = []
        for item in raw_calcs:
            if isinstance(item, dict) and str(item.get("formula", "")).strip():
                active_calc_cols.append({
                    "name": str(item.get("name") or item.get("formula") or "Расчёт").strip(),
                    "formula": str(item.get("formula")).strip(),
                    "is_pct": bool(item.get("is_pct", False)),
                })

        work = df.copy()
        work["_r1"] = work[lvl1_col].fillna("—").astype(str).str.strip().replace("", "—")
        if lvl2_col:
            work["_r2"] = work[lvl2_col].fillna("—").astype(str).str.strip().replace("", "—")
        if lvl3_col:
            work["_r3"] = work[lvl3_col].fillna("—").astype(str).str.strip().replace("", "—")

        num_keys: list[str] = []
        for idx_v, vc in enumerate(val_cols):
            k = f"_v{idx_v}"
            work[k] = _to_num_series(work[vc]) if self.agg_func != "count" else 1.0
            num_keys.append(k)

        agg_map = {"sum": "sum", "mean": "mean", "count": "count", "min": "min", "max": "max"}
        agg_fn = agg_map.get(self.agg_func, "sum")
        agg_label = {"sum": "Сумма", "mean": "Среднее", "count": "Кол-во", "min": "Мин", "max": "Макс"}.get(agg_fn, "Итог")

        has_col_group = bool(self.col_group_col and self.col_group_col in work.columns and self.col_group_col != lvl1_col)
        col_keys: list[str] = []
        if has_col_group:
            m_names, _ = _extract_month_info(work[self.col_group_col])
            if (m_names != "").any():
                work["_col"] = m_names.replace("", "—")
                present_m = set(work["_col"].unique())
                ordered_m = [m for m in _RU_MONTHS_ORDER if m in present_m]
                other_m = [c for c in work["_col"].unique() if c not in ordered_m]
                col_keys = ordered_m + other_m
            else:
                work["_col"] = work[self.col_group_col].fillna("—").astype(str).str.strip().replace("", "—")
                col_keys = list(dict.fromkeys(work["_col"].tolist()))

        def _fmt_num(val, is_pct: bool = False, force_float: bool = False) -> str:
            if pd.isna(val):
                return "0.00%" if is_pct else "0.00"
            v = float(val)
            if is_pct:
                return f"{v:+,.2f}%".replace(",", " ")
            if self.agg_func == "count" and not force_float:
                return f"{int(round(v)):,}".replace(",", " ")
            return f"{v:,.2f}".replace(",", " ")

        def _should_color_col(col_title: str, is_calc_col: bool) -> bool:
            if not self.color_calc_enabled:
                return False
            scope = str(self.color_calc_scope or "calc_and_dev")
            if scope == "all_cols":
                return True
            if is_calc_col:
                return True
            if scope == "calc_and_dev":
                low_t = str(col_title).lower()
                return any(w in low_t for w in ("откл", "разн", "дельт", "эконом", "перерасх", "баланс", "diff", "%"))
            return False

        neg_fg = str(self.neg_color or "#16a34a")
        pos_fg = str(self.pos_color or "#dc2626")
        neg_bg = self._hex_to_rgba(neg_fg, 0.11) if self.color_calc_bg else "transparent"
        pos_bg = self._hex_to_rgba(pos_fg, 0.11) if self.color_calc_bg else "transparent"

        def _cell_color_style(val: float, col_title: str, is_calc_col: bool) -> str:
            if not _should_color_col(col_title, is_calc_col):
                return ""
            if val < -1e-9:
                bg_part = f" background-color:{neg_bg} !important;" if self.color_calc_bg else ""
                return f' style="color:{neg_fg} !important; font-weight:700;{bg_part}"'
            if val > 1e-9:
                bg_part = f" background-color:{pos_bg} !important;" if self.color_calc_bg else ""
                return f' style="color:{pos_fg} !important; font-weight:700;{bg_part}"'
            return ""

        tbl_uid = f"ea_piv_{self.id}"
        max_r = max(5, int(self.top_n or 30))
        target_tbl_attr = _escape(str(self.target_table or "__ALL__"))

        all_metric_specs: list[tuple[str, bool, object]] = []
        for vc, nk in zip(val_cols, num_keys):
            all_metric_specs.append((vc, False, nk))
        for cc in active_calc_cols:
            all_metric_specs.append((cc["name"], True, cc))

        total_metrics_per_group = len(all_metric_specs)

        try:
            def _df_to_map(gdf) -> dict:
                if gdf is None or len(gdf) == 0:
                    return {}
                return dict(zip(gdf.index.tolist(), gdf.itertuples(index=False, name=None)))

            g1_tot = work.groupby("_r1", sort=False)[num_keys].agg(agg_fn)
            g1_tot = g1_tot.sort_values(by=num_keys[0], ascending=False).head(max_r)
            top_r1_list = g1_tot.index.tolist()

            # Фильтруем work по топ-группам Уровня 1 ДО тяжёлых группировок Уровней 2 и 3
            work_top = work[work["_r1"].isin(set(top_r1_list))]

            d1_tot = _df_to_map(g1_tot)
            d1_col = _df_to_map(work_top.groupby(["_r1", "_col"], sort=False)[num_keys].agg(agg_fn)) if has_col_group else {}

            if lvl2_col:
                d2_tot = _df_to_map(work_top.groupby(["_r1", "_r2"], sort=False)[num_keys].agg(agg_fn))
                d2_col = _df_to_map(work_top.groupby(["_r1", "_r2", "_col"], sort=False)[num_keys].agg(agg_fn)) if has_col_group else {}
            else:
                d2_tot, d2_col = {}, {}

            if lvl2_col and lvl3_col:
                d3_tot = _df_to_map(work_top.groupby(["_r1", "_r2", "_r3"], sort=False)[num_keys].agg(agg_fn))
                d3_col = _df_to_map(work_top.groupby(["_r1", "_r2", "_r3", "_col"], sort=False)[num_keys].agg(agg_fn)) if has_col_group else {}
            else:
                d3_tot, d3_col = {}, {}

            gt_tot_vals = tuple(
                0.0 if pd.isna(v) else float(v) for v in work[num_keys].agg(agg_fn).tolist()
            )
            gt_col_map = _df_to_map(work.groupby("_col", sort=False)[num_keys].agg(agg_fn)) if has_col_group else {}

            # Строим списки дочерних узлов в O(N) вместо сотен .loc[]
            l2_by_l1: dict[str, list[tuple[str, float]]] = {}
            for (r1_k, r2_k), vals in d2_tot.items():
                l2_by_l1.setdefault(r1_k, []).append((r2_k, 0.0 if pd.isna(vals[0]) else float(vals[0])))
            for lst in l2_by_l1.values():
                lst.sort(key=lambda x: x[1], reverse=True)

            l3_by_l12: dict[tuple[str, str], list[tuple[str, float]]] = {}
            for (r1_k, r2_k, r3_k), vals in d3_tot.items():
                l3_by_l12.setdefault((r1_k, r2_k), []).append((r3_k, 0.0 if pd.isna(vals[0]) else float(vals[0])))
            for lst in l3_by_l12.values():
                lst.sort(key=lambda x: x[1], reverse=True)

            compiled_calcs = [
                (cc["name"], cc["is_pct"], *self._compile_pivot_formula(cc["formula"], val_cols))
                for cc in active_calc_cols
            ]
            zeros_tuple = tuple(0.0 for _ in num_keys)

            hier_parts = [lvl1_col]
            if lvl2_col:
                hier_parts.append(lvl2_col)
            if lvl2_col and lvl3_col:
                hier_parts.append(lvl3_col)
            hier_header_title = " → ".join(hier_parts)

            thead_rows = []
            if has_col_group:
                if total_metrics_per_group == 1:
                    ths = [f'<th class="ea-piv-corner-th" style="text-align:left; min-width:220px;">{_escape(hier_header_title)}</th>']
                    for ck in col_keys:
                        ths.append(f"<th>{_escape(str(ck))}</th>")
                    if self.show_totals:
                        ths.append('<th class="ea-piv-tot-hdr">Итого</th>')
                    thead_rows.append("<tr>" + "".join(ths) + "</tr>")
                else:
                    top_ths = [f'<th rowspan="2" class="ea-piv-corner-th" style="text-align:left; min-width:220px;">{_escape(hier_header_title)}</th>']
                    sub_ths = []
                    for ck in col_keys:
                        top_ths.append(f'<th colspan="{total_metrics_per_group}">{_escape(str(ck))}</th>')
                        for m_title, is_c, _ in all_metric_specs:
                            calc_badge = " 🧮" if is_c else ""
                            sub_ths.append(f'<th class="ea-piv-sub-th">{_escape(m_title)}{calc_badge}</th>')
                    if self.show_totals:
                        top_ths.append(f'<th colspan="{total_metrics_per_group}" class="ea-piv-tot-hdr">Итого</th>')
                        for m_title, is_c, _ in all_metric_specs:
                            calc_badge = " 🧮" if is_c else ""
                            sub_ths.append(f'<th class="ea-piv-sub-th ea-piv-tot-hdr">{_escape(m_title)}{calc_badge}</th>')
                    thead_rows.append("<tr>" + "".join(top_ths) + "</tr>")
                    thead_rows.append("<tr>" + "".join(sub_ths) + "</tr>")
            else:
                ths = [f'<th class="ea-piv-corner-th" style="text-align:left; min-width:220px;">{_escape(hier_header_title)}</th>']
                for m_title, is_c, _ in all_metric_specs:
                    if is_c:
                        ths.append(f'<th>{_escape(m_title)} 🧮</th>')
                    else:
                        ths.append(f"<th>{_escape(m_title)} ({agg_label})</th>")
                thead_rows.append("<tr>" + "".join(ths) + "</tr>")

            def _render_metric_group_tds(base_vals: tuple, base_td_cls: str) -> list[str]:
                group_tds = []
                cls_attr = f' class="{base_td_cls}"' if base_td_cls else ""
                calc_cls = f"{base_td_cls} ea-piv-calc-td".strip()
                calc_cls_attr = f' class="{calc_cls}"' if calc_cls else ""

                for vc_name, v_raw in zip(val_cols, base_vals):
                    v_num = 0.0 if (v_raw is None or (isinstance(v_raw, float) and math.isnan(v_raw))) else float(v_raw)
                    c_style = _cell_color_style(v_num, vc_name, False)
                    group_tds.append(f"<td{cls_attr}{c_style}>{_fmt_num(v_num)}</td>")

                for c_name, is_pct, code_obj, used_toks in compiled_calcs:
                    c_val = self._eval_compiled_pivot_formula(code_obj, used_toks, base_vals)
                    c_style = _cell_color_style(c_val, c_name, True)
                    group_tds.append(f"<td{calc_cls_attr}{c_style}>{_fmt_num(c_val, is_pct=is_pct, force_float=True)}</td>")
                return group_tds

            def _build_value_cells(col_map: dict, tot_vals: tuple, idx_tuple: tuple, is_total_row: bool = False) -> str:
                tds = []
                base_cls = "ea-piv-tot-cell" if is_total_row else ""
                if has_col_group:
                    for ck in col_keys:
                        lookup = (*idx_tuple, ck) if idx_tuple else ck
                        base_vals = col_map.get(lookup, zeros_tuple)
                        tds.extend(_render_metric_group_tds(base_vals, base_cls))
                    if self.show_totals:
                        tds.extend(_render_metric_group_tds(tot_vals, "ea-piv-tot-col"))
                else:
                    tds.extend(_render_metric_group_tds(tot_vals, base_cls))
                return "".join(tds)

            tbody_rows = []
            max_l3_total = 8000  # защита браузера от раздувания DOM при сотнях тысяч листьев
            l3_rendered = 0
            total_cols_span = 1 + (len(col_keys) + (1 if self.show_totals else 0)) * total_metrics_per_group if has_col_group else (1 + total_metrics_per_group)

            for i1, r1_val in enumerate(top_r1_list):
                node1_id = f"{tbl_uid}_l1_{i1}"
                safe_r1 = _escape(str(r1_val))
                r2_list = l2_by_l1.get(r1_val, [])
                has_l2 = len(r2_list) > 0

                if has_l2:
                    row1_Attr = (
                        f'class="ea-piv-row-l1 ea-piv-expandable" data-level="1" data-node="{node1_id}" '
                        f'data-r1="{safe_r1}" onclick="window.toggleEaPivotRow(\'{tbl_uid}\', \'{node1_id}\', 1)"'
                    )
                    badge1 = f'<span class="ea-piv-cnt">{len(r2_list)}</span>'
                    label1_html = f'<span class="ea-piv-caret" id="caret_{node1_id}">▶</span> {safe_r1} {badge1}'
                else:
                    row1_Attr = f'class="ea-piv-row-l1" data-level="1" data-node="{node1_id}" data-r1="{safe_r1}"'
                    label1_html = safe_r1

                cells1 = _build_value_cells(d1_col, d1_tot.get(r1_val, zeros_tuple), (r1_val,))
                tbody_rows.append(f"<tr {row1_Attr}><th>{label1_html}</th>{cells1}</tr>")

                if has_l2:
                    for i2, (r2_val, _) in enumerate(r2_list):
                        node2_id = f"{node1_id}_l2_{i2}"
                        safe_r2 = _escape(str(r2_val))
                        r3_list = l3_by_l12.get((r1_val, r2_val), [])
                        has_l3 = len(r3_list) > 0 and l3_rendered < max_l3_total

                        if has_l3:
                            row2_Attr = (
                                f'class="ea-piv-row-l2 ea-piv-expandable" data-level="2" data-parent="{node1_id}" '
                                f'data-node="{node2_id}" data-r1="{safe_r1}" data-r2="{safe_r2}" '
                                f'style="display:none;" onclick="window.toggleEaPivotRow(\'{tbl_uid}\', \'{node2_id}\', 2)"'
                            )
                            badge2 = f'<span class="ea-piv-cnt">{len(r3_list)}</span>'
                            label2_html = f'<span class="ea-piv-caret" id="caret_{node2_id}">▶</span> {safe_r2} {badge2}'
                        else:
                            row2_Attr = (
                                f'class="ea-piv-row-l2" data-level="2" data-parent="{node1_id}" '
                                f'data-node="{node2_id}" data-r1="{safe_r1}" data-r2="{safe_r2}" style="display:none;"'
                            )
                            label2_html = f'<span style="color:#64748b; margin-right:6px;">•</span>{safe_r2}'

                        cells2 = _build_value_cells(d2_col, d2_tot.get((r1_val, r2_val), zeros_tuple), (r1_val, r2_val))
                        tbody_rows.append(f"<tr {row2_Attr}><th class=\"ea-piv-th-l2\">{label2_html}</th>{cells2}</tr>")

                        if has_l3:
                            shown_in_l2 = 0
                            for r3_val, _ in r3_list:
                                if l3_rendered >= max_l3_total:
                                    break
                                l3_rendered += 1
                                shown_in_l2 += 1
                                safe_r3 = _escape(str(r3_val))
                                js_r3 = safe_r3.replace("\\", "\\\\").replace("'", "\\'")
                                row3_Attr = (
                                    f'class="ea-piv-row-l3 ea-piv-clickable-leaf" data-level="3" data-parent="{node2_id}" '
                                    f'data-root="{node1_id}" data-r1="{safe_r1}" data-r2="{safe_r2}" data-r3="{safe_r3}" '
                                    f'style="display:none;" title="Нажмите, чтобы отфильтровать таблицу по «{safe_r3}»" '
                                    f'onclick="window.selectEaPivotLeaf(\'{tbl_uid}\', \'{js_r3}\', this)"'
                                )
                                label3_html = f'<span style="color:#94a3b8; margin-right:6px;">🏷</span>{safe_r3}'
                                cells3 = _build_value_cells(d3_col, d3_tot.get((r1_val, r2_val, r3_val), zeros_tuple), (r1_val, r2_val, r3_val))
                                tbody_rows.append(f"<tr {row3_Attr}><th class=\"ea-piv-th-l3\">{label3_html}</th>{cells3}</tr>")
                            if shown_in_l2 < len(r3_list):
                                hidden_cnt = len(r3_list) - shown_in_l2
                                tbody_rows.append(
                                    f'<tr class="ea-piv-row-l3" data-level="3" data-parent="{node2_id}" data-root="{node1_id}" style="display:none;">'
                                    f'<td colspan="{total_cols_span}" style="text-align:left; padding-left:52px; color:#64748b; font-style:italic;">'
                                    f'… скрыто ещё {hidden_cnt:,} позиций для защиты производительности браузера</td></tr>'
                                )

            if self.show_totals:
                tot_cells = _build_value_cells(gt_col_map, gt_tot_vals, (), is_total_row=True)
                tbody_rows.append(f'<tr class="ea-piv-grand-total"><th>Итого</th>{tot_cells}</tr>')

            tbl_classes = ["ea-pivot-table"]
            if self.sticky_header:
                tbl_classes.append("ea-piv-sticky-hdr")
            if self.sticky_first_col:
                tbl_classes.append("ea-piv-sticky-col")

            html_table = (
                f'<table class="{" ".join(tbl_classes)}" id="{tbl_uid}" data-target-table="{target_tbl_attr}">'
                f'<thead>{"".join(thead_rows)}</thead>'
                f'<tbody>{"".join(tbody_rows)}</tbody>'
                f'</table>'
            )
        except Exception as e:

            import traceback
            traceback.print_exc()
            html_table = f"<p style='color:red;'>Ошибка расчета сводной матрицы: {e}</p>"

        max_h_val = int(self.max_table_height or 0)
        max_h_css = f"max-height: {max_h_val}px;" if max_h_val > 0 else ""

        style_and_js = f"""
        <style>
        .ea-piv-scroll-wrap {{
            width: 100%;
            overflow-x: auto;
            overflow-y: auto;
            {max_h_css}
            border: 1px solid #e2e8f0;
            border-radius: 6px;
            position: relative;
        }}
        .ea-pivot-table {{ width: 100%; border-collapse: separate; border-spacing: 0; font-size: 13px; text-align: right; }}
        .ea-pivot-table th, .ea-pivot-table td {{ border-right: 1px solid #e2e8f0; border-bottom: 1px solid #e2e8f0; padding: 7px 12px; white-space: nowrap; }}
        .ea-pivot-table thead th {{ background: #f8fafc; font-weight: 700; text-align: center; color: #334155; }}
        .ea-pivot-table thead th.ea-piv-sub-th {{ font-size: 11.5px; color: #475569; background: #f1f5f9; padding: 5px 10px; }}
        .ea-pivot-table tbody tr.ea-piv-row-l1:hover td, .ea-pivot-table tbody tr.ea-piv-row-l1:hover th {{ background: #f1f8e9; }}
        .ea-pivot-table tbody tr.ea-piv-row-l1 th {{ text-align: left; background: #ffffff; color: #003F0B; font-weight: 600; }}
        .ea-pivot-table tbody tr.ea-piv-expandable {{ cursor: pointer; user-select: none; }}
        .ea-pivot-table tbody tr.ea-piv-expandable:hover th {{ color: #2bb24c; background: #f1f8e9; }}
        .ea-pivot-table tbody tr.ea-piv-row-l2 {{ background: #fafdf7; font-size: 12.5px; }}
        .ea-pivot-table tbody tr.ea-piv-row-l2:hover td, .ea-pivot-table tbody tr.ea-piv-row-l2:hover th {{ background: #eef8e3; }}
        .ea-pivot-table tbody th.ea-piv-th-l2 {{ text-align: left; padding-left: 28px !important; color: #1e293b; font-weight: 600; background: #fafdf7; }}
        .ea-pivot-table tbody tr.ea-piv-row-l3 {{ background: #ffffff; font-size: 12px; color: #475569; cursor: pointer; }}
        .ea-pivot-table tbody tr.ea-piv-row-l3:hover td, .ea-pivot-table tbody tr.ea-piv-row-l3:hover th {{ background: #ecfccb !important; color: #003F0B; }}
        .ea-pivot-table tbody tr.ea-piv-leaf-active td, .ea-pivot-table tbody tr.ea-piv-leaf-active th {{ background: #d9f99d !important; font-weight: 700 !important; color: #003F0B !important; }}
        .ea-pivot-table tbody th.ea-piv-th-l3 {{ text-align: left; padding-left: 52px !important; color: #475569; font-weight: 500; background: #ffffff; }}
        .ea-piv-caret {{ display: inline-block; width: 14px; font-size: 11px; color: #87C800; transition: transform 0.15s ease; }}
        .ea-piv-cnt {{ display: inline-block; margin-left: 6px; padding: 1px 6px; font-size: 10px; font-weight: 600; color: #475569; background: #e2e8f0; border-radius: 10px; }}
        .ea-piv-tot-col, .ea-piv-tot-hdr {{ font-weight: 700; background: #f8fafc !important; }}
        .ea-piv-calc-td {{ background: #fcfdfd; }}
        .ea-piv-grand-total th, .ea-piv-grand-total td {{ font-weight: 700; background: #f1f5f9 !important; color: #0f172a; border-top: 2px solid #cbd5e1; }}

        .ea-piv-sticky-hdr thead tr:first-child th {{
            position: sticky;
            top: 0;
            height: 32px;
            box-sizing: border-box;
            z-index: 4;
            background: #f8fafc;
            box-shadow: inset 0 -1px 0 #cbd5e1;
        }}
        .ea-piv-sticky-hdr thead tr:nth-child(2) th {{
            position: sticky;
            top: 31px;
            z-index: 4;
            background: #f1f5f9;
            box-shadow: inset 0 -2px 0 #cbd5e1;
        }}
        .ea-piv-sticky-col tbody th {{
            position: sticky;
            left: 0;
            z-index: 3;
            box-shadow: inset -2px 0 0 #cbd5e1;
        }}
        .ea-piv-sticky-col thead tr:first-child th.ea-piv-corner-th {{
            position: sticky;
            left: 0;
            z-index: 5;
            box-shadow: inset -2px 0 0 #cbd5e1;
        }}
        .ea-piv-sticky-hdr.ea-piv-sticky-col thead tr:first-child th.ea-piv-corner-th {{
            position: sticky;
            top: 0;
            left: 0;
            z-index: 7;
            box-shadow: inset -2px 0 0 #cbd5e1, inset 0 -1px 0 #cbd5e1;
        }}
        </style>
        <script>
        if (typeof window.toggleEaPivotRow === 'undefined') {{
            window.toggleEaPivotRow = function(tblId, nodeId, level) {{
                var tbl = document.getElementById(tblId);
                if (!tbl) return;
                var caret = document.getElementById('caret_' + nodeId);
                var children = tbl.querySelectorAll('tr[data-parent="' + nodeId + '"]');
                if (!children.length) return;
                var isOpening = (children[0].style.display === 'none');
                if (caret) caret.textContent = isOpening ? '▼' : '▶';

                children.forEach(function(row) {{
                    row.style.display = isOpening ? 'table-row' : 'none';
                    if (!isOpening && level === 1) {{
                        var childNode = row.getAttribute('data-node');
                        if (childNode) {{
                            var cCaret = document.getElementById('caret_' + childNode);
                            if (cCaret) cCaret.textContent = '▶';
                            var subChildren = tbl.querySelectorAll('tr[data-parent="' + childNode + '"]');
                            subChildren.forEach(function(sr) {{ sr.style.display = 'none'; }});
                        }}
                    }}
                }});
            }};

            window.expandAllEaPivot = function(tblId, expand) {{
                var tbl = document.getElementById(tblId);
                if (!tbl) return;
                tbl.querySelectorAll('tr.ea-piv-row-l1').forEach(function(r) {{
                    r.style.display = 'table-row';
                }});
                tbl.querySelectorAll('tr.ea-piv-row-l2, tr.ea-piv-row-l3').forEach(function(r) {{
                    r.style.display = expand ? 'table-row' : 'none';
                }});
                tbl.querySelectorAll('.ea-piv-caret').forEach(function(c) {{
                    c.textContent = expand ? '▼' : '▶';
                }});
            }};

            window.selectEaPivotLeaf = function(tblId, leafVal, rowEl) {{
                var tbl = document.getElementById(tblId);
                if (!tbl) return;
                var wasActive = rowEl.classList.contains('ea-piv-leaf-active');
                tbl.querySelectorAll('tr.ea-piv-leaf-active').forEach(function(r) {{
                    r.classList.remove('ea-piv-leaf-active');
                }});
                var targetTbl = tbl.getAttribute('data-target-table') || '__ALL__';
                if (wasActive) {{
                    if (typeof window.filterEaDataTable === 'function' && targetTbl !== '__NONE__') {{
                        window.filterEaDataTable(targetTbl, '', true);
                    }}
                }} else {{
                    rowEl.classList.add('ea-piv-leaf-active');
                    if (typeof window.filterEaDataTable === 'function' && targetTbl !== '__NONE__') {{
                        window.filterEaDataTable(targetTbl, leafVal, true);
                    }}
                }}
            }};

            window.filterEaPivot = function(tblId, rawQuery) {{
                var tbl = document.getElementById(tblId);
                if (!tbl) return;
                var q = String(rawQuery || '').trim().toLowerCase();
                var clearBtn = document.getElementById(tblId + '_search_clear');
                if (clearBtn) clearBtn.style.display = q ? 'inline-block' : 'none';

                var l1Rows = tbl.querySelectorAll('tr.ea-piv-row-l1');
                var l2Rows = tbl.querySelectorAll('tr.ea-piv-row-l2');
                var l3Rows = tbl.querySelectorAll('tr.ea-piv-row-l3');

                tbl.querySelectorAll('tr.ea-piv-leaf-active').forEach(function(r) {{
                    r.classList.remove('ea-piv-leaf-active');
                }});

                var targetTbl = tbl.getAttribute('data-target-table') || '__ALL__';

                if (!q) {{
                    l1Rows.forEach(function(r) {{ r.style.display = 'table-row'; }});
                    l2Rows.forEach(function(r) {{ r.style.display = 'none'; }});
                    l3Rows.forEach(function(r) {{ r.style.display = 'none'; }});
                    tbl.querySelectorAll('.ea-piv-caret').forEach(function(c) {{ c.textContent = '▶'; }});
                    if (typeof window.filterEaDataTable === 'function' && targetTbl !== '__NONE__') {{
                        window.filterEaDataTable(targetTbl, '', true);
                    }}
                    return;
                }}

                l1Rows.forEach(function(r) {{ r.style.display = 'none'; }});
                l2Rows.forEach(function(r) {{ r.style.display = 'none'; }});
                l3Rows.forEach(function(r) {{ r.style.display = 'none'; }});
                tbl.querySelectorAll('.ea-piv-caret').forEach(function(c) {{ c.textContent = '▶'; }});

                var showL1 = {{}};
                var showL2 = {{}};
                var l2HasMatchedL3 = {{}};
                var l1HasMatchedChild = {{}};

                l3Rows.forEach(function(r3) {{
                    var v3 = String(r3.getAttribute('data-r3') || '').toLowerCase();
                    if (v3.indexOf(q) !== -1) {{
                        r3.style.display = 'table-row';
                        r3.classList.add('ea-piv-leaf-active');
                        var p2 = r3.getAttribute('data-parent');
                        var p1 = r3.getAttribute('data-root');
                        if (p2) {{
                            showL2[p2] = true;
                            l2HasMatchedL3[p2] = true;
                        }}
                        if (p1) {{
                            showL1[p1] = true;
                            l1HasMatchedChild[p1] = true;
                        }}
                    }}
                }});

                l2Rows.forEach(function(r2) {{
                    var v2 = String(r2.getAttribute('data-r2') || '').toLowerCase();
                    var n2 = r2.getAttribute('data-node');
                    var p1 = r2.getAttribute('data-parent');
                    if (v2.indexOf(q) !== -1) {{
                        showL2[n2] = true;
                        if (p1) {{
                            showL1[p1] = true;
                            l1HasMatchedChild[p1] = true;
                        }}
                        if (!l2HasMatchedL3[n2]) {{
                            tbl.querySelectorAll('tr.ea-piv-row-l3[data-parent="' + n2 + '"]').forEach(function(ch3) {{
                                ch3.style.display = 'table-row';
                            }});
                        }}
                    }}
                }});

                l1Rows.forEach(function(r1) {{
                    var v1 = String(r1.getAttribute('data-r1') || '').toLowerCase();
                    var n1 = r1.getAttribute('data-node');
                    if (v1.indexOf(q) !== -1) {{
                        showL1[n1] = true;
                        if (!l1HasMatchedChild[n1]) {{
                            tbl.querySelectorAll('tr.ea-piv-row-l2[data-parent="' + n1 + '"]').forEach(function(ch2) {{
                                var cn2 = ch2.getAttribute('data-node');
                                showL2[cn2] = true;
                            }});
                        }}
                    }}
                }});

                Object.keys(showL2).forEach(function(n2) {{
                    var r2 = tbl.querySelector('tr.ea-piv-row-l2[data-node="' + n2 + '"]');
                    if (r2) {{
                        r2.style.display = 'table-row';
                        var c2 = document.getElementById('caret_' + n2);
                        if (c2) c2.textContent = '▼';
                    }}
                }});

                Object.keys(showL1).forEach(function(n1) {{
                    var r1 = tbl.querySelector('tr.ea-piv-row-l1[data-node="' + n1 + '"]');
                    if (r1) {{
                        r1.style.display = 'table-row';
                        var c1 = document.getElementById('caret_' + n1);
                        if (c1) c1.textContent = '▼';
                    }}
                }});

                if (typeof window.filterEaDataTable === 'function' && targetTbl !== '__NONE__') {{
                    window.filterEaDataTable(targetTbl, String(rawQuery || '').trim(), true);
                }}
            }};

            window.clearEaPivotSearch = function(tblId) {{
                var inp = document.getElementById(tblId + '_search_inp');
                if (inp) inp.value = '';
                window.filterEaPivot(tblId, '');
            }};
        }}
        </script>
        """

        col_sub = f" × {self.col_group_col}" if has_col_group else ""
        all_titles_list = val_cols + [cc["name"] for cc in active_calc_cols]
        vals_title = ", ".join(all_titles_list)

        search_box_html = ""
        if self.show_search:
            search_box_html = f'''
            <div style="display:flex; align-items:center; gap:4px;">
                <input type="text" id="{tbl_uid}_search_inp"
                       placeholder="🔍 Поиск по группе, подкатегории или ID..."
                       oninput="window.filterEaPivot('{tbl_uid}', this.value)"
                       style="padding:4px 10px; font-size:12px; min-width:240px; border:1px solid #87C800;
                              border-radius:6px; outline:none; background:#ffffff; color:#1e293b;" />
                <button type="button" id="{tbl_uid}_search_clear"
                        onclick="window.clearEaPivotSearch('{tbl_uid}')"
                        style="display:none; padding:4px 8px; font-size:11.5px; font-weight:700; border:1px solid #fecdd3;
                               border-radius:6px; background:#fff1f2; color:#e11d48; cursor:pointer;">
                    ✕
                </button>
            </div>
            '''

        expand_btns_html = ""
        if lvl2_col:
            expand_btns_html = f'''
            <button type="button" onclick="window.expandAllEaPivot('{tbl_uid}', true)"
                    style="padding:4px 10px; font-size:11.5px; font-weight:600; border:1px solid #cbd5e1; border-radius:6px; background:#f8fafc; cursor:pointer; color:#334155;">
                ➕ Развернуть все
            </button>
            <button type="button" onclick="window.expandAllEaPivot('{tbl_uid}', false)"
                    style="padding:4px 10px; font-size:11.5px; font-weight:600; border:1px solid #cbd5e1; border-radius:6px; background:#f8fafc; cursor:pointer; color:#334155;">
                ➖ Свернуть все
            </button>
            '''

        controls_btns = f'''
        <div style="display:flex; align-items:center; flex-wrap:wrap; gap:6px; flex-shrink:0;">
            {search_box_html}
            {expand_btns_html}
        </div>
        '''

        inner = f'''
        <div class="block" style="width:100%;">
            <div class="block-card" style="width:100%; padding: 16px; overflow: hidden; background: #ffffff; box-sizing: border-box;">
                <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; margin-bottom: 12px; border-bottom: 2px solid #87C800; padding-bottom: 8px;">
                    <div style="font-weight: 700; font-size: 14px; color: #003F0B; min-width: 200px; flex: 1;">
                        {_escape(self.title)} ({_escape(hier_header_title)}{_escape(col_sub)} → {_escape(vals_title)})
                    </div>
                    {controls_btns}
                </div>
                {style_and_js}
                <div class="ea-piv-scroll-wrap">
                    {html_table}
                </div>
            </div>
        </div>
        '''
        return self.wrap_layout(inner)

# ============================================================
# Дерево декомпозиции (Treemap / Sunburst)
# ============================================================
@dataclass
class DecompositionBlock(Block):
    type: str = "decomposition"
    dataframe: object = None
    source_file_name: str = ""
    source_sheet: str = ""
    title: str = "Дерево декомпозиции"
    value_col: str = ""
    level1_col: str = ""
    level2_col: str = ""
    level3_col: str = ""
    level_cols: list[str] = field(default_factory=list)
    tree_mode: str = "treemap"
    agg_func: str = "sum"
    palette: str = "Greens"
    top_n: int = 60

    @staticmethod
    def _plain_fig_arrays(fig, metric_label: str, agg_label: str):
        """Конвертирует numpy-массивы в чистые списки Python (отключает бинарный bdata) и задаёт чистый шаблон подсказок."""
        hover_tpl = (
            "<b>%{label}</b><br>"
            "Группа: %{parent}<br>"
            f"{_escape(metric_label)} ({agg_label}): <b>%{{value:,.2f}}</b><br>"
            "Доля в группе: <b>%{percentParent:.1%}</b><br>"
            "Доля от общего итога: <b>%{percentRoot:.1%}</b>"
            "<extra></extra>"
        )
        fig.update_traces(
            textinfo="label+value+percent parent",
            texttemplate="<b>%{label}</b><br>%{value:,.2f}<br>(%{percentParent:.1%})",
            hovertemplate=hover_tpl,
            marker=dict(line=dict(width=1.5, color="#ffffff")),
        )
        for tr in fig.data:
            if getattr(tr, "values", None) is not None and hasattr(tr.values, "tolist"):
                tr.values = [float(x) for x in tr.values.tolist()]
            for attr in ("labels", "parents", "ids", "text"):
                v = getattr(tr, attr, None)
                if v is not None and hasattr(v, "tolist"):
                    setattr(tr, attr, [str(x) for x in v.tolist()])
            if hasattr(tr, "marker") and tr.marker is not None:
                mc = getattr(tr.marker, "colors", None)
                if mc is not None and hasattr(mc, "tolist"):
                    tr.marker.colors = [float(x) if isinstance(x, (int, float)) or hasattr(x, "item") else x for x in mc.tolist()]
        return fig

    def render(self) -> str:
        import plotly.express as px
        import plotly.io as pio

        report_obj, own_cfg = _find_report_and_config(self)
        if report_obj is not None:
            self._report_ref = report_obj
        for k, v in own_cfg.items():
            if hasattr(self, k) and k not in ("id", "type", "dataframe", "width", "margin_top", "margin_bottom", "min_height"):
                setattr(self, k, v)

        manager = getattr(self, "_file_manager", None)
        if not manager and report_obj and hasattr(report_obj, "file_manager"):
            manager = report_obj.file_manager

        df = DataMemoryCache.get_dataframe(
            manager, self.source_file_name, self.source_sheet or own_cfg.get("source_file", ""), fallback_df=self.dataframe
        )
        if df is None or len(df) == 0:
            return self.wrap_layout('<div class="block-card" style="padding:40px; text-align:center; color:#888;">Нет данных для дерева декомпозиции</div>')

        cols = [str(c) for c in df.columns]
        num_cols = [str(c) for c in df.select_dtypes(include="number").columns]
        str_cols = [c for c in cols if c not in num_cols]

        levels = []
        for lv in (self.level1_col, self.level2_col, self.level3_col):
            if lv and lv in df.columns and lv not in levels:
                levels.append(lv)

        if not levels:
            raw_levels = self.level_cols or own_cfg.get("level_cols", [])
            if isinstance(raw_levels, str):
                raw_levels = [x.strip() for x in raw_levels.split(",") if x.strip()]
            for lv in raw_levels:
                if lv in df.columns and lv not in levels:
                    levels.append(lv)

        if not levels:
            for cand in str_cols:
                if any(k in cand.lower() for k in ("тип", "марк", "модел", "групп", "категор")):
                    if cand not in levels:
                        levels.append(cand)
                if len(levels) >= 2:
                    break
            if not levels:
                levels = str_cols[:2] if len(str_cols) >= 2 else cols[:1]

        if not self.value_col or self.value_col not in df.columns:
            for cand in cols:
                if any(k in cand.lower() for k in ("факт", "расход", "норм", "сумм")):
                    self.value_col = cand
                    break
            if not self.value_col:
                self.value_col = num_cols[0] if num_cols else ""

        work = df.copy()
        if self.value_col and self.value_col in work.columns and self.agg_func != "count":
            work["_val"] = _to_num_series(work[self.value_col]).abs()
            metric_label = self.value_col
        else:
            work["_val"] = 1.0
            metric_label = "Количество записей"

        work = work[work["_val"] > 0]

        for c in levels:
            work[c] = work[c].fillna("Не указано").astype(str).str.strip().replace("", "Не указано")

        plot_div_id = f"ea-plotly-{self.id}"
        row_slicer_payload = {}

        try:
            agg_fn = "mean" if self.agg_func == "mean" else "sum"
            agg_label = {"sum": "Сумма", "mean": "Среднее", "count": "Кол-во"}.get(self.agg_func, "Сумма")
            max_items = max(10, int(self.top_n or 60))
            grouped = work.groupby(levels, as_index=False)["_val"].agg(agg_fn).nlargest(max_items, "_val")
            grouped["_val"] = grouped["_val"].astype(float)

            scale_map = {
                "Greens": ["#d9f0d3", "#74c476", "#238b45", "#00441b"],
                "Blues": ["#deebf7", "#6baed6", "#2171b5", "#08306b"],
                "Viridis": "Viridis",
                "YlOrRd": "YlOrRd",
                "Tealgrn": "Tealgrn",
            }
            c_scale = scale_map.get(self.palette, scale_map["Greens"])
            chart_fn = px.sunburst if self.tree_mode == "sunburst" else px.treemap

            fig = chart_fn(
                grouped,
                path=levels,
                values="_val",
                color="_val",
                color_continuous_scale=c_scale,
                title=f"{self.title} ({' → '.join(levels)} → {metric_label})",
            )
            self._plain_fig_arrays(fig, metric_label, agg_label)
            target_h = max(420, int(self.min_height or 0))
            fig.update_layout(
                height=target_h,
                margin=dict(t=45, l=10, r=10, b=10),
                coloraxis_colorbar=dict(title=metric_label),
            )

            base_traces = json.loads(pio.to_json(fig)).get("data", [])
            row_slicer_payload["ALL"] = base_traces
            if len(levels) >= 1:
                first_lvl = levels[0]
                for g_val in grouped[first_lvl].unique():
                    sub_g = grouped[grouped[first_lvl] == g_val]
                    if len(sub_g) > 0:
                        sub_fig = chart_fn(
                            sub_g,
                            path=levels,
                            values="_val",
                            color="_val",
                            color_continuous_scale=c_scale,
                        )
                        self._plain_fig_arrays(sub_fig, metric_label, agg_label)
                        row_slicer_payload[str(g_val)] = json.loads(pio.to_json(sub_fig)).get("data", [])

            chart_div = pio.to_html(fig, include_plotlyjs=False, full_html=False, div_id=plot_div_id, config={"responsive": True})
        except Exception as e:
            chart_div = f"<p style='color:red;'>Ошибка рендера дерева: {e}</p>"

        slicer_script = ""
        if row_slicer_payload:
            slicer_script = f'<script type="application/json" id="{plot_div_id}-rowmap">{json.dumps(row_slicer_payload, ensure_ascii=False)}</script>'

        inner = f'<div class="block" style="width:100%;"><div class="block-card" style="padding:16px; width:100%; box-sizing:border-box;">{chart_div}{slicer_script}</div></div>'
        return self.wrap_layout(inner)


# ============================================================
# Гео-карта / Аналитика по локациям и подразделениям (Geo Map)
# ============================================================
@dataclass
class GeoMapBlock(Block):
    type: str = "geo_map"
    dataframe: object = None
    source_file_name: str = ""
    source_sheet: str = ""
    title: str = "География и рейтинг объектов"
    loc_col: str = ""
    value_col: str = ""
    map_mode: str = "ranking_bar"
    agg_func: str = "sum"
    top_n: int = 20
    palette: str = "Greens"

    def render(self) -> str:
        import plotly.express as px
        import plotly.io as pio

        report_obj, own_cfg = _find_report_and_config(self)
        if report_obj is not None:
            self._report_ref = report_obj
        for k, v in own_cfg.items():
            if hasattr(self, k) and k not in ("id", "type", "dataframe", "width", "margin_top", "margin_bottom", "min_height"):
                setattr(self, k, v)

        manager = getattr(self, "_file_manager", None)
        if not manager and report_obj and hasattr(report_obj, "file_manager"):
            manager = report_obj.file_manager

        df = DataMemoryCache.get_dataframe(
            manager, self.source_file_name, self.source_sheet or own_cfg.get("source_file", ""), fallback_df=self.dataframe
        )
        if df is None or len(df) == 0:
            return self.wrap_layout('<div class="block-card" style="padding:40px; text-align:center; color:#888;">Нет данных для карты</div>')

        cols = [str(c) for c in df.columns]
        num_cols = [str(c) for c in df.select_dtypes(include="number").columns]
        str_cols = [c for c in cols if c not in num_cols]

        if not self.loc_col or self.loc_col not in df.columns:
            for cand in str_cols:
                if any(k in cand.lower() for k in ("регион", "город", "филиал", "колонн", "маршрут", "тип", "марк")):
                    self.loc_col = cand
                    break
            if not self.loc_col:
                self.loc_col = str_cols[0] if str_cols else cols[0]

        if not self.value_col or self.value_col not in df.columns:
            for cand in cols:
                if any(k in cand.lower() for k in ("факт", "расход", "норм", "сумм")):
                    self.value_col = cand
                    break
            if not self.value_col:
                self.value_col = num_cols[0] if num_cols else cols[-1]

        work = df.copy()
        work["_val"] = _to_num_series(work[self.value_col]) if self.agg_func != "count" else 1.0
        work["_loc"] = work[self.loc_col].fillna("—").astype(str).str.strip()

        plot_div_id = f"ea-plotly-{self.id}"
        c_scale = self.palette if self.palette in ("Greens", "Blues", "Viridis", "YlOrRd", "Tealgrn") else "Greens"
        agg_fn = {"sum": "sum", "mean": "mean", "count": "count", "max": "max", "min": "min"}.get(self.agg_func, "sum")
        max_items = max(5, int(self.top_n or 20))

        try:
            grouped = work.groupby("_loc", as_index=False)["_val"].agg(agg_fn)
            if self.map_mode == "choropleth":
                fig = px.choropleth(
                    grouped,
                    locations="_loc",
                    locationmode="country names",
                    color="_val",
                    title=f"{self.title}: {self.loc_col} → {self.value_col}",
                    color_continuous_scale=c_scale,
                    labels={"_loc": self.loc_col, "_val": self.value_col},
                )
                fig.update_geos(fitbounds="locations", visible=True, showcountries=True)
            elif self.map_mode == "treemap":
                top_g = grouped.nlargest(max_items, "_val")
                fig = px.treemap(
                    top_g,
                    path=["_loc"],
                    values="_val",
                    color="_val",
                    color_continuous_scale=c_scale,
                    title=f"{self.title}: {self.loc_col} → {self.value_col}",
                )
            else:
                top_g = grouped.sort_values(by="_val", ascending=True).tail(max_items)
                fig = px.bar(
                    top_g,
                    x="_val",
                    y="_loc",
                    orientation="h",
                    color="_val",
                    text_auto=".2s",
                    color_continuous_scale=c_scale,
                    title=f"{self.title}: {self.loc_col} → {self.value_col}",
                    labels={"_loc": self.loc_col, "_val": self.value_col},
                )
            target_h = max(400, int(self.min_height or 0))
            fig.update_layout(height=target_h, margin=dict(t=45, l=20, r=20, b=20))
            chart_div = pio.to_html(fig, include_plotlyjs=False, full_html=False, div_id=plot_div_id, config={"responsive": True})
        except Exception as e:
            chart_div = f"<p style='color:red;'>Ошибка рендера карты: {e}</p>"

        inner = f'<div class="block" style="width:100%;"><div class="block-card" style="padding:16px; width:100%; box-sizing:border-box;">{chart_div}</div></div>'
        return self.wrap_layout(inner)

# ============================================================
# График Plotly
# ============================================================

_PALETTE_HEX = {
    "corporate": ["#2b7fff", "#87C800", "#ff9f1c", "#e71d36", "#6f42c1", "#20c997", "#fd7e14"],
    "emerald":   ["#003F0B", "#2bb24c", "#87C800", "#52b788", "#74c69d", "#95d5b2", "#b7e4c7"],
    "sunset":    ["#f72585", "#7209b7", "#3a0ca3", "#4361ee", "#4cc9f0", "#ff9e00", "#ff0055"],
    "pastel":    ["#60a5fa", "#34d399", "#fbbf24", "#f87171", "#a78bfa", "#f472b6", "#38bdf8"],
}


def _iter_all_report_blocks(blocks_list):
    """Рекурсивно обходит все блоки раздела, включая дочерние блоки внутри контейнеров."""
    for b in (blocks_list or []):
        yield b
        b_type = b.get("type") if isinstance(b, dict) else getattr(b, "type", "")
        if b_type == "container":
            b_cfg = b.get("config", {}) if isinstance(b, dict) else (getattr(b, "config", {}) or {})
            children = b_cfg.get("children", [])
            if children:
                yield from _iter_all_report_blocks(children)


def _find_report_and_config(block_obj) -> tuple[object, dict]:
    """Находит объект Report, FileManager и актуальный словарь config для блока."""
    import inspect
    report_obj = getattr(block_obj, "_report_ref", None)
    fm_obj = getattr(block_obj, "_file_manager", None)
    found_cfg = dict(getattr(block_obj, "config", {}) or {})

    frame = inspect.currentframe()
    try:
        f = frame.f_back
        while f is not None:
            loc = f.f_locals
            if report_obj is None:
                if "report" in loc and hasattr(loc["report"], "sections"):
                    report_obj = loc["report"]
                elif "ctx" in loc and hasattr(loc["ctx"], "report") and loc["ctx"].report is not None:
                    report_obj = loc["ctx"].report
                elif "self" in loc and hasattr(loc["self"], "report") and hasattr(loc["self"].report, "sections"):
                    report_obj = loc["self"].report
                elif "self" in loc and hasattr(loc["self"], "_report_ref") and loc["self"]._report_ref is not None:
                    report_obj = loc["self"]._report_ref
            if fm_obj is None:
                if "file_manager" in loc and loc["file_manager"] is not None:
                    fm_obj = loc["file_manager"]
                elif "ctx" in loc and getattr(loc["ctx"], "file_manager", None) is not None:
                    fm_obj = loc["ctx"].file_manager
                elif "self" in loc and getattr(loc["self"], "file_manager", None) is not None:
                    fm_obj = loc["self"].file_manager
            if not found_cfg and "spec" in loc:
                sp = loc["spec"]
                sp_id = sp.get("id") if isinstance(sp, dict) else getattr(sp, "id", None)
                if sp_id == getattr(block_obj, "id", None):
                    sp_cfg = sp.get("config") if isinstance(sp, dict) else getattr(sp, "config", None)
                    if isinstance(sp_cfg, dict):
                        found_cfg = dict(sp_cfg)
            f = f.f_back
    finally:
        del frame

    # Если FileManager ещё не найден, проверяем верхние виджеты приложения (MainWindow)
    if fm_obj is None:
        if report_obj is not None and getattr(report_obj, "file_manager", None) is not None:
            fm_obj = report_obj.file_manager
        else:
            try:
                from PySide6.QtWidgets import QApplication
                app = QApplication.instance()
                if app is not None:
                    for w in app.topLevelWidgets():
                        if getattr(w, "file_manager", None) is not None:
                            fm_obj = w.file_manager
                            break
            except Exception:
                pass

    if fm_obj is not None:
        block_obj._file_manager = fm_obj
        if report_obj is not None and getattr(report_obj, "file_manager", None) is None:
            report_obj.file_manager = fm_obj

    if report_obj is not None and hasattr(report_obj, "sections"):
        target_id = getattr(block_obj, "id", None)
        matched_in_report = False
        for sec in report_obj.sections:
            for b in _iter_all_report_blocks(getattr(sec, "blocks", [])):
                b_id = b.get("id") if isinstance(b, dict) else getattr(b, "id", None)
                if b_id == target_id:
                    b_cfg = b.get("config", {}) if isinstance(b, dict) else (getattr(b, "config", {}) or {})
                    if isinstance(b_cfg, dict):
                        found_cfg = dict(b_cfg)
                        matched_in_report = True
                    break
            if matched_in_report:
                break

    return report_obj, found_cfg


_RU_MONTHS_ORDER = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]

_RU_MONTH_PREFIX_MAP = {
    "янв": (1, "Январь"),
    "jan": (1, "Январь"),
    "фев": (2, "Февраль"),
    "feb": (2, "Февраль"),
    "мар": (3, "Март"),
    "mar": (3, "Март"),
    "апр": (4, "Апрель"),
    "apr": (4, "Апрель"),
    "май": (5, "Май"),
    "мая": (5, "Май"),
    "may": (5, "Май"),
    "июн": (6, "Июнь"),
    "jun": (6, "Июнь"),
    "июл": (7, "Июль"),
    "jul": (7, "Июль"),
    "авг": (8, "Август"),
    "aug": (8, "Август"),
    "сен": (9, "Сентябрь"),
    "sep": (9, "Сентябрь"),
    "окт": (10, "Октябрь"),
    "oct": (10, "Октябрь"),
    "ноя": (11, "Ноябрь"),
    "nov": (11, "Ноябрь"),
    "дек": (12, "Декабрь"),
    "dec": (12, "Декабрь"),
}


def _extract_month_info(s: pd.Series) -> tuple[pd.Series, pd.Series]:
    """
    Точно извлекает месяц из дат только 1 раз и сохраняет результат в оперативной памяти (RAM).
    """
    s = _ensure_series(s)
    cache_key = (id(s), len(s), str(getattr(s, "name", "")))
    with DataMemoryCache._lock:
        cached_m = DataMemoryCache._month_series_cache.get(cache_key)
        if cached_m is not None:
            DataMemoryCache._month_series_cache.move_to_end(cache_key)
            return cached_m

    names = pd.Series(index=s.index, dtype="object")
    nums = pd.Series(index=s.index, dtype="float64")

    # 1. Если столбец уже в формате datetime
    if pd.api.types.is_datetime64_any_dtype(s):
        m_num = s.dt.month
        valid = m_num.notna() & (m_num >= 1) & (m_num <= 12)
        nums[valid] = m_num[valid]
        names[valid] = m_num[valid].astype(int).map(lambda m: _RU_MONTHS_ORDER[m - 1])
        res = (names.fillna(""), nums.fillna(99))
        DataMemoryCache._put_lru(DataMemoryCache._month_series_cache, cache_key, res, DataMemoryCache._MAX_SERIES, owner_obj=s)
        return res

    str_s = s.fillna("").astype(str).str.strip()

    # 2. Прямое извлечение месяца из дат вида YYYY-MM-DD (2026-01-12) и DD.MM.YYYY (12.01.2026)
    m_iso = str_s.str.extract(r"^\d{4}[-/.](\d{1,2})[-/.]\d{1,2}", expand=False)
    m_dmy = str_s.str.extract(r"^\d{1,2}[-/.](\d{1,2})[-/.]\d{2,4}", expand=False)
    m_extracted = pd.to_numeric(m_iso.fillna(m_dmy), errors="coerce")

    valid_regex = m_extracted.notna() & (m_extracted >= 1) & (m_extracted <= 12)
    if valid_regex.any():
        nums[valid_regex] = m_extracted[valid_regex]
        names[valid_regex] = m_extracted[valid_regex].astype(int).map(lambda m: _RU_MONTHS_ORDER[m - 1])

    # 3. Если остались текстовые названия месяцев ("Январь", "01_Январь" и т.д.)
    rem_mask = names.isna() & (str_s != "")
    if rem_mask.any():
        low_s = str_s[rem_mask].str.lower()
        for pref, (m_idx, m_title) in _RU_MONTH_PREFIX_MAP.items():
            mask = low_s.str.contains(pref, regex=False)
            if mask.any():
                matched_idx = low_s.index[mask]
                names[matched_idx] = m_title
                nums[matched_idx] = m_idx

    res = (names.fillna(""), nums.fillna(99))
    DataMemoryCache._put_lru(DataMemoryCache._month_series_cache, cache_key, res, DataMemoryCache._MAX_SERIES, owner_obj=s)
    return res


_CHART_ANIM_ASSETS_HTML = r"""
<style id="ea-chart-anim-css">
@keyframes eaZoomIn {
    0%   { opacity: 0; transform: scale(0.92); }
    100% { opacity: 1; transform: scale(1); }
}
@keyframes eaZoomOut {
    0%   { opacity: 0; transform: scale(1.05); }
    100% { opacity: 1; transform: scale(1); }
}
@keyframes eaFadeUp {
    0%   { opacity: 0; transform: translateY(10px); }
    100% { opacity: 1; transform: translateY(0); }
}
@keyframes eaSlideUp {
    0%   { opacity: 0; transform: translateY(24px); }
    100% { opacity: 1; transform: translateY(0); }
}
@keyframes eaSlideLeft {
    0%   { opacity: 0; transform: translateX(-26px); }
    100% { opacity: 1; transform: translateX(0); }
}
@keyframes eaFadeOnly {
    0%   { opacity: 0; }
    100% { opacity: 1; }
}
@keyframes eaPieSpin {
    0%   { opacity: 0; transform: rotate(-95deg) scale(0.86); }
    100% { opacity: 1; transform: rotate(0deg) scale(1); }
}
@keyframes eaPieSpinBack {
    0%   { opacity: 0; transform: rotate(75deg) scale(1.04); }
    100% { opacity: 1; transform: rotate(0deg) scale(1); }
}

.ea-anim-zoom-in    { animation: eaZoomIn var(--ea-anim-dur, 480ms) cubic-bezier(0.22, 1, 0.36, 1) both; }
.ea-anim-zoom-out   { animation: eaZoomOut var(--ea-anim-dur, 480ms) cubic-bezier(0.22, 1, 0.36, 1) both; }
.ea-anim-fade-up    { animation: eaFadeUp var(--ea-anim-dur, 480ms) cubic-bezier(0.22, 1, 0.36, 1) both; }
.ea-anim-slide-up   { animation: eaSlideUp var(--ea-anim-dur, 480ms) cubic-bezier(0.22, 1, 0.36, 1) both; }
.ea-anim-slide-left { animation: eaSlideLeft var(--ea-anim-dur, 480ms) cubic-bezier(0.22, 1, 0.36, 1) both; }
.ea-anim-fade-only  { animation: eaFadeOnly var(--ea-anim-dur, 480ms) ease-out both; }
.ea-anim-refresh    { animation: eaFadeUp 260ms ease-out both; }
.ea-anim-pie-spin {
    transform-box: fill-box;
    transform-origin: center center;
    animation: eaPieSpin var(--ea-anim-dur, 480ms) cubic-bezier(0.22, 1, 0.36, 1) both;
}
.ea-anim-pie-spin-back {
    transform-box: fill-box;
    transform-origin: center center;
    animation: eaPieSpinBack var(--ea-anim-dur, 480ms) cubic-bezier(0.22, 1, 0.36, 1) both;
}

.ea-chart-card {
    position: relative;
    transition: box-shadow 0.25s ease, border-color 0.25s ease,
                opacity 0.42s cubic-bezier(0.22, 1, 0.36, 1),
                transform 0.42s cubic-bezier(0.22, 1, 0.36, 1);
}
.ea-chart-card:hover {
    box-shadow: 0 10px 26px rgba(15, 23, 42, 0.07);
}
.ea-chart-card.ea-reveal-hidden {
    opacity: 0;
    transform: translateY(16px);
}
.ea-chart-card.ea-reveal-visible {
    opacity: 1;
    transform: translateY(0);
}
.kpi-card {
    transition: transform 0.22s ease, box-shadow 0.22s ease;
}
.kpi-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 20px rgba(15, 23, 42, 0.08);
}

.ea-chart-topbar {
    position: absolute;
    top: 10px;
    right: 12px;
    z-index: 12;
    display: flex;
    align-items: center;
    gap: 8px;
}
.ea-chart-collapsed-title {
    display: none;
    font-size: 13.5px;
    font-weight: 700;
    color: #003F0B;
    user-select: none;
}
.ea-chart-collapsed-hint {
    font-size: 11.5px;
    font-weight: 500;
    color: #64748b;
    margin-left: 6px;
}
.ea-chart-card.ea-collapsed {
    padding-top: 11px !important;
    padding-bottom: 11px !important;
}
.ea-chart-card.ea-collapsed .ea-chart-topbar {
    position: static;
    width: 100%;
    justify-content: space-between;
    cursor: pointer;
}
.ea-chart-card.ea-collapsed .ea-chart-collapsed-title {
    display: inline-flex;
    align-items: center;
    gap: 6px;
}
.ea-chart-toggle-btn {
    width: 26px;
    height: 26px;
    border-radius: 6px;
    border: 1px solid #e2e8f0;
    background: rgba(255, 255, 255, 0.92);
    color: #475569;
    font-size: 13px;
    line-height: 1;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    transition: background 0.2s ease, border-color 0.2s ease, color 0.2s ease;
}
.ea-chart-toggle-btn:hover {
    border-color: #87C800;
    color: #003F0B;
    background: #f1f8e9;
}
.ea-toggle-icon {
    display: inline-block;
    transition: transform 0.34s cubic-bezier(0.22, 1, 0.36, 1);
}
.ea-chart-card.ea-collapsed .ea-toggle-icon {
    transform: rotate(-90deg);
}

.ea-chart-collapsible {
    display: grid;
    grid-template-rows: 1fr;
    opacity: 1;
    transform: translateY(0) scale(1);
    transform-origin: top center;
    transition: grid-template-rows 0.38s cubic-bezier(0.22, 1, 0.36, 1),
                opacity 0.24s ease,
                transform 0.38s cubic-bezier(0.22, 1, 0.36, 1);
}
.ea-chart-collapsible-inner {
    overflow: hidden;
    min-height: 0;
}
.ea-chart-card.ea-collapsed .ea-chart-collapsible {
    grid-template-rows: 0fr;
    opacity: 0;
    transform: translateY(-6px) scale(0.985);
    pointer-events: none;
}

/* Подсветка секторов круга БЕЗ transition на hovertext (подсказка больше не вылетает из угла) */
.js-plotly-plot .pielayer .slice path {
    transition: filter 0.2s ease;
}
.js-plotly-plot .pielayer .slice:hover path {
    filter: brightness(1.06);
}
.ea-pie-month-btn:hover, .ea-dut-btn:hover {
    filter: brightness(0.97);
}

@media (prefers-reduced-motion: reduce) {
    .ea-chart-card, .ea-chart-collapsible, .ea-toggle-icon,
    .ea-anim-zoom-in, .ea-anim-zoom-out, .ea-anim-fade-up,
    .ea-anim-slide-up, .ea-anim-slide-left, .ea-anim-fade-only,
    .ea-anim-pie-spin, .ea-anim-pie-spin-back, .ea-anim-refresh {
        animation: none !important;
        transition: none !important;
    }
}
</style>
<script>
if (typeof window._eaAnimReady === 'undefined') {
    window._eaAnimReady = true;

    window._eaReducedMotion = function() {
        return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    };

    window._eaGetChartAnimCfg = function(el) {
        var card = (el && el.classList && el.classList.contains('ea-chart-card'))
            ? el
            : (el && typeof el.closest === 'function' ? el.closest('.ea-chart-card') : null);
        var style = (card && card.getAttribute('data-anim-style')) || 'auto';
        var speed = Number((card && card.getAttribute('data-anim-speed')) || 480);
        if (!speed || isNaN(speed)) speed = 480;
        return { style: style, speed: speed };
    };

    window._eaAnimClasses = [
        'ea-anim-zoom-in', 'ea-anim-zoom-out', 'ea-anim-fade-up',
        'ea-anim-slide-up', 'ea-anim-slide-left', 'ea-anim-fade-only'
    ];

    /* 1. Анимация переходов при смене данных / среза / Drill-Down */
    window._eaPlayElAnim = function(el, animKind) {
        if (!el || window._eaReducedMotion()) return;
        var ac = window._eaGetChartAnimCfg(el);
        if (ac.style === 'none') return;
        el.style.setProperty('--ea-anim-dur', ac.speed + 'ms');

        var pieTraces = el.querySelectorAll('.pielayer .trace');
        var useSpin = (ac.style === 'spin') || (ac.style === 'auto' && pieTraces && pieTraces.length > 0);
        if (useSpin && pieTraces && pieTraces.length) {
            var pieCls = (animKind === 'drill-out') ? 'ea-anim-pie-spin-back' : 'ea-anim-pie-spin';
            pieTraces.forEach(function(pt) {
                pt.style.setProperty('--ea-anim-dur', ac.speed + 'ms');
                pt.classList.remove('ea-anim-pie-spin', 'ea-anim-pie-spin-back');
                void pt.getBoundingClientRect();
                pt.classList.add(pieCls);
            });
            return;
        }

        if (ac.style === 'cascade') {
            window._eaPlayCascade(el, ac.speed);
            return;
        }

        var cls = 'ea-anim-fade-up';
        if (ac.style === 'zoom') {
            cls = (animKind === 'drill-out') ? 'ea-anim-zoom-out' : 'ea-anim-zoom-in';
        } else if (ac.style === 'slide_up') {
            cls = 'ea-anim-slide-up';
        } else if (ac.style === 'slide_left') {
            cls = 'ea-anim-slide-left';
        } else if (ac.style === 'fade') {
            cls = 'ea-anim-fade-only';
        } else {
            cls = (animKind === 'drill-in')
                ? 'ea-anim-zoom-in'
                : ((animKind === 'drill-out') ? 'ea-anim-zoom-out' : 'ea-anim-fade-up');
        }

        window._eaAnimClasses.forEach(function(c) { el.classList.remove(c); });
        void el.offsetWidth;
        el.classList.add(cls);
    };

    /* Каскадная анимация элементов (столбцы / сектора / линии по очереди) */
    window._eaPlayCascade = function(plotDiv, dur) {
        var step = Math.max(18, Math.min(55, Math.round(dur / 14)));
        var items = plotDiv.querySelectorAll('.barlayer .point, .pielayer .slice, .scatterlayer .trace');
        if (!items.length) {
            window._eaPlayElAnim(plotDiv, 'fade');
            return;
        }
        items.forEach(function(item, idx) {
            var delay = Math.min(idx, 18) * step;
            item.style.transition = 'none';
            item.style.opacity = '0';
            item.style.transformBox = 'fill-box';
            item.style.transformOrigin = 'center bottom';
            item.style.transform = 'translateY(10px) scale(0.96)';
            void item.getBoundingClientRect();
            item.style.transition = 'transform ' + dur + 'ms cubic-bezier(0.22, 1, 0.36, 1) ' + delay + 'ms, opacity ' + Math.round(dur * 0.7) + 'ms ease-out ' + delay + 'ms';
            item.style.opacity = '1';
            item.style.transform = 'translateY(0) scale(1)';
            setTimeout(function() {
                item.style.transition = '';
                item.style.transform = '';
                item.style.opacity = '';
            }, dur + delay + 80);
        });
    };

    /* 2. Первичная анимация при появлении карточки в кадре (ждёт загрузку Plotly из CDN) */
    window._eaAnimateChartEntrance = function(cardEl, retry) {
        if (!cardEl || window._eaReducedMotion()) return;
        var ac = window._eaGetChartAnimCfg(cardEl);
        if (ac.style === 'none') return;

        var plots = cardEl.querySelectorAll('.js-plotly-plot');
        if (!plots.length) {
            if ((retry || 0) < 50) {
                setTimeout(function() { window._eaAnimateChartEntrance(cardEl, (retry || 0) + 1); }, 140);
            }
            return;
        }
        var hasSvg = (typeof Plotly !== 'undefined');
        if (hasSvg) {
            hasSvg = false;
            plots.forEach(function(p) {
                if (p.querySelector('svg.main-svg .plot, svg.main-svg .pielayer')) hasSvg = true;
            });
        }
        if (!hasSvg) {
            if ((retry || 0) < 50) {
                setTimeout(function() { window._eaAnimateChartEntrance(cardEl, (retry || 0) + 1); }, 140);
            }
            return;
        }

        var dur = ac.speed;
        plots.forEach(function(plotDiv) {
            if (plotDiv._eaEntrancePlayed) return;
            plotDiv._eaEntrancePlayed = true;
            plotDiv.style.setProperty('--ea-anim-dur', dur + 'ms');

            /* Если выбран конкретный стиль (не auto) — применяем его напрямую */
            if (ac.style !== 'auto') {
                window._eaPlayElAnim(plotDiv, 'drill-in');
                return;
            }

            /* Режим "auto": каждому типу графика — своя лучшая анимация */
            plotDiv.querySelectorAll('.scatterlayer path.js-line').forEach(function(path, idx) {
                try {
                    var cs = window.getComputedStyle(path);
                    var origDash = path.style.strokeDasharray || '';
                    var isDashed = cs.strokeDasharray && cs.strokeDasharray !== 'none' && cs.strokeDasharray !== '0px';
                    var len = (typeof path.getTotalLength === 'function') ? path.getTotalLength() : 0;
                    var lineDur = Math.round(dur * 1.25);
                    if (!isDashed && len > 2 && isFinite(len)) {
                        path.style.transition = 'none';
                        path.style.strokeDasharray = len + ' ' + len;
                        path.style.strokeDashoffset = String(len);
                        void path.getBoundingClientRect();
                        path.style.transition = 'stroke-dashoffset ' + lineDur + 'ms cubic-bezier(0.22, 1, 0.36, 1) ' + (idx * 65) + 'ms';
                        path.style.strokeDashoffset = '0';
                        setTimeout(function() {
                            path.style.transition = '';
                            path.style.strokeDasharray = origDash;
                            path.style.strokeDashoffset = '';
                        }, lineDur + 120 + idx * 65);
                    } else {
                        path.style.opacity = '0';
                        void path.getBoundingClientRect();
                        path.style.transition = 'opacity ' + dur + 'ms ease-out ' + (idx * 60) + 'ms';
                        path.style.opacity = '1';
                        setTimeout(function() { path.style.transition = ''; path.style.opacity = ''; }, dur + 100 + idx * 60);
                    }
                } catch (e) {}
            });

            plotDiv.querySelectorAll('.scatterlayer .points').forEach(function(g) {
                g.style.opacity = '0';
                void g.getBoundingClientRect();
                g.style.transition = 'opacity ' + Math.round(dur * 0.7) + 'ms ease-out ' + Math.round(dur * 0.35) + 'ms';
                g.style.opacity = '1';
                setTimeout(function() { g.style.transition = ''; g.style.opacity = ''; }, dur + 120);
            });

            var hasNegBars = Array.isArray(plotDiv.data) && plotDiv.data.some(function(tr) {
                return tr && tr.type === 'bar' && Array.isArray(tr.y) && tr.y.some(function(v) { return Number(v) < 0; });
            });
            plotDiv.querySelectorAll('.barlayer .bars').forEach(function(bGroup, idx) {
                bGroup.style.transformBox = 'fill-box';
                bGroup.style.transformOrigin = hasNegBars ? 'center center' : 'center bottom';
                bGroup.style.opacity = '0';
                bGroup.style.transform = hasNegBars ? 'translateY(10px)' : 'scaleY(0.18)';
                void bGroup.getBoundingClientRect();
                bGroup.style.transition = 'transform ' + dur + 'ms cubic-bezier(0.22, 1, 0.36, 1) ' + (idx * 55) + 'ms, opacity ' + Math.round(dur * 0.65) + 'ms ease-out';
                bGroup.style.opacity = '1';
                bGroup.style.transform = hasNegBars ? 'translateY(0)' : 'scaleY(1)';
                setTimeout(function() {
                    bGroup.style.transition = '';
                    bGroup.style.transform = '';
                    bGroup.style.opacity = '';
                }, dur + 120 + idx * 55);
            });

            plotDiv.querySelectorAll('.pielayer .trace').forEach(function(pTrace, idx) {
                var pieDur = Math.round(dur * 1.25);
                pTrace.style.transformBox = 'fill-box';
                pTrace.style.transformOrigin = 'center center';
                pTrace.style.opacity = '0';
                pTrace.style.transform = 'rotate(-95deg) scale(0.86)';
                void pTrace.getBoundingClientRect();
                pTrace.style.transition = 'transform ' + pieDur + 'ms cubic-bezier(0.22, 1, 0.36, 1) ' + (idx * 70) + 'ms, opacity ' + Math.round(dur * 0.75) + 'ms ease-out ' + (idx * 70) + 'ms';
                pTrace.style.opacity = '1';
                pTrace.style.transform = 'rotate(0deg) scale(1)';
                setTimeout(function() {
                    pTrace.style.transition = '';
                    pTrace.style.transform = '';
                    pTrace.style.opacity = '';
                }, pieDur + 120 + idx * 70);
            });
        });
    };

    /* 3. Проверка возможности живого морфинга */
    window._eaCanMorphTraces = function(oldTraces, newTraces) {
        if (!Array.isArray(oldTraces) || !Array.isArray(newTraces)) return false;
        if (oldTraces.length === 0 || oldTraces.length !== newTraces.length) return false;
        for (var i = 0; i < newTraces.length; i++) {
            var nt = newTraces[i], ot = oldTraces[i];
            if (!nt || !ot) return false;
            var nType = nt.type || 'scatter', oType = ot.type || 'scatter';
            if (nType === 'pie' || nType === 'treemap' || nType === 'sunburst' || nType !== oType) return false;
            if (!Array.isArray(nt.x) || !Array.isArray(ot.x) || nt.x.length !== ot.x.length || nt.x.length === 0) return false;
            for (var j = 0; j < nt.x.length; j++) {
                if (String(nt.x[j]) !== String(ot.x[j])) return false;
            }
        }
        return true;
    };

    /* 4. Единая анимированная перерисовка Plotly с учётом выбранного стиля и скорости */
    window._eaAnimatedPlotlyReact = function(plotDiv, traces, animKind) {
        if (!plotDiv || !traces || typeof Plotly === 'undefined') return;
        var ac = window._eaGetChartAnimCfg(plotDiv);
        var cleanTraces = JSON.parse(JSON.stringify(traces));
        var isPieOrTree = cleanTraces.some(function(t) {
            return t.type === 'pie' || t.type === 'treemap' || t.type === 'sunburst';
        });
        var reduced = window._eaReducedMotion() || (ac.style === 'none');
        var canMorph = (!reduced && ac.style === 'auto' && !isPieOrTree && (!animKind || animKind === 'auto') && window._eaCanMorphTraces(plotDiv.data, cleanTraces));

        if (!plotDiv.layout) plotDiv.layout = {};
        plotDiv.layout.datarevision = (plotDiv.layout.datarevision || 0) + 1;

        if (!isPieOrTree) {
            if (plotDiv.layout.xaxis)  { delete plotDiv.layout.xaxis.range;  plotDiv.layout.xaxis.autorange = true; }
            if (plotDiv.layout.yaxis)  { delete plotDiv.layout.yaxis.range;  plotDiv.layout.yaxis.autorange = true; }
            if (plotDiv.layout.yaxis2) { delete plotDiv.layout.yaxis2.range; plotDiv.layout.yaxis2.autorange = true; }
            if (plotDiv.layout.legend && plotDiv.layout.legend.orientation === 'h' && Number(plotDiv.layout.legend.y) < 0) {
                var maxXL = 0;
                cleanTraces.forEach(function(t) {
                    if (Array.isArray(t.x)) {
                        t.x.forEach(function(xv) {
                            var s = String(xv || '');
                            if (s.length > maxXL) maxXL = s.length;
                        });
                    }
                });
                var hEst = Math.max(180, (plotDiv.offsetHeight || 380) - 130);
                var dropPx = 42 + maxXL * 2.35;
                plotDiv.layout.legend.y = -Math.min(0.68, Math.max(0.30, dropPx / hEst));
                if (plotDiv.layout.margin) plotDiv.layout.margin.b = 65 + Math.max(0, (maxXL - 12) * 3) + 48;
            }
        }

        if (canMorph) {
            plotDiv.layout.transition = { duration: ac.speed, easing: 'cubic-in-out' };
            Plotly.react(plotDiv, cleanTraces, plotDiv.layout);
        } else {
            delete plotDiv.layout.transition;
            Plotly.react(plotDiv, cleanTraces, plotDiv.layout);
            if (!reduced) {
                window._eaPlayElAnim(plotDiv, animKind || 'fade');
            }
        }
    };

    /* 5. Плавный пересчёт итоговых чисел (Count-Up) в шапках графиков */
    window._eaParseFmtNum = function(txt) {
        var s = String(txt || '').trim();
        var m = s.match(/^([+-]?)([\d\s,\u00a0]+(?:\.\d+)?)(\s*[%а-яА-Яa-zA-Z.]*)$/);
        if (!m) return null;
        var numPart = m[2];
        var sep = numPart.indexOf(',') !== -1 ? ',' : (numPart.indexOf(' ') !== -1 ? ' ' : '');
        var decIdx = numPart.indexOf('.');
        var decimals = decIdx >= 0 ? (numPart.length - decIdx - 1) : 0;
        var val = parseFloat((m[1] === '-' ? '-' : '') + numPart.replace(/[\s,\u00a0]/g, ''));
        if (isNaN(val)) return null;
        return { val: val, plus: m[1] === '+', sep: sep, decimals: decimals, suffix: m[3] || '' };
    };

    window._eaFormatLike = function(val, meta) {
        var sign = val < -1e-9 ? '-' : (meta.plus && val > 1e-9 ? '+' : '');
        var absStr = Math.abs(val).toFixed(meta.decimals);
        var parts = absStr.split('.');
        if (meta.sep) {
            parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, meta.sep);
        }
        return sign + parts.join('.') + meta.suffix;
    };

    window._eaUpdateHeaderAnimated = function(hdrEl, newHtml) {
        if (!hdrEl) return;
        var ac = window._eaGetChartAnimCfg(hdrEl);
        var prevVals = hdrEl._eaPrevNums || [];
        hdrEl.innerHTML = newHtml;
        var bolds = hdrEl.querySelectorAll('b');
        var nextVals = [];
        var reduced = window._eaReducedMotion() || (ac.style === 'none');
        var tasks = [];

        bolds.forEach(function(b, idx) {
            var parsed = window._eaParseFmtNum(b.textContent);
            if (!parsed) {
                nextVals.push(null);
                return;
            }
            nextVals.push(parsed.val);
            if (!reduced && prevVals[idx] !== undefined && prevVals[idx] !== null && Math.abs(prevVals[idx] - parsed.val) > 1e-6) {
                tasks.push({ el: b, from: prevVals[idx], to: parsed.val, meta: parsed });
            }
        });
        hdrEl._eaPrevNums = nextVals;

        if (!tasks.length) return;
        var startTs = performance.now();
        var dur = Math.min(800, Math.max(180, Math.round(ac.speed * 0.72)));
        function tick(now) {
            var t = Math.min(1, (now - startTs) / dur);
            var eased = 1 - Math.pow(1 - t, 3);
            for (var i = 0; i < tasks.length; i++) {
                var tk = tasks[i];
                var cur = tk.from + (tk.to - tk.from) * eased;
                tk.el.textContent = window._eaFormatLike(t >= 1 ? tk.to : cur, tk.meta);
            }
            if (t < 1) requestAnimationFrame(tick);
        }
        requestAnimationFrame(tick);
    };

    /* 6. Плавное сворачивание и раскрытие карточки графика */
    window.toggleEaChartCard = function(uid, ev) {
        if (ev && typeof ev.stopPropagation === 'function') ev.stopPropagation();
        var card = document.getElementById(uid + '-card');
        if (!card) return;
        var willCollapse = !card.classList.contains('ea-collapsed');
        card.classList.toggle('ea-collapsed', willCollapse);
        var btn = card.querySelector('.ea-chart-toggle-btn');
        if (btn) btn.title = willCollapse ? 'Развернуть график' : 'Свернуть график';

        setTimeout(function() {
            if (!willCollapse && typeof Plotly !== 'undefined') {
                card.querySelectorAll('.js-plotly-plot').forEach(function(p) {
                    try { Plotly.Plots.resize(p); } catch (e) {}
                });
            }
            window.dispatchEvent(new Event('resize'));
        }, 390);
    };

    /* 7. Scroll Reveal при прокрутке страницы */
    window._eaInitCardReveal = function() {
        var cards = document.querySelectorAll('.ea-chart-card:not([data-ea-reveal-bound])');
        if (!cards.length) return;
        if (window._eaReducedMotion() || typeof IntersectionObserver === 'undefined') {
            cards.forEach(function(c) { c.setAttribute('data-ea-reveal-bound', '1'); });
            return;
        }
        var obs = new IntersectionObserver(function(entries) {
            entries.forEach(function(entry) {
                if (entry.isIntersecting) {
                    entry.target.classList.remove('ea-reveal-hidden');
                    entry.target.classList.add('ea-reveal-visible');
                    window._eaAnimateChartEntrance(entry.target, 0);
                    obs.unobserve(entry.target);
                }
            });
        }, { threshold: 0.08 });

        cards.forEach(function(c) {
            c.setAttribute('data-ea-reveal-bound', '1');
            var ac = window._eaGetChartAnimCfg(c);
            if (ac.style === 'none') {
                c.classList.add('ea-reveal-visible');
                return;
            }
            var r = c.getBoundingClientRect();
            if (r.top > window.innerHeight * 0.96) {
                c.classList.add('ea-reveal-hidden');
                obs.observe(c);
            } else {
                c.classList.add('ea-reveal-visible');
                setTimeout(function() { window._eaAnimateChartEntrance(c, 0); }, 80);
            }
        });
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', window._eaInitCardReveal);
    } else {
        setTimeout(window._eaInitCardReveal, 60);
    }
    window.addEventListener('load', function() {
        window._eaInitCardReveal();
        document.querySelectorAll('.ea-chart-card.ea-reveal-visible').forEach(function(c) {
            window._eaAnimateChartEntrance(c, 0);
        });
    });
}
</script>
"""


@dataclass
class PlotlyChartBlock(Block):
    row_multi_mode: str = "separate"
    row_multi_func: str = "sum"
    pie_row_mode: str = "models_with_months"
    show_title: bool = True
    show_axis_labels: bool = True
    type: str = "plotly_chart"
    dataframe: object = None
    source_file_name: str = ""
    source_sheet: str = ""
    multi_y_mode: str = "separate"
    multi_y_func: str = "sum"
    chart_type: str = "bar"
    data_mode: str = "columns"
    x_col: str = ""
    y_col: str = ""
    row_columns: list[str] = field(default_factory=list)
    row_target_val: str = "__ALL_SERIES__"
    clean_col_labels: bool = True
    filter_from_chart: str = ""
    parent_group_col: str = ""
    model_col: str = ""
    date_col: str = ""
    deviation_mode: str = "formula_pct_self"
    calc_formula: str = "((A - B) / B) * 100"
    formula_num: str = "(A - B)"
    formula_den: str = "B"
    formula_mul100: bool = True
    formula_row_scope: str = "all_rows"
    calc_eval_mode: str = "separate"
    calc_group_col: str = ""
    pie_value_display: str = "formula_pct"
    fact_col: str = ""
    norm_col: str = ""
    plate_col: str = ""
    dut_col: str = ""
    pct_col: str = ""
    dut_pct_op: str = "gt"
    dut_pct_val: float = 3.0
    dut_count_mode: str = "unique_ts"
    pie_display_mode: str = "single_interactive"
    filter_col: str = ""
    filter_op: str = ">"
    filter_val: str = ""
    custom_query: str = ""
    title: str = "График данных"
    agg: str = "sum"
    sort_by: str = "value_desc"
    top_n: int = 12
    row_start: int = 0
    row_limit: int = 0
    palette: str = "corporate"
    bg_color: str = "#ffffff"
    legend_pos: str = "right"
    show_legend: bool = True
    show_values: bool = True
    show_grid: bool = True
    font_size: int = 12
    value_label_mode: str = "auto"
    hover_format: str = "default"
    hover_custom_tpl: str = ""
    all_groups_label: str = "Итого (Все категории)"
    prefix_legend_with_group: bool = False
    show_summary_header: bool = True
    show_summary_total: bool = False
    summary_total_label: str = "Σ Итого"
    custom_legend_names: str = ""
    column_aliases: dict = field(default_factory=dict)
    custom_x_title: str = ""
    custom_y_title: str = ""
    min_slice_pct: float = 0.0  # Значение процента для фильтрации
    slice_pct_mode: str = "ge"  # Режим: "ge" ( >= ) или "le" ( <= )
    combo_series: list = field(default_factory=list)
    combo_barmode: str = "group"
    combo_y2_title: str = ""
    combo_show_zero_line: bool = True
    combo_target_val: str = ""
    combo_target_label: str = "Норма / Цель"
    combo_target_color: str = "#e11d48"
    combo_level1_col: str = ""
    combo_level2_col: str = ""
    combo_level3_col: str = ""
    combo_level1_sort: str = "value_desc"
    combo_level2_sort: str = "value_desc"
    combo_level3_sort: str = "value_desc"
    combo_sort_series_idx: int = 0
    bar_text_pos: str = "outside"
    bar_text_angle: str = "0"
    anim_style: str = "auto"
    anim_speed: int = 480

    def _get_bar_text_props(self) -> dict:
        """Возвращает единые настройки положения и угла наклона подписей для столбчатых графиков."""
        pos_mode = str(getattr(self, "bar_text_pos", "outside") or "outside")
        ang_mode = str(getattr(self, "bar_text_angle", "0") or "0")

        props: dict = {"cliponaxis": False}
        if pos_mode == "outside":
            props["textposition"] = "outside"
        elif pos_mode == "inside":
            props["textposition"] = "inside"
            props["insidetextanchor"] = "end"
        elif pos_mode == "inside_middle":
            props["textposition"] = "inside"
            props["insidetextanchor"] = "middle"
        elif pos_mode == "inside_base":
            props["textposition"] = "inside"
            props["insidetextanchor"] = "start"
        else:
            props["textposition"] = "auto"

        if ang_mode in ("0", "-90", "-45", "90"):
            props["textangle"] = int(ang_mode)
        return props

    def _get_col_display_name(self, col_name: str, idx: int = -1) -> str:
        """Возвращает пользовательское имя столбца/легенды, если оно задано в Инспекторе."""
        raw_col = str(col_name or "").strip()
        if not raw_col:
            return ""

        aliases = getattr(self, "column_aliases", None)
        if isinstance(aliases, dict):
            if raw_col in aliases and str(aliases[raw_col]).strip():
                return str(aliases[raw_col]).strip()
            for k, v in aliases.items():
                if str(k).strip().lower() == raw_col.lower() and str(v).strip():
                    return str(v).strip()

        custom_str = str(getattr(self, "custom_legend_names", "") or "").strip()
        if custom_str:
            parts = [p.strip() for p in re.split(r"[,;]", custom_str) if p.strip()]
            kv_map = {}
            pos_list = []
            for p in parts:
                if "=" in p:
                    k_part, v_part = p.split("=", 1)
                    kv_map[k_part.strip().lower()] = v_part.strip()
                else:
                    pos_list.append(p)
            if raw_col.lower() in kv_map and kv_map[raw_col.lower()]:
                return kv_map[raw_col.lower()]
            if 0 <= idx < len(pos_list) and pos_list[idx]:
                return pos_list[idx]

        return raw_col

    def _get_linked_chart_allowed_types(self, fallback_df: pd.DataFrame) -> list[str]:
        """Возвращает список Типов ТС, которые прошли фильтр в связанном первом графике."""
        if not self.filter_from_chart:
            return []
        try:
            report_obj = getattr(self, "_report_ref", None)
            manager = getattr(self, "_file_manager", None)
            if not report_obj or not hasattr(report_obj, "sections"):
                return []

            src_cfg = None
            for sec in report_obj.sections:
                for b in _iter_all_report_blocks(sec.blocks):
                    b_id = b.get("id") if isinstance(b, dict) else getattr(b, "id", "")
                    if b_id == self.filter_from_chart:
                        src_cfg = b.get("config", {}) if isinstance(b, dict) else (getattr(b, "config", {}) or {})
                        break
                if src_cfg:
                    break

            if not src_cfg:
                return []

            sf = src_cfg.get("source_file_name", "")
            ss = src_cfg.get("source_sheet", "") or src_cfg.get("source_file", "")
            src_df = DataMemoryCache.get_dataframe(manager, sf, ss, fallback_df=fallback_df)
            if hasattr(report_obj, "get_block_dataframe"):
                resolved_src = report_obj.get_block_dataframe(src_cfg, fallback_df=src_df)
                if resolved_src is not None:
                    src_df = resolved_src

            if src_df is None or len(src_df) == 0:
                return []

            src_x_col = (
                src_cfg.get("parent_group_col", "")
                if (src_cfg.get("parent_group_col") and src_cfg.get("parent_group_col") in src_df.columns)
                else (src_cfg.get("x_col", "") if (src_cfg.get("x_col") and src_cfg.get("x_col") in src_df.columns) else str(src_df.columns[0]))
            )
            dummy = PlotlyChartBlock(
                id=self.filter_from_chart,
                type="plotly_chart",
                x_col=src_x_col,
                parent_group_col=src_cfg.get("parent_group_col", ""),
                filter_from_chart=src_cfg.get("filter_from_chart", ""),
                filter_col=src_cfg.get("filter_col", ""),
                filter_op=src_cfg.get("filter_op", ">"),
                filter_val=src_cfg.get("filter_val", ""),
                custom_query=src_cfg.get("custom_query", ""),
            )
            dummy._report_ref = report_obj
            dummy._file_manager = manager
            filtered_src_df = dummy._apply_smart_filter(src_df)
            if src_x_col in filtered_src_df.columns:
                return [
                    str(v).strip()
                    for v in filtered_src_df[src_x_col].dropna().unique()
                    if str(v).strip()
                ]
        except Exception as e:
            print(f"[PlotlyChartBlock] Ошибка связи с графиком {self.filter_from_chart}: {e}")
        return []

    def _apply_smart_filter(self, df: pd.DataFrame) -> pd.DataFrame:
        work = _dedup_dataframe_columns(df).copy()

        # 1. Фильтрация по группам (Типам ТС), попавшим в связанный первый график
        allowed_types = self._get_linked_chart_allowed_types(df)
        if allowed_types:
            allowed_lower = {t.lower() for t in allowed_types}
            match_col = (
                self.parent_group_col
                if (self.parent_group_col and self.parent_group_col in work.columns)
                else self.x_col
            )
            # Если в match_col выбран столбец месяцев, автоматически находим столбец с категориями ТС
            if (
                not match_col
                or match_col not in work.columns
                or not work[match_col].astype(str).str.strip().str.lower().isin(allowed_lower).any()
            ):
                for cand_col in work.columns:
                    if work[cand_col].astype(str).str.strip().str.lower().isin(allowed_lower).any():
                        match_col = cand_col
                        break
            if match_col and match_col in work.columns:
                work = work[work[match_col].astype(str).str.strip().str.lower().isin(allowed_lower)]

        # 2. Собственное условие отбора блока
        if self.filter_col and self.filter_col in work.columns:
            col_s = work[self.filter_col]
            op = self.filter_op or ">"
            raw_v = str(self.filter_val or "").strip()

            if op == "not_null":
                work = work[col_s.notna() & (col_s.astype(str).str.strip() != "")]
            elif op == "above_mean":
                num_s = _to_num_series(col_s)
                work = work[num_s > num_s.mean()]
            elif op == "below_mean":
                num_s = _to_num_series(col_s)
                work = work[num_s < num_s.mean()]
            elif raw_v:
                if op in (">", ">=", "<", "<="):
                    num_s = _to_num_series(col_s)
                    v_num = _to_float(raw_v)
                    if op == ">":
                        work = work[num_s > v_num]
                    elif op == ">=":
                        work = work[num_s >= v_num]
                    elif op == "<":
                        work = work[num_s < v_num]
                    elif op == "<=":
                        work = work[num_s <= v_num]
                elif op == "between":
                    parts = [p.strip() for p in raw_v.split(",") if p.strip()]
                    if len(parts) >= 2:
                        num_s = _to_num_series(col_s)
                        v1, v2 = _to_float(parts[0]), _to_float(parts[1])
                        work = work[(num_s >= min(v1, v2)) & (num_s <= max(v1, v2))]
                elif op == "==":
                    work = work[col_s.astype(str).str.strip().str.lower() == raw_v.lower()]
                elif op == "!=":
                    work = work[col_s.astype(str).str.strip().str.lower() != raw_v.lower()]
                elif op == "contains":
                    work = work[col_s.astype(str).str.contains(raw_v, case=False, na=False)]
                elif op == "not_contains":
                    work = work[~col_s.astype(str).str.contains(raw_v, case=False, na=False)]
                elif op == "in_list":
                    allowed = {p.strip().lower() for p in raw_v.split(",") if p.strip()}
                    work = work[col_s.astype(str).str.strip().str.lower().isin(allowed)]

        if self.custom_query and str(self.custom_query).strip():
            work = work.query(str(self.custom_query).strip())

        return work

    def _build_hover_template(self, is_pie: bool = False, has_monthly_data: bool = False) -> str:
        """Формирует шаблон всплывающей подсказки при наведении мыши (hovertemplate)."""
        custom_tpl = str(getattr(self, "hover_custom_tpl", "") or "").strip()
        h_fmt = str(getattr(self, "hover_format", "default") or "default")

        if custom_tpl or h_fmt == "custom":
            if not custom_tpl:
                custom_tpl = "<b>{label}</b><br>Доля: {percent} ({value})<br>{details}" if is_pie else "<b>{x}</b><br>{name}: {value}"
            tpl = custom_tpl.replace("\\n", "<br>")
            if is_pie:
                tpl = (
                    tpl.replace("{label}", "%{label}")
                    .replace("{x}", "%{label}")
                    .replace("{value}", "%{value:,.0f}")
                    .replace("{y}", "%{value:,.0f}")
                    .replace("{percent}", "%{percent}")
                    .replace("{name}", "%{fullData.name}")
                    .replace("{details}", "%{customdata}")
                    .replace("{months}", "%{customdata}")
                )
            else:
                tpl = (
                    tpl.replace("{label}", "%{x}")
                    .replace("{x}", "%{x}")
                    .replace("{value}", "%{y:,.2f}")
                    .replace("{y}", "%{y:,.2f}")
                    .replace("{percent}", "%{y:,.1f}%")
                    .replace("{name}", "%{fullData.name}")
                    .replace("{details}", "%{customdata}")
                    .replace("{months}", "%{customdata}")
                )
            return tpl + "<extra></extra>"

        if is_pie:
            if h_fmt == "label_percent":
                return "<b>%{label}</b>: %{percent}<extra></extra>"
            elif h_fmt == "label_value":
                return "<b>%{label}</b>: %{value:,.0f}<extra></extra>"
            else:
                if has_monthly_data:
                    return "<b>%{label}</b><br>Доля отклонений: <b>%{percent}</b> (%{value:,.0f})<br>%{customdata}<extra></extra>"
                return "<b>%{label}</b><br>Значение: %{value:,.2f} (<b>%{percent}</b>)<extra></extra>"
        else:
            if h_fmt == "label_percent":
                return "<b>%{x}</b><br>%{fullData.name}: %{y:,.1f}%<extra></extra>"
            elif h_fmt == "label_value":
                return "<b>%{x}</b>: %{y:,.2f}<extra></extra>"
            return "<b>%{x}</b><br>%{fullData.name}: <b>%{y:,.2f}</b><extra></extra>"

    def _get_pie_textinfo(self) -> str:
        if not self.show_values:
            return "none"
        mode = str(getattr(self, "value_label_mode", "auto") or "auto")
        if mode == "none":
            return "none"
        if mode == "auto":
            return "percent+label"
        return mode

    def _is_formula_mode(self) -> bool:
        return getattr(self, "deviation_mode", "formula_pct_self") in (
            "formula_pct_self",
            "formula_pct_group",
            "formula_saving_self",
            "formula_ratio_ab",
            "custom_formula",
        )

    def _get_active_formula_str(self) -> str:
        dev_mode = getattr(self, "deviation_mode", "formula_pct_self")
        if dev_mode == "formula_pct_self":
            return "((A - B) / B) * 100"
        if dev_mode == "formula_pct_group":
            return "((A - B) / B_TOTAL) * 100"
        if dev_mode == "formula_saving_self":
            return "((B - A) / B) * 100"
        if dev_mode == "formula_ratio_ab":
            return "(A / B) * 100"
        custom_f = str(getattr(self, "calc_formula", "") or "").strip()
        return custom_f if custom_f else "((A - B) / B) * 100"

    def _eval_custom_formula(
        self,
        a_val: float,
        b_val: float,
        a_total: float,
        b_total: float,
        count_val: int,
        count_total: int,
        diff_count_val: int = 0,
        abs_diff_val: float = 0.0,
    ) -> float:
        """Вычисляет формулу процента/показателя, заданную в Инспекторе."""
        import math
        formula_str = self._get_active_formula_str()
        expr = str(formula_str).strip().upper()
        expr = (
            expr.replace(",", ".")
            .replace("%", "")
            .replace("−", "-")
            .replace("–", "-")
            .replace("×", "*")
            .replace("÷", "/")
            .replace("ФАКТ ОБЩИЙ ГРУППЫ", "ФАКТ_ОБЩИЙ")
            .replace("НОРМАТИВ ОБЩИЙ ГРУППЫ", "НОРМАТИВ_ОБЩИЙ")
            .replace("ФАКТ ОБЩИЙ", "ФАКТ_ОБЩИЙ")
            .replace("НОРМАТИВ ОБЩИЙ", "НОРМАТИВ_ОБЩИЙ")
            .replace("НОРМА ОБЩАЯ", "НОРМАТИВ_ОБЩИЙ")
            .replace("ФАКТ ГРУППЫ", "ФАКТ")
            .replace("НОРМАТИВ ГРУППЫ", "НОРМАТИВ")
        )

        env = {
            "ABS": abs,
            "ROUND": round,
            "MIN": min,
            "MAX": max,
            "SQRT": math.sqrt,
            "A": float(a_val),
            "B": float(b_val),
            "FACT": float(a_val),
            "NORM": float(b_val),
            "PLAN": float(b_val),
            "A_TOTAL": float(a_total),
            "B_TOTAL": float(b_total),
            "TOTAL_A": float(a_total),
            "TOTAL_B": float(b_total),
            "A_GROUP": float(a_total),
            "B_GROUP": float(b_total),
            "DIFF": float(a_val - b_val),
            "ABS_DIFF": float(abs_diff_val if abs_diff_val else abs(a_val - b_val)),
            "TOTAL_DIFF": float(a_total - b_total),
            "COUNT": float(count_val),
            "COUNT_TOTAL": float(count_total),
            "TOTAL_COUNT": float(count_total),
            "COUNT_DIFF": float(diff_count_val),
            # Русские имена переменных
            "А": float(a_val),
            "Б": float(b_val),
            "ФАКТ": float(a_val),
            "НОРМА": float(b_val),
            "НОРМАТИВ": float(b_val),
            "ПЛАН": float(b_val),
            "А_ОБЩ": float(a_total),
            "Б_ОБЩ": float(b_total),
            "ФАКТ_ОБЩИЙ": float(a_total),
            "НОРМАТИВ_ОБЩИЙ": float(b_total),
            "КОЛВО": float(count_val),
            "КОЛВО_ОБЩ": float(count_total),
        }
        try:
            res = eval(expr, {"__builtins__": {}}, env)
            res_f = float(res)
            if math.isnan(res_f) or math.isinf(res_f):
                return 0.0
            return res_f
        except Exception:
            return 0.0

    def _format_pie_slice_texts(self, labels: list[str], raw_formula_vals: list[float]) -> tuple[list[str] | None, str]:
        """Формирует компактные подписи секторов круга, чтобы длинные названия не сжимали диаграмму."""
        pie_textinfo = self._get_pie_textinfo()
        if not self.show_values or pie_textinfo == "none":
            return None, "none"

        lbl_mode = getattr(self, "value_label_mode", "auto")
        if not self._is_formula_mode():
            # В режиме 'auto' выводим на секторе только процент, так как названия уже есть в легенде справа
            return None, ("percent" if lbl_mode == "auto" else pie_textinfo)

        disp = getattr(self, "pie_value_display", "formula_pct")
        if disp == "share_only":
            return None, ("percent" if lbl_mode == "auto" else pie_textinfo)

        texts = []
        # Показываем название прямо на секторе только если пользователь явно выбрал режим с названием
        show_lbl = lbl_mode in ("label+percent", "label+value+percent", "label")

        for lbl, f_val in zip(labels, raw_formula_vals):
            val_str = f"{abs(f_val):.2f}%" if disp == "formula_abs_pct" else f"{f_val:+.2f}%"
            if lbl_mode == "label":
                texts.append(f"{lbl}")
            elif show_lbl:
                short_lbl = (lbl[:18] + "…") if len(lbl) > 19 else lbl
                texts.append(f"{short_lbl}<br>{val_str}")
            else:
                texts.append(val_str)

        if disp == "formula_and_share":
            return texts, "text+percent"
        return texts, "text"

    def _check_pie_pct_filter(self, r_val: float, share_pct: float, is_formula_pct: bool) -> bool:
        """Проверяет, проходит ли сектор круговой диаграммы заданный пользователем фильтр процентов."""
        pct_mode = str(getattr(self, "slice_pct_mode", "ge") or "ge")
        raw_min = getattr(self, "min_slice_pct", 0.0)
        try:
            min_pct = float(raw_min)
        except Exception:
            min_pct = 0.0

        if pct_mode == "none":
            return True

        # По умолчанию берем результат формулы (например, -11.62 или +22.08)
        val_to_check = float(r_val)
        
        # Если пользователь выбрал режим площади или модуля — берем соответствующее значение
        if pct_mode in ("share_ge", "share_le"):
            val_to_check = float(share_pct)
        elif pct_mode in ("abs_ge", "abs_le"):
            val_to_check = abs(float(r_val))

        # Выполняем точную проверку выбранного оператора
        if pct_mode in ("ge", "share_ge"):
            return val_to_check >= min_pct
        if pct_mode == "gt":
            return val_to_check > min_pct
        if pct_mode in ("le", "share_le"):
            return val_to_check <= min_pct
        if pct_mode == "lt":
            return val_to_check < min_pct
        if pct_mode == "abs_ge":
            return val_to_check >= min_pct
        if pct_mode == "abs_le":
            return val_to_check <= min_pct

        return True

    def _calc_waybill_types_overview_slice(
        self,
        sub_df: pd.DataFrame,
        ordered_types: list[str],
        month_label: str,
        type_color_map: dict[str, str],
        colors_list: list[str],
        level1_col_name: str = "Группа",
        level2_col_name: str = "Подкатегория",
    ) -> tuple[list[str], list[float], list[str], list[str], str, list[str] | None, str]:
        """
        УРОВЕНЬ 1 (Фильтр = «Все значения»):
        Для каждого Типа ТС считает процент по формуле: ((Факт общий типа - Норматив общий типа) / Норматив общий типа) * 100%
        (или по формуле, выбранной пользователем в Инспекторе).
        """
        if sub_df is None or len(sub_df) == 0:
            return [], [], [], [], "0", None, "none"

        dev_mode = getattr(self, "deviation_mode", "formula_pct_self")
        is_formula = self._is_formula_mode()
        has_fact_norm = "_fact_num" in sub_df.columns and "_norm_num" in sub_df.columns
        has_overrun = "_overrun_val" in sub_df.columns
        has_metric = "_metric_val" in sub_df.columns

        total_all_rows = len(sub_df)
        if total_all_rows == 0:
            return [], [], [], [], "0", None, "none"

        total_a_all = float(sub_df["_fact_num"].sum()) if has_fact_norm else 0.0
        total_b_all = float(sub_df["_norm_num"].sum()) if has_fact_norm else 0.0
        total_diff_rows = int((sub_df["_overrun_val"].abs() > 1e-6).sum()) if has_overrun else total_all_rows
        total_abs_overrun = float(sub_df["_overrun_val"].abs().sum()) if has_overrun else 0.0

        # Общий процент по всей выборке: ((Факт общий - Норматив общий) / Норматив общий) * 100%
        overall_pct = self._eval_custom_formula(
            total_a_all, total_b_all, total_a_all, total_b_all,
            total_all_rows, total_all_rows, total_diff_rows, total_abs_overrun
        ) if (is_formula and has_fact_norm) else 0.0

        stats = []
        for t_name in ordered_types:
            t_group = sub_df[sub_df["_type_clean"].str.lower() == t_name.lower()]
            t_count = len(t_group)
            if t_count == 0:
                continue

            t_a = float(t_group["_fact_num"].sum()) if has_fact_norm else 0.0
            t_b = float(t_group["_norm_num"].sum()) if has_fact_norm else 0.0
            t_diff = t_a - t_b
            t_abs_overrun = float(t_group["_overrun_val"].abs().sum()) if has_overrun else 0.0
            t_diff_cnt = int((t_group["_overrun_val"].abs() > 1e-6).sum()) if has_overrun else t_count

            if is_formula and has_fact_norm:
                raw_val = self._eval_custom_formula(
                    t_a, t_b, total_a_all, total_b_all,
                    t_count, total_all_rows, t_diff_cnt, t_abs_overrun
                )
                size_val = abs(raw_val)
            elif dev_mode == "waybill_overrun_sum" and has_overrun:
                raw_val = t_abs_overrun
                size_val = t_abs_overrun
            elif dev_mode == "value_sum" and has_metric:
                raw_val = float(t_group["_metric_val"].sum())
                size_val = abs(raw_val)
            elif dev_mode == "value_mean" and has_metric:
                raw_val = float(t_group["_metric_val"].mean())
                size_val = abs(raw_val)
            else:
                raw_val = float(t_count)
                size_val = float(t_count)

            if size_val <= 1e-9:
                continue

            own_pct = ((t_a - t_b) / t_b * 100.0) if (has_fact_norm and abs(t_b) > 1e-9) else 0.0
            grp_share_pct = ((t_a - t_b) / total_b_all * 100.0) if (has_fact_norm and abs(total_b_all) > 1e-9) else 0.0

            details_lines = [f"{level1_col_name}: <b>{t_name}</b> | Период: <b>{month_label}</b>"]
            if has_fact_norm:
                a_lbl = self.fact_col or "Факт"
                b_lbl = self.norm_col or "Норматив"
                details_lines.append(
                    f"По формуле: <b>{raw_val:+.2f}%</b> (Собств. откл.: <b>{own_pct:+.2f}%</b> | От общ. нормы: <b>{grp_share_pct:+.2f}%</b>)"
                )
                details_lines.append(
                    f"{a_lbl} общий: <b>{t_a:,.1f}</b> | {b_lbl} общий: <b>{t_b:,.1f}</b> (Разница: <b>{t_diff:+,.1f}</b>)"
                )
            details_lines.append(
                f"Записей в группе: <b>{t_count}</b> из <b>{total_all_rows}</b> ({t_count / total_all_rows * 100:.1f}%)"
            )

            if "_model_clean" in t_group.columns:
                top_m = t_group["_model_clean"].value_counts().head(5)
                if len(top_m) > 0:
                    m_str = ", ".join(f"{m} ({cnt})" for m, cnt in top_m.items() if m)
                    details_lines.append(f"Топ ({level2_col_name}): {m_str}")

            stats.append((t_name, size_val, raw_val, "<br>".join(details_lines), t_count))

        stats.sort(key=lambda x: x[1], reverse=True)
        total_sum_val = sum(item[1] for item in stats) if stats else 0.0
        use_formula_pct = bool(is_formula and has_fact_norm)

        f_labels, f_values, f_raw, f_details = [], [], [], []
        total_cnt = 0

        for item in stats:
            lbl, size_v, r_val, c_det, t_cnt = item
            share_pct = (size_v / total_sum_val * 100.0) if total_sum_val > 0 else 0.0
            if self._check_pie_pct_filter(r_val, share_pct, use_formula_pct):
                f_labels.append(lbl)
                f_values.append(size_v)
                f_raw.append(r_val)
                f_details.append(c_det)
                total_cnt += t_cnt

        labels = f_labels
        values = f_values
        raw_vals = f_raw
        custom_details = f_details

        slice_colors = [
            type_color_map.get(lbl, colors_list[idx % len(colors_list)])
            for idx, lbl in enumerate(labels)
        ]
        slice_texts, textinfo_mode = self._format_pie_slice_texts(labels, raw_vals)

        if is_formula and has_fact_norm:
            summary_badge = f"{overall_pct:+.2f}% (записей: {total_cnt})"
        else:
            summary_badge = f"{total_cnt}"

        return labels, values, custom_details, slice_colors, summary_badge, slice_texts, textinfo_mode

    def _calc_waybill_models_slice(
        self,
        sub_df: pd.DataFrame,
        type_label: str,
        month_label: str,
        model_color_map: dict[str, str],
        colors_list: list[str],
        level1_col_name: str = "Группа",
        level2_col_name: str = "Элемент",
    ) -> tuple[list[str], list[float], list[str], list[str], str, list[str] | None, str]:
        """
        УРОВЕНЬ 2 (В Фильтре выбрана конкретная группа 1-го уровня):
        Считает общий процент отклонения группы: ((Факт общий группы - Норматив общий группы) / Норматив общий группы) * 100%,
        и процент по каждой подкатегории (Модели ТС) внутри этой группы.
        """
        if sub_df is None or len(sub_df) == 0 or "_model_clean" not in sub_df.columns:
            return [], [], [], [], "0", None, "none"

        dev_df = sub_df
        total_group_rows = len(dev_df)
        if total_group_rows == 0:
            return [], [], [], [], "0", None, "none"

        dev_mode = getattr(self, "deviation_mode", "formula_pct_self")
        is_formula = self._is_formula_mode()
        has_fact_norm = "_fact_num" in dev_df.columns and "_norm_num" in dev_df.columns
        has_overrun = "_overrun_val" in dev_df.columns
        has_metric = "_metric_val" in dev_df.columns

        group_a_total = float(dev_df["_fact_num"].sum()) if has_fact_norm else 0.0
        group_b_total = float(dev_df["_norm_num"].sum()) if has_fact_norm else 0.0
        group_diff_rows = int((dev_df["_overrun_val"].abs() > 1e-6).sum()) if has_overrun else total_group_rows
        group_abs_overrun = float(dev_df["_overrun_val"].abs().sum()) if has_overrun else 0.0

        # Процент отклонения выбранной группы: ((Факт общий группы - Норматив общий группы) / Норматив общий группы) * 100%
        group_formula_pct = self._eval_custom_formula(
            group_a_total, group_b_total, group_a_total, group_b_total,
            total_group_rows, total_group_rows, group_diff_rows, group_abs_overrun
        ) if (is_formula and has_fact_norm) else 0.0

        stats = []
        for model_name, m_group in dev_df.groupby("_model_clean", sort=False):
            if not model_name:
                continue
            m_count = len(m_group)
            m_a = float(m_group["_fact_num"].sum()) if has_fact_norm else 0.0
            m_b = float(m_group["_norm_num"].sum()) if has_fact_norm else 0.0
            m_diff = m_a - m_b
            m_abs_overrun = float(m_group["_overrun_val"].abs().sum()) if has_overrun else 0.0
            m_diff_cnt = int((m_group["_overrun_val"].abs() > 1e-6).sum()) if has_overrun else m_count

            if is_formula and has_fact_norm:
                raw_val = self._eval_custom_formula(
                    m_a, m_b, group_a_total, group_b_total,
                    m_count, total_group_rows, m_diff_cnt, m_abs_overrun
                )
                size_val = abs(raw_val)
            elif dev_mode == "waybill_overrun_sum" and has_overrun:
                raw_val = m_abs_overrun
                size_val = m_abs_overrun
            elif dev_mode == "value_sum" and has_metric:
                raw_val = float(m_group["_metric_val"].sum())
                size_val = abs(raw_val)
            elif dev_mode == "value_mean" and has_metric:
                raw_val = float(m_group["_metric_val"].mean())
                size_val = abs(raw_val)
            else:
                raw_val = float(m_count)
                size_val = float(m_count)

            if size_val <= 1e-9:
                continue

            own_pct = ((m_a - m_b) / m_b * 100.0) if (has_fact_norm and abs(m_b) > 1e-9) else 0.0
            of_group_norm_pct = ((m_a - m_b) / group_b_total * 100.0) if (has_fact_norm and abs(group_b_total) > 1e-9) else 0.0

            details_lines = [
                f"{level2_col_name}: <b>{model_name}</b> ({level1_col_name}: <b>{type_label}</b> | {month_label})",
            ]
            if has_fact_norm:
                a_lbl = self.fact_col or "Факт"
                b_lbl = self.norm_col or "Норматив"
                details_lines.append(
                    f"По формуле: <b>{raw_val:+.2f}%</b> (От своей нормы: <b>{own_pct:+.2f}%</b> | От нормы группы: <b>{of_group_norm_pct:+.2f}%</b>)"
                )
                details_lines.append(
                    f"{a_lbl}: <b>{m_a:,.1f}</b> | {b_lbl}: <b>{m_b:,.1f}</b> (Разница: <b>{m_diff:+,.1f}</b>)"
                )
                details_lines.append(
                    f"Итог группы «{type_label}»: {a_lbl} = <b>{group_a_total:,.1f}</b>, {b_lbl} = <b>{group_b_total:,.1f}</b> (<b>{group_formula_pct:+.2f}%</b>)"
                )
            details_lines.append(
                f"Записей: <b>{m_count}</b> из <b>{total_group_rows}</b> в группе ({m_count / total_group_rows * 100:.1f}%)"
            )

            key_plate_col = (
                self.calc_group_col
                if (getattr(self, "calc_group_col", "") and self.calc_group_col in m_group.columns)
                else (self.plate_col if (self.plate_col and self.plate_col in m_group.columns) else "")
            )
            if key_plate_col and has_fact_norm:
                p_series = m_group[key_plate_col].dropna().astype(str).str.strip()
                p_sums = m_group.groupby(p_series, sort=False)["_overrun_val"].sum()
                if len(p_sums) > 0:
                    p_items = []
                    for p_num, p_val in p_sums.head(8).items():
                        if not p_num:
                            continue
                        verd = "🟢 Экономит" if p_val < -1e-6 else ("🔴 Перерасход" if p_val > 1e-6 else "⚪ Норма")
                        p_items.append(f"<b>{p_num}</b>: {p_val:+,.1f} ({verd})")
                    if p_items:
                        details_lines.append(f"{key_plate_col} (итог по машине):<br>• " + "<br>• ".join(p_items))
            elif self.plate_col and self.plate_col in m_group.columns:
                plates_vc = m_group[self.plate_col].dropna().astype(str).str.strip().value_counts()
                if len(plates_vc) > 0:
                    top_plates = [f"{p} ({cnt})" for p, cnt in plates_vc.head(6).items() if p]
                    if top_plates:
                        details_lines.append(f"{self.plate_col}: " + ", ".join(top_plates))

            stats.append((model_name, size_val, raw_val, "<br>".join(details_lines)))

        stats.sort(key=lambda x: x[1], reverse=True)
        total_sum_val2 = sum(item[1] for item in stats) if stats else 0.0
        use_formula_pct2 = bool(is_formula and has_fact_norm)

        filtered_stats = []
        for item in stats:
            lbl, size_v, r_val, c_det = item
            share_pct2 = (size_v / total_sum_val2 * 100.0) if total_sum_val2 > 0 else 0.0
            if self._check_pie_pct_filter(r_val, share_pct2, use_formula_pct2):
                filtered_stats.append(item)

        if self.top_n and self.top_n > 0 and len(filtered_stats) > self.top_n:
            filtered_stats = filtered_stats[:self.top_n]

        f_labels2 = [item[0] for item in filtered_stats]
        f_values2 = [item[1] for item in filtered_stats]
        f_raw2 = [item[2] for item in filtered_stats]
        f_details2 = [item[3] for item in filtered_stats]

        labels = f_labels2
        values = f_values2
        raw_vals = f_raw2
        custom_details = f_details2
        slice_colors = [
            model_color_map.get(lbl, colors_list[idx % len(colors_list)])
            for idx, lbl in enumerate(labels)
        ]
        slice_texts, textinfo_mode = self._format_pie_slice_texts(labels, raw_vals)

        if is_formula and has_fact_norm:
            summary_badge = f"{group_formula_pct:+.2f}% (записей: {total_group_rows})"
        else:
            summary_badge = f"{total_group_rows}"

        return labels, values, custom_details, slice_colors, summary_badge, slice_texts, textinfo_mode

    def render(self) -> str:
        target_df = self.dataframe
        report_obj, config_dict = _find_report_and_config(self)
        if report_obj is not None:
            self._report_ref = report_obj
        self.config = config_dict

        # Синхронизируем все настройки из Инспектора в атрибуты блока
        _skip_keys = {"id", "type", "dataframe", "width", "margin_top", "margin_bottom"}
        for k, v in config_dict.items():
            if hasattr(self, k) and k not in _skip_keys:
                setattr(self, k, v)

        source_file_name = self.source_file_name or config_dict.get("source_file_name", "")
        source_sheet = (
            self.source_sheet
            or config_dict.get("source_sheet", "")
            or config_dict.get("source_file", "")
        )

        manager = getattr(self, "_file_manager", None)
        if not manager and report_obj and hasattr(report_obj, "file_manager"):
            manager = report_obj.file_manager

        if not manager:
            try:
                from PySide6.QtWidgets import QApplication
                app = QApplication.instance()
                if app:
                    for w in app.topLevelWidgets():
                        if hasattr(w, "file_manager") and w.file_manager:
                            manager = w.file_manager
                            break
            except Exception:
                pass

        target_df = DataMemoryCache.get_dataframe(
            manager, source_file_name, source_sheet, fallback_df=target_df
        )

        if target_df is None or len(target_df) == 0:
            return self.wrap_layout(self._render_empty("Нет данных для выбранного листа"))

        df = DataMemoryCache.dedup_df(target_df)

        linked_sig = tuple(self._get_linked_chart_allowed_types(df)) if self.filter_from_chart else ()
        render_sig = json.dumps(
            {
                "df": (id(df), len(df), len(df.columns)),
                "cfg": config_dict,
                "linked": linked_sig,
                "w": self.width,
                "mh": self.min_height,
            },
            sort_keys=True,
            default=str,
        )
        if "DataMemoryCache" in globals():
            cached_html = DataMemoryCache.get_render_html(self.id, render_sig)
            if cached_html is not None:
                return cached_html
        if self.row_start > 0 or self.row_limit > 0:
            end_idx = (self.row_start + self.row_limit) if self.row_limit > 0 else len(df)
            df = df.iloc[self.row_start:end_idx]

        if len(df) == 0:
            return self.wrap_layout(self._render_empty("Выбранный диапазон строк пуст"))

        if not self.x_col or self.x_col not in df.columns:
            self.x_col = str(df.columns[0])

        plot_div_id = f"ea-plotly-{self.id}"
        row_slicer_payload = {}
        fig = None

        try:
            import plotly.express as px
            import plotly.graph_objects as go
            import plotly.io as pio
            from plotly.subplots import make_subplots

            work_df = self._apply_smart_filter(df)
            if len(work_df) == 0:
                return self.wrap_layout(self._render_empty("Условие фильтрации отсекло все строки"))

            colors_list = _PALETTE_HEX.get(self.palette, _PALETTE_HEX["corporate"])
            chart_title = self.title if self.show_title else ""
            actual_font_size = int(config_dict.get("font_size", getattr(self, "font_size", 12)) or 12)

            # =========================================================
            # РЕЖИМ КОМБИНИРОВАННОГО ГРАФИКА (НЕСКОЛЬКО ТИПОВ НА ОДНОЙ ОСИ)
            # =========================================================
            if self.chart_type in ("pie", "donut") and getattr(self, "pie_display_mode", "") in ("dut_two_pies", "dut_single_drill"):
                final_html = self._render_dut_pct_drill_pie(
                    work_df, config_dict, plot_div_id, colors_list, actual_font_size, chart_title
                )
                if "render_sig" in locals() and "DataMemoryCache" in globals():
                    DataMemoryCache.set_render_html(self.id, render_sig, final_html, owner_obj=df)
                return final_html

            is_hierarchical_pie = (
                self.chart_type in ("pie", "donut")
                and self.data_mode != "rows"
                and (
                    bool(self.fact_col and self.norm_col and self.fact_col in work_df.columns and self.norm_col in work_df.columns)
                    or bool(self.parent_group_col and self.parent_group_col in work_df.columns)
                    or bool(self.date_col and self.date_col in work_df.columns)
                    or bool(self.filter_from_chart)
                )
            )

            if self.chart_type == "combo":
                combo_df = work_df.copy()
                cols_all = [str(c) for c in combo_df.columns]
                num_cands = [str(c) for c in combo_df.select_dtypes(include="number").columns]
                str_cands = [c for c in cols_all if c not in num_cands]

                # 1. Определяем базовые колонки ФАКТ (A) и НОРМАТИВ (B)
                a_col_name = self.fact_col if (self.fact_col and self.fact_col in combo_df.columns) else ""
                b_col_name = self.norm_col if (self.norm_col and self.norm_col in combo_df.columns) else ""

                raw_series_list = list(self.combo_series or config_dict.get("combo_series") or [])
                if not a_col_name or not b_col_name:
                    for s_cand in raw_series_list:
                        if str(s_cand.get("source_type", "column")) == "column":
                            c_cand = str(s_cand.get("col", "") or "").strip()
                            if c_cand in combo_df.columns:
                                if not a_col_name and "факт" in c_cand.lower():
                                    a_col_name = c_cand
                                elif not b_col_name and any(w in c_cand.lower() for w in ("норм", "план")):
                                    b_col_name = c_cand

                if not a_col_name:
                    for c_cand in cols_all:
                        if "факт" in c_cand.lower():
                            a_col_name = c_cand
                            break
                if not b_col_name:
                    for c_cand in cols_all:
                        if any(w in c_cand.lower() for w in ("норм", "план")):
                            b_col_name = c_cand
                            break

                # Если серии ещё не настроены, создаём по умолчанию:
                # 1) Столбцы (Факт - Норматив) на правой оси Y2
                # 2) Линия тенденции ((Факт - Норматив) / Норматив * 100%) на левой оси Y1
                if not raw_series_list:
                    raw_series_list = [
                        {
                            "name": "Отклонение (Факт − Норматив)",
                            "source_type": "formula",
                            "col": "",
                            "formula": "ФАКТ - НОРМАТИВ",
                            "agg": "sum",
                            "plot_type": "bar",
                            "y_axis": "y2",
                            "color": colors_list[0 % len(colors_list)],
                            "line_dash": "solid",
                            "line_width": 3,
                            "marker_size": 8,
                            "opacity": 0.85,
                            "show_labels": bool(self.show_values),
                            "suffix": "",
                            "visible": True,
                        },
                        {
                            "name": "Тенденция отклонения, %",
                            "source_type": "formula",
                            "col": "",
                            "formula": "((ФАКТ - НОРМАТИВ) / НОРМАТИВ) * 100",
                            "agg": "sum",
                            "plot_type": "line",
                            "y_axis": "y1",
                            "color": colors_list[1 % len(colors_list)],
                            "line_dash": "solid",
                            "line_width": 3,
                            "marker_size": 8,
                            "opacity": 1.0,
                            "show_labels": bool(self.show_values),
                            "suffix": "%",
                            "visible": True,
                        },
                    ]

                # 2. Переводим ВСЕ используемые колонки (включая ФАКТ и НОРМАТИВ) в числовой кэш
                used_cols: list[str] = []
                for c_try in [a_col_name, b_col_name, self.fact_col, self.norm_col] + [
                    str(s.get("col", "") or "").strip() for s in raw_series_list
                ]:
                    if c_try and c_try in combo_df.columns and c_try not in used_cols:
                        used_cols.append(c_try)
                for c_extra in cols_all:
                    if c_extra not in used_cols and (
                        c_extra in num_cands
                        or any(c_extra in str(s.get("formula", "")) for s in raw_series_list)
                    ):
                        used_cols.append(c_extra)

                col_to_num_key: dict[str, str] = {}
                for idx_u, uc in enumerate(used_cols):
                    nk = f"_cmb_v{idx_u}"
                    combo_df[nk] = _to_num_series(combo_df[uc])
                    col_to_num_key[uc] = nk

                if not a_col_name and used_cols:
                    a_col_name = used_cols[0]
                if not b_col_name and len(used_cols) >= 2:
                    b_col_name = used_cols[1]

                # 3. Определяем 3 уровня погружения: 1) Тип ТС -> 2) Модель ТС -> 3) Гос. номер
                lvl1_col = (
                    self.combo_level1_col
                    if (getattr(self, "combo_level1_col", "") and self.combo_level1_col in combo_df.columns)
                    else (
                        self.parent_group_col
                        if (self.parent_group_col and self.parent_group_col in combo_df.columns)
                        else (self.x_col if (self.x_col and self.x_col in combo_df.columns) else cols_all[0])
                    )
                )
                if not getattr(self, "combo_level1_col", "") and not self.parent_group_col:
                    for cand in str_cands:
                        if any(w in cand.lower() for w in ("тип", "групп", "категор")):
                            lvl1_col = cand
                            break

                lvl2_col = ""
                raw_l2 = getattr(self, "combo_level2_col", "") or self.model_col
                if raw_l2 == "__NONE__":
                    lvl2_col = ""
                elif raw_l2 and raw_l2 in combo_df.columns and raw_l2 != lvl1_col:
                    lvl2_col = raw_l2
                else:
                    for cand in str_cands:
                        if cand != lvl1_col and any(w in cand.lower() for w in ("модел", "марк", "авто")):
                            lvl2_col = cand
                            break

                lvl3_col = ""
                raw_l3 = getattr(self, "combo_level3_col", "") or self.plate_col
                if raw_l3 == "__NONE__":
                    lvl3_col = ""
                elif raw_l3 and raw_l3 in combo_df.columns and raw_l3 not in (lvl1_col, lvl2_col):
                    lvl3_col = raw_l3
                else:
                    for cand in cols_all:
                        if cand not in (lvl1_col, lvl2_col) and any(w in cand.lower() for w in ("гос", "номер", "грз", "гараж", "вин")):
                            lvl3_col = cand
                            break

                combo_df["_cmb_l1"] = DataMemoryCache.get_str_series(combo_df, lvl1_col).replace("", "—")
                if lvl2_col:
                    combo_df["_cmb_l2"] = DataMemoryCache.get_str_series(combo_df, lvl2_col).replace("", "—")
                if lvl3_col:
                    combo_df["_cmb_l3"] = DataMemoryCache.get_str_series(combo_df, lvl3_col).replace("", "—")

                d_field = self.date_col if (self.date_col and self.date_col in combo_df.columns) else ""

                sort_lvl1 = str(getattr(self, "combo_level1_sort", "") or self.sort_by or "value_desc")
                sort_lvl2 = str(getattr(self, "combo_level2_sort", "") or self.sort_by or "value_desc")
                sort_lvl3 = str(getattr(self, "combo_level3_sort", "") or self.sort_by or "value_desc")
                sort_series_idx = int(getattr(self, "combo_sort_series_idx", 0) or 0)

                def _combo_if_fn(cond, t_val, f_val=0.0):
                    try:
                        return float(t_val) if bool(cond) else float(f_val)
                    except Exception:
                        return 0.0

                _combo_base_env = {
                    "__builtins__": {},
                    "abs": abs, "ABS": abs,
                    "round": round, "ROUND": round,
                    "min": min, "MIN": min,
                    "max": max, "MAX": max,
                    "sqrt": math.sqrt, "SQRT": math.sqrt,
                    "pow": pow, "POW": pow,
                    "if": _combo_if_fn, "IF": _combo_if_fn,
                    "если": _combo_if_fn, "ЕСЛИ": _combo_if_fn,
                    "_if_call": _combo_if_fn,
                }
                _combo_code_cache: dict = {}

                def _compile_combo_expr(expr_str: str, sorted_col_keys: tuple[str, ...]):
                    cache_k = (expr_str, sorted_col_keys)
                    cached = _combo_code_cache.get(cache_k)
                    if cached is not None:
                        return cached

                    raw_expr = str(expr_str or "0").strip()
                    if not raw_expr:
                        _combo_code_cache[cache_k] = (None, ())
                        return None, ()

                    expr = raw_expr
                    used_toks = []
                    used_set = set()
                    for idx_ck, c_k in enumerate(sorted_col_keys):
                        if not c_k:
                            continue
                        tok = f"__CC_{idx_ck}__"
                        if f"[{c_k}]" in expr:
                            expr = expr.replace(f"[{c_k}]", tok)
                            used_toks.append((c_k, tok))
                            used_set.add(idx_ck)

                    for idx_ck, c_k in enumerate(sorted_col_keys):
                        if not c_k or c_k in ("ФАКТ", "НОРМА", "НОРМАТИВ"):
                            continue
                        if c_k in expr:
                            tok = f"__CC_{idx_ck}__"
                            expr = expr.replace(c_k, tok)
                            if idx_ck not in used_set:
                                used_toks.append((c_k, tok))
                                used_set.add(idx_ck)

                    expr = (
                        expr.replace(";", ",")
                        .replace("−", "-")
                        .replace("–", "-")
                        .replace("×", "*")
                        .replace("÷", "/")
                    )
                    expr = re.sub(r"(\d),(\d)", r"\1.\2", expr)
                    expr = re.sub(r"(\d+(?:\.\d+)?)\s*%", r"\1", expr)
                    expr = expr.replace("[", "").replace("]", "")
                    expr = re.sub(r"\b(if|IF|если|ЕСЛИ)\s*\(", "_if_call(", expr)

                    try:
                        code_obj = compile(expr, "<combo_formula>", "eval")
                    except Exception:
                        code_obj = None

                    res = (code_obj, tuple(used_toks))
                    _combo_code_cache[cache_k] = res
                    return res

                def _eval_combo_formula_points(
                    expr_str: str,
                    pt_indices,
                    series_arrays: list[list[float]],
                    col_arrays: dict[str, list[float]],
                    cnt_arr: list[float],
                    cur_series_idx: int = -1,
                ) -> list[float]:
                    sorted_col_keys = tuple(sorted(col_arrays.keys(), key=len, reverse=True))
                    code_obj, used_toks = _compile_combo_expr(expr_str, sorted_col_keys)
                    if code_obj is None:
                        return [0.0 for _ in pt_indices]

                    f_arr = col_arrays.get(a_col_name, col_arrays.get("ФАКТ", []))
                    n_arr = col_arrays.get(b_col_name, col_arrays.get("НОРМА", []))
                    a_tot = float(sum(f_arr)) if f_arr else 0.0
                    b_tot = float(sum(n_arr)) if n_arr else 0.0
                    c_tot = float(sum(cnt_arr)) if cnt_arr else 0.0

                    env = dict(_combo_base_env)
                    env["A_TOTAL"] = env["ФАКТ_ОБЩИЙ"] = env["А_ОБЩ"] = a_tot
                    env["B_TOTAL"] = env["НОРМАТИВ_ОБЩИЙ"] = env["НОРМА_ОБЩ"] = env["Б_ОБЩ"] = b_tot
                    env["COUNT_TOTAL"] = env["КОЛВО_ОБЩ"] = c_tot

                    used_col_data = []
                    for c_k, tok in used_toks:
                        c_arr = col_arrays[c_k]
                        c_sum = float(sum(c_arr)) if c_arr else 0.0
                        env[f"{tok}_TOTAL"] = c_sum
                        used_col_data.append((tok, c_arr, len(c_arr), c_sum))

                    active_series_meta = []
                    for s_i, s_arr in enumerate(series_arrays):
                        if cur_series_idx >= 0 and s_i >= cur_series_idx:
                            continue
                        s_src_type = str(raw_series_list[s_i].get("source_type", "column") or "column") if s_i < len(raw_series_list) else "column"
                        if s_src_type == "column" or s_i >= 2:
                            active_series_meta.append((s_i, s_src_type, s_arr, len(s_arr), float(sum(s_arr)) if s_arr else 0.0))

                    len_f, len_n, len_c = len(f_arr), len(n_arr), len(cnt_arr)
                    out = []
                    for pt_idx in pt_indices:
                        if pt_idx < 0:
                            a_val, b_val, c_val = a_tot, b_tot, c_tot
                            for tok, _arr, _ln, c_sum in used_col_data:
                                env[tok] = c_sum
                        else:
                            a_val = float(f_arr[pt_idx]) if pt_idx < len_f else 0.0
                            b_val = float(n_arr[pt_idx]) if pt_idx < len_n else 0.0
                            c_val = float(cnt_arr[pt_idx]) if pt_idx < len_c else 0.0
                            for tok, arr, ln, _c_sum in used_col_data:
                                env[tok] = float(arr[pt_idx]) if pt_idx < ln else 0.0

                        env["ФАКТ"] = env["Факт"] = env["факт"] = env["FACT"] = env["fact"] = env["A"] = env["a"] = env["А"] = env["а"] = a_val
                        env["НОРМАТИВ"] = env["Норматив"] = env["норматив"] = env["НОРМА"] = env["Норма"] = env["норма"] = env["NORM"] = env["norm"] = env["PLAN"] = env["План"] = env["план"] = env["B"] = env["b"] = env["Б"] = env["б"] = b_val
                        env["DIFF"] = a_val - b_val
                        env["ABS_DIFF"] = abs(a_val - b_val)
                        env["COUNT"] = env["КОЛВО"] = c_val
                        env["S1"] = env["s1"] = a_val
                        env["S2"] = env["s2"] = b_val

                        for s_i, s_src_type, s_arr, s_len, s_sum in active_series_meta:
                            val_i = s_sum if pt_idx < 0 else (float(s_arr[pt_idx]) if pt_idx < s_len else 0.0)
                            env[f"S{s_i + 1}"] = env[f"s{s_i + 1}"] = val_i
                            if s_src_type == "column":
                                if s_i == 0 and not f_arr:
                                    env["A"] = env["a"] = env["А"] = env["ФАКТ"] = env["Факт"] = env["факт"] = val_i
                                elif s_i == 1 and not n_arr:
                                    env["B"] = env["b"] = env["Б"] = env["НОРМА"] = env["НОРМАТИВ"] = val_i

                        try:
                            res = float(eval(code_obj, {"__builtins__": {}}, env))
                            out.append(0.0 if (math.isnan(res) or math.isinf(res)) else res)
                        except Exception:
                           out.append(0.0)
                    return out

                def _build_combo_traces_for_df( 
                    sub_df: pd.DataFrame,
                    x_col_key: str,
                    level_sort_mode: str = "value_desc",
                    is_month_axis: bool = False,
                    fixed_x_order: list[str] | None = None,
                    level_num: int = 1,
                    apply_top_n: bool = True,
                ) -> tuple[list[dict], str, list[str]]:
                    if sub_df is None or len(sub_df) == 0:
                        return [], "Нет данных", []

                    if fixed_x_order is not None:
                        x_labels = [str(x) for x in fixed_x_order]
                    elif is_month_axis:
                        present = set(sub_df[x_col_key].unique())
                        x_labels = [m for m in _RU_MONTHS_ORDER if m in present] + [
                            c for c in sub_df[x_col_key].unique() if c not in _RU_MONTHS_ORDER
                        ]
                    else:
                        raw_uniq = [str(k) for k in sub_df[x_col_key].dropna().unique().tolist() if str(k).strip()]
                        non_dash = [k for k in raw_uniq if k != "—"]
                        x_labels = non_dash if non_dash else raw_uniq

                    if not x_labels:
                        return [], "Нет данных", []

                    grp_obj = sub_df.groupby(x_col_key, sort=False)
                    cnt_series = grp_obj.size()
                    cnt_arr = [float(cnt_series.get(xl, 0.0)) for xl in x_labels]

                    col_arrays_map: dict[str, list[float]] = {}
                    for uc, nk in col_to_num_key.items():
                        sum_s = grp_obj[nk].sum()
                        col_arrays_map[uc] = [float(sum_s.get(xl, 0.0)) for xl in x_labels]

                    if a_col_name and a_col_name in col_arrays_map:
                        col_arrays_map["ФАКТ"] = col_arrays_map[a_col_name]
                    if b_col_name and b_col_name in col_arrays_map:
                        col_arrays_map["НОРМА"] = col_arrays_map[b_col_name]
                        col_arrays_map["НОРМАТИВ"] = col_arrays_map[b_col_name]

                    # Шаг 1: Считаем серии со столбцами по всем категориям
                    computed_series_arrays: list[list[float]] = []
                    for idx_s, s_cfg in enumerate(raw_series_list):
                        src_type = str(s_cfg.get("source_type", "column") or "column")
                        c_name = str(s_cfg.get("col", "") or "")
                        agg_fn = str(s_cfg.get("agg", "sum") or "sum")

                        if src_type == "formula" or agg_fn == "formula":
                            computed_series_arrays.append([0.0] * len(x_labels))
                            continue

                        if agg_fn == "count" or not c_name or c_name not in col_to_num_key:
                            arr = list(cnt_arr)
                        else:
                            nk = col_to_num_key[c_name]
                            g_col = grp_obj[nk]
                            if agg_fn == "mean":
                                agg_s = g_col.mean()
                            elif agg_fn == "min":
                                agg_s = g_col.min()
                            elif agg_fn == "max":
                                agg_s = g_col.max()
                            elif agg_fn == "median":
                                agg_s = g_col.median()
                            else:
                                agg_s = g_col.sum()
                            arr = [float(agg_s.get(xl, 0.0)) for xl in x_labels]

                        computed_series_arrays.append(arr)
                        if c_name:
                            col_arrays_map[c_name] = arr

                    # Шаг 2: Считаем математические формулы по всем категориям (одним батчем)
                    n_pts = len(x_labels)
                    for idx_s, s_cfg in enumerate(raw_series_list):
                        src_type = str(s_cfg.get("source_type", "column") or "column")
                        agg_fn = str(s_cfg.get("agg", "sum") or "sum")
                        if src_type == "formula" or agg_fn == "formula":
                            f_str = str(s_cfg.get("formula", "ФАКТ - НОРМАТИВ") or "ФАКТ - НОРМАТИВ")
                            computed_series_arrays[idx_s] = _eval_combo_formula_points(
                                f_str, range(n_pts), computed_series_arrays, col_arrays_map, cnt_arr, cur_series_idx=idx_s
                            )

                    # Шаг 3: Сортировка категорий ПОСЛЕ расчёта формул
                    if not is_month_axis and fixed_x_order is None and len(x_labels) > 1:
                        target_s_idx = min(max(0, sort_series_idx), max(0, len(computed_series_arrays) - 1))
                        if target_s_idx < len(raw_series_list) and not raw_series_list[target_s_idx].get("visible", True):
                            for vis_i, s_c in enumerate(raw_series_list):
                                if s_c.get("visible", True):
                                    target_s_idx = vis_i
                                    break

                        sort_vals = computed_series_arrays[target_s_idx] if computed_series_arrays else [0.0] * len(x_labels)
                        indices = list(range(len(x_labels)))

                        if level_sort_mode == "value_desc":
                            indices.sort(key=lambda i: sort_vals[i], reverse=True)
                        elif level_sort_mode == "value_asc":
                            indices.sort(key=lambda i: sort_vals[i], reverse=False)
                        elif level_sort_mode == "abs_desc":
                            indices.sort(key=lambda i: abs(sort_vals[i]), reverse=True)
                        elif level_sort_mode == "label_asc":
                            indices.sort(key=lambda i: str(x_labels[i]).lower(), reverse=False)
                        elif level_sort_mode == "label_desc":
                            indices.sort(key=lambda i: str(x_labels[i]).lower(), reverse=True)

                        if apply_top_n and self.top_n and int(self.top_n) > 0:
                            indices = indices[: int(self.top_n)]

                        x_labels = [x_labels[i] for i in indices]
                        for s_i in range(len(computed_series_arrays)):
                            computed_series_arrays[s_i] = [computed_series_arrays[s_i][i] for i in indices]

                    # Шаг 4: Нарастающий итог (если включён для серии)
                    for idx_s, s_cfg in enumerate(raw_series_list):
                        p_type = str(s_cfg.get("plot_type", "bar") or "bar")
                        if p_type in ("cum_line", "cum_bar") or bool(s_cfg.get("is_cumulative", False)):
                            run_v = 0.0
                            cum_a = []
                            for v in computed_series_arrays[idx_s]:
                                run_v += v
                                cum_a.append(run_v)
                            computed_series_arrays[idx_s] = cum_a

                    has_bar_on_y2 = any(
                        s.get("visible", True) and str(s.get("plot_type", "bar")) in ("bar", "cum_bar") and str(s.get("y_axis", "y1")) == "y2"
                        for s in raw_series_list
                    )
                    has_line_on_y1 = any(
                        s.get("visible", True) and str(s.get("plot_type", "bar")) not in ("bar", "cum_bar") and str(s.get("y_axis", "y1")) != "y2"
                        for s in raw_series_list
                    )
                    swap_y_layers = bool(has_bar_on_y2 and has_line_on_y1)
                    self._combo_swap_y_layers = swap_y_layers

                    hl_over = bool(getattr(self, "combo_highlight_overrun", False))
                    hl_fact_idx = int(getattr(self, "combo_hl_fact_idx", 0) or 0)
                    hl_norm_idx = int(getattr(self, "combo_hl_norm_idx", 1) or 1)
                    over_color = str(getattr(self, "combo_over_color", "#e11d48") or "#e11d48")

                    traces_out = []
                    hdr_parts = []
                    drill_hint = (
                        "<br><i style='font-size:11px;color:#87C800;'>🖱 Кликните по столбцу/точке для перехода на Уровень "
                        + str(level_num + 1) + "</i>"
                        if (level_num == 1 and lvl2_col) or (level_num == 2 and lvl3_col)
                        else ""
                    )

                    for idx_s, (s_cfg, y_arr) in enumerate(zip(raw_series_list, computed_series_arrays)):
                        if not s_cfg.get("visible", True):
                            continue

                        s_name = str(s_cfg.get("name") or s_cfg.get("col") or f"Серия {idx_s + 1}").strip()
                        s_name = self._get_col_display_name(s_name, idx_s)
                        p_type = str(s_cfg.get("plot_type", "bar") or "bar")
                        y_ax = str(s_cfg.get("y_axis", "y1") or "y1")
                        c_hex = str(s_cfg.get("color") or colors_list[idx_s % len(colors_list)])
                        l_dash = str(s_cfg.get("line_dash", "solid") or "solid")
                        l_width = int(s_cfg.get("line_width", 3) or 3)
                        m_size = int(s_cfg.get("marker_size", 8) if "marker_size" in s_cfg else 8)
                        opac = float(s_cfg.get("opacity", 0.85 if p_type in ("bar", "cum_bar") else 1.0) or 1.0)
                        show_lbl = bool(s_cfg.get("show_labels", self.show_values))
                        suf = str(s_cfg.get("suffix", "") or "")
                        src_t = str(s_cfg.get("source_type", "column") or "column")

                        rounded_y = [round(v, 2) for v in y_arr]

                        # Точный расчёт итога в шапке (для формулы % считается от общих сумм выборки)
                        if src_t == "formula":
                            f_str_tot = str(s_cfg.get("formula", "ФАКТ - НОРМАТИВ") or "ФАКТ - НОРМАТИВ")
                            tot_s = _eval_combo_formula_points(f_str_tot, (-1,), computed_series_arrays, col_arrays_map, cnt_arr, cur_series_idx=idx_s)[0]
                        else:
                            tot_s = sum(y_arr)

                        hdr_parts.append(f"{_escape(s_name)}: <b style='color:{c_hex};'>{tot_s:+,.2f}{_escape(suf)}</b>" if ("%" in suf or "откл" in s_name.lower()) else f"{_escape(s_name)}: <b style='color:{c_hex};'>{tot_s:,.1f}{_escape(suf)}</b>")

                        htpl = f"<b>%{{x}}</b><br>{_escape(s_name)}: <b>%{{y:,.2f}}{_escape(suf)}</b>{drill_hint}<extra></extra>"
                        txt_arr = [f"{v:+,.1f}{suf}" if ("%" in suf and abs(v) > 1e-9) else (f"{v:,.1f}{suf}" if abs(v) > 1e-9 else "") for v in y_arr]

                        if p_type in ("bar", "cum_bar"):
                            marker_cfg = {"color": c_hex, "opacity": opac}
                            if hl_over and idx_s == hl_fact_idx and len(computed_series_arrays) > hl_norm_idx:
                                norm_arr = computed_series_arrays[hl_norm_idx]
                                marker_cfg["color"] = [
                                    over_color if f_v > n_v + 1e-6 else c_hex
                                    for f_v, n_v in zip(y_arr, norm_arr)
                                ]
                            elif hl_over and src_t == "formula":
                                marker_cfg["color"] = [over_color if f_v > 1e-6 else c_hex for f_v in y_arr]

                            tr = {
                                "type": "bar",
                                "name": s_name,
                                "x": x_labels,
                                "y": rounded_y,
                                "marker": marker_cfg,
                                "hovertemplate": htpl,
                            }
                            if show_lbl and self.value_label_mode != "none":
                                tr["text"] = txt_arr
                                tr.update(self._get_bar_text_props())
                        else:
                            has_markers = m_size > 0 and p_type != "area"
                            if p_type == "scatter":
                                mode_s = "markers+text" if (show_lbl and self.value_label_mode != "none") else "markers"
                            else:
                                base_m = "lines+markers" if has_markers else "lines"
                                mode_s = (base_m + "+text") if (show_lbl and self.value_label_mode != "none") else base_m

                            line_dict = {"color": c_hex, "width": l_width, "dash": l_dash}
                            if p_type == "spline":
                                line_dict["shape"] = "spline"
                                line_dict["smoothing"] = 1.15
                            elif p_type == "step":
                                line_dict["shape"] = "hv"

                            tr = {
                                "type": "scatter",
                                "mode": mode_s,
                                "name": s_name,
                                "x": x_labels,
                                "y": rounded_y,
                                "opacity": opac,
                                "line": line_dict,
                                "marker": {"size": max(4, m_size), "color": c_hex},
                                "hovertemplate": htpl,
                                "cliponaxis": False,
                            }
                            if p_type == "area":
                                tr["fill"] = "tozeroy"
                            if "+text" in mode_s:
                                tr["text"] = txt_arr
                                tr["textposition"] = "top center"

                        if swap_y_layers:
                            if y_ax != "y2":
                                tr["yaxis"] = "y2"
                        else:
                            if y_ax == "y2":
                                tr["yaxis"] = "y2"

                        traces_out.append(tr)

                    return traces_out, (" &nbsp;|&nbsp; ".join(hdr_parts) if hdr_parts else "Нет данных"), x_labels

                # 4. Строим 3-уровневую матрицу погружения (1: Тип ТС -> 2: Модель ТС -> 3: Гос. номер)
                if d_field and d_field in combo_df.columns:
                    m_names, m_nums = _extract_month_info(combo_df[d_field])
                    combo_df["_cmb_month"] = m_names
                    combo_df["_cmb_mnum"] = m_nums
                    valid_m = combo_df[combo_df["_cmb_month"] != ""]
                    if len(valid_m) > 0:
                        combo_df = valid_m
                        ord_months = (
                            combo_df[["_cmb_mnum", "_cmb_month"]]
                            .drop_duplicates()
                            .sort_values(by=["_cmb_mnum", "_cmb_month"])["_cmb_month"]
                            .tolist()
                        )
                    else:
                        ord_months = []
                else:
                    ord_months = []

                custom_all_lbl = str(getattr(self, "all_groups_label", "Все категории") or "Все категории").strip()
                matrix_groups = {}
                drill3_map = {}

                def _pack_month_slices(df_slice: pd.DataFrame, x_key: str, s_mode: str, title_prefix: str, lvl_idx: int) -> tuple[dict, dict, list[str]]:
                    m_dict, b_dict = {}, {}
                    tr_full, hdr_all, x_ord = _build_combo_traces_for_df(
                        df_slice, x_key, level_sort_mode=s_mode, level_num=lvl_idx, apply_top_n=False
                    )
                    m_dict["ALL_MONTHS"] = {
                        "traces": tr_full,
                        "header": f"<b>{_escape(title_prefix)}</b> — Весь период &nbsp;|&nbsp; {hdr_all}",
                    }
                    b_dict["ALL_MONTHS"] = "Весь период"
                    if ord_months:
                        month_groups = {k: g for k, g in df_slice.groupby("_cmb_month", sort=False)}
                        for m_name in ord_months:
                            m_sub = month_groups.get(m_name)
                            if m_sub is None or len(m_sub) == 0:
                                tr_m, hdr_m = [], "Нет данных"
                            else:
                                tr_m, hdr_m, _ = _build_combo_traces_for_df(
                                    m_sub, x_key, level_sort_mode=s_mode, level_num=lvl_idx, apply_top_n=False
                                )
                            m_dict[m_name] = {
                                "traces": tr_m,
                                "header": f"<b>{_escape(title_prefix)}</b> — Период: <b>{_escape(m_name)}</b> &nbsp;|&nbsp; {hdr_m}",
                            }
                            b_dict[m_name] = m_name
                    return m_dict, b_dict, x_ord

                # УРОВЕНЬ 1
                l1_months, l1_badges, all_l1_vals = _pack_month_slices(
                    combo_df, "_cmb_l1", sort_lvl1, f"Уровень 1 ({lvl1_col}): {custom_all_lbl}", 1
                )
                matrix_groups["ALL"] = {"months": l1_months, "badges": l1_badges, "level": 1, "label": custom_all_lbl}

                # УРОВЕНЬ 2 и УРОВЕНЬ 3 (однократная группировка через groupby)
                if lvl2_col:
                    l1_groups = {k: g for k, g in combo_df.groupby(combo_df["_cmb_l1"].str.lower(), sort=False)}
                    for l1_val in all_l1_vals[:60]:
                        l1_df = l1_groups.get(l1_val.lower())
                        if l1_df is None or len(l1_df) == 0:
                            continue
                        l2_months, l2_badges, all_l2_vals = _pack_month_slices(
                            l1_df, "_cmb_l2", sort_lvl2, f"Уровень 2 ({lvl2_col}): {l1_val}", 2
                        )
                        matrix_groups[l1_val] = {
                            "months": l2_months,
                            "badges": l2_badges,
                            "level": 2,
                            "parent": "ALL",
                            "label": l1_val,
                        }

                        if lvl3_col and len(drill3_map) < 300:
                            l2_groups = {k: g for k, g in l1_df.groupby(l1_df["_cmb_l2"].str.lower(), sort=False)}
                            for l2_val in all_l2_vals[:30]:
                                if len(drill3_map) >= 300:
                                    break
                                l2_df = l2_groups.get(l2_val.lower())
                                if l2_df is None or len(l2_df) == 0:
                                    continue
                                l3_months, l3_badges, _ = _pack_month_slices(
                                    l2_df, "_cmb_l3", sort_lvl3, f"Уровень 3 ({lvl3_col}): {l1_val} → {l2_val}", 3
                                )
                                drill3_map[f"{l1_val}|||{l2_val}"] = {
                                    "months": l3_months,
                                    "badges": l3_badges,
                                    "level": 3,
                                    "parent_l1": l1_val,
                                    "label": l2_val,
                                }

                # Для первичной отрисовки применяем top_n
                init_traces, _, _ = _build_combo_traces_for_df(
                    combo_df, "_cmb_l1", level_sort_mode=sort_lvl1, level_num=1, apply_top_n=True
                )

                # Находим индекс видимой серии для сортировки в браузере
                vis_series_idx = 0
                vis_counter = 0
                for idx_r, s_r in enumerate(raw_series_list):
                    if not s_r.get("visible", True):
                        continue
                    if idx_r == sort_series_idx:
                        vis_series_idx = vis_counter
                        break
                    vis_counter += 1

                row_slicer_payload = {
                    "__is_matrix__": True,
                    "__is_combo_drill__": True,
                    "has_lvl2": bool(lvl2_col),
                    "has_lvl3": bool(lvl2_col and lvl3_col),
                    "lvl1_title": lvl1_col,
                    "lvl2_title": lvl2_col or "Подкатегория",
                    "lvl3_title": lvl3_col or "Объект / ID",
                    "sort_lvl1": sort_lvl1,
                    "sort_lvl2": sort_lvl2,
                    "sort_lvl3": sort_lvl3,
                    "sort_series_idx": vis_series_idx,
                    "top_n": int(self.top_n or 0),
                    "ordered_months": ["ALL_MONTHS"] + ord_months,
                    "groups": matrix_groups,
                    "drill3": drill3_map,
                    "ALL": init_traces,
                }

                fig = go.Figure(data=init_traces)
                b_mode_combo = str(getattr(self, "combo_barmode", "group") or "group")
                fig.update_layout(title=chart_title, barmode=b_mode_combo)

                raw_tval = str(getattr(self, "combo_target_val", "") or "").strip()
                if raw_tval:
                    try:
                        t_num = float(raw_tval.replace(",", "."))
                        t_lbl = str(getattr(self, "combo_target_label", "Норма / Цель") or "Норма / Цель")
                        t_col = str(getattr(self, "combo_target_color", "#e11d48") or "#e11d48")
                        fig.add_hline(
                            y=t_num,
                            line_dash="dash",
                            line_color=t_col,
                            line_width=2,
                            annotation_text=t_lbl,
                            annotation_position="top right",
                        )
                    except Exception:
                        pass

                x_axis_caption = (self.custom_x_title or self._get_col_display_name(lvl1_col)) if self.show_axis_labels else ""
                s_titles = [
                    str(s.get("name") or s.get("col") or "")
                    for s in raw_series_list
                    if s.get("visible", True) and s.get("y_axis", "y1") != "y2"
                ]
                y_axis_caption = (self.custom_y_title or " / ".join(s_titles[:3])) if self.show_axis_labels else ""

            elif is_hierarchical_pie:
                hole_val = 0.52 if self.chart_type == "donut" else 0.0
                hover_tpl = self._build_hover_template(is_pie=True, has_monthly_data=True)
                dev_mode = getattr(self, "deviation_mode", "formula_pct_self")
                row_scope = getattr(self, "formula_row_scope", "all_rows")

                waybill_df = work_df.copy()
                has_fact_norm = (
                    self.fact_col and self.norm_col
                    and self.fact_col in waybill_df.columns
                    and self.norm_col in waybill_df.columns
                )

                if has_fact_norm:
                    waybill_df["_fact_num"] = _to_num_series(waybill_df[self.fact_col])
                    waybill_df["_norm_num"] = _to_num_series(waybill_df[self.norm_col])
                    waybill_df["_overrun_val"] = waybill_df["_fact_num"] - waybill_df["_norm_num"]

                    eval_mode = getattr(self, "calc_eval_mode", "separate")
                    key_col = (
                        self.calc_group_col
                        if (getattr(self, "calc_group_col", "") and self.calc_group_col in waybill_df.columns)
                        else (
                            self.plate_col
                            if (self.plate_col and self.plate_col in waybill_df.columns)
                            else (self.model_col if (self.model_col and self.model_col in waybill_df.columns) else self.x_col)
                        )
                    )

                    # Режим 1: "grouped" — сначала складываем (Факт - Норматив) по ключевому показателю (например, госномеру)
                    # Режим 2: "separate" — проверяем каждый путевой лист отдельно друг от друга (штатная логика)
                    if eval_mode == "grouped" and key_col and key_col in waybill_df.columns:
                        grp_keys = waybill_df[key_col].fillna("—").astype(str).str.strip()
                        waybill_df["_check_val"] = waybill_df.groupby(grp_keys)["_overrun_val"].transform("sum")
                    else:
                        waybill_df["_check_val"] = waybill_df["_overrun_val"]

                    if self._is_formula_mode():
                        if row_scope == "diff_only":
                            waybill_df = waybill_df[waybill_df["_check_val"].abs() > 1e-6]
                        elif row_scope == "over_only":
                            waybill_df = waybill_df[waybill_df["_check_val"] > 1e-6]
                        elif row_scope == "saving_only":
                            waybill_df = waybill_df[waybill_df["_check_val"] < -1e-6]
                    elif dev_mode == "waybill_count":
                        over_df = waybill_df[waybill_df["_check_val"] > 1e-6]
                        waybill_df = over_df if len(over_df) > 0 else waybill_df[waybill_df["_check_val"].abs() > 1e-6]
                    elif dev_mode == "waybill_saving":
                        sav_df = waybill_df[waybill_df["_check_val"] < -1e-6]
                        waybill_df = sav_df if len(sav_df) > 0 else waybill_df[waybill_df["_check_val"].abs() > 1e-6]
                    elif dev_mode == "waybill_equal_count":
                        waybill_df = waybill_df[waybill_df["_check_val"].abs() <= 1e-6]
                    elif dev_mode in ("waybill_diff_count", "waybill_overrun_sum"):
                        waybill_df = waybill_df[waybill_df["_check_val"].abs() > 1e-6]
                elif dev_mode in ("value_sum", "value_mean"):
                    metric_col = self.fact_col if (self.fact_col and self.fact_col in waybill_df.columns) else (
                        self.y_col.split(",")[0].strip() if self.y_col else ""
                    )
                    if metric_col and metric_col in waybill_df.columns:
                        waybill_df["_metric_val"] = _to_num_series(waybill_df[metric_col])

                if len(waybill_df) == 0:
                    return self.wrap_layout(
                        self._render_empty("В выбранной таблице нет записей, подходящих под условие расчёта")
                    )

                p_col = self.parent_group_col if (self.parent_group_col and self.parent_group_col in waybill_df.columns) else ""
                m_col = self.model_col if (self.model_col and self.model_col in waybill_df.columns) else ""
                if not m_col:
                    if self.x_col and self.x_col in waybill_df.columns and self.x_col != p_col:
                        m_col = self.x_col
                    else:
                        for c in waybill_df.columns:
                            c_str = str(c)
                            if c_str not in (p_col, self.date_col, self.fact_col, self.norm_col):
                                m_col = c_str
                                break
                        if not m_col:
                            m_col = self.x_col

                level1_title = p_col if p_col else "Группа"
                level2_title = m_col if m_col else "Категория"

                waybill_df["_model_clean"] = (
                    waybill_df[m_col].fillna("Не указано").astype(str).str.strip()
                    if m_col in waybill_df.columns
                    else "Не указано"
                )

                allowed_types = self._get_linked_chart_allowed_types(df)
                if p_col and p_col in waybill_df.columns:
                    waybill_df["_type_clean"] = waybill_df[p_col].fillna("").astype(str).str.strip()
                    present_types = [
                        t for t in waybill_df["_type_clean"].value_counts().head(40).index.tolist() if t
                    ]
                    if allowed_types:
                        lower_map = {t.lower(): t for t in waybill_df["_type_clean"].unique() if t}
                        ordered_types = [lower_map[t.lower()] for t in allowed_types if t.lower() in lower_map][:40]
                    else:
                        ordered_types = present_types
                else:
                    waybill_df["_type_clean"] = waybill_df["_model_clean"]
                    ordered_types = [
                        t for t in waybill_df["_model_clean"].value_counts().head(30).index.tolist() if t
                    ]

                if not ordered_types:
                    return self.wrap_layout(self._render_empty("Нет данных по выбранным категориям"))

                type_color_map = {
                    t_name: colors_list[idx % len(colors_list)]
                    for idx, t_name in enumerate(ordered_types)
                }
                unique_models = waybill_df["_model_clean"].unique().tolist()
                model_color_map = {
                    m_name: colors_list[idx % len(colors_list)]
                    for idx, m_name in enumerate(unique_models)
                }

                if self.date_col and self.date_col in waybill_df.columns:
                    m_names, m_nums = _extract_month_info(waybill_df[self.date_col])
                    waybill_df["_month_name"] = m_names
                    waybill_df["_month_num"] = m_nums
                    valid_m_df = waybill_df[waybill_df["_month_name"] != ""]
                    if len(valid_m_df) > 0:
                        waybill_df = valid_m_df
                        month_order_df = (
                            waybill_df[["_month_num", "_month_name"]]
                            .drop_duplicates()
                            .sort_values(by=["_month_num", "_month_name"])
                        )
                        ordered_months = month_order_df["_month_name"].tolist()
                    else:
                        ordered_months = ["Весь период"]
                        waybill_df["_month_name"] = "Весь период"
                else:
                    ordered_months = ["Весь период"]
                    waybill_df["_month_name"] = "Весь период"

                display_mode = getattr(self, "pie_display_mode", "single_interactive")

                if display_mode == "months_grid" and len(ordered_months) >= 1:
                    n_months = len(ordered_months)
                    n_cols_grid = min(3, n_months)
                    n_rows_grid = (n_months + n_cols_grid - 1) // n_cols_grid

                    fig = make_subplots(
                        rows=n_rows_grid,
                        cols=n_cols_grid,
                        specs=[[{"type": "domain"} for _ in range(n_cols_grid)] for _ in range(n_rows_grid)],
                    )
                    domains_list = []
                    for idx_m, m_name in enumerate(ordered_months):
                        r_i = idx_m // n_cols_grid + 1
                        c_i = idx_m % n_cols_grid + 1
                        fig.add_trace(go.Pie(labels=["—"], values=[1], name=m_name, hole=hole_val), row=r_i, col=c_i)
                    for tr in fig.data:
                        domains_list.append({"x": list(tr.domain.x), "y": list(tr.domain.y)})

                    all_overview_traces = []
                    for idx_m, m_name in enumerate(ordered_months):
                        m_df = waybill_df[waybill_df["_month_name"] == m_name]
                        lbls, vals, cust, cols_t, badge_str, s_texts, t_info = self._calc_waybill_types_overview_slice(
                            m_df, ordered_types, m_name, type_color_map, colors_list,
                            level1_col_name=level1_title, level2_col_name=level2_title,
                        )
                        dom = domains_list[idx_m]
                        if lbls and len(vals) > 0:
                            tr_dict = {
                                "type": "pie",
                                "name": m_name,
                                "domain": dom,
                                "title": {
                                    "text": f"<b>{m_name}</b><br><span style='font-size:11px;color:#555;'>Итог: {badge_str}</span>",
                                    "position": "top center",
                                },
                                "labels": lbls,
                                "values": vals,
                                "customdata": cust,
                                "hole": hole_val if hole_val > 0 else 0.38,
                                "marker": {"colors": cols_t},
                                "textinfo": t_info,
                                "hovertemplate": hover_tpl,
                            }
                            if s_texts is not None:
                                tr_dict["text"] = s_texts
                            all_overview_traces.append(tr_dict)
                        else:
                            all_overview_traces.append({
                                "type": "pie",
                                "name": m_name,
                                "domain": dom,
                                "title": {"text": f"<b>{m_name}</b><br><span style='font-size:11px;color:#999;'>Нет данных</span>", "position": "top center"},
                                "labels": ["Нет данных"],
                                "values": [1],
                                "customdata": [f"{m_name}: 0"],
                                "hole": hole_val if hole_val > 0 else 0.38,
                                "marker": {"colors": ["#e2e8f0"]},
                                "textinfo": "none",
                                "hoverinfo": "skip",
                                "showlegend": False,
                            })

                    row_slicer_payload["ALL"] = all_overview_traces

                    for t_name in ordered_types:
                        t_df = waybill_df[waybill_df["_type_clean"].str.lower() == t_name.lower()]
                        t_traces = []
                        for idx_m, m_name in enumerate(ordered_months):
                            m_df = t_df[t_df["_month_name"] == m_name]
                            lbls, vals, cust, cols_m, badge_str, s_texts, t_info = self._calc_waybill_models_slice(
                                m_df, t_name, m_name, model_color_map, colors_list,
                                level1_col_name=level1_title, level2_col_name=level2_title,
                            )
                            dom = domains_list[idx_m]
                            if lbls and len(vals) > 0:
                                tr_dict = {
                                    "type": "pie",
                                    "name": m_name,
                                    "domain": dom,
                                    "title": {
                                        "text": f"<b>{m_name}</b><br><span style='font-size:11px;color:#555;'>{t_name}: {badge_str}</span>",
                                        "position": "top center",
                                    },
                                    "labels": lbls,
                                    "values": vals,
                                    "customdata": cust,
                                    "hole": hole_val if hole_val > 0 else 0.38,
                                    "marker": {"colors": cols_m},
                                    "textinfo": t_info,
                                    "hovertemplate": hover_tpl,
                                }
                                if s_texts is not None:
                                    tr_dict["text"] = s_texts
                                t_traces.append(tr_dict)
                            else:
                                t_traces.append({
                                    "type": "pie",
                                    "name": m_name,
                                    "domain": dom,
                                    "title": {"text": f"<b>{m_name}</b><br><span style='font-size:11px;color:#999;'>{t_name}: 0</span>", "position": "top center"},
                                    "labels": ["Нет данных"],
                                    "values": [1],
                                    "customdata": [f"{t_name} | {m_name}: 0"],
                                    "hole": hole_val if hole_val > 0 else 0.38,
                                    "marker": {"colors": ["#e2e8f0"]},
                                    "textinfo": "none",
                                    "hoverinfo": "skip",
                                    "showlegend": False,
                                })
                        row_slicer_payload[t_name] = t_traces

                    fig = go.Figure(data=all_overview_traces)
                    if n_rows_grid >= 2 and (not self.min_height or self.min_height < 520):
                        fig.update_layout(height=290 * n_rows_grid)
                    fig.update_layout(title=chart_title)

                elif display_mode == "types_grid":
                    n_types = len(ordered_types)
                    n_cols_grid = min(3, n_types)
                    n_rows_grid = (n_types + n_cols_grid - 1) // n_cols_grid

                    fig = make_subplots(
                        rows=n_rows_grid,
                        cols=n_cols_grid,
                        specs=[[{"type": "domain"} for _ in range(n_cols_grid)] for _ in range(n_rows_grid)],
                    )
                    domains_list = []
                    for idx_t, t_name in enumerate(ordered_types):
                        r_i = idx_t // n_cols_grid + 1
                        c_i = idx_t % n_cols_grid + 1
                        fig.add_trace(go.Pie(labels=["—"], values=[1], name=t_name, hole=hole_val), row=r_i, col=c_i)
                    for tr in fig.data:
                        domains_list.append({"x": list(tr.domain.x), "y": list(tr.domain.y)})

                    traces_list = []
                    for idx_t, t_name in enumerate(ordered_types):
                        t_df = waybill_df[waybill_df["_type_clean"].str.lower() == t_name.lower()]
                        lbls, vals, cust, cols_t, badge_str, s_texts, t_info = self._calc_waybill_models_slice(
                            t_df, t_name, "Весь период", model_color_map, colors_list,
                            level1_col_name=level1_title, level2_col_name=level2_title,
                        )
                        dom = domains_list[idx_t]
                        if lbls and len(vals) > 0:
                            tr_dict = {
                                "type": "pie",
                                "name": t_name,
                                "domain": dom,
                                "title": {"text": f"<b>{t_name}</b><br><span style='font-size:11px;color:#555;'>Итог: {badge_str}</span>", "position": "top center"},
                                "labels": lbls,
                                "values": vals,
                                "customdata": cust,
                                "hole": hole_val if hole_val > 0 else 0.38,
                                "marker": {"colors": cols_t},
                                "textinfo": t_info,
                                "hovertemplate": hover_tpl,
                            }
                            if s_texts is not None:
                                tr_dict["text"] = s_texts
                            traces_list.append(tr_dict)
                        else:
                            traces_list.append({
                                "type": "pie",
                                "name": t_name,
                                "domain": dom,
                                "title": {"text": f"<b>{t_name}</b><br><span style='font-size:11px;color:#999;'>Нет данных</span>", "position": "top center"},
                                "labels": ["Нет данных"],
                                "values": [1],
                                "customdata": [f"{t_name}: 0"],
                                "hole": hole_val if hole_val > 0 else 0.38,
                                "marker": {"colors": ["#e2e8f0"]},
                                "textinfo": "none",
                                "hoverinfo": "skip",
                                "showlegend": False,
                            })

                    row_slicer_payload["ALL"] = traces_list
                    fig = go.Figure(data=traces_list)
                    if n_rows_grid >= 2 and (not self.min_height or self.min_height < 520):
                        fig.update_layout(height=290 * n_rows_grid)
                    fig.update_layout(title=chart_title)

                else:
                    def _make_clean_pie_trace(lbls, vals, cust, cols_c, t_info, s_texts, name_str: str) -> dict:
                        tr = {
                            "type": "pie",
                            "name": name_str,
                            "labels": lbls if lbls else ["Нет данных"],
                            "values": vals if vals else [1],
                            "customdata": cust if cust else ["Нет данных"],
                            "hole": hole_val if hole_val > 0 else 0.42,
                            "marker": {
                                "colors": cols_c if cols_c else ["#e2e8f0"],
                                "line": {"color": "#ffffff", "width": 1.5},
                            },
                            "textinfo": t_info if lbls else "none",
                            "textposition": "inside",
                            "insidetextorientation": "horizontal",
                            "textfont": {"size": actual_font_size, "family": "Segoe UI, sans-serif"},
                            "insidetextfont": {"size": actual_font_size, "family": "Segoe UI, sans-serif"},
                            "hovertemplate": hover_tpl,
                            "sort": False,
                        }
                        if s_texts is not None and lbls:
                            tr["text"] = s_texts
                        return tr

                    matrix_groups = {}
                    all_months_dict = {}
                    all_badges_dict = {}

                    lbls_all, vals_all, cust_all, cols_all, badge_all, texts_all, tinfo_all = self._calc_waybill_types_overview_slice(
                        waybill_df, ordered_types, "Весь период", type_color_map, colors_list,
                        level1_col_name=level1_title, level2_col_name=level2_title,
                    )
                    overview_trace = _make_clean_pie_trace(
                        lbls_all, vals_all, cust_all, cols_all, tinfo_all, texts_all, "Все категории"
                    )
                    header_all_html = (
                        f"<b>Все категории ({len(lbls_all)})</b> — Весь период &nbsp;|&nbsp; "
                        f"Общий итог: <b style='color:#003F0B;'>{badge_all}</b>"
                    )
                    all_months_dict["ALL_MONTHS"] = {
                        "traces": [overview_trace],
                        "header": header_all_html,
                    }
                    all_badges_dict["ALL_MONTHS"] = f"Весь период ({badge_all.split(' ')[0]})"

                    if len(ordered_months) > 1:
                        for m_name in ordered_months:
                            m_df = waybill_df[waybill_df["_month_name"] == m_name]
                            l_m, v_m, c_m, cl_m, b_m, tx_m, ti_m = self._calc_waybill_types_overview_slice(
                                m_df, ordered_types, m_name, type_color_map, colors_list,
                                level1_col_name=level1_title, level2_col_name=level2_title,
                            )
                            tr_m = _make_clean_pie_trace(l_m, v_m, c_m, cl_m, ti_m, tx_m, m_name)
                            all_months_dict[m_name] = {
                                "traces": [tr_m],
                                "header": (
                                    f"<b>Все категории ({len(l_m)})</b> — Период: <b>{m_name}</b> &nbsp;|&nbsp; "
                                    f"Итог за месяц: <b style='color:#003F0B;'>{b_m}</b>"
                                ),
                            }
                            all_badges_dict[m_name] = f"{m_name} ({b_m.split(' ')[0]})"

                    matrix_groups["ALL"] = {
                        "months": all_months_dict,
                        "badges": all_badges_dict,
                    }

                    for t_name in ordered_types:
                        t_df = waybill_df[waybill_df["_type_clean"].str.lower() == t_name.lower()]
                        t_months_dict = {}
                        t_badges_dict = {}

                        lbls_m, vals_m, cust_m, cols_m, badge_m, texts_m, tinfo_m = self._calc_waybill_models_slice(
                            t_df, t_name, "Весь период", model_color_map, colors_list,
                            level1_col_name=level1_title, level2_col_name=level2_title,
                        )
                        grp_trace = _make_clean_pie_trace(
                            lbls_m, vals_m, cust_m, cols_m, tinfo_m, texts_m, t_name
                        )
                        t_months_dict["ALL_MONTHS"] = {
                            "traces": [grp_trace],
                            "header": (
                                f"<b>{level1_title}: {t_name}</b> ({level2_title}: {len(lbls_m)}) — Весь период &nbsp;|&nbsp; "
                                f"Итог по группе: <b style='color:#003F0B;'>{badge_m}</b>"
                            ),
                        }
                        t_badges_dict["ALL_MONTHS"] = f"Весь период ({badge_m.split(' ')[0]})"

                        if len(ordered_months) > 1:
                            for m_name in ordered_months:
                                tm_df = t_df[t_df["_month_name"] == m_name]
                                lm_s, vm_s, cm_s, clm_s, bm_s, txm_s, tim_s = self._calc_waybill_models_slice(
                                    tm_df, t_name, m_name, model_color_map, colors_list,
                                    level1_col_name=level1_title, level2_col_name=level2_title,
                                )
                                tr_tm = _make_clean_pie_trace(
                                    lm_s, vm_s, cm_s, clm_s, tim_s, txm_s, f"{t_name} ({m_name})"
                                )
                                t_months_dict[m_name] = {
                                    "traces": [tr_tm],
                                    "header": (
                                        f"<b>{level1_title}: {t_name}</b> ({level2_title}: {len(lm_s)}) — Период: <b>{m_name}</b> &nbsp;|&nbsp; "
                                        f"Итог группы за {m_name}: <b style='color:#003F0B;'>{bm_s}</b>"
                                    ),
                                }
                                t_badges_dict[m_name] = f"{m_name} ({bm_s.split(' ')[0]})"

                        matrix_groups[t_name] = {
                            "months": t_months_dict,
                            "badges": t_badges_dict,
                        }

                    row_slicer_payload = {
                        "__is_matrix__": True,
                        "ordered_months": ["ALL_MONTHS"] + [m for m in ordered_months if m != "Весь период"],
                        "groups": matrix_groups,
                        "ALL": [overview_trace],
                    }

                    fig = go.Figure(data=[overview_trace])
                    fig.update_layout(
                        title=chart_title,
                        uniformtext=dict(minsize=max(10, actual_font_size - 2), mode="hide"),
                        height=max(380, int(self.min_height or 0)),
                    )

                x_axis_caption = ""
                y_axis_caption = ""

            # =========================================================
            # РЕЖИМ ИЕРАРХИЧЕСКОГО ЛИНЕЙНОГО / СТОЛБЧАТОГО / НАКОПИТЕЛЬНОГО ГРАФИКА
            # (Поддерживает 2, 3 и более столбцов из Оси Y или Факт/Норматив с разбивкой по Месяцам и Типам ТС)
            # =========================================================
            elif (
                self.chart_type in ("line", "bar", "bar_stacked", "bar_cumulative", "bar_stacked_100", "hbar", "area")
                and self.data_mode != "rows"
                and (
                    (self.date_col and self.date_col in work_df.columns)
                    or (self.x_col and self.x_col in work_df.columns and (_extract_month_info(work_df[self.x_col])[0] != "").any())
                )
                and (
                    bool([c.strip() for c in str(self.y_col or "").split(",") if c.strip() in work_df.columns])
                    or (self.fact_col and self.fact_col in work_df.columns)
                    or (self.norm_col and self.norm_col in work_df.columns)
                )
            ):
                xy_df = work_df.copy()
                active_date_col = (
                    self.date_col
                    if (self.date_col and self.date_col in xy_df.columns)
                    else self.x_col
                )

                # Собираем все выбранные столбцы показателей (из Оси Y + Столбец А / Столбец Б)
                metric_cols: list[str] = []
                for raw_c in str(self.y_col or "").split(","):
                    c_clean = raw_c.strip()
                    if c_clean and c_clean in xy_df.columns and c_clean not in metric_cols:
                        metric_cols.append(c_clean)
                for extra_c in (self.norm_col, self.fact_col):
                    if extra_c and extra_c in xy_df.columns and extra_c not in metric_cols:
                        metric_cols.append(extra_c)

                num_keys = []
                for idx_mc, mc in enumerate(metric_cols):
                    k_name = f"_mval_{idx_mc}"
                    xy_df[k_name] = _to_num_series(xy_df[mc])
                    num_keys.append(k_name)

                p_col = (
                    self.parent_group_col
                    if (self.parent_group_col and self.parent_group_col in xy_df.columns)
                    else (self.x_col if (self.x_col and self.x_col in xy_df.columns and self.x_col != active_date_col) else "")
                )
                if not p_col:
                    for cand in xy_df.columns:
                        c_str = str(cand)
                        if c_str != active_date_col and c_str not in metric_cols:
                            if any(w in c_str.lower() for w in ("тип", "групп", "категор", "филиал")):
                                p_col = c_str
                                break

                m_col = (
                    self.model_col
                    if (self.model_col and self.model_col in xy_df.columns)
                    else (self.x_col if (self.x_col and self.x_col in xy_df.columns and self.x_col not in (p_col, active_date_col)) else p_col)
                )

                xy_df["_grp_clean"] = (
                    DataMemoryCache.get_str_series(xy_df, p_col) if p_col else "Все категории"
                )
                xy_df["_sub_clean"] = (
                    DataMemoryCache.get_str_series(xy_df, m_col) if m_col else xy_df["_grp_clean"]
                )

                m_names, m_nums = _extract_month_info(xy_df[active_date_col])
                xy_df["_month_name"] = m_names
                xy_df["_month_num"] = m_nums
                xy_df = xy_df[xy_df["_month_name"] != ""]

                if len(xy_df) == 0:
                    return self.wrap_layout(self._render_empty("Не удалось распознать месяцы в выбранном столбце даты"))

                month_order_df = (
                    xy_df[["_month_num", "_month_name"]]
                    .drop_duplicates()
                    .sort_values(by=["_month_num", "_month_name"])
                )
                ordered_months = month_order_df["_month_name"].tolist()
                ordered_types = [t for t in xy_df["_grp_clean"].value_counts().head(50).index.tolist() if t]
                hover_tpl = self._build_hover_template(is_pie=False)

                # Переименованные названия столбцов для легенды и шапки
                display_metric_names = [
                    self._get_col_display_name(mc, idx_m) for idx_m, mc in enumerate(metric_cols)
                ]
                use_grp_prefix = bool(getattr(self, "prefix_legend_with_group", False))
                custom_all_label = str(getattr(self, "all_groups_label", "Итого (Все категории)") or "").strip()

                def _make_multi_xy_traces(x_vals: list[str], series_matrix: list[list[float]], grp_title: str, is_cumulative: bool = False) -> list[dict]:
                    traces = []
                    t_kind = "scatter" if self.chart_type in ("line", "area", "scatter") else "bar"
                    mode_s = "lines+markers+text" if (self.show_values and self.value_label_mode in ("value", "label+value+percent")) else "lines+markers"

                    for idx_s, (disp_label, raw_y_arr) in enumerate(zip(display_metric_names, series_matrix)):
                        y_arr = list(raw_y_arr)
                        if is_cumulative:
                            running = 0.0
                            cum_arr = []
                            for v in y_arr:
                                running += float(v)
                                cum_arr.append(running)
                            y_arr = cum_arr

                        c_hex = colors_list[idx_s % len(colors_list)]
                        if use_grp_prefix and grp_title:
                            s_name = f"{grp_title} ({disp_label})"
                        else:
                            s_name = disp_label

                        if t_kind == "scatter":
                            tr = {
                                "type": "scatter",
                                "mode": mode_s,
                                "name": s_name,
                                "x": x_vals,
                                "y": [round(v, 2) for v in y_arr],
                                "line": {"width": 3, "color": c_hex},
                                "marker": {"size": 8, "color": c_hex},
                                "hovertemplate": hover_tpl,
                            }
                            if self.chart_type == "area":
                                tr["fill"] = "tozeroy"
                            if "text" in mode_s:
                                tr["text"] = [f"{v:,.0f}" for v in y_arr]
                                tr["textposition"] = "top center"
                        else:
                            tr = {
                                "type": "bar",
                                "name": s_name,
                                "x": x_vals,
                                "y": [round(v, 2) for v in y_arr],
                                "marker": {"color": c_hex},
                                "hovertemplate": hover_tpl,
                            }
                            if self.show_values and self.value_label_mode != "none":
                                tr["text"] = [f"{v:,.0f}" if abs(v) > 0 else "" for v in y_arr]
                                if self.chart_type in ("bar_stacked", "bar_cumulative", "bar_stacked_100"):
                                    tr["textposition"] = "inside"
                                    if getattr(self, "bar_text_angle", "0") in ("0", "-90", "-45"):
                                        tr["textangle"] = int(getattr(self, "bar_text_angle", "0"))
                                else:
                                    tr.update(self._get_bar_text_props())
                        traces.append(tr)
                    return traces

                agg_method = "mean" if self.agg == "mean" else ("max" if self.agg == "max" else ("min" if self.agg == "min" else "sum"))
                is_cum_mode = (self.chart_type == "bar_cumulative")

                def _build_group_month_matrix(sub_df: pd.DataFrame, grp_caption: str, drill_col: str) -> tuple[dict, dict]:
                    m_dict = {}
                    b_dict = {}

                    by_m = getattr(sub_df.groupby("_month_name", sort=False)[num_keys], agg_method)()
                    series_by_m = []
                    summary_parts = []
                    grand_total = 0.0

                    for disp_lbl, k_name in zip(display_metric_names, num_keys):
                        arr = [float(by_m.loc[m, k_name]) if m in by_m.index else 0.0 for m in ordered_months]
                        series_by_m.append(arr)
                        col_tot = sum(arr)
                        grand_total += col_tot
                        summary_parts.append(f"{disp_lbl}: <b>{col_tot:,.1f}</b>")

                    tot_lbl = str(getattr(self, "summary_total_label", "Σ Итого") or "").strip()
                    show_tot = bool(getattr(self, "show_summary_total", False))
                    tot_suffix_all = f" &nbsp;|&nbsp; {_escape(tot_lbl)}: <b style='color:#003F0B;'>{grand_total:,.1f}</b>" if show_tot and tot_lbl else ""

                    hdr_prefix = f"<b>{grp_caption}</b> — Весь период &nbsp;|&nbsp; " if grp_caption else "<b>Весь период</b> &nbsp;|&nbsp; "
                    m_dict["ALL_MONTHS"] = {
                        "traces": _make_multi_xy_traces(ordered_months, series_by_m, grp_caption, is_cumulative=is_cum_mode),
                        "header": hdr_prefix + " &nbsp;|&nbsp; ".join(summary_parts) + tot_suffix_all,
                    }
                    b_dict["ALL_MONTHS"] = "Весь период"

                    for m_name in ordered_months:
                        m_slice = sub_df[sub_df["_month_name"] == m_name]
                        m_summary_parts = []
                        m_grand = 0.0
                        for disp_lbl, k_name in zip(display_metric_names, num_keys):
                            mv = float(getattr(m_slice[k_name], agg_method)()) if len(m_slice) > 0 else 0.0
                            m_grand += mv
                            m_summary_parts.append(f"{disp_lbl}: <b>{mv:,.1f}</b>")

                        if len(m_slice) > 0 and drill_col in m_slice.columns:
                            by_cat = getattr(m_slice.groupby(drill_col, sort=False)[num_keys], agg_method)()
                            by_cat["_tot"] = by_cat[num_keys].sum(axis=1)
                            by_cat = by_cat.sort_values(by="_tot", ascending=False).head(max(1, int(self.top_n or 15)))
                            cat_names = [str(x) for x in by_cat.index.tolist()]
                            cat_series = [[float(v) for v in by_cat[k_name].tolist()] for k_name in num_keys]
                        else:
                            cat_names = [m_name]
                            cat_series = [[float(getattr(m_slice[k_name], agg_method)()) if len(m_slice) > 0 else 0.0] for k_name in num_keys]

                        tot_suffix_m = f" &nbsp;|&nbsp; {_escape(tot_lbl)}: <b style='color:#003F0B;'>{m_grand:,.1f}</b>" if show_tot and tot_lbl else ""
                        m_hdr_prefix = f"<b>{grp_caption}</b> — Период: <b>{m_name}</b> &nbsp;|&nbsp; " if grp_caption else f"Период: <b>{m_name}</b> &nbsp;|&nbsp; "
                        m_dict[m_name] = {
                            "traces": _make_multi_xy_traces(cat_names, cat_series, f"{grp_caption} — {m_name}" if grp_caption else m_name, is_cumulative=False),
                            "header": m_hdr_prefix + " &nbsp;|&nbsp; ".join(m_summary_parts) + tot_suffix_m,
                        }

                        b_dict[m_name] = m_name

                    return m_dict, b_dict

                matrix_groups = {}
                all_m_dict, all_b_dict = _build_group_month_matrix(xy_df, custom_all_label, "_grp_clean")
                matrix_groups["ALL"] = {"months": all_m_dict, "badges": all_b_dict}

                for t_name in ordered_types:
                    t_slice = xy_df[xy_df["_grp_clean"].str.lower() == t_name.lower()]
                    tm_dict, tb_dict = _build_group_month_matrix(t_slice, t_name, "_sub_clean")
                    matrix_groups[t_name] = {"months": tm_dict, "badges": tb_dict}

                init_traces = all_m_dict["ALL_MONTHS"]["traces"]
                row_slicer_payload = {
                    "__is_matrix__": True,
                    "ordered_months": ["ALL_MONTHS"] + ordered_months,
                    "groups": matrix_groups,
                    "ALL": init_traces,
                }

                fig = go.Figure(data=init_traces)
                if self.chart_type in ("bar_stacked", "bar_cumulative"):
                    fig.update_layout(barmode="stack")
                elif self.chart_type == "bar_stacked_100":
                    fig.update_layout(barmode="stack", barnorm="percent")
                elif self.chart_type == "bar":
                    fig.update_layout(barmode="group")

                fig.update_layout(title=chart_title)
                x_axis_caption = (self.custom_x_title or "Период / Категория") if self.show_axis_labels else ""
                default_y_cap = "Доля, %" if self.chart_type == "bar_stacked_100" else " / ".join(display_metric_names)
                y_axis_caption = (self.custom_y_title or default_y_cap) if self.show_axis_labels else ""

            elif self.data_mode == "rows":
                sel_cols = [c for c in (self.row_columns or []) if c in work_df.columns and c != self.x_col]
                if not sel_cols:
                    sel_cols = [
                        str(c) for c in work_df.columns
                        if str(c) not in (self.x_col, self.parent_group_col)
                    ][:6]

                if not sel_cols:
                    return self.wrap_layout(self._render_empty("Отметьте столбцы месяцев в Инспекторе"))

                row_multi_mode = getattr(self, "row_multi_mode", "separate")
                row_multi_func = getattr(self, "row_multi_func", "sum")

                if self.chart_type in ("pie", "donut"):
                    hole_val = 0.52 if self.chart_type == "donut" else 0.0
                    pie_textinfo = self._get_pie_textinfo()
                    pie_mode = getattr(self, "pie_row_mode", "models_with_months")

                    for c in sel_cols:
                        work_df[c] = _to_num_series(work_df[c])

                    month_labels = [
                        (str(c).split("_", 1)[0].strip() if ("_" in str(c) and self.clean_col_labels) else str(c))
                        for c in sel_cols
                    ]

                    def _make_models_pie_data(sub_df: pd.DataFrame):
                        grouped_m = sub_df.groupby(sub_df[self.x_col].fillna("—").astype(str).str.strip(), sort=False)[sel_cols].sum()
                        if len(grouped_m) == 0:
                            return [], [], [], {}
                        models = grouped_m.index.tolist()
                        month_totals = {c: float(grouped_m[c].sum()) for c in sel_cols}
                        total_vals = []
                        custom_hover_list = []
                        per_month_vals = {m_lbl: [] for m_lbl in month_labels}

                        for m_name in models:
                            row_s = grouped_m.loc[m_name]
                            m_tot = float(row_s.sum())
                            total_vals.append(max(0.0, m_tot))
                            lines = ["<b>Помесячно (% нарушений):</b>"]
                            for c, m_lbl in zip(sel_cols, month_labels):
                                v = max(0.0, float(row_s[c]))
                                per_month_vals[m_lbl].append(v)
                                m_sum = month_totals[c]
                                pct = (v / m_sum * 100.0) if m_sum > 0 else 0.0
                                lines.append(f"• {m_lbl}: <b>{pct:.1f}%</b> ({v:,.1f})")
                            custom_hover_list.append("<br>".join(lines))

                        return models, total_vals, custom_hover_list, per_month_vals

                    models_all, vals_all, custom_all, per_month_all = _make_models_pie_data(work_df)
                    slice_colors = [colors_list[i % len(colors_list)] for i in range(max(len(models_all), len(month_labels), 1))]
                    hover_tpl = self._build_hover_template(is_pie=True, has_monthly_data=True)

                    if pie_mode == "subplots_by_month" and len(sel_cols) > 1:
                        n_cols_grid = min(3, len(sel_cols))
                        n_rows_grid = (len(sel_cols) + n_cols_grid - 1) // n_cols_grid
                        fig = make_subplots(
                            rows=n_rows_grid,
                            cols=n_cols_grid,
                            specs=[[{"type": "domain"} for _ in range(n_cols_grid)] for _ in range(n_rows_grid)],
                            subplot_titles=month_labels,
                        )
                        for idx_m, m_lbl in enumerate(month_labels):
                            r_i = idx_m // n_cols_grid + 1
                            c_i = idx_m % n_cols_grid + 1
                            fig.add_trace(
                                go.Pie(
                                    labels=models_all,
                                    values=per_month_all[m_lbl],
                                    name=m_lbl,
                                    hole=hole_val,
                                    marker=dict(colors=slice_colors),
                                    textinfo=pie_textinfo,
                                    customdata=custom_all,
                                    hovertemplate=hover_tpl,
                                ),
                                row=r_i,
                                col=c_i,
                            )
                    elif pie_mode == "slices_are_months":
                        month_sums = [max(0.0, float(work_df[c].sum())) for c in sel_cols]
                        hover_simple = self._build_hover_template(is_pie=True, has_monthly_data=False)
                        main_trace = {
                            "type": "pie",
                            "labels": month_labels,
                            "values": month_sums,
                            "hole": hole_val,
                            "marker": {"colors": slice_colors[:len(month_labels)]},
                            "textinfo": pie_textinfo,
                            "hovertemplate": hover_simple,
                        }
                        row_slicer_payload["ALL"] = [main_trace]
                        for df_idx, r_name in zip(work_df.index, work_df[self.x_col].fillna("—").astype(str).str.strip()):
                            r_vals = [max(0.0, _to_float(work_df.loc[df_idx, c])) for c in sel_cols]
                            row_slicer_payload[r_name] = [{
                                **main_trace,
                                "name": r_name,
                                "values": r_vals,
                            }]
                        fig = go.Figure(data=[main_trace])
                    else:
                        main_trace = {
                            "type": "pie",
                            "labels": models_all,
                            "values": vals_all,
                            "customdata": custom_all,
                            "hole": hole_val,
                            "marker": {"colors": slice_colors[:len(models_all)]},
                            "textinfo": pie_textinfo,
                            "hovertemplate": hover_tpl,
                        }
                        row_slicer_payload["ALL"] = [main_trace]
                        fig = go.Figure(data=[main_trace])

                    fig.update_layout(title=chart_title)
                    x_axis_caption = ""
                    y_axis_caption = ""

                else:
                    if row_multi_mode == "combined" and len(sel_cols) >= 2:
                        months_dict = {}
                        for c in sel_cols:
                            c_str = str(c)
                            if "_" in c_str:
                                m_name = c_str.split("_", 1)[0].strip()
                                months_dict.setdefault(m_name, []).append(c_str)
                            else:
                                months_dict.setdefault(c_str, []).append(c_str)

                        new_sel_cols = []
                        for m_name, m_cols in months_dict.items():
                            if len(m_cols) >= 2:
                                for c in m_cols:
                                    work_df[c] = _to_num_series(work_df[c])
                                combined_col_name = f"{m_name}_Объединено"
                                if row_multi_func == "sum":
                                    work_df[combined_col_name] = work_df[m_cols].sum(axis=1)
                                elif row_multi_func == "sub":
                                    work_df[combined_col_name] = work_df[m_cols[0]] - work_df[m_cols[1]]
                                elif row_multi_func == "mul":
                                    work_df[combined_col_name] = work_df[m_cols].prod(axis=1)
                                elif row_multi_func == "div":
                                    work_df[combined_col_name] = work_df[m_cols[0]] / work_df[m_cols[1]].replace(0, pd.NA)
                                    work_df[combined_col_name] = work_df[combined_col_name].fillna(0)
                                elif row_multi_func == "mean":
                                    work_df[combined_col_name] = work_df[m_cols].mean(axis=1)
                                else:
                                    work_df[combined_col_name] = work_df[m_cols].sum(axis=1)
                                new_sel_cols.append(combined_col_name)
                            else:
                                new_sel_cols.extend(m_cols)
                        sel_cols = new_sel_cols

                    metric_groups = {}
                    for c in sel_cols:
                        c_str = str(c)
                        if "_" in c_str and getattr(self, "clean_col_labels", True):
                            parts = c_str.split("_", 1)
                            month = parts[0].strip()
                            suf = parts[1].strip()
                        else:
                            month = c_str
                            suf = "Значение"

                        if suf not in metric_groups:
                            metric_groups[suf] = {"months": [], "cols": []}
                        metric_groups[suf]["months"].append(month)
                        metric_groups[suf]["cols"].append(c_str)

                    for c in sel_cols:
                        work_df[c] = _to_num_series(work_df[c])

                    all_traces = []
                    row_slicer_payload = {}
                    hover_tpl = self._build_hover_template(is_pie=False)

                    def _build_row_traces_for_series(r_name: str, series_row) -> list[dict]:
                        r_traces = []
                        for suf_idx, (suf, data) in enumerate(metric_groups.items()):
                            x_months = data["months"]
                            y_vals = [round(float(series_row[c]), 2) for c in data["cols"]]
                            c_hex = colors_list[suf_idx % len(colors_list)]
                            trace_name = f"{r_name} ({suf})" if suf != "Значение" and len(metric_groups) > 1 else r_name
                            t_type = self.chart_type

                            if t_type == "scatter":
                                trace = {"type": "scatter", "mode": "markers", "name": trace_name, "x": x_months, "y": y_vals, "marker": {"size": 11, "color": c_hex}, "hovertemplate": hover_tpl}
                            elif t_type == "line":
                                mode_str = "lines+markers+text" if (self.show_values and self.value_label_mode in ("value", "label+value+percent")) else "lines+markers"
                                trace = {"type": "scatter", "mode": mode_str, "name": trace_name, "x": x_months, "y": y_vals, "line": {"width": 3, "color": c_hex}, "marker": {"size": 8, "color": c_hex}, "hovertemplate": hover_tpl}
                                if "text" in mode_str:
                                    trace["text"] = [f"{v:,.1f}" for v in y_vals]
                                    trace["textposition"] = "top center"
                            else:
                                trace = {"type": "bar", "name": trace_name, "x": x_months, "y": y_vals, "marker": {"color": c_hex}, "hovertemplate": hover_tpl}
                                if self.show_values and self.value_label_mode != "none":
                                    trace["text"] = [f"{v:,.1f}" for v in y_vals]
                                    trace["textposition"] = "auto"
                            r_traces.append(trace)
                        return r_traces

                    work_df["_x_key"] = work_df[self.x_col].fillna("—").astype(str).str.strip()
                    grouped_x = (
                        work_df.groupby("_x_key", sort=False)[sel_cols].mean()
                        if (self.agg == "mean" or self.row_target_val == "__MEAN__")
                        else work_df.groupby("_x_key", sort=False)[sel_cols].sum()
                    )
                    for r_name in grouped_x.index:
                        r_tr = _build_row_traces_for_series(str(r_name), grouped_x.loc[r_name])
                        row_slicer_payload[str(r_name)] = r_tr
                        all_traces.extend(r_tr)

                    if self.parent_group_col and self.parent_group_col in work_df.columns and self.parent_group_col != self.x_col:
                        work_df["_p_key"] = work_df[self.parent_group_col].fillna("—").astype(str).str.strip()
                        grouped_p = (
                            work_df.groupby("_p_key", sort=False)[sel_cols].mean()
                            if (self.agg == "mean" or self.row_target_val == "__MEAN__")
                            else work_df.groupby("_p_key", sort=False)[sel_cols].sum()
                        )
                        for p_name in grouped_p.index:
                            if str(p_name) not in row_slicer_payload:
                                row_slicer_payload[str(p_name)] = _build_row_traces_for_series(str(p_name), grouped_p.loc[p_name])

                    sum_traces = []
                    mean_traces = []
                    for suf_idx, (suf, data) in enumerate(metric_groups.items()):
                        x_months = data["months"]
                        sum_y = [round(float(work_df[c].sum()), 2) for c in data["cols"]]
                        mean_y = [round(float(work_df[c].mean()), 2) for c in data["cols"]]
                        c_hex = colors_list[suf_idx % len(colors_list)]
                        s_name = f"Итого ({suf})" if suf != "Значение" and len(metric_groups) > 1 else "Итого (Сумма)"
                        m_name = f"Среднее ({suf})" if suf != "Значение" and len(metric_groups) > 1 else "Среднее"

                        is_bar_row = self.chart_type in ("bar", "bar_stacked", "bar_cumulative", "bar_stacked_100")
                        trace_base = {
                            "type": "bar" if is_bar_row else "scatter",
                            "marker": {"color": c_hex},
                            "hovertemplate": hover_tpl,
                        }
                        if not is_bar_row:
                            trace_base["mode"] = "lines+markers"
                            trace_base["line"] = {"width": 4, "color": c_hex}

                        sum_traces.append({**trace_base, "name": s_name, "x": x_months, "y": sum_y})
                        mean_traces.append({**trace_base, "name": m_name, "x": x_months, "y": mean_y})

                    default_aggregate = mean_traces if self.row_target_val == "__MEAN__" else sum_traces

                    if self.row_target_val == "__ALL_SERIES__":
                        row_slicer_payload["ALL"] = default_aggregate
                        initial_traces = default_aggregate
                    elif self.row_target_val == "__MEAN__":
                        row_slicer_payload["ALL"] = mean_traces
                        initial_traces = mean_traces
                    elif self.row_target_val == "__SUM__":
                        row_slicer_payload["ALL"] = sum_traces
                        initial_traces = sum_traces
                    elif self.row_target_val and self.row_target_val != "__ALL_SERIES__":
                        row_slicer_payload["ALL"] = default_aggregate
                        initial_traces = [t for t in all_traces if t.get("name") and t["name"].startswith(self.row_target_val)]
                        if not initial_traces:
                            initial_traces = default_aggregate
                    else:
                        row_slicer_payload["ALL"] = default_aggregate
                        initial_traces = default_aggregate

                    all_x_months = []
                    for data in metric_groups.values():
                        for m in data["months"]:
                            if m not in all_x_months:
                                all_x_months.append(m)

                    fig = go.Figure(data=initial_traces)
                    if self.chart_type in ("bar_stacked", "bar_cumulative"):
                        fig.update_layout(barmode="stack")
                    elif self.chart_type == "bar_stacked_100":
                        fig.update_layout(barmode="stack", barnorm="percent")
                    elif self.chart_type == "bar":
                        fig.update_layout(barmode="group")
                    fig.update_layout(
                        title=chart_title,
                        xaxis_title="Месяц" if self.show_axis_labels else "",
                        yaxis_title="Значение" if self.show_axis_labels else "",
                    )
                    fig.update_xaxes(type="category", categoryorder="array", categoryarray=all_x_months)

                    x_axis_caption = "Месяц" if self.show_axis_labels else ""
                    y_axis_caption = "Значение" if self.show_axis_labels else ""

            # =========================================================
            # РЕЖИМ 2: КЛАССИЧЕСКИЙ ПО СТОЛБЦАМ (ВКЛЮЧАЯ PIE / DONUT / BAR / LINE)
            # =========================================================
            else:
                y_fields = [c.strip() for c in str(self.y_col or "").split(",") if c.strip()]
                y_fields = [c for c in y_fields if c in work_df.columns]

                multi_y_mode = getattr(self, "multi_y_mode", "separate")
                multi_y_func = getattr(self, "multi_y_func", "sum")

                if multi_y_mode == "combined" and len(y_fields) >= 2:
                    for c in y_fields:
                        work_df[c] = _to_num_series(work_df[c])
                    combined_col_name = " / ".join(y_fields)

                    eval_mode = getattr(self, "calc_eval_mode", "separate")
                    key_col = (
                        self.calc_group_col
                        if (getattr(self, "calc_group_col", "") and self.calc_group_col in work_df.columns)
                        else (self.plate_col if (self.plate_col and self.plate_col in work_df.columns) else "")
                    )

                    # Если выбран сгруппированный расчёт по ключевому показателю, сначала агрегируем строки по ключу
                    if eval_mode == "grouped" and key_col and key_col in work_df.columns:
                        group_cols = [key_col]
                        if self.x_col and self.x_col in work_df.columns and self.x_col != key_col:
                            group_cols.insert(0, self.x_col)
                        work_df = work_df.groupby(group_cols, as_index=False, sort=False)[y_fields].sum()

                    if multi_y_func == "sum":
                        work_df[combined_col_name] = work_df[y_fields].sum(axis=1)
                    elif multi_y_func == "sub":
                        work_df[combined_col_name] = work_df[y_fields[0]] - work_df[y_fields[1]]
                    elif multi_y_func == "mul":
                        work_df[combined_col_name] = work_df[y_fields].prod(axis=1)
                    elif multi_y_func == "div":
                        work_df[combined_col_name] = work_df[y_fields[0]] / work_df[y_fields[1]].replace(0, pd.NA)
                        work_df[combined_col_name] = work_df[combined_col_name].fillna(0)
                    elif multi_y_func == "mean":
                        work_df[combined_col_name] = work_df[y_fields].mean(axis=1)
                    else:
                        work_df[combined_col_name] = work_df[y_fields].sum(axis=1)

                    # В сгруппированном режиме при необходимости отсекаем только экономию или только перерасход по ключу
                    row_scope = getattr(self, "formula_row_scope", "all_rows")
                    if eval_mode == "grouped" and multi_y_func == "sub":
                        if row_scope == "saving_only":
                            work_df = work_df[work_df[combined_col_name] < -1e-6]
                        elif row_scope == "over_only":
                            work_df = work_df[work_df[combined_col_name] > 1e-6]
                        elif row_scope == "diff_only":
                            work_df = work_df[work_df[combined_col_name].abs() > 1e-6]

                    y_fields = [combined_col_name]

                if self.chart_type == "histogram":
                    fig = px.histogram(
                        work_df, x=self.x_col, title=chart_title,
                        color_discrete_sequence=colors_list,
                    )
                else:
                    if not y_fields or self.agg == "count":
                        grouped = work_df[self.x_col].astype(str).value_counts()
                        y_label = "Количество записей"
                        plot_df = pd.DataFrame({self.x_col: grouped.index.tolist(), y_label: grouped.values.tolist()})
                        y_fields = [y_label]
                    else:
                        for c in y_fields:
                            work_df[c] = _to_num_series(work_df[c])
                        grp = work_df.groupby(work_df[self.x_col].astype(str), as_index=False, sort=False)[y_fields]
                        if self.agg == "mean":
                            plot_df = grp.mean()
                        elif self.agg == "max":
                            plot_df = grp.max()
                        elif self.agg == "min":
                            plot_df = grp.min()
                        elif self.agg == "median":
                            plot_df = grp.median()
                        else:
                            plot_df = grp.sum()

                    if self.sort_by == "value_desc":
                        plot_df = plot_df.sort_values(by=y_fields[0], ascending=False)
                    elif self.sort_by == "value_asc":
                        plot_df = plot_df.sort_values(by=y_fields[0], ascending=True)
                    elif self.sort_by == "label_asc":
                        plot_df = plot_df.sort_values(by=self.x_col, ascending=True)

                    if self.top_n > 0:
                        plot_df = plot_df.head(self.top_n)

                    y_arg = y_fields if len(y_fields) > 1 else y_fields[0]
                    hover_tpl = self._build_hover_template(
                        is_pie=(self.chart_type in ("pie", "donut")),
                        has_monthly_data=(len(y_fields) > 1),
                    )

                    if self.chart_type in ("bar", "bar_stacked", "bar_cumulative", "bar_stacked_100"):
                        if self.chart_type == "bar_cumulative" and y_fields:
                            plot_df = plot_df.copy()
                            plot_df[y_fields] = plot_df[y_fields].cumsum()
                        b_mode = "group" if self.chart_type == "bar" else "stack"
                        fig = px.bar(
                            plot_df, x=self.x_col, y=y_arg, barmode=b_mode,
                            color_discrete_sequence=colors_list, title=chart_title,
                        )
                        if self.chart_type == "bar_stacked_100":
                            fig.update_layout(barnorm="percent")
                        fig.update_traces(hovertemplate=hover_tpl)
                    elif self.chart_type == "hbar":
                        fig = px.bar(
                            plot_df, x=y_arg, y=self.x_col, orientation="h", barmode="group",
                            color_discrete_sequence=colors_list, title=chart_title,
                        )
                        fig.update_traces(hovertemplate=hover_tpl)
                    elif self.chart_type == "line":
                        fig = px.line(
                            plot_df, x=self.x_col, y=y_arg, markers=True,
                            color_discrete_sequence=colors_list, title=chart_title,
                        )
                        fig.update_traces(hovertemplate=hover_tpl)
                    elif self.chart_type == "scatter":
                        fig = px.scatter(
                            plot_df, x=self.x_col, y=y_arg,
                            color_discrete_sequence=colors_list, title=chart_title,
                        )
                        fig.update_traces(marker=dict(size=11), hovertemplate=hover_tpl)
                    elif self.chart_type == "area":
                        fig = px.area(
                            plot_df, x=self.x_col, y=y_arg,
                            color_discrete_sequence=colors_list, title=chart_title,
                        )
                        fig.update_traces(hovertemplate=hover_tpl)
                    elif self.chart_type in ("pie", "donut"):
                        hole_val = 0.52 if self.chart_type == "donut" else 0.0
                        pie_textinfo = self._get_pie_textinfo()
                        raw_labels = plot_df[self.x_col].astype(str).tolist()
                        raw_vals = [max(0.0, _to_float(v)) for v in plot_df[y_fields[0]].tolist()]
                        tot_v = sum(raw_vals) if raw_vals else 0.0
                        labels_list, vals_list = [], []
                        for lbl_i, val_i in zip(raw_labels, raw_vals):
                            sh_pct = (val_i / tot_v * 100.0) if tot_v > 0 else 0.0
                            if self._check_pie_pct_filter(sh_pct, sh_pct, False):
                                labels_list.append(lbl_i)
                                vals_list.append(val_i)
                        slice_colors = [colors_list[i % len(colors_list)] for i in range(len(labels_list))]
                        fig = go.Figure(
                            data=[
                                go.Pie(
                                    labels=labels_list,
                                    values=vals_list,
                                    hole=hole_val,
                                    marker=dict(colors=slice_colors, line=dict(color="#ffffff", width=1.5)),
                                    textinfo="percent" if pie_textinfo == "percent+label" else pie_textinfo,
                                    textposition="inside",
                                    insidetextorientation="horizontal",
                                    hovertemplate=hover_tpl,
                                )
                            ]
                        )
                        fig.update_layout(
                            title=chart_title,
                            uniformtext=dict(minsize=9, mode="hide"),
                            height=max(360, int(self.min_height or 0)),
                        )
                    elif self.chart_type == "box":
                        fig = px.box(
                            work_df, y=y_arg, title=chart_title,
                            color_discrete_sequence=colors_list,
                        )
                    elif self.chart_type == "funnel":
                        fig = px.funnel(
                            plot_df, x=y_fields[0], y=self.x_col,
                            color_discrete_sequence=colors_list, title=chart_title,
                        )
                    else:
                        fig = px.bar(
                            plot_df, x=self.x_col, y=y_arg, barmode="group",
                            color_discrete_sequence=colors_list, title=chart_title,
                        )

                    # Переименовываем серии в легенде по настройкам пользователя
                    if fig is not None and self.chart_type not in ("pie", "donut"):
                        for idx_tr, tr in enumerate(fig.data):
                            orig_n = getattr(tr, "name", "") or ""
                            if orig_n:
                                tr.name = self._get_col_display_name(orig_n, idx_tr)

                renamed_y = [self._get_col_display_name(c, i) for i, c in enumerate(y_fields)]
                x_axis_caption = (self.custom_x_title or self._get_col_display_name(self.x_col)) if self.show_axis_labels else ""
                y_axis_caption = (self.custom_y_title or (", ".join(renamed_y) if renamed_y else "Значения")) if self.show_axis_labels else ""

            actual_font_size = int(config_dict.get("font_size", getattr(self, "font_size", 12)) or 12)
            bg_hex = (self.bg_color or "#ffffff").lstrip("#")
            if len(bg_hex) == 3:
                bg_hex = "".join([c * 2 for c in bg_hex])
            try:
                r_val, g_val, b_val = int(bg_hex[0:2], 16), int(bg_hex[2:4], 16), int(bg_hex[4:6], 16)
                luminance = (0.299 * r_val + 0.587 * g_val + 0.114 * b_val) / 255
                is_dark = luminance < 0.5
            except Exception:
                is_dark = False

            text_color = "#f0f4f8" if is_dark else "#333333"
            grid_color = "#334155" if is_dark else "#e2e8f0"

            is_pie_layout = self.chart_type in ("pie", "donut")

            # Вычисляем максимальную длину подписи оси X, чтобы нижняя легенда никогда не наезжала на текст
            max_x_label_len = 0
            if fig is not None and not is_pie_layout:
                for tr_obj in fig.data:
                    x_seq = getattr(tr_obj, "x", None)
                    if x_seq is not None:
                        for xv in x_seq:
                            max_x_label_len = max(max_x_label_len, len(str(xv or "")))

            extra_bottom_px = max(0, (max_x_label_len - 12) * 3) if not is_pie_layout else 0
            raw_mh = int(config_dict.get("min_height", getattr(self, "min_height", 0)) or 0)
            base_default_h = 380 if is_pie_layout else (380 + (45 if self.legend_pos == "bottom" else 0) + extra_bottom_px // 2)
            target_chart_height = raw_mh if raw_mh >= 180 else base_default_h

            leg_bg = "rgba(30, 41, 59, 0.85)" if is_dark else "rgba(255, 255, 255, 0.88)"
            legend_config = dict(
                title_text="",
                visible=bool(self.show_legend),
                font=dict(family="Segoe UI, sans-serif", size=actual_font_size, color=text_color),
                bgcolor=leg_bg,
                itemsizing="constant",
                x=1.02, y=1.0, xanchor="left", yanchor="top",
            )
            if self.legend_pos == "top":
                legend_config.update(dict(orientation="h", yanchor="bottom", y=1.14, xanchor="center", x=0.5))
            elif self.legend_pos == "bottom":
                if is_pie_layout:
                    legend_config.update(dict(orientation="h", yanchor="top", y=-0.12, xanchor="center", x=0.5))
                else:
                    # Автоматически опускаем легенду ниже самых длинных наклонных подписей оси X
                    plot_h_est = max(180.0, float(target_chart_height - 130))
                    label_drop_px = 42.0 + max_x_label_len * 2.35 + (20.0 if x_axis_caption else 0.0)
                    y_bottom_pos = -min(0.68, max(0.30, label_drop_px / plot_h_est))
                    legend_config.update(dict(orientation="h", yanchor="top", y=round(y_bottom_pos, 3), xanchor="center", x=0.5))

            top_m = 88 if (self.title and self.show_title) else 58
            if self.legend_pos == "top":
                top_m += 26
            bot_m = 65 + extra_bottom_px + (48 if self.legend_pos == "bottom" else 0)

            chart_margins = (
                dict(l=20, r=20, t=40 if (self.title and self.show_title) else 12, b=45 if self.legend_pos == "bottom" else 16)
                if is_pie_layout
                else dict(l=50, r=55, t=top_m, b=bot_m)
            )

            if fig is not None:
                fig.update_layout(
                    height=target_chart_height,
                    plot_bgcolor=self.bg_color,
                    paper_bgcolor=self.bg_color,
                    font=dict(family="Segoe UI, sans-serif", size=actual_font_size, color=text_color),
                    margin=chart_margins,
                    title=dict(font=dict(size=actual_font_size + 3, color=text_color, family="Segoe UI, sans-serif")),
                    xaxis=dict(
                        title=dict(text=x_axis_caption, font=dict(size=actual_font_size + 2, color=text_color)),
                        tickfont=dict(size=actual_font_size, color=text_color),
                        showgrid=bool(self.show_grid),
                        gridcolor=grid_color,
                        tickangle=-25,
                        automargin=True,
                    ),
                    yaxis=dict(
                        title=dict(text=y_axis_caption, font=dict(size=actual_font_size + 2, color=text_color)),
                        tickfont=dict(size=actual_font_size, color=text_color),
                        showgrid=bool(self.show_grid),
                        gridcolor=grid_color,
                        zeroline=bool(getattr(self, "combo_show_zero_line", True)),
                        zerolinecolor="#94a3b8",
                        zerolinewidth=1.5,
                        automargin=True,
                    ),
                    legend=legend_config,
                    autosize=True,
                )
                if self.chart_type == "combo" and any(getattr(tr, "yaxis", "y") == "y2" for tr in fig.data):
                    y2_cap = str(getattr(self, "combo_y2_title", "") or "").strip()
                    if not y2_cap:
                        y2_names = [
                            str(s.get("name") or s.get("col") or "")
                            for s in (self.combo_series or [])
                            if s.get("visible", True) and s.get("y_axis") == "y2"
                        ]
                        y2_cap = " / ".join(y2_names[:2]) or "Отклонение (Факт − Норматив)"

                    if getattr(self, "_combo_swap_y_layers", False):
                        # Столбцы на правой шкале (в фоне), Линия тренда на левой шкале (поверх столбцов)
                        fig.update_layout(
                            yaxis=dict(
                                title=dict(text=y2_cap if self.show_axis_labels else "", font=dict(size=actual_font_size + 1, color=text_color)),
                                tickfont=dict(size=actual_font_size, color=text_color),
                                side="right",
                                showgrid=bool(self.show_grid),
                                gridcolor=grid_color,
                                zeroline=bool(getattr(self, "combo_show_zero_line", True)),
                                zerolinecolor="#94a3b8",
                                zerolinewidth=1.5,
                                automargin=True,
                            ),
                            yaxis2=dict(
                                title=dict(text=y_axis_caption if self.show_axis_labels else "", font=dict(size=actual_font_size + 1, color=text_color)),
                                tickfont=dict(size=actual_font_size, color=text_color),
                                overlaying="y",
                                side="left",
                                showgrid=False,
                                zeroline=False,
                                automargin=True,
                            ),
                        )
                    else:
                        fig.update_layout(
                            yaxis2=dict(
                                title=dict(text=y2_cap if self.show_axis_labels else "", font=dict(size=actual_font_size + 1, color=text_color)),
                                tickfont=dict(size=actual_font_size, color=text_color),
                                overlaying="y",
                                side="right",
                                showgrid=False,
                                zeroline=False,
                                automargin=True,
                            )
                        )

            if fig is None:
                fig = go.Figure()
                fig.update_layout(title="Нет данных для отображения")

            chart_div = pio.to_html(
                fig,
                include_plotlyjs=False,
                full_html=False,
                div_id=plot_div_id,
                config={"responsive": True},
            )

        except Exception as e:
            import traceback
            traceback.print_exc()
            chart_div = f"<p style='color:red; padding:16px;'>Ошибка построения графика: {e}</p>"

        slicer_json_script = ""
        matrix_controls_html = ""
        if row_slicer_payload:
            safe_json = json.dumps(row_slicer_payload, ensure_ascii=False)
            slicer_json_script = (
                f'<script type="application/json" id="{plot_div_id}-rowmap">{safe_json}</script>'
            )
            if isinstance(row_slicer_payload, dict) and row_slicer_payload.get("__is_matrix__"):
                all_grp = row_slicer_payload["groups"]["ALL"]
                init_header = all_grp["months"]["ALL_MONTHS"]["header"]
                ord_months = row_slicer_payload.get("ordered_months", ["ALL_MONTHS"])

                btns_html = ""
                if len(ord_months) > 0:
                    btn_items = []
                    for idx_m, m_key in enumerate(ord_months):
                        b_raw_label = all_grp["badges"].get(m_key, "Весь период")
                        b_label = _escape(b_raw_label)
                        is_act = (idx_m == 0)
                        bg_c = "#87C800" if is_act else "#f8fafc"
                        txt_c = "#ffffff" if is_act else "#334155"
                        fw_c = "700" if is_act else "500"
                        btn_fs = max(12, actual_font_size - 1)
                        btn_items.append(
                            f'<button type="button" class="ea-pie-month-btn" data-month="{_escape(m_key)}" '
                            f'onclick="window.selectPieMonth(\'{plot_div_id}\', \'{_escape(m_key)}\')" '
                            f'style="padding:6px 12px; border:1px solid #87C800; border-radius:6px; '
                            f'background:{bg_c}; color:{txt_c}; font-weight:{fw_c}; font-size:{btn_fs}px; '
                            f'cursor:pointer; transition:0.15s;">{b_label}</button>'
                        )
                    btns_html = (
                        f'<div id="{plot_div_id}-mbar" style="display:flex; flex-wrap:wrap; gap:6px; '
                        f'justify-content:center; margin-bottom:10px;">{"".join(btn_items)}</div>'
                    )

                hdr_fs = max(13, actual_font_size)
                drill_bar_html = ""
                if row_slicer_payload.get("__is_combo_drill__"):
                    l1_t = _escape(str(row_slicer_payload.get("lvl1_title", "Группа")))
                    init_s = _escape(str(row_slicer_payload.get("sort_lvl1", "value_desc")))
                    init_top = int(row_slicer_payload.get("top_n", 12) or 0)
                    drill_bar_html = f"""
                    <div id="{plot_div_id}-drillbar" style="display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:8px; margin-bottom:8px; padding:6px 40px 6px 12px; background:#f1f5f9; border-radius:6px; border:1px solid #cbd5e1;">
                        <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
                            <button type="button" id="{plot_div_id}-back-btn"
                                    onclick="window.stepBackComboDrill('{plot_div_id}')"
                                    style="display:none; padding:4px 10px; border:1px solid #003F0B; border-radius:5px; background:#003F0B; color:#fff; font-weight:700; font-size:11.5px; cursor:pointer;">
                                ⬅ На уровень выше
                            </button>
                            <span id="{plot_div_id}-crumb" style="font-size:12.5px; font-weight:700; color:#003F0B;">
                                📊 Уровень 1 ({l1_t}): Все категории
                            </span>
                        </div>
                        <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
                            <span style="font-size:11.5px; color:#475569; font-weight:600;">Топ групп:</span>
                            <select id="{plot_div_id}-topn-sel"
                                    onchange="window.changeComboTopN('{plot_div_id}', this.value)"
                                    style="padding:3px 6px; border:1px solid #94a3b8; border-radius:5px; font-size:11.5px; background:#fff; color:#1e293b; font-weight:600; cursor:pointer;">
                                <option value="5" {"selected" if init_top == 5 else ""}>Топ 5</option>
                                <option value="10" {"selected" if init_top == 10 else ""}>Топ 10</option>
                                <option value="12" {"selected" if init_top == 12 else ""}>Топ 12</option>
                                <option value="15" {"selected" if init_top == 15 else ""}>Топ 15</option>
                                <option value="20" {"selected" if init_top == 20 else ""}>Топ 20</option>
                                <option value="30" {"selected" if init_top == 30 else ""}>Топ 30</option>
                                <option value="50" {"selected" if init_top == 50 else ""}>Топ 50</option>
                                <option value="0" {"selected" if init_top == 0 else ""}>Все без лимита</option>
                            </select>
                            <span style="font-size:11.5px; color:#475569; font-weight:600;">Сортировка:</span>
                            <select id="{plot_div_id}-sort-sel"
                                    onchange="window.changeComboLevelSort('{plot_div_id}', this.value)"
                                    style="padding:3px 8px; border:1px solid #94a3b8; border-radius:5px; font-size:11.5px; background:#fff; color:#1e293b; font-weight:600; cursor:pointer;">
                                <option value="value_desc" {"selected" if init_s == "value_desc" else ""}>⬇ От большего к меньшему</option>
                                <option value="value_asc" {"selected" if init_s == "value_asc" else ""}>⬆ От меньшего к большему</option>
                                <option value="abs_desc" {"selected" if init_s == "abs_desc" else ""}>|Δ| По величине отклонения</option>
                                <option value="label_asc" {"selected" if init_s == "label_asc" else ""}>А→Я По алфавиту</option>
                                <option value="label_desc" {"selected" if init_s == "label_desc" else ""}>Я→А Обратный алфавит</option>
                                <option value="none" {"selected" if init_s == "none" else ""}>Без сортировки</option>
                            </select>
                        </div>
                    </div>
                    """

                matrix_controls_html = f"""
                {btns_html}
                {drill_bar_html}
                <div id="{plot_div_id}-hdr" style="text-align:center; font-size:{hdr_fs}px; color:#334155;
                     padding:6px 12px; margin-bottom:4px; background:#f8fafc; border-radius:6px;
                     border:1px solid #e2e8f0;">
                    {init_header}
                </div>
                <script>
                if (typeof window.syncMatrixPie === 'undefined') {{
                    window._sortAndSliceComboTraces = function(traces, sortMode, sortSeriesIdx, topN) {{
                        if (!traces || !traces.length) return traces;
                        var baseIdx = Math.min(Math.max(0, sortSeriesIdx || 0), traces.length - 1);
                        var xArr = traces[0].x;
                        if (!xArr || !Array.isArray(xArr) || xArr.length === 0) return traces;
                        var yBase = traces[baseIdx].y || [];
                        var idxs = xArr.map(function(_, i) {{ return i; }});

                        if (sortMode === 'value_desc') {{
                            idxs.sort(function(a, b) {{ return (Number(yBase[b]) || 0) - (Number(yBase[a]) || 0); }});
                        }} else if (sortMode === 'value_asc') {{
                            idxs.sort(function(a, b) {{ return (Number(yBase[a]) || 0) - (Number(yBase[b]) || 0); }});
                        }} else if (sortMode === 'abs_desc') {{
                            idxs.sort(function(a, b) {{ return Math.abs(Number(yBase[b]) || 0) - Math.abs(Number(yBase[a]) || 0); }});
                        }} else if (sortMode === 'label_asc') {{
                            idxs.sort(function(a, b) {{ return String(xArr[a]).localeCompare(String(xArr[b]), 'ru'); }});
                        }} else if (sortMode === 'label_desc') {{
                            idxs.sort(function(a, b) {{ return String(xArr[b]).localeCompare(String(xArr[a]), 'ru'); }});
                        }}

                        var limit = Number(topN || 0);
                        if (limit > 0 && idxs.length > limit) {{
                            idxs = idxs.slice(0, limit);
                        }}

                        return traces.map(function(tr) {{
                            var nt = JSON.parse(JSON.stringify(tr));
                            if (Array.isArray(nt.x)) nt.x = idxs.map(function(i) {{ return tr.x[i]; }});
                            if (Array.isArray(nt.y)) nt.y = idxs.map(function(i) {{ return tr.y[i]; }});
                            if (Array.isArray(nt.text)) nt.text = idxs.map(function(i) {{ return tr.text[i]; }});
                            if (nt.marker && Array.isArray(nt.marker.color)) {{
                                nt.marker.color = idxs.map(function(i) {{ return tr.marker.color[i]; }});
                            }}
                            return nt;
                        }});
                    }};

                    window.syncMatrixPie = function(plotDiv) {{
                        if (!plotDiv) return;
                        var mapEl = document.getElementById(plotDiv.id + '-rowmap');
                        if (!mapEl) return;
                        var rowMap = JSON.parse(mapEl.textContent);
                        if (!rowMap || !rowMap.__is_matrix__) return;

                        var curGroup = plotDiv._activeGroup || 'ALL';
                        var curSubGroup = plotDiv._activeSubGroup || '';
                        var curMonth = plotDiv._activeMonth || 'ALL_MONTHS';
                        var grpObj = null;
                        var activeLevel = 1;

                        if (rowMap.__is_combo_drill__ && curGroup !== 'ALL' && curSubGroup && rowMap.drill3) {{
                            var d3Key = curGroup + '|||' + curSubGroup;
                            grpObj = rowMap.drill3[d3Key];
                            if (!grpObj) {{
                                var normKey = d3Key.toLowerCase();
                                Object.keys(rowMap.drill3).forEach(function(k) {{
                                    if (k.toLowerCase() === normKey) grpObj = rowMap.drill3[k];
                                }});
                            }}
                            if (grpObj) activeLevel = 3;
                        }}

                        if (!grpObj) {{
                            grpObj = rowMap.groups[curGroup];
                            if (!grpObj && curGroup !== 'ALL') {{
                                var normG = String(curGroup).trim().toLowerCase();
                                Object.keys(rowMap.groups).forEach(function(k) {{
                                    if (String(k).trim().toLowerCase() === normG) {{
                                        grpObj = rowMap.groups[k];
                                    }}
                                }});
                            }}
                            if (!grpObj) {{
                                grpObj = rowMap.groups['ALL'];
                                activeLevel = 1;
                            }} else {{
                                activeLevel = (curGroup === 'ALL') ? 1 : 2;
                            }}
                        }}
                        if (!grpObj) return;
                        var prevLevel = plotDiv._activeLevel || 1;
                        var animDir = (activeLevel > prevLevel) ? 'drill-in' : ((activeLevel < prevLevel) ? 'drill-out' : 'auto');
                        plotDiv._activeLevel = activeLevel;

                        if (rowMap.__is_combo_drill__) {{
                            var backBtn = document.getElementById(plotDiv.id + '-back-btn');
                            var crumbEl = document.getElementById(plotDiv.id + '-crumb');
                            var sortSel = document.getElementById(plotDiv.id + '-sort-sel');
                            var topnSel = document.getElementById(plotDiv.id + '-topn-sel');
                            if (backBtn) backBtn.style.display = (activeLevel > 1) ? 'inline-block' : 'none';
                            if (crumbEl) {{
                                if (activeLevel === 1) {{
                                    crumbEl.innerHTML = '📊 Уровень 1 (' + (rowMap.lvl1_title || 'Группа') + '): Все категории';
                                }} else if (activeLevel === 2) {{
                                    crumbEl.innerHTML = '📊 ' + curGroup + ' ➔ 📂 Уровень 2 (' + (rowMap.lvl2_title || 'Подкатегория') + ')';
                                }} else {{
                                    crumbEl.innerHTML = '📊 ' + curGroup + ' ➔ 📂 ' + curSubGroup + ' ➔ 🏷 Уровень 3 (' + (rowMap.lvl3_title || 'Объект / ID') + ')';
                                }}
                            }}
                            plotDiv._levelSortOverrides = plotDiv._levelSortOverrides || {{
                                1: rowMap.sort_lvl1 || 'value_desc',
                                2: rowMap.sort_lvl2 || 'value_desc',
                                3: rowMap.sort_lvl3 || 'value_desc'
                            }};
                            if (plotDiv._activeTopN === undefined) {{
                                plotDiv._activeTopN = (rowMap.top_n !== undefined) ? rowMap.top_n : 12;
                            }}
                            if (sortSel) sortSel.value = plotDiv._levelSortOverrides[activeLevel] || 'value_desc';
                            if (topnSel) topnSel.value = String(plotDiv._activeTopN);
                        }}

                        var mbar = document.getElementById(plotDiv.id + '-mbar');
                        if (mbar && grpObj.badges) {{
                            var btns = mbar.querySelectorAll('.ea-pie-month-btn');
                            btns.forEach(function(b) {{
                                var mk = b.getAttribute('data-month');
                                if (grpObj.badges[mk]) {{
                                    b.textContent = grpObj.badges[mk];
                                }} else if (mk === 'ALL_MONTHS') {{
                                    b.textContent = 'Весь период';
                                }} else {{
                                    b.textContent = mk;
                                }}
                                if (mk === curMonth) {{
                                    b.style.background = '#87C800';
                                    b.style.color = '#ffffff';
                                    b.style.fontWeight = '700';
                                }} else {{
                                    b.style.background = '#f8fafc';
                                    b.style.color = '#334155';
                                    b.style.fontWeight = '500';
                                }}
                            }});
                        }}

                        var mEntry = grpObj.months[curMonth] || grpObj.months['ALL_MONTHS'];
                        if (!mEntry) return;

                        var hdrEl = document.getElementById(plotDiv.id + '-hdr');
                        if (hdrEl && mEntry.header) {{
                            if (typeof window._eaUpdateHeaderAnimated === 'function') {{
                                window._eaUpdateHeaderAnimated(hdrEl, mEntry.header);
                            }} else {{
                                hdrEl.innerHTML = mEntry.header;
                            }}
                        }}
                        var clonedTraces = JSON.parse(JSON.stringify(mEntry.traces));
                        if (rowMap.__is_combo_drill__ && plotDiv._levelSortOverrides) {{
                            var activeSort = plotDiv._levelSortOverrides[activeLevel];
                            var activeTop = (plotDiv._activeTopN !== undefined) ? plotDiv._activeTopN : (rowMap.top_n || 0);
                            clonedTraces = window._sortAndSliceComboTraces(clonedTraces, activeSort, rowMap.sort_series_idx || 0, activeTop);
                        }}

                        if (typeof window._eaAnimatedPlotlyReact === 'function') {{
                            window._eaAnimatedPlotlyReact(plotDiv, clonedTraces, animDir);
                        }} else {{
                            Plotly.react(plotDiv, clonedTraces, plotDiv.layout);
                        }}
                    }};

                    window.selectPieMonth = function(plotId, monthKey) {{
                        var plotDiv = document.getElementById(plotId);
                        if (!plotDiv) return;
                        plotDiv._activeMonth = monthKey;
                        window.syncMatrixPie(plotDiv);
                        if (typeof window.syncDynamicParagraphs === 'function') {{
                            window.syncDynamicParagraphs(plotDiv._activeGroup || 'ALL', monthKey, plotId);
                        }}
                    }};

                    window.stepBackComboDrill = function(plotId) {{
                        var plotDiv = document.getElementById(plotId);
                        if (!plotDiv) return;
                        if (plotDiv._activeLevel === 3) {{
                            plotDiv._activeSubGroup = '';
                        }} else {{
                            plotDiv._activeGroup = 'ALL';
                            plotDiv._activeSubGroup = '';
                        }}
                        window.syncMatrixPie(plotDiv);
                    }};

                    window.changeComboLevelSort = function(plotId, newSortMode) {{
                        var plotDiv = document.getElementById(plotId);
                        if (!plotDiv) return;
                        var lvl = plotDiv._activeLevel || 1;
                        plotDiv._levelSortOverrides = plotDiv._levelSortOverrides || {{}};
                        plotDiv._levelSortOverrides[lvl] = newSortMode;
                        window.syncMatrixPie(plotDiv);
                    }};

                    window.changeComboTopN = function(plotId, newTopVal) {{
                        var plotDiv = document.getElementById(plotId);
                        if (!plotDiv) return;
                        plotDiv._activeTopN = Number(newTopVal || 0);
                        window.syncMatrixPie(plotDiv);
                    }};
                }}

                setTimeout(function() {{
                    var plotDiv = document.getElementById('{plot_div_id}');
                    var mapEl = document.getElementById('{plot_div_id}-rowmap');
                    if (!plotDiv || !mapEl || plotDiv._hasComboDrillHook) return;
                    try {{
                        var rowMap = JSON.parse(mapEl.textContent);
                        if (!rowMap || !rowMap.__is_combo_drill__) return;
                        plotDiv._hasComboDrillHook = true;
                        plotDiv._activeLevel = 1;
                        if (typeof plotDiv.on === 'function') {{
                            plotDiv.on('plotly_click', function(evData) {{
                                if (!evData || !evData.points || !evData.points.length) return;
                                var clickedX = String(evData.points[0].x || '').trim();
                                if (!clickedX) return;
                                var curLvl = plotDiv._activeLevel || 1;
                                if (curLvl === 1 && rowMap.has_lvl2 && rowMap.groups[clickedX]) {{
                                    plotDiv._activeGroup = clickedX;
                                    plotDiv._activeSubGroup = '';
                                    window.syncMatrixPie(plotDiv);
                                }} else if (curLvl === 2 && rowMap.has_lvl3) {{
                                    var g1 = plotDiv._activeGroup || '';
                                    var candKey = g1 + '|||' + clickedX;
                                    if (rowMap.drill3 && rowMap.drill3[candKey]) {{
                                        plotDiv._activeSubGroup = clickedX;
                                        window.syncMatrixPie(plotDiv);
                                    }}
                                }} else if (curLvl === 3 && typeof window.filterEaDataTable === 'function') {{
                                    window.filterEaDataTable('__ALL__', clickedX, true);
                                }}
                            }});
                        }}
                    }} catch (e) {{}}
                }}, 250);
                </script>
                """

        card_caption = _escape(str(self.title or "График данных").strip() or "График данных")
        a_style = _escape(str(getattr(self, "anim_style", "auto") or "auto"))
        a_speed = int(getattr(self, "anim_speed", 480) or 480)
        inner = f"""
        {_CHART_ANIM_ASSETS_HTML}
        <div class="block" style="width:100%; min-width:0; max-width:100%;">
            <div class="block-card ea-chart-card" id="{plot_div_id}-card"
                 data-anim-style="{a_style}" data-anim-speed="{a_speed}"
                 style="width:100%; padding: 16px; background: {self.bg_color}; border-radius: 8px; min-width:0; max-width:100%; box-sizing: border-box; --ea-anim-dur:{a_speed}ms;">
                <div class="ea-chart-topbar"
                     onclick="if (this.parentElement.classList.contains('ea-collapsed')) window.toggleEaChartCard('{plot_div_id}', event)">
                    <span class="ea-chart-collapsed-title">📊 {card_caption}<span class="ea-chart-collapsed-hint">(нажмите, чтобы развернуть)</span></span>
                    <button type="button" class="ea-chart-toggle-btn" title="Свернуть график"
                            onclick="window.toggleEaChartCard('{plot_div_id}', event)">
                        <span class="ea-toggle-icon">▾</span>
                    </button>
                </div>
                <div class="ea-chart-collapsible" id="{plot_div_id}-body">
                    <div class="ea-chart-collapsible-inner">
                        {matrix_controls_html}
                        {chart_div}
                    </div>
                </div>
                {slicer_json_script}
            </div>
        </div>
        """
        final_html = self.wrap_layout(inner)
        if "render_sig" in locals() and "DataMemoryCache" in globals():
            DataMemoryCache._render_html_cache[self.id] = (render_sig, final_html)
        return final_html

    def _render_dut_pct_drill_pie(
        self,
        work_df: pd.DataFrame,
        config_dict: dict,
        plot_div_id: str,
        colors_list: list[str],
        actual_font_size: int,
        chart_title: str,
    ) -> str:
        """Интерактивная круговая диаграмма с живыми фильтрами ДУТ + % отклонения и 3-уровневым погружением."""
        cols_all = [str(c) for c in work_df.columns]
        num_cands = [str(c) for c in work_df.select_dtypes(include="number").columns]
        str_cands = [c for c in cols_all if c not in num_cands]

        def _parse_pct(s: pd.Series) -> pd.Series:
            s = _ensure_series(s)
            if pd.api.types.is_numeric_dtype(s):
                return s.fillna(0.0).astype(float)
            cleaned = (
                s.astype(str)
                .str.replace("%", "", regex=False)
                .str.replace("\u00a0", "", regex=False)
                .str.replace(" ", "", regex=False)
                .str.replace(",", ".", regex=False)
            )
            return pd.to_numeric(cleaned, errors="coerce").fillna(0.0).astype(float)

        # 1. Определяем колонки (выбранные в Инспекторе или автопоиском)
        dut_col = self.dut_col if (self.dut_col and self.dut_col in work_df.columns) else ""
        if not dut_col:
            for c in cols_all:
                if "дут" in c.lower():
                    dut_col = c
                    break

        pct_col = self.pct_col if (self.pct_col and self.pct_col in work_df.columns) else ""
        if not pct_col and not (self.fact_col and self.norm_col):
            for c in cols_all:
                cl = c.lower()
                if "%" in cl or "процент" in cl or ("перерасход" in cl and ("%" in cl or "проц" in cl)):
                    pct_col = c
                    break

        fact_col = self.fact_col if (self.fact_col and self.fact_col in work_df.columns) else ""
        norm_col = self.norm_col if (self.norm_col and self.norm_col in work_df.columns) else ""
        has_fact_norm = bool(fact_col and norm_col)

        type_col = self.parent_group_col if (self.parent_group_col and self.parent_group_col in work_df.columns) else ""
        if not type_col:
            for c in str_cands:
                if c != dut_col and any(w in c.lower() for w in ("тип", "групп", "категор")):
                    type_col = c
                    break
            if not type_col:
                type_col = self.x_col if (self.x_col and self.x_col in work_df.columns and self.x_col != dut_col) else (str_cands[0] if str_cands else cols_all[0])

        model_col = self.model_col if (self.model_col and self.model_col in work_df.columns and self.model_col != type_col) else ""
        if not model_col:
            for c in str_cands:
                if c not in (dut_col, type_col) and any(w in c.lower() for w in ("модел", "марк", "авто")):
                    model_col = c
                    break

        plate_col = self.plate_col if (self.plate_col and self.plate_col in work_df.columns and self.plate_col not in (type_col, model_col)) else ""
        if not plate_col:
            for c in cols_all:
                if c not in (dut_col, type_col, model_col, pct_col, fact_col, norm_col) and any(w in c.lower() for w in ("гос", "номер", "грз", "вин")):
                    plate_col = c
                    break

        date_col = self.date_col if (self.date_col and self.date_col in work_df.columns) else ""

        if not dut_col and not pct_col and not has_fact_norm:
            return self.wrap_layout(
                self._render_empty("Выберите в Инспекторе колонку «Оснащён ДУТ?» и «Процент отклонения» (или Факт/Норматив)")
            )

        # 2. Подготавливаем компактный датафрейм для мгновенного пересчёта в браузере
        df_tmp = pd.DataFrame(index=work_df.index)
        df_tmp["_dut"] = (
            DataMemoryCache.get_str_series(work_df, dut_col).replace("", "Не указано")
            if dut_col else "Все"
        )
        df_tmp["_type"] = (
            DataMemoryCache.get_str_series(work_df, type_col).replace("", "Не указано")
            if type_col else "Все типы"
        )
        df_tmp["_model"] = (
            DataMemoryCache.get_str_series(work_df, model_col).replace("", "Не указано")
            if model_col else ""
        )
        df_tmp["_plate"] = (
            DataMemoryCache.get_str_series(work_df, plate_col).replace("", "Не указано")
            if plate_col else ""
        )

        ordered_months: list[str] = []
        if date_col:
            m_names, m_nums = _extract_month_info(work_df[date_col])
            df_tmp["_month"] = m_names
            df_tmp["_mnum"] = m_nums
            valid_m = df_tmp[df_tmp["_month"] != ""]
            if len(valid_m) > 0:
                df_tmp = valid_m.copy()
                ordered_months = (
                    df_tmp[["_mnum", "_month"]]
                    .drop_duplicates()
                    .sort_values(by=["_mnum", "_month"])["_month"]
                    .tolist()
                )
            else:
                df_tmp["_month"] = ""
        else:
            df_tmp["_month"] = ""

        df_tmp["_fact"] = _to_num_series(work_df.loc[df_tmp.index, fact_col]) if has_fact_norm else 0.0
        df_tmp["_norm"] = _to_num_series(work_df.loc[df_tmp.index, norm_col]) if has_fact_norm else 0.0

        use_pct_col = bool(pct_col)
        if use_pct_col:
            raw_pct_col = _ensure_series(work_df.loc[df_tmp.index, pct_col])
            pct_s = _parse_pct(raw_pct_col)
            nz = pct_s[pct_s.abs() > 1e-9]
            # Автоперевод Excel-процентов из долей (0.03 -> 3.0%)
            if len(nz) > 0 and pd.api.types.is_numeric_dtype(raw_pct_col):
                if has_fact_norm:
                    valid_n = df_tmp["_norm"].abs() > 1e-9
                    if valid_n.any():
                        calc_p = ((df_tmp.loc[valid_n, "_fact"] - df_tmp.loc[valid_n, "_norm"]) / df_tmp.loc[valid_n, "_norm"] * 100.0).abs()
                        if float(nz.abs().quantile(0.9)) <= 1.5 and float(calc_p.quantile(0.9)) > 2.0:
                            pct_s = pct_s * 100.0
                elif float(nz.abs().quantile(0.9)) <= 1.0 and float((nz.abs() < 1.0).mean()) >= 0.85:
                    pct_s = pct_s * 100.0
            df_tmp["_pct"] = pct_s
        else:
            df_tmp["_pct"] = 0.0

        df_tmp["_cnt"] = 1

        # Группируем для компактности JSON: если есть Гос. номер — по каждой машине и месяцу; иначе с округлением % до 0.1
        if plate_col:
            grp_keys = ["_dut", "_type", "_model", "_plate", "_month"]
            agg_df = df_tmp.groupby(grp_keys, as_index=False, sort=False).agg(
                _fact=("_fact", "sum"),
                _norm=("_norm", "sum"),
                _pct_sum=("_pct", "sum"),
                _cnt=("_cnt", "sum"),
            )
        else:
            df_tmp["_pct_r"] = df_tmp["_pct"].round(1)
            grp_keys = ["_dut", "_type", "_model", "_plate", "_month", "_pct_r"]
            agg_df = df_tmp.groupby(grp_keys, as_index=False, sort=False).agg(
                _fact=("_fact", "sum"),
                _norm=("_norm", "sum"),
                _pct_sum=("_pct", "sum"),
                _cnt=("_cnt", "sum"),
            )

        # Порядок значений ДУТ: сначала «Да», потом «Нет», затем остальные
        raw_duts = [str(v) for v in agg_df["_dut"].unique().tolist() if str(v)]
        def _dut_sort_key(v: str):
            vl = v.strip().lower()
            if vl in ("да", "yes", "1", "true", "есть", "оборудован"):
                return (0, v)
            if vl in ("нет", "no", "0", "false", "не оборудован"):
                return (1, v)
            return (2, v.lower())
        ordered_duts = sorted(raw_duts, key=_dut_sort_key)

        dict_dut = ordered_duts
        dict_type = sorted(agg_df["_type"].unique().tolist())
        dict_model = sorted(agg_df["_model"].unique().tolist())
        dict_plate = sorted(agg_df["_plate"].unique().tolist())
        dict_month = ordered_months if ordered_months else [""]

        idx_dut = {v: i for i, v in enumerate(dict_dut)}
        idx_type = {v: i for i, v in enumerate(dict_type)}
        idx_model = {v: i for i, v in enumerate(dict_model)}
        idx_plate = {v: i for i, v in enumerate(dict_plate)}
        idx_month = {v: i for i, v in enumerate(dict_month)}

        compact_rows = [
            [
                idx_dut.get(v_dut, 0),
                idx_type.get(v_type, 0),
                idx_model.get(v_model, 0),
                idx_plate.get(v_plate, 0),
                idx_month.get(v_month, 0),
                round(float(v_fact), 2),
                round(float(v_norm), 2),
                round(float(v_pct_sum), 3),
                int(v_cnt),
            ]
            for v_dut, v_type, v_model, v_plate, v_month, v_fact, v_norm, v_pct_sum, v_cnt in agg_df[
                ["_dut", "_type", "_model", "_plate", "_month", "_fact", "_norm", "_pct_sum", "_cnt"]
            ].itertuples(index=False, name=None)
        ]

        display_mode = str(getattr(self, "pie_display_mode", "dut_two_pies") or "dut_two_pies")
        init_op = str(getattr(self, "dut_pct_op", "gt") or "gt")
        try:
            init_val = float(getattr(self, "dut_pct_val", 3.0) if getattr(self, "dut_pct_val", None) is not None else 3.0)
        except Exception:
            init_val = 3.0
        init_cnt_mode = str(getattr(self, "dut_count_mode", "unique_ts") or "unique_ts")
        if not plate_col:
            init_cnt_mode = "rows"

        raw_mh = int(config_dict.get("min_height", getattr(self, "min_height", 0)) or 0)
        chart_h = raw_mh if raw_mh >= 280 else 390

        payload = {
            "mode": display_mode,
            "hole": 0.46 if self.chart_type == "donut" else 0.0,
            "colors": colors_list,
            "bg_color": self.bg_color or "#ffffff",
            "font_size": actual_font_size,
            "height": chart_h,
            "show_legend": bool(self.show_legend),
            "show_values": bool(self.show_values),
            "top_n": int(self.top_n or 15),
            "dut_values": ordered_duts,
            "months": ordered_months,
            "has_plate": bool(plate_col),
            "has_model": bool(model_col),
            "has_fn": has_fact_norm,
            "use_pct_col": use_pct_col,
            "labels": {
                "dut": " ".join(str(dut_col or "Признак").split()),
                "pct": " ".join(str(pct_col or "Показатель, %").split()),
                "type": " ".join(str(type_col or "Группа").split()),
                "model": " ".join(str(model_col or "Подкатегория").split()),
                "plate": " ".join(str(plate_col or "Объект / ID").split()),
            },
            "init": {
                "dut": "ALL",
                "op": init_op,
                "val": init_val,
                "count_mode": init_cnt_mode,
            },
            "dict_dut": dict_dut,
            "dict_type": dict_type,
            "dict_model": dict_model,
            "dict_plate": dict_plate,
            "dict_month": dict_month,
            "rows": compact_rows,
        }

        uid = plot_div_id
        payload_json = json.dumps(payload, ensure_ascii=False)

        dut_btns_html = [
            f'<button type="button" class="ea-dut-btn" data-dut="ALL" '
            f'style="padding:5px 12px; border:1px solid #87C800; border-radius:6px; background:#87C800; color:#fff; font-weight:700; font-size:12px; cursor:pointer;">Все</button>'
        ]
        for dv in ordered_duts:
            safe_dv = _escape(dv)
            dut_btns_html.append(
                f'<button type="button" class="ea-dut-btn" data-dut="{safe_dv}" '
                f'style="padding:5px 12px; border:1px solid #87C800; border-radius:6px; background:#f8fafc; color:#334155; font-weight:600; font-size:12px; cursor:pointer;">{safe_dv}</button>'
            )

        month_bar_html = ""
        if len(ordered_months) > 1:
            m_btns = [
                '<button type="button" class="ea-pie-month-btn ea-dut-mbtn" data-month="ALL" '
                'style="padding:5px 11px; border:1px solid #87C800; border-radius:6px; background:#87C800; color:#fff; font-weight:700; font-size:12px; cursor:pointer;">Весь период</button>'
            ]
            for mn in ordered_months:
                safe_mn = _escape(mn)
                m_btns.append(
                    f'<button type="button" class="ea-pie-month-btn ea-dut-mbtn" data-month="{safe_mn}" '
                    f'style="padding:5px 11px; border:1px solid #87C800; border-radius:6px; background:#f8fafc; color:#334155; font-weight:500; font-size:12px; cursor:pointer;">{safe_mn}</button>'
                )
            month_bar_html = f'<div id="{uid}-mbar" style="display:flex; flex-wrap:wrap; gap:6px; justify-content:center; margin-bottom:10px;">{"".join(m_btns)}</div>'

        count_mode_html = ""
        if plate_col:
            sel_ts = "selected" if init_cnt_mode == "unique_ts" else ""
            sel_rw = "selected" if init_cnt_mode != "unique_ts" else ""
            count_mode_html = (
                f'<div style="display:flex; align-items:center; gap:6px;">'
                f'<span style="font-size:12px; color:#475569; font-weight:600;">Считать:</span>'
                f'<select id="{uid}-cnt-sel" style="padding:4px 8px; border:1px solid #cbd5e1; border-radius:6px; font-size:12px; background:#fff; color:#1e293b; font-weight:600; cursor:pointer;">'
                f'<option value="unique_ts" {sel_ts}>🏷 Уникальные объекты</option>'
                f'<option value="rows" {sel_rw}>📄 Все записи</option>'
                f'</select></div>'
            )

        title_html = (
            f'<div style="font-size:{actual_font_size + 3}px; font-weight:700; color:#003F0B; margin-bottom:10px; text-align:center;">{_escape(chart_title)}</div>'
            if chart_title else ""
        )

        if display_mode == "dut_two_pies":
            charts_area_html = f'''
            <div style="display:flex; flex-wrap:wrap; gap:16px; align-items:stretch; width:100%;">
                <div style="flex:1 1 360px; min-width:300px; border:1px solid #e2e8f0; border-radius:8px; padding:12px; background:#ffffff; box-sizing:border-box;">
                    <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px; margin-bottom:6px;">
                        <div id="{uid}-p1-title" style="font-size:13px; font-weight:700; color:#003F0B;">1. Сводка по признаку и порогу</div>
                        <label style="font-size:11.5px; color:#475569; cursor:pointer; display:flex; align-items:center; gap:4px;">
                            <input type="checkbox" id="{uid}-show-rest" checked style="cursor:pointer;" /> Показать остаток (в норме)
                        </label>
                    </div>
                    <div id="{uid}-p1-hdr" style="font-size:12px; color:#334155; background:#f8fafc; border:1px solid #e2e8f0; border-radius:6px; padding:6px 10px; margin-bottom:6px; text-align:center;"></div>
                    <div id="{uid}-pie1" style="width:100%; height:{chart_h}px;"></div>
                </div>
                <div style="flex:1.15 1 400px; min-width:300px; border:1px solid #e2e8f0; border-radius:8px; padding:12px; background:#ffffff; box-sizing:border-box;">
                    <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px; margin-bottom:6px;">
                        <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
                            <button type="button" id="{uid}-back-btn" style="display:none; padding:4px 10px; border:1px solid #003F0B; border-radius:5px; background:#003F0B; color:#fff; font-weight:700; font-size:11.5px; cursor:pointer;">⬅ На уровень выше</button>
                            <span id="{uid}-crumb" style="font-size:13px; font-weight:700; color:#003F0B;">Уровень 0: Признак и порог</span>
                        </div>
                        <button type="button" id="{uid}-reset-pin" style="display:none; padding:3px 8px; border:1px solid #fecdd3; border-radius:5px; background:#fff1f2; color:#e11d48; font-size:11px; font-weight:600; cursor:pointer;">✕ Сбросить выбор сектора</button>
                    </div>
                    <div id="{uid}-p2-hdr" style="font-size:12px; color:#334155; background:#f8fafc; border:1px solid #e2e8f0; border-radius:6px; padding:6px 10px; margin-bottom:6px; text-align:center;"></div>
                    <div id="{uid}-pie2" style="width:100%; height:{chart_h}px;"></div>
                </div>
            </div>
            '''
        else:
            charts_area_html = f'''
            <div style="border:1px solid #e2e8f0; border-radius:8px; padding:12px; background:#ffffff; box-sizing:border-box;">
                <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-bottom:6px;">
                    <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
                        <button type="button" id="{uid}-back-btn" style="display:none; padding:4px 10px; border:1px solid #003F0B; border-radius:5px; background:#003F0B; color:#fff; font-weight:700; font-size:11.5px; cursor:pointer;">⬅ На уровень выше</button>
                        <span id="{uid}-crumb" style="font-size:13px; font-weight:700; color:#003F0B;">Уровень 0: ДУТ и порог отклонения</span>
                    </div>
                    <label id="{uid}-rest-wrap" style="font-size:11.5px; color:#475569; cursor:pointer; display:flex; align-items:center; gap:4px;">
                        <input type="checkbox" id="{uid}-show-rest" checked style="cursor:pointer;" /> Показать остаток (в норме)
                    </label>
                </div>
                <div id="{uid}-p1-hdr" style="font-size:12.5px; color:#334155; background:#f8fafc; border:1px solid #e2e8f0; border-radius:6px; padding:6px 10px; margin-bottom:6px; text-align:center;"></div>
                <div id="{uid}-pie1" style="width:100%; height:{chart_h + 30}px;"></div>
            </div>
            '''

        js_code = r"""
        <script>
        (function() {
            var uid = "__UID__";
            var dataEl = document.getElementById(uid + "-dutdata");
            if (!dataEl) return;
            var cfg = JSON.parse(dataEl.textContent);

            var state = {
                dut: cfg.init.dut || "ALL",
                op: cfg.init.op || "gt",
                val: Number(cfg.init.val),
                month: "ALL",
                countMode: cfg.has_plate ? (cfg.init.count_mode || "unique_ts") : "rows",
                showRest: true,
                level: (cfg.mode === "dut_single_drill") ? 0 : 1,
                pinnedDut: null,
                pinnedMatched: true,
                selType: "",
                selModel: "",
                _ready: false
            };

            function esc(s) {
                return String(s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
            }

            function opText(op, val) {
                var vStr = Number(val).toFixed(1).replace(/\.0$/, "");
                if (op === "gt") return "> " + vStr + "%";
                if (op === "ge") return "≥ " + vStr + "%";
                if (op === "lt") return "< " + vStr + "%";
                if (op === "le") return "≤ " + vStr + "%";
                if (op === "abs_gt") return "|%| > " + vStr + "%";
                if (op === "abs_ge") return "|%| ≥ " + vStr + "%";
                return "Все значения";
            }

            function checkPct(pct, op, val) {
                if (op === "all") return true;
                if (op === "gt") return pct > val;
                if (op === "ge") return pct >= val;
                if (op === "lt") return pct < val;
                if (op === "le") return pct <= val;
                if (op === "abs_gt") return Math.abs(pct) > val;
                if (op === "abs_ge") return Math.abs(pct) >= val;
                return true;
            }

            function buildEntities() {
                var targetMonthIdx = -1;
                if (state.month !== "ALL") {
                    targetMonthIdx = cfg.dict_month.indexOf(state.month);
                }
                var raw = cfg.rows || [];
                var out = [];

                if (state.countMode === "unique_ts" && cfg.has_plate) {
                    var map = {};
                    for (var i = 0; i < raw.length; i++) {
                        var r = raw[i];
                        if (targetMonthIdx >= 0 && r[4] !== targetMonthIdx) continue;
                        var key = r[0] + "|" + r[1] + "|" + r[2] + "|" + r[3];
                        var item = map[key];
                        if (!item) {
                            item = { di: r[0], ti: r[1], mi: r[2], pi: r[3], f: 0, n: 0, ps: 0, c: 0 };
                            map[key] = item;
                        }
                        item.f += r[5];
                        item.n += r[6];
                        item.ps += r[7];
                        item.c += r[8];
                    }
                    var keys = Object.keys(map);
                    for (var k = 0; k < keys.length; k++) {
                        var it = map[keys[k]];
                        var pct = cfg.use_pct_col
                            ? (it.c > 0 ? it.ps / it.c : 0)
                            : (Math.abs(it.n) > 1e-9 ? ((it.f - it.n) / it.n) * 100 : 0);
                        out.push({
                            dut: cfg.dict_dut[it.di] || "Не указано",
                            type: cfg.dict_type[it.ti] || "Не указано",
                            model: cfg.dict_model[it.mi] || "",
                            plate: cfg.dict_plate[it.pi] || "",
                            f: it.f, n: it.n, pct: pct, w: 1, rows: it.c,
                            matched: checkPct(pct, state.op, state.val)
                        });
                    }
                } else {
                    for (var j = 0; j < raw.length; j++) {
                        var rw = raw[j];
                        if (targetMonthIdx >= 0 && rw[4] !== targetMonthIdx) continue;
                        var pVal = cfg.use_pct_col
                            ? (rw[8] > 0 ? rw[7] / rw[8] : 0)
                            : (Math.abs(rw[6]) > 1e-9 ? ((rw[5] - rw[6]) / rw[6]) * 100 : 0);
                        out.push({
                            dut: cfg.dict_dut[rw[0]] || "Не указано",
                            type: cfg.dict_type[rw[1]] || "Не указано",
                            model: cfg.dict_model[rw[2]] || "",
                            plate: cfg.dict_plate[rw[3]] || "",
                            f: rw[5], n: rw[6], pct: pVal, w: rw[8], rows: rw[8],
                            matched: checkPct(pVal, state.op, state.val)
                        });
                    }
                }
                return out;
            }

            function makeBaseLayout(h) {
                return {
                    height: h,
                    margin: { l: 14, r: 14, t: 16, b: 16 },
                    paper_bgcolor: cfg.bg_color || "#ffffff",
                    plot_bgcolor: cfg.bg_color || "#ffffff",
                    font: { family: "Segoe UI, Arial, sans-serif", size: cfg.font_size || 12, color: "#333" },
                    showlegend: !!cfg.show_legend,
                    legend: { orientation: "v", x: 1.02, y: 1.0, xanchor: "left", yanchor: "top", font: { size: Math.max(10, (cfg.font_size || 12) - 1) } },
                    uniformtext: { minsize: 10, mode: "hide" }
                };
            }

            function renderSummaryPie(divId, hdrId, entities, isSingleMode) {
                var divEl = document.getElementById(divId);
                if (!divEl) return;
                var unitLbl = (state.countMode === "unique_ts" && cfg.has_plate) ? "об." : "зап.";
                var condLbl = opText(state.op, state.val);

                var scoped = entities.filter(function(e) {
                    return state.dut === "ALL" || e.dut === state.dut;
                });

                var totalAll = 0;
                var totalMatched = 0;
                var byDutMatch = {};
                var byDutRest = {};
                cfg.dut_values.forEach(function(d) { byDutMatch[d] = 0; byDutRest[d] = 0; });

                scoped.forEach(function(e) {
                    totalAll += e.w;
                    if (e.matched) {
                        totalMatched += e.w;
                        byDutMatch[e.dut] = (byDutMatch[e.dut] || 0) + e.w;
                    } else {
                        byDutRest[e.dut] = (byDutRest[e.dut] || 0) + e.w;
                    }
                });

                var labels = [], values = [], colors = [], metaList = [], hoverHints = [], texts = [];
                var matchPalette = ["#2b7fff", "#e11d48", "#87C800", "#ff9f1c", "#6f42c1"];
                var restPalette = ["#cbd5e1", "#e2e8f0", "#d1d5db", "#e5e7eb"];
                var drillHintText = "🖱 Кликните для разбивки на " + esc(cfg.labels.type);

                var activeDuts = (state.dut === "ALL") ? cfg.dut_values : [state.dut];

                if (state.op === "all") {
                    activeDuts.forEach(function(d, idx) {
                        var cnt = (byDutMatch[d] || 0) + (byDutRest[d] || 0);
                        if (cnt <= 0) return;
                        labels.push(cfg.labels.dut + ": " + d);
                        values.push(cnt);
                        colors.push(matchPalette[idx % matchPalette.length]);
                        metaList.push({ kind: "summary", dut: d, matched: true });
                        hoverHints.push(drillHintText);
                        texts.push(cnt + " " + unitLbl);
                    });
                } else {
                    activeDuts.forEach(function(d, idx) {
                        var mCnt = byDutMatch[d] || 0;
                        if (mCnt > 0) {
                            labels.push(d + " (" + condLbl + ")");
                            values.push(mCnt);
                            colors.push(matchPalette[idx % matchPalette.length]);
                            metaList.push({ kind: "summary", dut: d, matched: true });
                            hoverHints.push(drillHintText);
                            texts.push(mCnt + " " + unitLbl);
                        }
                    });
                    if (state.showRest) {
                        activeDuts.forEach(function(d, idx) {
                            var rCnt = byDutRest[d] || 0;
                            if (rCnt > 0) {
                                labels.push(d + " (не подходят)");
                                values.push(rCnt);
                                colors.push(restPalette[idx % restPalette.length]);
                                metaList.push({ kind: "summary", dut: d, matched: false });
                                hoverHints.push(drillHintText);
                                texts.push(rCnt + " " + unitLbl);
                            }
                        });
                    }
                }

                var hdrEl = document.getElementById(hdrId);
                if (hdrEl) {
                    var pctM = totalAll > 0 ? (totalMatched / totalAll * 100).toFixed(1) : "0.0";
                    var dutBreakdown = activeDuts.map(function(d) {
                        return "«" + esc(d) + "»: <b>" + (byDutMatch[d] || 0) + "</b>";
                    }).join(" | ");
                    var sumHdrHtml =
                        "Всего (" + esc(state.dut === "ALL" ? "Все" : state.dut) + "): <b>" + totalAll + " " + unitLbl + "</b>" +
                        " &nbsp;|&nbsp; Подходят (<b>" + esc(condLbl) + "</b>): <b style='color:#003F0B;'>" + totalMatched + " " + unitLbl + " (" + pctM + "%)</b>" +
                        (activeDuts.length > 1 ? " &nbsp;[" + dutBreakdown + "]" : "");
                    if (state._ready && typeof window._eaUpdateHeaderAnimated === "function") {
                        window._eaUpdateHeaderAnimated(hdrEl, sumHdrHtml);
                    } else {
                        hdrEl.innerHTML = sumHdrHtml;
                    }
                }

                divEl._dutActiveMeta = metaList;

                var trace = labels.length ? {
                    type: "pie",
                    labels: labels,
                    values: values,
                    customdata: hoverHints,
                    hole: cfg.hole,
                    marker: { colors: colors, line: { color: "#ffffff", width: 2 } },
                    textinfo: cfg.show_values ? "value+percent" : "none",
                    texttemplate: cfg.show_values ? "<b>%{value} " + unitLbl + "</b><br>(%{percent})" : "",
                    textposition: "inside",
                    insidetextorientation: "horizontal",
                    sort: false,
                    hovertemplate: "<b>%{label}</b><br>Количество: <b>%{value} " + unitLbl + "</b> (%{percent})<br><i style='color:#87C800;'>%{customdata}</i><extra></extra>"
                } : {
                    type: "pie",
                    labels: ["Нет данных по условию"],
                    values: [1],
                    hole: cfg.hole,
                    marker: { colors: ["#e2e8f0"] },
                    textinfo: "label",
                    hoverinfo: "skip",
                    showlegend: false
                };

                var h = isSingleMode ? (cfg.height + 30) : cfg.height;
                Plotly.react(divEl, [trace], makeBaseLayout(h), { responsive: true });
                if (state._ready && typeof window._eaPlayElAnim === "function") {
                    window._eaPlayElAnim(divEl, state._animDir || "fade");
                }
                bindPieClick(divEl);
            }

            function renderDetailPie(divId, hdrId, entities, isSingleMode) {
                var divEl = document.getElementById(divId);
                if (!divEl) return;
                var unitLbl = (state.countMode === "unique_ts" && cfg.has_plate) ? "ТС" : "зап.";
                var condLbl = opText(state.op, state.val);

                var effDut = state.pinnedDut !== null ? state.pinnedDut : state.dut;
                var effMatched = (state.op === "all") ? true : state.pinnedMatched;

                var subset = entities.filter(function(e) {
                    if (effDut !== "ALL" && e.dut !== effDut) return false;
                    if (state.op !== "all" && e.matched !== effMatched) return false;
                    if (state.level >= 2 && state.selType && e.type !== state.selType) return false;
                    if (state.level >= 3 && state.selModel && e.model !== state.selModel) return false;
                    return true;
                });

                var grpMap = {};
                var totalWeight = 0;
                subset.forEach(function(e) {
                    var k = (state.level === 1) ? e.type : ((state.level === 2) ? (e.model || "Не указано") : (e.plate || "Не указано"));
                    var g = grpMap[k];
                    if (!g) {
                        g = { name: k, w: 0, pctSumW: 0, f: 0, n: 0, rows: 0, duts: {} };
                        grpMap[k] = g;
                    }
                    g.w += e.w;
                    g.pctSumW += e.pct * e.w;
                    g.f += e.f;
                    g.n += e.n;
                    g.rows += e.rows;
                    g.duts[e.dut] = (g.duts[e.dut] || 0) + e.w;
                    totalWeight += e.w;
                });

                var list = Object.keys(grpMap).map(function(k) {
                    var g = grpMap[k];
                    g.avgPct = g.w > 0 ? (g.pctSumW / g.w) : 0;
                    return g;
                });

                if (state.level === 3 && state.countMode === "unique_ts" && cfg.has_plate) {
                    list.sort(function(a, b) { return Math.abs(b.avgPct) - Math.abs(a.avgPct); });
                } else {
                    list.sort(function(a, b) { return b.w - a.w; });
                }

                var topN = Number(cfg.top_n || 15);
                if (topN > 0 && list.length > topN) {
                    var head = list.slice(0, topN);
                    var tail = list.slice(topN);
                    var other = { name: "Прочие (" + tail.length + ")", w: 0, pctSumW: 0, f: 0, n: 0, rows: 0, isOther: true };
                    tail.forEach(function(t) {
                        other.w += t.w;
                        other.pctSumW += t.pctSumW;
                        other.f += t.f;
                        other.n += t.n;
                        other.rows += t.rows;
                    });
                    other.avgPct = other.w > 0 ? (other.pctSumW / other.w) : 0;
                    head.push(other);
                    list = head;
                }

                var labels = [], values = [], colors = [], metaList = [], hoverBlocks = [], texts = [];
                var isLevel3Unique = (state.level === 3 && state.countMode === "unique_ts" && cfg.has_plate);
                var nextHint = "";
                if (state.level === 1 && cfg.has_model) nextHint = "🖱 Кликните ➔ " + esc(cfg.labels.model);
                else if (state.level === 1 && cfg.has_plate) nextHint = "🖱 Кликните ➔ " + esc(cfg.labels.plate);
                else if (state.level === 2 && cfg.has_plate) nextHint = "🖱 Кликните ➔ " + esc(cfg.labels.plate);
                else if (state.level === 3) nextHint = "🖱 Кликните для фильтрации таблицы данных";

                list.forEach(function(g, idx) {
                    labels.push(g.name);
                    var valPlot = isLevel3Unique ? Math.max(0.01, Math.abs(g.avgPct)) : g.w;
                    values.push(Number(valPlot.toFixed(2)));
                    colors.push(g.isOther ? "#cbd5e1" : cfg.colors[idx % cfg.colors.length]);
                    var pctStr = (g.avgPct >= 0 ? "+" : "") + g.avgPct.toFixed(2) + "%";
                    var shareStr = totalWeight > 0 ? (g.w / totalWeight * 100).toFixed(1) + "%" : "0%";
                    var fnInfo = cfg.has_fn ? ("<br>Факт: <b>" + g.f.toFixed(1) + "</b> | Норма: <b>" + g.n.toFixed(1) + "</b>") : "";
                    var hintLine = (!g.isOther && nextHint) ? ("<br><i style='color:#87C800;'>" + nextHint + "</i>") : "";
                    metaList.push({
                        kind: "detail",
                        name: g.name,
                        isOther: !!g.isOther
                    });
                    hoverBlocks.push(
                        "Количество: <b>" + g.w + " " + unitLbl + "</b> (" + shareStr + ")<br>" +
                        esc(cfg.labels.pct) + ": <b>" + pctStr + "</b>" + fnInfo + hintLine
                    );
                    if (isLevel3Unique) {
                        texts.push("<b>" + pctStr + "</b>");
                    } else {
                        texts.push("<b>" + g.w + " " + unitLbl + "</b><br>(" + shareStr + ")");
                    }
                });

                // Обновляем хлебные крошки и шапку
                var crumbEl = document.getElementById(uid + "-crumb");
                var backBtn = document.getElementById(uid + "-back-btn");
                var resetPinBtn = document.getElementById(uid + "-reset-pin");
                var dutTag = (effDut === "ALL") ? "Все" : (cfg.labels.dut + ": " + effDut);
                var condTag = (state.op === "all") ? "Все" : (effMatched ? condLbl : ("не подходят под " + condLbl));

                if (backBtn) {
                    var minLvl = isSingleMode ? 0 : 1;
                    backBtn.style.display = (state.level > minLvl) ? "inline-block" : "none";
                }
                if (resetPinBtn) {
                    resetPinBtn.style.display = (state.pinnedDut !== null || !state.pinnedMatched) ? "inline-block" : "none";
                }
                if (crumbEl) {
                    if (state.level === 1) {
                        crumbEl.innerHTML = "📂 Уровень 1 (" + esc(cfg.labels.type) + ")";
                    } else if (state.level === 2) {
                        crumbEl.innerHTML = "📂 " + esc(state.selType) + " ➔ Уровень 2 (" + esc(cfg.labels.model) + ")";
                    } else {
                        crumbEl.innerHTML = "📂 " + esc(state.selType) + (state.selModel ? (" ➔ " + esc(state.selModel)) : "") + " ➔ 🏷 Уровень 3 (" + esc(cfg.labels.plate) + ")";
                    }
                }

                var hdrEl = document.getElementById(hdrId);
                if (hdrEl) {
                    var detHdrHtml =
                        "Срез: <b>" + esc(dutTag) + "</b> | Условие: <b style='color:#003F0B;'>" + esc(condTag) + "</b>" +
                        " &nbsp;|&nbsp; Всего в выборке: <b>" + totalWeight + " " + unitLbl + "</b> (групп: " + list.length + ")";
                    if (state._ready && typeof window._eaUpdateHeaderAnimated === "function") {
                        window._eaUpdateHeaderAnimated(hdrEl, detHdrHtml);
                    } else {
                        hdrEl.innerHTML = detHdrHtml;
                    }
                }

                divEl._dutActiveMeta = metaList;

                var trace = labels.length ? {
                    type: "pie",
                    labels: labels,
                    values: values,
                    text: texts,
                    customdata: hoverBlocks,
                    hole: cfg.hole,
                    marker: { colors: colors, line: { color: "#ffffff", width: 1.5 } },
                    textinfo: cfg.show_values ? "text" : "none",
                    textposition: "inside",
                    insidetextorientation: "horizontal",
                    sort: false,
                    hovertemplate: "<b>%{label}</b><br>%{customdata}<extra></extra>"
                } : {
                    type: "pie",
                    labels: ["Нет записей, подходящих под условия"],
                    values: [1],
                    hole: cfg.hole,
                    marker: { colors: ["#e2e8f0"] },
                    textinfo: "label",
                    hoverinfo: "skip",
                    showlegend: false
                };

                var h = isSingleMode ? (cfg.height + 30) : cfg.height;
                Plotly.react(divEl, [trace], makeBaseLayout(h), { responsive: true });
                if (state._ready && typeof window._eaPlayElAnim === "function") {
                    window._eaPlayElAnim(divEl, state._animDir || "fade");
                }
                bindPieClick(divEl);
            }

            function bindPieClick(divEl) {
                if (!divEl || divEl._dutClickBound) return;
                divEl._dutClickBound = true;
                divEl.on("plotly_click", function(ev) {
                    if (!ev || !ev.points || !ev.points.length) return;
                    var pt = ev.points[0];
                    var ptIdx = (pt.i !== undefined) ? pt.i : pt.pointNumber;
                    var meta = divEl._dutActiveMeta ? divEl._dutActiveMeta[ptIdx] : null;
                    if (!meta) return;

                    if (meta.kind === "summary") {
                        state.pinnedDut = meta.dut;
                        state.pinnedMatched = !!meta.matched;
                        state.selType = "";
                        state.selModel = "";
                        state.level = 1;
                        state._animDir = "drill-in";
                        renderAll();
                    } else if (meta.kind === "detail" && !meta.isOther) {
                        if (state.level === 1) {
                            if (cfg.has_model) {
                                state.selType = meta.name;
                                state.selModel = "";
                                state.level = 2;
                                state._animDir = "drill-in";
                                renderAll();
                            } else if (cfg.has_plate) {
                                state.selType = meta.name;
                                state.selModel = "";
                                state.level = 3;
                                state._animDir = "drill-in";
                                renderAll();
                            }
                        } else if (state.level === 2 && cfg.has_plate) {
                            state.selModel = meta.name;
                            state.level = 3;
                            state._animDir = "drill-in";
                            renderAll();
                        } else if (state.level === 3 && typeof window.filterEaDataTable === "function") {
                            window.filterEaDataTable("__ALL__", meta.name, true);
                        }
                    }
                });
            }

            function syncControlStyles() {
                var dutWrap = document.getElementById(uid + "-dutbar");
                if (dutWrap) {
                    dutWrap.querySelectorAll(".ea-dut-btn").forEach(function(b) {
                        var active = b.getAttribute("data-dut") === state.dut;
                        b.style.background = active ? "#87C800" : "#f8fafc";
                        b.style.color = active ? "#ffffff" : "#334155";
                        b.style.fontWeight = active ? "700" : "600";
                    });
                }
                var mWrap = document.getElementById(uid + "-mbar");
                if (mWrap) {
                    mWrap.querySelectorAll(".ea-dut-mbtn").forEach(function(b) {
                        var active = b.getAttribute("data-month") === state.month;
                        b.style.background = active ? "#87C800" : "#f8fafc";
                        b.style.color = active ? "#ffffff" : "#334155";
                        b.style.fontWeight = active ? "700" : "500";
                    });
                }
                var restWrap = document.getElementById(uid + "-rest-wrap");
                if (restWrap) {
                    restWrap.style.display = (state.level === 0) ? "flex" : "none";
                }
            }

            function renderAll() {
                if (typeof Plotly === "undefined") return;
                syncControlStyles();
                var entities = buildEntities();
                if (cfg.mode === "dut_two_pies") {
                    renderSummaryPie(uid + "-pie1", uid + "-p1-hdr", entities, false);
                    renderDetailPie(uid + "-pie2", uid + "-p2-hdr", entities, false);
                } else {
                    if (state.level === 0) {
                        var backBtn = document.getElementById(uid + "-back-btn");
                        var crumbEl = document.getElementById(uid + "-crumb");
                        if (backBtn) backBtn.style.display = "none";
                        if (crumbEl) crumbEl.innerHTML = "📊 Уровень 0: " + esc(cfg.labels.dut) + " и " + esc(cfg.labels.pct);
                        renderSummaryPie(uid + "-pie1", uid + "-p1-hdr", entities, true);
                    } else {
                        renderDetailPie(uid + "-pie1", uid + "-p1-hdr", entities, true);
                    }
                }
                state._ready = true;
                state._animDir = "fade";
            }

            // Подключаем кнопки ДУТ
            var dutBar = document.getElementById(uid + "-dutbar");
            if (dutBar) {
                dutBar.querySelectorAll(".ea-dut-btn").forEach(function(btn) {
                    btn.addEventListener("click", function() {
                        state.dut = btn.getAttribute("data-dut") || "ALL";
                        state.pinnedDut = null;
                        state.pinnedMatched = true;
                        state.selType = "";
                        state.selModel = "";
                        if (cfg.mode === "dut_two_pies") state.level = 1;
                        renderAll();
                    });
                });
            }

            // Подключаем оператор и число % отклонения
            var opSel = document.getElementById(uid + "-op-sel");
            var valInp = document.getElementById(uid + "-val-inp");
            if (opSel) {
                opSel.value = state.op;
                opSel.addEventListener("change", function() {
                    state.op = opSel.value;
                    if (valInp) valInp.disabled = (state.op === "all");
                    renderAll();
                });
            }
            if (valInp) {
                valInp.value = String(state.val);
                valInp.disabled = (state.op === "all");
                valInp.addEventListener("input", function() {
                    var parsed = parseFloat(String(valInp.value).replace(",", "."));
                    if (!isNaN(parsed)) {
                        state.val = parsed;
                        renderAll();
                    }
                });
            }

            // Быстрые кнопки процентов (3%, 5%, 10%, 20%)
            var pctQuick = document.getElementById(uid + "-pct-quick");
            if (pctQuick) {
                pctQuick.querySelectorAll("button").forEach(function(b) {
                    b.addEventListener("click", function() {
                        var v = parseFloat(b.getAttribute("data-v"));
                        if (!isNaN(v)) {
                            state.val = v;
                            if (state.op === "all") {
                                state.op = "gt";
                                if (opSel) opSel.value = "gt";
                            }
                            if (valInp) {
                                valInp.disabled = false;
                                valInp.value = String(v);
                            }
                            renderAll();
                        }
                    });
                });
            }

            // Переключатель Уникальные ТС / Все записи
            var cntSel = document.getElementById(uid + "-cnt-sel");
            if (cntSel) {
                cntSel.addEventListener("change", function() {
                    state.countMode = cntSel.value;
                    renderAll();
                });
            }

            // Галочка «Показать остаток (в норме)»
            var chkRest = document.getElementById(uid + "-show-rest");
            if (chkRest) {
                chkRest.addEventListener("change", function() {
                    state.showRest = !!chkRest.checked;
                    renderAll();
                });
            }

            // Кнопки месяцев
            var mBar = document.getElementById(uid + "-mbar");
            if (mBar) {
                mBar.querySelectorAll(".ea-dut-mbtn").forEach(function(b) {
                    b.addEventListener("click", function() {
                        state.month = b.getAttribute("data-month") || "ALL";
                        renderAll();
                    });
                });
            }

            // Кнопка «На уровень выше»
            var backBtn = document.getElementById(uid + "-back-btn");
            if (backBtn) {
                backBtn.addEventListener("click", function() {
                    if (state.level === 3) {
                        state.selModel = "";
                        state.level = cfg.has_model ? 2 : 1;
                    } else if (state.level === 2) {
                        state.selType = "";
                        state.level = 1;
                    } else if (state.level === 1 && cfg.mode === "dut_single_drill") {
                        state.pinnedDut = null;
                        state.pinnedMatched = true;
                        state.level = 0;
                    }
                    state._animDir = "drill-out";
                    renderAll();
                });
            }

            // Кнопка сброса клика по сектору Левого круга
            var resetPinBtn = document.getElementById(uid + "-reset-pin");
            if (resetPinBtn) {
                resetPinBtn.addEventListener("click", function() {
                    state.pinnedDut = null;
                    state.pinnedMatched = true;
                    state.selType = "";
                    state.selModel = "";
                    state.level = 1;
                    renderAll();
                });
            }

            if (typeof Plotly !== "undefined") {
                renderAll();
            } else {
                window.addEventListener("load", renderAll);
            }
        })();
        </script>
        """.replace("__UID__", uid)

        dut_caption = _escape(str(self.title or "Диаграмма").strip() or "Диаграмма")
        a_style = _escape(str(getattr(self, "anim_style", "auto") or "auto"))
        a_speed = int(getattr(self, "anim_speed", 480) or 480)
        inner = f'''
        {_CHART_ANIM_ASSETS_HTML}
        <div class="block" style="width:100%; min-width:0; max-width:100%;">
            <div class="block-card ea-chart-card" id="{uid}-card"
                 data-anim-style="{a_style}" data-anim-speed="{a_speed}"
                 style="width:100%; padding:16px; background:{self.bg_color or '#ffffff'}; border-radius:8px; box-sizing:border-box; --ea-anim-dur:{a_speed}ms;">
                <div class="ea-chart-topbar"
                     onclick="if (this.parentElement.classList.contains('ea-collapsed')) window.toggleEaChartCard('{uid}', event)">
                    <span class="ea-chart-collapsed-title">🥧 {dut_caption}<span class="ea-chart-collapsed-hint">(нажмите, чтобы развернуть)</span></span>
                    <button type="button" class="ea-chart-toggle-btn" title="Свернуть график"
                            onclick="window.toggleEaChartCard('{uid}', event)">
                        <span class="ea-toggle-icon">▾</span>
                    </button>
                </div>
                <div class="ea-chart-collapsible" id="{uid}-body">
                    <div class="ea-chart-collapsible-inner">
                        {title_html}
                        <div style="display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:10px; padding:10px 12px; background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; margin-bottom:10px;">
                    <div id="{uid}-dutbar" style="display:flex; flex-wrap:wrap; align-items:center; gap:6px;">
                        <span style="font-size:12px; font-weight:700; color:#003F0B;">🔌 {_escape(dut_col or 'Оснащён ДУТ')}:</span>
                        {"".join(dut_btns_html)}
                    </div>
                    <div style="display:flex; flex-wrap:wrap; align-items:center; gap:6px;">
                        <span style="font-size:12px; font-weight:700; color:#003F0B;" title="{_escape(' '.join(str(pct_col or '% отклонения').split()))}">📐 Отклонение:</span>
                        <select id="{uid}-op-sel" style="padding:4px 8px; border:1px solid #87C800; border-radius:6px; font-size:12px; background:#fff; color:#1e293b; font-weight:600; cursor:pointer;">
                            <option value="gt">&gt; Больше</option>
                            <option value="ge">≥ Больше или равно</option>
                            <option value="lt">&lt; Меньше</option>
                            <option value="le">≤ Меньше или равно</option>
                            <option value="abs_gt">|%| &gt; По модулю больше</option>
                            <option value="abs_ge">|%| ≥ По модулю ≥</option>
                            <option value="all">Все (без порога)</option>
                        </select>
                        <input type="number" id="{uid}-val-inp" step="0.5" value="{init_val}" style="width:74px; padding:4px 8px; border:1px solid #87C800; border-radius:6px; font-size:12px; font-weight:700; color:#003F0B; background:#fff;" />
                        <span style="font-size:12px; font-weight:700; color:#334155;">%</span>
                        <div id="{uid}-pct-quick" style="display:flex; gap:4px;">
                            <button type="button" data-v="3" style="padding:3px 7px; border:1px solid #cbd5e1; border-radius:4px; background:#fff; color:#334155; font-size:11px; font-weight:600; cursor:pointer;">3%</button>
                            <button type="button" data-v="5" style="padding:3px 7px; border:1px solid #cbd5e1; border-radius:4px; background:#fff; color:#334155; font-size:11px; font-weight:600; cursor:pointer;">5%</button>
                            <button type="button" data-v="10" style="padding:3px 7px; border:1px solid #cbd5e1; border-radius:4px; background:#fff; color:#334155; font-size:11px; font-weight:600; cursor:pointer;">10%</button>
                            <button type="button" data-v="20" style="padding:3px 7px; border:1px solid #cbd5e1; border-radius:4px; background:#fff; color:#334155; font-size:11px; font-weight:600; cursor:pointer;">20%</button>
                        </div>
                    </div>
                    {count_mode_html}
                </div>
                {month_bar_html}
                {charts_area_html}
                <script type="application/json" id="{uid}-dutdata">{payload_json}</script>
                {js_code}
            </div>
        </div>
        '''
        return self.wrap_layout(inner)

    def _render_empty(self, msg: str) -> str:
        return f'''
        <div class="block">
            <div class="block-card" style="text-align:center; padding: 40px 20px; background: {self.bg_color};">
                <p style="color:#888; font-size: 13px;">📊 График: {msg}</p>
            </div>
        </div>
        '''


# ============================================================
# Срез / Интерактивный фильтр дашборда
# ============================================================

@dataclass
class DashboardFilterBlock(Block):
    type: str = "dashboard_filter"
    title: str = "Фильтр"
    filter_col: str = ""
    target_chart: str = ""
    target_charts: list[str] = field(default_factory=list)
    extra_target_charts: str = ""
    dataframe: object = None
    source_file_name: str = ""
    source_sheet: str = ""
    max_height: int = 420
    sync_height: bool = True

    def render(self) -> str:
        unique_vals = []
        report_obj, own_cfg = _find_report_and_config(self)
        if report_obj is not None:
            self._report_ref = report_obj

        for k, v in own_cfg.items():
            if hasattr(self, k) and k not in ("id", "type", "dataframe", "width", "margin_top", "margin_bottom", "min_height"):
                setattr(self, k, v)

        df_work = self.dataframe
        source_file_name = self.source_file_name or own_cfg.get("source_file_name", "")
        source_sheet = self.source_sheet or own_cfg.get("source_sheet", "") or own_cfg.get("source_file", "")

        manager = getattr(self, "_file_manager", None)
        if not manager and report_obj and hasattr(report_obj, "file_manager"):
            manager = report_obj.file_manager

        df_work = DataMemoryCache.get_dataframe(
            manager, source_file_name, source_sheet, fallback_df=df_work
        )

        # Собираем все ID привязанных графиков (список чекбоксов + основной + дополнительные)
        raw_targets: list[str] = []
        for lst_cand in (self.target_charts, own_cfg.get("target_charts", [])):
            if isinstance(lst_cand, list):
                for item in lst_cand:
                    p_clean = str(item or "").strip()
                    if p_clean and p_clean not in raw_targets:
                        raw_targets.append(p_clean)
        for src_str in (self.target_chart, own_cfg.get("target_chart", ""), self.extra_target_charts, own_cfg.get("extra_target_charts", "")):
            if src_str:
                for part in str(src_str).split(","):
                    p_clean = part.strip()
                    if p_clean and p_clean not in raw_targets:
                        raw_targets.append(p_clean)

        primary_chart_id = raw_targets[0] if raw_targets else ""

        if self.filter_col:
            target_cfg = {}
            try:
                if report_obj and hasattr(report_obj, "sections"):
                    if raw_targets:
                        for cand_id in raw_targets:
                            for section in report_obj.sections:
                                for b in _iter_all_report_blocks(section.blocks):
                                    b_id = b.get("id") if isinstance(b, dict) else getattr(b, "id", "")
                                    b_type = b.get("type") if isinstance(b, dict) else getattr(b, "type", "")
                                    if b_id == cand_id and b_type == "plotly_chart":
                                        target_cfg = b.get("config", {}) if isinstance(b, dict) else (getattr(b, "config", {}) or {})
                                        primary_chart_id = cand_id
                                        break
                                if target_cfg:
                                    break
                            if target_cfg:
                                break

                    if not target_cfg and not raw_targets:
                        for section in report_obj.sections:
                            for b in _iter_all_report_blocks(section.blocks):
                                b_type = b.get("type") if isinstance(b, dict) else getattr(b, "type", "")
                                if b_type == "plotly_chart":
                                    c_cfg = b.get("config", {}) if isinstance(b, dict) else (getattr(b, "config", {}) or {})
                                    if c_cfg.get("filter_col") or c_cfg.get("custom_query"):
                                        target_cfg = c_cfg
                                        break
                            if target_cfg:
                                break

                # 1. Если у фильтра указан привязанный график — проверяем его лист (приоритетно, если там есть filter_col)
                if target_cfg:
                    chart_df = None
                    if hasattr(report_obj, "get_block_dataframe"):
                        chart_df = report_obj.get_block_dataframe(target_cfg, fallback_df=None)
                    if chart_df is None or self.filter_col not in chart_df.columns:
                        tc_file = target_cfg.get("source_file_name", "")
                        tc_sheet = target_cfg.get("source_sheet", "") or target_cfg.get("source_file", "")
                        if tc_file or tc_sheet:
                            chart_df = DataMemoryCache.get_dataframe(manager, tc_file, tc_sheet, fallback_df=None)
                    if chart_df is not None and self.filter_col in chart_df.columns:
                        df_work = chart_df

                # 2. Если filter_col всё ещё нет в df_work — ищем лист с этой колонкой среди всех загруженных в FileManager
                if (df_work is None or self.filter_col not in df_work.columns) and manager is not None:
                    alt_df = None
                    if hasattr(manager, "find_dataframe_with_column"):
                        alt_df = manager.find_dataframe_with_column(self.filter_col)
                    if alt_df is None and hasattr(manager, "get_files_dict"):
                        for f_k, sh_list in (manager.get_files_dict() or {}).items():
                            for s_k in (sh_list or []):
                                cand_df = DataMemoryCache.get_dataframe(manager, f_k, s_k, fallback_df=None)
                                if cand_df is not None and self.filter_col in cand_df.columns:
                                    alt_df = cand_df
                                    break
                            if alt_df is not None:
                                break
                    if alt_df is not None:
                        df_work = alt_df
            except Exception as e:
                print(f"[DashboardFilterBlock] Ошибка подбора источника данных: {e}")

        if df_work is not None and self.filter_col and self.filter_col in df_work.columns:
            filtered_df = df_work
            try:
                if target_cfg:
                    dummy_chart = PlotlyChartBlock(
                        id=primary_chart_id or "target",
                        type="plotly_chart",
                        filter_col=target_cfg.get("filter_col", ""),
                        filter_op=target_cfg.get("filter_op", ">"),
                        filter_val=target_cfg.get("filter_val", ""),
                        custom_query=target_cfg.get("custom_query", ""),
                    )
                    dummy_chart._report_ref = report_obj
                    dummy_chart._file_manager = manager
                    filtered_df = dummy_chart._apply_smart_filter(df_work)
            except Exception as e:
                print(f"[DashboardFilterBlock] Ошибка применения фильтра графика: {e}")

            unique_vals = [
                str(v).strip()
                for v in filtered_df[self.filter_col].dropna().unique()
                if str(v).strip()
            ][:60]

        if not unique_vals:
            unique_vals = ["(Выберите колонку в Инспекторе)"]

        filter_id = f"filter_{self.id}"
        target_tokens = []
        for cid in raw_targets:
            target_tokens.append(f"ea-plotly-{cid}")
            target_tokens.append(f"ea-para-{cid}")
        target_ids_csv = ",".join(target_tokens)

        items_html = (
            f'<div class="ea-filter-item active" data-val="ALL" '
            f'onclick="window.applyFilter(\'{filter_id}\', \'{target_ids_csv}\', \'ALL\', this)" '
            f'style="padding: 8px 12px; background: #87C800; color: white; border-radius: 6px; '
            f'cursor: pointer; margin-bottom: 4px; font-weight: bold; transition: 0.2s; '
            f'white-space: normal; word-wrap: break-word; overflow-wrap: anywhere; line-height: 1.3;">'
            f'Все значения</div>'
        )

        for v in unique_vals:
            safe_val = _escape(str(v))
            js_val = safe_val.replace("\\", "\\\\").replace("'", "\\'")
            items_html += (
                f'<div class="ea-filter-item" data-val="{safe_val}" '
                f'onclick="window.applyFilter(\'{filter_id}\', \'{target_ids_csv}\', \'{js_val}\', this)" '
                f'style="padding: 8px 12px; cursor: pointer; border-radius: 6px; margin-bottom: 4px; '
                f'color: #333; transition: 0.2s; white-space: normal; word-wrap: break-word; '
                f'overflow-wrap: anywhere; line-height: 1.3;">'
                f'{safe_val}</div>'
            )

        js_script = '''
        <script>
        if (typeof window.applyFilter === 'undefined') {
            window._eaRedrawPlotClean = function(plotDiv, traces) {
                if (!plotDiv || !traces) return;
                var cleanTraces = JSON.parse(JSON.stringify(traces));
                var isPieOrTree = cleanTraces.some(function(t) {
                    return t.type === 'pie' || t.type === 'treemap' || t.type === 'sunburst';
                });
                if (plotDiv.layout) {
                    delete plotDiv.layout.transition;
                }
                if (isPieOrTree) {
                    Plotly.react(plotDiv, cleanTraces, plotDiv.layout);
                } else {
                    if (plotDiv.layout) {
                        if (plotDiv.layout.xaxis) {
                            delete plotDiv.layout.xaxis.range;
                            plotDiv.layout.xaxis.autorange = true;
                        }
                        if (plotDiv.layout.yaxis) {
                            delete plotDiv.layout.yaxis.range;
                            plotDiv.layout.yaxis.autorange = true;
                        }
                    }
                    Plotly.react(plotDiv, cleanTraces, plotDiv.layout);
                    Plotly.relayout(plotDiv, { 'xaxis.autorange': true, 'yaxis.autorange': true });
                }
            };

            window.applyFilter = function(filterGroupId, targetPlotIdsCsv, value, el) {
                var container = el.parentElement;
                var items = container.querySelectorAll('.ea-filter-item');
                items.forEach(function(i) {
                    i.style.background = 'transparent';
                    i.style.color = '#333';
                    i.style.fontWeight = 'normal';
                    i.classList.remove('active');
                });
                el.style.background = '#87C800';
                el.style.color = 'white';
                el.style.fontWeight = 'bold';
                el.classList.add('active');

                var targetIds = targetPlotIdsCsv
                    ? targetPlotIdsCsv.split(',').map(function(s) { return s.trim(); }).filter(Boolean)
                    : [];

                if (typeof window.syncDynamicParagraphs === 'function') {
                    if (targetIds.length > 0) {
                        targetIds.forEach(function(tid) { window.syncDynamicParagraphs(value, null, tid); });
                    } else {
                        window.syncDynamicParagraphs(value, null, '');
                    }
                }

                var plots = Array.from(document.querySelectorAll('.js-plotly-plot'));
                if (targetIds.length > 0) {
                    plots = plots.filter(function(p) {
                        return targetIds.indexOf(p.id) !== -1;
                    });
                }

                plots.forEach(function(plotDiv) {
                    if (!plotDiv || !plotDiv.data) return;

                    var mapEl = document.getElementById(plotDiv.id + '-rowmap');
                    if (mapEl) {
                        var rowMap = null;
                        try { rowMap = JSON.parse(mapEl.textContent); } catch (e) {}
                        if (rowMap && rowMap.__is_matrix__ && typeof window.syncMatrixPie === 'function') {
                            // 1. Обязательно сбрасываем уровень погружения до 1 (корневой)
                            plotDiv._activeLevel = 1;
                            // 2. Устанавливаем новую группу 1-го уровня (Тип ТС)
                            plotDiv._activeGroup = value;
                            // 3. Жестко зачищаем 2-й и 3-й уровни
                            plotDiv._activeSubGroup = '';
                            delete plotDiv._activeSubGroup; 
                            
                            try { window.syncMatrixPie(plotDiv); } catch (e) { console.error(e); }
                            return; // Выходим из функции, чтобы нижний код не сломал отрисовку
                        }
                    }
                    if (!plotDiv._originalData) {
                        plotDiv._originalData = JSON.parse(JSON.stringify(plotDiv.data));
                    }
                    var origData = plotDiv._originalData;
                    var newData = [];

                    for (var i = 0; i < origData.length; i++) {
                        var trace = JSON.parse(JSON.stringify(origData[i]));
                        if (value === 'ALL') {
                            newData.push(trace);
                            continue;
                        }
                        if (trace.name && String(trace.name) === value) {
                            newData.push(trace);
                            continue;
                        }
                        if (trace.x && Array.isArray(trace.x)) {
                            var newX = [];
                            var newY = [];
                            for (var j = 0; j < trace.x.length; j++) {
                                if (String(trace.x[j]) === value) {
                                    newX.push(trace.x[j]);
                                    if (trace.y) newY.push(trace.y[j]);
                                }
                            }
                            if (newX.length > 0) {
                                trace.x = newX;
                                if (trace.y) trace.y = newY;
                                newData.push(trace);
                            }
                        }
                    }
                    window._eaRedrawPlotClean(plotDiv, newData);
                });
            };
        }
        </script>
        '''

        max_h_val = int(getattr(self, "max_height", 420) or 0)
        sync_flag = "1" if getattr(self, "sync_height", True) else "0"
        scroll_style = f"max-height: {max_h_val}px; overflow-y: auto; padding-right: 4px; padding-bottom: 6px;" if max_h_val > 0 else "overflow-y: auto; padding-right: 4px; padding-bottom: 6px;"

        sync_js = f'''
        <script>
        (function() {{
            function syncFilterHeight_{self.id}() {{
                var filterEl = document.getElementById("{filter_id}");
                if (!filterEl) return;
                var filterCard = filterEl.querySelector(".block-card");
                var scrollBox = filterEl.querySelector(".ea-filter-scroll");
                if (!scrollBox || !filterCard) return;
                var syncEnabled = "{sync_flag}" === "1";
                var manualMax = {max_h_val};

                if (syncEnabled) {{
                    var rowContainer = filterEl.closest(".container-row");
                    if (rowContainer) {{
                        var chartCards = rowContainer.querySelectorAll(".ea-container-cell[data-child-type='plotly_chart'] .block-card");
                        var maxChartCardH = 0;
                        chartCards.forEach(function(c) {{
                            if (c.offsetHeight > maxChartCardH) maxChartCardH = c.offsetHeight;
                        }});
                        if (maxChartCardH > 160) {{
                            filterCard.style.minHeight = maxChartCardH + "px";
                            var availH = Math.max(120, maxChartCardH - 72);
                            scrollBox.style.maxHeight = availH + "px";
                            return;
                        }}
                    }}
                }}
                filterCard.style.minHeight = "";
                if (manualMax > 0) {{
                    scrollBox.style.maxHeight = manualMax + "px";
                }} else {{
                    scrollBox.style.maxHeight = "none";
                }}
            }}
            window.addEventListener("load", function() {{
                setTimeout(syncFilterHeight_{self.id}, 150);
                setTimeout(syncFilterHeight_{self.id}, 600);
            }});
            window.addEventListener("resize", syncFilterHeight_{self.id});
            setTimeout(syncFilterHeight_{self.id}, 120);
        }})();
        </script>
        '''

        self.min_height = 0
        inner = f'''
        <div class="block" style="width:100%; min-width:0; max-width:100%;" id="{filter_id}">
            <div class="block-card" style="padding: 16px; background: #ffffff; width: 100%; box-sizing: border-box;">
                <div style="font-weight: bold; font-size: 14px; color: #003F0B; margin-bottom: 12px; border-bottom: 2px solid #87C800; padding-bottom: 4px; white-space: normal; word-wrap: break-word;">{_escape(self.title)}</div>
                <div class="ea-filter-scroll" style="font-size: 13px; {scroll_style}">
                    {items_html}
                </div>
            </div>
            {js_script}
            {sync_js}
        </div>
        '''
        return self.wrap_layout(inner)

# ============================================================
# Контейнер (сетка)
# ============================================================

@dataclass
class ContainerBlock(Block):
    type: str = "container"
    layout: str = "row"
    gap: int = 14
    children_html: list[str] = field(default_factory=list)

    def render(self) -> str:
        css_class = "container-row" if self.layout == "row" else "container-column"
        if self.layout == "row":
            style = f"display: flex; flex-direction: row; flex-wrap: wrap; gap: {self.gap}px; align-items: flex-start; width: 100%; box-sizing: border-box;"
        else:
            style = f"display: flex; flex-direction: column; gap: {self.gap}px; align-items: flex-start; width: 100%; box-sizing: border-box;"
            
        inner = f'<div class="{css_class}" style="{style}">{"".join(self.children_html)}</div>'
        return self.wrap_layout(inner)


# ============================================================
# Утилиты
# ============================================================

def _escape(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )


def _extract_body(html: str) -> str:
    if not isinstance(html, str):
        return ""
    low = html.lower()
    start = low.find("<body")
    if start == -1:
        return html
    gt = html.find(">", start)
    if gt == -1:
        return html
    end = low.rfind("</body>")
    if end == -1:
        return html[gt + 1:]
    return html[gt + 1:end]