"""
Диалоги для работы с проектом .eaproj:
  • SaveProjectDialog — сохранение с опцией пароля
  • OpenProjectPasswordDialog — ввод пароля при открытии
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QCheckBox, QPushButton, QMessageBox, QFrame
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
            font-size: 12px;
        }}

        QLabel#title {{
            color: {theme.primary};
            font-size: 16px;
            font-weight: 700;
            padding-bottom: 2px;
        }}

        QLabel#subtitle {{
            color: {theme.text_muted};
            font-size: 12px;
        }}

        QLabel#fieldlabel {{
            color: {theme.text_muted};
            font-size: 11px;
            font-weight: 600;
            letter-spacing: 0.3px;
            padding-left: 4px;
        }}

        QLabel#error {{
            color: #e74c3c;
            font-size: 12px;
        }}

        QFrame#divider {{
            background: {theme.border};
            max-height: 1px;
            border: none;
        }}

        /* ── Поля ввода — крупные, скруглённые ── */
        QLineEdit {{
            background: {theme.bg_panel};
            color: {theme.text_main};
            border: 1px solid transparent;
            border-radius: 18px;
            padding: 12px 18px;
            font-size: 13px;
            selection-background-color: {theme.primary_hover};
            selection-color: {theme.primary_dark};
        }}
        QLineEdit:hover {{
            border: 1px solid {theme.border};
        }}
        QLineEdit:focus {{
            border: 1px solid {theme.primary};
            background: {theme.bg_card};
        }}

        QCheckBox {{
            color: {theme.text_main};
            font-size: 13px;
            spacing: 10px;
            padding: 6px 0;
            background: transparent;
        }}
        QCheckBox::indicator {{
            width: 20px;
            height: 20px;
            border-radius: 6px;
            border: 1px solid {theme.border};
            background: {theme.bg_panel};
        }}
        QCheckBox::indicator:hover {{
            border: 1px solid {theme.primary};
        }}
        QCheckBox::indicator:checked {{
            background: {theme.primary};
            border: 1px solid {theme.primary};
        }}

        QPushButton#primary {{
            background: {theme.primary};
            color: #ffffff;
            border: none;
            padding: 10px 22px;
            border-radius: 18px;
            font-size: 13px;
            font-weight: 600;
            min-width: 110px;
        }}
        QPushButton#primary:hover {{
            background: #6ea800;
        }}
        QPushButton#primary:pressed {{
            background: #5c8f00;
        }}

        QPushButton#secondary {{
            background: transparent;
            color: {theme.text_main};
            border: 1px solid {theme.border};
            padding: 10px 22px;
            border-radius: 18px;
            font-size: 13px;
            min-width: 90px;
        }}
        QPushButton#secondary:hover {{
            background: {theme.bg_panel};
            border: 1px solid {theme.primary_hover};
        }}
        QPushButton#secondary:pressed {{
            background: {theme.primary_hover};
        }}
    """


# ============================================================
# Сохранение проекта
# ============================================================

class SaveProjectDialog(QDialog):
    """
    Спрашивает: защитить паролем или сохранить для этой машины.
    self.password (str | None), self.mode ("password" | "machine")
    """

    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.password: str | None = None
        self.mode: str = "machine"

        self.setWindowTitle("Сохранить проект")
        self.setModal(True)
        self.setMinimumWidth(460)
        self.setStyleSheet(_dialog_qss(theme))

        self._build_ui()
        # после сборки подгоняем размер под содержимое
        self.adjustSize()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)

        # ── Заголовок ──
        title = QLabel("Сохранение проекта .eaproj")
        title.setObjectName("title")
        layout.addWidget(title)

        subtitle = QLabel(
            "Проект будет зашифрован.\n"
            "• Для этой машины — откроется только на этом ПК.\n"
            "• С паролем — откроется где угодно при вводе пароля."
        )
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        # ── Разделитель ──
        line = QFrame()
        line.setObjectName("divider")
        line.setFrameShape(QFrame.HLine)
        layout.addWidget(line)

        # ── Чекбокс ──
        self.chk_password = QCheckBox("Защитить паролем")
        self.chk_password.toggled.connect(self._on_toggle)
        layout.addWidget(self.chk_password)

        # ── Поля пароля (без обёртки, напрямую) ──
        self.lbl_pass = QLabel("ПАРОЛЬ")
        self.lbl_pass.setObjectName("fieldlabel")
        layout.addWidget(self.lbl_pass)

        self.edit_pass = QLineEdit()
        self.edit_pass.setEchoMode(QLineEdit.Password)
        self.edit_pass.setPlaceholderText("Введите пароль")
        layout.addWidget(self.edit_pass)

        self.lbl_pass2 = QLabel("ПОВТОРИТЕ ПАРОЛЬ")
        self.lbl_pass2.setObjectName("fieldlabel")
        layout.addWidget(self.lbl_pass2)

        self.edit_pass2 = QLineEdit()
        self.edit_pass2.setEchoMode(QLineEdit.Password)
        self.edit_pass2.setPlaceholderText("Повторите пароль")
        self.edit_pass2.returnPressed.connect(self._on_save)
        layout.addWidget(self.edit_pass2)

        # Стартовое состояние — скрыты
        self._set_fields_visible(False)

        # ── Кнопки ──
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addStretch()

        btn_cancel = QPushButton("Отмена")
        btn_cancel.setObjectName("secondary")
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)
        row.addWidget(btn_cancel)

        btn_save = QPushButton("Сохранить")
        btn_save.setObjectName("primary")
        btn_save.setCursor(Qt.PointingHandCursor)
        btn_save.clicked.connect(self._on_save)
        row.addWidget(btn_save)

        layout.addLayout(row)

    def _set_fields_visible(self, visible: bool):
        """Показать/скрыть все поля пароля."""
        self.lbl_pass.setVisible(visible)
        self.edit_pass.setVisible(visible)
        self.lbl_pass2.setVisible(visible)
        self.edit_pass2.setVisible(visible)

    def _on_toggle(self, checked: bool):
        self._set_fields_visible(checked)

        # Пересчитываем размер окна
        self.layout().activate()
        self.adjustSize()

        # Плавно пересчитываем минимальную высоту
        hint = self.sizeHint()
        self.resize(self.width(), max(hint.height(), 200))

        if checked:
            self.edit_pass.setFocus()

    def _on_save(self):
        if not self.chk_password.isChecked():
            self.mode = "machine"
            self.password = None
            self.accept()
            return

        p1 = self.edit_pass.text()
        p2 = self.edit_pass2.text()

        if not p1:
            QMessageBox.warning(self, "Пароль пустой", "Введите пароль")
            self.edit_pass.setFocus()
            return
        if len(p1) < 4:
            QMessageBox.warning(self, "Слабый пароль", "Минимум 4 символа")
            self.edit_pass.setFocus()
            return
        if p1 != p2:
            QMessageBox.warning(self, "Ошибка", "Пароли не совпадают")
            self.edit_pass2.clear()
            self.edit_pass2.setFocus()
            return

        self.mode = "password"
        self.password = p1
        self.accept()


# ============================================================
# Ввод пароля при открытии
# ============================================================

class OpenProjectPasswordDialog(QDialog):
    """Запрос пароля для открытия .eaproj."""

    def __init__(self, theme, file_name: str, error: str = "", parent=None):
        super().__init__(parent)
        self.theme = theme
        self.password: str | None = None

        self.setWindowTitle("Открыть проект")
        self.setModal(True)
        self.setMinimumWidth(440)
        self.setStyleSheet(_dialog_qss(theme))

        self._build_ui(file_name, error)

    def _build_ui(self, file_name: str, error: str):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)

        title = QLabel(f"🔒  {file_name}")
        title.setObjectName("title")
        title.setWordWrap(True)
        layout.addWidget(title)

        subtitle = QLabel("Проект защищён паролем. Введите его, чтобы открыть.")
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        if error:
            err_lbl = QLabel(error)
            err_lbl.setObjectName("error")
            err_lbl.setWordWrap(True)
            layout.addWidget(err_lbl)

        line = QFrame()
        line.setObjectName("divider")
        line.setFrameShape(QFrame.HLine)
        layout.addWidget(line)

        self.lbl_pass = QLabel("ПАРОЛЬ")
        self.lbl_pass.setObjectName("fieldlabel")
        layout.addWidget(self.lbl_pass)

        self.edit_pass = QLineEdit()
        self.edit_pass.setEchoMode(QLineEdit.Password)
        self.edit_pass.setPlaceholderText("Введите пароль")
        self.edit_pass.returnPressed.connect(self._on_ok)
        layout.addWidget(self.edit_pass)

        row = QHBoxLayout()
        row.setSpacing(10)
        row.addStretch()

        btn_cancel = QPushButton("Отмена")
        btn_cancel.setObjectName("secondary")
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)
        row.addWidget(btn_cancel)

        btn_ok = QPushButton("Открыть")
        btn_ok.setObjectName("primary")
        btn_ok.setCursor(Qt.PointingHandCursor)
        btn_ok.clicked.connect(self._on_ok)
        row.addWidget(btn_ok)

        layout.addLayout(row)

        self.edit_pass.setFocus()

    def _on_ok(self):
        if self.mode == "save":
            name = self.edit_name.text().strip()
            if not name:
                return
            if self.default_ext and not name.lower().endswith(self.default_ext.lower()):
                name += self.default_ext
            full = Path(self.current_dir) / name
            self.selected_path = str(full)
            self.accept()
            return

        # ── open ──
        items = self.files_list.selectedItems()
        if not items:
            return

        it = items[0]
        kind = it.data(Qt.UserRole + 1)
        path = it.data(Qt.UserRole)

        if kind == "file":
            self.selected_path = path
            self.accept()
            return

        if kind == "folder":
            # ★ Одинарный клик по папке + «Открыть» = импорт папки целиком.
            # Заход внутрь — только двойным кликом.
            self.selected_path = path
            self.accept()
            return