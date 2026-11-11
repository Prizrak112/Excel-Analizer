"""Панель свойств блока (правая панель Конструктора)."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit,
    QSpinBox, QCheckBox, QScrollArea, QFrame, QComboBox, QPushButton,
    QSlider, QColorDialog, QDialog, QGridLayout,
)
from PySide6.QtCore import Qt, Signal, QTimer

from src.core.block_factory import BLOCK_TYPES


_CHART_TYPES = [
    ("🔀 Комбинированный график (Несколько графиков на одной оси)", "combo"),
    ("📊 Столбчатая диаграмма (Bar)", "bar"),
    ("🧱 Накопительная гистограмма (Stacked Bar)", "bar_stacked"),
    ("📐 Накопительная с нарастающим итогом (Cumulative)", "bar_cumulative"),
    ("💯 100% Накопительная гистограмма (100% Stacked)", "bar_stacked_100"),
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
    ("↔ По строкам (выбор столбцов строки / по месяцам)", "rows"),
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
    ("Без сортировки (порядок как в таблице)", "none"),
    ("По убыванию значения", "value_desc"),
    ("По возрастанию значения", "value_asc"),
    ("По алфавиту (Ось X)", "label_asc"),
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
    (">  Больше чем", ">"),
    (">= Больше или равно", ">="),
    ("<  Меньше чем", "<"),
    ("<= Меньше или равно", "<="),
    ("== Равно (точное совпадение)", "=="),
    ("!= Не равно (исключить)", "!="),
    ("↔ В диапазоне (мин, макс)", "between"),
    ("🔍 Содержит текст", "contains"),
    ("🚫 НЕ содержит текст", "not_contains"),
    ("📋 Одно из списка (через запятую)", "in_list"),
    ("📈 Выше среднего по столбцу", "above_mean"),
    ("📉 Ниже среднего по столбцу", "below_mean"),
    ("✔ Только непустые (Not Null)", "not_null"),
]


class BlockInspector(QWidget):
    """Интерактивная панель свойств блока с поддержкой построения графиков
    как по столбцам, так и по строкам (выбор определенных столбцов строки)."""

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

        # Сохраняем список всех доступных файлов и листов из проекта
        self._available_files = []
        if hasattr(self, "report_ref") and self.report_ref:
            # Проверяем различные возможные методы получения листов/файлов из вашего менеджера
            if hasattr(self.report_ref, "get_available_files"):
                self._available_files = self.report_ref.get_available_files()
            elif hasattr(self.report_ref, "file_manager") and hasattr(self.report_ref.file_manager, "sheets"):
                self._available_files = list(self.report_ref.file_manager.sheets.keys())
            elif hasattr(self.report_ref, "sheets"):
                self._available_files = list(self.report_ref.sheets.keys())
            
        # Если у вас есть глобальный доступ к активным вкладкам листов через mainWindow или file_manager:
        if not self._available_files and hasattr(self, "parent") and self.parent():
            # Запасной сбор из родительского интерфейса, если применимо
            pass

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
            
            self._section_header("Оформление текста")
            row_font = QHBoxLayout()
            row_font.setSpacing(4)
            
            default_size = 24 if block.type == "section_title" else 14
            self._field_spin_inline("Размер (px)", "font_size", cfg, default_size, 8, 120, parent_layout=row_font)
            
            cb_align = QComboBox()
            cb_align.addItem("⬅ Слева", "left")
            cb_align.addItem("↔ По центру", "center")
            cb_align.addItem("➡ Справа", "right")
            cb_align.addItem("📄 По ширине", "justify")
            
            cur_align = cfg.get("text_align", "left")
            idx_a = cb_align.findData(cur_align)
            cb_align.setCurrentIndex(idx_a if idx_a >= 0 else 0)
            self._style_input(cb_align)
            cb_align.currentIndexChanged.connect(lambda i: self._change_block("text_align", cb_align.itemData(i)))
            
            align_widget = QWidget()
            align_layout = QVBoxLayout(align_widget)
            align_layout.setContentsMargins(0, 0, 0, 0)
            align_layout.setSpacing(2)
            lbl = QLabel("Выравнивание")
            lbl.setStyleSheet(f"color:{self.theme.text_muted}; font-size:9px; background:transparent;")
            align_layout.addWidget(lbl)
            align_layout.addWidget(cb_align)
            
            row_font.addWidget(align_widget)
            self._lay.insertWidget(self._lay.count() - 1, self._wrap_row(row_font))

            if block.type == "paragraph":
                self._build_paragraph_dynamic_settings(cfg)

        elif block.type == "kpi_row":
            self._section_header("Карточки KPI")
            self._field_kpi(cfg)

        elif block.type == "plotly_chart":
            self._build_chart_settings(cfg)

        elif block.type == "dashboard_filter":
            self._section_header("1. Источник данных (Файл и Лист)")
            self._build_source_selectors(cfg)
            actual_cols = self._get_target_columns(cfg)

            self._section_header("2. Настройки Среза (Фильтра)")
            self._field_text("Заголовок блока", "title", cfg, placeholder="Например: Тип ТС")

            self._add_label("Колонка для фильтрации (например, Тип ТС)")
            cb_col = QComboBox()
            cb_col.addItem("— Выберите колонку —", "")
            for col in actual_cols:
                cb_col.addItem(str(col), str(col))
            cur_col = cfg.get("filter_col", "")
            idx = cb_col.findData(cur_col)
            cb_col.setCurrentIndex(idx if idx >= 0 else 0)
            self._style_input(cb_col)
            cb_col.currentIndexChanged.connect(lambda i: self._change_block("filter_col", cb_col.itemData(i)))
            self._lay.insertWidget(self._lay.count() - 1, cb_col)

            self._add_label("Управляет основным графиком")
            cb_target = QComboBox()
            cb_target.addItem("🌐 Все графики в отчёте", "")

            chart_items_list: list[tuple[str, str]] = []
            if hasattr(self, "report_ref") and self.report_ref:
                def _find_charts(blocks):
                    found = []
                    for b in blocks:
                        b_type = b.get("type") if isinstance(b, dict) else getattr(b, "type", "")
                        if b_type == "plotly_chart":
                            found.append(b)
                        elif b_type == "container":
                            b_cfg = b.get("config", {}) if isinstance(b, dict) else (getattr(b, "config", {}) or {})
                            found.extend(_find_charts(b_cfg.get("children", [])))
                    return found

                for section in self.report_ref.sections:
                    for chart_block in _find_charts(section.blocks):
                        c_id = chart_block.get("id", "") if isinstance(chart_block, dict) else chart_block.id
                        c_cfg = chart_block.get("config", {}) if isinstance(chart_block, dict) else (chart_block.config or {})
                        t = c_cfg.get("title", "График без названия")
                        label_str = f"📊 {t} (ID: {str(c_id)[:4]})"
                        cb_target.addItem(label_str, c_id)
                        chart_items_list.append((label_str, str(c_id)))

            cur_target = cfg.get("target_chart", "")
            idx_t = cb_target.findData(cur_target)
            cb_target.setCurrentIndex(idx_t if idx_t >= 0 else 0)
            self._style_input(cb_target)
            cb_target.currentIndexChanged.connect(lambda i: self._change_block("target_chart", cb_target.itemData(i)))
            self._lay.insertWidget(self._lay.count() - 1, cb_target)

            # Поле подключения среза к дополнительным графикам
            self._add_label("Дополнительные графики для этого среза:")
            row_extra_charts = QHBoxLayout()
            row_extra_charts.setSpacing(4)

            edit_extra_charts = QLineEdit(str(cfg.get("extra_target_charts", "") or ""))
            edit_extra_charts.setPlaceholderText("ID дополнительных графиков через запятую...")
            self._style_input(edit_extra_charts)
            row_extra_charts.addWidget(edit_extra_charts, 1)

            btn_clear_extra = QPushButton("✕")
            btn_clear_extra.setFixedWidth(26)
            btn_clear_extra.setToolTip("Очистить дополнительные графики")
            self._style_input(btn_clear_extra)
            row_extra_charts.addWidget(btn_clear_extra)
            self._lay.insertWidget(self._lay.count() - 1, self._wrap_row(row_extra_charts))

            cb_add_chart = QComboBox()
            cb_add_chart.addItem("➕ Подключить ещё к графику…", "")
            for c_label, c_id in chart_items_list:
                cb_add_chart.addItem(f"+ {c_label}", c_id)
            self._style_input(cb_add_chart)
            self._lay.insertWidget(self._lay.count() - 1, cb_add_chart)

            def on_add_extra_chart(i):
                c_id = cb_add_chart.itemData(i)
                if not c_id:
                    return
                parts = [p.strip() for p in edit_extra_charts.text().split(",") if p.strip()]
                if c_id not in parts and c_id != cb_target.currentData():
                    parts.append(c_id)
                new_csv = ", ".join(parts)
                edit_extra_charts.blockSignals(True)
                edit_extra_charts.setText(new_csv)
                edit_extra_charts.blockSignals(False)
                cb_add_chart.blockSignals(True)
                cb_add_chart.setCurrentIndex(0)
                cb_add_chart.blockSignals(False)
                self._change_block("extra_target_charts", new_csv)

            def on_clear_extra_charts():
                edit_extra_charts.setText("")
                self._change_block("extra_target_charts", "")

            cb_add_chart.currentIndexChanged.connect(on_add_extra_chart)
            btn_clear_extra.clicked.connect(on_clear_extra_charts)
            edit_extra_charts.textChanged.connect(lambda v: self._change_block("extra_target_charts", v))

            self._section_header("3. Высота и прокрутка (Скролл)")
            self._field_checkbox(
                "🔄 Синхронизировать высоту с соседним графиком",
                "sync_height",
                cfg,
                True,
            )
            self._field_int(
                "Макс. высота списка со скроллом (px, 0 = без лимита)",
                "max_height",
                cfg,
                default=420,
                min_val=0,
                max_val=2000,
                tooltip="Если элементов в фильтре много, появится аккуратная полоса прокрутки.",
            )

            self._add_hint("💡 Выберите конкретный график или оставьте «Все графики», чтобы срез переключал строки/категории.")

        elif block.type in ("pivot_matrix", "decomposition", "geo_map"):
            from src.core.blocks import DataMemoryCache

            self._section_header("1. ИСТОЧНИК ДАННЫХ (ФАЙЛ И ЛИСТ)")
            fm = getattr(self, "file_manager", None)
            if fm is None and hasattr(self, "report_ref") and self.report_ref is not None:
                fm = getattr(self.report_ref, "file_manager", None)

            files_dict = fm.get_files_dict() if (fm is not None and hasattr(fm, "get_files_dict")) else {}
            cur_file = str(cfg.get("source_file_name", "") or "")
            cur_sheet = str(cfg.get("source_sheet", "") or cfg.get("source_file", "") or "")

            if not cur_file and files_dict:
                cur_file = next(iter(files_dict.keys()))

            self._add_label("Файл источника")
            cb_file = QComboBox()
            for f_name in files_dict.keys():
                cb_file.addItem(f_name, f_name)
            idx_f = cb_file.findData(cur_file)
            if idx_f >= 0:
                cb_file.setCurrentIndex(idx_f)
            self._style_input(cb_file)
            self._lay.insertWidget(self._lay.count() - 1, cb_file)

            self._add_label("Лист таблицы")
            cb_sheet = QComboBox()
            sheets_for_file = files_dict.get(cur_file, [])
            for s_name in sheets_for_file:
                cb_sheet.addItem(s_name, s_name)
            idx_s = cb_sheet.findData(cur_sheet)
            if idx_s >= 0:
                cb_sheet.setCurrentIndex(idx_s)
            self._style_input(cb_sheet)
            self._lay.insertWidget(self._lay.count() - 1, cb_sheet)

            df_target = DataMemoryCache.get_dataframe(
                fm, cur_file, cur_sheet, fallback_df=getattr(self, "_df", None)
            )
            cols_list = [str(c) for c in df_target.columns] if (df_target is not None and hasattr(df_target, "columns")) else []

            def _on_src_file_changed(i):
                new_f = cb_file.itemData(i) or ""
                new_sheets = files_dict.get(new_f, [])
                first_s = new_sheets[0] if new_sheets else ""
                if self._block is not None:
                    self._block.config["source_file_name"] = new_f
                    self._block.config["source_sheet"] = first_s
                    self.config_changed.emit(self._block.id)
                    self.show_block(self._block)

            def _on_src_sheet_changed(i):
                new_s = cb_sheet.itemData(i) or ""
                if self._block is not None:
                    self._block.config["source_sheet"] = new_s
                    self.config_changed.emit(self._block.id)
                    self.show_block(self._block)

            cb_file.currentIndexChanged.connect(_on_src_file_changed)
            cb_sheet.currentIndexChanged.connect(_on_src_sheet_changed)

            def _make_col_combo(label_txt: str, cfg_key: str, allow_empty: bool = False):
                self._add_label(label_txt)
                cb = QComboBox()
                if allow_empty:
                    cb.addItem("— Не выбрано —", "")
                for c_name in cols_list:
                    cb.addItem(c_name, c_name)
                cur_v = str(cfg.get(cfg_key, "") or "")
                idx_c = cb.findData(cur_v)
                cb.setCurrentIndex(idx_c if idx_c >= 0 else 0)
                self._style_input(cb)
                cb.currentIndexChanged.connect(lambda i, k=cfg_key, box=cb: self._change_block(k, box.itemData(i)))
                self._lay.insertWidget(self._lay.count() - 1, cb)
                return cb

            if block.type == "pivot_matrix":
                self._section_header("2. НАСТРОЙКИ СВОДНОЙ МАТРИЦЫ И ИЕРАРХИИ")
                self._add_label("Заголовок блока")
                ed_title = QLineEdit(str(cfg.get("title", "Сводная матрица")))
                self._style_input(ed_title)
                ed_title.textChanged.connect(lambda v: self._change_block("title", v))
                self._lay.insertWidget(self._lay.count() - 1, ed_title)

                _make_col_combo("Строки — Уровень 1 (Основная группа, напр. Тип ТС):", "row_group_col")

                def _make_drill_combo(label_txt: str, cfg_key: str, auto_hint: str):
                    self._add_label(label_txt)
                    cb = QComboBox()
                    cb.addItem(f"⚡ Авто ({auto_hint})", "")
                    cb.addItem("🚫 Не раскрывать этот уровень", "__NONE__")
                    for c_name in cols_list:
                        cb.addItem(c_name, c_name)
                    cur_v = str(cfg.get(cfg_key, "") or "")
                    idx_c = cb.findData(cur_v)
                    cb.setCurrentIndex(idx_c if idx_c >= 0 else 0)
                    self._style_input(cb)
                    cb.currentIndexChanged.connect(lambda i, k=cfg_key, box=cb: self._change_block(k, box.itemData(i)))
                    self._lay.insertWidget(self._lay.count() - 1, cb)

                _make_drill_combo("Раскрытие при клике — Уровень 2 (Модель / Марка):", "row_level2_col", "Марка / Модель")
                _make_drill_combo("Раскрытие при клике — Уровень 3 (Гос. номер):", "row_level3_col", "Гос. номер")

                _make_col_combo("Столбцы по горизонтали (напр. Дата / Месяц):", "col_group_col", allow_empty=True)
                _make_col_combo("Основной числовой показатель (Столбец A / C1):", "value_col")

                # Выбор дополнительных столбцов, по которым будут считаться данные
                self._add_label("Дополнительные столбцы для расчёта (B / C2, C / C3...):")
                raw_vcols = cfg.get("value_cols") or []
                if isinstance(raw_vcols, str):
                    raw_vcols = [x.strip() for x in raw_vcols.split(",") if x.strip()]
                selected_vcols = set(raw_vcols)

                scroll_v = QScrollArea()
                scroll_v.setWidgetResizable(True)
                scroll_v.setFixedHeight(115)
                scroll_v.setStyleSheet(
                    f"QScrollArea {{ background:{self.theme.bg_panel}; border:1px solid {self.theme.border}; border-radius:4px; }}"
                )
                v_host = QWidget()
                v_host.setStyleSheet("background:transparent;")
                v_lay = QVBoxLayout(v_host)
                v_lay.setContentsMargins(6, 6, 6, 6)
                v_lay.setSpacing(2)

                v_checkboxes: list[tuple[str, QCheckBox]] = []

                def _sync_pivot_vcols():
                    chosen = [c_name for c_name, chk in v_checkboxes if chk.isChecked()]
                    self._change_block("value_cols", chosen)

                for c_name in cols_list:
                    chk = QCheckBox(str(c_name))
                    chk.setChecked(c_name in selected_vcols)
                    chk.setStyleSheet(f"QCheckBox {{ color:{self.theme.text_main}; font-size:11px; padding:2px; background:transparent; }}")
                    chk.toggled.connect(lambda _v: _sync_pivot_vcols())
                    v_lay.addWidget(chk)
                    v_checkboxes.append((str(c_name), chk))

                v_lay.addStretch()
                scroll_v.setWidget(v_host)
                self._lay.insertWidget(self._lay.count() - 1, scroll_v)

                self._add_label("Функция расчёта")
                cb_agg = QComboBox()
                for k_agg, lbl_agg in (
                    ("sum", "Сумма (SUM)"),
                    ("mean", "Среднее (AVG)"),
                    ("count", "Количество записей (COUNT)"),
                    ("max", "Максимум (MAX)"),
                    ("min", "Минимум (MIN)"),
                ):
                    cb_agg.addItem(lbl_agg, k_agg)
                idx_a = cb_agg.findData(cfg.get("agg_func", "sum"))
                cb_agg.setCurrentIndex(idx_a if idx_a >= 0 else 0)
                self._style_input(cb_agg)
                cb_agg.currentIndexChanged.connect(lambda i: self._change_block("agg_func", cb_agg.itemData(i)))
                self._lay.insertWidget(self._lay.count() - 1, cb_agg)

                # ── 3. ВЫЧИСЛЯЕМЫЕ СТОЛБЦЫ И ФОРМУЛЫ ──
                self._section_header("3. ВЫЧИСЛЯЕМЫЕ СТОЛБЦЫ (МАТ. ФУНКЦИИ И ФОРМУЛЫ)")
                self._add_hint(
                    "💡 Переменные в формулах: A (или C1) — 1-й столбец, B (или C2) — 2-й столбец, "
                    "C (или C3) — 3-й столбец, либо точные имена столбцов."
                )

                cur_calcs = list(cfg.get("calc_cols") or [])
                for idx_cc, cc_item in enumerate(cur_calcs):
                    if not isinstance(cc_item, dict):
                        continue
                    row_cc = QHBoxLayout()
                    row_cc.setSpacing(4)
                    cc_lbl = QLabel(
                        f"🧮 <b>{cc_item.get('name', 'Расчёт')}</b> = <code>{cc_item.get('formula', '')}</code>"
                        + (" (%)" if cc_item.get("is_pct") else "")
                    )
                    cc_lbl.setWordWrap(True)
                    cc_lbl.setStyleSheet(f"color:{self.theme.text_main}; font-size:10.5px; background:transparent;")
                    row_cc.addWidget(cc_lbl, 1)

                    btn_del_cc = QPushButton("✕")
                    btn_del_cc.setFixedWidth(24)
                    btn_del_cc.setToolTip("Удалить этот вычисляемый столбец")
                    self._style_input(btn_del_cc)

                    def _remove_calc_col(rem_i=idx_cc):
                        if self._block is None:
                            return
                        new_list = [x for j, x in enumerate(list(self._block.config.get("calc_cols") or [])) if j != rem_i]
                        self._block.config["calc_cols"] = new_list
                        self.config_changed.emit(self._block.id)
                        self.show_block(self._block)

                    btn_del_cc.clicked.connect(_remove_calc_col)
                    row_cc.addWidget(btn_del_cc)
                    self._lay.insertWidget(self._lay.count() - 1, self._wrap_row(row_cc))

                self._add_label("Готовая математическая функция (быстрый шаблон):")
                cb_preset_fn = QComboBox()
                _PIV_PRESETS = [
                    ("— Выберите функцию или введите формулу ниже —", "", "", False),
                    ("➖ Разность: А − Б (Факт − Норма)", "Отклонение (А−Б)", "A - B", False),
                    ("➖ Экономия: Б − А (Норма − Факт)", "Экономия (Б−А)", "B - A", False),
                    ("📐 % отклонения: ((А − Б) / Б) × 100%", "% отклонения", "((A - B) / B) * 100", True),
                    ("📐 % выполнения: (А / Б) × 100%", "% от нормы", "(A / B) * 100", True),
                    ("➕ Сумма: А + Б", "Сумма (А+Б)", "A + B", False),
                    ("✖ Произведение: А × Б", "Произведение", "A * B", False),
                    ("➗ Отношение: А / Б", "Отношение (А/Б)", "A / B", False),
                ]
                for p_title, p_name, p_form, p_pct in _PIV_PRESETS:
                    cb_preset_fn.addItem(p_title, (p_name, p_form, p_pct))
                self._style_input(cb_preset_fn)
                self._lay.insertWidget(self._lay.count() - 1, cb_preset_fn)

                self._add_label("Название нового столбца:")
                ed_cc_name = QLineEdit()
                ed_cc_name.setPlaceholderText("Напр.: Отклонение ГСМ  или  % перерасхода")
                self._style_input(ed_cc_name)
                self._lay.insertWidget(self._lay.count() - 1, ed_cc_name)

                self._add_label("Формула расчёта:")
                ed_cc_formula = QLineEdit()
                ed_cc_formula.setPlaceholderText("Напр.: A - B   или   ((A - B) / B) * 100")
                self._style_input(ed_cc_formula)
                self._lay.insertWidget(self._lay.count() - 1, ed_cc_formula)

                chk_cc_pct = QCheckBox("Отображать результат со знаком процента (%)")
                chk_cc_pct.setStyleSheet(f"QCheckBox {{ color:{self.theme.text_main}; font-size:11px; background:transparent; }}")
                self._lay.insertWidget(self._lay.count() - 1, chk_cc_pct)

                def _on_preset_selected(idx_p):
                    data_p = cb_preset_fn.itemData(idx_p)
                    if not data_p or not data_p[1]:
                        return
                    p_name, p_form, p_pct = data_p
                    ed_cc_name.setText(p_name)
                    ed_cc_formula.setText(p_form)
                    chk_cc_pct.setChecked(bool(p_pct))

                cb_preset_fn.currentIndexChanged.connect(_on_preset_selected)

                btn_add_cc = QPushButton("➕ Добавить вычисляемый столбец в таблицу")
                btn_add_cc.setCursor(Qt.PointingHandCursor)
                btn_add_cc.setStyleSheet(
                    f"QPushButton {{ background:{self.theme.bg_panel}; color:{self.theme.primary}; "
                    f"border:1px solid {self.theme.primary}; border-radius:5px; padding:6px; font-size:11px; font-weight:700; }}"
                    f"QPushButton:hover {{ background:{self.theme.primary}; color:{self.theme.text_inverse}; }}"
                )

                def _on_add_calc_col():
                    if self._block is None:
                        return
                    f_txt = ed_cc_formula.text().strip()
                    if not f_txt:
                        return
                    n_txt = ed_cc_name.text().strip() or f_txt
                    cur_list = list(self._block.config.get("calc_cols") or [])
                    cur_list.append({
                        "name": n_txt,
                        "formula": f_txt,
                        "is_pct": bool(chk_cc_pct.isChecked()),
                    })
                    self._block.config["calc_cols"] = cur_list
                    self.config_changed.emit(self._block.id)
                    self.show_block(self._block)

                btn_add_cc.clicked.connect(_on_add_calc_col)
                self._lay.insertWidget(self._lay.count() - 1, btn_add_cc)

                # ── 4. ЦВЕТОВАЯ ИНДИКАЦИЯ ОТРИЦАТЕЛЬНЫХ / ПОЛОЖИТЕЛЬНЫХ ЧИСЕЛ ──
                self._section_header("4. ЦВЕТОВАЯ ИНДИКАЦИЯ ЗНАЧЕНИЙ (+ / −)")
                self._field_checkbox(
                    "🎨 Выделять положительные и отрицательные числа цветом",
                    "color_calc_enabled",
                    cfg,
                    False,
                )

                _COLOR_SCOPES = [
                    ("В вычисляемых столбцах и столбцах отклонений", "calc_and_dev"),
                    ("Только в добавленных вычисляемых столбцах (🧮)", "calc_only"),
                    ("Во всех числовых столбцах сводной таблицы", "all_cols"),
                ]
                self._field_combo("Где применять цветовую подсветку:", "color_calc_scope", cfg, _COLOR_SCOPES, "calc_and_dev")

                def _make_color_picker_row(lbl_text: str, cfg_key: str, default_hex: str):
                    self._add_label(lbl_text)
                    row_c = QHBoxLayout()
                    row_c.setSpacing(6)
                    cur_hex = str(cfg.get(cfg_key, default_hex) or default_hex)

                    ed_hex = QLineEdit(cur_hex)
                    self._style_input(ed_hex)

                    btn_pick = QPushButton("🎨 Выбрать")
                    btn_pick.setCursor(Qt.PointingHandCursor)
                    btn_pick.setFixedWidth(88)
                    btn_pick.setStyleSheet(
                        f"QPushButton {{ background:{cur_hex}; color:#ffffff; border:1px solid {self.theme.border}; "
                        f"border-radius:4px; padding:4px 8px; font-size:11px; font-weight:700; }}"
                    )

                    def _on_hex_typed(v_txt: str):
                        v_clean = v_txt.strip()
                        if len(v_clean) in (4, 7) and v_clean.startswith("#"):
                            btn_pick.setStyleSheet(
                                f"QPushButton {{ background:{v_clean}; color:#ffffff; border:1px solid {self.theme.border}; "
                                f"border-radius:4px; padding:4px 8px; font-size:11px; font-weight:700; }}"
                            )
                            self._change_block(cfg_key, v_clean)

                    def _open_color_dlg():
                        c_dlg = QColorDialog.getColor( parent=self, title=lbl_text)
                        if c_dlg.isValid():
                            new_hex = c_dlg.name()
                            ed_hex.setText(new_hex)
                            self._change_block(cfg_key, new_hex)

                    ed_hex.textChanged.connect(_on_hex_typed)
                    btn_pick.clicked.connect(_open_color_dlg)
                    row_c.addWidget(ed_hex, 1)
                    row_c.addWidget(btn_pick)
                    self._lay.insertWidget(self._lay.count() - 1, self._wrap_row(row_c))

                _make_color_picker_row("Цвет для ОТРИЦАТЕЛЬНЫХ значений (< 0):", "neg_color", "#16a34a")
                _make_color_picker_row("Цвет для ПОЛОЖИТЕЛЬНЫХ значений (> 0):", "pos_color", "#dc2626")
                self._field_checkbox("Мягкая заливка фона ячейки в тон цвета", "color_calc_bg", cfg, True)

                # ── 5. ЗАКРЕПЛЕНИЕ ШАПКИ, ПЕРВОГО СТОЛБЦА И ПРОКРУТКА ──
                self._section_header("5. ЗАКРЕПЛЕНИЕ ОБЛАСТЕЙ И ОТОБРАЖЕНИЕ")
                self._field_checkbox("📌 Закрепить шапку таблицы при прокрутке вниз", "sticky_header", cfg, True)
                self._field_checkbox("📌 Закрепить первый столбец (названия строк) при прокрутке вбок", "sticky_first_col", cfg, True)
                self._field_int(
                    "Макс. высота таблицы со скроллом (px, 0 = без лимита)",
                    "max_table_height",
                    cfg,
                    default=520,
                    min_val=0,
                    max_val=3000,
                )

                chk_tot = QCheckBox("Показывать строку и столбец «Итого»")
                chk_tot.setChecked(bool(cfg.get("show_totals", True)))
                chk_tot.setStyleSheet(f"QCheckBox {{ color:{self.theme.text_main}; font-size:11px; background:transparent; }}")
                chk_tot.toggled.connect(lambda v: self._change_block("show_totals", bool(v)))
                self._lay.insertWidget(self._lay.count() - 1, chk_tot)

                self._add_label("Максимум групп 1-го уровня (Топ N)")
                sp_top = QSpinBox()
                sp_top.setRange(5, 500)
                sp_top.setValue(int(cfg.get("top_n", 30) or 30))
                self._style_input(sp_top)
                sp_top.valueChanged.connect(lambda v: self._change_block("top_n", int(v)))
                self._lay.insertWidget(self._lay.count() - 1, sp_top)

                # ── 6. ПОИСК И СВЯЗКА С ТАБЛИЦЕЙ ПУТЕВЫХ ЛИСТОВ ──
                self._section_header("6. ПОИСК И СВЯЗКА С ТАБЛИЦЕЙ ПУТЕВЫХ ЛИСТОВ")
                self._field_checkbox(
                    "🔍 Показывать поле поиска по госномеру / модели в шапке",
                    "show_search",
                    cfg,
                    True,
                )

                self._add_label("Синхронизировать поиск с Таблицей путевых листов:")
                cb_ttbl = QComboBox()
                cb_ttbl.addItem("🌐 Все таблицы данных в отчёте (Авто)", "")
                cb_ttbl.addItem("🚫 Не фильтровать таблицы данных", "__NONE__")

                if hasattr(self, "report_ref") and self.report_ref:
                    def _find_tables(blocks_list):
                        res = []
                        for b in (blocks_list or []):
                            b_type = b.get("type") if isinstance(b, dict) else getattr(b, "type", "")
                            if b_type == "data_table":
                                res.append(b)
                            elif b_type == "container":
                                b_cfg = b.get("config", {}) if isinstance(b, dict) else (getattr(b, "config", {}) or {})
                                res.extend(_find_tables(b_cfg.get("children", [])))
                        return res

                    for sec in self.report_ref.sections:
                        for tb in _find_tables(sec.blocks):
                            t_id = tb.get("id", "") if isinstance(tb, dict) else getattr(tb, "id", "")
                            t_cfg = tb.get("config", {}) if isinstance(tb, dict) else (getattr(tb, "config", {}) or {})
                            t_title = t_cfg.get("title") or "Таблица путевых листов"
                            cb_ttbl.addItem(f"📋 {t_title} (ID: {str(t_id)[:4]})", str(t_id))

                cur_ttbl = str(cfg.get("target_table", "") or "")
                idx_tt = cb_ttbl.findData(cur_ttbl)
                cb_ttbl.setCurrentIndex(idx_tt if idx_tt >= 0 else 0)
                self._style_input(cb_ttbl)
                cb_ttbl.currentIndexChanged.connect(lambda i: self._change_block("target_table", cb_ttbl.itemData(i)))
                self._lay.insertWidget(self._lay.count() - 1, cb_ttbl)

                btn_spawn_tbl = QPushButton("➕ Создать и привязать таблицу путевых листов под сводной")
                btn_spawn_tbl.setCursor(Qt.PointingHandCursor)
                btn_spawn_tbl.setStyleSheet(
                    f"QPushButton {{ background:{self.theme.primary}; color:{self.theme.text_inverse}; "
                    f"border:none; border-radius:6px; padding:7px 10px; font-size:11px; font-weight:700; }}"
                    f"QPushButton:hover {{ background:#9ade4f; }}"
                )

                def _on_create_linked_waybills_table():
                    if self._block is None or not hasattr(self, "report_ref") or self.report_ref is None:
                        return
                    from src.core.report_model import ReportBlock
                    found_parent = self.report_ref.find_block_parent(self._block.id)
                    if not found_parent:
                        return
                    _sec, parent_list, piv_blk = found_parent
                    piv_cfg = dict(piv_blk.config or {})

                    new_tbl_cfg = {
                        "title": "Реестр путевых листов",
                        "source_file_name": piv_cfg.get("source_file_name", ""),
                        "source_sheet": piv_cfg.get("source_sheet", ""),
                        "max_rows": 20,
                        "width": 100,
                        "align": "left",
                        "offset_x": 0,
                    }
                    new_tbl_block = ReportBlock.create("data_table", new_tbl_cfg)
                    ins_idx = parent_list.index(piv_blk) + 1
                    parent_list.insert(ins_idx, new_tbl_block)

                    piv_cfg["target_table"] = new_tbl_block.id
                    piv_blk.config = piv_cfg
                    self.config_changed.emit(piv_blk.id)
                    self.show_block(piv_blk)

                btn_spawn_tbl.clicked.connect(_on_create_linked_waybills_table)
                self._lay.insertWidget(self._lay.count() - 1, btn_spawn_tbl)

            elif block.type == "decomposition":
                self._section_header("2. НАСТРОЙКИ ДЕРЕВА ДЕКОМПОЗИЦИИ")
                self._add_label("Заголовок блока")
                ed_title = QLineEdit(str(cfg.get("title", "Дерево декомпозиции")))
                self._style_input(ed_title)
                ed_title.textChanged.connect(lambda v: self._change_block("title", v))
                self._lay.insertWidget(self._lay.count() - 1, ed_title)

                self._add_label("Вид визуализации иерархии")
                cb_mode = QComboBox()
                cb_mode.addItem("🌳 Дерево прямоугольников (Treemap)", "treemap")
                cb_mode.addItem("☀ Солнечные лучи / Кольца (Sunburst)", "sunburst")
                idx_m = cb_mode.findData(cfg.get("tree_mode", "treemap"))
                cb_mode.setCurrentIndex(idx_m if idx_m >= 0 else 0)
                self._style_input(cb_mode)
                cb_mode.currentIndexChanged.connect(lambda i: self._change_block("tree_mode", cb_mode.itemData(i)))
                self._lay.insertWidget(self._lay.count() - 1, cb_mode)

                _make_col_combo("Уровень 1 — Основная группа (напр. Тип ТС):", "level1_col")
                _make_col_combo("Уровень 2 — Подкатегория (напр. Марка):", "level2_col", allow_empty=True)
                _make_col_combo("Уровень 3 — Детализация (напр. Гос. номер):", "level3_col", allow_empty=True)
                _make_col_combo("Числовой показатель (Вес блока):", "value_col")

                self._add_label("Функция расчёта")
                cb_agg = QComboBox()
                for k_agg, lbl_agg in (("sum", "Сумма"), ("mean", "Среднее"), ("count", "Количество записей")):
                    cb_agg.addItem(lbl_agg, k_agg)
                idx_a = cb_agg.findData(cfg.get("agg_func", "sum"))
                cb_agg.setCurrentIndex(idx_a if idx_a >= 0 else 0)
                self._style_input(cb_agg)
                cb_agg.currentIndexChanged.connect(lambda i: self._change_block("agg_func", cb_agg.itemData(i)))
                self._lay.insertWidget(self._lay.count() - 1, cb_agg)

                self._add_label("Цветовая палитра")
                cb_pal = QComboBox()
                for k_p, lbl_p in (("Greens", "🌿 Изумрудная (Greens)"), ("Blues", "🌊 Синяя (Blues)"), ("Viridis", "🔮 Контрастная (Viridis)"), ("YlOrRd", "🔥 Тепловая (YlOrRd)")):
                    cb_pal.addItem(lbl_p, k_p)
                idx_p = cb_pal.findData(cfg.get("palette", "Greens"))
                cb_pal.setCurrentIndex(idx_p if idx_p >= 0 else 0)
                self._style_input(cb_pal)
                cb_pal.currentIndexChanged.connect(lambda i: self._change_block("palette", cb_pal.itemData(i)))
                self._lay.insertWidget(self._lay.count() - 1, cb_pal)

            elif block.type == "geo_map":
                self._section_header("2. НАСТРОЙКИ ГЕО-КАРТЫ И ЛОКАЦИЙ")
                self._add_label("Заголовок блока")
                ed_title = QLineEdit(str(cfg.get("title", "География и рейтинг объектов")))
                self._style_input(ed_title)
                ed_title.textChanged.connect(lambda v: self._change_block("title", v))
                self._lay.insertWidget(self._lay.count() - 1, ed_title)

                self._add_label("Режим отображения")
                cb_gmode = QComboBox()
                cb_gmode.addItem("📊 Рейтинг по локациям / филиалам / группам (Bar)", "ranking_bar")
                cb_gmode.addItem("🗺 Тепловая плитка объектов (Treemap)", "treemap")
                cb_gmode.addItem("🌍 Географическая карта стран (Choropleth)", "choropleth")
                idx_gm = cb_gmode.findData(cfg.get("map_mode", "ranking_bar"))
                cb_gmode.setCurrentIndex(idx_gm if idx_gm >= 0 else 0)
                self._style_input(cb_gmode)
                cb_gmode.currentIndexChanged.connect(lambda i: self._change_block("map_mode", cb_gmode.itemData(i)))
                self._lay.insertWidget(self._lay.count() - 1, cb_gmode)

                _make_col_combo("Колонка локации / филиала / подразделения:", "loc_col")
                _make_col_combo("Числовой показатель (Окраска и размер):", "value_col")

                self._add_label("Функция расчёта")
                cb_agg = QComboBox()
                for k_agg, lbl_agg in (("sum", "Сумма"), ("mean", "Среднее"), ("count", "Количество записей"), ("max", "Максимум")):
                    cb_agg.addItem(lbl_agg, k_agg)
                idx_a = cb_agg.findData(cfg.get("agg_func", "sum"))
                cb_agg.setCurrentIndex(idx_a if idx_a >= 0 else 0)
                self._style_input(cb_agg)
                cb_agg.currentIndexChanged.connect(lambda i: self._change_block("agg_func", cb_agg.itemData(i)))
                self._lay.insertWidget(self._lay.count() - 1, cb_agg)

                self._add_label("Количество объектов (Топ N)")
                sp_top = QSpinBox()
                sp_top.setRange(5, 100)
                sp_top.setValue(int(cfg.get("top_n", 20) or 20))
                self._style_input(sp_top)
                sp_top.valueChanged.connect(lambda v: self._change_block("top_n", int(v)))
                self._lay.insertWidget(self._lay.count() - 1, sp_top)

        elif block.type == "data_table":
            self._section_header("1. Источник данных (Файл и Лист путевых листов)")
            self._build_source_selectors(cfg)
            self._all_columns = self._get_target_columns(cfg)

            self._section_header("2. Параметры таблицы путевых листов")
            self._field_text("Заголовок таблицы", "title", cfg, placeholder="Например: Реестр путевых листов")
            self._field_int(
                "Видимых строк в окне", "max_rows", cfg, default=20, min_val=0, max_val=10000,
                tooltip="Количество видимых строк по высоте окна таблицы.",
            )
            self._section_header("3. Отображаемые колонки")
            self._field_columns(cfg)
            
        elif block.type == "container":
            self._section_header("Расположение графиков / блоков в группе")
            self._field_container_layout(cfg)

            children = cfg.get("children", [])
            if children:
                btn_pos = QPushButton(f"📐 Позиционирование блоков ({len(children)} шт.)")
                btn_pos.setCursor(Qt.PointingHandCursor)
                btn_pos.setStyleSheet(
                    f"QPushButton {{ background:{self.theme.primary}; color:{self.theme.text_inverse}; "
                    f"border:none; border-radius:6px; padding:8px 10px; font-size:11px; font-weight:700; }}"
                    f"QPushButton:hover {{ background:#9ade4f; }}"
                )
                btn_pos.clicked.connect(lambda _, b_ref=block: self._open_container_layout_dialog(b_ref))
                self._lay.insertWidget(self._lay.count() - 1, btn_pos)

            row_cnt = QHBoxLayout()
            row_cnt.setSpacing(4)
            self._field_spin_inline("Отступ между блоками (px)", "gap", cfg, 14, 0, 100, parent_layout=row_cnt)
            self._lay.insertWidget(self._lay.count() - 1, self._wrap_row(row_cnt))

            if children:
                self._section_header(f"Размеры и порядок блоков в контейнере ({len(children)})")
                self._build_container_children_controls(block, children)

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

    def _open_container_layout_dialog(self, container_block):
        """Открывает окно с визуальными схемами позиционирования блоков в зависимости от их количества."""
        cfg = dict(container_block.config or {})
        children = list(cfg.get("children", []))
        n = len(children)
        if n == 0:
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Позиционирование блоков в контейнере (блоков: {n})")
        dlg.setMinimumWidth(520)
        dlg.setStyleSheet(f"QDialog {{ background:{self.theme.bg_card}; color:{self.theme.text_main}; }}")

        root = QVBoxLayout(dlg)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        title_lbl = QLabel(f"Выберите схему расположения для {n} блоков:")
        title_lbl.setStyleSheet(f"color:{self.theme.text_main}; font-size:14px; font-weight:700;")
        root.addWidget(title_lbl)

        # Определяем, является ли первый блок узким срезом (фильтром)
        first_type = children[0].get("type") if isinstance(children[0], dict) else getattr(children[0], "type", "")
        top_pair_widths = (25, 75) if first_type == "dashboard_filter" else (50, 50)

        # Формируем варианты раскладок в зависимости от числа блоков в контейнере
        if n == 3:
            presets = [
                (
                    "1) Друг под другом",
                    "3 блока вертикально друг под другом на всю ширину",
                    "column",
                    [{"width": 100, "full_row": False}, {"width": 100, "full_row": False}, {"width": 100, "full_row": False}],
                    [[("1", 100)], [("2", 100)], [("3", 100)]],
                ),
                (
                    "2) 2 рядом сверху, 1 под ними",
                    "Блоки 1 и 2 стоят рядом друг с другом, блок 3 — на всю ширину под ними",
                    "row",
                    [
                        {"width": top_pair_widths[0], "full_row": False},
                        {"width": top_pair_widths[1], "full_row": False},
                        {"width": 100, "full_row": False},
                    ],
                    [[("1", top_pair_widths[0]), ("2", top_pair_widths[1])], [("3", 100)]],
                ),
                (
                    "3) 3 рядом друг с другом",
                    "Все 3 блока выстроены в один общий горизонтальный ряд",
                    "row",
                    [{"width": 33, "full_row": False}, {"width": 33, "full_row": False}, {"width": 34, "full_row": False}],
                    [[("1", 33), ("2", 33), ("3", 34)]],
                ),
                (
                    "4) 1 по центру сверху и 2 рядом под ним",
                    "Блок 1 расположен сверху по центру, а блоки 2 и 3 — рядом друг с другом под ним",
                    "row",
                    [
                        {"width": 70, "full_row": True},
                        {"width": 50, "full_row": False},
                        {"width": 50, "full_row": False},
                    ],
                    [[("1 (по центру)", 70)], [("2", 50), ("3", 50)]],
                ),
            ]
        elif n == 2:
            presets = [
                (
                    "1) Друг под другом",
                    "2 блока вертикально друг под другом (100% / 100%)",
                    "column",
                    [{"width": 100, "full_row": False}, {"width": 100, "full_row": False}],
                    [[("1", 100)], [("2", 100)]],
                ),
                (
                    "2) 2 рядом поровну (50% + 50%)",
                    "Два одинаковых блока рядом друг с другом",
                    "row",
                    [{"width": 50, "full_row": False}, {"width": 50, "full_row": False}],
                    [[("1 (50%)", 50), ("2 (50%)", 50)]],
                ),
                (
                    "3) Фильтр слева + График справа (25% + 75%)",
                    "Узкая панель слева и широкий график справа",
                    "row",
                    [{"width": 25, "full_row": False}, {"width": 75, "full_row": False}],
                    [[("1 (25%)", 25), ("2 (75%)", 75)]],
                ),
                (
                    "4) График слева + Панель справа (75% + 25%)",
                    "Широкий блок слева и узкая колонка справа",
                    "row",
                    [{"width": 75, "full_row": False}, {"width": 25, "full_row": False}],
                    [[("1 (75%)", 75), ("2 (25%)", 25)]],
                ),
            ]
        else:
            eq_w = max(20, 100 // n)
            rem_w = max(20, 100 // max(1, n - 1))
            presets = [
                (
                    "1) Друг под другом",
                    f"Все {n} блоков вертикально друг под другом",
                    "column",
                    [{"width": 100, "full_row": False} for _ in range(n)],
                    [[(str(i + 1), 100)] for i in range(min(n, 4))],
                ),
                (
                    "2) Сетка по 2 блока в ряд (2×2)",
                    "По 2 блока рядом друг с другом на каждой строке",
                    "row",
                    [
                        {"width": 100 if (i == n - 1 and n % 2 == 1) else 50, "full_row": False}
                        for i in range(n)
                    ],
                    [[("1", 50), ("2", 50)], [("3", 50), ("4", 50)]],
                ),
                (
                    f"3) Все рядом в один ряд ({n} шт.)",
                    "Все блоки выстроены в одну горизонтальную линию",
                    "row",
                    [{"width": eq_w, "full_row": False} for _ in range(n)],
                    [[(str(i + 1), eq_w) for i in range(min(n, 4))]],
                ),
                (
                    "4) 1 по центру сверху + остальные рядом под ним",
                    "Первый блок сверху по центру, остальные стоят в ряд под ним",
                    "row",
                    [{"width": 75, "full_row": True}] + [{"width": rem_w, "full_row": False} for _ in range(n - 1)],
                    [[("1 (по центру)", 75)], [(str(i + 2), rem_w) for i in range(min(n - 1, 3))]],
                ),
            ]

        grid = QGridLayout()
        grid.setSpacing(12)

        def apply_preset(layout_mode: str, child_rules: list[dict]):
            cfg["layout"] = layout_mode
            for idx_c, ch in enumerate(children):
                rule = child_rules[idx_c] if idx_c < len(child_rules) else {"width": 100, "full_row": False}
                if isinstance(ch, dict):
                    c_dict = ch.setdefault("config", {})
                    c_dict["width"] = rule["width"]
                    c_dict["full_row"] = rule.get("full_row", False)
                else:
                    if ch.config is None:
                        ch.config = {}
                    ch.config["width"] = rule["width"]
                    ch.config["full_row"] = rule.get("full_row", False)
            cfg["children"] = children
            container_block.config = cfg
            self.config_changed.emit(container_block.id)
            dlg.accept()
            QTimer.singleShot(0, lambda b=container_block: self.show_block(b))

        for idx_p, (p_title, p_desc, p_layout, p_rules, visual_rows) in enumerate(presets):
            card = QFrame()
            card.setCursor(Qt.PointingHandCursor)
            card.setStyleSheet(
                f"QFrame {{ background:{self.theme.bg_panel}; border:1px solid {self.theme.border}; "
                f"border-radius:8px; padding:8px; }}"
                f"QFrame:hover {{ border:2px solid {self.theme.primary}; }}"
            )
            c_lay = QVBoxLayout(card)
            c_lay.setContentsMargins(8, 8, 8, 8)
            c_lay.setSpacing(6)

            lbl_t = QLabel(p_title)
            lbl_t.setStyleSheet(f"color:{self.theme.text_main}; font-size:12px; font-weight:700; border:none;")
            c_lay.addWidget(lbl_t)

            # Рисуем визуальную мини-схему блоков
            preview_box = QFrame()
            preview_box.setFixedHeight(92)
            preview_box.setStyleSheet(
                f"QFrame {{ background:{self.theme.bg_card}; border:1px dashed {self.theme.border}; border-radius:6px; }}"
            )
            pv_lay = QVBoxLayout(preview_box)
            pv_lay.setContentsMargins(6, 6, 6, 6)
            pv_lay.setSpacing(4)

            for v_row in visual_rows:
                r_lay = QHBoxLayout()
                r_lay.setContentsMargins(0, 0, 0, 0)
                r_lay.setSpacing(4)
                if len(v_row) == 1 and v_row[0][1] < 100:
                    r_lay.addStretch(1)
                for b_label, b_w in v_row:
                    blk_vis = QLabel(f"Блок {b_label}")
                    blk_vis.setAlignment(Qt.AlignCenter)
                    blk_vis.setStyleSheet(
                        "background:#87C800; color:#ffffff; font-size:10px; font-weight:700; "
                        "border-radius:4px; padding:4px; border:none;"
                    )
                    r_lay.addWidget(blk_vis, max(1, int(b_w)))
                if len(v_row) == 1 and v_row[0][1] < 100:
                    r_lay.addStretch(1)
                pv_lay.addLayout(r_lay, 1)

            c_lay.addWidget(preview_box)

            lbl_d = QLabel(p_desc)
            lbl_d.setWordWrap(True)
            lbl_d.setStyleSheet(f"color:{self.theme.text_muted}; font-size:10px; border:none;")
            c_lay.addWidget(lbl_d)

            btn_choose = QPushButton("Применить эту схему")
            btn_choose.setCursor(Qt.PointingHandCursor)
            btn_choose.setStyleSheet(
                f"QPushButton {{ background:{self.theme.bg_card}; color:{self.theme.text_main}; "
                f"border:1px solid {self.theme.primary}; border-radius:4px; padding:5px; font-size:11px; font-weight:600; }}"
                f"QPushButton:hover {{ background:{self.theme.primary}; color:{self.theme.text_inverse}; }}"
            )
            btn_choose.clicked.connect(lambda _, lm=p_layout, rl=p_rules: apply_preset(lm, rl))
            c_lay.addWidget(btn_choose)

            grid.addWidget(card, idx_p // 2, idx_p % 2)

        root.addLayout(grid)
        dlg.exec()

    # ── Управление дочерними блоками внутри контейнера ──
    def _build_container_children_controls(self, container_block, children: list):
        for idx, child in enumerate(children):
            c_type = child.get("type") if isinstance(child, dict) else getattr(child, "type", "")
            c_cfg = child.get("config", {}) if isinstance(child, dict) else (getattr(child, "config", {}) or {})
            c_title = c_cfg.get("title") or BLOCK_TYPES.get(c_type, c_type)
            c_width = int(c_cfg.get("width", 50))
            if c_width >= 100:
                c_width = max(20, 100 // max(1, len(children)))

            row = QHBoxLayout()
            row.setSpacing(4)

            lbl = QLabel(f"{idx + 1}. {c_title[:16]}")
            lbl.setStyleSheet(f"color:{self.theme.text_main}; font-size:11px; background:transparent;")
            row.addWidget(lbl, 1)

            sp_w = QSpinBox()
            sp_w.setRange(15, 100)
            sp_w.setSuffix("%")
            sp_w.setValue(c_width)
            sp_w.setFixedWidth(64)
            sp_w.setToolTip("Ширина этого блока внутри контейнера (%)")
            self._style_input(sp_w)

            def on_child_w(val, child_ref=child):
                if isinstance(child_ref, dict):
                    child_ref.setdefault("config", {})["width"] = val
                else:
                    if child_ref.config is None:
                        child_ref.config = {}
                    child_ref.config["width"] = val
                self.config_changed.emit(container_block.id)

            sp_w.valueChanged.connect(on_child_w)
            row.addWidget(sp_w)

            btn_up = QPushButton("⬆")
            btn_up.setFixedWidth(24)
            btn_up.setEnabled(idx > 0)
            btn_up.setToolTip("Переместить левее / выше")
            self._style_input(btn_up)

            btn_dn = QPushButton("⬇")
            btn_dn.setFixedWidth(24)
            btn_dn.setEnabled(idx < len(children) - 1)
            btn_dn.setToolTip("Переместить правее / ниже")
            self._style_input(btn_dn)

            def move_child(delta: int, cur_i=idx):
                new_i = cur_i + delta
                if 0 <= new_i < len(children):
                    children[cur_i], children[new_i] = children[new_i], children[cur_i]
                    container_block.config["children"] = list(children)
                    self.config_changed.emit(container_block.id)
                    self.show_block(container_block)

            btn_up.clicked.connect(lambda _, d=-1: move_child(d))
            btn_dn.clicked.connect(lambda _, d=1: move_child(d))

            row.addWidget(btn_up)
            row.addWidget(btn_dn)

            self._lay.insertWidget(self._lay.count() - 1, self._wrap_row(row))


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
                def_file, def_sheet = manager.get_default_file_and_sheet()
                cur_file = def_file if def_file in files_dict else next(iter(files_dict.keys()))
                cfg["source_file_name"] = cur_file

            sheets_for_file = files_dict.get(cur_file, [])
            if sheets_for_file and (not cur_sheet or cur_sheet not in sheets_for_file):
                cur_sheet = sheets_for_file[0]
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
        target_df = self._get_target_dataframe(cfg)
        if target_df is not None:
            return [str(c) for c in target_df.columns]
        return self._all_columns

    def _build_source_selectors(self, cfg: dict):
        cur_file, cur_sheet, files_dict = self._ensure_source_pinned(cfg)
        if self._block is not None:
            self._block.config = cfg

        self._add_label("Файл источника")
        cb_file = QComboBox()
        if not files_dict:
            cb_file.addItem("— Нет файлов —", "")
        else:
            for file_name in files_dict.keys():
                cb_file.addItem(str(file_name), str(file_name))
            idx_f = cb_file.findData(cur_file)
            cb_file.setCurrentIndex(idx_f if idx_f >= 0 else 0)

        self._style_input(cb_file)
        self._lay.insertWidget(self._lay.count() - 1, cb_file)

        self._add_label("Лист таблицы")
        cb_sheet = QComboBox()
        sheets = files_dict.get(cur_file, []) if files_dict else []
        if not sheets:
            cb_sheet.addItem("— Нет листов —", "")
        else:
            for s in sheets:
                cb_sheet.addItem(str(s), str(s))
            idx_s = cb_sheet.findData(cur_sheet)
            cb_sheet.setCurrentIndex(idx_s if idx_s >= 0 else 0)

        self._style_input(cb_sheet)
        self._lay.insertWidget(self._lay.count() - 1, cb_sheet)

        def on_file_changed(i):
            f_name = cb_file.itemData(i)
            if not f_name: return
            avail_sheets = files_dict.get(f_name, [])
            new_sheet = avail_sheets[0] if avail_sheets else ""
            if self._block is not None:
                new_cfg = dict(self._block.config or {})
                new_cfg["source_file_name"] = f_name
                new_cfg["source_sheet"] = new_sheet
                self._block.config = new_cfg
                self.config_changed.emit(self._block.id)
                QTimer.singleShot(0, lambda b=self._block: self.show_block(b) if b else None)

        def on_sheet_changed(i):
            s_name = cb_sheet.itemData(i)
            if not s_name: return
            self._change_block("source_sheet", s_name)
            if self._block is not None:
                QTimer.singleShot(0, lambda b=self._block: self.show_block(b) if b else None)

        cb_file.currentIndexChanged.connect(on_file_changed)
        cb_sheet.currentIndexChanged.connect(on_sheet_changed)

    def _build_chart_settings(self, cfg: dict):
        self._section_header("1. Источник данных (Файл и Лист)")
        self._build_source_selectors(cfg)

        self._section_header("2. Тип и заголовок графика")
        self._field_text("Заголовок графика", "title", cfg, placeholder="Например: Расход топлива по месяцам")

        self._add_label("Тип визуализации")
        cb_type = QComboBox()
        for title, val in _CHART_TYPES:
            cb_type.addItem(title, val)
        cur_type = cfg.get("chart_type", "bar")
        idx_t = cb_type.findData(cur_type)
        cb_type.setCurrentIndex(idx_t if idx_t >= 0 else 0)
        self._style_input(cb_type)

        def on_chart_type_changed(i):
            new_t = cb_type.itemData(i)
            self._change_block("chart_type", new_t)
            if self._block:
                QTimer.singleShot(0, lambda b=self._block: self.show_block(b) if b else None)

        cb_type.currentIndexChanged.connect(on_chart_type_changed)
        self._lay.insertWidget(self._lay.count() - 1, cb_type)

        self._section_header("3. Источник данных (Режим)")
        self._add_label("Как обрабатывать данные")
        cb_mode = QComboBox()
        for title, val in _DATA_MODES:
            cb_mode.addItem(title, val)
        cur_mode = cfg.get("data_mode", "columns")
        idx_m = cb_mode.findData(cur_mode)
        cb_mode.setCurrentIndex(idx_m if idx_m >= 0 else 0)
        self._style_input(cb_mode)

        def on_mode_changed(i):
            new_m = cb_mode.itemData(i)
            self._change_block("data_mode", new_m)
            if self._block:
                QTimer.singleShot(0, lambda b=self._block: self.show_block(b) if b else None)

        cb_mode.currentIndexChanged.connect(on_mode_changed)
        self._lay.insertWidget(self._lay.count() - 1, cb_mode)

        # Получаем правильные колонки для выбранного листа
        actual_cols = self._get_target_columns(cfg)

        if cur_type == "combo":
            self._build_combo_chart_inspector(cfg, actual_cols)
        elif cur_mode == "rows":
            self._field_row_mode_selectors(cfg, actual_cols)
        else:
            self._field_axis_selectors(cfg, actual_cols)
            self._field_combo("Функция расчёта (Агрегация)", "agg", cfg, _AGG_FUNCS, "sum")
            self._field_combo("Сортировка данных", "sort_by", cfg, _SORT_MODES, "value_desc")

        row_slice = QHBoxLayout()
        row_slice.setSpacing(4)
        self._field_spin_inline("Топ Категорий", "top_n", cfg, 12, 0, 500, parent_layout=row_slice)
        self._field_spin_inline("С какой строки", "row_start", cfg, 0, 0, 100000, parent_layout=row_slice)
        self._field_spin_inline("Лимит строк", "row_limit", cfg, 0, 0, 100000, parent_layout=row_slice)
        self._lay.insertWidget(self._lay.count() - 1, self._wrap_row(row_slice))

        self._section_header("4. Умный отбор данных (Условие ЕСЛИ)")
        self._field_chart_filter_rules(cfg, actual_cols)

        self._section_header("5. Легенда, Переименование столбцов и Стиль")
        self._field_text(
            "Название сводки «Все значения» (вместо «Итого (Все типы ТС)»)",
            "all_groups_label",
            cfg,
            placeholder="Например: Весь автопарк  (или оставьте пустым)",
        )
        self._field_checkbox(
            "Добавлять название группы перед каждым столбцом в легенде",
            "prefix_legend_with_group",
            cfg,
            False,
        )
        self._field_text(
            "Свои названия рядов в легенде (через запятую или Старое=Новое)",
            "custom_legend_names",
            cfg,
            placeholder="Напр.: Факт ГСМ, Норма ГСМ, По регламенту",
        )

        # Индивидуальные поля переименования для каждого выбранного столбца графика
        active_chart_cols: list[str] = []
        for raw_c in str(cfg.get("y_col", "") or "").split(","):
            c_clean = raw_c.strip()
            if c_clean and c_clean not in active_chart_cols:
                active_chart_cols.append(c_clean)
        for extra_k in ("norm_col", "fact_col"):
            ec = str(cfg.get(extra_k, "") or "").strip()
            if ec and ec not in active_chart_cols:
                active_chart_cols.append(ec)

        if active_chart_cols:
            self._add_label("Индивидуальные названия выбранных столбцов:")
            cur_aliases = dict(cfg.get("column_aliases") or {})
            for col_orig in active_chart_cols:
                row_al = QHBoxLayout()
                row_al.setSpacing(6)
                lbl_orig = QLabel(col_orig[:22] + ("…" if len(col_orig) > 22 else ""))
                lbl_orig.setToolTip(col_orig)
                lbl_orig.setStyleSheet(f"color:{self.theme.text_muted}; font-size:10px; min-width:110px;")
                ed_al = QLineEdit(str(cur_aliases.get(col_orig, "")))
                ed_al.setPlaceholderText(f"Новое имя для «{col_orig}»...")
                self._style_input(ed_al)

                def _on_alias_edit(val_txt: str, c_key: str = col_orig):
                    if self._block is None:
                        return
                    new_cfg = dict(self._block.config or {})
                    al_map = dict(new_cfg.get("column_aliases") or {})
                    if val_txt.strip():
                        al_map[c_key] = val_txt.strip()
                    else:
                        al_map.pop(c_key, None)
                    new_cfg["column_aliases"] = al_map
                    self._block.config = new_cfg
                    self.config_changed.emit(self._block.id)

                ed_al.textChanged.connect(_on_alias_edit)
                row_al.addWidget(lbl_orig)
                row_al.addWidget(ed_al, 1)
                self._lay.insertWidget(self._lay.count() - 1, self._wrap_row(row_al))

        self._field_text("Своя подпись оси X (необязательно)", "custom_x_title", cfg, placeholder="Например: Месяцы 2026 г.")
        self._field_text("Своя подпись оси Y (необязательно)", "custom_y_title", cfg, placeholder="Например: Расход топлива, л")

        self._field_combo("Цветовая палитра", "palette", cfg, _PALETTES, "corporate")
        self._field_background_picker(cfg)
        self._field_combo("Позиция легенды", "legend_pos", cfg, _LEGEND_POS, "right")
        self._field_int("Размер шрифта текста (px)", "font_size", cfg, default=12, min_val=8, max_val=48)

        self._section_header("6. Надписи на графике и при наведении мыши")
        _LABEL_MODES = [
            ("Авто (Категория + Доля %)", "auto"),
            ("Только процент (%)", "percent"),
            ("Категория + Процент (%)", "label+percent"),
            ("Процент + Значение", "percent+value"),
            ("Категория + Значение + Процент (%)", "label+value+percent"),
            ("Только числовое значение", "value"),
            ("Только название категории", "label"),
            ("Скрыть надписи на элементах", "none"),
        ]
        self._field_combo("Надписи на элементах графика", "value_label_mode", cfg, _LABEL_MODES, "auto")

        _HOVER_MODES = [
            ("Подробный (Категория + Значение + Доля % + Детализация)", "default"),
            ("Только Категория и Доля (%)", "label_percent"),
            ("Только Категория и Значение", "label_value"),
            ("Свой шаблон подсказки (ввести ниже)", "custom"),
        ]
        self._field_combo("Вид подсказки при наведении мыши", "hover_format", cfg, _HOVER_MODES, "default")
        self._field_text(
            "Свой шаблон при наведении мыши (необязательно)",
            "hover_custom_tpl",
            cfg,
            placeholder="Напр.: {label} | Значение: {value} ({percent}) | {details}",
        )
        self._add_hint(
            "💡 Теги для шаблона: {label} — категория/элемент, {value} — расчётное значение, "
            "{percent} — доля в %, {name} — название ряда, {details} — сводка по группе и доп. полям."
        )

        self._field_checkbox("Показывать легенду", "show_legend", cfg, True)
        self._field_checkbox("Показывать подписи значений", "show_values", cfg, True)
        self._field_checkbox("Показывать координатную сетку", "show_grid", cfg, True)
        self._field_checkbox("Показывать заголовок графика", "show_title", cfg, True)
        self._field_checkbox("Показывать подписи осей (X/Y)", "show_axis_labels", cfg, True)

    def _build_combo_chart_inspector(self, cfg: dict, cols: list[str]):
        """Интуитивный конструктор комбинированного графика с 3 уровнями погружения и 2 осями Y."""
        self._section_header("3. Иерархия погружения (3 уровня) и сортировка")

        _LEVEL_SORT_MODES = [
            ("⬇ От большего к меньшему (По убыванию)", "value_desc"),
            ("⬆ От меньшего к большему (По возрастанию)", "value_asc"),
            ("|Δ| По величине отклонения (По модулю)", "abs_desc"),
            ("А→Я По алфавиту", "label_asc"),
            ("Я→А Обратный алфавит", "label_desc"),
            ("Без сортировки (как в таблице)", "none"),
        ]

        def _make_combo_col_box(lbl_txt: str, key_name: str, empty_label: str = "— Не выбрано —", allow_none: bool = False):
            self._add_label(lbl_txt)
            cb = QComboBox()
            cb.addItem(empty_label, "")
            if allow_none:
                cb.addItem("🚫 Отключить этот уровень", "__NONE__")
            for c in cols:
                cb.addItem(str(c), str(c))
            cur_v = str(cfg.get(key_name, "") or "")
            idx_v = cb.findData(cur_v)
            cb.setCurrentIndex(idx_v if idx_v >= 0 else 0)
            self._style_input(cb)
            cb.currentIndexChanged.connect(lambda i, k=key_name, box=cb: self._change_block(k, box.itemData(i)))
            self._lay.insertWidget(self._lay.count() - 1, cb)
            return cb

        # 1-й уровень: Тип ТС + сортировка
        _make_combo_col_box("1-й уровень погружения (По типам ТС):", "combo_level1_col", "⚡ Авто (Тип ТС / Ось X)")
        self._field_combo("Сортировка 1-го уровня (Типы ТС):", "combo_level1_sort", cfg, _LEVEL_SORT_MODES, "value_desc")

        # 2-й уровень: Модель ТС + сортировка
        _make_combo_col_box("2-й уровень погружения (По моделям ТС):", "combo_level2_col", "⚡ Авто (Модель / Марка ТС)", allow_none=True)
        self._field_combo("Сортировка 2-го уровня (Модели ТС):", "combo_level2_sort", cfg, _LEVEL_SORT_MODES, "value_desc")

        # 3-й уровень: Гос. номер + сортировка
        _make_combo_col_box("3-й уровень погружения (По гос. номеру):", "combo_level3_col", "⚡ Авто (Гос. номер / ГРЗ)", allow_none=True)
        self._field_combo("Сортировка 3-го уровня (Гос. номера):", "combo_level3_sort", cfg, _LEVEL_SORT_MODES, "value_desc")

        self._section_header("3.1. Базовые столбцы ФАКТ и НОРМАТИВ и Период")
        _make_combo_col_box("Столбец ФАКТ (переменная ФАКТ / A):", "fact_col", "⚡ Авто (Фактический расход)")
        _make_combo_col_box("Столбец НОРМАТИВ (переменная НОРМАТИВ / B):", "norm_col", "⚡ Авто (Нормативный расход)")
        _make_combo_col_box("Столбец Даты / Периода (для кнопок месяцев):", "date_col", "— Без кнопок месяцев —")

        self._section_header("4. Быстрые шаблоны комбинированного графика")
        cb_preset = QComboBox()
        cb_preset.addItem("⚡ Выберите готовый шаблон серий (в 1 клик)…", "")
        cb_preset.addItem("🎯 Столбцы (Факт−Норма, Ось Y2 справа) + Линия тренда ((Факт−Норма)/Норма %, Ось Y1 слева)", "bar_diff_y2_line_pct_y1")
        cb_preset.addItem("📊 Столбцы (Факт) + 📉 Линия (Норматив) на одной оси", "fact_norm_bar_line")
        cb_preset.addItem("📊 Факт и Норма (Столбцы) + 📈 Линия отклонения (Факт − Норма)", "fact_norm_diff")
        cb_preset.addItem("⛰ Область (Норматив) + 📊 Столбцы (Факт) + 📐 % отклонения (Ось Y2)", "area_bar_pct")
        cb_preset.addItem("📊 Столбцы (Показатель) + 📈 Нарастающий итог (Линия)", "bar_cum_line")
        self._style_input(cb_preset)
        self._lay.insertWidget(self._lay.count() - 1, cb_preset)

        def _guess_fact_norm_cols() -> tuple[str, str]:
            f_c = str(cfg.get("fact_col", "") or "")
            n_c = str(cfg.get("norm_col", "") or "")
            for c in cols:
                cl = c.lower()
                if not f_c and "факт" in cl:
                    f_c = c
                elif not n_c and ("норм" in cl or "план" in cl):
                    n_c = c
            if not f_c and cols:
                f_c = cols[-1]
            if not n_c and len(cols) >= 2:
                n_c = cols[-2] if cols[-2] != f_c else cols[0]
            return f_c, n_c

        def _apply_combo_preset(idx_p: int):
            p_code = cb_preset.itemData(idx_p)
            if not p_code or self._block is None:
                return
            f_c, n_c = _guess_fact_norm_cols()
            if f_c:
                self._block.config["fact_col"] = f_c
            if n_c:
                self._block.config["norm_col"] = n_c
            new_series = []
            if p_code == "bar_diff_y2_line_pct_y1":
                new_series = [
                    {
                        "name": "Отклонение (Факт − Норматив)",
                        "source_type": "formula",
                        "col": "",
                        "formula": "ФАКТ - НОРМАТИВ",
                        "agg": "sum",
                        "plot_type": "bar",
                        "y_axis": "y2",
                        "color": "#2b7fff",
                        "line_dash": "solid",
                        "line_width": 3,
                        "marker_size": 8,
                        "opacity": 0.85,
                        "show_labels": True,
                        "suffix": "",
                        "visible": True,
                    },
                    {
                        "name": "Тенденция отклонения, %",
                        "source_type": "formula",
                        "col": "",
                        "formula": "((ФАКТ - НОРМАТИВ) / НОРМАТИВ) * 100",
                        "agg": "sum",
                        "plot_type": "line",
                        "y_axis": "y1",
                        "color": "#87C800",
                        "line_dash": "solid",
                        "line_width": 3,
                        "marker_size": 8,
                        "opacity": 1.0,
                        "show_labels": True,
                        "suffix": "%",
                        "visible": True,
                    },
                ]
            elif p_code == "fact_norm_bar_line":
                new_series = [
                    {"name": f_c or "Факт", "source_type": "column", "col": f_c, "formula": "", "agg": "sum", "plot_type": "bar", "y_axis": "y1", "color": "#2b7fff", "line_dash": "solid", "line_width": 3, "marker_size": 8, "opacity": 0.9, "show_labels": True, "suffix": ""},
                    {"name": n_c or "Норматив", "source_type": "column", "col": n_c, "formula": "", "agg": "sum", "plot_type": "line", "y_axis": "y1", "color": "#87C800", "line_dash": "solid", "line_width": 3, "marker_size": 8, "opacity": 1.0, "show_labels": True, "suffix": ""},
                ]
            elif p_code == "fact_norm_diff":
                new_series = [
                    {"name": f_c or "Факт (S1)", "source_type": "column", "col": f_c, "formula": "", "agg": "sum", "plot_type": "bar", "y_axis": "y1", "color": "#2b7fff", "line_dash": "solid", "line_width": 3, "marker_size": 8, "opacity": 0.88, "show_labels": False, "suffix": ""},
                    {"name": n_c or "Норматив (S2)", "source_type": "column", "col": n_c, "formula": "", "agg": "sum", "plot_type": "bar", "y_axis": "y1", "color": "#94a3b8", "line_dash": "solid", "line_width": 3, "marker_size": 8, "opacity": 0.88, "show_labels": False, "suffix": ""},
                    {"name": "Отклонение (S1−S2)", "source_type": "formula", "col": "", "formula": "S1 - S2", "agg": "sum", "plot_type": "spline", "y_axis": "y1", "color": "#e11d48", "line_dash": "solid", "line_width": 3, "marker_size": 8, "opacity": 1.0, "show_labels": True, "suffix": ""},
                ]
            elif p_code == "area_bar_pct":
                new_series = [
                    {"name": n_c or "Норматив (S1)", "source_type": "column", "col": n_c, "formula": "", "agg": "sum", "plot_type": "area", "y_axis": "y1", "color": "#94a3b8", "line_dash": "dot", "line_width": 2, "marker_size": 0, "opacity": 0.35, "show_labels": False, "suffix": ""},
                    {"name": f_c or "Факт (S2)", "source_type": "column", "col": f_c, "formula": "", "agg": "sum", "plot_type": "bar", "y_axis": "y1", "color": "#2b7fff", "line_dash": "solid", "line_width": 3, "marker_size": 8, "opacity": 0.9, "show_labels": True, "suffix": ""},
                    {"name": "% отклонения", "source_type": "formula", "col": "", "formula": "((S2 - S1) / S1) * 100", "agg": "sum", "plot_type": "line", "y_axis": "y2", "color": "#e11d48", "line_dash": "solid", "line_width": 3, "marker_size": 8, "opacity": 1.0, "show_labels": True, "suffix": "%"},
                ]
            elif p_code == "bar_cum_line":
                new_series = [
                    {"name": f_c or "Показатель", "source_type": "column", "col": f_c, "formula": "", "agg": "sum", "plot_type": "bar", "y_axis": "y1", "color": "#2b7fff", "line_dash": "solid", "line_width": 3, "marker_size": 8, "opacity": 0.85, "show_labels": True, "suffix": ""},
                    {"name": "Нарастающий итог", "source_type": "column", "col": f_c, "formula": "", "agg": "sum", "plot_type": "cum_line", "y_axis": "y1", "color": "#87C800", "line_dash": "solid", "line_width": 3, "marker_size": 8, "opacity": 1.0, "show_labels": True, "suffix": ""},
                ]
            self._block.config["combo_series"] = new_series
            self.config_changed.emit(self._block.id)
            QTimer.singleShot(0, lambda b=self._block: self.show_block(b) if b else None)

        cb_preset.currentIndexChanged.connect(_apply_combo_preset)

        # ── Список карточек серий на графике ──
        series_list = list(cfg.get("combo_series") or [])
        if not series_list and cols:
            f_c, n_c = _guess_fact_norm_cols()
            series_list = [
                {"name": f_c or "Серия 1", "source_type": "column", "col": f_c, "formula": "", "agg": "sum", "plot_type": "bar", "y_axis": "y1", "color": "#2b7fff", "line_dash": "solid", "line_width": 3, "marker_size": 8, "opacity": 0.9, "show_labels": True, "suffix": ""},
                {"name": n_c or "Серия 2", "source_type": "column", "col": n_c, "formula": "", "agg": "sum", "plot_type": "line", "y_axis": "y1", "color": "#87C800", "line_dash": "solid", "line_width": 3, "marker_size": 8, "opacity": 1.0, "show_labels": True, "suffix": ""},
            ]
            cfg["combo_series"] = series_list
            if self._block is not None:
                self._block.config = cfg

        self._section_header(f"5. Графики (серии) на оси ({len(series_list)} шт.)")

        _SERIES_PLOT_TYPES = [
            ("📊 Столбцы (Bar)", "bar"),
            ("📉 Линия с точками (Line)", "line"),
            ("🌊 Плавная кривая (Spline)", "spline"),
            ("⛰ Закрашенная область (Area)", "area"),
            ("📐 Ступенчатая линия (Step)", "step"),
            ("🔵 Только точки (Scatter)", "scatter"),
            ("📈 Нарастающий итог — Линия", "cum_line"),
            ("🧱 Нарастающий итог — Столбцы", "cum_bar"),
        ]

        _SERIES_LINE_DASHES = [
            ("━━ Сплошная линия", "solid"),
            ("╌╌ Штриховая (Dash)", "dash"),
            ("···· Точечный пунктир (Dot)", "dot"),
            ("−·− Штрих-пунктир", "dashdot"),
        ]

        _SERIES_AXES = [
            ("📏 На общей оси Y (Единая ось со всеми)", "y1"),
            ("📐 На правой оси Y2 (Вторая шкала справа)", "y2"),
        ]

        def _save_series_list(updated_list: list, rebuild_ui: bool = False):
            if self._block is None:
                return
            new_cfg = dict(self._block.config or {})
            new_cfg["combo_series"] = updated_list
            self._block.config = new_cfg
            self.config_changed.emit(self._block.id)
            if rebuild_ui:
                QTimer.singleShot(0, lambda b=self._block: self.show_block(b) if b else None)

        for idx_s, s_item in enumerate(series_list):
            if not isinstance(s_item, dict):
                continue

            card = QFrame()
            card.setStyleSheet(
                f"QFrame {{ background:{self.theme.bg_panel}; border:1px solid {self.theme.border}; "
                f"border-radius:7px; padding:6px; margin-bottom:4px; }}"
            )
            c_lay = QVBoxLayout(card)
            c_lay.setContentsMargins(6, 6, 6, 6)
            c_lay.setSpacing(4)

            # Шапка карточки серии: цветной индикатор + номер S1/S2 + кнопки Вверх/Вниз/Удалить
            hdr_row = QHBoxLayout()
            hdr_row.setSpacing(4)
            s_color = str(s_item.get("color") or "#2b7fff")
            lbl_badge = QLabel(f"● Серия S{idx_s + 1}")
            lbl_badge.setStyleSheet(f"color:{s_color}; font-size:11px; font-weight:700; border:none; background:transparent;")
            hdr_row.addWidget(lbl_badge, 1)

            btn_up = QPushButton("⬆")
            btn_up.setFixedWidth(24)
            btn_up.setEnabled(idx_s > 0)
            self._style_input(btn_up)

            btn_dn = QPushButton("⬇")
            btn_dn.setFixedWidth(24)
            btn_dn.setEnabled(idx_s < len(series_list) - 1)
            self._style_input(btn_dn)

            btn_del = QPushButton("✕")
            btn_del.setFixedWidth(24)
            btn_del.setToolTip("Удалить эту серию")
            self._style_input(btn_del)

            def _move_s(delta: int, cur_i: int = idx_s):
                lst = list(self._block.config.get("combo_series") or [])
                ni = cur_i + delta
                if 0 <= ni < len(lst):
                    lst[cur_i], lst[ni] = lst[ni], lst[cur_i]
                    _save_series_list(lst, rebuild_ui=True)

            def _del_s(cur_i: int = idx_s):
                lst = [x for j, x in enumerate(list(self._block.config.get("combo_series") or [])) if j != cur_i]
                _save_series_list(lst, rebuild_ui=True)

            btn_up.clicked.connect(lambda _, d=-1: _move_s(d))
            btn_dn.clicked.connect(lambda _, d=1: _move_s(d))
            btn_del.clicked.connect(_del_s)

            hdr_row.addWidget(btn_up)
            hdr_row.addWidget(btn_dn)
            hdr_row.addWidget(btn_del)
            c_lay.addWidget(self._wrap_row(hdr_row))

            # 1) Тип графика этой серии
            cb_ptype = QComboBox()
            for pt_lbl, pt_val in _SERIES_PLOT_TYPES:
                cb_ptype.addItem(pt_lbl, pt_val)
            cur_pt = str(s_item.get("plot_type", "bar") or "bar")
            cb_ptype.setCurrentIndex(max(0, cb_ptype.findData(cur_pt)))
            self._style_input(cb_ptype)

            def _on_pt_change(i_pt: int, cur_i: int = idx_s, box=cb_ptype):
                lst = list(self._block.config.get("combo_series") or [])
                if cur_i < len(lst):
                    lst[cur_i]["plot_type"] = box.itemData(i_pt)
                    _save_series_list(lst, rebuild_ui=False)

            cb_ptype.currentIndexChanged.connect(_on_pt_change)
            c_lay.addWidget(cb_ptype)

            # 2) Источник данных серии (Столбец таблицы или Формула)
            cb_src = QComboBox()
            cb_src.addItem("🧮 Математическая формула (S1, S2, A, B...)", "__FORMULA__")
            for col_n in cols:
                cb_src.addItem(f"📋 Столбец: {col_n}", str(col_n))

            is_form_mode = str(s_item.get("source_type", "column")) == "formula"
            cur_col_v = "__FORMULA__" if is_form_mode else str(s_item.get("col", "") or "")
            idx_src = cb_src.findData(cur_col_v)
            cb_src.setCurrentIndex(idx_src if idx_src >= 0 else (1 if cb_src.count() > 1 else 0))
            self._style_input(cb_src)
            c_lay.addWidget(cb_src)

            def _on_src_change(i_src: int, cur_i: int = idx_s, box=cb_src):
                val_s = box.itemData(i_src)
                lst = list(self._block.config.get("combo_series") or [])
                if cur_i < len(lst):
                    if val_s == "__FORMULA__":
                        lst[cur_i]["source_type"] = "formula"
                        if not lst[cur_i].get("formula"):
                            lst[cur_i]["formula"] = "S1 - S2"
                    else:
                        lst[cur_i]["source_type"] = "column"
                        lst[cur_i]["col"] = val_s
                        lst[cur_i]["name"] = val_s
                    _save_series_list(lst, rebuild_ui=True)

            cb_src.currentIndexChanged.connect(_on_src_change)

            # 3) Если выбран столбец — агрегация; если формула — конструктор формулы
            if is_form_mode:
                # ── РАСШИРЕННЫЙ РЕДАКТОР ФОРМУЛЫ ──
                ed_f = QLineEdit(str(s_item.get("formula", "S1 - S2") or "S1 - S2"))
                ed_f.setPlaceholderText("Напр.: S1 - S2   или   ((S1 - S2) / S2) * 100   или   if(S1 > S2; S1 - S2; 0)")
                ed_f.setStyleSheet(
                    f"background:{self.theme.bg_panel}; color:{self.theme.text_main}; "
                    f"border:1px solid {self.theme.primary}; border-radius:4px; "
                    f"padding:6px 8px; font-size:13px; "
                    f"font-family:'Consolas','Courier New',monospace;"
                )

                # Кнопки вставки ссылок на предыдущие серии S1..Sn
                vars_row = QHBoxLayout()
                vars_row.setSpacing(3)
                for v_idx in range(1, min(7, len(series_list) + 1)):
                    b_var = QPushButton(f"S{v_idx}")
                    b_var.setFixedWidth(34)
                    b_var.setToolTip(f"Вставить S{v_idx} (A/B/C = S1/S2/S3)")
                    b_var.setStyleSheet(
                        f"QPushButton {{ background:{self.theme.bg_panel}; color:{self.theme.primary}; "
                        f"border:1px solid {self.theme.primary}; border-radius:3px; "
                        f"padding:2px 3px; font-size:10px; font-weight:700; }}"
                        f"QPushButton:hover {{ background:{self.theme.primary}; color:{self.theme.text_inverse}; }}"
                    )
                    b_var.clicked.connect(lambda _, v=v_idx: ed_f.insert(f"S{v}"))
                    vars_row.addWidget(b_var)
                for f_lbl, f_tok in (("Факт", "ФАКТ"), ("Норма", "НОРМА")):
                    b_fact = QPushButton(f_lbl)
                    b_fact.setFixedWidth(44)
                    b_fact.setToolTip(f"Вставить [{f_tok}] (значение из настроек Иерархии)")
                    b_fact.setStyleSheet(
                        f"QPushButton {{ background:{self.theme.bg_panel}; color:{self.theme.primary}; "
                        f"border:1px solid {self.theme.primary}; border-radius:3px; "
                        f"padding:2px 3px; font-size:10px; font-weight:700; }}"
                    )
                    b_fact.clicked.connect(lambda _, v=f_tok: ed_f.insert(f"[{v}]"))
                    vars_row.addWidget(b_fact)
                
                lbl_alias = QLabel("A/B/C = S1/S2/S3")
                lbl_alias.setStyleSheet(f"color:{self.theme.text_muted}; font-size:9px; background:transparent;")
                vars_row.addWidget(lbl_alias, 1)
                c_lay.addWidget(self._wrap_row(vars_row))

                # Кнопки вставки математических функций
                funcs_row = QHBoxLayout()
                funcs_row.setSpacing(3)
                for f_lbl, f_tok, f_tip in (
                    ("|x|", "abs()", "Модуль"),
                    ("√", "sqrt()", "Корень"),
                    ("⌒", "round(,2)", "Округление"),
                    ("if", "if(; ; )", "Условие: if(условие; да; нет)"),
                    ("min", "min(,)", "Минимум"),
                    ("max", "max(,)", "Максимум"),
                    ("xⁿ", "pow(,)", "Степень"),
                    ("×100", "* 100", "Умножить на 100 (для %)"),
                ):
                    b_f = QPushButton(f_lbl)
                    b_f.setToolTip(f_tip)
                    b_f.setStyleSheet(
                        f"QPushButton {{ background:{self.theme.bg_panel}; color:{self.theme.text_main}; "
                        f"border:1px solid {self.theme.border}; border-radius:3px; "
                        f"padding:2px 6px; font-size:10px; }}"
                        f"QPushButton:hover {{ border-color:{self.theme.primary}; color:{self.theme.primary}; }}"
                    )
                    b_f.clicked.connect(lambda _, t=f_tok: ed_f.insert(t))
                    funcs_row.addWidget(b_f)
                c_lay.addWidget(self._wrap_row(funcs_row))

                # Шаблоны формул
                cb_f_preset = QComboBox()
                cb_f_preset.addItem("⚡ Вставить готовый шаблон…", "")
                cb_f_preset.addItem("Разность: S1 − S2 (Факт − Норма)", "S1 - S2")
                cb_f_preset.addItem("Экономия: S2 − S1", "S2 - S1")
                cb_f_preset.addItem("Сумма: S1 + S2", "S1 + S2")
                cb_f_preset.addItem("Отношение: S1 / S2", "S1 / S2")
                cb_f_preset.addItem("% отклонения: ((S1 − S2) / S2) × 100", "((S1 - S2) / S2) * 100")
                cb_f_preset.addItem("% выполнения: (S1 / S2) × 100", "(S1 / S2) * 100")
                cb_f_preset.addItem("Условное отклонение: if(S1 > S2; S1 − S2; 0)", "if(S1 > S2; S1 - S2; 0)")
                cb_f_preset.addItem("Условный %: if(S1 > S2; ((S1−S2)/S2)*100; 0)", "if(S1 > S2; ((S1 - S2) / S2) * 100; 0)")
                cb_f_preset.addItem("|S1 − S2| (модуль разности)", "abs(S1 - S2)")
                self._style_input(cb_f_preset)
                cb_f_preset.currentIndexChanged.connect(
                    lambda i, box=cb_f_preset: ed_f.setText(box.itemData(i)) if box.itemData(i) else None
                )

                def _on_f_edit(txt_f: str, cur_i: int = idx_s):
                    lst = list(self._block.config.get("combo_series") or [])
                    if cur_i < len(lst):
                        lst[cur_i]["formula"] = txt_f
                        _save_series_list(lst, rebuild_ui=False)

                ed_f.textChanged.connect(_on_f_edit)
                c_lay.addWidget(ed_f)
                c_lay.addWidget(cb_f_preset)
            else:
                cb_sagg = QComboBox()
                for agg_lbl, agg_v in _AGG_FUNCS:
                    cb_sagg.addItem(agg_lbl, agg_v)
                cur_sa = str(s_item.get("agg", "sum") or "sum")
                cb_sagg.setCurrentIndex(max(0, cb_sagg.findData(cur_sa)))
                self._style_input(cb_sagg)

                def _on_sagg_change(i_a: int, cur_i: int = idx_s, box=cb_sagg):
                    lst = list(self._block.config.get("combo_series") or [])
                    if cur_i < len(lst):
                        lst[cur_i]["agg"] = box.itemData(i_a)
                        _save_series_list(lst, rebuild_ui=False)

                cb_sagg.currentIndexChanged.connect(_on_sagg_change)
                c_lay.addWidget(cb_sagg)

            # 4) Имя в легенде + Суффикс единиц + Кнопка выбора цвета
            row_name_color = QHBoxLayout()
            row_name_color.setSpacing(4)

            ed_sname = QLineEdit(str(s_item.get("name") or s_item.get("col") or f"Серия {idx_s + 1}"))
            ed_sname.setPlaceholderText("Название в легенде...")
            self._style_input(ed_sname)

            ed_suf = QLineEdit(str(s_item.get("suffix", "") or ""))
            ed_suf.setPlaceholderText("Ед. (%, л)")
            ed_suf.setFixedWidth(58)
            ed_suf.setToolTip("Суффикс значений (например: % или л)")
            self._style_input(ed_suf)

            btn_scolor = QPushButton("🎨")
            btn_scolor.setFixedWidth(30)
            btn_scolor.setToolTip("Выбрать цвет этой серии")
            btn_scolor.setStyleSheet(
                f"QPushButton {{ background:{s_color}; color:#fff; border:1px solid {self.theme.border}; border-radius:4px; padding:3px; }}"
            )

            def _on_sname_edit(txt_n: str, cur_i: int = idx_s):
                lst = list(self._block.config.get("combo_series") or [])
                if cur_i < len(lst):
                    lst[cur_i]["name"] = txt_n
                    _save_series_list(lst, rebuild_ui=False)

            def _on_suf_edit(txt_sf: str, cur_i: int = idx_s):
                lst = list(self._block.config.get("combo_series") or [])
                if cur_i < len(lst):
                    lst[cur_i]["suffix"] = txt_sf
                    _save_series_list(lst, rebuild_ui=False)

            def _pick_scolor(cur_i: int = idx_s):
                c_dlg = QColorDialog.getColor(parent=self, title="Цвет серии")
                if c_dlg.isValid():
                    lst = list(self._block.config.get("combo_series") or [])
                    if cur_i < len(lst):
                        lst[cur_i]["color"] = c_dlg.name()
                        _save_series_list(lst, rebuild_ui=True)

            ed_sname.textChanged.connect(_on_sname_edit)
            ed_suf.textChanged.connect(_on_suf_edit)
            btn_scolor.clicked.connect(_pick_scolor)

            row_name_color.addWidget(ed_sname, 1)
            row_name_color.addWidget(ed_suf)
            row_name_color.addWidget(btn_scolor)
            c_lay.addWidget(self._wrap_row(row_name_color))

            # 5) Выбор оси (Единая ось Y или Правая ось Y2) + Стиль линии
            row_ax_dash = QHBoxLayout()
            row_ax_dash.setSpacing(4)

            cb_ax = QComboBox()
            for ax_lbl, ax_v in _SERIES_AXES:
                cb_ax.addItem(ax_lbl, ax_v)
            cb_ax.setCurrentIndex(max(0, cb_ax.findData(str(s_item.get("y_axis", "y1") or "y1"))))
            self._style_input(cb_ax)

            cb_dash = QComboBox()
            for d_lbl, d_v in _SERIES_LINE_DASHES:
                cb_dash.addItem(d_lbl, d_v)
            cb_dash.setCurrentIndex(max(0, cb_dash.findData(str(s_item.get("line_dash", "solid") or "solid"))))
            self._style_input(cb_dash)

            def _on_ax_change(i_ax: int, cur_i: int = idx_s, box=cb_ax):
                lst = list(self._block.config.get("combo_series") or [])
                if cur_i < len(lst):
                    lst[cur_i]["y_axis"] = box.itemData(i_ax)
                    _save_series_list(lst, rebuild_ui=False)

            def _on_dash_change(i_d: int, cur_i: int = idx_s, box=cb_dash):
                lst = list(self._block.config.get("combo_series") or [])
                if cur_i < len(lst):
                    lst[cur_i]["line_dash"] = box.itemData(i_d)
                    _save_series_list(lst, rebuild_ui=False)

            cb_ax.currentIndexChanged.connect(_on_ax_change)
            cb_dash.currentIndexChanged.connect(_on_dash_change)

            row_ax_dash.addWidget(cb_ax, 1)
            row_ax_dash.addWidget(cb_dash, 1)
            c_lay.addWidget(self._wrap_row(row_ax_dash))

            # 6) Подписи значений на этой серии + толщина линии / размер точек
            row_opts = QHBoxLayout()
            row_opts.setSpacing(6)

            chk_svis = QCheckBox("👁 Показывать")
            chk_svis.setChecked(bool(s_item.get("visible", True)))
            chk_svis.setStyleSheet(f"QCheckBox {{ color:{self.theme.text_main}; font-size:10.5px; border:none; background:transparent; }}")
            
            def _on_svis_toggle(v_b: bool, cur_i: int = idx_s):
                lst = list(self._block.config.get("combo_series") or [])
                if cur_i < len(lst):
                    lst[cur_i]["visible"] = bool(v_b)
                    _save_series_list(lst, rebuild_ui=False)
            
            chk_svis.toggled.connect(_on_svis_toggle)

            chk_slbl = QCheckBox("Подписи чисел")
            chk_slbl.setChecked(bool(s_item.get("show_labels", True)))
            chk_slbl.setStyleSheet(f"QCheckBox {{ color:{self.theme.text_main}; font-size:10.5px; border:none; background:transparent; }}")

            sp_lw = QSpinBox()
            sp_lw.setRange(1, 10)
            sp_lw.setPrefix("Толщ: ")
            sp_lw.setValue(int(s_item.get("line_width", 3) or 3))
            self._style_input(sp_lw)

            sp_ms = QSpinBox()
            sp_ms.setRange(0, 20)
            sp_ms.setPrefix("Точки: ")
            sp_ms.setValue(int(s_item.get("marker_size", 8) if "marker_size" in s_item else 8))
            self._style_input(sp_ms)

            def _on_slbl_toggle(v_b: bool, cur_i: int = idx_s):
                lst = list(self._block.config.get("combo_series") or [])
                if cur_i < len(lst):
                    lst[cur_i]["show_labels"] = bool(v_b)
                    _save_series_list(lst, rebuild_ui=False)

            def _on_lw_change(v_w: int, cur_i: int = idx_s):
                lst = list(self._block.config.get("combo_series") or [])
                if cur_i < len(lst):
                    lst[cur_i]["line_width"] = int(v_w)
                    _save_series_list(lst, rebuild_ui=False)

            def _on_ms_change(v_m: int, cur_i: int = idx_s):
                lst = list(self._block.config.get("combo_series") or [])
                if cur_i < len(lst):
                    lst[cur_i]["marker_size"] = int(v_m)
                    _save_series_list(lst, rebuild_ui=False)

            chk_svis = QCheckBox("👁 Показывать")
            chk_svis.setChecked(bool(s_item.get("visible", True)))
            chk_svis.setStyleSheet(f"QCheckBox {{ color:{self.theme.text_main}; font-size:10.5px; border:none; background:transparent; }}")
            
            def _on_svis_toggle(v_b: bool, cur_i: int = idx_s):
                lst = list(self._block.config.get("combo_series") or [])
                if cur_i < len(lst):
                    lst[cur_i]["visible"] = bool(v_b)
                    _save_series_list(lst, rebuild_ui=False)
            
            chk_svis.toggled.connect(_on_svis_toggle)

            # Добавляем новую галочку "Показывать" перед чекбоксом подписей
            row_opts.addWidget(chk_svis) 
            
            chk_slbl.toggled.connect(_on_slbl_toggle)
            sp_lw.valueChanged.connect(_on_lw_change)
            sp_ms.valueChanged.connect(_on_ms_change)

            row_opts.addWidget(chk_slbl)
            row_opts.addWidget(sp_lw)
            row_opts.addWidget(sp_ms)
            c_lay.addWidget(self._wrap_row(row_opts))

            self._lay.insertWidget(self._lay.count() - 1, card)

        # Кнопки добавления новой серии (Столбец таблицы или Формула)
        add_btns_row = QHBoxLayout()
        add_btns_row.setSpacing(4)

        btn_add_col_s = QPushButton("➕ Добавить график (Столбец)")
        btn_add_col_s.setCursor(Qt.PointingHandCursor)
        btn_add_col_s.setStyleSheet(
            f"QPushButton {{ background:{self.theme.primary}; color:{self.theme.text_inverse}; "
            f"border:none; border-radius:5px; padding:6px 8px; font-size:10.5px; font-weight:700; }}"
        )

        btn_add_form_s = QPushButton("🧮 Добавить формулу")
        btn_add_form_s.setCursor(Qt.PointingHandCursor)
        btn_add_form_s.setStyleSheet(
            f"QPushButton {{ background:{self.theme.bg_panel}; color:{self.theme.primary}; "
            f"border:1px solid {self.theme.primary}; border-radius:5px; padding:6px 8px; font-size:10.5px; font-weight:700; }}"
        )

        palette_default = ["#2b7fff", "#87C800", "#ff9f1c", "#e71d36", "#6f42c1", "#20c997"]

        def _add_new_series(is_formula: bool = False):
            lst = list(self._block.config.get("combo_series") or [])
            idx_new = len(lst)
            def_c = cols[min(idx_new, len(cols) - 1)] if cols else ""
            c_hex = palette_default[idx_new % len(palette_default)]
            if is_formula:
                lst.append({
                    "name": f"Формула S{idx_new + 1}",
                    "source_type": "formula",
                    "col": "",
                    "formula": "S1 - S2",
                    "agg": "sum",
                    "plot_type": "spline",
                    "y_axis": "y1",
                    "color": c_hex,
                    "line_dash": "solid",
                    "line_width": 3,
                    "marker_size": 8,
                    "opacity": 1.0,
                    "show_labels": True,
                    "suffix": "",
                })
            else:
                lst.append({
                    "name": def_c or f"Серия {idx_new + 1}",
                    "source_type": "column",
                    "col": def_c,
                    "formula": "",
                    "agg": "sum",
                    "plot_type": "line" if idx_new > 0 else "bar",
                    "y_axis": "y1",
                    "color": c_hex,
                    "line_dash": "solid",
                    "line_width": 3,
                    "marker_size": 8,
                    "opacity": 0.9 if idx_new == 0 else 1.0,
                    "show_labels": True,
                    "suffix": "",
                })
            _save_series_list(lst, rebuild_ui=True)

        btn_add_col_s.clicked.connect(lambda: _add_new_series(False))
        btn_add_form_s.clicked.connect(lambda: _add_new_series(True))
        add_btns_row.addWidget(btn_add_col_s, 1)
        add_btns_row.addWidget(btn_add_form_s, 1)
        self._lay.insertWidget(self._lay.count() - 1, self._wrap_row(add_btns_row))

        # ── Общие настройки комбинированных осей и целевой линии ──
        self._section_header("6. Режим столбцов, сортировка и целевая линия")
        _CMB_BARMODES = [
            ("📊 Рядом друг с другом (Group)", "group"),
            ("🧱 В стопку друг на друге (Stack)", "stack"),
            ("🔀 С наложением (Overlay)", "overlay"),
        ]
        self._field_combo("Как располагать несколько столбчатых серий:", "combo_barmode", cfg, _CMB_BARMODES, "group")

        self._add_label("По какому графику (серии) сортировать столбцы и отбирать Топ N:")
        cb_sort_s = QComboBox()
        for idx_sn, s_obj in enumerate(series_list):
            s_lbl = str(s_obj.get("name") or s_obj.get("col") or f"Серия S{idx_sn + 1}")
            cb_sort_s.addItem(f"По Серии S{idx_sn + 1}: {s_lbl}", idx_sn)
        cb_sort_s.setCurrentIndex(max(0, cb_sort_s.findData(int(cfg.get("combo_sort_series_idx", 0) or 0))))
        self._style_input(cb_sort_s)
        cb_sort_s.currentIndexChanged.connect(lambda i: self._change_block("combo_sort_series_idx", cb_sort_s.itemData(i)))
        self._lay.insertWidget(self._lay.count() - 1, cb_sort_s)
        self._field_text("Подпись правой оси Y2 (если используется Y2):", "combo_y2_title", cfg, placeholder="Например: Отклонение, %")
        self._field_checkbox("Выделять нулевую линию (Y = 0)", "combo_show_zero_line", cfg, True)
        self._field_text("Горизонтальная целевая линия (число, пусто = скрыть):", "combo_target_val", cfg, placeholder="Например: 0  или  1000")
        self._field_text("Подпись целевой линии:", "combo_target_label", cfg, placeholder="Например: Лимит расхода")
        # ── Настройки подсветки превышения над нормой ──
        self._section_header("7. Подсветка превышения над нормой (Цветом)")
        self._field_checkbox(
            "🚨 Другим цветом окрашивать столбцы при превышении норматива",
            "combo_highlight_overrun",
            cfg,
            False,
        )

        row_hl = QHBoxLayout()
        row_hl.setSpacing(6)
        series_names_list = [str(s.get("name") or s.get("col") or f"Серия {i+1}") for i, s in enumerate(series_list)]

        cb_fact_s = QComboBox()
        cb_fact_s.addItem("Факт серия", 0)
        for idx_sn, s_name_lbl in enumerate(series_names_list):
            cb_fact_s.addItem(f"Факт: {s_name_lbl}", idx_sn)
        cb_fact_s.setCurrentIndex(max(0, cb_fact_s.findData(int(cfg.get("combo_hl_fact_idx", 0) or 0))))
        self._style_input(cb_fact_s)
        cb_fact_s.currentIndexChanged.connect(lambda i: self._change_block("combo_hl_fact_idx", cb_fact_s.itemData(i)))

        cb_norm_s = QComboBox()
        cb_norm_s.addItem("Норма серия", 1)
        for idx_sn, s_name_lbl in enumerate(series_names_list):
            cb_norm_s.addItem(f"Норма: {s_name_lbl}", idx_sn)
        cb_norm_s.setCurrentIndex(max(0, cb_norm_s.findData(int(cfg.get("combo_hl_norm_idx", min(1, len(series_list)-1)) or 1))))
        self._style_input(cb_norm_s)
        cb_norm_s.currentIndexChanged.connect(lambda i: self._change_block("combo_hl_norm_idx", cb_norm_s.itemData(i)))

        row_hl.addWidget(cb_fact_s, 1)
        row_hl.addWidget(cb_norm_s, 1)
        self._lay.insertWidget(self._lay.count() - 1, self._wrap_row(row_hl))

        self._add_label("Сигнальный цвет при превышении (если факт > нормы):")
        row_oc = QHBoxLayout()
        row_oc.setSpacing(6)
        cur_oc = str(cfg.get("combo_over_color", "#e11d48") or "#e11d48")
        ed_oc = QLineEdit(cur_oc)
        self._style_input(ed_oc)
        ed_oc.textChanged.connect(lambda v: self._change_block("combo_over_color", v))
        row_oc.addWidget(ed_oc, 1)
        self._lay.insertWidget(self._lay.count() - 1, self._wrap_row(row_oc))

    def _field_row_mode_selectors(self, cfg: dict, cols: list[str]):
        if not cols:
            self._add_hint("Сначала загрузите таблицу для выбора столбцов.")
            return

        # 1. Столбец названия строк (категорий)
        self._add_label("Столбец с названием строк / категорий")
        cb_x = QComboBox()
        for col in cols:
            cb_x.addItem(str(col), str(col))
        cur_x = cfg.get("x_col", "") or (cols[0] if cols else "")
        idx_x = cb_x.findData(cur_x)
        cb_x.setCurrentIndex(idx_x if idx_x >= 0 else 0)
        self._style_input(cb_x)

        def on_row_label_col_changed(i):
            self._change_block("x_col", cb_x.itemData(i))
            if self._block:
                self.show_block(self._block)

        cb_x.currentIndexChanged.connect(on_row_label_col_changed)
        self._lay.insertWidget(self._lay.count() - 1, cb_x)

        # 2. Какую строку / агрегацию показывать
        self._add_label("Какие строки отображать на графике")
        cb_row_target = QComboBox()
        cb_row_target.addItem("📊 Итог по строкам + переключение Срезом", "__ALL_SERIES__")
        cb_row_target.addItem("Σ Сумма по всем строкам (управляется Срезом)", "__SUM__")
        cb_row_target.addItem("⌀ Среднее по всем строкам (управляется Срезом)", "__MEAN__")

        target_df = self._get_target_dataframe(cfg)
        if target_df is not None and cur_x in target_df.columns:
            unique_rows = target_df[cur_x].dropna().astype(str).unique()[:100]
            for r_val in unique_rows:
                r_str = r_val.strip()
                if r_str:
                    cb_row_target.addItem(f"📌 Только категория: {r_str}", r_str)

        cur_target_val = cfg.get("row_target_val", "__ALL_SERIES__")
        idx_rt = cb_row_target.findData(cur_target_val)
        cb_row_target.setCurrentIndex(idx_rt if idx_rt >= 0 else 0)
        self._style_input(cb_row_target)
        cb_row_target.currentIndexChanged.connect(
            lambda i: self._change_block("row_target_val", cb_row_target.itemData(i))
        )
        self._lay.insertWidget(self._lay.count() - 1, cb_row_target)

        # 3. Очистка префиксов столбцов
        self._field_checkbox(
            "✂ Оставлять на оси X только префикс / период (до знака '_')",
            "clean_col_labels", cfg, True
        )

        # Настройки мульти-столбцов для режима строк
        self._section_header("Режим мульти-столбцов (для строк)")
        
        self._add_label("Как отображать выбранные столбцы:")
        cb_row_multi_mode = QComboBox()
        cb_row_multi_mode.addItem("📊 Раздельные серии (каждый показатель отдельно)", "separate")
        cb_row_multi_mode.addItem("🧮 Объединить столбцы внутри периода через функцию", "combined")

        cur_rmm = cfg.get("row_multi_mode", "separate")
        idx_rmm = cb_row_multi_mode.findData(cur_rmm)
        cb_row_multi_mode.setCurrentIndex(idx_rmm if idx_rmm >= 0 else 0)
        self._style_input(cb_row_multi_mode)
        cb_row_multi_mode.currentIndexChanged.connect(lambda i: self._change_block("row_multi_mode", cb_row_multi_mode.itemData(i)))
        self._lay.insertWidget(self._lay.count() - 1, cb_row_multi_mode)

        self._add_label("Функция объединения:")
        cb_row_func = QComboBox()
        cb_row_func.addItem("Сумма (Sum)", "sum")
        cb_row_func.addItem("Разность (Sub)", "sub")
        cb_row_func.addItem("Произведение (Mul)", "mul")
        cb_row_func.addItem("Частное / Деление (Div)", "div")
        cb_row_func.addItem("Среднее значение (Mean)", "mean")

        cur_rf = cfg.get("row_multi_func", "sum")
        idx_rf = cb_row_func.findData(cur_rf)
        cb_row_func.setCurrentIndex(idx_rf if idx_rf >= 0 else 0)
        self._style_input(cb_row_func)
        cb_row_func.currentIndexChanged.connect(lambda i: self._change_block("row_multi_func", cb_row_func.itemData(i)))
        self._lay.insertWidget(self._lay.count() - 1, cb_row_func)

        self._add_label("Для круговых диаграмм (Pie / Donut) в режиме строк:")
        cb_pie_mode = QComboBox()
        cb_pie_mode.addItem("📊 Доли = Категории (% по периодам + выбор периода)", "models_with_months")
        cb_pie_mode.addItem("📅 Отдельный круг на каждый период (Сетка)", "subplots_by_month")
        cb_pie_mode.addItem("📆 Доли = Периоды (% каждого периода)", "slices_are_months")
        cur_pm = cfg.get("pie_row_mode", "models_with_months")
        idx_pm = cb_pie_mode.findData(cur_pm)
        cb_pie_mode.setCurrentIndex(idx_pm if idx_pm >= 0 else 0)
        self._style_input(cb_pie_mode)
        cb_pie_mode.currentIndexChanged.connect(lambda i: self._change_block("pie_row_mode", cb_pie_mode.itemData(i)))
        self._lay.insertWidget(self._lay.count() - 1, cb_pie_mode)

        # 4. Умный выбор определенных столбцов строки
        self._add_label("Выберите определенные столбцы строки для графика:")

        selected_cols = cfg.get("row_columns")
        if not isinstance(selected_cols, list):
            selected_cols = []
        selected_set = set(selected_cols)

        # Собираем уникальные показатели после '_'
        suffixes = []
        for c in cols:
            if c == cur_x:
                continue
            if "_" in c:
                suf = c.split("_", 1)[1].strip()
                if suf and suf not in suffixes:
                    suffixes.append(suf)

        if suffixes:
            cb_metric = QComboBox()
            cb_metric.addItem("⚡ Быстрый выбор показателя по всем месяцам…", "")
            for suf in suffixes:
                cb_metric.addItem(f"☑ Выбрать все столбцы «{suf}»", suf)
            self._style_input(cb_metric)
            self._lay.insertWidget(self._lay.count() - 1, cb_metric)

        # Поиск по названию столбца + кнопки
        search_row = QHBoxLayout()
        search_row.setSpacing(4)
        inp_search = QLineEdit()
        inp_search.setPlaceholderText("🔍 Фильтр столбцов (напр. Пробег или Январь)...")
        self._style_input(inp_search)
        search_row.addWidget(inp_search, 1)

        btn_sel_vis = QPushButton("☑ Все")
        btn_sel_vis.setFixedWidth(48)
        self._style_input(btn_sel_vis)
        search_row.addWidget(btn_sel_vis)

        btn_clr_vis = QPushButton("☐ Сброс")
        btn_clr_vis.setFixedWidth(56)
        self._style_input(btn_clr_vis)
        search_row.addWidget(btn_clr_vis)

        self._lay.insertWidget(self._lay.count() - 1, self._wrap_row(search_row))

        # Прокручиваемый список галочек
        scroll_cols = QScrollArea()
        scroll_cols.setWidgetResizable(True)
        scroll_cols.setFixedHeight(170)
        scroll_cols.setStyleSheet(f"QScrollArea {{ background:{self.theme.bg_panel}; border:1px solid {self.theme.border}; border-radius:4px; }}")
        cols_host = QWidget()
        cols_host.setStyleSheet("background:transparent;")
        cols_lay = QVBoxLayout(cols_host)
        cols_lay.setContentsMargins(6, 6, 6, 6)
        cols_lay.setSpacing(2)

        checkboxes: list[tuple[str, QCheckBox]] = []

        def sync_selected_from_ui():
            ordered = [col_name for col_name, cb in checkboxes if cb.isChecked()]
            self._change_block("row_columns", ordered)

        for col in cols:
            if col == cur_x:
                continue
            cb_item = QCheckBox(str(col))
            cb_item.setChecked(col in selected_set)
            cb_item.setStyleSheet(f"QCheckBox {{ color:{self.theme.text_main}; font-size:11px; padding:2px; background:transparent; }}")
            cb_item.toggled.connect(lambda _v: sync_selected_from_ui())
            cols_lay.addWidget(cb_item)
            checkboxes.append((str(col), cb_item))

        cols_lay.addStretch()
        scroll_cols.setWidget(cols_host)
        self._lay.insertWidget(self._lay.count() - 1, scroll_cols)

        def on_search_text(txt: str):
            q = txt.strip().lower()
            for col_name, cb_item in checkboxes:
                cb_item.setVisible(not q or (q in col_name.lower()))

        def on_select_visible():
            for _col_name, cb_item in checkboxes:
                if not cb_item.isHidden():
                    cb_item.blockSignals(True)
                    cb_item.setChecked(True)
                    cb_item.blockSignals(False)
            sync_selected_from_ui()

        def on_clear_all():
            for _col_name, cb_item in checkboxes:
                cb_item.blockSignals(True)
                cb_item.setChecked(False)
                cb_item.blockSignals(False)
            sync_selected_from_ui()

        inp_search.textChanged.connect(on_search_text)
        btn_sel_vis.clicked.connect(on_select_visible)
        btn_clr_vis.clicked.connect(on_clear_all)

        if suffixes:
            def on_quick_metric(i):
                suf = cb_metric.itemData(i)
                if not suf: return
                for col_name, cb_item in checkboxes:
                    if col_name.endswith(f"_{suf}") or col_name == suf:
                        cb_item.blockSignals(True)
                        cb_item.setChecked(True)
                        cb_item.blockSignals(False)
                cb_metric.blockSignals(True)
                cb_metric.setCurrentIndex(0)
                cb_metric.blockSignals(False)
                sync_selected_from_ui()
            cb_metric.currentIndexChanged.connect(on_quick_metric)
    def _build_paragraph_dynamic_settings(self, cfg: dict):
        """Панель настройки динамического текста с логическими выражениями и синхронизацией со срезами."""
        self._section_header("1. Источник данных и связь с графиком")
        self._build_source_selectors(cfg)
        cols = self._get_target_columns(cfg)

        self._add_label("Синхронизировать колонки с графиком:")
        cb_chart = QComboBox()
        cb_chart.addItem("— Настроить колонки вручную ниже —", "")
        if hasattr(self, "report_ref") and self.report_ref:
            def _collect_charts(blocks_list):
                res = []
                for b in (blocks_list or []):
                    b_type = b.get("type") if isinstance(b, dict) else getattr(b, "type", "")
                    if b_type == "plotly_chart":
                        res.append(b)
                    elif b_type == "container":
                        b_cfg = b.get("config", {}) if isinstance(b, dict) else (getattr(b, "config", {}) or {})
                        res.extend(_collect_charts(b_cfg.get("children", [])))
                return res

            for sec in self.report_ref.sections:
                for ch in _collect_charts(sec.blocks):
                    c_id = ch.get("id", "") if isinstance(ch, dict) else getattr(ch, "id", "")
                    c_cfg = ch.get("config", {}) if isinstance(ch, dict) else (getattr(ch, "config", {}) or {})
                    c_title = c_cfg.get("title", "График")
                    cb_chart.addItem(f"📊 {c_title} (ID: {str(c_id)[:4]})", c_id)

        cur_tc = cfg.get("target_chart", "")
        idx_tc = cb_chart.findData(cur_tc)
        cb_chart.setCurrentIndex(idx_tc if idx_tc >= 0 else 0)
        self._style_input(cb_chart)
        cb_chart.currentIndexChanged.connect(lambda i: self._change_block("target_chart", cb_chart.itemData(i)))
        self._lay.insertWidget(self._lay.count() - 1, cb_chart)

        for lbl_text, key_name in (
            ("Колонка группы (Тип ТС — для среза):", "parent_group_col"),
            ("Колонка детализации (Марка / Модель):", "model_col"),
            ("Колонка даты / месяца:", "date_col"),
            ("Переменная A (Факт):", "fact_col"),
            ("Переменная B (Норматив):", "norm_col"),
        ):
            self._add_label(lbl_text)
            cb = QComboBox()
            cb.addItem("— Авто (из привязанного графика) —", "")
            for col in cols:
                cb.addItem(str(col), str(col))
            idx_c = cb.findData(cfg.get(key_name, ""))
            cb.setCurrentIndex(idx_c if idx_c >= 0 else 0)
            self._style_input(cb)
            cb.currentIndexChanged.connect(lambda i, k=key_name, combo=cb: self._change_block(k, combo.itemData(i)))
            self._lay.insertWidget(self._lay.count() - 1, cb)

        self._section_header("2. Шаблон динамического вывода и логика ЕСЛИ")
        txt_edit = QTextEdit()
        txt_edit.setPlainText(str(cfg.get("text", "")))
        txt_edit.setFixedHeight(130)
        txt_edit.setPlaceholderText(
            "Пример:\n"
            "Категория: {{ group }} | Период: {{ month }}\n"
            "Факт: {{ fact }} | Норматив: {{ norm }}\n"
            "Вывод: {{ if(pct > 0; 'Перерасход ' + abs_pct + '% (' + abs_diff + ')'; 'Экономия ' + abs_pct + '% (' + abs_diff + ')') }}"
        )
        self._style_input(txt_edit)

        def on_txt_changed():
            if self._block is None:
                return
            new_cfg = dict(self._block.config or {})
            new_cfg["text"] = txt_edit.toPlainText()
            new_cfg["raw_html"] = False
            self._block.config = new_cfg
            self.config_changed.emit(self._block.id)

        txt_edit.textChanged.connect(on_txt_changed)
        self._lay.insertWidget(self._lay.count() - 1, txt_edit)

        # Кнопки быстрой вставки переменных
        var_row1 = QHBoxLayout()
        var_row1.setSpacing(3)
        for b_lbl, b_tok in (
            ("Тип ТС", "{{ group }}"),
            ("Месяц", "{{ month }}"),
            ("Факт (A)", "{{ fact }}"),
            ("Норма (B)", "{{ norm }}"),
            ("Разница", "{{ diff }}"),
            ("Процент %", "{{ pct }}%"),
        ):
            btn_v = QPushButton(b_lbl)
            btn_v.setCursor(Qt.PointingHandCursor)
            btn_v.setStyleSheet(
                f"QPushButton {{ background:{self.theme.bg_panel}; color:{self.theme.text_main}; "
                f"border:1px solid {self.theme.border}; border-radius:3px; padding:2px 4px; font-size:9px; }}"
                f"QPushButton:hover {{ border-color:{self.theme.primary}; }}"
            )
            btn_v.clicked.connect(lambda _, tk=b_tok: txt_edit.insertPlainText(tk))
            var_row1.addWidget(btn_v)
        self._lay.insertWidget(self._lay.count() - 1, self._wrap_row(var_row1))

        btn_tpl = QPushButton("⚡ Вставить готовый шаблон умного вывода (с условием ЕСЛИ)")
        btn_tpl.setCursor(Qt.PointingHandCursor)
        btn_tpl.setStyleSheet(
            f"QPushButton {{ background:{self.theme.bg_panel}; color:{self.theme.primary}; "
            f"border:1px solid {self.theme.primary}; border-radius:4px; padding:5px; font-size:10px; font-weight:700; }}"
        )
        smart_tpl = (
            "📊 Аналитический вывод ({group} — {month}):\n"
            "• Суммарный Факт: {{ fact }} | Норматив: {{ norm }} (записей: {{ count }})\n"
            "• Результат: {{ if(pct > 0; '⚠ Зафиксирован ПЕРЕРАСХОД на ' + abs_pct + '% (+' + abs_diff + ')'; "
            "if(pct < 0; '✅ Достигнута ЭКОНОМИЯ на ' + abs_pct + '% (-' + abs_diff + ')'; 'В пределах нормы (0%)')) }}\n"
            "• Наибольший вклад: {{ top_name }} (отклонение {{ top_pct }}%)"
        ).replace("{group}", "{{ group }}").replace("{month}", "{{ month }}")
        btn_tpl.clicked.connect(lambda: txt_edit.setPlainText(smart_tpl))
        self._lay.insertWidget(self._lay.count() - 1, btn_tpl)

        self._add_hint(
            "💡 Доступные переменные:\n"
            "• {{ group }} — выбранный Тип ТС, {{ month }} — выбранный месяц\n"
            "• {{ fact }} (или A), {{ norm }} (или B), {{ diff }} (Факт−Норма), {{ abs_diff }}\n"
            "• {{ pct }} (% отклонения), {{ abs_pct }}, {{ count }} (кол-во строк)\n"
            "• {{ top_name }} — лидер по отклонению, {{ top_pct }} — его %\n"
            "• Логика: {{ if(pct > 0; 'Перерасход ' + abs_pct + '%'; 'Экономия ' + abs_pct + '%') }}"
        )

    def _field_chart_filter_rules(self, cfg: dict, cols: list[str]):
        """Универсальный конструктор иерархии (Drill-Down), формулы процента и фильтрации."""
        supports_hierarchy = cfg.get("chart_type", "bar") in (
            "pie", "donut", "line", "bar", "bar_stacked", "bar_cumulative", "bar_stacked_100", "hbar", "area"
        )

        if supports_hierarchy:
            self._section_header("Иерархия (Тип ТС × Месяц) и расчёт Факт / Норматив")

            self._add_label("1) Синхронизация с другим графиком (фильтр по категориям):")
            cb_link = QComboBox()
            cb_link.addItem("— Не привязывать (брать все категории таблицы) —", "")

            if hasattr(self, "report_ref") and self.report_ref:
                def _collect_charts(blocks_list):
                    res = []
                    for b in (blocks_list or []):
                        b_type = b.get("type") if isinstance(b, dict) else getattr(b, "type", "")
                        if b_type == "plotly_chart":
                            res.append(b)
                        elif b_type == "container":
                            b_cfg = b.get("config", {}) if isinstance(b, dict) else (getattr(b, "config", {}) or {})
                            res.extend(_collect_charts(b_cfg.get("children", [])))
                    return res

                own_id = getattr(self._block, "id", "") if self._block else ""
                for section in self.report_ref.sections:
                    for ch in _collect_charts(section.blocks):
                        c_id = ch.get("id", "") if isinstance(ch, dict) else getattr(ch, "id", "")
                        if c_id and c_id != own_id:
                            c_cfg = ch.get("config", {}) if isinstance(ch, dict) else (getattr(ch, "config", {}) or {})
                            c_title = c_cfg.get("title", "График")
                            cb_link.addItem(f"📊 {c_title} (ID: {str(c_id)[:4]})", c_id)

            cur_link = cfg.get("filter_from_chart", "")
            idx_l = cb_link.findData(cur_link)
            cb_link.setCurrentIndex(idx_l if idx_l >= 0 else 0)
            self._style_input(cb_link)
            cb_link.currentIndexChanged.connect(lambda i: self._change_block("filter_from_chart", cb_link.itemData(i)))
            self._lay.insertWidget(self._lay.count() - 1, cb_link)

            self._add_label("2) Категория 1-го уровня (Основная группа для «Все значения»):")
            cb_pcol = QComboBox()
            cb_pcol.addItem("— Не выбрана (без группировки 1-го уровня) —", "")
            for col in cols:
                cb_pcol.addItem(str(col), str(col))
            cur_pcol = cfg.get("parent_group_col", "")
            idx_p = cb_pcol.findData(cur_pcol)
            cb_pcol.setCurrentIndex(idx_p if idx_p >= 0 else 0)
            self._style_input(cb_pcol)
            cb_pcol.currentIndexChanged.connect(lambda i: self._change_block("parent_group_col", cb_pcol.itemData(i)))
            self._lay.insertWidget(self._lay.count() - 1, cb_pcol)

            self._add_label("3) Категория 2-го уровня (Детализация при выборе группы в Фильтре):")
            cb_mcol = QComboBox()
            cb_mcol.addItem("— Авто (использовать столбец Оси X) —", "")
            for col in cols:
                cb_mcol.addItem(str(col), str(col))
            cur_mcol = cfg.get("model_col", "")
            idx_mc = cb_mcol.findData(cur_mcol)
            cb_mcol.setCurrentIndex(idx_mc if idx_mc >= 0 else 0)
            self._style_input(cb_mcol)
            cb_mcol.currentIndexChanged.connect(lambda i: self._change_block("model_col", cb_mcol.itemData(i)))
            self._lay.insertWidget(self._lay.count() - 1, cb_mcol)

            self._add_label("4) Столбец даты / периода (группировка по месяцам):")
            cb_dcol = QComboBox()
            cb_dcol.addItem("— Без группировки по датам —", "")
            for col in cols:
                cb_dcol.addItem(str(col), str(col))
            cur_dcol = cfg.get("date_col", "")
            idx_dc = cb_dcol.findData(cur_dcol)
            cb_dcol.setCurrentIndex(idx_dc if idx_dc >= 0 else 0)
            self._style_input(cb_dcol)
            cb_dcol.currentIndexChanged.connect(lambda i: self._change_block("date_col", cb_dcol.itemData(i)))
            self._lay.insertWidget(self._lay.count() - 1, cb_dcol)

            self._add_label("Столбец А (Основной показатель / Факт)")
            cb_fact = QComboBox()
            cb_fact.addItem("— Не выбран (брать Ось Y) —", "")
            for col in cols:
                cb_fact.addItem(str(col), str(col))
            idx_fc = cb_fact.findData(cfg.get("fact_col", ""))
            cb_fact.setCurrentIndex(idx_fc if idx_fc >= 0 else 0)
            self._style_input(cb_fact)
            cb_fact.currentIndexChanged.connect(lambda i: self._change_block("fact_col", cb_fact.itemData(i)))
            self._lay.insertWidget(self._lay.count() - 1, cb_fact)

            self._add_label("Столбец Б (База для сравнения / Норматив / План)")
            cb_norm = QComboBox()
            cb_norm.addItem("— Не выбран —", "")
            for col in cols:
                cb_norm.addItem(str(col), str(col))
            idx_nc = cb_norm.findData(cfg.get("norm_col", ""))
            cb_norm.setCurrentIndex(idx_nc if idx_nc >= 0 else 0)
            self._style_input(cb_norm)
            cb_norm.currentIndexChanged.connect(lambda i: self._change_block("norm_col", cb_norm.itemData(i)))
            self._lay.insertWidget(self._lay.count() - 1, cb_norm)

            _DEV_MODES = [
                ("📐 Процент отклонения: ((А − Б) / Б) × 100%", "formula_pct_self"),
                ("📐 Вклад в отклонение группы: ((А − Б) / Б_общий) × 100%", "formula_pct_group"),
                ("📐 Процент снижения/экономии: ((Б − А) / Б) × 100%", "formula_saving_self"),
                ("📐 Отношение показателей: (А / Б) × 100%", "formula_ratio_ab"),
                ("🧮 Своя формула (конструктор ниже)", "custom_formula"),
                ("Сравнение: Кол-во записей, где А ≠ Б (все отклонения)", "waybill_diff_count"),
                ("Сравнение: Кол-во записей, где А > Б (превышение)", "waybill_count"),
                ("Сравнение: Кол-во записей, где А < Б (снижение / экономия)", "waybill_saving"),
                ("Сравнение: Кол-во записей, где А = Б (совпадение / норма)", "waybill_equal_count"),
                ("Сравнение: Сумма разницы |Столбец А − Столбец Б|", "waybill_overrun_sum"),
                ("Количество всех записей (COUNT строк по категориям)", "waybill_all_rows"),
                ("Сумма значений по Столбцу А (SUM)", "value_sum"),
                ("Среднее значение по Столбцу А (AVG)", "value_mean"),
                ("Стандартный режим (по настройкам Оси X / Оси Y выше)", "none"),
            ]

            self._add_label("5) Режим расчёта показателя / процента")
            cb_dev = QComboBox()
            for title, val in _DEV_MODES:
                cb_dev.addItem(title, val)
            cur_dev = cfg.get("deviation_mode", "formula_pct_self")
            idx_dv = cb_dev.findData(cur_dev)
            cb_dev.setCurrentIndex(idx_dv if idx_dv >= 0 else 0)
            self._style_input(cb_dev)
            self._lay.insertWidget(self._lay.count() - 1, cb_dev)

            # --- КОНСТРУКТОР ФОРМУЛЫ ПРОЦЕНТА (ЧТО ИЩЕМ И ЧТО НА ЧТО ДЕЛИМ) ---
            self._section_header("Конструктор формулы процента (Что на что делим)")

            self._add_label("Числитель (Что ищем):")
            cb_num = QComboBox()
            _NUM_ITEMS = [
                ("А − Б  (Факт общий − Норматив общий)", "(A - B)"),
                ("|А − Б|  (Абсолютное отклонение)", "abs(A - B)"),
                ("Б − А  (Норматив общий − Факт общий)", "(B - A)"),
                ("А  (Сумма Столбца А / Факт)", "A"),
                ("Б  (Сумма Столбца Б / Норматив)", "B"),
                ("Кол-во записей с отклонением (А ≠ Б)", "COUNT_DIFF"),
                ("Общее кол-во записей категории", "COUNT"),
            ]
            for t, v in _NUM_ITEMS:
                cb_num.addItem(t, v)
            cur_num = cfg.get("formula_num", "(A - B)")
            idx_nm = cb_num.findData(cur_num)
            cb_num.setCurrentIndex(idx_nm if idx_nm >= 0 else 0)
            self._style_input(cb_num)
            self._lay.insertWidget(self._lay.count() - 1, cb_num)

            self._add_label("Знаменатель (На что делим):")
            cb_den = QComboBox()
            _DEN_ITEMS = [
                ("÷ Б  (На Норматив общий этой категории / группы)", "B"),
                ("÷ Б_общий  (На Норматив общий всей выборки / группы)", "B_TOTAL"),
                ("÷ А  (На Факт общий этой категории / группы)", "A"),
                ("÷ А_общий  (На Факт общий всей выборки / группы)", "A_TOTAL"),
                ("÷ |А_общий − Б_общий|  (На общую разницу группы)", "abs(TOTAL_DIFF)"),
                ("÷ Общее кол-во записей группы (COUNT_TOTAL)", "COUNT_TOTAL"),
                ("÷ Кол-во записей категории (COUNT)", "COUNT"),
                ("Без деления (оставить только числитель)", "1"),
            ]
            for t, v in _DEN_ITEMS:
                cb_den.addItem(t, v)
            cur_den = cfg.get("formula_den", "B")
            idx_dn = cb_den.findData(cur_den)
            cb_den.setCurrentIndex(idx_dn if idx_dn >= 0 else 0)
            self._style_input(cb_den)
            self._lay.insertWidget(self._lay.count() - 1, cb_den)

            cb_mul100 = QCheckBox("× 100% (Перевести результат деления в проценты)")
            cb_mul100.setChecked(bool(cfg.get("formula_mul100", True)))
            cb_mul100.setStyleSheet(
                f"QCheckBox {{ color:{self.theme.text_main}; font-size:11px; padding:2px 0; background:transparent; }}"
            )
            self._lay.insertWidget(self._lay.count() - 1, cb_mul100)

            self._add_label("Итоговая формула (можно редактировать и писать свою):")
            inp_formula = QLineEdit(str(cfg.get("calc_formula", "((A - B) / B) * 100")))
            inp_formula.setPlaceholderText("Например: ((A - B) / B) * 100  или  ((Факт - Норматив) / Норматив) * 100%")
            self._style_input(inp_formula)
            self._lay.insertWidget(self._lay.count() - 1, inp_formula)

            # Кнопки быстрой вставки переменных в поле формулы
            tokens_row = QHBoxLayout()
            tokens_row.setSpacing(3)
            for btn_lbl, token_str in (
                ("А (Факт)", "A"),
                ("Б (Норма)", "B"),
                ("А_общ", "A_TOTAL"),
                ("Б_общ", "B_TOTAL"),
                ("Кол-во", "COUNT"),
                ("*100", " * 100"),
            ):
                b_tok = QPushButton(btn_lbl)
                b_tok.setCursor(Qt.PointingHandCursor)
                b_tok.setStyleSheet(
                    f"QPushButton {{ background:{self.theme.bg_panel}; color:{self.theme.text_main}; "
                    f"border:1px solid {self.theme.border}; border-radius:3px; padding:2px 4px; font-size:9px; }}"
                    f"QPushButton:hover {{ border-color:{self.theme.primary}; }}"
                )
                b_tok.clicked.connect(lambda _, tk=token_str: inp_formula.insert(tk))
                tokens_row.addWidget(b_tok)
            self._lay.insertWidget(self._lay.count() - 1, self._wrap_row(tokens_row))

            def rebuild_formula_from_parts():
                num_s = cb_num.currentData() or "(A - B)"
                den_s = cb_den.currentData() or "B"
                mul_b = cb_mul100.isChecked()
                if den_s == "1":
                    f_str = f"({num_s}) * 100" if mul_b else f"{num_s}"
                else:
                    f_str = f"({num_s} / {den_s}) * 100" if mul_b else f"({num_s} / {den_s})"

                inp_formula.blockSignals(True)
                inp_formula.setText(f_str)
                inp_formula.blockSignals(False)

                cb_dev.blockSignals(True)
                idx_c = cb_dev.findData("custom_formula")
                if idx_c >= 0:
                    cb_dev.setCurrentIndex(idx_c)
                cb_dev.blockSignals(False)

                if self._block is not None:
                    new_cfg = dict(self._block.config or {})
                    new_cfg["formula_num"] = num_s
                    new_cfg["formula_den"] = den_s
                    new_cfg["formula_mul100"] = mul_b
                    new_cfg["calc_formula"] = f_str
                    new_cfg["deviation_mode"] = "custom_formula"
                    self._block.config = new_cfg
                    self.config_changed.emit(self._block.id)

            def on_dev_mode_changed(i):
                m_val = cb_dev.itemData(i)
                preset_map = {
                    "formula_pct_self": ("((A - B) / B) * 100", "(A - B)", "B", True),
                    "formula_pct_group": ("((A - B) / B_TOTAL) * 100", "(A - B)", "B_TOTAL", True),
                    "formula_saving_self": ("((B - A) / B) * 100", "(B - A)", "B", True),
                    "formula_ratio_ab": ("(A / B) * 100", "A", "B", True),
                }
                if m_val in preset_map:
                    f_str, n_val, d_val, m_bool = preset_map[m_val]
                    inp_formula.blockSignals(True)
                    inp_formula.setText(f_str)
                    inp_formula.blockSignals(False)
                    cb_num.blockSignals(True)
                    cb_den.blockSignals(True)
                    cb_mul100.blockSignals(True)
                    cb_num.setCurrentIndex(max(0, cb_num.findData(n_val)))
                    cb_den.setCurrentIndex(max(0, cb_den.findData(d_val)))
                    cb_mul100.setChecked(m_bool)
                    cb_num.blockSignals(False)
                    cb_den.blockSignals(False)
                    cb_mul100.blockSignals(False)
                    if self._block is not None:
                        new_cfg = dict(self._block.config or {})
                        new_cfg["deviation_mode"] = m_val
                        new_cfg["calc_formula"] = f_str
                        new_cfg["formula_num"] = n_val
                        new_cfg["formula_den"] = d_val
                        new_cfg["formula_mul100"] = m_bool
                        self._block.config = new_cfg
                        self.config_changed.emit(self._block.id)
                else:
                    self._change_block("deviation_mode", m_val)

            def on_manual_formula_edited(txt: str):
                cb_dev.blockSignals(True)
                idx_c = cb_dev.findData("custom_formula")
                if idx_c >= 0:
                    cb_dev.setCurrentIndex(idx_c)
                cb_dev.blockSignals(False)
                if self._block is not None:
                    new_cfg = dict(self._block.config or {})
                    new_cfg["calc_formula"] = txt
                    new_cfg["deviation_mode"] = "custom_formula"
                    self._block.config = new_cfg
                    self.config_changed.emit(self._block.id)

            cb_dev.currentIndexChanged.connect(on_dev_mode_changed)
            cb_num.currentIndexChanged.connect(lambda _i: rebuild_formula_from_parts())
            cb_den.currentIndexChanged.connect(lambda _i: rebuild_formula_from_parts())
            cb_mul100.toggled.connect(lambda _v: rebuild_formula_from_parts())
            inp_formula.textEdited.connect(on_manual_formula_edited)

            _SCOPE_MODES = [
                ("Все строки категории (полный Факт общий и Норматив общий)", "all_rows"),
                ("Только с отклонением (где А ≠ Б)", "diff_only"),
                ("Только перерасход / превышение (где А > Б)", "over_only"),
                ("Только экономия / снижение (где А < Б)", "saving_only"),
            ]
            self._field_combo("По каким данным считать суммы А и Б (Отбор):", "formula_row_scope", cfg, _SCOPE_MODES, "all_rows")

            _EVAL_MODES = [
                ("📄 Отдельно друг от друга (по каждому путевому листу / строке)", "separate"),
                ("🚗 Группированно на основе ключевого показателя (сумма по машине / госномеру)", "grouped"),
            ]
            self._field_combo("Как производить операцию (А и Б):", "calc_eval_mode", cfg, _EVAL_MODES, "separate")

            self._add_label("Ключевой показатель для группировки (напр. Гос. номер / ТС):")
            cb_gkey = QComboBox()
            cb_gkey.addItem("— Авто (брать Доп. поле / Гос. номер / Ось X) —", "")
            for col in cols:
                cb_gkey.addItem(str(col), str(col))
            idx_gk = cb_gkey.findData(cfg.get("calc_group_col", ""))
            cb_gkey.setCurrentIndex(idx_gk if idx_gk >= 0 else 0)
            self._style_input(cb_gkey)
            cb_gkey.currentIndexChanged.connect(lambda i: self._change_block("calc_group_col", cb_gkey.itemData(i)))
            self._lay.insertWidget(self._lay.count() - 1, cb_gkey)

            _PIE_VAL_MODES = [
                ("Точный % по формуле со знаком (напр. -6.20% или +5.40%)", "formula_pct"),
                ("Модуль % по формуле без минуса (напр. 6.20%)", "formula_abs_pct"),
                ("% по формуле + Доля сектора от круга", "formula_and_share"),
                ("Классическая доля сектора от 100% круга", "share_only"),
            ]
            self._field_combo("Что выводить как % на секторах круга", "pie_value_display", cfg, _PIE_VAL_MODES, "formula_pct")

            # ── ИНТЕРАКТИВНЫЙ ФИЛЬТР ПО РАСЧЕТНОМУ ПРОЦЕНТУ ──
            from PySide6.QtWidgets import QDoubleSpinBox
            self._section_header("Фильтрация секторов по проценту")

            # 1. Выпадающий список условия (на отдельной строке во всю ширину)
            self._add_label("Условие отбора секторов:")
            cb_pct_mode = QComboBox()
            cb_pct_mode.addItem("≥ Больше или равно (со знаком +/−)", "ge")
            cb_pct_mode.addItem("≤ Меньше или равно (со знаком +/−)", "le")
            cb_pct_mode.addItem("> Строго больше (со знаком +/−)", "gt")
            cb_pct_mode.addItem("< Строго меньше (со знаком +/−)", "lt")
            cb_pct_mode.addItem("|%| ≥ Больше или равно (по модулю)", "abs_ge")
            cb_pct_mode.addItem("|%| ≤ Меньше или равно (по модулю)", "abs_le")
            cb_pct_mode.addItem("Доля круга ≥ (% площади сектора)", "share_ge")
            cb_pct_mode.addItem("Доля круга ≤ (% площади сектора)", "share_le")
            cb_pct_mode.addItem("— Без фильтра (показывать все) —", "none")

            cur_pmode = cfg.get("slice_pct_mode", "ge")
            cb_pct_mode.setCurrentIndex(max(0, cb_pct_mode.findData(cur_pmode)))
            self._style_input(cb_pct_mode)
            cb_pct_mode.currentIndexChanged.connect(
                lambda i: self._change_block("slice_pct_mode", cb_pct_mode.itemData(i))
            )
            self._lay.insertWidget(self._lay.count() - 1, cb_pct_mode)

            # 2. Поле ввода самого значения процента (на отдельной строке во всю ширину)
            self._add_label("Значение процента (впишите число, напр. 5, 10, 20):")
            sp_min_pct = QDoubleSpinBox()
            sp_min_pct.setRange(-1000.0, 1000.0)
            sp_min_pct.setDecimals(1)
            sp_min_pct.setSingleStep(1.0)
            sp_min_pct.setSuffix(" %")
            sp_min_pct.setValue(float(cfg.get("min_slice_pct", 0.0) or 0.0))
            sp_min_pct.setToolTip("Введите порог процента с клавиатуры (например: 5, 10, 20) и нажмите «Обновить рендер».")
            self._style_input(sp_min_pct)
            sp_min_pct.valueChanged.connect(lambda val: self._change_block("min_slice_pct", float(val)))
            self._lay.insertWidget(self._lay.count() - 1, sp_min_pct)

            # 3. Быстрые кнопки под полем (0%, 5%, 10%, 15%, 20%)
            pct_presets_row = QHBoxLayout()
            pct_presets_row.setSpacing(4)
            for p_lbl, p_val in (("Все (0%)", 0.0), ("5%", 5.0), ("10%", 10.0), ("15%", 15.0), ("20%", 20.0)):
                btn_p = QPushButton(p_lbl)
                btn_p.setCursor(Qt.PointingHandCursor)
                btn_p.setStyleSheet(
                    f"QPushButton {{ background:{self.theme.bg_panel}; color:{self.theme.text_main}; "
                    f"border:1px solid {self.theme.border}; border-radius:3px; padding:3px 4px; font-size:10px; }}"
                    f"QPushButton:hover {{ border-color:{self.theme.primary}; }}"
                )
                btn_p.clicked.connect(lambda _, v=p_val: sp_min_pct.setValue(v))
                pct_presets_row.addWidget(btn_p)
            self._lay.insertWidget(self._lay.count() - 1, self._wrap_row(pct_presets_row))
            # ──────────────────────────────────────────────────────────────────────

            self._add_label("Доп. поле для всплывающей подсказки (напр. ID, Номер, Артикул)")
            cb_plate = QComboBox()
            cb_plate.addItem("— Не выбрано —", "")
            for col in cols:
                cb_plate.addItem(str(col), str(col))
            idx_pl = cb_plate.findData(cfg.get("plate_col", ""))
            cb_plate.setCurrentIndex(idx_pl if idx_pl >= 0 else 0)
            self._style_input(cb_plate)
            cb_plate.currentIndexChanged.connect(lambda i: self._change_block("plate_col", cb_plate.itemData(i)))
            self._lay.insertWidget(self._lay.count() - 1, cb_plate)

            _PIE_DISPLAY = [
                ("🎯 Один круг: «Все значения» = Уровень 1 ➔ Фильтр = Уровень 2", "single_interactive"),
                ("📅 Сетка по месяцам: «Все значения» = Уровень 1 ➔ Фильтр = Уровень 2", "months_grid"),
                ("🗂 Сетка по группам 1-го уровня (отдельный круг на каждую группу)", "types_grid"),
            ]
            self._field_combo("6) Режим отображения диаграммы", "pie_display_mode", cfg, _PIE_DISPLAY, "single_interactive")
            self._add_hint(
                "💡 В формуле можно использовать переменные: A (или Факт), B (или Норматив), "
                "A_TOTAL (Факт общий группы), B_TOTAL (Норматив общий группы), COUNT (кол-во записей)."
            )

        self._section_header("Условие отбора строк (ЕСЛИ)")
        self._add_label("Столбец для проверки условия")
        cb_fcol = QComboBox()
        cb_fcol.addItem("— Без фильтра (брать все строки) —", "")
        for col in cols:
            cb_fcol.addItem(str(col), str(col))
        cur_fcol = cfg.get("filter_col", "")
        idx_f = cb_fcol.findData(cur_fcol)
        cb_fcol.setCurrentIndex(idx_f if idx_f >= 0 else 0)
        self._style_input(cb_fcol)
        cb_fcol.currentIndexChanged.connect(lambda i: self._change_block("filter_col", cb_fcol.itemData(i)))
        self._lay.insertWidget(self._lay.count() - 1, cb_fcol)

        self._field_combo("Условие отбора", "filter_op", cfg, _FILTER_OPS, ">")
        self._field_text("Значение условия", "filter_val", cfg, placeholder="Например: 5  или  100, 500  или  Категория")
        self._field_text("Продвинутая формула (необязательно)", "custom_query", cfg, placeholder="Например: `Сумма` > 1000 and `Статус` == 'Активен'")

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

    def _field_axis_selectors(self, cfg: dict, cols: list[str]):
        if not cols:
            self._add_hint("Сначала загрузите Excel-файл для выбора столбцов.")
            return

        self._add_label("Ось X (Категории / Группировка)")
        cb_x = QComboBox()
        cb_x.addItem("— Авто (первый столбец) —", "")
        for col in cols:
            cb_x.addItem(str(col), str(col))
        cur_x = cfg.get("x_col", "")
        idx_x = cb_x.findData(cur_x)
        cb_x.setCurrentIndex(idx_x if idx_x >= 0 else 0)
        self._style_input(cb_x)
        cb_x.currentIndexChanged.connect(lambda i: self._change_block("x_col", cb_x.itemData(i)))
        self._lay.insertWidget(self._lay.count() - 1, cb_x)

        self._add_label("Ось Y (Основной столбец для расчёта)")
        cb_y = QComboBox()
        cb_y.addItem("— Количество строк (COUNT) —", "")
        for col in cols:
            cb_y.addItem(str(col), str(col))
        cur_y = str(cfg.get("y_col", "") or "")
        first_y = cur_y.split(",")[0].strip() if cur_y else ""
        idx_y = cb_y.findData(first_y)
        cb_y.setCurrentIndex(idx_y if idx_y >= 0 else 0)
        self._style_input(cb_y)
        self._lay.insertWidget(self._lay.count() - 1, cb_y)

        self._add_label("Несколько графиков на одном (столбцы Y через запятую)")
        row_multi = QHBoxLayout()
        row_multi.setSpacing(4)

        edit_y = QLineEdit(cur_y)
        edit_y.setPlaceholderText("Столбец1, Столбец2...")
        self._style_input(edit_y)
        row_multi.addWidget(edit_y, 1)

        btn_clear_y = QPushButton("✕")
        btn_clear_y.setFixedWidth(26)
        self._style_input(btn_clear_y)
        row_multi.addWidget(btn_clear_y)
        self._lay.insertWidget(self._lay.count() - 1, self._wrap_row(row_multi))

        cb_add_y = QComboBox()
        cb_add_y.addItem("➕ Добавить ещё столбец на этот график…", "")
        for col in cols:
            cb_add_y.addItem(f"+ {col}", str(col))
        self._style_input(cb_add_y)
        self._lay.insertWidget(self._lay.count() - 1, cb_add_y)

        def on_primary_y_changed(i):
            col_val = cb_y.itemData(i) or ""
            current_parts = [c.strip() for c in edit_y.text().split(",") if c.strip()]
            if not col_val:
                new_val = ""
            elif len(current_parts) <= 1:
                new_val = col_val
            else:
                current_parts[0] = col_val
                new_val = ", ".join(current_parts)
            edit_y.blockSignals(True)
            edit_y.setText(new_val)
            edit_y.blockSignals(False)
            self._change_block("y_col", new_val)

        def on_add_extra_y(i):
            col_val = cb_add_y.itemData(i)
            if not col_val: return
            current_parts = [c.strip() for c in edit_y.text().split(",") if c.strip()]
            if col_val not in current_parts:
                current_parts.append(col_val)
            new_val = ", ".join(current_parts)
            edit_y.blockSignals(True)
            edit_y.setText(new_val)
            edit_y.blockSignals(False)
            cb_add_y.blockSignals(True)
            cb_add_y.setCurrentIndex(0)
            cb_add_y.blockSignals(False)
            self._change_block("y_col", new_val)

        def on_clear_y():
            edit_y.setText("")
            cb_y.blockSignals(True)
            cb_y.setCurrentIndex(0)
            cb_y.blockSignals(False)
            self._change_block("y_col", "")

        cb_y.currentIndexChanged.connect(on_primary_y_changed)
        cb_add_y.currentIndexChanged.connect(on_add_extra_y)
        btn_clear_y.clicked.connect(on_clear_y)
        edit_y.textChanged.connect(lambda v: self._change_block("y_col", v))

        _MULTI_Y_MODES = [
            ("📊 Отдельно друг от друга (несколько линий / столбцов)", "separate"),
            ("🧮 Объединить выбранные столбцы Y математической операцией", "combined"),
        ]
        self._field_combo("Режим нескольких столбцов Y:", "multi_y_mode", cfg, _MULTI_Y_MODES, "separate")

        _MULTI_Y_FUNCS = [
            ("Разность: Столбец 1 − Столбец 2 (Факт − Норматив)", "sub"),
            ("Сумма: Столбец 1 + Столбец 2", "sum"),
            ("Деление: Столбец 1 / Столбец 2", "div"),
            ("Произведение: Столбец 1 × Столбец 2", "mul"),
            ("Среднее значение столбцов", "mean"),
        ]
        self._field_combo("Операция при объединении столбцов Y:", "multi_y_func", cfg, _MULTI_Y_FUNCS, "sub")

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