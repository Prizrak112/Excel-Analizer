"""
Виджет визуального разделения строки.
Пользователь кликает в строку — появляется маяк (красная линия).
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QMenu
)
from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QTextCursor, QTextCharFormat, QColor


class VisualSplitWidget(QWidget):
    """Визуальное разделение строки маяками."""

    markers_changed = Signal(list)

    MARKER_COLOR = QColor("#e74c3c")
    MARKER_HOVER_COLOR = QColor("#ff5722")
    HIT_RADIUS = 1

    def __init__(self, text: str, theme, parent=None):
        super().__init__(parent)

        self.theme = theme
        self._text = text or ""
        self._markers = []
        self._hovered_marker = None

        self._build_ui()
        self._update_text()

    # ============================================================
    # UI
    # ============================================================

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.text_edit = _ClickableTextEdit(self)
        self.text_edit.setReadOnly(True)
        self.text_edit.setTextInteractionFlags(Qt.NoTextInteraction)
        self.text_edit.setFixedHeight(40)
        self.text_edit.setLineWrapMode(QTextEdit.NoWrap)
        self.text_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # margin вместо QSS padding — cursorForPosition корректно его учитывает
        self.text_edit.document().setDocumentMargin(6)

        self.text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {self.theme.bg_panel};
                border: 1px solid {self.theme.border};
                border-radius: 4px;
                padding: 0;
                font-family: 'Consolas', monospace;
                font-size: 13px;
                color: {self.theme.text_main};
            }}
            QTextEdit:focus {{
                border: 1px solid {self.theme.primary};
            }}
        """)

        self.text_edit.mouse_clicked.connect(self._on_text_clicked)
        self.text_edit.mouse_moved.connect(self._on_text_moved)
        self.text_edit.right_clicked.connect(self._on_text_right_clicked)
        self.text_edit.leave_event.connect(self._on_leave)

        layout.addWidget(self.text_edit)

        hints = QWidget()
        hints.setFixedHeight(18)
        hints_layout = QHBoxLayout(hints)
        hints_layout.setContentsMargins(0, 0, 0, 0)
        hints_layout.setSpacing(16)

        hint_1 = QLabel("💡 Кликните в строку — поставить маяк")
        hint_1.setStyleSheet(f"""
            color: {self.theme.text_muted};
            font-size: 11px;
            background: transparent;
            border: none;
        """)
        hints_layout.addWidget(hint_1)

        hint_2 = QLabel("🖱 ПКМ по маяку — удалить")
        hint_2.setStyleSheet(f"""
            color: {self.theme.text_muted};
            font-size: 11px;
            background: transparent;
            border: none;
        """)
        hints_layout.addWidget(hint_2)

        hints_layout.addStretch()
        layout.addWidget(hints)

    def _update_text(self):
        self.text_edit.setPlainText(self._text)
        self._redraw_markers()

    # ============================================================
    # Работа с маяками
    # ============================================================

    def set_text(self, text: str):
        self._text = text or ""
        self._markers = []
        self._hovered_marker = None
        self._update_text()
        self.markers_changed.emit([])

    def get_markers(self) -> list[int]:
        return sorted(self._markers)

    def set_markers(self, positions: list[int]):
        self._markers = sorted(p for p in positions if 0 < p < len(self._text))
        self._redraw_markers()
        self.markers_changed.emit(self.get_markers())

    def clear_markers(self):
        self._markers = []
        self._redraw_markers()
        self.markers_changed.emit([])

    def _toggle_marker(self, position: int):
        if position <= 0 or position >= len(self._text):
            return

        if position in self._markers:
            self._markers.remove(position)
            self._redraw_markers()
            self.markers_changed.emit(self.get_markers())
            return

        self._markers.append(position)
        self._markers.sort()
        self._redraw_markers()
        self.markers_changed.emit(self.get_markers())

    def _remove_marker(self, position: int):
        if position in self._markers:
            self._markers.remove(position)
            self._redraw_markers()
            self.markers_changed.emit(self.get_markers())

    # ============================================================
    # Отрисовка
    # ============================================================

    def _redraw_markers(self):
        selections = []

        for pos in self._markers:
            sel = QTextEdit.ExtraSelection()
            fmt = QTextCharFormat()
            color = self.MARKER_HOVER_COLOR if pos == self._hovered_marker else self.MARKER_COLOR
            fmt.setBackground(color)
            fmt.setForeground(QColor("white"))

            cursor = self.text_edit.textCursor()
            cursor.setPosition(max(0, pos - 1))
            cursor.setPosition(pos, QTextCursor.KeepAnchor)

            sel.cursor = cursor
            sel.format = fmt
            selections.append(sel)

        self.text_edit.setExtraSelections(selections)

    # ============================================================
    # Мышь
    # ============================================================

    def _on_text_clicked(self, position: int):
        self._toggle_marker(position)

    def _on_text_moved(self, position: int, global_pos: QPoint):
        hovered = None
        for m in self._markers:
            if abs(m - position) <= self.HIT_RADIUS:
                hovered = m
                break

        if hovered != self._hovered_marker:
            self._hovered_marker = hovered
            self._redraw_markers()

        if hovered is not None:
            self.text_edit.viewport().setCursor(Qt.PointingHandCursor)
        else:
            self.text_edit.viewport().setCursor(Qt.IBeamCursor)

    def _on_text_right_clicked(self, position: int, global_pos: QPoint):
        hovered = None
        for m in self._markers:
            if abs(m - position) <= self.HIT_RADIUS:
                hovered = m
                break

        if hovered is None:
            return

        menu = QMenu(self)
        action_remove = menu.addAction("✂️ Убрать маяк")
        action_clear = menu.addAction("🗑 Убрать все маяки")

        action = menu.exec(global_pos)

        if action == action_remove:
            self._remove_marker(hovered)
        elif action == action_clear:
            self.clear_markers()

    def _on_leave(self):
        if self._hovered_marker is not None:
            self._hovered_marker = None
            self._redraw_markers()


# ============================================================
# Кастомный QTextEdit
# ============================================================

class _ClickableTextEdit(QTextEdit):
    """QTextEdit, который отправляет сигналы клика с позицией символа."""

    mouse_clicked = Signal(int)
    mouse_moved = Signal(int, QPoint)
    right_clicked = Signal(int, QPoint)
    leave_event = Signal()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pos = self._position_from_event(event)
            self.mouse_clicked.emit(pos)
            event.accept()
            return
        elif event.button() == Qt.RightButton:
            pos = self._position_from_event(event)
            global_pos = event.globalPosition().toPoint()
            self.right_clicked.emit(pos, global_pos)
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        pos = self._position_from_event(event)
        global_pos = event.globalPosition().toPoint()
        self.mouse_moved.emit(pos, global_pos)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.leave_event.emit()
        super().leaveEvent(event)

    def _position_from_event(self, event) -> int:
        """
        Точная позиция курсора с учётом того, на каком символе был клик.

        Логика:
          • cursorForPosition возвращает границу между символами, ближайшую
            к точке клика. Для левой половины символа — границу ПЕРЕД ним,
            для правой — ПОСЛЕ.
          • Маркер подсвечивает символ СЛЕВА от pos. Значит, если клик
            был в левую половину символа i, cursorForPosition вернёт i, и
            маркер ошибочно подсветит символ i-1.
          • Чтобы это исправить, смотрим на cursorRect(cursor) — он даёт
            x-координату границы pos. Если точка клика ПРАВЕЕ этой границы,
            значит мы на левой половине символа pos → сдвигаем pos на +1.
        """
        # Координаты виджета → координаты viewport
        widget_pos = event.position().toPoint()
        viewport_pos = self.viewport().mapFrom(self, widget_pos)

        # Ближайшая граница
        cursor = self.cursorForPosition(viewport_pos)
        pos = cursor.position()

        # x-координата этой границы
        rect = self.cursorRect(cursor)

        # Клик правее границы → символ справа от неё находится под курсором
        if viewport_pos.x() >= rect.x():
            pos += 1

        return pos