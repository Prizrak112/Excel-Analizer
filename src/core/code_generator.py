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


def _make_required_header(uid: str, h_doc: str, h_check: str) -> list:
    """Строки, которые обязаны быть в докстринге."""
    return [
        "",
        f"{SIGNATURE_MARKER}",
        f"UID: {uid}",
        f"Сгенерировано приложением: {APP_NAME} v{APP_VERSION}",
        f"Автор: {AUTHOR_NAME}",
        f"По всем вопросам: {AUTHOR_EMAIL}",
        f"Контрольная метка (doc): {h_doc}",
        f"Контрольная метка (meta): {h_check}",
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

    # Функция провала
    lines.append(f"def {p['n_fail']}():")
    lines.append('    print("=" * 60)')
    lines.append('    print("❌ Скрипт программы поврежден, просьба откатить файл")')
    lines.append('    print("=" * 60)')
    lines.append(f'    print("По вопросам: {AUTHOR_EMAIL}")')
    lines.append('    print("=" * 60)')
    lines.append(f"    {p['n_sys']}.exit(1)")
    lines.append("")

    # Универсальная функция проверки: принимает набор условий
    lines.append(f"def {p['n_check']}(*conditions):")
    lines.append('    """Проверяет список условий. Падает, если хоть одно False."""')
    lines.append("    for _c in conditions:")
    lines.append("        if not _c:")
    lines.append(f"            {p['n_fail']}()")
    lines.append("")

    # Регистрация проверки на выход
    lines.append(
        f"{p['n_atexit']}.register("
        f"lambda: {p['n_check']}({p['n_m6']} in ({p['n_uid']} + {p['n_m1']})))"
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
        return f"{chk}({m6} in ({u} + {m1}), {m6} != '')"
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
        for l in _make_required_header(p["uid"], p["h_doc"], p["h_check"]):
            lines.append(l)
        lines.append('"""')
        lines.append("")

        # ===== ИМПОРТЫ =====
        lines.append("import pandas as pd")
        lines.append("import numpy as np")
        lines.append("from pathlib import Path")
        lines.append("")

        # ===== БЛОК ЗАЩИТЫ =====
        for l in _make_protection_block(p):
            lines.append(l)

        # Первая проверка — сразу после импортов
        lines.append(f"# контроль 1")
        lines.append(_make_check_call(p, "doc"))
        lines.append("")

        # ===== КОНФИГУРАЦИЯ =====
        lines.append("# ============================================================")
        lines.append("# КОНФИГУРАЦИЯ")
        lines.append("# ============================================================")
        lines.append(f'SOURCE_FILE = Path(r"{self.file_name}")')
        lines.append(f'SHEET_NAME = {self.sheet_name!r}')
        lines.append(f'OUTPUT_FILE = Path(r"{self.output_name}")')
        lines.append(f"RESET_INDEX = {self.reset_index}")
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

class ReportCodeGenerator:
    """Генерирует автономный Python-скрипт для сборки HTML-дашборда."""
    
    def __init__(self, report_model, file_name: str = "data.xlsx", sheet_name: str | None = None, **kwargs):
        self.report = report_model
        self.file_name = file_name
        self.sheet_name = sheet_name

    def _emit_block_code(self, block, idx_label: str, target_list_var: str = "html_parts") -> list[str]:
        lines: list[str] = []
        b_type = getattr(block, "type", "paragraph")
        cfg = getattr(block, "config", {}) or {}

        width = max(15, min(100, int(cfg.get("width", 100))))
        align = str(cfg.get("align", "left"))
        offset_x = max(0, min(100 - width, int(cfg.get("offset_x", 0))))
        margin_top = int(cfg.get("margin_top", 0))
        margin_bottom = int(cfg.get("margin_bottom", 14))
        min_height = int(cfg.get("min_height", 0))

        lines.append(f"# --- Блок {idx_label}: {b_type} (ширина={width}%, позиция={align}, сдвиг={offset_x}%) ---")

        if b_type == "section_title":
            title_repr = repr(cfg.get("title", "Раздел"))
            lines.append(f"block_html_{idx_label} = f'<h1 class=\"section-title\">{{{title_repr}}}</h1>'")
            lines.append(f"{target_list_var}.append(block_html_{idx_label})")
            lines.append("")
            return lines

        if b_type == "divider":
            lines.append(f"{target_list_var}.append('<div class=\"section-divider\"></div>')")
            lines.append("")
            return lines

        if b_type == "paragraph":
            text_repr = repr(cfg.get("text", ""))
            lines.append(
                f"block_html_{idx_label} = f'<div class=\"block\"><div class=\"block-card\">"
                f"<div class=\"paragraph\">{{{text_repr}}}</div></div></div>'"
            )

        elif b_type == "list":
            items_repr = repr(cfg.get("items", []))
            html_raw = cfg.get("html", "")
            if cfg.get("raw_html") and html_raw:
                lines.append(
                    f"block_html_{idx_label} = f'<div class=\"block\"><div class=\"block-card\">"
                    f"<div class=\"list-rich\">{{{repr(html_raw)}}}</div></div></div>'"
                )
            else:
                lines.append(f"_items_{idx_label} = ''.join(f'<li>{{x}}</li>' for x in {items_repr})")
                lines.append(
                    f"block_html_{idx_label} = f'<div class=\"block\"><div class=\"block-card\">"
                    f"<ul class=\"block-list\">{{_items_{idx_label}}}</ul></div></div>'"
                )

        elif b_type == "kpi_row":
            cards_repr = repr(cfg.get("cards", []))
            lines.append(f"_cards_html_{idx_label} = []")
            lines.append(f"for _c in {cards_repr}:")
            lines.append("    _acc = ' accent' if _c.get('accent') else ''")
            lines.append(
                f"    _cards_html_{idx_label}.append("
                "f'<div class=\"kpi-card\">"
                "<div class=\"kpi-value{_acc}\">{_c.get(\"value\", \"\")}</div>"
                "<div class=\"kpi-label\">{_c.get(\"label\", \"\")}</div></div>')"
            )
            lines.append(
                f"block_html_{idx_label} = f'<div class=\"block\"><div class=\"kpi-row\">"
                f"{{''.join(_cards_html_{idx_label})}}</div></div>'"
            )

        elif b_type == "data_table":
            max_rows = int(cfg.get("max_rows", 20))
            vis_cols = cfg.get("visible_columns")
            lines.append(f"_df_tbl_{idx_label} = df.copy()")
            if vis_cols is not None:
                lines.append(f"_cols_{idx_label} = [c for c in {repr(vis_cols)} if c in _df_tbl_{idx_label}.columns]")
                lines.append(f"_df_tbl_{idx_label} = _df_tbl_{idx_label}[_cols_{idx_label}]")
            if max_rows > 0:
                lines.append(f"_df_tbl_{idx_label} = _df_tbl_{idx_label}.head({max_rows})")
            lines.append(
                f"block_html_{idx_label} = '<div class=\"block\"><div class=\"block-card\">' + "
                f"_df_tbl_{idx_label}.to_html(index=False, classes='ea-data-table') + '</div></div>'"
            )

        elif b_type == "plotly_chart":
            chart_type = cfg.get("chart_type", "bar")
            x_col = cfg.get("x_col", "")
            y_col = cfg.get("y_col", "")
            title = cfg.get("title", "График данных")
            agg = cfg.get("agg", "sum")
            sort_by = cfg.get("sort_by", "value_desc")
            top_n = int(cfg.get("top_n", 12))
            row_start = int(cfg.get("row_start", 0))
            row_limit = int(cfg.get("row_limit", 0))
            palette = cfg.get("palette", "corporate")
            bg_color = cfg.get("bg_color", "#ffffff")
            legend_pos = cfg.get("legend_pos", "right")
            show_legend = bool(cfg.get("show_legend", True))
            show_values = bool(cfg.get("show_values", True))
            show_grid = bool(cfg.get("show_grid", True))

            palettes_map = {
                "corporate": ["#2b7fff", "#87C800", "#ff9f1c", "#e71d36", "#6f42c1", "#20c997", "#fd7e14"],
                "emerald":   ["#003F0B", "#2bb24c", "#87C800", "#52b788", "#74c69d", "#95d5b2", "#b7e4c7"],
                "sunset":    ["#f72585", "#7209b7", "#3a0ca3", "#4361ee", "#4cc9f0", "#ff9e00", "#ff0055"],
                "pastel":    ["#60a5fa", "#34d399", "#fbbf24", "#f87171", "#a78bfa", "#f472b6", "#38bdf8"],
            }
            colors_list = palettes_map.get(palette, palettes_map["corporate"])

            lines.append(f"_work_df_{idx_label} = df.copy()")
            if row_start > 0 or row_limit > 0:
                end_expr = f"{row_start + row_limit}" if row_limit > 0 else f"len(_work_df_{idx_label})"
                lines.append(f"_work_df_{idx_label} = _work_df_{idx_label}.iloc[{row_start}:{end_expr}]")

            lines.append(
                f"_x_col_{idx_label} = {repr(x_col)} if ({repr(x_col)} in _work_df_{idx_label}.columns) "
                f"else _work_df_{idx_label}.columns[0]"
            )
            lines.append(f"_y_col_{idx_label} = {repr(y_col)}")

            if not y_col or agg == "count":
                lines.append(f"_grp_{idx_label} = _work_df_{idx_label}[_x_col_{idx_label}].astype(str).value_counts()")
                lines.append(
                    f"_plot_df_{idx_label} = pd.DataFrame({{_x_col_{idx_label}: _grp_{idx_label}.index, '_y_val': _grp_{idx_label}.values}})"
                )
            else:
                lines.append(
                    f"if _y_col_{idx_label} in _work_df_{idx_label}.columns:\n"
                    f"    _work_df_{idx_label}[_y_col_{idx_label}] = pd.to_numeric(_work_df_{idx_label}[_y_col_{idx_label}], errors='coerce').fillna(0)\n"
                    f"    _grp_{idx_label} = _work_df_{idx_label}.groupby(_work_df_{idx_label}[_x_col_{idx_label}].astype(str))[_y_col_{idx_label}].{agg}()\n"
                    f"    _plot_df_{idx_label} = pd.DataFrame({{_x_col_{idx_label}: _grp_{idx_label}.index, '_y_val': _grp_{idx_label}.values}})\n"
                    f"else:\n"
                    f"    _grp_{idx_label} = _work_df_{idx_label}[_x_col_{idx_label}].astype(str).value_counts()\n"
                    f"    _plot_df_{idx_label} = pd.DataFrame({{_x_col_{idx_label}: _grp_{idx_label}.index, '_y_val': _grp_{idx_label}.values}})"
                )

            if sort_by == "value_desc":
                lines.append(f"_plot_df_{idx_label} = _plot_df_{idx_label}.sort_values(by='_y_val', ascending=False)")
            elif sort_by == "value_asc":
                lines.append(f"_plot_df_{idx_label} = _plot_df_{idx_label}.sort_values(by='_y_val', ascending=True)")
            elif sort_by == "label_asc":
                lines.append(f"_plot_df_{idx_label} = _plot_df_{idx_label}.sort_values(by=_x_col_{idx_label}, ascending=True)")

            if top_n > 0:
                lines.append(f"_plot_df_{idx_label} = _plot_df_{idx_label}.head({top_n})")

            if chart_type == "bar":
                lines.append(
                    f"_fig_{idx_label} = px.bar(_plot_df_{idx_label}, x=_x_col_{idx_label}, y='_y_val', "
                    f"color=_x_col_{idx_label}, color_discrete_sequence={repr(colors_list)}, "
                    f"title={repr(title)}, text='_y_val' if {show_values} else None)"
                )
                if show_values:
                    lines.append(f"_fig_{idx_label}.update_traces(texttemplate='%{{text:,.0f}}', textposition='outside')")
            elif chart_type == "hbar":
                lines.append(
                    f"_fig_{idx_label} = px.bar(_plot_df_{idx_label}, x='_y_val', y=_x_col_{idx_label}, "
                    f"color=_x_col_{idx_label}, color_discrete_sequence={repr(colors_list)}, "
                    f"orientation='h', title={repr(title)}, text='_y_val' if {show_values} else None)"
                )
                if show_values:
                    lines.append(f"_fig_{idx_label}.update_traces(texttemplate='%{{text:,.0f}}', textposition='outside')")
            elif chart_type == "line":
                lines.append(
                    f"_fig_{idx_label} = px.line(_plot_df_{idx_label}, x=_x_col_{idx_label}, y='_y_val', "
                    f"title={repr(title)}, markers=True)"
                )
                lines.append(f"_fig_{idx_label}.update_traces(line=dict(color={repr(colors_list[0])}, width=3))")
            elif chart_type == "area":
                lines.append(
                    f"_fig_{idx_label} = px.area(_plot_df_{idx_label}, x=_x_col_{idx_label}, y='_y_val', title={repr(title)})"
                )
            elif chart_type == "scatter":
                lines.append(
                    f"_fig_{idx_label} = px.scatter(_plot_df_{idx_label}, x=_x_col_{idx_label}, y='_y_val', "
                    f"color=_x_col_{idx_label}, color_discrete_sequence={repr(colors_list)}, title={repr(title)})"
                )
            elif chart_type in ("pie", "donut"):
                hole_val = 0.52 if chart_type == "donut" else 0.0
                lines.append(
                    f"_fig_{idx_label} = px.pie(_plot_df_{idx_label}, names=_x_col_{idx_label}, values='_y_val', "
                    f"color_discrete_sequence={repr(colors_list)}, title={repr(title)}, hole={hole_val})"
                )
            elif chart_type == "histogram":
                lines.append(
                    f"_fig_{idx_label} = px.histogram(_work_df_{idx_label}, x=_x_col_{idx_label}, title={repr(title)}, "
                    f"color_discrete_sequence={repr(colors_list)})"
                )
            elif chart_type == "box":
                lines.append(
                    f"_fig_{idx_label} = px.box(_work_df_{idx_label}, y=_y_col_{idx_label} if _y_col_{idx_label} else _x_col_{idx_label}, title={repr(title)}, color_discrete_sequence={repr(colors_list)})"
                )
            elif chart_type == "funnel":
                lines.append(
                    f"_fig_{idx_label} = px.funnel(_plot_df_{idx_label}, x='_y_val', y=_x_col_{idx_label}, "
                    f"color=_x_col_{idx_label}, color_discrete_sequence={repr(colors_list)}, title={repr(title)})"
                )
            else:
                lines.append(
                    f"_fig_{idx_label} = px.bar(_plot_df_{idx_label}, x=_x_col_{idx_label}, y='_y_val', title={repr(title)})"
                )

            lines.append(
                f"_fig_{idx_label}.update_layout("
                f"plot_bgcolor={repr(bg_color)}, paper_bgcolor={repr(bg_color)}, "
                f"showlegend={str(show_legend)}, "
                f"xaxis=dict(showgrid={str(show_grid)}, tickangle=-25), "
                f"yaxis=dict(showgrid={str(show_grid)}))"
            )
            lines.append(
                f"block_html_{idx_label} = '<div class=\"block\"><div class=\"block-card\" "
                f"style=\"padding:16px; background:{bg_color}; border-radius:8px;\">' + "
                f"pio.to_html(_fig_{idx_label}, include_plotlyjs='cdn', full_html=False) + '</div></div>'"
            )

        elif b_type == "container":
            layout_kind = cfg.get("layout", "row")
            gap = int(cfg.get("gap", 14))
            children = cfg.get("children", [])
            flex_dir = "row" if layout_kind == "row" else "column"
            lines.append(f"_container_items_{idx_label} = []")
            for c_idx, child in enumerate(children):
                if isinstance(child, dict):
                    from src.core.report_model import ReportBlock
                    child = ReportBlock(
                        id=child.get("id", f"c_{c_idx}"),
                        type=child.get("type", "paragraph"),
                        config=child.get("config", {}),
                    )
                lines.extend(self._emit_block_code(child, f"{idx_label}_{c_idx}", f"_container_items_{idx_label}"))
            lines.append(
                f"block_html_{idx_label} = f'<div class=\"container-{layout_kind}\" "
                f"style=\"display:flex; flex-direction:{flex_dir}; gap:{gap}px;\">"
                f"{{''.join(_container_items_{idx_label})}}</div>'"
            )

        else:
            lines.append(f"block_html_{idx_label} = '<!-- неизвестный блок {b_type} -->'")

        lines.append(
            f"{target_list_var}.append(wrap_positioned_block("
            f"block_html_{idx_label}, width={width}, align={repr(align)}, "
            f"offset_x={offset_x}, margin_top={margin_top}, margin_bottom={margin_bottom}, min_height={min_height}))"
        )
        lines.append("")
        return lines

    def generate(self) -> str:
        lines: list[str] = [
            '"""',
            f'Автоматически сгенерированный скрипт отчёта: {getattr(self.report, "title", "Отчёт")}',
            '"""',
            "",
            "import pandas as pd",
            "import plotly.express as px",
            "import plotly.io as pio",
            "from pathlib import Path",
            "",
            f"FILE_PATH = {repr(str(self.file_name))}",
        ]
        if getattr(self, "sheet_name", None):
            lines.append(f"SHEET_NAME = {repr(self.sheet_name)}")
            lines.append("df = pd.read_excel(FILE_PATH, sheet_name=SHEET_NAME)")
        else:
            lines.append("df = pd.read_excel(FILE_PATH)")

        lines.extend([
            "",
            "def wrap_positioned_block(html: str, width: int = 100, align: str = 'left', offset_x: int = 0, margin_top: int = 0, margin_bottom: int = 14, min_height: int = 0) -> str:",
            "    min_h_css = f'min-height:{min_height}px;' if min_height > 0 else ''",
            "    if width >= 100:",
            "        return f'<div style=\"width:100%; margin-top:{margin_top}px; margin-bottom:{margin_bottom}px; {min_h_css}\">{html}</div>'",
            "    justify = 'center' if align == 'center' else ('flex-end' if align == 'right' else 'flex-start')",
            "    ml = f'{offset_x}%' if (align == 'custom' and offset_x > 0) else '0'",
            "    return (",
            "        f'<div style=\"display:flex; width:100%; justify-content:{justify}; margin-top:{margin_top}px; margin-bottom:{margin_bottom}px;\">'",
            "        f'<div style=\"width:{width}%; max-width:{width}%; margin-left:{ml}; {min_h_css} box-sizing:border-box;\">{html}</div></div>'",
            "    )",
            "",
            "html_parts = []",
            "",
        ])

        sections = getattr(self.report, "sections", [])
        if sections:
            for s_idx, sec in enumerate(sections, start=1):
                sec_title = f"{getattr(sec, 'icon', '')} {getattr(sec, 'title', '')}".strip()
                lines.append(f"# ==================== РАЗДЕЛ {s_idx}: {sec_title} ====================")
                lines.append(f"html_parts.append({repr(f'<h1 class=\"section-title\">{sec_title}</h1>')})")
                lines.append("")
                for b_idx, block in enumerate(sec.blocks, start=1):
                    lines.extend(self._emit_block_code(block, f"s{s_idx}_b{b_idx}", "html_parts"))

        lines.extend([
            "full_html = '<!DOCTYPE html><html><head><meta charset=\"utf-8\">' \\",
            "    + '<title>' + " + repr(getattr(self.report, "title", "Отчёт")) + " + '</title>' \\",
            "    + '<style>body{font-family:Segoe UI,Arial,sans-serif;background:#f4f6f9;margin:0;padding:32px;}' \\",
            "    + '.section-title{color:#003F0B;border-bottom:2px solid #87C800;padding-bottom:8px;}' \\",
            "    + '.block-card{background:#fff;border:1px solid #e0e0e5;border-radius:8px;padding:16px;}</style></head>' \\",
            "    + '<body><div style=\"max-width:1200px;margin:0 auto;background:#fff;padding:36px 44px;border-radius:10px;\">' + '\\n'.join(html_parts) + '</div></body></html>'",
            "",
            "output_path = Path('report_output.html')",
            "output_path.write_text(full_html, encoding='utf-8')",
            "print(f'Отчёт успешно сохранён: {output_path.resolve()}')",
        ])

        return "\n".join(lines)


def generate_report_script(
    report_model,
    file_name: str = "data.xlsx",
    sheet_name: str | None = None,
    **kwargs,
) -> str:
    """Генерирует Python-скрипт для отчёта из модели Конструктора."""
    try:
        gen = ReportCodeGenerator(report_model, file_name=file_name, sheet_name=sheet_name, **kwargs)
        return gen.generate()
    except Exception as e:
        return f"# Ошибка генерации кода: {e}"