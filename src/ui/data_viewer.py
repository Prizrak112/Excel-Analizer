"""
Виджет редактора данных на основе QTableView.
Переключатель листов + кнопка «Изменить сводную».
"""

import pandas as pd

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableView,
    QAbstractItemView, QLabel, QInputDialog, QMenu, QFrame,
    QStackedWidget, QComboBox, QPushButton, QHeaderView
)
from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, Signal, QPoint
from PySide6.QtGui import QColor

from src.ui.filter_header import FilterHeader


_COLOR_NA = QColor("#8B93A7")
_ALIGN_RIGHT = int(Qt.AlignRight | Qt.AlignVCenter)
_ALIGN_LEFT = int(Qt.AlignLeft | Qt.AlignVCenter)


class DataFrameModel(QAbstractTableModel):
    cell_edited = Signal(int, int, object)

    def __init__(self, df, parent=None):
        super().__init__(parent)
        self._df = df
        self._isna = pd.isna
        self._n_rows = len(df)
        self._n_cols = len(df.columns)
        self._columns = list(df.columns)

    def rowCount(self, parent=QModelIndex()):
        return self._n_rows

    def columnCount(self, parent=QModelIndex()):
        return self._n_cols

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row = index.row()
        col = index.column()
        value = self._df.iat[row, col]

        if role == Qt.DisplayRole:
            if value is None:
                return ""
            if self._isna(value):
                return "—"
            if isinstance(value, float):
                if value == int(value):
                    return f"{int(value):,}"
                return f"{value:,.2f}"
            if isinstance(value, int):
                return f"{value:,}"
            return str(value)

        elif role == Qt.EditRole:
            # ★ Отдаём «сырое» значение — редактор при двойном клике
            #   откроется с текущим содержимым ячейки, а не пустым.
            if value is None or self._isna(value):
                return ""
            return str(value) if not isinstance(value, str) else value

        elif role == Qt.TextAlignmentRole:
            if isinstance(value, (int, float)):
                return _ALIGN_RIGHT
            return _ALIGN_LEFT

        elif role == Qt.ForegroundRole:
            if self._isna(value):
                return _COLOR_NA

        return None

    def setData(self, index, value, role=Qt.EditRole):
        if not index.isValid() or role != Qt.EditRole:
            return False
        row = index.row()
        col = index.column()
        try:
            self._df.iat[row, col] = value
        except Exception:
            return False
        self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole])
        self.cell_edited.emit(row, col, value)
        return True

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return str(self._columns[section])
            return str(section + 1)
        elif role == Qt.TextAlignmentRole:
            if orientation == Qt.Horizontal:
                return _ALIGN_LEFT
            return _ALIGN_RIGHT
        return None

    def update_dataframe(self, df):
        self.beginResetModel()
        self._df = df
        self._isna = pd.isna
        self._n_rows = len(df)
        self._n_cols = len(df.columns)
        self._columns = list(df.columns)
        self.endResetModel()


class DataViewerWidget(QWidget):
    column_selected = Signal(str)
    cell_edit_requested = Signal(int, str, object)
    column_rename_requested = Signal(str, str)
    delete_columns_requested = Signal(list)
    delete_rows_requested = Signal(list)
    filter_requested = Signal(str, QPoint)
    sort_requested = Signal(str, bool)
    sheet_switch_requested = Signal(str)
    pivot_edit_requested = Signal()
    sheet_rename_requested = Signal(str)

    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self._model = None
        self._real_columns: list[str] = []
        self._last_selected_col: str | None = None
        self._header = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background: transparent;")

        # ── Страница 0 — таблица ──
        table_page = QWidget()
        table_page.setStyleSheet("background: transparent;")
        tp_layout = QVBoxLayout(table_page)
        tp_layout.setContentsMargins(0, 0, 0, 0)
        tp_layout.setSpacing(0)

        # ── Верхняя инфо-полоса ──
        self._top_bar = QWidget()
        self._top_bar.setStyleSheet(f"""
            QWidget {{
                background: {self.theme.bg_page};
                border: none;
            }}
        """)
        top_layout = QHBoxLayout(self._top_bar)
        top_layout.setContentsMargins(16, 8, 16, 8)
        top_layout.setSpacing(10)

        # ── Переключатель листов ──
        self.combo_sheets = QComboBox()
        self.combo_sheets.setVisible(False)
        self.combo_sheets.setMinimumWidth(200)
        self.combo_sheets.setStyleSheet(f"""
            QComboBox {{
                background: {self.theme.bg_panel};
                color: {self.theme.text_main};
                border: 1px solid {self.theme.border};
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 13px;
                font-weight: 600;
            }}
            QComboBox:hover {{
                border: 1px solid {self.theme.primary};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 24px;
            }}
            QComboBox QAbstractItemView {{
                background: {self.theme.bg_card};
                color: {self.theme.text_main};
                border: 1px solid {self.theme.border};
                selection-background-color: {self.theme.primary_hover};
                selection-color: {self.theme.text_main};
                padding: 4px;
                font-size: 13px;
            }}
        """)
        self.combo_sheets.currentTextChanged.connect(self._on_sheet_changed)
        self.combo_sheets.setToolTip("ПКМ — переименовать лист")
        self.combo_sheets.setContextMenuPolicy(Qt.CustomContextMenu)
        self.combo_sheets.customContextMenuRequested.connect(self._on_sheet_context_menu)
        top_layout.addWidget(self.combo_sheets)

        # ── Кнопка «Изменить сводную» ──
        self.btn_edit_pivot = QPushButton("✏  Изменить сводную")
        self.btn_edit_pivot.setVisible(False)
        self.btn_edit_pivot.setCursor(Qt.PointingHandCursor)
        self.btn_edit_pivot.setStyleSheet(f"""
            QPushButton {{
                background: {self.theme.bg_panel};
                color: {self.theme.primary};
                border: 1px solid {self.theme.primary};
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {self.theme.primary_hover};
            }}
        """)
        self.btn_edit_pivot.clicked.connect(self.pivot_edit_requested.emit)
        top_layout.addWidget(self.btn_edit_pivot)

        self.label_info = QLabel("")
        self.label_info.setStyleSheet(f"""
            color: {self.theme.text_muted};
            font-size: 11px;
            letter-spacing: 0.3px;
            background: transparent;
            border: none;
        """)
        top_layout.addWidget(self.label_info)
        top_layout.addStretch()

        tp_layout.addWidget(self._top_bar)

        # ── Таблица ──
        self.table = QTableView()
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
        )
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.verticalHeader().setMinimumWidth(52)
        self.table.setFrameShape(QFrame.NoFrame)
        self.table.setShowGrid(False)

        self._header = FilterHeader(Qt.Horizontal, self.theme, self.table)
        self.table.setHorizontalHeader(self._header)
        self._header.setStretchLastSection(False)
        self._header.setCascadingSectionResizes(False)
        self._header.setSectionsMovable(True)
        self._header.setSectionsClickable(True)
        self._header.setFixedHeight(36)
        self._header.sectionClicked.connect(self._on_header_clicked)
        self._header.sectionDoubleClicked.connect(self._on_header_double_clicked)
        self._header.filter_clicked.connect(self._on_filter_clicked)
        self._header.sort_clicked.connect(self._on_sort_clicked)
        self._header.setContextMenuPolicy(Qt.CustomContextMenu)
        self._header.customContextMenuRequested.connect(self._on_header_context_menu)

        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_cell_context_menu)

        self.table.setStyleSheet(f"""
            QTableView {{
                background: {self.theme.bg_card};
                alternate-background-color: {self.theme.bg_panel};
                gridline-color: transparent;
                color: {self.theme.text_main};
                font-size: 12px;
                border: none;
                outline: none;
                selection-background-color: {self.theme.primary_hover};
                selection-color: {self.theme.text_main};
            }}
            QTableView::item {{
                padding: 4px 8px;
                border: none;
            }}
            QTableView::item:selected {{
                background: {self.theme.primary_hover};
                color: {self.theme.text_main};
            }}
            /* ★ Редактор ячейки — непрозрачный, без больших отступов и
               скруглений, чтобы полностью накрывать содержимое ячейки
               и не пропускать старый текст. */
            QTableView QLineEdit {{
                background: {self.theme.bg_panel};
                color: {self.theme.text_main};
                border: 1px solid {self.theme.primary};
                border-radius: 0px;
                padding: 0px 6px;
                margin: 0px;
                font-size: 12px;
                selection-background-color: {self.theme.primary_hover};
                selection-color: {self.theme.text_main};
            }}
            QTableView::corner {{
                background: {self.theme.bg_card};
                border: none;
            }}
            QTableCornerButton::section {{
                background: {self.theme.bg_card};
                border: none;
            }}
            QHeaderView {{
                background: {self.theme.bg_card};
                border: none;
            }}
            QHeaderView::section {{
                background: {self.theme.bg_card};
                color: {self.theme.primary};
                padding: 6px 10px;
                border: none;
                border-bottom: 1px solid {self.theme.border};
                font-weight: 600;
                font-size: 11px;
                letter-spacing: 0.3px;
            }}
            QHeaderView::section:hover {{
                background: {self.theme.bg_panel};
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 12px;
                margin: 0;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {self.theme.border};
                min-height: 30px;
                border-radius: 5px;
                margin: 3px 3px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {self.theme.text_muted};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0; background: none; border: none;
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
                background: {self.theme.border};
                min-width: 30px;
                border-radius: 5px;
                margin: 3px 3px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: {self.theme.text_muted};
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0; background: none; border: none;
            }}
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
                background: none;
            }}
        """)

        tp_layout.addWidget(self.table, stretch=1)
        self._stack.addWidget(table_page)

        # ── Страница 1 — пустое состояние ──
        empty_page = QWidget()
        empty_page.setStyleSheet(f"background: {self.theme.bg_card};")
        ep_layout = QVBoxLayout(empty_page)
        ep_layout.setContentsMargins(40, 40, 40, 40)
        ep_layout.setSpacing(0)
        ep_layout.addStretch()

        icon = QLabel("📊")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("font-size: 72px; background: transparent;")
        ep_layout.addWidget(icon)

        ep_layout.addSpacing(16)

        title = QLabel("Откройте файл, чтобы начать")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(f"""
            color: {self.theme.text_main};
            font-size: 18px;
            font-weight: 700;
            background: transparent;
        """)
        ep_layout.addWidget(title)

        ep_layout.addSpacing(8)

        subtitle = QLabel(
            "Excel-файлы (.xlsx, .xls) или готовые проекты (.eaproj)\n"
            "Перетащите в окно или нажмите Ctrl+O"
        )
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet(f"""
            color: {self.theme.text_muted};
            font-size: 12px;
            line-height: 1.6;
            background: transparent;
        """)
        ep_layout.addWidget(subtitle)

        ep_layout.addStretch()
        self._stack.addWidget(empty_page)

        layout.addWidget(self._stack, stretch=1)
        self._stack.setCurrentIndex(1)

    # ============================================================
    # Публичный API
    # ============================================================

    def set_data(self, df, info_text: str = "", real_columns: list | None = None):
        self._real_columns = list(real_columns) if real_columns else list(df.columns)
        self._model = DataFrameModel(df, self.table)
        self._model.cell_edited.connect(self._on_model_cell_edited)
        self.table.setModel(self._model)

        n_cols = self._model.columnCount()
        rows = self._model.rowCount()
        if rows <= 1000:
            self.table.resizeColumnsToContents()
            for col in range(n_cols):
                if self.table.columnWidth(col) > 300:
                    self.table.setColumnWidth(col, 300)
        else:
            for col in range(n_cols):
                self.table.setColumnWidth(col, 150)

        # ★ Фиксируем Interactive-режим и «замораживаем» ширины
        for col in range(n_cols):
            self._header.setSectionResizeMode(col, QHeaderView.Interactive)
            self._header.resizeSection(col, self.table.columnWidth(col))

        if not info_text:
            info_text = f"{len(df):,} строк × {len(df.columns)} колонок"
        self.label_info.setText(info_text)

        self._stack.setCurrentIndex(0)

    def set_sheets(self, names: list, active: str, is_pivot: bool = False):
        """Заполнить переключатель листов + показать/скрыть кнопку."""
        self.combo_sheets.blockSignals(True)
        self.combo_sheets.clear()
        for n in names:
            self.combo_sheets.addItem(str(n))
        if active in names:
            self.combo_sheets.setCurrentText(active)
        self.combo_sheets.setVisible(bool(names))
        self.combo_sheets.blockSignals(False)

        self.btn_edit_pivot.setVisible(bool(is_pivot))

    def _on_sheet_changed(self, name: str):
        if not name:
            return
        self.sheet_switch_requested.emit(name)

    def _on_sheet_context_menu(self, pos):
        """ПКМ по combo-переключателю листов."""
        if self.combo_sheets.count() == 0:
            return
        current = self.combo_sheets.currentText()
        if not current:
            return

        menu = QMenu(self)
        action_rename = menu.addAction(f"✏  Переименовать «{current}»")
        chosen = menu.exec(self.combo_sheets.mapToGlobal(pos))
        if chosen == action_rename:
            self.sheet_rename_requested.emit(current)

    def clear(self):
        self.table.setModel(None)
        self._model = None
        self._real_columns = []
        self._last_selected_col = None
        self.label_info.setText("")
        self.combo_sheets.setVisible(False)
        self.btn_edit_pivot.setVisible(False)
        self._stack.setCurrentIndex(1)

    def set_filtered_columns(self, filtered_names: set):
        if not filtered_names:
            indices = set()
        else:
            indices = {i for i, name in enumerate(self._real_columns) if name in filtered_names}
        if self._header is not None:
            self._header.set_filtered_indices(indices)

    def set_sort_state(self, sort_state_names: list):
        if not self._real_columns:
            if self._header is not None:
                self._header.set_sort_state([])
            return
        indices = []
        for col_name, asc in sort_state_names:
            try:
                idx = self._real_columns.index(col_name)
                indices.append((idx, asc))
            except ValueError:
                continue
        if self._header is not None:
            self._header.set_sort_state(indices)

    # ============================================================
    # Поиск
    # ============================================================

    def find_all(self, text: str, case_sensitive: bool, scope: str) -> list:
        if self._model is None or not text:
            return []
        df = self._model._df
        n_cols = self._model.columnCount()
        if n_cols == 0:
            return []
        if scope == "column":
            cur_col = self.table.currentIndex().column()
            cols_to_search = [cur_col if cur_col >= 0 else 0]
        else:
            cols_to_search = range(n_cols)
        needle = text if case_sensitive else text.lower()
        columns = self._model._columns
        matches = []
        for c in cols_to_search:
            series = df.iloc[:, c]
            str_series = series.astype(str)
            if case_sensitive:
                mask = str_series.str.contains(needle, regex=False, na=False)
            else:
                mask = str_series.str.lower().str.contains(needle, regex=False, na=False)
            if not mask.any():
                continue
            col_name = str(columns[c])
            for r in mask[mask].index.tolist():
                val_str = str(series.iat[r])
                if len(val_str) > 80:
                    val_str = val_str[:77] + "..."
                matches.append({"row": int(r), "col": c, "col_name": col_name, "value": val_str})
        return matches

    def go_to_cell(self, row: int, col: int):
        if self._model is None:
            return
        index = self._model.index(row, col)
        self.table.setCurrentIndex(index)
        self.table.scrollTo(index, self.table.ScrollHint.PositionAtCenter)
        self.table.selectRow(row)

    def clear_find(self):
        self.table.clearSelection()

    # ============================================================
    # Обработчики
    # ============================================================

    def _on_header_clicked(self, index: int):
        if not (0 <= index < len(self._real_columns)):
            return
        real = self._real_columns[index]
        if real == self._last_selected_col:
            return
        self._last_selected_col = real
        self.column_selected.emit(real)

    def _on_header_double_clicked(self, index: int):
        if index < 0 or index >= len(self._real_columns):
            return
        real_name = self._real_columns[index]
        current_display = real_name
        if self._model is not None:
            current_display = self._model.headerData(index, Qt.Horizontal) or real_name
        new_name, ok = QInputDialog.getText(
            self, "Переименовать колонку",
            f"Новое имя для «{current_display}»:",
            text=str(current_display),
        )
        if ok and new_name.strip() and new_name.strip() != current_display:
            self.column_rename_requested.emit(real_name, new_name.strip())

    def _on_filter_clicked(self, index: int):
        if not (0 <= index < len(self._real_columns)):
            return
        col_name = self._real_columns[index]
        left = self._header.sectionViewportPosition(index)
        width = self._header.sectionSize(index)
        x = left + width - FilterHeader.FUNNEL_WIDTH // 2
        y = self._header.height()
        global_pos = self._header.mapToGlobal(QPoint(x, y))
        self.filter_requested.emit(col_name, global_pos)

    def _on_sort_clicked(self, index: int, shift: bool):
        if not (0 <= index < len(self._real_columns)):
            return
        self.sort_requested.emit(self._real_columns[index], shift)

    def _on_header_context_menu(self, pos: QPoint):
        index = self._header.logicalIndexAt(pos)
        if index < 0 or index >= len(self._real_columns):
            return

        # ★ Мультивыбор: берём все колонки, охваченные выделенными ячейками
        #   таблицы. Если правый клик по невыделенной колонке — работаем
        #   только с ней (одна колонка).
        sm = self.table.selectionModel()
        selected_cols: set[int] = set()
        if sm is not None:
            selected_cols = {idx.column() for idx in sm.selectedIndexes()}

        if index not in selected_cols:
            selected_cols = {index}

        real_names = [
            self._real_columns[i] for i in sorted(selected_cols)
            if 0 <= i < len(self._real_columns)
        ]
        if not real_names:
            return

        menu = QMenu(self)
        if len(real_names) == 1:
            idx0 = self._real_columns.index(real_names[0])
            display_name = real_names[0]
            if self._model is not None:
                display_name = self._model.headerData(idx0, Qt.Horizontal) or real_names[0]
            action_delete = menu.addAction(f"🗑  Удалить колонку «{display_name}»")
        else:
            action_delete = menu.addAction(f"🗑  Удалить {len(real_names)} колонок")

        action = menu.exec(self._header.mapToGlobal(pos))
        if action == action_delete:
            self.delete_columns_requested.emit(real_names)
    def _on_cell_context_menu(self, pos: QPoint):
        index = self.table.indexAt(pos)
        if not index.isValid():
            return

        sm = self.table.selectionModel()
        if sm is None:
            rows = [index.row()]
            cols = [index.column()]
        else:
            selected_rows = {idx.row() for idx in sm.selectedIndexes()}
            selected_cols = {idx.column() for idx in sm.selectedIndexes()}
            if index.row() not in selected_rows:
                selected_rows = {index.row()}
            if index.column() not in selected_cols:
                selected_cols = {index.column()}
            rows = sorted(selected_rows)
            cols = sorted(selected_cols)

        menu = QMenu(self)

        # ── Удалить строки ──
        if len(rows) == 1:
            action_rows = menu.addAction(f"🗑  Удалить строку {rows[0] + 1}")
        else:
            action_rows = menu.addAction(f"🗑  Удалить {len(rows)} строк")

        menu.addSeparator()

        # ── Удалить колонки ──
        if len(cols) == 1:
            c0 = cols[0]
            real = self._real_columns[c0] if 0 <= c0 < len(self._real_columns) else "?"
            display = real
            if self._model is not None:
                display = self._model.headerData(c0, Qt.Horizontal) or real
            action_cols = menu.addAction(f"🗑  Удалить колонку «{display}»")
        else:
            action_cols = menu.addAction(f"🗑  Удалить {len(cols)} колонок")

        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if chosen == action_rows:
            self.delete_rows_requested.emit(rows)
        elif chosen == action_cols:
            real_names = [
                self._real_columns[c] for c in cols
                if 0 <= c < len(self._real_columns)
            ]
            if real_names:
                self.delete_columns_requested.emit(real_names)

    def _on_model_cell_edited(self, row: int, col: int, value):
        if 0 <= col < len(self._real_columns):
            self.cell_edit_requested.emit(row, self._real_columns[col], value)