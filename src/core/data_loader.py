"""
Загрузка данных из Excel/CSV файлов.
Поддержка нескольких листов в одном документе (основной + сводные).
"""

from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd
import numpy as np


# ============================================================
# Модель загруженных данных
# ============================================================

@dataclass
class LoadedData:
    """Загруженные данные + метаинформация."""

    source_path: str
    sheet_name: Optional[str]
    dataframe: pd.DataFrame
    columns: list[str]
    dtypes: dict[str, str]
    rows_count: int
    cols_count: int

    column_order: list[str] = field(default_factory=list)
    visible_columns: list[str] = field(default_factory=list)
    column_meta: dict = field(default_factory=dict)
    column_filters: dict = field(default_factory=dict)

    # Дополнительные листы того же файла: {имя_листа: DataFrame}
    extra_sheets: dict = field(default_factory=dict)

    # Спецификации сводных таблиц: {имя_листа: spec}
    pivot_specs: dict = field(default_factory=dict)

    # ★ По-листовое хранилище метаданных: {имя_листа: {...}}
    sheet_states: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.column_order:
            self.column_order = list(self.columns)
        if not self.visible_columns:
            self.visible_columns = list(self.columns)
        if not self.column_meta:
            self.column_meta = {}
        if not self.column_filters:
            self.column_filters = {}
        if not self.extra_sheets:
            self.extra_sheets = {}
        if not self.pivot_specs:
            self.pivot_specs = {}
        if not self.sheet_states:
            self.sheet_states = {}

    # ============================================================
    # Листы
    # ============================================================

    def list_sheets(self) -> list[str]:
        """Все листы: активный + дополнительные."""
        names = [self.sheet_name or "Sheet1"]
        for n in self.extra_sheets.keys():
            if n not in names:
                names.append(n)
        return names

    def add_sheet(self, name: str, df: pd.DataFrame):
        """Добавить дополнительный лист."""
        if not name:
            return
        current = self.sheet_name or "Sheet1"
        if name == current:
            return
        self.extra_sheets[name] = df

    def rename_sheet(self, old_name: str, new_name: str) -> tuple[bool, str]:
        """
        Переименовать лист.
        Обновляет: sheet_name / extra_sheets / pivot_specs / sheet_states,
        а также ссылки source_sheet в чужих сводных.
        """
        if not new_name:
            return False, "Пустое имя листа"
        new_name = new_name.strip()
        if not new_name:
            return False, "Пустое имя листа"
        if new_name == old_name:
            return False, "Имя не изменилось"
        if len(new_name) > 31:
            return False, "Имя листа не может быть длиннее 31 символа"
        for ch in ':\\/?*[]':
            if ch in new_name:
                return False, f"Недопустимый символ в имени: {ch}"

        if new_name in self.list_sheets():
            return False, f"Лист «{new_name}» уже существует"

        current = self.sheet_name or "Sheet1"

        if old_name == current:
            # Переименовываем активный
            self.sheet_name = new_name
        elif old_name in self.extra_sheets:
            # Переименовываем в extra_sheets, сохраняя порядок
            new_extra = {}
            for k, v in self.extra_sheets.items():
                if k == old_name:
                    new_extra[new_name] = v
                else:
                    new_extra[k] = v
            self.extra_sheets = new_extra
        else:
            return False, f"Лист «{old_name}» не найден"

        # Спецификация сводной (если переименовываем саму сводную)
        if old_name in self.pivot_specs:
            new_specs = {}
            for k, v in self.pivot_specs.items():
                if k == old_name:
                    new_specs[new_name] = v
                else:
                    new_specs[k] = v
            self.pivot_specs = new_specs

        # Метаданные листа (если лист неактивный)
        if old_name in self.sheet_states:
            self.sheet_states[new_name] = self.sheet_states.pop(old_name)

        # Ссылки на этот лист в других сводных (source_sheet)
        for _spec in self.pivot_specs.values():
            if _spec.get("source_sheet") == old_name:
                _spec["source_sheet"] = new_name

        return True, f"Лист «{old_name}» → «{new_name}»"

    def switch_sheet(self, name: str) -> bool:
        """
        Переключить активный лист.
        Текущий активный уходит в extra_sheets вместе со своими метаданными,
        целевой становится основным; его метаданные восстанавливаются.
        """
        current = self.sheet_name or "Sheet1"
        if name == current:
            return False
        if name not in self.extra_sheets:
            return False

        # ★ Сохраняем метаданные текущего листа
        self.sheet_states[current] = {
            "column_meta":    dict(self.column_meta),
            "column_filters": dict(self.column_filters),
            "column_order":   list(self.column_order),
            "visible_columns": list(self.visible_columns),
        }

        # swap данных
        current_df = self.dataframe
        target_df = self.extra_sheets.pop(name)
        self.extra_sheets[current] = current_df

        # активируем целевой
        self.dataframe = target_df
        self.sheet_name = name
        self.columns = list(target_df.columns)
        self.dtypes = {c: str(t) for c, t in target_df.dtypes.items()}
        self.rows_count = len(target_df)
        self.cols_count = len(target_df.columns)

        # ★ Восстанавливаем метаданные целевого листа
        saved = self.sheet_states.pop(name, None)
        if saved:
            self.column_meta    = saved["column_meta"]
            self.column_filters = saved["column_filters"]
            self.column_order   = [c for c in saved["column_order"] if c in self.columns]
            self.visible_columns = [c for c in saved["visible_columns"] if c in self.columns]
            # подстраховка, если что-то потерялось
            for c in self.columns:
                if c not in self.column_order:
                    self.column_order.append(c)
        else:
            self.column_meta = {}
            self.column_filters = {}
            self.column_order = list(target_df.columns)
            self.visible_columns = list(target_df.columns)

        self.invalidate_cache()
        return True

    def get_sheets_for_save(self) -> list[tuple[str, pd.DataFrame]]:
        """Список (имя_листа, DataFrame) для сохранения в XLSX."""
        result = []
        current = self.sheet_name or "Sheet1"
        result.append((current, self.dataframe))
        for n, df in self.extra_sheets.items():
            if n != current:
                result.append((n, df))
        return result

    # ============================================================
    # Мета-данные колонок
    # ============================================================

    def get_display_name(self, column: str) -> str:
        meta = self.column_meta.get(column)
        if meta:
            return meta.get("display_name", column)
        return column

    def set_display_name(self, column: str, display_name: str):
        if column not in self.columns:
            return
        if column not in self.column_meta:
            self.column_meta[column] = {}
        self.column_meta[column]["display_name"] = display_name

    def reset_column_meta(self, column: str):
        self.column_meta.pop(column, None)

    # ============================================================
    # Преобразование типа
    # ============================================================

    def cast_column(self, column: str, new_dtype: str) -> tuple[bool, str]:
        if column not in self.columns:
            return False, f"Колонка '{column}' не найдена"
        try:
            series = self.dataframe[column]

            if new_dtype in ("int", "int64"):
                converted = pd.to_numeric(series, errors="coerce")
                if converted.isna().all():
                    return False, "Не удалось преобразовать в число"
                if converted.isna().any():
                    self.dataframe[column] = converted
                    self.dtypes[column] = "float64"
                    return True, "Преобразовано в float64 (есть пустые значения)"
                self.dataframe[column] = converted.astype("int64")
                self.dtypes[column] = "int64"
                return True, "Преобразовано в int64"

            elif new_dtype in ("float", "float64"):
                converted = pd.to_numeric(series, errors="coerce")
                if converted.isna().all():
                    return False, "Не удалось преобразовать в число"
                self.dataframe[column] = converted
                self.dtypes[column] = "float64"
                return True, "Преобразовано в float64"

            elif new_dtype in ("str", "string", "object"):
                self.dataframe[column] = series.astype(str)
                self.dtypes[column] = "str"
                return True, "Преобразовано в строку"

            elif new_dtype in ("datetime", "datetime64[ns]"):
                converted = pd.to_datetime(series, errors="coerce")
                if converted.isna().all():
                    return False, "Не удалось преобразовать в дату"
                self.dataframe[column] = converted
                self.dtypes[column] = "datetime64[ns]"
                return True, "Преобразовано в дату"

            elif new_dtype in ("bool", "boolean"):
                converted = series.astype(bool)
                self.dataframe[column] = converted
                self.dtypes[column] = "bool"
                return True, "Преобразовано в boolean"

            return False, f"Неизвестный тип: {new_dtype}"

        except Exception as e:
            return False, f"Ошибка: {type(e).__name__}: {e}"

    # ============================================================
    # РАЗДЕЛЕНИЕ КОЛОНКИ
    # ============================================================

    def split_column(
        self,
        column: str,
        mode: str,
        params: dict,
        new_names: list[str],
        delete_original: bool = False,
    ) -> tuple[bool, str]:
        print(f"[split_column] column='{column}', mode='{mode}'")

        if column not in self.columns:
            return False, f"Колонка '{column}' не найдена"

        if len(new_names) != 2:
            return False, "Нужно ровно 2 имени колонок"

        for name in new_names:
            if not name or not name.strip():
                return False, "Все имена колонок должны быть заполнены"

        if new_names[0] == new_names[1]:
            return False, "Имена колонок должны быть разными"

        existing_to_check = set(self.columns)
        if delete_original:
            existing_to_check.discard(column)

        for name in new_names:
            if name in existing_to_check:
                return False, f"Колонка '{name}' уже существует"

        try:
            series = self.dataframe[column]

            if mode == "marker":
                result = series.apply(lambda v: self._split_by_marker(v, **params))
            elif mode == "position":
                result = series.apply(lambda v: self._split_by_position(v, **params))
            elif mode == "separator":
                result = series.apply(lambda v: self._split_by_separator(v, **params))
            else:
                return False, f"Неизвестный режим: {mode}"

            parts_1 = result.apply(lambda t: t[0])
            parts_2 = result.apply(lambda t: t[1])

            orig_index = self.columns.index(column)
            name_1, name_2 = new_names[0], new_names[1]

            if delete_original:
                self.dataframe = self.dataframe.drop(columns=[column])
                del self.dtypes[column]
                self.columns.remove(column)
                self.column_order.remove(column)
                self.visible_columns.remove(column)
                self.reset_column_meta(column)
                orig_index = min(orig_index, len(self.columns))

            self.dataframe.insert(orig_index, name_1, parts_1)
            self.dataframe.insert(orig_index + 1, name_2, parts_2)

            self.dtypes[name_1] = str(parts_1.dtype)
            self.dtypes[name_2] = str(parts_2.dtype)

            self.columns.insert(orig_index, name_1)
            self.columns.insert(orig_index + 1, name_2)

            pos_in_order = min(orig_index, len(self.column_order))
            self.column_order.insert(pos_in_order, name_1)
            self.column_order.insert(pos_in_order + 1, name_2)

            pos_visible = min(orig_index, len(self.visible_columns))
            self.visible_columns.insert(pos_visible, name_1)
            self.visible_columns.insert(pos_visible + 1, name_2)

            self.cols_count = len(self.columns)

            return True, f"Колонка «{column}» разделена на «{name_1}» и «{name_2}»"

        except Exception as e:
            import traceback
            traceback.print_exc()
            return False, f"Ошибка: {type(e).__name__}: {e}"

    def _split_by_marker(
        self,
        value,
        marker: str,
        before: bool = True,
        keep_spaces: bool = False,
    ) -> tuple[str, str]:
        if pd.isna(value):
            return "", ""
        s = str(value)
        if not marker:
            return s, ""
        pos = s.find(marker)
        if pos < 0:
            result = s if keep_spaces else s.strip()
            return result, ""
        if before:
            part_1 = s[:pos]
            part_2 = s[pos:]
        else:
            part_1 = s[:pos + len(marker)]
            part_2 = s[pos + len(marker):]
        if not keep_spaces:
            part_1 = part_1.strip()
            part_2 = part_2.strip()
        return part_1, part_2

    def _split_by_position(
        self,
        value,
        position: int,
        keep_spaces: bool = False,
    ) -> tuple[str, str]:
        if pd.isna(value):
            return "", ""
        s = str(value)
        if position <= 0 or position >= len(s):
            result = s if keep_spaces else s.strip()
            return result, ""
        part_1 = s[:position]
        part_2 = s[position:]
        if not keep_spaces:
            part_1 = part_1.strip()
            part_2 = part_2.strip()
        return part_1, part_2

    def _split_by_separator(
        self,
        value,
        separator: str,
        keep_spaces: bool = False,
    ) -> tuple[str, str]:
        if pd.isna(value):
            return "", ""
        s = str(value)
        if not separator:
            return s, ""
        pos = s.find(separator)
        if pos < 0:
            result = s if keep_spaces else s.strip()
            return result, ""
        part_1 = s[:pos]
        part_2 = s[pos + len(separator):]
        if not keep_spaces:
            part_1 = part_1.strip()
            part_2 = part_2.strip()
        return part_1, part_2

    # ---------- Разделение по правилам (визуальный режим) ----------

    def split_by_rules(
        self,
        column: str,
        rules: list,
        new_names: list[str],
        delete_original: bool = False,
    ) -> tuple[bool, str]:
        from src.core.rule_detector import RuleDetector

        print(f"[split_by_rules] column='{column}', rules={len(rules)}")

        if column not in self.columns:
            return False, f"Колонка '{column}' не найдена"

        if not rules:
            return False, "Нет правил для применения"

        expected_cols = len(rules) + 1
        if len(new_names) != expected_cols:
            return False, f"Нужно {expected_cols} имён колонок, получено {len(new_names)}"

        for name in new_names:
            if not name or not name.strip():
                return False, "Все имена колонок должны быть заполнены"

        if len(set(new_names)) != len(new_names):
            return False, "Имена колонок должны быть разными"

        existing_to_check = set(self.columns)
        if delete_original:
            existing_to_check.discard(column)

        for name in new_names:
            if name in existing_to_check:
                return False, f"Колонка '{name}' уже существует"

        try:
            series = self.dataframe[column]
            rows_parts = series.apply(
                lambda v: self._apply_rules_to_value(v, rules)
            )
            parts_lists = rows_parts.tolist()

            new_columns_data = []
            for i in range(expected_cols):
                col_data = [parts[i] if i < len(parts) else "" for parts in parts_lists]
                new_columns_data.append(col_data)

            orig_index = self.columns.index(column)

            if delete_original:
                self.dataframe = self.dataframe.drop(columns=[column])
                del self.dtypes[column]
                self.columns.remove(column)
                self.column_order.remove(column)
                self.visible_columns.remove(column)
                self.reset_column_meta(column)
                orig_index = min(orig_index, len(self.columns))

            for i, name in enumerate(new_names):
                self.dataframe.insert(orig_index + i, name, new_columns_data[i])
                self.dtypes[name] = "str"
                self.columns.insert(orig_index + i, name)

            pos_in_order = min(orig_index, len(self.column_order))
            for i, name in enumerate(new_names):
                self.column_order.insert(pos_in_order + i, name)

            pos_visible = min(orig_index, len(self.visible_columns))
            for i, name in enumerate(new_names):
                self.visible_columns.insert(pos_visible + i, name)

            self.cols_count = len(self.columns)

            names_str = ", ".join(f"«{n}»" for n in new_names)
            return True, f"Колонка «{column}» разделена на {len(new_names)} частей: {names_str}"

        except Exception as e:
            import traceback
            traceback.print_exc()
            return False, f"Ошибка: {type(e).__name__}: {e}"

    def _apply_rules_to_value(self, value, rules: list) -> list[str]:
        import pandas as pd
        from src.core.rule_detector import RuleDetector

        expected_cols = len(rules) + 1

        if pd.isna(value):
            return [""] * expected_cols

        s = str(value)

        positions = []
        for rule in rules:
            pos = RuleDetector._find_split_position(rule, s)
            if pos is not None and 0 < pos < len(s):
                positions.append(pos)

        positions = sorted(set(positions))

        if not positions:
            return [s.strip()] + [""] * (expected_cols - 1)

        parts = []
        prev = 0
        for pos in positions:
            parts.append(s[prev:pos].strip())
            prev = pos
        parts.append(s[prev:].strip())

        while len(parts) < expected_cols:
            parts.append("")

        return parts[:expected_cols]

    # ---------- Preview разделения ----------

    def preview_split(
        self,
        column: str,
        mode: str,
        params: dict,
        n: int = 5,
    ) -> list[tuple[str, str]]:
        if column not in self.columns:
            return []
        series = self.dataframe[column].head(n)
        try:
            if mode == "marker":
                result = series.apply(lambda v: self._split_by_marker(v, **params))
            elif mode == "position":
                result = series.apply(lambda v: self._split_by_position(v, **params))
            elif mode == "separator":
                result = series.apply(lambda v: self._split_by_separator(v, **params))
            else:
                return []
            return list(result)
        except Exception as e:
            print(f"[preview_split] Ошибка: {e}")
            return []

    # ============================================================
    # ФИЛЬТРЫ
    # ============================================================

    def set_column_filter(self, column: str, allowed_values: list):
        if not allowed_values:
            self.column_filters.pop(column, None)
        else:
            self.column_filters[column] = list(allowed_values)
        self.invalidate_cache()

    def clear_column_filter(self, column: str):
        self.column_filters.pop(column, None)
        self.invalidate_cache()

    def clear_all_filters(self):
        self.column_filters.clear()
        self.invalidate_cache()

    def has_any_filter(self) -> bool:
        return bool(self.column_filters)

    def get_filtered_indices(self) -> list:
        n = len(self.dataframe)
        if not self.column_filters:
            return list(range(n))

        mask = np.ones(n, dtype=bool)
        df = self.dataframe

        for col, allowed in self.column_filters.items():
            if col not in df.columns:
                continue
            allowed_strs = set(str(v) for v in allowed)
            include_na = "—" in allowed_strs

            series = df[col]
            str_series = series.astype(str)

            col_mask = str_series.isin(allowed_strs).to_numpy(dtype=bool, na_value=False)
            if include_na:
                col_mask |= series.isna().to_numpy(dtype=bool, na_value=False)

            mask &= col_mask

        return np.nonzero(mask)[0].tolist()

    # ============================================================
    # Preview данных
    # ============================================================

    def get_preview(self, n: int = 20, columns: list[str] | None = None) -> pd.DataFrame:
        cols = columns if columns is not None else self.visible_columns
        cols = [c for c in cols if c in self.columns]
        return self.dataframe[cols].head(n)

    def get_renamed_preview(self, n: int = 20) -> pd.DataFrame:
        df_head = self.dataframe.head(n)
        cols = [c for c in self.visible_columns if c in self.columns]
        df = df_head[cols].copy()
        rename_map = {c: self.get_display_name(c) for c in df.columns}
        return df.rename(columns=rename_map)

    # ============================================================
    # Видимость
    # ============================================================

    def show_all_columns(self):
        self.visible_columns = [c for c in self.column_order if c in self.columns]

    def hide_all_columns(self):
        self.visible_columns = []

    def toggle_column(self, column: str, visible: bool):
        if column not in self.columns:
            return

        if visible:
            if column not in self.visible_columns:
                col_pos = self.column_order.index(column)
                insert_pos = len(self.visible_columns)
                for i, vc in enumerate(self.visible_columns):
                    if vc in self.column_order and self.column_order.index(vc) > col_pos:
                        insert_pos = i
                        break
                self.visible_columns.insert(insert_pos, column)
        else:
            if column in self.visible_columns:
                self.visible_columns.remove(column)

    def is_column_visible(self, column: str) -> bool:
        return column in self.visible_columns

    # ============================================================
    # Порядок
    # ============================================================

    def reorder_visible_columns(self, new_visible_order: list[str]):
        self.visible_columns = [c for c in new_visible_order if c in self.columns]
        hidden = [c for c in self.column_order if c not in self.visible_columns]
        self.column_order = list(self.visible_columns) + hidden

    # ============================================================
    # Информация
    # ============================================================

    def get_columns_info(self) -> list[dict]:
        if hasattr(self, "_columns_info_cache"):
            return self._columns_info_cache

        info = []
        df = self.dataframe
        meta = self.column_meta
        visible_set = set(self.visible_columns)
        dtypes = self.dtypes

        for col in self.columns:
            series = df[col]
            m = meta.get(col)
            display_name = m.get("display_name", col) if m else col

            info.append({
                "name": col,
                "display_name": display_name,
                "dtype": str(dtypes.get(col, "unknown")),
                "n_unique": int(series.nunique(dropna=True)),
                "n_nulls": int(series.isna().sum()),
                "visible": col in visible_set,
            })

        self._columns_info_cache = info
        return info

    def get_columns_basic(self) -> list[dict]:
        """
        Лёгкая информация по колонкам — БЕЗ nunique/nulls.
        Используется в дереве колонок.
        """
        info = []
        meta = self.column_meta
        visible_set = set(self.visible_columns)
        dtypes = self.dtypes

        for col in self.columns:
            m = meta.get(col)
            display_name = m.get("display_name", col) if m else col
            info.append({
                "name": col,
                "display_name": display_name,
                "dtype": str(dtypes.get(col, "unknown")),
                "visible": col in visible_set,
            })
        return info

    def get_column_info(self, column: str) -> dict | None:
        for info in self.get_columns_info():
            if info["name"] == column:
                return info
        return None

    def invalidate_cache(self):
        if hasattr(self, "_columns_info_cache"):
            del self._columns_info_cache


# ============================================================
# Загрузчик
# ============================================================

class DataLoader:
    """Загружает данные из файлов."""

    SUPPORTED_EXTENSIONS = {".xlsx", ".xls"}

    @classmethod
    def get_excel_sheets(cls, filepath: str) -> list[str]:
        try:
            xls = pd.ExcelFile(filepath)
            return xls.sheet_names
        except Exception as e:
            raise RuntimeError(f"Не удалось прочитать листы: {e}")

    @classmethod
    def load_excel(cls, filepath: str, sheet_name: str | int = 0) -> LoadedData:
        path = Path(filepath)

        if not path.exists():
            raise FileNotFoundError(f"Файл не найден: {filepath}")

        if path.suffix.lower() not in cls.SUPPORTED_EXTENSIONS:
            raise ValueError(f"Неподдерживаемый формат: {path.suffix}")

        # ★ Быстрый движок: python-calamine (Rust) — в 10-30 раз быстрее
        #   openpyxl на больших файлах (100k+ строк).
        #   Если calamine не установлен — fallback на openpyxl.
        import time as _time
        t0 = _time.time()
        engine = None
        try:
            import python_calamine
            engine = "calamine"
        except ImportError:
            engine = None

        try:
            if engine:
                df = pd.read_excel(filepath, sheet_name=sheet_name, engine="calamine")
            else:
                df = pd.read_excel(filepath, sheet_name=sheet_name)
        except Exception:
            # calamine иногда не умеет какие-то фичи — откатываемся
            df = pd.read_excel(filepath, sheet_name=sheet_name)

        t1 = _time.time()
        print(f"[DataLoader] read_excel: {t1 - t0:.2f} сек, "
              f"{len(df)} строк, {len(df.columns)} колонок (engine={engine or 'default'})")

        df = df.dropna(axis=1, how="all")
        df = df.dropna(axis=0, how="all")

        dtypes = {col: str(dtype) for col, dtype in df.dtypes.items()}

        return LoadedData(
            source_path=str(path),
            sheet_name=str(sheet_name) if sheet_name is not None else None,
            dataframe=df,
            columns=list(df.columns),
            dtypes=dtypes,
            rows_count=len(df),
            cols_count=len(df.columns),
        )

    @classmethod
    def load(cls, filepath: str, sheet_name: str | int = 0) -> LoadedData:
        return cls.load_excel(filepath, sheet_name)