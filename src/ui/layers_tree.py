"""
Дерево слоёв и используемых блоков отчёта (вторая панель Конструктора).
Отображает разделы и блоки с цветными графическими бейджами и понятными названиями,
полностью соответствующими палитре BI-элементов.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem, QFrame,
)
from PySide6.QtCore import Qt, Signal, QSize, QRectF
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont, QPen


# Единый справочник: технический тип -> (Понятное название, символ иконки, цвет бейджа)
_LAYER_META: dict[str, tuple[str, str, str]] = {
    "plotly_chart":     ("Интерактивный график",   "📈", "#87C800"),
    "dashboard_filter": ("Фильтр (Срез данных)",   "🎯", "#2b7fff"),
    "kpi_row":          ("KPI-карточки (Метрики)", "📊", "#a855f7"),
    "pivot_matrix":     ("Сводная матрица",        "⊞",  "#0ea5e9"),
    "decomposition":    ("Дерево декомпозиции",    "🌳", "#f43f5e"),
    "geo_map":          ("Гео-карта объектов",     "🗺", "#14b8a6"),
    "data_table":       ("Таблица данных",         "🗂", "#64748b"),
    "paragraph":        ("Аналитический текст",    "📝", "#f59e0b"),
    "section_title":    ("Заголовок раздела",      "📑", "#10b981"),
    "list":             ("Маркированный список",   "📋", "#ec4899"),
    "divider":          ("Разделитель",            "➖", "#94a3b8"),
    "container":        ("Группа блоков",          "🗃", "#6366f1"),
}

# Уточнённые иконки и названия для разных подтипов графиков
_CHART_SUBTYPE_META: dict[str, tuple[str, str]] = {
    "bar":            ("Столбчатая диаграмма",   "📊"),
    "bar_stacked":    ("Накопительная гистограмма", "🧱"),
    "bar_cumulative": ("Накопительная (итог)",   "📐"),
    "bar_stacked_100":("100% Накопительная",     "💯"),
    "hbar":           ("Горизонтальная диаграмма", "📈"),
    "line":           ("Линейный график",        "📉"),
    "donut":          ("Кольцевая диаграмма",    "🍩"),
    "pie":            ("Круговая диаграмма",     "🥧"),
    "area":           ("Площадной график",       "⛰"),
    "scatter":        ("Точечная диаграмма",     "🔵"),
    "histogram":      ("Гистограмма",            "📶"),
    "box":            ("Ящик с усами",           "📦"),
    "funnel":         ("Воронка",                "🌪"),
}


def _make_badge_icon(symbol: str, hex_color: str, size: int = 22) -> QIcon:
    """Рисует аккуратную цветную иконку-бейдж для элемента списка слоёв."""
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)

    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)

    base_color = QColor(hex_color)
    bg_color = QColor(base_color)
    bg_color.setAlpha(45)

    pen = QPen(base_color)
    pen.setWidthF(1.2)
    painter.setPen(pen)
    painter.setBrush(bg_color)
    painter.drawRoundedRect(QRectF(1.0, 1.0, size - 2.0, size - 2.0), 5.0, 5.0)

    font = QFont("Segoe UI Emoji", 10)
    painter.setFont(font)
    painter.setPen(QColor("#ffffff"))
    painter.drawText(QRectF(0, 0, size, size), Qt.AlignCenter, symbol)
    painter.end()

    return QIcon(pix)


class LayersTree(QWidget):
    """Панель структуры отчёта (Разделы и используемые BI-блоки)."""

    block_selected = Signal(str)
    section_selected = Signal(str)

    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self._icon_cache: dict[tuple[str, str], QIcon] = {}
        self.setMinimumWidth(185)
        self._build_ui()

    def _get_badge(self, symbol: str, color_hex: str) -> QIcon:
        key = (symbol, color_hex)
        if key not in self._icon_cache:
            self._icon_cache[key] = _make_badge_icon(symbol, color_hex)
        return self._icon_cache[key]

    def _build_ui(self):
        t = self.theme
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QLabel("🗂  СТРУКТУРА ОТЧЁТА")
        header.setStyleSheet(f"""
            color: {t.primary};
            font-size: 10px;
            font-weight: 800;
            letter-spacing: 1.0px;
            background: {t.bg_card};
            padding: 12px 12px 8px 12px;
            border-bottom: 1px solid {t.border};
        """)
        root.addWidget(header)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setFrameShape(QFrame.NoFrame)
        self.tree.setIconSize(QSize(22, 22))
        self.tree.setIndentation(14)
        self.tree.setAnimated(True)
        self.tree.setStyleSheet(f"""
            QTreeWidget {{
                background: {t.bg_card};
                color: {t.text_main};
                border: none;
                outline: none;
                padding: 6px 4px;
                font-size: 12px;
            }}
            QTreeWidget::item {{
                padding: 5px 6px;
                border-radius: 6px;
                margin: 1px 2px;
            }}
            QTreeWidget::item:hover {{
                background: {t.bg_hover};
            }}
            QTreeWidget::item:selected {{
                background: {t.primary_hover};
                color: {t.text_main};
                font-weight: 600;
            }}
        """)
        self.tree.itemClicked.connect(self._on_item_clicked)
        root.addWidget(self.tree, 1)

    def _format_block_label_and_icon(self, block) -> tuple[str, QIcon]:
        b_type = block.get("type", "") if isinstance(block, dict) else getattr(block, "type", "")
        b_cfg = (block.get("config") if isinstance(block, dict) else getattr(block, "config", None)) or {}

        base_name, symbol, color_hex = _LAYER_META.get(
            b_type, ("Блок отчёта", "▪", "#87C800")
        )

        if b_type == "plotly_chart":
            ch_type = str(b_cfg.get("chart_type", "bar") or "bar")
            sub_name, sub_sym = _CHART_SUBTYPE_META.get(ch_type, (base_name, symbol))
            symbol = sub_sym
            custom_title = str(b_cfg.get("title", "") or "").strip()
            if custom_title and custom_title not in ("График данных", sub_name):
                label = f"{sub_name}: {custom_title}"
            else:
                label = sub_name

        elif b_type == "dashboard_filter":
            f_col = str(b_cfg.get("filter_col", "") or "").strip()
            f_title = str(b_cfg.get("title", "") or "").strip()
            if f_col:
                label = f"{base_name}: {f_col}"
            elif f_title and f_title != "Фильтр":
                label = f"{base_name}: {f_title}"
            else:
                label = base_name

        elif b_type == "container":
            children = b_cfg.get("children") or []
            label = f"{base_name} ({len(children)})"

        elif b_type in ("pivot_matrix", "decomposition", "geo_map", "section_title"):
            custom_title = str(b_cfg.get("title", "") or "").strip()
            if custom_title and custom_title != base_name:
                label = f"{base_name}: {custom_title}"
            else:
                label = base_name

        else:
            label = base_name

        if len(label) > 34:
            label = label[:33] + "…"

        return label, self._get_badge(symbol, color_hex)

    def rebuild(self, report):
        self.tree.blockSignals(True)
        self.tree.clear()

        if report is not None and hasattr(report, "sections"):
            for section in report.sections:
                sec_icon_str = getattr(section, "icon", "📊") or "📊"
                sec_title = getattr(section, "title", "Раздел") or "Раздел"

                sec_item = QTreeWidgetItem([f"{sec_icon_str}  {sec_title}"])
                sec_item.setData(0, Qt.UserRole, ("section", section.id))
                font = sec_item.font(0)
                font.setBold(True)
                sec_item.setFont(0, font)
                self.tree.addTopLevelItem(sec_item)

                for block in getattr(section, "blocks", []):
                    b_id = block.get("id", "") if isinstance(block, dict) else getattr(block, "id", "")
                    b_type = block.get("type", "") if isinstance(block, dict) else getattr(block, "type", "")
                    b_cfg = (block.get("config") if isinstance(block, dict) else getattr(block, "config", None)) or {}

                    lbl, icon = self._format_block_label_and_icon(block)
                    blk_item = QTreeWidgetItem([lbl])
                    blk_item.setIcon(0, icon)
                    blk_item.setData(0, Qt.UserRole, ("block", b_id))
                    blk_item.setToolTip(0, lbl)
                    sec_item.addChild(blk_item)

                    # Если это контейнер — показываем вложенные блоки внутри него
                    if b_type == "container":
                        for child in (b_cfg.get("children") or []):
                            c_id = child.get("id", "") if isinstance(child, dict) else getattr(child, "id", "")
                            c_lbl, c_icon = self._format_block_label_and_icon(child)
                            ch_item = QTreeWidgetItem([c_lbl])
                            ch_item.setIcon(0, c_icon)
                            ch_item.setData(0, Qt.UserRole, ("block", c_id))
                            ch_item.setToolTip(0, c_lbl)
                            blk_item.addChild(ch_item)
                        blk_item.setExpanded(True)

                sec_item.setExpanded(True)

        self.tree.blockSignals(False)

    def select_block(self, block_id: str | None):
        self.tree.blockSignals(True)
        self.tree.clearSelection()
        if block_id:
            it = self._find_item_by_role("block", block_id)
            if it is not None:
                it.setSelected(True)
                self.tree.scrollToItem(it)
        self.tree.blockSignals(False)

    def select_section(self, section_id: str | None):
        self.tree.blockSignals(True)
        self.tree.clearSelection()
        if section_id:
            it = self._find_item_by_role("section", section_id)
            if it is not None:
                it.setSelected(True)
                self.tree.scrollToItem(it)
        self.tree.blockSignals(False)

    def _find_item_by_role(self, kind: str, target_id: str) -> QTreeWidgetItem | None:
        def _walk(item: QTreeWidgetItem) -> QTreeWidgetItem | None:
            data = item.data(0, Qt.UserRole)
            if isinstance(data, tuple) and len(data) == 2 and data[0] == kind and data[1] == target_id:
                return item
            for i in range(item.childCount()):
                found = _walk(item.child(i))
                if found is not None:
                    return found
            return None

        for i in range(self.tree.topLevelItemCount()):
            res = _walk(self.tree.topLevelItem(i))
            if res is not None:
                return res
        return None

    def _on_item_clicked(self, item: QTreeWidgetItem, _col: int):
        data = item.data(0, Qt.UserRole)
        if not isinstance(data, tuple) or len(data) != 2:
            return
        kind, obj_id = data
        if kind == "section":
            self.section_selected.emit(obj_id)
        elif kind == "block":
            self.block_selected.emit(obj_id)