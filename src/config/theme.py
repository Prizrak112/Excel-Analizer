"""
Темы оформления приложения: светлая и тёмная.
Стиль: современный дашборд (Notion / Power BI).
"""

from dataclasses import dataclass

@dataclass
class Theme:
    """Базовый класс темы."""

    name: str = "Theme"
    is_dark: bool = False

    # Основные цвета (Сохранен фирменный зеленый)
    primary: str = "#87C800"
    primary_dark: str = "#003F0B"
    primary_text: str = "#195532"
    primary_hover: str = "#e9f5e9"

    # Фоны
    bg_page: str = "#F7F9FA"  # Более мягкий, современный серый фон
    bg_card: str = "#FFFFFF"
    bg_panel: str = "#F0F2F5"
    bg_hover: str = "#EAECEF"

    # Границы
    border: str = "#E2E4E9"
    border_focus: str = "#87C800"

    # Текст
    text_main: str = "#1A1A1C"
    text_muted: str = "#7A7E86"
    text_inverse: str = "#FFFFFF"

    # Формы
    border_radius: int = 12
    border_radius_small: int = 8

    # Типографика
    font_family: str = "Segoe UI, -apple-system, BlinkMacSystemFont, Roboto, sans-serif"
    font_size_base: int = 13
    font_size_small: int = 12
    font_size_large: int = 16
    font_size_menu: int = 13
    font_size_title: int = 15
    font_size_button: int = 13
    font_size_header: int = 13

    def to_qss(self) -> str:
        return self._build_qss()

    def _build_qss(self) -> str:
        return f"""
        /* БАЗА */
        QMainWindow, QWidget {{
            background-color: {self.bg_page};
            color: {self.text_main};
            font-family: "{self.font_family}";
            font-size: {self.font_size_base}px;
        }}
        QLabel {{
            color: {self.text_main};
            background: transparent;
            font-size: {self.font_size_base}px;
        }}

        /* МЕНЮ */
        QMenuBar {{
            background-color: {self.bg_page};
            border: none;
            color: {self.text_main};
            padding: 8px 12px;
            font-size: {self.font_size_menu}px;
        }}
        QMenuBar::item {{
            padding: 8px 14px;
            background: transparent;
            border-radius: 6px;
        }}
        QMenuBar::item:selected {{ background-color: {self.bg_panel}; }}
        
        QMenu {{
            background-color: {self.bg_card};
            border: 1px solid {self.border};
            border-radius: 8px;
            padding: 6px;
        }}
        QMenu::item {{
            padding: 8px 28px 8px 16px;
            border-radius: 6px;
        }}
        QMenu::item:selected {{ background-color: {self.bg_panel}; }}
        QMenu::separator {{ height: 1px; background: {self.border}; margin: 6px 10px; }}

        /* ТУЛБАР */
        QToolBar {{
            background-color: {self.bg_card};
            border: none;
            border-bottom: 1px solid {self.border};
            padding: 10px 16px;
            spacing: 8px;
        }}
        QToolBar QToolButton {{
            background: transparent;
            color: {self.text_main};
            padding: 8px 14px;
            border: none;
            border-radius: 8px;
            font-size: {self.font_size_button}px;
            font-weight: 500;
        }}
        QToolBar QToolButton:hover {{ background: {self.bg_panel}; }}
        QToolBar QToolButton:pressed {{ background: {self.bg_hover}; }}
        QToolBar::separator {{ background: {self.border}; width: 1px; margin: 4px 12px; }}

        /* ВКЛАДКИ */
        QTabWidget {{ background: {self.bg_page}; }}
        QTabWidget::pane {{ border: none; background: transparent; }}
        QTabWidget::tab-bar {{ alignment: left; }}
        QTabBar {{ background: transparent; qproperty-drawBase: 0; }}
        QTabBar::tab {{
            background: transparent;
            color: {self.text_muted};
            padding: 8px 16px;
            margin: 4px 8px 4px 0px;
            border: none;
            border-radius: 8px;
            font-weight: 500;
        }}
        QTabBar::tab:hover:!selected {{ background: {self.bg_panel}; color: {self.text_main}; }}
        QTabBar::tab:selected {{ background: {self.bg_card}; color: {self.text_main}; font-weight: 600; border: 1px solid {self.border}; }}

        /* СПЛИТТЕР */
        QSplitter {{ background: {self.bg_page}; }}
        QSplitter::handle {{ background: transparent; }}

        /* СПИСКИ И ДЕРЕВЬЯ */
        QListWidget, QTreeWidget {{
            background: transparent;
            border: none;
            outline: none;
            padding: 4px;
        }}
        QListWidget::item, QTreeWidget::item {{
            padding: 10px 14px;
            border-radius: 8px;
            margin-bottom: 2px;
        }}
        QListWidget::item:selected, QTreeWidget::item:selected {{ background: {self.bg_panel}; color: {self.text_main}; font-weight: 500; }}
        QListWidget::item:hover, QTreeWidget::item:hover {{ background: {self.bg_hover}; }}

        /* ТАБЛИЦА */
        QTableView {{
            background: {self.bg_card};
            alternate-background-color: {self.bg_page};
            gridline-color: {self.bg_panel};
            border: 1px solid {self.border};
            border-radius: 8px;
            selection-background-color: {self.primary_hover};
            selection-color: {self.text_main};
        }}
        QHeaderView::section {{
            background: {self.bg_page};
            color: {self.text_muted};
            padding: 12px;
            border: none;
            border-bottom: 1px solid {self.border};
            border-right: 1px solid {self.border};
            font-weight: 600;
        }}
        QHeaderView::section:hover {{ background: {self.bg_panel}; color: {self.text_main}; }}

        /* ПОЛЯ ВВОДА */
        QLineEdit, QPlainTextEdit, QTextEdit, QComboBox {{
            background: {self.bg_card};
            border: 1px solid {self.border};
            border-radius: 8px;
            padding: 10px 14px;
            selection-background-color: {self.primary_hover};
        }}
        QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus {{ border: 1px solid {self.primary}; }}
        QComboBox::drop-down {{ border: none; width: 28px; }}
        QComboBox QAbstractItemView {{ background: {self.bg_card}; border: 1px solid {self.border}; border-radius: 8px; padding: 6px; outline: none; }}

        /* КНОПКИ */
        QPushButton {{
            background-color: {self.primary};
            color: {self.text_inverse};
            border: none;
            padding: 10px 24px;
            border-radius: 8px;
            font-weight: 600;
        }}
        QPushButton:hover {{ background-color: #9ade4f; }}
        QPushButton:pressed {{ background-color: #6ea800; }}
        QPushButton:disabled {{ background-color: {self.bg_panel}; color: {self.text_muted}; }}

        /* ЧЕКБОКСЫ */
        QCheckBox {{ spacing: 12px; }}
        QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 4px; border: 1px solid {self.border}; background: {self.bg_card}; }}
        QCheckBox::indicator:hover {{ border: 1px solid {self.primary}; }}
        QCheckBox::indicator:checked {{ background: {self.primary}; border: 1px solid {self.primary}; }}

        /* СТАТУС-БАР */
        QStatusBar {{ background: {self.bg_page}; border-top: 1px solid {self.border}; padding: 6px 16px; color: {self.text_muted}; }}
        QStatusBar::item {{ border: none; }}

        /* СКРОЛЛБАРЫ */
        QScrollBar:vertical {{ background: transparent; width: 10px; border: none; margin: 4px 0; }}
        QScrollBar::handle:vertical {{ background: {self.border}; border-radius: 5px; min-height: 40px; }}
        QScrollBar::handle:vertical:hover {{ background: {self.text_muted}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical, QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; border: none; height: 0; }}

        QScrollBar:horizontal {{ background: transparent; height: 10px; border: none; margin: 0 4px; }}
        QScrollBar::handle:horizontal {{ background: {self.border}; border-radius: 5px; min-width: 40px; }}
        QScrollBar::handle:horizontal:hover {{ background: {self.text_muted}; }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal, QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: none; border: none; width: 0; }}
        """

@dataclass
class LightTheme(Theme):
    name: str = "Светлая"
    is_dark: bool = False
    primary: str = "#87C800"
    primary_dark: str = "#003F0B"
    primary_text: str = "#195532"
    primary_hover: str = "#e9f5e9"
    bg_page: str = "#F7F9FA"
    bg_card: str = "#FFFFFF"
    bg_panel: str = "#F0F2F5"
    bg_hover: str = "#EAECEF"
    border: str = "#E2E4E9"
    border_focus: str = "#87C800"
    text_main: str = "#1A1A1C"
    text_muted: str = "#7A7E86"
    text_inverse: str = "#FFFFFF"

@dataclass
class DarkTheme(Theme):
    name: str = "Тёмная"
    is_dark: bool = True
    primary: str = "#87C800"
    primary_dark: str = "#E6EBF2"
    primary_text: str = "#87C800"
    primary_hover: str = "#2A3A20"
    bg_page: str = "#121418"
    bg_card: str = "#1A1D24"
    bg_panel: str = "#22262F"
    bg_hover: str = "#2A2E39"
    border: str = "#2C313D"
    border_focus: str = "#87C800"
    text_main: str = "#E6EBF2"
    text_muted: str = "#8B93A7"
    text_inverse: str = "#0F1318"

LIGHT_THEME = LightTheme()
DARK_THEME = DarkTheme()
_current_theme: Theme = LIGHT_THEME

def get_theme() -> Theme: return _current_theme
def set_theme(theme: Theme):
    global _current_theme
    _current_theme = theme
def toggle_theme() -> Theme:
    global _current_theme
    _current_theme = LIGHT_THEME if _current_theme.is_dark else DARK_THEME
    return _current_theme

default_theme = LIGHT_THEME