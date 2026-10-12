"""
Диалог извлечения текста по шаблону.

Две вкладки:
  1. «✂ Выделить в примере» — пользователь выделяет целевой фрагмент
     (номер, модель, что угодно). Алгоритм сам строит regex.
  2. «📋 Шаблон / пресеты» — ручной regex или готовый пресет.

Логика визуальной вкладки:
  • Показывается одна строка за раз.
  • Пользователь выделяет в ней то, что должно остаться.
  • Пример добавляется. Пока не покрыты все строки — можно
    показать ещё пример на другой строке (клик по «➕»).
  • Все накопленные примеры видны в списке внизу — можно удалять.
"""

import re as _re

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QLineEdit, QComboBox, QListWidget,
    QListWidgetItem, QTabWidget, QWidget,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from src.ui.toast import ToastManager
from src.ui.visual_extract_widget import VisualExtractWidget
from src.core.text_extractor import PRESETS, validate_pattern
from src.core.extract_rule_builder import ExtractRuleBuilder


PREVIEW_ROWS = 10


class ExtractTextDialog(QDialog):
    """Диалог извлечения текста по шаблону."""

    def __init__(self, data, theme, display_names: dict | None = None, parent=None):
        super().__init__(parent)
        self.data = data
        self.theme = theme
        self._columns = list(data.columns)
        self._display_names = display_names or {}

        self.result_data: dict | None = None

        self._selected_column: str | None = None
        self._rule_builder: ExtractRuleBuilder | None = None
        self._current_row_index: int = 0

        self.setWindowTitle("Извлечь по шаблону")
        self.setMinimumSize(820, 780)
        self.resize(860, 840)
        self.setStyleSheet(f"QDialog {{ background: {self.theme.bg_card}; }}")

        self._build_ui()

    # ============================================================
    # UI
    # ============================================================

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(10)

        title = QLabel("✂  Извлечь по шаблону")
        title.setStyleSheet(
            f"color:{self.theme.primary}; font-size:15px; font-weight:700;"
        )
        root.addWidget(title)

        hint = QLabel(
            "Выделите мышкой фрагмент, который должен ОСТАТЬСЯ в новой "
            "колонке (номер, модель ТС, что угодно). Программа сама "
            "построит правило и применит его ко всему столбцу."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color:{self.theme.text_muted}; font-size:12px;")
        root.addWidget(hint)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background:{self.theme.border}; border:none;")
        root.addWidget(sep)

        # ── Колонка ──
        root.addWidget(self._section_label("Колонка для обработки"))

        self.cols_list = QListWidget()
        self.cols_list.setStyleSheet(f"""
            QListWidget {{
                background: {self.theme.bg_panel};
                border: 1px solid {self.theme.border};
                border-radius: 6px;
                color: {self.theme.text_main};
                font-size: 12px;
                padding: 4px;
                outline: none;
            }}
            QListWidget::item {{ padding: 6px 8px; border-radius: 4px; }}
            QListWidget::item:selected {{
                background: {self.theme.primary_hover};
                color: {self.theme.text_main};
            }}
            QListWidget::item:hover {{ background: {self.theme.bg_hover}; }}
        """)
        self.cols_list.setMaximumHeight(110)

        for col in self._columns:
            display = self._display_names.get(col, col)
            label = display if display == col else f"{display}  ({col})"
            it = QListWidgetItem(label)
            it.setData(Qt.UserRole, col)
            self.cols_list.addItem(it)

        if self._columns:
            self.cols_list.setCurrentRow(0)
            self._selected_column = self._columns[0]

        self.cols_list.currentItemChanged.connect(self._on_column_changed)
        root.addWidget(self.cols_list)

        # ── Вкладки ──
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(self._tabs_qss())
        self.tabs.addTab(self._build_visual_tab(), "✂  Выделить в примере")
        self.tabs.addTab(self._build_pattern_tab(), "📋  Шаблон / пресеты")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        root.addWidget(self.tabs, 1)

        # ── Предпросмотр ──
        root.addWidget(self._section_label("Предпросмотр"))
        self.preview_list = QListWidget()
        self.preview_list.setStyleSheet(self._preview_qss())
        self.preview_list.setMinimumHeight(120)
        root.addWidget(self.preview_list, 1)

        # ── Кнопки ──
        btns = QHBoxLayout()
        btns.setSpacing(8)
        btns.addStretch()

        b_cancel = QPushButton("Отмена")
        b_cancel.setCursor(Qt.PointingHandCursor)
        b_cancel.setStyleSheet(self._btn_secondary())
        b_cancel.clicked.connect(self.reject)
        btns.addWidget(b_cancel)

        self.b_apply = QPushButton("Применить")
        self.b_apply.setCursor(Qt.PointingHandCursor)
        self.b_apply.setDefault(True)
        self.b_apply.setStyleSheet(self._btn_primary())
        self.b_apply.clicked.connect(self._on_apply)
        self.b_apply.setEnabled(False)
        btns.addWidget(self.b_apply)

        root.addLayout(btns)

        if self._columns:
            self._reset_visual_state()

    # ------------------------------------------------------------
    # Вкладка 1 — визуальное выделение
    # ------------------------------------------------------------

    def _build_visual_tab(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        # Пример строки
        example_row = QHBoxLayout()
        example_row.setSpacing(6)

        self.lbl_example_info = QLabel("—")
        self.lbl_example_info.setStyleSheet(
            f"color:{self.theme.text_muted}; font-size:11px;"
        )
        example_row.addWidget(self.lbl_example_info)
        example_row.addStretch()

        self.b_prev_example = QPushButton("↑  Предыдущий")
        self.b_prev_example.setCursor(Qt.PointingHandCursor)
        self.b_prev_example.setStyleSheet(self._btn_small())
        self.b_prev_example.clicked.connect(lambda: self._shift_example(-1))
        example_row.addWidget(self.b_prev_example)

        self.b_next_example = QPushButton("↓  Следующий")
        self.b_next_example.setCursor(Qt.PointingHandCursor)
        self.b_next_example.setStyleSheet(self._btn_small())
        self.b_next_example.clicked.connect(lambda: self._shift_example(1))
        example_row.addWidget(self.b_next_example)

        lay.addLayout(example_row)

        # Виджет выделения
        self.visual_widget = VisualExtractWidget("", self.theme)
        self.visual_widget.selection_changed.connect(self._on_visual_selection)
        lay.addWidget(self.visual_widget)

        # Статус
        self.lbl_visual_status = QLabel("")
        self.lbl_visual_status.setWordWrap(True)
        self.lbl_visual_status.setStyleSheet(
            f"color:{self.theme.text_muted}; font-size:11px; padding:4px 0;"
        )
        lay.addWidget(self.lbl_visual_status)

        # ── Список накопленных примеров ──
        lay.addWidget(self._section_label("Примеры (что выделено)"))

        self.examples_list = QListWidget()
        self.examples_list.setStyleSheet(f"""
            QListWidget {{
                background: {self.theme.bg_panel};
                border: 1px solid {self.theme.border};
                border-radius: 6px;
                color: {self.theme.text_main};
                font-size: 12px;
                padding: 4px;
                outline: none;
                font-family: 'Consolas', monospace;
            }}
            QListWidget::item {{ padding: 4px 8px; border-radius: 4px; }}
            QListWidget::item:selected {{
                background: {self.theme.primary_hover};
            }}
        """)
        self.examples_list.setMaximumHeight(90)
        lay.addWidget(self.examples_list)

        # ── Кнопки управления ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self.b_more_example = QPushButton("➕  Показать ещё пример")
        self.b_more_example.setCursor(Qt.PointingHandCursor)
        self.b_more_example.setStyleSheet(self._btn_small())
        self.b_more_example.clicked.connect(self._on_more_example)
        self.b_more_example.setEnabled(False)
        btn_row.addWidget(self.b_more_example)

        self.b_del_example = QPushButton("🗑  Удалить пример")
        self.b_del_example.setCursor(Qt.PointingHandCursor)
        self.b_del_example.setStyleSheet(self._btn_small())
        self.b_del_example.clicked.connect(self._on_delete_example)
        self.b_del_example.setEnabled(False)
        btn_row.addWidget(self.b_del_example)

        self.b_reset_examples = QPushButton("🔄  Сбросить все")
        self.b_reset_examples.setCursor(Qt.PointingHandCursor)
        self.b_reset_examples.setStyleSheet(self._btn_small())
        self.b_reset_examples.clicked.connect(self._on_reset_examples)
        btn_row.addWidget(self.b_reset_examples)

        btn_row.addStretch()
        lay.addLayout(btn_row)

        lay.addStretch()
        return w

    # ------------------------------------------------------------
    # Вкладка 2 — пресеты / шаблон
    # ------------------------------------------------------------

    def _build_pattern_tab(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        lay.addWidget(self._section_label("Готовый шаблон"))

        self.combo_preset = QComboBox()
        self.combo_preset.setStyleSheet(self._combo_qss())
        self.combo_preset.addItem("— свой шаблон —", userData="")
        for name, pattern, example in PRESETS:
            self.combo_preset.addItem(name, userData=pattern)
            self.combo_preset.setItemData(
                self.combo_preset.count() - 1, example, Qt.ToolTipRole,
            )
        self.combo_preset.currentIndexChanged.connect(self._on_preset_changed)
        lay.addWidget(self.combo_preset)

        lay.addWidget(self._section_label("Шаблон (regex)"))

        self.edit_pattern = QLineEdit()
        self.edit_pattern.setPlaceholderText(
            r"Например: Гос\.?\s*№\s*([^,\s]+)"
        )
        self.edit_pattern.setStyleSheet(self._input_qss())
        self.edit_pattern.textChanged.connect(self._on_pattern_text_changed)
        lay.addWidget(self.edit_pattern)

        self.lbl_pattern_example = QLabel("")
        self.lbl_pattern_example.setWordWrap(True)
        self.lbl_pattern_example.setStyleSheet(
            f"color:{self.theme.text_muted}; font-size:11px; "
            f"font-family:'Consolas', monospace;"
        )
        lay.addWidget(self.lbl_pattern_example)

        lay.addStretch()
        return w

    # ============================================================
    # Логика визуальной вкладки
    # ============================================================

    def _on_column_changed(self, current, _previous):
        if current is None:
            self._selected_column = None
            return
        self._selected_column = current.data(Qt.UserRole)
        self._reset_visual_state()

    def _reset_visual_state(self):
        self._rule_builder = None
        self._current_row_index = 0

        if (self._selected_column is None
                or self._selected_column not in self.data.columns):
            self.visual_widget.set_text("")
            self.lbl_example_info.setText("—")
            self.lbl_visual_status.setText("")
            self.examples_list.clear()
            self.b_more_example.setEnabled(False)
            self.b_del_example.setEnabled(False)
            self._update_preview()
            return

        series = self.data.dataframe[self._selected_column]
        first_idx = 0
        for i, v in enumerate(series):
            if v is None:
                continue
            try:
                import pandas as pd
                if pd.isna(v):
                    continue
            except Exception:
                pass
            first_idx = i
            break

        self._current_row_index = first_idx
        self._rule_builder = ExtractRuleBuilder(series)
        self._show_example(first_idx)
        self.lbl_visual_status.setText("")
        self._refresh_examples_list()
        self.b_more_example.setEnabled(False)
        self.b_del_example.setEnabled(False)
        self._update_preview()

    def _show_example(self, idx: int):
        series = self.data.dataframe[self._selected_column]
        value = series.iloc[idx]
        text = "" if value is None else str(value)
        self.visual_widget.set_text(text)
        total = len(series)
        self.lbl_example_info.setText(f"Строка {idx + 1} из {total}")

    def _shift_example(self, delta: int):
        if self._selected_column is None:
            return
        total = len(self.data.dataframe)
        if total == 0:
            return
        new_idx = self._current_row_index + delta
        if 0 <= new_idx < total:
            self._current_row_index = new_idx
            self._show_example(new_idx)

    def _on_visual_selection(self, start: int, end: int):
        if start < 0 or end <= start or self._rule_builder is None:
            return

        idx = self._current_row_index
        series = self.data.dataframe[self._selected_column]
        value = series.iloc[idx]
        text = "" if value is None else str(value)
        selected_text = text[start:end]

        changed = self._rule_builder.set_example(idx, text, start, end)
        result = self._rule_builder.build()

        if not changed:
            self.lbl_visual_status.setText(
                f"⚠  Выделено: «{selected_text}» — правило не изменилось."
            )
        else:
            preview_vals = [v for _, v in result.samples_extracted[:3]]
            preview_str = ", ".join(f"«{v}»" for v in preview_vals) if preview_vals else "—"
            self.lbl_visual_status.setText(
                f"✅ Выделено: «{selected_text}»  ·  "
                f"покрыто {result.coverage_str}  ·  в первых: {preview_str}"
            )

        self._refresh_examples_list()
        self.b_more_example.setEnabled(bool(result.pattern and result.uncovered_rows))
        self._update_preview(result.pattern if result.pattern else None)

    def _refresh_examples_list(self):
        """Обновить список накопленных примеров."""
        self.examples_list.clear()
        if self._rule_builder is None:
            self.b_del_example.setEnabled(False)
            return

        examples = self._rule_builder.list_examples()
        for row_key, sel_text in examples:
            it = QListWidgetItem(f"Строка {row_key + 1}:  «{sel_text}»")
            it.setData(Qt.UserRole, row_key)
            self.examples_list.addItem(it)

        self.b_del_example.setEnabled(bool(examples))

    def _on_delete_example(self):
        """Удалить выбранный в списке пример."""
        if self._rule_builder is None:
            return
        item = self.examples_list.currentItem()
        if item is None:
            return
        row_key = item.data(Qt.UserRole)
        if row_key is None:
            return
        self._rule_builder.remove_example(row_key)
        result = self._rule_builder.build()
        self._refresh_examples_list()
        self.b_more_example.setEnabled(bool(result.pattern and result.uncovered_rows))
        self._update_preview(result.pattern if result.pattern else None)
        self.lbl_visual_status.setText(
            f"🗑 Пример для строки {row_key + 1} удалён."
        )

    def _on_more_example(self):
        """Перейти на первую НЕпокрытую строку для нового примера."""
        if self._rule_builder is None:
            return

        uncovered = self._rule_builder.get_uncovered_examples(n=20)
        if not uncovered:
            self.lbl_visual_status.setText("✅ Все строки покрыты.")
            self.b_more_example.setEnabled(False)
            return

        orig_idx, _text = uncovered[0]
        self._current_row_index = orig_idx
        self._show_example(orig_idx)
        self.lbl_visual_status.setText(
            f"Выделите целевой фрагмент на строке {orig_idx + 1}."
        )

    def _on_reset_examples(self):
        """Полный сброс примеров."""
        if self._rule_builder is None:
            return
        self._rule_builder.clear()
        self._refresh_examples_list()
        self.lbl_visual_status.setText("Примеры сброшены.")
        self.b_more_example.setEnabled(False)
        self._update_preview()

    # ============================================================
    # Вкладка пресетов
    # ============================================================

    def _on_preset_changed(self, idx: int):
        pattern = self.combo_preset.itemData(idx) or ""
        if pattern:
            self.edit_pattern.blockSignals(True)
            self.edit_pattern.setText(pattern)
            self.edit_pattern.blockSignals(False)
        self._update_preview()

    def _on_pattern_text_changed(self, _text: str):
        self._update_preview()

    # ============================================================
    # Предпросмотр
    # ============================================================

    def _on_tab_changed(self, _idx: int):
        self._update_preview()

    def _current_pattern(self) -> str:
        if self.tabs.currentIndex() == 0:
            if self._rule_builder is None:
                return ""
            return self._rule_builder.build().pattern or ""
        return self.edit_pattern.text().strip()

    def _update_preview(self, override_pattern: str | None = None):
        self.preview_list.clear()
        pattern = (override_pattern if override_pattern is not None
                   else self._current_pattern())
        col = self._selected_column

        if not pattern:
            self._add_line("Выделите целевой фрагмент или введите шаблон.", muted=True)
            self.b_apply.setEnabled(False)
            return

        ok, err = validate_pattern(pattern)
        if not ok:
            self._add_line(f"⚠ {err}", muted=True, color="#e74c3c")
            self.b_apply.setEnabled(False)
            return

        if col is None:
            self._add_line("Выберите колонку.", muted=True)
            self.b_apply.setEnabled(False)
            return

        try:
            rx = _re.compile(pattern)
        except _re.error as e:
            self._add_line(f"⚠ {e}", muted=True, color="#e74c3c")
            self.b_apply.setEnabled(False)
            return

        series = self.data.dataframe[col]
        total = len(series)
        ok_count = 0
        any_ok = False
        shown_ok = 0
        shown_err = 0

        for i, v in enumerate(series):
            was = "" if v is None else str(v)
            short = was if len(was) <= 80 else was[:77] + "..."
            try:
                m = rx.search(was)
                if m is None:
                    result = None
                elif m.lastindex:
                    result = m.group(1)
                else:
                    result = m.group(0)
            except Exception:
                result = None

            if result:
                any_ok = True
                ok_count += 1
                if shown_ok < PREVIEW_ROWS:
                    self._add_line(f"✓  {short}   →   {result}",
                                   color=self.theme.primary)
                    shown_ok += 1
            else:
                if shown_err < PREVIEW_ROWS:
                    self._add_line(f"⚠  {short}   →   (не найдено)",
                                   muted=True, color="#e74c3c")
                    shown_err += 1

        if total > PREVIEW_ROWS:
            self._add_line(f"…  всего {total} строк", muted=True)

        self._add_line(
            f"Покрыто: {ok_count} из {total}",
            color=self.theme.primary if ok_count == total else None,
            muted=(ok_count != total),
        )
        self.b_apply.setEnabled(any_ok)

    def _add_line(self, text: str, muted: bool = False, color: str | None = None):
        it = QListWidgetItem(text)
        if color:
            it.setForeground(QColor(color))
        elif muted:
            it.setForeground(QColor(self.theme.text_muted))
        self.preview_list.addItem(it)

    # ============================================================
    # Применение
    # ============================================================

    def _on_apply(self):
        pattern = self._current_pattern()
        ok, err = validate_pattern(pattern)
        if not ok:
            ToastManager.warning("Ошибка шаблона", err, self.theme)
            return
        if self._selected_column is None:
            ToastManager.warning("Не выбрана колонка",
                                 "Выберите колонку для обработки", self.theme)
            return
        self.result_data = {
            "columns": [self._selected_column],
            "pattern": pattern,
        }
        self.accept()

    # ============================================================
    # Стили
    # ============================================================

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text.upper())
        lbl.setStyleSheet(
            f"color:{self.theme.text_muted}; font-size:10px; font-weight:700;"
            f"letter-spacing:0.5px; padding-top:6px;"
        )
        return lbl

    def _tabs_qss(self) -> str:
        t = self.theme
        return f"""
            QTabWidget::pane {{
                border: 1px solid {t.border};
                border-radius: 6px;
                background: {t.bg_panel};
                top: -1px;
            }}
            QTabBar {{ background: transparent; qproperty-drawBase: 0; }}
            QTabBar::tab {{
                background: transparent;
                color: {t.text_muted};
                border: none;
                padding: 8px 16px;
                margin: 4px 4px 0 0;
                font-size: 12px;
                font-weight: 600;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
            }}
            QTabBar::tab:hover:!selected {{
                background: {t.bg_hover};
                color: {t.text_main};
            }}
            QTabBar::tab:selected {{
                background: {t.bg_panel};
                color: {t.text_main};
                border: 1px solid {t.border};
                border-bottom: 1px solid {t.bg_panel};
            }}
        """

    def _preview_qss(self) -> str:
        return f"""
            QListWidget {{
                background: {self.theme.bg_panel};
                border: 1px solid {self.theme.border};
                border-radius: 6px;
                color: {self.theme.text_main};
                font-size: 12px;
                padding: 4px;
                outline: none;
                font-family: 'Consolas', monospace;
            }}
            QListWidget::item {{
                padding: 4px 8px;
                border-bottom: 1px solid {self.theme.border};
            }}
        """

    def _input_qss(self) -> str:
        return f"""
            QLineEdit {{
                background: {self.theme.bg_panel};
                border: 1px solid {self.theme.border};
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 12px;
                color: {self.theme.text_main};
                font-family: 'Consolas', monospace;
            }}
            QLineEdit:focus {{ border: 1px solid {self.theme.primary}; }}
        """

    def _combo_qss(self) -> str:
        return f"""
            QComboBox {{
                background: {self.theme.bg_panel};
                color: {self.theme.text_main};
                border: 1px solid {self.theme.border};
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 12px;
            }}
            QComboBox:hover {{ border: 1px solid {self.theme.primary}; }}
            QComboBox QAbstractItemView {{
                background: {self.theme.bg_card};
                color: {self.theme.text_main};
                border: 1px solid {self.theme.border};
                selection-background-color: {self.theme.primary_hover};
                selection-color: {self.theme.text_main};
                padding: 4px;
                font-size: 12px;
            }}
        """

    def _btn_small(self) -> str:
        return f"""
            QPushButton {{
                background: {self.theme.bg_panel};
                color: {self.theme.text_main};
                border: 1px solid {self.theme.border};
                border-radius: 4px;
                padding: 4px 14px;
                font-size: 12px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background: {self.theme.primary_hover};
                border-color: {self.theme.primary};
            }}
            QPushButton:disabled {{ color: {self.theme.text_muted}; }}
        """

    def _btn_primary(self) -> str:
        return f"""
            QPushButton {{
                background: {self.theme.primary};
                color: {self.theme.text_inverse};
                border: none;
                padding: 8px 22px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background: #6ea800; }}
            QPushButton:disabled {{
                background: {self.theme.bg_panel};
                color: {self.theme.text_muted};
            }}
        """

    def _btn_secondary(self) -> str:
        return f"""
            QPushButton {{
                background: transparent;
                color: {self.theme.text_main};
                border: 1px solid {self.theme.border};
                padding: 8px 22px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background: {self.theme.primary_hover};
                border-color: {self.theme.primary};
            }}
        """