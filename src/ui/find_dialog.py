"""
Диалог поиска (Ctrl+F) — со списком совпадений.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QCheckBox, QPushButton, QComboBox,
    QListWidget, QListWidgetItem
)
from PySide6.QtCore import Qt, Signal


class FindDialog(QDialog):
    """Немодальный диалог поиска со списком совпадений."""

    find_all = Signal(str, bool, str)     # text, case_sensitive, scope
    match_selected = Signal(int, int)     # row, col — перейти к ячейке
    closed = Signal()

    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.setWindowTitle("Поиск")
        self.setModal(False)
        self.setMinimumSize(520, 480)

        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        # ─── Поле поиска ───
        row1 = QHBoxLayout()
        row1.setSpacing(6)

        lbl = QLabel("Найти:")
        lbl.setStyleSheet(f"color: {self.theme.text_main}; font-size: 13px;")
        row1.addWidget(lbl)

        self.edit_text = QLineEdit()
        self.edit_text.setPlaceholderText("Введите текст...")
        self.edit_text.returnPressed.connect(self._on_find)
        row1.addWidget(self.edit_text, stretch=1)

        layout.addLayout(row1)

        # ─── Опции ───
        opts = QHBoxLayout()
        opts.setSpacing(12)

        self.chk_case = QCheckBox("Учитывать регистр")
        self.chk_case.setStyleSheet(f"color: {self.theme.text_main}; font-size: 12px;")
        self.chk_case.stateChanged.connect(self._on_find)
        opts.addWidget(self.chk_case)

        lbl_scope = QLabel("Искать:")
        lbl_scope.setStyleSheet(f"color: {self.theme.text_main}; font-size: 12px;")
        opts.addWidget(lbl_scope)

        self.combo_scope = QComboBox()
        self.combo_scope.addItem("Во всей таблице", "all")
        self.combo_scope.addItem("Только в выбранной колонке", "column")
        self.combo_scope.currentIndexChanged.connect(self._on_find)
        self.combo_scope.setStyleSheet(f"""
            QComboBox {{
                background: {self.theme.bg_card};
                color: {self.theme.text_main};
                border: 1px solid {self.theme.border};
                border-radius: 4px;
                padding: 3px 6px;
                font-size: 12px;
            }}
        """)
        opts.addWidget(self.combo_scope)
        opts.addStretch()
        layout.addLayout(opts)

        # ─── Кнопки ───
        row3 = QHBoxLayout()
        row3.setSpacing(6)

        self.btn_find = QPushButton("Найти все")
        self.btn_find.clicked.connect(self._on_find)

        self.btn_close = QPushButton("Закрыть")
        self.btn_close.clicked.connect(self.close)

        for b in (self.btn_find, self.btn_close):
            b.setStyleSheet(f"""
                QPushButton {{
                    background: {self.theme.bg_panel};
                    color: {self.theme.text_main};
                    border: 1px solid {self.theme.border};
                    border-radius: 4px;
                    padding: 5px 12px;
                    font-size: 12px;
                }}
                QPushButton:hover {{
                    background: {self.theme.primary_hover};
                    color: {self.theme.primary_dark};
                }}
            """)

        row3.addStretch()
        row3.addWidget(self.btn_find)
        row3.addWidget(self.btn_close)
        layout.addLayout(row3)

        # ─── Список совпадений ───
        self.list_matches = QListWidget()
        self.list_matches.itemClicked.connect(self._on_item_clicked)
        self.list_matches.itemDoubleClicked.connect(self._on_item_clicked)
        self.list_matches.setStyleSheet(f"""
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
                padding: 5px 8px;
                border-radius: 3px;
            }}
            QListWidget::item:selected {{
                background: {self.theme.primary_hover};
                color: {self.theme.primary_dark};
            }}
            QListWidget::item:hover {{
                background: {self.theme.bg_hover};
            }}
        """)
        layout.addWidget(self.list_matches, stretch=1)

        # ─── Статус ───
        self.label_status = QLabel("")
        self.label_status.setStyleSheet(
            f"color: {self.theme.text_muted}; font-size: 11px;"
        )
        layout.addWidget(self.label_status)

    def _apply_style(self):
        self.setStyleSheet(f"""
            QDialog {{
                background: {self.theme.bg_card};
            }}
            QLineEdit {{
                background: {self.theme.bg_panel};
                color: {self.theme.text_main};
                border: 1px solid {self.theme.border};
                border-radius: 4px;
                padding: 5px 8px;
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border: 1px solid {self.theme.primary};
            }}
        """)

    # ============================================================
    # Публичное API
    # ============================================================

    def set_status(self, text: str):
        self.label_status.setText(text)

    def focus_input(self):
        self.edit_text.setFocus()
        self.edit_text.selectAll()

    def set_matches(self, matches: list):
        """
        matches: список dict {row, col, col_name, value, index}
        Заполняет список.
        """
        self.list_matches.clear()

        if not matches:
            self.list_matches.addItem("— совпадений не найдено —")
            return

        for m in matches:
            text = f"Строка {m['row'] + 1} · {m['col_name']}: {m['value']}"
            # Обрезаем длинные значения
            if len(text) > 120:
                text = text[:117] + "..."

            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, (m["row"], m["col"]))
            self.list_matches.addItem(item)

    # ============================================================
    # События
    # ============================================================

    def _on_find(self):
        text = self.edit_text.text()
        if not text:
            self.list_matches.clear()
            self.set_status("")
            return
        self.find_all.emit(text, self.chk_case.isChecked(), self.combo_scope.currentData())

    def _on_item_clicked(self, item: QListWidgetItem):
        data = item.data(Qt.UserRole)
        if data is None:
            return
        row, col = data
        self.match_selected.emit(row, col)

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)