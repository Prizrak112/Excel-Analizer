"""
Превращает "инструкцию блока" в готовый HTML-блок.
Передает все настройки графиков (тип, агрегацию, фильтрацию строк, легенду, подложку)
и пространственное позиционирование блока (width, align, offset_x) в HTML-рендерер.
"""

from __future__ import annotations

from dataclasses import dataclass
import inspect
import pandas as pd

from src.core.report_model import ReportBlock
from src.core.blocks import (
    Block,
    SectionTitleBlock,
    ParagraphBlock,
    ListBlock,
    DividerBlock,
    KpiRowBlock,
    KpiCard,
    DataTableBlock,
    ContainerBlock,
    PlotlyChartBlock,
)


# ============================================================
# ЕДИНЫЙ СПИСОК ВСЕХ ТИПОВ БЛОКОВ
# ============================================================

BLOCK_TYPES: dict[str, str] = {
    "section_title": "Заголовок раздела",
    "paragraph":     "Параграф",
    "list":          "Список",
    "divider":       "Разделитель",
    "kpi_row":       "KPI-ряд",
    "data_table":    "Таблица данных",
    "plotly_chart":  "График (Plotly)",
}


@dataclass
class RenderContext:
    dataframe: pd.DataFrame | None = None
    preview_limit: int = 0


def _wrap_positioned_html(html: str, spec: ReportBlock) -> str:
    """Оборачивает HTML блока в flex-строку, которая на 100% повторяет его позицию
    и ширину с холста Конструктора (лево / по центру / право / точный сдвиг offset_x %)."""
    if spec.type in ("divider", "section_title"):
        return html

    w_pct = spec.get_width()
    align = spec.get_align()
    offset_x = spec.get_offset_x()
    mt = spec.get_margin_top()
    mb = spec.get_margin_bottom()

    if w_pct >= 100:
        return f'<div style="width:100%; margin-top:{mt}px; margin-bottom:{mb}px;">{html}</div>'

    justify = "flex-start"
    margin_left_css = "0"
    if align == "center":
        justify = "center"
    elif align == "right":
        justify = "flex-end"
    elif align == "custom" and offset_x > 0:
        margin_left_css = f"{offset_x}%"

    return (
        f'<div class="ea-free-row" style="display:flex; width:100%; justify-content:{justify}; '
        f'margin-top:{mt}px; margin-bottom:{mb}px; box-sizing:border-box;">'
        f'<div class="ea-free-cell" style="width:{w_pct}%; max-width:{w_pct}%; '
        f'margin-left:{margin_left_css}; box-sizing:border-box;">{html}</div>'
        f'</div>'
    )


def create_block(spec: ReportBlock, ctx: RenderContext) -> Block:
    """Читает инструкцию блока (spec) и делает из неё готовый блок."""
    t = spec.type
    cfg = spec.config or {}

    layout_kwargs = {
        "width": 100 if t != "container" else spec.get_width(),
        "margin_top": 0,
        "margin_bottom": 0,
        "min_height": spec.get_min_height(),
    }

    if t == "section_title":
        b = SectionTitleBlock(
            id=spec.id,
            title=cfg.get("title", ""),
            width=100,
            margin_top=spec.get_margin_top(),
            margin_bottom=spec.get_margin_bottom(),
            min_height=spec.get_min_height(),
        )
        return b

    # --- График Plotly ---
    if t == "plotly_chart":
        sig = inspect.signature(PlotlyChartBlock.__init__)
        chart_kwargs = {
            "id": spec.id,
            "dataframe": ctx.dataframe,
            "chart_type": cfg.get("chart_type", "bar"),
            "x_col": cfg.get("x_col", ""),
            "y_col": cfg.get("y_col", ""),
            "title": cfg.get("title", "График данных"),
            "agg": cfg.get("agg", "sum"),
            "sort_by": cfg.get("sort_by", "value_desc"),
            "top_n": int(cfg.get("top_n", 12)),
            "row_start": int(cfg.get("row_start", 0)),
            "row_limit": int(cfg.get("row_limit", 0)),
            "palette": cfg.get("palette", "corporate"),
            "bg_color": cfg.get("bg_color", "#ffffff"),
            "legend_pos": cfg.get("legend_pos", "right"),
            "show_legend": bool(cfg.get("show_legend", True)),
            "show_values": bool(cfg.get("show_values", True)),
            "show_grid": bool(cfg.get("show_grid", True)),
            "show_title": bool(cfg.get("show_title", True)),
            "show_axis_labels": bool(cfg.get("show_axis_labels", True)),
        }
        # Фильтруем только те параметры, которые реально есть в текущем конструкторе PlotlyChartBlock
        filtered_kwargs = {k: v for k, v in chart_kwargs.items() if k in sig.parameters}
        return PlotlyChartBlock(**filtered_kwargs, **layout_kwargs)

    if t == "paragraph":
        b = ParagraphBlock(
            id=spec.id,
            text=cfg.get("text", ""),
            raw_html=cfg.get("raw_html", False),
            **layout_kwargs,
        )
        b._spec_ref = spec
        return b

    if t == "list":
        b = ListBlock(
            id=spec.id,
            items=list(cfg.get("items", [])),
            **layout_kwargs,
        )
        b._spec_ref = spec
        return b

    if t == "divider":
        return DividerBlock(id=spec.id)

    if t == "kpi_row":
        cards = []
        for c in cfg.get("cards", []):
            cards.append(KpiCard(
                label=c.get("label", ""),
                value=str(c.get("value", "")),
                accent=bool(c.get("accent", False)),
            ))
        b = KpiRowBlock(id=spec.id, cards=cards, **layout_kwargs)
        b._spec_ref = spec
        return b

    if t == "data_table":
        b = DataTableBlock(
            id=spec.id,
            dataframe=ctx.dataframe,
            max_rows=int(cfg.get("max_rows", 20)),
            visible_columns=cfg.get("visible_columns"),
            preview_limit=ctx.preview_limit,
            **layout_kwargs,
        )
        b._spec_ref = spec
        return b

    if t == "container":
        children_specs = cfg.get("children", [])
        layout_kind = cfg.get("layout", "row")
        gap = int(cfg.get("gap", 16))
        
        children_html = []
        for child_spec in children_specs:
            if isinstance(child_spec, dict):
                child_spec = ReportBlock(
                    id=child_spec.get("id", ""),
                    type=child_spec.get("type", ""),
                    config=child_spec.get("config", {}),
                )
            child_block = create_block(child_spec, ctx)
            raw_child_html = child_block.render()
            
            # Если это горизонтальный ряд (row), делаем графики гибкими: каждый занимает ровно 50% минус отступ
            if layout_kind == "row":
                wrapped_child = (
                    f'<div style="flex: 1 1 calc(50% - {gap // 2}px); '
                    f'width: calc(50% - {gap // 2}px); min-width: 280px; max-width: 100%; '
                    f'box-sizing: border-box; background: #ffffff; border: 1px solid #e0e0e5; '
                    f'border-radius: 10px; padding: 12px; box-shadow: 0 1px 4px rgba(0,0,0,0.04); overflow: hidden;">'
                    f'<div style="width: 100%; max-width: 100%; overflow: hidden;">{raw_child_html}</div>'
                    f'</div>'
                )
            else:
                wrapped_child = (
                    f'<div style="width: 100%; max-width: 100%; box-sizing: border-box; '
                    f'background: #ffffff; border: 1px solid #e0e0e5; '
                    f'border-radius: 10px; padding: 12px; box-shadow: 0 1px 4px rgba(0,0,0,0.04); overflow: hidden;">'
                    f'<div style="width: 100%; max-width: 100%; overflow: hidden;">{raw_child_html}</div>'
                    f'</div>'
                )
            
            children_html.append(wrapped_child)

        b = ContainerBlock(
            id=spec.id,
            layout=layout_kind,
            gap=gap,
            children_html=children_html,
            width=100,
            margin_top=0,
            margin_bottom=0,
            min_height=spec.get_min_height(),
        )
        b._spec_ref = spec
        return b


def render_report(report, ctx: RenderContext) -> str:
    """Проходит по всем разделам и блокам, возвращает HTML с точным повторением
    позиций и размеров блоков с холста."""
    aside_items = []
    for i, section in enumerate(report.sections):
        title = f"{section.icon} {section.title}".strip()
        cls = "toc-item active" if i == 0 else "toc-item"
        aside_items.append(
            f'<li><a class="{cls}" href="#section-{section.id}" '
            f'data-target="section-{section.id}">{_esc(title)}</a></li>'
        )

    aside_html = (
        '<aside class="report-toc">'
        '<h2>Разделы</h2>'
        '<ul>' + "".join(aside_items) + '</ul>'
        '</aside>'
    )

    parts_html = []
    for section in report.sections:
        sec_block = SectionTitleBlock(
            id=f"section-{section.id}",
            title=f"{section.icon} {section.title}".strip(),
        )
        parts_html.append(sec_block.render())

        for spec in section.blocks:
            block_obj = create_block(spec, ctx)
            raw_block_html = block_obj.render()
            parts_html.append(_wrap_positioned_html(raw_block_html, spec))

        parts_html.append(DividerBlock(id=f"div_{section.id}").render())

    content = "\n".join(parts_html)

    return (
        aside_html
        + '<div class="report-content">' + content + '</div>'
    )


def _esc(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )


_KNOWN_TYPES = {
    "section_title",
    "paragraph",
    "list",
    "divider",
    "kpi_row",
    "data_table",
    "container",
    "plotly_chart",
}

assert set(BLOCK_TYPES) | {"container"} == _KNOWN_TYPES, (
    "BLOCK_TYPES и create_block разошлись!"
)