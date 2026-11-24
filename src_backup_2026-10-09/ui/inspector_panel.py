"""
Инспектор для правой панели.
Виджеты создаются один раз в __init__, при переключении колонки — только обновление значений.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QComboBox, QCheckBox, QPushButton, QFrame
)
from PySide6.QtCore import Qt, Signal


DTYPE_OPTIONS = [
    ("int64",          "🔢  Целое (int64)"),
    ("float64",        "🔢  Дробное (float64)"),
    ("str",            "📝  Строка (str)"),
    ("datetime64[ns]", "📅  Дата (datetime)"),
    ("bool",           "☑  Логический (bool)"),
]


class InspectorPanel(QWidget):
    """Инспектор справа. Виджеты переиспользуются."""

    column_updated = Signal(str, str, bool)   # name, display_name, visible
    column_cast_requested = Signal(str, str)  # name, new_dtype
    column_split_requested = Signal(str)      # name

    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self._current_column = None

        self._build_ui()
        self.show_empty()

    # ============================================================
    # UI — создаётся один раз
    # ============================================================

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── content ──
        self.content_widget = QWidget()
        self.content_widget.setStyleSheet("background: transparent;")
        cl = QVBoxLayout(self.content_widget)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(18)

        # ── Заголовок колонки ──
        self.header_label = QLabel()
        self.header_label.setStyleSheet(f"""
            color: {self.theme.text_main};
            font-size: 17px;
            font-weight: 700;
            padding: 0 0 4px 0;
            background: transparent;
        """)
        cl.addWidget(self.header_label)

        # ═══════════════════════════════════════════════════════════
        # НАСТРОЙКИ
        # ═══════════════════════════════════════════════════════════
        cl.addWidget(self._make_section("НАСТРОЙКИ"))

        lbl_name = QLabel("Отображаемое имя")
        lbl_name.setStyleSheet(f"""
            color: {self.theme.text_muted};
            font-size: 12px;
            background: transparent;
        """)
        cl.addWidget(lbl_name)

        self.edit_display_name = QLineEdit()
        self.edit_display_name.setStyleSheet(self._input_style())
        cl.addWidget(self.edit_display_name)

        self.check_visible = QCheckBox("Показывать в таблице")
        self.check_visible.setStyleSheet(f"""
            QCheckBox {{
                color: {self.theme.text_main};
                font-size: 13px;
                spacing: 10px;
                padding: 8px 0;
                background: transparent;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 1px solid {self.theme.border};
                background: {self.theme.bg_panel};
            }}
            QCheckBox::indicator:hover {{
                border: 1px solid {self.theme.primary};
            }}
            QCheckBox::indicator:checked {{
                background: {self.theme.primary};
                border: 1px solid {self.theme.primary};
            }}
        """)
        cl.addWidget(self.check_visible)

        # ═══════════════════════════════════════════════════════════
        # ТИП ДАННЫХ
        # ═══════════════════════════════════════════════════════════
        cl.addWidget(self._make_section("ТИП ДАННЫХ"))

        hint = QLabel("Преобразует значения колонки")
        hint.setStyleSheet(f"""
            color: {self.theme.text_muted};
            font-size: 12px;
            background: transparent;
        """)
        cl.addWidget(hint)

        self.combo_dtype = QComboBox()
        for key, title in DTYPE_OPTIONS:
            self.combo_dtype.addItem(title, key)
        self.combo_dtype.setStyleSheet(self._input_style())
        cl.addWidget(self.combo_dtype)

        self.btn_cast = QPushButton("Преобразовать")
        self.btn_cast.setCursor(Qt.PointingHandCursor)
        self.btn_cast.setStyleSheet(self._btn_outline_style())
        self.btn_cast.clicked.connect(self._on_cast)
        cl.addWidget(self.btn_cast)

        # ═══════════════════════════════════════════════════════════
        # ОПЕРАЦИИ
        # ═══════════════════════════════════════════════════════════
        cl.addWidget(self._make_section("ОПЕРАЦИИ"))

        self.btn_split = QPushButton("✂️   Разделить колонку")
        self.btn_split.setCursor(Qt.PointingHandCursor)
        self.btn_split.setStyleSheet(self._btn_outline_style())
        self.btn_split.clicked.connect(self._on_split)
        cl.addWidget(self.btn_split)

        # ═══════════════════════════════════════════════════════════
        # КНОПКИ
        # ═══════════════════════════════════════════════════════════
        btns = QWidget()
        btns.setStyleSheet("background: transparent;")
        bl = QHBoxLayout(btns)
        bl.setContentsMargins(0, 6, 0, 0)
        bl.setSpacing(8)

        self.btn_apply = QPushButton("Применить")
        self.btn_apply.setCursor(Qt.PointingHandCursor)
        self.btn_apply.setStyleSheet(f"""
            QPushButton {{
                background: {self.theme.primary};
                color: {self.theme.text_inverse};
                border: none;
                padding: 11px 16px;
                border-radius: 9px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background: #9ade4f; }}
            QPushButton:pressed {{ background: #6ea800; }}
        """)
        self.btn_apply.clicked.connect(self._on_apply)
        bl.addWidget(self.btn_apply)

        self.btn_reset = QPushButton("Сбросить")
        self.btn_reset.setCursor(Qt.PointingHandCursor)
        self.btn_reset.setStyleSheet(f"""
            QPushButton {{
                background: {self.theme.bg_panel};
                color: {self.theme.text_main};
                border: 1px solid {self.theme.border};
                padding: 11px 16px;
                border-radius: 9px;
                font-size: 13px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background: {self.theme.bg_hover};
                border: 1px solid {self.theme.text_muted};
            }}
        """)
        self.btn_reset.clicked.connect(self._on_reset)
        bl.addWidget(self.btn_reset)

        cl.addWidget(btns)
        cl.addStretch()

        root.addWidget(self.content_widget)

        # ── Пустое состояние ──
        self.empty_label = QLabel("Выберите колонку,\nчтобы увидеть её настройки")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setWordWrap(True)
        self.empty_label.setStyleSheet(f"""
            color: {self.theme.text_muted};
            font-size: 13px;
            padding: 40px 20px;
            background: transparent;
        """)
        root.addWidget(self.empty_label)

    # ============================================================
    # Утилиты стилей
    # ============================================================

    def _make_section(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"""
            color: {self.theme.text_muted};
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 1.2px;
            padding: 2px 0 2px 0;
            background: transparent;
        """)
        return lbl

    def _input_style(self) -> str:
        return f"""
            QLineEdit, QComboBox {{
                background: {self.theme.bg_panel};
                border: 1px solid {self.theme.border};
                border-radius: 8px;
                padding: 10px 12px;
                font-size: 13px;
                color: {self.theme.text_main};
            }}
            QLineEdit:focus, QComboBox:focus {{
                border: 1px solid {self.theme.primary};
            }}
            QComboBox::drop-down {{
                border: none;
                padding-right: 8px;
                width: 20px;
            }}
            QComboBox QAbstractItemView {{
                background: {self.theme.bg_card};
                border: 1px solid {self.theme.border};
                border-radius: 8px;
                selection-background-color: {self.theme.bg_panel};
                selection-color: {self.theme.text_main};
                color: {self.theme.text_main};
                padding: 6px;
                outline: none;
                font-size: 13px;
            }}
        """

    def _btn_outline_style(self) -> str:
        return f"""
            QPushButton {{
                background: {self.theme.bg_panel};
                color: {self.theme.primary};
                border: 1px solid {self.theme.primary};
                padding: 11px 14px;
                border-radius: 9px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {self.theme.primary_hover};
                color: {self.theme.primary};
            }}
            QPushButton:pressed {{
                background: {self.theme.bg_hover};
            }}
        """

    # ============================================================
    # Публичный API
    # ============================================================

    def current_column_name(self) -> str | None:
        if self._current_column is None:
            return None
        return self._current_column.get("name")

    def show_empty(self):
        self._current_column = None
        self.content_widget.hide()
        self.empty_label.show()

    def show_column(self, col_info: dict):
        """Обновляет значения виджетов. НЕ пересоздаёт их."""
        self._current_column = col_info

        self.empty_label.hide()
        self.content_widget.show()

        display_name = col_info.get("display_name", col_info["name"])
        dtype = col_info["dtype"]
        visible = col_info.get("visible", True)

        self.header_label.setText(f"📊  {display_name}")
        self.edit_display_name.setText(display_name)
        self.edit_display_name.setPlaceholderText(col_info["name"])
        self.check_visible.setChecked(visible)

        idx = 0
        for i, (key, _) in enumerate(DTYPE_OPTIONS):
            if key in dtype or dtype in key:
                idx = i
                break
        self.combo_dtype.setCurrentIndex(idx)

    # ============================================================
    # Обработчики
    # ============================================================

    def _on_apply(self):
        if self._current_column is None:
            return
        name = self._current_column["name"]
        display_name = self.edit_display_name.text().strip() or name
        visible = self.check_visible.isChecked()
        self.column_updated.emit(name, display_name, visible)

    def _on_cast(self):
        if self._current_column is None:
            return
        name = self._current_column["name"]
        new_dtype = self.combo_dtype.currentData()
        self.column_cast_requested.emit(name, new_dtype)

    def _on_split(self):
        if self._current_column is None:
            return
        name = self._current_column["name"]
        self.column_split_requested.emit(name)

    def _on_reset(self):
        if self._current_column is None:
            return
        col = self._current_column
        self.edit_display_name.setText(col.get("display_name", col["name"]))
        self.check_visible.setChecked(col.get("visible", True))