"""
Современный файловый диалог.
Замена QFileDialog: слева быстрый доступ, сверху путь, снизу имя.
Универсальный — работает и для .eaproj, и для .xlsx, и для любых файлов.
"""

import os
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QListWidget, QListWidgetItem,
    QFileIconProvider, QFrame, QComboBox
)
from PySide6.QtCore import Qt, QSize, QFileInfo, QStandardPaths


class ProjectFileDialog(QDialog):
    """
    Режимы:
      mode = "save"   — сохранение (поле имени, кнопка «Сохранить»)
      mode = "open"   — открытие (двойной клик по файлу = выбрать)

    Параметры:
      title        — заголовок окна
      filters      — список (label, pattern). Например:
                     [("Excel файлы (*.xlsx *.xls)", "*.xlsx *.xls"),
                      ("Все файлы (*)", "*")]
      default_ext  — расширение, которое добавляется в save-режиме (".xlsx")
                     Если не указано — не добавляется.
    """

    def __init__(
        self,
        theme,
        mode: str = "open",
        title: str = "Открыть файл",
        filters: list | None = None,
        start_dir: str = "",
        default_name: str = "",
        default_ext: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.theme = theme
        self.mode = mode
        self.title_text = title
        self.filters = filters or [("Все файлы (*)", "*")]
        self.default_ext = default_ext
        self.current_dir = Path(start_dir) if start_dir else Path.home()
        self.selected_path: str | None = None
        self._icon_provider = QFileIconProvider()

        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumSize(760, 500)

        self._build_ui(default_name)
        self._apply_style()
        self._refresh_quick_access()
        self._load_dir(self.current_dir)

    # ============================================================
    # UI
    # ============================================================

    def _build_ui(self, default_name: str):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        # ── Заголовок ──
        title = QLabel(self.title_text)
        title.setObjectName("title")
        root.addWidget(title)

        # ── Основная область ──
        body = QHBoxLayout()
        body.setSpacing(12)

        # ЛЕВО
        left = QVBoxLayout()
        left.setSpacing(6)

        quick_lbl = QLabel("БЫСТРЫЙ ДОСТУП")
        quick_lbl.setObjectName("sectlabel")
        left.addWidget(quick_lbl)

        self.quick_list = QListWidget()
        self.quick_list.setFixedWidth(210)
        self.quick_list.itemClicked.connect(self._on_quick_clicked)
        left.addWidget(self.quick_list, stretch=1)

        body.addLayout(left)

        # ПРАВО
        right = QVBoxLayout()
        right.setSpacing(8)

        # Путь
        path_row = QHBoxLayout()
        path_row.setSpacing(6)

        self.btn_up = QPushButton("↑")
        self.btn_up.setObjectName("iconbtn")
        self.btn_up.setFixedSize(34, 34)
        self.btn_up.setToolTip("Вверх")
        self.btn_up.clicked.connect(self._go_up)
        path_row.addWidget(self.btn_up)

        self.btn_home = QPushButton("⌂")
        self.btn_home.setObjectName("iconbtn")
        self.btn_home.setFixedSize(34, 34)
        self.btn_home.setToolTip("Домашняя папка")
        self.btn_home.clicked.connect(lambda: self._load_dir(Path.home()))
        path_row.addWidget(self.btn_home)

        self.edit_path = QLineEdit()
        self.edit_path.setObjectName("pathfield")
        self.edit_path.returnPressed.connect(self._on_path_entered)
        path_row.addWidget(self.edit_path, stretch=1)

        right.addLayout(path_row)

        # Список файлов
        self.files_list = QListWidget()
        self.files_list.setIconSize(QSize(20, 20))
        self.files_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.files_list.itemSelectionChanged.connect(self._on_selection_changed)
        right.addWidget(self.files_list, stretch=1)

        # Фильтр
        bottom = QHBoxLayout()
        bottom.setSpacing(8)

        filter_lbl = QLabel("Фильтр:")
        filter_lbl.setObjectName("sub")
        bottom.addWidget(filter_lbl)

        self.combo_filter = QComboBox()
        for label, pattern in self.filters:
            self.combo_filter.addItem(label, pattern)
        self.combo_filter.currentIndexChanged.connect(self._reload_current_dir)
        bottom.addWidget(self.combo_filter)

        bottom.addStretch()
        right.addLayout(bottom)

        # Имя файла (для сохранения)
        if self.mode == "save":
            name_row = QHBoxLayout()
            name_row.setSpacing(8)

            name_lbl = QLabel("Имя файла:")
            name_lbl.setObjectName("sub")
            name_row.addWidget(name_lbl)

            self.edit_name = QLineEdit(default_name or "")
            self.edit_name.selectAll()
            name_row.addWidget(self.edit_name, stretch=1)

            right.addLayout(name_row)

        body.addLayout(right, stretch=1)
        root.addLayout(body, stretch=1)

        # Разделитель
        line = QFrame()
        line.setObjectName("divider")
        line.setFrameShape(QFrame.HLine)
        root.addWidget(line)

        # Кнопки
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()

        btn_cancel = QPushButton("Отмена")
        btn_cancel.setObjectName("secondary")
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_ok_text = "Сохранить" if self.mode == "save" else "Открыть"
        self.btn_ok = QPushButton(btn_ok_text)
        self.btn_ok.setObjectName("primary")
        self.btn_ok.setCursor(Qt.PointingHandCursor)
        self.btn_ok.clicked.connect(self._on_ok)
        btn_row.addWidget(self.btn_ok)

        root.addLayout(btn_row)

    def _apply_style(self):
        t = self.theme
        self.setStyleSheet(f"""
            QDialog {{ background: {t.bg_card}; }}
            QLabel#title {{
                color: {t.primary};
                font-size: 16px; font-weight: 700;
            }}
            QLabel#sectlabel {{
                color: {t.text_muted};
                font-size: 10px; font-weight: 700;
                letter-spacing: 0.5px; padding-left: 4px;
            }}
            QLabel#sub {{
                color: {t.text_muted}; font-size: 12px;
            }}
            QFrame#divider {{
                background: {t.border};
                max-height: 1px; border: none;
            }}
            QListWidget {{
                background: {t.bg_panel};
                color: {t.text_main};
                border: 1px solid {t.border};
                border-radius: 8px;
                padding: 4px;
                outline: none;
                font-size: 12px;
            }}
            QListWidget::item {{
                padding: 6px 8px; border-radius: 6px; min-height: 22px;
            }}
            QListWidget::item:selected {{
                background: {t.primary_hover};
                color: {t.primary_dark};
            }}
            QListWidget::item:hover {{ background: {t.bg_hover}; }}

            QLineEdit {{
                background: {t.bg_panel};
                color: {t.text_main};
                border: 1px solid {t.border};
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 12px;
                selection-background-color: {t.primary_hover};
                selection-color: {t.primary_dark};
            }}
            QLineEdit:focus {{ border: 1px solid {t.primary}; }}

            QComboBox {{
                background: {t.bg_panel};
                color: {t.text_main};
                border: 1px solid {t.border};
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 12px;
                min-width: 220px;
            }}
            QComboBox:hover {{ border: 1px solid {t.primary}; }}
            QComboBox::drop-down {{ border: none; width: 20px; }}
            QComboBox QAbstractItemView {{
                background: {t.bg_card};
                color: {t.text_main};
                border: 1px solid {t.border};
                selection-background-color: {t.primary_hover};
                selection-color: {t.primary_dark};
                padding: 4px;
            }}

            QPushButton#primary {{
                background: {t.primary};
                color: #ffffff;
                border: none;
                padding: 9px 22px;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 600;
                min-width: 110px;
            }}
            QPushButton#primary:hover {{ background: #6ea800; }}
            QPushButton#primary:pressed {{ background: #5c8f00; }}

            QPushButton#secondary {{
                background: transparent;
                color: {t.text_main};
                border: 1px solid {t.border};
                padding: 9px 22px;
                border-radius: 8px;
                font-size: 13px;
                min-width: 90px;
            }}
            QPushButton#secondary:hover {{
                background: {t.bg_panel};
                border: 1px solid {t.primary_hover};
            }}

            QPushButton#iconbtn {{
                background: {t.bg_panel};
                color: {t.text_main};
                border: 1px solid {t.border};
                border-radius: 8px;
                font-size: 16px;
                font-weight: bold;
                padding: 0;
            }}
            QPushButton#iconbtn:hover {{
                background: {t.primary_hover};
                border: 1px solid {t.primary_hover};
            }}

            QScrollBar:vertical {{
                background: {t.bg_panel};
                width: 10px; border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {t.border};
                min-height: 30px; border-radius: 5px; margin: 2px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {t.primary}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0; background: none; border: none;
            }}
            QScrollBar:horizontal {{
                background: {t.bg_panel};
                height: 10px; border: none;
            }}
            QScrollBar::handle:horizontal {{
                background: {t.border};
                min-width: 30px; border-radius: 5px; margin: 2px;
            }}
            QScrollBar::handle:horizontal:hover {{ background: {t.primary}; }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0; background: none; border: none;
            }}
        """)

    # ============================================================
    # Быстрый доступ
    # ============================================================

    def _refresh_quick_access(self):
        self.quick_list.clear()

        items = []

        def _std(kind, label):
            p = QStandardPaths.writableLocation(kind)
            if p and Path(p).exists():
                items.append((label, p))

        _std(QStandardPaths.DesktopLocation, "🖥  Рабочий стол")
        _std(QStandardPaths.DocumentsLocation, "📄  Документы")
        _std(QStandardPaths.DownloadLocation, "⬇  Загрузки")

        items.append(("🏠  Домой", str(Path.home())))

        proj_root = Path(__file__).resolve().parent.parent.parent
        if proj_root.exists():
            items.append(("📦  Проект", str(proj_root)))

        if self.current_dir and self.current_dir.exists():
            items.append(("🕘  Текущая", str(self.current_dir)))

        for label, path in items:
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, path)
            self.quick_list.addItem(item)

    def _on_quick_clicked(self, item: QListWidgetItem):
        path = item.data(Qt.UserRole)
        if path:
            self._load_dir(Path(path))

    # ============================================================
    # Навигация
    # ============================================================

    def _load_dir(self, dir_path: Path):
        if not dir_path.exists() or not dir_path.is_dir():
            return
        self.current_dir = dir_path
        self.edit_path.setText(str(dir_path))
        self._populate_files()

    def _reload_current_dir(self):
        self._populate_files()

    def _populate_files(self):
        self.files_list.clear()

        folders = []
        files = []
        try:
            for entry in sorted(os.scandir(self.current_dir), key=lambda e: e.name.lower()):
                if entry.is_dir():
                    folders.append(entry)
                else:
                    files.append(entry)
        except (PermissionError, OSError):
            return

        pattern_str = self.combo_filter.currentData() or "*"
        patterns = [p.strip().lower() for p in pattern_str.split() if p.strip()]
        only_all = "*" in patterns

        # Папки
        for entry in folders:
            item = QListWidgetItem(
                self._icon_provider.icon(QFileInfo(entry.path)),
                entry.name,
            )
            item.setData(Qt.UserRole, entry.path)
            item.setData(Qt.UserRole + 1, "folder")
            self.files_list.addItem(item)

        # Файлы
        for entry in files:
            if not only_all:
                name_lower = entry.name.lower()
                match = False
                for pat in patterns:
                    suffix = pat.replace("*", "")
                    if name_lower.endswith(suffix):
                        match = True
                        break
                if not match:
                    continue
            item = QListWidgetItem(
                self._icon_provider.icon(QFileInfo(entry.path)),
                entry.name,
            )
            item.setData(Qt.UserRole, entry.path)
            item.setData(Qt.UserRole + 1, "file")
            self.files_list.addItem(item)

    def _go_up(self):
        parent = self.current_dir.parent
        if parent != self.current_dir:
            self._load_dir(parent)

    def _on_path_entered(self):
        p = Path(self.edit_path.text())
        if p.exists() and p.is_dir():
            self._load_dir(p)

    # ============================================================
    # Работа с файлами
    # ============================================================

    def _on_selection_changed(self):
        items = self.files_list.selectedItems()
        if not items:
            return
        it = items[0]
        kind = it.data(Qt.UserRole + 1)
        path = it.data(Qt.UserRole)

        if self.mode == "save" and kind == "file":
            name = Path(path).name
            self.edit_name.setText(name)

    def _on_item_double_clicked(self, item: QListWidgetItem):
        kind = item.data(Qt.UserRole + 1)
        path = item.data(Qt.UserRole)

        if kind == "folder":
            self._load_dir(Path(path))
        else:
            if self.mode == "open":
                self.selected_path = path
                self.accept()
            else:
                self.edit_name.setText(Path(path).name)

    def _on_ok(self):
        if self.mode == "save":
            name = self.edit_name.text().strip()
            if not name:
                return

            # Добавляем расширение, если задано и имени его нет
            if self.default_ext and not name.lower().endswith(self.default_ext.lower()):
                name += self.default_ext

            full = Path(self.current_dir) / name
            self.selected_path = str(full)
            self.accept()
            return

        # open
        items = self.files_list.selectedItems()
        if items:
            it = items[0]
            kind = it.data(Qt.UserRole + 1)
            path = it.data(Qt.UserRole)
            if kind == "file":
                self.selected_path = path
                self.accept()
                return
            if kind == "folder":
                self._load_dir(Path(path))
                return