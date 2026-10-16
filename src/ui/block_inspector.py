"""Панель свойств блока (правая панель Конструктора)."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit,
    QSpinBox, QCheckBox, QScrollArea, QFrame, QComboBox, QPushButton,
    QSlider, QColorDialog,
)
from PySide6.QtCore import Qt, Signal

from src.core.block_factory import BLOCK_TYPES


_CHART_TYPES = [
    ("📊 Столбчатая диаграмма (Bar)", "bar"),
    ("📈 Горизонтальная (H-Bar)", "hbar"),
    ("📉 Линейный график (Line)", "line"),
    ("⛰ Площадной график (Area)", "area"),
    ("🔵 Точечная диаграмма (Scatter)", "scatter"),
    ("🥧 Круговая диаграмма (Pie)", "pie"),
    ("🍩 Кольцевая диаграмма (Donut)", "donut"),
    ("📶 Гистограмма распределения", "histogram"),
    ("📦 Ящик с усами (Boxplot)", "box"),
    ("🌪 Воронка (Funnel)", "funnel"),
]

_AGG_FUNCS = [
    ("Сумма значений (SUM)", "sum"),
    ("Среднее значение (AVG)", "mean"),
    ("Количество записей (COUNT)", "count"),
    ("Медиана (MEDIAN)", "median"),
    ("Минимум (MIN)", "min"),
    ("Максимум (MAX)", "max"),
]

_SORT_MODES = [
    ("По убыванию значения", "value_desc"),
    ("По возрастанию значения", "value_asc"),
    ("По алфавиту (Ось X)", "label_asc"),
    ("Без сортировки (как в таблице)", "none"),
]

_LEGEND_POS = [
    ("Справа от графика", "right"),
    ("Сверху над графиком", "top"),
    ("Снизу под графиком", "bottom"),
]

_PALETTES = [
    ("Корпоративная (Синий / Зелёный)", "corporate"),
    ("Изумрудная (Emerald)", "emerald"),
    ("Закат (Sunset Контраст)", "sunset"),
    ("Пастельная мягкая", "pastel"),
]

_BG_PRESETS = [
    ("Чистый белый (#FFFFFF)", "#ffffff"),
    ("Светло-серый (#F8FAFC)", "#f8fafc"),
    ("Мягкий зелёный (#F2F9EB)", "#f2f9eb"),
    ("Мягкий голубой (#EFF6FF)", "#eff6ff"),
    ("Тёмный графит (#1E293B)", "#1e293b"),
]


class BlockInspector(QWidget):
    """Интерактивная панель свойств блока с мгновенной синхронизацией ширины,
    позиции в пространстве и полным конфигуратором графиков."""

    config_changed = Signal(str)
    unmerge_requested = Signal(str)

    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self._block = None
        self._section = None
        self._all_columns: list[str] = []

        # Ссылки на живые контролы геометрии (чтобы обновлять их без пересборки при тяге мышью)
        self._width_spin: QSpinBox | None = None
        self._width_slider: QSlider | None = None
        self._height_spin: QSpinBox | None = None
        self._offset_spin: QSpinBox | None = None

        self.setStyleSheet(f"background:{theme.bg_card};")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setStyleSheet(f"QScrollArea {{ background:{theme.bg_card}; border:none; }}")

        self._body = QWidget()
        self._body.setStyleSheet(f"background:{theme.bg_card};")
        self._lay = QVBoxLayout(self._body)
        self._lay.setContentsMargins(12, 12, 12, 12)
        self._lay.setSpacing(6)
        self._lay.addStretch()

        self._scroll.setWidget(self._body)
        outer.addWidget(self._scroll)

        self.show_empty()

    def set_dataframe(self, df):
        self._all_columns = list(df.columns) if df is not None else []

    def sync_live_geometry(self, block_id: str, width_pct: int, min_height_px: int):
        """Мгновенно обновляет значение «Ширина блока (%)» и «Мин.В» при растягивании блока на холсте."""
        if self._block is None or getattr(self._block, "id", None) != block_id:
            return
        if self._width_spin is not None:
            self._width_spin.blockSignals(True)
            self._width_spin.setValue(width_pct)
            self._width_spin.blockSignals(False)
        if self._width_slider is not None:
            self._width_slider.blockSignals(True)
            self._width_slider.setValue(width_pct)
            self._width_slider.blockSignals(False)
        if self._height_spin is not None:
            self._height_spin.blockSignals(True)
            self._height_spin.setValue(min_height_px)
            self._height_spin.blockSignals(False)
        if self._offset_spin is not None:
            max_off = max(0, 100 - width_pct)
            self._offset_spin.setMaximum(max_off)

    def show_empty(self):
        self._clear()
        self._add_title("Свойства")
        self._add_hint("Выберите блок на холсте или в дереве для настройки.")
        self._block = None
        self._section = None

    def show_block(self, block):
        self._block = block
        self._section = None
        self._clear()

        b_name = BLOCK_TYPES.get(block.type, block.type)
        self._add_title(f"⚡ {b_name}")
        cfg = block.config or {}

        # ── Секция ГЕОМЕТРИЯ И ПОЛОЖЕНИЕ НА СТРАНИЦЕ ──
        if block.type != "divider":
            self._section_header("Геометрия и положение на листе")
            self._field_width(cfg)
            self._field_alignment_and_offset(cfg)

            row_geo = QHBoxLayout()
            row_geo.setSpacing(4)
            self._height_spin = self._field_spin_inline(
                "Мин.В (px)", "min_height", cfg, 0, 0, 2000, parent_layout=row_geo, tooltip="Минимальная высота (px)"
            )
            self._field_spin_inline(
                "Отступ Т", "margin_top", cfg, 0, 0, 200, parent_layout=row_geo, tooltip="Отступ сверху (px)"
            )
            self._field_spin_inline(
                "Отступ Б", "margin_bottom", cfg, 14, 0, 200, parent_layout=row_geo, tooltip="Отступ снизу (px)"
            )
            self._lay.insertWidget(self._lay.count() - 1, self._wrap_row(row_geo))

        # ── Специфичные настройки по типам блоков ──
        if block.type in ("section_title", "paragraph", "list"):
            self._add_hint("💡 Двойной клик на блоке или ПКМ открывает редактор текста.")

        elif block.type == "kpi_row":
            self._section_header("Карточки KPI")
            self._field_kpi(cfg)

        elif block.type == "plotly_chart":
            self._build_chart_settings(cfg)

        elif block.type == "data_table":
            self._section_header("Параметры таблицы")
            self._field_int(
                "Видимых строк в окне", "max_rows", cfg, default=20, min_val=0, max_val=10000,
                tooltip="0 — во всю высоту без прокрутки внутри блока.",
            )
            self._section_header("Колонки")
            self._field_columns(cfg)

        elif block.type == "container":
            self._section_header("Расположение графиков / блоков в группе")
            self._field_container_layout(cfg)

            row_cnt = QHBoxLayout()
            row_cnt.setSpacing(4)
            self._field_spin_inline("Отступ между блоками (px)", "gap", cfg, 14, 0, 100, parent_layout=row_cnt)
            self._lay.insertWidget(self._lay.count() - 1, self._wrap_row(row_cnt))

            children = cfg.get("children", [])
            self._add_hint(f"📦 Вложенных элементов: {len(children)} (перетащите блок на другой блок, чтобы объединить)")

            self._section_header("Действия")
            btn = QPushButton("💥 Разъединить блоки по отдельности")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(
                f"background:{self.theme.bg_panel}; color:{self.theme.text_main};"
                f"border:1px solid {self.theme.border}; border-radius:4px; padding:6px 10px; font-size:11px;"
            )
            btn.clicked.connect(lambda _, b_id=block.id: self.unmerge_requested.emit(b_id))
            self._lay.insertWidget(self._lay.count() - 1, btn)

        elif block.type == "divider":
            self._add_hint("У этого блока нет настроек.")

    # ── Полный конфигуратор графиков ──
    def _build_chart_settings(self, cfg: dict):
        self._section_header("1. Тип и заголовок графика")
        self._field_text("Заголовок графика", "title", cfg, placeholder="Например: Динамика продаж")
        self._field_combo("Тип визуализации", "chart_type", cfg, _CHART_TYPES, "bar")
        self._section_header("3. Легенда, Подложка и Стиль")
        self._field_combo("Цветовая палитра", "palette", cfg, _PALETTES, "corporate")
        self._field_background_picker(cfg)
        self._field_combo("Позиция легенды", "legend_pos", cfg, _LEGEND_POS, "right")

        self._field_checkbox("Показывать легенду", "show_legend", cfg, True)
        self._field_checkbox("Показывать подписи значений", "show_values", cfg, True)
        self._field_checkbox("Показывать координатную сетку", "show_grid", cfg, True)
        self._field_checkbox("Показывать заголовок графика", "show_title", cfg, True)
        self._field_checkbox("Показывать подписи осей (X/Y)", "show_axis_labels", cfg, True)

        self._section_header("2. Данные: Столбцы и Строки")
        self._field_axis_selectors(cfg)
        self._field_combo("Функция расчёта (Агрегация)", "agg", cfg, _AGG_FUNCS, "sum")
        self._field_combo("Сортировка данных", "sort_by", cfg, _SORT_MODES, "value_desc")

        row_slice = QHBoxLayout()
        row_slice.setSpacing(4)
        self._field_spin_inline(
            "Топ Категорий", "top_n", cfg, 12, 0, 500, parent_layout=row_slice,
            tooltip="Сколько категорий показать на графике (0 — все)"
        )
        self._field_spin_inline(
            "С какой строки", "row_start", cfg, 0, 0, 100000, parent_layout=row_slice,
            tooltip="Начальная строка таблицы для фильтрации"
        )
        self._field_spin_inline(
            "Лимит строк", "row_limit", cfg, 0, 0, 100000, parent_layout=row_slice,
            tooltip="Сколько строк брать из таблицы (0 — все строки)"
        )
        self._lay.insertWidget(self._lay.count() - 1, self._wrap_row(row_slice))

        self._section_header("3. Легенда, Подложка и Стиль")
        self._field_combo("Цветовая палитра", "palette", cfg, _PALETTES, "corporate")
        self._field_background_picker(cfg)
        self._field_combo("Позиция легенды", "legend_pos", cfg, _LEGEND_POS, "right")

        self._field_checkbox("Показывать легенду", "show_legend", cfg, True)
        self._field_checkbox("Показывать подписи значений", "show_values", cfg, True)
        self._field_checkbox("Показывать координатную сетку", "show_grid", cfg, True)

    def _field_text(self, label: str, key: str, cfg: dict, placeholder: str = ""):
        self._add_label(label)
        e = QLineEdit(str(cfg.get(key, "")))
        if placeholder:
            e.setPlaceholderText(placeholder)
        self._style_input(e)
        e.textChanged.connect(lambda v: self._change_block(key, v))
        self._lay.insertWidget(self._lay.count() - 1, e)

    def _field_combo(self, label: str, key: str, cfg: dict, items: list[tuple[str, str]], default_val: str):
        self._add_label(label)
        cb = QComboBox()
        for title, val in items:
            cb.addItem(title, val)
        cur = cfg.get(key, default_val)
        idx = cb.findData(cur)
        cb.setCurrentIndex(idx if idx >= 0 else 0)
        self._style_input(cb)
        cb.currentIndexChanged.connect(lambda i: self._change_block(key, cb.itemData(i)))
        self._lay.insertWidget(self._lay.count() - 1, cb)

    def _field_checkbox(self, label: str, key: str, cfg: dict, default_val: bool):
        cb = QCheckBox(label)
        cb.setChecked(bool(cfg.get(key, default_val)))
        cb.setStyleSheet(
            f"QCheckBox {{ color:{self.theme.text_main}; font-size:11px; padding:2px 0; background:transparent; }}"
        )
        cb.toggled.connect(lambda v: self._change_block(key, v))
        self._lay.insertWidget(self._lay.count() - 1, cb)

    def _field_background_picker(self, cfg: dict):
        self._add_label("Цвет подложки (фон карточки графика)")
        row = QHBoxLayout()
        row.setSpacing(4)

        cb = QComboBox()
        for title, hex_v in _BG_PRESETS:
            cb.addItem(title, hex_v)
        cur_bg = cfg.get("bg_color", "#ffffff")
        idx = cb.findData(cur_bg)
        if idx < 0:
            cb.addItem(f"Свой цвет ({cur_bg})", cur_bg)
            idx = cb.count() - 1
        cb.setCurrentIndex(idx)
        self._style_input(cb)
        cb.currentIndexChanged.connect(lambda i: self._change_block("bg_color", cb.itemData(i)))
        row.addWidget(cb, 1)

        btn_color = QPushButton("🎨")
        btn_color.setFixedWidth(32)
        btn_color.setToolTip("Выбрать произвольный цвет подложки")
        self._style_input(btn_color)

        def pick_color():
            c = QColorDialog.getColor()
            if c.isValid():
                hex_c = c.name()
                self._change_block("bg_color", hex_c)
                if self._block:
                    self.show_block(self._block)

        btn_color.clicked.connect(pick_color)
        row.addWidget(btn_color)
        self._lay.insertWidget(self._lay.count() - 1, self._wrap_row(row))

    def _field_axis_selectors(self, cfg):
        if not self._all_columns:
            self._add_hint("Сначала загрузите Excel-файл для выбора столбцов.")
            return

        self._add_label("Ось X (Категории / Группировка)")
        cb_x = QComboBox()
        cb_x.addItem("— Авто (первый столбец) —", "")
        for col in self._all_columns:
            cb_x.addItem(str(col), str(col))
        cur_x = cfg.get("x_col", "")
        idx_x = cb_x.findData(cur_x)
        cb_x.setCurrentIndex(idx_x if idx_x >= 0 else 0)
        self._style_input(cb_x)
        cb_x.currentIndexChanged.connect(lambda i: self._change_block("x_col", cb_x.itemData(i)))
        self._lay.insertWidget(self._lay.count() - 1, cb_x)

        self._add_label("Ось Y (Числовой столбец для расчёта)")
        cb_y = QComboBox()
        cb_y.addItem("— Количество строк (COUNT) —", "")
        for col in self._all_columns:
            cb_y.addItem(str(col), str(col))
        cur_y = cfg.get("y_col", "")
        idx_y = cb_y.findData(cur_y)
        cb_y.setCurrentIndex(idx_y if idx_y >= 0 else 0)
        self._style_input(cb_y)
        cb_y.currentIndexChanged.connect(lambda i: self._change_block("y_col", cb_y.itemData(i)))
        self._lay.insertWidget(self._lay.count() - 1, cb_y)

    # ── Ширина (15%..100%) и Позиция на странице (Лево / Центр / Право / Сдвиг X) ──
    def _field_width(self, cfg):
        self._add_label("Ширина блока на странице (макс. 100%)")
        current = max(15, min(100, int(cfg.get("width", 100))))

        row = QHBoxLayout()
        row.setSpacing(6)

        slider = QSlider(Qt.Horizontal)
        slider.setRange(15, 100)
        slider.setValue(current)
        self._width_slider = slider

        sp = QSpinBox()
        sp.setRange(15, 100)
        sp.setSuffix("%")
        sp.setValue(current)
        sp.setFixedWidth(68)
        self._style_input(sp)
        self._width_spin = sp

        def on_width_val(val: int):
            val = max(15, min(100, int(val)))
            slider.blockSignals(True)
            sp.blockSignals(True)
            slider.setValue(val)
            sp.setValue(val)
            slider.blockSignals(False)
            sp.blockSignals(False)
            if self._offset_spin is not None:
                self._offset_spin.setMaximum(max(0, 100 - val))
            self._change_block("width", val)

        slider.valueChanged.connect(on_width_val)
        sp.valueChanged.connect(on_width_val)

        row.addWidget(slider, 1)
        row.addWidget(sp)
        self._lay.insertWidget(self._lay.count() - 1, self._wrap_row(row))

        # Кнопки быстрых пресетов ширины
        presets_row = QHBoxLayout()
        presets_row.setSpacing(4)
        for p_val in (25, 33, 50, 66, 75, 100):
            b = QPushButton(f"{p_val}%")
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(
                f"QPushButton {{ background:{self.theme.bg_panel}; color:{self.theme.text_main}; "
                f"border:1px solid {self.theme.border}; border-radius:3px; padding:2px 4px; font-size:10px; }}"
                f"QPushButton:hover {{ border-color:{self.theme.primary}; }}"
            )
            b.clicked.connect(lambda _, v=p_val: on_width_val(v))
            presets_row.addWidget(b)
        self._lay.insertWidget(self._lay.count() - 1, self._wrap_row(presets_row))

    def _field_alignment_and_offset(self, cfg):
        self._add_label("Положение блока в пространстве страницы")
        row = QHBoxLayout()
        row.setSpacing(4)

        cb_align = QComboBox()
        cb_align.addItem("⬅ По левому краю", "left")
        cb_align.addItem("↔ По центру страницы", "center")
        cb_align.addItem("➡ По правому краю", "right")
        cb_align.addItem("🎯 Свободный сдвиг X (%)", "custom")

        cur_align = cfg.get("align", "left")
        idx = cb_align.findData(cur_align)
        cb_align.setCurrentIndex(idx if idx >= 0 else 0)
        self._style_input(cb_align)
        row.addWidget(cb_align, 2)

        w_pct = max(15, min(100, int(cfg.get("width", 100))))
        sp_off = QSpinBox()
        sp_off.setRange(0, max(0, 100 - w_pct))
        sp_off.setSuffix("% X")
        sp_off.setValue(int(cfg.get("offset_x", 0)))
        sp_off.setToolTip("Горизонтальное смещение слева в процентах ширины листа")
        self._style_input(sp_off)
        self._offset_spin = sp_off
        row.addWidget(sp_off, 1)

        def on_align_changed(i):
            mode = cb_align.itemData(i)
            self._change_block("align", mode)

        def on_offset_changed(val):
            if cb_align.currentData() != "custom" and val > 0:
                cb_align.blockSignals(True)
                cb_align.setCurrentIndex(3)
                cb_align.blockSignals(False)
                if self._block:
                    self._block.config["align"] = "custom"
            self._change_block("offset_x", val)

        cb_align.currentIndexChanged.connect(on_align_changed)
        sp_off.valueChanged.connect(on_offset_changed)

        self._lay.insertWidget(self._lay.count() - 1, self._wrap_row(row))

    def show_section(self, section):
        self._section = section
        self._block = None
        self._clear()
        self._add_title("📂 Раздел отчёта")

        row = QHBoxLayout()
        row.setSpacing(4)

        w_title = QWidget()
        l_t = QVBoxLayout(w_title)
        l_t.setContentsMargins(0, 0, 0, 0)
        l_t.setSpacing(2)
        lbl1 = QLabel("Название")
        lbl1.setStyleSheet(f"color:{self.theme.text_muted}; font-size:10px; background:transparent;")
        e1 = QLineEdit(section.title)
        self._style_input(e1)
        e1.textChanged.connect(lambda v: self._change_section("title", v))
        l_t.addWidget(lbl1)
        l_t.addWidget(e1)
        row.addWidget(w_title, stretch=4)

        w_icon = QWidget()
        l_i = QVBoxLayout(w_icon)
        l_i.setContentsMargins(0, 0, 0, 0)
        l_i.setSpacing(2)
        lbl2 = QLabel("Иконка")
        lbl2.setStyleSheet(f"color:{self.theme.text_muted}; font-size:10px; background:transparent;")
        e2 = QLineEdit(section.icon)
        e2.setMaxLength(2)
        self._style_input(e2)
        e2.textChanged.connect(lambda v: self._change_section("icon", v))
        l_i.addWidget(lbl2)
        l_i.addWidget(e2)
        row.addWidget(w_icon, stretch=1)

        self._lay.insertWidget(self._lay.count() - 1, self._wrap_row(row))

    def _change_block(self, key, value):
        if self._block is None:
            return
        cfg = dict(self._block.config or {})
        cfg[key] = value
        self._block.config = cfg
        self.config_changed.emit(self._block.id)

    def _change_section(self, key, value):
        if self._section is None:
            return
        setattr(self._section, key, value)
        self.config_changed.emit("")

    def _section_header(self, text):
        lbl = QLabel(text.upper())
        lbl.setStyleSheet(
            f"color:{self.theme.primary}; font-size:9px; font-weight:700;"
            f"letter-spacing:0.5px; padding-top:6px; padding-bottom:1px;"
            f"background:transparent;"
        )
        self._lay.insertWidget(self._lay.count() - 1, lbl)

    def _clear(self):
        self._width_spin = None
        self._width_slider = None
        self._height_spin = None
        self._offset_spin = None
        while self._lay.count() > 1:
            it = self._lay.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()

    def _add_title(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color:{self.theme.text_main}; font-size:13px; font-weight:700;"
            f"padding-bottom:2px; background:transparent;"
        )
        self._lay.insertWidget(self._lay.count() - 1, lbl)

    def _add_hint(self, text):
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color:{self.theme.text_muted}; font-size:11px; background:transparent; line-height:1.4;")
        self._lay.insertWidget(self._lay.count() - 1, lbl)

    def _add_label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color:{self.theme.text_muted}; font-size:10px; font-weight:600;"
            f"padding-top:2px; background:transparent;"
        )
        self._lay.insertWidget(self._lay.count() - 1, lbl)

    def _wrap_row(self, h_layout):
        w = QWidget()
        w.setLayout(h_layout)
        w.setStyleSheet("background:transparent;")
        h_layout.setContentsMargins(0, 0, 0, 0)
        return w

    def _field_spin_inline(self, label, key, cfg, default, min_v, max_v, parent_layout, tooltip="") -> QSpinBox:
        w = QWidget()
        w.setStyleSheet("background:transparent;")
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(2)

        lbl = QLabel(label)
        lbl.setStyleSheet(f"color:{self.theme.text_muted}; font-size:9px; background:transparent;")
        l.addWidget(lbl)

        sp = QSpinBox()
        sp.setRange(min_v, max_v)
        sp.setValue(int(cfg.get(key, default)))
        if tooltip:
            sp.setToolTip(tooltip)
        self._style_input(sp)
        sp.valueChanged.connect(lambda v: self._change_block(key, v))
        l.addWidget(sp)

        parent_layout.addWidget(w)
        return sp

    def _field_int(self, label, key, cfg, default=20, min_val=0, max_val=5000, tooltip=""):
        self._add_label(label)
        sp = QSpinBox()
        sp.setRange(min_val, max_val)
        sp.setValue(int(cfg.get(key, default)))
        if tooltip:
            sp.setToolTip(tooltip)
        self._style_input(sp)
        sp.valueChanged.connect(lambda v: self._change_block(key, v))
        self._lay.insertWidget(self._lay.count() - 1, sp)

    def _field_container_layout(self, cfg):
        self._add_label("Как расположить блоки внутри группы")
        cb = QComboBox()
        cb.addItem("↔ Рядом друг с другом (В одну строку)", "row")
        cb.addItem("↕ Друг под другом (Вертикальной колонкой)", "column")
        current = cfg.get("layout", "row")
        cb.setCurrentIndex(0 if current == "row" else 1)
        self._style_input(cb)
        cb.currentIndexChanged.connect(
            lambda i: self._change_block("layout", "row" if i == 0 else "column")
        )
        self._lay.insertWidget(self._lay.count() - 1, cb)

    def _field_kpi(self, cfg):
        self._add_label("Метка [TAB] Значение  ·  «!» — акцент")
        cards = cfg.get("cards") or []
        text = "\n".join(
            f"{c.get('label','')}\t{c.get('value','')}{'  !' if c.get('accent') else ''}"
            for c in cards
        )
        e = QTextEdit()
        e.setPlainText(text)
        e.setFixedHeight(90)
        e.setPlaceholderText("Выручка\t1 000 000  !\nКлиентов\t42")
        self._style_input(e)

        def on_ch():
            new = []
            for line in e.toPlainText().split("\n"):
                if not line.strip():
                    continue
                parts = line.split("\t")
                if len(parts) == 1:
                    parts = [line, ""]
                label, value = parts[0].strip(), parts[1].strip()
                accent = value.endswith("!")
                if accent:
                    value = value.rstrip("! ").strip()
                new.append({"label": label, "value": value, "accent": accent})
            self._change_block("cards", new)

        e.textChanged.connect(on_ch)
        self._lay.insertWidget(self._lay.count() - 1, e)

    def _field_columns(self, cfg):
        selected = cfg.get("visible_columns")
        if not self._all_columns:
            self._add_hint("Сначала загрузите Excel-файл.")
            return

        container = QWidget()
        container.setStyleSheet("background:transparent;")
        lay = QVBoxLayout(container)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)

        for col in self._all_columns:
            cb = QCheckBox(str(col))
            cb.setChecked(True if selected is None else (col in selected))
            cb.setStyleSheet(
                f"QCheckBox {{ color:{self.theme.text_main}; font-size:11px;"
                f"padding:2px; background:transparent; }}"
            )
            cb.toggled.connect(lambda v, c=col: self._on_col_toggle(c, v))
            lay.addWidget(cb)

        self._lay.insertWidget(self._lay.count() - 1, container)

    def _on_col_toggle(self, col, checked):
        if self._block is None:
            return
        cfg = self._block.config or {}
        current = cfg.get("visible_columns")
        if current is None:
            current = list(self._all_columns)
        current = list(current)
        if checked and col not in current:
            current.append(col)
        elif not checked and col in current:
            current.remove(col)
        self._change_block("visible_columns", current)

    def _style_input(self, w):
        t = self.theme
        w.setStyleSheet(
            f"background:{t.bg_panel}; color:{t.text_main};"
            f"border:1px solid {t.border}; border-radius:4px;"
            f"padding:4px 6px; font-size:11px;"
        )