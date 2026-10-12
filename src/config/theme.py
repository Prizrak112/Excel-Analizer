"""
Темы оформления приложения: светлая и тёмная.
Шрифты увеличены для комфортного чтения.
"""

from dataclasses import dataclass


@dataclass
class Theme:
    """Базовый класс темы."""

    name: str = "Theme"
    is_dark: bool = False

    # Основные цвета
    primary: str = "#87C800"
    primary_dark: str = "#003F0B"
    primary_text: str = "#195532"
    primary_hover: str = "#e9f5e9"

    # Фоны
    bg_page: str = "#f5f7f9"
    bg_card: str = "#ffffff"
    bg_panel: str = "#fafafa"
    bg_hover: str = "#f5f5f5"

    # Границы
    border: str = "#e5e7eb"
    border_focus: str = "#87C800"

    # Текст
    text_main: str = "#333333"
    text_muted: str = "#888888"
    text_inverse: str = "#ffffff"

    # Формы
    border_radius: int = 12
    border_radius_small: int = 8

    # Типографика (увеличено)
    font_family: str = "Segoe UI"
    font_size_base: int = 14      # было 13
    font_size_small: int = 13     # было 11
    font_size_large: int = 16
    font_size_menu: int = 14      # было по умолчанию ~12
    font_size_title: int = 16     # для заголовков секций
    font_size_button: int = 13
    font_size_header: int = 13    # заголовки таблиц

    def to_qss(self) -> str:
        return self._build_qss()

    def _build_qss(self) -> str:
        return f"""
        /* ═══════════════════════════════════════════════════════════
           БАЗА
           ═══════════════════════════════════════════════════════════ */
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

        /* ═══════════════════════════════════════════════════════════
           МЕНЮ
           ═══════════════════════════════════════════════════════════ */
        QMenuBar {{
            background-color: {self.bg_page};
            border: none;
            color: {self.text_main};
            padding: 4px 6px;
            font-size: {self.font_size_menu}px;
        }}

        QMenuBar::item {{
            padding: 8px 16px;
            background: transparent;
            border-radius: 6px;
            font-size: {self.font_size_menu}px;
        }}

        QMenuBar::item:selected {{
            background-color: {self.bg_panel};
            color: {self.text_main};
        }}

        QMenu {{
            background-color: {self.bg_card};
            border: 1px solid {self.border};
            border-radius: 8px;
            padding: 6px;
            font-size: {self.font_size_menu}px;
        }}

        QMenu::item {{
            padding: 8px 28px 8px 16px;
            color: {self.text_main};
            border-radius: 6px;
            font-size: {self.font_size_menu}px;
        }}

        QMenu::item:selected {{
            background-color: {self.bg_panel};
            color: {self.text_main};
        }}

        QMenu::separator {{
            height: 1px;
            background: {self.border};
            margin: 4px 10px;
        }}

        /* ═══════════════════════════════════════════════════════════
           ТУЛБАР
           ═══════════════════════════════════════════════════════════ */
        QToolBar {{
            background-color: {self.bg_card};
            border: none;
            border-bottom: 1px solid {self.border};
            padding: 8px 10px;
            spacing: 4px;
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

        QToolBar QToolButton:hover {{
            background: {self.bg_panel};
            color: {self.text_main};
        }}

        QToolBar QToolButton:pressed {{
            background: {self.bg_hover};
        }}

        QToolBar QToolButton:disabled {{
            color: {self.text_muted};
        }}

        QToolBar::separator {{
            background: {self.border};
            width: 1px;
            margin: 6px 8px;
        }}

        /* ═══════════════════════════════════════════════════════════
           ВКЛАДКИ
           ═══════════════════════════════════════════════════════════ */
        QTabWidget {{
            background: {self.bg_page};
        }}

        QTabWidget::pane {{
            border: none;
            background: {self.bg_page};
        }}

        QTabWidget::tab-bar {{
            background: {self.bg_card};
            border: none;
            alignment: left;
        }}

        QTabBar {{
            background: {self.bg_card};
            qproperty-drawBase: 0;
            border: none;
        }}

        QTabBar::tab {{
            background: transparent;
            color: {self.text_muted};
            padding: 12px 22px;
            margin: 8px 6px;
            border: none;
            border-radius: 10px;
            font-size: {self.font_size_base}px;
            font-weight: 500;
            min-width: 90px;
        }}

        QTabBar::tab:selected {{
            background: {self.primary_hover};
            color: {self.text_main};
            font-weight: 700;
        }}

        QTabBar::tab:hover:!selected {{
            background: {self.bg_panel};
            color: {self.text_main};
        }}

        /* ═══════════════════════════════════════════════════════════
           СПЛИТТЕР
           ═══════════════════════════════════════════════════════════ */
        QSplitter {{
            background: {self.bg_page};
        }}

        QSplitter::handle {{
            background: {self.bg_page};
        }}

        QSplitter::handle:horizontal {{
            width: 1px;
        }}

        QSplitter::handle:vertical {{
            height: 1px;
        }}

        /* ═══════════════════════════════════════════════════════════
           СПИСКИ И ДЕРЕВЬЯ
           ═══════════════════════════════════════════════════════════ */
        QListWidget, QTreeWidget {{
            background: transparent;
            border: none;
            color: {self.text_main};
            outline: none;
            padding: 0;
            font-size: {self.font_size_base}px;
        }}

        QListWidget::item, QTreeWidget::item {{
            padding: 9px 12px;
            border-radius: 8px;
            color: {self.text_main};
            min-height: 26px;
            font-size: {self.font_size_base}px;
        }}

        QListWidget::item:selected, QTreeWidget::item:selected {{
            background: {self.bg_panel};
            color: {self.text_main};
        }}

        QListWidget::item:hover, QTreeWidget::item:hover {{
            background: {self.bg_hover};
        }}

        QTreeWidget::indicator {{
            width: 16px;
            height: 16px;
            border-radius: 4px;
            border: 1px solid {self.border};
            background: {self.bg_card};
        }}

        QTreeWidget::indicator:hover {{
            border: 1px solid {self.primary};
        }}

        QTreeWidget::indicator:checked {{
            background: {self.primary};
            border: 1px solid {self.primary};
        }}

        /* ═══════════════════════════════════════════════════════════
           ТАБЛИЦА
           ═══════════════════════════════════════════════════════════ */
        QTableView {{
            background: {self.bg_card};
            alternate-background-color: {self.bg_panel};
            gridline-color: {self.border};
            color: {self.text_main};
            font-size: {self.font_size_base}px;
            border: none;
            selection-background-color: {self.primary_hover};
            selection-color: {self.text_main};
        }}

        QTableView::corner {{
            background: {self.bg_panel};
            border: none;
        }}

        QTableCornerButton::section {{
            background: {self.bg_panel};
            border: none;
        }}

        QHeaderView::section {{
            background: {self.bg_panel};
            color: {self.primary_text};
            padding: 10px 12px;
            border: none;
            border-bottom: 1px solid {self.border};
            font-weight: 600;
            font-size: {self.font_size_header}px;
        }}

        QHeaderView::section:hover {{
            background: {self.bg_hover};
        }}

        /* ═══════════════════════════════════════════════════════════
           ПОЛЯ ВВОДА
           ═══════════════════════════════════════════════════════════ */
        QLineEdit, QPlainTextEdit, QTextEdit {{
            background: {self.bg_panel};
            border: 1px solid {self.border};
            border-radius: 8px;
            padding: 9px 14px;
            color: {self.text_main};
            font-size: {self.font_size_base}px;
            selection-background-color: {self.primary_hover};
            selection-color: {self.text_main};
        }}

        QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{
            border: 1px solid {self.primary};
        }}

        QComboBox {{
            background: {self.bg_panel};
            border: 1px solid {self.border};
            border-radius: 8px;
            padding: 8px 12px;
            color: {self.text_main};
            font-size: {self.font_size_base}px;
        }}

        QComboBox:hover {{
            border: 1px solid {self.text_muted};
        }}

        QComboBox:focus {{
            border: 1px solid {self.primary};
        }}

        QComboBox::drop-down {{
            border: none;
            width: 24px;
        }}

        QComboBox QAbstractItemView {{
            background: {self.bg_card};
            border: 1px solid {self.border};
            border-radius: 8px;
            selection-background-color: {self.bg_panel};
            selection-color: {self.text_main};
            color: {self.text_main};
            padding: 6px;
            outline: none;
            font-size: {self.font_size_base}px;
        }}

        /* ═══════════════════════════════════════════════════════════
           КНОПКИ
           ═══════════════════════════════════════════════════════════ */
        QPushButton {{
            background-color: {self.primary};
            color: {self.text_inverse};
            border: none;
            padding: 10px 20px;
            border-radius: 9px;
            font-weight: 600;
            font-size: {self.font_size_button}px;
        }}

        QPushButton:hover {{
            background-color: #9ade4f;
        }}

        QPushButton:pressed {{
            background-color: #6ea800;
        }}

        QPushButton:disabled {{
            background-color: {self.bg_panel};
            color: {self.text_muted};
        }}

        /* ═══════════════════════════════════════════════════════════
           ЧЕКБОКСЫ
           ═══════════════════════════════════════════════════════════ */
        QCheckBox {{
            color: {self.text_main};
            spacing: 10px;
            background: transparent;
            font-size: {self.font_size_base}px;
        }}

        QCheckBox::indicator {{
            width: 18px;
            height: 18px;
            border-radius: 4px;
            border: 1px solid {self.border};
            background: {self.bg_card};
        }}

        QCheckBox::indicator:hover {{
            border: 1px solid {self.primary};
        }}

        QCheckBox::indicator:checked {{
            background: {self.primary};
            border: 1px solid {self.primary};
        }}

        /* ═══════════════════════════════════════════════════════════
           СТАТУС-БАР
           ═══════════════════════════════════════════════════════════ */
        QStatusBar {{
            background-color: {self.bg_card};
            border: none;
            border-top: 1px solid {self.border};
            color: {self.text_muted};
            font-size: {self.font_size_small}px;
            padding: 4px 12px;
        }}

        QStatusBar::item {{
            border: none;
        }}

        /* ═══════════════════════════════════════════════════════════
           ДИАЛОГИ
           ═══════════════════════════════════════════════════════════ */
        QDialog {{
            background: {self.bg_card};
        }}

        /* ═══════════════════════════════════════════════════════════
           ПОДСКАЗКИ
           ═══════════════════════════════════════════════════════════ */
        QToolTip {{
            background: {self.bg_panel};
            color: {self.text_main};
            border: 1px solid {self.border};
            padding: 8px 12px;
            border-radius: 6px;
            font-size: {self.font_size_small}px;
        }}

        /* ═══════════════════════════════════════════════════════════
           СКРОЛЛБАРЫ
           ═══════════════════════════════════════════════════════════ */
        QScrollBar:vertical {{
            background: transparent;
            width: 12px;
            margin: 0;
            border: none;
        }}

        QScrollBar::handle:vertical {{
            background: {self.border};
            border-radius: 6px;
            min-height: 30px;
            margin: 2px;
        }}

        QScrollBar::handle:vertical:hover {{
            background: {self.text_muted};
        }}

        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0;
            background: none;
            border: none;
        }}

        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
            background: none;
        }}

        QScrollBar:horizontal {{
            background: transparent;
            height: 12px;
            margin: 0;
            border: none;
        }}

        QScrollBar::handle:horizontal {{
            background: {self.border};
            border-radius: 6px;
            min-width: 30px;
            margin: 2px;
        }}

        QScrollBar::handle:horizontal:hover {{
            background: {self.text_muted};
        }}

        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0;
            background: none;
            border: none;
        }}

        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
            background: none;
        }}

        /* ═══════════════════════════════════════════════════════════
           ПРОЧЕЕ
           ═══════════════════════════════════════════════════════════ */
        QFrame {{
            background: transparent;
            border: none;
        }}

        QStackedWidget {{
            background: transparent;
        }}

        QScrollArea {{
            background: transparent;
            border: none;
        }}

        QScrollArea > QWidget > QWidget {{
            background: transparent;
        }}
        """


@dataclass
class LightTheme(Theme):
    """Светлая тема."""
    name: str = "Светлая"
    is_dark: bool = False

    primary: str = "#87C800"
    primary_dark: str = "#003F0B"
    primary_text: str = "#195532"
    primary_hover: str = "#e9f5e9"

    bg_page: str = "#f5f7f9"
    bg_card: str = "#ffffff"
    bg_panel: str = "#fafafa"
    bg_hover: str = "#f5f5f5"

    border: str = "#e5e7eb"
    border_focus: str = "#87C800"

    text_main: str = "#333333"
    text_muted: str = "#888888"
    text_inverse: str = "#ffffff"


@dataclass
class DarkTheme(Theme):
    """Тёмная тема."""

    name: str = "Тёмная"
    is_dark: bool = True

    primary: str = "#87C800"
    primary_dark: str = "#E6EBF2"
    primary_text: str = "#87C800"
    primary_hover: str = "#2a3a20"

    bg_page: str = "#141821"
    bg_card: str = "#1B202B"
    bg_panel: str = "#232838"
    bg_hover: str = "#2A3040"

    border: str = "#2A303F"
    border_focus: str = "#87C800"

    text_main: str = "#E6EBF2"
    text_muted: str = "#8B93A7"
    text_inverse: str = "#0F1318"


LIGHT_THEME = LightTheme()
DARK_THEME = DarkTheme()

_current_theme: Theme = LIGHT_THEME


def get_theme() -> Theme:
    return _current_theme


def set_theme(theme: Theme):
    global _current_theme
    _current_theme = theme


def toggle_theme() -> Theme:
    global _current_theme
    if _current_theme.is_dark:
        _current_theme = LIGHT_THEME
    else:
        _current_theme = DARK_THEME
    return _current_theme


default_theme = LIGHT_THEME