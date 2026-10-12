"""
Цепочка преобразований DataFrame по списку Step.
Data → Filter → GroupBy → Agg → Sort → Limit → ...
"""

import pandas as pd
import numpy as np

from src.core.report.block_model import Step


# ============================================================
# Операторы фильтра
# ============================================================

FILTER_OPS = {
    "==":        lambda s, v: s == v,
    "!=":        lambda s, v: s != v,
    ">":         lambda s, v: s > v,
    ">=":        lambda s, v: s >= v,
    "<":         lambda s, v: s < v,
    "<=":        lambda s, v: s <= v,
    "in":        lambda s, v: s.isin(v if isinstance(v, (list, tuple)) else [v]),
    "not_in":    lambda s, v: ~s.isin(v if isinstance(v, (list, tuple)) else [v]),
    "contains":  lambda s, v: s.astype(str).str.contains(str(v), na=False, regex=False),
    "is_null":   lambda s, v: s.isna(),
    "not_null":  lambda s, v: s.notna(),
}

AGG_FUNCS = {
    "sum":     "sum",
    "mean":    "mean",
    "count":   "count",
    "min":     "min",
    "max":     "max",
    "median":  "median",
    "std":     "std",
    "nunique": "nunique",
}


# ============================================================
# Главная функция
# ============================================================

def apply_steps(df: pd.DataFrame, steps: list[Step]) -> pd.DataFrame:
    """Применить цепочку шагов к DataFrame. Возвращает новый DataFrame."""
    if df is None or df.empty:
        return df

    result = df.copy()

    for step in steps:
        try:
            result = _apply_step(result, step)
            if result is None or (hasattr(result, "empty") and result.empty):
                return result if result is not None else pd.DataFrame()
        except Exception as e:
            print(f"[transform] Ошибка на шаге {step.kind}: {e}")
    return result


def _apply_step(df: pd.DataFrame, step: Step) -> pd.DataFrame:
    kind = step.kind
    p = step.params or {}

    if kind == "filter":
        return _apply_filter(df, p)
    elif kind == "groupby":
        return _apply_groupby(df, p)
    elif kind == "agg":
        return _apply_agg(df, p)
    elif kind == "sort":
        return _apply_sort(df, p)
    elif kind == "limit":
        return _apply_limit(df, p)
    elif kind == "rename":
        return _apply_rename(df, p)
    elif kind == "dropna":
        return _apply_dropna(df, p)
    else:
        print(f"[transform] Неизвестный шаг: {kind}")
        return df


# ============================================================
# Шаги
# ============================================================

def _apply_filter(df: pd.DataFrame, p: dict) -> pd.DataFrame:
    col = p.get("column")
    op = p.get("op", "==")
    val = p.get("value")
    if col not in df.columns:
        return df
    fn = FILTER_OPS.get(op)
    if fn is None:
        return df
    try:
        mask = fn(df[col], val)
        if hasattr(mask, "fillna"):
            mask = mask.fillna(False)
        return df[mask]
    except Exception as e:
        print(f"[filter] {op}: {e}")
        return df


def _apply_groupby(df: pd.DataFrame, p: dict) -> pd.DataFrame:
    cols = p.get("columns") or []
    cols = [c for c in cols if c in df.columns]
    if not cols:
        return df
    df.attrs["_groupby_cols"] = cols
    return df


def _apply_agg(df: pd.DataFrame, p: dict) -> pd.DataFrame:
    col = p.get("column")
    func = AGG_FUNCS.get(p.get("func", "sum"), "sum")
    groupby_cols = df.attrs.get("_groupby_cols") or []

    if col not in df.columns:
        return df

    if groupby_cols:
        grouped = df.groupby(groupby_cols, dropna=False)[col].agg(func)
        result = grouped.reset_index()
        result.columns = list(groupby_cols) + [f"{func}_{col}"]
        return result
    else:
        val = getattr(df[col], func)()
        return pd.DataFrame({f"{func}_{col}": [val]})


def _apply_sort(df: pd.DataFrame, p: dict) -> pd.DataFrame:
    col = p.get("column")
    asc = bool(p.get("asc", True))
    if col not in df.columns:
        return df
    return df.sort_values(by=col, ascending=asc, na_position="last")


def _apply_limit(df: pd.DataFrame, p: dict) -> pd.DataFrame:
    n = int(p.get("n", 100))
    if p.get("tail"):
        return df.tail(n)
    return df.head(n)


def _apply_rename(df: pd.DataFrame, p: dict) -> pd.DataFrame:
    mapping = p.get("mapping") or {}
    return df.rename(columns=mapping)


def _apply_dropna(df: pd.DataFrame, p: dict) -> pd.DataFrame:
    subset = p.get("subset") or None
    how = p.get("how", "any")
    if subset:
        subset = [c for c in subset if c in df.columns]
    return df.dropna(subset=subset, how=how)


# ============================================================
# Проверка
# ============================================================

def validate_steps(df: pd.DataFrame, steps: list[Step]) -> list[str]:
    """Проверить корректность цепочки. Возвращает список предупреждений."""
    warnings = []
    if df is None:
        return ["Нет данных"]

    cols = set(df.columns)
    for i, step in enumerate(steps):
        k = step.kind
        p = step.params or {}
        if k == "filter":
            if p.get("column") not in cols:
                warnings.append(f"Шаг {i+1} (filter): колонка «{p.get('column')}» не найдена")
        elif k == "groupby":
            for c in p.get("columns", []):
                if c not in cols:
                    warnings.append(f"Шаг {i+1} (groupby): колонка «{c}» не найдена")
        elif k == "agg":
            if p.get("column") not in cols:
                warnings.append(f"Шаг {i+1} (agg): колонка «{p.get('column')}» не найдена")
        elif k == "sort":
            if p.get("column") not in cols:
                warnings.append(f"Шаг {i+1} (sort): колонка «{p.get('column')}» не найдена")
    return warnings