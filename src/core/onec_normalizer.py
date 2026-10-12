"""
Нормализатор выгрузок 1С.
Воспроизводит VBA-макрос LAO_Kart1c (карточка счёта 10.03).
Возвращает (df, log, operations) — операции по шагам для генератора.
"""

import pandas as pd


class OneCNormalizer:
    """Приводит грязную выгрузку 1С в читабельный вид."""

    def __init__(self):
        self.log: list[str] = []
        self.operations: list[dict] = []

    def _log(self, msg: str):
        self.log.append(msg)

    # ============================================================
    # Публичный API
    # ============================================================

    def normalize(self, df: pd.DataFrame):
        """Возвращает (новый df, журнал, список операций по шагам)."""
        self.log = []
        self.operations = []
        df = df.copy()

        df = self._find_start_table(df)
        df = self._delete_cur_saldo(df)
        df = self._delete_empty_columns(df)
        df = self._fill_headers(df)

        df = self._split_multiline(df)
        df = self._delete_empty_columns(df)
        df = self._fill_headers(df)

        df = self._delete_after_sum_kt_2(df)
        df = self._date_only(df)
        df = self._delete_useless_cols(df)

        df = df.reset_index(drop=True)
        self._log(f"Итог: {len(df)} строк × {len(df.columns)} колонок")
        return df, self.log, self.operations

    # ============================================================
    # Шаг 1: найти начало таблицы
    # ============================================================

    def _find_start_table(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df

        limit = min(20, len(df))
        start_row = 0
        found = False

        for i in range(limit):
            val = df.iloc[i, 0]
            if val is None or (isinstance(val, float) and pd.isna(val)):
                continue
            s = str(val).strip().lower()
            if s.startswith("период") or s.startswith("дата"):
                start_row = i
                found = True
                break

        if not found:
            self._log("Строка 'Период'/'Дата' не найдена — оставлены все данные")
            return df

        if start_row > 0:
            df = df.iloc[start_row:].reset_index(drop=True)
            self._log(f"Обрезаны первые {start_row} строк")

        df.iloc[0, 0] = "Период"

        self.operations.append({
            "type": "1c_find_start",
            "params": {"start_row": int(start_row)},
        })
        return df

    # ============================================================
    # Шаг 2: удалить "Текущее сальдо" + следующий столбец
    # ============================================================

    def _delete_cur_saldo(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df

        cols = list(df.columns)
        head = df.head(5)

        target_col_idx = None
        for i, col in enumerate(cols):
            for v in head[col]:
                if v is None or (isinstance(v, float) and pd.isna(v)):
                    continue
                if str(v).strip() == "Текущее сальдо":
                    target_col_idx = i
                    break
            if target_col_idx is not None:
                break

        if target_col_idx is None:
            return df

        to_drop = [cols[target_col_idx]]
        if target_col_idx + 1 < len(cols):
            to_drop.append(cols[target_col_idx + 1])

        df = df.drop(columns=to_drop)
        self._log("Удалена колонка 'Текущее сальдо' и следующая")

        self.operations.append({
            "type": "1c_delete_cur_saldo",
            "params": {"col_name": str(cols[target_col_idx])},
        })
        return df

    # ============================================================
    # Шаг 3: удалить пустые столбцы
    # ============================================================

    def _delete_empty_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df

        df_clean = df.replace(r"^\s*$", pd.NA, regex=True)
        keep_mask = df_clean.notna().any(axis=0)
        dropped = int((~keep_mask).sum())
        if dropped:
            self._log(f"Удалено пустых колонок: {dropped}")
            self.operations.append({
                "type": "1c_drop_empty_cols",
                "params": {"count": int(dropped)},
            })
        return df.loc[:, keep_mask]

    # ============================================================
    # Шаг 4: заполнить пустые заголовки
    # ============================================================

    def _fill_headers(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df

        raw_headers = list(df.iloc[0])
        fixed = self._fix_headers(raw_headers)
        df = df.iloc[1:].reset_index(drop=True)
        df.columns = self._make_unique(fixed)

        self.operations.append({
            "type": "1c_fill_headers",
            "params": {"headers": list(fixed)},
        })
        return df

    def _fix_headers(self, headers: list) -> list[str]:
        result = []
        for h in headers:
            if h is None or (isinstance(h, float) and pd.isna(h)):
                result.append("")
            else:
                result.append(str(h).strip())

        for i in range(len(result) - 1):
            if result[i] == "Дебет" and result[i + 1] == "":
                result[i + 1] = "Сумма_Дт"
            elif result[i] == "Кредит" and result[i + 1] == "":
                result[i + 1] = "Сумма_Кт"

        for i in range(1, len(result)):
            if result[i] == "":
                prev = result[i - 1]
                if prev and prev[-1].isdigit():
                    try:
                        n = int(prev[-1]) + 1
                        result[i] = prev[:-1] + str(n)
                    except ValueError:
                        result[i] = prev + "_2"
                else:
                    result[i] = prev + "_2"

        return result

    def _make_unique(self, names: list[str]) -> list[str]:
        seen: dict[str, int] = {}
        out = []
        for n in names:
            base = n if n else "Col"
            if base not in seen:
                seen[base] = 0
                out.append(base)
            else:
                seen[base] += 1
                out.append(f"{base}_{seen[base]}")
        return out

    # ============================================================
    # Шаг 5: разбить многострочные ячейки
    # ============================================================

    SKIP_SPLIT = {"Дебет", "Кредит", "Сумма_Дт", "Сумма_Кт", "Период"}

    def _split_multiline(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df

        cols = list(df.columns)
        cols_to_split = []
        for i, c in enumerate(cols):
            if c in self.SKIP_SPLIT:
                continue
            series = df.iloc[:, i]
            if series.astype(str).str.contains("\n", regex=False, na=False).any():
                cols_to_split.append(i)

        if not cols_to_split:
            self._log("Многострочных колонок не найдено")
            return df

        for col_idx in sorted(cols_to_split, reverse=True):
            df = self._split_one_column(df, col_idx)

        self._log(f"Разделено колонок: {len(cols_to_split)}")

        names = [str(cols[i]) for i in cols_to_split]
        self.operations.append({
            "type": "1c_split_multiline",
            "params": {"columns": names},
        })
        return df

    def _split_one_column(self, df: pd.DataFrame, col_idx: int) -> pd.DataFrame:
        col_name = df.columns[col_idx]
        series = df.iloc[:, col_idx]

        parts_list = []
        max_parts = 1

        for v in series:
            if v is None or (isinstance(v, float) and pd.isna(v)):
                parts_list.append([""])
            else:
                parts = str(v).split("\n")
                parts_list.append(parts)
                max_parts = max(max_parts, len(parts))

        max_parts = min(max_parts, 8)

        left = df.iloc[:, :col_idx]
        right = df.iloc[:, col_idx + 1:]

        new_cols = {col_name: [p[0] if len(p) > 0 else "" for p in parts_list]}
        for pi in range(1, max_parts):
            new_cols[f"__split_{col_name}_{pi}__"] = [
                p[pi] if len(p) > pi else "" for p in parts_list
            ]

        parts_df = pd.DataFrame(new_cols, index=df.index)
        return pd.concat([left, parts_df, right], axis=1)

    # ============================================================
    # Шаг 6: обрезать после "Сумма_Кт_2"
    # ============================================================

    def _delete_after_sum_kt_2(self, df: pd.DataFrame) -> pd.DataFrame:
        cols = list(df.columns)
        for i, c in enumerate(cols):
            if c == "Сумма_Кт_2":
                df = df.iloc[:, :i + 1]
                self._log(f"Обрезано после 'Сумма_Кт_2' (колонок: {i + 1})")
                self.operations.append({
                    "type": "1c_delete_after_col",
                    "params": {"col_name": "Сумма_Кт_2"},
                })
                return df
        return df

    # ============================================================
    # Шаг 7: только строки с датой в колонке A
    # ============================================================

    def _date_only(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or len(df.columns) == 0:
            return df

        first_col = df.columns[0]

        # format='mixed' убирает UserWarning и парсит каждую ячейку отдельно
        try:
            dates = pd.to_datetime(df[first_col], errors="coerce", format="mixed")
        except TypeError:
            # Старые версии pandas (< 2.0) не знают format='mixed'
            dates = pd.to_datetime(df[first_col], errors="coerce")

        before = len(df)
        df = df[dates.notna()].reset_index(drop=True)
        after = len(df)

        if before != after:
            self._log(f"Удалено строк без даты: {before - after}")

        try:
            df[first_col] = pd.to_datetime(df[first_col], errors="coerce", format="mixed")
        except TypeError:
            df[first_col] = pd.to_datetime(df[first_col], errors="coerce")

        self.operations.append({
            "type": "1c_date_only",
            "params": {"column": str(first_col)},
        })
        return df

    # ============================================================
    # Шаг 8: удалить бесполезные столбцы
    # ============================================================

    def _delete_useless_cols(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df

        keep_cols = []
        for c in df.columns:
            col = df[c]
            has_real = False
            for v in col:
                if v is None or (isinstance(v, float) and pd.isna(v)):
                    continue
                s = str(v).strip()
                if s and s != "<...>" and s.lower() != "nan":
                    has_real = True
                    break
            if has_real:
                keep_cols.append(c)

        dropped = len(df.columns) - len(keep_cols)
        if dropped:
            self._log(f"Удалено бесполезных колонок: {dropped}")
            self.operations.append({
                "type": "1c_delete_useless",
                "params": {"count": int(dropped)},
            })

        return df[keep_cols]


# ============================================================
# Утилита
# ============================================================

def normalize_1c(df: pd.DataFrame):
    """Нормализовать df. Возвращает (df, лог, список операций)."""
    return OneCNormalizer().normalize(df)