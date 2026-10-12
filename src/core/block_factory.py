"""
Превращает "инструкцию блока" в готовый HTML-блок.

Как это работает:
  1. В проекте (.earpg) хранятся ИНСТРУКЦИИ.
  2. Когда надо показать отчёт — этот файл читает инструкцию,
     берёт АКТУАЛЬНЫЕ данные из загруженного Excel
     и делает из этого готовый к показу блок.
  3. Готовый блок умеет render() → возвращает HTML.

Больше нигде в программе типы блоков не перечисляются.
Только здесь — в списке BLOCK_TYPES.
"""

from __future__ import annotations

from dataclasses import dataclass

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
    # container — не в палитре, создаётся через слияние блоков
}


# ============================================================
# ДАННЫЕ, КОТОРЫЕ НУЖНЫ БЛОКАМ ВО ВРЕМЯ ПОКАЗА
# ============================================================

@dataclass
class RenderContext:
    """То, что блоки могут взять во время показа."""
    dataframe: pd.DataFrame | None = None
    # ★ Лимит строк для data_table: 0 = без лимита (экспорт),
    #   >0 = резать (preview — большие таблицы тормозят браузер).
    preview_limit: int = 0


# ============================================================
# ГЛАВНАЯ ФУНКЦИЯ: инструкция → готовый блок
# ============================================================

def create_block(spec: ReportBlock, ctx: RenderContext) -> Block:
    """Читает инструкцию блока (spec) и делает из неё готовый блок."""
    t = spec.type
    cfg = spec.config or {}

    # Layout-параметры (для всех, кроме divider и container)
    layout_kwargs = {
        "width": spec.get_width(),
        "margin_top": spec.get_margin_top(),
        "margin_bottom": spec.get_margin_bottom(),
        "min_height": spec.get_min_height(),
    }

    # --- Заголовок раздела ---
    if t == "section_title":
        return SectionTitleBlock(
            id=spec.id,
            title=cfg.get("title", ""),
            **layout_kwargs,
        )

    # --- Параграф ---
    if t == "paragraph":
        return ParagraphBlock(
            id=spec.id,
            text=cfg.get("text", ""),
            raw_html=cfg.get("raw_html", False),
            **layout_kwargs,
        )

    # --- Список ---
    if t == "list":
        return ListBlock(
            id=spec.id,
            items=list(cfg.get("items", [])),
            **layout_kwargs,
        )

    # --- Разделитель ---
    if t == "divider":
        return DividerBlock(id=spec.id)

    # --- KPI-ряд ---
    if t == "kpi_row":
        cards = []
        for c in cfg.get("cards", []):
            cards.append(KpiCard(
                label=c.get("label", ""),
                value=str(c.get("value", "")),
                accent=bool(c.get("accent", False)),
            ))
        return KpiRowBlock(id=spec.id, cards=cards, **layout_kwargs)

    # --- Таблица данных ---
    if t == "data_table":
        return DataTableBlock(
            id=spec.id,
            dataframe=ctx.dataframe,
            max_rows=int(cfg.get("max_rows", 20)),
            visible_columns=cfg.get("visible_columns"),
            preview_limit=ctx.preview_limit,
            **layout_kwargs,
        )
    # --- Контейнер (сетка) ---
    if t == "container":
        children_specs = cfg.get("children", [])
        children_html = []
        for child_spec in children_specs:
            # child_spec — это dict или ReportBlock
            if isinstance(child_spec, dict):
                child_spec = ReportBlock(
                    id=child_spec.get("id", ""),
                    type=child_spec.get("type", ""),
                    config=child_spec.get("config", {}),
                )
            child_block = create_block(child_spec, ctx)
            children_html.append(child_block.render())
        return ContainerBlock(
            id=spec.id,
            layout=cfg.get("layout", "row"),
            gap=int(cfg.get("gap", 14)),
            children_html=children_html,
            **layout_kwargs,
        )

    # --- Неизвестный тип ---
    return Block(
        id=spec.id,
        type=t,
        title=f"[неизвестный блок: {t}]",
        **layout_kwargs,
    )


# ============================================================
# ГРУППИРОВКА БЛОКОВ В СТРОКИ (flexbox)
# ============================================================

def _group_into_rows(blocks: list[ReportBlock]) -> list[list[ReportBlock]]:
    """
    Группирует блоки: соседние блоки с width < 100 и суммой ≤ 100
    попадают в одну flexbox-строку.
    Блоки с width=100 — отдельная строка.
    """
    rows: list[list[ReportBlock]] = []
    current_row: list[ReportBlock] = []
    current_width = 0

    for block in blocks:
        if block.type == "divider":
            # Divider — всегда отдельно
            if current_row:
                rows.append(current_row)
                current_row = []
                current_width = 0
            rows.append([block])
            continue

        w = block.get_width()

        if w >= 100:
            if current_row:
                rows.append(current_row)
                current_row = []
                current_width = 0
            rows.append([block])
        else:
            if current_width + w > 100:
                rows.append(current_row)
                current_row = [block]
                current_width = w
            else:
                current_row.append(block)
                current_width += w

    if current_row:
        rows.append(current_row)
    return rows


# ============================================================
# ОТРИСОВКА ВСЕГО ОТЧЁТА
# ============================================================

def render_report(report, ctx: RenderContext) -> str:
    """Проходит по всем разделам и блокам, возвращает HTML.
    Плюс слева — статичное меню разделов (оформление по эталону)."""
    from src.core.renderer import Renderer

    # ── Левое меню (оформление — по эталону отчёта ГСМ) ──
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

    # ── Контент отчёта ──
    r = Renderer()
    for section in report.sections:
        r.add_raw(f'<div id="section-{section.id}" class="section-anchor"></div>')
        r.add(SectionTitleBlock(
            id=section.id,
            title=f"{section.icon} {section.title}".strip(),
        ))

        for spec in section.blocks:
            r.add(create_block(spec, ctx))

        r.add(DividerBlock(id=f"div_{section.id}"))

    content = r.render()

    return (
        aside_html
        + '<div class="report-content">' + content + '</div>'
    )


def _esc(text: str) -> str:
    """Экранирование HTML для меню."""
    if not isinstance(text, str):
        text = str(text)
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )


# ============================================================
# ЗАЩИТА ОТ РАССИНХРОНА
# ============================================================

_KNOWN_TYPES = {
    "section_title",
    "paragraph",
    "list",
    "divider",
    "kpi_row",
    "data_table",
    "container",
}

assert set(BLOCK_TYPES) | {"container"} == _KNOWN_TYPES, (
    "BLOCK_TYPES и create_block разошлись!"
)