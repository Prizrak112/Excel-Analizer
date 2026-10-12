"""
Палитра блоков — левая панель Конструктора.
Показывает список доступных типов блоков в виде плиток.
Клик по плитке → сигнал block_requested(block_type).
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QFrame,
)
from PySide6.QtCore import Qt, Signal


# Иконки — те же, что в layers_tree.py, чтобы стиль был единый.
# Если добавишь новый блок в BLOCK_TYPES — добавь иконку сюда.
_ICONS = {
    "section_title": "📑",
    "paragraph":     "¶",
    "list":          "☰",
    "divider":       "─",
    "kpi_row":       "🔢",
    "data_table":    "▦",
}


class BlocksPalette(QWidget):
    """Левая панель с плитками блоков. Клик = добавить блок."""

    block_requested = Signal(str)   # block_type

    def __init__(self, theme, block_types: dict[str, str], parent=None):
        """
        theme — тема приложения.
        block_types — словарь {tech_name: human_name} (передаём BLOCK_TYPES
                       из block_factory, чтобы палитра не хардкодила список).
        """
        super().__init__(parent)
        self.theme = theme
        self.block_types = block_types
        self.setMinimumWidth(150)

        self._build_ui()

    def _build_ui(self):
        t = self.theme

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Заголовок панели ──
        header = QLabel("🧱  БЛОКИ")
        header.setStyleSheet(f"""
            color: {t.text_muted};
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 1.2px;
            background: {t.bg_card};
            padding: 12px 14px 8px 14px;
            border-bottom: 1px solid {t.border};
        """)
        root.addWidget(header)

        # ── Скролл со списком плиток ──
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                background: {t.bg_card};
                border: none;
            }}
        """)

        inner = QWidget()
        inner.setStyleSheet(f"background: {t.bg_card};")
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(6)

        for tech_name, human_name in self.block_types.items():
            lay.addWidget(self._make_tile(tech_name, human_name))

        lay.addStretch()
        scroll.setWidget(inner)
        root.addWidget(scroll, stretch=1)

    def _make_tile(self, tech_name: str, human_name: str) -> QPushButton:
        t = self.theme
        icon = _ICONS.get(tech_name, "▪")

        btn = QPushButton(f"  {icon}   {human_name}")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setToolTip(f"Добавить блок «{human_name}»")
        btn.setMinimumHeight(36)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {t.bg_panel};
                color: {t.text_main};
                border: 1px solid {t.border};
                border-radius: 6px;
                padding: 8px 10px;
                text-align: left;
                font-size: 12px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background: {t.bg_hover};
                border: 1px solid {t.primary};
                color: {t.primary};
            }}
            QPushButton:pressed {{
                background: {t.primary_hover};
            }}
        """)
        btn.clicked.connect(
            lambda _checked=False, tn=tech_name: self.block_requested.emit(tn)
        )
        return btn