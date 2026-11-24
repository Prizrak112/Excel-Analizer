"""
Построение regex-правила для извлечения фрагмента по примерам пользователя.

Логика:
  • Пользователь выделяет нужный фрагмент в 1+ строках-примерах.
  • Алгоритм строит правило:
        <левый якорь>(<значение>)<правый якорь>
    где:
      – значение  — «.+?» если выделение содержит пробелы/запятые (фраза),
                    иначе класс символов (буквы, цифры, дефис, подчёркивание);
      – левый якорь  — общий СУФФИКС левых контекстов, обрезанный
                        до 5 символов, ИЛИ «^» если все примеры
                        начинаются с 0-й позиции;
      – правый якорь — общий ПРЕФИКС правых контекстов, обрезанный
                        до 5 символов, ИЛИ «$» если все примеры
                        заканчиваются на len(text).
  • Правило применяется ко ВСЕМУ столбцу.
"""

import re
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd


# Максимальная длина якоря. Если общий суффикс/префикс длиннее — обрезаем.
MAX_ANCHOR_LEN = 5


# ============================================================
# Результат построения правила
# ============================================================

@dataclass
class BuildResult:
    pattern: Optional[str]
    covered_rows: list = field(default_factory=list)
    uncovered_rows: list = field(default_factory=list)
    samples_extracted: list = field(default_factory=list)
    left_anchor: str = ""
    right_anchor: str = ""
    value_class: str = ""

    @property
    def is_ready(self) -> bool:
        return bool(self.pattern) and not self.uncovered_rows

    @property
    def total(self) -> int:
        return len(self.covered_rows) + len(self.uncovered_rows)

    @property
    def coverage_str(self) -> str:
        return f"{len(self.covered_rows)} из {self.total}"


# ============================================================
# Строитель правила
# ============================================================

class ExtractRuleBuilder:
    """Строит regex по примерам, которые показывает пользователь."""

    def __init__(self, series: pd.Series, max_attempts: int = 5):
        self._orig_index = list(series.index)
        self._series = series.reset_index(drop=True)
        self._examples: dict[int, tuple[str, int, int]] = {}
        self._max_attempts = max_attempts
        self._last_pattern: Optional[str] = None
        self._ineffective_count = 0

    @property
    def attempts(self) -> int:
        return len(self._examples)

    @property
    def max_attempts_reached(self) -> bool:
        return self.attempts >= self._max_attempts

    @property
    def ineffective_count(self) -> int:
        return self._ineffective_count

    # ------------------------------------------------------------

    def set_example(self, row_key: int, text: str, start: int, end: int) -> bool:
        if not (0 <= start < end <= len(text)):
            return False

        self._examples[row_key] = (text, start, end)
        new_result = self.build()

        changed = (new_result.pattern != self._last_pattern)
        if changed:
            self._ineffective_count = 0
        else:
            self._ineffective_count += 1

        self._last_pattern = new_result.pattern
        return changed

    def clear(self):
        self._examples.clear()
        self._last_pattern = None
        self._ineffective_count = 0

    def has_examples(self) -> bool:
        return bool(self._examples)

    def list_examples(self) -> list[tuple[int, str]]:
        result = []
        for row_key, (text, s, e) in self._examples.items():
            result.append((row_key, text[s:e]))
        return result

    def remove_example(self, row_key: int) -> bool:
        if row_key in self._examples:
            del self._examples[row_key]
            self._last_pattern = None
            self._ineffective_count = 0
            return True
        return False

    # ------------------------------------------------------------
    # Построение
    # ------------------------------------------------------------

    def build(self) -> BuildResult:
        if not self._examples:
            return BuildResult(
                pattern=None,
                uncovered_rows=list(self._orig_index),
            )

        examples_list = list(self._examples.values())

        left_contexts = [t[:s] for t, s, _e in examples_list]
        right_contexts = [t[e:] for t, _s, e in examples_list]

        left_anchor = self._common_suffix(left_contexts)
        right_anchor = self._common_prefix(right_contexts)

        # ★ Обрезаем якоря — они не должны быть длиннее MAX_ANCHOR_LEN.
        #   Иначе правило получается сверх-специфичным и работает
        #   только на одной конкретной форме.
        if len(left_anchor) > MAX_ANCHOR_LEN:
            left_anchor = left_anchor[-MAX_ANCHOR_LEN:]
        if len(right_anchor) > MAX_ANCHOR_LEN:
            right_anchor = right_anchor[:MAX_ANCHOR_LEN]

        all_start_at_zero = all(s == 0 for _t, s, _e in examples_list)
        all_end_at_len = all(e == len(t) for t, _s, e in examples_list)

        # ★ Режим значения: фраза (.+?) или токен [chars]+
        selections = [t[s:e] for t, s, e in examples_list]
        has_spaces = any(
            (" " in sel) or ("\t" in sel) or ("," in sel)
            for sel in selections
        )

        if has_spaces:
            value_re = ".+?"
        else:
            chars: set = set()
            for sel in selections:
                chars.update(sel)
            value_re = self._chars_to_class(chars)

        pattern = self._build_pattern(
            left_anchor,
            right_anchor,
            value_re,
            left_at_start=all_start_at_zero,
            right_at_end=all_end_at_len,
        )

        covered, uncovered, samples = self._apply(pattern)

        covered_orig = [self._orig_index[i] for i in covered]
        uncovered_orig = [self._orig_index[i] for i in uncovered]
        samples_orig = [(self._orig_index[i], val) for i, val in samples]

        return BuildResult(
            pattern=pattern,
            covered_rows=covered_orig,
            uncovered_rows=uncovered_orig,
            samples_extracted=samples_orig,
            left_anchor=left_anchor,
            right_anchor=right_anchor,
            value_class=value_re,
        )

    # ------------------------------------------------------------

    @staticmethod
    def _chars_to_class(chars: set) -> str:
        has_digit = any(c.isdigit() for c in chars)
        has_lat = any(("A" <= c <= "Z") or ("a" <= c <= "z") for c in chars)
        has_cyr = any(
            ("А" <= c <= "Я") or ("а" <= c <= "я") or c in "Ёё"
            for c in chars
        )
        has_letter = has_lat or has_cyr
        has_dash = "-" in chars
        has_under = "_" in chars

        parts = []
        if has_digit:
            parts.append("0-9")
        if has_letter:
            parts.append("A-Za-z")
            parts.append("А-Яа-яЁё")
        if has_dash or (has_digit and has_letter):
            parts.append("\\-")
        if has_under or (has_digit and has_letter):
            parts.append("_")

        if not parts:
            return r".+?"
        return "[" + "".join(parts) + "]+"

    # ------------------------------------------------------------

    @staticmethod
    def _common_suffix(strings: list) -> str:
        if not strings:
            return ""
        if len(strings) == 1:
            return strings[0]
        min_len = min(len(s) for s in strings)
        result = ""
        for i in range(1, min_len + 1):
            ch = strings[0][-i]
            if all(s[-i] == ch for s in strings):
                result = ch + result
            else:
                break
        return result

    @staticmethod
    def _common_prefix(strings: list) -> str:
        if not strings:
            return ""
        if len(strings) == 1:
            return strings[0]
        min_len = min(len(s) for s in strings)
        result = ""
        for i in range(min_len):
            ch = strings[0][i]
            if all(s[i] == ch for s in strings):
                result += ch
            else:
                break
        return result

    # ------------------------------------------------------------

    @staticmethod
    def _build_pattern(left: str, right: str, value_re: str,
                       left_at_start: bool = False,
                       right_at_end: bool = False) -> str:
        if left_at_start:
            left_re = "^"
        elif left:
            left_re = re.escape(left)
        else:
            left_re = ""

        if right_at_end:
            right_re = "$"
        elif right:
            right_re = re.escape(right)
        else:
            # ★ Нет общего правого якоря — используем типовые разделители
            #   (запятая / точка с запятой / табуляция). Иначе `^(.+?)`
            #   без правого якоря вернёт один символ (первую букву).
            right_re = r"[,;\t]"

        return f"{left_re}({value_re}){right_re}"

    # ------------------------------------------------------------

    def _apply(self, pattern: str) -> tuple[list, list, list]:
        try:
            rx = re.compile(pattern)
        except re.error:
            return [], list(range(len(self._series))), []

        covered: list[int] = []
        uncovered: list[int] = []
        samples: list = []

        for i, val in self._series.items():
            if val is None:
                uncovered.append(i)
                continue
            try:
                if pd.isna(val):
                    uncovered.append(i)
                    continue
            except (TypeError, ValueError):
                pass

            s = str(val)
            m = rx.search(s)
            if m and m.group(1):
                covered.append(i)
                if len(samples) < 5:
                    samples.append((i, m.group(1)))
            else:
                uncovered.append(i)

        return covered, uncovered, samples

    # ------------------------------------------------------------

    def get_uncovered_examples(self, n: int = 5) -> list[tuple[int, str]]:
        result = self.build()
        uncovered_set = set(result.uncovered_rows)

        examples: list[tuple[int, str]] = []
        for orig_idx, val in zip(self._orig_index, self._series.tolist()):
            if orig_idx not in uncovered_set:
                continue
            if val is None:
                continue
            try:
                if pd.isna(val):
                    continue
            except (TypeError, ValueError):
                pass
            examples.append((orig_idx, str(val)))
            if len(examples) >= n:
                break
        return examples