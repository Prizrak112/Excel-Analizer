"""
Стартовая страница приложения.
Две большие карточки-кнопки: Редактор / Конструктор.
"""

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
        self.setMinimumSize(300, 280)
        self.setMaximumWidth(380)

        self._apply_style(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 32, 28, 32)
        layout.setSpacing(0)

        layout.addStretch()

        icon_lbl = QLabel(icon)
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet(
            "font-size: 64px; background: transparent; border: none;"
        )
        layout.addWidget(icon_lbl)

        layout.addSpacing(20)

        title_lbl = QLabel(title)
        title_lbl.setAlignment(Qt.AlignCenter)
        title_lbl.setStyleSheet(f"""
            color: {theme.text_main};
            font-size: 19px;
            font-weight: 700;
            background: transparent;
            border: none;
        """)
        layout.addWidget(title_lbl)

        layout.addSpacing(10)

        sub_lbl = QLabel(subtitle)
        sub_lbl.setAlignment(Qt.AlignCenter)
        sub_lbl.setWordWrap(True)
        sub_lbl.setStyleSheet(f"""
            color: {theme.text_muted};
            font-size: 13px;
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
                border-radius: 14px;
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
        self.setStyleSheet(f"background: {t.bg_card};")

        root = QVBoxLayout(self)
        root.setContentsMargins(60, 60, 60, 60)
        root.setSpacing(0)

        root.addStretch(1)

        # ── Приветствие ──
        hello = QLabel("Добро пожаловать")
        hello.setAlignment(Qt.AlignCenter)
        hello.setStyleSheet(f"""
            color: {t.text_main};
            font-size: 32px;
            font-weight: 700;
            background: transparent;
        """)
        root.addWidget(hello)

        root.addSpacing(10)

        sub = QLabel(
            "Excel Analyzer — конструктор HTML-отчётов с редактором Excel-файлов.\n"
            "Выберите, с чего начать:"
        )
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet(f"""
            color: {t.text_muted};
            font-size: 13px;
            line-height: 1.6;
            background: transparent;
        """)
        root.addWidget(sub)

        root.addSpacing(50)

        # ── Карточки ──
        cards_row = QHBoxLayout()
        cards_row.setSpacing(28)
        cards_row.setAlignment(Qt.AlignCenter)

        card_editor = StartCard(
            t,
            "📊",
            "Редактор",
            "Загрузка XLSX, чистка данных,\n"
            "преобразования, фильтры, сортировка\n"
            "и просмотр Python-кода обработки",
        )
        card_editor.clicked.connect(lambda: self.navigate_to.emit("editor"))
        cards_row.addWidget(card_editor)

        card_html = StartCard(
            t,
            "🎨",
            "Конструктор",
            "Сборка HTML-отчёта из блоков:\n"
            "KPI, таблицы, текст\n"
            "с живым предпросмотром в браузере",
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
            font-size: 11px;
            letter-spacing: 0.3px;
            background: transparent;
            padding-top: 20px;
        """)
        root.addWidget(hint)

        root.addSpacing(28)

        # ── Копирайт ──
        copyright_lbl = QLabel(
            "Все права на данную программу принадлежат: Рагимов В\n"
            "По всем вопросам, можно обращаться в МТС Линк или на почту"
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