"""
Команды для Undo/Redo.
Каждая команда умеет do() и undo() и пишет операцию в историю файла.
"""

from src.core.history import Command


# ============================================================
# Утилита — запись операции
# ============================================================

def _log_operation(data, op_type: str, params: dict):
    """Записать операцию в историю файла (если есть)."""
    if data is None:
        return
    ops = getattr(data, "operations", None)
    if ops is None:
        return
    file_id = getattr(data, "file_id", "")
    ops.add_new(op_type, params, file_id)


# ============================================================
# Показать/скрыть колонку
# ============================================================

class ToggleColumnCommand(Command):
    """Показать или скрыть одну колонку."""

    def __init__(self, data, column: str, visible: bool, on_change):
        self._data = data
        self._column = column
        self._visible = visible
        self._on_change = on_change
        self._prev_visible = None

    def do(self):
        self._prev_visible = self._data.is_column_visible(self._column)
        self._data.toggle_column(self._column, self._visible)

        _log_operation(self._data, "toggle_column", {
            "column": self._column,
            "visible": self._visible,
        })


    def undo(self):
        if self._prev_visible is not None:
            self._data.toggle_column(self._column, self._visible)
            ops = getattr(self._data, "operations", None)
            if ops:
                ops.pop_last()

    def description(self) -> str:
        action = "Показать" if self._visible else "Скрыть"
        name = self._data.get_display_name(self._column)
        return f"{action} колонку «{name}»"


# ============================================================
# Переименовать колонку
# ============================================================

class RenameColumnCommand(Command):
    """Изменить отображаемое имя колонки."""

    def __init__(self, data, column: str, new_name: str, on_change):
        self._data = data
        self._column = column
        self._new_name = new_name
        self._on_change = on_change
        self._prev_name = None

    def do(self):
        self._prev_name = self._data.get_display_name(self._column)
        self._data.set_display_name(self._column, self._new_name)

        _log_operation(self._data, "rename_column", {
            "column": self._column,
            "new_name": self._new_name,
            "prev_name": self._prev_name,
        })

        # ★ Раньше on_change не вызывался — из-за этого UI (дерево колонок,
        # таблица, инспектор) не перерисовывался после переименования.
        self._data.invalidate_cache()
        if self._on_change:
            self._on_change()


    def undo(self):
        if self._prev_name is not None:
            if self._prev_name == self._column:
                if self._column in self._data.column_meta:
                    self._data.column_meta[self._column].pop("display_name", None)
            else:
                self._data.set_display_name(self._column, self._prev_name)

            ops = getattr(self._data, "operations", None)
            if ops:
                ops.pop_last()
            self._data.invalidate_cache()

    def description(self) -> str:
        return f"Переименовать «{self._prev_name or self._column}» → «{self._new_name}»"


# ============================================================
# Сменить тип данных
# ============================================================

class CastColumnCommand(Command):
    """Преобразовать тип данных колонки."""

    def __init__(self, data, column: str, new_dtype: str, on_change):
        self._data = data
        self._column = column
        self._new_dtype = new_dtype
        self._on_change = on_change
        self._backup_series = None
        self._backup_dtype = None
        self._ok = False
        self._message = ""

    def do(self):
        self._backup_series = self._data.dataframe[self._column].copy()
        self._backup_dtype = self._data.dtypes.get(self._column, "")

        self._ok, self._message = self._data.cast_column(self._column, self._new_dtype)

        if self._ok:
            _log_operation(self._data, "cast_column", {
                "column": self._column,
                "new_dtype": self._new_dtype,
                "prev_dtype": self._backup_dtype,
            })

            self._data.invalidate_cache()
            self._on_change()
        else:
            self._data.dataframe[self._column] = self._backup_series
            self._data.dtypes[self._column] = self._backup_dtype
            self._data.invalidate_cache()

    def undo(self):
        if not self._ok or self._backup_series is None:
            return

        self._data.dataframe[self._column] = self._backup_series
        self._data.dtypes[self._column] = self._backup_dtype

        ops = getattr(self._data, "operations", None)
        if ops:
            ops.pop_last()

        self._data.invalidate_cache()
        self._on_change()

    def description(self) -> str:
        name = self._data.get_display_name(self._column)
        return f"Преобразовать тип «{name}» в {self._new_dtype}"

    @property
    def was_successful(self) -> bool:
        return self._ok

    @property
    def message(self) -> str:
        return self._message


# ============================================================
# Изменить порядок колонок
# ============================================================

class ReorderColumnsCommand(Command):
    """Изменить порядок видимых колонок."""

    def __init__(self, data, new_order: list, on_change):
        self._data = data
        self._new_order = list(new_order)
        self._on_change = on_change
        self._prev_order = None

    def do(self):
        self._prev_order = list(self._data.visible_columns)
        self._data.reorder_visible_columns(self._new_order)

        _log_operation(self._data, "reorder_columns", {
            "new_order": self._new_order,
            "prev_order": self._prev_order,
        })

        self._data.invalidate_cache()
        self._on_change()

    def undo(self):
        if self._prev_order is not None:
            self._data.reorder_visible_columns(self._prev_order)
            ops = getattr(self._data, "operations", None)
            if ops:
                ops.pop_last()
            self._data.invalidate_cache()
            self._on_change()

    def description(self) -> str:
        return "Изменить порядок колонок"


# ============================================================
# Разделить колонку
# ============================================================

class SplitColumnCommand(Command):
    """Разделить колонку. Сохраняет backup DataFrame."""

    def __init__(self, data, column: str, mode: str, params: dict,
                 new_names: list, delete_original: bool, on_change):
        self._data = data
        self._column = column
        self._mode = mode
        self._params = params
        self._new_names = list(new_names)
        self._delete_original = delete_original
        self._on_change = on_change

        self._backup_df = None
        self._backup_columns = None
        self._backup_dtypes = None
        self._backup_meta = None
        self._backup_column_order = None
        self._backup_visible = None

        self._ok = False
        self._message = ""

    def do(self):
        self._backup_df = self._data.dataframe.copy()
        self._backup_columns = list(self._data.columns)
        self._backup_dtypes = dict(self._data.dtypes)
        self._backup_meta = {k: dict(v) for k, v in self._data.column_meta.items()}
        self._backup_column_order = list(self._data.column_order)
        self._backup_visible = list(self._data.visible_columns)

        if self._mode == "visual":
            self._ok, self._message = self._data.split_by_rules(
                self._column, self._params.get("rules", []),
                self._new_names, self._delete_original,
            )
        else:
            self._ok, self._message = self._data.split_column(
                self._column, self._mode, self._params,
                self._new_names, self._delete_original,
            )

        if self._ok:
            _log_operation(self._data, "split_column", {
                "column": self._column,
                "mode": self._mode,
                "params": self._params,
                "new_names": self._new_names,
                "delete_original": self._delete_original,
            })
            self._data.invalidate_cache()
            self._on_change()

    def undo(self):
        if not self._ok or self._backup_df is None:
            return

        self._data.dataframe = self._backup_df
        self._data.columns = self._backup_columns
        self._data.dtypes = self._backup_dtypes
        self._data.column_meta = self._backup_meta
        self._data.column_order = self._backup_column_order
        self._data.visible_columns = self._backup_visible
        self._data.cols_count = len(self._backup_columns)

        ops = getattr(self._data, "operations", None)
        if ops:
            ops.pop_last()

        self._data.invalidate_cache()
        self._on_change()

    def description(self) -> str:
        return f"Разделить колонку «{self._column}» на {len(self._new_names)} частей"

    @property
    def was_successful(self) -> bool:
        return self._ok

    @property
    def message(self) -> str:
        return self._message


# ============================================================
# Изменить ячейку
# ============================================================

class EditCellCommand(Command):
    """Изменение значения одной ячейки."""

    def __init__(self, data, row: int, column: str, new_value, on_change=None):
        self._data = data
        self._row = int(row)
        self._column = column
        self._new_value = new_value
        self._on_change = on_change
        self._prev_value = None
        self._prev_dtype = None

    def do(self):
        try:
            loc = self._data.dataframe.columns.get_loc(self._column)
        except KeyError:
            return

        self._prev_value = self._data.dataframe.iat[self._row, loc]
        self._prev_dtype = self._data.dtypes.get(self._column, "")

        value = self._coerce(self._new_value, self._prev_dtype)
        self._data.dataframe.iat[self._row, loc] = value

        _log_operation(self._data, "edit_cell", {
            "row": self._row,
            "column": self._column,
            "new_value": str(value) if value is not None else "",
            "prev_value": str(self._prev_value) if self._prev_value is not None else "",
        })

        self._data.invalidate_cache()
        if self._on_change:
            self._on_change()

    def undo(self):
        try:
            loc = self._data.dataframe.columns.get_loc(self._column)
            self._data.dataframe.iat[self._row, loc] = self._prev_value
        except Exception:
            return

        ops = getattr(self._data, "operations", None)
        if ops:
            ops.pop_last()

        self._data.invalidate_cache()
        if self._on_change:
            self._on_change()

    def description(self) -> str:
        name = self._data.get_display_name(self._column)
        return f"Изменить ячейку «{name}» (строка {self._row + 1})"

    def _coerce(self, value, dtype: str):
        if value is None:
            return None
        if isinstance(value, str) and value.strip() == "":
            return None
        try:
            if "int" in dtype:
                return int(float(value))
            if "float" in dtype:
                return float(value)
            if "datetime" in dtype:
                import pandas as pd
                return pd.to_datetime(value)
            if "bool" in dtype:
                s = str(value).strip().lower()
                return s in ("1", "true", "yes", "да", "истина")
        except Exception:
            pass
        return value


# ============================================================
# Удалить колонки
# ============================================================

class DeleteColumnsCommand(Command):
    """Удаление одной или нескольких колонок."""

    def __init__(self, data, columns: list, on_change=None):
        self._data = data
        self._columns = list(columns)
        self._on_change = on_change

        self._backup_df = None
        self._backup_columns = None
        self._backup_dtypes = None
        self._backup_meta = None
        self._backup_order = None
        self._backup_visible = None

        self._ok = False
        self._message = ""

    def do(self):
        missing = [c for c in self._columns if c not in self._data.columns]
        if missing:
            self._message = f"Колонки не найдены: {missing}"
            return

        if not self._columns:
            self._message = "Не указано ни одной колонки"
            return

        self._backup_df = self._data.dataframe.copy()
        self._backup_columns = list(self._data.columns)
        self._backup_dtypes = dict(self._data.dtypes)
        self._backup_meta = {k: dict(v) for k, v in self._data.column_meta.items()}
        self._backup_order = list(self._data.column_order)
        self._backup_visible = list(self._data.visible_columns)

        try:
            self._data.dataframe = self._data.dataframe.drop(columns=self._columns)

            for col in self._columns:
                self._data.columns.remove(col)
                self._data.dtypes.pop(col, None)
                self._data.column_meta.pop(col, None)
                if col in self._data.column_order:
                    self._data.column_order.remove(col)
                if col in self._data.visible_columns:
                    self._data.visible_columns.remove(col)

            self._data.cols_count = len(self._data.columns)
            self._ok = True

            _log_operation(self._data, "delete_columns", {
                "columns": list(self._columns),
            })

            self._data.invalidate_cache()
            if self._on_change:
                self._on_change()

            self._message = f"Удалено колонок: {len(self._columns)}"

        except Exception as e:
            self._data.dataframe = self._backup_df
            self._data.columns = self._backup_columns
            self._data.dtypes = self._backup_dtypes
            self._data.column_meta = self._backup_meta
            self._data.column_order = self._backup_order
            self._data.visible_columns = self._backup_visible
            self._data.cols_count = len(self._backup_columns)
            self._message = f"Ошибка: {type(e).__name__}: {e}"

    def undo(self):
        if not self._ok or self._backup_df is None:
            return

        self._data.dataframe = self._backup_df
        self._data.columns = self._backup_columns
        self._data.dtypes = self._backup_dtypes
        self._data.column_meta = self._backup_meta
        self._data.column_order = self._backup_order
        self._data.visible_columns = self._backup_visible
        self._data.cols_count = len(self._backup_columns)

        ops = getattr(self._data, "operations", None)
        if ops:
            ops.pop_last()

        self._data.invalidate_cache()
        if self._on_change:
            self._on_change()

    def description(self) -> str:
        if len(self._columns) == 1:
            name = self._data.get_display_name(self._columns[0]) if self._columns else "?"
            return f"Удалить колонку «{name}»"
        return f"Удалить {len(self._columns)} колонок"

    @property
    def was_successful(self) -> bool:
        return self._ok

    @property
    def message(self) -> str:
        return self._message


# ============================================================
# Удалить строки
# ============================================================

class DeleteRowsCommand(Command):
    """Удаление строк по позиционным индексам (0-based)."""

    def __init__(self, data, rows: list, on_change=None):
        self._data = data
        self._rows = sorted({int(r) for r in rows})
        self._on_change = on_change

        self._backup_df = None
        self._ok = False
        self._message = ""

    def do(self):
        if not self._rows:
            self._message = "Не указано ни одной строки"
            return

        n = len(self._data.dataframe)
        bad = [r for r in self._rows if r < 0 or r >= n]
        if bad:
            self._message = f"Индексы вне диапазона: {bad}"
            return

        self._backup_df = self._data.dataframe.copy()

        try:
            labels_to_drop = self._data.dataframe.index[self._rows]
            self._data.dataframe = (
                self._data.dataframe
                .drop(labels=labels_to_drop)
                .reset_index(drop=True)
            )
            self._data.rows_count = len(self._data.dataframe)

            self._ok = True
            _log_operation(self._data, "delete_rows", {
                "indices": list(self._rows),
            })

            self._data.invalidate_cache()
            if self._on_change:
                self._on_change()

            self._message = f"Удалено строк: {len(self._rows)}"

        except Exception as e:
            self._data.dataframe = self._backup_df
            self._data.rows_count = len(self._backup_df)
            self._message = f"Ошибка: {type(e).__name__}: {e}"

    def undo(self):
        if not self._ok or self._backup_df is None:
            return

        self._data.dataframe = self._backup_df
        self._data.rows_count = len(self._backup_df)

        ops = getattr(self._data, "operations", None)
        if ops:
            ops.pop_last()

        self._data.invalidate_cache()
        if self._on_change:
            self._on_change()

    def description(self) -> str:
        if len(self._rows) == 1:
            return f"Удалить строку {self._rows[0] + 1}"
        return f"Удалить {len(self._rows)} строк"

    @property
    def was_successful(self) -> bool:
        return self._ok

    @property
    def message(self) -> str:
        return self._message


# ============================================================
# 🧹 Нормализация выгрузки 1С
# ============================================================

class Normalize1CCommand(Command):
    """
    Применяет нормализатор 1С (карточка счёта).
    Сохраняет backup df, метаданные, порядок.
    """

    def __init__(self, data, on_change=None):
        self._data = data
        self._on_change = on_change

        self._backup_df = None
        self._backup_columns = None
        self._backup_dtypes = None
        self._backup_meta = None
        self._backup_order = None
        self._backup_visible = None
        self._backup_rows = None

        self._ok = False
        self._message = ""
        self._log: list[str] = []

    def do(self):
        from src.core.onec_normalizer import normalize_1c

        self._backup_df = self._data.dataframe.copy()
        self._backup_columns = list(self._data.columns)
        self._backup_dtypes = dict(self._data.dtypes)
        self._backup_meta = {k: dict(v) for k, v in self._data.column_meta.items()}
        self._backup_order = list(self._data.column_order)
        self._backup_visible = list(self._data.visible_columns)
        self._backup_rows = self._data.rows_count

        try:
            new_df, log, operations = normalize_1c(self._data.dataframe)
            self._log = log

            self._data.dataframe = new_df
            self._data.columns = list(new_df.columns)
            self._data.dtypes = {c: str(t) for c, t in new_df.dtypes.items()}
            self._data.rows_count = len(new_df)
            self._data.cols_count = len(new_df.columns)
            self._data.column_meta = {}
            self._data.column_order = list(new_df.columns)
            self._data.visible_columns = list(new_df.columns)
            self._data.column_filters = {}

            self._ok = True

            for op in operations:
                _log_operation(self._data, op["type"], op["params"])

            self._data.invalidate_cache()
            if self._on_change:
                self._on_change()

            self._message = (
                f"Нормализация 1С: {len(new_df)} строк × {len(new_df.columns)} колонок"
            )

        except Exception as e:
            import traceback
            traceback.print_exc()
            self._data.dataframe = self._backup_df
            self._data.columns = self._backup_columns
            self._data.dtypes = self._backup_dtypes
            self._data.column_meta = self._backup_meta
            self._data.column_order = self._backup_order
            self._data.visible_columns = self._backup_visible
            self._data.rows_count = self._backup_rows
            self._data.cols_count = len(self._backup_columns)
            self._message = f"Ошибка: {type(e).__name__}: {e}"

    def undo(self):
        if not self._ok or self._backup_df is None:
            return

        ops = getattr(self._data, "operations", None)
        if ops:
            count = sum(
                1 for op in ops.get_all() if op.type.startswith("1c_")
            )
            for _ in range(count):
                ops.pop_last()

        self._data.dataframe = self._backup_df
        self._data.columns = self._backup_columns
        self._data.dtypes = self._backup_dtypes
        self._data.column_meta = self._backup_meta
        self._data.column_order = self._backup_order
        self._data.visible_columns = self._backup_visible
        self._data.rows_count = self._backup_rows
        self._data.cols_count = len(self._backup_columns)

        self._data.invalidate_cache()
        if self._on_change:
            self._on_change()

    def description(self) -> str:
        return "Нормализация выгрузки 1С"

    @property
    def was_successful(self) -> bool:
        return self._ok

    @property
    def message(self) -> str:
        return self._message

    @property
    def log(self) -> list:
        return self._log


# ============================================================
# ✂ Извлечение текста по шаблону
# ============================================================

class ExtractTextCommand(Command):
    """
    Извлекает из выбранных колонок фрагмент по regex-шаблону.

    Для каждой колонки:
      • создаёт {col}_извлечено — значения, где шаблон совпал,
      • создаёт {col}_ошибки    — исходные значения, где шаблон не совпал.

    Исходная колонка НЕ трогается.
    Backup dataframe + метаданных → Undo восстанавливает всё.
    """

    def __init__(self, data, columns: list, pattern: str, on_change=None):
        self._data = data
        self._columns = list(columns)
        self._pattern = pattern
        self._on_change = on_change

        # Backup
        self._backup_df = None
        self._backup_columns = None
        self._backup_dtypes = None
        self._backup_meta = None
        self._backup_order = None
        self._backup_visible = None
        self._backup_filters = None
        self._backup_cols_count = None

        self._ok = False
        self._message = ""
        self._log: list[str] = []

    # ---------- do ----------

    def do(self):
        from src.core.text_extractor import extract_value, validate_pattern

        if self._data is None or not self._columns:
            self._message = "Не выбрано ни одной колонки"
            return

        ok_re, err = validate_pattern(self._pattern)
        if not ok_re:
            self._message = err
            return

        # ── Backup ──
        self._backup_df = self._data.dataframe.copy()
        self._backup_columns = list(self._data.columns)
        self._backup_dtypes = dict(self._data.dtypes)
        self._backup_meta = {k: dict(v) for k, v in self._data.column_meta.items()}
        self._backup_order = list(self._data.column_order)
        self._backup_visible = list(self._data.visible_columns)
        self._backup_filters = dict(self._data.column_filters)
        self._backup_cols_count = self._data.cols_count

        try:
            total_cols = len(self._columns)
            ok_cols = 0

            for col in self._columns:
                if col not in self._data.columns:
                    self._log.append(f"⚠ Колонка «{col}» не найдена")
                    continue

                series = self._data.dataframe[col]

                extracted = []
                errors = []
                count_ok = 0
                count_err = 0

                for v in series:
                    result, is_ok = extract_value(v, self._pattern)
                    if is_ok:
                        extracted.append(result)
                        errors.append(None)
                        count_ok += 1
                    else:
                        extracted.append(None)
                        errors.append(str(v) if v is not None else "")
                        count_err += 1

                idx = self._data.columns.index(col)

                name_ext = f"{col}_извлечено"
                name_err = f"{col}_ошибки"

                # ★ Если такие колонки уже есть (повторное извлечение) —
                #   сначала удаляем их, иначе dataframe.insert упадёт
                #   с "cannot insert, already exists".
                if name_ext in self._data.columns:
                    self._drop_existing_column(name_ext)
                if name_err in self._data.columns:
                    self._drop_existing_column(name_err)

                # Индекс мог сдвинуться после удаления — пересчитываем
                idx = self._data.columns.index(col)

                made_ext = False
                made_err = False

                if count_ok > 0:
                    ext_values = [v if v is not None else "" for v in extracted]
                    self._insert_column(name_ext, ext_values, idx + 1)
                    made_ext = True

                if count_err > 0:
                    err_values = [v if v is not None else "" for v in errors]
                    offset = 1 if made_ext else 0
                    self._insert_column(name_err, err_values, idx + 1 + offset)
                    made_err = True

                parts = []
                if made_ext:
                    parts.append(f"+«{name_ext}» ({count_ok} значений)")
                if made_err:
                    parts.append(f"+«{name_err}» ({count_err} ошибок)")
                if parts:
                    self._log.append(f"✓ «{col}»: " + ", ".join(parts))
                    ok_cols += 1
                else:
                    self._log.append(f"⚠ «{col}»: нет данных для обработки")

            self._data.cols_count = len(self._data.columns)
            self._ok = ok_cols > 0

            _log_operation(self._data, "extract_text", {
                "columns": list(self._columns),
                "pattern": self._pattern,
            })

            self._data.invalidate_cache()
            if self._on_change:
                self._on_change()

            if self._ok:
                self._message = f"Обработано колонок: {ok_cols} из {total_cols}"
            else:
                self._message = "Ничего не извлечено"

        except Exception as e:
            import traceback
            traceback.print_exc()
            self._restore_backup()
            self._message = f"Ошибка: {type(e).__name__}: {e}"

    # ---------- undo ----------

    def undo(self):
        if self._backup_df is None:
            return

        ops = getattr(self._data, "operations", None)
        if ops:
            ops.pop_last()

        self._restore_backup()

        self._data.invalidate_cache()
        if self._on_change:
            self._on_change()

    # ---------- Вспомогательные ----------

    def _drop_existing_column(self, name: str):
        """Удалить колонку с таким именем из всех структур (для повторного extract)."""
        d = self._data
        if name in d.dataframe.columns:
            d.dataframe = d.dataframe.drop(columns=[name])
        if name in d.columns:
            d.columns.remove(name)
        if name in d.column_order:
            d.column_order.remove(name)
        if name in d.visible_columns:
            d.visible_columns.remove(name)
        d.dtypes.pop(name, None)
        d.column_meta.pop(name, None)

    def _insert_column(self, name: str, values: list, position: int):
        """Вставить колонку в dataframe + обновить все структуры."""
        d = self._data

        d.dataframe.insert(position, name, values)
        d.dtypes[name] = "str"

        pos = min(position, len(d.columns))
        d.columns.insert(pos, name)

        pos_order = min(position, len(d.column_order))
        d.column_order.insert(pos_order, name)

        pos_vis = min(position, len(d.visible_columns))
        d.visible_columns.insert(pos_vis, name)

    def _restore_backup(self):
        d = self._data
        d.dataframe = self._backup_df
        d.columns = self._backup_columns
        d.dtypes = self._backup_dtypes
        d.column_meta = self._backup_meta
        d.column_order = self._backup_order
        d.visible_columns = self._backup_visible
        d.column_filters = self._backup_filters
        d.cols_count = self._backup_cols_count

    # ---------- Публичные ----------

    def description(self) -> str:
        n = len(self._columns)
        if n == 1:
            return f"Извлечь по шаблону из «{self._columns[0]}»"
        return f"Извлечь по шаблону из {n} колонок"

    @property
    def was_successful(self) -> bool:
        return self._ok

    @property
    def message(self) -> str:
        return self._message

    @property
    def log(self) -> list:
        return self._log
    # ============================================================
# 🔽 Сортировка по колонкам
# ============================================================

class SortByColumnCommand(Command):
    """
    Сортировка DataFrame по списку колонок.
    sort_spec: [(col_name, asc), ...]
    """

    def __init__(self, data, sort_spec: list, on_change=None):
        self._data = data
        self._sort_spec = list(sort_spec)
        self._on_change = on_change
        self._backup_df = None
        self._ok = False
        self._message = ""

    def do(self):
        if not self._sort_spec:
            self._message = "Пустой список сортировки"
            return

        by = []
        ascending = []
        for col_name, asc in self._sort_spec:
            if col_name not in self._data.dataframe.columns:
                self._message = f"Колонка не найдена: {col_name}"
                return
            by.append(col_name)
            ascending.append(bool(asc))

        self._backup_df = self._data.dataframe.copy()

        try:
            self._data.dataframe = (
                self._data.dataframe
                .sort_values(by=by, ascending=ascending, kind="mergesort")
                .reset_index(drop=True)
            )
            self._ok = True

            _log_operation(self._data, "sort_values", {
                "by": by,
                "ascending": ascending,
            })

            self._data.invalidate_cache()
            if self._on_change:
                self._on_change()

            names = ", ".join(by)
            if all(ascending):
                direction = " ↑"
            elif not any(ascending):
                direction = " ↓"
            else:
                direction = " ↑↓"
            self._message = f"Сортировка: {names}{direction}"

        except Exception as e:
            import traceback
            traceback.print_exc()
            self._data.dataframe = self._backup_df
            self._message = f"Ошибка: {type(e).__name__}: {e}"

    def undo(self):
        if not self._ok or self._backup_df is None:
            return

        self._data.dataframe = self._backup_df

        ops = getattr(self._data, "operations", None)
        if ops:
            ops.pop_last()

        self._data.invalidate_cache()
        if self._on_change:
            self._on_change()

    def description(self) -> str:
        names = ", ".join(c for c, _ in self._sort_spec)
        return f"Сортировка: {names}"

    @property
    def was_successful(self) -> bool:
        return self._ok

    @property
    def message(self) -> str:
        return self._message

    # ============================================================
# 🗑 Удалить дубликаты
# ============================================================

class DropDuplicatesCommand(Command):
    """Удаление дубликатов по подмножеству колонок (или по всем)."""

    def __init__(self, data, subset: list | None = None, on_change=None):
        self._data = data
        self._subset = list(subset) if subset else []
        self._on_change = on_change
        self._backup_df = None
        self._ok = False
        self._message = ""

    def do(self):
        self._backup_df = self._data.dataframe.copy()
        before = len(self._data.dataframe)

        try:
            if self._subset:
                # Проверяем, что все колонки существуют
                missing = [c for c in self._subset if c not in self._data.dataframe.columns]
                if missing:
                    self._message = f"Колонки не найдены: {missing}"
                    return

                df_new = (
                    self._data.dataframe
                    .drop_duplicates(subset=self._subset)
                    .reset_index(drop=True)
                )
            else:
                df_new = (
                    self._data.dataframe
                    .drop_duplicates()
                    .reset_index(drop=True)
                )

            removed = before - len(df_new)
            self._data.dataframe = df_new
            self._data.rows_count = len(df_new)
            self._ok = True

            _log_operation(self._data, "drop_duplicates", {
                "subset": list(self._subset),
            })

            self._data.invalidate_cache()
            if self._on_change:
                self._on_change()

            self._message = f"Удалено дубликатов: {removed}"

        except Exception as e:
            import traceback
            traceback.print_exc()
            self._data.dataframe = self._backup_df
            self._data.rows_count = len(self._backup_df)
            self._message = f"Ошибка: {type(e).__name__}: {e}"

    def undo(self):
        if not self._ok or self._backup_df is None:
            return
        self._data.dataframe = self._backup_df
        self._data.rows_count = len(self._backup_df)
        ops = getattr(self._data, "operations", None)
        if ops:
            ops.pop_last()
        self._data.invalidate_cache()
        if self._on_change:
            self._on_change()

    def description(self) -> str:
        if self._subset:
            return f"Удалить дубликаты по {len(self._subset)} колонкам"
        return "Удалить дубликаты (по всем колонкам)"

    @property
    def was_successful(self) -> bool:
        return self._ok

    @property
    def message(self) -> str:
        return self._message


# ============================================================
# 🗑 Удалить строки с пропусками
# ============================================================

class DropNaCommand(Command):
    """Удаление строк с пропусками (NaN)."""

    def __init__(self, data, subset: list | None = None, how: str = "any",
                 on_change=None):
        self._data = data
        self._subset = list(subset) if subset else []
        self._how = how  # "any" | "all"
        self._on_change = on_change
        self._backup_df = None
        self._ok = False
        self._message = ""

    def do(self):
        self._backup_df = self._data.dataframe.copy()
        before = len(self._data.dataframe)

        try:
            if self._subset:
                missing = [c for c in self._subset if c not in self._data.dataframe.columns]
                if missing:
                    self._message = f"Колонки не найдены: {missing}"
                    return

                df_new = (
                    self._data.dataframe
                    .dropna(subset=self._subset, how=self._how)
                    .reset_index(drop=True)
                )
            else:
                df_new = (
                    self._data.dataframe
                    .dropna(how=self._how)
                    .reset_index(drop=True)
                )

            removed = before - len(df_new)
            self._data.dataframe = df_new
            self._data.rows_count = len(df_new)
            self._ok = True

            _log_operation(self._data, "dropna", {
                "subset": list(self._subset),
                "how": self._how,
            })

            self._data.invalidate_cache()
            if self._on_change:
                self._on_change()

            self._message = f"Удалено строк: {removed}"

        except Exception as e:
            import traceback
            traceback.print_exc()
            self._data.dataframe = self._backup_df
            self._data.rows_count = len(self._backup_df)
            self._message = f"Ошибка: {type(e).__name__}: {e}"

    def undo(self):
        if not self._ok or self._backup_df is None:
            return
        self._data.dataframe = self._backup_df
        self._data.rows_count = len(self._backup_df)
        ops = getattr(self._data, "operations", None)
        if ops:
            ops.pop_last()
        self._data.invalidate_cache()
        if self._on_change:
            self._on_change()

    def description(self) -> str:
        if self._subset:
            return f"Удалить пустые по {len(self._subset)} колонкам ({self._how})"
        return f"Удалить пустые (по всем колонкам, {self._how})"

    @property
    def was_successful(self) -> bool:
        return self._ok

    @property
    def message(self) -> str:
        return self._message


# ============================================================
# 🔤 Нормализация текстовых данных (гос-номера и др.)
# ============================================================

class NormalizeTextCommand(Command):
    """
    Нормализует выбранные колонки:
      • заменяет буквы (латиница ↔ кириллица),
      • приводит к верхнему регистру,
      • удаляет спецсимволы и пробелы.

    Для каждой колонки создаёт:
      • {col}_нормализовано — если есть хотя бы одно валидное значение,
      • {col}_ошибки        — если есть хотя бы одно невалидное значение.

    Исходная колонка НЕ трогается.
    Backup dataframe + метаданных → Undo восстанавливает всё.
    """

    def __init__(self, data, columns: list, options: dict, on_change=None):
        self._data = data
        self._columns = list(columns)
        self._options = dict(options)
        self._on_change = on_change

        # Backup
        self._backup_df = None
        self._backup_columns = None
        self._backup_dtypes = None
        self._backup_meta = None
        self._backup_order = None
        self._backup_visible = None
        self._backup_filters = None
        self._backup_cols_count = None

        self._ok = False
        self._message = ""
        self._log: list[str] = []

    # ---------- do ----------

    def do(self):
        from src.core.text_normalizer import normalize_value

        if self._data is None or not self._columns:
            self._message = "Не выбрано ни одной колонки"
            return

        # Сохраняем backup
        self._backup_df = self._data.dataframe.copy()
        self._backup_columns = list(self._data.columns)
        self._backup_dtypes = dict(self._data.dtypes)
        self._backup_meta = {k: dict(v) for k, v in self._data.column_meta.items()}
        self._backup_order = list(self._data.column_order)
        self._backup_visible = list(self._data.visible_columns)
        self._backup_filters = dict(self._data.column_filters)
        self._backup_cols_count = self._data.cols_count

        direction = self._options.get("direction", "lat2cyr")
        upper = bool(self._options.get("upper", True))
        remove_spaces = bool(self._options.get("remove_spaces", True))
        remove_chars = set(self._options.get("remove_chars", set()))

        try:
            total_cols = len(self._columns)
            ok_cols = 0

            for col in self._columns:
                if col not in self._data.columns:
                    self._log.append(f"⚠ Колонка «{col}» не найдена")
                    continue

                series = self._data.dataframe[col]

                normalized = []
                errors = []

                count_ok = 0
                count_err = 0

                for v in series:
                    result, ok = normalize_value(
                        v,
                        direction=direction,
                        upper=upper,
                        remove_spaces=remove_spaces,
                        remove_chars=remove_chars,
                    )
                    if ok:
                        normalized.append(result)
                        errors.append(None)
                        count_ok += 1
                    else:
                        normalized.append(None)
                        errors.append(str(v) if v is not None else "")
                        count_err += 1

                idx = self._data.columns.index(col)

                name_norm = f"{col}_нормализовано"
                name_err = f"{col}_ошибки"

                made_norm = False
                made_err = False

                if count_ok > 0:
                    norm_values = [v if v is not None else "" for v in normalized]
                    self._insert_column(name_norm, norm_values, idx + 1)
                    made_norm = True

                if count_err > 0:
                    err_values = [v if v is not None else "" for v in errors]
                    offset = 1 if made_norm else 0
                    self._insert_column(name_err, err_values, idx + 1 + offset)
                    made_err = True

                parts = []
                if made_norm:
                    parts.append(f"+«{name_norm}» ({count_ok} значений)")
                if made_err:
                    parts.append(f"+«{name_err}» ({count_err} ошибок)")
                if parts:
                    self._log.append(f"✓ «{col}»: " + ", ".join(parts))
                    ok_cols += 1
                else:
                    self._log.append(f"⚠ «{col}»: нет данных для обработки")

            self._data.cols_count = len(self._data.columns)
            self._ok = ok_cols > 0

            _log_operation(self._data, "normalize_text", {
                "columns": list(self._columns),
                "direction": direction,
                "upper": upper,
                "remove_spaces": remove_spaces,
                "remove_chars": sorted(remove_chars),
            })

            self._data.invalidate_cache()
            if self._on_change:
                self._on_change()

            if self._ok:
                self._message = f"Обработано колонок: {ok_cols} из {total_cols}"
            else:
                self._message = "Не удалось обработать ни одной колонки"

        except Exception as e:
            import traceback
            traceback.print_exc()
            self._restore_backup()
            self._message = f"Ошибка: {type(e).__name__}: {e}"

    # ---------- undo ----------

    def undo(self):
        if self._backup_df is None:
            return

        ops = getattr(self._data, "operations", None)
        if ops:
            ops.pop_last()

        self._restore_backup()

        self._data.invalidate_cache()
        if self._on_change:
            self._on_change()

    # ---------- Вспомогательные ----------

    def _insert_column(self, name: str, values: list, position: int):
        """Вставить колонку в dataframe + обновить все структуры."""
        d = self._data

        # В dataframe
        d.dataframe.insert(position, name, values)
        d.dtypes[name] = "str"

        # В columns
        pos = min(position, len(d.columns))
        d.columns.insert(pos, name)

        # В column_order
        pos_order = min(position, len(d.column_order))
        d.column_order.insert(pos_order, name)

        # В visible_columns
        pos_vis = min(position, len(d.visible_columns))
        d.visible_columns.insert(pos_vis, name)

    def _restore_backup(self):
        d = self._data
        d.dataframe = self._backup_df
        d.columns = self._backup_columns
        d.dtypes = self._backup_dtypes
        d.column_meta = self._backup_meta
        d.column_order = self._backup_order
        d.visible_columns = self._backup_visible
        d.column_filters = self._backup_filters
        d.cols_count = self._backup_cols_count

    # ---------- Публичные ----------

    def description(self) -> str:
        n = len(self._columns)
        if n == 1:
            return f"Нормализовать колонку «{self._columns[0]}»"
        return f"Нормализовать {n} колонок"

    @property
    def was_successful(self) -> bool:
        return self._ok

    @property
    def message(self) -> str:
        return self._message

    @property
    def log(self) -> list:
        return self._log