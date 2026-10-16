"""
Диалог разделения колонки.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QRadioButton, QCheckBox, QPushButton,
    QButtonGroup, QWidget, QGridLayout,
    QListWidget, QListWidgetItem, QTableWidget, QTableWidgetItem, QHeaderView
)
from PySide6.QtCore import Qt, QTimer

from src.ui.toast import ToastManager
from src.ui.visual_split_widget import VisualSplitWidget
from src.core.rule_detector import RuleDetector, SplitRule


SEPARATOR_PRESETS = [
    (", ", "Запятая + пробел"),
    (",",  "Запятая"),
    ("; ", "Точка с запятой + пробел"),
    (";",  "Точка с запятой"),
    (" | ", "Вертикальная черта с пробелами"),
    ("|",  "Вертикальная черта"),
    ("\t", "Табуляция"),
    (" - ", "Дефис с пробелами"),
    (" ",  "Пробел"),
]


class SplitDialog(QDialog):
    """Диалог разделения колонки."""

    def _on_example_text_edited(self, text: str):
        self._schedule_preview()

    def __init__(self, data, column_name: str, theme, parent=None):
        super().__init__(parent)
        
        self.data = data
        self.column_name = column_name
        self.theme = theme
        
        self.result_data = None
        self._detected_rules: list[SplitRule] = []
        self.name_edits: list[QLineEdit] = []
        
        self.setWindowTitle(f"Разделить колонку: {column_name}")
        self.setMinimumWidth(760)
        self.setMinimumHeight(880)
        self.setStyleSheet(f"QDialog {{ background: {self.theme.bg_card}; }}")
        
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(300)
        self._preview_timer.timeout.connect(self._update_preview)
        
        self._build_ui()
        self._auto_detect_separator()
        self._update_preview()
    
    # ============================================================
    # Стили
    # ============================================================
    
    def _label_style(self, muted=False) -> str:
        color = self.theme.text_muted if muted else self.theme.text_main
        size = 11 if muted else 12
        return f"""
            color: {color};
            font-size: {size}px;
            background: transparent;
            border: none;
            padding: 0;
        """
    
    def _section_label_style(self) -> str:
        return f"""
            color: {self.theme.text_muted};
            font-size: 10px;
            font-weight: bold;
            letter-spacing: 0.5px;
            background: transparent;
            border: none;
            padding: 0;
        """
    
    def _input_style(self) -> str:
        return f"""
            QLineEdit {{
                background: {self.theme.bg_panel};
                border: 1px solid {self.theme.border};
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 12px;
                color: {self.theme.text_main};
            }}
            QLineEdit:focus {{
                border: 1px solid {self.theme.primary};
            }}
        """
    
    def _radio_style(self) -> str:
        return f"""
            QRadioButton {{
                color: {self.theme.text_main};
                font-size: 12px;
                padding: 3px 0;
                spacing: 6px;
                background: transparent;
                border: none;
            }}
        """
    
    def _checkbox_style(self) -> str:
        return f"""
            QCheckBox {{
                color: {self.theme.text_main};
                font-size: 12px;
                padding: 3px 0;
                spacing: 6px;
                background: transparent;
                border: none;
            }}
        """
    
    def _button_primary_style(self) -> str:
        return f"""
            QPushButton {{
                background: {self.theme.primary};
                color: {self.theme.text_inverse};
                border: none;
                padding: 8px 18px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background: #6ea800; }}
        """
    
    def _button_secondary_style(self) -> str:
        return f"""
            QPushButton {{
                background: transparent;
                color: {self.theme.text_main};
                border: 1px solid {self.theme.border};
                padding: 8px 18px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background: {self.theme.primary_hover};
                border-color: {self.theme.primary};
            }}
        """
    
    def _make_label(self, text: str, muted: bool = False) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(self._label_style(muted))
        return lbl
    
    def _make_panel(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent; border: none;")
        return w
    
    # ============================================================
    # Заполнение разнообразных примеров
    # ============================================================
    
    def _populate_diverse_examples(self):
        try:
            self.table_examples.blockSignals(True)
            self.table_examples.setRowCount(0)
            
            if self.column_name in self.data.dataframe.columns:
                series = self.data.dataframe[self.column_name].dropna()
                diverse = RuleDetector.get_diverse_examples(series, max_count=5)
                
                if not diverse:
                    diverse = [str(series.iloc[0])] if len(series) > 0 else [""]
                
                self.table_examples.setRowCount(len(diverse))
                for row, item_text in enumerate(diverse):
                    text_str = str(item_text)
                    self.table_examples.setRowHeight(row, 30)
                    
                    # Колонка 0: Исходный текст (только для чтения)
                    item_src = QTableWidgetItem(text_str)
                    item_src.setFlags(item_src.flags() & ~Qt.ItemIsEditable)
                    self.table_examples.setItem(row, 0, item_src)
                    
                    # Колонка 1: Полноценное поле ввода QLineEdit с исходной строкой внутри
                    line_edit = QLineEdit(text_str)
                    line_edit.setProperty("original_text", text_str)
                    line_edit.setStyleSheet(f"""
                        QLineEdit {{
                            background: {self.theme.bg_panel};
                            color: {self.theme.text_main};
                            border: 1px solid transparent;
                            padding: 2px 6px;
                            font-size: 11px;
                        }}
                        QLineEdit:focus {{
                            background: {self.theme.bg_card};
                            border: 1px solid {self.theme.primary};
                        }}
                    """)
                    line_edit.textEdited.connect(self._on_example_text_edited)
                    self.table_examples.setCellWidget(row, 1, line_edit)
        except Exception as e:
            print(f"[SplitDialog] Ошибка заполнения примеров: {e}")
        finally:
            self.table_examples.blockSignals(False)

    # ============================================================
    # UI
    # ============================================================
    
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)
        
        # ЗАГОЛОВОК
        title = QLabel(f"✂️  Разделить колонку «{self.column_name}»")
        title.setStyleSheet(f"""
            color: {self.theme.primary};
            font-size: 15px;
            font-weight: bold;
            padding-bottom: 6px;
            border: none;
            border-bottom: 1px solid {self.theme.border};
            background: transparent;
        """)
        layout.addWidget(title)
        
        # ПРИМЕР ЗНАЧЕНИЯ
        example_label = QLabel("Пример значения:")
        example_label.setStyleSheet(self._section_label_style())
        layout.addWidget(example_label)
        
        example_text = ""
        if self.column_name in self.data.columns:
            series = self.data.dataframe[self.column_name].dropna()
            if len(series) > 0:
                example_text = str(series.iloc[0])
        
        self.example_text = example_text
        
        example_box = QLabel(example_text)
        example_box.setWordWrap(True)
        example_box.setTextInteractionFlags(Qt.TextSelectableByMouse)
        example_box.setStyleSheet(f"""
            background: {self.theme.bg_panel};
            border: 1px solid {self.theme.border};
            border-radius: 4px;
            padding: 10px 12px;
            font-family: 'Consolas', monospace;
            font-size: 12px;
            color: {self.theme.text_main};
        """)
        layout.addWidget(example_box)
        
        # РЕЖИМЫ
        modes_label = QLabel("Режим разделения:")
        modes_label.setStyleSheet(self._section_label_style())
        layout.addWidget(modes_label)
        
        self.mode_group = QButtonGroup(self)
        
        # === Визуальный режим ===
        self.radio_visual = QRadioButton("Визуально (кликните в строку, чтобы поставить маяк)")
        self.radio_visual.setStyleSheet(self._radio_style())
        self.mode_group.addButton(self.radio_visual, 0)
        layout.addWidget(self.radio_visual)
        
        self.visual_panel = self._make_panel()
        visual_layout = QVBoxLayout(self.visual_panel)
        visual_layout.setContentsMargins(0, 6, 0, 6)
        visual_layout.setSpacing(8)
        
        self.visual_widget = VisualSplitWidget(self.example_text, self.theme)
        self.visual_widget.markers_changed.connect(self._on_markers_changed)
        visual_layout.addWidget(self.visual_widget)
        
        self.rules_label = QLabel("")
        self.rules_label.setStyleSheet(f"""
            color: {self.theme.text_muted};
            font-size: 11px;
            background: transparent;
            border: none;
            padding: 0;
        """)
        self.rules_label.setMinimumHeight(16)
        self.rules_label.setVisible(False)
        visual_layout.addWidget(self.rules_label)
        
        self.rules_list = QListWidget()
        self.rules_list.setFixedHeight(0)
        self.rules_list.setStyleSheet(f"""
            QListWidget {{
                background: transparent;
                border: none;
                font-size: 12px;
                color: {self.theme.text_main};
                padding: 0;
                outline: none;
            }}
            QListWidget::item {{
                padding: 2px 0;
                background: transparent;
                border: none;
            }}
        """)
        self.rules_list.setVisible(False)
        visual_layout.addWidget(self.rules_list)
        
        self.accuracy_warning = QLabel("")
        self.accuracy_warning.setStyleSheet(f"""
            color: #f39c12;
            font-size: 11px;
            background: transparent;
            border: none;
            padding: 0;
        """)
        self.accuracy_warning.setWordWrap(True)
        self.accuracy_warning.setVisible(False)
        visual_layout.addWidget(self.accuracy_warning)
        
        self.visual_panel.setVisible(False)
        layout.addWidget(self.visual_panel)
        
        # === По метке ===
        self.radio_marker = QRadioButton("1.  По метке (ключевому слову)")
        self.radio_marker.setStyleSheet(self._radio_style())
        self.mode_group.addButton(self.radio_marker, 1)
        layout.addWidget(self.radio_marker)
        
        self.marker_panel = self._make_panel()
        marker_layout = QGridLayout(self.marker_panel)
        marker_layout.setContentsMargins(0, 6, 0, 6)
        marker_layout.setSpacing(8)
        marker_layout.setVerticalSpacing(6)
        
        marker_layout.addWidget(self._make_label("Метка:"), 0, 0)
        self.edit_marker = QLineEdit()
        self.edit_marker.setPlaceholderText("Например: Гос")
        self.edit_marker.setStyleSheet(self._input_style())
        self.edit_marker.textChanged.connect(self._schedule_preview)
        marker_layout.addWidget(self.edit_marker, 0, 1, 1, 2)
        
        marker_layout.addWidget(self._make_label("Позиция:"), 1, 0)
        
        position_row = QWidget()
        position_row.setStyleSheet("background: transparent; border: none;")
        position_row_layout = QHBoxLayout(position_row)
        position_row_layout.setContentsMargins(0, 0, 0, 0)
        position_row_layout.setSpacing(12)
        
        self.radio_before = QRadioButton("Перед меткой")
        self.radio_before.setChecked(True)
        self.radio_before.setStyleSheet(self._radio_style())
        self.radio_before.toggled.connect(self._schedule_preview)
        position_row_layout.addWidget(self.radio_before)
        
        self.radio_after = QRadioButton("После метки")
        self.radio_after.setStyleSheet(self._radio_style())
        self.radio_after.toggled.connect(self._schedule_preview)
        position_row_layout.addWidget(self.radio_after)
        
        position_row_layout.addStretch()
        marker_layout.addWidget(position_row, 1, 1, 1, 2)
        
        marker_layout.setColumnStretch(1, 1)
        marker_layout.setColumnStretch(2, 1)
        
        self.marker_panel.setVisible(False)
        layout.addWidget(self.marker_panel)
        
        # === По позиции ===
        self.radio_position = QRadioButton("2.  По позиции (в символах)")
        self.radio_position.setStyleSheet(self._radio_style())
        self.mode_group.addButton(self.radio_position, 2)
        layout.addWidget(self.radio_position)
        
        self.position_panel = self._make_panel()
        pos_layout = QHBoxLayout(self.position_panel)
        pos_layout.setContentsMargins(0, 6, 0, 6)
        pos_layout.setSpacing(8)
        pos_layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        
        pos_layout.addWidget(self._make_label("Разделить после"))
        
        self.spin_position = QLineEdit()
        self.spin_position.setPlaceholderText("25")
        self.spin_position.setFixedWidth(80)
        self.spin_position.setStyleSheet(self._input_style())
        self.spin_position.textChanged.connect(self._schedule_preview)
        pos_layout.addWidget(self.spin_position)
        
        pos_layout.addWidget(self._make_label("символов"))
        pos_layout.addStretch()
        
        self.position_panel.setVisible(False)
        layout.addWidget(self.position_panel)

        # === По примеру (Flash Fill / Интерактивный ввод) ===
        self.radio_example = QRadioButton("4.  По примеру (Flash Fill / Интерактивный ввод)")
        self.radio_example.setStyleSheet(self._radio_style())
        self.mode_group.addButton(self.radio_example, 4)
        layout.addWidget(self.radio_example)
        
        self.example_panel = self._make_panel()
        example_layout = QVBoxLayout(self.example_panel)
        example_layout.setContentsMargins(0, 6, 0, 6)
        example_layout.setSpacing(6)
        
        example_layout.addWidget(self._make_label("Отредактируйте желаемый результат для примеров (кликните в правый столбец и сотрите лишнее):"))
        
        self.table_examples = QTableWidget(0, 2)
        self.table_examples.setMinimumHeight(130)
        self.table_examples.setHorizontalHeaderLabels(["Исходный текст", "Желаемый результат"])
        self.table_examples.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table_examples.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table_examples.verticalHeader().setVisible(False)
        self.table_examples.setSelectionMode(QTableWidget.NoSelection)
        self.table_examples.setStyleSheet(f"""
            QTableWidget {{
                background: {self.theme.bg_panel};
                border: 1px solid {self.theme.border};
                border-radius: 4px;
                font-size: 11px;
                color: {self.theme.text_main};
                gridline-color: {self.theme.border};
            }}
            QHeaderView::section {{
                background: {self.theme.bg_card};
                color: {self.theme.primary};
                padding: 4px;
                border: none;
                border-bottom: 1px solid {self.theme.border};
                font-weight: bold;
            }}
        """)
        
        example_layout.addWidget(self.table_examples)
        
        self.example_panel.setVisible(False)
        layout.addWidget(self.example_panel)

        # === По разделителю ===
        self.radio_separator = QRadioButton("3.  По разделителю")
        self.radio_separator.setChecked(True)
        self.radio_separator.setStyleSheet(self._radio_style())
        self.mode_group.addButton(self.radio_separator, 3)
        layout.addWidget(self.radio_separator)
        
        self.separator_panel = self._make_panel()
        sep_layout = QVBoxLayout(self.separator_panel)
        sep_layout.setContentsMargins(0, 6, 0, 6)
        sep_layout.setSpacing(6)
        
        self.separator_group = QButtonGroup(self)
        
        presets_widget = QWidget()
        presets_widget.setStyleSheet("background: transparent; border: none;")
        presets_grid = QGridLayout(presets_widget)
        presets_grid.setContentsMargins(0, 0, 0, 0)
        presets_grid.setHorizontalSpacing(16)
        presets_grid.setVerticalSpacing(4)
        
        for i, (sep_value, sep_title) in enumerate(SEPARATOR_PRESETS):
            rb = QRadioButton(sep_title)
            rb.setStyleSheet(self._radio_style())
            rb.toggled.connect(self._schedule_preview)
            self.separator_group.addButton(rb, i)
            row = i // 3
            col = i % 3
            presets_grid.addWidget(rb, row, col)
            if i == 0:
                rb.setChecked(True)
        
        sep_layout.addWidget(presets_widget)
        
        custom_row = QWidget()
        custom_row.setStyleSheet("background: transparent; border: none;")
        custom_layout = QHBoxLayout(custom_row)
        custom_layout.setContentsMargins(0, 0, 0, 0)
        custom_layout.setSpacing(8)
        
        self.radio_custom = QRadioButton("Свой:")
        self.radio_custom.setStyleSheet(self._radio_style())
        self.radio_custom.toggled.connect(self._schedule_preview)
        self.separator_group.addButton(self.radio_custom, len(SEPARATOR_PRESETS))
        custom_layout.addWidget(self.radio_custom)
        
        self.edit_custom_sep = QLineEdit()
        self.edit_custom_sep.setPlaceholderText("Символ или строка")
        self.edit_custom_sep.setStyleSheet(self._input_style())
        self.edit_custom_sep.textChanged.connect(self._schedule_preview)
        custom_layout.addWidget(self.edit_custom_sep, 1)
        
        sep_layout.addWidget(custom_row)
        
        occurrence_row = QWidget()
        occurrence_row.setStyleSheet("background: transparent; border: none;")
        occurrence_layout = QHBoxLayout(occurrence_row)
        occurrence_layout.setContentsMargins(0, 4, 0, 0)
        occurrence_layout.setSpacing(16)
        
        occ_label = QLabel("Где резать:")
        occ_label.setStyleSheet(self._label_style(muted=True))
        occurrence_layout.addWidget(occ_label)
        
        self.occurrence_group = QButtonGroup(self)
        
        self.radio_occ_first = QRadioButton("По первому вхождению")
        self.radio_occ_first.setChecked(True)
        self.radio_occ_first.setStyleSheet(self._radio_style())
        self.radio_occ_first.toggled.connect(self._schedule_preview)
        self.occurrence_group.addButton(self.radio_occ_first, 0)
        occurrence_layout.addWidget(self.radio_occ_first)
        
        self.radio_occ_last = QRadioButton("По последнему")
        self.radio_occ_last.setStyleSheet(self._radio_style())
        self.radio_occ_last.toggled.connect(self._schedule_preview)
        self.occurrence_group.addButton(self.radio_occ_last, 1)
        occurrence_layout.addWidget(self.radio_occ_last)
        
        self.radio_occ_all = QRadioButton("По всем вхождениям")
        self.radio_occ_all.setStyleSheet(self._radio_style())
        self.radio_occ_all.toggled.connect(self._schedule_preview)
        self.occurrence_group.addButton(self.radio_occ_all, 2)
        occurrence_layout.addWidget(self.radio_occ_all)
        
        occurrence_layout.addStretch()
        sep_layout.addWidget(occurrence_row)
        
        layout.addWidget(self.separator_panel)
        
        self.mode_group.buttonClicked.connect(self._on_mode_changed)
        
        # ДОПОЛНИТЕЛЬНО
        options_label = QLabel("Дополнительно:")
        options_label.setStyleSheet(self._section_label_style())
        layout.addWidget(options_label)
        
        self.check_keep_spaces = QCheckBox("Сохранять пробелы как есть")
        self.check_keep_spaces.setStyleSheet(self._checkbox_style())
        self.check_keep_spaces.toggled.connect(self._schedule_preview)
        layout.addWidget(self.check_keep_spaces)
        
        self.check_delete_original = QCheckBox("Удалить исходную колонку")
        self.check_delete_original.setStyleSheet(self._checkbox_style())
        layout.addWidget(self.check_delete_original)
        
        # ПРЕДПРОСМОТР
        preview_label = QLabel("Предпросмотр (первые 5 строк):")
        preview_label.setStyleSheet(self._section_label_style())
        layout.addWidget(preview_label)
        
        self.headers_widget = QWidget()
        self.headers_widget.setStyleSheet("background: transparent; border: none;")
        self.headers_layout = QHBoxLayout(self.headers_widget)
        self.headers_layout.setContentsMargins(0, 0, 0, 0)
        self.headers_layout.setSpacing(0)
        layout.addWidget(self.headers_widget)
        
        self.previews_widget = QWidget()
        self.previews_widget.setFixedHeight(130)
        self.previews_widget.setStyleSheet(f"""
            background: {self.theme.bg_panel};
            border: 1px solid {self.theme.border};
            border-top: none;
            border-bottom-left-radius: 4px;
            border-bottom-right-radius: 4px;
        """)
        self.previews_layout = QHBoxLayout(self.previews_widget)
        self.previews_layout.setContentsMargins(0, 0, 0, 0)
        self.previews_layout.setSpacing(0)
        
        self.preview_left = QListWidget()
        self.preview_left.setStyleSheet(f"""
            QListWidget {{
                background: transparent;
                border: none;
                border-right: 1px solid {self.theme.border};
                font-size: 12px;
                color: {self.theme.text_main};
                padding: 4px;
                outline: none;
            }}
            QListWidget::item {{
                padding: 4px 8px;
                border-bottom: 1px solid {self.theme.border};
                background: transparent;
            }}
        """)
        self.preview_left.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.preview_left.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.previews_layout.addWidget(self.preview_left, 1)
        
        self.preview_right = QListWidget()
        self.preview_right.setStyleSheet(f"""
            QListWidget {{
                background: transparent;
                border: none;
                font-size: 12px;
                color: {self.theme.text_main};
                padding: 4px;
                outline: none;
            }}
            QListWidget::item {{
                padding: 4px 8px;
                border-bottom: 1px solid {self.theme.border};
                background: transparent;
            }}
        """)
        self.preview_right.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.preview_right.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.previews_layout.addWidget(self.preview_right, 1)
        
        layout.addWidget(self.previews_widget)
        
        # ИМЕНА КОЛОНОК
        self.names_label = QLabel("Имена новых колонок:")
        self.names_label.setStyleSheet(self._section_label_style())
        layout.addWidget(self.names_label)
        
        self.names_container = QWidget()
        self.names_container.setStyleSheet("background: transparent; border: none;")
        self.names_layout = QHBoxLayout(self.names_container)
        self.names_layout.setContentsMargins(0, 0, 0, 0)
        self.names_layout.setSpacing(8)
        layout.addWidget(self.names_container)
        
        self._rebuild_name_fields(2)
        
        # КНОПКИ
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(8)
        buttons_layout.addStretch()
        
        self.btn_cancel = QPushButton("Отмена")
        self.btn_cancel.setAutoDefault(False)
        self.btn_cancel.setDefault(False)
        self.btn_cancel.setStyleSheet(self._button_secondary_style())
        self.btn_cancel.clicked.connect(self.reject)
        buttons_layout.addWidget(self.btn_cancel)
        
        self.btn_split = QPushButton("✂️  Разделить")
        self.btn_split.setDefault(True)
        self.btn_split.setAutoDefault(True)
        self.btn_split.setStyleSheet(self._button_primary_style())
        self.btn_split.clicked.connect(self._on_split)
        buttons_layout.addWidget(self.btn_split)
        
        layout.addLayout(buttons_layout)
        
        self.radio_visual.setChecked(True)
        self._on_mode_changed(self.radio_visual)
        self._populate_diverse_examples()
    
    # ============================================================
    # Логика
    # ============================================================
    
    def _on_mode_changed(self, button):
        mode_id = self.mode_group.id(button)
        
        self.visual_panel.setVisible(mode_id == 0)
        self.marker_panel.setVisible(mode_id == 1)
        self.position_panel.setVisible(mode_id == 2)
        self.separator_panel.setVisible(mode_id == 3)
        self.example_panel.setVisible(mode_id == 4)
        
        if mode_id == 0:
            n = len(self._detected_rules) + 1 if self._detected_rules else 2
            self._rebuild_name_fields(n)
        else:
            self._rebuild_name_fields(2)
        
        self._schedule_preview()
    
    def _schedule_preview(self):
        self._preview_timer.start()
    
    def _get_current_mode(self) -> str:
        mode_id = self.mode_group.checkedId()
        if mode_id == 0:
            return "visual"
        elif mode_id == 1:
            return "marker"
        elif mode_id == 2:
            return "position"
        elif mode_id == 3:
            return "separator"
        else:
            return "example"

    def _get_current_params(self) -> dict:
        mode = self._get_current_mode()
        keep_spaces = self.check_keep_spaces.isChecked()
        
        if mode == "visual":
            return {"markers": self.visual_widget.get_markers(), "separator": "", "marker": "", "position": 0}
        elif mode == "marker":
            return {
                "marker": self.edit_marker.text(),
                "before": self.radio_before.isChecked(),
                "keep_spaces": keep_spaces,
                "separator": "",
                "position": 0,
            }
        elif mode == "position":
            text = self.spin_position.text().strip()
            try:
                position = int(text) if text else 0
            except ValueError:
                position = 0
            return {"position": position, "keep_spaces": keep_spaces, "separator": "", "marker": ""}
        elif mode == "example":
            edited_pairs = []
            all_pairs = []
            
            for r in range(self.table_examples.rowCount()):
                src_item = self.table_examples.item(r, 0)
                line_edit = self.table_examples.cellWidget(r, 1)
                if src_item and isinstance(line_edit, QLineEdit):
                    full_text = src_item.text()
                    part_text = line_edit.text()
                    if full_text and part_text:
                        all_pairs.append((full_text, part_text))
                        if full_text.strip() != part_text.strip():
                            edited_pairs.append((full_text, part_text))
            
            series = self.data.dataframe[self.column_name].dropna().head(100)
            rule = None
            
            if hasattr(RuleDetector, "detect_from_examples") and edited_pairs:
                rule = RuleDetector.detect_from_examples(edited_pairs, series)
            elif edited_pairs:
                best_rule = None
                best_score = -1.0
                for sample_full, sample_part in edited_pairs:
                    candidate = RuleDetector.detect_from_example(sample_full, sample_part, series)
                    if candidate:
                        match_user = 0
                        for f_txt, p_txt in edited_pairs:
                            pos = RuleDetector._find_split_position(candidate, f_txt)
                            if pos is not None:
                                left = f_txt[:pos].strip().rstrip(",;:|").strip()
                                right = f_txt[pos:].strip().lstrip(",;:|").strip()
                                p_clean = p_txt.strip().strip(",;:|").strip()
                                if left == p_clean or right == p_clean:
                                    match_user += 1
                        score = (match_user / len(edited_pairs)) * 0.7 + candidate.accuracy * 0.3
                        if score > best_score:
                            best_score = score
                            best_rule = candidate
                rule = best_rule
            
            sample_text = edited_pairs[0][0] if edited_pairs else (all_pairs[0][0] if all_pairs else self.example_text)
            return {
                "rule": rule,
                "sample": sample_text,
                "keep_spaces": keep_spaces,
                "separator": "",
                "marker": "",
                "position": 0,
            }
        else:
            if self.radio_custom.isChecked():
                sep = self.edit_custom_sep.text()
            else:
                sep_id = self.separator_group.checkedId()
                if 0 <= sep_id < len(SEPARATOR_PRESETS):
                    sep = SEPARATOR_PRESETS[sep_id][0]
                else:
                    sep = ", "
            
            occ_id = self.occurrence_group.checkedId()
            occurrence = "first" if occ_id == 0 else ("last" if occ_id == 1 else "all")
            
            return {
                "separator": sep,
                "occurrence": occurrence,
                "keep_spaces": keep_spaces,
                "marker": "",
                "position": 0,
            }
    
    def _rebuild_name_fields(self, count: int):
        old_values = [e.text() for e in self.name_edits]
        
        while self.names_layout.count():
            item = self.names_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.name_edits = []
        
        for i in range(count):
            edit = QLineEdit()
            edit.setPlaceholderText(f"{self.column_name}_{i+1}")
            edit.setStyleSheet(self._input_style())
            if i < len(old_values) and old_values[i]:
                edit.setText(old_values[i])
            self.names_layout.addWidget(edit)
            self.name_edits.append(edit)
    
    def _on_markers_changed(self, markers: list):
        if not markers:
            self.rules_label.setVisible(False)
            self.rules_label.setText("")
            self.rules_list.setVisible(False)
            self.rules_list.setFixedHeight(0)
            self.accuracy_warning.setVisible(False)
            self._detected_rules = []
            self._rebuild_name_fields(2)
            self._schedule_preview()
            return
        
        series = self.data.dataframe[self.column_name].dropna().head(50)
        self._detected_rules = []
        
        for pos in markers:
            rules = RuleDetector.detect_rules(
                self.example_text, pos, series, max_rules=3,
            )
            if rules:
                self._detected_rules.append(rules[0])
        
        self._update_rules_display()
        self._rebuild_name_fields(len(self._detected_rules) + 1)
        self._schedule_preview()
    
    def _update_rules_display(self):
        if not self._detected_rules:
            self.rules_label.setText("🎯 Не удалось определить правило")
            self.rules_label.setVisible(True)
            self.rules_list.setVisible(False)
            self.rules_list.setFixedHeight(0)
            self.accuracy_warning.setVisible(False)
            return
        
        self.rules_label.setText(f"🎯 Определено правил: {len(self._detected_rules)}")
        self.rules_label.setVisible(True)
        self.rules_list.clear()
        
        min_accuracy = 1.0
        for rule in self._detected_rules:
            min_accuracy = min(min_accuracy, rule.accuracy)
            icon = "✅" if rule.accuracy >= 0.95 else "⚠️" if rule.accuracy >= 0.5 else "❌"
            text = f"{icon}  {rule.describe()}  —  {rule.accuracy:.0%} ({rule.success_count}/{rule.total_count})"
            self.rules_list.addItem(QListWidgetItem(text))
        
        h = 22 * len(self._detected_rules) + 8
        self.rules_list.setFixedHeight(min(100, h))
        self.rules_list.setVisible(True)
        
        if min_accuracy < 0.5:
            self.accuracy_warning.setText("⚠️ Точность правила ниже 50%. Результат может быть неточным.")
            self.accuracy_warning.setVisible(True)
        elif min_accuracy < 0.9:
            self.accuracy_warning.setText("⚠️ Точность 50-90%. Некоторые строки могут разделиться неточно.")
            self.accuracy_warning.setVisible(True)
        else:
            self.accuracy_warning.setVisible(False)
    
    def _update_preview(self):
        self.preview_left.clear()
        self.preview_right.clear()
        
        mode = self._get_current_mode()
        
        if mode == "visual":
            self._update_visual_preview()
            return
        
        params = self._get_current_params()
        
        if mode == "example":
            rule = params.get("rule")
            if not rule:
                self._show_preview_empty("Отредактируйте хотя бы один пример в таблице выше (сотрите лишнюю часть строки)")
                self._set_preview_headers(2)
                return
            
            series = self.data.dataframe[self.column_name].dropna().head(5)
            self._set_preview_headers(2)
            for value in series:
                s = str(value)
                pos = RuleDetector._find_split_position(rule, s)
                if pos is not None and 0 < pos < len(s):
                    if params.get("keep_spaces"):
                        p1, p2 = s[:pos], s[pos:]
                    else:
                        p1 = s[:pos].strip().rstrip(",;:|").strip()
                        p2 = s[pos:].strip().lstrip(",;:|").strip()
                else:
                    p1, p2 = s.strip(), ""
                self.preview_left.addItem(QListWidgetItem(p1 or "—"))
                self.preview_right.addItem(QListWidgetItem(p2 or "—"))
            return
        
        if mode == "marker" and not params["marker"]:
            self._show_preview_empty("Введите метку для разделения")
            self._set_preview_headers(2)
            return
        
        if mode == "position" and params["position"] <= 0:
            self._show_preview_empty("Введите позицию (> 0)")
            self._set_preview_headers(2)
            return
        
        if mode == "separator" and not params["separator"]:
            self._show_preview_empty("Введите разделитель")
            self._set_preview_headers(2)
            return
        
        rows = self.data.preview_split(self.column_name, mode, params, n=5)
        
        if not rows:
            self._show_preview_empty("Не удалось построить предпросмотр")
            self._set_preview_headers(2)
            return
        
        for part_1, part_2 in rows:
            self.preview_left.addItem(QListWidgetItem(part_1 or "—"))
            self.preview_right.addItem(QListWidgetItem(part_2 or "—"))
        
        self._set_preview_headers(2)
    
    def _update_visual_preview(self):
        markers = self.visual_widget.get_markers()
        
        if not markers or not self._detected_rules:
            self._show_preview_empty("Поставьте маяки в примере строки")
            self._set_preview_headers(2)
            return
        
        series = self.data.dataframe[self.column_name].dropna().head(5)
        n_parts = len(self._detected_rules) + 1
        self._set_preview_headers(n_parts)
        
        for value in series:
            s = str(value)
            positions = []
            for rule in self._detected_rules:
                pos = RuleDetector._find_split_position(rule, s)
                if pos is not None and 0 < pos < len(s):
                    positions.append(pos)
            
            positions = sorted(set(positions))
            
            if not positions:
                parts = [s.strip()] + [""] * (n_parts - 1)
            else:
                parts = []
                prev = 0
                for pos in positions:
                    parts.append(s[prev:pos].strip())
                    prev = pos
                parts.append(s[prev:].strip())
                while len(parts) < n_parts:
                    parts.append("")
                parts = parts[:n_parts]
            
            self.preview_left.addItem(QListWidgetItem(parts[0] or "—"))
            rest = " | ".join(p or "—" for p in parts[1:])
            self.preview_right.addItem(QListWidgetItem(rest))
    
    def _set_preview_headers(self, n_cols: int):
        while self.headers_layout.count():
            item = self.headers_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        
        if n_cols <= 2:
            headers = ["ЧАСТЬ 1", "ЧАСТЬ 2"]
        else:
            headers = ["ЧАСТЬ 1", f"ЧАСТИ 2-{n_cols}"]
        
        for i, text in enumerate(headers):
            lbl = QLabel(text)
            lbl.setAlignment(Qt.AlignCenter)
            style = f"""
                background: {self.theme.bg_panel};
                color: {self.theme.primary};
                font-weight: bold;
                font-size: 11px;
                padding: 6px;
                border: none;
                border-bottom: 1px solid {self.theme.border};
            """
            if i == 0:
                style += "border-top-left-radius: 4px;"
            if i == len(headers) - 1:
                style += "border-top-right-radius: 4px;"
            lbl.setStyleSheet(style)
            self.headers_layout.addWidget(lbl, 1)
    
    def _show_preview_empty(self, message: str):
        self.preview_left.clear()
        self.preview_right.clear()
        self.preview_left.addItem(message)
    
    def _auto_detect_separator(self):
        if self.column_name not in self.data.columns:
            return
        
        series = self.data.dataframe[self.column_name].dropna().head(20)
        candidates = [", ", ",", "; ", ";", " | ", "|", "\t", " - ", " "]
        
        best_sep = None
        best_count = 0
        
        for sep in candidates:
            count = sum(1 for v in series if sep in str(v))
            if count > best_count:
                best_count = count
                best_sep = sep
        
        if best_sep and best_count >= len(series) * 0.7:
            for i, (sep_value, _) in enumerate(SEPARATOR_PRESETS):
                if sep_value == best_sep:
                    button = self.separator_group.button(i)
                    if button:
                        button.setChecked(True)
                    break
    
    def _on_split(self):
        mode = self._get_current_mode()
        params = self._get_current_params()
        
        if mode == "visual":
            if not params["markers"]:
                ToastManager.warning("Маяки не установлены", "Поставьте маяки в примере строки", self.theme)
                return
            if not self._detected_rules:
                ToastManager.warning("Правило не определено", "Не удалось определить правило", self.theme)
                return
        elif mode == "example":
            if not params.get("rule"):
                ToastManager.warning("Правило не определено", "Отредактируйте хотя бы один пример в таблице (сотрите лишнюю часть)", self.theme)
                return
        
        names = []
        for edit in self.name_edits:
            val = edit.text().strip() or edit.placeholderText()
            if not val:
                ToastManager.warning("Заполните имена", "Все новые столбцы должны иметь имя", self.theme)
                return
            names.append(val)
        
        if len(names) < 2:
            ToastManager.warning("Нужно минимум 2 колонки", "Для разделения нужно 2+ колонки", self.theme)
            return
        
        if mode == "visual":
            self.result_data = {
                "mode": "visual",
                "rules": self._detected_rules,
                "new_names": names,
                "delete_original": self.check_delete_original.isChecked(),
            }
        elif mode == "example":
            rule = params.get("rule")
            self.result_data = {
                "mode": "visual",
                "rules": [rule] if rule else [],
                "new_names": names,
                "delete_original": self.check_delete_original.isChecked(),
            }
        else:
            self.result_data = {
                "mode": mode,
                "params": params,
                "new_names": names[:2],
                "delete_original": self.check_delete_original.isChecked(),
            }
        
        self.accept()
    def _populate_diverse_examples(self):
        try:
            self.table_examples.blockSignals(True)
            self.table_examples.setRowCount(0)
            
            if self.column_name in self.data.dataframe.columns:
                series = self.data.dataframe[self.column_name].dropna()
                diverse = RuleDetector.get_diverse_examples(series, max_count=5)
                
                if not diverse:
                    diverse = [str(series.iloc[0])] if len(series) > 0 else [""]
                
                self.table_examples.setRowCount(len(diverse))
                for row, item_text in enumerate(diverse):
                    text_str = str(item_text)
                    self.table_examples.setRowHeight(row, 30)
                    
                    # Колонка 0: Исходный текст (только для чтения)
                    item_src = QTableWidgetItem(text_str)
                    item_src.setFlags(item_src.flags() & ~Qt.ItemIsEditable)
                    self.table_examples.setItem(row, 0, item_src)
                    
                    # Колонка 1: Полноценное поле ввода QLineEdit с исходной строкой внутри
                    line_edit = QLineEdit(text_str)
                    line_edit.setProperty("original_text", text_str)
                    line_edit.setStyleSheet(f"""
                        QLineEdit {{
                            background: {self.theme.bg_panel};
                            color: {self.theme.text_main};
                            border: 1px solid transparent;
                            padding: 2px 6px;
                            font-size: 11px;
                        }}
                        QLineEdit:focus {{
                            background: {self.theme.bg_card};
                            border: 1px solid {self.theme.primary};
                        }}
                    """)
                    line_edit.textEdited.connect(self._on_example_text_edited)
                    self.table_examples.setCellWidget(row, 1, line_edit)
        except Exception as e:
            print(f"[SplitDialog] Ошибка заполнения примеров: {e}")
        finally:
            self.table_examples.blockSignals(False)