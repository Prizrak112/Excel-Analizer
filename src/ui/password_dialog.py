"""
Диалог ввода и установки пароля.
Показывается при первом запуске и при последующих.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFrame, QMessageBox
)
from PySide6.QtCore import Qt


# Email для связи при блокировке
CONTACT_EMAIL = "v.ragimov@agroeco.ru"


class PasswordDialog(QDialog):
    """
    Диалог пароля.
    Режимы:
      - "setup" — первая установка пароля (пароль + подтверждение)
      - "login" — ввод пароля (3 попытки)
    """
    
    MAX_ATTEMPTS = 3
    
    def __init__(self, security, theme, mode: str = "login", parent=None):
        super().__init__(parent)
        
        self.security = security
        self.theme = theme
        self.mode = mode
        self.attempts = 0
        
        self.setWindowTitle("Excel Analyzer — Защита")
        self.setFixedSize(440, 340 if mode == "login" else 400)
        self.setWindowFlags(
            Qt.Dialog |
            Qt.WindowCloseButtonHint |
            Qt.CustomizeWindowHint
        )
        
        self.setStyleSheet(f"""
            QDialog {{
                background: {self.theme.bg_card};
            }}
            QLabel {{
                color: {self.theme.text_main};
            }}
            QLineEdit {{
                background: {self.theme.bg_panel};
                border: 1px solid {self.theme.border};
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
                color: {self.theme.text_main};
            }}
            QLineEdit:focus {{
                border: 1px solid {self.theme.primary};
            }}
        """)
        
        self._build_ui()
    
    # ============================================================
    # UI
    # ============================================================
    
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 25, 30, 25)
        layout.setSpacing(10)
        
        # Иконка
        icon = QLabel("🔒" if self.mode == "login" else "🔐")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("font-size: 42px;")
        layout.addWidget(icon)
        
        # Заголовок
        title_text = "Введите пароль" if self.mode == "login" else "Установите пароль"
        title = QLabel(title_text)
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(f"""
            color: {self.theme.primary_dark};
            font-size: 16px;
            font-weight: bold;
        """)
        layout.addWidget(title)
        
        # Подзаголовок
        if self.mode == "login":
            subtitle_text = f"Попыток осталось: {self.MAX_ATTEMPTS - self.attempts}"
        else:
            subtitle_text = "Пароль будет запрашиваться\nпри каждом запуске приложения"
        subtitle = QLabel(subtitle_text)
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet(f"""
            color: {self.theme.text_muted};
            font-size: 11px;
            margin-bottom: 6px;
        """)
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        
        self.subtitle = subtitle
        
        # Разделитель
        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setStyleSheet(f"background: {self.theme.border}; max-height: 1px;")
        layout.addWidget(divider)
        
        # Пароль
        label_pwd = QLabel("Пароль:")
        label_pwd.setStyleSheet(f"color: {self.theme.text_muted}; font-size: 11px;")
        layout.addWidget(label_pwd)
        
        self.edit_password = QLineEdit()
        self.edit_password.setEchoMode(QLineEdit.Password)
        self.edit_password.setPlaceholderText("••••••••")
        self.edit_password.returnPressed.connect(self._on_submit)
        layout.addWidget(self.edit_password)
        
        # Подтверждение (только для setup)
        if self.mode == "setup":
            label_confirm = QLabel("Подтвердите пароль:")
            label_confirm.setStyleSheet(f"color: {self.theme.text_muted}; font-size: 11px;")
            layout.addWidget(label_confirm)
            
            self.edit_confirm = QLineEdit()
            self.edit_confirm.setEchoMode(QLineEdit.Password)
            self.edit_confirm.setPlaceholderText("••••••••")
            self.edit_confirm.returnPressed.connect(self._on_submit)
            layout.addWidget(self.edit_confirm)
        else:
            self.edit_confirm = None
        
        # Сообщение об ошибке
        self.error_label = QLabel("")
        self.error_label.setAlignment(Qt.AlignCenter)
        self.error_label.setStyleSheet(f"""
            color: #e74c3c;
            font-size: 11px;
            font-weight: 600;
        """)
        self.error_label.setVisible(False)
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)
        
        layout.addStretch()
        
        # Кнопки
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        
        btn_cancel = QPushButton("Отмена")
        btn_cancel.setAutoDefault(False)  # ← Не срабатывает на Enter
        btn_cancel.setDefault(False)      # ← Не default
        btn_cancel.setStyleSheet(f"""
            QPushButton {{
                background: {self.theme.bg_panel};
                color: {self.theme.primary_text};
                border: 1px solid {self.theme.border};
                padding: 8px 16px;
                border-radius: 5px;
                font-size: 13px;
                font-weight: 500;
            }}
            QPushButton:hover {{ background: {self.theme.primary_hover}; }}
        """)
        btn_cancel.clicked.connect(self.reject)
        buttons.addWidget(btn_cancel)
        
        buttons.addStretch()
        
        self.btn_submit = QPushButton("Войти" if self.mode == "login" else "Установить")
        self.btn_submit.setDefault(True)  # ← Enter вызывает эту кнопку
        self.btn_submit.setAutoDefault(True)
        self.btn_submit.setStyleSheet(f"""
            QPushButton {{
                background: {self.theme.primary};
                color: white;
                border: none;
                padding: 8px 20px;
                border-radius: 5px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background: #6ea800; }}
        """)
        self.btn_submit.clicked.connect(self._on_submit)
        buttons.addWidget(self.btn_submit)
        
        layout.addLayout(buttons)
        
        # Фокус
        self.edit_password.setFocus()
    
    # ============================================================
    # Логика
    # ============================================================
    
    def _on_submit(self):
        password = self.edit_password.text()
        
        if not password:
            self._show_error("Пароль не может быть пустым")
            return
        
        if self.mode == "setup":
            self._handle_setup(password)
        else:
            self._handle_login(password)
    
    def _handle_setup(self, password: str):
        """Установка нового пароля."""
        confirm = self.edit_confirm.text() if self.edit_confirm else ""
        
        if len(password) < 4:
            self._show_error("Пароль должен быть минимум 4 символа")
            return
        
        if password != confirm:
            self._show_error("Пароли не совпадают")
            return
        
        self.security.set_password(password)
        print("[PasswordDialog] Пароль установлен")
        self.accept()
    
    def _handle_login(self, password: str):
        """Проверка пароля."""
        if self.security.check_password(password):
            print("[PasswordDialog] Вход выполнен")
            self.accept()
            return
        
        # Неверный пароль
        self.attempts += 1
        self.security.log_failed_attempt()
        
        remaining = self.MAX_ATTEMPTS - self.attempts
        
        if remaining <= 0:
            print("[PasswordDialog] Лимит попыток исчерпан")
            self._show_limit_exceeded()
            return
        
        print(f"[PasswordDialog] Неверный пароль. Осталось попыток: {remaining}")
        self._show_error(f"Неверный пароль. Осталось попыток: {remaining}")
        self.subtitle.setText(f"Попыток осталось: {remaining}")
        # НЕ вызываем clear() и setFocus() — они могут влиять на exec()
    
    def _show_limit_exceeded(self):
        """Показать сообщение о превышении лимита попыток."""
        self.edit_password.setEnabled(False)
        self.btn_submit.setEnabled(False)
        
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowTitle("Доступ заблокирован")
        msg.setText("⛔  Лимит попыток исчерпан")
        msg.setInformativeText(
            f"Превышено количество попыток ввода пароля.\n\n"
            f"Для восстановления доступа обратитесь к сотруднику:\n\n"
            f"📧  {CONTACT_EMAIL}"
        )
        msg.setStandardButtons(QMessageBox.Ok)
        msg.setStyleSheet(f"""
            QMessageBox {{
                background: {self.theme.bg_card};
            }}
            QMessageBox QLabel {{
                color: {self.theme.text_main};
                font-size: 12px;
            }}
            QMessageBox QPushButton {{
                background: {self.theme.primary};
                color: white;
                border: none;
                padding: 6px 20px;
                border-radius: 4px;
                font-size: 12px;
                font-weight: 600;
                min-width: 80px;
            }}
            QMessageBox QPushButton:hover {{
                background: #6ea800;
            }}
        """)
        msg.exec()
        
        self.reject()
    
    def _show_error(self, message: str):
        """Показать сообщение об ошибке."""
        print(f"[PasswordDialog] _show_error: {message}")
        self.error_label.setText(f"⚠️ {message}")
        self.error_label.setVisible(True)