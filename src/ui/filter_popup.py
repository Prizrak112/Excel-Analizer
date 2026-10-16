"""
Всплывающее окно фильтра колонки — список уникальных значений с чекбоксами и сортировкой.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QListWidget, QListWidgetItem
)
from PySide6.QtCore import Qt, Signal


MAX_UNIQUE_VALUES = 5000


class FilterPopup(QWidget):
    """Попап фильтра колонки с управлением сортировкой."""

    applied = Signal(str, list)         # column_name, allowed_values (пусто = снять фильтр)
    sort_requested = Signal(str, bool)  # column_name, ascending

    def __init__(self, theme, column_name, unique_values, current_filter, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.theme = theme
        self.column_name = column_name
        self.unique_values = [str(v) for v in unique_values]
        self.current_filter = (
            set(str(v) for v in current_filter) if current_filter else None
        )

        self._build_ui()
        self._populate()

    # ============================================================
    # UI
    # ============================================================

    def _build_ui(self):
        self.setFixedSize(300, 460)
        self.setStyleSheet(f"""
            QWidget {{
                background: {self.theme.bg_card};
                color: {self.theme.text_main};
            }}
            QLineEdit {{
                background: {self.theme.bg_panel};
                color: {self.theme.text_main};
                border: 1px solid {self.theme.border};
                border-radius: 4px;
                padding: 5px 8px;
                font-size: 12px;
            }}
            QListWidget {{
                background: {self.theme.bg_panel};
                color: {self.theme.text_main};
                border: 1px solid {self.theme.border};
                border-radius: 4px;
                font-size: 12px;
                outline: none;
                padding: 4px;
            }}
            QListWidget::item {{
                padding: 3px 4px;
            }}
            QListWidget::item:selected {{
                background: {self.theme.primary_hover};
                color: {self.theme.primary_dark};
            }}
            QPushButton {{
                background: {self.theme.bg_panel};
                color: {self.theme.text_main};
                border: 1px solid {self.theme.border};
                border-radius: 4px;
                padding: 5px 10px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background: {self.theme.primary_hover};
                color: {self.theme.primary_dark};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        # Заголовок
        title = QLabel(f"Фильтр: {self.column_name}")
        title.setStyleSheet(
            f"color: {self.theme.primary}; font-size: 12px; font-weight: bold;"
        )
        layout.addWidget(title)

        # Кнопки сортировки (перенесены из шапки)
        sort_row = QHBoxLayout()
        sort_row.setSpacing(6)

        btn_sort_asc = QPushButton("▲ Сортировка А-Я")
        btn_sort_asc.clicked.connect(lambda: self._on_sort(True))

        btn_sort_desc = QPushButton("▼ Сортировка Я-А")
        btn_sort_desc.clicked.connect(lambda: self._on_sort(False))

        sort_row.addWidget(btn_sort_asc)
        sort_row.addWidget(btn_sort_desc)
        layout.addLayout(sort_row)

        # Поле поиска
        self.edit_search = QLineEdit()
        self.edit_search.setPlaceholderText("Поиск значений...")
        self.edit_search.textChanged.connect(self._on_search)
        layout.addWidget(self.edit_search)

        # Кнопки все / ничего
        row_top = QHBoxLayout()
        row_top.setSpacing(6)

        btn_all = QPushButton("Выделить все")
        btn_all.clicked.connect(lambda: self._set_all(True))

        btn_none = QPushButton("Снять все")
        btn_none.clicked.connect(lambda: self._set_all(False))

        row_top.addWidget(btn_all)
        row_top.addWidget(btn_none)
        layout.addLayout(row_top)

        # Список значений
        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget, stretch=1)

        # ОК / Отмена
        row_bottom = QHBoxLayout()
        row_bottom.setSpacing(6)

        btn_ok = QPushButton("ОК")
        btn_ok.clicked.connect(self._on_ok)

        btn_cancel = QPushButton("Отмена")
        btn_cancel.clicked.connect(self.close)

        row_bottom.addStretch()
        row_bottom.addWidget(btn_ok)
        row_bottom.addWidget(btn_cancel)
        layout.addLayout(row_bottom)

    # ============================================================
    # Наполнение
    # ============================================================

    def _populate(self):
        self.list_widget.blockSignals(True)
        self.list_widget.clear()

        if len(self.unique_values) > MAX_UNIQUE_VALUES:
            item = QListWidgetItem(
                f"Слишком много значений ({len(self.unique_values)}). "
                f"Фильтр недоступен."
            )
            item.setFlags(Qt.NoItemFlags)
            self.list_widget.addItem(item)
            self.list_widget.blockSignals(False)
            return

        for v in self.unique_values:
            item = QListWidgetItem(v)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            checked = (self.current_filter is None) or (v in self.current_filter)
            item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
            self.list_widget.addItem(item)

        self.list_widget.blockSignals(False)

    # ============================================================
    # Действия
    # ============================================================

    def _on_sort(self, ascending: bool):
        self.sort_requested.emit(self.column_name, ascending)
        self.close()

    def _on_search(self, text: str):
        needle = text.lower()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if needle:
                item.setHidden(needle not in item.text().lower())
            else:
                item.setHidden(False)

    def _set_all(self, state: bool):
        self.list_widget.blockSignals(True)
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if not item.isHidden():
                item.setCheckState(Qt.Checked if state else Qt.Unchecked)
        self.list_widget.blockSignals(False)

    def _on_ok(self):
        allowed = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.Checked:
                allowed.append(item.text())

        if len(allowed) == len(self.unique_values):
            self.applied.emit(self.column_name, [])
        else:
            self.applied.emit(self.column_name, allowed)

        self.close()