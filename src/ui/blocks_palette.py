"""
Верхняя интерактивная панель добавления BI-блоков (Ribbon-меню Конструктора).
Разбита на смысловые группы. При наведении курсора (с задержкой 1 сек) или по клику
открывает интерактивное меню группы. При удержании курсора на любом блоке внутри того же
меню раскрывается живое зацикленное превью холста (анимация работы блока) и описание.
"""

from __future__ import annotations
import math

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QGridLayout, QApplication,
)
from PySide6.QtCore import Qt, Signal, QTimer, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QPainterPath, QPolygonF


# ============================================================
# Каталог групп, блоков и обучающих описаний для живого превью
# ============================================================

_GROUPS_CATALOG = [
    {
        "id": "charts",
        "title": "📈  Графики и Диаграммы",
        "accent": "#87C800",
        "items": [
            {
                "key": "plotly_chart",
                "title": "Интерактивный график (Универсальный)",
                "subtitle": "Линейные, столбчатые, накопительные и круговые диаграммы",
                "icon": "📈",
                "accent": "#87C800",
                "anim_kind": "chart_cycle",
                "how_it_works": (
                    "Строит динамические графики по столбцам или строкам таблицы.\n"
                    "• Поддерживает переключение типов: Линия ➔ Столбцы ➔ Накопление ➔ Кольцо.\n"
                    "• Автоматически группирует даты по месяцам и пересчитывает масштаб осей при фильтрации."
                ),
                "presets": [
                    ("📉 Линейный", "plotly_chart:line"),
                    ("📊 Столбчатый", "plotly_chart:bar"),
                    ("🧱 Накопительный", "plotly_chart:bar_stacked"),
                    ("📐 Нарастающий итог", "plotly_chart:bar_cumulative"),
                    ("💯 100% Накопит.", "plotly_chart:bar_stacked_100"),
                    ("🍩 Кольцевой", "plotly_chart:donut"),
                ],
            },
            {
                "key": "plotly_chart:bar_stacked",
                "title": "Накопительная гистограмма (Stacked)",
                "subtitle": "Складывает 2, 3 и более показателей внутри каждого месяца",
                "icon": "🧱",
                "accent": "#2bb24c",
                "anim_kind": "stacked_bar",
                "how_it_works": (
                    "Наглядно показывает общую сумму и вклад каждого из 3+ столбцов по месяцам.\n"
                    "• Выберите столбец Даты по оси X и добавьте нужные показатели по оси Y.\n"
                    "• Сегменты складываются друг на друга с подписями значений внутри столбцов."
                ),
                "presets": [],
            },
            {
                "key": "plotly_chart:donut",
                "title": "Кольцевая / Круговая с месяцами",
                "subtitle": "Доли категорий с кнопками переключения месяцев и Drill-Down",
                "icon": "🍩",
                "accent": "#f59e0b",
                "anim_kind": "donut_drill",
                "how_it_works": (
                    "Рассчитывает доли и процент отклонения по формуле ((Факт − Норма) / Норма) × 100%.\n"
                    "• Над диаграммой автоматически создаются кнопки месяцев.\n"
                    "• При клике на Фильтр раскрывает модели/марки внутри выбранного типа ТС."
                ),
                "presets": [],
            },
        ],
    },
    {
        "id": "bi_analytics",
        "title": "🎯  Фильтры и BI-Аналитика",
        "accent": "#2b7fff",
        "items": [
            {
                "key": "dashboard_filter",
                "title": "Фильтр (Срез данных)",
                "subtitle": "Интерактивные кнопки отбора для управления графиками и текстом",
                "icon": "🎯",
                "accent": "#2b7fff",
                "anim_kind": "filter_sync",
                "how_it_works": (
                    "Управляет одним или сразу несколькими графиками и текстовыми выводами.\n"
                    "• При нажатии на категорию в срезе все связанные графики мгновенно перестраиваются.\n"
                    "• Высота списка автоматически синхронизируется с соседним графиком."
                ),
                "presets": [],
            },
            {
                "key": "pivot_matrix",
                "title": "Сводная матрица (Pivot)",
                "subtitle": "Перекрёстная таблица Строки × Столбцы с авто-итогами",
                "icon": "⊞",
                "accent": "#0ea5e9",
                "anim_kind": "pivot",
                "how_it_works": (
                    "Группирует данные по строкам (например, Тип ТС) и столбцам (Месяцы).\n"
                    "• Автоматически считает Сумму, Среднее или Количество.\n"
                    "• Формирует итоговую строку и столбец «Итого» с подсветкой."
                ),
                "presets": [],
            },
            {
                "key": "decomposition",
                "title": "Дерево декомпозиции",
                "subtitle": "Иерархический анализ вклада (Treemap / Sunburst до 3 уровней)",
                "icon": "🌳",
                "accent": "#f43f5e",
                "anim_kind": "treemap",
                "how_it_works": (
                    "Разбивает общий показатель на вложенные уровни: Группа ➔ Марка ➔ Гос.номер.\n"
                    "• Размер прямоугольника или сектора пропорционален весу показателя.\n"
                    "• Поддерживает режимы Прямоугольников (Treemap) и Солнечных лучей (Sunburst)."
                ),
                "presets": [],
            },
            {
                "key": "geo_map",
                "title": "Гео-карта и рейтинг локаций",
                "subtitle": "Распределение показателей по регионам, филиалам и объектам",
                "icon": "🗺",
                "accent": "#14b8a6",
                "anim_kind": "geomap",
                "how_it_works": (
                    "Визуализирует географию и рейтинг подразделений или маршрутов.\n"
                    "• Режимы: Горизонтальный рейтинг (Bar), Тепловая карта (Treemap) и Карта стран (Choropleth).\n"
                    "• Автоматически выделяет лидеров цветовой шкалой."
                ),
                "presets": [],
            },
        ],
    },
    {
        "id": "tables_kpi",
        "title": "📊  Таблицы и Метрики",
        "accent": "#a855f7",
        "items": [
            {
                "key": "kpi_row",
                "title": "KPI-карточки (Метрики)",
                "subtitle": "Ряд крупных цифровых показателей с цветовыми акцентами",
                "icon": "📊",
                "accent": "#a855f7",
                "anim_kind": "kpi",
                "how_it_works": (
                    "Выводит ключевые цифры отчёта (Выручка, Факт ГСМ, Экономия %) в верхней части листа.\n"
                    "• Добавьте знак «!» после значения в Инспекторе, чтобы выделить карточку зелёным акцентом."
                ),
                "presets": [],
            },
            {
                "key": "data_table",
                "title": "Таблица данных",
                "subtitle": "Интерактивная таблица с живым поиском и прокруткой",
                "icon": "🗂",
                "accent": "#64748b",
                "anim_kind": "table",
                "how_it_works": (
                    "Встраивает исходную или отфильтрованную таблицу в отчёт.\n"
                    "• Включает кнопку живого поиска по всем колонкам прямо в браузере.\n"
                    "• В Инспекторе можно выбрать только нужные для показа столбцы."
                ),
                "presets": [],
            },
        ],
    },
    {
        "id": "text_layout",
        "title": "📝  Текст и Разметка",
        "accent": "#f59e0b",
        "items": [
            {
                "key": "paragraph:smart",
                "title": "Умный аналитический вывод (ЕСЛИ)",
                "subtitle": "Авто-текст, меняющийся при клике на фильтр и месяцы",
                "icon": "🧠",
                "accent": "#f59e0b",
                "anim_kind": "smart_text",
                "how_it_works": (
                    "Автоматически подставляет расчёты Факта, Нормы и % отклонения в текст.\n"
                    "• Поддерживает формулы {{ if(pct > 0; 'Перерасход'; 'Экономия') }}.\n"
                    "• Мгновенно переписывает вывод при выборе категории в Срезе."
                ),
                "presets": [
                    ("🧠 Шаблон ЕСЛИ", "paragraph:smart"),
                    ("📝 Обычный текст", "paragraph"),
                ],
            },
            {
                "key": "section_title",
                "title": "Заголовок раздела",
                "subtitle": "Крупный заголовок с автоматической привязкой к оглавлению",
                "icon": "📑",
                "accent": "#10b981",
                "anim_kind": "layout_doc",
                "how_it_works": (
                    "Создаёт визуальный заголовок смыслового блока с фирменной линией.\n"
                    "• Двойной клик по блоку на холсте открывает визуальный редактор шрифта и цвета."
                ),
                "presets": [],
            },
            {
                "key": "list",
                "title": "Маркированный список",
                "subtitle": "Структурированный перечень выводов или рекомендаций",
                "icon": "📋",
                "accent": "#ec4899",
                "anim_kind": "layout_doc",
                "how_it_works": (
                    "Оформляет ключевые тезисы и буллиты отчёта.\n"
                    "• Редактируется прямо на холсте двойным кликом."
                ),
                "presets": [],
            },
            {
                "key": "divider",
                "title": "Разделительная линия",
                "subtitle": "Визуальная граница между блоками отчёта",
                "icon": "➖",
                "accent": "#94a3b8",
                "anim_kind": "layout_doc",
                "how_it_works": (
                    "Добавляет аккуратную горизонтальную линию для отделения смысловых частей дашборда."
                ),
                "presets": [],
            },
        ],
    },
    {
        "id": "combos",
        "title": "⚡  Готовые дашборды",
        "accent": "#10b981",
        "items": [
            {
                "key": "combo:filter_line",
                "title": "Дашборд: Фильтр + Линейный тренд",
                "subtitle": "Готовая связка 25% / 75% с привязкой среза к графику",
                "icon": "📈",
                "accent": "#87C800",
                "anim_kind": "filter_sync",
                "how_it_works": (
                    "В один клик создаёт контейнер из Среза слева (25%) и Линейного графика справа (75%).\n"
                    "• Связь между фильтром и графиком уже настроена автоматически."
                ),
                "presets": [],
            },
            {
                "key": "combo:filter_donut_text",
                "title": "Комплексный: Срез + Кольцо + Вывод ЕСЛИ",
                "subtitle": "Полный интерактивный дашборд из 3 связанных блоков",
                "icon": "🎯",
                "accent": "#2b7fff",
                "anim_kind": "combo_full",
                "how_it_works": (
                    "Создаёт готовый аналитический комплекс: Фильтр + Кольцевая диаграмма по месяцам + Умный вывод.\n"
                    "• Клик по фильтру или месяцу одновременно обновляет и диаграмму, и текст вывода."
                ),
                "presets": [],
            },
            {
                "key": "combo:two_charts",
                "title": "Два графика в ряд (50% + 50%)",
                "subtitle": "Готовый контейнер из столбчатой и кольцевой диаграмм",
                "icon": "⚖",
                "accent": "#a855f7",
                "anim_kind": "chart_cycle",
                "how_it_works": (
                    "Размещает два графика рядом друг с другом (по 50% ширины листа).\n"
                    "• Удобно для одновременного сравнения динамики и структуры долей."
                ),
                "presets": [],
            },
        ],
    },
]


# ============================================================
# Виджет зацикленной анимации («живая GIF-демонстрация» холста)
# ============================================================

class _LoopedCanvasAnimator(QWidget):
    """
    Рисует мини-холст отчёта и в бесконечном цикле анимирует работу выбранного блока
    (смена линейного графика на столбчатый и круговой, клики по фильтру, матрица и т.д.).
    """

    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self._anim_kind = "chart_cycle"
        self._tick = 0
        self.setFixedSize(290, 155)

        self._timer = QTimer(self)
        self._timer.setInterval(40)  # 25 кадров/сек
        self._timer.timeout.connect(self._on_step)

    def set_animation_kind(self, kind: str):
        if self._anim_kind != kind:
            self._anim_kind = kind
            self._tick = 0
        if not self._timer.isActive():
            self._timer.start()
        self.update()

    def stop_animation(self):
        self._timer.stop()

    def _on_step(self):
        self._tick = (self._tick + 1) % 360
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        # Фон мини-холста
        p.setPen(QPen(QColor("#334155"), 1))
        p.setBrush(QColor("#0f172a"))
        p.drawRoundedRect(QRectF(1, 1, w - 2, h - 2), 8, 8)

        # Верхняя шапка «Холст отчёта»
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#1e293b"))
        p.drawRoundedRect(QRectF(8, 7, w - 16, 18), 4, 4)

        p.setBrush(QColor("#87C800"))
        p.drawEllipse(QPointF(16, 16), 3.5, 3.5)
        p.setPen(QColor("#94a3b8"))
        p.setFont(QFont("Segoe UI", 7, QFont.Bold))
        p.drawText(QRectF(25, 7, w - 35, 18), Qt.AlignVCenter | Qt.AlignLeft, "ПРЕВЬЮ ХОЛСТА (АВТО-ДЕМО)")

        canvas_rect = QRectF(8, 29, w - 16, h - 36)
        p.setPen(QPen(QColor("#1e293b"), 1))
        p.setBrush(QColor("#162032"))
        p.drawRoundedRect(canvas_rect, 6, 6)

        kind = self._anim_kind
        if kind == "chart_cycle":
            self._draw_chart_cycle(p, canvas_rect)
        elif kind == "stacked_bar":
            self._draw_stacked_bar(p, canvas_rect)
        elif kind == "donut_drill":
            self._draw_donut_drill(p, canvas_rect)
        elif kind == "filter_sync":
            self._draw_filter_sync(p, canvas_rect)
        elif kind == "pivot":
            self._draw_pivot(p, canvas_rect)
        elif kind == "treemap":
            self._draw_treemap(p, canvas_rect)
        elif kind == "geomap":
            self._draw_geomap(p, canvas_rect)
        elif kind == "kpi":
            self._draw_kpi(p, canvas_rect)
        elif kind == "table":
            self._draw_table(p, canvas_rect)
        elif kind == "smart_text":
            self._draw_smart_text(p, canvas_rect)
        elif kind == "combo_full":
            self._draw_combo_full(p, canvas_rect)
        else:
            self._draw_layout_doc(p, canvas_rect)

        p.end()

    def _draw_badge(self, p: QPainter, rect: QRectF, text: str, color_hex: str):
        p.setPen(Qt.NoPen)
        c = QColor(color_hex)
        c.setAlpha(45)
        p.setBrush(c)
        p.drawRoundedRect(QRectF(rect.left() + 6, rect.top() + 5, rect.width() - 12, 16), 4, 4)
        p.setPen(QColor(color_hex))
        p.setFont(QFont("Segoe UI", 7, QFont.Bold))
        p.drawText(QRectF(rect.left() + 10, rect.top() + 5, rect.width() - 20, 16), Qt.AlignVCenter | Qt.AlignLeft, text)

    def _draw_chart_cycle(self, p: QPainter, r: QRectF):
        # 4 фазы по 45 тиков (1.8 сек каждая): Line -> Bar -> Stacked -> Donut
        phase = (self._tick // 45) % 4
        local_t = min(1.0, (self._tick % 45) / 22.0)
        vals = [0.35, 0.65, 0.50, 0.85, 0.72]

        if phase == 0:
            self._draw_badge(p, r, "1/4  📉 Линейный график (Динамика)", "#87C800")
            pts = []
            x0, y0, cw, ch = r.left() + 20, r.bottom() - 14, r.width() - 40, r.height() - 42
            for i, v in enumerate(vals):
                px = x0 + i * (cw / (len(vals) - 1))
                py = y0 - v * ch * local_t
                pts.append(QPointF(px, py))
            p.setPen(QPen(QColor("#87C800"), 2.4))
            for i in range(len(pts) - 1):
                p.drawLine(pts[i], pts[i + 1])
            p.setBrush(QColor("#2b7fff"))
            for pt in pts:
                p.drawEllipse(pt, 3.5, 3.5)

        elif phase == 1:
            self._draw_badge(p, r, "2/4  📊 Столбчатая диаграмма (Bar)", "#2b7fff")
            x0, y0, cw, ch = r.left() + 22, r.bottom() - 12, r.width() - 44, r.height() - 42
            bw = cw / len(vals) - 8
            colors = ["#2b7fff", "#87C800", "#0ea5e9", "#a855f7", "#f59e0b"]
            for i, v in enumerate(vals):
                bh = v * ch * local_t
                bx = x0 + i * (bw + 8)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(colors[i % len(colors)]))
                p.drawRoundedRect(QRectF(bx, y0 - bh, bw, bh), 3, 3)

        elif phase == 2:
            self._draw_badge(p, r, "3/4  🧱 Накопительная (3 столбца)", "#10b981")
            self._draw_stacked_bars_inner(p, r, local_t)

        else:
            self._draw_badge(p, r, "4/4  🍩 Кольцевая диаграмма (Доли %)", "#f59e0b")
            cx, cy = r.center().x(), r.center().y() + 8
            rad = 34
            pie_rect = QRectF(cx - rad, cy - rad, rad * 2, rad * 2)
            spans = [(140, "#87C800"), (110, "#2b7fff"), (70, "#f59e0b"), (40, "#a855f7")]
            start_a = 90 * 16
            for deg, c_hex in spans:
                span_a = int(-deg * 16 * local_t)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(c_hex))
                p.drawPie(pie_rect, start_a, span_a)
                start_a += span_a
            p.setBrush(QColor("#162032"))
            p.drawEllipse(QPointF(cx, cy), 17, 17)
            p.setPen(QColor("#ffffff"))
            p.setFont(QFont("Segoe UI", 7, QFont.Bold))
            p.drawText(pie_rect, Qt.AlignCenter, "-12%")

    def _draw_stacked_bars_inner(self, p: QPainter, r: QRectF, progress: float):
        x0, y0, cw, ch = r.left() + 20, r.bottom() - 12, r.width() - 40, r.height() - 42
        cols_data = [
            (0.30, 0.25, 0.15),
            (0.28, 0.30, 0.18),
            (0.35, 0.28, 0.20),
            (0.32, 0.26, 0.16),
            (0.38, 0.30, 0.22),
        ]
        seg_colors = ["#2b7fff", "#87C800", "#f59e0b"]
        bw = cw / len(cols_data) - 8
        for i, segs in enumerate(cols_data):
            bx = x0 + i * (bw + 8)
            cur_y = y0
            for s_idx, s_val in enumerate(segs):
                sh = s_val * ch * progress
                cur_y -= sh
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(seg_colors[s_idx]))
                p.drawRect(QRectF(bx, cur_y, bw, max(0.0, sh - 1)))

    def _draw_stacked_bar(self, p: QPainter, r: QRectF):
        progress = min(1.0, (self._tick % 70) / 30.0)
        self._draw_badge(p, r, "🧱 Помесячное накопление 3 показателей", "#87C800")
        self._draw_stacked_bars_inner(p, r, progress)

    def _draw_donut_drill(self, p: QPainter, r: QRectF):
        phase = (self._tick // 50) % 3
        months = ["Весь период (-12%)", "Январь (-9.5%)", "Февраль (-7.8%)"]
        self._draw_badge(p, r, f"🍩 Период: {months[phase]}", "#f59e0b")
        cx, cy = r.center().x(), r.center().y() + 9
        rad = 33
        pie_rect = QRectF(cx - rad, cy - rad, rad * 2, rad * 2)
        presets = [
            [(150, "#87C800"), (120, "#2b7fff"), (90, "#f59e0b")],
            [(95, "#87C800"), (165, "#2b7fff"), (100, "#f59e0b")],
            [(180, "#87C800"), (80, "#2b7fff"), (100, "#f59e0b")],
        ]
        start_a = 90 * 16
        for deg, c_hex in presets[phase]:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(c_hex))
            p.drawPie(pie_rect, start_a, -deg * 16)
            start_a -= deg * 16
        p.setBrush(QColor("#162032"))
        p.drawEllipse(QPointF(cx, cy), 16, 16)

    def _draw_filter_sync(self, p: QPainter, r: QRectF):
        sel = (self._tick // 40) % 3
        names = ["Все ТС", "Грузовой", "Самосвал"]
        self._draw_badge(p, r, f"🎯 Срез: выбрано «{names[sel]}» ➔ пересчёт осей", "#2b7fff")

        # Левая колонка среза
        fx = r.left() + 8
        fy = r.top() + 26
        for i, name in enumerate(names):
            is_act = (i == sel)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#87C800" if is_act else "#1e293b"))
            p.drawRoundedRect(QRectF(fx, fy + i * 22, 68, 18), 4, 4)
            p.setPen(QColor("#ffffff" if is_act else "#94a3b8"))
            p.setFont(QFont("Segoe UI", 7, QFont.Bold if is_act else QFont.Normal))
            p.drawText(QRectF(fx + 5, fy + i * 22, 58, 18), Qt.AlignVCenter, name)

        # Правая часть — график, меняющийся от фильтра
        series_sets = [
            [0.85, 0.70, 0.90, 0.78],
            [0.45, 0.62, 0.52, 0.70],
            [0.75, 0.40, 0.65, 0.88],
        ]
        vals = series_sets[sel]
        gx, gy, gw, gh = fx + 80, r.bottom() - 12, r.width() - 96, r.height() - 44
        bw = gw / len(vals) - 6
        for i, v in enumerate(vals):
            bh = v * gh
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#2b7fff" if i % 2 == 0 else "#87C800"))
            p.drawRoundedRect(QRectF(gx + i * (bw + 6), gy - bh, bw, bh), 3, 3)

    def _draw_pivot(self, p: QPainter, r: QRectF):
        self._draw_badge(p, r, "⊞ Сводная матрица (Строки × Месяцы + Итого)", "#0ea5e9")
        tx, ty = r.left() + 10, r.top() + 26
        cw, ch = (r.width() - 20) / 4, 18
        active_col = (self._tick // 30) % 4
        for row in range(4):
            for col in range(4):
                cell_r = QRectF(tx + col * cw, ty + row * ch, cw - 2, ch - 2)
                if row == 0 or col == 3 or row == 3:
                    p.setBrush(QColor("#1e3a5f" if (col == active_col or row == 3) else "#1e293b"))
                else:
                    p.setBrush(QColor("#0f172a"))
                p.setPen(QPen(QColor("#334155"), 0.8))
                p.drawRoundedRect(cell_r, 2, 2)

    def _draw_treemap(self, p: QPainter, r: QRectF):
        self._draw_badge(p, r, "🌳 Иерархия: Группа ➔ Марка ➔ Модель", "#f43f5e")
        pulse = 0.5 + 0.5 * math.sin(self._tick * 0.12)
        bx, by, bw, bh = r.left() + 10, r.top() + 26, r.width() - 20, r.height() - 34
        rects = [
            (QRectF(bx, by, bw * 0.52, bh * 0.62), "#15803d"),
            (QRectF(bx, by + bh * 0.65, bw * 0.52, bh * 0.35), "#22c55e"),
            (QRectF(bx + bw * 0.55, by, bw * 0.45, bh * 0.45), "#0ea5e9"),
            (QRectF(bx + bw * 0.55, by + bh * 0.48, bw * 0.22, bh * 0.52), "#87C800"),
            (QRectF(bx + bw * 0.79, by + bh * 0.48, bw * 0.21, bh * 0.52), "#eab308"),
        ]
        for idx, (rc, c_hex) in enumerate(rects):
            c = QColor(c_hex)
            if idx == 0:
                c = c.lighter(int(100 + 25 * pulse))
            p.setPen(QPen(QColor("#0f172a"), 1.5))
            p.setBrush(c)
            p.drawRoundedRect(rc, 4, 4)

    def _draw_geomap(self, p: QPainter, r: QRectF):
        self._draw_badge(p, r, "🗺 Гео-распределение и рейтинг филиалов", "#14b8a6")
        spots = [(0.28, 0.52), (0.50, 0.42), (0.72, 0.62), (0.42, 0.72)]
        pulse_r = 4 + (self._tick % 25) * 0.45
        for idx, (sx, sy) in enumerate(spots):
            pt = QPointF(r.left() + sx * r.width(), r.top() + 18 + sy * (r.height() - 24))
            c = QColor("#14b8a6" if idx % 2 == 0 else "#87C800")
            c_fade = QColor(c)
            c_fade.setAlpha(max(20, 180 - int(pulse_r * 8)))
            p.setPen(Qt.NoPen)
            p.setBrush(c_fade)
            p.drawEllipse(pt, pulse_r, pulse_r)
            p.setBrush(c)
            p.drawEllipse(pt, 4.5, 4.5)

    def _draw_kpi(self, p: QPainter, r: QRectF):
        self._draw_badge(p, r, "📊 Карточки ключевых метрик (KPI)", "#a855f7")
        step_v = int(1200 + (self._tick % 60) * 15)
        labels = [(f"{step_v:,}", "Факт ГСМ", True), ("-12.4%", "Экономия", True), ("2 363", "Путевых", False)]
        cw = (r.width() - 28) / 3
        for i, (val_s, lbl_s, acc) in enumerate(labels):
            kr = QRectF(r.left() + 8 + i * (cw + 6), r.top() + 30, cw, r.height() - 42)
            p.setPen(QPen(QColor("#87C800" if acc else "#334155"), 1.2))
            p.setBrush(QColor("#1e293b"))
            p.drawRoundedRect(kr, 6, 6)
            p.setPen(QColor("#87C800" if acc else "#f8fafc"))
            p.setFont(QFont("Segoe UI", 9, QFont.Bold))
            p.drawText(QRectF(kr.left(), kr.top() + 8, kr.width(), 20), Qt.AlignCenter, val_s)
            p.setPen(QColor("#94a3b8"))
            p.setFont(QFont("Segoe UI", 7))
            p.drawText(QRectF(kr.left(), kr.bottom() - 20, kr.width(), 16), Qt.AlignCenter, lbl_s)

    def _draw_table(self, p: QPainter, r: QRectF):
        q_str = "🔍 Поиск: КАМАЗ"[: 10 + (self._tick // 8) % 6]
        self._draw_badge(p, r, f"🗂 Таблица  |  {q_str}|", "#64748b")
        ty = r.top() + 28
        for i in range(4):
            row_r = QRectF(r.left() + 10, ty + i * 18, r.width() - 20, 15)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#1e3a2f" if i == 1 else "#1e293b"))
            p.drawRoundedRect(row_r, 3, 3)

    def _draw_smart_text(self, p: QPainter, r: QRectF):
        is_over = ((self._tick // 55) % 2) == 1
        self._draw_badge(p, r, "🧠 Динамический вывод с условием if(...)", "#f59e0b")
        box = QRectF(r.left() + 10, r.top() + 28, r.width() - 20, r.height() - 38)
        p.setPen(QPen(QColor("#ef4444" if is_over else "#87C800"), 1.2))
        p.setBrush(QColor("#1e293b"))
        p.drawRoundedRect(box, 6, 6)
        p.setPen(QColor("#f8fafc"))
        p.setFont(QFont("Segoe UI", 8, QFont.Bold))
        msg = (
            "📊 Группа: Самосвал (Май)\n⚠ Перерасход: +8.4% (+420 л)"
            if is_over
            else "📊 Группа: Рефрижераторы (Июнь)\n✅ Экономия: -12.0% (-1 150 л)"
        )
        p.drawText(box.adjusted(8, 6, -8, -6), Qt.AlignLeft | Qt.AlignVCenter, msg)

    def _draw_combo_full(self, p: QPainter, r: QRectF):
        self._draw_badge(p, r, "⚡ Связка: Срез + Диаграмма + Вывод ЕСЛИ", "#10b981")
        # Срез слева, кольцо справа, текст внизу
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#1e293b"))
        p.drawRoundedRect(QRectF(r.left() + 8, r.top() + 26, 60, 48), 4, 4)
        p.setBrush(QColor("#87C800"))
        p.drawRoundedRect(QRectF(r.left() + 12, r.top() + 30 + ((self._tick // 35) % 2) * 18, 52, 14), 3, 3)

        cx, cy = r.left() + 150, r.top() + 50
        p.setBrush(QColor("#2b7fff"))
        p.drawEllipse(QPointF(cx, cy), 22, 22)
        p.setBrush(QColor("#162032"))
        p.drawEllipse(QPointF(cx, cy), 10, 10)

        p.setBrush(QColor("#1e3a2f"))
        p.drawRoundedRect(QRectF(r.left() + 8, r.bottom() - 24, r.width() - 16, 18), 4, 4)
        p.setPen(QColor("#87C800"))
        p.setFont(QFont("Segoe UI", 7, QFont.Bold))
        p.drawText(QRectF(r.left() + 14, r.bottom() - 24, r.width() - 28, 18), Qt.AlignVCenter, "✅ Вывод синхронизирован со срезом")

    def _draw_layout_doc(self, p: QPainter, r: QRectF):
        self._draw_badge(p, r, "📑 Заголовки, списки и структура раздела", "#10b981")
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#87C800"))
        p.drawRoundedRect(QRectF(r.left() + 10, r.top() + 28, r.width() - 20, 6), 2, 2)
        p.setBrush(QColor("#334155"))
        for i in range(3):
            p.drawRoundedRect(QRectF(r.left() + 16, r.top() + 42 + i * 16, r.width() - 45, 9), 3, 3)


# ============================================================
# Карточка элемента внутри выпадающего меню группы
# ============================================================

class _MenuBlockItemWidget(QFrame):
    """Карточка блока в выпадающем меню. Отслеживает задержку курсора для показа превью."""

    clicked = Signal(str)
    hover_started = Signal(dict)

    def __init__(self, theme, item_meta: dict, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.item_meta = item_meta
        self.accent = item_meta.get("accent", theme.primary)
        self.setCursor(Qt.PointingHandCursor)
        self.setObjectName("menuBlockItem")
        self._apply_style(False)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(5)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(9)

        badge = QLabel(item_meta.get("icon", "▪"))
        badge.setFixedSize(30, 30)
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet(
            f"background: rgba(135, 200, 0, 0.15); border: 1px solid {self.accent}; "
            f"border-radius: 7px; font-size: 14px;"
        )
        top.addWidget(badge)

        txt_col = QVBoxLayout()
        txt_col.setContentsMargins(0, 1, 0, 1)
        txt_col.setSpacing(3)

        lbl_t = QLabel(item_meta["title"])
        lbl_t.setWordWrap(True)
        lbl_t.setStyleSheet(
            f"color: {theme.text_main}; font-size: 12px; font-weight: 700; "
            f"line-height: 1.25; padding-bottom: 1px; border: none; background: transparent;"
        )
        txt_col.addWidget(lbl_t)

        lbl_s = QLabel(item_meta["subtitle"])
        lbl_s.setWordWrap(True)
        lbl_s.setMinimumHeight(28)
        lbl_s.setStyleSheet(
            f"color: {theme.text_muted}; font-size: 10.5px; "
            f"line-height: 1.3; padding-top: 1px; border: none; background: transparent;"
        )
        txt_col.addWidget(lbl_s)

        top.addLayout(txt_col, 1)

        plus_lbl = QLabel("+")
        plus_lbl.setFixedSize(20, 20)
        plus_lbl.setAlignment(Qt.AlignCenter)
        plus_lbl.setStyleSheet(
            f"background: {self.accent}; color: #ffffff; border-radius: 5px; font-size: 12px; font-weight: 700;"
        )
        top.addWidget(plus_lbl)
        lay.addLayout(top)

        presets = item_meta.get("presets") or []
        if presets:
            grid = QGridLayout()
            grid.setContentsMargins(0, 3, 0, 0)
            grid.setHorizontalSpacing(4)
            grid.setVerticalSpacing(4)
            for idx, (p_lbl, p_code) in enumerate(presets):
                btn = QPushButton(p_lbl)
                btn.setCursor(Qt.PointingHandCursor)
                btn.setFixedHeight(22)
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {theme.bg_card};
                        color: {theme.text_main};
                        border: 1px solid {theme.border};
                        border-radius: 4px;
                        padding: 2px 6px;
                        font-size: 10px;
                        font-weight: 600;
                    }}
                    QPushButton:hover {{
                        background: {self.accent};
                        color: #ffffff;
                        border: 1px solid {self.accent};
                    }}
                """)
                btn.clicked.connect(lambda _c=False, code=p_code: self.clicked.emit(code))
                grid.addWidget(btn, idx // 3, idx % 3)
            lay.addLayout(grid)

    def _apply_style(self, hovered: bool):
        t = self.theme
        if hovered:
            self.setStyleSheet(
                f"QFrame#menuBlockItem {{ background: {t.bg_hover}; border: 1px solid {self.accent}; border-radius: 8px; }}"
            )
        else:
            self.setStyleSheet(
                f"QFrame#menuBlockItem {{ background: {t.bg_panel}; border: 1px solid {t.border}; border-radius: 8px; }}"
            )

    def enterEvent(self, event):
        self._apply_style(True)
        self.hover_started.emit(self.item_meta)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._apply_style(False)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.item_meta["key"])
        super().mousePressEvent(event)


# ============================================================
# Выпадающее интерактивное окно группы со встроенным превью
# ============================================================

class _InteractiveGroupPopup(QFrame):
    """
    Всплывающее меню группы со списком блоков слева и интерактивным
    информативным превью (текст + зацикленная анимация холста) в этом же меню.
    """

    block_chosen = Signal(str)

    def __init__(self, theme, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.theme = theme
        self._pending_meta: dict | None = None

        # Таймер задержки наведения на блок внутри меню (550 мс) для раскрытия живого превью
        self._dwell_timer = QTimer(self)
        self._dwell_timer.setSingleShot(True)
        self._dwell_timer.setInterval(550)
        self._dwell_timer.timeout.connect(self._reveal_showcase)

        self.setObjectName("groupMegaPopup")
        self.setStyleSheet(f"""
            QFrame#groupMegaPopup {{
                background: {theme.bg_card};
                border: 1px solid {theme.primary};
                border-radius: 10px;
            }}
        """)

        main_lay = QHBoxLayout(self)
        main_lay.setContentsMargins(12, 12, 12, 12)
        main_lay.setSpacing(12)

        # Левая колонка: карточки блоков группы
        self.left_col = QWidget()
        self.left_col.setFixedWidth(380)
        self.left_col.setStyleSheet("background: transparent;")
        self.items_lay = QVBoxLayout(self.left_col)
        self.items_lay.setContentsMargins(0, 0, 0, 0)
        self.items_lay.setSpacing(7)
        main_lay.addWidget(self.left_col)

        # Правая панель (в том же меню!): Интерактивное превью с зацикленной анимацией
        self.showcase_panel = QFrame()
        self.showcase_panel.setFixedWidth(315)
        self.showcase_panel.setStyleSheet(f"""
            QFrame {{
                background: {theme.bg_panel};
                border: 1px solid {theme.border};
                border-radius: 8px;
            }}
        """)
        sh_lay = QVBoxLayout(self.showcase_panel)
        sh_lay.setContentsMargins(10, 10, 10, 10)
        sh_lay.setSpacing(8)

        self.lbl_sh_badge = QLabel("🎬  ИНТЕРАКТИВНЫЙ ОБЗОР БЛОКА")
        self.lbl_sh_badge.setStyleSheet(
            f"color: {theme.primary}; font-size: 9px; font-weight: 800; letter-spacing: 0.7px; border: none;"
        )
        sh_lay.addWidget(self.lbl_sh_badge)

        self.lbl_sh_title = QLabel("Наведите курсор на блок")
        self.lbl_sh_title.setWordWrap(True)
        self.lbl_sh_title.setStyleSheet(
            f"color: {theme.text_main}; font-size: 13px; font-weight: 700; border: none;"
        )
        sh_lay.addWidget(self.lbl_sh_title)

        self.animator = _LoopedCanvasAnimator(theme, self.showcase_panel)
        sh_lay.addWidget(self.animator, 0, Qt.AlignCenter)

        self.lbl_sh_desc = QLabel("")
        self.lbl_sh_desc.setWordWrap(True)
        self.lbl_sh_desc.setStyleSheet(
            f"color: {theme.text_main}; font-size: 11px; line-height: 1.35; border: none; background: transparent;"
        )
        sh_lay.addWidget(self.lbl_sh_desc)

        self.btn_quick_insert = QPushButton("➕  Добавить этот блок на холст")
        self.btn_quick_insert.setCursor(Qt.PointingHandCursor)
        self.btn_quick_insert.setStyleSheet(f"""
            QPushButton {{
                background: {theme.primary};
                color: {theme.text_inverse};
                border: none;
                border-radius: 6px;
                padding: 7px 10px;
                font-size: 11px;
                font-weight: 700;
            }}
            QPushButton:hover {{
                background: #9ade4f;
            }}
        """)
        self.btn_quick_insert.clicked.connect(self._on_quick_insert_clicked)
        sh_lay.addWidget(self.btn_quick_insert)

        sh_lay.addStretch(1)
        main_lay.addWidget(self.showcase_panel)

    def populate_group(self, group_data: dict):
        while self.items_lay.count():
            it = self.items_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

        hdr = QLabel(f"{group_data['title'].upper()}  ·  УДЕРЖИВАЙТЕ КУРСОР ДЛЯ ПРЕВЬЮ")
        hdr.setStyleSheet(
            f"color: {self.theme.text_muted}; font-size: 9px; font-weight: 700; letter-spacing: 0.5px; padding-bottom: 2px;"
        )
        self.items_lay.addWidget(hdr)

        items = group_data.get("items", [])
        for item_meta in items:
            card = _MenuBlockItemWidget(self.theme, item_meta, self.left_col)
            card.clicked.connect(self._on_card_clicked)
            card.hover_started.connect(self._on_item_hovered)
            self.items_lay.addWidget(card)

        self.items_lay.addStretch(1)

        # Показываем превью первого элемента сразу и обновляем при задержании мыши на любом блоке
        if items:
            self._pending_meta = items[0]
            self._reveal_showcase()

        self.adjustSize()

    def _on_item_hovered(self, meta: dict):
        self._pending_meta = meta
        self._dwell_timer.start()

    def _reveal_showcase(self):
        if not self._pending_meta:
            return
        m = self._pending_meta
        self.lbl_sh_title.setText(f"{m.get('icon', '')}  {m.get('title', '')}")
        self.lbl_sh_desc.setText(m.get("how_it_works", ""))
        self.animator.set_animation_kind(m.get("anim_kind", "chart_cycle"))
        self.showcase_panel.setVisible(True)
        self.adjustSize()

    def _on_quick_insert_clicked(self):
        if self._pending_meta:
            code = self._pending_meta["key"]
            self.close()
            self.block_chosen.emit(code)

    def _on_card_clicked(self, code: str):
        self.close()
        self.block_chosen.emit(code)

    def hideEvent(self, event):
        self._dwell_timer.stop()
        self.animator.stop_animation()
        super().hideEvent(event)


# ============================================================
# Кнопка группы в верхнем ряду с таймером наведения 1 секунда
# ============================================================

class _GroupRibbonButton(QPushButton):
    """Кнопка группы в верхнем ряду: открывает меню при клике или удержании курсора 1 секунду."""

    open_requested = Signal(str, object)

    def __init__(self, theme, group_data: dict, parent=None):
        super().__init__(f"{group_data['title']}  ▾", parent)
        self.theme = theme
        self.group_data = group_data
        self.accent = group_data.get("accent", theme.primary)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(32)

        # Таймер 1000 мс (1 секунда) при наведении мыши
        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(1000)
        self._hover_timer.timeout.connect(self._trigger_open)

        self._apply_style(False)

    def _apply_style(self, active: bool):
        t = self.theme
        if active:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: {t.bg_hover};
                    color: {t.text_main};
                    border: 1px solid {self.accent};
                    border-radius: 7px;
                    padding: 4px 12px;
                    font-size: 12px;
                    font-weight: 700;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: {t.bg_panel};
                    color: {t.text_main};
                    border: 1px solid {t.border};
                    border-radius: 7px;
                    padding: 4px 12px;
                    font-size: 12px;
                    font-weight: 600;
                }}
                QPushButton:hover {{
                    background: {t.bg_hover};
                    border: 1px solid {self.accent};
                }}
            """)

    def enterEvent(self, event):
        self._apply_style(True)
        self._hover_timer.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover_timer.stop()
        self._apply_style(False)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._hover_timer.stop()
            self._trigger_open()
            return
        super().mousePressEvent(event)

    def _trigger_open(self):
        self.open_requested.emit(self.group_data["id"], self)


# ============================================================
# Главная верхняя панель конструктора (BlocksPalette)
# ============================================================

class BlocksPalette(QWidget):
    """
    Горизонтальная адаптивная панель групп BI-элементов для верхнего ряда Конструктора.
    Корректно масштабируется как на 13" ноутбуках, так и на широких мониторах.
    """

    block_requested = Signal(str)

    def __init__(self, theme, block_types: dict[str, str] | None = None, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.block_types = block_types or {}
        self._popup: _InteractiveGroupPopup | None = None
        self.setFixedHeight(42)
        self._build_ui()

    def _build_ui(self):
        t = self.theme
        self.setStyleSheet(f"""
            QWidget {{
                background: {t.bg_card};
                border-bottom: 1px solid {t.border};
            }}
        """)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 4, 10, 4)
        lay.setSpacing(6)

        self.lbl_prefix = QLabel("➕ ДОБАВИТЬ:")
        self.lbl_prefix.setStyleSheet(
            f"color: {t.primary}; font-size: 10px; font-weight: 800; letter-spacing: 0.6px; border: none;"
        )
        lay.addWidget(self.lbl_prefix)

        self._group_buttons: dict[str, _GroupRibbonButton] = {}
        for grp in _GROUPS_CATALOG:
            btn = _GroupRibbonButton(t, grp, self)
            btn.open_requested.connect(self._on_group_open_requested)
            lay.addWidget(btn)
            self._group_buttons[grp["id"]] = btn

        self.hint_lbl = QLabel("💡 Наведите (1 сек) или нажмите")
        self.hint_lbl.setStyleSheet(f"color: {t.text_muted}; font-size: 10px; border: none; padding-left: 4px;")
        lay.addWidget(self.hint_lbl)

        lay.addStretch(1)

    def resizeEvent(self, event):
        # На компактных экранах (13" ноутбуки) скрываем вспомогательную подпись, чтобы кнопки не сжимались
        w = event.size().width()
        if hasattr(self, "hint_lbl"):
            self.hint_lbl.setVisible(w >= 1180)
        if hasattr(self, "lbl_prefix"):
            self.lbl_prefix.setText("➕ ДОБАВИТЬ:" if w >= 980 else "➕")
        super().resizeEvent(event)

    def _on_group_open_requested(self, group_id: str, btn_widget: QWidget):
        grp_data = next((g for g in _GROUPS_CATALOG if g["id"] == group_id), None)
        if not grp_data:
            return

        if self._popup is None:
            self._popup = _InteractiveGroupPopup(self.theme, self)
            self._popup.block_chosen.connect(self.block_requested.emit)

        self._popup.populate_group(grp_data)

        global_pos = btn_widget.mapToGlobal(btn_widget.rect().bottomLeft())
        global_pos.setY(global_pos.y() + 4)

        screen = QApplication.screenAt(global_pos) or QApplication.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
            sz = self._popup.sizeHint()
            if global_pos.x() + sz.width() > avail.right() - 8:
                global_pos.setX(max(avail.left() + 8, avail.right() - sz.width() - 8))
            if global_pos.y() + sz.height() > avail.bottom() - 8:
                global_pos.setY(max(avail.top() + 8, avail.bottom() - sz.height() - 8))

        self._popup.move(global_pos)
        self._popup.show()
        self._popup.raise_()