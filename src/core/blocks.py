"""
Модель блоков отчёта.
Простые dataclass'ы — что именно показывать в отчёте.
"""

import pandas as pd

from dataclasses import dataclass, field


# ============================================================
# Базовый блок
# ============================================================

@dataclass
class Block:
    """Базовый блок."""
    id: str
    type: str
    title: str = ""

    # Layout-параметры (из config, прокидываются в render)
    width: int = 100
    margin_top: int = 0
    margin_bottom: int = 14
    min_height: int = 0

    def render(self) -> str:
        """Рендерит блок в HTML. Переопределяется в наследниках."""
        return f'<!-- block {self.id}: {self.type} -->'

    def wrap_layout(self, inner_html: str) -> str:
        """Оборачивает блок в div с шириной и отступами."""
        width = self.width
        style = (
            f"flex: 0 0 {width}%; "
            f"max-width: {width}%; "
            f"width: {width}%; "
            f"margin-top: {self.margin_top}px; "
            f"margin-bottom: {self.margin_bottom}px; "
            f"box-sizing: border-box;"
        )
        if self.min_height and self.min_height > 0:
            style += f" min-height: {self.min_height}px;"
            # ★ Чтобы внутренний block-card растянулся на всю высоту,
            # нужен flex-column на layout-item.
            style += " display: flex; flex-direction: column;"

        return f'<div class="layout-item" style="{style}">{inner_html}</div>'


# ============================================================
# Текстовые блоки
# ============================================================

@dataclass
class SectionTitleBlock(Block):
    """Заголовок раздела. Поддерживает rich-text, если в title есть теги."""
    type: str = "section_title"
    raw_html: bool = False

    def render(self) -> str:
        if self.raw_html:
            title = _extract_body(self.title)
        else:
            # Если пользователь ввёл простой текст — экранируем.
            title = _escape(self.title)
        inner = f'<h1 class="section-title">{title}</h1>'
        return self.wrap_layout(inner)


@dataclass
class ParagraphBlock(Block):
    """Параграф текста. Поддерживает HTML (rich-text)."""
    type: str = "paragraph"
    text: str = ""
    raw_html: bool = False

    def render(self) -> str:
        if self.raw_html:
            # Rich-text: чистим Qt-обёртку и вставляем как есть.
            content = _extract_body(self.text)
            if not content.strip():
                content = "<p></p>"
        else:
            # Плейн-текст: как раньше — экранируем и режем по пустым строкам.
            safe = _escape(self.text)
            paragraphs = [
                f"<p>{p.strip()}</p>"
                for p in safe.split("\n\n")
                if p.strip()
            ]
            content = "".join(paragraphs) if paragraphs else "<p></p>"

        inner = (
            f'<div class="block">'
            f'<div class="block-card">'
            f'<div class="paragraph">{content}</div>'
            f'</div></div>'
        )
        return self.wrap_layout(inner)


@dataclass
class ListBlock(Block):
    """Список пунктов.
    Два режима:
      - items=[...] + raw_html=False — простые пункты (экранируются).
      - html="<ul>...</ul>"        — rich-text HTML целиком (тулбар).
    """
    type: str = "list"
    items: list[str] = field(default_factory=list)
    html: str = ""
    raw_html: bool = False

    def render(self) -> str:
        if self.raw_html and self.html.strip():
            # Rich-text: HTML уже готов (обычно <ul>/<ol> из Qt).
            content = _extract_body(self.html)
        else:
            # Простой режим: строим <ul> из items.
            items_html = "".join(
                f"<li>{_escape(item)}</li>" for item in self.items
            )
            content = f'<ul class="block-list">{items_html}</ul>'

        inner = (
            f'<div class="block">'
            f'<div class="block-card">'
            f'<div class="list-rich">{content}</div>'
            f'</div></div>'
        )
        return self.wrap_layout(inner)


@dataclass
class DividerBlock(Block):
    """Разделитель между разделами."""
    type: str = "divider"

    def render(self) -> str:
        # Divider — служебный элемент между разделами.
        # Ширину игнорируем, всегда 100%.
        return '<div class="section-divider"></div>'


# ============================================================
# KPI-блоки
# ============================================================

@dataclass
class KpiCard:
    """Одна KPI-карточка."""
    label: str
    value: str
    accent: bool = False


@dataclass
class KpiRowBlock(Block):
    """Ряд KPI-карточек."""
    type: str = "kpi_row"
    cards: list[KpiCard] = field(default_factory=list)

    def render(self) -> str:
        cards_html = []
        for card in self.cards:
            accent_class = " accent" if card.accent else ""
            cards_html.append(
                f'<div class="kpi-card">'
                f'<div class="kpi-value{accent_class}">{_escape(card.value)}</div>'
                f'<div class="kpi-label">{_escape(card.label)}</div>'
                f'</div>'
            )
        inner = (
            f'<div class="block">'
            f'<div class="kpi-row">{"".join(cards_html)}</div>'
            f'</div>'
        )
        return self.wrap_layout(inner)


# ============================================================
# Таблица данных
# ============================================================

@dataclass
class DataTableBlock(Block):
    type: str = "data_table"
    dataframe: object = None
    max_rows: int = 20
    visible_columns: list[str] | None = None
    preview_limit: int = 0

    def render(self) -> str:
        if self.dataframe is None or len(self.dataframe) == 0:
            return self.wrap_layout(self._render_empty())

        df = self.dataframe
        if self.visible_columns is None:
            cols = list(df.columns)
        else:
            cols = [c for c in self.visible_columns if c in df.columns]
        if not cols:
            return self.wrap_layout(self._render_empty())

        df = df[cols]

        total_rows = len(df)
        truncated = False
        # ★ Жёсткий потолок для preview = 1000 строк, чтобы HTML
        #   не пух. max_rows задаёт высоту окна, preview_limit —
        #   максимальное число строк, которые физически попадут в HTML.
        hard_cap = self.preview_limit if self.preview_limit and self.preview_limit > 0 else 1000
        if len(df) > hard_cap:
            df = df.head(hard_cap)
            truncated = True

        records = df.to_dict("records")
        rows_data = []
        for rec in records:
            item = {}
            for col in df.columns:
                item[str(col)] = self._format_value(rec.get(col))
            rows_data.append(item)

        import json as _json
        schema = [{"name": str(c)} for c in df.columns]
        payload_json = _json.dumps(
            {"schema": schema, "rows": rows_data},
            ensure_ascii=False,
        )

        tbl_id = f"ea-tbl-{self.id}"

        max_rows_val = int(self.max_rows) if self.max_rows is not None else 20
        window_h = 40 + max_rows_val * 30 if max_rows_val > 0 else 500
        if window_h < 120:
            window_h = 120

        info = f"Всего строк: {total_rows}."
        if truncated:
            info = (f"⚠ Показаны первые {self.preview_limit} "
                    f"из {total_rows} строк (preview).")

        inner = f'''
        <div class="block" style="min-width:0; max-width:100%;">
            <div class="block-card" style="padding:0; min-width:0; max-width:100%; overflow:hidden;">
                <div class="ea-table-toolbar"
                     style="padding: 8px 12px; border-bottom: 1px solid #eee;
                            background: #fafafa; display: flex;
                            align-items: center; gap: 8px;">
                    <button type="button"
                            class="ea-table-search-btn"
                            data-target="{tbl_id}"
                            style="background: #fff; color: #333;
                                   border: 1px solid #d5d5db;
                                   border-radius: 6px; padding: 5px 12px;
                                   font-size: 12px; cursor: pointer;
                                   font-weight: 600;">
                        🔍  Найти
                    </button>
                    <input type="text"
                           class="ea-table-search-input"
                           data-target="{tbl_id}"
                           placeholder="Поиск по всем колонкам..."
                           style="display:none; flex:1; min-width:180px;
                                  padding:5px 10px; font-size:12px;
                                  border:1px solid #87C800;
                                  border-radius:6px;
                                  outline:none; background:#fff;" />
                </div>
                <div style="width:100%; max-width:100%; overflow:hidden;">
                    <div id="{tbl_id}"
                         style="width:100%; max-width:100%;
                                height:{window_h}px; overflow:hidden;"></div>
                </div>
                <div style="padding:8px 12px; font-size:12px; color:#888;
                            border-top:1px solid #eee;">
                    {info}
                </div>
            </div>
        </div>
        <script type="application/json" id="{tbl_id}-payload">{payload_json}</script>
        <script>
        (function() {{
            if (typeof canvasDatagrid === "undefined") return;
            var el = document.getElementById("{tbl_id}");
            var payload = JSON.parse(
                document.getElementById("{tbl_id}-payload").textContent
            );

            // ★ Ширина = ширина родителя. Иначе canvas-datagrid растянется
            //   под содержимое и вылезет за правый край.
            function hostWidth() {{
                var w = el.clientWidth;
                if (!w && el.parentNode) w = el.parentNode.clientWidth;
                return w > 100 ? w : 800;
            }}

            var grid = canvasDatagrid({{
                parentNode: el,
                data: payload.rows,
                schema: payload.schema,
                editable: false,
                autoResizeColumns: true,
                columnHeaderHeight: 32,
                rowHeaderWidth: 50,
                showRowHeaders: true,
                style: {{
                    width: hostWidth() + "px",
                    height: "{window_h}px",
                    overflowX: "auto",
                    overflowY: "auto",
                }},
            }});

            window.addEventListener("resize", function() {{
                try {{
                    grid.style.width = hostWidth() + "px";
                    grid.resize();
                }} catch (e) {{}}
            }});

            // ── Поиск ──
            var btn = document.querySelector('.ea-table-search-btn[data-target="{tbl_id}"]');
            var inp = document.querySelector('.ea-table-search-input[data-target="{tbl_id}"]');

            btn.addEventListener("click", function() {{
                btn.style.display = "none";
                inp.style.display = "inline-block";
                inp.focus();
            }});
            inp.addEventListener("input", function() {{
                grid.filter = inp.value;
            }});
            inp.addEventListener("keydown", function(e) {{
                if (e.key === "Escape") {{
                    inp.value = "";
                    grid.filter = "";
                    inp.style.display = "none";
                    btn.style.display = "inline-block";
                }}
            }});
            inp.addEventListener("blur", function() {{
                if (!inp.value.trim()) {{
                    inp.style.display = "none";
                    btn.style.display = "inline-block";
                }}
            }});
        }})();
        </script>
        '''
        return self.wrap_layout(inner)

    def _render_empty(self) -> str:
        return '''
        <div class="block">
            <div class="block-card" style="text-align:center; padding: 60px 20px;">
                <p style="color:#888; font-size: 14px;">Нет выбранных колонок</p>
            </div>
        </div>
        '''

    @staticmethod
    def _format_value(val) -> str:
        if pd.isna(val):
            return "—"
        if isinstance(val, float):
            if abs(val) < 1:
                return f"{val:.4f}".rstrip("0").rstrip(".")
            return f"{val:,.2f}"
        if isinstance(val, int):
            return f"{val:,}"
        return str(val)

@dataclass
class ContainerBlock(Block):
    """
    Контейнер с вложенными блоками.
    layout: "row" (горизонтально) или "column" (вертикально).
    gap: отступ между вложенными блоками (px).
    children: список дочерних блоков (уже отрендеренных в HTML).
    """
    type: str = "container"
    layout: str = "row"
    gap: int = 14
    children_html: list[str] = field(default_factory=list)

    def render(self) -> str:
        if self.dataframe is None or len(self.dataframe) == 0:
            return self.wrap_layout(self._render_empty())

        if self.visible_columns is not None and len(self.visible_columns) == 0:
            return self.wrap_layout(self._render_empty())

        df = self.dataframe

        if self.visible_columns is None:
            cols = list(df.columns)
        else:
            cols = [c for c in self.visible_columns if c in df.columns]

        if not cols:
            return self.wrap_layout(self._render_empty())

        df = df[cols]

        # ★ НЕ режем строки. Всегда рендерим всю таблицу.
        #   max_rows — это теперь ВЫСОТА ОКНА в строках:
        #     > 0  → max-height ≈ N строк, внутри вертикальный скролл
        #     <= 0 → высота авто (вся таблица развёрнута на странице)
        total_rows = len(df)
        max_rows_val = int(self.max_rows) if self.max_rows is not None else 20

        ROW_PX = 30        # высота одной строки (под наш CSS)
        HEADER_PX = 42     # высота шапки

        if max_rows_val > 0:
            window_h = HEADER_PX + max_rows_val * ROW_PX
            wrapper_style = (
                f"max-height: {window_h}px;"
                f"overflow-y: auto;"
                f"overflow-x: auto;"
            )
            footer_html = (
                f'<div style="padding:8px 12px; font-size:12px; '
                f'color:#888; border-top:1px solid #eee;">'
                f'Всего строк: {total_rows}. '
                f'Прокрутите таблицу, чтобы увидеть все.'
                f'</div>'
            )
        else:
            # 0 или отрицательное — «окно во всю таблицу»
            wrapper_style = "overflow-x: auto;"
            footer_html = (
                f'<div style="padding:8px 12px; font-size:12px; '
                f'color:#888; border-top:1px solid #eee;">'
                f'Всего строк: {total_rows} (показаны все).'
                f'</div>'
            )

        headers_html = "".join(
            f"<th>{_escape(str(col))}</th>" for col in df.columns
        )

        rows_html = []
        for _, row in df.iterrows():
            cells = []
            for col in df.columns:
                val = row[col]
                text = self._format_value(val)
                cells.append(f"<td>{_escape(text)}</td>")
            rows_html.append(f"<tr>{''.join(cells)}</tr>")

        inner = f'''
        <div class="block" style="min-width:0;">
            <div class="block-card" style="padding: 0; min-width:0; overflow:hidden;">
                <div class="data-table-wrapper"
                     style="{wrapper_style} width:100%; max-width:100%;">
                    <table class="data-table"
                           style="width:max-content; min-width:100%;">
                        <thead><tr>{headers_html}</tr></thead>
                        <tbody>{''.join(rows_html)}</tbody>
                    </table>
                </div>
                {footer_html}
            </div>
        </div>
        '''
        return self.wrap_layout(inner)


# ============================================================
# Утилиты
# ============================================================

def _escape(text: str) -> str:
    """Простое экранирование HTML."""
    if not isinstance(text, str):
        text = str(text)
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )


def _extract_body(html: str) -> str:
    """
    Достаёт внутренности <body>…</body> из Qt-HTML.
    Если <body> нет — возвращает исходную строку.

    Qt QTextEdit.toHtml() отдаёт полный документ с <html>, <head>,
    встроенными <style> и т.п. Для отчёта нам нужна только
    содержательная часть.
    """
    if not isinstance(html, str):
        return ""
    low = html.lower()
    start = low.find("<body")
    if start == -1:
        return html
    gt = html.find(">", start)
    if gt == -1:
        return html
    end = low.rfind("</body>")
    if end == -1:
        return html[gt + 1:]
    return html[gt + 1:end]