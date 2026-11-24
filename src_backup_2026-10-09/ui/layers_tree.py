"""Дерево слоёв (левая панель Конструктора)."""

from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QFrame
from PySide6.QtCore import Qt, Signal


_ICONS = {
    "section_title": "📑",
    "paragraph":     "¶",
    "list":          "☰",
    "divider":       "─",
    "kpi_row":       "🔢",
    "data_table":    "▦",
}


class LayersTree(QTreeWidget):
    block_selected = Signal(str)
    section_selected = Signal(str)

    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.setHeaderHidden(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setIndentation(14)
        self._apply_style()
        self.itemClicked.connect(self._on_item_clicked)

    def _apply_style(self):
        t = self.theme
        self.setStyleSheet(f"""
            QTreeWidget {{
                background: {t.bg_card};
                border: none;
                color: {t.text_main};
                outline: none;
                padding: 8px 6px;
                font-size: 13px;
            }}
            QTreeWidget::item {{
                padding: 6px 8px;
                border-radius: 6px;
                min-height: 22px;
            }}
            QTreeWidget::item:selected {{
                background: {t.primary}33;
                color: {t.text_main};
            }}
            QTreeWidget::item:hover {{
                background: {t.bg_hover};
            }}
        """)

    def rebuild(self, report):
        self.blockSignals(True)
        self.clear()
        for section in report.sections:
            top = QTreeWidgetItem()
            top.setText(0, f"{section.icon}  {section.title}")
            top.setData(0, Qt.UserRole, ("section", section.id))
            f = top.font(0)
            f.setBold(True)
            top.setFont(0, f)
            self.addTopLevelItem(top)

            for spec in section.blocks:
                child = QTreeWidgetItem()
                icon = _ICONS.get(spec.type, "?")
                child.setText(0, f"{icon}  {_short_title(spec)}")
                child.setData(0, Qt.UserRole, ("block", spec.id))
                top.addChild(child)

            top.setExpanded(True)
        self.blockSignals(False)

    def select_block(self, block_id: str):
        self.blockSignals(True)
        for i in range(self.topLevelItemCount()):
            top = self.topLevelItem(i)
            for j in range(top.childCount()):
                ch = top.child(j)
                data = ch.data(0, Qt.UserRole)
                if data and data[1] == block_id:
                    self.setCurrentItem(ch)
                    self.blockSignals(False)
                    return
        self.blockSignals(False)

    def _on_item_clicked(self, item, _col):
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        kind, ident = data
        if kind == "block":
            self.block_selected.emit(ident)
        else:
            self.section_selected.emit(ident)


def _short_title(spec) -> str:
    cfg = spec.config or {}
    if spec.type == "paragraph":
        t = (cfg.get("text") or "").strip().replace("\n", " ")
        return (t[:28] + "…") if len(t) > 28 else (t or "Параграф")
    if spec.type == "section_title":
        return cfg.get("title", "Заголовок") or "Заголовок"
    return {
        "data_table": "Таблица",
        "kpi_row":    "KPI",
        "list":       "Список",
        "divider":    "Разделитель",
    }.get(spec.type, spec.type)