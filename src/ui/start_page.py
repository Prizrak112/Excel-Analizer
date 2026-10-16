from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor


class StartCard(QFrame):
    """Карточка-кнопка стартовой страницы."""

    clicked = Signal()

    def __init__(self, theme, icon: str, title: str, subtitle: str, parent=None):
        super().__init__(parent)
        self.theme = theme

        self.setObjectName("start_card")
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setMinimumSize(320, 280)
        self.setMaximumWidth(380)

        self._apply_style(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 40, 32, 40)
        layout.setSpacing(0)

        layout.addStretch()

        icon_lbl = QLabel(icon)
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet(
            "font-size: 64px; background: transparent; border: none;"
        )
        layout.addWidget(icon_lbl)

        layout.addSpacing(24)

        title_lbl = QLabel(title)
        title_lbl.setAlignment(Qt.AlignCenter)
        title_lbl.setStyleSheet(f"""
            color: {theme.text_main};
            font-size: 20px;
            font-weight: 700;
            background: transparent;
            border: none;
        """)
        layout.addWidget(title_lbl)

        layout.addSpacing(12)

        sub_lbl = QLabel(subtitle)
        sub_lbl.setAlignment(Qt.AlignCenter)
        sub_lbl.setWordWrap(True)
        sub_lbl.setStyleSheet(f"""
            color: {theme.text_muted};
            font-size: 14px;
            line-height: 1.6;
            background: transparent;
            border: none;
        """)
        layout.addWidget(sub_lbl)

        layout.addStretch()

    def _apply_style(self, hover: bool):
        t = self.theme
        if hover:
            bg = t.bg_panel
            border = t.primary
        else:
            bg = t.bg_card
            border = t.border

        self.setStyleSheet(f"""
            #start_card {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 16px;
            }}
        """)

    def enterEvent(self, event):
        self._apply_style(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._apply_style(False)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class StartPage(QWidget):
    """Стартовая страница с двумя карточками."""

    # Сигналы — что нажали: "editor" / "constructor"
    navigate_to = Signal(str)

    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self._build_ui()

    def _build_ui(self):
        t = self.theme
        # Используем цвет фона приложения, чтобы карточки выделялись объёмом
        self.setStyleSheet(f"background: {t.bg_page};")

        root = QVBoxLayout(self)
        root.setContentsMargins(60, 60, 60, 60)
        root.setSpacing(0)

        root.addStretch(1)

        # ── Логотип и Название ──
        logo_container = QWidget()
        logo_container.setStyleSheet("background: transparent; border: none;")
        logo_lay = QHBoxLayout(logo_container)
        logo_lay.setContentsMargins(0, 0, 0, 0)
        logo_lay.setSpacing(12)
        logo_lay.setAlignment(Qt.AlignCenter)

        icon_label = QLabel("⬡")
        icon_label.setStyleSheet(f"""
            color: {t.primary};
            font-size: 56px;
            font-weight: normal;
            margin-bottom: 8px; /* Визуальная компенсация центрирования */
        """)
        icon_label.setAlignment(Qt.AlignVCenter)

        text_label = QLabel("<b>NEX</b>GRID")
        text_label.setStyleSheet(f"""
            color: {t.text_main};
            font-family: "Century Gothic", "Tw Cen MT", "Segoe UI", sans-serif;
            font-size: 38px;
            letter-spacing: 6px;
        """)
        text_label.setAlignment(Qt.AlignVCenter)

        logo_lay.addWidget(icon_label)
        logo_lay.addWidget(text_label)

        root.addWidget(logo_container)

        root.addSpacing(16)

        # ── Подзаголовок ──
        sub = QLabel(
            "Современный инструмент для анализа данных и публикации HTML-дашбордов.\n"
            "Выберите, с чего начать:"
        )
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet(f"""
            color: {t.text_muted};
            font-size: 15px;
            line-height: 1.6;
            background: transparent;
        """)
        root.addWidget(sub)

        root.addSpacing(60)

        # ── Карточки ──
        cards_row = QHBoxLayout()
        cards_row.setSpacing(32)
        cards_row.setAlignment(Qt.AlignCenter)

        card_editor = StartCard(
            t,
            "📊",
            "Данные",
            "Загрузка XLSX, чистка таблиц,\n"
            "преобразования, сводные, фильтры\n"
            "и генерация Python-скрипта",
        )
        card_editor.clicked.connect(lambda: self.navigate_to.emit("editor"))
        cards_row.addWidget(card_editor)

        card_html = StartCard(
            t,
            "🎨",
            "Отчёт",
            "Сборка дашборда из блоков:\n"
            "KPI, графики, таблицы, текст\n"
            "и публикация в автономный HTML",
        )
        card_html.clicked.connect(lambda: self.navigate_to.emit("constructor"))
        cards_row.addWidget(card_html)

        root.addLayout(cards_row)

        root.addStretch(1)

        # ── Подсказка снизу ──
        hint = QLabel(
            "Ctrl+O — открыть файл или проект   ·   "
            "Ctrl+Shift+O — импорт папки"
        )
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet(f"""
            color: {t.text_muted};
            font-size: 12px;
            letter-spacing: 0.5px;
            background: transparent;
            padding-top: 20px;
        """)
        root.addWidget(hint)

        root.addSpacing(32)

        # ── Копирайт ──
        copyright_lbl = QLabel(
            "Все права на данную программу принадлежат: В. Рагимов\n"
            "По всем вопросам можно обращаться в МТС Линк или на почту"
        )
        copyright_lbl.setAlignment(Qt.AlignCenter)
        copyright_lbl.setStyleSheet(f"""
            color: {t.text_muted};
            font-size: 11px;
            letter-spacing: 0.3px;
            line-height: 1.6;
            background: transparent;
        """)
        root.addWidget(copyright_lbl)