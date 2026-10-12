"""
Диалог сводной таблицы — как в Excel.
4 зоны: Фильтры / Колонки / Строки / Значения + drag-n-drop.
Фильтры: диалог выбора значений по колонке.
"""

import pandas as pd

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QFrame, QTableWidget,
    QTableWidgetItem, QHeaderView, QCheckBox, QAbstractItemView,
    QMenu, QGridLayout, QWidget, QSizePolicy, QMessageBox,
    QScrollArea, QLineEdit
)
from PySide6.QtCore import Qt, Signal, QTimer, QMimeData, QPoint
from PySide6.QtGui import QDrag, QColor, QBrush


AGGREGATIONS = [
    ("sum",     "Сумма",          "Σ"),
    ("mean",    "Среднее",        "⌀"),
    ("count",   "Количество",     "#"),
    ("nunique", "Уник. значения", "№"),
    ("min",     "Минимум",        "↓"),
    ("max",     "Максимум",       "↑"),
    ("median",  "Медиана",        "M"),
    ("std",     "Ст. отклонение", "σ"),
]

AGG_MAP = {k: (label, sym) for k, label, sym in AGGREGATIONS}


def col_name_text(item: QListWidgetItem) -> str:
    return item.data(Qt.UserRole) or ""


# ============================================================
# Диалог выбора значений фильтра
# ============================================================

class FilterValuesDialog(QDialog):
    """Диалог выбора значений для фильтра колонки."""

    def __init__(self, theme, column: str, unique_values: list,
                 current: list | None = None, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.column = column
        self.unique_values = [str(v) for v in unique_values]
        self.current = set(str(v) for v in current) if current else None

        self.result_values: list[str] | None = None

        self.setWindowTitle(f"Фильтр: {column}")
        self.setModal(True)
        self.setMinimumSize(420, 560)

        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        t = self.theme
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        title = QLabel(f"Фильтр: {self.column}")
        title.setObjectName("title")
        layout.addWidget(title)

        hint = QLabel(
            "Выберите значения, которые должны остаться в сводной.\n"
            "Если ничего не выбрано — фильтр снимается."
        )
        hint.setObjectName("subtitle")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f"background: {t.border}; max-height: 1px; border: none;")
        layout.addWidget(line)

        # ── Поиск ──
        self.edit_search = QLineEdit()
        self.edit_search.setPlaceholderText("Поиск значений…")
        self.edit_search.setStyleSheet(f"""
            QLineEdit {{
                background: {t.bg_panel};
                color: {t.text_main};
                border: 1px solid {t.border};
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 12px;
            }}
            QLineEdit:focus {{ border: 1px solid {t.primary}; }}
        """)
        self.edit_search.textChanged.connect(self._on_search)
        layout.addWidget(self.edit_search)

        # ── Список ──
        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(f"""
            QListWidget {{
                background: {t.bg_panel};
                border: 1px solid {t.border};
                border-radius: 8px;
                padding: 4px;
                font-size: 12px;
                color: {t.text_main};
                outline: none;
            }}
            QListWidget::item {{
                padding: 5px 8px;
                border-radius: 5px;
                color: {t.text_main};
            }}
            QListWidget::item:hover {{ background: {t.bg_hover}; }}
        """)

        if len(self.unique_values) > 5000:
            item = QListWidgetItem(f"Слишком много значений ({len(self.unique_values)}).")
            item.setFlags(Qt.NoItemFlags)
            self.list_widget.addItem(item)
        else:
            for v in self.unique_values:
                item = QListWidgetItem(v)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                checked = (self.current is None) or (v in self.current)
                item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
                item.setForeground(QBrush(QColor(t.text_main)))
                self.list_widget.addItem(item)
        layout.addWidget(self.list_widget, stretch=1)

        # ── Пилюли ──
        row = QHBoxLayout()
        row.setSpacing(8)

        btn_all = QPushButton("Выделить все")
        btn_all.clicked.connect(lambda: self._set_all(True))
        btn_none = QPushButton("Снять все")
        btn_none.clicked.connect(lambda: self._set_all(False))

        for b in (btn_all, btn_none):
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(f"""
                QPushButton {{
                    background: {t.bg_panel};
                    color: {t.text_main};
                    border: 1px solid {t.border};
                    padding: 6px 14px;
                    border-radius: 12px;
                    font-size: 11px;
                    font-weight: 600;
                }}
                QPushButton:hover {{ background: {t.bg_hover}; }}
            """)
        row.addWidget(btn_all)
        row.addWidget(btn_none)
        row.addStretch()
        layout.addLayout(row)

        # ── Кнопки OK/Cancel ──
        btns = QHBoxLayout()
        btns.setSpacing(10)
        btns.addStretch()

        btn_cancel = QPushButton("Отмена")
        btn_cancel.clicked.connect(self.reject)
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {t.text_main};
                border: 1px solid {t.border};
                padding: 9px 20px;
                border-radius: 8px;
                font-size: 12px;
                min-width: 90px;
            }}
            QPushButton:hover {{ background: {t.bg_panel}; }}
        """)
        btns.addWidget(btn_cancel)

        btn_ok = QPushButton("Применить")
        btn_ok.clicked.connect(self._on_ok)
        btn_ok.setCursor(Qt.PointingHandCursor)
        btn_ok.setStyleSheet(f"""
            QPushButton {{
                background: {t.primary};
                color: {t.text_inverse};
                border: none;
                padding: 9px 20px;
                border-radius: 8px;
                font-size: 12px;
                font-weight: 600;
                min-width: 120px;
            }}
            QPushButton:hover {{ background: #9ade4f; }}
        """)
        btns.addWidget(btn_ok)
        layout.addLayout(btns)

    def _apply_style(self):
        t = self.theme
        self.setStyleSheet(f"""
            QDialog {{ background: {t.bg_card}; }}
            QLabel {{ color: {t.text_main}; font-size: 13px; }}
            QLabel#title {{ font-size: 17px; font-weight: 700; }}
            QLabel#subtitle {{ color: {t.text_muted}; font-size: 12px; }}
        """)

    def _on_search(self, text: str):
        needle = text.lower()
        for i in range(self.list_widget.count()):
            it = self.list_widget.item(i)
            it.setHidden(needle not in it.text().lower() if needle else False)

    def _set_all(self, state: bool):
        for i in range(self.list_widget.count()):
            it = self.list_widget.item(i)
            if not it.isHidden():
                it.setCheckState(Qt.Checked if state else Qt.Unchecked)

    def _on_ok(self):
        checked = []
        for i in range(self.list_widget.count()):
            it = self.list_widget.item(i)
            if it.checkState() == Qt.Checked:
                checked.append(it.text())

        if len(checked) == len(self.unique_values):
            # Все выбраны — фильтр не нужен
            self.result_values = None
        else:
            self.result_values = checked
        self.accept()


# ============================================================
# Списки с drag-n-drop
# ============================================================

class PivotList(QListWidget):
    """Список в одной из зон сводной."""

    changed = Signal()

    def __init__(self, zone: str, theme, parent=None):
        super().__init__(parent)
        self.zone = zone
        self.theme = theme

        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setAlternatingRowColors(False)

        t = theme
        self.setStyleSheet(f"""
            QListWidget {{
                background: {t.bg_panel};
                border: 1px solid {t.border};
                border-radius: 8px;
                padding: 4px;
                outline: none;
                font-size: 12px;
                color: {t.text_main};
            }}
            QListWidget::item {{
                padding: 5px 8px;
                border-radius: 5px;
                color: {t.text_main};
                background: transparent;
                min-height: 22px;
            }}
            QListWidget::item:selected {{
                background: {t.primary_hover};
                color: {t.text_main};
            }}
            QListWidget::item:hover {{
                background: {t.bg_hover};
            }}
        """)

        self.itemDoubleClicked.connect(self._on_double_click)

    # ------------------------------------------------------------
    # Drag
    # ------------------------------------------------------------

    def startDrag(self, supported_actions):
        item = self.currentItem()
        if item is None:
            return

        mime = QMimeData()
        mime.setText(item.data(Qt.UserRole))
        mime.setData("application/x-pivot-source", self.zone.encode())

        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.MoveAction)

    # ------------------------------------------------------------
    # Drop
    # ------------------------------------------------------------

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-pivot-source"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat("application/x-pivot-source"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if not event.mimeData().hasFormat("application/x-pivot-source"):
            event.ignore()
            return

        source_zone = event.mimeData().data("application/x-pivot-source").data().decode()
        col_name = event.mimeData().text()

        if self.zone == "available":
            self._add_plain_item(col_name)
            if source_zone != "available":
                self._remove_from_sibling(source_zone, col_name)
            self.changed.emit()
            event.acceptProposedAction()
            return

        # ★ Фильтры — особый случай: показать диалог
        if self.zone == "filters":
            self._add_filter_item(col_name, source_zone)
            event.acceptProposedAction()
            return

        if self.zone == "values":
            if self._find_item(col_name) is not None:
                event.ignore()
                return
            self._add_value_item(col_name, "sum")
        else:
            if self._find_item(col_name) is not None:
                event.ignore()
                return
            self._add_plain_item(col_name)

        if source_zone != "available":
            self._remove_from_sibling(source_zone, col_name)

        self.changed.emit()
        event.acceptProposedAction()

    # ------------------------------------------------------------
    # Добавление
    # ------------------------------------------------------------

    def _add_plain_item(self, col_name: str):
        item = QListWidgetItem(col_name)
        item.setForeground(QBrush(QColor(self.theme.text_main)))
        item.setData(Qt.UserRole, col_name)
        item.setData(Qt.UserRole + 1, self.zone)
        self.addItem(item)

    def _add_filter_item(self, col_name: str, source_zone: str):
        """Добавить колонку в фильтры — с диалогом выбора значений."""
        if self._find_item(col_name) is not None:
            return

        # Получить уникальные значения из исходного df
        dlg_window = self.window()
        df = getattr(dlg_window, "df", None)
        if df is None or col_name not in df.columns:
            return

        try:
            import pandas as pd
            unique = sorted({str(v) for v in df[col_name].dropna().unique()})
        except Exception:
            return

        # Открыть диалог выбора значений
        sel_dialog = FilterValuesDialog(
            self.theme, col_name, unique,
            current=None,
            parent=self.window(),
        )
        if sel_dialog.exec() != QDialog.Accepted:
            return

        values = sel_dialog.result_values

        item = QListWidgetItem()
        item.setForeground(QBrush(QColor(self.theme.text_main)))
        item.setData(Qt.UserRole, col_name)
        item.setData(Qt.UserRole + 1, "filters")
        item.setData(Qt.UserRole + 3, values)
        self._update_filter_label(item)
        self.addItem(item)

        if source_zone != "available":
            self._remove_from_sibling(source_zone, col_name)

        self.changed.emit()

    def _update_filter_label(self, item):
        """Обновить текст элемента-фильтра."""
        col_name = item.data(Qt.UserRole) or ""
        values = item.data(Qt.UserRole + 3)
        if values is None:
            item.setText(f"{col_name}  ·  все")
            item.setToolTip(f"{col_name}: фильтр не задан")
        else:
            item.setText(f"{col_name}  ·  {len(values)}")
            preview = values[:20]
            item.setToolTip(
                f"{col_name}: {len(values)} значений\n"
                f"{preview}{'…' if len(values) > 20 else ''}"
            )

    def _add_value_item(self, col_name: str, agg: str):
        label, sym = AGG_MAP.get(agg, ("Сумма", "Σ"))
        item = QListWidgetItem(f"{col_name}    {sym}")
        item.setForeground(QBrush(QColor(self.theme.text_main)))
        item.setData(Qt.UserRole, col_name)
        item.setData(Qt.UserRole + 1, "values")
        item.setData(Qt.UserRole + 2, agg)
        item.setToolTip(f"{col_name}: {label}")
        self.addItem(item)

    # ------------------------------------------------------------
    # Утилиты
    # ------------------------------------------------------------

    def _find_item(self, col_name: str):
        for i in range(self.count()):
            it = self.item(i)
            if it.data(Qt.UserRole) == col_name:
                return it
        return None

    def _remove_by_name(self, col_name: str, from_drop: bool = False):
        it = self._find_item(col_name)
        if it is not None:
            self.takeItem(self.row(it))
            if not from_drop:
                self.changed.emit()

    def _remove_from_sibling(self, zone: str, col_name: str):
        try:
            src = self._find_sibling(zone)
            if src is not None:
                src._remove_by_name(col_name, from_drop=True)
        except Exception:
            pass

    def _find_sibling(self, zone: str):
        dlg = self.window()
        for attr in ("list_filters", "list_rows", "list_cols", "list_values",
                     "list_available"):
            lst = getattr(dlg, attr, None)
            if lst is not None and getattr(lst, "zone", None) == zone:
                return lst
        return None

    # ------------------------------------------------------------
    # Двойной клик
    # ------------------------------------------------------------

    def _on_double_click(self, item):
        if self.zone == "values":
            self._ask_aggregation(item)
            return

        if self.zone == "filters":
            self._edit_filter(item)
            return

        col_name = item.data(Qt.UserRole)
        if not col_name:
            return

        # Из «Доступных» — в «Строки»
        if self.zone == "available":
            dlg = self.window()
            rows_list = getattr(dlg, "list_rows", None)
            if rows_list is not None and rows_list._find_item(col_name) is None:
                rows_list._add_plain_item(col_name)
                rows_list.changed.emit()

            self.takeItem(self.row(item))
            self.changed.emit()
            return

        # Из «Строк» / «Колонок» — в «Доступные»
        self.takeItem(self.row(item))
        dlg = self.window()
        try:
            dlg._return_to_available(col_name)
        except Exception:
            pass
        self.changed.emit()

    def _edit_filter(self, item):
        """Двойной клик по фильтру — изменить список значений."""
        col_name = item.data(Qt.UserRole)
        if not col_name:
            return

        dlg_window = self.window()
        df = getattr(dlg_window, "df", None)
        if df is None or col_name not in df.columns:
            return

        try:
            unique = sorted({str(v) for v in df[col_name].dropna().unique()})
        except Exception:
            return

        current = item.data(Qt.UserRole + 3)

        sel_dialog = FilterValuesDialog(
            self.theme, col_name, unique,
            current=current,
            parent=self.window(),
        )
        if sel_dialog.exec() != QDialog.Accepted:
            return

        item.setData(Qt.UserRole + 3, sel_dialog.result_values)
        self._update_filter_label(item)
        self.changed.emit()

    def _ask_aggregation(self, item):
        menu = QMenu(self)
        actions = {}
        current = item.data(Qt.UserRole + 2) or "sum"
        for key, label, sym in AGGREGATIONS:
            prefix = "● " if key == current else "   "
            act = menu.addAction(f"{prefix}{label}  {sym}")
            actions[act] = ("agg", key)

        menu.addSeparator()
        act_remove = menu.addAction("🗑  Убрать из «Значений»")
        actions[act_remove] = ("remove", None)

        pos = self.viewport().mapToGlobal(self.visualItemRect(item).center())
        chosen = menu.exec(pos)
        if chosen is None:
            return
        action = actions.get(chosen)
        if action is None:
            return

        kind, value = action

        if kind == "remove":
            col_name = item.data(Qt.UserRole)
            self.takeItem(self.row(item))
            dlg = self.window()
            try:
                dlg._return_to_available(col_name)
            except Exception:
                pass
            self.changed.emit()
            return

        new_key = value
        item.setData(Qt.UserRole + 2, new_key)
        label, sym = AGG_MAP[new_key]
        item.setText(f"{col_name_text(item)}    {sym}")
        item.setToolTip(f"{col_name_text(item)}: {label}")
        self.changed.emit()


# ============================================================
# Диалог
# ============================================================

class PivotDialog(QDialog):
    """Диалог создания/редактирования сводной таблицы."""

    def __init__(self, theme, df: pd.DataFrame, initial_spec: dict | None = None,
                 parent=None):
        super().__init__(parent)
        self.theme = theme
        self.df = df
        self.columns = list(df.columns)
        self._initial_spec = initial_spec

        self.result_spec: dict | None = None
        self.preview_result: pd.DataFrame | None = None

        title = "Редактирование сводной" if initial_spec else "Сводная таблица"
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumSize(1180, 780)

        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(200)
        self._preview_timer.timeout.connect(self._rebuild_preview)

        self._build_ui()
        self._apply_style()

        if initial_spec:
            self._fill_from_spec(initial_spec)
        else:
            self._fill_available()

        self._schedule_preview()

    # ============================================================
    # UI
    # ============================================================

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(14)

        title_text = "✏️  Редактирование сводной" if self._initial_spec else "📊  Сводная таблица"
        title = QLabel(title_text)
        title.setObjectName("title")
        root.addWidget(title)

        subtitle = QLabel(
            "Перетащите колонки в зоны. Двойной клик по значению — выбор агрегации.\n"
            "Двойной клик по фильтру — изменить список значений."
        )
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        line = QFrame()
        line.setObjectName("divider")
        line.setFrameShape(QFrame.HLine)
        root.addWidget(line)

        body = QHBoxLayout()
        body.setSpacing(16)

        # ── Доступные ──
        left = QVBoxLayout()
        left.setSpacing(6)

        lbl_av = QLabel("ДОСТУПНЫЕ КОЛОНКИ")
        lbl_av.setObjectName("sectlabel")
        left.addWidget(lbl_av)

        self.list_available = PivotList("available", self.theme)
        self.list_available.setMinimumWidth(180)
        self.list_available.setMaximumWidth(220)
        left.addWidget(self.list_available, stretch=1)

        body.addLayout(left)

        # ── Зоны ──
        right = QVBoxLayout()
        right.setSpacing(12)

        grid = QGridLayout()
        grid.setSpacing(12)

        self.list_filters = PivotList("filters", self.theme)
        grid.addLayout(self._wrap_zone(self.list_filters, "ФИЛЬТРЫ", "🎯"), 0, 0)

        self.list_cols = PivotList("cols", self.theme)
        grid.addLayout(self._wrap_zone(self.list_cols, "КОЛОНКИ", "📋"), 0, 1)

        self.list_rows = PivotList("rows", self.theme)
        grid.addLayout(self._wrap_zone(self.list_rows, "СТРОКИ", "↕"), 1, 0)

        self.list_values = PivotList("values", self.theme)
        grid.addLayout(self._wrap_zone(self.list_values, "ЗНАЧЕНИЯ", "Σ"), 1, 1)

        right.addLayout(grid)

        opts = QHBoxLayout()
        opts.setSpacing(16)

        self.chk_fill_zero = QCheckBox("Пустые → 0")
        self.chk_fill_zero.setChecked(True)
        opts.addWidget(self.chk_fill_zero)

        self.chk_margins = QCheckBox("Показать «Итого»")
        self.chk_margins.setChecked(False)
        opts.addWidget(self.chk_margins)

        opts.addStretch()
        right.addLayout(opts)

        lbl_prev = QLabel("ПРЕДПРОСМОТР (первые 100 строк)")
        lbl_prev.setObjectName("sectlabel")
        right.addWidget(lbl_prev)

        self.preview = QTableWidget()
        self.preview.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.preview.setAlternatingRowColors(True)
        self.preview.horizontalHeader().setStretchLastSection(False)
        self.preview.setStyleSheet(self._preview_style())
        right.addWidget(self.preview, stretch=2)

        body.addLayout(right, stretch=1)
        root.addLayout(body, stretch=1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()

        btn_cancel = QPushButton("Отмена")
        btn_cancel.setObjectName("secondary")
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        ok_text = "Сохранить" if self._initial_spec else "Создать"
        self.btn_create = QPushButton(ok_text)
        self.btn_create.setObjectName("primary")
        self.btn_create.setCursor(Qt.PointingHandCursor)
        self.btn_create.setEnabled(False)
        self.btn_create.clicked.connect(self._on_create)
        btn_row.addWidget(self.btn_create)

        root.addLayout(btn_row)

        for lst in (self.list_available, self.list_filters,
                    self.list_cols, self.list_rows, self.list_values):
            lst.changed.connect(self._schedule_preview)

        self.chk_fill_zero.toggled.connect(self._schedule_preview)
        self.chk_margins.toggled.connect(self._schedule_preview)

    def _wrap_zone(self, lst: PivotList, title: str, icon: str) -> QVBoxLayout:
        lay = QVBoxLayout()
        lay.setSpacing(6)
        lbl = QLabel(f"{icon}  {title}")
        lbl.setObjectName("sectlabel")
        lay.addWidget(lbl)
        lst.setMinimumHeight(130)
        lay.addWidget(lst, stretch=1)
        return lay

    def _preview_style(self) -> str:
        t = self.theme
        return f"""
            QTableWidget {{
                background: {t.bg_panel};
                alternate-background-color: {t.bg_card};
                color: {t.text_main};
                border: 1px solid {t.border};
                border-radius: 8px;
                font-size: 11px;
                gridline-color: transparent;
                outline: none;
            }}
            QTableWidget::item {{
                padding: 4px 6px;
                border: none;
                color: {t.text_main};
            }}
            QTableWidget::item:selected {{
                background: {t.primary_hover};
                color: {t.text_main};
            }}
            QHeaderView {{
                background: {t.bg_card};
                border: none;
            }}
            QHeaderView::section {{
                background: {t.bg_card};
                color: {t.primary};
                padding: 5px 8px;
                border: none;
                border-bottom: 1px solid {t.border};
                font-weight: 600;
                font-size: 11px;
            }}
        """

    def _apply_style(self):
        t = self.theme
        self.setStyleSheet(f"""
            QDialog {{ background: {t.bg_card}; }}
            QLabel {{
                color: {t.text_main};
                background: transparent;
                font-size: 13px;
            }}
            QLabel#title {{
                font-size: 20px;
                font-weight: 700;
                color: {t.text_main};
            }}
            QLabel#subtitle {{
                font-size: 12px;
                color: {t.text_muted};
            }}
            QLabel#sectlabel {{
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 1.2px;
                color: {t.text_muted};
                padding: 2px 4px;
            }}
            QFrame#divider {{
                background: {t.border};
                max-height: 1px;
                border: none;
            }}
            QCheckBox {{
                color: {t.text_main};
                font-size: 12px;
                spacing: 8px;
                padding: 4px 0;
                background: transparent;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 1px solid {t.border};
                background: {t.bg_panel};
            }}
            QCheckBox::indicator:checked {{
                background: {t.primary};
                border: 1px solid {t.primary};
            }}
            QPushButton#primary {{
                background: {t.primary};
                color: {t.text_inverse};
                border: none;
                padding: 10px 24px;
                border-radius: 9px;
                font-size: 13px;
                font-weight: 600;
                min-width: 130px;
            }}
            QPushButton#primary:hover {{ background: #9ade4f; }}
            QPushButton#primary:disabled {{
                background: {t.bg_panel};
                color: {t.text_muted};
            }}
            QPushButton#secondary {{
                background: transparent;
                color: {t.text_main};
                border: 1px solid {t.border};
                padding: 10px 24px;
                border-radius: 9px;
                font-size: 13px;
                min-width: 100px;
            }}
            QPushButton#secondary:hover {{ background: {t.bg_panel}; }}
            QMenu {{
                background: {t.bg_card};
                color: {t.text_main};
                border: 1px solid {t.border};
                border-radius: 6px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 6px 16px;
                border-radius: 4px;
                font-size: 12px;
                color: {t.text_main};
            }}
            QMenu::item:selected {{ background: {t.primary_hover}; }}
        """)

    # ============================================================
    # Наполнение
    # ============================================================

    def _fill_available(self):
        self.list_available.blockSignals(True)
        self.list_available.clear()
        for col in self.columns:
            item = QListWidgetItem(str(col))
            item.setForeground(QBrush(QColor(self.theme.text_main)))
            item.setData(Qt.UserRole, str(col))
            item.setData(Qt.UserRole + 1, "available")
            item.setToolTip(str(col))
            self.list_available.addItem(item)
        self.list_available.blockSignals(False)

    def _fill_from_spec(self, spec: dict):
        """Заполнить зоны из существующей спецификации."""
        # Все колонки доступны изначально
        self._fill_available()

        used = set()

        # ── Фильтры ──
        for col in spec.get("filters", []):
            item = QListWidgetItem()
            item.setForeground(QBrush(QColor(self.theme.text_main)))
            item.setData(Qt.UserRole, col)
            item.setData(Qt.UserRole + 1, "filters")
            item.setData(Qt.UserRole + 3, spec.get("filter_values", {}).get(col))
            self.list_filters._update_filter_label(item)
            self.list_filters.addItem(item)
            used.add(col)

        # ── Строки ──
        for col in spec.get("rows", []):
            self.list_rows._add_plain_item(col)
            used.add(col)

        # ── Колонки ──
        for col in spec.get("cols", []):
            self.list_cols._add_plain_item(col)
            used.add(col)

        # ── Значения ──
        for v in spec.get("values", []):
            col = v.get("column")
            agg = v.get("agg", "sum")
            if col:
                self.list_values._add_value_item(col, agg)
                used.add(col)

        # ── Убрать использованные из «Доступных» ──
        self.list_available.blockSignals(True)
        for i in range(self.list_available.count() - 1, -1, -1):
            it = self.list_available.item(i)
            if it.data(Qt.UserRole) in used:
                self.list_available.takeItem(i)
        self.list_available.blockSignals(False)

        # ── Опции ──
        self.chk_fill_zero.setChecked(spec.get("fill_zero", True))
        self.chk_margins.setChecked(spec.get("margins", False))

    def _return_to_available(self, col_name: str):
        for i in range(self.list_available.count()):
            if self.list_available.item(i).data(Qt.UserRole) == col_name:
                return
        item = QListWidgetItem(col_name)
        item.setForeground(QBrush(QColor(self.theme.text_main)))
        item.setData(Qt.UserRole, col_name)
        item.setData(Qt.UserRole + 1, "available")
        item.setToolTip(col_name)
        self.list_available.addItem(item)

    # ============================================================
    # Предпросмотр
    # ============================================================

    def _schedule_preview(self):
        self._preview_timer.start()

    def _collect_spec(self) -> dict:
        def _names(lst):
            out = []
            for i in range(lst.count()):
                out.append(lst.item(i).data(Qt.UserRole))
            return out

        values = []
        for i in range(self.list_values.count()):
            it = self.list_values.item(i)
            values.append({
                "column": it.data(Qt.UserRole),
                "agg": it.data(Qt.UserRole + 2) or "sum",
            })

        # Значения фильтров
        filter_values = {}
        for i in range(self.list_filters.count()):
            it = self.list_filters.item(i)
            col = it.data(Qt.UserRole)
            vals = it.data(Qt.UserRole + 3)
            if col is not None:
                filter_values[col] = vals

        return {
            "filters": _names(self.list_filters),
            "filter_values": filter_values,
            "rows":    _names(self.list_rows),
            "cols":    _names(self.list_cols),
            "values":  values,
            "fill_zero": self.chk_fill_zero.isChecked(),
            "margins":   self.chk_margins.isChecked(),
            "reset_index": True,   # плоский вид — всегда
        }

    def _apply_filters(self, df: pd.DataFrame, spec: dict) -> pd.DataFrame:
        """Применить фильтры из спецификации."""
        filter_values = spec.get("filter_values", {})
        for col, allowed in filter_values.items():
            if allowed is None:
                continue
            if col not in df.columns:
                continue
            allowed_set = set(str(v) for v in allowed)
            mask = df[col].astype(str).isin(allowed_set)
            # Учитываем NaN, если "—" был в allowed
            df = df[mask]
        return df

    def _rebuild_preview(self):
        spec = self._collect_spec()
        self.btn_create.setEnabled(len(spec["values"]) > 0)

        if not spec["values"]:
            self.preview.clear()
            self.preview.setRowCount(0)
            self.preview.setColumnCount(1)
            self.preview.setHorizontalHeaderLabels(["Нет значений"])
            return

        try:
            df_in = self._apply_filters(self.df, spec)
            result = self._compute_pivot(df_in, spec)
            self.preview_result = result
            self._render_preview(result)
        except Exception as e:
            self.preview_result = None
            self.preview.clear()
            self.preview.setRowCount(1)
            self.preview.setColumnCount(1)
            self.preview.setHorizontalHeaderLabels(["Ошибка"])
            it = QTableWidgetItem(f"{type(e).__name__}: {e}")
            it.setForeground(QBrush(QColor(self.theme.text_main)))
            self.preview.setItem(0, 0, it)

    def _compute_pivot(self, df: pd.DataFrame, spec: dict) -> pd.DataFrame:
        rows = spec["rows"] or None
        cols = spec["cols"] or None
        values = spec["values"]

        if not values:
            return pd.DataFrame()

        aggs = {v["agg"] for v in values}
        val_cols = [v["column"] for v in values]

        if len(aggs) == 1:
            agg = aggs.pop()
            fill = 0 if spec["fill_zero"] else None
            result = pd.pivot_table(
                df,
                index=rows,
                columns=cols,
                values=val_cols,
                aggfunc=agg,
                fill_value=fill,
                margins=spec["margins"],
                margins_name="Итого",
            )
        else:
            group_keys = (rows or [])
            if not group_keys:
                data = {}
                for v in values:
                    key = f"{v['column']} ({v['agg']})"
                    data[key] = [df[v["column"]].agg(v["agg"])]
                result = pd.DataFrame(data)
            else:
                grouped = df.groupby(group_keys, dropna=False)
                result = grouped.agg({
                    v["column"]: v["agg"] for v in values
                })
                result.columns = [
                    f"{c} ({v['agg']})"
                    for c, v in zip(result.columns, values)
                ]
                if spec["reset_index"]:
                    result = result.reset_index()

        if isinstance(result, pd.Series):
            result = result.to_frame()

        # Всегда разворачиваем индекс — плоский вид для xlsx
        if not isinstance(result.index, pd.RangeIndex):
            try:
                result = result.reset_index()
            except Exception:
                pass

        return result

    def _render_preview(self, df: pd.DataFrame, max_rows: int = 100):
        if df is None or df.empty:
            self.preview.clear()
            self.preview.setRowCount(0)
            self.preview.setColumnCount(1)
            self.preview.setHorizontalHeaderLabels(["Пусто"])
            return

        view = df.head(max_rows).copy()

        # ★ Показываем индекс как обычные колонки (для наглядности)
        n_index_cols = 0
        if not isinstance(view.index, pd.RangeIndex):
            idx_names = list(view.index.names)
            fixed_names = []
            for i, nm in enumerate(idx_names):
                if nm is None or str(nm) == "" or str(nm) == "None":
                    fixed_names.append(f"Группа {i + 1}")
                else:
                    fixed_names.append(str(nm))
            view = view.reset_index()
            # Переименовываем индексные колонки (их имена из reset_index — временные)
            view.columns = fixed_names + [str(c) for c in view.columns[n_index_cols + len(fixed_names):]]
            n_index_cols = len(fixed_names)

        self.preview.clear()
        self.preview.setRowCount(len(view))
        self.preview.setColumnCount(len(view.columns))
        self.preview.setHorizontalHeaderLabels([str(c) for c in view.columns])

        muted = QColor(self.theme.text_muted)
        main = QColor(self.theme.text_main)

        for r in range(len(view)):
            for c in range(len(view.columns)):
                value = view.iat[r, c]
                if value is None:
                    text = ""
                else:
                    try:
                        if pd.isna(value):
                            text = ""
                        else:
                            text = str(value)
                    except Exception:
                        text = str(value)

                item = QTableWidgetItem(text)
                # Индексные колонки — приглушённые, чтобы отличались от данных
                item.setForeground(QBrush(muted if c < n_index_cols else main))
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.preview.setItem(r, c, item)

        self.preview.resizeColumnsToContents()
        for c in range(self.preview.columnCount()):
            if self.preview.columnWidth(c) > 220:
                self.preview.setColumnWidth(c, 220)

    # ============================================================
    # Создание
    # ============================================================

    def _on_create(self):
        spec = self._collect_spec()
        if not spec["values"]:
            QMessageBox.warning(self, "Нет значений",
                                "Добавьте хотя бы одну колонку в «Значения».")
            return

        self.result_spec = spec
        self.accept()