"""
Извлечение текста по шаблону (regex).

Чистая логика, без UI. Используется ExtractTextCommand.

Основная функция:
    extract_value(s, pattern) → (результат: str, ok: bool)

ok=False, если:
  • значение пустое / None / NaN,
  • шаблон не найден в строке,
  • regex некорректен.
"""

import re


# ============================================================
# Готовые шаблоны для типовых задач
# ============================================================

# Список: (название, regex, пример «было → стало»)
PRESETS: list[tuple[str, str, str]] = [
    (
        "Гос. номер РФ",
        r"Гос\.?\s*№\s*([^,\s]+)",
        'Трактор … , Гос.№36ЕТ7854, …  →  36ЕТ7854',
    ),
    (
        "VIN (17 символов)",
        r"[A-HJ-NPR-Z0-9]{17}",
        "VIN: XTA21150053918842  →  XTA21150053918842",
    ),
    (
        "Серийный / инв. номер",
        r"[Сс]ер(?:ия|\.)?\s*№?\s*([A-ZА-Я0-9\-]+)",
        "Сер.№ АБ-123  →  АБ-123",
    ),
    (
        "Всё после последней запятой",
        r",\s*([^,]+)$",
        "A, B, C  →  C",
    ),
]


# ============================================================
# Главная функция
# ============================================================

def extract_value(s, pattern: str) -> tuple[str, bool]:
    """
    Извлечь фрагмент из значения по regex-шаблону.

    Если в шаблоне есть группа захвата — берётся группа 1.
    Если групп нет — берётся всё найденное совпадение.
    """
    # ── None / NaN / пусто ──
    if s is None:
        return "", False

    try:
        import math
        if isinstance(s, float) and math.isnan(s):
            return "", False
    except Exception:
        pass

    text = str(s)
    if not text.strip():
        return "", False

    if not pattern:
        return "", False

    # ── Компиляция regex ──
    try:
        rx = re.compile(pattern)
    except re.error:
        return "", False

    # ── Поиск ──
    m = rx.search(text)
    if not m:
        return "", False

    # ── Группа 1, если есть; иначе — всё совпадение ──
    if m.lastindex and m.lastindex >= 1:
        result = m.group(1)
    else:
        result = m.group(0)

    if result is None:
        return "", False

    result = str(result).strip()
    if not result:
        return "", False

    return result, True


def validate_pattern(pattern: str) -> tuple[bool, str]:
    """
    Проверить regex на корректность.
    Возвращает (ok, сообщение_об_ошибке).
    """
    if not pattern:
        return False, "Шаблон пуст"
    try:
        re.compile(pattern)
        return True, ""
    except re.error as e:
        return False, f"Ошибка в шаблоне: {e}"