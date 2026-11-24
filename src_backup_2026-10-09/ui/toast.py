"""
Всплывающее уведомление (toast) в правом нижнем углу.
Появляется снизу, висит 3 секунды, уходит вниз.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGraphicsOpacityEffect, QApplication
)
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QPoint, QEasingCurve
from PySide6.QtGui import QFont


class Toast(QWidget):
    """Всплывающее уведомление."""
    
    WIDTH = 380
    DURATION = 3000      # мс — сколько висит
    ANIM_DURATION = 300  # мс — скорость анимации
    MARGIN = 20          # px — отступ от края
    
    def __init__(self, title: str, message: str, theme, kind: str = "info", parent=None):
        """
        kind: "info" | "success" | "warning" | "error"
        """
        super().__init__(parent)
        
        self.theme = theme
        self.kind = kind
        
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.Tool |
            Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        self.setFixedWidth(self.WIDTH)
        
        self._build_ui(title, message)
        self._position_window()
        
        # Таймер автоскрытия
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._hide_animated)
    
    # ============================================================
    # UI
    # ============================================================
    
    def _build_ui(self, title: str, message: str):
        # Цвета по типу
        colors = {
            "info":    ("#3498db", "ℹ️"),
            "success": ("#009128", "✅"),
            "warning": ("#f39c12", "⚠️"),
            "error":   ("#e74c3c", "❌"),
        }
        accent, icon = colors.get(self.kind, colors["info"])
        
        container = QWidget(self)
        container.setObjectName("toast_container")
        container.setStyleSheet(f"""
            #toast_container {{
                background: {self.theme.bg_card};
                border: 1px solid {self.theme.border};
                border-left: 4px solid {accent};
                border-radius: 8px;
            }}
        """)
        
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(container)
        
        layout = QVBoxLayout(container)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)
        
        # ============ ХЕДЕР ============
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)
        
        icon_label = QLabel(icon)
        icon_label.setStyleSheet("font-size: 16px;")
        header_layout.addWidget(icon_label)
        
        title_label = QLabel(title)
        title_label.setStyleSheet(f"""
            color: {self.theme.primary_dark};
            font-size: 13px;
            font-weight: bold;
        """)
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        
        btn_close = QPushButton("✕")
        btn_close.setFixedSize(22, 22)
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {self.theme.text_muted};
                border: none;
                border-radius: 4px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {self.theme.primary_hover};
                color: {self.theme.primary_dark};
            }}
        """)
        btn_close.clicked.connect(self._hide_animated)
        header_layout.addWidget(btn_close)
        
        layout.addWidget(header)
        
        # ============================================================
        # СООБЩЕНИЕ
        # ============================================================
        msg_label = QLabel(message)
        msg_label.setWordWrap(True)
        msg_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        msg_label.setStyleSheet(f"""
            color: {self.theme.text_main};
            font-size: 12px;
            padding-left: 24px;
        """)
        layout.addWidget(msg_label)
    
    # ============================================================
    # Позиционирование
    # ============================================================
    
    def _position_window(self):
        """Позиционирует окно в правом нижнем углу экрана."""
        screen = QApplication.primaryScreen().availableGeometry()
        
        self.adjustSize()
        
        x = screen.right() - self.width() - self.MARGIN
        y = screen.bottom() - self.height() - self.MARGIN
        
        self._final_pos = QPoint(x, y)
        self._start_pos = QPoint(x, y + 80)  # стартует ниже
    
    # ============================================================
    # Анимации
    # ============================================================
    
    def show_animated(self):
        """Показать с анимацией (всплытие снизу)."""
        self.move(self._start_pos)
        self.show()
        
        # Анимация позиции
        self._anim_pos = QPropertyAnimation(self, b"pos")
        self._anim_pos.setDuration(self.ANIM_DURATION)
        self._anim_pos.setStartValue(self._start_pos)
        self._anim_pos.setEndValue(self._final_pos)
        self._anim_pos.setEasingCurve(QEasingCurve.OutCubic)
        
        # Анимация прозрачности
        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        
        self._anim_opacity = QPropertyAnimation(self._effect, b"opacity")
        self._anim_opacity.setDuration(self.ANIM_DURATION)
        self._anim_opacity.setStartValue(0.0)
        self._anim_opacity.setEndValue(1.0)
        
        self._anim_pos.start()
        self._anim_opacity.start()
        
        # Таймер автоскрытия
        self._timer.start(self.DURATION)
    
    def _hide_animated(self):
        """Скрыть с анимацией (уход вниз)."""
        self._timer.stop()
        
        if hasattr(self, '_anim_pos') and self._anim_pos.state() == QPropertyAnimation.Running:
            return
        
        # Анимация позиции
        self._anim_pos_out = QPropertyAnimation(self, b"pos")
        self._anim_pos_out.setDuration(self.ANIM_DURATION)
        self._anim_pos_out.setStartValue(self.pos())
        self._anim_pos_out.setEndValue(self._start_pos)
        self._anim_pos_out.setEasingCurve(QEasingCurve.InCubic)
        
        # Анимация прозрачности
        self._anim_opacity_out = QPropertyAnimation(self._effect, b"opacity")
        self._anim_opacity_out.setDuration(self.ANIM_DURATION)
        self._anim_opacity_out.setStartValue(1.0)
        self._anim_opacity_out.setEndValue(0.0)
        
        self._anim_pos_out.finished.connect(self._on_hide_finished)
        self._anim_pos_out.start()
        self._anim_opacity_out.start()
    
    def _on_hide_finished(self):
        """Удалить после анимации."""
        self.close()
        self.deleteLater()


# ============================================================
# Менеджер уведомлений
# ============================================================

class ToastManager:
    """Управляет показом уведомлений (одно за раз)."""
    
    _current: Toast | None = None
    
    @classmethod
    def show(cls, title: str, message: str, theme, kind: str = "info"):
        """Показать уведомление. Закрывает предыдущее, если есть."""
        # Закрыть предыдущее
        if cls._current is not None:
            try:
                cls._current.close()
                cls._current.deleteLater()
            except Exception:
                pass
        
        toast = Toast(title, message, theme, kind)
        cls._current = toast
        toast.show_animated()
        
        return toast
    
    @classmethod
    def info(cls, title: str, message: str, theme):
        return cls.show(title, message, theme, "info")
    
    @classmethod
    def success(cls, title: str, message: str, theme):
        return cls.show(title, message, theme, "success")
    
    @classmethod
    def warning(cls, title: str, message: str, theme):
        return cls.show(title, message, theme, "warning")
    
    @classmethod
    def error(cls, title: str, message: str, theme):
        return cls.show(title, message, theme, "error")