"""
Внешний тулбар форматирования для Конструктора.

Отделён от RichTextEditor, потому что:
  • на холсте редакторов может быть много (по одному на текстовый блок),
  • а тулбар должен быть один — общий, в полосе над холстом.

Использование:
    toolbar = RichTextToolbar(theme)
    toolbar.set_editor(rich_text_editor)   # активировать кнопки
    toolbar.set_editor(None)               # деактивировать (кнопки серые)

Кнопки вызывают ПУБЛИЧНЫЕ методы RichTextEditor:
    toggle_bold(), toggle_italic(), set_align(), make_list(),
    apply_color(), apply_bg_color(), clear_format(), undo(), redo(),
    pick_color_text(), pick_color_bg(), ...
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QToolButton, QFrame, QComboBox, QMenu,
)
from PySide6.QtGui import (
    QIcon, QPixmap, QPainter, QColor, QAction, QBrush, QPen,
    QPainterPath, QFont,
)
from PySide6.QtCore import Qt, QSize, QRect, QPoint

# Импортируем генераторы иконок из rich_text_editor,
# чтобы не дублировать код. Они — модульные функции.
from src.ui.rich_text_editor import (
    _make_text_icon,
    _make_align_icon,
    _make_list_icon,
    _make_color_icon,
    _make_clear_icon,
    _make_undo_icon,
    _PALETTE,
    _FONT_FAMILIES,
    _FONT_SIZES,
)


class RichTextToolbar(QWidget):
    """Общий тулбар форматирования. Управляет активным RichTextEditor."""

    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.theme = theme

        # ★ Активный редактор. None → все кнопки задизейблены.
        self._current_editor = None

        # Последние использованные цвета (для иконок кнопок).
        # Когда редактор активен — обновляются после выбора.
        self._last_text_color = "#e6e6e6"
        self._last_bg_color = "#f1c40f"

        self._build_ui()
        self._apply_styles()
        self._update_enabled_state()

    # ---------- Публичный API ----------

    def set_editor(self, editor):
        """
        Установить активный редактор.
        editor=None → кнопки серые, действия ничего не делают.
        """
        self._current_editor = editor
        self._update_enabled_state()

    def current_editor(self):
        return self._current_editor

    # ---------- Построение ----------

    def _build_ui(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(2)

        # Группа 1: Шрифт + Размер
        self._font_combo = QComboBox()
        self._font_combo.addItems(_FONT_FAMILIES)
        self._font_combo.setFixedWidth(110)
        self._font_combo.setFixedHeight(24)
        self._font_combo.currentTextChanged.connect(self._on_font_changed)
        lay.addWidget(self._font_combo)

        self._size_combo = QComboBox()
        self._size_combo.addItems([str(s) for s in _FONT_SIZES])
        self._size_combo.setFixedWidth(52)
        self._size_combo.setFixedHeight(24)
        self._size_combo.currentTextChanged.connect(self._on_size_changed)
        lay.addWidget(self._size_combo)

        lay.addWidget(self._sep())

        # Группа 2: Ж / К / Ч
        self._btn_b = self._btn(_make_text_icon("Ж", bold=True), "Жирный (Ctrl+B)",
                                self._on_bold)
        self._btn_i = self._btn(_make_text_icon("К", italic=True), "Курсив (Ctrl+I)",
                                self._on_italic)
        self._btn_u = self._btn(_make_text_icon("Ч", underline=True), "Подчёркнутый (Ctrl+U)",
                                self._on_underline)
        lay.addWidget(self._btn_b)
        lay.addWidget(self._btn_i)
        lay.addWidget(self._btn_u)

        lay.addWidget(self._sep())

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
        lay.addWidget(self._btn_align)

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
        lay.addWidget(self._btn_list)

        lay.addWidget(self._sep())

        # Группа 5: Цвет текста / Цвет фона
        self._btn_color = self._btn(
            _make_color_icon("A", self._last_text_color),
            "Цвет текста",
            self._on_color_text,
        )
        self._btn_bg = self._btn(
            _make_color_icon("✎", self._last_bg_color),
            "Цвет фона (выделение)",
            self._on_color_bg,
        )
        lay.addWidget(self._btn_color)
        lay.addWidget(self._btn_bg)

        # Группа 6: Очистка
        self._btn_clear = self._btn(
            _make_clear_icon(),
            "Очистить форматирование",
            self._on_clear,
        )
        lay.addWidget(self._btn_clear)

        lay.addWidget(self._sep())

        # Группа 7: Отмена / Повтор
        self._btn_undo = self._btn(
            _make_undo_icon(redo=False),
            "Отменить (Ctrl+Z)",
            self._on_undo,
        )
        self._btn_redo = self._btn(
            _make_undo_icon(redo=True),
            "Повторить (Ctrl+Y)",
            self._on_redo,
        )
        lay.addWidget(self._btn_undo)
        lay.addWidget(self._btn_redo)

        lay.addStretch()

    def _btn(self, icon: QIcon, tooltip: str, callback) -> QToolButton:
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
        menu.setStyleSheet(self._menu_qss())

        for label, kind in [
            ("По левому краю", "left"),
            ("По центру", "center"),
            ("По правому краю", "right"),
            ("По ширине", "justify"),
        ]:
            a = QAction(_make_align_icon(kind), label, menu)
            a.triggered.connect(
                lambda checked=False, k=kind: self._on_align(k)
            )
            menu.addAction(a)

        return menu

    def _build_list_menu(self) -> QMenu:
        menu = QMenu(self)
        menu.setStyleSheet(self._menu_qss())

        act_ul = QAction(_make_list_icon(ordered=False), "Маркированный список", menu)
        act_ul.triggered.connect(lambda: self._on_list(ordered=False))
        menu.addAction(act_ul)

        act_ol = QAction(_make_list_icon(ordered=True), "Нумерованный список", menu)
        act_ol.triggered.connect(lambda: self._on_list(ordered=True))
        menu.addAction(act_ol)

        act_rm = QAction("Убрать список", menu)
        act_rm.triggered.connect(self._on_remove_list)
        menu.addSeparator()
        menu.addAction(act_rm)

        return menu

    def _menu_qss(self) -> str:
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

    # ---------- Стилизация ----------

    def _apply_styles(self):
        t = self.theme
        self.setStyleSheet(f"""
            RichTextToolbar {{
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
            QToolButton:disabled {{
                opacity: 0.35;
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
        """)

    def _update_enabled_state(self):
        """Включить/выключить кнопки в зависимости от наличия редактора."""
        has_editor = self._current_editor is not None

        for w in (
            self._btn_b, self._btn_i, self._btn_u,
            self._btn_align, self._btn_list,
            self._btn_color, self._btn_bg,
            self._btn_clear, self._btn_undo, self._btn_redo,
            self._font_combo, self._size_combo,
        ):
            w.setEnabled(has_editor)

    # ---------- Обработчики ----------

    def _on_bold(self):
        if self._current_editor is not None:
            self._current_editor.toggle_bold()

    def _on_italic(self):
        if self._current_editor is not None:
            self._current_editor.toggle_italic()

    def _on_underline(self):
        if self._current_editor is not None:
            self._current_editor.toggle_underline()

    def _on_font_changed(self, family: str):
        if self._current_editor is not None and family:
            self._current_editor.apply_font_family(family)

    def _on_size_changed(self, text: str):
        if self._current_editor is None:
            return
        try:
            size = float(text)
        except ValueError:
            return
        self._current_editor.apply_font_size(int(size))

    def _on_align(self, kind: str):
        if self._current_editor is not None:
            self._current_editor.set_align(kind)

    def _on_list(self, ordered: bool):
        if self._current_editor is not None:
            self._current_editor.make_list(ordered)

    def _on_remove_list(self):
        if self._current_editor is not None:
            self._current_editor.remove_list()

    def _on_color_text(self):
        if self._current_editor is None:
            return
        color = self._current_editor.pick_color_text()
        if color:
            self._last_text_color = color
            self._current_editor.apply_color(color)
            self._btn_color.setIcon(_make_color_icon("A", color))

    def _on_color_bg(self):
        if self._current_editor is None:
            return
        color = self._current_editor.pick_color_bg()
        if color:
            self._last_bg_color = color
            self._current_editor.apply_bg_color(color)
            self._btn_bg.setIcon(_make_color_icon("✎", color))

    def _on_clear(self):
        if self._current_editor is not None:
            self._current_editor.clear_format()

    def _on_undo(self):
        if self._current_editor is not None:
            self._current_editor.undo()

    def _on_redo(self):
        if self._current_editor is not None:
            self._current_editor.redo()