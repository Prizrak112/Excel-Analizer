"""
Правая панель «Данные».
Современный вид: карточки, крупная статистика, единый стиль.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QListWidget, QListWidgetItem, QScrollArea
)
from PySide6.QtCore import Qt, Signal


class DataPanel(QWidget):
    """Панель операций над данными."""

    # Сигналы наружу
    sort_reset_requested = Signal()
    filter_remove_requested = Signal(str)   # column_name (real)
    filters_reset_requested = Signal()
    drop_duplicates_requested = Signal()
    drop_na_requested = Signal()
    normalize_text_requested = Signal()
    extract_text_requested = Signal()

    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.theme = theme

        self._build_ui()
        self.update_state(sort_state=[], filters=[], total=0, shown=0)

    # ============================================================
    # UI
    # ============================================================

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            QScrollArea > QWidget > QWidget {{
                background: transparent;
            }}
        """)

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        # ═══════════════════════════════════════════════════════════
        # СТАТИСТИКА — крупная цифра
        # ═══════════════════════════════════════════════════════════
        stats_card = QFrame()
        stats_card.setObjectName("stats_card")
        stats_card.setStyleSheet(f"""
            #stats_card {{
                background: {self.theme.bg_panel};
                border: 1px solid {self.theme.border};
                border-radius: 10px;
            }}
        """)
        sc_layout = QVBoxLayout(stats_card)
        sc_layout.setContentsMargins(16, 14, 16, 14)
        sc_layout.setSpacing(6)

        stats_title = QLabel("СТРОК В ТАБЛИЦЕ")
        stats_title.setStyleSheet(f"""
            color: {self.theme.text_muted};
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 1px;
            background: transparent;
        """)
        sc_layout.addWidget(stats_title)

        self.label_stats_value = QLabel("—")
        self.label_stats_value.setStyleSheet(f"""
            color: {self.theme.text_main};
            font-size: 30px;
            font-weight: 700;
            background: transparent;
        """)
        sc_layout.addWidget(self.label_stats_value)

        self.label_stats_sub = QLabel("Файл не загружен")
        self.label_stats_sub.setStyleSheet(f"""
            color: {self.theme.text_muted};
            font-size: 12px;
            background: transparent;
        """)
        sc_layout.addWidget(self.label_stats_sub)

        layout.addWidget(stats_card)

        # ═══════════════════════════════════════════════════════════
        # СОРТИРОВКА
        # ═══════════════════════════════════════════════════════════
        layout.addWidget(self._make_section("СОРТИРОВКА"))

        self.sort_card = QFrame()
        self.sort_card.setObjectName("sort_card")
        sort_card_layout = QVBoxLayout(self.sort_card)
        sort_card_layout.setContentsMargins(14, 12, 14, 12)
        sort_card_layout.setSpacing(4)

        self.label_sort = QLabel("Не активна")
        self.label_sort.setWordWrap(True)
        self.label_sort.setStyleSheet(f"""
            color: {self.theme.text_muted};
            font-size: 13px;
            background: transparent;
        """)
        sort_card_layout.addWidget(self.label_sort)

        layout.addWidget(self.sort_card)
        self._style_sort_card(active=False)

        self.btn_clear_sort = QPushButton("Сбросить сортировку")
        self.btn_clear_sort.setCursor(Qt.PointingHandCursor)
        self.btn_clear_sort.clicked.connect(self.sort_reset_requested.emit)
        self.btn_clear_sort.setStyleSheet(self._btn_secondary_style())
        layout.addWidget(self.btn_clear_sort)

        # ═══════════════════════════════════════════════════════════
        # ФИЛЬТРЫ
        # ═══════════════════════════════════════════════════════════
        layout.addWidget(self._make_section("АКТИВНЫЕ ФИЛЬТРЫ"))

        self.filters_list = QListWidget()
        self.filters_list.setMinimumHeight(70)
        self.filters_list.setMaximumHeight(220)
        self.filters_list.setStyleSheet(f"""
            QListWidget {{
                background: {self.theme.bg_panel};
                border: 1px solid {self.theme.border};
                border-radius: 10px;
                color: {self.theme.text_main};
                outline: none;
                padding: 4px;
                font-size: 13px;
            }}
            QListWidget::item {{
                padding: 10px 12px;
                border-radius: 6px;
                color: {self.theme.text_main};
                margin: 2px 0;
                font-size: 13px;
            }}
            QListWidget::item:hover {{
                background: {self.theme.bg_hover};
            }}
        """)
        self.filters_list.itemDoubleClicked.connect(self._on_filter_double_click)
        layout.addWidget(self.filters_list)

        self.label_filters_empty = QLabel("Нет активных фильтров")
        self.label_filters_empty.setAlignment(Qt.AlignCenter)
        self.label_filters_empty.setStyleSheet(f"""
            color: {self.theme.text_muted};
            font-size: 12px;
            padding: 18px 14px;
            background: {self.theme.bg_panel};
            border: 1px dashed {self.theme.border};
            border-radius: 10px;
        """)
        layout.addWidget(self.label_filters_empty)

        self.btn_clear_filters = QPushButton("Сбросить все фильтры")
        self.btn_clear_filters.setCursor(Qt.PointingHandCursor)
        self.btn_clear_filters.clicked.connect(self.filters_reset_requested.emit)
        self.btn_clear_filters.setStyleSheet(self._btn_secondary_style())
        layout.addWidget(self.btn_clear_filters)

        # ═══════════════════════════════════════════════════════════
        # ОЧИСТКА
        # ═══════════════════════════════════════════════════════════
        layout.addWidget(self._make_section("ОЧИСТКА ДАННЫХ"))

        self.btn_duplicates = QPushButton("🗑   Удалить дубликаты…")
        self.btn_duplicates.setCursor(Qt.PointingHandCursor)
        self.btn_duplicates.clicked.connect(self.drop_duplicates_requested.emit)
        self.btn_duplicates.setStyleSheet(self._btn_action_style())
        layout.addWidget(self.btn_duplicates)

        self.btn_drop_na = QPushButton("🧹   Удалить строки с пустыми…")
        self.btn_drop_na.setCursor(Qt.PointingHandCursor)
        self.btn_drop_na.clicked.connect(self.drop_na_requested.emit)
        self.btn_drop_na.setStyleSheet(self._btn_action_style())
        layout.addWidget(self.btn_drop_na)

        # ★ Нормализация текста (гос-номера, замена латиницы↔кириллицы и т.д.)
        self.btn_normalize_text = QPushButton("🔤   Нормализовать текст…")
        self.btn_normalize_text.setCursor(Qt.PointingHandCursor)
        self.btn_normalize_text.clicked.connect(self.normalize_text_requested.emit)
        self.btn_normalize_text.setStyleSheet(self._btn_action_style())
        layout.addWidget(self.btn_normalize_text)

        # ★ Извлечение по шаблону (regex) — гос. номер, VIN и т.д.
        self.btn_extract_text = QPushButton("✂   Извлечь по шаблону…")
        self.btn_extract_text.setCursor(Qt.PointingHandCursor)
        self.btn_extract_text.clicked.connect(self.extract_text_requested.emit)
        self.btn_extract_text.setStyleSheet(self._btn_action_style())
        layout.addWidget(self.btn_extract_text)

        layout.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll)

    # ============================================================
    # Утилиты стилей
    # ============================================================

    def _make_section(self, title: str) -> QLabel:
        lbl = QLabel(title)
        lbl.setStyleSheet(f"""
            color: {self.theme.text_muted};
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 1px;
            padding: 4px 2px 2px 2px;
            background: transparent;
        """)
        return lbl

    def _style_sort_card(self, active: bool):
        if active:
            self.sort_card.setStyleSheet(f"""
                #sort_card {{
                    background: {self.theme.primary_hover};
                    border: 1px solid {self.theme.primary};
                    border-radius: 10px;
                }}
            """)
            self.label_sort.setStyleSheet(f"""
                color: {self.theme.primary};
                font-size: 13px;
                font-weight: 600;
                background: transparent;
            """)
        else:
            self.sort_card.setStyleSheet(f"""
                #sort_card {{
                    background: {self.theme.bg_panel};
                    border: 1px dashed {self.theme.border};
                    border-radius: 10px;
                }}
            """)
            self.label_sort.setStyleSheet(f"""
                color: {self.theme.text_muted};
                font-size: 13px;
                background: transparent;
            """)

    def _btn_secondary_style(self) -> str:
        return f"""
            QPushButton {{
                background: {self.theme.bg_panel};
                color: {self.theme.text_main};
                border: 1px solid {self.theme.border};
                padding: 11px 14px;
                border-radius: 9px;
                font-size: 13px;
                font-weight: 500;
                text-align: left;
            }}
            QPushButton:hover {{
                background: {self.theme.bg_hover};
                border: 1px solid {self.theme.text_muted};
            }}
            QPushButton:disabled {{
                background: {self.theme.bg_panel};
                color: {self.theme.text_muted};
                border: 1px solid {self.theme.border};
            }}
        """

    def _btn_action_style(self) -> str:
        """Кнопка-действие в зелёном корпоративном стиле (тема primary)."""
        return f"""
            QPushButton {{
                background: {self.theme.bg_panel};
                color: {self.theme.primary};
                border: 1px solid {self.theme.primary};
                padding: 11px 14px;
                border-radius: 9px;
                font-size: 13px;
                font-weight: 500;
                text-align: left;
            }}
            QPushButton:hover {{
                background: {self.theme.primary_hover};
                border: 1px solid {self.theme.primary};
            }}
            QPushButton:pressed {{
                background: {self.theme.primary_hover};
            }}
        """

    # ============================================================
    # Публичный API
    # ============================================================

    def update_state(self, sort_state: list, filters: list,
                     total: int, shown: int):
        """
        sort_state: [(real, display, asc), ...]
        filters:    [(real, display, [values]), ...]
        """
        # ── СТАТИСТИКА ──
        if total == 0:
            self.label_stats_value.setText("—")
            self.label_stats_sub.setText("Файл не загружен")
            self.label_stats_value.setStyleSheet(f"""
                color: {self.theme.text_muted};
                font-size: 30px;
                font-weight: 700;
                background: transparent;
            """)
        else:
            if shown != total:
                self.label_stats_value.setText(f"{shown:,}")
                self.label_stats_value.setStyleSheet(f"""
                    color: {self.theme.primary};
                    font-size: 30px;
                    font-weight: 700;
                    background: transparent;
                """)
                self.label_stats_sub.setText(f"из {total:,} — активны фильтры")
            else:
                self.label_stats_value.setText(f"{total:,}")
                self.label_stats_value.setStyleSheet(f"""
                    color: {self.theme.text_main};
                    font-size: 30px;
                    font-weight: 700;
                    background: transparent;
                """)
                self.label_stats_sub.setText("Показаны все строки")

        # ── СОРТИРОВКА ──
        if not sort_state:
            self.label_sort.setText("Не активна")
            self._style_sort_card(active=False)
            self.btn_clear_sort.setEnabled(False)
        else:
            parts = []
            multi = len(sort_state) > 1
            for i, item in enumerate(sort_state, 1):
                if len(item) == 3:
                    real, display, asc = item
                else:
                    real, asc = item
                    display = real
                arrow = "▲" if asc else "▼"
                if multi:
                    parts.append(f"{i}.  {display}  {arrow}")
                else:
                    parts.append(f"{display}  {arrow}")

            self.label_sort.setText("\n".join(parts))
            self._style_sort_card(active=True)
            self.btn_clear_sort.setEnabled(True)

        # ── ФИЛЬТРЫ ──
        self.filters_list.clear()

        if not filters:
            self.filters_list.setVisible(False)
            self.label_filters_empty.setVisible(True)
            self.btn_clear_filters.setEnabled(False)
        else:
            self.filters_list.setVisible(True)
            self.label_filters_empty.setVisible(False)
            self.btn_clear_filters.setEnabled(True)

            for item in filters:
                if len(item) == 3:
                    real, display, values = item
                else:
                    real, display, values = item[0], item[0], item[1]

                if values:
                    text = f"🔎   {display}   ·   {len(values)}"
                else:
                    text = f"🔎   {display}   ·   все"

                it = QListWidgetItem(text)
                it.setData(Qt.UserRole, real)
                preview = values[:20] if values else []
                it.setToolTip(
                    f"Значения: {preview}{'...' if len(values) > 20 else ''}\n"
                    f"Двойной клик — снять"
                )
                self.filters_list.addItem(it)

    # ============================================================
    # Обработчики
    # ============================================================

    def _on_filter_double_click(self, item: QListWidgetItem):
        col_name = item.data(Qt.UserRole)
        if col_name:
            self.filter_remove_requested.emit(col_name)