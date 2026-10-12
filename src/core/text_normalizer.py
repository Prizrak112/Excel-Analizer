"""
Нормализация текстовых данных (гос-номера и др.).

Чистая логика, без UI. Используется NormalizeTextCommand.

Основная функция:
    normalize_value(s, *, direction, upper, remove_spaces, remove_chars)
        → (результат: str, ok: bool)

ok=False, если значение не удалось нормализовать:
  • остались латинские буквы после замены в кириллицу (и наоборот),
  • нет ни одной буквы (числа, спецсимволы),
  • пустое значение.
"""


# ============================================================
# Карты замен
# ============================================================

# Латиница → кириллица (только буквы, у которых есть двойник в РФ)
_LAT_TO_CYR = {
    "A": "А", "B": "В", "E": "Е", "K": "К", "M": "М",
    "H": "Н", "O": "О", "P": "Р", "C": "С", "T": "Т",
    "Y": "У", "X": "Х",
}

# Кириллица → латиница (обратная карта)
_CYR_TO_LAT = {v: k for k, v in _LAT_TO_CYR.items()}

# Множества ВСЕХ кириллических и латинских букв (для проверки остатка).
# Если после замены осталась хоть одна буква "чужого" алфавита —
# значение некорректное.
import string as _string

_LAT_LETTERS = set(_string.ascii_uppercase)              # A…Z (26 букв)
_CYR_LETTERS = set(
    "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ"                  # 33 буквы
)


# ============================================================
# Главная функция
# ============================================================

def normalize_value(
    s,
    *,
    direction: str = "lat2cyr",
    upper: bool = True,
    remove_spaces: bool = True,
    remove_chars: set[str] | None = None,
) -> tuple[str, bool]:
    """
    Нормализовать одно значение.

    direction: "lat2cyr" | "cyr2lat"
    upper: привести к верхнему регистру
    remove_spaces: удалить все пробельные символы
    remove_chars: набор символов для удаления (например, {".", "-", "№"})

    Возвращает (результат, ok).
    """
    # ── 1. Числа и None сразу в ошибку ──
    if s is None:
        return "", False

    # Проверка "число без букв" (int, float, numpy и т.п.)
    try:
        import numbers
        if isinstance(s, numbers.Number):
            return str(s), False
    except Exception:
        pass

    # NaN
    try:
        import math
        if isinstance(s, float) and math.isnan(s):
            return "", False
    except Exception:
        pass

    text = str(s)

    # Пустое или только пробелы — тоже ошибка
    if not text.strip():
        return "", False

    # ── 2. Удаление спецсимволов ──
    if remove_chars:
        for ch in remove_chars:
            if ch:
                text = text.replace(ch, "")

    # ── 3. Удаление пробелов ──
    if remove_spaces:
        # удаляем все пробельные символы: " ", "\t", "\n", "\r", \xa0 и т.п.
        text = "".join(ch for ch in text if not ch.isspace())

    # ── 4. Верхний регистр ──
    if upper:
        text = text.upper()
    else:
        # даже если не upper, для замены нужны заглавные буквы —
        # но менять регистр пользователь запретил, поэтому
        # обрабатываем только заглавные.
        pass

    # ── 5. Замена букв ──
    if direction == "lat2cyr":
        text = "".join(_LAT_TO_CYR.get(ch, ch) for ch in text)
        forbidden = _LAT_LETTERS  # остались латинские → ошибка
    elif direction == "cyr2lat":
        text = "".join(_CYR_TO_LAT.get(ch, ch) for ch in text)
        forbidden = _CYR_LETTERS  # остались кириллические → ошибка
    else:
        # неизвестное направление — ничего не делаем
        return text, False

    # ── 6. Проверка ok ──
    ok = _is_valid(text, forbidden)
    return text, ok


# ============================================================
# Проверка
# ============================================================

def _is_valid(text: str, forbidden: set[str]) -> bool:
    """
    True — если значение корректное:
      • содержит хотя бы одну букву,
      • НЕ содержит запрещённых букв (чужих алфавитов),
      • не содержит посторонних символов (кроме букв и цифр).

    forbidden — множество букв ЧУЖОГО алфавита.
    Пример: для lat2cyr forbidden = A…Z; осталась хоть одна — ошибка.
    """
    if not text:
        return False

    has_letter = False

    for ch in text:
        if ch.isdigit():
            continue
        if ch in forbidden:
            return False
        if ch.isalpha():
            has_letter = True
            continue
        # любой другой символ (не буква, не цифра) → ошибка
        return False

    return has_letter