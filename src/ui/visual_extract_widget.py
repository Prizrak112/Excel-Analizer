"""
Виджет выделения фрагмента в примере строки.

Что делает:
  • Клик — выделяет слово под курсором.
  • Протяжка — выделяет РОВНО то, что протянул (только снимает пробелы).

Никаких "умных" снэпов и подсказок — пользователь сам решает,
что должно остаться.
"""

import re

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QTextCursor


_TOKEN_RE = re.compile(r"[0-9A-Za-zА-Яа-яЁё\-_]+")


class VisualExtractWidget(QWidget):
    """Выделение фрагмента в примере строки."""

    selection_changed = Signal(int, int)

    def __init__(self, text: str, theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self._text = text or ""
        self._build_ui()
        self._update_text()

    # ============================================================
    # UI
    # ============================================================

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.text_edit = _ClickableTextEdit(self)
        self.text_edit.setReadOnly(True)
        self.text_edit.setFixedHeight(42)
        self.text_edit.setLineWrapMode(QTextEdit.NoWrap)
        self.text_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
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
                selection-background-color: {self.theme.primary};
                selection-color: {self.theme.text_inverse};
            }}
            QTextEdit:focus {{
                border: 1px solid {self.theme.primary};
            }}
        """)

        self.text_edit.clicked.connect(self._on_clicked)
        self.text_edit.drag_released.connect(self._on_drag_released)
        layout.addWidget(self.text_edit)

        hints = QWidget()
        hints.setFixedHeight(18)
        hints_layout = QHBoxLayout(hints)
        hints_layout.setContentsMargins(0, 0, 0, 0)
        hints_layout.setSpacing(16)

        hint = QLabel(
            "💡 Клик — слово. Протяжка — любая фраза."
        )
        hint.setStyleSheet(f"""
            color: {self.theme.text_muted};
            font-size: 11px;
            background: transparent;
            border: none;
        """)
        hints_layout.addWidget(hint)
        hints_layout.addStretch()
        layout.addWidget(hints)

    def _update_text(self):
        self.text_edit.setPlainText(self._text)

    # ============================================================
    # Публичный API
    # ============================================================

    def set_text(self, text: str):
        self._text = text or ""
        self._update_text()
        cursor = self.text_edit.textCursor()
        cursor.clearSelection()
        self.text_edit.setTextCursor(cursor)

    def get_selection(self):
        cursor = self.text_edit.textCursor()
        if not cursor.hasSelection():
            return None
        s = cursor.selectionStart()
        e = cursor.selectionEnd()
        if s == e:
            return None
        return (s, e)

    def clear_selection(self):
        cursor = self.text_edit.textCursor()
        cursor.clearSelection()
        self.text_edit.setTextCursor(cursor)
        self.selection_changed.emit(-1, -1)

    # ============================================================
    # Логика
    # ============================================================

    def _on_clicked(self, pos: int):
        """
        Клик — выделяем «фразу» вокруг клика:
        от предыдущей запятой/таба/начала строки до следующей запятой/таба/конца.
        Так клик по «Комбайн» даёт всю модель ТС целиком.
        """
        PHRASE_BREAKS = ",;\t"
        text = self._text
        if not text:
            return

        # левая граница — ближайшая запятая/таб слева (или начало строки)
        s = 0
        for i in range(pos, -1, -1):
            if text[i] in PHRASE_BREAKS:
                s = i + 1
                break

        # правая граница — ближайшая запятая/таб справа (или конец строки)
        e = len(text)
        for i in range(pos, len(text)):
            if text[i] in PHRASE_BREAKS:
                e = i
                break

        # снимаем пробелы по краям
        while s < e and text[s].isspace():
            s += 1
        while e > s and text[e - 1].isspace():
            e -= 1

        if s >= e:
            return

        cursor = self.text_edit.textCursor()
        cursor.setPosition(s)
        cursor.setPosition(e, QTextCursor.KeepAnchor)
        self.text_edit.setTextCursor(cursor)
        self.selection_changed.emit(s, e)

    def _on_drag_released(self, start: int, end: int):
        """Протяжка — оставляем ровно то, что выделено (снимаем пробелы по краям)."""
        s, e = min(start, end), max(start, end)
        if s >= e:
            return

        text = self._text
        while s < e and text[s].isspace():
            s += 1
        while e > s and text[e - 1].isspace():
            e -= 1

        if s >= e:
            self.clear_selection()
            return

        cursor = self.text_edit.textCursor()
        cursor.setPosition(s)
        cursor.setPosition(e, QTextCursor.KeepAnchor)
        self.text_edit.setTextCursor(cursor)
        self.selection_changed.emit(s, e)

    def _find_token_at(self, pos: int):
        for m in _TOKEN_RE.finditer(self._text):
            if m.start() <= pos < m.end():
                return (m.start(), m.end())
        for m in _TOKEN_RE.finditer(self._text):
            if m.start() >= pos:
                return (m.start(), m.end())
        last = None
        for m in _TOKEN_RE.finditer(self._text):
            last = (m.start(), m.end())
        return last


class _ClickableTextEdit(QTextEdit):
    """QTextEdit, различающий клик и протяжку по смещению в пикселях."""

    clicked = Signal(int)
    drag_released = Signal(int, int)

    DRAG_THRESHOLD_PX = 6

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_start_pos: int | None = None
        self._drag_start_px = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            viewport_pos = self.viewport().mapFrom(self, event.position().toPoint())
            cursor = self.cursorForPosition(viewport_pos)
            self._drag_start_pos = cursor.position()
            self._drag_start_px = event.position().toPoint()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            viewport_pos = self.viewport().mapFrom(self, event.position().toPoint())
            cursor = self.cursorForPosition(viewport_pos)
            end_pos = cursor.position()

            if self._drag_start_pos is None or self._drag_start_px is None:
                self.clicked.emit(end_pos)
            else:
                end_px = event.position().toPoint()
                dx = abs(end_px.x() - self._drag_start_px.x())
                dy = abs(end_px.y() - self._drag_start_px.y())
                is_real_drag = (dx + dy) > self.DRAG_THRESHOLD_PX

                if is_real_drag:
                    self.drag_released.emit(self._drag_start_pos, end_pos)
                else:
                    self.clicked.emit(end_pos)

            self._drag_start_pos = None
            self._drag_start_px = None
            event.accept()
            return
        super().mouseReleaseEvent(event)