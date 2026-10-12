"""Панель свойств блока (правая панель Конструктора)."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QLineEdit, QTextEdit,
    QSpinBox, QCheckBox, QScrollArea, QFrame, QComboBox,
)
from PySide6.QtCore import Qt, Signal

from src.core.block_factory import BLOCK_TYPES


# ============================================================
# Хелпер: чистка Qt-HTML от лишних инлайн-стилей
# ============================================================

# ============================================================
# Хелперы для rich-text — ВЫНЕСЕНЫ в диалог редактирования.
# В инспекторе больше не нужны, поэтому здесь оставлены только
# базовые утилиты для legacy-полей items.
# ============================================================

# Пресеты ширины блока
_WIDTH_PRESETS = [
    ("100% — на всю ширину", 100),
    ("75%", 75),
    ("66% — две трети", 66),
    ("50% — половина", 50),
    ("33% — треть", 33),
    ("25% — четверть", 25),
]


class BlockInspector(QWidget):
    """Показывает поля конфига выбранного блока. Меняет его config."""

    config_changed = Signal(str)  # block_id — config уже обновлён в модели

    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self._block = None
        self._section = None
        self._all_columns: list[str] = []

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
        self._lay.setContentsMargins(16, 16, 16, 16)
        self._lay.setSpacing(8)
        self._lay.addStretch()

        self._scroll.setWidget(self._body)
        outer.addWidget(self._scroll)

        self.show_empty()

    # ---------- Публичное ----------

    def set_dataframe(self, df):
        self._all_columns = list(df.columns) if df is not None else []

    def show_empty(self):
        self._clear()
        self._add_title("Свойства")
        self._add_hint("Выберите блок на холсте или в дереве.")
        self._block = None
        self._section = None

    def show_block(self, block):
        self._block = block
        self._section = None
        self._clear()
        self._add_title(f"Блок: {BLOCK_TYPES.get(block.type, block.type)}")
        cfg = block.config or {}

        # ── Секция РАЗМЕР (для всех, кроме divider) ──
        if block.type != "divider":
            self._section_header("Размер")
            self._field_width(cfg)
            self._field_int("Мин. высота (px, 0 = авто)", "min_height", cfg, default=0, min_val=0)

            self._section_header("Отступы")
            self._field_int("Сверху (px)", "margin_top", cfg, default=0, min_val=0)
            self._field_int("Снизу (px)", "margin_bottom", cfg, default=14, min_val=0)

        # ── Специфичные поля по типу ──
        # ★ Для текстовых блоков редактор убран — правится в диалоге
        # через двойной клик на холсте или ПКМ → «Редактировать текст».
        if block.type == "section_title":
            self._add_hint(
                "✏  Двойной клик на блоке или ПКМ → «Редактировать текст»\n"
                "чтобы изменить заголовок."
            )
        elif block.type == "paragraph":
            self._add_hint(
                "✏  Двойной клик на блоке или ПКМ → «Редактировать текст»\n"
                "чтобы изменить содержимое."
            )
        elif block.type == "list":
            self._add_hint(
                "✏  Двойной клик на блоке или ПКМ → «Редактировать текст»\n"
                "чтобы изменить список."
            )
        elif block.type == "kpi_row":
            self._field_kpi(cfg)
        elif block.type == "data_table":
            self._field_int(
                "Высота окна  (строк)",
                "max_rows",
                cfg,
                default=20,
                min_val=0,
                max_val=1_000_000,
                tooltip=(
                    "Сколько строк видно в блоке за раз.\n"
                    "Остальные — прокручиваются вертикальным скроллом.\n\n"
                    "0 — показать таблицу во всю высоту, без окна."
                ),
            )
            self._add_hint(
                "💡 В окне видны первые N строк — остальные доступны\n"
                "прокруткой внутри блока.\n\n"
                "⚠ В HTML-отчёт попадает максимум 1000 строк. Если\n"
                "нужна вся таблица — смотрите её в Excel."
            )
            self._field_columns(cfg)
        elif block.type == "container":
            self._section_header("Сетка контейнера")
            self._field_container_layout(cfg)
            self._field_int("Отступ между блоками (px)", "gap", cfg, default=14)
        elif block.type == "divider":
            self._add_hint("У этого блока нет настроек.")

    def show_section(self, section):
        self._section = section
        self._block = None
        self._clear()
        self._add_title("Раздел")

        self._add_label("Название")
        e1 = QLineEdit(section.title)
        self._style_input(e1)
        e1.textChanged.connect(lambda v: self._change_section("title", v))
        self._lay.insertWidget(self._lay.count() - 1, e1)

        self._add_label("Иконка")
        e2 = QLineEdit(section.icon)
        e2.setMaxLength(2)
        self._style_input(e2)
        e2.textChanged.connect(lambda v: self._change_section("icon", v))
        self._lay.insertWidget(self._lay.count() - 1, e2)

    # ---------- Изменение ----------

    def _change_block(self, key, value):
        if self._block is None:
            return
        cfg = dict(self._block.config or {})
        cfg[key] = value
        self._block.config = cfg
        self.config_changed.emit(self._block.id)

    def _change_block_multi(self, updates: dict):
        """Записать несколько ключей config за один раз (один сигнал)."""
        if self._block is None:
            return
        cfg = dict(self._block.config or {})
        cfg.update(updates)
        self._block.config = cfg
        self.config_changed.emit(self._block.id)

    def _change_section(self, key, value):
        if self._section is None:
            return
        setattr(self._section, key, value)
        self.config_changed.emit("")

    # ---------- Поля ----------

    def _section_header(self, text):
        lbl = QLabel(f"── {text.upper()} ──")
        lbl.setStyleSheet(
            f"color:{self.theme.text_muted}; font-size:10px; font-weight:700;"
            f"letter-spacing:0.5px; padding-top:10px; padding-bottom:2px;"
            f"background:transparent;"
        )
        self._lay.insertWidget(self._lay.count() - 1, lbl)

    def _clear(self):
        while self._lay.count() > 1:
            it = self._lay.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()

    def _add_title(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color:{self.theme.text_main}; font-size:14px; font-weight:700;"
            f"padding-bottom:6px; background:transparent;"
        )
        self._lay.insertWidget(self._lay.count() - 1, lbl)

    def _add_hint(self, text):
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color:{self.theme.text_muted}; font-size:12px; background:transparent;")
        self._lay.insertWidget(self._lay.count() - 1, lbl)

    def _add_label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color:{self.theme.text_muted}; font-size:11px; font-weight:600;"
            f"padding-top:6px; background:transparent;"
        )
        self._lay.insertWidget(self._lay.count() - 1, lbl)

    def _field_text(self, label, key, cfg):
        self._add_label(label)
        e = QLineEdit(str(cfg.get(key, "")))
        self._style_input(e)
        e.textChanged.connect(lambda v: self._change_block(key, v))
        self._lay.insertWidget(self._lay.count() - 1, e)

    def _field_multiline(self, label, key, cfg):
        """Оставлено для совместимости (плейн-текст)."""
        self._add_label(label)
        e = QTextEdit()
        e.setPlainText(str(cfg.get(key, "")))
        e.setFixedHeight(120)
        self._style_input(e)
        e.textChanged.connect(lambda: self._change_block(key, e.toPlainText()))
        self._lay.insertWidget(self._lay.count() - 1, e)

    # _field_rich — УДАЛЁН.
    # Rich-text редактирование переехало в отдельный диалог
    # (src/ui/rich_text_dialog.py), который открывается двойным
    # кликом по блоку на холсте или через ПКМ → «Редактировать текст».

    def _field_lines(self, label, key, cfg):
        self._add_label(label)
        items = cfg.get(key) or []
        e = QTextEdit()
        e.setPlainText("\n".join(str(x) for x in items))
        e.setFixedHeight(110)
        self._style_input(e)
        def on_ch():
            new = [s.strip() for s in e.toPlainText().split("\n") if s.strip()]
            self._change_block(key, new)
        e.textChanged.connect(on_ch)
        self._lay.insertWidget(self._lay.count() - 1, e)

    def _field_checkbox(self, label, key, cfg):
        cb = QCheckBox(label)
        cb.setChecked(bool(cfg.get(key, False)))
        cb.setStyleSheet(
            f"QCheckBox {{ color:{self.theme.text_main}; font-size:12px;"
            f"padding:4px; background:transparent; }}"
        )
        cb.toggled.connect(lambda v: self._change_block(key, v))
        self._lay.insertWidget(self._lay.count() - 1, cb)

    def _field_int(self, label, key, cfg, default=20, min_val=0,
                   max_val=5000, tooltip: str = ""):
        self._add_label(label)
        sp = QSpinBox()
        sp.setRange(min_val, max_val)
        sp.setValue(int(cfg.get(key, default)))
        if tooltip:
            sp.setToolTip(tooltip)
        sp.setSingleStep(1)
        self._style_input(sp)
        sp.valueChanged.connect(lambda v: self._change_block(key, v))
        self._lay.insertWidget(self._lay.count() - 1, sp)

    def _field_width(self, cfg):
        self._add_label("Ширина блока")
        cb = QComboBox()
        for label, value in _WIDTH_PRESETS:
            cb.addItem(label, value)
        current = int(cfg.get("width", 100))
        idx = 0
        for i, (_, v) in enumerate(_WIDTH_PRESETS):
            if v == current:
                idx = i
                break
        cb.setCurrentIndex(idx)
        self._style_input(cb)
        cb.currentIndexChanged.connect(
            lambda i: self._change_block("width", _WIDTH_PRESETS[i][1])
        )
        self._lay.insertWidget(self._lay.count() - 1, cb)

    def _field_container_layout(self, cfg):
        self._add_label("Расположение")
        cb = QComboBox()
        cb.addItem("Горизонтально (row)", "row")
        cb.addItem("Вертикально (column)", "column")
        current = cfg.get("layout", "row")
        cb.setCurrentIndex(0 if current == "row" else 1)
        self._style_input(cb)
        cb.currentIndexChanged.connect(
            lambda i: self._change_block("layout", "row" if i == 0 else "column")
        )
        self._lay.insertWidget(self._lay.count() - 1, cb)

    def _field_kpi(self, cfg):
        self._add_label("Карточки  ·  Метка [TAB] Значение  ·  «!» — зелёный акцент")
        cards = cfg.get("cards") or []
        text = "\n".join(
            f"{c.get('label','')}\t{c.get('value','')}{'  !' if c.get('accent') else ''}"
            for c in cards
        )
        e = QTextEdit()
        e.setPlainText(text)
        e.setFixedHeight(140)
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
        self._add_label("Колонки")
        selected = cfg.get("visible_columns")
        if not self._all_columns:
            self._add_hint("Сначала загрузите Excel-файл.")
            return
        for col in self._all_columns:
            cb = QCheckBox(str(col))
            cb.setChecked(True if selected is None else (col in selected))
            cb.setStyleSheet(
                f"QCheckBox {{ color:{self.theme.text_main}; font-size:12px;"
                f"padding:3px; background:transparent; }}"
            )
            cb.toggled.connect(lambda v, c=col: self._on_col_toggle(c, v))
            self._lay.insertWidget(self._lay.count() - 1, cb)

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
            f"border:1px solid {t.border}; border-radius:6px;"
            f"padding:6px 8px; font-size:12px;"
        )


# Модуль-хелперы _html_esc / _html_to_items УДАЛЕНЫ.
# Rich-text редактирование переехало в диалог
# (src/ui/rich_text_dialog.py), и там они снова понадобятся —
# но уже в контексте диалога, а не инспектора.