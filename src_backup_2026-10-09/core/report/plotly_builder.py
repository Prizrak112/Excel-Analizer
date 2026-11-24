"""
Построение Plotly-фигур для блоков отчёта.
Заход 1: line, bar, pie, scatter, table.
Каждая функция возвращает dict-представление figure (json-сериализуемое),
которое затем встраивается в HTML как JSON.
"""

import pandas as pd

try:
    import plotly.graph_objects as go
    import plotly.express as px
except Exception as e:
    go = None
    px = None
    print(f"[plotly_builder] Plotly не доступен: {e}")


# ============================================================
# Цвета по умолчанию (совпадают с темой приложения)
# ============================================================

DEFAULT_COLOR = "#87C800"
DEFAULT_PALETTE = [
    "#87C800", "#3b82f6", "#f59e0b", "#ef4444",
    "#8b5cf6", "#06b6d4", "#ec4899", "#10b981",
    "#f97316", "#6366f1", "#14b8a6", "#eab308",
]


# ============================================================
# Публичная функция
# ============================================================

def build_figure(df: pd.DataFrame, chart_type: str, config: dict) -> dict | None:
    """
    Построить Plotly-фигуру для одного блока-графика.

    df      — уже пропущенный через цепочку Step'ов DataFrame.
    chart_type — "line" | "bar" | "pie" | "scatter" | "table".
    config  — словарь настроек (см. Block.chart_config).

    Возвращает dict, пригодный для json.dumps (go.Figure.to_plotly_json()),
    либо None при ошибке.
    """
    if go is None:
        return None
    if df is None or df.empty:
        return _empty_figure("Нет данных", config)

    try:
        if chart_type == "line":
            fig = _build_line(df, config)
        elif chart_type == "bar":
            fig = _build_bar(df, config)
        elif chart_type == "pie":
            fig = _build_pie(df, config)
        elif chart_type == "scatter":
            fig = _build_scatter(df, config)
        elif chart_type == "table":
            fig = _build_table(df, config)
        else:
            fig = _empty_figure(f"Тип «{chart_type}» пока не поддержан", config)

        _apply_common_layout(fig, config)
        # Возвращаем JSON-строку — Plotly сам корректно сериализует numpy-массивы.
        # Обёртка-словарь: {"data": [...], "layout": {...}}
        return _fig_to_json_dict(fig)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return _empty_figure(f"Ошибка построения: {type(e).__name__}: {e}", config)


# ============================================================
# Отдельные типы
# ============================================================

def _build_line(df: pd.DataFrame, cfg: dict):
    x = cfg.get("x")
    ys = _as_list(cfg.get("y"))
    if not x or not ys:
        return _empty_figure("Укажите X и Y", cfg)

    palette = _palette(cfg)
    fig = go.Figure()

    for i, y in enumerate(ys):
        if y not in df.columns or x not in df.columns:
            continue
        fig.add_trace(go.Scatter(
            x=df[x],
            y=df[y],
            mode="lines+markers",
            name=str(y),
            line=dict(color=palette[i % len(palette)], width=2),
            marker=dict(size=6),
        ))
    return fig


def _build_bar(df: pd.DataFrame, cfg: dict):
    x = cfg.get("x")
    ys = _as_list(cfg.get("y"))
    if not x or not ys:
        return _empty_figure("Укажите X и Y", cfg)

    palette = _palette(cfg)
    horizontal = bool(cfg.get("horizontal", False))
    stacked = bool(cfg.get("stacked", False))

    fig = go.Figure()

    for i, y in enumerate(ys):
        if y not in df.columns or x not in df.columns:
            continue
        if horizontal:
            trace = go.Bar(
                x=df[y], y=df[x],
                name=str(y),
                orientation="h",
                marker=dict(color=palette[i % len(palette)]),
            )
        else:
            trace = go.Bar(
                x=df[x], y=df[y],
                name=str(y),
                marker=dict(color=palette[i % len(palette)]),
            )
        fig.add_trace(trace)

    if stacked and len(ys) > 1:
        fig.update_layout(barmode="stack")
    return fig


def _build_pie(df: pd.DataFrame, cfg: dict):
    names = cfg.get("x")
    values = _as_list(cfg.get("y"))
    if not names or not values:
        return _empty_figure("Укажите категории и значение", cfg)
    val = values[0]
    if names not in df.columns or val not in df.columns:
        return _empty_figure("Колонки не найдены", cfg)

    palette = _palette(cfg)
    fig = go.Figure(go.Pie(
        labels=df[names],
        values=df[val],
        hole=float(cfg.get("hole", 0.0)),
        marker=dict(colors=palette),
        textinfo=cfg.get("textinfo", "label+percent"),
    ))
    return fig


def _build_scatter(df: pd.DataFrame, cfg: dict):
    x = cfg.get("x")
    ys = _as_list(cfg.get("y"))
    if not x or not ys:
        return _empty_figure("Укажите X и Y", cfg)

    palette = _palette(cfg)
    fig = go.Figure()
    for i, y in enumerate(ys):
        if y not in df.columns or x not in df.columns:
            continue
        fig.add_trace(go.Scatter(
            x=df[x], y=df[y],
            mode="markers",
            name=str(y),
            marker=dict(
                color=palette[i % len(palette)],
                size=int(cfg.get("marker_size", 8)),
                opacity=float(cfg.get("opacity", 0.8)),
            ),
        ))
    return fig


def _build_table(df: pd.DataFrame, cfg: dict):
    cols = cfg.get("columns") or list(df.columns)
    cols = [c for c in cols if c in df.columns]
    if not cols:
        cols = list(df.columns)

    limit = int(cfg.get("limit", 50))
    view = df[cols].head(limit)

    header_vals = [f"<b>{c}</b>" for c in cols]
    cell_vals = []
    for c in cols:
        cell_vals.append([_fmt(v) for v in view[c].tolist()])

    fig = go.Figure(data=[go.Table(
        header=dict(
            values=header_vals,
            fill_color=cfg.get("header_bg", "#232838"),
            font=dict(color=cfg.get("header_fg", "#E6EBF2"), size=12),
            align="left",
            height=28,
        ),
        cells=dict(
            values=cell_vals,
            fill_color=cfg.get("row_bg", "#1B202B"),
            font=dict(color=cfg.get("row_fg", "#E6EBF2"), size=11),
            align="left",
            height=24,
        ),
    )])
    return fig


# ============================================================
# Общий layout
# ============================================================

def _apply_common_layout(fig, cfg: dict):
    layout = {
        "margin": dict(l=40, r=20, t=40, b=40),
        "paper_bgcolor": cfg.get("bg", "rgba(0,0,0,0)"),
        "plot_bgcolor": cfg.get("plot_bg", "rgba(0,0,0,0)"),
        "font": dict(
            family=cfg.get("font_family", "Inter, sans-serif"),
            size=int(cfg.get("font_size", 12)),
            color=cfg.get("text_color", "#E6EBF2"),
        ),
        "showlegend": bool(cfg.get("show_legend", True)),
        "hovermode": cfg.get("hovermode", "closest"),
    }
    if cfg.get("title"):
        layout["title"] = dict(
            text=cfg["title"],
            font=dict(size=int(cfg.get("title_size", 14))),
            x=0.01, xanchor="left",
        )
    if not cfg.get("show_grid", True):
        layout["xaxis"] = dict(showgrid=False, zeroline=False)
        layout["yaxis"] = dict(showgrid=False, zeroline=False)
    else:
        grid_color = cfg.get("grid_color", "rgba(255,255,255,0.06)")
        layout["xaxis"] = dict(
            title=cfg.get("x_label") or None,
            gridcolor=grid_color, zeroline=False,
        )
        layout["yaxis"] = dict(
            title=cfg.get("y_label") or None,
            gridcolor=grid_color, zeroline=False,
        )
    fig.update_layout(**layout)


# ============================================================
# Утилиты
# ============================================================

def _as_list(v) -> list:
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        return list(v)
    return [v]


def _palette(cfg: dict) -> list:
    colors = cfg.get("colors")
    if isinstance(colors, list) and colors:
        return colors
    base = cfg.get("color")
    if base:
        return [base] + DEFAULT_PALETTE[1:]
    return DEFAULT_PALETTE


def _empty_figure(msg: str, cfg: dict):
    fig = go.Figure()
    fig.add_annotation(
        text=msg, x=0.5, y=0.5, xref="paper", yref="paper",
        showarrow=False,
        font=dict(size=13, color=cfg.get("text_color", "#8B93A7")),
    )
    fig.update_layout(
        margin=dict(l=20, r=20, t=20, b=20),
        paper_bgcolor=cfg.get("bg", "rgba(0,0,0,0)"),
        plot_bgcolor=cfg.get("plot_bg", "rgba(0,0,0,0)"),
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
    )
    return fig


def _fmt(v) -> str:
    if v is None:
        return ""
    try:
        if pd.isna(v):
            return ""
    except Exception:
        pass
    if isinstance(v, float):
        if v == int(v):
            return f"{int(v):,}"
        return f"{v:,.2f}"
    if isinstance(v, int):
        return f"{v:,}"
    return str(v)

def _fig_to_json_dict(fig) -> dict:
    """
    Преобразовать go.Figure в обычный dict без numpy-типов.
    Использует fig.to_json() — Plotly сам всё сериализует корректно,
    потом json.loads даёт чистый Python-dict.
    """
    import json
    return json.loads(fig.to_json())