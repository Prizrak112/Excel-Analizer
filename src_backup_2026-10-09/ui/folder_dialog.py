"""
Диалог импорта папки с Excel-файлами.
Показывает дерево файлов и подпапок с чекбоксами.
Файлы получают системную иконку (Excel для .xlsx).
"""

import os
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTreeWidget, QTreeWidgetItem, QFileDialog, QFrame,
    QFileIconProvider, QStyle
)
from PySide6.QtCore import Qt, QFileInfo
from PySide6.QtGui import QIcon


EXCEL_EXTS = (".xlsx", ".xls")


class FolderOpenDialog(QDialog):
    """Диалог выбора папки с Excel-файлами."""

    def __init__(self, theme, start_dir: str = "", parent=None):
        super().__init__(parent)
        self.theme = theme
        self.start_dir = start_dir or str(Path.home())
        self.selected_files: list[str] = []

        # Провайдер системных иконок
        self._icon_provider = QFileIconProvider()
        self._folder_icon = self.style().standardIcon(QStyle.SP_DirIcon)
        self._file_icon = self.style().standardIcon(QStyle.SP_FileIcon)

        self.setWindowTitle("Открыть папку с Excel-файлами")
        self.setModal(True)
        self.setMinimumSize(760, 620)

        self._build_ui()
        self._apply_style()
        self._scan_folder(self.start_dir)

    # ============================================================
    # Иконки
    # ============================================================

    def _get_file_icon(self, path: str) -> QIcon:
        """Системная иконка файла (для .xlsx будет иконка Excel)."""
        try:
            icon = self._icon_provider.icon(QFileInfo(path))
            if not icon.isNull():
                return icon
        except Exception:
            pass
        return self._file_icon

    def _get_folder_icon(self, path: str) -> QIcon:
        """Системная иконка папки."""
        try:
            icon = self._icon_provider.icon(QFileInfo(path))
            if not icon.isNull():
                return icon
        except Exception:
            pass
        return self._folder_icon

    # ============================================================
    # UI
    # ============================================================

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)

        title = QLabel("Импорт папки с Excel-файлами")
        title.setObjectName("title")
        layout.addWidget(title)

        subtitle = QLabel(
            "Выберите папку — все Excel-файлы внутри будут найдены автоматически.\n"
            "Отметьте файлы или целые папки для импорта."
        )
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        line = QFrame()
        line.setObjectName("divider")
        line.setFrameShape(QFrame.HLine)
        layout.addWidget(line)

        # ── Путь ──
        path_row = QHBoxLayout()
        path_row.setSpacing(8)

        lbl = QLabel("Папка:")
        lbl.setStyleSheet(f"color: {self.theme.text_main}; font-size: 13px;")
        path_row.addWidget(lbl)

        self.edit_path = QLineEdit(self.start_dir)
        self.edit_path.setReadOnly(True)
        self.edit_path.setStyleSheet(f"""
            QLineEdit {{
                background: {self.theme.bg_panel};
                color: {self.theme.text_main};
                border: 1px solid {self.theme.border};
                border-radius: 8px;
                padding: 9px 12px;
                font-size: 12px;
            }}
        """)
        path_row.addWidget(self.edit_path, stretch=1)

        btn_browse = QPushButton("Обзор…")
        btn_browse.setCursor(Qt.PointingHandCursor)
        btn_browse.setStyleSheet(self._btn_secondary_style())
        btn_browse.clicked.connect(self._on_browse)
        path_row.addWidget(btn_browse)

        layout.addLayout(path_row)

        # ── Дерево файлов ──
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(20)
        self.tree.setIconSize(QFileInfo("x").size() if False else self.tree.iconSize())
        self.tree.setIconSize(self._folder_icon.actualSize(self.tree.iconSize()) or self.tree.iconSize())
        self.tree.setStyleSheet(f"""
            QTreeWidget {{
                background: {self.theme.bg_panel};
                border: 1px solid {self.theme.border};
                border-radius: 10px;
                outline: none;
                padding: 6px;
                font-size: 13px;
                color: {self.theme.text_main};
            }}
            QTreeWidget::item {{
                padding: 6px 8px;
                border-radius: 6px;
                min-height: 24px;
                color: {self.theme.text_main};
            }}
            QTreeWidget::item:selected {{
                background: {self.theme.primary_hover};
                color: {self.theme.text_main};
            }}
            QTreeWidget::item:hover {{
                background: {self.theme.bg_hover};
            }}
            QTreeWidget::indicator {{
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 1px solid {self.theme.border};
                background: {self.theme.bg_card};
            }}
            QTreeWidget::indicator:hover {{
                border: 1px solid {self.theme.primary};
            }}
            QTreeWidget::indicator:checked {{
                background: {self.theme.primary};
                border: 1px solid {self.theme.primary};
            }}
        """)
        self.tree.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.tree, stretch=1)

        # ── Низ: счётчик и пилюли ──
        bottom = QHBoxLayout()
        bottom.setSpacing(8)

        self.label_count = QLabel("Выбрано: 0 из 0")
        self.label_count.setStyleSheet(f"""
            color: {self.theme.primary};
            font-size: 12px;
            font-weight: 600;
        """)
        bottom.addWidget(self.label_count)
        bottom.addStretch()

        btn_all = QPushButton("Выделить все")
        btn_all.setObjectName("pill")
        btn_all.setCursor(Qt.PointingHandCursor)
        btn_all.clicked.connect(lambda: self._set_all(True))
        bottom.addWidget(btn_all)

        btn_none = QPushButton("Снять все")
        btn_none.setObjectName("pill")
        btn_none.setCursor(Qt.PointingHandCursor)
        btn_none.clicked.connect(lambda: self._set_all(False))
        bottom.addWidget(btn_none)

        layout.addLayout(bottom)

        # ── Действия ──
        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.addStretch()

        btn_cancel = QPushButton("Отмена")
        btn_cancel.setObjectName("secondary")
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)
        actions.addWidget(btn_cancel)

        self.btn_import = QPushButton("Импортировать")
        self.btn_import.setObjectName("primary")
        self.btn_import.setCursor(Qt.PointingHandCursor)
        self.btn_import.setEnabled(False)
        self.btn_import.clicked.connect(self._on_import)
        actions.addWidget(self.btn_import)

        layout.addLayout(actions)

    def _btn_secondary_style(self) -> str:
        return f"""
            QPushButton {{
                background: {self.theme.bg_panel};
                color: {self.theme.text_main};
                border: 1px solid {self.theme.border};
                border-radius: 8px;
                padding: 9px 18px;
                font-size: 12px;
                font-weight: 500;
            }}
            QPushButton:hover {{ background: {self.theme.bg_hover}; }}
        """

    def _apply_style(self):
        self.setStyleSheet(f"""
            QDialog {{ background: {self.theme.bg_card}; }}
            QLabel#title {{
                color: {self.theme.text_main};
                font-size: 18px;
                font-weight: 700;
            }}
            QLabel#subtitle {{
                color: {self.theme.text_muted};
                font-size: 12px;
            }}
            QFrame#divider {{
                background: {self.theme.border};
                max-height: 1px;
                border: none;
            }}
            QPushButton#primary {{
                background: {self.theme.primary};
                color: {self.theme.text_inverse};
                border: none;
                padding: 10px 22px;
                border-radius: 9px;
                font-size: 13px;
                font-weight: 600;
                min-width: 130px;
            }}
            QPushButton#primary:hover {{ background: #9ade4f; }}
            QPushButton#primary:disabled {{
                background: {self.theme.bg_panel};
                color: {self.theme.text_muted};
            }}
            QPushButton#secondary {{
                background: transparent;
                color: {self.theme.text_main};
                border: 1px solid {self.theme.border};
                padding: 10px 22px;
                border-radius: 9px;
                font-size: 13px;
                min-width: 100px;
            }}
            QPushButton#secondary:hover {{
                background: {self.theme.bg_panel};
            }}
            QPushButton#pill {{
                background: {self.theme.bg_panel};
                color: {self.theme.text_main};
                border: 1px solid {self.theme.border};
                padding: 5px 14px;
                border-radius: 12px;
                font-size: 11px;
                font-weight: 600;
            }}
            QPushButton#pill:hover {{
                background: {self.theme.bg_hover};
            }}
        """)

    # ============================================================
    # Сканирование
    # ============================================================

    def _on_browse(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Выберите папку", self.start_dir,
        )
        if folder:
            self._scan_folder(folder)

    def _scan_folder(self, folder: str):
        self.tree.blockSignals(True)
        self.tree.clear()
        self.start_dir = folder
        self.edit_path.setText(folder)

        root_name = Path(folder).name or folder
        root_item = QTreeWidgetItem([root_name])
        root_item.setIcon(0, self._get_folder_icon(folder))
        root_item.setData(0, Qt.UserRole, folder)
        root_item.setData(0, Qt.UserRole + 1, "folder")
        root_item.setFlags(root_item.flags() | Qt.ItemIsUserCheckable)
        root_item.setCheckState(0, Qt.Checked)
        self.tree.addTopLevelItem(root_item)

        self._populate_tree(root_item, folder)
        root_item.setExpanded(True)

        self.tree.blockSignals(False)
        self._update_count()

    def _populate_tree(self, parent_item: QTreeWidgetItem, folder: str):
        try:
            entries = sorted(
                os.scandir(folder),
                key=lambda e: (not e.is_dir(), e.name.lower()),
            )
        except (PermissionError, OSError):
            return

        for entry in entries:
            if entry.is_dir():
                if not self._has_excel_files(entry.path):
                    continue
                sub_item = QTreeWidgetItem([entry.name])
                sub_item.setIcon(0, self._get_folder_icon(entry.path))
                sub_item.setData(0, Qt.UserRole, entry.path)
                sub_item.setData(0, Qt.UserRole + 1, "folder")
                sub_item.setFlags(sub_item.flags() | Qt.ItemIsUserCheckable)
                sub_item.setCheckState(0, Qt.Checked)
                parent_item.addChild(sub_item)
                self._populate_tree(sub_item, entry.path)

            elif entry.is_file():
                if not entry.name.lower().endswith(EXCEL_EXTS):
                    continue
                file_item = QTreeWidgetItem([entry.name])
                file_item.setIcon(0, self._get_file_icon(entry.path))
                file_item.setData(0, Qt.UserRole, entry.path)
                file_item.setData(0, Qt.UserRole + 1, "file")
                file_item.setFlags(file_item.flags() | Qt.ItemIsUserCheckable)
                file_item.setCheckState(0, Qt.Checked)
                parent_item.addChild(file_item)

    def _has_excel_files(self, folder: str) -> bool:
        try:
            for entry in os.scandir(folder):
                if entry.is_file() and entry.name.lower().endswith(EXCEL_EXTS):
                    return True
                if entry.is_dir() and self._has_excel_files(entry.path):
                    return True
        except (PermissionError, OSError):
            pass
        return False

    # ============================================================
    # Логика чекбоксов
    # ============================================================

    def _on_item_changed(self, item, column):
        self.tree.blockSignals(True)
        state = item.checkState(0)
        self._set_children_state(item, state)
        self._update_parent_state(item)
        self.tree.blockSignals(False)
        self._update_count()

    def _set_children_state(self, item, state):
        for i in range(item.childCount()):
            child = item.child(i)
            child.setCheckState(0, state)
            self._set_children_state(child, state)

    def _update_parent_state(self, item):
        parent = item.parent()
        if parent is None:
            return
        states = [parent.child(i).checkState(0) for i in range(parent.childCount())]
        if all(s == Qt.Checked for s in states):
            parent.setCheckState(0, Qt.Checked)
        elif all(s == Qt.Unchecked for s in states):
            parent.setCheckState(0, Qt.Unchecked)
        else:
            parent.setCheckState(0, Qt.PartiallyChecked)

    def _set_all(self, state: bool):
        self.tree.blockSignals(True)
        new_state = Qt.Checked if state else Qt.Unchecked
        for i in range(self.tree.topLevelItemCount()):
            root = self.tree.topLevelItem(i)
            root.setCheckState(0, new_state)
            self._set_children_state(root, new_state)
        self.tree.blockSignals(False)
        self._update_count()

    def _collect_checked_files(self) -> list[str]:
        files = []
        for i in range(self.tree.topLevelItemCount()):
            self._collect_from_item(self.tree.topLevelItem(i), files)
        return files

    def _collect_from_item(self, item: QTreeWidgetItem, files: list):
        kind = item.data(0, Qt.UserRole + 1)
        path = item.data(0, Qt.UserRole)
        state = item.checkState(0)

        if kind == "file" and state == Qt.Checked:
            files.append(path)

        for i in range(item.childCount()):
            self._collect_from_item(item.child(i), files)

    def _update_count(self):
        selected = len(self._collect_checked_files())
        total = self._count_all_files()
        self.label_count.setText(f"Выбрано: {selected} из {total}")
        self.btn_import.setEnabled(selected > 0)

    def _count_all_files(self) -> int:
        return sum(
            self._count_from_item(self.tree.topLevelItem(i))
            for i in range(self.tree.topLevelItemCount())
        )

    def _count_from_item(self, item) -> int:
        n = 1 if item.data(0, Qt.UserRole + 1) == "file" else 0
        return n + sum(
            self._count_from_item(item.child(i))
            for i in range(item.childCount())
        )

    # ============================================================
    # Импорт
    # ============================================================

    def _on_import(self):
        self.selected_files = self._collect_checked_files()
        if not self.selected_files:
            return
        self.accept()