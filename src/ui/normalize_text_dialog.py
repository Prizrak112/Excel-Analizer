"""
Диалог нормализации текстовых данных.

Открывается из меню «Данные» → «🔤 Нормализовать текст…».

Позволяет выбрать колонки, направление замены букв,
набор опций (верхний регистр, удаление пробелов, удаление спецсимволов).
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QCheckBox, QRadioButton, QPushButton, QButtonGroup,
    QScrollArea, QWidget, QFrame, QSizePolicy,
)
from PySide6.QtCore import Qt

from src.ui.toast import ToastManager


# Спецсимволы, которые пользователь может удалять
SPECIAL_CHARS = [
    (".", "точка"),
    (",", "запятая"),
    ("-", "дефис"),
    ("№", "номер"),
    ("(", "скобка ("),
    (")", "скобка )"),
    ("_", "подчёркивание"),
    ("/", "слэш"),
    ("\\", "обратный слэш"),
    ("*", "звёздочка"),
]


class NormalizeTextDialog(QDialog):
    """Диалог нормализации текстовых данных."""

    def __init__(self, theme, columns: list[str], display_names: dict | None = None,
                 parent=None):
        super().__init__(parent)
        self.theme = theme
        self._columns = list(columns)               # имена настоящих колонок
        self._display_names = display_names or {}   # {col_name: display}

        # Результат — заполняется в _on_apply
        self.result_data: dict | None = None

        self._col_checkboxes: dict[str, QCheckBox] = {}
        self._char_checkboxes: dict[str, QCheckBox] = {}

        self.setWindowTitle("Нормализовать текст")
        self.setMinimumSize(560, 640)
        self.resize(580, 720)
        self.setStyleSheet(f"QDialog {{ background: {self.theme.bg_card}; }}")

        self._build_ui()
        self._apply_styles()

    # ============================================================
    # UI
    # ============================================================

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(10)

        # ── Заголовок ──
        title = QLabel("🔤  Нормализовать текст")
        title.setStyleSheet(
            f"color:{self.theme.primary}; font-size:15px; font-weight:700;"
        )
        root.addWidget(title)

        hint = QLabel(
            "Заменяет буквы между латиницей и кириллицей, приводит к верхнему "
            "регистру, удаляет пробелы и спецсимволы. Рядом с исходной колонкой "
            "появятся «…_нормализовано» и (если есть проблемы) «…_ошибки»."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(
            f"color:{self.theme.text_muted}; font-size:12px;"
        )
        root.addWidget(hint)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background:{self.theme.border}; border:none;")
        root.addWidget(sep)

        # ════════════════════════════════════════════════════════
        # КОЛОНКИ
        # ════════════════════════════════════════════════════════
        root.addWidget(self._section_label("Колонки для обработки"))

        cols_toolbar = QHBoxLayout()
        cols_toolbar.setSpacing(6)

        b_all = QPushButton("Все")
        b_all.setCursor(Qt.PointingHandCursor)
        b_all.setStyleSheet(self._btn_small())
        b_all.clicked.connect(self._select_all)
        cols_toolbar.addWidget(b_all)

        b_none = QPushButton("Снять")
        b_none.setCursor(Qt.PointingHandCursor)
        b_none.setStyleSheet(self._btn_small())
        b_none.clicked.connect(self._deselect_all)
        cols_toolbar.addWidget(b_none)

        cols_toolbar.addStretch()
        root.addLayout(cols_toolbar)

        # Прокручиваемый список колонок
        cols_scroll = QScrollArea()
        cols_scroll.setWidgetResizable(True)
        cols_scroll.setFrameShape(QFrame.NoFrame)
        cols_scroll.setStyleSheet(
            f"QScrollArea {{ background:{self.theme.bg_panel}; "
            f"border:1px solid {self.theme.border}; border-radius:6px; }}"
        )
        cols_scroll.setMinimumHeight(140)

        cols_container = QWidget()
        cols_container.setStyleSheet(f"background:{self.theme.bg_panel};")
        cols_v = QVBoxLayout(cols_container)
        cols_v.setContentsMargins(10, 8, 10, 8)
        cols_v.setSpacing(4)

        if not self._columns:
            empty = QLabel("Нет доступных колонок.")
            empty.setStyleSheet(
                f"color:{self.theme.text_muted}; font-size:12px;"
            )
            cols_v.addWidget(empty)
        else:
            for col in self._columns:
                display = self._display_names.get(col, col)
                label = f"{display}" if display == col else f"{display}  ({col})"
                cb = QCheckBox(label)
                cb.setStyleSheet(self._checkbox_qss())
                cb.setChecked(True)  # по умолчанию выбраны все
                self._col_checkboxes[col] = cb
                cols_v.addWidget(cb)

        cols_v.addStretch()
        cols_scroll.setWidget(cols_container)
        root.addWidget(cols_scroll)

        # ════════════════════════════════════════════════════════
        # НАПРАВЛЕНИЕ ЗАМЕНЫ
        # ════════════════════════════════════════════════════════
        root.addWidget(self._section_label("Направление замены букв"))

        dir_row = QHBoxLayout()
        dir_row.setSpacing(16)

        self._dir_group = QButtonGroup(self)
        self._rb_lat2cyr = QRadioButton("Латиница → Кириллица  (A→А, B→В, …)")
        self._rb_lat2cyr.setChecked(True)
        self._rb_lat2cyr.setStyleSheet(self._radio_qss())
        self._dir_group.addButton(self._rb_lat2cyr, 0)
        dir_row.addWidget(self._rb_lat2cyr)

        self._rb_cyr2lat = QRadioButton("Кириллица → Латиница  (А→A, В→B, …)")
        self._rb_cyr2lat.setStyleSheet(self._radio_qss())
        self._dir_group.addButton(self._rb_cyr2lat, 1)
        dir_row.addWidget(self._rb_cyr2lat)

        dir_row.addStretch()
        root.addLayout(dir_row)

        # ════════════════════════════════════════════════════════
        # ОПЦИИ
        # ════════════════════════════════════════════════════════
        root.addWidget(self._section_label("Опции обработки"))

        self._cb_upper = QCheckBox("Привести к верхнему регистру")
        self._cb_upper.setChecked(True)
        self._cb_upper.setStyleSheet(self._checkbox_qss())
        root.addWidget(self._cb_upper)

        self._cb_spaces = QCheckBox("Удалить пробелы")
        self._cb_spaces.setChecked(True)
        self._cb_spaces.setStyleSheet(self._checkbox_qss())
        root.addWidget(self._cb_spaces)

        # ── Мастер-галочка спецсимволов ──
        self._cb_all_special = QCheckBox("Удалить все спецсимволы")
        self._cb_all_special.setChecked(True)
        self._cb_all_special.setStyleSheet(self._checkbox_qss())
        self._cb_all_special.toggled.connect(self._on_master_special_toggled)
        root.addWidget(self._cb_all_special)

        # ── Отдельные символы (сетка 5x2) ──
        chars_panel = QWidget()
        chars_panel.setStyleSheet("background: transparent;")
        chars_grid = QGridLayout(chars_panel)
        chars_grid.setContentsMargins(20, 2, 0, 0)
        chars_grid.setHorizontalSpacing(12)
        chars_grid.setVerticalSpacing(4)

        for i, (ch, name) in enumerate(SPECIAL_CHARS):
            cb = QCheckBox(f"{ch}  —  {name}")
            cb.setChecked(True)
            cb.setStyleSheet(self._checkbox_qss())
            cb.toggled.connect(self._on_char_toggled)
            self._char_checkboxes[ch] = cb
            row = i // 2
            col = i % 2
            chars_grid.addWidget(cb, row, col)

        root.addWidget(chars_panel)
        root.addStretch()

        # ════════════════════════════════════════════════════════
        # КНОПКИ
        # ════════════════════════════════════════════════════════
        btns = QHBoxLayout()
        btns.setSpacing(8)
        btns.addStretch()

        b_cancel = QPushButton("Отмена")
        b_cancel.setCursor(Qt.PointingHandCursor)
        b_cancel.setStyleSheet(self._btn_secondary())
        b_cancel.clicked.connect(self.reject)
        btns.addWidget(b_cancel)

        b_apply = QPushButton("Применить")
        b_apply.setCursor(Qt.PointingHandCursor)
        b_apply.setDefault(True)
        b_apply.setStyleSheet(self._btn_primary())
        b_apply.clicked.connect(self._on_apply)
        btns.addWidget(b_apply)

        root.addLayout(btns)

    # ============================================================
    # Вспомогательные построители
    # ============================================================

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text.upper())
        lbl.setStyleSheet(
            f"color:{self.theme.text_muted}; font-size:10px; font-weight:700;"
            f"letter-spacing:0.5px; padding-top:6px;"
        )
        return lbl

    # ============================================================
    # Логика кнопок
    # ============================================================

    def _select_all(self):
        for cb in self._col_checkboxes.values():
            cb.setChecked(True)

    def _deselect_all(self):
        for cb in self._col_checkboxes.values():
            cb.setChecked(False)

    def _on_master_special_toggled(self, checked: bool):
        """Мастер-галочка «Удалить все спецсимволы»."""
        for cb in self._char_checkboxes.values():
            cb.blockSignals(True)
            cb.setChecked(checked)
            cb.blockSignals(False)

    def _on_char_toggled(self, _checked: bool):
        """Отдельный символ изменён — обновить мастер-галочку."""
        all_on = all(cb.isChecked() for cb in self._char_checkboxes.values())
        any_on = any(cb.isChecked() for cb in self._char_checkboxes.values())
        self._cb_all_special.blockSignals(True)
        self._cb_all_special.setChecked(all_on)
        self._cb_all_special.blockSignals(False)
        # Визуально «полу-галочку» Qt не умеет — оставим просто unchecked.

    # ============================================================
    # Применение
    # ============================================================

    def _on_apply(self):
        # ── Колонки ──
        selected_cols = [
            col for col, cb in self._col_checkboxes.items()
            if cb.isChecked()
        ]
        if not selected_cols:
            ToastManager.warning(
                "Не выбрано колонок",
                "Отметьте хотя бы одну колонку для обработки",
                self.theme,
            )
            return

        # ── Направление ──
        direction = "lat2cyr" if self._rb_lat2cyr.isChecked() else "cyr2lat"

        # ── Опции ──
        upper = self._cb_upper.isChecked()
        remove_spaces = self._cb_spaces.isChecked()

        remove_chars = {
            ch for ch, cb in self._char_checkboxes.items() if cb.isChecked()
        }

        self.result_data = {
            "columns": selected_cols,
            "direction": direction,
            "upper": upper,
            "remove_spaces": remove_spaces,
            "remove_chars": remove_chars,
        }
        self.accept()

    # ============================================================
    # Стили
    # ============================================================

    def _apply_styles(self):
        pass  # все стили заданы inline

    def _checkbox_qss(self) -> str:
        return (
            f"QCheckBox {{ color:{self.theme.text_main}; font-size:12px;"
            f"padding:3px 0; spacing:6px; background:transparent; }}"
        )

    def _radio_qss(self) -> str:
        return (
            f"QRadioButton {{ color:{self.theme.text_main}; font-size:12px;"
            f"padding:3px 0; spacing:6px; background:transparent; }}"
        )

    def _btn_small(self) -> str:
        return f"""
            QPushButton {{
                background: {self.theme.bg_panel};
                color: {self.theme.text_main};
                border: 1px solid {self.theme.border};
                border-radius: 4px;
                padding: 4px 14px;
                font-size: 12px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background: {self.theme.primary_hover};
                border-color: {self.theme.primary};
            }}
        """

    def _btn_primary(self) -> str:
        return f"""
            QPushButton {{
                background: {self.theme.primary};
                color: {self.theme.text_inverse};
                border: none;
                padding: 8px 22px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background: #6ea800; }}
        """

    def _btn_secondary(self) -> str:
        return f"""
            QPushButton {{
                background: transparent;
                color: {self.theme.text_main};
                border: 1px solid {self.theme.border};
                padding: 8px 22px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background: {self.theme.primary_hover};
                border-color: {self.theme.primary};
            }}
        """