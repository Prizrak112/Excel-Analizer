"""
Определение правил разделения по маякам.
Проверяет все возможные правила, оценивает точность, возвращает топ-3.
"""

import re
from dataclasses import dataclass, field
from typing import Any


# ============================================================
# Правило разделения
# ============================================================

@dataclass
class SplitRule:
    """
    Одно правило разделения.
    
    type:
      - "before_word":  разделить перед словом X
      - "after_word":   разделить после слова X
      - "before_char":  разделить перед символом X
      - "after_char":   разделить после символа X
      - "position":     разделить на позиции N (fallback)
    
    value: что искать (слово/символ) или номер позиции
    occurrence: какое вхождение (1, 2, 3...) — если метка повторяется
    """
    type: str
    value: Any
    occurrence: int = 1
    accuracy: float = 0.0        # % успешных строк (0.0 - 1.0)
    success_count: int = 0
    total_count: int = 0
    
    def describe(self) -> str:
        """Человеческое описание правила."""
        occ = f" ({self.occurrence}-е вхождение)" if self.occurrence > 1 else ""
        
        if self.type == "before_word":
            return f"Разделить перед словом «{self.value}»{occ}"
        elif self.type == "after_word":
            return f"Разделить после слова «{self.value}»{occ}"
        elif self.type == "before_char":
            return f"Разделить перед «{self.value}»{occ}"
        elif self.type == "after_char":
            return f"Разделить после «{self.value}»{occ}"
        elif self.type == "position":
            return f"Разделить на позиции {self.value}"
        return f"Правило: {self.type} {self.value}"


# ============================================================
# Определение правил
# ============================================================

class RuleDetector:
    """Определяет правила разделения по примеру."""
    
    @classmethod
    def detect_rules(
        cls,
        sample_value: str,
        marker_position: int,
        series,
        max_rules: int = 3,
    ) -> list[SplitRule]:
        """
        Определяет возможные правила для одного маяка.
        
        sample_value: пример строки
        marker_position: позиция маяка в примере
        series: Series с данными (для оценки точности)
        max_rules: сколько лучших вернуть
        
        Возвращает топ-N правил по точности.
        """
        print(f"[RuleDetector] Определяю правила для позиции {marker_position}")
        
        candidates: list[SplitRule] = []
        
        # Пробуем все возможные правила
        candidates.extend(
            cls._try_word_rules(sample_value, marker_position)
        )
        candidates.extend(
            cls._try_char_rules(sample_value, marker_position)
        )
        candidates.append(
            cls._try_position_rule(marker_position)
        )
        
        # Убираем дубликаты
        candidates = cls._deduplicate(candidates)
        
        # Оцениваем каждое
        for rule in candidates:
            cls._evaluate(rule, series)
        
        # Сортируем по точности
        candidates.sort(key=lambda r: (-r.accuracy, r.occurrence))
        
        # Возвращаем топ-N
        top = candidates[:max_rules]
        
        print(f"[RuleDetector] Найдено {len(candidates)} правил, топ-{len(top)}:")
        for r in top:
            print(f"  {r.accuracy:.1%} — {r.describe()}")
        
        return top
    
    # ============================================================
    # Кандидаты правил
    # ============================================================
    
    @classmethod
    def _try_word_rules(
        cls,
        sample: str,
        position: int,
    ) -> list[SplitRule]:
        """Правила по словам."""
        rules = []
        
        # Слово слева — разделить ПОСЛЕ него
        left_word = cls._word_ending_at(sample, position)
        if left_word and cls._is_good_word(left_word):
            rules.append(SplitRule(
                type="after_word",
                value=left_word,
                occurrence=cls._count_occurrences_before(sample, left_word, position),
            ))
        
        # Слово справа — разделить ПЕРЕД ним
        right_word = cls._word_starting_at(sample, position)
        if right_word and cls._is_good_word(right_word):
            rules.append(SplitRule(
                type="before_word",
                value=right_word,
                occurrence=cls._count_occurrences_before(sample, right_word, position) + 1,
            ))
        
        return rules
    
    @staticmethod
    def _is_good_word(word: str) -> bool:
        """
        Проверяет, хорошее ли слово для метки.
        Плохие: короткие (1-2 символа), только цифры, пустые.
        """
        if not word or len(word) < 3:
            return False
        
        # Слово только из цифр — плохо (00, 01, 2026 и т.п.)
        if word.isdigit():
            return False
        
        # Слово только из знаков препинания — плохо
        if not any(c.isalnum() for c in word):
            return False
        
        return True
    
    @classmethod
    def _try_char_rules(
        cls,
        sample: str,
        position: int,
    ) -> list[SplitRule]:
        """Правила по символам."""
        rules = []
        
        # === СПЕЦИАЛЬНЫЙ СЛУЧАЙ: маяк между пробелами ===
        # Если слева и справа от маяка пробелы — разделить по пробелу
        if 0 < position < len(sample):
            left_char = sample[position - 1]
            right_char = sample[position] if position < len(sample) else ""
            
            # Маяк внутри пробелов — правило "по пробелу"
            if left_char == " " and right_char != " ":
                # Маяк после пробела, перед началом слова
                rules.append(SplitRule(
                    type="before_char",
                    value=" ",
                    occurrence=cls._count_occurrences_before(sample, " ", position),
                ))
            elif left_char != " " and right_char == " ":
                # Маяк перед пробелом, после конца слова
                rules.append(SplitRule(
                    type="before_char",
                    value=" ",
                    occurrence=cls._count_occurrences_before(sample, " ", position) + 1,
                ))
        
        # Символ слева — разделить ПОСЛЕ него
        if 0 < position <= len(sample):
            lc = sample[position - 1:position]
            if lc.strip() and not lc.isdigit():  # не пробел и не цифра
                rules.append(SplitRule(
                    type="after_char",
                    value=lc,
                    occurrence=cls._count_occurrences_before(sample, lc, position),
                ))
        
        # Символ справа — разделить ПЕРЕД ним
        if position < len(sample):
            rc = sample[position:position + 1]
            if rc.strip() and not rc.isdigit():  # не пробел и не цифра
                rules.append(SplitRule(
                    type="before_char",
                    value=rc,
                    occurrence=cls._count_occurrences_before(sample, rc, position) + 1,
                ))
        
        return rules
    
    @classmethod
    def _try_position_rule(cls, position: int) -> SplitRule:
        """Правило по позиции."""
        return SplitRule(
            type="position",
            value=position,
            occurrence=1,
        )
    
    # ============================================================
    # Утилиты
    # ============================================================
    
    @staticmethod
    def _word_ending_at(sample: str, position: int) -> str:
        """Возвращает слово, которое заканчивается на позиции."""
        if position <= 0:
            return ""
        
        # Идём влево, пока не пробел/спецсимвол
        end = position
        start = position
        while start > 0 and sample[start - 1:start] not in " \t\n\r,;:!?()[]{}<>«»\"'":
            start -= 1
        
        word = sample[start:end].strip()
        # Слово должно быть > 1 символа (не одиночный символ)
        return word if len(word) > 1 else ""
    
    @staticmethod
    def _word_starting_at(sample: str, position: int) -> str:
        """Возвращает слово, которое начинается на позиции."""
        if position >= len(sample):
            return ""
        
        start = position
        end = position
        while end < len(sample) and sample[end:end + 1] not in " \t\n\r,;:!?()[]{}<>«»\"'":
            end += 1
        
        word = sample[start:end].strip()
        return word if len(word) > 1 else ""
    
    @staticmethod
    def _count_occurrences_before(sample: str, sub: str, position: int) -> int:
        """Сколько раз sub встречается до позиции."""
        if not sub:
            return 0
        part = sample[:position]
        return part.count(sub)
    
    @staticmethod
    def _deduplicate(rules: list[SplitRule]) -> list[SplitRule]:
        """Убирает дубликаты правил."""
        seen = set()
        result = []
        for r in rules:
            key = (r.type, r.value, r.occurrence)
            if key not in seen:
                seen.add(key)
                result.append(r)
        return result
    
    # ============================================================
    # Оценка точности
    # ============================================================
    
    @classmethod
    def _evaluate(cls, rule: SplitRule, series) -> None:
        """Оценивает правило на данных."""
        success = 0
        total = 0
        
        for value in series:
            if cls._is_valid_value(value):
                total += 1
                if cls._applies_to(rule, str(value)):
                    success += 1
        
        rule.success_count = success
        rule.total_count = total
        rule.accuracy = (success / total) if total > 0 else 0.0
    
    @staticmethod
    def _is_valid_value(value) -> bool:
        """Проверяет, что значение валидно для разделения."""
        import pandas as pd
        if pd.isna(value):
            return False
        return len(str(value).strip()) > 0
    
    @classmethod
    def _applies_to(cls, rule: SplitRule, value: str) -> bool:
        """Проверяет, применимо ли правило к строке."""
        pos = cls._find_split_position(rule, value)
        
        if pos is None:
            return False
        
        # Позиция должна быть > 0 и < len (не пустая часть)
        if pos <= 0 or pos >= len(value):
            return False
        
        # Проверяем, что обе части не пустые
        left = value[:pos].strip()
        right = value[pos:].strip()
        
        return len(left) > 0 and len(right) > 0
    
    @classmethod
    def _find_split_position(cls, rule: SplitRule, value: str) -> int | None:
        """Находит позицию разделения для правила."""
        
        if rule.type == "before_word":
            return cls._find_nth(value, rule.value, rule.occurrence)
        
        elif rule.type == "after_word":
            pos = cls._find_nth(value, rule.value, rule.occurrence)
            if pos is None:
                return None
            return pos + len(rule.value)
        
        elif rule.type == "before_char":
            return cls._find_nth(value, rule.value, rule.occurrence)
        
        elif rule.type == "after_char":
            pos = cls._find_nth(value, rule.value, rule.occurrence)
            if pos is None:
                return None
            return pos + len(rule.value)
        
        elif rule.type == "position":
            return int(rule.value)
        
        return None
    
    @staticmethod
    def _find_nth(value: str, sub: str, n: int) -> int | None:
        """Находит позицию N-го вхождения sub."""
        if not sub or n < 1:
            return None
        
        pos = -1
        for _ in range(n):
            pos = value.find(sub, pos + 1)
            if pos < 0:
                return None
        return pos


# ============================================================
# Применение правил
# ============================================================

def apply_rule(rule: SplitRule, value) -> tuple[str, str]:
    """
    Применяет правило к строке.
    Возвращает (часть_1, часть_2).
    Если правило не применимо — возвращает (строка, "").
    """
    import pandas as pd
    
    if pd.isna(value):
        return "", ""
    
    s = str(value)
    
    pos = RuleDetector._find_split_position(rule, s)
    
    if pos is None or pos <= 0 or pos >= len(s):
        return s.strip(), ""
    
    return s[:pos].strip(), s[pos:].strip()


def apply_rules_to_row(rules: list[SplitRule], value) -> list[str]:
    """
    Применяет список правил последовательно.
    Возвращает список частей (len(rules) + 1).
    """
    import pandas as pd
    
    if pd.isna(value):
        return [""] * (len(rules) + 1)
    
    s = str(value)
    
    # Находим все позиции разделения
    positions = []
    for rule in rules:
        pos = RuleDetector._find_split_position(rule, s)
        if pos is not None and 0 < pos < len(s):
            positions.append(pos)
    
    # Сортируем и убираем дубликаты
    positions = sorted(set(positions))
    
    if not positions:
        return [s.strip()] + [""] * len(rules)
    
    # Разбиваем строку
    parts = []
    prev = 0
    for pos in positions:
        parts.append(s[prev:pos].strip())
        prev = pos
    parts.append(s[prev:].strip())
    
    # Дополняем до len(rules) + 1
    while len(parts) < len(rules) + 1:
        parts.append("")
    
    return parts