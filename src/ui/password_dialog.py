"""
Диалог ввода и установки пароля.
Показывается при первом запуске и при последующих.
"""

import math
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFrame, QMessageBox, QWidget, QSizePolicy
)
from PySide6.QtGui import QPainter, QColor, QPen, QPolygonF, QMouseEvent
from PySide6.QtCore import Qt, QTimer, QPointF


# Email для связи при блокировке
CONTACT_EMAIL = "v.ragimov@agroeco.ru"


class AnimatedHexagon(QWidget):
    """Кастомный анимированный виджет логотипа (вращающийся 6-угольник)."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(80, 80)
        self.angle = 0
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_frame)
        self.timer.start(16)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def _update_frame(self):
        self.angle = (self.angle + 2) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        painter.translate(self.width() / 2, self.height() / 2)
        painter.rotate(self.angle)
        
        poly = QPolygonF()
        radius = 26
        for i in range(6):
            angle_rad = math.radians(i * 60 - 30)
            x = radius * math.cos(angle_rad)
            y = radius * math.sin(angle_rad)
            poly.append(QPointF(x, y))
            
        pen = QPen(QColor("#87C800"))
        pen.setWidth(4)
        pen.setJoinStyle(Qt.MiterJoin)
        painter.setPen(pen)
        painter.drawPolygon(poly)
        
        painter.end()


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
        
        self.setAttribute(Qt.WA_PaintOnScreen, False)
        
        target_width = 400
        target_height = 450 if mode == "setup" else 415
        
        self.setWindowTitle("NexGrid — Авторизация")
        self.setAttribute(Qt.WA_DontShowOnScreen, False)
        self.setFixedSize(target_width, target_height)
        
        self.setWindowFlags(
            Qt.Dialog |
            Qt.FramelessWindowHint |
            Qt.WindowSystemMenuHint
        )
        
        self._drag_position = None
        
        self.setStyleSheet(f"""
            QDialog {{
                background: {self.theme.bg_card};
                border: 1px solid {self.theme.border};
                border-radius: 10px;
            }}
            QLabel {{
                color: {self.theme.text_main};
            }}
            QLineEdit {{
                background: {self.theme.bg_panel};
                border: 1px solid {self.theme.border};
                border-radius: 6px;
                padding: 10px 14px;
                font-size: 14px;
                color: {self.theme.text_main};
                letter-spacing: 2px;
            }}
            QLineEdit:focus {{
                border: 1px solid {self.theme.primary};
                background: {self.theme.bg_card};
            }}
        """)
        self.setProperty("no_dpi_scale", True)

        self._build_ui()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        expected_width = 400
        expected_height = 450 if self.mode == "setup" else 415
        if self.width() != expected_width or self.height() != expected_height:
            self.resize(expected_width, expected_height)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if event.buttons() == Qt.LeftButton and self._drag_position is not None:
            self.move(event.globalPosition().toPoint() - self._drag_position)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_position = None

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 20, 36, 30)
        layout.setSpacing(10)
        
        top_bar = QHBoxLayout()
        top_bar.addStretch()
        btn_close = QPushButton("✕")
        btn_close.setFixedSize(28, 28)
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {self.theme.text_muted};
                border: none;
                font-size: 14px;
                font-weight: bold;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background: #e74c3c;
                color: white;
            }}
        """)
        btn_close.clicked.connect(self.reject)
        top_bar.addWidget(btn_close)
        layout.addLayout(top_bar)
        
        logo_layout = QHBoxLayout()
        logo_layout.addStretch()
        self.logo = AnimatedHexagon()
        logo_layout.addWidget(self.logo)
        logo_layout.addStretch()
        layout.addLayout(logo_layout)
        
        title_text = "Введите пароль" if self.mode == "login" else "Установите пароль"
        title = QLabel(title_text)
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(f"""
            color: {self.theme.text_main};
            font-size: 20px;
            font-weight: 700;
            letter-spacing: 0.5px;
            margin-top: 2px;
        """)
        layout.addWidget(title)
        
        if self.mode == "login":
            subtitle_text = f"Попыток осталось: {self.MAX_ATTEMPTS - self.attempts}"
        else:
            subtitle_text = "Пароль будет запрашиваться\nпри каждом запуске приложения"
        subtitle = QLabel(subtitle_text)
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet(f"""
            color: {self.theme.text_muted};
            font-size: 13px;
            margin-bottom: 6px;
        """)
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        
        self.subtitle = subtitle
        
        label_pwd = QLabel("ПАРОЛЬ")
        label_pwd.setStyleSheet(f"color: {self.theme.text_muted}; font-size: 11px; font-weight: 700; letter-spacing: 1px;")
        layout.addWidget(label_pwd)
        
        self.edit_password = QLineEdit()
        self.edit_password.setEchoMode(QLineEdit.Password)
        self.edit_password.setPlaceholderText("••••••••")
        layout.addWidget(self.edit_password)
        
        if self.mode == "setup":
            layout.addSpacing(4)
            label_confirm = QLabel("ПОДТВЕРЖДЕНИЕ")
            label_confirm.setStyleSheet(f"color: {self.theme.text_muted}; font-size: 11px; font-weight: 700; letter-spacing: 1px;")
            layout.addWidget(label_confirm)
            
            self.edit_confirm = QLineEdit()
            self.edit_confirm.setEchoMode(QLineEdit.Password)
            self.edit_confirm.setPlaceholderText("••••••••")
            layout.addWidget(self.edit_confirm)
        else:
            self.edit_confirm = None
        
        self.error_label = QLabel("")
        self.error_label.setAlignment(Qt.AlignCenter)
        self.error_label.setFixedHeight(22)
        self.error_label.setStyleSheet("""
            color: #e74c3c;
            font-size: 12px;
            font-weight: 600;
        """)
        layout.addWidget(self.error_label)
        
        layout.addStretch()
        
        buttons = QHBoxLayout()
        buttons.setSpacing(12)
        
        btn_cancel = QPushButton("Отмена")
        btn_cancel.setAutoDefault(False)
        btn_cancel.setDefault(False)
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.setStyleSheet(f"""
            QPushButton {{
                background: {self.theme.bg_panel};
                color: {self.theme.primary_text};
                border: 1px solid {self.theme.border};
                padding: 10px 16px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: 500;
            }}
            QPushButton:hover {{ background: {self.theme.bg_hover}; }}
        """)
        btn_cancel.clicked.connect(self.reject)
        buttons.addWidget(btn_cancel)
        
        self.btn_submit = QPushButton("Войти" if self.mode == "login" else "Установить")
        self.btn_submit.setDefault(True)
        self.btn_submit.setAutoDefault(True)
        self.btn_submit.setCursor(Qt.PointingHandCursor)
        self.btn_submit.setStyleSheet(f"""
            QPushButton {{
                background: {self.theme.primary};
                color: white;
                border: none;
                padding: 10px 24px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background: #76af00; }}
        """)
        self.btn_submit.clicked.connect(self._on_submit)
        buttons.addWidget(self.btn_submit)
        
        layout.addLayout(buttons)
        self.edit_password.setFocus()
    
    def _on_submit(self):
        self.error_label.setText("")
        password = self.edit_password.text()
        
        if not password:
            self._show_error("Пароль не может быть пустым")
            return
        
        if self.mode == "setup":
            self._handle_setup(password)
        else:
            self._handle_login(password)
    
    def _handle_setup(self, password: str):
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
        if self.security.check_password(password):
            print("[PasswordDialog] Вход выполнен")
            self.accept()
            return
        
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
        
        self.edit_password.clear()
        self.edit_password.setFocus()
    
    def _show_limit_exceeded(self):
        self.edit_password.setEnabled(False)
        self.btn_submit.setEnabled(False)
        self.logo.timer.stop()
        
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowTitle("Доступ заблокирован")
        msg.setText("⛔  Лимит попыток исчерпан")
        msg.setInformativeText(
            f"Превышено количество попыток ввода пароля.\n\n"
            f"Для восстановления доступа обратитесь к администратору:\n\n"
            f"📧  {CONTACT_EMAIL}"
        )
        msg.setStandardButtons(QMessageBox.Ok)
        msg.setStyleSheet(f"""
            QMessageBox {{
                background: {self.theme.bg_card};
            }}
            QMessageBox QLabel {{
                color: {self.theme.text_main};
                font-size: 13px;
            }}
            QMessageBox QPushButton {{
                background: {self.theme.primary};
                color: white;
                border: none;
                padding: 8px 24px;
                border-radius: 5px;
                font-size: 13px;
                font-weight: 600;
                min-width: 80px;
            }}
            QMessageBox QPushButton:hover {{
                background: #76af00;
            }}
        """)
        msg.exec()
        self.reject()
    
    def _show_error(self, message: str):
        """Показать сообщение об ошибке."""
        self.error_label.setText(f"⚠️ {message}")