"""
Превращает "инструкцию блока" в готовый HTML-блок.
Передает все настройки графиков (режим по столбцам/строкам, выбранные столбцы строки,
условия фильтрации, легенду, подложку) и пространственное позиционирование в HTML-рендерер.
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
    PivotMatrixBlock,
    DecompositionBlock,
    GeoMapBlock,
    ContainerBlock,
    PlotlyChartBlock,
    DashboardFilterBlock,
)


BLOCK_TYPES: dict[str, str] = {
    "section_title":    "Заголовок раздела",
    "paragraph":        "Аналитический текст",
    "list":             "Маркированный список",
    "divider":          "Разделитель",
    "kpi_row":          "KPI-карточки (Метрики)",
    "data_table":       "Таблица данных",
    "pivot_matrix":     "Сводная матрица",
    "decomposition":    "Дерево декомпозиции",
    "geo_map":          "Гео-карта объектов",
    "plotly_chart":     "Интерактивный график",
    "dashboard_filter": "Фильтр (Срез данных)",
}

@dataclass
class RenderContext:
    dataframe: pd.DataFrame | None = None
    preview_limit: int = 0
    report: object = None
    file_manager: object = None

def _resolve_df_for_spec(spec: ReportBlock, ctx: RenderContext) -> pd.DataFrame | None:
    """Определяет DataFrame, жёстко закреплённый за блоком, игнорируя активный файл редактора."""
    cfg = spec.config or {}
    
    # Проверяем фильтр, привязанный к графику
    source_file_name = cfg.get("source_file_name", "")
    source_sheet = cfg.get("source_sheet", "") or cfg.get("source_file", "")
    if not source_sheet and cfg.get("target_chart"):
        if ctx.report and hasattr(ctx.report, "find_block"):
            found = ctx.report.find_block(cfg["target_chart"])
            if found:
                _, c_block = found
                c_cfg = c_block.config or {}
                source_file_name = c_cfg.get("source_file_name", "") or source_file_name
                source_sheet = c_cfg.get("source_sheet", "") or c_cfg.get("source_file", "")

    # Строгая привязка через FileManager
    if ctx.file_manager is not None and hasattr(ctx.file_manager, "get_dataframe"):
        if source_file_name or (source_sheet and source_sheet != "— Авто (первый лист) —"):
            df = ctx.file_manager.get_dataframe(source_file_name, source_sheet)
            if df is not None:
                return df
        
        # Если файл не выбран — берем строго ПЕРВЫЙ файл в проекте, а не активную вкладку!
        if hasattr(ctx.file_manager, "get_files_dict"):
            files_dict = ctx.file_manager.get_files_dict()
            if files_dict:
                first_file = next(iter(files_dict.keys()))
                first_sheet = files_dict[first_file][0] if files_dict[first_file] else ""
                df = ctx.file_manager.get_dataframe(first_file, first_sheet)
                if df is not None:
                    return df

    return ctx.dataframe

def _wrap_positioned_html(html: str, spec: ReportBlock) -> str:
    if spec.type in ("divider", "section_title"):
        return html

    cfg = spec.config or {}
    w_pct = max(15, min(100, int(cfg.get("width", 100) or 100)))
    align = str(cfg.get("align", "left") or "left")
    offset_x = max(0, min(85, int(cfg.get("offset_x", 0) or 0)))
    mt = int(cfg.get("margin_top", 0) or 0)
    mb = int(cfg.get("margin_bottom", 14) if "margin_bottom" in cfg else 14)

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
    block_df = _resolve_df_for_spec(spec, ctx)

    w_val = max(15, min(100, int(cfg.get("width", 100) or 100)))
    mt_val = int(cfg.get("margin_top", 0) or 0)
    mb_val = int(cfg.get("margin_bottom", 14) if "margin_bottom" in cfg else 14)
    mh_val = int(cfg.get("min_height", 0) or 0)

    layout_kwargs = {
        "width": 100 if t != "container" else w_val,
        "margin_top": 0,
        "margin_bottom": 0,
        "min_height": mh_val,
    }

    if t == "section_title":
        return SectionTitleBlock(
            id=spec.id,
            title=cfg.get("title", ""),
            raw_html=bool(cfg.get("raw_html", False)),
            width=100,
            margin_top=mt_val,
            margin_bottom=mb_val,
            min_height=mh_val,
        )

    if t == "plotly_chart":
        sig = inspect.signature(PlotlyChartBlock.__init__)
        chart_kwargs = {
            "id": spec.id,
            "dataframe": block_df,
            "source_file_name": cfg.get("source_file_name", ""),
            "source_sheet": cfg.get("source_sheet", "") or cfg.get("source_file", ""),
            "chart_type": cfg.get("chart_type", "bar"),
            "data_mode": cfg.get("data_mode", "columns"),
            "x_col": cfg.get("x_col", ""),
            "y_col": cfg.get("y_col", ""),
            "row_columns": list(cfg.get("row_columns") or []),
            "row_target_val": cfg.get("row_target_val", "__ALL_SERIES__"),
            "clean_col_labels": bool(cfg.get("clean_col_labels", True)),
            "filter_col": cfg.get("filter_col", ""),
            "filter_op": cfg.get("filter_op", ">"),
            "filter_val": cfg.get("filter_val", ""),
            "custom_query": cfg.get("custom_query", ""),
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
            "font_size": int(cfg.get("font_size", 12) or 12),
            "fact_col": str(cfg.get("fact_col", "") or ""),
            "norm_col": str(cfg.get("norm_col", "") or ""),
            "parent_group_col": str(cfg.get("parent_group_col", "") or ""),
            "model_col": str(cfg.get("model_col", "") or ""),
            "plate_col": str(cfg.get("plate_col", "") or ""),
            "date_col": str(cfg.get("date_col", "") or ""),
            "min_slice_pct": float(cfg.get("min_slice_pct", 0.0) or 0.0),
            "slice_pct_mode": str(cfg.get("slice_pct_mode", "ge") or "ge"),
            "combo_series": list(cfg.get("combo_series") or []),
            "combo_barmode": str(cfg.get("combo_barmode", "group") or "group"),
            "combo_y2_title": str(cfg.get("combo_y2_title", "") or ""),
            "combo_show_zero_line": bool(cfg.get("combo_show_zero_line", True)),
            "combo_target_val": str(cfg.get("combo_target_val", "") or ""),
            "combo_target_label": str(cfg.get("combo_target_label", "Норма / Цель") or "Норма / Цель"),
            "combo_target_color": str(cfg.get("combo_target_color", "#e11d48") or "#e11d48"),
            "combo_level1_col": str(cfg.get("combo_level1_col", "") or ""),
            "combo_level2_col": str(cfg.get("combo_level2_col", "") or ""),
            "combo_level3_col": str(cfg.get("combo_level3_col", "") or ""),
            "combo_level1_sort": str(cfg.get("combo_level1_sort", cfg.get("sort_by", "value_desc")) or "value_desc"),
            "combo_level2_sort": str(cfg.get("combo_level2_sort", "value_desc") or "value_desc"),
            "combo_level3_sort": str(cfg.get("combo_level3_sort", "value_desc") or "value_desc"),
            "combo_sort_series_idx": int(cfg.get("combo_sort_series_idx", 0) or 0),
        }
        filtered_kwargs = {k: v for k, v in chart_kwargs.items() if k in sig.parameters}
        b = PlotlyChartBlock(**filtered_kwargs, **layout_kwargs)
        b.config = cfg
        b._report_ref = ctx.report
        b._file_manager = ctx.file_manager
        return b

    if t == "dashboard_filter":
        b = DashboardFilterBlock(
            id=spec.id,
            title=cfg.get("title", "Фильтр"),
            filter_col=cfg.get("filter_col", ""),
            target_chart=cfg.get("target_chart", ""),
            extra_target_charts=cfg.get("extra_target_charts", ""),
            dataframe=block_df,
            source_file_name=cfg.get("source_file_name", ""),
            source_sheet=cfg.get("source_sheet", "") or cfg.get("source_file", ""),
            max_height=int(cfg.get("max_height", 420) if "max_height" in cfg else 420),
            sync_height=bool(cfg.get("sync_height", True)),
            **layout_kwargs,
        )
        b.config = cfg
        b._report_ref = ctx.report
        b._file_manager = ctx.file_manager
        return b

    if t == "paragraph":
        b = ParagraphBlock(
            id=spec.id,
            text=cfg.get("text", ""),
            raw_html=bool(cfg.get("raw_html", False)),
            font_size=int(cfg.get("font_size", 14) or 14),
            text_align=str(cfg.get("text_align", "left") or "left"),
            **layout_kwargs,
        )
        b.config = cfg
        b._spec_ref = spec
        b._report_ref = ctx.report
        b._file_manager = ctx.file_manager
        return b

    if t == "list":
        b = ListBlock(
            id=spec.id,
            items=list(cfg.get("items", [])),
            html=cfg.get("html", ""),
            raw_html=bool(cfg.get("raw_html", False)),
            **layout_kwargs,
        )
        b._spec_ref = spec
        return b

    if t == "divider":
        return DividerBlock(id=spec.id)

    if t == "kpi_row":
        cards = [
            KpiCard(
                label=c.get("label", ""),
                value=str(c.get("value", "")),
                accent=bool(c.get("accent", False)),
            )
            for c in cfg.get("cards", [])
        ]
        b = KpiRowBlock(id=spec.id, cards=cards, **layout_kwargs)
        b._spec_ref = spec
        return b

    if t == "data_table":
        sig_dt = inspect.signature(DataTableBlock.__init__)
        dt_kwargs = {
            "id": spec.id,
            "title": cfg.get("title", "Реестр путевых листов / Таблица данных"),
            "dataframe": block_df,
            "source_file_name": cfg.get("source_file_name", ""),
            "source_sheet": cfg.get("source_sheet", "") or cfg.get("source_file", ""),
            "max_rows": int(cfg.get("max_rows", 20)),
            "visible_columns": cfg.get("visible_columns"),
            "preview_limit": ctx.preview_limit,
            **layout_kwargs,
        }
        filtered_dt = {k: v for k, v in dt_kwargs.items() if k in sig_dt.parameters}
        b = DataTableBlock(**filtered_dt)
        b.config = cfg
        b._spec_ref = spec
        b._report_ref = ctx.report
        b._file_manager = ctx.file_manager
        return b

    if t == "pivot_matrix":
        sig_pm = inspect.signature(PivotMatrixBlock.__init__)
        pm_kwargs = {
            "id": spec.id,
            "title": cfg.get("title", "Сводная матрица"),
            "dataframe": block_df,
            "source_file_name": cfg.get("source_file_name", ""),
            "source_sheet": cfg.get("source_sheet", "") or cfg.get("source_file", ""),
            "row_group_col": cfg.get("row_group_col", ""),
            "row_level2_col": cfg.get("row_level2_col", ""),
            "row_level3_col": cfg.get("row_level3_col", ""),
            "col_group_col": cfg.get("col_group_col", ""),
            "value_col": cfg.get("value_col", ""),
            "value_cols": list(cfg.get("value_cols") or []),
            "calc_cols": list(cfg.get("calc_cols") or []),
            "color_calc_enabled": bool(cfg.get("color_calc_enabled", False)),
            "color_calc_scope": str(cfg.get("color_calc_scope", "calc_and_dev") or "calc_and_dev"),
            "neg_color": str(cfg.get("neg_color", "#16a34a") or "#16a34a"),
            "pos_color": str(cfg.get("pos_color", "#dc2626") or "#dc2626"),
            "color_calc_bg": bool(cfg.get("color_calc_bg", True)),
            "sticky_header": bool(cfg.get("sticky_header", True)),
            "sticky_first_col": bool(cfg.get("sticky_first_col", True)),
            "max_table_height": int(cfg.get("max_table_height", 520) if "max_table_height" in cfg else 520),
            "show_search": bool(cfg.get("show_search", True)),
            "target_table": str(cfg.get("target_table", "") or ""),
            "agg_func": cfg.get("agg_func", "sum"),
            "show_totals": bool(cfg.get("show_totals", True)),
            "top_n": int(cfg.get("top_n", 30) or 30),
            **layout_kwargs,
        }
        filtered_pm = {k: v for k, v in pm_kwargs.items() if k in sig_pm.parameters}
        b = PivotMatrixBlock(**filtered_pm)
        b.config = cfg
        b._report_ref = ctx.report
        b._file_manager = ctx.file_manager
        return b

    if t == "decomposition":
        b = DecompositionBlock(
            id=spec.id,
            title=cfg.get("title", "Дерево декомпозиции"),
            dataframe=block_df,
            source_file_name=cfg.get("source_file_name", ""),
            source_sheet=cfg.get("source_sheet", "") or cfg.get("source_file", ""),
            value_col=cfg.get("value_col", ""),
            level1_col=cfg.get("level1_col", ""),
            level2_col=cfg.get("level2_col", ""),
            level3_col=cfg.get("level3_col", ""),
            level_cols=list(cfg.get("level_cols") or []),
            tree_mode=cfg.get("tree_mode", "treemap"),
            agg_func=cfg.get("agg_func", "sum"),
            palette=cfg.get("palette", "Greens"),
            top_n=int(cfg.get("top_n", 60) or 60),
            **layout_kwargs,
        )
        b.config = cfg
        b._report_ref = ctx.report
        b._file_manager = ctx.file_manager
        return b

    if t == "geo_map":
        b = GeoMapBlock(
            id=spec.id,
            title=cfg.get("title", "География и рейтинг объектов"),
            dataframe=block_df,
            source_file_name=cfg.get("source_file_name", ""),
            source_sheet=cfg.get("source_sheet", "") or cfg.get("source_file", ""),
            loc_col=cfg.get("loc_col", ""),
            value_col=cfg.get("value_col", ""),
            map_mode=cfg.get("map_mode", "ranking_bar"),
            agg_func=cfg.get("agg_func", "sum"),
            top_n=int(cfg.get("top_n", 20) or 20),
            palette=cfg.get("palette", "Greens"),
            **layout_kwargs,
        )
        b.config = cfg
        b._report_ref = ctx.report
        b._file_manager = ctx.file_manager
        return b

    if t == "container":
        children_specs = cfg.get("children", [])
        layout_kind = cfg.get("layout", "row")
        gap = int(cfg.get("gap", 16))
        n_children = max(1, len(children_specs))
        default_w = max(20, 100 // n_children)

        children_html = []
        for child_spec in children_specs:
            if isinstance(child_spec, dict):
                child_spec = ReportBlock(
                    id=child_spec.get("id", ""),
                    type=child_spec.get("type", ""),
                    config=child_spec.get("config", {}),
                )
            c_cfg = dict(child_spec.config or {})
            raw_w = int(c_cfg.get("width", default_w))
            child_w_pct = max(15, min(100, raw_w))
            # Если у контейнера задана большая высота, передаём её вложенному графику
            if mh_val > 0 and int(c_cfg.get("min_height", 0) or 0) <= 260:
                c_cfg["min_height"] = mh_val
                child_spec.config = c_cfg
            full_row = bool(c_cfg.get("full_row", False))

            child_block = create_block(child_spec, ctx)
            if isinstance(child_block, ParagraphBlock):
                raw_child_html = child_block.render(dataframe=_resolve_df_for_spec(child_spec, ctx))
            else:
                raw_child_html = child_block.render()

            if layout_kind == "row":
                if full_row and child_w_pct < 100:
                    wrapped_child = (
                        f'<div class="ea-container-cell" data-child-type="{child_spec.type}" '
                        f'style="flex: 0 0 100%; max-width: 100%; display: flex; justify-content: center; box-sizing: border-box;">'
                        f'<div style="width: {child_w_pct}%; max-width: {child_w_pct}%; box-sizing: border-box;">'
                        f'{raw_child_html}'
                        f'</div></div>'
                    )
                else:
                    gap_deduct = 0 if child_w_pct >= 100 else max(0, int(round(gap * (100 - child_w_pct) / 100.0)))
                    css_w = "100%" if child_w_pct >= 100 else f"calc({child_w_pct}% - {gap_deduct}px)"
                    wrapped_child = (
                        f'<div class="ea-container-cell" data-child-type="{child_spec.type}" '
                        f'style="flex: 0 0 {css_w}; max-width: {css_w}; width: {css_w}; box-sizing: border-box;">'
                        f'{raw_child_html}'
                        f'</div>'
                    )
            else:
                wrapped_child = (
                    f'<div class="ea-container-cell" data-child-type="{child_spec.type}" '
                    f'style="width: 100%; max-width: 100%; box-sizing: border-box;">'
                    f'{raw_child_html}'
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
            min_height=mh_val if 'mh_val' in locals() else 0,
        )
        b._spec_ref = spec
        return b

    return Block(id=spec.id, type=t, **layout_kwargs)


def render_report(report, ctx: RenderContext) -> str:
    if ctx.report is None:
        ctx.report = report
    if ctx.file_manager is None:
        ctx.file_manager = getattr(report, "file_manager", None)

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
            if isinstance(block_obj, ParagraphBlock):
                raw_block_html = block_obj.render(dataframe=_resolve_df_for_spec(spec, ctx))
            else:
                raw_block_html = block_obj.render()

            parts_html.append(_wrap_positioned_html(raw_block_html, spec))

        parts_html.append(DividerBlock(id=f"div_{section.id}").render())

    content = "\n".join(parts_html)
    return aside_html + '<div class="report-content">' + content + '</div>'


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
    "pivot_matrix",
    "decomposition",
    "geo_map",
    "container",
    "plotly_chart",
    "dashboard_filter",
}

assert set(BLOCK_TYPES) | {"container"} == _KNOWN_TYPES, (
    "BLOCK_TYPES и create_block разошлись!"
)