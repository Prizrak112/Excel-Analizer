"""Панель свойств блока (правая панель Конструктора NexGrid).

Универсальный модульный инспектор для любых бизнес-данных:
- 4 логические вкладки (Данные / Фильтры / Вид / Макет) вместо длинной прокрутки;
- сворачиваемые секции (аккордеоны) с запоминанием состояния;
- контекстная фильтрация настроек строго под выбранный тип и подтип блока;
- единый пул переиспользуемых компонентов и нейтральная бизнес-терминология.
"""

from contextlib import contextmanager

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDialog, QDoubleSpinBox, QFrame,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
    QSizePolicy, QSlider, QSpinBox, QStackedWidget, QTextEdit, QVBoxLayout,
    QWidget,
)

from src.core.block_factory import BLOCK_TYPES


# ============================================================
# Справочники (универсальная терминология под любые данные)
# ============================================================

_CHART_TYPES = [
    ("🔀 Комбинированный (несколько серий / 2 оси Y)", "combo"),
    ("📊 Столбчатая диаграмма (Bar)", "bar"),
    ("🧱 Накопительная (Stacked Bar)", "bar_stacked"),
    ("📐 С нарастающим итогом (Cumulative)", "bar_cumulative"),
    ("💯 100% Накопительная (100% Stacked)", "bar_stacked_100"),
    ("📈 Горизонтальная (H-Bar)", "hbar"),
    ("📉 Линейный график (Line)", "line"),
    ("🔵 Точечная диаграмма (Scatter)", "scatter"),
    ("⛰ Площадной график (Area)", "area"),
    ("🥧 Круговая диаграмма (Pie)", "pie"),
    ("🍩 Кольцевая диаграмма (Donut)", "donut"),
    ("📶 Гистограмма распределения", "histogram"),
    ("📦 Ящик с усами (Boxplot)", "box"),
    ("🌪 Воронка (Funnel)", "funnel"),
]

_DATA_MODES = [
    ("📊 По столбцам (классический)", "columns"),
    ("↔ По строкам (периоды в столбцах)", "rows"),
]

_PIE_SUBTYPES = [
    ("🎯 Классическая / Иерархия (1 круг + срез)", "single_interactive"),
    ("🔀 2 круга: Признак + Порог ➔ 3 уровня погружения", "dut_two_pies"),
    ("🔎 1 круг (4 уровня): Признак/Порог ➔ Группа ➔ Подгруппа ➔ Объект", "dut_single_drill"),
    ("📅 Сетка по периодам (месяцам)", "months_grid"),
    ("🗂 Сетка по группам 1-го уровня", "types_grid"),
]

_AGG_FUNCS = [
    ("Сумма (SUM)", "sum"),
    ("Среднее (AVG)", "mean"),
    ("Количество записей (COUNT)", "count"),
    ("Медиана (MEDIAN)", "median"),
    ("Минимум (MIN)", "min"),
    ("Максимум (MAX)", "max"),
]

_PIVOT_AGG_FUNCS = [
    ("Сумма (SUM)", "sum"),
    ("Среднее (AVG)", "mean"),
    ("Количество записей (COUNT)", "count"),
    ("Максимум (MAX)", "max"),
    ("Минимум (MIN)", "min"),
]

_SORT_MODES = [
    ("По убыванию значения", "value_desc"),
    ("По возрастанию значения", "value_asc"),
    ("По алфавиту (А→Я)", "label_asc"),
    ("Без сортировки (как в таблице)", "none"),
]

_LEVEL_SORT_MODES = [
    ("⬇ От большего к меньшему", "value_desc"),
    ("⬆ От меньшего к большему", "value_asc"),
    ("|Δ| По модулю отклонения", "abs_desc"),
    ("А→Я По алфавиту", "label_asc"),
    ("Я→А Обратный алфавит", "label_desc"),
    ("Без сортировки", "none"),
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

_FILTER_OPS = [
    (">  Больше", ">"),
    (">= Больше или равно", ">="),
    ("<  Меньше", "<"),
    ("<= Меньше или равно", "<="),
    ("== Равно (точно)", "=="),
    ("!= Не равно", "!="),
    ("↔ В диапазоне (мин, макс)", "between"),
    ("🔍 Содержит текст", "contains"),
    ("🚫 Не содержит текст", "not_contains"),
    ("📋 Одно из списка (через запятую)", "in_list"),
    ("📈 Выше среднего", "above_mean"),
    ("📉 Ниже среднего", "below_mean"),
    ("✔ Только непустые", "not_null"),
]

_THRESHOLD_OPS = [
    ("> Больше порога", "gt"),
    ("≥ Больше или равно", "ge"),
    ("< Меньше порога", "lt"),
    ("≤ Меньше или равно", "le"),
    ("|%| > По модулю больше", "abs_gt"),
    ("|%| ≥ По модулю ≥", "abs_ge"),
    ("Все (без порога)", "all"),
]

_DEV_MODES = [
    ("📐 % отклонения: ((А − Б) / Б) × 100%", "formula_pct_self"),
    ("📐 Вклад в группу: ((А − Б) / Б_общ) × 100%", "formula_pct_group"),
    ("📐 % снижения: ((Б − А) / Б) × 100%", "formula_saving_self"),
    ("📐 Отношение: (А / Б) × 100%", "formula_ratio_ab"),
    ("🧮 Своя формула (конструктор)", "custom_formula"),
    ("Кол-во записей, где А ≠ Б", "waybill_diff_count"),
    ("Кол-во записей, где А > Б", "waybill_count"),
    ("Кол-во записей, где А < Б", "waybill_saving"),
    ("Кол-во записей, где А = Б", "waybill_equal_count"),
    ("Сумма разницы |А − Б|", "waybill_overrun_sum"),
    ("Количество всех записей (COUNT)", "waybill_all_rows"),
    ("Сумма по показателю А (SUM)", "value_sum"),
    ("Среднее по показателю А (AVG)", "value_mean"),
    ("Стандартный режим (по Оси X / Оси Y)", "none"),
]

_LABEL_MODES = [
    ("Авто", "auto"),
    ("Только процент (%)", "percent"),
    ("Категория + Процент (%)", "label+percent"),
    ("Процент + Значение", "percent+value"),
    ("Категория + Значение + %", "label+value+percent"),
    ("Только числовое значение", "value"),
    ("Только категория", "label"),
    ("Скрыть надписи", "none"),
]

_BAR_TEXT_POS = [
    ("Сверху над столбцом (снаружи)", "outside"),
    ("Внутри у верхнего края", "inside"),
    ("Внутри по центру", "inside_middle"),
    ("Внутри у основания", "inside_base"),
    ("Авто (на усмотрение Plotly)", "auto"),
]

_BAR_TEXT_ANGLE = [
    ("Горизонтально (0°)", "0"),
    ("Вертикально (-90°)", "-90"),
    ("Под наклоном (-45°)", "-45"),
    ("Авто", "auto"),
]

_HOVER_MODES = [
    ("Подробная (Категория + Значение + %)", "default"),
    ("Категория и Доля (%)", "label_percent"),
    ("Категория и Значение", "label_value"),
    ("Свой шаблон (задать ниже)", "custom"),
]

_ANIM_STYLES = [
    ("✨ Умная авто (по типу графика)", "auto"),
    ("🌀 Раскручивание (Spin)", "spin"),
    ("🔍 Масштаб из центра (Zoom)", "zoom"),
    ("⬆ Подъём снизу (Slide Up)", "slide_up"),
    ("➡ Выезд слева (Slide Left)", "slide_left"),
    ("📈 Волна / Каскад (Cascade)", "cascade"),
    ("🌫 Мягкое проявление (Fade)", "fade"),
    ("🚫 Без анимации", "none"),
]

_ANIM_SPEEDS = [
    ("⚡ Очень быстрая (200 мс)", 200),
    ("🚀 Быстрая (320 мс)", 320),
    ("✨ Оптимальная (480 мс)", 480),
    ("🌊 Плавная (700 мс)", 700),
    ("🎬 Презентационная (1000 мс)", 1000),
    ("🐢 Медленная (1400 мс)", 1400),
]


def _clean_col_label(text: object) -> str:
    """Убирает переносы строк и лишние пробелы из названий колонок Excel."""
    return " ".join(str(text or "").split())


# ============================================================
# Сворачиваемая секция (аккордеон)
# ============================================================

class CollapsibleSection(QFrame):
    """Компактная сворачиваемая карточка настроек."""

    def __init__(self, title: str, theme, expanded: bool = True, on_toggled=None, parent=None):
        super().__init__(parent)
        self.theme = theme
        self._expanded = expanded
        self._on_toggled = on_toggled

        self.setStyleSheet(
            f"CollapsibleSection {{ background:{theme.bg_panel}; "
            f"border:1px solid {theme.border}; border-radius:6px; }}"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._btn = QPushButton()
        self._btn.setCursor(Qt.PointingHandCursor)
        self._btn.setCheckable(True)
        self._btn.setChecked(expanded)
        self._btn.setStyleSheet(
            f"QPushButton {{ text-align:left; background:transparent; color:{theme.primary}; "
            f"border:none; padding:6px 8px; font-size:10px; font-weight:700; letter-spacing:0.3px; }}"
            f"QPushButton:hover {{ color:{theme.text_main}; }}"
        )
        self._title = title.upper()
        self._btn.clicked.connect(self._toggle)
        root.addWidget(self._btn)

        self._content = QWidget()
        self._content.setStyleSheet("background:transparent;")
        self.content_layout = QVBoxLayout(self._content)
        self.content_layout.setContentsMargins(8, 2, 8, 8)
        self.content_layout.setSpacing(5)
        root.addWidget(self._content)

        self._apply_state()

    def _toggle(self):
        self._expanded = not self._expanded
        self._apply_state()
        if callable(self._on_toggled):
            self._on_toggled(self._expanded)

    def _apply_state(self):
        arrow = "▾" if self._expanded else "▸"
        self._btn.setText(f"{arrow}  {self._title}")
        self._btn.setChecked(self._expanded)
        self._content.setVisible(self._expanded)


# ============================================================
# Основной класс Инспектора
# ============================================================

class BlockInspector(QWidget):
    """Модульная панель свойств блока с вкладками и сворачиваемыми секциями."""

    config_changed = Signal(str)
    unmerge_requested = Signal(str)

    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self._block = None
        self._section = None
        self._df = None
        self._all_columns: list[str] = []
        self.report_ref = None
        self.file_manager = None

        self._width_spin: QSpinBox | None = None
        self._width_slider: QSlider | None = None
        self._height_spin: QSpinBox | None = None
        self._offset_spin: QSpinBox | None = None

        self._cur_lay: QVBoxLayout | None = None
        self._tab_buttons: list[tuple[str, QPushButton]] = []
        self._tab_pages: dict[str, QVBoxLayout] = {}
        self._active_tab_key: str = ""
        self._last_block_id: str | None = None
        self._section_states: dict[tuple[str, str], bool] = {}

        self.setStyleSheet(f"background:{theme.bg_card};")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Шапка Инспектора (Заголовок + панель вкладок) ──
        self._header = QWidget()
        self._header.setStyleSheet(
            f"background:{theme.bg_panel}; border-bottom:1px solid {theme.border};"
        )
        h_lay = QVBoxLayout(self._header)
        h_lay.setContentsMargins(10, 8, 10, 8)
        h_lay.setSpacing(6)

        self._title_lbl = QLabel("Свойства")
        self._title_lbl.setWordWrap(True)
        self._title_lbl.setStyleSheet(
            f"color:{theme.text_main}; font-size:12.5px; font-weight:700; "
            f"background:transparent; border:none;"
        )
        h_lay.addWidget(self._title_lbl)

        self._tab_bar_host = QWidget()
        self._tab_bar_host.setStyleSheet("background:transparent; border:none;")
        self._tab_bar_lay = QHBoxLayout(self._tab_bar_host)
        self._tab_bar_lay.setContentsMargins(0, 0, 0, 0)
        self._tab_bar_lay.setSpacing(3)
        h_lay.addWidget(self._tab_bar_host)
        outer.addWidget(self._header)

        # ── Стек прокручиваемых вкладок ──
        self._stack = QStackedWidget()
        self._stack.setStyleSheet(f"background:{theme.bg_card};")
        outer.addWidget(self._stack, 1)

        self.show_empty()

    # ============================================================
    # Публичный API (полная совместимость с ConstructorTab)
    # ============================================================

    def set_dataframe(self, df):
        self._df = df
        self._all_columns = [str(c) for c in df.columns] if df is not None else []

    def sync_live_geometry(self, block_id: str, width_pct: int, min_height_px: int):
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
            self._offset_spin.setMaximum(max(0, 100 - width_pct))

    def show_empty(self):
        self._block = None
        self._section = None
        self._last_block_id = None
        self._reset_tabs("Свойства")
        lay = self._add_tab("empty", "Свойства", show_bar=False)
        with self._use_layout(lay):
            self._add_hint("Выберите блок на холсте или в дереве отчёта для настройки.")
        lay.addStretch()

    def show_section(self, section):
        self._section = section
        self._block = None
        self._last_block_id = None
        self._reset_tabs("📂 Раздел отчёта")
        lay = self._add_tab("sec", "Раздел", show_bar=False)
        with self._use_layout(lay):
            with self._section_box("Параметры раздела", "sec_main", expanded=True):
                row = QHBoxLayout()
                row.setSpacing(6)

                w_t = QWidget()
                lt = QVBoxLayout(w_t)
                lt.setContentsMargins(0, 0, 0, 0)
                lt.setSpacing(2)
                lt.addWidget(self._make_label("Название"))
                e1 = QLineEdit(str(getattr(section, "title", "")))
                self._style_input(e1)
                e1.textChanged.connect(lambda v: self._change_section("title", v))
                lt.addWidget(e1)
                row.addWidget(w_t, 4)

                w_i = QWidget()
                li = QVBoxLayout(w_i)
                li.setContentsMargins(0, 0, 0, 0)
                li.setSpacing(2)
                li.addWidget(self._make_label("Иконка"))
                e2 = QLineEdit(str(getattr(section, "icon", "📊")))
                e2.setMaxLength(2)
                self._style_input(e2)
                e2.textChanged.connect(lambda v: self._change_section("icon", v))
                li.addWidget(e2)
                row.addWidget(w_i, 1)

                self._add_row(row)
        lay.addStretch()

    def show_block(self, block):
        same_block = (self._last_block_id == getattr(block, "id", None))
        prev_tab_key = self._active_tab_key if same_block else ""

        self._block = block
        self._section = None
        self._last_block_id = getattr(block, "id", None)

        b_name = BLOCK_TYPES.get(block.type, block.type)
        self._reset_tabs(f"⚡ {b_name}")
        cfg = block.config or {}

        if block.type == "divider":
            lay = self._add_tab("main", "Настройки", show_bar=False)
            with self._use_layout(lay):
                self._add_hint("Горизонтальный разделитель не требует дополнительных настроек.")
            lay.addStretch()
            return

        if block.type == "plotly_chart":
            self._build_chart_tabs(cfg)
        elif block.type == "pivot_matrix":
            self._build_pivot_tabs(cfg)
        elif block.type == "dashboard_filter":
            self._build_filter_tabs(cfg)
        elif block.type == "data_table":
            self._build_table_tabs(cfg)
        elif block.type == "paragraph":
            self._build_paragraph_tabs(cfg)
        elif block.type in ("decomposition", "geo_map"):
            self._build_visual_block_tabs(block.type, cfg)
        elif block.type in ("section_title", "list"):
            self._build_text_block_tabs(block.type, cfg)
        elif block.type == "kpi_row":
            self._build_kpi_tabs(cfg)
        elif block.type == "container":
            self._build_container_tabs(block, cfg)
        else:
            lay = self._add_tab("layout", "Макет", show_bar=False)
            with self._use_layout(lay):
                self._build_layout_controls(cfg)
            lay.addStretch()

        for t_lay in self._tab_pages.values():
            t_lay.addStretch()

        if prev_tab_key and prev_tab_key in self._tab_pages:
            self._select_tab(prev_tab_key)
        elif self._tab_buttons:
            self._select_tab(self._tab_buttons[0][0])

    # ============================================================
    # Управление вкладками и контекстом компоновки
    # ============================================================

    def _reset_tabs(self, title: str):
        self._title_lbl.setText(title)
        self._width_spin = None
        self._width_slider = None
        self._height_spin = None
        self._offset_spin = None
        self._cur_lay = None
        self._tab_buttons.clear()
        self._tab_pages.clear()

        while self._tab_bar_lay.count():
            it = self._tab_bar_lay.takeAt(0)
            w = it.widget()
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()

        while self._stack.count():
            w = self._stack.widget(0)
            self._stack.removeWidget(w)
            if isinstance(w, QScrollArea):
                inner = w.takeWidget()
                if inner is not None:
                    inner.hide()
                    inner.setParent(None)
                    inner.deleteLater()
            w.hide()
            w.setParent(None)
            w.deleteLater()

        self._tab_bar_host.setVisible(False)

    def _add_tab(self, key: str, label: str, show_bar: bool = True) -> QVBoxLayout:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"QScrollArea {{ background:{self.theme.bg_card}; border:none; }}")

        page = QWidget()
        page.setStyleSheet(f"background:{self.theme.bg_card};")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(8, 8, 8, 12)
        lay.setSpacing(8)
        scroll.setWidget(page)

        idx = self._stack.addWidget(scroll)
        self._tab_pages[key] = lay

        btn = QPushButton(label)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setCheckable(True)
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btn.clicked.connect(lambda _=False, k=key: self._select_tab(k))
        self._tab_bar_lay.addWidget(btn, 1)
        self._tab_buttons.append((key, btn))

        if show_bar and len(self._tab_buttons) > 1:
            self._tab_bar_host.setVisible(True)
        if idx == 0:
            self._select_tab(key)
        return lay

    def _select_tab(self, key: str):
        self._active_tab_key = key
        t = self.theme
        for idx, (k, btn) in enumerate(self._tab_buttons):
            active = (k == key)
            btn.setChecked(active)
            if active:
                self._stack.setCurrentIndex(idx)
                btn.setStyleSheet(
                    f"QPushButton {{ background:{t.primary}; color:{t.text_inverse}; "
                    f"border:1px solid {t.primary}; border-radius:5px; padding:5px 2px; "
                    f"font-size:10.5px; font-weight:700; }}"
                )
            else:
                btn.setStyleSheet(
                    f"QPushButton {{ background:{t.bg_card}; color:{t.text_muted}; "
                    f"border:1px solid {t.border}; border-radius:5px; padding:5px 2px; "
                    f"font-size:10.5px; font-weight:600; }}"
                    f"QPushButton:hover {{ color:{t.text_main}; border-color:{t.primary}; }}"
                )

    @contextmanager
    def _use_layout(self, lay: QVBoxLayout):
        prev = self._cur_lay
        self._cur_lay = lay
        try:
            yield lay
        finally:
            self._cur_lay = prev

    @contextmanager
    def _section_box(self, title: str, key: str, expanded: bool = True):
        b_id = str(getattr(self._block, "id", "") or "sec")
        state_key = (b_id, key)
        is_open = self._section_states.get(state_key, expanded)

        def _remember(val: bool):
            self._section_states[state_key] = val

        box = CollapsibleSection(title, self.theme, expanded=is_open, on_toggled=_remember)
        self._add_widget(box)
        with self._use_layout(box.content_layout):
            yield box

    def _rebuild_later(self):
        if self._block is not None:
            b_ref = self._block
            QTimer.singleShot(0, lambda b=b_ref: self.show_block(b) if self._block is b else None)

    # ============================================================
    # 1. ГРАФИКИ PLOTLY (Данные / Фильтры / Вид / Макет)
    # ============================================================

    def _build_chart_tabs(self, cfg: dict):
        cur_type = str(cfg.get("chart_type", "bar") or "bar")
        cur_mode = str(cfg.get("data_mode", "columns") or "columns")
        pie_mode = str(cfg.get("pie_display_mode", "single_interactive") or "single_interactive")
        is_pie = cur_type in ("pie", "donut")
        is_combo = (cur_type == "combo")
        is_bar_like = cur_type in ("bar", "bar_stacked", "bar_cumulative", "bar_stacked_100", "hbar", "combo")
        is_dual_pie = is_pie and cur_mode != "rows" and pie_mode in ("dut_two_pies", "dut_single_drill")

        tab_data = self._add_tab("data", "Данные")
        tab_filt = self._add_tab("filters", "Фильтры")
        tab_view = self._add_tab("view", "Вид")
        tab_lay = self._add_tab("layout", "Макет")

        # ── ВКЛАДКА «ДАННЫЕ» ──
        with self._use_layout(tab_data):
            with self._section_box("Источник и тип", "ch_src", expanded=True):
                self._build_source_selectors(cfg)
                cols = self._get_target_columns(cfg)
                self._field_text("Заголовок графика", "title", cfg, placeholder="Например: Динамика показателей")
                self._field_combo("Тип визуализации", "chart_type", cfg, _CHART_TYPES, "bar", rebuild=True)

                if is_pie:
                    self._field_combo("Режим обработки", "data_mode", cfg, _DATA_MODES, "columns", rebuild=True)
                    if cur_mode != "rows":
                        self._field_combo("Подтип круговой диаграммы", "pie_display_mode", cfg, _PIE_SUBTYPES, "single_interactive", rebuild=True)
                elif not is_combo:
                    self._field_combo("Режим обработки", "data_mode", cfg, _DATA_MODES, "columns", rebuild=True)

            if is_combo:
                self._build_combo_data_sections(cfg, cols)
            elif cur_mode == "rows":
                self._build_row_mode_sections(cfg, cols, is_pie=is_pie)
            elif is_dual_pie:
                self._build_dual_pie_data_sections(cfg, cols)
            elif is_pie:
                self._build_pie_data_sections(cfg, cols)
            else:
                self._build_xy_data_sections(cfg, cols)

        # ── ВКЛАДКА «ФИЛЬТРЫ» ──
        with self._use_layout(tab_filt):
            with self._section_box("Сортировка и объём", "ch_sort", expanded=True):
                if is_combo:
                    series_list = list(cfg.get("combo_series") or [])
                    if series_list:
                        items_s = [
                            (f"S{i + 1}: {_clean_col_label(s.get('name') or s.get('col') or f'Серия {i + 1}')}", i)
                            for i, s in enumerate(series_list) if isinstance(s, dict)
                        ]
                        self._field_combo("Сортировать и отбирать Топ-N по серии", "combo_sort_series_idx", cfg, items_s, 0)
                elif cur_mode != "rows":
                    self._field_combo("Сортировка категорий", "sort_by", cfg, _SORT_MODES, "value_desc")

                self._field_spin_pair(
                    ("Топ категорий (0 = все)", "top_n", 12, 0, 500),
                    ("Лимит строк (0 = все)", "row_limit", 0, 0, 100000),
                    cfg,
                )
                self._field_int("Начать со строки (сдвиг)", "row_start", cfg, default=0, min_val=0, max_val=100000)

            if is_pie and not is_dual_pie and cur_mode != "rows":
                has_pct_filt = (cfg.get("slice_pct_mode", "ge") != "none" and float(cfg.get("min_slice_pct", 0.0) or 0.0) != 0.0)
                with self._section_box("Фильтр секторов по %", "ch_pie_pct", expanded=has_pct_filt):
                    self._build_pie_slice_filter(cfg)

            has_row_filt = bool(cfg.get("filter_col") or cfg.get("custom_query"))
            with self._section_box("Отбор строк (ЕСЛИ)", "ch_if", expanded=has_row_filt):
                self._field_col("Столбец для проверки", "filter_col", cfg, cols, "— Без фильтра —")
                self._field_combo("Условие", "filter_op", cfg, _FILTER_OPS, ">")
                self._field_text("Значение условия", "filter_val", cfg, placeholder="Напр.: 10  или  100, 500  или  Активен")
                self._field_text("Формула pandas.query (опц.)", "custom_query", cfg, placeholder="`Сумма` > 1000 and `Статус` == 'Да'")

            with self._section_box("Связь с другим графиком", "ch_link", expanded=bool(cfg.get("filter_from_chart"))):
                self._build_chart_link_combo(cfg)

        # ── ВКЛАДКА «ВИД» ──
        with self._use_layout(tab_view):
            with self._section_box("Стиль и легенда", "ch_style", expanded=True):
                self._field_combo("Цветовая палитра", "palette", cfg, _PALETTES, "corporate")
                self._field_background_picker(cfg)
                self._field_combo("Позиция легенды", "legend_pos", cfg, _LEGEND_POS, "right")
                self._field_int("Размер шрифта (px)", "font_size", cfg, default=12, min_val=8, max_val=48)

            with self._section_box("Элементы отображения", "ch_toggles", expanded=True):
                self._field_checkbox("Показывать заголовок", "show_title", cfg, True)
                self._field_checkbox("Показывать легенду", "show_legend", cfg, True)
                self._field_checkbox("Показывать подписи значений", "show_values", cfg, True)
                if not is_pie:
                    self._field_checkbox("Показывать сетку", "show_grid", cfg, True)
                    self._field_checkbox("Показывать подписи осей (X/Y)", "show_axis_labels", cfg, True)
                    self._field_checkbox("Показывать сумму серий (Σ Итого)", "show_summary_total", cfg, False)

            with self._section_box("Анимация графика", "ch_anim", expanded=True):
                self._field_combo("Стиль анимации", "anim_style", cfg, _ANIM_STYLES, "auto", rebuild=True)
                if str(cfg.get("anim_style", "auto") or "auto") != "none":
                    self._field_combo("Скорость движения", "anim_speed", cfg, _ANIM_SPEEDS, 480)

            with self._section_box("Подписи значений и подсказки", "ch_labels", expanded=False):
                self._field_combo("Формат надписей", "value_label_mode", cfg, _LABEL_MODES, "auto")
                if is_pie and not is_dual_pie:
                    _PIE_VAL_MODES = [
                        ("Точный % по формуле (+/−)", "formula_pct"),
                        ("Модуль % без знака", "formula_abs_pct"),
                        ("% по формуле + доля круга", "formula_and_share"),
                        ("Классическая доля круга (100%)", "share_only"),
                    ]
                    self._field_combo("Значение на секторах", "pie_value_display", cfg, _PIE_VAL_MODES, "formula_pct")
                if is_bar_like:
                    self._field_combo("Положение на столбцах", "bar_text_pos", cfg, _BAR_TEXT_POS, "outside")
                    self._field_combo("Поворот на столбцах", "bar_text_angle", cfg, _BAR_TEXT_ANGLE, "0")
                self._field_combo("Подсказка при наведении", "hover_format", cfg, _HOVER_MODES, "default")
                self._field_text("Свой шаблон подсказки", "hover_custom_tpl", cfg, placeholder="{label}: {value} ({percent})")
                self._add_hint("Теги: {label}, {value}, {percent}, {name}, {details}")

            if is_combo:
                with self._section_box("Оси, цель и подсветка", "ch_combo_view", expanded=False):
                    _BARMODES = [
                        ("📊 Рядом (Group)", "group"),
                        ("🧱 В стопку (Stack)", "stack"),
                        ("🔀 Наложение (Overlay)", "overlay"),
                    ]
                    self._field_combo("Расположение столбцов", "combo_barmode", cfg, _BARMODES, "group")
                    self._field_text("Подпись правой оси Y2", "combo_y2_title", cfg, placeholder="Напр.: Отклонение, %")
                    self._field_checkbox("Выделять нулевую линию (Y = 0)", "combo_show_zero_line", cfg, True)
                    self._field_text("Целевая линия (число)", "combo_target_val", cfg, placeholder="Напр.: 0 или 1000")
                    self._field_text("Подпись целевой линии", "combo_target_label", cfg, placeholder="Напр.: План / Лимит")
                    self._field_checkbox("🚨 Подсвечивать превышение (А > Б)", "combo_highlight_overrun", cfg, False)
                    series_list = list(cfg.get("combo_series") or [])
                    if series_list:
                        s_items = [
                            (f"S{i + 1}: {_clean_col_label(s.get('name') or s.get('col') or f'Серия {i + 1}')}", i)
                            for i, s in enumerate(series_list) if isinstance(s, dict)
                        ]
                        self._field_combo("Серия А (Факт)", "combo_hl_fact_idx", cfg, s_items, 0)
                        self._field_combo("Серия Б (База)", "combo_hl_norm_idx", cfg, s_items, min(1, len(s_items) - 1))
                    self._field_color("Сигнальный цвет превышения", "combo_over_color", cfg, "#e11d48")

            with self._section_box("Подписи осей и переименование", "ch_aliases", expanded=False):
                self._field_text("Название сводки «Все значения»", "all_groups_label", cfg, placeholder="Напр.: Все категории")
                self._field_checkbox("Добавлять группу в легенду", "prefix_legend_with_group", cfg, False)
                self._field_text("Свои названия рядов (через запятую)", "custom_legend_names", cfg, placeholder="Напр.: Факт, План  или  Старое=Новое")
                if not is_pie:
                    self._field_text("Своя подпись оси X", "custom_x_title", cfg, placeholder="Напр.: Период")
                    self._field_text("Своя подпись оси Y", "custom_y_title", cfg, placeholder="Напр.: Сумма, руб.")
                self._build_column_aliases_editor(cfg)

        # ── ВКЛАДКА «МАКЕТ» ──
        with self._use_layout(tab_lay):
            self._build_layout_controls(cfg)

    # ── Секции данных для обычных X/Y графиков ──
    def _build_xy_data_sections(self, cfg: dict, cols: list[str]):
        if not cols:
            self._add_hint("Загрузите таблицу для выбора столбцов.")
            return

        with self._section_box("Оси и показатель", "xy_axes", expanded=True):
            self._field_col("Ось X (Категория / Группа)", "x_col", cfg, cols, "⚡ Авто (1-й столбец)")

            cur_y = str(cfg.get("y_col", "") or "")
            first_y = cur_y.split(",")[0].strip() if cur_y else ""
            cb_y = self._make_col_combobox(cols, first_y, "— Количество строк (COUNT) —")
            self._add_label("Ось Y (Основной показатель)")
            self._add_widget(cb_y)

            self._field_combo("Агрегация", "agg", cfg, _AGG_FUNCS, "sum")
            self._field_col("Период / Дата (кнопки месяцев)", "date_col", cfg, cols, "— Без разбивки по датам —")

        has_multi_y = ("," in cur_y) or (cfg.get("multi_y_mode", "separate") == "combined")
        with self._section_box("Несколько показателей Y", "xy_multi", expanded=has_multi_y):
            row_m = QHBoxLayout()
            row_m.setSpacing(4)
            ed_y = QLineEdit(cur_y)
            ed_y.setPlaceholderText("Столбец 1, Столбец 2...")
            self._style_input(ed_y)
            row_m.addWidget(ed_y, 1)

            btn_clr = QPushButton("✕")
            btn_clr.setFixedWidth(26)
            self._style_input(btn_clr)
            row_m.addWidget(btn_clr)
            self._add_row(row_m)

            cb_add = self._make_col_combobox(cols, "", "➕ Добавить столбец на ось Y…")
            self._add_widget(cb_add)

            def _on_primary_y(i):
                v = cb_y.itemData(i) or ""
                parts = [c.strip() for c in ed_y.text().split(",") if c.strip()]
                new_val = "" if not v else (v if len(parts) <= 1 else ", ".join([v] + parts[1:]))
                ed_y.blockSignals(True)
                ed_y.setText(new_val)
                ed_y.blockSignals(False)
                self._change_block("y_col", new_val)

            def _on_add_y(i):
                v = cb_add.itemData(i)
                if not v:
                    return
                parts = [c.strip() for c in ed_y.text().split(",") if c.strip()]
                if v not in parts:
                    parts.append(v)
                new_val = ", ".join(parts)
                ed_y.blockSignals(True)
                ed_y.setText(new_val)
                ed_y.blockSignals(False)
                cb_add.blockSignals(True)
                cb_add.setCurrentIndex(0)
                cb_add.blockSignals(False)
                self._change_block("y_col", new_val)

            def _on_clear_y():
                ed_y.setText("")
                cb_y.blockSignals(True)
                cb_y.setCurrentIndex(0)
                cb_y.blockSignals(False)
                self._change_block("y_col", "")

            cb_y.currentIndexChanged.connect(_on_primary_y)
            cb_add.currentIndexChanged.connect(_on_add_y)
            btn_clr.clicked.connect(_on_clear_y)
            ed_y.textChanged.connect(lambda v: self._change_block("y_col", v))

            self._field_combo(
                "Режим нескольких столбцов Y",
                "multi_y_mode",
                cfg,
                [("📊 Раздельные серии", "separate"), ("🧮 Объединить формулой", "combined")],
                "separate",
            )
            self._field_combo(
                "Операция объединения",
                "multi_y_func",
                cfg,
                [
                    ("Разность: А − Б", "sub"),
                    ("Сумма: А + Б", "sum"),
                    ("Деление: А / Б", "div"),
                    ("Произведение: А × Б", "mul"),
                    ("Среднее", "mean"),
                ],
                "sub",
            )

        has_hier = bool(cfg.get("parent_group_col") or cfg.get("model_col") or cfg.get("fact_col") or cfg.get("norm_col"))
        with self._section_box("Иерархия для среза и А / Б", "xy_hier", expanded=has_hier):
            self._field_col("Уровень 1 — Группа (для среза)", "parent_group_col", cfg, cols, "— Не выбран —")
            self._field_col("Уровень 2 — Подкатегория", "model_col", cfg, cols, "⚡ Авто (Ось X)")
            self._field_col("Показатель А (Факт / Текущее)", "fact_col", cfg, cols, "— Не выбран —")
            self._field_col("Показатель Б (План / База)", "norm_col", cfg, cols, "— Не выбран —")

    # ── Секции данных для двухфакторной круговой диаграммы (Признак + Порог) ──
    def _build_dual_pie_data_sections(self, cfg: dict, cols: list[str]):
        with self._section_box("Живые фильтры: Признак и Порог", "dual_pie_f", expanded=True):
            self._field_col("Фильтр 1 — Признак / Категория (напр. Да/Нет, Статус)", "dut_col", cfg, cols, "⚡ Авто")
            self._field_col("Фильтр 2 — Показатель порога (%)", "pct_col", cfg, cols, "⚡ Авто (столбец % или (А−Б)/Б)")
            self._field_combo("Условие порога по умолчанию", "dut_pct_op", cfg, _THRESHOLD_OPS, "gt")
            self._field_double("Стартовый порог (%)", "dut_pct_val", cfg, default=3.0, suffix=" %")
            self._field_combo(
                "Единица подсчёта",
                "dut_count_mode",
                cfg,
                [("🏷 Уникальные объекты (по Уровню 3 / ID)", "unique_ts"), ("📄 Все строки таблицы", "rows")],
                "unique_ts",
            )

        with self._section_box("Иерархия погружения (3 уровня)", "dual_pie_h", expanded=True):
            self._field_col("Уровень 1 — Группа / Категория", "parent_group_col", cfg, cols, "⚡ Авто")
            self._field_col("Уровень 2 — Подкатегория", "model_col", cfg, cols, "⚡ Авто")
            self._field_col("Уровень 3 — Объект / ID", "plate_col", cfg, cols, "⚡ Авто")
            self._field_col("Период / Дата (кнопки месяцев)", "date_col", cfg, cols, "— Без разбивки по датам —")

        with self._section_box("Расчёт % из А и Б (если нет готового %)", "dual_pie_ab", expanded=False):
            self._field_col("Показатель А (Факт / Текущее)", "fact_col", cfg, cols, "— Не выбран —")
            self._field_col("Показатель Б (План / База)", "norm_col", cfg, cols, "— Не выбран —")

    # ── Секции данных для классической и иерархической круговой диаграммы ──
    def _build_pie_data_sections(self, cfg: dict, cols: list[str]):
        with self._section_box("Группировка и иерархия", "pie_hier", expanded=True):
            self._field_col("Уровень 1 — Основная группа", "parent_group_col", cfg, cols, "— Использовать Ось X —")
            self._field_col("Уровень 2 — Подкатегория (при выборе в срезе)", "model_col", cfg, cols, "⚡ Авто (Ось X)")
            self._field_col("Уровень 3 / Поле детализации (ID, Код)", "plate_col", cfg, cols, "— Не выбрано —")
            self._field_col("Период / Дата (кнопки месяцев)", "date_col", cfg, cols, "— Без разбивки по датам —")

        dev_mode = str(cfg.get("deviation_mode", "formula_pct_self") or "formula_pct_self")
        with self._section_box("Показатели и расчёт долей", "pie_calc", expanded=True):
            self._field_combo("Режим расчёта", "deviation_mode", cfg, _DEV_MODES, "formula_pct_self", rebuild=True)
            if dev_mode == "none":
                self._field_col("Категории (Ось X)", "x_col", cfg, cols, "⚡ Авто (1-й столбец)")
                self._field_col("Значение (Ось Y)", "y_col", cfg, cols, "— Кол-во строк (COUNT) —")
                self._field_combo("Агрегация", "agg", cfg, _AGG_FUNCS, "sum")
            else:
                self._field_col("Показатель А (Факт / Текущее)", "fact_col", cfg, cols, "— Не выбран (брать Ось Y) —")
                self._field_col("Показатель Б (План / База)", "norm_col", cfg, cols, "— Не выбран —")
                self._field_combo(
                    "Отбор строк для сумм А и Б",
                    "formula_row_scope",
                    cfg,
                    [
                        ("Все строки категории", "all_rows"),
                        ("Только с отклонением (А ≠ Б)", "diff_only"),
                        ("Только превышение (А > Б)", "over_only"),
                        ("Только снижение (А < Б)", "saving_only"),
                    ],
                    "all_rows",
                )
                self._field_combo(
                    "Уровень вычисления",
                    "calc_eval_mode",
                    cfg,
                    [
                        ("📄 Построчно (по каждой записи)", "separate"),
                        ("🏷 Сгруппированно по ключевому объекту", "grouped"),
                    ],
                    "separate",
                    rebuild=True,
                )
                if cfg.get("calc_eval_mode") == "grouped":
                    self._field_col("Ключевой объект (ID / Код)", "calc_group_col", cfg, cols, "⚡ Авто (Уровень 3 / Ось X)")

        is_custom_f = (dev_mode == "custom_formula")
        if dev_mode in ("formula_pct_self", "formula_pct_group", "formula_saving_self", "formula_ratio_ab", "custom_formula"):
            with self._section_box("Конструктор формулы", "pie_formula", expanded=is_custom_f):
                self._build_pie_formula_constructor(cfg)

    def _build_pie_formula_constructor(self, cfg: dict):
        cb_num = QComboBox()
        for t, v in [
            ("А − Б (Разница)", "(A - B)"),
            ("|А − Б| (Модуль разницы)", "abs(A - B)"),
            ("Б − А (Снижение)", "(B - A)"),
            ("А (Сумма показателя А)", "A"),
            ("Б (Сумма показателя Б)", "B"),
            ("Кол-во с отклонением (А ≠ Б)", "COUNT_DIFF"),
            ("Общее кол-во записей", "COUNT"),
        ]:
            cb_num.addItem(t, v)
        cb_num.setCurrentIndex(max(0, cb_num.findData(cfg.get("formula_num", "(A - B)"))))
        self._style_combo(cb_num)
        self._add_label("Числитель (что ищем)")
        self._add_widget(cb_num)

        cb_den = QComboBox()
        for t, v in [
            ("÷ Б (База категории)", "B"),
            ("÷ Б_общий (База всей выборки)", "B_TOTAL"),
            ("÷ А (Факт категории)", "A"),
            ("÷ А_общий (Факт всей выборки)", "A_TOTAL"),
            ("÷ |А_общ − Б_общ|", "abs(TOTAL_DIFF)"),
            ("÷ Общее кол-во (COUNT_TOTAL)", "COUNT_TOTAL"),
            ("÷ Кол-во категории (COUNT)", "COUNT"),
            ("Без деления (1)", "1"),
        ]:
            cb_den.addItem(t, v)
        cb_den.setCurrentIndex(max(0, cb_den.findData(cfg.get("formula_den", "B"))))
        self._style_combo(cb_den)
        self._add_label("Знаменатель (на что делим)")
        self._add_widget(cb_den)

        chk_100 = QCheckBox("× 100% (перевести в проценты)")
        chk_100.setChecked(bool(cfg.get("formula_mul100", True)))
        chk_100.setStyleSheet(f"QCheckBox {{ color:{self.theme.text_main}; font-size:11px; background:transparent; }}")
        self._add_widget(chk_100)

        self._add_label("Итоговая формула")
        ed_f = QLineEdit(str(cfg.get("calc_formula", "((A - B) / B) * 100")))
        ed_f.setPlaceholderText("((A - B) / B) * 100")
        self._style_input(ed_f)
        self._add_widget(ed_f)

        tok_row = QHBoxLayout()
        tok_row.setSpacing(3)
        for lbl_b, tok in (("A", "A"), ("B", "B"), ("A_общ", "A_TOTAL"), ("B_общ", "B_TOTAL"), ("COUNT", "COUNT"), ("×100", " * 100")):
            b = QPushButton(lbl_b)
            b.setCursor(Qt.PointingHandCursor)
            self._style_chip(b)
            b.clicked.connect(lambda _, tk=tok: ed_f.insert(tk))
            tok_row.addWidget(b)
        self._add_row(tok_row)

        def _rebuild_f():
            n_s = cb_num.currentData() or "(A - B)"
            d_s = cb_den.currentData() or "B"
            m_b = chk_100.isChecked()
            f_str = (f"({n_s}) * 100" if m_b else n_s) if d_s == "1" else (f"({n_s} / {d_s}) * 100" if m_b else f"({n_s} / {d_s})")
            ed_f.blockSignals(True)
            ed_f.setText(f_str)
            ed_f.blockSignals(False)
            if self._block is not None:
                nc = dict(self._block.config or {})
                nc.update({"formula_num": n_s, "formula_den": d_s, "formula_mul100": m_b, "calc_formula": f_str, "deviation_mode": "custom_formula"})
                self._block.config = nc
                self.config_changed.emit(self._block.id)

        def _on_edit(txt: str):
            if self._block is not None:
                nc = dict(self._block.config or {})
                nc["calc_formula"] = txt
                nc["deviation_mode"] = "custom_formula"
                self._block.config = nc
                self.config_changed.emit(self._block.id)

        cb_num.currentIndexChanged.connect(lambda _: _rebuild_f())
        cb_den.currentIndexChanged.connect(lambda _: _rebuild_f())
        chk_100.toggled.connect(lambda _: _rebuild_f())
        ed_f.textEdited.connect(_on_edit)

    def _build_pie_slice_filter(self, cfg: dict):
        _SLICE_MODES = [
            ("≥ Больше или равно (+/−)", "ge"),
            ("≤ Меньше или равно (+/−)", "le"),
            ("> Строго больше (+/−)", "gt"),
            ("< Строго меньше (+/−)", "lt"),
            ("|%| ≥ По модулю ≥", "abs_ge"),
            ("|%| ≤ По модулю ≤", "abs_le"),
            ("Доля круга ≥ (%)", "share_ge"),
            ("Доля круга ≤ (%)", "share_le"),
            ("— Без фильтра —", "none"),
        ]
        self._field_combo("Условие отбора секторов", "slice_pct_mode", cfg, _SLICE_MODES, "ge")
        sp = self._field_double("Порог процента", "min_slice_pct", cfg, default=0.0, suffix=" %", use_editing_finished=False)

        p_row = QHBoxLayout()
        p_row.setSpacing(4)
        for p_lbl, p_val in (("Все", 0.0), ("5%", 5.0), ("10%", 10.0), ("20%", 20.0)):
            b = QPushButton(p_lbl)
            b.setCursor(Qt.PointingHandCursor)
            self._style_chip(b)

            def _apply_preset(_=False, v=p_val):
                sp.setValue(v)
                self._change_block("min_slice_pct", float(v))

            b.clicked.connect(_apply_preset)
            p_row.addWidget(b)
        self._add_row(p_row)

    # ── Секции данных для комбинированного графика ──
    def _build_combo_data_sections(self, cfg: dict, cols: list[str]):
        def _guess_ab_cols() -> tuple[str, str]:
            f_c = str(cfg.get("fact_col", "") or "")
            n_c = str(cfg.get("norm_col", "") or "")
            for c in cols:
                cl = c.lower()
                if not f_c and any(w in cl for w in ("факт", "fact", "текущ", "итог")):
                    f_c = c
                elif not n_c and any(w in cl for w in ("план", "норм", "баз", "цель", "plan", "norm")):
                    n_c = c
            if not f_c and cols:
                f_c = cols[-1]
            if not n_c and len(cols) >= 2:
                n_c = cols[-2] if cols[-2] != f_c else cols[0]
            return f_c, n_c

        series_list = list(cfg.get("combo_series") or [])
        if not series_list and cols:
            f_c, n_c = _guess_ab_cols()
            series_list = [
                {"name": _clean_col_label(f_c) or "Серия 1", "source_type": "column", "col": f_c, "formula": "", "agg": "sum", "plot_type": "bar", "y_axis": "y1", "color": "#2b7fff", "line_dash": "solid", "line_width": 3, "marker_size": 8, "opacity": 0.9, "show_labels": True, "suffix": "", "visible": True},
                {"name": _clean_col_label(n_c) or "Серия 2", "source_type": "column", "col": n_c, "formula": "", "agg": "sum", "plot_type": "line", "y_axis": "y1", "color": "#87C800", "line_dash": "solid", "line_width": 3, "marker_size": 8, "opacity": 1.0, "show_labels": True, "suffix": "", "visible": True},
            ]
            cfg["combo_series"] = series_list
            if self._block is not None:
                self._block.config = cfg

        def _save_series(updated: list, rebuild: bool = False):
            if self._block is None:
                return
            nc = dict(self._block.config or {})
            nc["combo_series"] = updated
            self._block.config = nc
            self.config_changed.emit(self._block.id)
            if rebuild:
                self._rebuild_later()

        with self._section_box(f"Серии на графике ({len(series_list)})", "cmb_series", expanded=True):
            cb_pre = QComboBox()
            cb_pre.addItem("⚡ Применить готовый шаблон…", "")
            cb_pre.addItem("🎯 Отклонение (А−Б, Y2) + Тренд % (Y1)", "diff_y2_pct_y1")
            cb_pre.addItem("📊 Столбцы (А) + Линия (Б) на общей оси", "ab_bar_line")
            cb_pre.addItem("📊 Столбцы (А и Б) + Линия разницы (А−Б)", "ab_diff")
            cb_pre.addItem("⛰ Область (Б) + Столбцы (А) + % (Y2)", "area_bar_pct")
            cb_pre.addItem("📊 Столбцы + Нарастающий итог (Линия)", "bar_cum")
            self._style_combo(cb_pre)
            self._add_widget(cb_pre)

            def _apply_preset(i):
                code = cb_pre.itemData(i)
                if not code or self._block is None:
                    return
                a_c, b_c = _guess_ab_cols()
                if a_c:
                    self._block.config["fact_col"] = a_c
                if b_c:
                    self._block.config["norm_col"] = b_c
                presets = {
                    "diff_y2_pct_y1": [
                        {"name": "Отклонение (А − Б)", "source_type": "formula", "col": "", "formula": "A - B", "agg": "sum", "plot_type": "bar", "y_axis": "y2", "color": "#2b7fff", "line_dash": "solid", "line_width": 3, "marker_size": 8, "opacity": 0.85, "show_labels": True, "suffix": "", "visible": True},
                        {"name": "Тренд отклонения, %", "source_type": "formula", "col": "", "formula": "((A - B) / B) * 100", "agg": "sum", "plot_type": "line", "y_axis": "y1", "color": "#87C800", "line_dash": "solid", "line_width": 3, "marker_size": 8, "opacity": 1.0, "show_labels": True, "suffix": "%", "visible": True},
                    ],
                    "ab_bar_line": [
                        {"name": _clean_col_label(a_c) or "Показатель А", "source_type": "column", "col": a_c, "formula": "", "agg": "sum", "plot_type": "bar", "y_axis": "y1", "color": "#2b7fff", "line_dash": "solid", "line_width": 3, "marker_size": 8, "opacity": 0.9, "show_labels": True, "suffix": "", "visible": True},
                        {"name": _clean_col_label(b_c) or "Показатель Б", "source_type": "column", "col": b_c, "formula": "", "agg": "sum", "plot_type": "line", "y_axis": "y1", "color": "#87C800", "line_dash": "solid", "line_width": 3, "marker_size": 8, "opacity": 1.0, "show_labels": True, "suffix": "", "visible": True},
                    ],
                    "ab_diff": [
                        {"name": _clean_col_label(a_c) or "А (S1)", "source_type": "column", "col": a_c, "formula": "", "agg": "sum", "plot_type": "bar", "y_axis": "y1", "color": "#2b7fff", "line_dash": "solid", "line_width": 3, "marker_size": 8, "opacity": 0.88, "show_labels": False, "suffix": "", "visible": True},
                        {"name": _clean_col_label(b_c) or "Б (S2)", "source_type": "column", "col": b_c, "formula": "", "agg": "sum", "plot_type": "bar", "y_axis": "y1", "color": "#94a3b8", "line_dash": "solid", "line_width": 3, "marker_size": 8, "opacity": 0.88, "show_labels": False, "suffix": "", "visible": True},
                        {"name": "Разница (S1−S2)", "source_type": "formula", "col": "", "formula": "S1 - S2", "agg": "sum", "plot_type": "spline", "y_axis": "y1", "color": "#e11d48", "line_dash": "solid", "line_width": 3, "marker_size": 8, "opacity": 1.0, "show_labels": True, "suffix": "", "visible": True},
                    ],
                    "area_bar_pct": [
                        {"name": _clean_col_label(b_c) or "База (S1)", "source_type": "column", "col": b_c, "formula": "", "agg": "sum", "plot_type": "area", "y_axis": "y1", "color": "#94a3b8", "line_dash": "dot", "line_width": 2, "marker_size": 0, "opacity": 0.35, "show_labels": False, "suffix": "", "visible": True},
                        {"name": _clean_col_label(a_c) or "Факт (S2)", "source_type": "column", "col": a_c, "formula": "", "agg": "sum", "plot_type": "bar", "y_axis": "y1", "color": "#2b7fff", "line_dash": "solid", "line_width": 3, "marker_size": 8, "opacity": 0.9, "show_labels": True, "suffix": "", "visible": True},
                        {"name": "% отклонения", "source_type": "formula", "col": "", "formula": "((S2 - S1) / S1) * 100", "agg": "sum", "plot_type": "line", "y_axis": "y2", "color": "#e11d48", "line_dash": "solid", "line_width": 3, "marker_size": 8, "opacity": 1.0, "show_labels": True, "suffix": "%", "visible": True},
                    ],
                    "bar_cum": [
                        {"name": _clean_col_label(a_c) or "Показатель", "source_type": "column", "col": a_c, "formula": "", "agg": "sum", "plot_type": "bar", "y_axis": "y1", "color": "#2b7fff", "line_dash": "solid", "line_width": 3, "marker_size": 8, "opacity": 0.85, "show_labels": True, "suffix": "", "visible": True},
                        {"name": "Нарастающий итог", "source_type": "column", "col": a_c, "formula": "", "agg": "sum", "plot_type": "cum_line", "y_axis": "y1", "color": "#87C800", "line_dash": "solid", "line_width": 3, "marker_size": 8, "opacity": 1.0, "show_labels": True, "suffix": "", "visible": True},
                    ],
                }
                if code in presets:
                    _save_series(presets[code], rebuild=True)

            cb_pre.currentIndexChanged.connect(_apply_preset)

            for idx_s, s_item in enumerate(series_list):
                if isinstance(s_item, dict):
                    self._build_combo_series_card(idx_s, s_item, series_list, cols, _save_series)

            add_row = QHBoxLayout()
            add_row.setSpacing(4)
            btn_c = QPushButton("➕ Столбец")
            btn_f = QPushButton("🧮 Формула")
            for b, prim in ((btn_c, True), (btn_f, False)):
                b.setCursor(Qt.PointingHandCursor)
                b.setStyleSheet(
                    f"QPushButton {{ background:{self.theme.primary if prim else self.theme.bg_card}; "
                    f"color:{self.theme.text_inverse if prim else self.theme.primary}; "
                    f"border:1px solid {self.theme.primary}; border-radius:5px; padding:5px; font-size:10.5px; font-weight:700; }}"
                )

            pal = ["#2b7fff", "#87C800", "#ff9f1c", "#e71d36", "#6f42c1", "#20c997"]

            def _add_s(is_formula: bool):
                lst = list(self._block.config.get("combo_series") or [])
                ni = len(lst)
                dc = cols[min(ni, len(cols) - 1)] if cols else ""
                ch = pal[ni % len(pal)]
                if is_formula:
                    lst.append({"name": f"Формула S{ni + 1}", "source_type": "formula", "col": "", "formula": "S1 - S2", "agg": "sum", "plot_type": "spline", "y_axis": "y1", "color": ch, "line_dash": "solid", "line_width": 3, "marker_size": 8, "opacity": 1.0, "show_labels": True, "suffix": "", "visible": True})
                else:
                    lst.append({"name": _clean_col_label(dc) or f"Серия {ni + 1}", "source_type": "column", "col": dc, "formula": "", "agg": "sum", "plot_type": "line" if ni > 0 else "bar", "y_axis": "y1", "color": ch, "line_dash": "solid", "line_width": 3, "marker_size": 8, "opacity": 0.9 if ni == 0 else 1.0, "show_labels": True, "suffix": "", "visible": True})
                _save_series(lst, rebuild=True)

            btn_c.clicked.connect(lambda: _add_s(False))
            btn_f.clicked.connect(lambda: _add_s(True))
            add_row.addWidget(btn_c, 1)
            add_row.addWidget(btn_f, 1)
            self._add_row(add_row)

        with self._section_box("Иерархия погружения (3 уровня)", "cmb_drill", expanded=False):
            self._field_col("Уровень 1 — Группа", "combo_level1_col", cfg, cols, "⚡ Авто (1-я категория)")
            self._field_combo("Сортировка Уровня 1", "combo_level1_sort", cfg, _LEVEL_SORT_MODES, "value_desc")
            self._field_col("Уровень 2 — Подкатегория", "combo_level2_col", cfg, cols, "⚡ Авто", allow_disable=True)
            self._field_combo("Сортировка Уровня 2", "combo_level2_sort", cfg, _LEVEL_SORT_MODES, "value_desc")
            self._field_col("Уровень 3 — Объект / ID", "combo_level3_col", cfg, cols, "⚡ Авто", allow_disable=True)
            self._field_combo("Сортировка Уровня 3", "combo_level3_sort", cfg, _LEVEL_SORT_MODES, "value_desc")
            self._field_col("Период / Дата (кнопки месяцев)", "date_col", cfg, cols, "— Без кнопок месяцев —")

        with self._section_box("Базовые переменные А и Б", "cmb_ab", expanded=False):
            self._field_col("Показатель А (переменная A / ФАКТ)", "fact_col", cfg, cols, "⚡ Авто")
            self._field_col("Показатель Б (переменная B / НОРМА)", "norm_col", cfg, cols, "⚡ Авто")

    def _build_combo_series_card(self, idx_s: int, s_item: dict, series_list: list, cols: list[str], save_cb):
        s_color = str(s_item.get("color") or "#2b7fff")
        s_name_cur = str(s_item.get("name") or s_item.get("col") or f"Серия {idx_s + 1}")
        short_title = f"S{idx_s + 1} · {_clean_col_label(s_name_cur)[:20]}"

        with self._section_box(short_title, f"cmb_card_{idx_s}", expanded=(idx_s < 2)):
            top_r = QHBoxLayout()
            top_r.setSpacing(4)
            chk_vis = QCheckBox("👁 Показывать")
            chk_vis.setChecked(bool(s_item.get("visible", True)))
            chk_vis.setStyleSheet(f"QCheckBox {{ color:{self.theme.text_main}; font-size:10.5px; background:transparent; }}")
            top_r.addWidget(chk_vis, 1)

            btn_up = QPushButton("⬆")
            btn_dn = QPushButton("⬇")
            btn_del = QPushButton("✕")
            for b in (btn_up, btn_dn, btn_del):
                b.setFixedWidth(24)
                self._style_input(b)
            btn_up.setEnabled(idx_s > 0)
            btn_dn.setEnabled(idx_s < len(series_list) - 1)

            def _upd(key, val, reb=False):
                lst = list(self._block.config.get("combo_series") or [])
                if idx_s < len(lst):
                    lst[idx_s][key] = val
                    save_cb(lst, reb)

            def _move(delta):
                lst = list(self._block.config.get("combo_series") or [])
                ni = idx_s + delta
                if 0 <= ni < len(lst):
                    lst[idx_s], lst[ni] = lst[ni], lst[idx_s]
                    save_cb(lst, True)

            def _del():
                lst = [x for j, x in enumerate(list(self._block.config.get("combo_series") or [])) if j != idx_s]
                save_cb(lst, True)

            chk_vis.toggled.connect(lambda v: _upd("visible", bool(v)))
            btn_up.clicked.connect(lambda: _move(-1))
            btn_dn.clicked.connect(lambda: _move(1))
            btn_del.clicked.connect(_del)
            top_r.addWidget(btn_up)
            top_r.addWidget(btn_dn)
            top_r.addWidget(btn_del)
            self._add_row(top_r)

            cb_pt = QComboBox()
            for lbl, val in [
                ("📊 Столбцы (Bar)", "bar"),
                ("📉 Линия с точками (Line)", "line"),
                ("🌊 Плавная кривая (Spline)", "spline"),
                ("⛰ Область (Area)", "area"),
                ("📐 Ступенчатая (Step)", "step"),
                ("🔵 Точки (Scatter)", "scatter"),
                ("📈 Нарастающий — Линия", "cum_line"),
                ("🧱 Нарастающий — Столбцы", "cum_bar"),
            ]:
                cb_pt.addItem(lbl, val)
            cb_pt.setCurrentIndex(max(0, cb_pt.findData(str(s_item.get("plot_type", "bar") or "bar"))))
            self._style_combo(cb_pt)
            cb_pt.currentIndexChanged.connect(lambda i: _upd("plot_type", cb_pt.itemData(i)))
            self._add_widget(cb_pt)

            cb_src = QComboBox()
            cb_src.addItem("🧮 Математическая формула (S1, S2, A, B...)", "__FORMULA__")
            for c in cols:
                cb_src.addItem(f"📋 {_clean_col_label(c)}", str(c))
            is_form = str(s_item.get("source_type", "column")) == "formula"
            cur_v = "__FORMULA__" if is_form else str(s_item.get("col", "") or "")
            idx_src = cb_src.findData(cur_v)
            cb_src.setCurrentIndex(idx_src if idx_src >= 0 else (1 if cb_src.count() > 1 else 0))
            self._style_combo(cb_src)

            def _on_src(i):
                v = cb_src.itemData(i)
                lst = list(self._block.config.get("combo_series") or [])
                if idx_s < len(lst):
                    if v == "__FORMULA__":
                        lst[idx_s]["source_type"] = "formula"
                        if not lst[idx_s].get("formula"):
                            lst[idx_s]["formula"] = "A - B"
                    else:
                        lst[idx_s]["source_type"] = "column"
                        lst[idx_s]["col"] = v
                        lst[idx_s]["name"] = _clean_col_label(v)
                    save_cb(lst, True)

            cb_src.currentIndexChanged.connect(_on_src)
            self._add_widget(cb_src)

            if is_form:
                ed_f = QLineEdit(str(s_item.get("formula", "A - B") or "A - B"))
                ed_f.setPlaceholderText("Напр.: A - B  или  ((A - B) / B) * 100")
                ed_f.setStyleSheet(
                    f"background:{self.theme.bg_card}; color:{self.theme.text_main}; "
                    f"border:1px solid {self.theme.primary}; border-radius:4px; "
                    f"padding:5px 7px; font-size:12px; font-family:'Consolas','Courier New',monospace;"
                )
                ed_f.textChanged.connect(lambda t: _upd("formula", t))
                self._add_widget(ed_f)

                chip_r = QHBoxLayout()
                chip_r.setSpacing(3)
                for tok in ("A", "B", "S1", "S2", "abs()", "if(; ; )"):
                    b = QPushButton(tok)
                    b.setCursor(Qt.PointingHandCursor)
                    self._style_chip(b)
                    b.clicked.connect(lambda _, tk=tok: ed_f.insert(tk))
                    chip_r.addWidget(b)
                self._add_row(chip_r)

                cb_fp = QComboBox()
                cb_fp.addItem("⚡ Шаблон формулы…", "")
                cb_fp.addItem("Разность: A − B", "A - B")
                cb_fp.addItem("% отклонения: ((A − B) / B) × 100", "((A - B) / B) * 100")
                cb_fp.addItem("% выполнения: (A / B) × 100", "(A / B) * 100")
                cb_fp.addItem("Условие: if(A > B; A − B; 0)", "if(A > B; A - B; 0)")
                cb_fp.addItem("Разность серий: S1 − S2", "S1 - S2")
                self._style_combo(cb_fp)
                cb_fp.currentIndexChanged.connect(lambda i: ed_f.setText(cb_fp.itemData(i)) if cb_fp.itemData(i) else None)
                self._add_widget(cb_fp)
            else:
                cb_agg = QComboBox()
                for lbl, val in _AGG_FUNCS:
                    cb_agg.addItem(lbl, val)
                cb_agg.setCurrentIndex(max(0, cb_agg.findData(str(s_item.get("agg", "sum") or "sum"))))
                self._style_combo(cb_agg)
                cb_agg.currentIndexChanged.connect(lambda i: _upd("agg", cb_agg.itemData(i)))
                self._add_widget(cb_agg)

            nc_r = QHBoxLayout()
            nc_r.setSpacing(4)
            ed_n = QLineEdit(s_name_cur)
            ed_n.setPlaceholderText("Название в легенде")
            self._style_input(ed_n)
            ed_n.textChanged.connect(lambda t: _upd("name", t))

            ed_suf = QLineEdit(str(s_item.get("suffix", "") or ""))
            ed_suf.setPlaceholderText("Ед.")
            ed_suf.setFixedWidth(48)
            self._style_input(ed_suf)
            ed_suf.textChanged.connect(lambda t: _upd("suffix", t))

            btn_c = QPushButton("🎨")
            btn_c.setFixedWidth(28)
            btn_c.setStyleSheet(f"QPushButton {{ background:{s_color}; color:#fff; border:1px solid {self.theme.border}; border-radius:4px; padding:3px; }}")

            def _pick_c():
                c = QColorDialog.getColor(QColor(s_color), self, "Цвет серии")
                if c.isValid():
                    _upd("color", c.name(), reb=True)

            btn_c.clicked.connect(_pick_c)
            nc_r.addWidget(ed_n, 1)
            nc_r.addWidget(ed_suf)
            nc_r.addWidget(btn_c)
            self._add_row(nc_r)

            ad_r = QHBoxLayout()
            ad_r.setSpacing(4)
            cb_ax = QComboBox()
            cb_ax.addItem("Ось Y (слева)", "y1")
            cb_ax.addItem("Ось Y2 (справа)", "y2")
            cb_ax.setCurrentIndex(max(0, cb_ax.findData(str(s_item.get("y_axis", "y1") or "y1"))))
            self._style_combo(cb_ax)
            cb_ax.currentIndexChanged.connect(lambda i: _upd("y_axis", cb_ax.itemData(i)))

            cb_d = QComboBox()
            for lbl, val in [("Сплошная", "solid"), ("Штрих", "dash"), ("Точки", "dot"), ("Штрих-пунктир", "dashdot")]:
                cb_d.addItem(lbl, val)
            cb_d.setCurrentIndex(max(0, cb_d.findData(str(s_item.get("line_dash", "solid") or "solid"))))
            self._style_combo(cb_d)
            cb_d.currentIndexChanged.connect(lambda i: _upd("line_dash", cb_d.itemData(i)))

            ad_r.addWidget(cb_ax, 1)
            ad_r.addWidget(cb_d, 1)
            self._add_row(ad_r)

            opt_r = QHBoxLayout()
            opt_r.setSpacing(4)
            chk_l = QCheckBox("Числа")
            chk_l.setChecked(bool(s_item.get("show_labels", True)))
            chk_l.setStyleSheet(f"QCheckBox {{ color:{self.theme.text_main}; font-size:10.5px; background:transparent; }}")
            chk_l.toggled.connect(lambda v: _upd("show_labels", bool(v)))

            sp_w = QSpinBox()
            sp_w.setRange(1, 10)
            sp_w.setPrefix("Лин: ")
            sp_w.setValue(int(s_item.get("line_width", 3) or 3))
            self._style_input(sp_w)
            sp_w.valueChanged.connect(lambda v: _upd("line_width", int(v)))

            sp_m = QSpinBox()
            sp_m.setRange(0, 20)
            sp_m.setPrefix("Точ: ")
            sp_m.setValue(int(s_item.get("marker_size", 8) if "marker_size" in s_item else 8))
            self._style_input(sp_m)
            sp_m.valueChanged.connect(lambda v: _upd("marker_size", int(v)))

            opt_r.addWidget(chk_l)
            opt_r.addWidget(sp_w, 1)
            opt_r.addWidget(sp_m, 1)
            self._add_row(opt_r)

    # ── Секции данных для режима «По строкам» ──
    def _build_row_mode_sections(self, cfg: dict, cols: list[str], is_pie: bool = False):
        if not cols:
            self._add_hint("Сначала загрузите таблицу.")
            return

        with self._section_box("Настройки по строкам", "row_mode_main", expanded=True):
            cur_x = cfg.get("x_col", "") or cols[0]
            self._field_col("Столбец названий строк (категорий)", "x_col", cfg, cols, "⚡ Авто", rebuild=True)

            cb_rt = QComboBox()
            cb_rt.addItem("📊 Итог + переключение Срезом", "__ALL_SERIES__")
            cb_rt.addItem("Σ Сумма по всем строкам", "__SUM__")
            cb_rt.addItem("⌀ Среднее по всем строкам", "__MEAN__")
            tdf = self._get_target_dataframe(cfg)
            if tdf is not None and cur_x in tdf.columns:
                for rv in tdf[cur_x].dropna().astype(str).unique()[:100]:
                    rs = rv.strip()
                    if rs:
                        cb_rt.addItem(f"📌 {rs}", rs)
            cb_rt.setCurrentIndex(max(0, cb_rt.findData(cfg.get("row_target_val", "__ALL_SERIES__"))))
            self._style_combo(cb_rt)
            cb_rt.currentIndexChanged.connect(lambda i: self._change_block("row_target_val", cb_rt.itemData(i)))
            self._add_label("Какие строки отображать")
            self._add_widget(cb_rt)

            self._field_checkbox("Оставлять на оси X префикс до '_'", "clean_col_labels", cfg, True)

            if is_pie:
                self._field_combo(
                    "Режим круговой по строкам",
                    "pie_row_mode",
                    cfg,
                    [
                        ("📊 Доли = Категории (с детализацией)", "models_with_months"),
                        ("📅 Отдельный круг на период", "subplots_by_month"),
                        ("📆 Доли = Периоды", "slices_are_months"),
                    ],
                    "models_with_months",
                )

            avail_cols = [c for c in cols if c != cur_x]
            self._build_multi_col_checklist("row_columns", cfg, avail_cols, allow_suffix_picker=True)

        if not is_pie:
            with self._section_box("Объединение столбцов периода", "row_mode_comb", expanded=False):
                self._field_combo(
                    "Режим мульти-столбцов",
                    "row_multi_mode",
                    cfg,
                    [("📊 Раздельные серии", "separate"), ("🧮 Объединить функцией", "combined")],
                    "separate",
                )
                self._field_combo(
                    "Функция объединения",
                    "row_multi_func",
                    cfg,
                    [("Сумма", "sum"), ("Разность", "sub"), ("Произведение", "mul"), ("Деление", "div"), ("Среднее", "mean")],
                    "sum",
                )

    # ============================================================
    # 2. СВОДНАЯ МАТРИЦА (Данные / Формулы / Вид / Макет)
    # ============================================================

    def _build_pivot_tabs(self, cfg: dict):
        tab_data = self._add_tab("data", "Данные")
        tab_calc = self._add_tab("calc", "Формулы")
        tab_view = self._add_tab("view", "Вид")
        tab_lay = self._add_tab("layout", "Макет")

        with self._use_layout(tab_data):
            with self._section_box("Источник и заголовок", "piv_src", expanded=True):
                self._build_source_selectors(cfg)
                cols = self._get_target_columns(cfg)
                self._field_text("Заголовок", "title", cfg, placeholder="Сводная матрица")

            with self._section_box("Иерархия строк и столбцы", "piv_hier", expanded=True):
                self._field_col("Строки — Уровень 1 (Группа)", "row_group_col", cfg, cols, "⚡ Авто")
                self._field_col("Раскрытие — Уровень 2 (Подгруппа)", "row_level2_col", cfg, cols, "⚡ Авто", allow_disable=True)
                self._field_col("Раскрытие — Уровень 3 (Объект / ID)", "row_level3_col", cfg, cols, "⚡ Авто", allow_disable=True)
                self._field_col("Столбцы по горизонтали (Период / Категория)", "col_group_col", cfg, cols, "— Без разбивки —")

            with self._section_box("Показатели", "piv_vals", expanded=True):
                self._field_col("Основной показатель (А / C1)", "value_col", cfg, cols, "⚡ Авто")
                self._field_combo("Агрегация", "agg_func", cfg, _PIVOT_AGG_FUNCS, "sum")
                self._add_label("Дополнительные показатели (B / C2, C / C3...)")
                self._build_multi_col_checklist("value_cols", cfg, cols, height=110)

        with self._use_layout(tab_calc):
            with self._section_box("Вычисляемые столбцы", "piv_calcs", expanded=True):
                self._add_hint("Переменные: A (C1), B (C2), C (C3) или точные имена столбцов.")
                cur_calcs = list(cfg.get("calc_cols") or [])
                for idx_cc, cc in enumerate(cur_calcs):
                    if not isinstance(cc, dict):
                        continue
                    r = QHBoxLayout()
                    r.setSpacing(4)
                    lbl = QLabel(f"🧮 <b>{cc.get('name', 'Расчёт')}</b> = <code>{cc.get('formula', '')}</code>" + (" (%)" if cc.get("is_pct") else ""))
                    lbl.setWordWrap(True)
                    lbl.setStyleSheet(f"color:{self.theme.text_main}; font-size:10.5px; background:transparent;")
                    r.addWidget(lbl, 1)
                    b_del = QPushButton("✕")
                    b_del.setFixedWidth(24)
                    self._style_input(b_del)

                    def _rem(ri=idx_cc):
                        if self._block is None:
                            return
                        self._block.config["calc_cols"] = [x for j, x in enumerate(list(self._block.config.get("calc_cols") or [])) if j != ri]
                        self.config_changed.emit(self._block.id)
                        self._rebuild_later()

                    b_del.clicked.connect(_rem)
                    r.addWidget(b_del)
                    self._add_row(r)

                cb_p = QComboBox()
                for t, n, f, is_p in [
                    ("⚡ Быстрый шаблон формулы…", "", "", False),
                    ("Разность: А − Б", "Отклонение (А−Б)", "A - B", False),
                    ("Разность: Б − А", "Снижение (Б−А)", "B - A", False),
                    ("% отклонения: ((А − Б) / Б) × 100%", "% отклонения", "((A - B) / B) * 100", True),
                    ("% выполнения: (А / Б) × 100%", "% от базы", "(A / B) * 100", True),
                    ("Сумма: А + Б", "Сумма (А+Б)", "A + B", False),
                    ("Отношение: А / Б", "Отношение", "A / B", False),
                ]:
                    cb_p.addItem(t, (n, f, is_p))
                self._style_combo(cb_p)
                self._add_widget(cb_p)

                ed_n = QLineEdit()
                ed_n.setPlaceholderText("Название столбца")
                self._style_input(ed_n)
                self._add_widget(ed_n)

                ed_f = QLineEdit()
                ed_f.setPlaceholderText("Формула: A - B  или  ((A - B) / B) * 100")
                self._style_input(ed_f)
                self._add_widget(ed_f)

                chk_p = QCheckBox("Выводить со знаком %")
                chk_p.setStyleSheet(f"QCheckBox {{ color:{self.theme.text_main}; font-size:11px; background:transparent; }}")
                self._add_widget(chk_p)

                def _on_pre(i):
                    d = cb_p.itemData(i)
                    if d and d[1]:
                        ed_n.setText(d[0])
                        ed_f.setText(d[1])
                        chk_p.setChecked(bool(d[2]))

                cb_p.currentIndexChanged.connect(_on_pre)

                btn_add = QPushButton("➕ Добавить столбец")
                btn_add.setCursor(Qt.PointingHandCursor)
                btn_add.setStyleSheet(
                    f"QPushButton {{ background:{self.theme.bg_card}; color:{self.theme.primary}; "
                    f"border:1px solid {self.theme.primary}; border-radius:5px; padding:6px; font-size:11px; font-weight:700; }}"
                )

                def _add_cc():
                    if self._block is None or not ed_f.text().strip():
                        return
                    lst = list(self._block.config.get("calc_cols") or [])
                    lst.append({"name": ed_n.text().strip() or ed_f.text().strip(), "formula": ed_f.text().strip(), "is_pct": chk_p.isChecked()})
                    self._block.config["calc_cols"] = lst
                    self.config_changed.emit(self._block.id)
                    self._rebuild_later()

                btn_add.clicked.connect(_add_cc)
                self._add_widget(btn_add)

            with self._section_box("Поиск и связь с таблицей", "piv_link", expanded=False):
                self._field_checkbox("🔍 Поиск в шапке матрицы", "show_search", cfg, True)
                tbl_items = [("🌐 Все таблицы отчёта (Авто)", ""), ("🚫 Не фильтровать таблицы", "__NONE__")]
                for tb in self._collect_report_blocks("data_table"):
                    tid = tb.get("id", "") if isinstance(tb, dict) else getattr(tb, "id", "")
                    tcfg = tb.get("config", {}) if isinstance(tb, dict) else (getattr(tb, "config", {}) or {})
                    tbl_items.append((f"📋 {tcfg.get('title') or 'Таблица данных'} ({str(tid)[:4]})", str(tid)))
                self._field_combo("Связанная таблица данных", "target_table", cfg, tbl_items, "")

                btn_sp = QPushButton("➕ Создать связанную таблицу ниже")
                btn_sp.setCursor(Qt.PointingHandCursor)
                btn_sp.setStyleSheet(
                    f"QPushButton {{ background:{self.theme.primary}; color:{self.theme.text_inverse}; "
                    f"border:none; border-radius:5px; padding:6px; font-size:10.5px; font-weight:700; }}"
                )
                btn_sp.clicked.connect(self._spawn_linked_data_table)
                self._add_widget(btn_sp)

        with self._use_layout(tab_view):
            with self._section_box("Цветовая индикация (+ / −)", "piv_col", expanded=True):
                self._field_checkbox("🎨 Подсвечивать знаки чисел", "color_calc_enabled", cfg, False)
                self._field_combo(
                    "Область подсветки",
                    "color_calc_scope",
                    cfg,
                    [
                        ("Формулы и столбцы отклонений", "calc_and_dev"),
                        ("Только вычисляемые столбцы", "calc_only"),
                        ("Все числовые столбцы", "all_cols"),
                    ],
                    "calc_and_dev",
                )
                self._field_color("Цвет отрицательных (< 0)", "neg_color", cfg, "#16a34a")
                self._field_color("Цвет положительных (> 0)", "pos_color", cfg, "#dc2626")
                self._field_checkbox("Мягкая заливка фона ячейки", "color_calc_bg", cfg, True)

            with self._section_box("Отображение и прокрутка", "piv_disp", expanded=True):
                self._field_checkbox("📌 Закрепить шапку", "sticky_header", cfg, True)
                self._field_checkbox("📌 Закрепить 1-й столбец", "sticky_first_col", cfg, True)
                self._field_checkbox("Показывать «Итого»", "show_totals", cfg, True)
                self._field_spin_pair(
                    ("Макс. высота (px)", "max_table_height", 520, 0, 3000),
                    ("Топ групп (Ур. 1)", "top_n", 30, 5, 500),
                    cfg,
                )

        with self._use_layout(tab_lay):
            self._build_layout_controls(cfg)

    def _spawn_linked_data_table(self):
        if self._block is None or not getattr(self, "report_ref", None):
            return
        from src.core.report_model import ReportBlock
        found = self.report_ref.find_block_parent(self._block.id)
        if not found:
            return
        _sec, parent_list, piv_blk = found
        piv_cfg = dict(piv_blk.config or {})
        new_tbl = ReportBlock.create(
            "data_table",
            {
                "title": "Детальный реестр данных",
                "source_file_name": piv_cfg.get("source_file_name", ""),
                "source_sheet": piv_cfg.get("source_sheet", ""),
                "max_rows": 20,
                "width": 100,
                "align": "left",
                "offset_x": 0,
            },
        )
        parent_list.insert(parent_list.index(piv_blk) + 1, new_tbl)
        piv_cfg["target_table"] = new_tbl.id
        piv_blk.config = piv_cfg
        self.config_changed.emit(piv_blk.id)
        self._rebuild_later()

    # ============================================================
    # 3. ФИЛЬТР / СРЕЗ (Настройки / Макет)
    # ============================================================

    def _build_filter_tabs(self, cfg: dict):
        tab_main = self._add_tab("data", "Настройки")
        tab_lay = self._add_tab("layout", "Макет")

        with self._use_layout(tab_main):
            with self._section_box("Источник и колонка", "flt_src", expanded=True):
                self._build_source_selectors(cfg)
                cols = self._get_target_columns(cfg)
                self._field_text("Заголовок фильтра", "title", cfg, placeholder="Например: Категория")
                self._field_col("Колонка для среза", "filter_col", cfg, cols, "— Выберите колонку —")

            with self._section_box("Привязка к графикам", "flt_bind", expanded=True):
                charts = self._collect_report_blocks("plotly_chart")
                chart_items = [("🌐 Все графики отчёта", "")]
                for ch in charts:
                    cid = ch.get("id", "") if isinstance(ch, dict) else getattr(ch, "id", "")
                    ccfg = ch.get("config", {}) if isinstance(ch, dict) else (getattr(ch, "config", {}) or {})
                    chart_items.append((f"📊 {ccfg.get('title') or 'График'} ({str(cid)[:4]})", str(cid)))

                cb_t = self._field_combo("Основной график", "target_chart", cfg, chart_items, "")

                def _sync_filter_targets():
                    if self._block is None:
                        return
                    nc = dict(self._block.config or {})
                    main_id = str(nc.get("target_chart", "") or "").strip()
                    extras = [p.strip() for p in str(nc.get("extra_target_charts", "") or "").split(",") if p.strip()]
                    merged = ([main_id] if main_id else []) + [x for x in extras if x != main_id]
                    nc["target_charts"] = merged
                    self._block.config = nc

                cb_t.currentIndexChanged.connect(lambda _: _sync_filter_targets())

                self._add_label("Дополнительные графики (ID через запятую)")
                row_ex = QHBoxLayout()
                row_ex.setSpacing(4)
                ed_ex = QLineEdit(str(cfg.get("extra_target_charts", "") or ""))
                ed_ex.setPlaceholderText("ID графиков через запятую...")
                self._style_input(ed_ex)
                row_ex.addWidget(ed_ex, 1)

                btn_clr = QPushButton("✕")
                btn_clr.setFixedWidth(26)
                self._style_input(btn_clr)
                row_ex.addWidget(btn_clr)
                self._add_row(row_ex)

                cb_add = QComboBox()
                cb_add.addItem("➕ Подключить ещё график…", "")
                for lbl, cid in chart_items[1:]:
                    cb_add.addItem(f"+ {lbl}", cid)
                self._style_combo(cb_add)
                self._add_widget(cb_add)

                def _add_ex(i):
                    cid = cb_add.itemData(i)
                    if not cid:
                        return
                    parts = [p.strip() for p in ed_ex.text().split(",") if p.strip()]
                    if cid not in parts and cid != cb_t.currentData():
                        parts.append(cid)
                    csv = ", ".join(parts)
                    ed_ex.blockSignals(True)
                    ed_ex.setText(csv)
                    ed_ex.blockSignals(False)
                    cb_add.blockSignals(True)
                    cb_add.setCurrentIndex(0)
                    cb_add.blockSignals(False)
                    self._change_block("extra_target_charts", csv)
                    _sync_filter_targets()

                cb_add.currentIndexChanged.connect(_add_ex)
                btn_clr.clicked.connect(lambda: (ed_ex.setText(""), self._change_block("extra_target_charts", ""), _sync_filter_targets()))
                ed_ex.textChanged.connect(lambda v: (self._change_block("extra_target_charts", v), _sync_filter_targets()))

            with self._section_box("Высота и прокрутка", "flt_scroll", expanded=False):
                self._field_checkbox("🔄 Синхронизировать высоту с графиком", "sync_height", cfg, True)
                self._field_int("Макс. высота списка (px, 0 = авто)", "max_height", cfg, default=420, min_val=0, max_val=2000)

        with self._use_layout(tab_lay):
            self._build_layout_controls(cfg)

    # ============================================================
    # 4. ТАБЛИЦА ДАННЫХ (Данные / Макет)
    # ============================================================

    def _build_table_tabs(self, cfg: dict):
        tab_data = self._add_tab("data", "Данные")
        tab_lay = self._add_tab("layout", "Макет")

        with self._use_layout(tab_data):
            with self._section_box("Источник и параметры", "tbl_src", expanded=True):
                self._build_source_selectors(cfg)
                cols = self._get_target_columns(cfg)
                self._all_columns = cols
                self._field_text("Заголовок таблицы", "title", cfg, placeholder="Таблица данных")
                self._field_int("Видимых строк в окне", "max_rows", cfg, default=20, min_val=0, max_val=10000)

            with self._section_box(f"Отображаемые колонки ({len(cols)})", "tbl_cols", expanded=True):
                self._build_multi_col_checklist("visible_columns", cfg, cols, height=190, default_all=True)

        with self._use_layout(tab_lay):
            self._build_layout_controls(cfg)

    # ============================================================
    # 5. ПАРАГРАФ (Текст / Данные / Макет)
    # ============================================================

    def _build_paragraph_tabs(self, cfg: dict):
        tab_txt = self._add_tab("text", "Текст")
        tab_data = self._add_tab("data", "Данные")
        tab_lay = self._add_tab("layout", "Макет")

        with self._use_layout(tab_txt):
            with self._section_box("Оформление", "p_style", expanded=True):
                self._build_font_and_align_row(cfg, default_size=14)
                self._add_hint("💡 Двойной клик на блоке открывает расширенный редактор.")

            with self._section_box("Динамический шаблон и макросы", "p_tpl", expanded=True):
                txt_edit = QTextEdit()
                txt_edit.setPlainText(str(cfg.get("text", "")))
                txt_edit.setFixedHeight(125)
                txt_edit.setPlaceholderText("{{ group }} | {{ month }} — Факт: {{ fact }}, План: {{ norm }} ({{ pct }}%)")
                self._style_input(txt_edit)

                def _on_txt():
                    if self._block is None:
                        return
                    nc = dict(self._block.config or {})
                    nc["text"] = txt_edit.toPlainText()
                    nc["raw_html"] = False
                    self._block.config = nc
                    self.config_changed.emit(self._block.id)

                txt_edit.textChanged.connect(_on_txt)
                self._add_widget(txt_edit)

                r1 = QHBoxLayout()
                r1.setSpacing(3)
                for lbl_b, tok in (("Группа", "{{ group }}"), ("Период", "{{ month }}"), ("Факт (A)", "{{ fact }}"), ("База (B)", "{{ norm }}"), ("Разница", "{{ diff }}"), ("%", "{{ pct }}%")):
                    b = QPushButton(lbl_b)
                    b.setCursor(Qt.PointingHandCursor)
                    self._style_chip(b)
                    b.clicked.connect(lambda _, tk=tok: txt_edit.insertPlainText(tk))
                    r1.addWidget(b)
                self._add_row(r1)

                btn_tpl = QPushButton("⚡ Вставить шаблон умного вывода (ЕСЛИ)")
                btn_tpl.setCursor(Qt.PointingHandCursor)
                btn_tpl.setStyleSheet(
                    f"QPushButton {{ background:{self.theme.bg_card}; color:{self.theme.primary}; "
                    f"border:1px solid {self.theme.primary}; border-radius:4px; padding:5px; font-size:10px; font-weight:700; }}"
                )
                smart_tpl = (
                    "📊 Аналитический вывод ({{ group }} — {{ month }}):\n"
                    "• Показатель А: {{ fact }} | Показатель Б: {{ norm }} (записей: {{ count }})\n"
                    "• Итог: {{ if(pct > 0; '⚠ Превышение на ' + abs_pct + '% (+' + abs_diff + ')'; "
                    "if(pct < 0; '✅ Снижение на ' + abs_pct + '% (-' + abs_diff + ')'; 'В пределах базы (0%)')) }}\n"
                    "• Лидер по вкладу: {{ top_name }} ({{ top_pct }}%)"
                )
                btn_tpl.clicked.connect(lambda: txt_edit.setPlainText(smart_tpl))
                self._add_widget(btn_tpl)

        with self._use_layout(tab_data):
            with self._section_box("Источник и привязка", "p_src", expanded=True):
                self._build_source_selectors(cfg)
                cols = self._get_target_columns(cfg)
                charts = self._collect_report_blocks("plotly_chart")
                c_items = [("— Настроить колонки вручную —", "")]
                for ch in charts:
                    cid = ch.get("id", "") if isinstance(ch, dict) else getattr(ch, "id", "")
                    ccfg = ch.get("config", {}) if isinstance(ch, dict) else (getattr(ch, "config", {}) or {})
                    c_items.append((f"📊 {ccfg.get('title') or 'График'} ({str(cid)[:4]})", str(cid)))
                self._field_combo("Синхронизация с графиком", "target_chart", cfg, c_items, "")

            with self._section_box("Поля расчёта (опционально)", "p_cols", expanded=False):
                self._field_col("Группа (Уровень 1)", "parent_group_col", cfg, cols, "— Авто из графика —")
                self._field_col("Подкатегория (Уровень 2)", "model_col", cfg, cols, "— Авто из графика —")
                self._field_col("Дата / Период", "date_col", cfg, cols, "— Авто из графика —")
                self._field_col("Переменная A (Факт)", "fact_col", cfg, cols, "— Авто из графика —")
                self._field_col("Переменная B (База / План)", "norm_col", cfg, cols, "— Авто из графика —")

        with self._use_layout(tab_lay):
            self._build_layout_controls(cfg)

    # ============================================================
    # 6. ДЕКОМПОЗИЦИЯ И ГЕО-КАРТА (Данные / Вид / Макет)
    # ============================================================

    def _build_visual_block_tabs(self, b_type: str, cfg: dict):
        tab_data = self._add_tab("data", "Данные")
        tab_view = self._add_tab("view", "Вид")
        tab_lay = self._add_tab("layout", "Макет")

        with self._use_layout(tab_data):
            with self._section_box("Источник и поля", f"{b_type}_src", expanded=True):
                self._build_source_selectors(cfg)
                cols = self._get_target_columns(cfg)
                def_t = "Дерево декомпозиции" if b_type == "decomposition" else "География и рейтинг"
                self._field_text("Заголовок", "title", cfg, placeholder=def_t)

                if b_type == "decomposition":
                    self._field_combo("Вид иерархии", "tree_mode", cfg, [("🌳 Плитки (Treemap)", "treemap"), ("☀ Кольца (Sunburst)", "sunburst")], "treemap")
                    self._field_col("Уровень 1 — Группа", "level1_col", cfg, cols, "⚡ Авто")
                    self._field_col("Уровень 2 — Подгруппа", "level2_col", cfg, cols, "— Не выбран —")
                    self._field_col("Уровень 3 — Объект / ID", "level3_col", cfg, cols, "— Не выбран —")
                    self._field_col("Числовой показатель (Вес)", "value_col", cfg, cols, "⚡ Авто")
                    self._field_combo("Агрегация", "agg_func", cfg, [("Сумма", "sum"), ("Среднее", "mean"), ("Количество", "count")], "sum")
                else:
                    self._field_combo(
                        "Режим отображения",
                        "map_mode",
                        cfg,
                        [("📊 Рейтинг (Bar)", "ranking_bar"), ("🗺 Тепловая плитка (Treemap)", "treemap"), ("🌍 Карта стран (Choropleth)", "choropleth")],
                        "ranking_bar",
                    )
                    self._field_col("Колонка локации / объекта", "loc_col", cfg, cols, "⚡ Авто")
                    self._field_col("Числовой показатель", "value_col", cfg, cols, "⚡ Авто")
                    self._field_combo("Агрегация", "agg_func", cfg, [("Сумма", "sum"), ("Среднее", "mean"), ("Количество", "count"), ("Максимум", "max")], "sum")
                    self._field_int("Количество объектов (Топ N)", "top_n", cfg, default=20, min_val=5, max_val=200)

        with self._use_layout(tab_view):
            with self._section_box("Цветовая схема", f"{b_type}_pal", expanded=True):
                self._field_combo(
                    "Палитра",
                    "palette",
                    cfg,
                    [("🌿 Изумрудная (Greens)", "Greens"), ("🌊 Синяя (Blues)", "Blues"), ("🔮 Контрастная (Viridis)", "Viridis"), ("🔥 Тепловая (YlOrRd)", "YlOrRd")],
                    "Greens",
                )

        with self._use_layout(tab_lay):
            self._build_layout_controls(cfg)

    # ============================================================
    # 7. ПРОСТЫЕ БЛОКИ (Заголовок, Список, KPI, Контейнер)
    # ============================================================

    def _build_text_block_tabs(self, b_type: str, cfg: dict):
        tab_main = self._add_tab("main", "Оформление")
        tab_lay = self._add_tab("layout", "Макет")
        with self._use_layout(tab_main):
            with self._section_box("Шрифт и выравнивание", "txt_style", expanded=True):
                self._build_font_and_align_row(cfg, default_size=24 if b_type == "section_title" else 14)
                self._add_hint("💡 Двойной клик на блоке открывает редактор текста.")
        with self._use_layout(tab_lay):
            self._build_layout_controls(cfg)

    def _build_kpi_tabs(self, cfg: dict):
        tab_main = self._add_tab("main", "Карточки")
        tab_lay = self._add_tab("layout", "Макет")
        with self._use_layout(tab_main):
            with self._section_box("Карточки KPI", "kpi_main", expanded=True):
                self._add_label("Метка [TAB] Значение  ·  «!» в конце — акцент")
                cards = cfg.get("cards") or []
                text = "\n".join(f"{c.get('label', '')}\t{c.get('value', '')}{'  !' if c.get('accent') else ''}" for c in cards)
                e = QTextEdit()
                e.setPlainText(text)
                e.setFixedHeight(110)
                e.setPlaceholderText("Выручка\t1 000 000  !\nКлиентов\t42")
                self._style_input(e)

                def _on_ch():
                    new = []
                    for line in e.toPlainText().split("\n"):
                        if not line.strip():
                            continue
                        parts = line.split("\t") if "\t" in line else [line, ""]
                        lbl, val = parts[0].strip(), parts[1].strip()
                        acc = val.endswith("!")
                        if acc:
                            val = val.rstrip("! ").strip()
                        new.append({"label": lbl, "value": val, "accent": acc})
                    self._change_block("cards", new)

                e.textChanged.connect(_on_ch)
                self._add_widget(e)
        with self._use_layout(tab_lay):
            self._build_layout_controls(cfg)

    def _build_container_tabs(self, block, cfg: dict):
        tab_main = self._add_tab("main", "Сетка")
        tab_lay = self._add_tab("layout", "Макет")
        children = cfg.get("children", [])

        with self._use_layout(tab_main):
            with self._section_box("Расположение в группе", "cnt_grid", expanded=True):
                self._field_combo(
                    "Направление",
                    "layout",
                    cfg,
                    [("↔ В одну строку (Row)", "row"), ("↕ Вертикально (Column)", "column")],
                    "row",
                )
                self._field_int("Отступ между блоками (px)", "gap", cfg, default=14, min_val=0, max_val=100)
                if children:
                    btn_pos = QPushButton(f"📐 Схемы расположения ({len(children)} шт.)")
                    btn_pos.setCursor(Qt.PointingHandCursor)
                    btn_pos.setStyleSheet(
                        f"QPushButton {{ background:{self.theme.primary}; color:{self.theme.text_inverse}; "
                        f"border:none; border-radius:5px; padding:7px; font-size:11px; font-weight:700; }}"
                    )
                    btn_pos.clicked.connect(lambda _, b_ref=block: self._open_container_layout_dialog(b_ref))
                    self._add_widget(btn_pos)

            if children:
                with self._section_box(f"Блоки внутри ({len(children)})", "cnt_kids", expanded=True):
                    self._build_container_children_controls(block, children)

            btn_un = QPushButton("💥 Разъединить контейнер")
            btn_un.setCursor(Qt.PointingHandCursor)
            self._style_input(btn_un)
            btn_un.clicked.connect(lambda _, b_id=block.id: self.unmerge_requested.emit(b_id))
            self._add_widget(btn_un)

        with self._use_layout(tab_lay):
            self._build_layout_controls(cfg)

    # ============================================================
    # 8. ВКЛАДКА «МАКЕТ» (общая для всех блоков)
    # ============================================================

    def _build_layout_controls(self, cfg: dict):
        with self._section_box("Ширина и выравнивание", "lay_pos", expanded=True):
            self._add_label("Ширина блока (% от листа)")
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
            sp.setFixedWidth(64)
            self._style_input(sp)
            self._width_spin = sp

            def _on_w(val: int):
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

            slider.valueChanged.connect(_on_w)
            sp.valueChanged.connect(_on_w)
            row.addWidget(slider, 1)
            row.addWidget(sp)
            self._add_row(row)

            p_row = QHBoxLayout()
            p_row.setSpacing(3)
            for pv in (25, 33, 50, 75, 100):
                b = QPushButton(f"{pv}%")
                b.setCursor(Qt.PointingHandCursor)
                self._style_chip(b)
                b.clicked.connect(lambda _, v=pv: _on_w(v))
                p_row.addWidget(b)
            self._add_row(p_row)

            self._add_label("Положение и сдвиг X")
            a_row = QHBoxLayout()
            a_row.setSpacing(4)
            cb_a = QComboBox()
            for lbl, val in [("⬅ Слева", "left"), ("↔ По центру", "center"), ("➡ Справа", "right"), ("🎯 Сдвиг X", "custom")]:
                cb_a.addItem(lbl, val)
            cb_a.setCurrentIndex(max(0, cb_a.findData(cfg.get("align", "left"))))
            self._style_combo(cb_a)

            sp_off = QSpinBox()
            sp_off.setRange(0, max(0, 100 - current))
            sp_off.setSuffix("%")
            sp_off.setValue(int(cfg.get("offset_x", 0)))
            sp_off.setFixedWidth(64)
            self._style_input(sp_off)
            self._offset_spin = sp_off

            cb_a.currentIndexChanged.connect(lambda i: self._change_block("align", cb_a.itemData(i)))

            def _on_off(v):
                if cb_a.currentData() != "custom" and v > 0:
                    cb_a.blockSignals(True)
                    cb_a.setCurrentIndex(3)
                    cb_a.blockSignals(False)
                    if self._block:
                        self._block.config["align"] = "custom"
                self._change_block("offset_x", int(v))

            sp_off.valueChanged.connect(_on_off)
            a_row.addWidget(cb_a, 1)
            a_row.addWidget(sp_off)
            self._add_row(a_row)

        with self._section_box("Высота и отступы (px)", "lay_pad", expanded=True):
            self._height_spin = self._field_int("Минимальная высота (px, 0 = авто)", "min_height", cfg, default=0, min_val=0, max_val=2000)
            self._field_spin_pair(
                ("Отступ сверху (px)", "margin_top", 0, 0, 200),
                ("Отступ снизу (px)", "margin_bottom", 14, 0, 200),
                cfg,
            )

    # ============================================================
    # Общие переиспользуемые виджеты и пул хелперов
    # ============================================================

    def _build_font_and_align_row(self, cfg: dict, default_size: int = 14):
        row = QHBoxLayout()
        row.setSpacing(6)

        w1 = QWidget()
        l1 = QVBoxLayout(w1)
        l1.setContentsMargins(0, 0, 0, 0)
        l1.setSpacing(2)
        l1.addWidget(self._make_label("Размер (px)"))
        sp = QSpinBox()
        sp.setRange(8, 120)
        sp.setValue(int(cfg.get("font_size", default_size)))
        self._style_input(sp)
        sp.valueChanged.connect(lambda v: self._change_block("font_size", int(v)))
        l1.addWidget(sp)
        row.addWidget(w1, 1)

        w2 = QWidget()
        l2 = QVBoxLayout(w2)
        l2.setContentsMargins(0, 0, 0, 0)
        l2.setSpacing(2)
        l2.addWidget(self._make_label("Выравнивание"))
        cb = QComboBox()
        for lbl, val in [("⬅ Слева", "left"), ("↔ По центру", "center"), ("➡ Справа", "right"), ("По ширине", "justify")]:
            cb.addItem(lbl, val)
        cb.setCurrentIndex(max(0, cb.findData(cfg.get("text_align", "left"))))
        self._style_combo(cb)
        cb.currentIndexChanged.connect(lambda i: self._change_block("text_align", cb.itemData(i)))
        l2.addWidget(cb)
        row.addWidget(w2, 2)

        self._add_row(row)

    def _build_chart_link_combo(self, cfg: dict):
        own_id = getattr(self._block, "id", "") if self._block else ""
        items = [("— Не связывать —", "")]
        for ch in self._collect_report_blocks("plotly_chart", exclude_id=own_id):
            cid = ch.get("id", "") if isinstance(ch, dict) else getattr(ch, "id", "")
            ccfg = ch.get("config", {}) if isinstance(ch, dict) else (getattr(ch, "config", {}) or {})
            items.append((f"📊 {ccfg.get('title') or 'График'} ({str(cid)[:4]})", str(cid)))
        self._field_combo("Брать категории из графика", "filter_from_chart", cfg, items, "")

    def _build_column_aliases_editor(self, cfg: dict):
        active_cols: list[str] = []
        for raw_c in str(cfg.get("y_col", "") or "").split(","):
            cc = raw_c.strip()
            if cc and cc not in active_cols:
                active_cols.append(cc)
        for k in ("norm_col", "fact_col"):
            ec = str(cfg.get(k, "") or "").strip()
            if ec and ec not in active_cols:
                active_cols.append(ec)
        if not active_cols:
            return

        self._add_label("Индивидуальное переименование столбцов:")
        cur_aliases = dict(cfg.get("column_aliases") or {})
        for col_orig in active_cols:
            r = QHBoxLayout()
            r.setSpacing(4)
            clean_c = _clean_col_label(col_orig)
            lbl = QLabel(clean_c[:16] + ("…" if len(clean_c) > 16 else ""))
            lbl.setToolTip(col_orig)
            lbl.setStyleSheet(f"color:{self.theme.text_muted}; font-size:10px; min-width:85px; background:transparent;")
            ed = QLineEdit(str(cur_aliases.get(col_orig, "")))
            ed.setPlaceholderText("Новое имя...")
            self._style_input(ed)

            def _on_al(v: str, ck: str = col_orig):
                if self._block is None:
                    return
                nc = dict(self._block.config or {})
                am = dict(nc.get("column_aliases") or {})
                if v.strip():
                    am[ck] = v.strip()
                else:
                    am.pop(ck, None)
                nc["column_aliases"] = am
                self._block.config = nc
                self.config_changed.emit(self._block.id)

            ed.textChanged.connect(_on_al)
            r.addWidget(lbl)
            r.addWidget(ed, 1)
            self._add_row(r)

    def _build_multi_col_checklist(
        self,
        key: str,
        cfg: dict,
        cols: list[str],
        height: int = 140,
        allow_suffix_picker: bool = False,
        default_all: bool = False,
    ):
        if not cols:
            self._add_hint("Сначала загрузите файл данных.")
            return

        raw = cfg.get(key)
        if raw is None:
            sel_set = set(cols) if default_all else set()
        elif isinstance(raw, str):
            sel_set = {x.strip() for x in raw.split(",") if x.strip()}
        else:
            sel_set = set(raw)

        cb_suf = None
        if allow_suffix_picker:
            suffixes = []
            for c in cols:
                if "_" in c:
                    s = c.split("_", 1)[1].strip()
                    if s and s not in suffixes:
                        suffixes.append(s)
            if suffixes:
                cb_suf = QComboBox()
                cb_suf.addItem("⚡ Быстрый выбор по суффиксу…", "")
                for s in suffixes:
                    cb_suf.addItem(f"☑ Все «{s}»", s)
                self._style_combo(cb_suf)
                self._add_widget(cb_suf)

        s_row = QHBoxLayout()
        s_row.setSpacing(4)
        ed_s = QLineEdit()
        ed_s.setPlaceholderText("🔍 Фильтр столбцов...")
        self._style_input(ed_s)
        btn_all = QPushButton("Все")
        btn_clr = QPushButton("Сброс")
        for b in (btn_all, btn_clr):
            b.setFixedWidth(46)
            self._style_input(b)
        s_row.addWidget(ed_s, 1)
        s_row.addWidget(btn_all)
        s_row.addWidget(btn_clr)
        self._add_row(s_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(height)
        scroll.setStyleSheet(f"QScrollArea {{ background:{self.theme.bg_card}; border:1px solid {self.theme.border}; border-radius:4px; }}")
        host = QWidget()
        host.setStyleSheet("background:transparent;")
        v_lay = QVBoxLayout(host)
        v_lay.setContentsMargins(6, 6, 6, 6)
        v_lay.setSpacing(2)

        boxes: list[tuple[str, QCheckBox]] = []

        def _sync():
            self._change_block(key, [c for c, cb in boxes if cb.isChecked()])

        for c in cols:
            cb = QCheckBox(_clean_col_label(c))
            cb.setToolTip(str(c))
            cb.setChecked(c in sel_set)
            cb.setStyleSheet(f"QCheckBox {{ color:{self.theme.text_main}; font-size:11px; padding:1px; background:transparent; }}")
            cb.toggled.connect(lambda _: _sync())
            v_lay.addWidget(cb)
            boxes.append((str(c), cb))

        v_lay.addStretch()
        scroll.setWidget(host)
        self._add_widget(scroll)

        def _on_search(q: str):
            ql = q.strip().lower()
            for c, cb in boxes:
                cb.setVisible(not ql or ql in c.lower())

        def _sel_vis():
            for _, cb in boxes:
                if not cb.isHidden():
                    cb.blockSignals(True)
                    cb.setChecked(True)
                    cb.blockSignals(False)
            _sync()

        def _clr_all():
            for _, cb in boxes:
                cb.blockSignals(True)
                cb.setChecked(False)
                cb.blockSignals(False)
            _sync()

        ed_s.textChanged.connect(_on_search)
        btn_all.clicked.connect(_sel_vis)
        btn_clr.clicked.connect(_clr_all)

        if cb_suf is not None:
            def _on_suf(i):
                suf = cb_suf.itemData(i)
                if not suf:
                    return
                for c, cb in boxes:
                    if c.endswith(f"_{suf}") or c == suf:
                        cb.blockSignals(True)
                        cb.setChecked(True)
                        cb.blockSignals(False)
                cb_suf.blockSignals(True)
                cb_suf.setCurrentIndex(0)
                cb_suf.blockSignals(False)
                _sync()

            cb_suf.currentIndexChanged.connect(_on_suf)

    # ============================================================
    # Источники данных и поиск блоков отчёта (единый пул)
    # ============================================================

    def _get_file_manager(self):
        if getattr(self, "file_manager", None) is not None:
            return self.file_manager
        ref = getattr(self, "report_ref", None)
        if ref and getattr(ref, "file_manager", None) is not None:
            return ref.file_manager
        p = self.parent()
        while p is not None:
            if getattr(p, "file_manager", None) is not None:
                return p.file_manager
            if hasattr(p, "report") and getattr(p.report, "file_manager", None) is not None:
                return p.report.file_manager
            p = p.parent()
        return None

    def _ensure_source_pinned(self, cfg: dict) -> tuple[str, str, dict]:
        manager = self._get_file_manager()
        files_dict = manager.get_files_dict() if (manager and hasattr(manager, "get_files_dict")) else {}
        cur_file = cfg.get("source_file_name", "")
        cur_sheet = cfg.get("source_sheet", "") or cfg.get("source_file", "")

        if files_dict:
            if not cur_file or cur_file not in files_dict:
                def_file, _ = manager.get_default_file_and_sheet() if hasattr(manager, "get_default_file_and_sheet") else ("", "")
                cur_file = def_file if def_file in files_dict else next(iter(files_dict.keys()))
                cfg["source_file_name"] = cur_file
            sheets = files_dict.get(cur_file, [])
            if sheets and (not cur_sheet or cur_sheet not in sheets):
                cur_sheet = sheets[0]
                cfg["source_sheet"] = cur_sheet
        return cur_file, cur_sheet, files_dict

    def _get_target_dataframe(self, cfg: dict):
        manager = self._get_file_manager()
        if manager and hasattr(manager, "get_dataframe"):
            f_name = cfg.get("source_file_name", "")
            s_name = cfg.get("source_sheet", "") or cfg.get("source_file", "")
            if not s_name and cfg.get("target_chart") and getattr(self, "report_ref", None):
                found = self.report_ref.find_block(cfg["target_chart"])
                if found:
                    c_cfg = found[1].config or {}
                    f_name = c_cfg.get("source_file_name", "") or f_name
                    s_name = c_cfg.get("source_sheet", "") or c_cfg.get("source_file", "")
            if f_name or s_name:
                df = manager.get_dataframe(f_name, s_name)
                if df is not None:
                    return df
        return self._df

    def _get_target_columns(self, cfg: dict) -> list[str]:
        tdf = self._get_target_dataframe(cfg)
        if tdf is not None and hasattr(tdf, "columns"):
            return [str(c) for c in tdf.columns]
        return list(self._all_columns)

    def _build_source_selectors(self, cfg: dict):
        cur_file, cur_sheet, files_dict = self._ensure_source_pinned(cfg)
        if self._block is not None:
            self._block.config = cfg

        row = QHBoxLayout()
        row.setSpacing(4)

        w1 = QWidget()
        l1 = QVBoxLayout(w1)
        l1.setContentsMargins(0, 0, 0, 0)
        l1.setSpacing(2)
        l1.addWidget(self._make_label("Файл"))
        cb_f = QComboBox()
        if not files_dict:
            cb_f.addItem("— Нет —", "")
        else:
            for fn in files_dict.keys():
                cb_f.addItem(str(fn), str(fn))
            cb_f.setCurrentIndex(max(0, cb_f.findData(cur_file)))
        self._style_combo(cb_f)
        l1.addWidget(cb_f)
        row.addWidget(w1, 1)

        w2 = QWidget()
        l2 = QVBoxLayout(w2)
        l2.setContentsMargins(0, 0, 0, 0)
        l2.setSpacing(2)
        l2.addWidget(self._make_label("Лист"))
        cb_s = QComboBox()
        sheets = files_dict.get(cur_file, []) if files_dict else []
        if not sheets:
            cb_s.addItem("— Нет —", "")
        else:
            for sn in sheets:
                cb_s.addItem(str(sn), str(sn))
            cb_s.setCurrentIndex(max(0, cb_s.findData(cur_sheet)))
        self._style_combo(cb_s)
        l2.addWidget(cb_s)
        row.addWidget(w2, 1)

        self._add_row(row)

        def _on_f(i):
            fn = cb_f.itemData(i)
            if not fn or self._block is None:
                return
            av = files_dict.get(fn, [])
            nc = dict(self._block.config or {})
            nc["source_file_name"] = fn
            nc["source_sheet"] = av[0] if av else ""
            self._block.config = nc
            self.config_changed.emit(self._block.id)
            self._rebuild_later()

        def _on_s(i):
            sn = cb_s.itemData(i)
            if not sn:
                return
            self._change_block("source_sheet", sn)
            self._rebuild_later()

        cb_f.currentIndexChanged.connect(_on_f)
        cb_s.currentIndexChanged.connect(_on_s)

    def _collect_report_blocks(self, block_type: str, exclude_id: str = "") -> list:
        res = []
        ref = getattr(self, "report_ref", None)
        if not ref or not hasattr(ref, "sections"):
            return res

        def _walk(blocks):
            for b in (blocks or []):
                bt = b.get("type") if isinstance(b, dict) else getattr(b, "type", "")
                bid = b.get("id", "") if isinstance(b, dict) else getattr(b, "id", "")
                if bt == block_type and bid != exclude_id:
                    res.append(b)
                elif bt == "container":
                    bcfg = b.get("config", {}) if isinstance(b, dict) else (getattr(b, "config", {}) or {})
                    _walk(bcfg.get("children", []))

        for sec in ref.sections:
            _walk(getattr(sec, "blocks", []))
        return res

    # ============================================================
    # Контейнерные диалоги
    # ============================================================

    def _build_container_children_controls(self, container_block, children: list):
        for idx, child in enumerate(children):
            c_type = child.get("type") if isinstance(child, dict) else getattr(child, "type", "")
            c_cfg = child.get("config", {}) if isinstance(child, dict) else (getattr(child, "config", {}) or {})
            c_title = c_cfg.get("title") or BLOCK_TYPES.get(c_type, c_type)
            c_w = int(c_cfg.get("width", 50))
            if c_w >= 100:
                c_w = max(20, 100 // max(1, len(children)))

            row = QHBoxLayout()
            row.setSpacing(4)
            lbl = QLabel(f"{idx + 1}. {_clean_col_label(c_title)[:15]}")
            lbl.setStyleSheet(f"color:{self.theme.text_main}; font-size:10.5px; background:transparent;")
            row.addWidget(lbl, 1)

            sp = QSpinBox()
            sp.setRange(15, 100)
            sp.setSuffix("%")
            sp.setValue(c_w)
            sp.setFixedWidth(58)
            self._style_input(sp)

            def _on_cw(val, cref=child):
                if isinstance(cref, dict):
                    cref.setdefault("config", {})["width"] = val
                else:
                    if cref.config is None:
                        cref.config = {}
                    cref.config["width"] = val
                self.config_changed.emit(container_block.id)

            sp.valueChanged.connect(_on_cw)
            row.addWidget(sp)

            b_up = QPushButton("⬆")
            b_dn = QPushButton("⬇")
            for b in (b_up, b_dn):
                b.setFixedWidth(22)
                self._style_input(b)
            b_up.setEnabled(idx > 0)
            b_dn.setEnabled(idx < len(children) - 1)

            def _mv(delta, ci=idx):
                ni = ci + delta
                if 0 <= ni < len(children):
                    children[ci], children[ni] = children[ni], children[ci]
                    container_block.config["children"] = list(children)
                    self.config_changed.emit(container_block.id)
                    self._rebuild_later()

            b_up.clicked.connect(lambda _, d=-1: _mv(d))
            b_dn.clicked.connect(lambda _, d=1: _mv(d))
            row.addWidget(b_up)
            row.addWidget(b_dn)
            self._add_row(row)

    def _open_container_layout_dialog(self, container_block):
        cfg = dict(container_block.config or {})
        children = list(cfg.get("children", []))
        n = len(children)
        if n == 0:
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Схема расположения ({n} блоков)")
        dlg.setMinimumWidth(500)
        dlg.setStyleSheet(f"QDialog {{ background:{self.theme.bg_card}; color:{self.theme.text_main}; }}")

        root = QVBoxLayout(dlg)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)
        t_lbl = QLabel(f"Выберите расположение для {n} блоков:")
        t_lbl.setStyleSheet(f"color:{self.theme.text_main}; font-size:13px; font-weight:700;")
        root.addWidget(t_lbl)

        first_type = children[0].get("type") if isinstance(children[0], dict) else getattr(children[0], "type", "")
        pair_w = (25, 75) if first_type == "dashboard_filter" else (50, 50)

        if n == 2:
            presets = [
                ("Друг под другом", "100% / 100%", "column", [{"width": 100}, {"width": 100}], [[("1", 100)], [("2", 100)]]),
                ("Поровну (50 / 50)", "Два блока рядом", "row", [{"width": 50}, {"width": 50}], [[("1", 50), ("2", 50)]]),
                ("Узкий слева (25 / 75)", "Фильтр + График", "row", [{"width": 25}, {"width": 75}], [[("1", 25), ("2", 75)]]),
                ("Узкий справа (75 / 25)", "График + Панель", "row", [{"width": 75}, {"width": 25}], [[("1", 75), ("2", 25)]]),
            ]
        elif n == 3:
            presets = [
                ("Друг под другом", "3 блока вертикально", "column", [{"width": 100}] * 3, [[("1", 100)], [("2", 100)], [("3", 100)]]),
                ("2 сверху + 1 снизу", "Верхний ряд + широкий нижний", "row", [{"width": pair_w[0]}, {"width": pair_w[1]}, {"width": 100}], [[("1", pair_w[0]), ("2", pair_w[1])], [("3", 100)]]),
                ("3 в один ряд", "33% / 33% / 34%", "row", [{"width": 33}, {"width": 33}, {"width": 34}], [[("1", 33), ("2", 33), ("3", 34)]]),
                ("1 сверху + 2 снизу", "По центру + 2 рядом", "row", [{"width": 70, "full_row": True}, {"width": 50}, {"width": 50}], [[("1", 70)], [("2", 50), ("3", 50)]]),
            ]
        else:
            eq = max(20, 100 // n)
            presets = [
                ("Друг под другом", f"{n} блоков вертикально", "column", [{"width": 100}] * n, [[(str(i + 1), 100)] for i in range(min(n, 4))]),
                ("Сетка 2 в ряд", "По 2 блока на строку", "row", [{"width": 100 if (i == n - 1 and n % 2) else 50} for i in range(n)], [[("1", 50), ("2", 50)], [("3", 50), ("4", 50)]]),
                ("Все в один ряд", f"По {eq}%", "row", [{"width": eq}] * n, [[(str(i + 1), eq) for i in range(min(n, 4))]]),
            ]

        grid = QGridLayout()
        grid.setSpacing(10)

        def _apply(lm, rules):
            cfg["layout"] = lm
            for ic, ch in enumerate(children):
                r = rules[ic] if ic < len(rules) else {"width": 100}
                target_c = ch.setdefault("config", {}) if isinstance(ch, dict) else (ch.config if ch.config is not None else {})
                if not isinstance(ch, dict) and ch.config is None:
                    ch.config = target_c
                target_c["width"] = r["width"]
                target_c["full_row"] = r.get("full_row", False)
            cfg["children"] = children
            container_block.config = cfg
            self.config_changed.emit(container_block.id)
            dlg.accept()
            self._rebuild_later()

        for ip, (pt, pd_txt, plm, prules, vrows) in enumerate(presets):
            card = QFrame()
            card.setStyleSheet(f"QFrame {{ background:{self.theme.bg_panel}; border:1px solid {self.theme.border}; border-radius:8px; padding:8px; }}")
            cl = QVBoxLayout(card)
            cl.setSpacing(6)
            lt = QLabel(pt)
            lt.setStyleSheet(f"color:{self.theme.text_main}; font-size:11.5px; font-weight:700; border:none;")
            cl.addWidget(lt)

            pv = QFrame()
            pv.setFixedHeight(78)
            pv.setStyleSheet(f"QFrame {{ background:{self.theme.bg_card}; border:1px dashed {self.theme.border}; border-radius:6px; }}")
            pvl = QVBoxLayout(pv)
            pvl.setContentsMargins(6, 6, 6, 6)
            pvl.setSpacing(4)
            for vr in vrows:
                rl = QHBoxLayout()
                rl.setSpacing(4)
                for bl, bw in vr:
                    w = QLabel(bl)
                    w.setAlignment(Qt.AlignCenter)
                    w.setStyleSheet("background:#87C800; color:#fff; font-size:10px; font-weight:700; border-radius:3px; border:none;")
                    rl.addWidget(w, max(1, int(bw)))
                pvl.addLayout(rl, 1)
            cl.addWidget(pv)

            ld = QLabel(pd_txt)
            ld.setStyleSheet(f"color:{self.theme.text_muted}; font-size:10px; border:none;")
            cl.addWidget(ld)

            btn = QPushButton("Применить")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(
                f"QPushButton {{ background:{self.theme.bg_card}; color:{self.theme.text_main}; "
                f"border:1px solid {self.theme.primary}; border-radius:4px; padding:4px; font-size:10.5px; font-weight:600; }}"
                f"QPushButton:hover {{ background:{self.theme.primary}; color:{self.theme.text_inverse}; }}"
            )
            btn.clicked.connect(lambda _, m=plm, rl=prules: _apply(m, rl))
            cl.addWidget(btn)
            grid.addWidget(card, ip // 2, ip % 2)

        root.addLayout(grid)
        dlg.exec()

    # ============================================================
    # Унифицированные фабрики полей ввода
    # ============================================================

    def _change_block(self, key: str, value):
        if self._block is None:
            return
        cfg = dict(self._block.config or {})
        cfg[key] = value
        self._block.config = cfg
        self.config_changed.emit(self._block.id)

    def _change_section(self, key: str, value):
        if self._section is None:
            return
        setattr(self._section, key, value)
        self.config_changed.emit("")

    def _add_widget(self, w: QWidget):
        if self._cur_lay is not None:
            self._cur_lay.addWidget(w)

    def _add_row(self, h_lay: QHBoxLayout):
        w = QWidget()
        w.setStyleSheet("background:transparent;")
        h_lay.setContentsMargins(0, 0, 0, 0)
        w.setLayout(h_lay)
        self._add_widget(w)

    def _make_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color:{self.theme.text_muted}; font-size:10px; font-weight:600; background:transparent;")
        return lbl

    def _add_label(self, text: str):
        self._add_widget(self._make_label(text))

    def _add_hint(self, text: str):
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color:{self.theme.text_muted}; font-size:10.5px; background:transparent;")
        self._add_widget(lbl)

    def _make_col_combobox(self, cols: list[str], cur_val: str, empty_label: str = "— Авто —", allow_disable: bool = False) -> QComboBox:
        cb = QComboBox()
        cb.addItem(empty_label, "")
        if allow_disable:
            cb.addItem("🚫 Отключить уровень", "__NONE__")
        for c in cols:
            cb.addItem(_clean_col_label(c), str(c))
            cb.setItemData(cb.count() - 1, str(c), Qt.ToolTipRole)
        idx = cb.findData(str(cur_val or ""))
        cb.setCurrentIndex(idx if idx >= 0 else 0)
        self._style_combo(cb)
        return cb

    def _field_col(self, label: str, key: str, cfg: dict, cols: list[str], empty_label: str = "— Авто —", allow_disable: bool = False, rebuild: bool = False) -> QComboBox:
        self._add_label(label)
        cb = self._make_col_combobox(cols, str(cfg.get(key, "") or ""), empty_label, allow_disable)

        def _on_ch(i):
            self._change_block(key, cb.itemData(i))
            if rebuild:
                self._rebuild_later()

        cb.currentIndexChanged.connect(_on_ch)
        self._add_widget(cb)
        return cb

    def _field_text(self, label: str, key: str, cfg: dict, placeholder: str = "") -> QLineEdit:
        self._add_label(label)
        e = QLineEdit(str(cfg.get(key, "")))
        if placeholder:
            e.setPlaceholderText(placeholder)
        self._style_input(e)
        e.textChanged.connect(lambda v: self._change_block(key, v))
        self._add_widget(e)
        return e

    def _field_combo(self, label: str, key: str, cfg: dict, items: list[tuple], default_val, rebuild: bool = False) -> QComboBox:
        self._add_label(label)
        cb = QComboBox()
        for title, val in items:
            cb.addItem(str(title), val)
        cur_val = cfg.get(key, default_val)
        idx = cb.findData(cur_val)
        if idx < 0 and cur_val is not None:
            for i_try in range(cb.count()):
                if str(cb.itemData(i_try)) == str(cur_val):
                    idx = i_try
                    break
        cb.setCurrentIndex(idx if idx >= 0 else 0)
        self._style_combo(cb)

        def _on_ch(i):
            self._change_block(key, cb.itemData(i))
            if rebuild:
                self._rebuild_later()

        cb.currentIndexChanged.connect(_on_ch)
        self._add_widget(cb)
        return cb

    def _field_checkbox(self, label: str, key: str, cfg: dict, default_val: bool) -> QCheckBox:
        cb = QCheckBox(label)
        cb.setChecked(bool(cfg.get(key, default_val)))
        cb.setStyleSheet(f"QCheckBox {{ color:{self.theme.text_main}; font-size:11px; padding:1px 0; background:transparent; }}")
        cb.toggled.connect(lambda v: self._change_block(key, bool(v)))
        self._add_widget(cb)
        return cb

    def _field_int(self, label: str, key: str, cfg: dict, default: int = 0, min_val: int = 0, max_val: int = 5000) -> QSpinBox:
        self._add_label(label)
        sp = QSpinBox()
        sp.setRange(min_val, max_val)
        sp.setValue(int(cfg.get(key, default) or 0))
        self._style_input(sp)
        sp.valueChanged.connect(lambda v: self._change_block(key, int(v)))
        self._add_widget(sp)
        return sp

    def _field_double(self, label: str, key: str, cfg: dict, default: float = 0.0, suffix: str = "", use_editing_finished: bool = False) -> QDoubleSpinBox:
        self._add_label(label)
        sp = QDoubleSpinBox()
        sp.setKeyboardTracking(False)
        sp.setRange(-10000.0, 10000.0)
        sp.setDecimals(1)
        sp.setSingleStep(1.0)
        if suffix:
            sp.setSuffix(suffix)
        raw_v = cfg.get(key, default)
        try:
            sp.setValue(float(default if raw_v is None else raw_v))
        except Exception:
            sp.setValue(float(default))
        self._style_input(sp)
        if use_editing_finished:
            sp.editingFinished.connect(lambda: self._change_block(key, float(sp.value())))
        else:
            sp.valueChanged.connect(lambda v: self._change_block(key, float(v)))
        self._add_widget(sp)
        return sp

    def _field_spin_pair(self, left: tuple, right: tuple, cfg: dict):
        row = QHBoxLayout()
        row.setSpacing(6)
        for lbl, key, default, mn, mx in (left, right):
            w = QWidget()
            w.setStyleSheet("background:transparent;")
            l = QVBoxLayout(w)
            l.setContentsMargins(0, 0, 0, 0)
            l.setSpacing(2)
            l.addWidget(self._make_label(lbl))
            sp = QSpinBox()
            sp.setRange(mn, mx)
            sp.setValue(int(cfg.get(key, default) or 0))
            self._style_input(sp)
            sp.valueChanged.connect(lambda v, k=key: self._change_block(k, int(v)))
            l.addWidget(sp)
            row.addWidget(w, 1)
        self._add_row(row)

    def _field_color(self, label: str, key: str, cfg: dict, default_hex: str):
        self._add_label(label)
        cur_hex = str(cfg.get(key, default_hex) or default_hex)
        row = QHBoxLayout()
        row.setSpacing(4)
        ed = QLineEdit(cur_hex)
        self._style_input(ed)

        btn = QPushButton("🎨")
        btn.setFixedWidth(32)
        btn.setCursor(Qt.PointingHandCursor)

        def _paint(hx: str):
            btn.setStyleSheet(f"QPushButton {{ background:{hx}; color:#fff; border:1px solid {self.theme.border}; border-radius:4px; padding:3px; }}")

        _paint(cur_hex)

        def _on_ed(txt: str):
            s = txt.strip()
            if len(s) in (4, 7) and s.startswith("#"):
                _paint(s)
                self._change_block(key, s)

        def _pick():
            c = QColorDialog.getColor(QColor(ed.text().strip() or default_hex), self, label)
            if c.isValid():
                ed.setText(c.name())
                self._change_block(key, c.name())

        ed.textChanged.connect(_on_ed)
        btn.clicked.connect(_pick)
        row.addWidget(ed, 1)
        row.addWidget(btn)
        self._add_row(row)

    def _field_background_picker(self, cfg: dict):
        self._add_label("Фон карточки графика")
        row = QHBoxLayout()
        row.setSpacing(4)
        cb = QComboBox()
        for title, hx in _BG_PRESETS:
            cb.addItem(title, hx)
        cur_bg = str(cfg.get("bg_color", "#ffffff") or "#ffffff")
        idx = cb.findData(cur_bg)
        if idx < 0:
            cb.addItem(f"Свой ({cur_bg})", cur_bg)
            idx = cb.count() - 1
        cb.setCurrentIndex(idx)
        self._style_combo(cb)
        cb.currentIndexChanged.connect(lambda i: self._change_block("bg_color", cb.itemData(i)))
        row.addWidget(cb, 1)

        btn = QPushButton("🎨")
        btn.setFixedWidth(30)
        btn.setCursor(Qt.PointingHandCursor)
        self._style_input(btn)

        def _pick():
            c = QColorDialog.getColor(QColor(cur_bg), self, "Цвет фона")
            if c.isValid():
                self._change_block("bg_color", c.name())
                self._rebuild_later()

        btn.clicked.connect(_pick)
        row.addWidget(btn)
        self._add_row(row)

    # ============================================================
    # Стилизация элементов
    # ============================================================

    def _style_input(self, w: QWidget):
        t = self.theme
        w.setStyleSheet(
            f"background:{t.bg_card}; color:{t.text_main}; "
            f"border:1px solid {t.border}; border-radius:4px;"
            f"padding:4px 6px; font-size:11px;"
        )

    def _style_combo(self, cb: QComboBox):
        cb.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        cb.setMinimumContentsLength(6)
        self._style_input(cb)

    def _style_chip(self, btn: QPushButton):
        t = self.theme
        btn.setStyleSheet(
            f"QPushButton {{ background:{t.bg_card}; color:{t.text_main}; "
            f"border:1px solid {t.border}; border-radius:3px; padding:2px 4px; font-size:9.5px; font-weight:600; }}"
            f"QPushButton:hover {{ border-color:{t.primary}; color:{t.primary}; }}"
        )