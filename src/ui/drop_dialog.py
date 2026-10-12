"""
Диалоги удаления дубликатов и строк с пустыми.
Современный вид: toggle-стиль, счётчик выбранных, чистые чекбоксы.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QCheckBox, QFrame, QScrollArea, QWidget,
    QRadioButton, QMessageBox, QSizePolicy
)
from PySide6.QtCore import Qt


def _dialog_qss(theme) -> str:
    return f"""
        QDialog {{
            background: {theme.bg_card};
        }}

        QLabel {{
            background: transparent;
            color: {theme.text_main};
            font-size: 13px;
        }}
        QLabel#title {{
            color: {theme.text_main};
            font-size: 18px;
            font-weight: 700;
            padding-bottom: 2px;
        }}
        QLabel#subtitle {{
            color: {theme.text_muted};
            font-size: 12px;
        }}
        QLabel#sectlabel {{
            color: {theme.text_muted};
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 1.2px;
        }}
        QLabel#counter {{
            color: {theme.primary};
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 1.2px;
        }}

        QFrame#divider {{
            background: {theme.border};
            max-height: 1px;
            border: none;
        }}

        /* ── Карточка со списком колонок ── */
        QFrame#card {{
            background: {theme.bg_panel};
            border: 1px solid {theme.border};
            border-radius: 12px;
        }}
        QScrollArea {{
            background: transparent;
            border: none;
        }}
        QScrollArea > QWidget > QWidget {{
            background: transparent;
        }}

        /* ── Чекбокс-переключатель «Все колонки» ── */
        QCheckBox#toggle {{
            color: {theme.text_main};
            font-size: 14px;
            font-weight: 600;
            spacing: 12px;
            padding: 14px 16px;
            background: {theme.bg_panel};
            border: 1px solid {theme.border};
            border-radius: 10px;
        }}
        QCheckBox#toggle:hover {{
            border: 1px solid {theme.primary_hover};
            background: {theme.bg_hover};
        }}
        QCheckBox#toggle::indicator {{
            width: 22px;
            height: 22px;
            border-radius: 6px;
            border: 2px solid {theme.border};
            background: {theme.bg_card};
        }}
        QCheckBox#toggle::indicator:hover {{
            border: 2px solid {theme.primary};
        }}
        QCheckBox#toggle::indicator:checked {{
            background: {theme.primary};
            border: 2px solid {theme.primary};
            image: none;
        }}

        /* ── Обычный чекбокс в списке ── */
        QCheckBox {{
            color: {theme.text_main};
            font-size: 13px;
            spacing: 10px;
            padding: 8px 10px;
            background: transparent;
            border-radius: 6px;
        }}
        QCheckBox:hover {{
            background: {theme.bg_hover};
        }}
        QCheckBox::indicator {{
            width: 18px;
            height: 18px;
            border-radius: 5px;
            border: 1px solid {theme.border};
            background: {theme.bg_card};
        }}
        QCheckBox::indicator:hover {{
            border: 1px solid {theme.primary};
        }}
        QCheckBox::indicator:checked {{
            background: {theme.primary};
            border: 1px solid {theme.primary};
            image: none;
        }}

        /* ── Radio ── */
        QRadioButton {{
            color: {theme.text_main};
            font-size: 13px;
            spacing: 12px;
            padding: 10px 12px;
            background: transparent;
            border-radius: 8px;
        }}
        QRadioButton:hover {{
            background: {theme.bg_hover};
        }}
        QRadioButton::indicator {{
            width: 18px;
            height: 18px;
            border-radius: 9px;
            border: 1px solid {theme.border};
            background: {theme.bg_card};
        }}
        QRadioButton::indicator:hover {{
            border: 1px solid {theme.primary};
        }}
        QRadioButton::indicator:checked {{
            background: {theme.primary};
            border: 5px solid {theme.primary};
        }}

        /* ── Кнопки ── */
        QPushButton#primary {{
            background: {theme.primary};
            color: #ffffff;
            border: none;
            padding: 11px 26px;
            border-radius: 10px;
            font-size: 13px;
            font-weight: 600;
            min-width: 120px;
        }}
        QPushButton#primary:hover {{ background: #6ea800; }}
        QPushButton#primary:pressed {{ background: #5c8f00; }}

        QPushButton#secondary {{
            background: transparent;
            color: {theme.text_main};
            border: 1px solid {theme.border};
            padding: 11px 26px;
            border-radius: 10px;
            font-size: 13px;
            font-weight: 500;
            min-width: 100px;
        }}
        QPushButton#secondary:hover {{
            background: {theme.bg_panel};
            border: 1px solid {theme.text_muted};
        }}

        QPushButton#pill {{
            background: {theme.bg_panel};
            color: {theme.text_main};
            border: 1px solid {theme.border};
            padding: 6px 14px;
            border-radius: 14px;
            font-size: 11px;
            font-weight: 500;
        }}
        QPushButton#pill:hover {{
            background: {theme.primary_hover};
            color: {theme.primary_dark};
            border: 1px solid {theme.primary_hover};
        }}

        /* ── Скроллбар ── */
        QScrollBar:vertical {{
            background: transparent;
            width: 10px;
            border: none;
            margin: 6px 2px 6px 0;
        }}
        QScrollBar::handle:vertical {{
            background: {theme.border};
            min-height: 40px;
            border-radius: 5px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {theme.primary};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0; background: none; border: none;
        }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
            background: transparent;
        }}
    """


# ============================================================
# Базовый класс
# ============================================================

class _BaseDropDialog(QDialog):
    """Общая логика: чекбокс-переключатель + показ/скрытие списка."""

    def __init__(self, theme, columns, display_names, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.columns = list(columns)
        self.display_names = dict(display_names or {})
        self.selected_columns: list[str] = []
        self.use_all: bool = True

        self.setModal(True)
        self.setMinimumWidth(520)
        self.setStyleSheet(_dialog_qss(theme))

    # ------------------------------------------------------------
    # Секция со списком колонок
    # ------------------------------------------------------------

    def _build_columns_section(self, layout):
        """Скрываемая секция: заголовок + счётчик + карточка + пилюли."""

        self.columns_section = QWidget()
        cs_layout = QVBoxLayout(self.columns_section)
        cs_layout.setContentsMargins(0, 0, 0, 0)
        cs_layout.setSpacing(10)

        # ── Шапка: КОЛОНКИ + счётчик ──
        header_row = QHBoxLayout()
        header_row.setContentsMargins(4, 0, 4, 0)
        header_row.setSpacing(8)

        sect_cols = QLabel("КОЛОНКИ")
        sect_cols.setObjectName("sectlabel")
        header_row.addWidget(sect_cols)

        header_row.addStretch()

        self.label_counter = QLabel("0 ИЗ 0")
        self.label_counter.setObjectName("counter")
        header_row.addWidget(self.label_counter)

        cs_layout.addLayout(header_row)

        # ── Карточка со списком ──
        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(6, 6, 6, 6)
        card_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setMinimumHeight(240)
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(4, 4, 4, 4)
        container_layout.setSpacing(0)

        self.checkboxes = {}
        for col in self.columns:
            display = self.display_names.get(col, col)
            cb = QCheckBox(str(display))
            cb.setChecked(True)
            cb.toggled.connect(self._update_counter)
            self.checkboxes[col] = cb
            container_layout.addWidget(cb)

        container_layout.addStretch()
        scroll.setWidget(container)
        card_layout.addWidget(scroll)

        cs_layout.addWidget(card, stretch=1)

        # ── Пилюли «Выделить все / Снять все» ──
        pill_row = QHBoxLayout()
        pill_row.setContentsMargins(0, 0, 0, 0)
        pill_row.setSpacing(8)

        btn_select_all = QPushButton("Выделить все")
        btn_select_all.setObjectName("pill")
        btn_select_all.setCursor(Qt.PointingHandCursor)
        btn_select_all.clicked.connect(lambda: self._set_all(True))
        pill_row.addWidget(btn_select_all)

        btn_deselect = QPushButton("Снять все")
        btn_deselect.setObjectName("pill")
        btn_deselect.setCursor(Qt.PointingHandCursor)
        btn_deselect.clicked.connect(lambda: self._set_all(False))
        pill_row.addWidget(btn_deselect)

        pill_row.addStretch()
        cs_layout.addLayout(pill_row)

        layout.addWidget(self.columns_section)

    # ------------------------------------------------------------
    # Логика
    # ------------------------------------------------------------

    def _on_all_toggled(self, checked: bool):
        self.columns_section.setVisible(not checked)

        self.layout().activate()

        if checked:
            self.setMinimumHeight(0)
            self.adjustSize()
        else:
            self.setMinimumHeight(620)
            self.adjustSize()

    def _set_all(self, state: bool):
        for cb in self.checkboxes.values():
            cb.setChecked(state)
        self._update_counter()

    def _update_counter(self):
        if not hasattr(self, "label_counter"):
            return
        total = len(self.checkboxes)
        selected = sum(1 for cb in self.checkboxes.values() if cb.isChecked())
        self.label_counter.setText(f"{selected} ИЗ {total}")

    def _validate_and_accept(self):
        if self.chk_all.isChecked():
            self.use_all = True
            self.selected_columns = list(self.columns)
            self.accept()
            return

        selected = [c for c, cb in self.checkboxes.items() if cb.isChecked()]
        if not selected:
            QMessageBox.warning(
                self, "Не выбрано",
                "Отметьте хотя бы одну колонку или включите «Все колонки»."
            )
            return

        self.use_all = False
        self.selected_columns = selected
        self.accept()


# ============================================================
# Удаление дубликатов
# ============================================================

class DropDuplicatesDialog(_BaseDropDialog):

    def __init__(self, theme, columns: list, display_names: dict, parent=None):
        super().__init__(theme, columns, display_names, parent)
        self.setWindowTitle("Удалить дубликаты")
        self.setMinimumHeight(0)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)

        # ── Заголовок ──
        title = QLabel("Удалить дубликаты")
        title.setObjectName("title")
        layout.addWidget(title)

        subtitle = QLabel(
            "Строки с одинаковыми значениями в выбранных колонках будут удалены."
        )
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        layout.addWidget(self._divider())

        # ── Переключатель «Все колонки» ──
        self.chk_all = QCheckBox("Все колонки")
        self.chk_all.setObjectName("toggle")
        self.chk_all.setChecked(True)
        self.chk_all.toggled.connect(self._on_all_toggled)
        layout.addWidget(self.chk_all)

        # ── Список колонок ──
        self._build_columns_section(layout)

        # ── Кнопки ──
        layout.addLayout(self._build_buttons("Удалить"))

        self.columns_section.setVisible(False)
        self._update_counter()

    # ----------

    def _divider(self) -> QFrame:
        d = QFrame()
        d.setObjectName("divider")
        d.setFrameShape(QFrame.HLine)
        return d

    def _build_buttons(self, ok_text: str) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)
        row.addStretch()

        btn_cancel = QPushButton("Отмена")
        btn_cancel.setObjectName("secondary")
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)
        row.addWidget(btn_cancel)

        btn_ok = QPushButton(ok_text)
        btn_ok.setObjectName("primary")
        btn_ok.setCursor(Qt.PointingHandCursor)
        btn_ok.clicked.connect(self._on_ok)
        btn_ok.setDefault(True)
        row.addWidget(btn_ok)

        return row

    def _on_ok(self):
        self._validate_and_accept()


# ============================================================
# Удаление строк с пустыми
# ============================================================

class DropNaDialog(_BaseDropDialog):

    def __init__(self, theme, columns: list, display_names: dict, parent=None):
        super().__init__(theme, columns, display_names, parent)
        self.setWindowTitle("Удалить строки с пустыми")
        self.setMinimumHeight(0)

        self.how: str = "any"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)

        # ── Заголовок ──
        title = QLabel("Удалить строки с пустыми")
        title.setObjectName("title")
        layout.addWidget(title)

        subtitle = QLabel(
            "Выберите колонки и режим удаления строк с пустыми значениями."
        )
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        layout.addWidget(self._divider())

        # ── Режим ──
        sect_mode = QLabel("РЕЖИМ УДАЛЕНИЯ")
        sect_mode.setObjectName("sectlabel")
        layout.addWidget(sect_mode)

        mode_card = QFrame()
        mode_card.setObjectName("card")
        mc_layout = QVBoxLayout(mode_card)
        mc_layout.setContentsMargins(6, 6, 6, 6)
        mc_layout.setSpacing(2)

        self.radio_any = QRadioButton(
            "Удалить, если пусто хотя бы в одной из выбранных"
        )
        self.radio_any.setChecked(True)
        mc_layout.addWidget(self.radio_any)

        self.radio_all = QRadioButton(
            "Удалить, если пусто во всех выбранных"
        )
        mc_layout.addWidget(self.radio_all)

        layout.addWidget(mode_card)

        # ── Переключатель «Все колонки» ──
        self.chk_all = QCheckBox("Все колонки")
        self.chk_all.setObjectName("toggle")
        self.chk_all.setChecked(True)
        self.chk_all.toggled.connect(self._on_all_toggled)
        layout.addWidget(self.chk_all)

        # ── Список колонок ──
        self._build_columns_section(layout)

        # ── Кнопки ──
        layout.addLayout(self._build_buttons("Удалить"))

        self.columns_section.setVisible(False)
        self._update_counter()

    # ----------

    def _divider(self) -> QFrame:
        d = QFrame()
        d.setObjectName("divider")
        d.setFrameShape(QFrame.HLine)
        return d

    def _build_buttons(self, ok_text: str) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)
        row.addStretch()

        btn_cancel = QPushButton("Отмена")
        btn_cancel.setObjectName("secondary")
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)
        row.addWidget(btn_cancel)

        btn_ok = QPushButton(ok_text)
        btn_ok.setObjectName("primary")
        btn_ok.setCursor(Qt.PointingHandCursor)
        btn_ok.clicked.connect(self._on_ok)
        btn_ok.setDefault(True)
        row.addWidget(btn_ok)

        return row

    def _on_ok(self):
        self.how = "any" if self.radio_any.isChecked() else "all"
        self._validate_and_accept()