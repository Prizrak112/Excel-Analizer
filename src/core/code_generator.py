"""
Генератор Python-скрипта из истории операций.
Усиленная защита: уникальные хэши, 6 точек проверки, случайные имена.
"""

from pathlib import Path
from datetime import datetime
import pandas as pd
import hmac
import hashlib
import secrets


PROTECTION_SECRET = b"EA_2026_PROTECT_KEY_x9k2m7p4"
SIGNATURE_MARKER = "=== EXCEL ANALYZER SIGNATURE ==="
AUTHOR_NAME = "В. Рагимов"
AUTHOR_EMAIL = "v.ragimov@agroeco.ru"
APP_NAME = "NexGrid"
APP_VERSION = "1.0"


# ============================================================
# Генерация уникальной защиты
# ============================================================

def _build_protection() -> dict:
    """
    Создаёт уникальный набор хэшей и имён для каждого запуска.
    Никогда не повторяется между генерациями.
    """
    uid = secrets.token_hex(8)

    def h(part: str) -> str:
        return hmac.new(
            PROTECTION_SECRET,
            f"{part}|{uid}".encode(),
            hashlib.sha256,
        ).hexdigest()[:20]

    # 6 разных хэшей для разных мест
    return {
        "uid": uid,
        "h_doc": h("doc"),
        "h_body1": h("body1"),
        "h_body2": h("body2"),
        "h_body3": h("body3"),
        "h_check": h("check"),
        "h_tail": h("tail"),
        # Случайные имена — чтобы нельзя было запомнить и создать шаблон
        "n_uid": "_u" + secrets.token_hex(4),
        "n_m1": "_m" + secrets.token_hex(4),
        "n_m2": "_m" + secrets.token_hex(4),
        "n_m3": "_m" + secrets.token_hex(4),
        "n_m4": "_m" + secrets.token_hex(4),
        "n_m5": "_m" + secrets.token_hex(4),
        "n_m6": "_m" + secrets.token_hex(4),
        "n_check": "_c" + secrets.token_hex(4),
        "n_fail": "_f" + secrets.token_hex(4),
        "n_sys": "_s" + secrets.token_hex(4),
        "n_hash": "_h" + secrets.token_hex(4),
        "n_hmac": "_hm" + secrets.token_hex(4),
        "n_atexit": "_at" + secrets.token_hex(4),
    }


def _make_required_header(p: dict) -> list:
    """Строки, которые обязаны быть в докстринге."""
    return [
        "",
        f"{SIGNATURE_MARKER}",
        f"UID: {p['uid']}",
        f"Сгенерировано приложением: {APP_NAME} v{APP_VERSION}",
        f"Автор: {AUTHOR_NAME}",
        f"По всем вопросам: {AUTHOR_EMAIL}",
        f"Контрольная метка (doc): {p['h_doc']}",
        f"Контрольная метка (b1): {p['h_body1']}",
        f"Контрольная метка (b2): {p['h_body2']}",
        f"Контрольная метка (b3): {p['h_body3']}",
        f"Контрольная метка (meta): {p['h_check']}",
        f"Контрольная метка (tail): {p['h_tail']}",
        "Удаление или изменение этого блока — нарушение целостности скрипта.",
        f"{SIGNATURE_MARKER}",
        "",
    ]


def _make_protection_block(p: dict) -> list:
    """
    Блок с константами и функциями проверки.
    Размещается в начале файла (после импортов).
    """
    lines = []
    lines.append("# ============================================================")
    lines.append("# СИСТЕМА КОНТРОЛЯ ЦЕЛОСТНОСТИ — НЕ УДАЛЯТЬ")
    lines.append("# ============================================================")
    lines.append(f"import sys as {p['n_sys']}")
    lines.append(f"import hashlib as {p['n_hash']}")
    lines.append(f"import hmac as {p['n_hmac']}")
    lines.append(f"import atexit as {p['n_atexit']}")
    lines.append("")
    lines.append(f"{p['n_uid']} = {p['uid']!r}")
    lines.append(f"{p['n_m1']} = {p['h_doc']!r}")
    lines.append(f"{p['n_m2']} = {p['h_body1']!r}")
    lines.append(f"{p['n_m3']} = {p['h_body2']!r}")
    lines.append(f"{p['n_m4']} = {p['h_body3']!r}")
    lines.append(f"{p['n_m5']} = {p['h_check']!r}")
    lines.append(f"{p['n_m6']} = {p['h_tail']!r}")
    lines.append("")

    lines.append(f"def {p['n_fail']}():")
    lines.append('    print("=" * 60)')
    lines.append('    print("❌ Скрипт программы поврежден, просьба откатить файл")')
    lines.append('    print("=" * 60)')
    lines.append(f'    print("По вопросам: {AUTHOR_EMAIL}")')
    lines.append('    print("=" * 60)')
    lines.append(f"    {p['n_sys']}.exit(1)")
    lines.append("")

    lines.append(f"def {p['n_check']}(*conditions):")
    lines.append('    """Проверяет список условий. Падает, если хоть одно False."""')
    lines.append("    for _c in conditions:")
    lines.append("        if not _c:")
    lines.append(f"            {p['n_fail']}()")
    lines.append("")

    lines.append(
        f"{p['n_atexit']}.register("
        f"lambda: {p['n_check']}({p['n_m6']} in (__doc__ or ''), {p['n_uid']} in (__doc__ or '')))"
    )
    lines.append("")

    return lines


def _make_check_call(p: dict, kind: str) -> str:
    """
    Возвращает одну строку — вызов проверки с нужными условиями.
    kind: 'doc' | 'uid' | 'body' | 'tail' | 'full'
    """
    u = p['n_uid']
    m1 = p['n_m1']
    m2 = p['n_m2']
    m3 = p['n_m3']
    m4 = p['n_m4']
    m5 = p['n_m5']
    m6 = p['n_m6']
    chk = p['n_check']

    if kind == "doc":
        return f"{chk}({m1} in (__doc__ or ''), {m2} in (__doc__ or ''))"
    if kind == "uid":
        return f"{chk}({u} and len({u}) == 16, {m1} in (__doc__ or ''))"
    if kind == "body":
        return f"{chk}({m3} in (__doc__ or ''), {u} in (__doc__ or ''))"
    if kind == "full":
        return (
            f"{chk}("
            f"{m1} in (__doc__ or ''), "
            f"{m4} in (__doc__ or ''), "
            f"{m5} in (__doc__ or ''))"
        )
    if kind == "tail":
        return f"{chk}({m6} in (__doc__ or ''), {m6} != '')"
    return f"{chk}(True)"


# ============================================================
# Утилиты значений
# ============================================================

def _value_to_literal(val) -> str:
    if val is None:
        return "None"
    s = str(val)
    if s == "":
        return "None"
    try:
        n = float(s)
        if "." not in s and "e" not in s.lower() and n == int(n):
            return str(int(n))
        return repr(n)
    except (ValueError, TypeError):
        pass
    return repr(s)


def _col(col: str) -> str:
    return repr(col)


# =============== =============================================
# Компрессор
# ============================================================

class OperationCompressor:
    @classmethod
    def compress(cls, operations: list) -> list:
        if not operations:
            return []

        final_dtype = {}
        initial_dtype = {}
        cast_changes = {}
        rename_map = {}       # исходное_имя -> финальное_имя
        reverse_rename = {}   # текущее_имя -> исходное_имя (для цепочек A->B->C)
        edit_map = {}
        edit_order = []
        fillna_map = {}
        col_transform_map = {}  # (op_type, column) -> params (схлопывает повторные правки колонки)
        deleted_cols = []

        reorder_op = None
        sort_op = None
        dedup_op = None
        dropna_op = None
        reset_idx_op = None

        onec_types = {
            "1c_find_start", "1c_delete_cur_saldo", "1c_drop_empty_cols",
            "1c_fill_headers", "1c_split_multiline", "1c_delete_after_col",
            "1c_date_only", "1c_delete_useless",
        }
        col_overwritable_types = {
            "str_strip", "str_lower", "str_upper", "str_title",
            "str_replace", "replace_value", "num_round", "num_abs",
            "dt_extract", "dt_strftime", "split_column",
        }

        other_ops = []

        for op in operations:
            if not hasattr(op, "type") or not hasattr(op, "params"):
                continue
            t = op.type
            p = op.params or {}

            if t == "cast_column":
                col = p["column"]
                if col not in initial_dtype:
                    initial_dtype[col] = p.get("prev_dtype", "unknown")
                final_dtype[col] = p["new_dtype"]
                cast_changes[col] = cast_changes.get(col, 0) + 1

            elif t == "rename_column":
                old_col = p["column"]
                new_name = p["new_name"]
                orig_col = reverse_rename.pop(old_col, old_col)
                if orig_col == new_name:
                    rename_map.pop(orig_col, None)
                else:
                    rename_map[orig_col] = new_name
                    reverse_rename[new_name] = orig_col

            elif t == "edit_cell":
                key = (p.get("row"), p.get("column"))
                if key not in edit_map:
                    edit_order.append(key)
                edit_map[key] = p.get("new_value", "")

            elif t == "fillna":
                fillna_map[p.get("column", "")] = p

            elif t == "reorder_columns":
                reorder_op = p

            elif t == "delete_columns":
                for c in p.get("columns", []):
                    if c not in deleted_cols:
                        deleted_cols.append(c)

            elif t == "sort_values":
                sort_op = p
            elif t == "drop_duplicates":
                dedup_op = p
            elif t == "dropna":
                dropna_op = p
            elif t == "reset_index":
                reset_idx_op = p

            elif t in col_overwritable_types:
                col_key = (t, p.get("column", ""), p.get("new_column", ""))
                # Перезаписываем и сдвигаем в конец очереди
                if col_key in col_transform_map:
                    del col_transform_map[col_key]
                col_transform_map[col_key] = {"type": t, "params": p}

            elif t in onec_types:
                other_ops.append({"type": t, "params": p})

            elif t == "toggle_column":
                continue

            else:
                other_ops.append({"type": t, "params": p})

        compacted = []

        # 1. Сперва операции 1С (если есть)
        for op_dict in other_ops:
            if op_dict["type"] in onec_types:
                compacted.append(op_dict)

        # 2. Удаление колонок (одним списком)
        if deleted_cols:
            compacted.append({
                "type": "delete_columns",
                "params": {"columns": deleted_cols},
            })

        # 3. Преобразование типов (только финальный тип каждой колонки)
        for col, new_dtype in final_dtype.items():
            if col in deleted_cols:
                continue
            initial = initial_dtype.get(col, "unknown")
            changes = cast_changes.get(col, 0)
            if changes == 0 or initial == new_dtype:
                continue
            compacted.append({
                "type": "cast_column",
                "params": {
                    "column": col,
                    "prev_dtype": initial,
                    "new_dtype": new_dtype,
                    "was_changes": changes > 1,
                    "changes_count": changes,
                }
            })

        # 4. Трансформации колонок (округление, строки, даты — только последние настройки)
        for col_op in col_transform_map.values():
            compacted.append(col_op)

        # 5. Заполнение пропусков
        for col, p in fillna_map.items():
            if col not in deleted_cols:
                compacted.append({"type": "fillna", "params": p})

        # 6. Точечные правки ячеек (только последнее значение ячейки)
        for key in edit_order:
            row, col = key
            if col not in deleted_cols:
                compacted.append({
                    "type": "edit_cell",
                    "params": {
                        "row": row,
                        "column": col,
                        "new_value": edit_map[key],
                    }
                })

        # 7. Переименование колонок (единым блоком)
        if rename_map:
            compacted.append({
                "type": "rename_columns_bulk",
                "params": {"mapping": dict(rename_map)}
            })

        # 8. Финальный порядок колонок
        if reorder_op is not None:
            compacted.append({"type": "reorder_columns", "params": reorder_op})

        # 9. Удаление строк и прочие операции
        for op_dict in other_ops:
            if op_dict["type"] not in onec_types:
                compacted.append(op_dict)

        # 10. Глобальные табличные операции (сортировка, дубликаты, пропуски)
        if dropna_op is not None:
            compacted.append({"type": "dropna", "params": dropna_op})
        if dedup_op is not None:
            compacted.append({"type": "drop_duplicates", "params": dedup_op})
        if sort_op is not None:
            compacted.append({"type": "sort_values", "params": sort_op})
        if reset_idx_op is not None:
            compacted.append({"type": "reset_index", "params": reset_idx_op})

        return compacted

# ============================================================
# Генератор
# ============================================================

class CodeGenerator:
    def __init__(
        self,
        file_name: str = "data.xlsx",
        sheet_name: str = "Sheet1",
        output_name: str = "output.xlsx",
        reset_index: bool = False,
    ):
        self.file_name = file_name
        self.sheet_name = sheet_name
        self.output_name = output_name
        self.reset_index = reset_index

    def generate(self, operations: list) -> str:
        compacted = OperationCompressor.compress(operations)
        p = _build_protection()  # уникальные хэши и имена

        lines = []

        # ===== ДОКСТРИНГ =====
        lines.append('"""')
        lines.append("Автоматически сгенерированный скрипт обработки Excel")
        lines.append(f"Сгенерировано: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
        lines.append(f"Источник: {Path(self.file_name).name}")
        lines.append(f"Лист: {self.sheet_name}")
        lines.append("")
        lines.append("Скрипт воспроизводит все действия, выполненные в Excel Analyzer.")
        lines.append("Можно запустить как есть или использовать в Jupyter.")
        for l in _make_required_header(p):
            lines.append(l)
        lines.append('"""')
        lines.append("")

        # ===== ИМПОРТЫ И АВТОУСТАНОВКА =====
        lines.append("from pathlib import Path")
        lines.append("")
        lines.extend(_make_auto_install_lines({
            "pandas": "pandas",
            "numpy": "numpy",
            "openpyxl": "openpyxl",
        }))
        lines.append("import pandas as pd  # noqa: E402")
        lines.append("import numpy as np  # noqa: E402")
        lines.append("")

        # ===== БЛОК ЗАЩИТЫ =====
        for l in _make_protection_block(p):
            lines.append(l)

        # Первая проверка — сразу после импортов
        lines.append("# контроль 1")
        lines.append(_make_check_call(p, "doc"))
        lines.append("")

        # ===== КОНФИГУРАЦИЯ =====
        lines.append("# ============================================================")
        lines.append("# КОНФИГУРАЦИЯ")
        lines.append("# ============================================================")
        lines.append(f"SOURCE_FILE = Path({str(self.file_name)!r})")
        lines.append(f"SHEET_NAME = {self.sheet_name!r}")
        lines.append(f"OUTPUT_FILE = Path({str(self.output_name)!r})")
        lines.append(f"RESET_INDEX = {bool(self.reset_index)}")
        lines.append("")

        # Вторая проверка — перед main
        lines.append(f"# контроль 2")
        lines.append(_make_check_call(p, "uid"))
        lines.append("")
        lines.append("")

        # ===== MAIN =====
        lines.append("def main():")
        lines.append("    # ========================================================")
        lines.append("    # ШАГ 1: Загрузка данных")
        lines.append("    # ========================================================")

        # Третья проверка — в начале main
        lines.append(f"    {_make_check_call(p, 'body')}")

        lines.append('    print("Загрузка данных...")')
        lines.append("    df = pd.read_excel(SOURCE_FILE, sheet_name=SHEET_NAME)")
        lines.append('    print(f"  Загружено: {len(df)} строк, {len(df.columns)} колонок")')
        lines.append("")

        # Четвёртая проверка — в середине main
        lines.append(f"    {_make_check_call(p, 'uid')}")
        lines.append("")

        step_num = 2
        for op in compacted:
            block = self._render_operation(op, step_num)
            if block:
                lines.append(block)
                step_num += 1

        # Пятая проверка — перед сохранением
        lines.append(f"    {_make_check_call(p, 'full')}")
        lines.append("")

        lines.append("    # ========================================================")
        lines.append("    # ИТОГ")
        lines.append("    # ========================================================")
        lines.append('    print(f"Готово: {len(df)} строк, {len(df.columns)} колонок")')
        lines.append("")
        lines.append("    if RESET_INDEX:")
        lines.append("        df = df.reset_index(drop=True)")
        lines.append("")
        lines.append('    print(f"Сохранение в {OUTPUT_FILE}...")')
        lines.append("    df.to_excel(OUTPUT_FILE, index=False)")
        lines.append('    print("✅ Готово!")')
        lines.append("")
        lines.append("")
        lines.append('if __name__ == "__main__":')
        lines.append("    main()")
        lines.append("")

        # Шестая проверка — в самом конце файла
        lines.append(f"# контроль 6 (final)")
        lines.append(_make_check_call(p, "tail"))

        return "\n".join(lines)

    def _render_operation(self, op: dict, step_num: int) -> str:
        t = op["type"]
        p = op["params"]
        lines = []
        lines.append("    # ========================================================")

        if t == "cast_column":
            col = p["column"]
            new_dtype = p["new_dtype"]
            old_dtype = p.get("prev_dtype", "unknown")
            lines.append(f"    # ШАГ {step_num}: Преобразовать {col!r} в {new_dtype}")
            if p.get("was_changes"):
                lines.append(f"    # (промежуточных изменений типа: {p.get('changes_count', 0)})")
            lines.append(f"    # Было: {old_dtype} → Стало: {new_dtype}")
            lines.append("    # ========================================================")
            lines.append(f'    print("Преобразование {col} в {new_dtype}...")')
            c = _col(col)
            if new_dtype in ("int64", "int"):
                lines.append(f'    df[{c}] = pd.to_numeric(df[{c}], errors="coerce").fillna(0).astype("int64")')
            elif new_dtype in ("float64", "float"):
                lines.append(f'    df[{c}] = pd.to_numeric(df[{c}], errors="coerce")')
            elif new_dtype in ("datetime64[ns]", "datetime"):
                lines.append(f'    df[{c}] = pd.to_datetime(df[{c}], errors="coerce")')
            elif new_dtype in ("str", "string", "object"):
                lines.append(f'    df[{c}] = df[{c}].astype(str)')
            elif new_dtype in ("bool", "boolean"):
                lines.append(f'    df[{c}] = df[{c}].astype(bool)')
            else:
                lines.append(f"    # Неизвестный тип: {new_dtype}")
            lines.append("")

        elif t == "edit_cell":
            row = int(p.get("row", 0))
            col = p.get("column", "")
            val_repr = _value_to_literal(p.get("new_value", ""))
            lines.append(f"    # ШАГ {step_num}: Изменить ячейку в {col!r} (строка {row + 1})")
            lines.append("    # ========================================================")
            lines.append(f'    print("Изменение ячейки {col} (строка {row + 1})...")')
            lines.append(f'    df.iat[{row}, df.columns.get_loc({_col(col)})] = {val_repr}')
            lines.append("")

        elif t == "rename_columns_bulk":
            mapping = p["mapping"]
            lines.append(f"    # ШАГ {step_num}: Переименование колонок")
            lines.append("    # ========================================================")
            lines.append('    print("Переименование колонок...")')
            lines.append("    df = df.rename(columns={")
            for old, new in mapping.items():
                lines.append(f"        {old!r}: {new!r},")
            lines.append("    })")
            lines.append("")

        elif t == "toggle_column":
            col = p["column"]
            action = "видима" if p["visible"] else "скрыта"
            lines.append(f"    # ШАГ {step_num}: Колонка {col!r} — {action} (в UI)")
            lines.append("    # ========================================================")
            lines.append("    # (на данные не влияет — только для отображения)")
            lines.append("")

        elif t == "reorder_columns":
            new_order = p.get("new_order", [])
            lines.append(f"    # ШАГ {step_num}: Изменить порядок колонок")
            lines.append("    # ========================================================")
            lines.append('    print("Изменение порядка колонок...")')
            cols_repr = ", ".join(repr(c) for c in new_order)
            lines.append(f"    df = df[[{cols_repr}]]")
            lines.append("")

        elif t == "split_column":
            col = p["column"]
            mode = p["mode"]
            new_names = p.get("new_names", [])
            delete_original = p.get("delete_original", False)
            lines.append(f"    # ШАГ {step_num}: Разделить {col!r} на {len(new_names)} колонок")
            lines.append("    # ========================================================")
            lines.append(f'    print("Разделение колонки {col}...")')
            c = _col(col)
            if mode == "separator":
                sep = p.get("separator", " ")
                if len(new_names) == 2:
                    n0, n1 = _col(new_names[0]), _col(new_names[1])
                    lines.append(f'    df[[{n0}, {n1}]] = df[{c}].str.split({sep!r}, n=1, expand=True)')
                else:
                    lines.append(f'    split_parts = df[{c}].str.split({sep!r}, expand=True)')
                    for i, name in enumerate(new_names):
                        lines.append(f'    df[{_col(name)}] = split_parts[{i}]')
            elif mode == "position":
                position = p.get("position", 0)
                lines.append(f'    df[{_col(new_names[0])}] = df[{c}].str[:{position}]')
                lines.append(f'    df[{_col(new_names[1])}] = df[{c}].str[{position}:]')
            if delete_original:
                lines.append(f'    df = df.drop(columns=[{c}])')
            lines.append("")

        elif t == "delete_columns":
            cols = p.get("columns", [])
            lines.append(f"    # ШАГ {step_num}: Удалить колонки")
            lines.append("    # ========================================================")
            cols_repr = ", ".join(repr(c) for c in cols)
            lines.append(f"    df = df.drop(columns=[{cols_repr}])")
            lines.append("")

        elif t == "delete_rows":
            indices = sorted(int(i) for i in p.get("indices", []))
            lines.append(f"    # ШАГ {step_num}: Удалить {len(indices)} строк(и)")
            lines.append("    # ========================================================")
            lines.append(f'    print("Удаление {len(indices)} строк...")')
            idx_repr = ", ".join(str(i) for i in indices)
            lines.append(f"    df = df.drop(df.index[[{idx_repr}]]).reset_index(drop=True)")
            lines.append("")

        elif t == "sort_values":
            by = p.get("by", [])
            asc = p.get("ascending", [True] * len(by))
            lines.append(f"    # ШАГ {step_num}: Сортировка по {by}")
            lines.append("    # ========================================================")
            by_repr = ", ".join(repr(c) for c in by)
            asc_repr = ", ".join(str(bool(a)) for a in asc)
            lines.append(f'    print("Сортировка...")')
            lines.append(f"    df = df.sort_values(by=[{by_repr}], ascending=[{asc_repr}])")
            lines.append("")

        elif t == "drop_duplicates":
            subset = p.get("subset", [])
            lines.append(f"    # ШАГ {step_num}: Удалить дубликаты")
            lines.append("    # ========================================================")
            lines.append('    print("Удаление дубликатов...")')
            if subset:
                sub_repr = ", ".join(repr(c) for c in subset)
                lines.append(f"    df = df.drop_duplicates(subset=[{sub_repr}])")
            else:
                lines.append("    df = df.drop_duplicates()")
            lines.append("")

        elif t == "dropna":
            subset = p.get("subset", [])
            how = p.get("how", "any")
            lines.append(f"    # ШАГ {step_num}: Удалить строки с пропусками ({how})")
            lines.append("    # ========================================================")
            lines.append('    print("Удаление пропусков...")')
            if subset:
                sub_repr = ", ".join(repr(c) for c in subset)
                lines.append(f'    df = df.dropna(subset=[{sub_repr}], how={how!r})')
            else:
                lines.append(f"    df = df.dropna(how={how!r})")
            lines.append("")

        elif t == "fillna":
            col = p.get("column", "")
            method = p.get("method")
            value = p.get("value", "")
            lines.append(f"    # ШАГ {step_num}: Заполнить пропуски в {col!r}")
            lines.append("    # ========================================================")
            c = _col(col)
            if method == "ffill":
                lines.append(f"    df[{c}] = df[{c}].ffill()")
            elif method == "bfill":
                lines.append(f"    df[{c}] = df[{c}].bfill()")
            else:
                lines.append(f"    df[{c}] = df[{c}].fillna({_value_to_literal(value)})")
            lines.append("")

        elif t in ("str_strip", "str_lower", "str_upper", "str_title"):
            col = p.get("column", "")
            method_map = {
                "str_strip": "str.strip()",
                "str_lower": "str.lower()",
                "str_upper": "str.upper()",
                "str_title": "str.title()",
            }
            op_name = {
                "str_strip": "Убрать пробелы",
                "str_lower": "Нижний регистр",
                "str_upper": "Верхний регистр",
                "str_title": "Заглавные",
            }[t]
            lines.append(f"    # ШАГ {step_num}: {op_name} — {col!r}")
            lines.append("    # ========================================================")
            c = _col(col)
            lines.append(f"    df[{c}] = df[{c}].astype(str).{method_map[t]}")
            lines.append("")

        elif t == "str_replace":
            col = p.get("column", "")
            old = p.get("old", "")
            new = p.get("new", "")
            regex = bool(p.get("regex", False))
            lines.append(f"    # ШАГ {step_num}: Заменить в {col!r}")
            lines.append("    # ========================================================")
            c = _col(col)
            lines.append(
                f"    df[{c}] = df[{c}].astype(str).str.replace("
                f"{old!r}, {new!r}, regex={regex})"
            )
            lines.append("")

        elif t == "replace_value":
            col = p.get("column", "")
            old = p.get("old", "")
            new = p.get("new", "")
            lines.append(f"    # ШАГ {step_num}: Заменить {old!r} → {new!r} в {col!r}")
            lines.append("    # ========================================================")
            lines.append(
                f"    df[{_col(col)}] = df[{_col(col)}]"
                f".replace({_value_to_literal(old)}, {_value_to_literal(new)})"
            )
            lines.append("")

        elif t in ("num_round", "num_abs"):
            col = p.get("column", "")
            c = _col(col)
            if t == "num_round":
                decimals = int(p.get("decimals", 2))
                lines.append(f"    # ШАГ {step_num}: Округлить {col!r} до {decimals}")
                lines.append("    # ========================================================")
                lines.append(f'    df[{c}] = pd.to_numeric(df[{c}], errors="coerce").round({decimals})')
            else:
                lines.append(f"    # ШАГ {step_num}: Модуль {col!r}")
                lines.append("    # ========================================================")
                lines.append(f'    df[{c}] = pd.to_numeric(df[{c}], errors="coerce").abs()')
            lines.append("")

        elif t == "dt_extract":
            col = p.get("column", "")
            part = p.get("part", "year")
            new_col = p.get("new_column") or f"{col}_{part}"
            part_map = {
                "year": "year", "month": "month", "day": "day",
                "weekday": "weekday", "hour": "hour", "minute": "minute",
                "quarter": "quarter", "week": "isocalendar().week",
            }
            accessor = part_map.get(part, "year")
            lines.append(f"    # ШАГ {step_num}: Извлечь {part} из {col!r}")
            lines.append("    # ========================================================")
            lines.append(
                f'    df[{_col(new_col)}] = pd.to_datetime(df[{_col(col)}], errors="coerce")'
                f".dt.{accessor}"
            )
            lines.append("")

        elif t == "dt_strftime":
            col = p.get("column", "")
            fmt = p.get("format", "%Y-%m")
            new_col = p.get("new_column") or f"{col}_fmt"
            lines.append(f"    # ШАГ {step_num}: Формат даты {col!r} → {fmt!r}")
            lines.append("    # ========================================================")
            lines.append(
                f'    df[{_col(new_col)}] = pd.to_datetime(df[{_col(col)}], errors="coerce")'
                f".dt.strftime({fmt!r})"
            )
            lines.append("")

        # ============ 1С ============
        elif t == "1c_find_start":
            start_row = int(p.get("start_row", 0))
            lines.append(f"    # ШАГ {step_num}: 1С — обрезать шапку до строки {start_row + 1}")
            lines.append("    # ========================================================")
            if start_row > 0:
                lines.append(f"    df = df.iloc[{start_row}:].reset_index(drop=True)")
            lines.append('    df.iloc[0, 0] = "Период"')
            lines.append("")

        elif t == "1c_delete_cur_saldo":
            col_name = p.get("col_name", "")
            lines.append(f"    # ШАГ {step_num}: 1С — удалить 'Текущее сальдо' + следующую колонку")
            lines.append("    # ========================================================")
            lines.append("    _cols = list(df.columns)")
            lines.append(f"    _idx = _cols.index({col_name!r}) if {col_name!r} in _cols else -1")
            lines.append("    if _idx >= 0:")
            lines.append("        _drop = [_cols[_idx]]")
            lines.append("        if _idx + 1 < len(_cols):")
            lines.append("            _drop.append(_cols[_idx + 1])")
            lines.append("        df = df.drop(columns=_drop)")
            lines.append("")

        elif t == "1c_drop_empty_cols":
            cnt = int(p.get("count", 0))
            lines.append(f"    # ШАГ {step_num}: 1С — удалить пустые столбцы (~{cnt})")
            lines.append("    # ========================================================")
            lines.append('    df = df.replace(r"^\\s*$", pd.NA, regex=True)')
            lines.append("    df = df.loc[:, df.notna().any(axis=0)]")
            lines.append("")

        elif t == "1c_fill_headers":
            headers = p.get("headers", [])
            n = len(headers)
            lines.append(f"    # ШАГ {step_num}: 1С — заполнить заголовки ({n} колонок)")
            lines.append("    # ========================================================")
            lines.append("    df = df.iloc[1:].reset_index(drop=True)")
            lines.append(f"    df.columns = {headers!r}")
            lines.append("")

        elif t == "1c_split_multiline":
            cols = p.get("columns", [])
            cols_repr = ", ".join(repr(c) for c in cols)
            lines.append(f"    # ШАГ {step_num}: 1С — разбить многострочные ячейки ({len(cols)} кол.)")
            lines.append("    # ========================================================")
            lines.append(f"    for _col_name in [{cols_repr}]:")
            lines.append("        if _col_name not in df.columns:")
            lines.append("            continue")
            lines.append("        _idx = list(df.columns).index(_col_name)")
            lines.append("        _parts = df.iloc[:, _idx].astype(str).str.split('\\n')")
            lines.append("        _max = max((len(x) for x in _parts), default=1)")
            lines.append("        _max = min(_max, 8)")
            lines.append("        _left = df.iloc[:, :_idx]")
            lines.append("        _right = df.iloc[:, _idx + 1:]")
            lines.append("        _new = {_col_name: [p[0] if len(p) > 0 else '' for p in _parts]}")
            lines.append("        for _pi in range(1, _max):")
            lines.append("            _new[f'__split_{_idx}_{_pi}__'] = [")
            lines.append("                p[_pi] if len(p) > _pi else '' for p in _parts")
            lines.append("            ]")
            lines.append("        _parts_df = pd.DataFrame(_new, index=df.index)")
            lines.append("        df = pd.concat([_left, _parts_df, _right], axis=1)")
            lines.append("")

        elif t == "1c_delete_after_col":
            col_name = p.get("col_name", "")
            lines.append(f"    # ШАГ {step_num}: 1С — обрезать после '{col_name}'")
            lines.append("    # ========================================================")
            lines.append(f"    if {col_name!r} in df.columns:")
            lines.append(f"        _idx = list(df.columns).index({col_name!r})")
            lines.append("        df = df.iloc[:, :_idx + 1]")
            lines.append("")

        elif t == "1c_date_only":
            col = p.get("column", "Период")
            lines.append(f"    # ШАГ {step_num}: 1С — оставить только строки с датой в {col!r}")
            lines.append("    # ========================================================")
            lines.append(f"    _d = pd.to_datetime(df[{col!r}], errors='coerce')")
            lines.append("    df = df[_d.notna()].reset_index(drop=True)")
            lines.append(f"    df[{col!r}] = pd.to_datetime(df[{col!r}], errors='coerce')")
            lines.append("")

        elif t == "1c_delete_useless":
            cnt = int(p.get("count", 0))
            lines.append(f"    # ШАГ {step_num}: 1С — удалить бесполезные столбцы (~{cnt})")
            lines.append("    # ========================================================")
            lines.append("    _keep = []")
            lines.append("    for _c in df.columns:")
            lines.append("        _has = False")
            lines.append("        for _v in df[_c]:")
            lines.append("            if pd.isna(_v):")
            lines.append("                continue")
            lines.append("            _s = str(_v).strip()")
            lines.append("            if _s and _s != '<...>' and _s.lower() != 'nan':")
            lines.append("                _has = True")
            lines.append("                break")
            lines.append("        if _has:")
            lines.append("            _keep.append(_c)")
            lines.append("    df = df[_keep]")
            lines.append("")

        elif t == "merge_headers":
            lines.append(f"    # ШАГ {step_num}: Склеить двухуровневую шапку")
            lines.append("    # ========================================================")
            lines.append("    print('Склеивание двухуровневой шапки...')")
            lines.append("    old_cols = list(df.columns)")
            lines.append("    first_row = df.iloc[0].fillna('').astype(str).tolist()")
            lines.append("    new_cols = []")
            lines.append("    last_top = ''")
            lines.append("    for i, col in enumerate(old_cols):")
            lines.append("        top_str = str(col)")
            lines.append("        if 'Unnamed:' in top_str or not top_str:")
            lines.append("            top_part = last_top")
            lines.append("        else:")
            lines.append("            top_part = top_str")
            lines.append("            last_top = top_str")
            lines.append("        bottom_part = first_row[i].strip()")
            lines.append("        if top_part and bottom_part:")
            lines.append("            new_cols.append(f'{top_part}_{bottom_part}')")
            lines.append("        else:")
            lines.append("            new_cols.append(top_part or bottom_part or f'Колонка_{i}')")
            lines.append("    df.columns = new_cols")
            lines.append("    df = df.iloc[1:].reset_index(drop=True)")
            lines.append("")

        else:
            lines.append(f"    # ШАГ {step_num}: {t}")
            lines.append("    # ========================================================")
            lines.append("    # (не поддерживается в генераторе)")
            lines.append("")

        return "\n".join(lines)


# ============================================================
# Утилита
# ============================================================

def generate_script(
    operations: list,
    file_name: str,
    sheet_name: str = "Sheet1",
    reset_index: bool = False,
) -> str:
    output_name = Path(file_name).stem + "_processed.xlsx"
    gen = CodeGenerator(
        file_name=file_name,
        sheet_name=sheet_name,
        output_name=output_name,
        reset_index=reset_index,
    )
    return gen.generate(operations)
# ============================================================
# Генератор скрипта HTML-отчёта (NexGrid Dashboard)
# ============================================================

import ast
import base64
import inspect
import json
import zlib


def _build_embedded_engine_b64() -> list[str]:
    """Сжимает актуальные модули blocks.py, block_factory.py и HTML-оболочку в base64-строки."""
    import sys

    core_dir = Path(__file__).resolve().parent
    mem_sources = getattr(sys, "_nexgrid_sources", {})

    def _read_module_src(filename: str, fallback_mod_name: str) -> str:
        if fallback_mod_name in mem_sources:
            return mem_sources[fallback_mod_name]
        p = core_dir / filename
        if p.is_file():
            return p.read_text(encoding="utf-8")
        import importlib
        return inspect.getsource(importlib.import_module(fallback_mod_name))

    payload = {
        "blocks": _read_module_src("blocks.py", "src.core.blocks"),
        "block_factory": _read_module_src("block_factory.py", "src.core.block_factory"),
        "html_shell": _wrap_html("__BODY__", "__TITLE__"),
    }
    raw_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    b64_str = base64.b64encode(zlib.compress(raw_bytes, level=9)).decode("ascii")
    return [b64_str[i : i + 96] for i in range(0, len(b64_str), 96)]


def _make_auto_install_lines(packages: dict[str, str]) -> list[str]:
    """Генерирует блок проверки и автоматической доустановки недостающих библиотек."""
    pkg_lines = ["REQUIRED_PACKAGES = {"]
    for mod_name, pip_name in packages.items():
        pkg_lines.append(f"    {mod_name!r}: {pip_name!r},")
    pkg_lines.append("}")

    return [
        "# ============================================================",
        "# ПРОВЕРКА И АВТОУСТАНОВКА НЕОБХОДИМЫХ БИБЛИОТЕК",
        "# ============================================================",
        "import importlib",
        "import importlib.util",
        "import site",
        "import subprocess",
        "import sys",
        "",
        "for _stream in (sys.stdout, sys.stderr):",
        '    if _stream is not None and hasattr(_stream, "reconfigure"):',
        "        try:",
        '            _stream.reconfigure(encoding="utf-8", errors="replace")',
        "        except Exception:",
        "            try:",
        '                _stream.reconfigure(errors="replace")',
        "            except Exception:",
        "                pass",
        "",
        *pkg_lines,
        "",
        "",
        "def _ensure_dependencies(packages: dict) -> None:",
        '    """Проверяет импорты и автоматически догружает недостающие библиотеки через pip."""',
        "    missing = [",
        "        pip_name",
        "        for mod_name, pip_name in packages.items()",
        "        if importlib.util.find_spec(mod_name) is None",
        "    ]",
        "    if not missing:",
        "        return",
        "",
        '    missing_str = ", ".join(missing)',
        '    pip_args_str = " ".join(missing)',
        '    print(f"📦 Не найдены библиотеки: {missing_str}. Начинаю автоматическую установку...")',
        "    try:",
        '        subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])',
        "    except (subprocess.CalledProcessError, OSError):",
        '        print("⚠ Пробую установку в пользовательскую папку (--user)...")',
        "        try:",
        '            subprocess.check_call([sys.executable, "-m", "pip", "install", "--user", *missing])',
        "            user_site = site.getusersitepackages()",
        "            if user_site and user_site not in sys.path:",
        "                sys.path.append(user_site)",
        "        except Exception as exc:",
        '            print(f"❌ Не удалось автоматически установить библиотеки: {exc}")',
        '            print(f"Установите вручную командой: pip install {pip_args_str}")',
        "            sys.exit(1)",
        "",
        "    importlib.invalidate_caches()",
        '    print("✅ Библиотеки догружены, продолжаю выполнение скрипта...")',
        "",
        "",
        "_ensure_dependencies(REQUIRED_PACKAGES)",
        "",
    ]


def _clean_comment_line(text: object, max_len: int = 48) -> str:
    """Превращает произвольный текст в безопасную однострочную подпись для комментария."""
    s = str(text or "").replace("\r", " ").replace("\n", " ").strip()
    s = " ".join(s.split())
    if len(s) > max_len:
        s = s[: max_len - 1] + "…"
    return s


def _safe_docstring_line(text: object) -> str:
    """Экранирует тройные кавычки и переносы строк внутри докстринга."""
    return str(text or "").replace('"""', "'''").replace("\r", " ").replace("\n", " ").strip()


_PATH_ATTR_CANDIDATES = (
    "full_path", "filepath", "file_path", "path", "source_path",
    "excel_path", "orig_path", "original_path", "filename", "file_name",
    "file", "source", "location",
)
_TABLE_EXTS = (".xlsx", ".xls", ".xlsm", ".xlsb", ".csv", ".ods")


def _extract_path_from_obj(obj) -> str:
    """Извлекает реальный путь к Excel/CSV-файлу из объекта данных, записи FileManager или словаря."""
    if obj is None:
        return ""
    if isinstance(obj, (str, Path)):
        s = str(obj).strip()
        return s if (s and s.lower().endswith(_TABLE_EXTS) and s.lower() != "data.xlsx") else ""

    candidates: list[str] = []

    def _collect(val):
        if isinstance(val, (str, Path)):
            s = str(val).strip()
            if s and s.lower() != "data.xlsx":
                if s.lower().endswith(_TABLE_EXTS) or ("\\" in s or "/" in s):
                    if s not in candidates:
                        candidates.append(s)

    if isinstance(obj, dict):
        for k in _PATH_ATTR_CANDIDATES:
            _collect(obj.get(k))
        for v in obj.values():
            _collect(v)
    else:
        for attr in _PATH_ATTR_CANDIDATES:
            _collect(getattr(obj, attr, None))
        try:
            for v in vars(obj).values():
                _collect(v)
        except Exception:
            pass

    if not candidates:
        return ""
    for c in candidates:
        try:
            if Path(c).is_file():
                return str(Path(c).resolve())
        except Exception:
            pass
    for c in candidates:
        if "\\" in c or "/" in c:
            return c
    for c in candidates:
        if c.lower().endswith(_TABLE_EXTS):
            return c
    return candidates[0]


def _format_py_value(val, indent: int = 8) -> str:
    """Рекурсивно форматирует Python-значение (dict, list, ReportBlock, примитивы) с ровными 4-пробельными отступами."""
    sp = " " * indent
    inner_sp = " " * (indent + 4)

    # Объект блока (ReportBlock) внутри children
    if hasattr(val, "id") and hasattr(val, "type") and hasattr(val, "config") and not isinstance(val, dict):
        b_id = getattr(val, "id", "")
        b_type = getattr(val, "type", "")
        b_cfg = getattr(val, "config", {}) or {}
        cfg_fmt = _format_py_value(b_cfg, indent + 4)
        return (
            "ReportBlock(\n"
            f"{inner_sp}id={b_id!r},\n"
            f"{inner_sp}type={b_type!r},\n"
            f"{inner_sp}config={cfg_fmt},\n"
            f"{sp})"
        )

    if isinstance(val, dict):
        if not val:
            return "{}"
        lines = ["{"]
        for k, v in val.items():
            v_str = _format_py_value(v, indent + 4)
            lines.append(f"{inner_sp}{k!r}: {v_str},")
        lines.append(f"{sp}}}")
        return "\n".join(lines)

    if isinstance(val, (list, tuple)):
        open_ch, close_ch = ("[", "]") if isinstance(val, list) else ("(", ")")
        if not val:
            return f"{open_ch}{close_ch}"
        # Короткий список простых значений оставляем в одну строку
        all_simple = all(isinstance(x, (str, int, float, bool, type(None))) for x in val)
        if all_simple and len(val) <= 6:
            one_line = f"{open_ch}" + ", ".join(repr(x) for x in val) + ("," if isinstance(val, tuple) and len(val) == 1 else "") + f"{close_ch}"
            if len(one_line) <= 84:
                return one_line
        lines = [open_ch]
        for item in val:
            item_str = _format_py_value(item, indent + 4)
            lines.append(f"{inner_sp}{item_str},")
        lines.append(f"{sp}{close_ch}")
        return "\n".join(lines)

    if isinstance(val, (str, int, float, bool, type(None))):
        return repr(val)

    return repr(str(val))


def _wrap_html(body: str, title: str) -> str:
    """Оборачивает HTML-тело отчёта в автономный HTML-документ со стилями и Plotly."""
    safe_title = (
        str(title or "Отчёт")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    tpl = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<title>__TITLE__</title>
<style>
    * { box-sizing: border-box; }
    .js-plotly-plot, .plot-container, .user-select-none {
        width: 100% !important;
        max-width: 100% !important;
    }
    body {
        margin: 0;
        padding: 0;
        font-family: Arial, sans-serif;
        background: #f5f7f9;
        color: #222;
    }
    .container-row {
        display: flex;
        flex-wrap: wrap;
        align-items: stretch;
        gap: 16px;
        width: 100%;
    }
    .container-column {
        display: flex;
        flex-direction: column;
        gap: 16px;
        width: 100%;
    }
    h1.section-title {
        color: #003F0B;
        font-size: 1.8rem;
        font-weight: 700;
        margin: 25px 0 10px 0;
        padding-bottom: 8px;
        border-bottom: 2px solid #87C800;
        scroll-margin-top: 25px;
    }
    .block {
        margin-bottom: 0;
        display: block;
        min-width: 0;
        width: 100%;
    }
    .block-card {
        background: #fff;
        border: 1px solid #e0e0e5;
        border-radius: 10px;
        padding: 20px;
        min-width: 0;
        width: 100%;
        box-shadow: 0 2px 6px rgba(15, 23, 42, 0.03);
    }
    .kpi-row { display: flex; gap: 16px; flex-wrap: wrap; }
    .kpi-card {
        flex: 1 1 120px;
        background: #fff;
        border: 1px solid #e0e0e5;
        border-radius: 10px;
        padding: 16px;
    }
    .kpi-value { font-size: 26px; font-weight: 700; }
    .kpi-value.accent { color: #2bb24c; }
    .kpi-label { color: #666; font-size: 12px; margin-top: 4px; }
    .section-divider { height: 1px; background: #ddd; margin: 20px 0; }
    :root { --toc-width: clamp(185px, 17vw, 250px); }
    .report-toc {
        position: fixed;
        left: 0;
        top: 0;
        width: var(--toc-width);
        height: 100vh;
        background: #ffffff;
        border-right: 1px solid #e0e0e0;
        overflow-y: auto;
        padding: 16px;
        box-shadow: 2px 0 5px rgba(0, 0, 0, 0.05);
        z-index: 100;
    }
    .report-toc h2 {
        font-size: 1.15rem;
        margin: 0 0 14px 0;
        color: #003F0B;
        border-bottom: 2px solid #87C800;
        padding-bottom: 8px;
    }
    .report-toc ul { list-style: none; padding-left: 0; margin: 0; }
    .report-toc ul li { margin: 5px 0; }
    .toc-item {
        text-decoration: none;
        color: #195532;
        font-weight: 500;
        font-size: 12.5px;
        display: block;
        padding: 6px 10px;
        border-radius: 6px;
        cursor: pointer;
    }
    .toc-item:hover { background: #e9f5e9; color: #003F0B; }
    .toc-item.active { background: #87C800; color: #ffffff; font-weight: bold; }
    .report-content {
        margin-left: var(--toc-width);
        padding: 16px clamp(14px, 2.2vw, 30px) 36px;
        width: calc(100% - var(--toc-width));
        max-width: calc(100% - var(--toc-width));
    }
    @media (max-width: 860px) {
        .report-toc {
            position: static;
            width: 100%;
            height: auto;
            border-right: none;
            border-bottom: 1px solid #e0e0e0;
            margin-bottom: 12px;
        }
        .report-content {
            margin-left: 0;
            width: 100%;
            max-width: 100%;
            padding: 12px;
        }
    }
</style>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
</head>
<body>
__BODY__
<script>
(function() {
    var items = document.querySelectorAll('.toc-item');
    items.forEach(function(item) {
        item.addEventListener('click', function(e) {
            e.preventDefault();
            var targetId = this.getAttribute('data-target');
            var target = document.getElementById(targetId);
            if (target) {
                items.forEach(function(i) { i.classList.remove('active'); });
                this.classList.add('active');
                target.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        });
    });
})();
</script>
</body>
</html>"""
    return tpl.replace("__TITLE__", safe_title).replace("__BODY__", body)


class ReportCodeGenerator:
    """Генерирует корректный Python-скрипт с правильными отступами для запуска в VS Code."""

    def __init__(self, report_model, file_name: str = "data.xlsx", sheet_name: str | None = None, **kwargs):
        self.report = report_model
        self.file_name = str(file_name or "data.xlsx")
        self.sheet_name = sheet_name

    @staticmethod
    def _serialize_block(block) -> dict:
        """Сериализует блок (включая вложенные children) в словарь — используется и для баг-репортов."""
        if isinstance(block, dict):
            b_id = block.get("id", "")
            b_type = block.get("type", "")
            raw_cfg = dict(block.get("config") or {})
        else:
            b_id = getattr(block, "id", "")
            b_type = getattr(block, "type", "")
            raw_cfg = dict(getattr(block, "config", {}) or {})

        if "children" in raw_cfg and isinstance(raw_cfg["children"], list):
            raw_cfg["children"] = [
                ReportCodeGenerator._serialize_block(ch) for ch in raw_cfg["children"]
            ]

        return {"id": b_id, "type": b_type, "config": raw_cfg}

    def _collect_excel_files(self) -> dict[str, str]:
        """Собирает словарь {имя_файла_в_проекте: реальный_путь_на_диске} из FileManager и редактора."""
        result: dict[str, str] = {}
        fm = getattr(self.report, "file_manager", None)

        if fm is not None:
            # 1. Обход записей через get_all()
            if hasattr(fm, "get_all"):
                try:
                    for entry in (fm.get_all() or []):
                        data_obj = getattr(entry, "data", None)
                        fp = _extract_path_from_obj(entry) or _extract_path_from_obj(data_obj)
                        if fp:
                            fname = (
                                getattr(entry, "file_name", None)
                                or getattr(entry, "name", None)
                                or Path(fp).name
                            )
                            result[str(fname)] = fp
                except Exception:
                    pass

            # 2. Обход внутренних словарей FileManager (_files, files, _entries, _paths и т.д.)
            try:
                for attr_val in vars(fm).values():
                    if not isinstance(attr_val, dict):
                        continue
                    for k, v in attr_val.items():
                        fp = _extract_path_from_obj(v) or _extract_path_from_obj(getattr(v, "data", None)) or _extract_path_from_obj(k)
                        if fp:
                            key_name = Path(fp).name
                            if key_name not in result or not ("\\" in result[key_name] or "/" in result[key_name]):
                                result[key_name] = fp
            except Exception:
                pass

            # 3. Сопоставляем имена файлов из get_files_dict() (их используют блоки в source_file_name)
            if hasattr(fm, "get_files_dict"):
                try:
                    by_basename = {Path(p).name.lower(): p for p in result.values()}
                    for f_key in fm.get_files_dict().keys():
                        f_str = str(f_key).strip()
                        if not f_str:
                            continue
                        if f_str not in result:
                            matched = by_basename.get(Path(f_str).name.lower())
                            if matched:
                                result[f_str] = matched
                            elif Path(f_str).is_file():
                                result[f_str] = str(Path(f_str).resolve())
                except Exception:
                    pass

        # 4. Добавляем путь из активного файла редактора, если он передан
        if self.file_name and self.file_name.lower() != "data.xlsx":
            ed_name = Path(self.file_name).name
            if ed_name not in result or not ("\\" in result[ed_name] or "/" in result[ed_name]):
                result[ed_name] = self.file_name

        if not result and self.file_name:
            result[Path(self.file_name).name] = self.file_name
        return result

    def _collect_column_renames(self) -> dict[str, str]:
        """Собирает переименования колонок из Редактора (get_display_name), чтобы выгруженный скрипт совпадал с предпросмотром."""
        renames: dict[str, str] = {}
        fm = getattr(self.report, "file_manager", None)
        if fm is not None and hasattr(fm, "get_all"):
            try:
                for entry in (fm.get_all() or []):
                    data_obj = getattr(entry, "data", entry)
                    df_obj = getattr(data_obj, "dataframe", None)
                    if df_obj is not None and hasattr(data_obj, "get_display_name"):
                        for col in df_obj.columns:
                            disp = data_obj.get_display_name(col)
                            if disp and disp != col:
                                renames[str(col)] = str(disp)
            except Exception:
                pass
        return renames

    def _resolve_initial_sheet(self):
        """Определяет стартовый лист: из параметра, FileManager или первого фильтра/графика отчёта."""
        if self.sheet_name not in (None, "", 0):
            return self.sheet_name

        fm = getattr(self.report, "file_manager", None)
        if fm is not None and hasattr(fm, "get_default_file_and_sheet"):
            try:
                _, def_s = fm.get_default_file_and_sheet()
                if def_s:
                    return def_s
            except Exception:
                pass

        # Если дефолтный лист не задан — берём source_sheet из первого блока отчёта (включая контейнеры)
        def _walk(blocks):
            for b in (blocks or []):
                cfg = (b.get("config") if isinstance(b, dict) else getattr(b, "config", {})) or {}
                sh = cfg.get("source_sheet") or cfg.get("source_file")
                if sh:
                    return sh
                ch = cfg.get("children")
                if isinstance(ch, list):
                    found = _walk(ch)
                    if found:
                        return found
            return None

        for sec in getattr(self.report, "sections", []) or []:
            found_sh = _walk(getattr(sec, "blocks", []))
            if found_sh:
                return found_sh
        return 0

    def _emit_block_code(self, block, idx_label: str, sec_var: str) -> list[str]:
        lines: list[str] = []
        b_type = block.get("type", "paragraph") if isinstance(block, dict) else getattr(block, "type", "paragraph")
        cfg = dict((block.get("config") if isinstance(block, dict) else getattr(block, "config", {})) or {})
        b_id = block.get("id", f"blk_{idx_label}") if isinstance(block, dict) else getattr(block, "id", f"blk_{idx_label}")

        type_descriptions = {
            "section_title": "Заголовок раздела",
            "paragraph": "Аналитический текст / Умный вывод с макросами",
            "list": "Маркированный список",
            "divider": "Разделитель",
            "kpi_row": "KPI-карточки (Метрики)",
            "data_table": "Реестр путевых листов / Таблица данных",
            "pivot_matrix": "Сводная матрица (с формулами и Drill-Down)",
            "decomposition": "Дерево декомпозиции (Treemap / Sunburst)",
            "geo_map": "Гео-карта объектов и рейтинг",
            "plotly_chart": "Интерактивный график Plotly",
            "dashboard_filter": "Интерактивный фильтр (Срез данных)",
            "container": "Контейнер (сетка для расположения блоков рядом)",
        }
        readable_desc = type_descriptions.get(b_type, b_type)
        raw_hint = cfg.get("title") or cfg.get("text") or ""
        clean_hint = _clean_comment_line(raw_hint, max_len=42)
        hint_suffix = f" — «{clean_hint}»" if clean_hint else ""

        cfg_str = _format_py_value(cfg, indent=8)

        lines.append("    # " + "-" * 60)
        lines.append(f"    # Блок {idx_label}: {readable_desc}{hint_suffix}")
        lines.append(f"    # ID: {b_id} | Тип: {b_type}")
        lines.append("    # " + "-" * 60)
        lines.append(f"    block_{idx_label} = ReportBlock(")
        lines.append(f"        id={b_id!r},")
        lines.append(f"        type={b_type!r},")
        lines.append(f"        config={cfg_str},")
        lines.append("    )")
        lines.append(f"    {sec_var}.add_block(block_{idx_label})")
        lines.append("")
        return lines

    def generate(self) -> str:
        report_title = str(getattr(self.report, "title", "Аналитический отчёт") or "Аналитический отчёт")
        excel_files_map = self._collect_excel_files()

        primary_file_path = self.file_name
        if (
            not primary_file_path
            or primary_file_path.lower() == "data.xlsx"
            or not Path(primary_file_path).is_file()
        ) and excel_files_map:
            cand_by_name = excel_files_map.get(Path(primary_file_path).name) if primary_file_path else None
            primary_file_path = cand_by_name or next(iter(excel_files_map.values()))

        sheet_val = self._resolve_initial_sheet()
        col_renames_map = self._collect_column_renames()

        engine_b64_chunks = _build_embedded_engine_b64()

        lines: list[str] = [
            '"""',
            f"Автономный Python-отчёт NexGrid: {_safe_docstring_line(report_title)}",
            f"Сгенерировано: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            "",
            "Работает на любом ПК (установка программы NexGrid не требуется).",
            "Как запустить:",
            "1. Установите зависимости (один раз): pip install pandas openpyxl plotly",
            "2. Положите Excel-файл с данными рядом с этим скриптом (или укажите путь в FILE_PATH).",
            "3. Запустите файл в VS Code или через python — откроется интерактивный HTML-отчёт.",
            '"""',
            "",
            "from dataclasses import dataclass, field",
            "from pathlib import Path",
            "import base64",
            "import json",
            "import types",
            "import uuid",
            "import webbrowser",
            "import zlib",
            "",
            *_make_auto_install_lines({
                "pandas": "pandas",
                "numpy": "numpy",
                "openpyxl": "openpyxl",
                "plotly": "plotly",
            }),
            "import numpy as np  # noqa: E402, F401",
            "import openpyxl  # noqa: E402, F401",
            "import pandas as pd  # noqa: E402",
            "import plotly  # noqa: E402, F401",
            "",
            "",
            "# ============================================================",
            "# КОНФИГУРАЦИЯ (укажите свой путь к Excel при необходимости)",
            "# ============================================================",
            f"FILE_PATH = Path({primary_file_path!r})",
            f"SHEET_NAME = {sheet_val!r}",
            'OUTPUT_HTML = Path("final_dashboard_report.html")',
            "OPEN_IN_BROWSER = True",
            "",
            f"EXCEL_FILES = {_format_py_value(excel_files_map, indent=0)}",
            f"COLUMN_RENAMES = {_format_py_value(col_renames_map, indent=0)}",
            "",
            "",
            "# ============================================================",
            "# МОДЕЛЬ ОТЧЁТА И ЗАГРУЗЧИК EXCEL (АВТОНОМНЫЕ)",
            "# ============================================================",
            "@dataclass",
            "class ReportBlock:",
            "    id: str",
            "    type: str",
            "    config: dict = field(default_factory=dict)",
            "",
            "    @classmethod",
            "    def create(cls, block_type: str, config: dict | None = None):",
            "        return cls(id=uuid.uuid4().hex[:8], type=block_type, config=dict(config or {}))",
            "",
            "",
            "@dataclass",
            "class ReportSection:",
            "    id: str",
            "    title: str",
            '    icon: str = "📊"',
            "    blocks: list = field(default_factory=list)",
            "",
            "    def add_block(self, block: ReportBlock):",
            "        self.blocks.append(block)",
            "        return block",
            "",
            "",
            "class Report:",
            '    def __init__(self, title: str = "Отчёт", file_manager=None):',
            "        self.title = title",
            "        self.sections: list[ReportSection] = []",
            "        self.file_manager = file_manager",
            "",
            '    def add_section(self, title: str, icon: str = "📊") -> ReportSection:',
            "        sec = ReportSection(id=uuid.uuid4().hex[:8], title=title, icon=icon)",
            "        self.sections.append(sec)",
            "        return sec",
            "",
            "    def find_block(self, block_id: str):",
            "        def _search(blocks_list):",
            "            for b in (blocks_list or []):",
            '                b_id = b.get("id") if isinstance(b, dict) else getattr(b, "id", None)',
            "                if b_id == block_id:",
            "                    return b",
            '                b_type = b.get("type") if isinstance(b, dict) else getattr(b, "type", "")',
            '                if b_type == "container":',
            '                    b_cfg = b.get("config", {}) if isinstance(b, dict) else (getattr(b, "config", {}) or {})',
            '                    hit = _search(b_cfg.get("children", []))',
            "                    if hit is not None:",
            "                        return hit",
            "            return None",
            "",
            "        for sec in self.sections:",
            "            found = _search(sec.blocks)",
            "            if found is not None:",
            "                return sec, found",
            "        return None",
            "",
            "    def get_block_dataframe(self, cfg: dict, fallback_df=None):",
            "        fm = self.file_manager",
            "        if fm is None:",
            "            return fallback_df",
            '        f_name = str((cfg or {}).get("source_file_name", "") or "").strip()',
            '        s_name = str((cfg or {}).get("source_sheet", "") or (cfg or {}).get("source_file", "") or "").strip()',
            '        if not s_name and (cfg or {}).get("target_chart"):',
            '            found = self.find_block(str(cfg["target_chart"]))',
            "            if found is not None:",
            '                c_cfg = found[1].get("config", {}) if isinstance(found[1], dict) else (getattr(found[1], "config", {}) or {})',
            '                f_name = f_name or str(c_cfg.get("source_file_name", "") or "").strip()',
            '                s_name = s_name or str(c_cfg.get("source_sheet", "") or c_cfg.get("source_file", "") or "").strip()',
            "        df = fm.get_dataframe(f_name, s_name) if (f_name or s_name) else fallback_df",
            '        req_col = str((cfg or {}).get("filter_col", "") or "").strip()',
            "        if req_col and (df is None or req_col not in df.columns):",
            "            alt = fm.find_dataframe_with_column(req_col)",
            "            if alt is not None:",
            "                return alt",
            "        return df if df is not None else fallback_df",
            "",
            "",
            "class _StandaloneSheetEntry:",
            "    def __init__(self, file_name: str, sheet_name: str, df: pd.DataFrame, path: Path):",
            "        self.name = file_name",
            "        self.file_name = file_name",
            "        self.sheet_name = sheet_name",
            "        self.filepath = str(path)",
            "        self.dataframe = df",
            "        self.data = self",
            "",
            "",
            "class StandaloneFileManager:",
            '    """Загружает Excel-файлы с диска или из папки рядом со скриптом."""',
            "",
            "    def __init__(self, files_map: dict, default_path: Path, default_sheet=0, col_renames: dict | None = None):",
            "        self._sheets: dict[str, dict[str, pd.DataFrame]] = {}",
            "        self._entries: list[_StandaloneSheetEntry] = []",
            '        self._default_file = ""',
            '        self._default_sheet = ""',
            "        script_dir = Path(__file__).resolve().parent",
            "        renames = dict(col_renames or {})",
            "",
            "        to_load = {str(k): Path(v) for k, v in (files_map or {}).items()}",
            "        if not to_load and default_path:",
            "            to_load[default_path.name] = default_path",
            "",
            "        loaded_by_path: dict[str, dict[str, pd.DataFrame]] = {}",
            "        for display_name, f_path in to_load.items():",
            "            resolved = self._resolve_excel_path(f_path, script_dir, len(to_load) == 1)",
            "            if resolved is None:",
            '                print(f"⚠ Файл не найден: {f_path}")',
            '                print(f"  Положите «{f_path.name}» в папку {script_dir} или поправьте FILE_PATH.")',
            "                continue",
            "            try:",
            "                res_key = str(resolved)",
            "                if res_key in loaded_by_path:",
            "                    self._sheets[display_name] = loaded_by_path[res_key]",
            "                    continue",
            '                if resolved.suffix.lower() == ".csv":',
            '                    all_sheets = {"Sheet1": pd.read_csv(resolved)}',
            "                else:",
            "                    all_sheets = pd.read_excel(resolved, sheet_name=None)",
            "                loaded_map: dict[str, pd.DataFrame] = {}",
            "                for sh_k, sh_df in all_sheets.items():",
            "                    if renames:",
            "                        r_sub = {c: renames[c] for c in sh_df.columns if c in renames}",
            "                        if r_sub:",
            "                            sh_df = sh_df.rename(columns=r_sub)",
            "                    sh_name = str(sh_k)",
            "                    loaded_map[sh_name] = sh_df",
            "                    self._entries.append(_StandaloneSheetEntry(display_name, sh_name, sh_df, resolved))",
            "                self._sheets[display_name] = loaded_map",
            "                loaded_by_path[res_key] = loaded_map",
            "                if isinstance(default_sheet, str) and default_sheet in loaded_map:",
            "                    self._default_file = display_name",
            "                    self._default_sheet = default_sheet",
            "                elif not self._default_file and loaded_map:",
            "                    self._default_file = display_name",
            "                    sheet_names = list(loaded_map.keys())",
            "                    if isinstance(default_sheet, int) and 0 <= default_sheet < len(sheet_names):",
            "                        self._default_sheet = sheet_names[default_sheet]",
            "                    else:",
            "                        self._default_sheet = sheet_names[0]",
            '                print(f"📂 Загружен файл: {resolved} (листов: {len(loaded_map)})")',
            "            except Exception as exc:",
            '                print(f"⚠ Ошибка чтения {resolved}: {exc}")',
            "",
            "    @staticmethod",
            "    def _resolve_excel_path(f_path: Path, script_dir: Path, allow_single_fallback: bool):",
            "        candidates = [",
            "            f_path,",
            "            script_dir / f_path.name,",
            "            Path.cwd() / f_path.name,",
            "        ]",
            "        for cand in candidates:",
            "            if cand.is_file():",
            "                return cand.resolve()",
            "        if allow_single_fallback:",
            '            local_excels = [p for p in script_dir.iterdir() if p.is_file() and p.suffix.lower() in (".xlsx", ".xls", ".xlsm") and not p.name.startswith("~$")]',
            "            if len(local_excels) == 1:",
            "                return local_excels[0].resolve()",
            "        return None",
            "",
            "    def get_all(self) -> list:",
            "        return list(self._entries)",
            "",
            "    def get_files_dict(self) -> dict[str, list[str]]:",
            "        return {fname: list(sheets.keys()) for fname, sheets in self._sheets.items()}",
            "",
            "    def get_default_file_and_sheet(self) -> tuple[str, str]:",
            "        return self._default_file, self._default_sheet",
            "",
            "    def find_dataframe_with_column(self, col_name: str):",
            "        target = str(col_name or '').strip()",
            "        if not target:",
            "            return None",
            "        for sheets in self._sheets.values():",
            "            for df in sheets.values():",
            "                if target in df.columns:",
            "                    return df",
            "        return None",
            "",
            '    def get_dataframe(self, file_name: str = "", sheet_name: str = ""):',
            '        f_key = str(file_name or "").strip()',
            '        s_key = str(sheet_name or "").strip()',
            "        # Поиск файла по точному имени или по базовому имени файла",
            "        if f_key and f_key not in self._sheets:",
            "            f_base = Path(f_key).name.lower()",
            "            for k in self._sheets.keys():",
            "                if Path(k).name.lower() == f_base:",
            "                    f_key = k",
            "                    break",
            "        if not f_key or f_key not in self._sheets:",
            "            if s_key:",
            "                for k, sh_map in self._sheets.items():",
            "                    if s_key in sh_map:",
            "                        return sh_map[s_key]",
            "            f_key = self._default_file or (next(iter(self._sheets.keys())) if self._sheets else '')",
            "        sheets = self._sheets.get(f_key, {})",
            "        if not sheets:",
            "            return None",
            "        if s_key in sheets:",
            "            return sheets[s_key]",
            "        if s_key:",
            "            for sh_map in self._sheets.values():",
            "                if s_key in sh_map:",
            "                    return sh_map[s_key]",
            "        if self._default_sheet in sheets:",
            "            return sheets[self._default_sheet]",
            "        return next(iter(sheets.values()))",
            "",
            "",
            "def main():",
            '    print("🚀 Запуск автономного генератора отчёта NexGrid...")',
            "    file_manager = StandaloneFileManager(EXCEL_FILES, FILE_PATH, SHEET_NAME, COLUMN_RENAMES)",
            "    default_df = file_manager.get_dataframe()",
            "    if default_df is None:",
            '        print("❌ Не удалось загрузить данные. Положите Excel-файл рядом со скриптом и повторите запуск.")',
            "        sys.exit(1)",
            "",
            f"    report = Report(title={report_title!r}, file_manager=file_manager)",
            "",
        ]

        sections = getattr(self.report, "sections", []) or []
        for s_idx, sec in enumerate(sections, start=1):
            sec_title = _clean_comment_line(getattr(sec, "title", f"Раздел {s_idx}"), max_len=60)
            sec_icon = str(getattr(sec, "icon", "📊") or "📊")
            sec_id = getattr(sec, "id", f"sec_{s_idx}")
            sec_var = f"sec_{s_idx}"

            lines.append("    # " + "=" * 60)
            lines.append(f"    # РАЗДЕЛ {s_idx}: «{sec_title}» (ID: {sec_id})")
            lines.append("    # " + "=" * 60)
            lines.append(
                f"    {sec_var} = report.add_section("
                f"title={getattr(sec, 'title', '')!r}, icon={sec_icon!r})"
            )
            lines.append(f"    {sec_var}.id = {sec_id!r}")
            lines.append("")

            for b_idx, block in enumerate(getattr(sec, "blocks", []) or [], start=1):
                lines.extend(self._emit_block_code(block, f"s{s_idx}_b{b_idx}", sec_var))

        lines.extend([
            "    # Рендеринг полного HTML-отчёта через встроенный движок",
            '    print("🎨 Сборка интерактивного HTML-дашборда...")',
            "    RenderContext, render_report, html_shell = _load_nexgrid_engine()",
            "    ctx = RenderContext(",
            "        dataframe=default_df,",
            "        preview_limit=0,",
            "        report=report,",
            "        file_manager=file_manager,",
            "    )",
            "    body_html = render_report(report, ctx)",
            "    safe_title = (",
            '        str(report.title or "Отчёт")',
            '        .replace("&", "&amp;")',
            '        .replace("<", "&lt;")',
            '        .replace(">", "&gt;")',
            "    )",
            '    final_html = html_shell.replace("__TITLE__", safe_title).replace("__BODY__", body_html)',
            "",
            '    OUTPUT_HTML.write_text(final_html, encoding="utf-8")',
            '    print(f"✅ Отчёт сохранён: {OUTPUT_HTML.resolve()}")',
            "    if OPEN_IN_BROWSER:",
            "        webbrowser.open(OUTPUT_HTML.resolve().as_uri())",
            "",
            "",
            "# ============================================================",
            "# ВСТРОЕННЫЙ ДВИЖОК РЕНДЕРИНГА NEXGRID (НЕ РЕДАКТИРОВАТЬ)",
            "# ============================================================",
            "def _load_nexgrid_engine():",
            '    raw = zlib.decompress(base64.b64decode(_NEXGRID_ENGINE_B64)).decode("utf-8")',
            "    payload = json.loads(raw)",
            "",
            '    pkg_src = types.ModuleType("src")',
            "    pkg_src.__path__ = []",
            '    pkg_core = types.ModuleType("src.core")',
            "    pkg_core.__path__ = []",
            "    pkg_src.core = pkg_core",
            "",
            '    mod_rm = types.ModuleType("src.core.report_model")',
            "    mod_rm.Report = Report",
            "    mod_rm.ReportSection = ReportSection",
            "    mod_rm.ReportBlock = ReportBlock",
            "    pkg_core.report_model = mod_rm",
            "",
            '    mod_blocks = types.ModuleType("src.core.blocks")',
            '    mod_factory = types.ModuleType("src.core.block_factory")',
            "    pkg_core.blocks = mod_blocks",
            "    pkg_core.block_factory = mod_factory",
            "",
            '    sys.modules["src"] = pkg_src',
            '    sys.modules["src.core"] = pkg_core',
            '    sys.modules["src.core.report_model"] = mod_rm',
            '    sys.modules["src.core.blocks"] = mod_blocks',
            '    sys.modules["src.core.block_factory"] = mod_factory',
            "",
            '    exec(compile(payload["blocks"], "<nexgrid:blocks>", "exec"), mod_blocks.__dict__)',
            '    exec(compile(payload["block_factory"], "<nexgrid:block_factory>", "exec"), mod_factory.__dict__)',
            '    return mod_factory.RenderContext, mod_factory.render_report, payload["html_shell"]',
            "",
            "",
            "_NEXGRID_ENGINE_B64 = (",
        ])

        for chunk in engine_b64_chunks:
            lines.append(f"    {chunk!r}")

        lines.extend([
            ")",
            "",
            "",
            'if __name__ == "__main__":',
            "    main()",
            "",
        ])

        script = "\n".join(lines)
        ast.parse(script)
        return script


def generate_report_script(
    report_model,
    file_name: str = "data.xlsx",
    sheet_name: str | None = None,
    **kwargs,
) -> str:
    """Генерирует проверенный Python-скрипт отчёта из модели Конструктора."""
    try:
        gen = ReportCodeGenerator(report_model, file_name=file_name, sheet_name=sheet_name, **kwargs)
        return gen.generate()
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"# Ошибка генерации кода отчёта: {e}"