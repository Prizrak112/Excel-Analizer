"""
Дерево колонок с drag-n-drop и контекстным меню.
"""

from PySide6.QtWidgets import (
    QTreeWidget, QTreeWidgetItem, QAbstractItemView, QMenu
)
from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QShortcut, QKeySequence


class ColumnsTree(QTreeWidget):
    """Дерево колонок."""

    order_changed = Signal(list)
    delete_columns_requested = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setHeaderHidden(True)
        # ★ Множественное выделение (Ctrl / Shift / протяжка) — для массового
        #   удаления колонок.
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setIndentation(0)
        self.setRootIsDecorated(False)

        self._edit_mode = False
        self._column_map = {}

        self.setDragDropMode(QAbstractItemView.NoDragDrop)
        self.setDragEnabled(False)
        self.setAcceptDrops(False)
        self.setDropIndicatorShown(False)

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)

        # ★ Del — удалить выделенные колонки
        del_shortcut = QShortcut(QKeySequence.Delete, self)
        del_shortcut.activated.connect(self._on_delete_selected)

    def set_edit_mode(self, enabled: bool):
        self._edit_mode = enabled

        if enabled:
            self.setDragDropMode(QAbstractItemView.InternalMove)
            self.setDragEnabled(True)
            self.setAcceptDrops(True)
            self.setDropIndicatorShown(True)
            self.setDefaultDropAction(Qt.MoveAction)
            self.setCursor(Qt.OpenHandCursor)
        else:
            self.setDragDropMode(QAbstractItemView.NoDragDrop)
            self.setDragEnabled(False)
            self.setAcceptDrops(False)
            self.setDropIndicatorShown(False)
            self.setCursor(Qt.ArrowCursor)

    def is_edit_mode(self) -> bool:
        return self._edit_mode

    def set_column_map(self, mapping: dict):
        self._column_map = mapping or {}

    # ============================================================
    # Контекстное меню
    # ============================================================

    def _on_context_menu(self, pos: QPoint):
        if self._edit_mode:
            return

        item = self.itemAt(pos)
        if item is None:
            return

        # ★ Если ПКМ по элементу, который НЕ входит в текущее выделение —
        #   сбрасываем выделение и работаем только с ним. Если входит —
        #   работаем со всем выделением.
        selected = self.selectedItems()
        if item not in selected:
            self.clearSelection()
            item.setSelected(True)
            self.setCurrentItem(item)
            selected = [item]

        col_names = []
        for it in selected:
            cn = it.data(0, Qt.UserRole)
            if cn:
                col_names.append(cn)

        if not col_names:
            return

        menu = QMenu(self)
        if len(col_names) == 1:
            action_delete = menu.addAction("🗑  Удалить колонку")
        else:
            action_delete = menu.addAction(f"🗑  Удалить {len(col_names)} колонок")

        action = menu.exec(self.viewport().mapToGlobal(pos))

        if action == action_delete:
            self.delete_columns_requested.emit(col_names)

    # ============================================================
    # Удаление по Del
    # ============================================================

    def _on_delete_selected(self):
        """Del — удалить все выделенные колонки."""
        if self._edit_mode:
            return
        col_names = []
        for it in self.selectedItems():
            cn = it.data(0, Qt.UserRole)
            if cn:
                col_names.append(cn)
        if col_names:
            self.delete_columns_requested.emit(col_names)

    # ============================================================
    # Перехват drop
    # ============================================================

    def dropEvent(self, event):
        super().dropEvent(event)
        self._restore_all_data()
        new_order = self._collect_order()
        if new_order:
            self.order_changed.emit(new_order)

    def _restore_all_data(self):
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            if item.data(0, Qt.UserRole) is None:
                text = item.text(0)
                clean = text.replace("⋮⋮ ", "").strip()
                for col_name in self._column_map.keys():
                    if clean.endswith(col_name):
                        item.setData(0, Qt.UserRole, col_name)
                        break

    def _collect_order(self) -> list[str]:
        order = []
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            col_name = item.data(0, Qt.UserRole)
            if col_name:
                order.append(col_name)
        return order

    def get_columns_order(self) -> list[str]:
        return self._collect_order()

    def update_item_display(self, item: QTreeWidgetItem, col_name: str, edit_mode: bool):
        if edit_mode:
            item.setText(0, f"⋮⋮ {col_name}")
            item.setFlags(item.flags() & ~Qt.ItemIsUserCheckable)
        else:
            item.setText(0, col_name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)