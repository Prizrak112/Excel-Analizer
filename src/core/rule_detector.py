"""
Определение правил разделения по маякам.
Проверяет все возможные правила, оценивает точность, возвращает топ-3.
"""

import re
import pandas as pd
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
      - "before_word":           разделить перед словом/фразой X
      - "after_word":            разделить после слова/фразы X
      - "before_char":           разделить перед символом X
      - "after_char":            разделить после символа X
      - "position":              разделить на позиции N от начала
      - "position_from_end":     разделить за N символов до конца
      - "word_count":            разделить после N-го слова
      - "word_count_from_end":   разделить за N слов до конца
      - "char_class_transition": разделить на границе смены типа символов
      - "regex_boundary":        разделить по контекстному regex-шаблону
    
    value: что искать (слово/символ/шаблон) или номер позиции
    occurrence: какое вхождение (1, 2, 3... или -1 для последнего)
    """
    type: str
    value: Any
    occurrence: int = 1
    accuracy: float = 0.0        # % успешных строк (0.0 - 1.0)
    success_count: int = 0
    total_count: int = 0
    
    def describe(self) -> str:
        """Человеческое описание правила."""
        occ = " (последнее вхождение)" if self.occurrence == -1 else (f" ({self.occurrence}-е вхождение)" if self.occurrence > 1 else "")
        
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
        elif self.type == "position_from_end":
            return f"Разделить за {self.value} симв. с конца"
        elif self.type == "word_count":
            return f"После {self.value}-го слова"
        elif self.type == "word_count_from_end":
            return f"За {self.value} сл. с конца"
        elif self.type == "regex_boundary":
            return f"По шаблону контекста «{self.value}»"
        elif self.type == "char_class_transition":
            return f"На границе смены типа символов ({self.value}){occ}"
        return f"Правило: {self.type} {self.value}"


# ============================================================
# Определение правил
# ============================================================

class RuleDetector:
    """Определяет правила разделения по примеру."""

    @classmethod
    def get_diverse_examples(cls, series, max_count: int = 7) -> list[str]:
        """
        Выбирает максимально разнообразные по структуре и длине примеры из колонки
        (кластеризация по структурной сигнатуре: знаки препинания, количество слов, цифры).
        """
        raw_values = [str(v).strip() for v in series if pd.notna(v) and str(v).strip()]
        if not raw_values:
            return []
        
        unique_values = list(dict.fromkeys(raw_values))
        if len(unique_values) <= max_count:
            return unique_values

        def _structural_signature(s: str) -> tuple:
            punct = "".join(sorted(set(c for c in s if not c.isalnum() and not c.isspace())))
            words_bucket = min(len(s.split()), 6)
            has_digits = any(c.isdigit() for c in s)
            return (punct, words_bucket, has_digits)

        clusters: dict[tuple, list[str]] = {}
        for val in unique_values:
            sig = _structural_signature(val)
            clusters.setdefault(sig, []).append(val)

        sorted_clusters = sorted(clusters.values(), key=len, reverse=True)
        
        examples = []
        for group in sorted_clusters:
            if len(examples) >= max_count:
                break
            group_sorted = sorted(group, key=len)
            median_val = group_sorted[len(group_sorted) // 2]
            if median_val not in examples:
                examples.append(median_val)

        if len(examples) < max_count:
            by_len = sorted(unique_values, key=len)
            step = max(1, len(by_len) // (max_count - len(examples) + 1))
            for i in range(0, len(by_len), step):
                if len(examples) >= max_count:
                    break
                if by_len[i] not in examples:
                    examples.append(by_len[i])

        return examples[:max_count]
    
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
        
        candidates.extend(
            cls._try_word_rules(sample_value, marker_position)
        )
        candidates.extend(
            cls._try_char_rules(sample_value, marker_position)
        )
        candidates.append(
            cls._try_position_rule(marker_position)
        )
        
        candidates = cls._deduplicate(candidates)
        
        for rule in candidates:
            cls._evaluate(rule, series)
        
        candidates.sort(key=lambda r: (-r.accuracy, r.occurrence))
        
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
        
        left_word = cls._word_ending_at(sample, position)
        if left_word and cls._is_good_word(left_word):
            rules.append(SplitRule(
                type="after_word",
                value=left_word,
                occurrence=cls._count_occurrences_before(sample, left_word, position),
            ))
        
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
        
        if word.isdigit():
            return False
        
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
        
        if 0 < position < len(sample):
            left_char = sample[position - 1]
            right_char = sample[position] if position < len(sample) else ""
            
            if left_char == " " and right_char != " ":
                rules.append(SplitRule(
                    type="before_char",
                    value=" ",
                    occurrence=cls._count_occurrences_before(sample, " ", position),
                ))
            elif left_char != " " and right_char == " ":
                rules.append(SplitRule(
                    type="before_char",
                    value=" ",
                    occurrence=cls._count_occurrences_before(sample, " ", position) + 1,
                ))
        
        if 0 < position <= len(sample):
            lc = sample[position - 1:position]
            if lc.strip() and not lc.isdigit():
                rules.append(SplitRule(
                    type="after_char",
                    value=lc,
                    occurrence=cls._count_occurrences_before(sample, lc, position),
                ))
        
        if position < len(sample):
            rc = sample[position:position + 1]
            if rc.strip() and not rc.isdigit():
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
        
        end = position
        start = position
        while start > 0 and sample[start - 1:start] not in " \t\n\r,;:!?()[]{}<>«»\"'":
            start -= 1
        
        word = sample[start:end].strip()
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
        
        if pos <= 0 or pos >= len(value):
            return False
        
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
            pos = int(rule.value)
            return pos if 0 < pos < len(value) else None
        
        elif rule.type == "position_from_end":
            pos = len(value) - int(rule.value)
            return pos if 0 < pos < len(value) else None
        
        elif rule.type == "word_count":
            matches = list(re.finditer(r'\S+', value))
            n = int(rule.value)
            if 0 < n < len(matches):
                return matches[n - 1].end()
            return None
        
        elif rule.type == "word_count_from_end":
            matches = list(re.finditer(r'\S+', value))
            n = int(rule.value)
            if 0 < n < len(matches):
                return matches[len(matches) - n].start()
            return None
        
        elif rule.type == "regex_boundary":
            m = re.search(str(rule.value), value)
            if m:
                return m.start(1) if m.lastindex and m.lastindex >= 1 else m.start()
            return None
        
        elif rule.type == "char_class_transition":
            pattern = str(rule.value)
            matches = list(re.finditer(pattern, value))
            if not matches:
                return None
            if rule.occurrence == -1:
                return matches[-1].start(1)
            elif 1 <= rule.occurrence <= len(matches):
                return matches[rule.occurrence - 1].start(1)
            return None
        
        return None
    
    @staticmethod
    def _find_nth(value: str, sub: str, n: int) -> int | None:
        """Находит позицию N-го вхождения sub (или последнего при n == -1)."""
        if not sub:
            return None
        if n == -1:
            pos = value.rfind(sub)
            return pos if pos >= 0 else None
        if n < 1:
            return None
        
        pos = -1
        for _ in range(n):
            pos = value.find(sub, pos + 1)
            if pos < 0:
                return None
        return pos

    @classmethod
    def _infer_cut_positions(cls, full_str: str, target_str: str) -> list[tuple[int, str]]:
        """
        Определяет точные индексы разреза в исходной строке, которые дают target_str
        (в качестве левой или правой части с учетом пробелов и знаков-разделителей).
        """
        full_s = full_str
        target_s = target_str.strip()
        if not full_s or not target_s or full_s.strip() == target_s:
            return []
        
        results = []
        for pos in range(1, len(full_s)):
            left_raw = full_s[:pos].strip()
            right_raw = full_s[pos:].strip()
            
            left_clean = left_raw.rstrip(",;:|/- ")
            right_clean = right_raw.lstrip(",;:|/- ")
            
            if left_raw == target_s or left_clean == target_s:
                results.append((pos, "left"))
            if right_raw == target_s or right_clean == target_s:
                results.append((pos, "right"))
                
        return results

    @classmethod
    def _generate_flash_fill_candidates(cls, sample: str, pos: int) -> list[SplitRule]:
        """Генерирует все возможные гипотезы правил для разреза в точке pos."""
        candidates: list[SplitRule] = []
        
        for offset in (0, -1, 1, -2, 2):
            p = pos + offset
            if 0 < p < len(sample):
                candidates.extend(cls._try_word_rules(sample, p))
                candidates.extend(cls._try_char_rules(sample, p))
                
                lc = sample[p - 1:p]
                if lc.strip() and not lc.isdigit() and sample.rfind(lc) == p - 1:
                    candidates.append(SplitRule(type="after_char", value=lc, occurrence=-1))
                rc = sample[p:p + 1]
                if rc.strip() and not rc.isdigit() and sample.rfind(rc) == p:
                    candidates.append(SplitRule(type="before_char", value=rc, occurrence=-1))

        for sep in (", ", "; ", " - ", " | ", " / ", " №", " Гос.", " гос.", " ("):
            idx = sample.find(sep)
            while idx != -1:
                if abs(idx - pos) <= 2:
                    occ = sample[:idx].count(sep) + 1
                    candidates.append(SplitRule(type="before_word", value=sep, occurrence=occ))
                    if sample.rfind(sep) == idx:
                        candidates.append(SplitRule(type="before_word", value=sep, occurrence=-1))
                if abs((idx + len(sep)) - pos) <= 2:
                    occ = sample[:idx].count(sep) + 1
                    candidates.append(SplitRule(type="after_word", value=sep, occurrence=occ))
                    if sample.rfind(sep) == idx:
                        candidates.append(SplitRule(type="after_word", value=sep, occurrence=-1))
                idx = sample.find(sep, idx + 1)

        left_words = len(re.findall(r'\S+', sample[:pos]))
        right_words = len(re.findall(r'\S+', sample[pos:]))
        if left_words > 0 and right_words > 0:
            candidates.append(SplitRule(type="word_count", value=left_words, occurrence=1))
            candidates.append(SplitRule(type="word_count_from_end", value=right_words, occurrence=1))

        transitions = [
            r'(?<=[А-Яа-яЁёA-Za-z])\s*(\d)',
            r'(?<=\d)\s*([А-Яа-яЁёA-Za-z])',
            r'(?<=[а-яёa-z])\s*([А-ЯЁA-Z])',
        ]
        for pat in transitions:
            matches = list(re.finditer(pat, sample))
            for idx_m, m in enumerate(matches):
                if abs(m.start(1) - pos) <= 1:
                    candidates.append(SplitRule(type="char_class_transition", value=pat, occurrence=idx_m + 1))
                    if idx_m == len(matches) - 1:
                        candidates.append(SplitRule(type="char_class_transition", value=pat, occurrence=-1))

        candidates.append(SplitRule(type="position", value=pos, occurrence=1))
        if len(sample) - pos > 0:
            candidates.append(SplitRule(type="position_from_end", value=len(sample) - pos, occurrence=1))

        return cls._deduplicate(candidates)

    @classmethod
    def _matches_user_pair(cls, rule: SplitRule, full_str: str, target_str: str) -> bool:
        """Проверяет, дает ли правило точную целевую подстроку пользователя на примере."""
        pos = cls._find_split_position(rule, full_str)
        if pos is None or pos <= 0 or pos >= len(full_str):
            return False
        
        target_clean = target_str.strip().strip(",;:|/- ")
        left_clean = full_str[:pos].strip().rstrip(",;:|/- ")
        right_clean = full_str[pos:].strip().lstrip(",;:|/- ")
        
        return (
            full_str[:pos].strip() == target_str.strip()
            or full_str[pos:].strip() == target_str.strip()
            or left_clean == target_clean
            or right_clean == target_clean
        )

    @staticmethod
    def _rule_specificity_bonus(rule: SplitRule) -> float:
        """Бонус за обобщающую способность типа правила."""
        bonuses = {
            "before_word": 0.08,
            "after_word": 0.08,
            "before_char": 0.06,
            "after_char": 0.06,
            "char_class_transition": 0.05,
            "word_count": 0.03,
            "word_count_from_end": 0.03,
            "position_from_end": 0.01,
            "position": 0.0,
        }
        return bonuses.get(rule.type, 0.0)

    @classmethod
    def detect_from_examples(
        cls,
        examples_pairs: list[tuple[str, str]],
        series,
    ) -> SplitRule | None:
        """
        Интеллектуальный синтез правила (Flash Fill) по набору отредактированных примеров
        [(исходная_строка, желаемый_результат), ...].
        """
        valid_pairs = [
            (full.strip(), part.strip())
            for full, part in examples_pairs
            if full and part and full.strip() != part.strip()
        ]
        if not valid_pairs:
            return None

        all_candidates: list[SplitRule] = []
        for full_str, target_str in valid_pairs:
            cut_points = cls._infer_cut_positions(full_str, target_str)
            if not cut_points:
                idx = full_str.find(target_str)
                if idx == 0:
                    cut_points.append((len(target_str), "left"))
                elif idx > 0:
                    cut_points.append((idx, "right"))
            
            for pos, _ in cut_points:
                all_candidates.extend(cls._generate_flash_fill_candidates(full_str, pos))

        all_candidates = cls._deduplicate(all_candidates)
        if not all_candidates:
            return None

        best_rule = None
        best_score = -1.0

        for rule in all_candidates:
            cls._evaluate(rule, series)
            
            user_matches = sum(
                1 for full_s, part_s in valid_pairs
                if cls._matches_user_pair(rule, full_s, part_s)
            )
            user_ratio = user_matches / len(valid_pairs)
            
            score = (user_ratio * 0.70) + (rule.accuracy * 0.30) + cls._rule_specificity_bonus(rule)
            if score > best_score:
                best_score = score
                best_rule = rule

        return best_rule

    @classmethod
    def detect_from_example(
        cls,
        sample_full: str,
        sample_part: str,
        series,
    ) -> SplitRule | None:
        """
        Определяет правило разделения на основе одного примера.
        """
        if not sample_full or not sample_part:
            return None
        return cls.detect_from_examples([(sample_full, sample_part)], series)


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
    
    p1 = s[:pos].strip().rstrip(",;:|")
    p2 = s[pos:].strip().lstrip(",;:|")
    return p1.strip(), p2.strip()


def apply_rules_to_row(rules: list[SplitRule], value) -> list[str]:
    """
    Применяет список правил последовательно.
    Возвращает список частей (len(rules) + 1).
    """
    import pandas as pd
    
    if pd.isna(value):
        return [""] * (len(rules) + 1)
    
    s = str(value)
    
    positions = []
    for rule in rules:
        pos = RuleDetector._find_split_position(rule, s)
        if pos is not None and 0 < pos < len(s):
            positions.append(pos)
    
    positions = sorted(set(positions))
    
    if not positions:
        return [s.strip()] + [""] * len(rules)
    
    parts = []
    prev = 0
    for pos in positions:
        parts.append(s[prev:pos].strip().strip(",;:|").strip())
        prev = pos
    parts.append(s[prev:].strip().strip(",;:|").strip())
    
    while len(parts) < len(rules) + 1:
        parts.append("")
    
    return parts