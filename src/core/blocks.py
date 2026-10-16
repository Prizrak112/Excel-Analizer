"""
Модель блоков отчёта.
Содержит логику рендеринга всех типов блоков в HTML, включая продвинутые графики Plotly
с поддержкой агрегаций, цветовых палитр, легенд и подложек.
"""

import pandas as pd
from dataclasses import dataclass, field


# ============================================================
# Базовый блок
# ============================================================

@dataclass
class Block:
    """Базовый блок отчёта."""
    id: str
    type: str
    title: str = ""

    width: int = 100
    margin_top: int = 0
    margin_bottom: int = 14
    min_height: int = 0

    def render(self) -> str:
        return f'<!-- block {self.id}: {self.type} -->'

    def wrap_layout(self, inner_html: str) -> str:
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
            style += " display: flex; flex-direction: column;"

        return f'<div class="layout-item" style="{style}">{inner_html}</div>'


# ============================================================
# Текстовые блоки
# ============================================================

@dataclass
class SectionTitleBlock(Block):
    type: str = "section_title"
    raw_html: bool = False

    def render(self) -> str:
        if self.raw_html:
            title = _extract_body(self.title)
        else:
            title = _escape(self.title)
        inner = f'<h1 class="section-title" id="{self.id}">{title}</h1>'
        return self.wrap_layout(inner)


@dataclass
class ParagraphBlock(Block):
    type: str = "paragraph"
    text: str = ""
    raw_html: bool = False

    def render(self) -> str:
        if self.raw_html:
            content = _extract_body(self.text)
            if not content.strip():
                content = "<p></p>"
        else:
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
    type: str = "list"
    items: list[str] = field(default_factory=list)
    html: str = ""
    raw_html: bool = False

    def render(self) -> str:
        if self.raw_html and self.html.strip():
            content = _extract_body(self.html)
        else:
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
    type: str = "divider"

    def render(self) -> str:
        return '<div class="section-divider"></div>'


# ============================================================
# KPI-блоки
# ============================================================

@dataclass
class KpiCard:
    label: str
    value: str
    accent: bool = False


@dataclass
class KpiRowBlock(Block):
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
            info = f"⚠ Показаны первые {self.preview_limit} из {total_rows} строк (preview)."

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


# ============================================================
# График Plotly (Продвинутый генератор для HTML-экспорта)
# ============================================================

_PALETTE_HEX = {
    "corporate": ["#2b7fff", "#87C800", "#ff9f1c", "#e71d36", "#6f42c1", "#20c997", "#fd7e14"],
    "emerald":   ["#003F0B", "#2bb24c", "#87C800", "#52b788", "#74c69d", "#95d5b2", "#b7e4c7"],
    "sunset":    ["#f72585", "#7209b7", "#3a0ca3", "#4361ee", "#4cc9f0", "#ff9e00", "#ff0055"],
    "pastel":    ["#60a5fa", "#34d399", "#fbbf24", "#f87171", "#a78bfa", "#f472b6", "#38bdf8"],
}


@dataclass
class PlotlyChartBlock(Block):
    show_title: bool = True
    show_axis_labels: bool = True
    type: str = "plotly_chart"
    dataframe: object = None
    chart_type: str = "bar"
    x_col: str = ""
    y_col: str = ""
    title: str = "График данных"
    agg: str = "sum"
    sort_by: str = "value_desc"
    top_n: int = 12
    row_start: int = 0
    row_limit: int = 0
    palette: str = "corporate"
    bg_color: str = "#ffffff"
    legend_pos: str = "right"
    show_legend: bool = True
    show_values: bool = True
    show_grid: bool = True

    def render(self) -> str:
        if self.dataframe is None or len(self.dataframe) == 0:
            return self.wrap_layout(self._render_empty("Нет данных (загрузите Excel)"))

        df = self.dataframe
        if self.row_start > 0 or self.row_limit > 0:
            end_idx = (self.row_start + self.row_limit) if self.row_limit > 0 else len(df)
            df = df.iloc[self.row_start:end_idx]

        if not self.x_col or self.x_col not in df.columns:
            self.x_col = df.columns[0]

        try:
            import plotly.express as px
            import plotly.io as pio

            work_df = df.copy()
            if self.chart_type == "histogram":
                fig = px.histogram(
                    work_df,
                    x=self.x_col,
                    title=self.title if self.show_title else "",
                    color_discrete_sequence=_PALETTE_HEX.get(self.palette, _PALETTE_HEX["corporate"]),
                )
            else:
                if not self.y_col or self.y_col not in work_df.columns or self.agg == "count":
                    grouped = work_df[self.x_col].astype(str).value_counts()
                    y_label = "Количество записей"
                    plot_df = pd.DataFrame({self.x_col: grouped.index, y_label: grouped.values})
                    y_field = y_label
                else:
                    work_df[self.y_col] = pd.to_numeric(work_df[self.y_col], errors="coerce").fillna(0)
                    if self.agg == "mean":
                        grouped = work_df.groupby(work_df[self.x_col].astype(str))[self.y_col].mean()
                    elif self.agg == "max":
                        grouped = work_df.groupby(work_df[self.x_col].astype(str))[self.y_col].max()
                    elif self.agg == "min":
                        grouped = work_df.groupby(work_df[self.x_col].astype(str))[self.y_col].min()
                    elif self.agg == "median":
                        grouped = work_df.groupby(work_df[self.x_col].astype(str))[self.y_col].median()
                    else:
                        grouped = work_df.groupby(work_df[self.x_col].astype(str))[self.y_col].sum()
                    y_label = str(self.y_col)
                    plot_df = pd.DataFrame({self.x_col: grouped.index, y_label: grouped.values})
                    y_field = y_label

                if self.sort_by == "value_desc":
                    plot_df = plot_df.sort_values(by=y_field, ascending=False)
                elif self.sort_by == "value_asc":
                    plot_df = plot_df.sort_values(by=y_field, ascending=True)
                elif self.sort_by == "label_asc":
                    plot_df = plot_df.sort_values(by=self.x_col, ascending=True)

                if self.top_n > 0:
                    plot_df = plot_df.head(self.top_n)

                colors_list = _PALETTE_HEX.get(self.palette, _PALETTE_HEX["corporate"])
                chart_title = self.title if self.show_title else ""

                if self.chart_type == "bar":
                    fig = px.bar(
                        plot_df, x=self.x_col, y=y_field,
                        color=self.x_col, color_discrete_sequence=colors_list,
                        title=chart_title, text=y_field if self.show_values else None,
                    )
                    if self.show_values:
                        fig.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
                elif self.chart_type == "hbar":
                    fig = px.bar(
                        plot_df, x=y_field, y=self.x_col,
                        color=self.x_col, color_discrete_sequence=colors_list,
                        orientation="h", title=chart_title, text=y_field if self.show_values else None,
                    )
                    if self.show_values:
                        fig.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
                elif self.chart_type == "line":
                    fig = px.line(plot_df, x=self.x_col, y=y_field, title=chart_title, markers=True)
                    fig.update_traces(line=dict(color=colors_list[0], width=3))
                elif self.chart_type == "area":
                    fig = px.area(plot_df, x=self.x_col, y=y_field, title=chart_title)
                elif self.chart_type == "scatter":
                    fig = px.scatter(
                        plot_df, x=self.x_col, y=y_field,
                        color=self.x_col, color_discrete_sequence=colors_list, title=chart_title,
                    )
                elif self.chart_type in ("pie", "donut"):
                    fig = px.pie(
                        plot_df, names=self.x_col, values=y_field,
                        color_discrete_sequence=colors_list, title=chart_title,
                        hole=0.52 if self.chart_type == "donut" else 0.0,
                    )
                elif self.chart_type == "box":
                    fig = px.box(work_df, y=self.y_col if self.y_col else self.x_col, title=chart_title, color_discrete_sequence=colors_list)
                elif self.chart_type == "funnel":
                    fig = px.funnel(
                        plot_df, x=y_field, y=self.x_col,
                        color=self.x_col, color_discrete_sequence=colors_list, title=chart_title,
                    )
                else:
                    fig = px.bar(plot_df, x=self.x_col, y=y_field, title=chart_title)

            bg_hex = (self.bg_color or "#ffffff").lstrip('#')
            if len(bg_hex) == 3:
                bg_hex = ''.join([c * 2 for c in bg_hex])
            try:
                r_val, g_val, b_val = int(bg_hex[0:2], 16), int(bg_hex[2:4], 16), int(bg_hex[4:6], 16)
                luminance = (0.299 * r_val + 0.587 * g_val + 0.114 * b_val) / 255
                is_dark = luminance < 0.5
            except Exception:
                is_dark = False

            text_color = "#f0f4f8" if is_dark else "#333333"
            grid_color = "#334155" if is_dark else "#e2e8f0"

            x_title_val = self.x_col if self.show_axis_labels else ""
            y_title_val = (self.y_col if self.y_col else "Значения") if self.show_axis_labels else ""

            legend_config = dict(title_text="", visible=bool(self.show_legend))
            if self.legend_pos == "top":
                legend_config.update(dict(orientation="h", yanchor="bottom", y=1.12, xanchor="center", x=0.5))
            elif self.legend_pos == "bottom":
                legend_config.update(dict(orientation="h", yanchor="top", y=-0.25, xanchor="center", x=0.5))
            else:
                legend_config.update(dict(orientation="v", yanchor="top", y=1.0, xanchor="left", x=1.02))

            fig.update_layout(
                plot_bgcolor=self.bg_color,
                paper_bgcolor=self.bg_color,
                font=dict(family="Segoe UI, sans-serif", size=12, color=text_color),
                margin=dict(l=45, r=50, t=55 if (self.title and self.show_title) else 25, b=65),
                title=dict(font=dict(size=15, color=text_color, family="Segoe UI, sans-serif")),
                xaxis=dict(title=dict(text=x_title_val), showgrid=bool(self.show_grid), gridcolor=grid_color, tickangle=-25),
                yaxis=dict(title=dict(text=y_title_val), showgrid=bool(self.show_grid), gridcolor=grid_color),
                legend=legend_config,
                autosize=True,
            )

            chart_div = pio.to_html(fig, include_plotlyjs="cdn", full_html=False)

        except Exception as e:
            chart_div = f"<p style='color:red;'>Ошибка построения графика: {e}</p>"

        inner = f"""
        <div class="block" style="min-width:0; max-width:100%;">
            <div class="block-card" style="padding: 16px; background: {self.bg_color}; border-radius: 8px; min-width:0; max-width:100%;">
                {chart_div}
            </div>
        </div>
        """
        return self.wrap_layout(inner)

    def _render_empty(self, msg: str) -> str:
        return f'''
        <div class="block">
            <div class="block-card" style="text-align:center; padding: 40px 20px; background: {self.bg_color};">
                <p style="color:#888; font-size: 13px;">📊 График: {msg}</p>
            </div>
        </div>
        '''


# ============================================================
# Контейнер (сетка)
# ============================================================

@dataclass
class ContainerBlock(Block):
    type: str = "container"
    layout: str = "row"
    gap: int = 14
    children_html: list[str] = field(default_factory=list)

    def render(self) -> str:
        css_class = "container-row" if self.layout == "row" else "container-column"
        style = f"gap: {self.gap}px;"
        inner = f'<div class="{css_class}" style="{style}">{"".join(self.children_html)}</div>'
        return self.wrap_layout(inner)


# ============================================================
# Утилиты
# ============================================================

def _escape(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )


def _extract_body(html: str) -> str:
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