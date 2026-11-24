"""
Главное окно приложения Excel Analyzer.
Стиль: современный dark dashboard.
"""

import os
import pandas as pd
from pathlib import Path


from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTreeWidgetItem, QMenu,
    QSplitter, QStackedWidget, QListWidget, QListWidgetItem,
    QTabWidget, QStatusBar, QToolBar, QFileDialog, QMessageBox, QInputDialog,
    QStyle, QFileIconProvider, QFrame, QAbstractItemView, QToolButton,
)
from PySide6.QtCore import Qt, QSize, QFileInfo, QTimer
from PySide6.QtGui import QAction, QShortcut, QKeySequence

from src.ui.constructor_tab import ConstructorTab
from src.config.theme import get_theme, set_theme, toggle_theme
from src.config.app_info import APP_WINDOW_TITLE
from src.config.settings import get_settings
from src.ui.columns_tree import ColumnsTree
from src.ui.inspector_panel import InspectorPanel
from src.ui.side_rail import SideRail
from src.ui.toast import ToastManager
from src.ui.split_dialog import SplitDialog
from src.ui.data_viewer import DataViewerWidget
from src.ui.find_dialog import FindDialog
from src.ui.filter_popup import FilterPopup
from src.ui.project_password_dialog import (
    SaveProjectDialog,
    OpenProjectPasswordDialog,
)
from src.ui.project_file_dialog import ProjectFileDialog
from src.ui.folder_dialog import FolderOpenDialog
from src.ui.pivot_dialog import PivotDialog
from src.ui.start_page import StartPage
from src.ui.drop_dialog import DropDuplicatesDialog, DropNaDialog
from src.ui.normalize_text_dialog import NormalizeTextDialog
from src.ui.extract_text_dialog import ExtractTextDialog
from src.ui.data_panel import DataPanel
from src.core.project_io import ProjectIO
from src.ui.code_editor import CodeEditorWidget
from src.core.code_generator import generate_script
from src.core.data_loader import DataLoader
from src.core.report_model import Report
from src.core.history import HistoryManager
from src.core.file_manager import FileManager
from src.core.commands import (
    ToggleColumnCommand,
    RenameColumnCommand,
    CastColumnCommand,
    ReorderColumnsCommand,
    SplitColumnCommand,
    EditCellCommand,
    DeleteColumnsCommand,
    DeleteRowsCommand,
    Normalize1CCommand,
    SortByColumnCommand,
    DropDuplicatesCommand,
    DropNaCommand,
    NormalizeTextCommand,
    ExtractTextCommand,
)


# ============================================================
# Утилиты
# ============================================================

def _resolve_lnk(path: str) -> str | None:
    """
    Развернуть ярлык .lnk в реальный путь.
    Пробует pywin32 → PowerShell.
    """
    try:
        import win32com.client
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortcut(path)
        target = (shortcut.TargetPath or "").strip()
        if target and os.path.exists(target):
            return target
    except Exception:
        pass

    try:
        import subprocess
        ps = (
            f'$sh = New-Object -ComObject WScript.Shell; '
            f'$sh.CreateShortcut("{path}").TargetPath'
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, text=True, timeout=5,
        )
        target = (result.stdout or "").strip()
        if target and os.path.exists(target):
            return target
    except Exception:
        pass

    return None


def _pill_btn_qss(theme, active: bool = False) -> str:
    """Маленькие кнопки-пилюли (Все / Сброс / Изменить)."""
    if active:
        bg = theme.primary
        color = theme.text_inverse
        border = "none"
        hover_bg = "#9ade4f"
    else:
        bg = theme.bg_panel
        color = theme.text_main
        border = f"1px solid {theme.border}"
        hover_bg = theme.bg_hover

    return f"""
        QPushButton {{
            background: {bg};
            color: {color};
            border: {border};
            padding: 4px 14px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 600;
            min-height: 22px;
            max-height: 22px;
        }}
        QPushButton:hover {{
            background: {hover_bg};
        }}
        QPushButton:pressed {{
            background: {hover_bg};
        }}
    """


def _list_qss(theme) -> str:
    """Единый стиль для QListWidget / QTreeWidget в левой панели."""
    return f"""
        QListWidget, QTreeWidget {{
            background: transparent;
            border: none;
            color: {theme.text_main};
            outline: none;
            padding: 0;
            font-size: 13px;
        }}
        QListWidget::item, QTreeWidget::item {{
            padding: 9px 12px;
            border-radius: 8px;
            color: {theme.text_main};
            min-height: 24px;
            font-size: 13px;
        }}
        QListWidget::item:selected, QTreeWidget::item:selected {{
            background: rgba(106, 195, 74, 0.20);
            color: {theme.text_main};
            border-left: 3px solid {theme.primary};
        }}
        QListWidget::item:hover, QTreeWidget::item:hover {{
            background: {theme.bg_hover};
        }}
        QTreeWidget::indicator {{
            width: 16px;
            height: 16px;
            border-radius: 4px;
            border: 1px solid {theme.border};
            background: {theme.bg_card};
        }}
        QTreeWidget::indicator:hover {{
            border: 1px solid {theme.primary};
        }}
        QTreeWidget::indicator:checked {{
            background: {theme.primary};
            border: 1px solid {theme.primary};
        }}
    """


class MainWindow(QMainWindow):
    """Главное окно приложения."""

    def __init__(self):
        super().__init__()

        self.theme = get_theme()
        self.settings = get_settings()
        self.current_data = None
        self._edit_mode = False
        self._selected_column = None
        self._content_visible = False
        self._displayed_indices: list[int] = []
        self._sort_state: list[tuple[str, bool]] = []
        self._find_dialog = None
        self.report = Report()
        self.history = HistoryManager(max_size=50)
        self.file_manager = FileManager()

        self.setWindowTitle(APP_WINDOW_TITLE)
        self.resize(1400, 900)

        self._build_menu()
        self._build_ui()
        self._build_statusbar()

        self.setStyleSheet(self.theme.to_qss())

    # ============================================================
    # Меню
    # ============================================================

    def _build_menu(self):
        menubar = self.menuBar()

        # ── «Правка» ──
        edit_menu = menubar.addMenu("Правка")

        self.action_undo = QAction("↶  Отменить", self)
        self.action_undo.setShortcut("Ctrl+Z")
        self.action_undo.setEnabled(False)
        self.action_undo.triggered.connect(self._on_undo)
        edit_menu.addAction(self.action_undo)

        edit_menu.addSeparator()

        self.action_find = QAction("🔍  Найти...", self)
        self.action_find.setShortcut("Ctrl+F")
        self.action_find.triggered.connect(self._on_find_open)
        edit_menu.addAction(self.action_find)

        # ── «Файл» ──
        file_menu = menubar.addMenu("Файл")

        action_home = QAction("🏠  На стартовую страницу", self)
        action_home.setShortcut("Ctrl+Shift+H")
        action_home.triggered.connect(self._go_home)
        file_menu.addAction(action_home)

        file_menu.addSeparator()

        action_open = QAction("📂  Открыть файл или проект...", self)
        action_open.setShortcut("Ctrl+O")
        action_open.triggered.connect(self.open_file)
        file_menu.addAction(action_open)

        action_open_folder = QAction("📁  Открыть папку с файлами...", self)
        action_open_folder.setShortcut("Ctrl+Shift+O")
        action_open_folder.triggered.connect(self.open_folder)
        file_menu.addAction(action_open_folder)

        action_close = QAction("Закрыть файл", self)
        action_close.setShortcut("Ctrl+W")
        action_close.triggered.connect(self._close_active_file)
        file_menu.addAction(action_close)

        file_menu.addSeparator()

        self.action_save = QAction("💾  Сохранить", self)
        self.action_save.setShortcut("Ctrl+S")
        self.action_save.triggered.connect(self._on_save)
        file_menu.addAction(self.action_save)

        self.action_save_as = QAction("💾  Сохранить как...", self)
        self.action_save_as.setShortcut("Ctrl+Shift+S")
        self.action_save_as.triggered.connect(self._on_save_as)
        file_menu.addAction(self.action_save_as)

        file_menu.addSeparator()

        self.action_save_project = QAction("📦  Сохранить проект...", self)
        self.action_save_project.setShortcut("Ctrl+Alt+S")
        self.action_save_project.triggered.connect(self._on_save_project)
        file_menu.addAction(self.action_save_project)

        self.action_open_project = QAction("📂  Открыть только проект...", self)
        self.action_open_project.setShortcut("Ctrl+Alt+O")
        self.action_open_project.triggered.connect(self._on_open_project)
        file_menu.addAction(self.action_open_project)

        file_menu.addSeparator()

        action_export = QAction("Экспорт в HTML", self)
        action_export.setShortcut("Ctrl+E")
        file_menu.addAction(action_export)

        file_menu.addSeparator()

        action_exit = QAction("Выход", self)
        action_exit.setShortcut("Alt+F4")
        action_exit.triggered.connect(self.close)
        file_menu.addAction(action_exit)

        # ── «Данные» ──
        data_menu = menubar.addMenu("Данные")

        action_load = QAction("Загрузить Excel...", self)
        action_load.triggered.connect(self.open_file)
        data_menu.addAction(action_load)

        data_menu.addSeparator()

        action_edit = QAction("Изменить порядок колонок", self)
        action_edit.triggered.connect(self._toggle_edit_mode)
        data_menu.addAction(action_edit)

        action_show_all = QAction("Показать все колонки", self)
        action_show_all.triggered.connect(self._show_all_columns)
        data_menu.addAction(action_show_all)

        action_hide_all = QAction("Скрыть все колонки", self)
        action_hide_all.triggered.connect(self._hide_all_columns)
        data_menu.addAction(action_hide_all)

        data_menu.addSeparator()

        action_clear_filters = QAction("Сбросить все фильтры", self)
        action_clear_filters.triggered.connect(self._clear_all_filters)
        data_menu.addAction(action_clear_filters)

        action_clear_sort = QAction("Сбросить сортировку", self)
        action_clear_sort.triggered.connect(self._clear_sort)
        data_menu.addAction(action_clear_sort)

        data_menu.addSeparator()

        action_pivot = QAction("📊  Сводная таблица...", self)
        action_pivot.triggered.connect(self._on_pivot_open)
        data_menu.addAction(action_pivot)

        data_menu.addSeparator()

        action_drop_duplicates = QAction("🗑  Удалить дубликаты...", self)
        action_drop_duplicates.triggered.connect(self._on_drop_duplicates)
        data_menu.addAction(action_drop_duplicates)

        action_drop_na = QAction("🗑  Удалить строки с пустыми...", self)
        action_drop_na.triggered.connect(self._on_drop_na)
        data_menu.addAction(action_drop_na)

        data_menu.addSeparator()

        # ★ Нормализация текста (гос-номера, замена латиницы↔кириллицы и т.д.)
        action_normalize_text = QAction("🔤  Нормализовать текст...", self)
        action_normalize_text.triggered.connect(self._on_normalize_text)
        data_menu.addAction(action_normalize_text)

        # ★ Извлечение по шаблону (regex) — гос. номер, VIN и т.д.
        action_extract_text = QAction("✂  Извлечь по шаблону...", self)
        action_extract_text.triggered.connect(self._on_extract_text)
        data_menu.addAction(action_extract_text)

        data_menu.addSeparator()

        action_normalize_1c = QAction("🧹 Обработать выгрузку 1С", self)
        action_normalize_1c.triggered.connect(self._on_normalize_1c)
        data_menu.addAction(action_normalize_1c)

        # ── «Вид» ──
        view_menu = menubar.addMenu("Вид")

        action_toggle_theme = QAction("🌓 Переключить тему", self)
        action_toggle_theme.setShortcut("Ctrl+T")
        action_toggle_theme.triggered.connect(self._on_toggle_theme)
        view_menu.addAction(action_toggle_theme)

        # ── «Отчёт» (только на Конструкторе) ──
        # ── Меню «Отчёт» убрано ──
        # Причины:
        #   • дублировало верхнюю навигацию и кнопки вкладки «Конструктор»,
        #   • конфликтовало по горячим клавишам (Ctrl+N, Ctrl+Alt+O, Ctrl+Alt+S),
        #   • Qt самопроизвольно раскрывал его при переключении на «Конструктор».
        # Все операции над отчётом остаются доступны:
        #   • через кнопку «🎨 Конструктор» в верхней навигации,
        #   • через верхний тулбар (кнопка «Экспорт HTML»),
        #   • через кнопки внутри вкладки «Конструктор» (Ctrl+P — предпросмотр).
        self.report_menu = None

        # ── «Справка» ──
        help_menu = menubar.addMenu("Справка")
        help_menu.addAction(QAction("О программе", self))

        # ★ Запоминаем меню-действия, чтобы скрывать их на Старте
        self._menu_actions: list[QAction] = []
        for action in menubar.actions():
            if action.menu() is not None:
                self._menu_actions.append(action)


    def _nav_btn_qss(self) -> str:
        t = self.theme
        return f"""
            QPushButton {{
                background: transparent;
                color: {t.text_muted};
                border: none;
                padding: 6px 18px;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {t.bg_panel};
                color: {t.text_main};
            }}
            QPushButton:checked {{
                background: {t.primary_hover};
                color: {t.text_main};
            }}
        """

    # ============================================================
    # Навигация (в правом углу менюбара)
    # ============================================================
    def _build_top_nav(self) -> QWidget:
        """Тонкая полоса навигации под менюбаром: Старт / Редактор / Конструктор."""
        bar = QWidget()
        bar.setFixedHeight(44)
        bar.setStyleSheet(
            f"background: {self.theme.bg_page}; "
            f"border-bottom: 1px solid {self.theme.border};"
        )
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 6, 16, 6)
        lay.setSpacing(6)

        self._nav_buttons = []

        def _make(label: str, page: int) -> QPushButton:
            b = QPushButton(label)
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(self._nav_btn_qss())
            b.clicked.connect(lambda _checked=False, p=page: self._switch_page(p))
            lay.addWidget(b)
            self._nav_buttons.append(b)
            return b

        _make("🏠   Старт", 0)
        _make("📊   Редактор", 1)
        _make("🎨   Конструктор", 2)

        lay.addStretch()
        return bar

    def _nav_btn_qss(self) -> str:
        t = self.theme
        return f"""
            QPushButton {{
                background: transparent;
                color: {t.text_muted};
                border: none;
                padding: 6px 18px;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {t.bg_panel};
                color: {t.text_main};
            }}
            QPushButton:checked {{
                background: {t.primary_hover};
                color: {t.text_main};
            }}
        """
    
    def _build_top_nav_inline(self) -> QWidget:
        """Кнопки навигации для встраивания в правый угол меню."""
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        self._nav_buttons: list[QPushButton] = []

        def _make(label: str, page: int) -> QPushButton:
            b = QPushButton(label)
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedHeight(26)
            b.setStyleSheet(self._nav_btn_inline_qss())
            b.clicked.connect(lambda _checked=False, p=page: self._switch_page(p))
            lay.addWidget(b)
            self._nav_buttons.append(b)
            return b

        _make("🏠   Старт", 0)
        _make("📊   Редактор", 1)
        _make("🎨   Конструктор", 2)

        return w

    def _nav_btn_inline_qss(self) -> str:
        t = self.theme
        return f"""
            QPushButton {{
                background: transparent;
                color: {t.text_muted};
                border: none;
                padding: 2px 12px;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {t.bg_panel};
                color: {t.text_main};
            }}
            QPushButton:checked {{
                background: {t.primary_hover};
                color: {t.text_main};
            }}
        """

    # ============================================================
    # Тулбар
    # ============================================================

    def _build_toolbar(self) -> QWidget:
        """Тулбар как виджет — встраивается в root_layout под навигацией."""
        bar = QWidget()
        bar.setObjectName("top_toolbar")
        bar.setFixedHeight(44)
        bar.setStyleSheet(f"""
            #top_toolbar {{
                background: {self.theme.bg_page};
                border: none;
                border-bottom: 1px solid {self.theme.border};
            }}
        """)

        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 4, 12, 4)
        lay.setSpacing(4)

        btn_qss = f"""
            QToolButton {{
                background: transparent;
                color: {self.theme.text_main};
                border: none;
                padding: 6px 12px;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 500;
            }}
            QToolButton:hover {{
                background: {self.theme.bg_panel};
                color: {self.theme.primary};
            }}
            QToolButton:disabled {{
                color: {self.theme.text_muted};
            }}
        """

        def _add(action: QAction):
            btn = QToolButton()
            btn.setDefaultAction(action)
            btn.setToolTip(action.toolTip())
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(btn_qss)
            lay.addWidget(btn)
            return btn

        def _sep():
            sep = QFrame()
            sep.setFrameShape(QFrame.VLine)
            sep.setStyleSheet(f"color: {self.theme.border};")
            sep.setFixedHeight(20)
            lay.addWidget(sep)

        action_open_tb = QAction("📂   Открыть", self)
        action_open_tb.setToolTip("Открыть Excel-файл или проект .eaproj (Ctrl+O)")
        action_open_tb.triggered.connect(self.open_file)
        _add(action_open_tb)

        action_open_folder_tb = QAction("📁   Открыть папку", self)
        action_open_folder_tb.setToolTip("Импорт папки с Excel-файлами (Ctrl+Shift+O)")
        action_open_folder_tb.triggered.connect(self.open_folder)
        _add(action_open_folder_tb)

        self.action_save_tb = QAction("💾   Сохранить", self)
        self.action_save_tb.setToolTip("Сохранить активный файл (Ctrl+S)")
        self.action_save_tb.triggered.connect(self._on_save)
        _add(self.action_save_tb)

        _sep()

        action_1c_tb = QAction("🧹   Обработать 1С", self)
        action_1c_tb.setToolTip("Нормализовать выгрузку 1С (карточка счёта)")
        action_1c_tb.triggered.connect(self._on_normalize_1c)
        _add(action_1c_tb)

        action_pivot_tb = QAction("📊   Сводная", self)
        action_pivot_tb.setToolTip("Создать сводную таблицу")
        action_pivot_tb.triggered.connect(self._on_pivot_open)
        _add(action_pivot_tb)

        self.action_undo_tb = QAction("↶   Отменить", self)
        self.action_undo_tb.setToolTip("Отменить последнее действие (Ctrl+Z)")
        self.action_undo_tb.setEnabled(False)
        self.action_undo_tb.triggered.connect(self._on_undo)
        _add(self.action_undo_tb)

        _sep()

        for text, tooltip in [
            ("📊   Данные", "Блок данных"),
            ("📈   График", "Блок графика"),
            ("🔢   KPI", "KPI-показатель"),
            ("📝   Текст", "Текстовый блок"),
        ]:
            a = QAction(text, self)
            a.setToolTip(tooltip)
            _add(a)

        _sep()

        a_export = QAction("🌐   Экспорт HTML", self)
        a_export.setToolTip("Экспорт в автономный HTML")
        a_export.triggered.connect(self._on_export_html_toolbar)
        _add(a_export)

        lay.addStretch()
        return bar

    def _on_export_html_toolbar(self):
        """Кнопка «Экспорт HTML» в тулбаре редактора — открывает
        конструктор, переключает на подвкладку «Экспорт» и вызывает сохранение."""
        if not hasattr(self, "constructor"):
            return
        self._switch_page(2)  # Конструктор
        self.constructor.show_export_tab()
        self.constructor._on_export_html()

    def _build_toolbar_widget(self) -> QWidget:
        """Тулбар как обычный виджет (встраивается в root_layout)."""
        bar = QWidget()
        bar.setFixedHeight(44)
        bar.setStyleSheet(f"""
            QWidget {{
                background: {self.theme.bg_page};
                border-bottom: 1px solid {self.theme.border};
            }}
        """)

        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 4, 12, 4)
        lay.setSpacing(6)

        def _add(text: str, tooltip: str, callback):
            b = QPushButton(text)
            b.setToolTip(tooltip)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {self.theme.text_main};
                    border: none;
                    padding: 6px 12px;
                    border-radius: 6px;
                    font-size: 12px;
                }}
                QPushButton:hover {{
                    background: {self.theme.bg_panel};
                    color: {self.theme.primary};
                }}
                QPushButton:disabled {{
                    color: {self.theme.text_muted};
                }}
            """)
            b.clicked.connect(callback)
            lay.addWidget(b)
            return b

        _add("📂   Открыть", "Открыть Excel-файл или проект .eaproj (Ctrl+O)", self.open_file)
        _add("📁   Открыть папку", "Импорт папки с Excel-файлами (Ctrl+Shift+O)", self.open_folder)
        self._btn_save = _add("💾   Сохранить", "Сохранить активный файл (Ctrl+S)", self._on_save)

        # Разделитель
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet(f"color: {self.theme.border};")
        sep.setFixedHeight(20)
        lay.addWidget(sep)

        _add("🧹   Обработать 1С", "Нормализовать выгрузку 1С", self._on_normalize_1c)
        _add("📊   Сводная", "Создать сводную таблицу", self._on_pivot_open)

        self._btn_undo_tb = _add("↶   Отменить", "Отменить (Ctrl+Z)", self._on_undo)
        self._btn_undo_tb.setEnabled(False)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.VLine)
        sep2.setStyleSheet(f"color: {self.theme.border};")
        sep2.setFixedHeight(20)
        lay.addWidget(sep2)

        _add("📊   Данные", "Блок данных", lambda: None)
        _add("📈   График", "Блок графика", lambda: None)
        _add("🔢   KPI", "KPI-показатель", lambda: None)
        _add("📝   Текст", "Текстовый блок", lambda: None)

        sep3 = QFrame()
        sep3.setFrameShape(QFrame.VLine)
        sep3.setStyleSheet(f"color: {self.theme.border};")
        sep3.setFixedHeight(20)
        lay.addWidget(sep3)

        _add("🌐   Экспорт HTML", "Экспорт в автономный HTML", lambda: None)

        lay.addStretch()
        return bar

    # ============================================================
    # UI
    # ============================================================

    def _build_ui(self):
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 1. Навигация
        self.top_nav = self._build_top_nav()
        root_layout.addWidget(self.top_nav)

        # 2. Тулбар — под навигацией
        self.top_toolbar = self._build_toolbar()
        root_layout.addWidget(self.top_toolbar)

        # 3. Основной сплиттер
        main_splitter = QSplitter(Qt.Horizontal)
        main_splitter.setHandleWidth(1)

        left_panel = self._build_left_panel()
        main_splitter.addWidget(left_panel)

        right_container = self._build_right_container()
        main_splitter.addWidget(right_container)

        main_splitter.setSizes([300, 1100])
        main_splitter.setStretchFactor(0, 0)
        main_splitter.setStretchFactor(1, 1)
        main_splitter.setCollapsible(0, False)
        main_splitter.setCollapsible(1, False)

        root_layout.addWidget(main_splitter, stretch=1)

        self.main_splitter = main_splitter
        self._left_panel = left_panel
        self._left_panel_expanded_width = 300
        self._left_panel_collapsed = False
        self._current_page = 0

        self.setCentralWidget(root)

        QTimer.singleShot(0, lambda: self._apply_page_layout(0))

    def _build_left_panel(self) -> QWidget:
        widget = QWidget()
        widget.setStyleSheet(f"background: {self.theme.bg_page};")
        widget.setMinimumWidth(70)

        outer = QVBoxLayout(widget)
        outer.setContentsMargins(0, 8, 0, 8)
        outer.setSpacing(0)

        # ═══ ШАПКА ═══
        self.left_header = QWidget()
        self.left_header.setFixedHeight(30)
        self.left_header.setStyleSheet("background: transparent;")
        header_lay = QHBoxLayout(self.left_header)
        header_lay.setContentsMargins(8, 0, 8, 0)
        header_lay.setSpacing(6)

        self.btn_toggle_left = QPushButton("<<")
        self.btn_toggle_left.setFixedSize(24, 24)
        self.btn_toggle_left.setCursor(Qt.PointingHandCursor)
        self.btn_toggle_left.setToolTip("Свернуть панель")
        self.btn_toggle_left.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {self.theme.primary};
                border: none;
                font-size: 14px;
                font-weight: 900;
                padding: 0;
            }}
            QPushButton:hover {{
                background: {self.theme.bg_panel};
                border-radius: 4px;
            }}
        """)
        self.btn_toggle_left.clicked.connect(self._toggle_left_panel)
        header_lay.addWidget(self.btn_toggle_left)

        self.label_left_title = QLabel("📁  ФАЙЛЫ")
        self.label_left_title.setStyleSheet(f"""
            color: {self.theme.text_muted};
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 1.2px;
            background: transparent;
        """)
        header_lay.addWidget(self.label_left_title)
        header_lay.addStretch()

        self.btn_add_file = QPushButton("+")
        self.btn_add_file.setFixedSize(22, 22)
        self.btn_add_file.setToolTip("Открыть файл")
        self.btn_add_file.setCursor(Qt.PointingHandCursor)
        self.btn_add_file.setStyleSheet(f"""
            QPushButton {{
                background: {self.theme.primary};
                color: {self.theme.text_inverse};
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
                padding: 0;
            }}
            QPushButton:hover {{ background: #9ade4f; }}
        """)
        self.btn_add_file.clicked.connect(self.open_file)
        header_lay.addWidget(self.btn_add_file)

        outer.addWidget(self.left_header, 0, Qt.AlignTop)
        outer.addSpacing(6)

        # ═══ КОНТЕНТ ═══
        self.left_content = QWidget()
        self.left_content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(self.left_content)
        layout.setContentsMargins(12, 0, 10, 0)
        layout.setSpacing(0)

        list_qss = _list_qss(self.theme)

        # ── Кнопка удалить ──
        files_header = QHBoxLayout()
        files_header.setContentsMargins(0, 0, 0, 0)
        files_header.setSpacing(4)
        files_header.addStretch()

        self.btn_delete_files = QPushButton("🗑")
        self.btn_delete_files.setFixedSize(22, 22)
        self.btn_delete_files.setToolTip("Удалить выбранные файлы")
        self.btn_delete_files.setCursor(Qt.PointingHandCursor)
        self.btn_delete_files.setEnabled(False)
        self.btn_delete_files.setStyleSheet(f"""
            QPushButton {{
                background: {self.theme.bg_panel};
                color: {self.theme.text_muted};
                border: 1px solid {self.theme.border};
                border-radius: 6px;
                font-size: 12px;
                padding: 0;
            }}
            QPushButton:hover:enabled {{
                background: rgba(231, 76, 60, 0.15);
                color: #e74c3c;
                border: 1px solid rgba(231, 76, 60, 0.5);
            }}
            QPushButton:disabled {{
                color: {self.theme.text_muted};
                opacity: 0.4;
            }}
        """)
        self.btn_delete_files.clicked.connect(self._on_delete_selected_files)
        files_header.addWidget(self.btn_delete_files)

        layout.addLayout(files_header)
        layout.addSpacing(6)

        # ── Список файлов ──
        self.files_stack = QStackedWidget()
        self.files_stack.setStyleSheet("background: transparent;")

        self.files_list = QListWidget()
        self.files_list.setIconSize(QSize(18, 18))
        self.files_list.setStyleSheet(list_qss)
        self.files_list.setFrameShape(QFrame.NoFrame)
        self.files_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.files_list.itemClicked.connect(self._on_file_clicked)
        self.files_list.itemSelectionChanged.connect(self._update_files_buttons)
        self.files_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.files_list.customContextMenuRequested.connect(self._on_files_context_menu)
        self.files_stack.addWidget(self.files_list)

        files_empty = QLabel("Перетащите файл\nили нажмите  +")
        files_empty.setAlignment(Qt.AlignCenter)
        files_empty.setStyleSheet(f"""
            color: {self.theme.text_muted};
            font-size: 12px;
            padding: 30px 10px;
            background: transparent;
            line-height: 1.5;
        """)
        self.files_stack.addWidget(files_empty)
        self.files_stack.setCurrentIndex(1)

        layout.addWidget(self.files_stack, stretch=1)

        del_shortcut = QShortcut(QKeySequence.Delete, self.files_list)
        del_shortcut.activated.connect(self._on_delete_selected_files)

        # ── Разделитель ──
        layout.addSpacing(12)
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {self.theme.border}; border: none;")
        layout.addWidget(sep)
        layout.addSpacing(12)

        # ── Колонки ──
        cols_header = QHBoxLayout()
        cols_header.setContentsMargins(0, 0, 0, 0)
        cols_header.setSpacing(4)

        label_cols = QLabel("📊  КОЛОНКИ")
        label_cols.setStyleSheet(f"""
            color: {self.theme.text_muted};
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 1.2px;
            background: transparent;
        """)
        cols_header.addWidget(label_cols)
        cols_header.addStretch()

        self.btn_edit = QPushButton("Изменить")
        self.btn_edit.setMinimumWidth(90)
        self.btn_edit.setCursor(Qt.PointingHandCursor)
        self.btn_edit.setStyleSheet(_pill_btn_qss(self.theme, active=False))
        self.btn_edit.clicked.connect(self._toggle_edit_mode)
        cols_header.addWidget(self.btn_edit)

        btn_show_all = QPushButton("Все")
        btn_show_all.setMinimumWidth(60)
        btn_show_all.setCursor(Qt.PointingHandCursor)
        btn_show_all.setStyleSheet(_pill_btn_qss(self.theme, active=True))
        btn_show_all.clicked.connect(self._show_all_columns)
        cols_header.addWidget(btn_show_all)

        btn_reset = QPushButton("Сброс")
        btn_reset.setMinimumWidth(70)
        btn_reset.setCursor(Qt.PointingHandCursor)
        btn_reset.setStyleSheet(_pill_btn_qss(self.theme, active=False))
        btn_reset.clicked.connect(self._hide_all_columns)
        cols_header.addWidget(btn_reset)

        layout.addLayout(cols_header)
        layout.addSpacing(6)

        self.cols_stack = QStackedWidget()
        self.cols_stack.setStyleSheet("background: transparent;")

        self.tree_columns = ColumnsTree()
        self.tree_columns.setStyleSheet(list_qss)
        self.tree_columns.setFrameShape(QFrame.NoFrame)
        self.tree_columns.itemChanged.connect(self._on_column_item_changed)
        self.tree_columns.itemClicked.connect(self._on_column_clicked)
        self.tree_columns.order_changed.connect(self._on_columns_reordered)
        self.tree_columns.delete_columns_requested.connect(self._on_delete_columns_requested)
        self.cols_stack.addWidget(self.tree_columns)

        cols_empty = QLabel("Колонки появятся\nпосле загрузки файла")
        cols_empty.setAlignment(Qt.AlignCenter)
        cols_empty.setStyleSheet(f"""
            color: {self.theme.text_muted};
            font-size: 12px;
            padding: 30px 10px;
            background: transparent;
            line-height: 1.5;
        """)
        self.cols_stack.addWidget(cols_empty)
        self.cols_stack.setCurrentIndex(1)

        layout.addWidget(self.cols_stack, stretch=1)

        outer.addWidget(self.left_content, stretch=1)

        return widget

    def _refresh_left_empty_states(self):
        if not hasattr(self, "files_stack"):
            return
        has_files = len(self.file_manager.get_all()) > 0
        self.files_stack.setCurrentIndex(0 if has_files else 1)
        self.cols_stack.setCurrentIndex(0 if has_files else 1)

    def _build_center_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.pages = QStackedWidget()

        # ── 0. Старт ──
        self.start_page = StartPage(self.theme)
        self.start_page.navigate_to.connect(self._on_start_navigate)
        self.pages.addWidget(self.start_page)

        # ── 1. Редактор: QTabWidget [Данные] [Код] ──
        self.editor_tabs = QTabWidget()
        self.editor_tabs.setDocumentMode(True)
        self._apply_tabs_style(self.editor_tabs)

        self.data_viewer = DataViewerWidget(self.theme)
        self.data_viewer.column_selected.connect(self._on_table_column_selected)
        self.data_viewer.cell_edit_requested.connect(self._on_table_cell_edit)
        self.data_viewer.column_rename_requested.connect(self._on_table_column_rename)
        self.data_viewer.delete_columns_requested.connect(self._on_delete_columns_requested)
        self.data_viewer.delete_rows_requested.connect(self._on_delete_rows_requested)
        self.data_viewer.filter_requested.connect(self._on_filter_requested)
        self.data_viewer.sort_requested.connect(self._on_sort_requested)
        self.data_viewer.sheet_switch_requested.connect(self._on_sheet_switch)
        self.data_viewer.pivot_edit_requested.connect(self._on_pivot_edit)
        self.data_viewer.sheet_rename_requested.connect(self._on_sheet_rename)
        self.editor_tabs.addTab(self.data_viewer, "📋   Данные")

        self.code_editor = CodeEditorWidget(self.theme)
        self.code_editor.btn_refresh.clicked.connect(self._refresh_code)
        self.code_editor.btn_copy.clicked.connect(self.code_editor.copy_to_clipboard)
        self.code_editor.btn_save.clicked.connect(self._save_code)
        self.editor_tabs.addTab(self.code_editor, "🐍   Код")

        self.editor_tabs.currentChanged.connect(self._on_editor_subtab_changed)
        self.pages.addWidget(self.editor_tabs)

        # ── 2. Конструктор ──
        self.constructor = ConstructorTab(self.theme, self.report)
        self.pages.addWidget(self.constructor)

        layout.addWidget(self.pages)
        return widget

    def _apply_tabs_style(self, tabs_widget=None):
        """Стиль вкладок как кнопок-пилюль."""
        if tabs_widget is None:
            tabs_widget = self.pages
        t = self.theme
        tabs_widget.setStyleSheet(f"""
            QTabWidget::pane {{
                border: none;
                background: {t.bg_card};
                top: -1px;
            }}
            QTabWidget::tab-bar {{
                alignment: left;
                left: 12px;
            }}
            QTabBar {{
                background: {t.bg_page};
                qproperty-drawBase: 0;
            }}
            QTabBar::tab {{
                background: {t.bg_panel};
                color: {t.text_muted};
                border: 1px solid {t.border};
                border-radius: 8px;
                padding: 8px 18px;
                margin: 6px 6px 6px 0px;
                font-size: 13px;
                font-weight: 600;
                min-height: 20px;
            }}
            QTabBar::tab:hover:!selected {{
                background: {t.bg_hover};
                color: {t.text_main};
                border: 1px solid {t.primary};
            }}
            QTabBar::tab:selected {{
                background: {t.primary_hover};
                color: {t.text_main};
                border: 1px solid {t.primary};
            }}
        """)

    def _build_right_container(self) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.center_panel = self._build_center_panel()
        layout.addWidget(self.center_panel, stretch=1)

        self.right_content = QStackedWidget()
        self.right_content.setMinimumWidth(320)
        self.right_content.setMaximumWidth(360)
        self.right_content.setStyleSheet(f"background: {self.theme.bg_page};")

        self.inspector = InspectorPanel(self.theme)
        self.inspector.column_updated.connect(self._on_inspector_apply)
        self.inspector.column_cast_requested.connect(self._on_column_cast)
        self.inspector.column_split_requested.connect(self._on_column_split)
        self.right_content.addWidget(self._wrap_with_title(self.inspector, "⚙️  ИНСПЕКТОР"))

        self.data_panel = DataPanel(self.theme)
        self.data_panel.sort_reset_requested.connect(self._clear_sort)
        self.data_panel.filters_reset_requested.connect(self._clear_all_filters)
        self.data_panel.filter_remove_requested.connect(self._on_remove_filter)
        self.data_panel.drop_duplicates_requested.connect(self._on_drop_duplicates)
        self.data_panel.drop_na_requested.connect(self._on_drop_na)
        self.data_panel.normalize_text_requested.connect(self._on_normalize_text)
        self.data_panel.extract_text_requested.connect(self._on_extract_text)
        self.right_content.addWidget(self._wrap_with_title(self.data_panel, "📊  ДАННЫЕ"))

        links_stub = QLabel("🔗  Раздел «Связи»\n\nБудет здесь позже.")
        links_stub.setAlignment(Qt.AlignCenter)
        links_stub.setStyleSheet(f"color: {self.theme.text_muted}; font-size: 12px; padding: 40px;")
        self.right_content.addWidget(self._wrap_with_title(links_stub, "🔗  СВЯЗИ"))

        style_stub = QLabel("🎨  Раздел «Стиль»\n\nБудет здесь позже.")
        style_stub.setAlignment(Qt.AlignCenter)
        style_stub.setStyleSheet(f"color: {self.theme.text_muted}; font-size: 12px; padding: 40px;")
        self.right_content.addWidget(self._wrap_with_title(style_stub, "🎨  СТИЛЬ"))

        self.right_content.setCurrentIndex(0)
        self.right_content.hide()

        layout.addWidget(self.right_content)

        self.rail = SideRail(self.theme)
        self.rail.section_selected.connect(self._on_rail_section_selected)
        self.rail.theme_toggled.connect(self._on_toggle_theme)
        layout.addWidget(self.rail)

        self.right_container = container
        return container

    def _wrap_with_title(self, widget: QWidget, title: str) -> QWidget:
        outer = QWidget()
        outer.setStyleSheet(f"background: {self.theme.bg_page};")
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(8, 8, 8, 8)
        outer_layout.setSpacing(0)

        card = QWidget()
        card.setObjectName("right_panel_card")
        card.setStyleSheet(f"""
            #right_panel_card {{
                background: {self.theme.bg_card};
                border: 1px solid {self.theme.border};
                border-radius: 12px;
            }}
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        header = QWidget()
        header.setStyleSheet(f"""
            background: transparent;
            border: none;
            border-bottom: 1px solid {self.theme.border};
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 12, 10, 12)
        header_layout.setSpacing(8)

        label = QLabel(title)
        label.setStyleSheet(f"""
            color: {self.theme.text_muted};
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 1.2px;
            background: transparent;
            border: none;
        """)
        header_layout.addWidget(label)
        header_layout.addStretch()

        btn_close = QPushButton("×")
        btn_close.setFixedSize(24, 24)
        btn_close.setToolTip("Свернуть панель")
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {self.theme.text_muted};
                border: none;
                border-radius: 12px;
                font-size: 18px;
                font-weight: 400;
                padding: 0;
            }}
            QPushButton:hover {{
                background: {self.theme.bg_panel};
                color: {self.theme.text_main};
            }}
        """)
        btn_close.clicked.connect(self._hide_content)
        header_layout.addWidget(btn_close)

        card_layout.addWidget(header)

        body = QWidget()
        body.setStyleSheet("background: transparent; border: none;")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(14, 12, 14, 14)
        body_layout.setSpacing(0)
        body_layout.addWidget(widget)
        card_layout.addWidget(body, stretch=1)

        outer_layout.addWidget(card)
        return outer

    def _build_statusbar(self):
        self.statusBar().showMessage("✅ Готово.")

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._apply_start_layout)

    def _apply_start_layout(self):
        self._switch_page(0)

    def closeEvent(self, event):
        modified = [e for e in self.file_manager.get_all() if e.is_modified]
        if modified:
            names = ", ".join(f"«{e.display_name}»" for e in modified[:3])
            if len(modified) > 3:
                names += f" и ещё {len(modified) - 3}"
            reply = QMessageBox.question(
                self, "Есть несохранённые изменения",
                f"Не сохранены изменения в файлах: {names}.\n\nВыйти без сохранения?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                event.ignore()
                return

        print("[MainWindow] Закрытие приложения...")
        event.accept()
        QTimer.singleShot(100, lambda: os._exit(0))

    # ============================================================
    # Файлы
    # ============================================================

    def _refresh_files_list(self):
        self.files_list.blockSignals(True)
        self.files_list.clear()
        active_id = self.file_manager.get_active_id()
        icon_provider = QFileIconProvider()

        for entry in self.file_manager.get_all():
            file_info = QFileInfo(entry.data.source_path)
            icon = icon_provider.icon(file_info)
            if icon.isNull():
                icon = self.style().standardIcon(QStyle.SP_FileIcon)

            marker = "● " if entry.id == active_id else "○ "
            modified = " *" if entry.is_modified else ""
            text = f"{marker}{entry.display_name}{modified}"

            item = QListWidgetItem(text)
            item.setIcon(icon)
            item.setData(Qt.UserRole, entry.id)
            item.setToolTip(entry.data.source_path)
            self.files_list.addItem(item)

        self.files_list.blockSignals(False)
        self._refresh_left_empty_states()
        self._update_files_buttons()

    def _update_files_buttons(self):
        if not hasattr(self, 'btn_delete_files'):
            return
        selected_count = len(self.files_list.selectedItems())
        total_files = len(self.file_manager.get_all())

        self.btn_delete_files.setEnabled(total_files > 0)

        if selected_count > 0:
            self.btn_delete_files.setToolTip(
                f"Удалить выбранные файлы ({selected_count}) — Del"
            )
        elif total_files > 0:
            self.btn_delete_files.setToolTip(
                f"Удалить все файлы ({total_files}) — ничего не выделено"
            )
        else:
            self.btn_delete_files.setToolTip("Нет файлов для удаления")

    def _on_delete_selected_files(self):
        selected = self.files_list.selectedItems()

        if not selected:
            total = len(self.file_manager.get_all())
            if total == 0:
                return
            reply = QMessageBox.question(
                self, "Удалить все файлы",
                f"Ничего не выбрано.\n\nУдалить все файлы ({total})?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
            self._on_delete_all_files()
            return

        file_ids = [it.data(Qt.UserRole) for it in selected]
        file_ids = [fid for fid in file_ids if fid is not None]
        if not file_ids:
            return

        entries = []
        for fid in file_ids:
            e = self.file_manager.get_file(fid)
            if e is not None:
                entries.append(e)

        if not entries:
            return

        if len(entries) == 1:
            text = f"Удалить файл «{entries[0].display_name}»?"
        else:
            text = f"Удалить {len(entries)} файлов?"

        modified = [e for e in entries if e.is_modified]
        if modified:
            names = ", ".join(f"«{m.display_name}»" for m in modified[:3])
            if len(modified) > 3:
                names += f" и ещё {len(modified) - 3}"
            text += (
                f"\n\nЕсть несохранённые изменения:\n{names}\n\n"
                f"Продолжить без сохранения?"
            )

        reply = QMessageBox.question(
            self, "Удаление файлов", text,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        for fid in file_ids:
            self.file_manager.remove_file(fid)

        active = self.file_manager.get_active()
        if active:
            self.current_data = active.data
            self.history = active.history
            self._sort_state = []
            self._update_columns_tree(self.current_data)
            self._update_data_viewer(self.current_data)
        else:
            self.current_data = None
            self.history = HistoryManager(max_size=50)
            self.tree_columns.clear()
            self.data_viewer.clear()
            self._sort_state = []
            self._update_data_panel()
            self._update_sheet_combo()

        self._update_undo_buttons()
        self._refresh_files_list()

        count = len(entries)
        word = "файл" if count == 1 else ("файла" if 2 <= count <= 4 else "файлов")
        ToastManager.info("Удалено", f"{count} {word}", self.theme)

    def _on_delete_all_files(self):
        entries = self.file_manager.get_all()
        if not entries:
            return

        count = len(entries)
        modified = [e for e in entries if e.is_modified]

        text = f"Удалить все файлы ({count})?"
        if modified:
            text += (
                f"\n\nЕсть несохранённые изменения в {len(modified)} "
                f"файл{'е' if len(modified) == 1 else 'ах'}.\n\n"
                f"Продолжить без сохранения?"
            )

        reply = QMessageBox.question(
            self, "Удалить всё", text,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self.file_manager.remove_all()

        self.current_data = None
        self.history = HistoryManager(max_size=50)
        self.tree_columns.clear()
        self.data_viewer.clear()
        self._sort_state = []
        self._update_data_panel()
        self._update_undo_buttons()
        self._refresh_files_list()

        ToastManager.info("Всё удалено", f"Удалено файлов: {count}", self.theme)

    def _on_file_clicked(self, item):
        file_id = item.data(Qt.UserRole)
        if file_id is None:
            return
        self._switch_to_file(file_id)

    def _switch_to_file(self, file_id: str):
        if not self.file_manager.set_active(file_id):
            return
        entry = self.file_manager.get_file(file_id)
        if entry is None:
            return
        self.current_data = entry.data
        self.history = entry.history
        self._sort_state = []
        self.data_viewer.set_sort_state([])
        self._update_columns_tree(self.current_data)
        self._update_data_viewer(self.current_data)
        self._update_undo_buttons()
        self._refresh_files_list()
        self.statusBar().showMessage(
            f"📊 {entry.display_name}: {entry.data.rows_count:,} строк, "
            f"{entry.data.cols_count} колонок"
        )

    def _on_files_context_menu(self, position):
        item = self.files_list.itemAt(position)

        menu = QMenu(self)
        file_id = None
        entry = None

        if item is not None:
            file_id = item.data(Qt.UserRole)
            if file_id:
                entry = self.file_manager.get_file(file_id)

        action_save = None
        action_save_as = None
        action_delete = None
        action_delete_all = None

        if entry is not None:
            action_save = menu.addAction(f"💾  Сохранить «{entry.display_name}»")
            action_save_as = menu.addAction("💾  Сохранить как...")
            menu.addSeparator()

            selected_count = len(self.files_list.selectedItems())
            if selected_count > 1:
                action_delete = menu.addAction(f"🗑  Удалить выбранные ({selected_count})")
            else:
                action_delete = menu.addAction(f"🗑  Удалить «{entry.display_name}»")

        if self.file_manager.get_all():
            if entry is not None:
                menu.addSeparator()
            action_delete_all = menu.addAction("🗑  Удалить все файлы")

        if menu.isEmpty():
            return

        chosen = menu.exec(self.files_list.mapToGlobal(position))
        if chosen is None:
            return

        if action_save is not None and chosen == action_save:
            self._switch_to_file(file_id)
            self._on_save()
        elif action_save_as is not None and chosen == action_save_as:
            self._switch_to_file(file_id)
            self._on_save_as()
        elif action_delete is not None and chosen == action_delete:
            if entry is not None and len(self.files_list.selectedItems()) <= 1:
                for i in range(self.files_list.count()):
                    it = self.files_list.item(i)
                    if it.data(Qt.UserRole) == file_id:
                        it.setSelected(True)
                        break
            self._on_delete_selected_files()
        elif action_delete_all is not None and chosen == action_delete_all:
            self._on_delete_all_files()

    def _close_active_file(self):
        file_id = self.file_manager.get_active_id()
        if file_id:
            self._close_file(file_id)

    def _close_file(self, file_id: str):
        entry = self.file_manager.get_file(file_id)
        if entry is None:
            return

        if entry.is_modified:
            reply = QMessageBox.question(
                self, "Файл изменён",
                f"Файл «{entry.display_name}» был изменён.\n\nСохранить перед закрытием?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                QMessageBox.Yes,
            )
            if reply == QMessageBox.Cancel:
                return
            if reply == QMessageBox.Yes:
                self._switch_to_file(file_id)
                if not self._on_save():
                    return

        self.file_manager.remove_file(file_id)
        active = self.file_manager.get_active()
        if active:
            self.current_data = active.data
            self.history = active.history
            self._update_columns_tree(self.current_data)
            self._update_data_viewer(self.current_data)
        else:
            self.current_data = None
            self.history = HistoryManager(max_size=50)
            self.tree_columns.clear()
            self.data_viewer.clear()
            self._sort_state = []
            self._update_data_panel()

        self._update_undo_buttons()
        self._refresh_files_list()
        ToastManager.info("Файл закрыт", f"«{entry.display_name}»", self.theme)

    # ============================================================
    # Сохранение
    # ============================================================

    def _on_save(self) -> bool:
        if self.current_data is None:
            return False
        entry = self.file_manager.get_active()
        if entry is None:
            return False

        target = entry.data.source_path

        if not target or not os.path.exists(target):
            return self._on_save_as()

        if not self._check_file_writable(target):
            return False

        choice = self._ask_save_mode(target)
        if choice == "cancel":
            return False
        elif choice == "overwrite":
            return self._save_to_path(entry, target)
        elif choice == "save_as":
            return self._on_save_as()

        return False

    def _ask_save_mode(self, path: str) -> str:
        box = QMessageBox(self)
        box.setWindowTitle("Сохранить файл")
        box.setIcon(QMessageBox.Question)
        box.setText("Как сохранить файл?")
        box.setInformativeText(f"Исходный файл:\n{path}")

        btn_overwrite = box.addButton("💾 Перезаписать", QMessageBox.AcceptRole)
        btn_save_as = box.addButton("📁 Сохранить как...", QMessageBox.ActionRole)
        btn_cancel = box.addButton("Отмена", QMessageBox.RejectRole)

        box.setDefaultButton(btn_overwrite)
        box.exec()

        clicked = box.clickedButton()
        if clicked == btn_overwrite:
            return "overwrite"
        elif clicked == btn_save_as:
            return "save_as"
        return "cancel"

    def _on_save_as(self) -> bool:
        if self.current_data is None:
            return False

        entry = self.file_manager.get_active()
        if entry is None:
            return False

        settings = get_settings()
        last_dir = settings.get_last_project_dir()

        if entry.data.source_path:
            stem = Path(entry.data.source_path).stem
            suggested = f"{stem}_processed.xlsx"
        else:
            suggested = "output.xlsx"

        dlg = ProjectFileDialog(
            self.theme,
            mode="save",
            title="Сохранить как",
            filters=[
                ("Excel файлы (*.xlsx)", "*.xlsx"),
                ("Все файлы (*)", "*"),
            ],
            start_dir=last_dir,
            default_name=suggested,
            default_ext=".xlsx",
            parent=self,
        )
        if dlg.exec() != ProjectFileDialog.Accepted or not dlg.selected_path:
            return False
        filepath = dlg.selected_path

        try:
            settings.set_last_project_dir(str(Path(filepath).parent))
        except Exception:
            pass

        return self._save_to_path(entry, filepath)

    def _save_to_path(self, entry, target: str) -> bool:
        try:
            import tempfile
            import shutil

            tmp_dir = tempfile.gettempdir()
            tmp_path = str(Path(tmp_dir) / f"ea_save_{os.getpid()}.xlsx")

            sheets = entry.data.get_sheets_for_save()
            with pd.ExcelWriter(tmp_path, engine="openpyxl") as writer:
                for sname, sdf in sheets:
                    safe_name = str(sname)[:31]
                    for ch in ':\\/?*[]':
                        safe_name = safe_name.replace(ch, "_")
                    if not safe_name:
                        safe_name = "Sheet1"
                    sdf.to_excel(writer, sheet_name=safe_name, index=False)
            shutil.move(tmp_path, target)

        except PermissionError:
            QMessageBox.critical(
                self, "Файл занят",
                f"Не удалось записать файл:\n{target}\n\n"
                f"Возможно, он открыт в другой программе (Excel).\n"
                f"Закройте файл и попробуйте снова."
            )
            return False
        except Exception as e:
            import traceback
            traceback.print_exc()
            QMessageBox.critical(
                self, "Ошибка сохранения",
                f"Не удалось сохранить файл:\n{type(e).__name__}: {e}"
            )
            return False

        entry.is_modified = False
        entry.data.source_path = target
        self._refresh_files_list()
        self._update_undo_buttons()

        ToastManager.success("Файл сохранён", target, self.theme)
        self.statusBar().showMessage(f"💾 Сохранено: {target}")
        return True

    def _check_file_writable(self, path: str) -> bool:
        if not os.path.exists(path):
            return True
        try:
            with open(path, "a+b"):
                pass
            return True
        except PermissionError:
            QMessageBox.critical(
                self, "Файл занят",
                f"Файл открыт в другой программе:\n{path}\n\n"
                f"Закройте его и попробуйте снова."
            )
            return False
        except Exception:
            return True

    # ============================================================
    # Вкладки, код
    # ============================================================

    def _switch_page(self, index: int):
        """Переключение между Старт / Редактор / Конструктор."""
        self._current_page = index
        if hasattr(self, "pages"):
            self.pages.setCurrentIndex(index)

        buttons = getattr(self, "_nav_buttons", [])
        alive = []
        for b in buttons:
            try:
                b.setChecked(False)
                alive.append(b)
            except RuntimeError:
                continue
        self._nav_buttons = alive

        for i, b in enumerate(alive):
            try:
                b.setChecked(i == index)
            except RuntimeError:
                continue

        if index == 2 and hasattr(self, "constructor"):
            try:
                self.constructor.set_data(self.current_data)
            except RuntimeError:
                pass

        if index == 1 and hasattr(self, "editor_tabs"):
            try:
                if self.editor_tabs.currentIndex() == 1:
                    self._refresh_code()
            except RuntimeError:
                pass

        self._apply_page_layout(index)

    def _is_code_tab_active(self) -> bool:
        if not hasattr(self, "editor_tabs"):
            return False
        return (self._current_page == 1
                and self.editor_tabs.currentIndex() == 1)

    def _on_editor_subtab_changed(self, index: int):
        """Переключение подвкладок внутри Редактора (0=Данные, 1=Код)."""
        if index == 1:
            self._refresh_code()

    def _toggle_left_panel(self):
        """Свернуть / развернуть левую панель."""
        if not hasattr(self, "main_splitter"):
            return

        self._left_panel_collapsed = not self._left_panel_collapsed
        sizes = self.main_splitter.sizes()
        total = sizes[0] + sizes[1]

        if self._left_panel_collapsed:
            if sizes[0] > 90:
                self._left_panel_expanded_width = sizes[0]

            self.left_content.setMaximumHeight(0)
            self.label_left_title.hide()
            self.btn_toggle_left.setText(">>")
            self.btn_toggle_left.setToolTip("Развернуть панель")

            self.main_splitter.setSizes([78, total - 78])
        else:
            self.left_content.setMaximumHeight(16777215)
            self.label_left_title.show()
            self.btn_toggle_left.setText("<<")
            self.btn_toggle_left.setToolTip("Свернуть панель")

            w = self._left_panel_expanded_width
            self.main_splitter.setSizes([w, total - w])

    def _apply_page_layout(self, index: int):
        """
        Показываем/скрываем панели в зависимости от страницы.
        """
        is_editor = (index == 1)
        is_constructor = (index == 2)
        is_start = (index == 0)

        # ── Полоса навигации (🏠 📊 🎨) — скрываем на Старте ──
        if hasattr(self, "top_nav"):
            self.top_nav.setVisible(not is_start)

        # ── Менюбар целиком скрываем на Старте ──
        if self.menuBar() is not None:
            self.menuBar().setVisible(not is_start)

        # ── Меню «Отчёт» убрано — проверяем на None для совместимости ──
        if getattr(self, "report_menu", None) is not None:
            self.report_menu.setVisible(is_constructor)

        # ── Тулбар — только на Редакторе ──
        # Тулбар действий — только на Редакторе
        if hasattr(self, "top_toolbar") and self.top_toolbar is not None:
            self.top_toolbar.setVisible(is_editor)

        # ── Левая панель — только на Редакторе ──
        if hasattr(self, "main_splitter"):
            left = self.main_splitter.widget(0)
            if left is not None:
                left.setVisible(is_editor)

        # ── Rail — только на Редакторе ──
        if hasattr(self, "rail"):
            self.rail.setVisible(is_editor)

        # ── Правая панель — только на Редакторе ──
        if hasattr(self, "right_content"):
            if is_editor and self._content_visible:
                self.right_content.show()
            else:
                self.right_content.hide()

    def _go_home(self):
        """Вернуться на стартовую страницу."""
        self._switch_page(0)

    def _on_start_navigate(self, target: str):
        """Навигация со стартовой страницы."""
        if target in ("editor", "code"):
            self._switch_page(1)
            if target == "code" and hasattr(self, "editor_tabs"):
                self.editor_tabs.setCurrentIndex(1)
        elif target in ("constructor", "export"):
            self._switch_page(2)
            if target == "export" and hasattr(self, "constructor"):
                self.constructor.show_export_tab()
        else:
            self._switch_page(1)

    def _refresh_code(self):
        if self.current_data is None:
            self.code_editor.set_code(
                "# Файл не загружен\n"
                "# Загрузите XLSX-файл и сделайте изменения — скрипт появится здесь"
            )
            return

        try:
            entry = self.file_manager.get_active()
            if entry is None:
                return
            operations = entry.operations.get_all()
            if not operations:
                self.code_editor.set_code(
                    "# Операций пока нет\n"
                    "# Сделайте какие-нибудь действия с данными — они появятся здесь"
                )
                return
            source_path = entry.data.source_path
            sheet_name = entry.data.sheet_name or "Sheet1"
            code = generate_script(
                operations=operations,
                file_name=source_path,
                sheet_name=sheet_name,
                reset_index=False,
            )
            self.code_editor.set_code(code)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.code_editor.set_code(f"# Ошибка генерации:\n# {type(e).__name__}: {e}")

    def _save_code(self):
        if self.current_data is None:
            return
        entry = self.file_manager.get_active()
        if entry is None:
            return
        stem = Path(entry.data.source_path).stem
        default_name = f"{stem}_processed.py"
        self.code_editor.save_to_file(default_name)

    # ============================================================
    # Проект .eaproj
    # ============================================================

    def _on_save_project(self):
        entries = self.file_manager.get_all()
        if not entries:
            ToastManager.info("Нет файлов", "Сначала откройте хотя бы один файл", self.theme)
            return

        dlg = SaveProjectDialog(self.theme, self)
        if dlg.exec() != SaveProjectDialog.Accepted:
            return

        from datetime import datetime

        settings = get_settings()
        last_dir = settings.get_last_project_dir()

        if len(entries) == 1:
            default_name = Path(entries[0].display_name).stem + ".eaproj"
        else:
            default_name = f"project_{datetime.now().strftime('%Y%m%d_%H%M')}.eaproj"

        file_dlg = ProjectFileDialog(
            self.theme,
            mode="save",
            title="Сохранить проект",
            filters=[
                ("Проекты Excel Analyzer (*.eaproj)", "*.eaproj"),
                ("Все файлы (*)", "*"),
            ],
            start_dir=last_dir,
            default_name=default_name,
            default_ext=".eaproj",
            parent=self,
        )
        if file_dlg.exec() != ProjectFileDialog.Accepted or not file_dlg.selected_path:
            return
        filepath = file_dlg.selected_path

        settings.set_last_project_dir(str(Path(filepath).parent))
        settings.set_last_project_file(filepath)

        extra = {
            "active_tab": getattr(self, "_current_page", 0),
            "theme": "dark" if self.theme.is_dark else "light",
            "tabs_format": 2,
        }

        ok, msg = ProjectIO.save(
            path=filepath,
            entries=entries,
            active_file_id=self.file_manager.get_active_id(),
            extra=extra,
            password=dlg.password,
        )

        if ok:
            ToastManager.success("Проект сохранён", msg, self.theme)
            self.statusBar().showMessage(f"📦 {filepath}")
        else:
            ToastManager.error("Ошибка сохранения", msg, self.theme)
            QMessageBox.critical(self, "Ошибка сохранения проекта", msg)

    def _on_open_project(self):
        settings = get_settings()
        last_dir = settings.get_last_project_dir()

        file_dlg = ProjectFileDialog(
            self.theme,
            mode="open",
            title="Открыть проект",
            filters=[
                ("Проекты Excel Analyzer (*.eaproj)", "*.eaproj"),
                ("Все файлы (*)", "*"),
            ],
            start_dir=last_dir,
            parent=self,
        )
        if file_dlg.exec() != ProjectFileDialog.Accepted or not file_dlg.selected_path:
            return
        filepath = file_dlg.selected_path

        settings.set_last_project_dir(str(Path(filepath).parent))
        self._open_project_by_path(filepath)

    def _open_project_by_path(self, filepath: str):
        password = None
        for _attempt in range(3):
            state, msg = ProjectIO.load(filepath, password=password)

            if state is not None:
                break

            if msg == "PASSWORD_REQUIRED":
                dlg = OpenProjectPasswordDialog(
                    self.theme, Path(filepath).name, "", self,
                )
                if dlg.exec() != OpenProjectPasswordDialog.Accepted:
                    return
                password = dlg.password
                continue

            if msg == "PASSWORD_WRONG":
                dlg = OpenProjectPasswordDialog(
                    self.theme, Path(filepath).name,
                    "Неверный пароль. Попробуйте снова.", self,
                )
                if dlg.exec() != OpenProjectPasswordDialog.Accepted:
                    return
                password = dlg.password
                continue

            if msg == "MACHINE_MISMATCH":
                QMessageBox.critical(
                    self,
                    "Проект зашифрован для другого ПК",
                    "Этот проект был сохранён на другой машине без пароля.\n\n"
                    "Чтобы перенести его, сохраните проект заново с паролем\n"
                    "или откройте его на исходном ПК.",
                )
                return

            if msg == "NOT_A_PROJECT":
                QMessageBox.warning(
                    self,
                    "Это не файл проекта",
                    f"Файл не является проектом Excel Analyzer:\n\n"
                    f"{filepath}\n\n"
                    f"Возможные причины:\n"
                    f"  • файл не был создан в Excel Analyzer (например, "
                    f"это переименованный .xlsx или .txt);\n"
                    f"  • файл повреждён или не до конца скопирован;\n"
                    f"  • расширение .eaproj установлено вручную.\n\n"
                    f"Проверьте, что выбран правильный файл.",
                )
                return

            QMessageBox.critical(self, "Ошибка открытия проекта", msg)
            return
        else:
            QMessageBox.warning(
                self, "Не удалось открыть",
                "Исчерпано 3 попытки ввода пароля.",
            )
            return

        self._apply_project_state(state)

    def _apply_project_state(self, state: dict):
        entries = state.get("entries", [])
        active_id = state.get("active_file_id")
        extra = state.get("extra", {})
        manifest = state.get("manifest", {})

        if not entries:
            ToastManager.error("Пустой проект", "В проекте нет файлов", self.theme)
            return

        for e in entries:
            if not hasattr(e.data, "operations") or e.data.operations is None:
                e.data.operations = e.operations
            e.data.file_id = e.id

        self.file_manager.restore_from_entries(entries, active_id)

        active = self.file_manager.get_active()
        if active is None and entries:
            active = entries[0]
            self.file_manager.set_active(active.id)

        if active is not None:
            self.current_data = active.data
            self.history = active.history

        self._sort_state = []
        if hasattr(self, 'data_viewer'):
            self.data_viewer.set_sort_state([])

        if self.current_data is not None:
            self._update_columns_tree(self.current_data)
            self._update_data_viewer(self.current_data)

        self._update_undo_buttons()
        self._refresh_files_list()

        tab_idx = int(extra.get("active_tab", 0))
        if extra.get("tabs_format", 1) < 2:
            tab_idx = {0: 0, 1: 1, 2: 2, 3: 1, 4: 2}.get(tab_idx, 0)
        if tab_idx < 0 or tab_idx > 2:
            tab_idx = 1
        self._switch_page(tab_idx)

        count = len(entries)
        files_str = f"{count} файл" + ("а" if 2 <= count <= 4 else "ов" if count != 1 else "")
        created = manifest.get("created_at", "")
        ToastManager.success(
            "Проект открыт",
            f"{files_str}, создан: {created}",
            self.theme,
        )
        self.statusBar().showMessage(f"📂 Проект загружен: {files_str}")

    # ============================================================
    # Тема
    # ============================================================

    def _on_toggle_theme(self):
        from PySide6.QtWidgets import QGraphicsOpacityEffect
        from PySide6.QtCore import QPropertyAnimation, QEasingCurve

        if hasattr(self, '_theme_animating') and self._theme_animating:
            return
        self._theme_animating = True

        was_content_visible = self._content_visible
        selected_column = self._selected_column
        active_tab = getattr(self, "_current_page", 0)
        active_rail_section = self.rail.get_active_section() if hasattr(self, 'rail') else "inspector"

        effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(effect)
        fade_out = QPropertyAnimation(effect, b"opacity")
        fade_out.setDuration(150)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.0)
        fade_out.setEasingCurve(QEasingCurve.OutCubic)

        self._fade_out_anim = fade_out
        self._fade_effect = effect
        self._theme_phase2_data = {
            "was_content_visible": was_content_visible,
            "selected_column": selected_column,
            "active_tab": active_tab,
            "active_rail_section": active_rail_section,
        }
        fade_out.finished.connect(self._theme_phase2)
        fade_out.start()

    def _theme_phase2(self):
        from PySide6.QtWidgets import QGraphicsOpacityEffect
        from PySide6.QtCore import QPropertyAnimation, QEasingCurve

        data = self._theme_phase2_data
        new_theme = toggle_theme()
        self.theme = new_theme
        name = "dark" if new_theme.is_dark else "light"
        self.settings.set_theme_name(name)

        self._rebuild_ui()

        self._content_visible = data["was_content_visible"]
        self._selected_column = data["selected_column"]

        if data["was_content_visible"]:
            self.right_content.show()
        self._switch_page(data.get("active_tab", 0))
        if hasattr(self, 'rail'):
            self.rail.set_active_section(data["active_rail_section"])

        if self.current_data:
            self._update_columns_tree(self.current_data)
            self._update_data_viewer(self.current_data)
            if data["selected_column"] and data["was_content_visible"]:
                col_info = self.current_data.get_column_info(data["selected_column"])
                if col_info:
                    self.inspector.show_column(col_info)

        effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(effect)
        fade_in = QPropertyAnimation(effect, b"opacity")
        fade_in.setDuration(150)
        fade_in.setStartValue(0.0)
        fade_in.setEndValue(1.0)
        fade_in.setEasingCurve(QEasingCurve.InCubic)
        self._fade_in_anim = fade_in
        fade_in.finished.connect(self._theme_phase3)
        fade_in.start()

    def _theme_phase3(self):
        self.setGraphicsEffect(None)
        self._theme_animating = False
        theme_name = "тёмная" if self.theme.is_dark else "светлая"
        ToastManager.info("Тема изменена", f"Включена {theme_name} тема", self.theme)

    def _rebuild_ui(self):
        """Пересобирает всё окно после смены темы."""
        self._nav_buttons = []
        self._left_panel_collapsed = False

        self.setStyleSheet(self.theme.to_qss())

        self.menuBar().clear()
        self._build_menu()

        for toolbar in self.findChildren(QToolBar):
            self.removeToolBar(toolbar)
            toolbar.deleteLater()

        old = self.centralWidget()
        self._build_ui()
        if old is not None:
            old.deleteLater()

        self._refresh_files_list()
        self._switch_page(getattr(self, "_current_page", 0))

    # ============================================================
    # Undo
    # ============================================================

    def _on_undo(self):
        if not self.history.can_undo():
            return

        desc = self.history.get_last_description()
        ok, description = self.history.undo()

        if ok:
            ToastManager.info("Отменено", description, self.theme)
            self.statusBar().showMessage(f"↶ Отменено: {description}")

            if desc and "ортировк" in desc:
                self._sort_state = []
                if self.current_data is not None:
                    self._update_data_viewer(self.current_data)
                    self.data_viewer.set_sort_state([])

            active_id = self.file_manager.get_active_id()
            if active_id:
                self.file_manager.mark_modified(active_id)
                self._refresh_files_list()

        self._update_undo_buttons()

    def _update_undo_buttons(self):
        can = self.history.can_undo()
        self.action_undo.setEnabled(can)

        # Обновляем tooltip у action (он есть всегда — создаётся в _build_menu)
        if can:
            desc = self.history.get_last_description()
            self.action_undo.setToolTip(f"Отменить: {desc}")
        else:
            self.action_undo.setToolTip("Нечего отменять")

        # Тулбарная кнопка «Отменить» — создаётся в _build_toolbar.
        # Может отсутствовать до первого _build_ui или после _rebuild_ui,
        # поэтому проверяем через hasattr.
        if hasattr(self, "action_undo_tb") and self.action_undo_tb is not None:
            self.action_undo_tb.setEnabled(can)
            if can:
                self.action_undo_tb.setToolTip(f"Отменить: {self.history.get_last_description()}")
            else:
                self.action_undo_tb.setToolTip("Нечего отменять")
    # ============================================================
    # Меню «Отчёт»
    # ============================================================

    def _on_report_new(self):
        if not hasattr(self, "constructor"):
            return
        self.constructor._on_new_report()

    def _on_report_open(self):
        if not hasattr(self, "constructor"):
            return
        self.constructor._on_open_report()

    def _on_report_save(self):
        if not hasattr(self, "constructor"):
            return
        self.constructor._on_save_report()

    def _on_report_export(self):
        if not hasattr(self, "constructor"):
            return
        self.constructor.show_export_tab()
        self.constructor._on_export_html()

    def _on_report_preview(self):
        if not hasattr(self, "constructor"):
            return
        self.constructor._on_preview()

    # ============================================================
    # Открытие файла
    # ============================================================

    def open_file(self):
        """Открыть файл: Excel (.xlsx/.xls), проект (.eaproj) или ярлык (.lnk)."""
        settings = get_settings()
        last_dir = settings.get_last_project_dir()

        dlg = ProjectFileDialog(
            self.theme,
            mode="open",
            title="Открыть файл или проект",
            filters=[
                ("Excel и проекты (*.xlsx *.xls *.eaproj)", "*.xlsx *.xls *.eaproj"),
                ("Excel файлы (*.xlsx *.xls)", "*.xlsx *.xls"),
                ("Проекты Excel Analyzer (*.eaproj)", "*.eaproj"),
                ("Все файлы (*)", "*"),
            ],
            start_dir=last_dir,
            parent=self,
        )
        if dlg.exec() != ProjectFileDialog.Accepted or not dlg.selected_path:
            return

        filepath = dlg.selected_path

        try:
            settings.set_last_project_dir(str(Path(filepath).parent))
        except Exception:
            pass

        if filepath.lower().endswith(".lnk"):
            real = _resolve_lnk(filepath)
            if not real:
                QMessageBox.information(
                    self,
                    "Ярлык не удалось открыть",
                    f"Не получилось определить цель ярлыка:\n\n{filepath}\n\n"
                    f"Попробуйте выбрать саму папку или файл.",
                )
                return
            filepath = real

        if os.path.isdir(filepath):
            self._open_folder_by_path(filepath)
            return

        if filepath.lower().endswith(".eaproj"):
            self._open_project_by_path(filepath)
            return

        if filepath.lower().endswith((".xlsx", ".xls")):
            self._open_excel_by_path(filepath)
            return

        reply = QMessageBox.question(
            self,
            "Неизвестный тип файла",
            f"Файл:\n{filepath}\n\n"
            f"Расширение не похоже на Excel или проект.\n"
            f"Попробовать открыть как Excel?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._open_excel_by_path(filepath)

    def open_folder(self):
        """Открыть папку с Excel-файлами — импорт выбранных."""
        settings = get_settings()
        last_dir = settings.get_last_project_dir()

        dlg = FolderOpenDialog(self.theme, last_dir, self)
        if dlg.exec() != FolderOpenDialog.Accepted:
            return

        self._import_files_from_list(dlg.selected_files)

    def _open_folder_by_path(self, folder: str):
        dlg = FolderOpenDialog(self.theme, folder, self)
        if dlg.exec() != FolderOpenDialog.Accepted:
            return
        self._import_files_from_list(dlg.selected_files)

    def _import_files_from_list(self, files: list):
        if not files:
            return

        try:
            settings = get_settings()
            settings.set_last_project_dir(str(Path(files[0]).parent))
        except Exception:
            pass

        existing_paths = {e.data.source_path for e in self.file_manager.get_all()}

        loaded = 0
        skipped = 0
        errors = []

        for path in files:
            if path in existing_paths:
                skipped += 1
                continue
            try:
                self._import_excel_silent(path)
                loaded += 1
            except Exception as e:
                errors.append((Path(path).name, f"{type(e).__name__}: {e}"))

        active = self.file_manager.get_active()
        if active:
            self.current_data = active.data
            self.history = active.history

        self._sort_state = []
        self.data_viewer.set_sort_state([])

        if self.current_data is not None:
            self._update_columns_tree(self.current_data)
            self._update_data_viewer(self.current_data)

        self._update_undo_buttons()
        self._refresh_files_list()

        parts = []
        if loaded:
            parts.append(f"загружено: {loaded}")
        if skipped:
            parts.append(f"уже открыто: {skipped}")
        if errors:
            parts.append(f"ошибок: {len(errors)}")
        text = ", ".join(parts) if parts else "ничего не загружено"

        if loaded:
            ToastManager.success("Импорт завершён", text, self.theme)
            self.statusBar().showMessage(f"📁 {text}")
        else:
            ToastManager.info("Импорт", text, self.theme)

        if errors:
            err_lines = [f"• {name}: {msg}" for name, msg in errors[:10]]
            if len(errors) > 10:
                err_lines.append(f"... и ещё {len(errors) - 10}")
            QMessageBox.warning(
                self, "Ошибки при импорте",
                "Не удалось загрузить:\n\n" + "\n".join(err_lines),
            )

    def _import_excel_silent(self, filepath: str):
        sheets = DataLoader.get_excel_sheets(filepath)
        sheet_name = sheets[0] if sheets else 0

        data = DataLoader.load(filepath, sheet_name)
        file_id = self.file_manager.add_file(data)

        data.file_id = file_id
        data.operations = self.file_manager.get_file(file_id).operations

    def _open_excel_by_path(self, filepath: str):
        try:
            for entry in self.file_manager.get_all():
                if entry.data.source_path == filepath:
                    self._switch_to_file(entry.id)
                    ToastManager.info("Файл уже открыт", f"«{entry.display_name}»", self.theme)
                    return

            lower = filepath.lower()
            if not lower.endswith((".xlsx", ".xls")):
                QMessageBox.warning(
                    self, "Неверный формат",
                    f"Файл не является Excel-файлом:\n{filepath}",
                )
                return

            sheets = DataLoader.get_excel_sheets(filepath)

            if len(sheets) > 1:
                sheet, ok = QInputDialog.getItem(
                    self, "Выбор листа",
                    f"Файл содержит {len(sheets)} листов.\nВыберите лист:",
                    sheets, 0, False
                )
                if not ok:
                    return
                sheet_name = sheet
            else:
                sheet_name = sheets[0] if sheets else 0

            data = DataLoader.load(filepath, sheet_name)
            file_id = self.file_manager.add_file(data)

            data.file_id = file_id
            data.operations = self.file_manager.get_file(file_id).operations

            entry = self.file_manager.get_active()
            self.current_data = entry.data
            self.history = entry.history

            self._sort_state = []
            self.data_viewer.set_sort_state([])

            if self._find_dialog is not None:
                self._find_dialog.set_status("")

            self._update_columns_tree(self.current_data)
            self._update_data_viewer(self.current_data)
            self._update_undo_buttons()
            self._refresh_files_list()

            self.statusBar().showMessage(
                f"✅ Загружено: {data.rows_count:,} строк, {data.cols_count} колонок"
            )
            ToastManager.success("Файл загружен", f"«{entry.display_name}»", self.theme)

        except Exception as e:
            import traceback
            traceback.print_exc()
            QMessageBox.critical(
                self, "Ошибка загрузки",
                f"Не удалось загрузить файл:\n\n{type(e).__name__}: {e}"
            )

    def _update_sheet_combo(self):
        if self.current_data is None:
            self.data_viewer.set_sheets([], "", is_pivot=False)
            return
        names = self.current_data.list_sheets()
        active = self.current_data.sheet_name or "Sheet1"
        is_pivot = active in self.current_data.pivot_specs
        self.data_viewer.set_sheets(names, active, is_pivot=is_pivot)

    def _update_data_viewer(self, data):
        if data is None:
            self.data_viewer.clear()
            self._displayed_indices = []
            self._update_data_panel()
            self._update_sheet_combo()
            return

        visible = data.visible_columns if data.visible_columns else list(data.columns)

        if data.column_filters:
            indices = data.get_filtered_indices()
            self._displayed_indices = indices
            df_base = data.dataframe.iloc[indices].reset_index(drop=True)
        else:
            n = len(data.dataframe)
            self._displayed_indices = list(range(n))
            df_base = data.dataframe

        df = df_base[visible]
        rename_map = {c: data.get_display_name(c) for c in visible}
        df = df.rename(columns=rename_map, copy=False)

        total = data.rows_count
        shown = len(df)
        if shown != total:
            info = f"{shown:,} из {total:,} строк  ·  {len(df.columns)} колонок"
        else:
            info = f"{total:,} строк  ·  {len(df.columns)} колонок"

        self.data_viewer.set_data(df, info, real_columns=visible)
        self.data_viewer.set_filtered_columns(set(data.column_filters.keys()))
        self.data_viewer.set_sort_state(self._sort_state)

        self._update_data_panel()

    def _update_data_panel(self):
        if not hasattr(self, 'data_panel') or self.data_panel is None:
            return

        if self.current_data is None:
            self.data_panel.update_state(
                sort_state=[], filters=[], total=0, shown=0,
            )
            return

        sort_display = []
        for col_name, asc in self._sort_state:
            display = self.current_data.get_display_name(col_name)
            sort_display.append((col_name, display, asc))

        filters_display = []
        for col_name, values in self.current_data.column_filters.items():
            display = self.current_data.get_display_name(col_name)
            filters_display.append((col_name, display, values))

        self.data_panel.update_state(
            sort_state=sort_display,
            filters=filters_display,
            total=self.current_data.rows_count,
            shown=len(self._displayed_indices),
        )

    # ============================================================
    # Изменения данных
    # ============================================================

    def _on_columns_changed(self):
        if self.current_data:
            self._update_columns_tree(self.current_data)
            self._update_data_viewer(self.current_data)
            active_id = self.file_manager.get_active_id()
            if active_id:
                self.file_manager.mark_modified(active_id)
                self._refresh_files_list()
            if self._is_code_tab_active():
                self._refresh_code()
            if self._selected_column and self.right_content.isVisible():
                col_info = self.current_data.get_column_info(self._selected_column)
                if col_info:
                    self.inspector.show_column(col_info)

    def _on_column_meta_changed(self, name: str):
        self._on_columns_changed()

    def _on_table_column_selected(self, col_name: str):
        self._selected_column = col_name
        if not (self.current_data and self.right_content.isVisible()):
            return
        if self.inspector.current_column_name() == col_name:
            return
        QTimer.singleShot(0, self._deferred_inspector_show)

    def _deferred_inspector_show(self):
        if not self._selected_column or not self.current_data:
            return
        col_info = self.current_data.get_column_info(self._selected_column)
        if col_info:
            self.inspector.show_column(col_info)

    def _on_table_cell_edit(self, row: int, col_name: str, new_value):
        if self.current_data is None:
            return
        if 0 <= row < len(self._displayed_indices):
            real_row = self._displayed_indices[row]
        else:
            real_row = row
        cmd = EditCellCommand(
            data=self.current_data,
            row=real_row,
            column=col_name,
            new_value=new_value,
            on_change=self._schedule_viewer_refresh,
        )
        self.history.execute(cmd)
        self._update_undo_buttons()
        active_id = self.file_manager.get_active_id()
        if active_id:
            self.file_manager.mark_modified(active_id)
            self._refresh_files_list()
        display = self.current_data.get_display_name(col_name)
        ToastManager.success(
            "Ячейка изменена", f"«{display}», строка {row + 1}", self.theme,
        )

    def _on_table_column_rename(self, col_name: str, new_display: str):
        if self.current_data is None:
            return
        cmd = RenameColumnCommand(
            data=self.current_data, column=col_name, new_name=new_display,
            on_change=self._on_columns_changed,
        )
        self.history.execute(cmd)
        self._update_undo_buttons()
        ToastManager.success("Колонка переименована", f"→ «{new_display}»", self.theme)

    def _on_delete_columns_requested(self, columns: list):
        if self.current_data is None or not columns:
            return
        if len(columns) == 1:
            display = self.current_data.get_display_name(columns[0])
            text = f"Удалить колонку «{display}»?\n\nДействие можно отменить (Ctrl+Z)."
        else:
            text = f"Удалить {len(columns)} колонок?\n\nДействие можно отменить (Ctrl+Z)."
        reply = QMessageBox.question(
            self, "Удаление колонок", text,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        cmd = DeleteColumnsCommand(
            data=self.current_data, columns=columns,
            on_change=self._on_columns_changed,
        )
        self.history.execute(cmd)
        if cmd.was_successful:
            ToastManager.success("Колонки удалены", cmd.message, self.theme)
            self.statusBar().showMessage(f"🗑 {cmd.message}")
        else:
            ToastManager.error("Ошибка удаления", cmd.message, self.theme)
        self._update_undo_buttons()

    def _on_delete_rows_requested(self, rows: list):
        if self.current_data is None or not rows:
            return
        if len(rows) == 1:
            text = f"Удалить строку {rows[0] + 1}?\n\nДействие можно отменить (Ctrl+Z)."
        else:
            text = f"Удалить {len(rows)} строк?\n\nДействие можно отменить (Ctrl+Z)."
        reply = QMessageBox.question(
            self, "Удаление строк", text,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        real_rows = []
        for r in rows:
            if 0 <= r < len(self._displayed_indices):
                real_rows.append(self._displayed_indices[r])
        if not real_rows:
            return
        cmd = DeleteRowsCommand(
            data=self.current_data, rows=real_rows,
            on_change=self._on_columns_changed,
        )
        self.history.execute(cmd)
        if cmd.was_successful:
            ToastManager.success("Строки удалены", cmd.message, self.theme)
            self.statusBar().showMessage(f"🗑 {cmd.message}")
        else:
            ToastManager.error("Ошибка удаления", cmd.message, self.theme)
        self._update_undo_buttons()

    def _schedule_viewer_refresh(self):
        QTimer.singleShot(0, self._deferred_viewer_refresh)

    def _deferred_viewer_refresh(self):
        if self.current_data is None:
            return
        self._update_data_viewer(self.current_data)
        if self._is_code_tab_active():
            self._refresh_code()

    # ============================================================
    # Фильтр
    # ============================================================

    def _on_filter_requested(self, col_name: str, global_pos):
        if self.current_data is None:
            return
        import pandas as pd
        series = self.current_data.dataframe[col_name]
        unique_raw = series.unique()
        na_mask = pd.isna(unique_raw)
        has_na = bool(na_mask.any())
        if has_na:
            unique_raw = unique_raw[~na_mask]
        unique_strs = sorted({str(v) for v in unique_raw})
        if has_na:
            unique_strs.append("—")
        current_filter = self.current_data.column_filters.get(col_name)
        popup = FilterPopup(self.theme, col_name, unique_strs, current_filter, self)
        popup.applied.connect(self._on_filter_applied)
        popup.move(global_pos)
        popup.show()

    def _on_filter_applied(self, col_name: str, allowed: list):
        if self.current_data is None:
            return
        if not allowed:
            self.current_data.clear_column_filter(col_name)
            msg = f"Фильтр снят: «{self.current_data.get_display_name(col_name)}»"
        else:
            self.current_data.set_column_filter(col_name, allowed)
            msg = (
                f"Фильтр: «{self.current_data.get_display_name(col_name)}» → "
                f"{len(allowed)} знач."
            )
        self._update_data_viewer(self.current_data)
        shown = len(self._displayed_indices)
        total = self.current_data.rows_count
        if shown != total:
            self.statusBar().showMessage(f"🔎 {msg}. Показано {shown:,} из {total:,}")
        else:
            self.statusBar().showMessage(f"🔎 {msg}")
        ToastManager.info("Фильтр применён", msg, self.theme)

    def _on_remove_filter(self, col_name: str):
        if self.current_data is None:
            return
        if col_name not in self.current_data.column_filters:
            return

        display = self.current_data.get_display_name(col_name)
        self.current_data.clear_column_filter(col_name)
        self._update_data_viewer(self.current_data)

        ToastManager.info("Фильтр снят", f"«{display}»", self.theme)
        self.statusBar().showMessage(f"🔎 Фильтр снят: «{display}»")

    def _clear_all_filters(self):
        if self.current_data is None:
            return
        if not self.current_data.has_any_filter():
            ToastManager.info("Нет фильтров", "Активных фильтров нет", self.theme)
            return
        self.current_data.clear_all_filters()
        self._update_data_viewer(self.current_data)
        self.statusBar().showMessage("🔎 Все фильтры сброшены")
        ToastManager.success("Фильтры сброшены", "Показаны все строки", self.theme)

    # ============================================================
    # Сортировка
    # ============================================================

    def _on_sort_requested(self, col_name: str, shift: bool):
        if self.current_data is None:
            return

        if not shift:
            if self._sort_state and self._sort_state[0][0] == col_name:
                prev_asc = self._sort_state[0][1]
                self._sort_state = [(col_name, not prev_asc)]
            else:
                self._sort_state = [(col_name, True)]
        else:
            found = False
            for i, (c, a) in enumerate(self._sort_state):
                if c == col_name:
                    self._sort_state[i] = (c, not a)
                    found = True
                    break
            if not found:
                self._sort_state.append((col_name, True))

        cmd = SortByColumnCommand(
            data=self.current_data,
            sort_spec=self._sort_state,
            on_change=self._on_sort_applied,
        )
        self.history.execute(cmd)

        if not cmd.was_successful:
            ToastManager.error("Ошибка сортировки", cmd.message, self.theme)
            self._sort_state = []
            self.data_viewer.set_sort_state([])
            self._update_data_panel()
            return

        self._update_undo_buttons()

    def _on_sort_applied(self):
        if self.current_data is None:
            return
        self._update_data_viewer(self.current_data)
        self.data_viewer.set_sort_state(self._sort_state)
        self._update_data_panel()

        if not self._sort_state:
            self.statusBar().showMessage("🔽 Сортировка сброшена")
            return

        if len(self._sort_state) == 1:
            col, asc = self._sort_state[0]
            arrow = "↑" if asc else "↓"
            display = self.current_data.get_display_name(col)
            self.statusBar().showMessage(f"🔽 Сортировка: «{display}» {arrow}")
            ToastManager.info("Сортировка", f"«{display}» {arrow}", self.theme)
        else:
            parts = []
            for col, asc in self._sort_state:
                arrow = "↑" if asc else "↓"
                parts.append(f"{self.current_data.get_display_name(col)} {arrow}")
            msg = ", ".join(parts)
            self.statusBar().showMessage(f"🔽 Сортировка: {msg}")
            ToastManager.info("Сортировка", msg, self.theme)

    def _clear_sort(self):
        if self.current_data is None:
            return
        if not self._sort_state:
            ToastManager.info("Нет сортировки", "Сортировка не активна", self.theme)
            return
        self._sort_state = []
        self.data_viewer.set_sort_state([])
        self._update_data_viewer(self.current_data)
        self.statusBar().showMessage("🔽 Сортировка сброшена")
        ToastManager.success("Сортировка сброшена", "", self.theme)

    # ============================================================
    # Сводная таблица
    # ============================================================

    def _on_pivot_open(self):
        """Открыть диалог сводной и добавить результат как новый лист."""
        if self.current_data is None:
            ToastManager.info("Нет данных", "Сначала загрузите файл", self.theme)
            return

        dlg = PivotDialog(self.theme, self.current_data.dataframe, parent=self)
        if dlg.exec() != PivotDialog.Accepted:
            return

        if dlg.preview_result is None or dlg.preview_result.empty:
            ToastManager.info("Пусто", "Сводная не содержит данных", self.theme)
            return

        result = dlg.preview_result.copy()

        new_cols = []
        for c in result.columns:
            if isinstance(c, tuple):
                parts = [str(x) for x in c if str(x)]
                new_cols.append("_".join(parts) if parts else "col")
            else:
                new_cols.append(str(c))

        seen: dict = {}
        unique_cols = []
        for c in new_cols:
            if c not in seen:
                seen[c] = 0
                unique_cols.append(c)
            else:
                seen[c] += 1
                unique_cols.append(f"{c}_{seen[c]}")
        result.columns = unique_cols

        try:
            if not isinstance(result.index, pd.RangeIndex):
                result = result.reset_index()
        except Exception:
            pass

        from datetime import datetime
        base = "Сводная"
        existing = self.current_data.list_sheets()
        stamp = datetime.now().strftime("%H:%M")
        name = f"{base} {stamp}"
        i = 2
        while name in existing:
            name = f"{base} {stamp}_{i}"
            i += 1

        source_sheet = self.current_data.sheet_name or "Sheet1"

        self.current_data.add_sheet(name, result)
        spec = dlg.result_spec or {}
        spec["source_sheet"] = source_sheet
        self.current_data.pivot_specs[name] = spec

        self.current_data.switch_sheet(name)

        self._sort_state = []
        self.data_viewer.set_sort_state([])
        self._update_columns_tree(self.current_data)
        self._update_data_viewer(self.current_data)
        self._update_undo_buttons()
        self._refresh_files_list()
        self._update_sheet_combo()

        ToastManager.success(
            "Сводная добавлена",
            f"Лист «{name}»  ·  {len(result):,} строк",
            self.theme,
        )

    def _on_pivot_edit(self):
        """Открыть существующую сводную в диалоге редактирования."""
        if self.current_data is None:
            return

        active = self.current_data.sheet_name or "Sheet1"
        spec = self.current_data.pivot_specs.get(active)
        if spec is None:
            ToastManager.info("Не сводная", "Текущий лист не является сводной", self.theme)
            return

        source_sheet = spec.get("source_sheet")
        source_df = None
        if source_sheet:
            if source_sheet == active:
                source_df = self.current_data.dataframe
            elif source_sheet in self.current_data.extra_sheets:
                source_df = self.current_data.extra_sheets[source_sheet]
            else:
                source_df = self.current_data.dataframe

        if source_df is None:
            source_df = self.current_data.dataframe

        dlg = PivotDialog(
            self.theme,
            source_df,
            initial_spec=spec,
            parent=self,
        )
        if dlg.exec() != PivotDialog.Accepted:
            return

        if dlg.preview_result is None or dlg.preview_result.empty:
            ToastManager.info("Пусто", "Сводная не содержит данных", self.theme)
            return

        result = dlg.preview_result.copy()

        new_cols = []
        for c in result.columns:
            if isinstance(c, tuple):
                parts = [str(x) for x in c if str(x)]
                new_cols.append("_".join(parts) if parts else "col")
            else:
                new_cols.append(str(c))

        seen: dict = {}
        unique_cols = []
        for c in new_cols:
            if c not in seen:
                seen[c] = 0
                unique_cols.append(c)
            else:
                seen[c] += 1
                unique_cols.append(f"{c}_{seen[c]}")
        result.columns = unique_cols

        try:
            if not isinstance(result.index, pd.RangeIndex):
                result = result.reset_index()
        except Exception:
            pass

        self.current_data.dataframe = result
        self.current_data.columns = list(result.columns)
        self.current_data.dtypes = {c: str(t) for c, t in result.dtypes.items()}
        self.current_data.rows_count = len(result)
        self.current_data.cols_count = len(result.columns)
        self.current_data.column_order = list(result.columns)
        self.current_data.visible_columns = list(result.columns)
        self.current_data.column_meta = {}
        self.current_data.column_filters = {}
        new_spec = dlg.result_spec or {}
        if source_sheet:
            new_spec["source_sheet"] = source_sheet
        self.current_data.pivot_specs[active] = new_spec
        self.current_data.invalidate_cache()

        if active in self.current_data.extra_sheets:
            self.current_data.extra_sheets[active] = result

        self._sort_state = []
        self.data_viewer.set_sort_state([])
        self._update_columns_tree(self.current_data)
        self._update_data_viewer(self.current_data)
        self._update_undo_buttons()
        self._refresh_files_list()
        self._update_sheet_combo()

        ToastManager.success(
            "Сводная обновлена",
            f"Лист «{active}»  ·  {len(result):,} строк",
            self.theme,
        )

    def _on_sheet_switch(self, name: str):
        if self.current_data is None:
            return
        if not self.current_data.switch_sheet(name):
            return

        self._sort_state = []
        self.data_viewer.set_sort_state([])
        self._update_columns_tree(self.current_data)
        self._update_data_viewer(self.current_data)
        self._update_undo_buttons()
        self._update_sheet_combo()

        self.statusBar().showMessage(
            f"📄 Лист «{name}»: {self.current_data.rows_count:,} строк, "
            f"{self.current_data.cols_count} колонок"
        )

    def _on_sheet_rename(self, old_name: str):
        if self.current_data is None:
            return

        new_name, ok = QInputDialog.getText(
            self,
            "Переименовать лист",
            f"Новое имя для листа «{old_name}»:",
            text=old_name,
        )
        if not ok:
            return

        new_name = new_name.strip()
        if not new_name or new_name == old_name:
            return

        ok_rename, msg = self.current_data.rename_sheet(old_name, new_name)
        if not ok_rename:
            QMessageBox.warning(self, "Не удалось переименовать", msg)
            return

        active_id = self.file_manager.get_active_id()
        if active_id:
            self.file_manager.mark_modified(active_id)

        self._update_sheet_combo()
        self._refresh_files_list()

        self.statusBar().showMessage(f"✏ {msg}")
        ToastManager.success("Лист переименован", msg, self.theme)

    # ============================================================
    # Дубликаты и пустые
    # ============================================================

    def _on_drop_duplicates(self):
        if self.current_data is None:
            ToastManager.info("Нет данных", "Сначала загрузите файл", self.theme)
            return

        columns = list(self.current_data.dataframe.columns)
        display_names = {c: self.current_data.get_display_name(c) for c in columns}

        dlg = DropDuplicatesDialog(self.theme, columns, display_names, self)
        if dlg.exec() != DropDuplicatesDialog.Accepted:
            return

        subset = [] if dlg.use_all else dlg.selected_columns

        cmd = DropDuplicatesCommand(
            data=self.current_data,
            subset=subset,
            on_change=self._on_columns_changed,
        )
        self.history.execute(cmd)

        if cmd.was_successful:
            ToastManager.success("Готово", cmd.message, self.theme)
            self.statusBar().showMessage(f"🗑 {cmd.message}")
        else:
            ToastManager.error("Ошибка", cmd.message, self.theme)

        self._update_undo_buttons()

    def _on_drop_na(self):
        if self.current_data is None:
            ToastManager.info("Нет данных", "Сначала загрузите файл", self.theme)
            return

        columns = list(self.current_data.dataframe.columns)
        display_names = {c: self.current_data.get_display_name(c) for c in columns}

        dlg = DropNaDialog(self.theme, columns, display_names, self)
        if dlg.exec() != DropNaDialog.Accepted:
            return

        subset = [] if dlg.use_all else dlg.selected_columns
        how = dlg.how

        cmd = DropNaCommand(
            data=self.current_data,
            subset=subset,
            how=how,
            on_change=self._on_columns_changed,
        )
        self.history.execute(cmd)

        if cmd.was_successful:
            ToastManager.success("Готово", cmd.message, self.theme)
            self.statusBar().showMessage(f"🗑 {cmd.message}")
        else:
            ToastManager.error("Ошибка", cmd.message, self.theme)

        self._update_undo_buttons()

    # ============================================================
    # Нормализация текста (гос-номера и др.)
    # ============================================================

    def _on_normalize_text(self):
        if self.current_data is None:
            ToastManager.info(
                "Нет данных",
                "Сначала загрузите Excel-файл",
                self.theme,
            )
            return

        columns = list(self.current_data.dataframe.columns)
        if not columns:
            ToastManager.info("Нет колонок", "В файле нет колонок", self.theme)
            return

        # Отображаемые имена (если пользователь переименовал)
        display_names = {
            c: self.current_data.get_display_name(c) for c in columns
        }

        dlg = NormalizeTextDialog(
            self.theme, columns, display_names, parent=self,
        )
        if dlg.exec() != NormalizeTextDialog.Accepted:
            return
        if not dlg.result_data:
            return

        rd = dlg.result_data

        cmd = NormalizeTextCommand(
            data=self.current_data,
            columns=rd["columns"],
            options={
                "direction": rd["direction"],
                "upper": rd["upper"],
                "remove_spaces": rd["remove_spaces"],
                "remove_chars": rd["remove_chars"],
            },
            on_change=self._on_columns_changed,
        )
        self.history.execute(cmd)

        if cmd.was_successful:
            ToastManager.success(
                "Нормализация завершена",
                cmd.message,
                self.theme,
            )
            self.statusBar().showMessage(f"🔤 {cmd.message}")

            # Если есть лог — показать его в отдельном окне
            if cmd.log:
                QMessageBox.information(
                    self,
                    "Нормализация текста — результат",
                    "\n".join(cmd.log),
                )
        else:
            ToastManager.error(
                "Не удалось обработать",
                cmd.message,
                self.theme,
            )

        self._update_undo_buttons()

    # ============================================================
    # Извлечение текста по шаблону (regex)
    # ============================================================

    def _on_extract_text(self):
        if self.current_data is None:
            ToastManager.info(
                "Нет данных",
                "Сначала загрузите Excel-файл",
                self.theme,
            )
            return

        columns = list(self.current_data.dataframe.columns)
        if not columns:
            ToastManager.info("Нет колонок", "В файле нет колонок", self.theme)
            return

        display_names = {
            c: self.current_data.get_display_name(c) for c in columns
        }

        dlg = ExtractTextDialog(
            self.current_data, self.theme, display_names, parent=self,
        )
        if dlg.exec() != ExtractTextDialog.Accepted:
            return
        if not dlg.result_data:
            return

        rd = dlg.result_data

        cmd = ExtractTextCommand(
            data=self.current_data,
            columns=rd["columns"],
            pattern=rd["pattern"],
            on_change=self._on_columns_changed,
        )
        self.history.execute(cmd)

        if cmd.was_successful:
            ToastManager.success(
                "Извлечение завершено",
                cmd.message,
                self.theme,
            )
            self.statusBar().showMessage(f"✂ {cmd.message}")

            if cmd.log:
                QMessageBox.information(
                    self,
                    "Извлечение по шаблону — результат",
                    "\n".join(cmd.log),
                )
        else:
            ToastManager.error(
                "Не удалось извлечь",
                cmd.message,
                self.theme,
            )

        self._update_undo_buttons()

    # ============================================================
    # Нормализация 1С
    # ============================================================

    def _on_normalize_1c(self):
        if self.current_data is None:
            ToastManager.info("Нет данных", "Сначала загрузите файл", self.theme)
            return
        reply = QMessageBox.question(
            self, "Обработать выгрузку 1С",
            "Привести файл к читабельному виду?\n\n"
            "Будут выполнены шаги:\n"
            "  • найти строку «Период» и обрезать шапку\n"
            "  • удалить пустые столбцы и «Текущее сальдо»\n"
            "  • заполнить пустые заголовки\n"
            "  • разбить многострочные ячейки (до 8 частей)\n"
            "  • оставить только строки с датой\n"
            "  • удалить бесполезные столбцы\n\n"
            "Действие можно отменить (Ctrl+Z).",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
        )
        if reply != QMessageBox.Yes:
            return
        cmd = Normalize1CCommand(data=self.current_data, on_change=self._on_columns_changed)
        self.history.execute(cmd)
        if cmd.was_successful:
            ToastManager.success("Файл обработан", cmd.message, self.theme)
            self.statusBar().showMessage(f"🧹 {cmd.message}")
            QMessageBox.information(
                self, "Нормализация 1С — журнал",
                "\n".join(cmd.log) if cmd.log else cmd.message,
            )
        else:
            ToastManager.error("Ошибка обработки", cmd.message, self.theme)
        self._update_undo_buttons()

    # ============================================================
    # Поиск
    # ============================================================

    def _on_find_open(self):
        if self.current_data is None:
            ToastManager.info("Нет данных", "Сначала загрузите файл", self.theme)
            return
        if self._find_dialog is None:
            self._find_dialog = FindDialog(self.theme, self)
            self._find_dialog.find_all.connect(self._on_find_all)
            self._find_dialog.match_selected.connect(self._on_find_match_selected)
            self._find_dialog.closed.connect(self._on_find_closed)
        self._find_dialog.show()
        self._find_dialog.raise_()
        self._find_dialog.activateWindow()
        self._find_dialog.focus_input()

    def _on_find_all(self, text: str, case_sensitive: bool, scope: str):
        if self.current_data is None:
            return
        matches = self.data_viewer.find_all(text, case_sensitive, scope)
        if self._find_dialog is not None:
            self._find_dialog.set_matches(matches)
            if matches:
                self._find_dialog.set_status(f"Найдено совпадений: {len(matches)}")
            else:
                self._find_dialog.set_status("Ничего не найдено")

    def _on_find_match_selected(self, row: int, col: int):
        self.data_viewer.go_to_cell(row, col)

    def _on_find_closed(self):
        self.data_viewer.clear_find()

    # ============================================================
    # Рельса
    # ============================================================

    def _on_rail_section_selected(self, key: str):
        index_map = {"inspector": 0, "data": 1, "links": 2, "style": 3}
        idx = index_map.get(key, 0)
        self.right_content.setCurrentIndex(idx)

        if key == "inspector" and self._selected_column and self.current_data:
            col_info = self.current_data.get_column_info(self._selected_column)
            if col_info:
                self.inspector.show_column(col_info)

        if key == "data":
            self._update_data_panel()

        self._show_content()

    def _show_content(self):
        if self._content_visible:
            return
        self._content_visible = True
        self.right_content.show()

    def _hide_content(self):
        if not self._content_visible:
            return
        self._content_visible = False
        self.right_content.hide()

    # ============================================================
    # Режим редактирования колонок
    # ============================================================

    def _toggle_edit_mode(self):
        self._edit_mode = not self._edit_mode
        self.tree_columns.set_edit_mode(self._edit_mode)
        self._update_columns_display()
        self._update_btn_edit_style()

    def _update_btn_edit_style(self):
        if self._edit_mode:
            self.btn_edit.setText("Готово")
            self.btn_edit.setStyleSheet(_pill_btn_qss(self.theme, active=True))
        else:
            self.btn_edit.setText("Изменить")
            self.btn_edit.setStyleSheet(_pill_btn_qss(self.theme, active=False))

    def _update_columns_display(self):
        if self.current_data is None:
            return
        self._update_columns_tree(self.current_data)

    # ============================================================
    # Дерево колонок
    # ============================================================

    def _update_columns_tree(self, data):
        self.tree_columns.blockSignals(True)

        if data is None:
            self.tree_columns.clear()
            self.tree_columns.blockSignals(False)
            self._refresh_left_empty_states()
            return

        try:
            columns_info = data.get_columns_basic()
        except AttributeError:
            columns_info = data.get_columns_info()

        info_by_name = {c["name"]: c for c in columns_info}
        column_map = {col_name: "📊" for col_name in data.column_order}
        self.tree_columns.set_column_map(column_map)

        existing = self.tree_columns.topLevelItemCount()
        want = len(data.column_order)

        if existing != want:
            self.tree_columns.clear()
            for col_name in data.column_order:
                info = info_by_name.get(col_name)
                if not info:
                    continue
                item = QTreeWidgetItem()
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setData(0, Qt.UserRole, col_name)
                self.tree_columns.addTopLevelItem(item)

        for i, col_name in enumerate(data.column_order):
            info = info_by_name.get(col_name)
            if not info:
                continue
            item = self.tree_columns.topLevelItem(i)
            if item is None:
                continue

            display_name = info["display_name"]
            if self._edit_mode:
                text = f"⋮⋮  {display_name}"
            else:
                text = display_name

            if item.text(0) != text:
                item.setText(0, text)

            desired_state = Qt.Checked if info["visible"] else Qt.Unchecked
            if item.checkState(0) != desired_state:
                item.setCheckState(0, desired_state)

            if item.data(0, Qt.UserRole) != col_name:
                item.setData(0, Qt.UserRole, col_name)

        self.tree_columns.blockSignals(False)
        self._refresh_left_empty_states()

    def _on_column_item_changed(self, item, column):
        if self._edit_mode:
            return
        col_name = item.data(0, Qt.UserRole)
        if col_name is None:
            return
        is_checked = item.checkState(0) == Qt.Checked
        QTimer.singleShot(
            0,
            lambda c=col_name, v=is_checked: self._do_toggle_column(c, v)
        )

    def _do_toggle_column(self, col_name: str, is_checked: bool):
        if self.current_data is None:
            return
        cmd = ToggleColumnCommand(
            data=self.current_data,
            column=col_name,
            visible=is_checked,
            on_change=self._on_columns_changed,
        )
        self.history.execute(cmd)
        self._update_undo_buttons()

    def _on_column_clicked(self, item, column):
        if item is None:
            return
        if self._edit_mode:
            return
        col_name = item.data(0, Qt.UserRole)
        if col_name is None:
            return
        self._selected_column = col_name
        if not (self.current_data and self.right_content.isVisible()):
            return
        if self.inspector.current_column_name() == col_name:
            return
        QTimer.singleShot(0, self._deferred_inspector_show)

    def _on_columns_reordered(self, new_order: list):
        if self.current_data is None:
            return
        cmd = ReorderColumnsCommand(
            data=self.current_data, new_order=new_order,
            on_change=self._on_columns_changed,
        )
        self.history.execute(cmd)
        self._update_undo_buttons()

    # ============================================================
    # Инспектор
    # ============================================================

    def _on_inspector_apply(self, name: str, display_name: str, visible: bool):
        if self.current_data is None:
            return
        changes = []
        prev_display = self.current_data.get_display_name(name)
        if display_name and display_name != prev_display:
            cmd = RenameColumnCommand(
                data=self.current_data, column=name, new_name=display_name,
                on_change=self._on_columns_changed,
            )
            self.history.execute(cmd)
            changes.append("имя")
        prev_visible = self.current_data.is_column_visible(name)
        if visible != prev_visible:
            cmd = ToggleColumnCommand(
                data=self.current_data, column=name, visible=visible,
                on_change=self._on_columns_changed,
            )
            self.history.execute(cmd)
            changes.append("видимость")
        self._update_undo_buttons()
        if changes:
            ToastManager.success(
                "Изменения применены",
                f"Колонка «{display_name}»: {', '.join(changes)}", self.theme,
            )
        else:
            ToastManager.info("Нечего применять", "Изменений не было", self.theme)

    def _on_column_cast(self, name: str, new_dtype: str):
        if self.current_data is None:
            return
        old_dtype = "unknown"
        display_name = name
        info = self.current_data.get_column_info(name)
        if info:
            old_dtype = info["dtype"]
            display_name = info["display_name"]
        cmd = CastColumnCommand(
            data=self.current_data, column=name, new_dtype=new_dtype,
            on_change=self._on_columns_changed,
        )
        self.history.execute(cmd)
        if cmd.was_successful:
            info = self.current_data.get_column_info(name)
            if info:
                display_name = info["display_name"]
                new_dtype_actual = info["dtype"]
                self.inspector.show_column(info)
            pretty_old = self._format_dtype(old_dtype)
            pretty_new = self._format_dtype(new_dtype_actual)
            msg = f"«{display_name}»\n{pretty_old} → {pretty_new}"
            self.statusBar().showMessage(f"✅ «{display_name}»: {pretty_old} → {pretty_new}")
            ToastManager.success("Тип данных изменён", msg, self.theme)
        else:
            ToastManager.error(
                "Ошибка преобразования",
                f"«{display_name}»\n{cmd.message}", self.theme,
            )
        self._update_undo_buttons()

    def _on_column_split(self, name: str):
        if self.current_data is None:
            return
        dialog = SplitDialog(self.current_data, name, self.theme, self)
        if dialog.exec() != SplitDialog.Accepted or not dialog.result_data:
            return
        rd = dialog.result_data
        mode = rd["mode"]
        if mode == "visual":
            rules = rd.get("rules", [])
            new_names = rd["new_names"]
            if not rules:
                ToastManager.error("Нет правил", "Правила не были определены", self.theme)
                return
            n_cols = len(rules) + 1
            if len(new_names) < n_cols:
                base = new_names[0] if new_names else name
                new_names = [f"{base}_{i+1}" for i in range(n_cols)]
            else:
                new_names = new_names[:n_cols]
            params = {"rules": rules}
        else:
            new_names = rd["new_names"]
            params = rd["params"]
        cmd = SplitColumnCommand(
            data=self.current_data, column=name, mode=mode, params=params,
            new_names=new_names, delete_original=rd["delete_original"],
            on_change=self._on_columns_changed,
        )
        self.history.execute(cmd)
        if cmd.was_successful:
            ToastManager.success("Колонка разделена", cmd.message, self.theme)
        else:
            ToastManager.error("Ошибка разделения", cmd.message, self.theme)
        self._update_undo_buttons()

    def _format_dtype(self, dtype: str) -> str:
        mapping = {
            "int64": "🔢 Целое (int64)",
            "float64": "🔢 Дробное (float64)",
            "str": "📝 Строка (str)",
            "object": "📝 Строка (str)",
            "datetime64[ns]": "📅 Дата (datetime)",
            "bool": "☑ Логический (bool)",
        }
        key = dtype.replace("'", "").replace('"', "").strip()
        return mapping.get(key, f"❔ {dtype}")

    # ============================================================
    # Кнопки видимости
    # ============================================================

    def _show_all_columns(self):
        if self.current_data is None:
            return
        self.tree_columns.blockSignals(True)
        self._set_all_checkboxes(Qt.Checked)
        self.tree_columns.blockSignals(False)
        self.current_data.show_all_columns()
        self._on_columns_changed()

    def _hide_all_columns(self):
        if self.current_data is None:
            return
        self.tree_columns.blockSignals(True)
        self._set_all_checkboxes(Qt.Unchecked)
        self.tree_columns.blockSignals(False)
        self.current_data.hide_all_columns()
        self._on_columns_changed()

    def _set_all_checkboxes(self, state):
        for i in range(self.tree_columns.topLevelItemCount()):
            item = self.tree_columns.topLevelItem(i)
            item.setCheckState(0, state)