"""
Rich-text редактор в стиле Excel (тёмная тема приложения).

Использование:
    # Редактор С тулбаром (для диалога):
    editor = RichTextEditor(theme)
    editor.set_html("<p>Привет, <b>мир</b>!</p>")
    html = editor.to_html()

    # Редактор БЕЗ тулбара (для холста — управление внешним toolbar):
    editor = RichTextEditor(theme, show_toolbar=False)

Параметр show_toolbar:
    True  — обычный виджет с панелью инструментов (диалог).
    False — только QTextEdit, без панели (холст).
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QToolButton, QTextEdit,
    QFrame, QColorDialog, QSizePolicy, QMenu, QComboBox,
)
from PySide6.QtGui import (
    QTextCharFormat, QTextCursor, QTextListFormat,
    QTextBlockFormat, QAction, QKeySequence, QIcon, QPixmap, QPainter,
    QColor, QFont, QPen, QBrush, QPainterPath, QFontMetrics,
)
from PySide6.QtCore import Qt, Signal, QSize, QRect, QPoint


# ============================================================
# Палитра цветов
# ============================================================

_PALETTE = [
    "#000000", "#444444", "#666666", "#999999", "#cccccc", "#ffffff",
    "#e74c3c", "#e67e22", "#f1c40f", "#2bb24c", "#27ae60", "#16a085",
    "#3498db", "#2980b9", "#9b59b6", "#8e44ad", "#34495e", "#7f8c8d",
    "#003F0B", "#87C800", "#195532", "#c0392b", "#d35400", "#c39bd3",
]

_FONT_FAMILIES = [
    "Arial", "Calibri", "Times New Roman", "Courier New",
    "Verdana", "Tahoma", "Georgia", "Segoe UI",
]

_FONT_SIZES = [8, 9, 10, 11, 12, 14, 16, 18, 20, 24, 28, 32, 36, 48]


# ============================================================
# Генерация иконок через QPainter
# ============================================================

def _make_text_icon(text: str, bold=False, italic=False, underline=False,
                    color: str = "#e6e6e6", size: int = 20) -> QIcon:
    """Иконка с одной буквой (Ж / К / Ч) в нужном стиле."""
    pm = QPixmap(28, 26)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)

    f = QFont("Arial", size)
    f.setBold(bold)
    f.setItalic(italic)
    f.setUnderline(underline)
    p.setFont(f)
    p.setPen(QColor(color))

    rect = QRect(0, 0, 28, 26)
    p.drawText(rect, Qt.AlignCenter, text)
    p.end()
    return QIcon(pm)


def _make_align_icon(kind: str, color: str = "#e6e6e6") -> QIcon:
    """
    Иконка выравнивания: 4 горизонтальные линии разной длины.

    kind: 'left' | 'center' | 'right' | 'justify'
    """
    pm = QPixmap(28, 26)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor(color)))

    x0, x1 = 3, 25
    line_h = 3
    gap = 2
    total = 4 * line_h + 3 * gap
    y0 = (26 - total) // 2

    if kind == "left":
        widths = [22, 14, 20, 12]
        xs = [x0] * 4
    elif kind == "center":
        widths = [22, 14, 20, 12]
        xs = [x0 + (22 - w) // 2 for w in widths]
    elif kind == "right":
        widths = [22, 14, 20, 12]
        xs = [x1 - w for w in widths]
    else:  # justify
        widths = [22, 22, 22, 22]
        xs = [x0] * 4

    for i, (w, x) in enumerate(zip(widths, xs)):
        y = y0 + i * (line_h + gap)
        p.drawRect(x, y, w, line_h)

    p.end()
    return QIcon(pm)


def _make_list_icon(ordered: bool, color: str = "#e6e6e6") -> QIcon:
    """Иконка списка: • + 3 линии (маркированный) или 1. + 3 линии."""
    pm = QPixmap(28, 26)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)

    line_color = QColor(color)
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(line_color))

    line_h = 2
    gap = 3
    total = 4 * line_h + 3 * gap
    y0 = (26 - total) // 2

    if ordered:
        f = QFont("Arial", 7)
        p.setFont(f)
        p.setPen(line_color)
        for i in range(4):
            y = y0 + i * (line_h + gap)
            p.drawText(QRect(2, y - 4, 8, 10), Qt.AlignLeft | Qt.AlignVCenter, "1.")
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(line_color))
    else:
        for i in range(4):
            y = y0 + i * (line_h + gap)
            p.drawEllipse(QPoint(5, y + line_h // 2), 2, 2)

    for i in range(4):
        y = y0 + i * (line_h + gap)
        p.drawRect(11, y, 14, line_h)

    p.end()
    return QIcon(pm)


def _make_color_icon(letter: str, color_hex: str, color_text: str = "#e6e6e6") -> QIcon:
    """Иконка «A» или «маркер» с цветной линией под буквой/значком."""
    pm = QPixmap(28, 26)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)

    f = QFont("Arial", 13)
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor(color_text))

    if letter == "A":
        p.drawText(QRect(0, -1, 28, 22), Qt.AlignCenter, "A")
    else:
        p.drawText(QRect(0, -3, 28, 22), Qt.AlignCenter, "✎")

    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor(color_hex)))
    p.drawRect(5, 22, 18, 3)

    p.end()
    return QIcon(pm)


def _make_clear_icon(color: str = "#e6e6e6") -> QIcon:
    """Иконка «✕» (очистить форматирование)."""
    pm = QPixmap(28, 26)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(color), 2))
    p.drawLine(8, 8, 20, 18)
    p.drawLine(20, 8, 8, 18)
    p.end()
    return QIcon(pm)


def _make_undo_icon(redo: bool = False, color: str = "#e6e6e6") -> QIcon:
    """Иконка отмены / повтора — изогнутая стрелка."""
    pm = QPixmap(28, 26)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color), 2)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)

    path = QPainterPath()
    if not redo:
        path.moveTo(9, 20)
        path.arcTo(QRect(6, 6, 16, 16), 180, -240)
        p.drawPath(path)
        p.drawLine(9, 20, 13, 17)
        p.drawLine(9, 20, 12, 22)
    else:
        path.moveTo(19, 20)
        path.arcTo(QRect(6, 6, 16, 16), 0, 240)
        p.drawPath(path)
        p.drawLine(19, 20, 15, 17)
        p.drawLine(19, 20, 16, 22)

    p.end()
    return QIcon(pm)


def _make_arrow_down(color: str = "#8a8d94") -> QIcon:
    """Маленькая стрелка ▾ в правом нижнем углу иконки."""
    pm = QPixmap(8, 8)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor(color)))
    p.drawPolygon(QPoint(0, 2), QPoint(8, 2), QPoint(4, 7))
    p.end()
    return QIcon(pm)


# ============================================================
# Сам виджет
# ============================================================

class RichTextEditor(QWidget):
    """Редактор с опциональным тулбаром. Отдаёт и принимает HTML."""

    textChanged = Signal()

    # ★ Кэш иконок: строим один раз, потом переиспользуем.
    _ICON_CACHE: dict = {}

    def __init__(self, theme, parent=None, min_height: int = 160,
                 show_toolbar: bool = True):
        """
        show_toolbar=True  — обычный редактор с тулбаром (диалог).
        show_toolbar=False — только QTextEdit без тулбара (холст).
        """
        super().__init__(parent)
        self.theme = theme
        self._show_toolbar = show_toolbar

        # Флаг «редактор полностью готов».
        self._ready = False

        # Последние использованные цвета (для иконки «A» и «маркер»)
        self._last_text_color = "#e6e6e6"
        self._last_bg_color = "#f1c40f"

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        # ── Редактор ── (создаём ПЕРВЫМ, тулбар к нему цепляется)
        self._edit = QTextEdit()
        self._edit.setAcceptRichText(True)
        self._edit.setMinimumHeight(min_height)
        self._edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # ── Тулбар ── (опциональный, по флагу show_toolbar)
        if show_toolbar:
            self._build_toolbar()

        # Редактор добавляется в layout всегда
        outer.addWidget(self._edit, 1)

        self._apply_styles()

        # ── Сигналы ──
        self._edit.textChanged.connect(self.textChanged.emit)

        # ★ Автосинхронизация тулбара ОТКЛЮЧЕНА.
        # В PySide6 6.11.x любой вызов из currentCharFormatChanged /
        # cursorPositionChanged роняет приложение с access violation.
        self._sync_scheduled = False

        # ── Контекстное меню (ПКМ) ──
        self._edit.setContextMenuPolicy(Qt.CustomContextMenu)
        self._edit.customContextMenuRequested.connect(self._show_context_menu)

        # ── Всё создано ──
        self._ready = True

    # ---------- Публичный API ----------

    def to_html(self) -> str:
        return self._edit.toHtml()

    def set_html(self, html: str):
        self._edit.blockSignals(True)
        self._edit.setHtml(html or "")
        self._edit.blockSignals(False)

    def to_plain(self) -> str:
        return self._edit.toPlainText()

    def set_plain(self, text: str):
        self._edit.blockSignals(True)
        self._edit.setPlainText(text or "")
        self._edit.blockSignals(False)

    def focus(self):
        self._edit.setFocus()

    def text_edit(self) -> QTextEdit:
        """Доступ к внутреннему QTextEdit (для внешнего тулбара)."""
        return self._edit

    # ---------- Публичные обёртки для внешнего тулбара ----------
    # Внутренние методы с подчёркиванием остаются, но внешний тулбар
    # (RichTextToolbar) вызывает именно эти обёртки.

    def toggle_bold(self):
        self._toggle_bold()

    def toggle_italic(self):
        self._toggle_italic()

    def toggle_underline(self):
        self._toggle_underline()

    def toggle_strike(self):
        self._toggle_strike()

    def apply_font_family(self, family: str):
        self._apply_font_family(family)

    def apply_font_size(self, size_pt: int):
        self._apply_font_size(size_pt)

    def set_align(self, kind: str):
        self._set_align(kind)

    def make_list(self, ordered: bool):
        self._make_list(ordered)

    def remove_list(self):
        self._remove_list()

    def apply_color(self, color_hex: str):
        self._apply_color(color_hex)

    def apply_bg_color(self, color_hex: str):
        self._apply_bg_color(color_hex)

    def clear_format(self):
        self._clear_format()

    def undo(self):
        self._edit.undo()

    def redo(self):
        self._edit.redo()

    def pick_color_text(self) -> str | None:
        """Открыть палитру для выбора цвета текста. Возвращает hex или None."""
        return self._pick_color_dialog(self._last_text_color)

    def pick_color_bg(self) -> str | None:
        """Открыть палитру для выбора цвета фона. Возвращает hex или None."""
        return self._pick_color_dialog(self._last_bg_color)

    # ---------- Построение тулбара (опционально) ----------

    def _build_toolbar(self):
        """Создаёт панель форматирования и добавляет её в layout."""
        outer = self.layout()

        self._toolbar = QFrame()
        self._toolbar.setObjectName("RichToolbar")
        tb = QHBoxLayout(self._toolbar)
        tb.setContentsMargins(4, 4, 4, 4)
        tb.setSpacing(2)

        # Группа 1: Шрифт + Размер
        self._font_combo = QComboBox()
        self._font_combo.addItems(_FONT_FAMILIES)
        self._font_combo.setFixedWidth(110)
        self._font_combo.setFixedHeight(24)
        self._font_combo.currentTextChanged.connect(self._apply_font_family)
        tb.addWidget(self._font_combo)

        self._size_combo = QComboBox()
        self._size_combo.addItems([str(s) for s in _FONT_SIZES])
        self._size_combo.setFixedWidth(52)
        self._size_combo.setFixedHeight(24)
        self._size_combo.currentTextChanged.connect(self._on_size_changed)
        tb.addWidget(self._size_combo)

        tb.addWidget(self._sep())

        # Группа 2: Ж / К / Ч
        self._btn_b = self._tool_button_icon(
            _make_text_icon("Ж", bold=True),
            "Жирный (Ctrl+B)",
            self._toggle_bold,
        )
        self._btn_i = self._tool_button_icon(
            _make_text_icon("К", italic=True),
            "Курсив (Ctrl+I)",
            self._toggle_italic,
        )
        self._btn_u = self._tool_button_icon(
            _make_text_icon("Ч", underline=True),
            "Подчёркнутый (Ctrl+U)",
            self._toggle_underline,
        )
        tb.addWidget(self._btn_b)
        tb.addWidget(self._btn_i)
        tb.addWidget(self._btn_u)

        tb.addWidget(self._sep())

        # Группа 3: Выравнивание
        self._btn_align = QToolButton()
        self._btn_align.setToolTip("Выравнивание")
        self._btn_align.setPopupMode(QToolButton.InstantPopup)
        self._btn_align.setAutoRaise(True)
        self._btn_align.setFixedSize(34, 26)
        self._btn_align.setCursor(Qt.PointingHandCursor)
        self._btn_align.setIconSize(QSize(26, 24))
        self._align_menu = self._build_align_menu()
        self._btn_align.setMenu(self._align_menu)
        self._btn_align.setIcon(_make_align_icon("left"))
        tb.addWidget(self._btn_align)

        # Группа 4: Список
        self._btn_list = QToolButton()
        self._btn_list.setToolTip("Список")
        self._btn_list.setPopupMode(QToolButton.InstantPopup)
        self._btn_list.setAutoRaise(True)
        self._btn_list.setFixedSize(34, 26)
        self._btn_list.setCursor(Qt.PointingHandCursor)
        self._btn_list.setIconSize(QSize(26, 24))
        self._list_menu = self._build_list_menu()
        self._btn_list.setMenu(self._list_menu)
        self._btn_list.setIcon(_make_list_icon(ordered=False))
        tb.addWidget(self._btn_list)

        tb.addWidget(self._sep())

        # Группа 5: Цвет текста / Цвет фона
        self._btn_color = self._tool_button_icon(
            _make_color_icon("A", self._last_text_color),
            "Цвет текста",
            self._pick_color_text,
        )
        self._btn_bg = self._tool_button_icon(
            _make_color_icon("✎", self._last_bg_color),
            "Цвет фона (выделение)",
            self._pick_color_bg,
        )
        tb.addWidget(self._btn_color)
        tb.addWidget(self._btn_bg)

        # Группа 6: Очистка
        self._btn_clear = self._tool_button_icon(
            _make_clear_icon(),
            "Очистить форматирование",
            self._clear_format,
        )
        tb.addWidget(self._btn_clear)

        tb.addWidget(self._sep())

        # Группа 7: Отмена / Повтор
        self._btn_undo = self._tool_button_icon(
            _make_undo_icon(redo=False),
            "Отменить (Ctrl+Z)",
            self._edit.undo,
        )
        self._btn_redo = self._tool_button_icon(
            _make_undo_icon(redo=True),
            "Повторить (Ctrl+Y)",
            self._edit.redo,
        )
        tb.addWidget(self._btn_undo)
        tb.addWidget(self._btn_redo)

        tb.addStretch()

        # Тулбар вставляем В НАЧАЛО layout (перед QTextEdit)
        outer.insertWidget(0, self._toolbar)

    # ---------- Построение кнопок ----------

    def _tool_button_icon(self, icon: QIcon, tooltip: str, callback) -> QToolButton:
        b = QToolButton()
        b.setIcon(icon)
        b.setIconSize(QSize(26, 24))
        b.setToolTip(tooltip)
        b.setCheckable(False)
        b.setAutoRaise(True)
        b.setFixedSize(30, 26)
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(callback)
        return b

    def _sep(self):
        s = QFrame()
        s.setFrameShape(QFrame.VLine)
        s.setFixedWidth(1)
        s.setStyleSheet(f"background:{self.theme.border}; border:none; margin:2px 4px;")
        return s

    def _build_align_menu(self) -> QMenu:
        menu = QMenu(self)
        menu.setStyleSheet(self._context_menu_qss())
        menu.setToolTipsVisible(True)

        self._act_align_left = QAction(
            _make_align_icon("left", "#e6e6e6"), "По левому краю", menu)
        self._act_align_left.triggered.connect(lambda: self._set_align("left"))
        menu.addAction(self._act_align_left)

        self._act_align_center = QAction(
            _make_align_icon("center", "#e6e6e6"), "По центру", menu)
        self._act_align_center.triggered.connect(lambda: self._set_align("center"))
        menu.addAction(self._act_align_center)

        self._act_align_right = QAction(
            _make_align_icon("right", "#e6e6e6"), "По правому краю", menu)
        self._act_align_right.triggered.connect(lambda: self._set_align("right"))
        menu.addAction(self._act_align_right)

        self._act_align_just = QAction(
            _make_align_icon("justify", "#e6e6e6"), "По ширине", menu)
        self._act_align_just.triggered.connect(lambda: self._set_align("justify"))
        menu.addAction(self._act_align_just)

        return menu

    def _build_list_menu(self) -> QMenu:
        menu = QMenu(self)
        menu.setStyleSheet(self._context_menu_qss())

        act_ul = QAction(_make_list_icon(ordered=False), "Маркированный список", menu)
        act_ul.triggered.connect(lambda: self._make_list(ordered=False))
        menu.addAction(act_ul)

        act_ol = QAction(_make_list_icon(ordered=True), "Нумерованный список", menu)
        act_ol.triggered.connect(lambda: self._make_list(ordered=True))
        menu.addAction(act_ol)

        act_rm = QAction("Убрать список", menu)
        act_rm.triggered.connect(self._remove_list)
        menu.addSeparator()
        menu.addAction(act_rm)

        return menu

    # ---------- Стилизация ----------

    def _apply_styles(self):
        t = self.theme
        self.setStyleSheet(f"""
            QFrame#RichToolbar {{
                background: {t.bg_panel};
                border: 1px solid {t.border};
                border-radius: 6px;
            }}
            QToolButton {{
                background: transparent;
                color: {t.text_main};
                border: 1px solid transparent;
                border-radius: 4px;
                padding: 0px;
            }}
            QToolButton:hover {{
                background: {t.bg_hover};
                border: 1px solid {t.border};
            }}
            QToolButton:pressed, QToolButton:checked {{
                background: {t.primary_hover};
                border: 1px solid {t.primary};
            }}
            QToolButton::menu-indicator {{
                image: none;
                width: 0;
            }}
            QComboBox {{
                background: {t.bg_card};
                color: {t.text_main};
                border: 1px solid {t.border};
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 12px;
            }}
            QComboBox:hover {{
                border: 1px solid {t.primary};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 18px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid {t.text_muted};
                margin-right: 4px;
            }}
            QComboBox QAbstractItemView {{
                background: {t.bg_card};
                color: {t.text_main};
                border: 1px solid {t.border};
                selection-background-color: {t.primary_hover};
                selection-color: {t.text_main};
            }}
            QTextEdit {{
                background: {t.bg_panel};
                color: {t.text_main};
                border: 1px solid {t.border};
                border-radius: 6px;
                padding: 6px 8px;
                font-size: 13px;
                selection-background-color: {t.primary};
                selection-color: {t.text_inverse};
            }}
            QTextEdit:focus {{
                border: 1px solid {t.primary};
            }}
        """)

    # ---------- Кэш иконок ----------

    def _cached_icon(self, key: str, factory):
        if key not in RichTextEditor._ICON_CACHE:
            RichTextEditor._ICON_CACHE[key] = factory()
        return RichTextEditor._ICON_CACHE[key]

    def _icon_bold(self, active: bool) -> QIcon:
        return self._cached_icon(
            f"b_{active}",
            lambda: _make_text_icon("Ж", bold=True,
                color="#87C800" if active else "#e6e6e6")
        )

    def _icon_italic(self, active: bool) -> QIcon:
        return self._cached_icon(
            f"i_{active}",
            lambda: _make_text_icon("К", italic=True,
                color="#87C800" if active else "#e6e6e6")
        )

    def _icon_underline(self, active: bool) -> QIcon:
        return self._cached_icon(
            f"u_{active}",
            lambda: _make_text_icon("Ч", underline=True,
                color="#87C800" if active else "#e6e6e6")
        )

    def _icon_align(self, kind: str) -> QIcon:
        return self._cached_icon(f"align_{kind}", lambda: _make_align_icon(kind))

    def _icon_list(self, ordered: bool) -> QIcon:
        return self._cached_icon(f"list_{ordered}", lambda: _make_list_icon(ordered=ordered))

    # ---------- Действия форматирования ----------

    def _merge_format(self, fmt: QTextCharFormat):
        cursor = self._edit.textCursor()
        if not cursor.hasSelection():
            cursor.select(QTextCursor.WordUnderCursor)
        cursor.mergeCharFormat(fmt)
        self._edit.mergeCurrentCharFormat(fmt)
        self._schedule_sync_toolbar()

    def _schedule_sync_toolbar(self, *args):
        if self._sync_scheduled:
            return
        self._sync_scheduled = True
        from PySide6.QtCore import QTimer
        QTimer.singleShot(50, self._do_scheduled_sync)

    def _do_scheduled_sync(self):
        self._sync_scheduled = False
        self._sync_toolbar()

    def _toggle_bold(self):
        fmt = QTextCharFormat()
        is_bold = self._edit.currentCharFormat().fontWeight() >= QFont.Bold
        fmt.setFontWeight(QFont.Normal if is_bold else QFont.Bold)
        self._merge_format(fmt)

    def _toggle_italic(self):
        fmt = QTextCharFormat()
        fmt.setFontItalic(not self._edit.currentCharFormat().fontItalic())
        self._merge_format(fmt)

    def _toggle_underline(self):
        fmt = QTextCharFormat()
        fmt.setFontUnderline(not self._edit.currentCharFormat().fontUnderline())
        self._merge_format(fmt)

    def _toggle_strike(self):
        fmt = QTextCharFormat()
        fmt.setFontStrikeOut(not self._edit.currentCharFormat().fontStrikeOut())
        self._merge_format(fmt)

    def _apply_font_family(self, family: str):
        if not family:
            return
        fmt = QTextCharFormat()
        fmt.setFontFamilies([family])
        self._merge_format(fmt)

    def _on_size_changed(self, text: str):
        try:
            size = float(text)
        except ValueError:
            return
        fmt = QTextCharFormat()
        fmt.setFontPointSize(size)
        self._merge_format(fmt)

    def _apply_font_size(self, size_pt: int):
        fmt = QTextCharFormat()
        fmt.setFontPointSize(float(size_pt))
        self._merge_format(fmt)

    def _set_align(self, kind: str):
        bf = QTextBlockFormat()
        if kind == "left":
            bf.setAlignment(Qt.AlignLeft)
        elif kind == "center":
            bf.setAlignment(Qt.AlignHCenter)
        elif kind == "right":
            bf.setAlignment(Qt.AlignRight)
        elif kind == "justify":
            bf.setAlignment(Qt.AlignJustify)

        cursor = self._edit.textCursor()
        cursor.mergeBlockFormat(bf)
        self._edit.setTextCursor(cursor)
        self._sync_toolbar()

    def _make_list(self, ordered: bool):
        cursor = self._edit.textCursor()
        cursor.beginEditBlock()
        lf = QTextListFormat()
        lf.setStyle(
            QTextListFormat.ListDecimal if ordered
            else QTextListFormat.ListDisc
        )
        cursor.createList(lf)
        cursor.endEditBlock()
        self._sync_toolbar()

    def _remove_list(self):
        cursor = self._edit.textCursor()
        cursor.beginEditBlock()
        bf = cursor.blockFormat()
        bf.setIndent(0)
        cursor.setBlockFormat(bf)
        lst = cursor.currentList()
        if lst is not None:
            lst.remove(cursor.block())
        cursor.endEditBlock()
        self._sync_toolbar()

    # ---------- Выбор цвета ----------

    def _pick_color_text(self):
        color = self._pick_color_dialog(self._last_text_color)
        if color:
            self._last_text_color = color
            self._apply_color(color)
            if self._show_toolbar:
                self._refresh_color_buttons()

    def _pick_color_bg(self):
        color = self._pick_color_dialog(self._last_bg_color)
        if color:
            self._last_bg_color = color
            self._apply_bg_color(color)
            if self._show_toolbar:
                self._refresh_color_buttons()

    def _pick_color_dialog(self, current: str) -> str | None:
        menu = QMenu(self)
        menu.setStyleSheet(self._context_menu_qss())

        for c in _PALETTE:
            pix = QPixmap(16, 16)
            pix.fill(QColor(c))
            painter = QPainter(pix)
            painter.setPen(QColor("#888"))
            painter.drawRect(0, 0, 15, 15)
            painter.end()
            act = QAction(QIcon(pix), c, menu)
            act.triggered.connect(
                lambda checked=False, col=c: self._on_color_chosen(col)
            )
            menu.addAction(act)

        menu.addSeparator()
        act_custom = QAction("Свой цвет…", menu)
        act_custom.triggered.connect(self._on_custom_color)
        menu.addAction(act_custom)

        self._pending_color_target = current
        self._pending_color_result = None

        btn = getattr(self, "_btn_color", None)
        if btn is not None and self.sender() is getattr(self, "_btn_bg", None):
            btn = self._btn_bg
        if btn is None:
            btn = self
        global_pos = btn.mapToGlobal(btn.rect().bottomLeft())
        menu.exec(global_pos)
        return self._pending_color_result

    def _on_color_chosen(self, color_hex: str):
        self._pending_color_result = color_hex

    def _on_custom_color(self):
        col = QColorDialog.getColor(
            QColor(self._pending_color_target), self, "Выберите цвет"
        )
        if col.isValid():
            self._pending_color_result = col.name()

    def _apply_color(self, color_hex: str):
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color_hex))
        self._merge_format(fmt)

    def _apply_bg_color(self, color_hex: str):
        fmt = QTextCharFormat()
        fmt.setBackground(QColor(color_hex))
        self._merge_format(fmt)

    def _refresh_color_buttons(self):
        if not getattr(self, "_show_toolbar", False):
            return
        self._btn_color.setIcon(
            _make_color_icon("A", self._last_text_color)
        )
        self._btn_bg.setIcon(
            _make_color_icon("✎", self._last_bg_color)
        )

    def _clear_format(self):
        cursor = self._edit.textCursor()
        if not cursor.hasSelection():
            cursor.select(QTextCursor.WordUnderCursor)
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Normal)
        fmt.setFontItalic(False)
        fmt.setFontUnderline(False)
        fmt.setFontStrikeOut(False)
        fmt.setForeground(QColor(self.theme.text_main))
        fmt.setBackground(QColor(Qt.transparent))
        cursor.setCharFormat(fmt)
        self._sync_toolbar()

    # ---------- Синхронизация тулбара (отключена) ----------

    def _sync_toolbar(self):
        if not getattr(self, "_ready", False):
            return
        if self.parent() is None:
            return
        if not self.isVisible():
            return
        try:
            self._sync_toolbar_impl()
        except Exception:
            import traceback
            traceback.print_exc()

    def _sync_toolbar_impl(self):
        """Заглушка — синхронизация отключена из-за крашей PySide6."""
        pass

    # ---------- Контекстное меню (ПКМ) ----------

    def _context_menu_qss(self) -> str:
        t = self.theme
        return f"""
            QMenu {{
                background: {t.bg_card};
                color: {t.text_main};
                border: 1px solid {t.border};
                border-radius: 6px;
                padding: 6px 4px;
                font-size: 12px;
            }}
            QMenu::item {{
                padding: 6px 24px 6px 12px;
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
        """

    def _show_context_menu(self, pos):
        menu = QMenu(self._edit)
        menu.setStyleSheet(self._context_menu_qss())

        fmt = self._edit.currentCharFormat()

        act_b = menu.addAction("Жирный")
        act_b.setCheckable(True)
        act_b.setChecked(fmt.fontWeight() >= QFont.Bold)
        act_b.setShortcut(QKeySequence("Ctrl+B"))
        act_b.triggered.connect(self._toggle_bold)

        act_i = menu.addAction("Курсив")
        act_i.setCheckable(True)
        act_i.setChecked(fmt.fontItalic())
        act_i.setShortcut(QKeySequence("Ctrl+I"))
        act_i.triggered.connect(self._toggle_italic)

        act_u = menu.addAction("Подчёркнутый")
        act_u.setCheckable(True)
        act_u.setChecked(fmt.fontUnderline())
        act_u.setShortcut(QKeySequence("Ctrl+U"))
        act_u.triggered.connect(self._toggle_underline)

        act_s = menu.addAction("Зачёркнутый")
        act_s.setCheckable(True)
        act_s.setChecked(fmt.fontStrikeOut())
        act_s.triggered.connect(self._toggle_strike)

        menu.addSeparator()

        sub_color = menu.addMenu("Цвет текста")
        sub_color.setStyleSheet(self._context_menu_qss())
        for c in _PALETTE:
            pix = QPixmap(14, 14)
            pix.fill(QColor(c))
            painter = QPainter(pix)
            painter.setPen(QColor("#888"))
            painter.drawRect(0, 0, 13, 13)
            painter.end()
            a = QAction(QIcon(pix), c, sub_color)
            a.triggered.connect(lambda checked=False, col=c: self._apply_color(col))
            sub_color.addAction(a)
        sub_color.addSeparator()
        a_custom = QAction("Свой цвет…", sub_color)
        a_custom.triggered.connect(self._pick_color_text)
        sub_color.addAction(a_custom)

        sub_bg = menu.addMenu("Цвет фона")
        sub_bg.setStyleSheet(self._context_menu_qss())
        for c in _PALETTE:
            pix = QPixmap(14, 14)
            pix.fill(QColor(c))
            painter = QPainter(pix)
            painter.setPen(QColor("#888"))
            painter.drawRect(0, 0, 13, 13)
            painter.end()
            a = QAction(QIcon(pix), c, sub_bg)
            a.triggered.connect(lambda checked=False, col=c: self._apply_bg_color(col))
            sub_bg.addAction(a)
        sub_bg.addSeparator()
        a_custom_bg = QAction("Свой цвет…", sub_bg)
        a_custom_bg.triggered.connect(self._pick_color_bg)
        sub_bg.addAction(a_custom_bg)

        sub_font = menu.addMenu("Шрифт")
        sub_font.setStyleSheet(self._context_menu_qss())
        current_family = fmt.fontFamily()
        for family in _FONT_FAMILIES:
            a = QAction(family, sub_font)
            a.setCheckable(True)
            a.setChecked(family == current_family)
            a.triggered.connect(
                lambda checked=False, f=family: self._apply_font_family(f)
            )
            sub_font.addAction(a)

        sub_size = menu.addMenu("Размер")
        sub_size.setStyleSheet(self._context_menu_qss())
        current_size = int(fmt.fontPointSize()) if fmt.fontPointSize() > 0 else 0
        for size in _FONT_SIZES:
            a = QAction(f"{size} pt", sub_size)
            a.setCheckable(True)
            a.setChecked(size == current_size)
            a.triggered.connect(
                lambda checked=False, s=size: self._apply_font_size(s)
            )
            sub_size.addAction(a)

        menu.addSeparator()

        sub_align = menu.addMenu("Выравнивание")
        sub_align.setStyleSheet(self._context_menu_qss())
        for label, kind in [
            ("По левому краю", "left"),
            ("По центру", "center"),
            ("По правому краю", "right"),
            ("По ширине", "justify"),
        ]:
            a = QAction(label, sub_align)
            a.triggered.connect(
                lambda checked=False, k=kind: self._set_align(k)
            )
            sub_align.addAction(a)

        menu.addSeparator()

        has_sel = self._edit.textCursor().hasSelection()
        act_copy = menu.addAction("Копировать")
        act_copy.setShortcut(QKeySequence("Ctrl+C"))
        act_copy.setEnabled(has_sel)
        act_copy.triggered.connect(self._edit.copy)

        act_cut = menu.addAction("Вырезать")
        act_cut.setShortcut(QKeySequence("Ctrl+X"))
        act_cut.setEnabled(has_sel)
        act_cut.triggered.connect(self._edit.cut)

        act_paste = menu.addAction("Вставить")
        act_paste.setShortcut(QKeySequence("Ctrl+V"))
        act_paste.triggered.connect(self._edit.paste)

        act_sel_all = menu.addAction("Выделить всё")
        act_sel_all.setShortcut(QKeySequence("Ctrl+A"))
        act_sel_all.triggered.connect(self._edit.selectAll)

        menu.addSeparator()

        act_clear = menu.addAction("Очистить форматирование")
        act_clear.triggered.connect(self._clear_format)

        global_pos = self._edit.mapToGlobal(pos)
        menu.exec(global_pos)