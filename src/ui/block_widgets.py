"""
Виджеты блоков отчёта на холсте Конструктора.
"""

import math
import pandas as pd
from PySide6.QtWidgets import (
    QApplication, QWidget, QFrame, QVBoxLayout, QHBoxLayout,
    QLabel, QSizePolicy, QTableWidget, QTableWidgetItem,
    QHeaderView, QMenu,
)
from PySide6.QtCore import Qt, Signal, QPoint, QTimer, QRectF
from PySide6.QtGui import (
    QFocusEvent, QPainter, QColor, QPen, QBrush, QFont, QPolygonF, QPainterPath,
)

from src.ui.rich_text_editor import RichTextEditor


# Палитры для графиков
CHART_PALETTES = {
    "corporate": ["#2b7fff", "#87C800", "#ff9f1c", "#e71d36", "#6f42c1", "#20c997", "#fd7e14"],
    "emerald":   ["#003F0B", "#2bb24c", "#87C800", "#52b788", "#74c69d", "#95d5b2", "#b7e4c7"],
    "sunset":    ["#f72585", "#7209b7", "#3a0ca3", "#4361ee", "#4cc9f0", "#ff9e00", "#ff0055"],
    "pastel":    ["#60a5fa", "#34d399", "#fbbf24", "#f87171", "#a78bfa", "#f472b6", "#38bdf8"],
}


# ============================================================
# Базовый блок
# ============================================================

class BlockWidget(QFrame):
    """Базовый виджет блока. Поддерживает drag-n-drop, точный resize в % с жесткими границами
    и позиционирование на листе (left / center / right / custom offset_x)."""

    clicked = Signal(str)
    resized = Signal(str, int, int)          # block_id, width_pct, min_height_px (финал)
    live_resized = Signal(str, int, int)     # block_id, width_pct, min_height_px (в реальном времени)
    position_changed = Signal(str, str, int) # block_id, align, offset_x_pct
    delete_requested = Signal(str)
    duplicate_requested = Signal(str)
    move_up_requested = Signal(str)
    move_down_requested = Signal(str)
    edit_text_requested = Signal(str)

    content_changed = Signal(str, str)
    focus_in = Signal(str)
    focus_out = Signal(str)

    def __init__(self, block_id: str, parent=None, theme=None):
        super().__init__(parent)
        self.block_id = block_id
        self._theme = theme
        self._selected = False
        self._drop_highlight = False
        self._drag_start_pos = None
        self._dragging = False
        self._config = {}
        self._block_type: str | None = None
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._handle = None
        self._size_badge = None
        if not block_id.startswith("__section__"):
            self._handle = ResizeHandle(self)
            self._handle.hide()
            self._size_badge = QLabel(self)
            self._size_badge.setStyleSheet(
                "background: rgba(43, 127, 255, 0.92); color: white; "
                "font-size: 11px; font-weight: 700; padding: 3px 8px; "
                "border-radius: 4px;"
            )
            self._size_badge.hide()

        self._apply_style()

    def set_config(self, config: dict):
        self._config = config if config is not None else {}
        self._apply_style()

    def _apply_style(self):
        bg_color = "white"
        if isinstance(self._config, dict) and self._config.get("bg_color"):
            bg_color = self._config.get("bg_color")

        if self._drop_highlight:
            self.setStyleSheet(
                f"BlockWidget {{ background: {bg_color}; border: 3px solid #2bb24c; "
                f"border-radius: 8px; }}"
            )
        elif self._selected:
            self.setStyleSheet(
                f"BlockWidget {{ background: {bg_color}; border: 2px solid #2b7fff; "
                f"border-radius: 8px; }}"
            )
        else:
            self.setStyleSheet(
                f"BlockWidget {{ background: {bg_color}; border: 1px solid #e0e0e5; "
                f"border-radius: 8px; }}"
                f"BlockWidget:hover {{ border: 1px solid #2b7fff; }}"
            )

    def show_size_badge(self, width_pct: int, height_px: int):
        if self._size_badge is None:
            return
        self._size_badge.setText(f"Ш: {width_pct}%  ·  В: {height_px}px")
        self._size_badge.adjustSize()
        self._size_badge.move(
            max(6, self.width() - self._size_badge.width() - 22),
            max(6, self.height() - self._size_badge.height() - 22),
        )
        self._size_badge.show()
        self._size_badge.raise_()

    def hide_size_badge(self):
        if self._size_badge is not None:
            self._size_badge.hide()

    def set_selected(self, value: bool):
        if self._selected == value:
            return
        self._selected = value
        self._apply_style()
        if self._handle is None:
            return
        if value:
            self._handle.show()
            self._handle.raise_()
            self._reposition_handle()
        else:
            self._handle.hide()
            self.hide_size_badge()

    def set_drop_highlight(self, value: bool):
        if self._drop_highlight == value:
            return
        self._drop_highlight = value
        self._apply_style()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_handle()

    def _reposition_handle(self):
        if self._handle is None:
            return
        s = self._handle.width()
        self._handle.move(self.width() - s - 4, self.height() - s - 4)

    def available_canvas_width(self) -> int:
        """Возвращает жесткую максимальную ширину рабочей области холста (между полями)."""
        p = self.parentWidget()
        while p is not None:
            if hasattr(p, "available_content_width"):
                return p.available_content_width()
            p = p.parentWidget()
        parent = self.parentWidget()
        return max(200, parent.width()) if parent else 800

    # ---------- Клик / ПКМ ----------

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.position().toPoint()
            self.clicked.emit(self.block_id)
        elif event.button() == Qt.RightButton:
            self._show_context_menu(event)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton and self._is_text_block():
            self.edit_text_requested.emit(self.block_id)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def _is_text_block(self) -> bool:
        t = getattr(self, "_block_type", None)
        if t is not None:
            return t in ("paragraph", "list", "section_title")
        return self.__class__.__name__ in (
            "ParagraphWidget", "ListWidget", "SectionTitleWidget"
        )

    def _show_context_menu(self, event):
        menu = QMenu(self)

        if self._theme is not None:
            t = self._theme
            menu.setStyleSheet(f"""
                QMenu {{
                    background: {t.bg_card};
                    color: {t.text_main};
                    border: 1px solid {t.border};
                    border-radius: 6px;
                    padding: 6px 4px;
                    font-size: 12px;
                }}
                QMenu::item {{
                    padding: 6px 20px 6px 12px;
                    border-radius: 4px;
                    color: {t.text_main};
                }}
                QMenu::item:selected {{
                    background: {t.primary_hover};
                    color: {t.text_main};
                }}
                QMenu::separator {{
                    height: 1px;
                    background: {t.border};
                    margin: 4px 8px;
                }}
            """)

        act_edit = None
        if self._is_text_block():
            act_edit = menu.addAction("✏  Редактировать текст")
            menu.addSeparator()

        # Быстрое позиционирование блока на странице (лево / центр / право)
        pos_menu = menu.addMenu("🎯  Положение на странице")
        act_left = pos_menu.addAction("⬅  Прижать влево")
        act_center = pos_menu.addAction("↔  По центру страницы")
        act_right = pos_menu.addAction("➡  Прижать вправо")

        size_menu = menu.addMenu("📐  Быстрая ширина")
        act_w100 = size_menu.addAction("100% (Во всю страницу)")
        act_w75 = size_menu.addAction("75%")
        act_w50 = size_menu.addAction("50% (Половина)")
        act_w33 = size_menu.addAction("33% (Треть)")

        menu.addSeparator()
        act_del = menu.addAction("🗑  Удалить блок")
        menu.addSeparator()
        act_dupl = menu.addAction("📋  Дублировать")
        act_up = menu.addAction("↑  Вверх")
        act_down = menu.addAction("↓  Вниз")

        chosen = menu.exec(event.globalPosition().toPoint())
        if chosen is None:
            return
        if act_edit is not None and chosen == act_edit:
            self.edit_text_requested.emit(self.block_id)
        elif chosen == act_left:
            self._config["align"] = "left"
            self._config["offset_x"] = 0
            self.position_changed.emit(self.block_id, "left", 0)
        elif chosen == act_center:
            self._config["align"] = "center"
            self._config["offset_x"] = 0
            self.position_changed.emit(self.block_id, "center", 0)
        elif chosen == act_right:
            self._config["align"] = "right"
            self._config["offset_x"] = 0
            self.position_changed.emit(self.block_id, "right", 0)
        elif chosen in (act_w100, act_w75, act_w50, act_w33):
            w_map = {act_w100: 100, act_w75: 75, act_w50: 50, act_w33: 33}
            new_pct = w_map[chosen]
            self._config["width"] = new_pct
            min_h = int(self._config.get("min_height", self.height()))
            self.live_resized.emit(self.block_id, new_pct, min_h)
            self.resized.emit(self.block_id, new_pct, min_h)
        elif chosen == act_del:
            self.delete_requested.emit(self.block_id)
        elif chosen == act_dupl:
            self.duplicate_requested.emit(self.block_id)
        elif chosen == act_up:
            self.move_up_requested.emit(self.block_id)
        elif chosen == act_down:
            self.move_down_requested.emit(self.block_id)

    # ---------- Drag-n-drop ----------

    def mouseMoveEvent(self, event):
        if self._dragging:
            return super().mouseMoveEvent(event)
            
        if not (event.buttons() & Qt.LeftButton):
            return super().mouseMoveEvent(event)
        if self._drag_start_pos is None:
            return super().mouseMoveEvent(event)

        if (event.position().toPoint() - self._drag_start_pos).manhattanLength() \
                < QApplication.startDragDistance():
            return super().mouseMoveEvent(event)

        from PySide6.QtCore import QMimeData
        from PySide6.QtGui import QDrag, QPixmap

        mime = QMimeData()
        mime.setData("application/x-ea-block", self.block_id.encode("utf-8"))
        # Передаем точку захвата курсора внутри блока для точного позиционирования по X
        mime.setData("application/x-ea-hotspot-x", str(self._drag_start_pos.x()).encode("utf-8"))

        drag = QDrag(self)
        drag.setMimeData(mime)

        pixmap = QPixmap(self.size())
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setOpacity(0.75)
        painter.setBrush(QColor("#2b7fff"))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(0, 0, self.width(), self.height(), 8, 8)
        painter.end()
        drag.setPixmap(pixmap)
        drag.setHotSpot(event.position().toPoint())

        drag.exec(Qt.MoveAction)
        self._drag_start_pos = None


# ============================================================
# Resize-хендл (с жестким лимитом 100% и пересчетом в реальном времени)
# ============================================================

class ResizeHandle(QWidget):
    """Уголок изменения размера в правом нижнем углу блока."""

    SIZE = 16

    def __init__(self, parent_block: "BlockWidget"):
        super().__init__(parent_block)
        self._block = parent_block
        self._dragging = False
        self._start_mouse_x = 0
        self._start_mouse_y = 0
        self._start_width = 0
        self._start_height = 0

        self.setFixedSize(self.SIZE, self.SIZE)
        self.setCursor(Qt.SizeFDiagCursor)
        self.setStyleSheet("background: transparent;")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor("#2b7fff"))
        pen.setWidth(2)
        p.setPen(pen)
        w = self.width()
        h = self.height()
        p.drawLine(w - 10, h - 2, w - 2, h - 10)
        p.drawLine(w - 6, h - 2, w - 2, h - 6)
        p.drawLine(w - 2, h - 2, w - 2, h - 2)
        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._start_mouse_x = event.globalPosition().x()
            self._start_mouse_y = event.globalPosition().y()
            self._start_width = self._block.width()
            self._start_height = self._block.height()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not self._dragging:
            return super().mouseMoveEvent(event)

        dx = event.globalPosition().x() - self._start_mouse_x
        dy = event.globalPosition().y() - self._start_mouse_y

        avail_w = self._block.available_canvas_width()
        cfg = getattr(self._block, "_config", {}) or {}
        align = cfg.get("align", "left")
        offset_pct = int(cfg.get("offset_x", 0)) if align == "custom" else 0
        max_allowed_pct = max(15, 100 - offset_pct)
        max_px = int(avail_w * max_allowed_pct / 100)
        min_px = max(120, int(avail_w * 0.15))

        # Жесткий предел: пользователь не может растянуть блок шире 100% рабочей зоны листа
        new_w = max(min_px, min(max_px, int(self._start_width + dx)))
        new_h = max(40, int(self._start_height + dy))

        width_pct = max(15, min(max_allowed_pct, int(round(new_w / avail_w * 100))))
        if width_pct >= 99:
            width_pct = 100
            new_w = avail_w

        self._block.setFixedWidth(new_w)
        self._block.setMinimumHeight(new_h)
        self._block._reposition_handle()
        self._block.show_size_badge(width_pct, new_h)

        if getattr(self._block, "_config", None) is not None:
            self._block._config["width"] = width_pct
            self._block._config["min_height"] = new_h

        # Постоянно отправляем сигнал для мгновенного обновления цифры в инспекторе
        self._block.live_resized.emit(self._block.block_id, width_pct, new_h)
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._dragging:
            self._dragging = False
            self._block.hide_size_badge()

            avail_w = self._block.available_canvas_width()
            new_w_px = min(avail_w, self._block.width())
            new_h_px = self._block.height()

            cfg = getattr(self._block, "_config", {}) or {}
            align = cfg.get("align", "left")
            offset_pct = int(cfg.get("offset_x", 0)) if align == "custom" else 0
            max_allowed_pct = max(15, 100 - offset_pct)

            width_pct = max(15, min(max_allowed_pct, int(round(new_w_px / avail_w * 100))))
            if width_pct >= 98:
                width_pct = 100

            if getattr(self._block, "_config", None) is not None:
                self._block._config["width"] = width_pct
                self._block._config["min_height"] = new_h_px

            self._block.resized.emit(self._block.block_id, width_pct, new_h_px)
            event.accept()
        else:
            super().mouseReleaseEvent(event)


# ============================================================
# Инлайн-редактор (обёртка над RichTextEditor для холста)
# ============================================================

class _InlineEditor(QWidget):
    content_changed = Signal(str)
    focus_in = Signal()
    focus_out = Signal()

    def __init__(self, theme, parent=None, min_height: int = 40):
        super().__init__(parent)
        self.theme = theme

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._editor = RichTextEditor(theme, min_height=min_height, show_toolbar=False)
        self._editor.setStyleSheet("""
            QTextEdit {
                background: transparent;
                color: #333;
                border: none;
                padding: 0px;
                font-size: 14px;
            }
        """)
        self._editor.text_edit().installEventFilter(self)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)
        self._debounce.timeout.connect(self._emit_changed)

        self._editor.textChanged.connect(self._on_text_changed)
        lay.addWidget(self._editor)

        from PySide6.QtGui import QShortcut, QKeySequence
        from PySide6.QtCore import Qt as _Qt

        for seq in ("Ctrl+Z", "Ctrl+Shift+Z", "Ctrl+Y"):
            sc = QShortcut(QKeySequence(seq), self._editor.text_edit())
            sc.setContext(_Qt.WidgetWithChildrenShortcut)
            if seq == "Ctrl+Z":
                sc.activated.connect(self._editor.undo)
            else:
                sc.activated.connect(self._editor.redo)

        self._adjust_height()

    def eventFilter(self, obj, event):
        if obj is self._editor.text_edit():
            if event.type() == QFocusEvent.FocusIn:
                self.focus_in.emit()
            elif event.type() == QFocusEvent.FocusOut:
                self.focus_out.emit()
        return super().eventFilter(obj, event)

    def _on_text_changed(self):
        self._debounce.start()
        self._adjust_height()

    def _emit_changed(self):
        try:
            html = self._editor.to_html()
        except RuntimeError:
            return
        self.content_changed.emit(html)

    def _adjust_height(self):
        try:
            doc = self._editor.text_edit().document()
            h = int(doc.size().height()) + 8
            if h < 40:
                h = 40
        except RuntimeError:
            return
        self._editor.setFixedHeight(h)

    def set_html(self, html: str):
        self._editor.set_html(html or "")
        self._adjust_height()

    def to_html(self) -> str:
        return self._editor.to_html()

    def rich_editor(self) -> RichTextEditor:
        return self._editor


# ============================================================
# Визуальный холст отрисовки графика (живой предпросмотр всех типов)
# ============================================================

class _ChartPreviewCanvas(QWidget):
    """Отрисовывает реальный график по данным DataFrame и настройкам блока."""

    def __init__(self, config: dict, dataframe=None, parent=None):
        super().__init__(parent)
        self.config = config or {}
        self.df = dataframe
        self.setMinimumHeight(210)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def _prepare_series(self) -> tuple[list[str], list[float], str]:
        if self.df is None or len(self.df) == 0:
            return ["Янв", "Фев", "Мар", "Апр", "Май"], [42.0, 68.0, 55.0, 89.0, 74.0], "Демо-данные (загрузите Excel)"

        x_col = self.config.get("x_col", "")
        y_col = self.config.get("y_col", "")
        agg = self.config.get("agg", "sum")
        top_n = int(self.config.get("top_n", 12))
        sort_by = self.config.get("sort_by", "value_desc")
        row_start = int(self.config.get("row_start", 0))
        row_limit = int(self.config.get("row_limit", 0))

        work_df = self.df
        if row_start > 0 or row_limit > 0:
            end_idx = (row_start + row_limit) if row_limit > 0 else len(work_df)
            work_df = work_df.iloc[row_start:end_idx]

        if not x_col or x_col not in work_df.columns:
            x_col = work_df.columns[0]

        try:
            if not y_col or y_col not in work_df.columns or agg == "count":
                grouped = work_df[x_col].astype(str).value_counts()
                subtitle = f"{x_col} · Количество записей"
            else:
                temp = work_df[[x_col, y_col]].copy()
                temp[y_col] = pd.to_numeric(temp[y_col], errors="coerce")
                temp = temp.dropna(subset=[y_col])
                if len(temp) == 0:
                    grouped = work_df[x_col].astype(str).value_counts()
                    subtitle = f"{x_col} · Количество (нет чисел в {y_col})"
                else:
                    if agg == "mean":
                        grouped = temp.groupby(temp[x_col].astype(str))[y_col].mean()
                        agg_lbl = "Среднее"
                    elif agg == "max":
                        grouped = temp.groupby(temp[x_col].astype(str))[y_col].max()
                        agg_lbl = "Максимум"
                    elif agg == "min":
                        grouped = temp.groupby(temp[x_col].astype(str))[y_col].min()
                        agg_lbl = "Минимум"
                    elif agg == "median":
                        grouped = temp.groupby(temp[x_col].astype(str))[y_col].median()
                        agg_lbl = "Медиана"
                    else:
                        grouped = temp.groupby(temp[x_col].astype(str))[y_col].sum()
                        agg_lbl = "Сумма"
                    subtitle = f"{x_col} → {y_col} ({agg_lbl})"

            if sort_by == "value_desc":
                grouped = grouped.sort_values(ascending=False)
            elif sort_by == "value_asc":
                grouped = grouped.sort_values(ascending=True)
            elif sort_by == "label_asc":
                grouped = grouped.sort_index(ascending=True)

            if top_n > 0:
                grouped = grouped.head(top_n)

            labels = [str(k)[:18] for k in grouped.index]
            values = [float(v) for v in grouped.values]
            if not values:
                return ["Нет данных"], [0.0], subtitle
            return labels, values, subtitle
        except Exception as e:
            return ["Ошибка"], [0.0], str(e)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()

        bg_hex = self.config.get("bg_color", "#ffffff") or "#ffffff"
        p.setBrush(QColor(bg_hex))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(0, 0, w, h, 6, 6)

        is_dark_bg = QColor(bg_hex).lightness() < 128
        text_main = QColor("#f0f4f8" if is_dark_bg else "#1e293b")
        text_muted = QColor("#94a3b8" if is_dark_bg else "#64748b")
        grid_color = QColor("#334155" if is_dark_bg else "#e2e8f0")

        palette_name = self.config.get("palette", "corporate")
        colors = [QColor(c) for c in CHART_PALETTES.get(palette_name, CHART_PALETTES["corporate"])]

        labels, values, subtitle = self._prepare_series()
        chart_type = self.config.get("chart_type", "bar")
        title = self.config.get("title") or "График"
        show_legend = self.config.get("show_legend", True)
        legend_pos = self.config.get("legend_pos", "right")
        show_grid = self.config.get("show_grid", True)
        show_values = self.config.get("show_values", True)

        # Заголовок и подзаголовок
        p.setPen(text_main)
        f_title = QFont("Segoe UI", 11, QFont.Bold)
        p.setFont(f_title)
        p.drawText(16, 22, title)

        p.setPen(text_muted)
        f_sub = QFont("Segoe UI", 8)
        p.setFont(f_sub)
        p.drawText(16, 36, subtitle)

        # Область построения с учетом позиции легенды
        left_pad = 48
        right_pad = 135 if (show_legend and legend_pos == "right") else 20
        top_pad = 64 if (show_legend and legend_pos == "top") else 46
        bottom_pad = 54 if (show_legend and legend_pos == "bottom") else 34

        plot_rect = QRectF(left_pad, top_pad, max(60, w - left_pad - right_pad), max(50, h - top_pad - bottom_pad))

        # Сетка
        if show_grid and chart_type not in ("pie", "donut", "funnel"):
            pen_grid = QPen(grid_color, 1, Qt.DashLine)
            p.setPen(pen_grid)
            for step in range(5):
                gy = plot_rect.top() + plot_rect.height() * step / 4
                p.drawLine(int(plot_rect.left()), int(gy), int(plot_rect.right()), int(gy))

        max_v = max(values) if values and max(values) > 0 else 1.0
        min_v = min(0.0, min(values)) if values else 0.0
        span_v = (max_v - min_v) if (max_v - min_v) != 0 else 1.0

        n = len(values)
        f_small = QFont("Segoe UI", 8)
        p.setFont(f_small)

        if chart_type in ("pie", "donut"):
            total = sum(max(0.0, v) for v in values) or 1.0
            diameter = min(plot_rect.width(), plot_rect.height()) - 10
            cx = plot_rect.center().x()
            cy = plot_rect.center().y()
            pie_rect = QRectF(cx - diameter / 2, cy - diameter / 2, diameter, diameter)
            start_angle = 90 * 16
            for i, v in enumerate(values):
                span_angle = -int(round((max(0.0, v) / total) * 360 * 16))
                p.setBrush(colors[i % len(colors)])
                p.setPen(QPen(QColor(bg_hex), 2))
                p.drawPie(pie_rect, start_angle, span_angle)
                start_angle += span_angle
            if chart_type == "donut":
                hole = diameter * 0.54
                p.setBrush(QColor(bg_hex))
                p.setPen(Qt.NoPen)
                p.drawEllipse(QRectF(cx - hole / 2, cy - hole / 2, hole, hole))
                p.setPen(text_main)
                p.setFont(QFont("Segoe UI", 9, QFont.Bold))
                p.drawText(QRectF(cx - hole / 2, cy - 10, hole, 20), Qt.AlignCenter, f"Σ {total:,.0f}")

        elif chart_type == "hbar":
            row_h = plot_rect.height() / max(1, n)
            bar_h = max(6.0, row_h * 0.65)
            for i, (lbl, v) in enumerate(zip(labels, values)):
                by = plot_rect.top() + i * row_h + (row_h - bar_h) / 2
                bw = max(2.0, (max(0.0, v) / max_v) * plot_rect.width())
                p.setBrush(colors[i % len(colors)])
                p.setPen(Qt.NoPen)
                p.drawRoundedRect(QRectF(plot_rect.left(), by, bw, bar_h), 3, 3)
                p.setPen(text_muted)
                p.drawText(QRectF(4, by, left_pad - 8, bar_h), Qt.AlignRight | Qt.AlignVCenter, lbl[:8])
                if show_values:
                    p.setPen(text_main)
                    p.drawText(int(plot_rect.left() + bw + 5), int(by + bar_h - 2), f"{v:,.0f}")

        elif chart_type == "funnel":
            row_h = plot_rect.height() / max(1, n)
            bar_h = max(8.0, row_h * 0.72)
            for i, (lbl, v) in enumerate(zip(labels, values)):
                by = plot_rect.top() + i * row_h + (row_h - bar_h) / 2
                bw = max(24.0, (max(0.0, v) / max_v) * plot_rect.width())
                bx = plot_rect.center().x() - bw / 2
                p.setBrush(colors[i % len(colors)])
                p.setPen(Qt.NoPen)
                p.drawRoundedRect(QRectF(bx, by, bw, bar_h), 4, 4)
                p.setPen(QColor("#ffffff"))
                p.drawText(QRectF(bx, by, bw, bar_h), Qt.AlignCenter, f"{lbl[:10]}: {v:,.0f}")

        elif chart_type in ("line", "area", "scatter"):
            pts = []
            for i, v in enumerate(values):
                px = plot_rect.left() + (i / max(1, n - 1)) * plot_rect.width() if n > 1 else plot_rect.center().x()
                py = plot_rect.bottom() - ((v - min_v) / span_v) * plot_rect.height()
                pts.append((px, py, v, labels[i]))

            if chart_type == "area" and len(pts) >= 2:
                path = QPainterPath()
                path.moveTo(pts[0][0], plot_rect.bottom())
                for px, py, _, _ in pts:
                    path.lineTo(px, py)
                path.lineTo(pts[-1][0], plot_rect.bottom())
                path.closeSubpath()
                fill_c = QColor(colors[0])
                fill_c.setAlpha(65)
                p.fillPath(path, QBrush(fill_c))

            if chart_type in ("line", "area") and len(pts) >= 2:
                pen_line = QPen(colors[0], 2.5)
                p.setPen(pen_line)
                for i in range(len(pts) - 1):
                    p.drawLine(int(pts[i][0]), int(pts[i][1]), int(pts[i + 1][0]), int(pts[i + 1][1]))

            for i, (px, py, v, lbl) in enumerate(pts):
                p.setBrush(colors[i % len(colors)] if chart_type == "scatter" else colors[0])
                p.setPen(QPen(QColor(bg_hex), 1.5))
                r = 5 if chart_type == "scatter" else 4
                p.drawEllipse(QRectF(px - r, py - r, r * 2, r * 2))
                if show_values and n <= 12:
                    p.setPen(text_main)
                    p.drawText(int(px - 14), int(py - 8), f"{v:,.0f}")
                if i % max(1, n // 6) == 0:
                    p.setPen(text_muted)
                    p.drawText(int(px - 18), int(plot_rect.bottom() + 14), lbl[:7])

        elif chart_type == "box":
            sorted_v = sorted(values)
            q1 = sorted_v[len(sorted_v) // 4]
            med = sorted_v[len(sorted_v) // 2]
            q3 = sorted_v[(len(sorted_v) * 3) // 4]
            vmin, vmax = sorted_v[0], sorted_v[-1]

            def _y(val):
                return plot_rect.bottom() - ((val - vmin) / max(1.0, vmax - vmin)) * plot_rect.height()

            cx = plot_rect.center().x()
            bw = min(90.0, plot_rect.width() * 0.35)
            p.setPen(QPen(colors[0], 2))
            p.drawLine(int(cx), int(_y(vmin)), int(cx), int(_y(vmax)))
            p.drawLine(int(cx - bw / 3), int(_y(vmin)), int(cx + bw / 3), int(_y(vmin)))
            p.drawLine(int(cx - bw / 3), int(_y(vmax)), int(cx + bw / 3), int(_y(vmax)))
            box_c = QColor(colors[0])
            box_c.setAlpha(90)
            p.setBrush(box_c)
            p.drawRect(QRectF(cx - bw / 2, _y(q3), bw, max(4.0, _y(q1) - _y(q3))))
            p.setPen(QPen(colors[1 % len(colors)], 3))
            p.drawLine(int(cx - bw / 2), int(_y(med)), int(cx + bw / 2), int(_y(med)))

        else:
            # bar / histogram
            col_w = plot_rect.width() / max(1, n)
            bar_w = max(6.0, col_w * (0.92 if chart_type == "histogram" else 0.65))
            for i, (lbl, v) in enumerate(zip(labels, values)):
                bx = plot_rect.left() + i * col_w + (col_w - bar_w) / 2
                bh = max(2.0, ((v - min_v) / span_v) * plot_rect.height())
                by = plot_rect.bottom() - bh
                p.setBrush(colors[0] if chart_type == "histogram" else colors[i % len(colors)])
                p.setPen(Qt.NoPen)
                p.drawRoundedRect(QRectF(bx, by, bar_w, bh), 3, 3)
                if show_values and n <= 12:
                    p.setPen(text_main)
                    p.drawText(QRectF(bx - 6, by - 16, bar_w + 12, 14), Qt.AlignCenter, f"{v:,.0f}")
                if i % max(1, n // 8) == 0:
                    p.setPen(text_muted)
                    p.drawText(QRectF(bx - 8, plot_rect.bottom() + 3, bar_w + 16, 16), Qt.AlignCenter, lbl[:7])

        # Отрисовка легенды
        if show_legend:
            p.setFont(QFont("Segoe UI", 8))
            max_leg = min(6, len(labels))
            if legend_pos == "right":
                lx = int(plot_rect.right() + 14)
                ly = int(plot_rect.top() + 4)
                for i in range(max_leg):
                    p.setBrush(colors[i % len(colors)])
                    p.setPen(Qt.NoPen)
                    p.drawRoundedRect(lx, ly + i * 18, 10, 10, 2, 2)
                    p.setPen(text_muted)
                    p.drawText(lx + 15, ly + i * 18 + 9, labels[i][:12])
            elif legend_pos in ("top", "bottom"):
                ly = 44 if legend_pos == "top" else int(h - 18)
                lx = int(plot_rect.left())
                for i in range(max_leg):
                    p.setBrush(colors[i % len(colors)])
                    p.setPen(Qt.NoPen)
                    p.drawRoundedRect(lx, ly, 10, 10, 2, 2)
                    p.setPen(text_muted)
                    lbl_short = labels[i][:9]
                    p.drawText(lx + 14, ly + 9, lbl_short)
                    lx += 24 + len(lbl_short) * 6

        p.end()


class PlotlyChartWidget(BlockWidget):
    """Интерактивный блок графика на холсте с живым рендерингом и настройками."""

    def __init__(self, block_id, config, dataframe=None, parent=None, theme=None):
        super().__init__(block_id, parent, theme)
        self.setMinimumHeight(int(config.get("min_height", 240)) or 240)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(0)

        self._canvas = _ChartPreviewCanvas(config, dataframe, self)
        layout.addWidget(self._canvas)


# ============================================================
# Конкретные блоки
# ============================================================

class SectionTitleWidget(BlockWidget):
    def __init__(self, block_id, config, dataframe=None, parent=None, theme=None):
        super().__init__(block_id, parent, theme)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 14, 24, 12)
        layout.setSpacing(8)

        title = config.get("title", "") or "(раздел без названия)"

        lbl = QLabel()
        lbl.setTextFormat(Qt.RichText)
        if config.get("raw_html"):
            lbl.setText(title)
        else:
            lbl.setText(_widget_esc(title))
        lbl.setWordWrap(True)
        lbl.setStyleSheet(
            "color:#003F0B; font-size:22px; font-weight:700; background:transparent;"
        )
        layout.addWidget(lbl)

        line = QFrame()
        line.setFixedHeight(2)
        line.setStyleSheet("background:#87C800; border:none;")
        layout.addWidget(line)


class ParagraphWidget(BlockWidget):
    def __init__(self, block_id, config, dataframe=None, parent=None, theme=None):
        super().__init__(block_id, parent, theme)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 18)

        self._inline = _InlineEditor(theme, self)

        text = config.get("text", "") or ""
        if config.get("raw_html"):
            html = _extract_body_local(text)
        else:
            html = _widget_esc(text).replace("\n", "<br>")
        self._inline.set_html(html)

        self._inline.content_changed.connect(
            lambda h: self.content_changed.emit(self.block_id, h)
        )
        self._inline.focus_in.connect(
            lambda: self.focus_in.emit(self.block_id)
        )
        self._inline.focus_out.connect(
            lambda: self.focus_out.emit(self.block_id)
        )

        layout.addWidget(self._inline)

    def inline_editor(self) -> RichTextEditor | None:
        return self._inline.rich_editor() if self._inline else None


class ListWidget(BlockWidget):
    def __init__(self, block_id, config, dataframe=None, parent=None, theme=None):
        super().__init__(block_id, parent, theme)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(4)

        self._inline = _InlineEditor(theme, self, min_height=60)

        html = config.get("html") or ""
        if not (config.get("raw_html") and html.strip()):
            items = config.get("items") or ["(пустой список)"]
            li = "".join(f"<li>{_widget_esc(str(x))}</li>" for x in items)
            html = f"<ul style='margin:0; padding-left:20px;'>{li}</ul>"
        else:
            html = _extract_body_local(html)

        self._inline.set_html(html)

        self._inline.content_changed.connect(
            lambda h: self.content_changed.emit(self.block_id, h)
        )
        self._inline.focus_in.connect(
            lambda: self.focus_in.emit(self.block_id)
        )
        self._inline.focus_out.connect(
            lambda: self.focus_out.emit(self.block_id)
        )

        layout.addWidget(self._inline)

    def inline_editor(self) -> RichTextEditor | None:
        return self._inline.rich_editor() if self._inline else None


class DividerWidget(BlockWidget):
    def __init__(self, block_id, config, dataframe=None, parent=None, theme=None):
        super().__init__(block_id, parent, theme)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 8)
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background:#d0d0d5;")
        layout.addWidget(line)
        self.setFixedHeight(18)


class KpiRowWidget(BlockWidget):
    def __init__(self, block_id, config, dataframe=None, parent=None, theme=None):
        super().__init__(block_id, parent, theme)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(110)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(14)
        outer.setAlignment(Qt.AlignTop)

        cards = config.get("cards") or [{"label": "KPI", "value": "—"}]
        for c in cards:
            card = QFrame()
            card.setStyleSheet(
                "QFrame { background:#f8f8fb; border:1px solid #e0e0e5; border-radius:8px; }"
            )
            card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            card.setMinimumWidth(110)
            card.setFixedHeight(78)

            cl = QVBoxLayout(card)
            cl.setContentsMargins(14, 10, 14, 10)
            cl.setSpacing(4)
            cl.setAlignment(Qt.AlignTop)

            val = QLabel(str(c.get("value", "")))
            color = "#2bb24c" if c.get("accent") else "#111"
            val.setStyleSheet(
                f"color:{color}; font-size:22px; font-weight:700; background:transparent;"
            )
            lbl = QLabel(str(c.get("label", "")))
            lbl.setStyleSheet("color:#666; font-size:12px; background:transparent;")

            cl.addWidget(val)
            cl.addWidget(lbl)
            outer.addWidget(card, 1)


class DataTableWidget(BlockWidget):
    def __init__(self, block_id, config, dataframe=None, parent=None, theme=None):
        super().__init__(block_id, parent, theme)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)

        max_rows = int(config.get("max_rows", 20))
        cols_cfg = config.get("visible_columns")

        if dataframe is not None and len(dataframe) > 0:
            if cols_cfg is None:
                shown = list(dataframe.columns)[:8]
            else:
                shown = [c for c in cols_cfg if c in dataframe.columns]
            info = f"Таблица  ·  {len(shown)} колонок  ·  до {max_rows} строк"
        else:
            shown = []
            info = "Таблица  ·  нет данных (загрузите Excel)"

        info_lbl = QLabel(info)
        info_lbl.setStyleSheet("color:#888; font-size:12px; background:transparent;")
        layout.addWidget(info_lbl)

        if shown and dataframe is not None and len(dataframe) > 0:
            preview_rows = min(5, max_rows if max_rows > 0 else 5, len(dataframe))
            mini = dataframe[shown].head(preview_rows)
            table = QTableWidget(len(mini), len(shown))
            table.setHorizontalHeaderLabels([str(c) for c in shown])
            for i in range(len(mini)):
                for j, col in enumerate(shown):
                    val = mini.iloc[i][col]
                    text = "—" if (val is None or (isinstance(val, float) and val != val)) else str(val)
                    table.setItem(i, j, QTableWidgetItem(text))
            table.verticalHeader().setVisible(False)
            table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            table.setEditTriggers(QTableWidget.NoEditTriggers)
            table.setSelectionMode(QTableWidget.NoSelection)
            table.setFocusPolicy(Qt.NoFocus)
            table.setStyleSheet("""
                QTableWidget { background:white; border:1px solid #e0e0e5;
                               border-radius:4px; gridline-color:#eee; font-size:12px; }
                QHeaderView::section { background:#f5f5f8; border:none;
                    border-bottom:1px solid #e0e0e5; padding:6px;
                    font-size:11px; font-weight:600; color:#555; }
            """)
            table.setFixedHeight(min(220, 34 + 24 * len(mini)))
            layout.addWidget(table)
        else:
            empty = QLabel("Нет данных")
            empty.setStyleSheet("color:#aaa; font-size:13px; padding:20px; background:transparent;")
            empty.setAlignment(Qt.AlignCenter)
            layout.addWidget(empty)


class ContainerWidget(BlockWidget):
    """Контейнер с вложенными блоками: каждый график имеет свои четкие границы и переносится вниз при нехватке места."""

    def __init__(self, block_id, config, dataframe=None, parent=None, theme=None):
        super().__init__(block_id, parent, theme)

        layout_kind = config.get("layout", "row")
        gap = int(config.get("gap", 14))

        box = QHBoxLayout(self)
        box.setContentsMargins(12, 12, 12, 12)
        box.setSpacing(gap)

        self.setStyleSheet(
            "ContainerWidget { background: #f8fafc; border: 2px dashed #94a3b8; "
            "border-radius: 8px; }"
        )

        children = config.get("children", [])
        n_children = max(1, len(children))

        for child in children:
            if hasattr(child, "id"):
                cid = child.id
                ctype = child.type
                ccfg = child.config
            else:
                cid = child.get("id", "")
                ctype = child.get("type", "paragraph")
                ccfg = child.get("config", {})

            child_widget = make_block_widget(ctype, cid, ccfg, dataframe, self, theme)
            child_widget.clicked.connect(self._on_child_clicked)
            
            # Если ряд, даем каждому блоку независимую ширину с учетом отступов, но не даем «слепляться»
            if layout_kind == "row":
                child_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
                box.addWidget(child_widget, 1)
            else:
                child_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                box.addWidget(child_widget)

    def _on_child_clicked(self, child_id: str):
        self.clicked.emit(child_id)


# ============================================================
# Хелперы и Фабрика
# ============================================================

def _widget_esc(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )


def _extract_body_local(html: str) -> str:
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


def make_block_widget(block_type, block_id, config, dataframe=None, parent=None, theme=None):
    config = config if config is not None else {}
    if block_type == "section_title":
        w = SectionTitleWidget(block_id, config, dataframe, parent, theme)
    elif block_type == "paragraph":
        w = ParagraphWidget(block_id, config, dataframe, parent, theme)
    elif block_type == "list":
        w = ListWidget(block_id, config, dataframe, parent, theme)
    elif block_type == "divider":
        w = DividerWidget(block_id, config, dataframe, parent, theme)
    elif block_type == "kpi_row":
        w = KpiRowWidget(block_id, config, dataframe, parent, theme)
    elif block_type == "data_table":
        w = DataTableWidget(block_id, config, dataframe, parent, theme)
    elif block_type == "plotly_chart":
        w = PlotlyChartWidget(block_id, config, dataframe, parent, theme)
    elif block_type == "container":
        w = ContainerWidget(block_id, config, dataframe, parent, theme)
    else:
        w = ParagraphWidget(block_id, {"text": f"[{block_type}]"}, dataframe, parent, theme)

    w._block_type = block_type
    w.set_config(config)
    return w