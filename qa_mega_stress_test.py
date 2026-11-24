"""
Мега-автотест, детектор утечек памяти/кэша и краш-тест движка NexGrid.

Запуск (из корня проекта в активированном venv):
    python qa_mega_stress_test.py                # полный прогон (тесты + утечки + краш-тест до 500k строк)
    python qa_mega_stress_test.py --extreme      # экстремальный краш-тест до 1 000 000 строк
    python qa_mega_stress_test.py --no-crash     # только функциональные тесты и проверка утечек (быстро)

Результат дополнительно сохраняется в файл: qa_stress_report.md
"""

from __future__ import annotations

import argparse
import ast
import concurrent.futures
import ctypes
import gc
import json
import os
import subprocess
import sys
import tempfile
import time
import traceback
import tracemalloc
import types
import warnings
import weakref
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Безопасный UTF-8 вывод в любой Windows-консоли
for _st in (sys.stdout, sys.stderr):
    if _st is not None and hasattr(_st, "reconfigure"):
        try:
            _st.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


# ============================================================
# Утилиты замера памяти (работают без psutil)
# ============================================================

def get_rss_mb() -> float:
    """Возвращает реальное потребление физической RAM (RSS) текущим процессом в МБ."""
    if os.name == "nt":
        try:
            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("cb", ctypes.c_ulong),
                    ("PageFaultCount", ctypes.c_ulong),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]
            counters = PROCESS_MEMORY_COUNTERS()
            counters.cb = ctypes.sizeof(counters)
            k32 = ctypes.windll.kernel32
            k32.GetCurrentProcess.restype = ctypes.c_void_p
            psapi = ctypes.windll.psapi
            psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
            psapi.GetProcessMemoryInfo.restype = ctypes.c_bool
            handle = k32.GetCurrentProcess()
            if psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                return counters.WorkingSetSize / (1024 * 1024)
        except Exception:
            pass
    else:
        try:
            import resource
            usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            # На Linux ru_maxrss в КБ, на macOS в байтах
            return (usage / (1024 * 1024)) if sys.platform == "darwin" else (usage / 1024.0)
        except Exception:
            pass
    cur, _ = tracemalloc.get_traced_memory() if tracemalloc.is_tracing() else (0, 0)
    return cur / (1024 * 1024)


def cache_snapshot() -> dict[str, int]:
    """Снимает количество записей во всех внутренних словарях DataMemoryCache."""
    from src.core.blocks import DataMemoryCache
    return {
        "sheet_df": len(DataMemoryCache._sheet_df_cache),
        "dedup": len(DataMemoryCache._dedup_cache),
        "num_series": len(DataMemoryCache._num_series_cache),
        "str_series": len(DataMemoryCache._str_series_cache),
        "month_series": len(DataMemoryCache._month_series_cache),
        "unique_vals": len(DataMemoryCache._unique_vals_cache),
        "filter_df": len(DataMemoryCache._filter_df_cache),
        "render_html": len(DataMemoryCache._render_html_cache),
    }


# ============================================================
# Генераторы тестовых данных (обычные, «грязные» и нагрузочные)
# ============================================================

def make_business_df(n_rows: int = 240, n_groups: int = 8, n_subgroups: int = 24, n_items: int = 120, seed: int = 42) -> pd.DataFrame:
    """Быстро генерирует векторный бизнес-датасет заданного объёма."""
    rng = np.random.default_rng(seed)
    months = np.array([
        "2026-01-15", "2026-02-15", "2026-03-15",
        "2026-04-15", "2026-05-15", "2026-06-15",
    ])
    grp_pool = np.array([f"Категория_{i + 1:02d}" for i in range(max(1, n_groups))])
    sub_pool = np.array([f"Подгруппа_{i + 1:03d}" for i in range(max(1, n_subgroups))])
    item_pool = np.array([f"ID-{i + 1:05d}" for i in range(max(1, n_items))])
    ctrl_pool = np.array(["Да", "Нет"])

    g_idx = rng.integers(0, len(grp_pool), size=n_rows)
    s_idx = rng.integers(0, len(sub_pool), size=n_rows)
    i_idx = rng.integers(0, len(item_pool), size=n_rows)
    m_idx = rng.integers(0, len(months), size=n_rows)
    c_idx = rng.integers(0, 2, size=n_rows)

    plan = np.round(rng.uniform(50.0, 500.0, size=n_rows), 2)
    factor = rng.uniform(0.82, 1.24, size=n_rows)
    fact = np.round(plan * factor, 2)
    pct = np.round(((fact - plan) / np.where(plan == 0, 1.0, plan)) * 100.0, 2)

    return pd.DataFrame({
        "Категория": grp_pool[g_idx],
        "Подкатегория": sub_pool[s_idx],
        "Артикул": item_pool[i_idx],
        "Дата": months[m_idx],
        "Факт": fact,
        "План": plan,
        "Отклонение_%": pct,
        "Контроль": ctrl_pool[c_idx],
    })


def make_dirty_df() -> pd.DataFrame:
    """Создаёт экстремально «грязный» DataFrame: дубли колонок, NaN, Inf, XSS, кавычки, NBSP."""
    df = pd.DataFrame({
        "Категория": [
            "Группа A",
            "O'Reilly \"Quotes\" \\ Slash",
            "<script>alert('xss')</script>",
            None,
            "",
            "   Пробелы   ",
            "Группа A",
        ],
        "Подкатегория": ["Под_1", "Под_2", "<b>Тег</b>", "Под_3", None, "Под_1", "Под_2"],
        "Артикул": ["A001AA77", "B002BB77", "C003CC77", "D004DD77", "E005EE77", "F006FF77", "A001AA77"],
        "Дата": ["2026-01-10", "15.02.2026", "Март 2026", "мусор", None, "2026-04-01", "2026-05-05"],
        "Факт": ["1 250,50", "980\u00a0,25", "—", "N/A", "0", "-45,5", "100"],
        "План": [1000.0, 0.0, np.nan, np.inf, -np.inf, 50.0, 0.0],
        "Контроль": ["Да", "Нет", None, "", "Да", "Нет", "Да"],
    })
    # Добавляем дублирующееся имя колонки «Факт»
    dup = pd.DataFrame({"Факт": [np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, 1.0]})
    return pd.concat([df, dup], axis=1)


class MockFileManager:
    def __init__(self, sheets_by_file: dict[str, dict[str, pd.DataFrame]], default_file: str = "", default_sheet: str = ""):
        self._sheets = sheets_by_file
        self._default_file = default_file or next(iter(sheets_by_file.keys()))
        self._default_sheet = default_sheet or next(iter(sheets_by_file[self._default_file].keys()))

    def get_files_dict(self):
        return {f: list(s.keys()) for f, s in self._sheets.items()}

    def get_default_file_and_sheet(self):
        return self._default_file, self._default_sheet

    def get_dataframe(self, file_name: str = "", sheet_name: str = ""):
        f_key = file_name if file_name in self._sheets else self._default_file
        sh = self._sheets.get(f_key, {})
        if not sh:
            return None
        if sheet_name in sh:
            return sh[sheet_name]
        if sheet_name:
            for sh_map in self._sheets.values():
                if sheet_name in sh_map:
                    return sh_map[sheet_name]
        def_df = sh.get(self._default_sheet)
        return def_df if def_df is not None else next(iter(sh.values()))

    def find_dataframe_with_column(self, col_name: str):
        for sh_map in self._sheets.values():
            for df in sh_map.values():
                if col_name in df.columns:
                    return df
        return None

    def get_all(self):
        out = []
        for fn, sh_map in self._sheets.items():
            for sn, df in sh_map.items():
                entry = types.SimpleNamespace(name=fn, file_name=fn, sheet_name=sn, dataframe=df)
                entry.data = entry
                out.append(entry)
        return out


# ============================================================
# Реестр результатов
# ============================================================

TEST_LOG: list[dict] = []
CRASH_TABLE: list[dict] = []
LEAK_FINDINGS: list[str] = []


def run_case(section: str, name: str, fn):
    t0 = time.perf_counter()
    try:
        msg = fn() or "OK"
        dt = time.perf_counter() - t0
        status = "WARN" if str(msg).startswith("WARN:") else "PASS"
        icon = "⚠" if status == "WARN" else "✅"
        TEST_LOG.append({"section": section, "name": name, "status": status, "detail": msg, "time": dt})
        print(f"{icon} [{status}] {name} — {msg} ({dt:.2f}s)")
    except Exception as exc:
        dt = time.perf_counter() - t0
        detail = f"{type(exc).__name__}: {exc}"
        TEST_LOG.append({"section": section, "name": name, "status": "FAIL", "detail": detail, "time": dt})
        print(f"❌ [FAIL] {name} — {detail} ({dt:.2f}s)")


# ============================================================
# БЛОК 1. ФУНКЦИОНАЛЬНЫЙ И EDGE-CASE ФАЗЗИНГ (12 тестов)
# ============================================================

def test_01_dirty_data_and_duplicates():
    from src.core.block_factory import RenderContext, render_report
    from src.core.blocks import DataMemoryCache
    from src.core.report_model import Report, ReportBlock

    DataMemoryCache.clear_all()
    df = make_dirty_df()
    fm = MockFileManager({"dirty.xlsx": {"Лист1": df}})
    rep = Report(title="Dirty QA")
    rep.file_manager = fm
    sec = rep.add_section("Грязные данные")
    sec.add_block(ReportBlock.create("plotly_chart", {
        "title": "Комбо на грязных данных",
        "chart_type": "combo",
        "source_file_name": "dirty.xlsx",
        "source_sheet": "Лист1",
        "combo_level1_col": "Категория",
        "combo_level2_col": "Подкатегория",
        "combo_level3_col": "Артикул",
        "date_col": "Дата",
        "fact_col": "Факт",
        "norm_col": "План",
    }))
    sec.add_block(ReportBlock.create("pivot_matrix", {
        "title": "Сводная на грязных данных",
        "source_file_name": "dirty.xlsx",
        "source_sheet": "Лист1",
        "row_group_col": "Категория",
        "row_level2_col": "Подкатегория",
        "row_level3_col": "Артикул",
        "col_group_col": "Дата",
        "value_col": "Факт",
        "value_cols": ["Факт", "План"],
        "calc_cols": [{"name": "Откл %", "formula": "((A - B) / B) * 100", "is_pct": True}],
    }))
    sec.add_block(ReportBlock.create("data_table", {
        "title": "Реестр",
        "source_file_name": "dirty.xlsx",
        "source_sheet": "Лист1",
    }))
    html = render_report(rep, RenderContext(dataframe=df, report=rep, file_manager=fm))
    assert "Ошибка построения графика" not in html, "Комбо упал на грязных данных"
    assert "Ошибка расчета сводной матрицы" not in html, "Сводная упала на грязных данных"
    assert len(html) > 2000
    return "дубли колонок, NBSP, запятые, NaN, Inf обработаны без падений"


def test_02_empty_and_single_row_df():
    from src.core.block_factory import RenderContext, render_report
    from src.core.blocks import DataMemoryCache
    from src.core.report_model import Report, ReportBlock

    for label, df in [
        ("empty_0_rows", make_business_df(1).iloc[0:0]),
        ("single_1_row", make_business_df(1)),
    ]:
        DataMemoryCache.clear_all()
        fm = MockFileManager({"edge.xlsx": {"Данные": df}})
        rep = Report(title=label)
        rep.file_manager = fm
        sec = rep.add_section(label)
        for bt, cfg in [
            ("plotly_chart", {"chart_type": "bar", "x_col": "Категория", "y_col": "Факт"}),
            ("plotly_chart", {"chart_type": "combo", "fact_col": "Факт", "norm_col": "План", "date_col": "Дата"}),
            ("plotly_chart", {"chart_type": "pie", "pie_display_mode": "dut_single_drill", "dut_col": "Контроль", "pct_col": "Отклонение_%"}),
            ("pivot_matrix", {"row_group_col": "Категория", "value_col": "Факт"}),
            ("data_table", {}),
            ("dashboard_filter", {"filter_col": "Категория"}),
            ("paragraph", {"text": "Строк: {{ count() }}, Факт: {{ sum(Факт) }}"}),
            ("decomposition", {"level1_col": "Категория", "value_col": "Факт"}),
            ("geo_map", {"loc_col": "Категория", "value_col": "Факт"}),
        ]:
            sec.add_block(ReportBlock.create(bt, cfg))
        html = render_report(rep, RenderContext(dataframe=df, report=rep, file_manager=fm))
        assert "Traceback" not in html and "Ошибка построения графика" not in html, f"Сбой на {label}"
    return "0 строк и 1 строка выдержаны всеми 9 типами блоков"


def test_03_xss_and_escaping():
    from src.core.block_factory import RenderContext, render_report
    from src.core.report_model import Report, ReportBlock

    df = make_dirty_df()
    fm = MockFileManager({"xss.xlsx": {"Лист1": df}})
    rep = Report(title="<script>window.__xss=1</script>")
    rep.file_manager = fm
    sec = rep.add_section("<img src=x onerror=alert(1)>")
    sec.add_block(ReportBlock.create("dashboard_filter", {"title": "<script>1</script>", "filter_col": "Категория"}))
    sec.add_block(ReportBlock.create("paragraph", {"text": "Тест: <script>bad()</script>", "raw_html": False}))
    sec.add_block(ReportBlock.create("pivot_matrix", {"title": "Pivot <script>", "row_group_col": "Категория", "value_col": "Факт"}))

    html = render_report(rep, RenderContext(dataframe=df, report=rep, file_manager=fm))
    assert "<script>alert('xss')</script>" not in html, "Обнаружен неэкранированный XSS в данных!"
    assert "<script>bad()</script>" not in html, "Обнаружен неэкранированный XSS в ParagraphBlock!"
    assert "<img src=x onerror=alert(1)>" not in html, "Обнаружен неэкранированный XSS в заголовке раздела!"
    return "экранирование HTML/XSS в фильтрах, сводной и текстах корректно"


def test_04_all_plotly_chart_types():
    from src.core.block_factory import RenderContext, render_report
    from src.core.report_model import Report, ReportBlock

    df = make_business_df(150, n_groups=5, n_subgroups=10, n_items=30)
    fm = MockFileManager({"all.xlsx": {"Данные": df}})
    rep = Report(title="All Charts")
    rep.file_manager = fm
    sec = rep.add_section("Типы графиков")

    chart_types = [
        "bar", "bar_stacked", "bar_cumulative", "bar_stacked_100",
        "hbar", "line", "area", "scatter", "pie", "donut",
        "histogram", "box", "funnel", "combo",
    ]
    for ct in chart_types:
        sec.add_block(ReportBlock.create("plotly_chart", {
            "title": f"Тип: {ct}",
            "chart_type": ct,
            "x_col": "Категория",
            "y_col": "Факт, План" if ct in ("bar", "bar_stacked", "bar_cumulative", "bar_stacked_100", "line", "area") else "Факт",
            "date_col": "Дата" if ct in ("line", "bar", "bar_stacked", "combo") else "",
            "fact_col": "Факт",
            "norm_col": "План",
            "parent_group_col": "Категория",
            "model_col": "Подкатегория",
            "plate_col": "Артикул",
            "anim_style": "auto",
            "anim_speed": 320,
        }))

    # Плюс режим data_mode="rows" (таблица месяцев по столбцам)
    df_rows = pd.DataFrame({
        "Модель": ["M1", "M2", "M3"],
        "Январь_Факт": [100, 200, 150],
        "Февраль_Факт": [120, 180, 160],
        "Январь_План": [90, 210, 140],
        "Февраль_План": [110, 190, 150],
    })
    fm_r = MockFileManager({"rows.xlsx": {"Месяцы": df_rows}})
    rep_r = Report(title="Rows Mode")
    rep_r.file_manager = fm_r
    sec_r = rep_r.add_section("Строки")
    for pmode in ("models_with_months", "subplots_by_month", "slices_are_months"):
        sec_r.add_block(ReportBlock.create("plotly_chart", {
            "chart_type": "pie", "data_mode": "rows", "pie_row_mode": pmode,
            "x_col": "Модель", "row_columns": ["Январь_Факт", "Февраль_Факт"],
        }))
    sec_r.add_block(ReportBlock.create("plotly_chart", {
        "chart_type": "bar", "data_mode": "rows", "row_multi_mode": "combined", "row_multi_func": "sub",
        "x_col": "Модель", "row_columns": ["Январь_Факт", "Январь_План", "Февраль_Факт", "Февраль_План"],
    }))

    h1 = render_report(rep, RenderContext(dataframe=df, report=rep, file_manager=fm))
    h2 = render_report(rep_r, RenderContext(dataframe=df_rows, report=rep_r, file_manager=fm_r))
    assert "Ошибка построения графика" not in h1, "Ошибка в одном из 14 типов графиков"
    assert "Ошибка построения графика" not in h2, "Ошибка в режиме data_mode='rows'"
    return f"все {len(chart_types)} типов + 4 режима data_mode='rows' без ошибок"


def test_05_combo_formulas_and_zero_div():
    from src.core.block_factory import RenderContext, render_report
    from src.core.report_model import Report, ReportBlock

    df = make_business_df(120, n_groups=4, n_subgroups=8, n_items=20)
    df.loc[df.index[:30], "План"] = 0.0  # провоцируем деление на ноль
    fm = MockFileManager({"zero.xlsx": {"Данные": df}})
    rep = Report(title="Formula Stress")
    rep.file_manager = fm
    sec = rep.add_section("Формулы")
    sec.add_block(ReportBlock.create("plotly_chart", {
        "title": "Формулы",
        "chart_type": "combo",
        "combo_level1_col": "Категория",
        "combo_level2_col": "Подкатегория",
        "combo_level3_col": "Артикул",
        "date_col": "Дата",
        "fact_col": "Факт",
        "norm_col": "План",
        "combo_series": [
            {"name": "Деление на 0", "source_type": "formula", "formula": "((ФАКТ - ПЛАН) / ПЛАН) * 100", "plot_type": "bar", "y_axis": "y1", "visible": True},
            {"name": "ЕСЛИ условие", "source_type": "formula", "formula": "если(A > B; A - B; 0)", "plot_type": "line", "y_axis": "y2", "visible": True},
            {"name": "Битая формула", "source_type": "formula", "formula": "A + * / ???", "plot_type": "line", "y_axis": "y1", "visible": True},
        ],
    }))
    html = render_report(rep, RenderContext(dataframe=df, report=rep, file_manager=fm))
    assert "Ошибка построения графика" not in html
    import re
    json_blocks = re.findall(r'<script[^>]+type="application/json"[^>]*>(.*?)</script>', html, flags=re.S)
    assert json_blocks, "Не найден JSON-пакет комбо-графика"
    def _reject_const(c):
        raise AssertionError(f"Невалидная константа {c} в JSON графика!")
    for jb in json_blocks:
        json.loads(jb, parse_constant=_reject_const)
    return "деление на 0, вложенные если() и битый синтаксис обработаны безопасно"


def test_06_formula_sandbox_security():
    from src.core.blocks import PivotMatrixBlock, PlotlyChartBlock, _eval_paragraph_template_py

    payloads = [
        "__import__('os').system('echo PWNED')",
        "open('qa_mega_stress_test.py').read()",
        "eval('1+1')",
        "exec('x=1')",
    ]
    ch = PlotlyChartBlock(id="sec1", type="plotly_chart", deviation_mode="custom_formula")
    for p in payloads:
        ch.calc_formula = p
        val = ch._eval_custom_formula(10, 5, 100, 50, 1, 10)
        assert val == 0.0, f"Неожиданный результат для {p}: {val}"
        pval = PivotMatrixBlock._eval_pivot_formula(p, [10.0, 5.0], ["A", "B"])
        assert pval == 0.0, f"Неожиданный результат Pivot для {p}: {pval}"
        tval = _eval_paragraph_template_py("{{" + p + "}}", {"raw_fact": 10, "raw_norm": 5})
        assert "PWNED" not in tval and "import" not in tval

    # Проверка защиты от обхода через __subclasses__
    subclass_payload = "().__class__.__base__.__subclasses__()"
    res_sub = PivotMatrixBlock._eval_pivot_formula(subclass_payload, [1.0], ["A"])
    assert res_sub == 0.0
    return "инъекции __import__/open/eval/subclasses заблокированы во всех 3 вычислителях"


def test_07_paragraph_macros_and_matrix():
    from src.core.block_factory import RenderContext, render_report
    from src.core.report_model import Report, ReportBlock

    df = make_business_df(100, n_groups=3, n_subgroups=6, n_items=15)
    fm = MockFileManager({"p.xlsx": {"Данные": df}})
    rep = Report(title="Para QA")
    rep.file_manager = fm
    sec = rep.add_section("Текст")
    sec.add_block(ReportBlock.create("paragraph", {
        "text": "Записей: {{ count() }} | Факт: {{ sum(Факт) }} | Статус: {{ если(pct > 0; 'Рост'; 'Снижение') }} | Лидер: {{ top_name }}",
        "parent_group_col": "Категория",
        "model_col": "Подкатегория",
        "date_col": "Дата",
        "fact_col": "Факт",
        "norm_col": "План",
    }))
    html = render_report(rep, RenderContext(dataframe=df, report=rep, file_manager=fm))
    assert "Записей: 100" in html, "Макрос count() не сработал"
    assert "ea-dynamic-paragraph" in html and "-matrix" in html, "Динамическая матрица параграфа не сгенерировалась"
    assert "{{" not in html.split("<script")[0], "В отрендеренном тексте остались нераскрытые {{ }}"
    return "макросы count/sum/если и JS-матрица синхронизации работают"


def test_08_pivot_matrix_all_aggs():
    from src.core.block_factory import RenderContext, render_report
    from src.core.report_model import Report, ReportBlock

    df = make_business_df(180, n_groups=4, n_subgroups=8, n_items=25)
    fm = MockFileManager({"piv.xlsx": {"Данные": df}})
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        for agg in ("sum", "mean", "count", "min", "max"):
            rep = Report(title=f"Pivot {agg}")
            rep.file_manager = fm
            sec = rep.add_section("S")
            sec.add_block(ReportBlock.create("pivot_matrix", {
                "row_group_col": "Категория",
                "row_level2_col": "Подкатегория",
                "row_level3_col": "Артикул",
                "col_group_col": "Дата",
                "value_col": "Факт",
                "value_cols": ["Факт", "План"],
                "calc_cols": [{"name": "Δ", "formula": "A - B", "is_pct": False}],
                "agg_func": agg,
                "color_calc_enabled": True,
            }))
            html = render_report(rep, RenderContext(dataframe=df, report=rep, file_manager=fm))
            assert "Ошибка расчета сводной матрицы" not in html, f"Сбой сводной на agg={agg}"
    perf_w = [w for w in caught if "PerformanceWarning" in w.category.__name__]
    assert not perf_w, f"Найдены PerformanceWarning ({len(perf_w)})"
    return "5 функций агрегации, 3 уровня и 0 PerformanceWarning"


def test_09_decomposition_and_geomap():
    from src.core.block_factory import RenderContext, render_report
    from src.core.report_model import Report, ReportBlock

    df = make_business_df(120, n_groups=4, n_subgroups=8, n_items=20)
    fm = MockFileManager({"geo.xlsx": {"Данные": df}})
    rep = Report(title="Deco Geo")
    rep.file_manager = fm
    sec = rep.add_section("Карты и деревья")
    for tm in ("treemap", "sunburst"):
        sec.add_block(ReportBlock.create("decomposition", {
            "tree_mode": tm, "level1_col": "Категория", "level2_col": "Подкатегория", "value_col": "Факт",
        }))
    for mm in ("ranking_bar", "treemap", "choropleth"):
        sec.add_block(ReportBlock.create("geo_map", {
            "map_mode": mm, "loc_col": "Категория", "value_col": "Факт",
        }))
    html = render_report(rep, RenderContext(dataframe=df, report=rep, file_manager=fm))
    assert "Ошибка рендера дерева" not in html and "Ошибка рендера карты" not in html
    return "treemap, sunburst, ranking_bar, choropleth без ошибок"


def test_10_dashboard_filter_chains():
    from src.core.block_factory import RenderContext, render_report
    from src.core.report_model import Report, ReportBlock

    df_main = make_business_df(120, n_groups=4)
    df_other = pd.DataFrame({"X": [1, 2], "Y": [3, 4]})
    fm = MockFileManager({"f.xlsx": {"Другой": df_other, "Данные": df_main}}, "f.xlsx", "Другой")
    rep = Report(title="Filter Chain")
    rep.file_manager = fm
    sec = rep.add_section("Срезы")
    c1 = ReportBlock.create("plotly_chart", {
        "chart_type": "line", "source_file_name": "f.xlsx", "source_sheet": "Данные",
        "x_col": "Категория", "y_col": "Факт, План", "date_col": "Дата", "parent_group_col": "Категория",
    })
    c2 = ReportBlock.create("plotly_chart", {
        "chart_type": "combo", "source_file_name": "f.xlsx", "source_sheet": "Данные",
        "combo_level1_col": "Категория", "combo_level2_col": "Подкатегория", "date_col": "Дата",
        "fact_col": "Факт", "norm_col": "План",
    })
    flt = ReportBlock.create("dashboard_filter", {
        "filter_col": "Категория",
        "target_chart": c1.id,
        "extra_target_charts": c2.id,
        "source_file_name": "deleted.xlsx",
        "source_sheet": "deleted_sheet",
    })
    sec.add_block(ReportBlock.create("container", {"layout": "row", "children": [flt, c1]}))
    sec.add_block(c2)
    html = render_report(rep, RenderContext(dataframe=df_other, report=rep, file_manager=fm))
    assert "(Выберите колонку в Инспекторе)" not in html
    assert f"ea-plotly-{c1.id}" in html and f"ea-plotly-{c2.id}" in html
    return "мульти-привязка к 2 графикам + восстановление битого листа OK"


def test_11_code_generator_compressor():
    from src.core.code_generator import CodeGenerator, OperationCompressor

    ops = [
        types.SimpleNamespace(type="rename_column", params={"column": "A", "new_name": "B"}),
        types.SimpleNamespace(type="rename_column", params={"column": "B", "new_name": "C"}),
        types.SimpleNamespace(type="rename_column", params={"column": "C", "new_name": "A"}),  # должно схлопнуться в 0!
        types.SimpleNamespace(type="cast_column", params={"column": "X", "prev_dtype": "object", "new_dtype": "float64"}),
        types.SimpleNamespace(type="cast_column", params={"column": "X", "prev_dtype": "float64", "new_dtype": "int64"}),
        types.SimpleNamespace(type="edit_cell", params={"row": 0, "column": "X", "new_value": "10"}),
        types.SimpleNamespace(type="edit_cell", params={"row": 0, "column": "X", "new_value": "25"}),
        types.SimpleNamespace(type="delete_columns", params={"columns": ["Trash"]}),
    ]
    comp = OperationCompressor.compress(ops)
    types_out = [o["type"] for o in comp]
    assert "rename_columns_bulk" not in types_out, "Циклическое переименование A->B->C->A не схлопнулось"
    assert types_out.count("cast_column") == 1, "Повторный cast_column не схлопнулся"
    assert types_out.count("edit_cell") == 1, "Повторный edit_cell не схлопнулся"

    code = CodeGenerator("test.xlsx", "Sheet1").generate(ops)
    ast.parse(code)
    assert "EXCEL ANALYZER SIGNATURE" in code
    return "схлопывание операций и генерация защищённого скрипта валидны"


def test_12_standalone_export_cp1251_exec():
    from src.core.code_generator import generate_report_script
    from src.core.report_model import Report, ReportBlock

    df_main = make_business_df(120, n_groups=4)
    df_other = pd.DataFrame({"Other": [1, 2]})
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        xlsx = tmp_dir / "cp1251_test.xlsx"
        with pd.ExcelWriter(xlsx, engine="openpyxl") as wr:
            df_other.to_excel(wr, sheet_name="Сводка", index=False)
            df_main.to_excel(wr, sheet_name="Данные", index=False)

        fm = MockFileManager({"cp1251_test.xlsx": {"Сводка": df_other, "Данные": df_main}}, "cp1251_test.xlsx", "Сводка")
        rep = Report(title="CP1251 Export QA")
        rep.file_manager = fm
        sec = rep.add_section("Экспорт")
        c1 = ReportBlock.create("plotly_chart", {
            "title": "Тренд", "chart_type": "line", "source_file_name": "cp1251_test.xlsx", "source_sheet": "Данные",
            "x_col": "Категория", "y_col": "Факт, План", "date_col": "Дата", "parent_group_col": "Категория",
            "anim_style": "spin", "anim_speed": 700,
        })
        flt = ReportBlock.create("dashboard_filter", {
            "filter_col": "Категория", "target_chart": c1.id, "source_sheet": "НесуществующийЛист",
        })
        sec.add_block(ReportBlock.create("container", {"layout": "row", "children": [flt, c1]}))

        code = generate_report_script(rep, file_name=str(xlsx), sheet_name="Сводка")
        code = code.replace("OPEN_IN_BROWSER = True", "OPEN_IN_BROWSER = False")
        py_file = tmp_dir / "run_cp1251.py"
        py_file.write_text(code, encoding="utf-8")

        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "cp1251"
        env.pop("PYTHONUTF8", None)

        proc = subprocess.run(
            [sys.executable, str(py_file)],
            cwd=str(tmp_dir),
            env=env,
            capture_output=True,
            text=True,
            encoding="cp1251",
            errors="replace",
            timeout=60,
        )
        assert proc.returncode == 0, f"Падение в cp1251-консоли:\n{proc.stderr or proc.stdout}"
        out_html = tmp_dir / "final_dashboard_report.html"
        assert out_html.is_file(), "HTML не создан"
        txt = out_html.read_text(encoding="utf-8")
        assert "(Выберите колонку в Инспекторе)" not in txt, "Срез пуст в выгруженном HTML"
        assert 'data-anim-style="spin"' in txt and 'data-anim-speed="700"' in txt
        return f"выгрузка прошла даже при принудительной cp1251 ({out_html.stat().st_size // 1024} КБ)"


# ============================================================
# БЛОК 2. АУДИТ УТЕЧЕК ПАМЯТИ, КЭША И ДАННЫХ (5 тестов)
# ============================================================

def test_13_memory_and_cache_leak_audit():
    """Проверяет рост DataMemoryCache и удержание удалённых DataFrame в памяти (weakref)."""
    from src.core.block_factory import RenderContext, render_report
    from src.core.blocks import DataMemoryCache
    from src.core.report_model import Report, ReportBlock

    DataMemoryCache.clear_all()
    gc.collect()
    tracemalloc.start()
    rss_start = get_rss_mb()
    mem_start, _ = tracemalloc.get_traced_memory()

    dead_refs = []
    cycles = 25
    for i in range(cycles):
        df_tmp = make_business_df(2000, n_groups=6, n_subgroups=12, n_items=40, seed=i)
        dead_refs.append(weakref.ref(df_tmp))
        fm = MockFileManager({f"file_{i}.xlsx": {"Лист1": df_tmp}})
        rep = Report(title=f"LeakCycle {i}")
        rep.file_manager = fm
        sec = rep.add_section("S")
        sec.add_block(ReportBlock.create("plotly_chart", {
            "chart_type": "combo", "source_file_name": f"file_{i}.xlsx", "source_sheet": "Лист1",
            "combo_level1_col": "Категория", "combo_level2_col": "Подкатегория",
            "date_col": "Дата", "fact_col": "Факт", "norm_col": "План",
        }))
        sec.add_block(ReportBlock.create("data_table", {
            "source_file_name": f"file_{i}.xlsx", "source_sheet": "Лист1",
        }))
        render_report(rep, RenderContext(dataframe=df_tmp, report=rep, file_manager=fm))
        del df_tmp, fm, rep, sec

    gc.collect()
    mem_end, mem_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    rss_end = get_rss_mb()

    snap = cache_snapshot()
    alive_dfs = sum(1 for r in dead_refs if r() is not None)
    leaked_mb = (mem_end - mem_start) / (1024 * 1024)
    total_cache_items = sum(snap.values())

    msg = (
        f"живых «удалённых» DF: {alive_dfs}/{cycles}, записей в DataMemoryCache: {total_cache_items} "
        f"({snap}), Δtraced RAM: +{leaked_mb:.1f} МБ (пик {mem_peak / 1024 / 1024:.1f} МБ, RSS {rss_start:.0f}→{rss_end:.0f} МБ)"
    )
    if alive_dfs > 0 or total_cache_items > 100 or leaked_mb > 25.0:
        LEAK_FINDINGS.append(
            f"УТЕЧКА ПАМЯТИ В DataMemoryCache: {alive_dfs} из {cycles} удалённых DataFrame навсегда застряли в RAM! "
            f"Словари кэша не имеют лимита размера (LRU/WeakKey) и накапливают временные копии Series/HTML: {snap} (+{leaked_mb:.1f} МБ)."
        )
        return "WARN: " + msg
    return msg


def test_14_cache_invalidation_completeness():
    """Проверяет, действительно ли DataMemoryCache.invalidate_file() освобождает все кэши файла."""
    from src.core.blocks import DataMemoryCache, _to_num_series, _extract_month_info

    DataMemoryCache.clear_all()
    df = make_business_df(1500)
    fm = MockFileManager({"inv.xlsx": {"Лист1": df}})
    loaded = DataMemoryCache.get_dataframe(fm, "inv.xlsx", "Лист1")
    _ = _to_num_series(loaded["Факт"])
    _ = DataMemoryCache.get_str_series(loaded, "Категория")
    _ = _extract_month_info(loaded["Дата"])
    _ = DataMemoryCache.get_unique_values(loaded, "Категория")

    before = cache_snapshot()
    DataMemoryCache.invalidate_file("inv.xlsx", "Лист1")
    after = cache_snapshot()

    leftovers = {k: v for k, v in after.items() if v > 0}
    if leftovers:
        LEAK_FINDINGS.append(
            f"НЕПОЛНЫЙ СБРОС КЭША в DataMemoryCache.invalidate_file(): после удаления файла в памяти остались "
            f"осиротевшие кэши {leftovers} (до сброса: {before}). При переоткрытии файлов память растёт бесконечно."
        )
        return f"WARN: после invalidate_file() остались записи в кэше: {leftovers}"
    return "invalidate_file() полностью очистил все кэши"


def test_15_id_reuse_stale_data_risk():
    """Проверяет авто-удаление ключей кэша (weakref.finalize) при удалении Series/DataFrame."""
    from src.core.blocks import DataMemoryCache, _to_num_series

    DataMemoryCache.clear_all()
    df1 = pd.DataFrame({"V": ["10", "20", "30"]})
    s_src = df1["V"]
    s1 = _to_num_series(s_src)
    assert float(s1.sum()) == 60.0
    cached_while_alive = len(DataMemoryCache._num_series_cache)
    assert cached_while_alive == 1, f"Ожидалась 1 запись в кэше, получено {cached_while_alive}"

    del s_src, s1, df1
    gc.collect()
    leftovers = len(DataMemoryCache._num_series_cache)
    if leftovers > 0:
        LEAK_FINDINGS.append(
            f"РИСК ПОДМЕНЫ ДАННЫХ ПО id(): после удаления Series в _num_series_cache осталось {leftovers} записей."
        )
        return f"WARN: после удаления Series осталось {leftovers} записей в кэше"
    return "weakref.finalize автоматически очистил ключ при удалении объекта (риск id-коллизии устранён)"


def test_16_qt_inspector_leak():
    """Проверяет утечки Qt-виджетов и памяти при 60 переключениях BlockInspector."""
    from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication, QWidget
    from src.config.theme import get_theme
    from src.core.report_model import Report, ReportBlock
    from src.ui.block_inspector import BlockInspector

    app = QApplication.instance() or QApplication(sys.argv)

    def _flush_qt():
        loop = QEventLoop()
        QTimer.singleShot(15, loop.quit)
        loop.exec()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()
        gc.collect()

    df = make_business_df(300)
    fm = MockFileManager({"qt.xlsx": {"Данные": df}})
    rep = Report(title="Qt Leak")
    rep.file_manager = fm

    insp = BlockInspector(get_theme())
    insp.report_ref = rep
    insp.file_manager = fm
    insp.set_dataframe(df)

    blocks = [
        ReportBlock.create("plotly_chart", {"chart_type": "combo", "anim_style": "auto", "anim_speed": 480}),
        ReportBlock.create("plotly_chart", {"chart_type": "pie", "pie_display_mode": "dut_single_drill"}),
        ReportBlock.create("pivot_matrix", {}),
        ReportBlock.create("dashboard_filter", {}),
        ReportBlock.create("data_table", {}),
        ReportBlock.create("paragraph", {}),
    ]

    # Прогрев
    for b in blocks:
        insp.show_block(b)
    _flush_qt()
    base_children = len(insp.findChildren(QWidget))
    tracemalloc.start()
    m0, _ = tracemalloc.get_traced_memory()

    for _ in range(10):
        for b in blocks:
            insp.show_block(b)
        app.processEvents()

    insp.show_empty()
    _flush_qt()
    _flush_qt()
    m1, _ = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    end_children = len(insp.findChildren(QWidget))
    delta_kb = (m1 - m0) / 1024.0

    if end_children > base_children + 40 or delta_kb > 4096:
        LEAK_FINDINGS.append(
            f"УТЕЧКА QT-ВИДЖЕТОВ В BlockInspector: после 60 переключений виджетов {base_children}→{end_children}, ΔRAM +{delta_kb:.0f} КБ."
        )
        return f"WARN: виджетов {base_children}→{end_children}, ΔRAM +{delta_kb:.0f} КБ"
    return f"60 переключений чисто: виджетов {base_children}→{end_children}, ΔRAM {delta_kb:+.0f} КБ"


def test_17_encryption_and_no_plaintext_leak():
    """Проверяет шифрование ядра Fernet: защита от неверного пароля, порчи байт и утечки открытого кода."""
    import base64
    import hashlib
    from cryptography.fernet import Fernet, InvalidToken

    sample_src = (ROOT / "src" / "core" / "blocks.py").read_bytes()
    k_good = base64.urlsafe_b64encode(hashlib.sha256(b"StrongPass_2026!").digest())
    k_bad = base64.urlsafe_b64encode(hashlib.sha256(b"WrongPass").digest())

    token = Fernet(k_good).encrypt(sample_src)
    # Проверяем, что в шифротексте нет открытых фрагментов Python-кода
    for secret_str in (b"class PlotlyChartBlock", b"DataMemoryCache", b"def render"):
        assert secret_str not in token, f"Открытый текст {secret_str!r} утёк в шифротекст!"

    # Неверный пароль обязан кидать InvalidToken
    failed_bad = False
    try:
        Fernet(k_bad).decrypt(token)
    except InvalidToken:
        failed_bad = True
    assert failed_bad, "Неверный пароль не вызвал InvalidToken!"

    # Порча 1 байта обязана ловиться
    corrupted = bytearray(token)
    corrupted[len(corrupted) // 2] ^= 0xFF
    failed_corrupt = False
    try:
        Fernet(k_good).decrypt(bytes(corrupted))
    except InvalidToken:
        failed_corrupt = True
    assert failed_corrupt, "Повреждённый .enc не вызвал InvalidToken!"

    dec = Fernet(k_good).decrypt(token)
    assert dec == sample_src
    return f"Fernet шифрование {len(sample_src) // 1024} КБ проверено, утечек открытого кода нет"


# ============================================================
# БЛОК 3. МНОГОПОТОЧНОСТЬ И БЫСТРЫЕ МУТАЦИИ (2 теста)
# ============================================================

def test_18_concurrent_render_stress():
    """Запускает 8 параллельных потоков рендера для проверки потокобезопасности кэша."""
    from src.core.block_factory import RenderContext, render_report
    from src.core.blocks import DataMemoryCache
    from src.core.report_model import Report, ReportBlock

    DataMemoryCache.clear_all()
    df = make_business_df(1500, n_groups=6, n_subgroups=12, n_items=50)
    fm = MockFileManager({"conc.xlsx": {"Данные": df}})

    def _worker(idx: int) -> int:
        rep = Report(title=f"Worker {idx}")
        rep.file_manager = fm
        sec = rep.add_section("S")
        sec.add_block(ReportBlock.create("plotly_chart", {
            "chart_type": "combo", "source_file_name": "conc.xlsx", "source_sheet": "Данные",
            "combo_level1_col": "Категория", "combo_level2_col": "Подкатегория",
            "date_col": "Дата", "fact_col": "Факт", "norm_col": "План",
        }))
        sec.add_block(ReportBlock.create("pivot_matrix", {
            "source_file_name": "conc.xlsx", "source_sheet": "Данные",
            "row_group_col": "Категория", "row_level2_col": "Подкатегория", "value_col": "Факт",
        }))
        html = render_report(rep, RenderContext(dataframe=df, report=rep, file_manager=fm))
        assert "Ошибка" not in html
        return len(html)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futs = [pool.submit(_worker, i) for i in range(16)]
        sizes = [f.result() for f in futs]

    assert all(s > 2000 for s in sizes)
    return f"16 задач в 8 потоках выполнены без гонок (HTML ~{sizes[0] // 1024} КБ)"


def test_19_rapid_config_mutations_and_cache_hit():
    """Имитирует 30 быстрых изменений настроек блока + проверяет ускорение повторного кэш-хита."""
    from src.core.block_factory import RenderContext, render_report
    from src.core.blocks import DataMemoryCache
    from src.core.report_model import Report, ReportBlock

    DataMemoryCache.clear_all()
    df = make_business_df(3000, n_groups=8, n_subgroups=16, n_items=80)
    fm = MockFileManager({"mut.xlsx": {"Данные": df}})
    rep = Report(title="Mutations")
    rep.file_manager = fm
    sec = rep.add_section("S")
    blk = ReportBlock.create("plotly_chart", {
        "chart_type": "combo", "source_file_name": "mut.xlsx", "source_sheet": "Данные",
        "combo_level1_col": "Категория", "combo_level2_col": "Подкатегория",
        "date_col": "Дата", "fact_col": "Факт", "norm_col": "План",
        "anim_style": "auto", "anim_speed": 480,
    })
    sec.add_block(blk)
    ctx = RenderContext(dataframe=df, report=rep, file_manager=fm)

    # Холодный рендер
    t0 = time.perf_counter()
    h_cold = render_report(rep, ctx)
    t_cold = time.perf_counter() - t0

    # Горячий рендер из _render_html_cache
    t1 = time.perf_counter()
    h_hot = render_report(rep, ctx)
    t_hot = time.perf_counter() - t1
    assert h_cold == h_hot

    # 20 мутаций настроек анимации/палитры/сортировки
    styles = ["auto", "spin", "zoom", "slide_up", "slide_left", "cascade", "fade", "none"]
    speeds = [200, 320, 480, 700, 1000, 1400]
    t2 = time.perf_counter()
    for i in range(20):
        blk.config["anim_style"] = styles[i % len(styles)]
        blk.config["anim_speed"] = speeds[i % len(speeds)]
        blk.config["top_n"] = 5 + (i % 15)
        h = render_report(rep, ctx)
        assert f'data-anim-style="{blk.config["anim_style"]}"' in h
    t_mut = time.perf_counter() - t2

    speedup = (t_cold / t_hot) if t_hot > 1e-6 else 999.0
    return f"холодный {t_cold*1000:.0f}мс → кэш {t_hot*1000:.1f}мс (ускорение {speedup:.0f}x), 20 мутаций за {t_mut:.2f}s"


# ============================================================
# БЛОК 4. КРАШ-ТЕСТ ДВИЖКА ДО ОТКАЗА (Progressive Load-to-Failure)
# ============================================================

def run_crash_test(extreme: bool = False):
    from src.core.block_factory import RenderContext, render_report
    from src.core.blocks import DataMemoryCache
    from src.core.report_model import Report, ReportBlock

    if extreme:
        stages = [
            ("5k (база)", 5_000, 10, 40, 200),
            ("25k (средний)", 25_000, 15, 60, 500),
            ("50k (рабочий)", 50_000, 20, 80, 1_000),
            ("100k (крупный)", 100_000, 25, 100, 2_000),
            ("250k (тяжёлый)", 250_000, 30, 150, 4_000),
            ("500k (предельный)", 500_000, 35, 200, 6_000),
            ("1M (экстрим)", 1_000_000, 40, 250, 10_000),
        ]
        time_limit = 35.0
        html_limit_mb = 150.0
        ram_limit_mb = 4096.0
    else:
        stages = [
            ("5k (база)", 5_000, 10, 40, 200),
            ("25k (средний)", 25_000, 15, 60, 500),
            ("50k (рабочий)", 50_000, 20, 80, 1_000),
            ("100k (крупный)", 100_000, 25, 100, 2_000),
            ("250k (тяжёлый)", 250_000, 30, 150, 4_000),
            ("500k (предельный)", 500_000, 35, 200, 6_000),
            ("50k × Кардинальность (2000 гр.)", 50_000, 2_000, 5_000, 10_000),
        ]
        time_limit = 15.0
        html_limit_mb = 80.0
        ram_limit_mb = 2048.0

    # Отслеживаем компоненты, уже достигшие точки отказа, чтобы остальные могли идти дальше
    broken: dict[str, str] = {}

    print("\n" + "=" * 78)
    print(f"🔥 КРАШ-ТЕСТ ДВИЖКА ДО ОТКАЗА (лимиты: >{time_limit:.0f}s | >{html_limit_mb:.0f} МБ HTML | >{ram_limit_mb:.0f} МБ RAM)")
    print("=" * 78)

    components = [
        ("Combo_3lvl", lambda: ReportBlock.create("plotly_chart", {
            "title": "Combo Crash", "chart_type": "combo",
            "source_file_name": "stress.xlsx", "source_sheet": "Данные",
            "combo_level1_col": "Категория", "combo_level2_col": "Подкатегория", "combo_level3_col": "Артикул",
            "date_col": "Дата", "fact_col": "Факт", "norm_col": "План",
            "combo_series": [
                {"name": "Δ", "source_type": "formula", "formula": "A - B", "plot_type": "bar", "y_axis": "y1", "visible": True},
                {"name": "%", "source_type": "formula", "formula": "((A - B) / B) * 100", "plot_type": "line", "y_axis": "y2", "suffix": "%", "visible": True},
            ],
        })),
        ("Pivot_3lvl", lambda: ReportBlock.create("pivot_matrix", {
            "title": "Pivot Crash", "source_file_name": "stress.xlsx", "source_sheet": "Данные",
            "row_group_col": "Категория", "row_level2_col": "Подкатегория", "row_level3_col": "Артикул",
            "col_group_col": "Дата", "value_col": "Факт", "value_cols": ["Факт", "План"],
            "calc_cols": [{"name": "Откл %", "formula": "((A - B) / B) * 100", "is_pct": True}],
            "color_calc_enabled": True, "top_n": 30,
        })),
        ("DUT_Pie", lambda: ReportBlock.create("plotly_chart", {
            "title": "DUT Crash", "chart_type": "pie", "pie_display_mode": "dut_single_drill",
            "source_file_name": "stress.xlsx", "source_sheet": "Данные",
            "dut_col": "Контроль", "pct_col": "Отклонение_%",
            "parent_group_col": "Категория", "model_col": "Подкатегория", "plate_col": "Артикул",
        })),
        ("DataTable", lambda: ReportBlock.create("data_table", {
            "title": "Registry Crash", "source_file_name": "stress.xlsx", "source_sheet": "Данные",
            "max_rows": 25,
        })),
    ]

    for stage_label, n_rows, n_grp, n_sub, n_it in stages:
        if len(broken) == len(components):
            print(f"\n🛑 Все компоненты достигли порога отказа. Остановка на ступени «{stage_label}».")
            break

        DataMemoryCache.clear_all()
        gc.collect()
        t_gen = time.perf_counter()
        df = make_business_df(n_rows, n_groups=n_grp, n_subgroups=n_sub, n_items=n_it)
        dt_gen = time.perf_counter() - t_gen
        fm = MockFileManager({"stress.xlsx": {"Данные": df}})

        rss_before = get_rss_mb()
        print(f"\n── Ступень: {stage_label} ({n_rows:,} строк, генерация {dt_gen:.2f}s, RAM старт: {rss_before:.0f} МБ) ──")

        row_record = {
            "stage": stage_label,
            "rows": n_rows,
            "rss_before_mb": round(rss_before, 1),
            "results": {},
        }

        for comp_name, factory_fn in components:
            if comp_name in broken:
                row_record["results"][comp_name] = f"SKIP ({broken[comp_name]})"
                print(f"   ⏭ {comp_name:<12} пропущен — предел достигнут ранее ({broken[comp_name]})")
                continue

            rep = Report(title=f"Stress {comp_name}")
            rep.file_manager = fm
            sec = rep.add_section("Load")
            sec.add_block(factory_fn())

            t0 = time.perf_counter()
            try:
                html = render_report(rep, RenderContext(dataframe=df, preview_limit=0, report=rep, file_manager=fm))
                dt = time.perf_counter() - t0
                html_mb = len(html.encode("utf-8")) / (1024 * 1024)
                rss_now = get_rss_mb()

                reason = None
                if dt > time_limit:
                    reason = f"TIMEOUT {dt:.1f}s > {time_limit:.0f}s"
                elif html_mb > html_limit_mb:
                    reason = f"HTML BLOAT {html_mb:.1f} МБ > {html_limit_mb:.0f} МБ"
                elif rss_now > ram_limit_mb:
                    reason = f"RAM LIMIT {rss_now:.0f} МБ > {ram_limit_mb:.0f} МБ"

                if reason:
                    broken[comp_name] = f"{stage_label}: {reason}"
                    status_str = f"💥 {dt:.2f}s | {html_mb:.1f} МБ HTML | {rss_now:.0f} МБ RAM [{reason}]"
                else:
                    status_str = f"✅ {dt:.2f}s | {html_mb:.2f} МБ HTML | {rss_now:.0f} МБ RAM"

                row_record["results"][comp_name] = status_str
                print(f"   {comp_name:<12} {status_str}")
                del html
            except MemoryError:
                dt = time.perf_counter() - t0
                broken[comp_name] = f"{stage_label}: MemoryError ({dt:.1f}s)"
                row_record["results"][comp_name] = f"💥 MemoryError ({dt:.1f}s)"
                print(f"   {comp_name:<12} 💥 MemoryError после {dt:.1f}s")
            except Exception as exc:
                dt = time.perf_counter() - t0
                broken[comp_name] = f"{stage_label}: {type(exc).__name__}: {exc}"
                row_record["results"][comp_name] = f"💥 {type(exc).__name__}: {exc}"
                print(f"   {comp_name:<12} 💥 {type(exc).__name__}: {exc}")
            finally:
                del rep, sec

        row_record["rss_after_mb"] = round(get_rss_mb(), 1)
        row_record["cache_after"] = cache_snapshot()
        CRASH_TABLE.append(row_record)

        del df, fm
        DataMemoryCache.clear_all()
        gc.collect()

    return broken


# ============================================================
# Генерация итогового отчёта qa_stress_report.md
# ============================================================

def write_markdown_report(broken_map: dict[str, str], total_elapsed: float) -> Path:
    passed = sum(1 for r in TEST_LOG if r["status"] == "PASS")
    warns = sum(1 for r in TEST_LOG if r["status"] == "WARN")
    fails = sum(1 for r in TEST_LOG if r["status"] == "FAIL")

    lines = [
        "# Отчёт мега-автотеста, аудита утечек и краш-теста NexGrid",
        "",
        f"- **Дата запуска:** {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}",
        f"- **Общее время прогона:** {total_elapsed:.2f} сек",
        f"- **Итог тестов:** ✅ PASS: {passed} | ⚠ WARN (утечки/риски): {warns} | ❌ FAIL: {fails}",
        "",
        "## 1. Результаты автотестов и аудита",
        "",
        "| Раздел | Тест | Статус | Время | Детали |",
        "| :--- | :--- | :---: | :---: | :--- |",
    ]
    for r in TEST_LOG:
        lines.append(f"| {r['section']} | {r['name']} | {r['status']} | {r['time']:.2f}s | {r['detail']} |")

    lines.extend(["", "## 2. Найденные утечки памяти и риски оптимизации", ""])
    if LEAK_FINDINGS:
        for i, item in enumerate(LEAK_FINDINGS, 1):
            lines.append(f"{i}. {item}")
    else:
        lines.append("Критических утечек памяти и кэша не обнаружено.")

    if CRASH_TABLE:
        lines.extend([
            "",
            "## 3. Таблица краш-теста (нагрузка до отказа)",
            "",
            "| Ступень | Строк | Combo_3lvl | Pivot_3lvl | DUT_Pie | DataTable | RAM после (МБ) |",
            "| :--- | ---: | :--- | :--- | :--- | :--- | ---: |",
        ])
        for row in CRASH_TABLE:
            res = row["results"]
            lines.append(
                f"| {row['stage']} | {row['rows']:,} | {res.get('Combo_3lvl', '—')} | "
                f"{res.get('Pivot_3lvl', '—')} | {res.get('DUT_Pie', '—')} | "
                f"{res.get('DataTable', '—')} | {row['rss_after_mb']} |"
            )

        lines.extend(["", "### Точки отказа (Breaking Points)", ""])
        if broken_map:
            for comp, reason in broken_map.items():
                lines.append(f"- **{comp}**: предел достигнут на `{reason}`")
        else:
            lines.append("- Все компоненты выдержали максимальную нагрузку без превышения порогов!")

    report_path = ROOT / "qa_stress_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def main():
    parser = argparse.ArgumentParser(description="Мега-автотест и краш-тест NexGrid")
    parser.add_argument("--extreme", action="store_true", help="Гнать краш-тест до 1 000 000 строк")
    parser.add_argument("--no-crash", action="store_true", help="Пропустить краш-тест, только юнит/утечки")
    args = parser.parse_args()

    t_all = time.perf_counter()
    print("=" * 78)
    print("🧪 МЕГА-АВТОТЕСТ И АУДИТ УТЕЧЕК NEXGRID")
    print("=" * 78)

    print("\n── БЛОК 1: Функционал и Edge-Case фаззинг ──")
    run_case("Фаззинг", "01. Грязные данные, дубли колонок, NBSP, NaN, Inf", test_01_dirty_data_and_duplicates)
    run_case("Фаззинг", "02. Пустой DataFrame (0 строк) и 1 строка", test_02_empty_and_single_row_df)
    run_case("Безопасность", "03. XSS и спецсимволы в заголовках/категориях", test_03_xss_and_escaping)
    run_case("Графики", "04. Все 14 типов Plotly + 4 режима data_mode='rows'", test_04_all_plotly_chart_types)
    run_case("Формулы", "05. Комбо-формулы, деление на 0, если(), битый синтаксис", test_05_combo_formulas_and_zero_div)
    run_case("Безопасность", "06. Песочница формул (инъекции __import__/open/subclasses)", test_06_formula_sandbox_security)
    run_case("Текст", "07. Макросы ParagraphBlock и матрица синхронизации", test_07_paragraph_macros_and_matrix)
    run_case("Сводная", "08. PivotMatrix (5 агрегаций, 3 уровня, 0 PerformanceWarning)", test_08_pivot_matrix_all_aggs)
    run_case("Визуалы", "09. Дерево декомпозиции и Гео-карта (все режимы)", test_09_decomposition_and_geomap)
    run_case("Срезы", "10. Цепочка срезов + мульти-привязка + битый лист", test_10_dashboard_filter_chains)
    run_case("Экспорт", "11. Компрессор операций и защита CodeGenerator", test_11_code_generator_compressor)
    run_case("Экспорт", "12. Реальный запуск автономного .py в cp1251-консоли", test_12_standalone_export_cp1251_exec)

    print("\n── БЛОК 2: Аудит утечек памяти, кэша и данных ──")
    run_case("Утечки", "13. Утечка RAM и удержание удалённых DF в DataMemoryCache", test_13_memory_and_cache_leak_audit)
    run_case("Утечки", "14. Полнота сброса DataMemoryCache.invalidate_file()", test_14_cache_invalidation_completeness)
    run_case("Утечки", "15. Риск подмены данных по ключам id(obj)", test_15_id_reuse_stale_data_risk)
    run_case("Утечки", "16. Утечка Qt-виджетов при 60 переключениях BlockInspector", test_16_qt_inspector_leak)
    run_case("Защита", "17. Шифрование Fernet: отказ пароля, порча, нет plaintext", test_17_encryption_and_no_plaintext_leak)

    print("\n── БЛОК 3: Конкурентность и быстрые мутации ──")
    run_case("Нагрузка", "18. 16 параллельных рендеров в 8 потоках", test_18_concurrent_render_stress)
    run_case("Нагрузка", "19. 20 быстрых мутаций настроек + замер кэш-хита", test_19_rapid_config_mutations_and_cache_hit)

    broken_map = {}
    if not args.no_crash:
        broken_map = run_crash_test(extreme=args.extreme)

    total_dt = time.perf_counter() - t_all
    report_path = write_markdown_report(broken_map, total_dt)

    passed = sum(1 for r in TEST_LOG if r["status"] == "PASS")
    warns = sum(1 for r in TEST_LOG if r["status"] == "WARN")
    fails = sum(1 for r in TEST_LOG if r["status"] == "FAIL")

    print("\n" + "=" * 78)
    print(f"📊 ИТОГ: ✅ PASS={passed} | ⚠ WARN={warns} | ❌ FAIL={fails} | Время: {total_dt:.2f}s")
    if LEAK_FINDINGS:
        print("\n🚨 ОБНАРУЖЕННЫЕ УТЕЧКИ И УЗКИЕ МЕСТА:")
        for idx, lf in enumerate(LEAK_FINDINGS, 1):
            print(f"  {idx}. {lf}")
    if broken_map:
        print("\n💥 ТОЧКИ ОТКАЗА КРАШ-ТЕСТА:")
        for comp, why in broken_map.items():
            print(f"  - {comp}: {why}")
    print(f"\n📝 Подробный отчёт сохранён: {report_path}")
    print("=" * 78)

    sys.exit(1 if fails > 0 else 0)


if __name__ == "__main__":
    main()