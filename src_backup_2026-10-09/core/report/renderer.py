"""
Сборка автономного HTML-отчёта из списка Block'ов.
Использует Jinja2 + plotly JSON.
"""

import os
import json
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.core.report.block_model import Block, ReportProject
from src.core.report.sources import SourceManager
from src.core.report.transform import apply_steps
from src.core.report.plotly_builder import build_figure


# ============================================================
# Окружение Jinja2
# ============================================================

_TEMPLATE_DIR = Path(__file__).parent / "templates"

_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


# ============================================================
# Публичная функция
# ============================================================

def render_report(project: ReportProject, source_manager: SourceManager) -> str:
    """
    Собрать HTML-строку для проекта отчёта.

    project          — ReportProject (blocks + theme).
    source_manager   — SourceManager для получения DataFrame'ов.

    Возвращает готовый HTML (автономный, с инлайн-данными).
    """
    blocks_html = []

    # Сортируем блоки по z_index, чтобы порядок в HTML совпал
    sorted_blocks = sorted(project.blocks, key=lambda b: b.z_index)

    for block in sorted_blocks:
        try:
            html = _render_block(block, project, source_manager)
            blocks_html.append(html)
        except Exception as e:
            import traceback
            traceback.print_exc()
            blocks_html.append(_error_block_html(block, e))

    template = _env.get_template("report_base.html")

    # Позиции блоков для canvas (абсолютное позиционирование)
    blocks_data = [b.to_dict() for b in sorted_blocks]

    html = template.render(
        title=project.title,
        theme=project.theme,
        blocks=blocks_html,
        blocks_data=json.dumps(blocks_data, ensure_ascii=False),
        page_width=project.theme.get("page_width", 1200),
    )
    return html


# ============================================================
# Отдельные типы блоков
# ============================================================

def _render_block(block: Block, project: ReportProject, sm: SourceManager) -> str:
    # Получаем DataFrame источника
    df = _get_block_df(block, sm)

    # Прогоняем через цепочку Step'ов
    df = apply_steps(df, block.steps)

    if block.type == "chart":
        return _render_chart(block, df)
    elif block.type == "kpi":
        return _render_kpi(block, df)
    elif block.type == "table":
        return _render_table(block, df)
    elif block.type == "text":
        return _render_text(block)
    else:
        return _render_text(block)


def _get_block_df(block: Block, sm: SourceManager) -> pd.DataFrame | None:
    """Получить исходный DataFrame для блока по source_id/sheet."""
    if not block.source_id:
        if block.inline_data:
            return pd.DataFrame(block.inline_data)
        return None
    src = None
    # SourceManager не хранит сами Source — их передают извне.
    # Здесь обращаемся к sm._cache напрямую.
    cache = sm._cache.get(block.source_id)
    if cache is None:
        return None
    sheet = block.sheet
    if sheet is None:
        sheet = next(iter(cache.keys()), None)
    return cache.get(sheet)


# ── График ──

def _render_chart(block: Block, df) -> str:
    fig_json = build_figure(df, block.chart_type or "line", block.chart_config or {})
    if fig_json is None:
        return _empty_chart_html(block, "Нет данных")

    # Уникальный div id — для Plotly.newPlot
    div_id = f"plot_{block.id}"

    # Сохраняем fig_json как JSON-строку для вставки в JS
    fig_js = json.dumps(fig_json, ensure_ascii=False)

    style = _block_style(block)
    return f"""
<div class="ea-block ea-chart" data-block-id="{block.id}" style="{style}">
  <div id="{div_id}" class="ea-chart-canvas"></div>
  <script>
    (function() {{
      var el = document.getElementById("{div_id}");
      if (el && window.Plotly) {{
        Plotly.newPlot(el, {fig_js}.data, {fig_js}.layout, {{
          responsive: true,
          displayModeBar: false,
          displaylogo: false
        }});
      }}
    }})();
  </script>
</div>
"""


def _empty_chart_html(block: Block, msg: str) -> str:
    style = _block_style(block)
    return f"""
<div class="ea-block ea-chart ea-empty" data-block-id="{block.id}" style="{style}">
  <div class="ea-empty-msg">{msg}</div>
</div>
"""


# ── KPI ──

def _render_kpi(block: Block, df) -> str:
    cfg = block.kpi_config or {}
    value = "—"
    if df is not None and not df.empty:
        # Ищем колонку
        col = cfg.get("column")
        func = cfg.get("agg", "sum")
        try:
            if col and col in df.columns:
                series = df[col]
            else:
                # Берём первую числовую
                nums = df.select_dtypes(include="number")
                if not nums.empty:
                    series = nums.iloc[:, 0]
                    col = nums.columns[0]
                else:
                    series = df.iloc[:, 0]
                    col = df.columns[0]
            val = getattr(series, func)()
            value = _fmt_number(val, cfg)
        except Exception as e:
            value = f"Ошибка: {e}"

    title = cfg.get("title", block.name or "KPI")
    subtitle = cfg.get("subtitle", "")
    color = cfg.get("color", "#87C800")
    font_size = int(cfg.get("font_size", 32))
    style = _block_style(block)

    sub_html = f'<div class="ea-kpi-subtitle">{subtitle}</div>' if subtitle else ""

    return f"""
<div class="ea-block ea-kpi" data-block-id="{block.id}" style="{style}">
  <div class="ea-kpi-title">{title}</div>
  <div class="ea-kpi-value" style="color: {color}; font-size: {font_size}px;">{value}</div>
  {sub_html}
</div>
"""


# ── Таблица ──

def _render_table(block: Block, df) -> str:
    cfg = block.table_config or {}
    if df is None or df.empty:
        return _empty_chart_html(block, "Нет данных")

    cols = cfg.get("columns") or list(df.columns)
    cols = [c for c in cols if c in df.columns]
    if not cols:
        cols = list(df.columns)

    limit = int(cfg.get("limit", 50))
    view = df[cols].head(limit)

    # Заголовки
    thead = "".join(f"<th>{c}</th>" for c in cols)
    # Строки
    rows_html = []
    for _, row in view.iterrows():
        cells = "".join(f"<td>{_fmt_number(row[c], {})}</td>" for c in cols)
        rows_html.append(f"<tr>{cells}</tr>")
    tbody = "".join(rows_html)

    striped = "ea-striped" if cfg.get("striped", True) else ""
    style = _block_style(block)

    return f"""
<div class="ea-block ea-table" data-block-id="{block.id}" style="{style}">
  <table class="ea-table-el {striped}">
    <thead><tr>{thead}</tr></thead>
    <tbody>{tbody}</tbody>
  </table>
</div>
"""


# ── Текст ──

def _render_text(block: Block) -> str:
    cfg = block.text_config or {}
    content = cfg.get("content", "")
    align = cfg.get("align", "left")
    font_size = int(cfg.get("font_size", 14))

    # Простейший markdown-подобный рендер: ##, **, переносы строк
    content_html = _mini_markdown(content)

    style = _block_style(block)
    return f"""
<div class="ea-block ea-text" data-block-id="{block.id}" style="{style}">
  <div class="ea-text-content" style="text-align: {align}; font-size: {font_size}px;">
    {content_html}
  </div>
</div>
"""


# ============================================================
# Утилиты
# ============================================================

def _block_style(block: Block) -> str:
    """Собрать inline-style из block.style + позиция."""
    s = block.style or {}
    parts = [
        f"left: {block.x}px",
        f"top: {block.y}px",
        f"width: {block.width}px",
        f"height: {block.height}px",
        f"z-index: {block.z_index}",
    ]
    if s.get("bg"):
        parts.append(f"background: {s['bg']}")
    if s.get("border"):
        parts.append(f"border: 1px solid {s['border']}")
    if s.get("radius"):
        parts.append(f"border-radius: {s['radius']}px")
    if s.get("padding") is not None:
        parts.append(f"padding: {s['padding']}px")
    return "; ".join(parts)


def _fmt_number(v, cfg: dict) -> str:
    if v is None:
        return ""
    try:
        if pd.isna(v):
            return ""
    except Exception:
        pass

    prefix = cfg.get("prefix", "")
    suffix = cfg.get("suffix", "")

    if isinstance(v, float):
        if v == int(v):
            num = f"{int(v):,}"
        else:
            num = f"{v:,.2f}"
    elif isinstance(v, int):
        num = f"{v:,}"
    else:
        return f"{prefix}{v}{suffix}"

    # Заменяем запятые-разделители тысяч на пробелы (русская типографика)
    num = num.replace(",", " ")
    return f"{prefix}{num}{suffix}"


def _mini_markdown(text: str) -> str:
    """Простой markdown-рендер: заголовки, **bold**, переносы."""
    if not text:
        return ""
    lines = text.split("\n")
    out = []
    in_list = False
    for line in lines:
        stripped = line.rstrip()
        if stripped.startswith("## "):
            if in_list:
                out.append("</ul>"); in_list = False
            out.append(f"<h2>{stripped[3:]}</h2>")
        elif stripped.startswith("# "):
            if in_list:
                out.append("</ul>"); in_list = False
            out.append(f"<h1>{stripped[2:]}</h1>")
        elif stripped.startswith("- "):
            if not in_list:
                out.append("<ul>"); in_list = True
            out.append(f"<li>{stripped[2:]}</li>")
        elif stripped == "":
            if in_list:
                out.append("</ul>"); in_list = False
            out.append("<br>")
        else:
            if in_list:
                out.append("</ul>"); in_list = False
            out.append(f"<p>{stripped}</p>")
    if in_list:
        out.append("</ul>")
    html = "\n".join(out)
    # **bold**
    import re
    html = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html)
    # *italic*
    html = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<i>\1</i>", html)
    return html


def _error_block_html(block: Block, e: Exception) -> str:
    style = _block_style(block)
    return f"""
<div class="ea-block ea-error" data-block-id="{block.id}" style="{style}">
  <div class="ea-error-msg">Ошибка блока:<br>{type(e).__name__}: {e}</div>
</div>
"""