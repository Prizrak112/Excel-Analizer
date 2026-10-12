"""
Диалог rich-text редактирования текстового блока.

Открывается двойным кликом на блоке на холсте
или через ПКМ → «Редактировать текст».

Использование:
    dlg = RichTextDialog(theme, kind="paragraph", initial_html="<p>Текст</p>")
    if dlg.exec() == RichTextDialog.Accepted:
        html = dlg.result_html          # очищенный HTML
        # → писать в config блока

kind: "paragraph" | "list" | "section_title"
"""

import re

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame,
)
from PySide6.QtCore import Qt

from src.ui.rich_text_editor import RichTextEditor


# ============================================================
# Белый список CSS-свойств, которые сохраняем в итоговом HTML.
# Qt к каждому <span>/<p> цепляет font-family, font-size и т.п.,
# а у нас в отчёте свои CSS — оставляем только семантику.
# ============================================================

_KEEP_STYLE_PROPS = {
    "color",
    "background-color",
    "text-align",
    "text-decoration",
    "font-family",
    "font-size",
    "font-weight",
    "font-style",
}


def clean_qt_html(html: str) -> str:
    """Убирает Qt-обёртку и лишние инлайн-стили из HTML."""
    if not html:
        return ""

    # 1) достаём только <body>...</body>
    low = html.lower()
    start = low.find("<body")
    if start != -1:
        gt = html.find(">", start)
        end = low.rfind("</body>")
        if gt != -1 and end != -1:
            html = html[gt + 1:end]

    # 2) чистим style="..." — оставляем только свойства из белого списка
    def _filter_style(match: re.Match) -> str:
        raw = match.group(1)
        parts = []
        for chunk in raw.split(";"):
            if ":" not in chunk:
                continue
            key, _, val = chunk.partition(":")
            key_l = key.strip().lower()
            if key_l in _KEEP_STYLE_PROPS:
                parts.append(f"{key.strip()}:{val.strip()}")
        if not parts:
            return ""
        return 'style="' + "; ".join(parts) + '"'

    return re.sub(r'style="([^"]*)"', _filter_style, html)


# ============================================================
# Заголовки и подсказки по типу блока
# ============================================================

_TITLES = {
    "paragraph":     "Редактировать параграф",
    "list":          "Редактировать список",
    "section_title": "Редактировать заголовок",
}

_HINTS = {
    "paragraph":     "Наберите текст, примените форматирование. Панель сверху — все настройки.",
    "list":          "Используйте кнопку «•» (маркированный список) или «1.» (нумерованный).",
    "section_title": "Введите заголовок. Можно применить форматирование.",
}


# ============================================================
# Диалог
# ============================================================

class RichTextDialog(QDialog):
    """Модальный диалог с rich-text редактором."""

    def __init__(self, theme, kind: str, initial_html: str = "", parent=None):
        super().__init__(parent)
        self.theme = theme
        self.kind = kind
        self._result_html: str = ""

        title = _TITLES.get(kind, "Редактирование текста")
        self.setWindowTitle(title)
        self.setMinimumSize(700, 480)
        self.resize(760, 540)

        self._build_ui(title, initial_html)
        self._apply_style()

    # ---------- Построение ----------

    def _build_ui(self, title: str, initial_html: str):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        # ── Заголовок + подсказка ──
        header = QLabel(title)
        header.setStyleSheet(
            f"color:{self.theme.text_main}; font-size:15px; font-weight:700;"
        )
        root.addWidget(header)

        hint_text = _HINTS.get(self.kind, "")
        if hint_text:
            hint = QLabel(hint_text)
            hint.setWordWrap(True)
            hint.setStyleSheet(
                f"color:{self.theme.text_muted}; font-size:12px;"
            )
            root.addWidget(hint)

        # ── Разделитель ──
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background:{self.theme.border}; border:none;")
        root.addWidget(sep)

        # ── Редактор ──
        self._editor = RichTextEditor(self.theme, min_height=320)
        self._editor.set_html(initial_html or "")
        root.addWidget(self._editor, stretch=1)

        # ── Кнопки ──
        btns = QHBoxLayout()
        btns.setContentsMargins(0, 4, 0, 0)
        btns.setSpacing(8)

        btns.addStretch()

        b_cancel = QPushButton("Отмена")
        b_cancel.setCursor(Qt.PointingHandCursor)
        b_cancel.setStyleSheet(self._btn_style(primary=False))
        b_cancel.clicked.connect(self.reject)
        btns.addWidget(b_cancel)

        b_save = QPushButton("💾  Сохранить")
        b_save.setCursor(Qt.PointingHandCursor)
        b_save.setStyleSheet(self._btn_style(primary=True))
        b_save.clicked.connect(self._on_save)
        btns.addWidget(b_save)

        root.addLayout(btns)

    # ---------- Стили ----------

    def _apply_style(self):
        self.setStyleSheet(
            f"QDialog {{ background:{self.theme.bg_card}; }}"
        )

    def _btn_style(self, primary: bool) -> str:
        t = self.theme
        if primary:
            return f"""
                QPushButton {{
                    background:{t.primary}; color:{t.text_inverse};
                    border:none; border-radius:6px;
                    padding:8px 18px; font-size:13px; font-weight:600;
                }}
                QPushButton:hover {{ background:#9ade4f; }}
            """
        return f"""
            QPushButton {{
                background:{t.bg_panel}; color:{t.text_main};
                border:1px solid {t.border}; border-radius:6px;
                padding:8px 18px; font-size:13px; font-weight:600;
            }}
            QPushButton:hover {{ background:{t.bg_hover}; }}
        """

    # ---------- Сохранение ----------

    def _on_save(self):
        raw = self._editor.to_html()
        self._result_html = clean_qt_html(raw)
        self.accept()

    # ---------- Публичное ----------

    @property
    def result_html(self) -> str:
        """HTML после нажатия «Сохранить»."""
        return self._result_html