"""
Боковая рельса (rail) — узкая панель с иконками разделов.
Справа от контента. Раскрывается при наведении.
Внизу — переключатель темы.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QSizePolicy,
    QGraphicsDropShadowEffect,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor


SECTIONS = [
    {"key": "inspector", "icon": "⚙",  "title": "Инспектор"},
    {"key": "data",      "icon": "📊", "title": "Данные"},
    {"key": "links",     "icon": "🔗", "title": "Связи"},
    {"key": "style",     "icon": "🎨", "title": "Стиль"},
]


class SideRail(QWidget):
    """Рельса с иконками. Раскрывается при hover. Переключатель темы."""
    
    section_selected = Signal(str)
    theme_toggled = Signal()
    
    WIDTH_COLLAPSED = 60
    WIDTH_EXPANDED = 200
    
    def __init__(self, theme, parent=None):
        super().__init__(parent)
        
        self.theme = theme
        self._expanded = False
        self._active_section = "inspector"
        self._section_buttons = {}
        self._theme_button = None
        
        self.setFixedWidth(self.WIDTH_COLLAPSED)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        
        self._build_ui()
        self._update_style()
    
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 10, 6, 10)
        layout.setSpacing(6)
        
        # Основные разделы
        for section in SECTIONS:
            btn = self._create_section_button(section)
            self._section_buttons[section["key"]] = btn
            layout.addWidget(btn)
        
        layout.addStretch()
        
        # Переключатель темы
        self._theme_button = self._create_theme_button()
        layout.addWidget(self._theme_button)
        
        self._update_section_styles()
    
    def _create_section_button(self, section: dict) -> QPushButton:
        btn = QPushButton(section["icon"])
        btn.setFixedHeight(48)
        btn.setToolTip(section["title"])
        btn.setCursor(Qt.PointingHandCursor)
        btn.setProperty("section_key", section["key"])
        btn.setProperty("section_icon", section["icon"])
        btn.setProperty("section_title", section["title"])
        btn.clicked.connect(lambda: self._on_section_clicked(section["key"]))
        return btn
    
    def _create_theme_button(self) -> QPushButton:
        btn = QPushButton("🌙")
        btn.setFixedHeight(48)
        btn.setToolTip("Переключить тему")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setProperty("is_theme_button", True)
        btn.clicked.connect(self._on_theme_toggle)
        return btn
    
    # ============================================================
    # Стиль
    # ============================================================
    
    def set_theme(self, theme):
        """Обновить тему рельсы."""
        self.theme = theme
        self._update_style()
    
    def _update_style(self):
        self.setStyleSheet(f"""
            SideRail {{
                background: {self.theme.bg_card};
                border-left: 1px solid {self.theme.border};
            }}
        """)
        self._update_section_styles()
    
    def _update_section_styles(self):
        # Кнопки разделов
        for key, btn in self._section_buttons.items():
            is_active = (key == self._active_section)
            icon = btn.property("section_icon") or ""
            title = btn.property("section_title") or ""
            
            if self._expanded:
                btn.setText(f"  {icon}   {title}")
            else:
                btn.setText(icon)
            
            btn.setStyleSheet(self._section_button_style(is_active))
            
            if is_active:
                shadow = QGraphicsDropShadowEffect(btn)
                shadow.setBlurRadius(12)
                shadow.setColor(QColor(135, 200, 0, 120))
                shadow.setOffset(0, 2)
                btn.setGraphicsEffect(shadow)
            else:
                btn.setGraphicsEffect(None)
        
        # Кнопка темы
        if self._theme_button:
            # Иконка: если текущая тёмная — показываем ☀️ (переключение на светлую)
            # Если светлая — показываем 🌙 (переключение на тёмную)
            if self.theme.is_dark:
                icon = "☀️"
                title = "Светлая тема"
            else:
                icon = "🌙"
                title = "Тёмная тема"
            
            if self._expanded:
                self._theme_button.setText(f"  {icon}   {title}")
            else:
                self._theme_button.setText(icon)
            
            self._theme_button.setToolTip(f"Переключить на: {title}")
            self._theme_button.setStyleSheet(self._theme_button_style())
    
    def _section_button_style(self, active: bool) -> str:
        if active:
            return f"""
                QPushButton {{
                    background: {self.theme.primary_hover};
                    color: {self.theme.primary_dark if not self.theme.is_dark else self.theme.primary};
                    border: 1px solid {self.theme.primary};
                    border-left: 3px solid {self.theme.primary};
                    border-radius: 6px;
                    font-size: 18px;
                    font-weight: 700;
                    text-align: left;
                    padding-left: 10px;
                    padding-right: 8px;
                    margin: 2px 0;
                }}
                QPushButton:hover {{
                    background: {self.theme.primary_hover};
                    border-color: {self.theme.primary};
                }}
            """
        return f"""
            QPushButton {{
                background: {self.theme.bg_panel};
                color: {self.theme.text_main};
                border: 1px solid {self.theme.border};
                border-left: 3px solid {self.theme.border};
                border-radius: 6px;
                font-size: 18px;
                font-weight: 500;
                text-align: left;
                padding-left: 10px;
                padding-right: 8px;
                margin: 2px 0;
            }}
            QPushButton:hover {{
                background: {self.theme.primary_hover};
                border-color: {self.theme.primary};
                color: {self.theme.primary};
            }}
        """
    
    def _theme_button_style(self) -> str:
        return f"""
            QPushButton {{
                background: transparent;
                color: {self.theme.text_main};
                border: 1px dashed {self.theme.border};
                border-radius: 6px;
                font-size: 18px;
                font-weight: 500;
                text-align: left;
                padding-left: 10px;
                padding-right: 8px;
                margin: 2px 0;
                margin-top: 8px;
            }}
            QPushButton:hover {{
                background: {self.theme.primary_hover};
                border-color: {self.theme.primary};
                border-style: solid;
                color: {self.theme.primary};
            }}
        """
    
    # ============================================================
    # Hover
    # ============================================================
    
    def enterEvent(self, event):
        super().enterEvent(event)
        if not self._expanded:
            self._expanded = True
            self.setFixedWidth(self.WIDTH_EXPANDED)
            self._update_section_styles()
    
    def leaveEvent(self, event):
        super().leaveEvent(event)
        if self._expanded:
            self._expanded = False
            self.setFixedWidth(self.WIDTH_COLLAPSED)
            self._update_section_styles()
    
    # ============================================================
    # Клики
    # ============================================================
    
    def _on_section_clicked(self, key: str):
        print(f"[Rail] Выбран раздел: {key}")
        self._active_section = key
        self._update_section_styles()
        self.section_selected.emit(key)
    
    def _on_theme_toggle(self):
        print("[Rail] Переключение темы")
        self.theme_toggled.emit()
    
    # ============================================================
    # Публичные методы
    # ============================================================
    
    def get_active_section(self) -> str:
        return self._active_section
    
    def set_active_section(self, key: str):
        self._active_section = key
        self._update_section_styles()