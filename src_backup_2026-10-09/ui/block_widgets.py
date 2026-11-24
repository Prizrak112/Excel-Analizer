"""
Виджеты блоков отчёта на холсте Конструктора.
"""

from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy,
    QTableWidget, QTableWidgetItem, QHeaderView, QMenu,
)
from PySide6.QtCore import Qt, Signal, QPoint, QTimer
from PySide6.QtGui import QFocusEvent

from src.ui.rich_text_editor import RichTextEditor


# ============================================================
# Базовый блок
# ============================================================

class BlockWidget(QFrame):
    """Базовый виджет блока. Клик → сигнал. Выделение → синяя рамка.
    ПКМ → меню действий. Поддерживает drag-n-drop и resize."""

    clicked = Signal(str)
    resized = Signal(str, int, int)          # block_id, width_pct, min_height_px
    delete_requested = Signal(str)           # ПКМ → Удалить
    duplicate_requested = Signal(str)        # ПКМ → Дублировать
    move_up_requested = Signal(str)          # ПКМ → Вверх
    move_down_requested = Signal(str)        # ПКМ → Вниз

    # ★ Двойной клик / ПКМ «Редактировать текст» — только для текстовых блоков
    edit_text_requested = Signal(str)        # block_id

    # ★ Инлайн-редактирование на холсте (для текстовых блоков)
    content_changed = Signal(str, str)       # block_id, html
    focus_in = Signal(str)                   # block_id
    focus_out = Signal(str)                  # block_id

    def __init__(self, block_id: str, parent=None, theme=None):
        super().__init__(parent)
        self.block_id = block_id
        self._theme = theme          # ★ тема для меню
        self._selected = False
        self._drop_highlight = False
        self._drag_start_pos = None
        self._config = {}
        # ★ Тип блока будет установлен фабрикой make_block_widget.
        # Используется для определения текстовых блоков (двойной клик).
        self._block_type: str | None = None
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # Resize-хендл — только для блоков, не для section_title
        self._handle = None
        if not block_id.startswith("__section__"):
            self._handle = ResizeHandle(self)
            self._handle.hide()

        self._apply_style()

    def set_config(self, config: dict):
        self._config = config or {}

    def _apply_style(self):
        if self._drop_highlight:
            self.setStyleSheet(
                "BlockWidget { background: white; border: 3px solid #2bb24c; "
                "border-radius: 8px; }"
            )
        elif self._selected:
            self.setStyleSheet(
                "BlockWidget { background: white; border: 2px solid #2b7fff; "
                "border-radius: 8px; }"
            )
        else:
            self.setStyleSheet(
                "BlockWidget { background: white; border: 1px solid #e0e0e5; "
                "border-radius: 8px; }"
                "BlockWidget:hover { border: 1px solid #b8b8c0; }"
            )

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
        """Двойной клик по блоку → редактировать текст (для текстовых типов)."""
        if event.button() == Qt.LeftButton and self._is_text_block():
            self.edit_text_requested.emit(self.block_id)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def _is_text_block(self) -> bool:
        """Текстовые блоки — те, что имеют редактируемое содержимое."""
        t = getattr(self, "_block_type", None)
        if t is not None:
            return t in ("paragraph", "list", "section_title")
        # Fallback по имени класса (на случай, если _block_type не задан)
        return self.__class__.__name__ in (
            "ParagraphWidget", "ListWidget", "SectionTitleWidget"
        )

    def _show_context_menu(self, event):
        """ПКМ → меню действий над блоком (в стиле темы)."""
        menu = QMenu(self)

        # ★ Стиль меню — под тему приложения
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

        # ★ Для текстовых блоков — пункт «Редактировать текст» сверху
        act_edit = None
        if self._is_text_block():
            act_edit = menu.addAction("✏  Редактировать текст")
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
        if not (event.buttons() & Qt.LeftButton):
            return super().mouseMoveEvent(event)
        if self._drag_start_pos is None:
            return super().mouseMoveEvent(event)

        if (event.position().toPoint() - self._drag_start_pos).manhattanLength() \
                < QApplication.startDragDistance():
            return super().mouseMoveEvent(event)

        from PySide6.QtCore import QMimeData
        from PySide6.QtGui import QDrag, QPixmap, QPainter, QColor

        mime = QMimeData()
        mime.setData("application/x-ea-block", self.block_id.encode("utf-8"))

        drag = QDrag(self)
        drag.setMimeData(mime)

        pixmap = QPixmap(self.size())
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setOpacity(0.7)
        painter.setBrush(QColor("#2b7fff"))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(0, 0, self.width(), self.height(), 8, 8)
        painter.end()
        drag.setPixmap(pixmap)
        drag.setHotSpot(event.position().toPoint())

        drag.exec(Qt.MoveAction)
        self._drag_start_pos = None


# ============================================================
# Resize-хендл
# ============================================================

class ResizeHandle(QWidget):
    """Квадратик в правом нижнем углу блока."""

    SIZE = 14

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
        from PySide6.QtGui import QPainter, QColor, QPen
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor("#2b7fff"))
        pen.setWidth(2)
        p.setPen(pen)
        w = self.width()
        h = self.height()
        p.drawLine(w - 8, h - 2, w - 2, h - 8)
        p.drawLine(w - 4, h - 2, w - 2, h - 4)
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

        new_w = max(80, int(self._start_width + dx))
        new_h = max(30, int(self._start_height + dy))

        self._block.setFixedWidth(new_w)
        self._block.setMinimumHeight(new_h)
        self._block._reposition_handle()
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._dragging:
            self._dragging = False

            new_w_px = self._block.width()
            new_h_px = self._block.height()

            parent = self._block.parent()
            parent_w = parent.width() if parent else 1000
            width_pct = max(10, min(100, int(round(new_w_px / parent_w * 100))))

            presets = [25, 33, 50, 66, 75, 100]
            width_pct = min(presets, key=lambda p: abs(p - width_pct))

            # ★ Пишем в config — чтобы после rebuild размер сохранился и попал в HTML
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
    """
    Обёртка над RichTextEditor(show_toolbar=False).

    Отдаёт наружу:
      • content_changed(text) — при вводе текста (debounce 300 мс);
      • focus_in() / focus_out() — при получении/потере фокуса.

    Плюс автовысота: QTextEdit растягивается по содержимому.
    """

    content_changed = Signal(str)     # html
    focus_in = Signal()
    focus_out = Signal()

    def __init__(self, theme, parent=None, min_height: int = 40):
        super().__init__(parent)
        self.theme = theme

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ★ Редактор БЕЗ тулбара
        self._editor = RichTextEditor(theme, min_height=min_height,
                                       show_toolbar=False)

        # Красим QTextEdit «прозрачно», чтобы выглядел как текст
        self._editor.setStyleSheet(f"""
            QTextEdit {{
                background: transparent;
                color: #333;
                border: none;
                padding: 0px;
                font-size: 14px;
            }}
        """)

        # ★ Ловим фокус через фильтр событий на внутреннем QTextEdit
        self._editor.text_edit().installEventFilter(self)

        # ★ Debounce: не эмитим content_changed на каждый keystroke
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)
        self._debounce.timeout.connect(self._emit_changed)

        self._editor.textChanged.connect(self._on_text_changed)

        lay.addWidget(self._editor)

        # ★ Локальные горячие клавиши для Undo/Redo.
        # Они приоритетнее глобальных shortcut окна (Ctrl+Z в «Правка → Отменить»),
        # поэтому работают именно в этом редакторе.
        from PySide6.QtGui import QShortcut, QKeySequence
        from PySide6.QtCore import Qt as _Qt

        for seq in ("Ctrl+Z", "Ctrl+Shift+Z", "Ctrl+Y"):
            sc = QShortcut(QKeySequence(seq), self._editor.text_edit())
            sc.setContext(_Qt.WidgetWithChildrenShortcut)
            if seq == "Ctrl+Z":
                sc.activated.connect(self._editor.undo)
            else:
                sc.activated.connect(self._editor.redo)

        # Автовысота
        self._adjust_height()

    # ---------- Фокус ----------

    def eventFilter(self, obj, event):
        if obj is self._editor.text_edit():
            if event.type() == QFocusEvent.FocusIn:
                self.focus_in.emit()
            elif event.type() == QFocusEvent.FocusOut:
                self.focus_out.emit()
        return super().eventFilter(obj, event)

    # ---------- Текст ----------

    def _on_text_changed(self):
        # Отложенная эмиссия + автовысота
        self._debounce.start()
        self._adjust_height()

    def _emit_changed(self):
        try:
            html = self._editor.to_html()
        except RuntimeError:
            return
        self.content_changed.emit(html)

    def _adjust_height(self):
        """Подгоняет высоту под содержимое."""
        try:
            doc = self._editor.text_edit().document()
            h = int(doc.size().height()) + 8
            if h < 40:
                h = 40
        except RuntimeError:
            return
        self._editor.setFixedHeight(h)

    # ---------- Публичный API ----------

    def set_html(self, html: str):
        self._editor.set_html(html or "")
        self._adjust_height()

    def to_html(self) -> str:
        return self._editor.to_html()

    def rich_editor(self) -> RichTextEditor:
        """Доступ к RichTextEditor (для внешнего тулбара)."""
        return self._editor


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
        # если пришёл rich-text — используем как есть, иначе экранируем
        if config.get("raw_html"):
            lbl.setText(title)
        else:
            lbl.setText(_widget_esc(title))
        lbl.setWordWrap(True)
        lbl.setStyleSheet(
            "color:#003F0B; font-size:22px; font-weight:700; background:transparent;"
        )
        layout.addWidget(lbl)

        # зелёная линия под заголовком — как в эталонном отчёте
        line = QFrame()
        line.setFixedHeight(2)
        line.setStyleSheet("background:#87C800; border:none;")
        layout.addWidget(line)


class ParagraphWidget(BlockWidget):
    def __init__(self, block_id, config, dataframe=None, parent=None, theme=None):
        super().__init__(block_id, parent, theme)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 18)

        # ★ Редактируемый текст
        self._inline = _InlineEditor(theme, self)

        # Определяем HTML для подстановки
        text = config.get("text", "") or ""
        if config.get("raw_html"):
            html = _extract_body_local(text)
        else:
            html = _widget_esc(text).replace("\n", "<br>")
        self._inline.set_html(html)

        # ★ Проброс сигналов наружу (через методы блока)
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
        """Доступ к RichTextEditor (для внешнего тулбара)."""
        return self._inline.rich_editor() if self._inline else None


class ListWidget(BlockWidget):
    def __init__(self, block_id, config, dataframe=None, parent=None, theme=None):
        super().__init__(block_id, parent, theme)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(4)

        # ★ Редактируемый список
        self._inline = _InlineEditor(theme, self, min_height=60)

        html = config.get("html") or ""
        if not (config.get("raw_html") and html.strip()):
            # legacy: собираем <ul> из items
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
        """Доступ к RichTextEditor (для внешнего тулбара)."""
        return self._inline.rich_editor() if self._inline else None


class DividerWidget(BlockWidget):
    def __init__(self, block_id, config, dataframe=None, parent=None, theme=None):
        super().__init__(block_id, parent, theme)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)   # ★ фикс
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 8)
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background:#d0d0d5;")
        layout.addWidget(line)
        self.setFixedHeight(18)   # ★ в самом конце


class KpiRowWidget(BlockWidget):
    def __init__(self, block_id, config, dataframe=None, parent=None, theme=None):
        super().__init__(block_id, parent, theme)

        # ★ Весь KPI-ряд — фиксированной высоты (компактный)
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
            # ★ Карточка — растягивается по ширине, фикс по высоте
            card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            card.setMinimumWidth(120)
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
            preview_rows = min(5, max_rows, len(dataframe))
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
    """Контейнер с вложенными блоками (row или column)."""

    def __init__(self, block_id, config, dataframe=None, parent=None, theme=None):
        super().__init__(block_id, parent, theme)

        layout_kind = config.get("layout", "row")
        gap = int(config.get("gap", 14))

        if layout_kind == "row":
            box = QHBoxLayout(self)
        else:
            box = QVBoxLayout(self)
        box.setContentsMargins(10, 10, 10, 10)
        box.setSpacing(gap)

        self.setStyleSheet(
            "ContainerWidget { background: #f5f7fa; border: 2px dashed #b8c6d6; "
            "border-radius: 8px; }"
        )

        for child in config.get("children", []):
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
            box.addWidget(child_widget)

    def _on_child_clicked(self, child_id: str):
        self.clicked.emit(child_id)


# ============================================================
# Фабрика
# ============================================================
# ============================================================
# Хелперы для rich-text на холсте
# ============================================================

def _widget_esc(text: str) -> str:
    """Экранирование для вставки в QLabel с RichText."""
    if not isinstance(text, str):
        text = str(text)
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )


def _extract_body_local(html: str) -> str:
    """Достаёт содержимое <body>…</body> из Qt-HTML (локальная копия)."""
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
    config = config or {}
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
    elif block_type == "container":
        w = ContainerWidget(block_id, config, dataframe, parent, theme)
    else:
        w = ParagraphWidget(block_id, {"text": f"[{block_type}]"}, dataframe, parent, theme)

    # ★ Запомним тип — он нужен для двойного клика и ПКМ-меню
    w._block_type = block_type
    w.set_config(config)
    return w