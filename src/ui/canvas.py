"""Холст Конструктора — светлый"""

from PySide6.QtWidgets import (
    QScrollArea, QWidget, QVBoxLayout, QFrame, QLabel, QApplication,
)
from PySide6.QtCore import Qt, Signal

from src.ui.block_widgets import make_block_widget, BlockWidget


class Canvas(QScrollArea):
    """Холст блоков. Поддерживает drag-n-drop, слияние, resize и контекстное меню."""

    block_clicked = Signal(str)
    section_clicked = Signal(str)
    block_moved = Signal(str, str, int)             # block_id, target_section_id, new_index
    block_merge_requested = Signal(str, str)        # source_id, target_id
    block_resized = Signal(str, int, int)           # block_id, width_pct, min_height_px
    empty_clicked = Signal()

    # Контекстное меню
    block_delete_requested = Signal(str)
    block_duplicate_requested = Signal(str)
    block_move_up_requested = Signal(str)
    block_move_down_requested = Signal(str)

    # ★ Редактирование текста (двойной клик / ПКМ на текстовом блоке)
    block_edit_text_requested = Signal(str)         # block_id

    # ★ Инлайн-редактирование на холсте (для текстовых блоков)
    block_content_changed = Signal(str, str)        # block_id, html
    block_focus_in = Signal(str)                    # block_id
    block_focus_out = Signal(str)                   # block_id

    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self._widgets: dict[str, BlockWidget] = {}
        self._selected_id: str | None = None
        self._positions: dict[str, tuple[str, int]] = {}
        self._drop_target_id: str | None = None

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setStyleSheet("QScrollArea { background:#e8e8ea; border:none; }")
        self.setAcceptDrops(True)

        self._inner = QWidget()
        self._inner.setStyleSheet("background:#e8e8ea;")
        self._inner.setAcceptDrops(True)
        self._layout = QVBoxLayout(self._inner)
        self._layout.setContentsMargins(80, 40, 80, 40)
        self._layout.setSpacing(14)
        self._layout.setAlignment(Qt.AlignTop)   # ★ прижать к верху
        self.setWidget(self._inner)

    def rebuild(self, report, dataframe=None):
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._widgets.clear()
        self._positions.clear()

        if not report.sections:
            hint = QLabel("Кликните по холсту, чтобы создать раздел")
            hint.setAlignment(Qt.AlignCenter)
            hint.setStyleSheet("color:#999; font-size:14px; padding:60px; background:transparent;")
            self._layout.addWidget(hint)
            self._layout.addStretch()
            return

        for section in report.sections:
            sec_w = make_block_widget(
                "section_title",
                f"__section__{section.id}",
                {"title": f"{section.icon} {section.title}".strip()},
                dataframe,
                self._inner,
                self.theme,
            )
            sec_w.clicked.connect(self._on_section_widget_clicked)
            # ★ Прокидываем сигналы контекстного меню заголовка раздела —
            #   раньше был подключён только `clicked`, а ПКМ-«Удалить блок»
            #   уходил в пустоту.
            sec_w.delete_requested.connect(self.block_delete_requested.emit)
            sec_w.duplicate_requested.connect(self.block_duplicate_requested.emit)
            sec_w.move_up_requested.connect(self.block_move_up_requested.emit)
            sec_w.move_down_requested.connect(self.block_move_down_requested.emit)
            sec_w.edit_text_requested.connect(self.block_edit_text_requested.emit)
            self._widgets[f"__section__{section.id}"] = sec_w
            self._positions[f"__section__{section.id}"] = (section.id, -1)
            self._layout.addWidget(sec_w)

            for i, spec in enumerate(section.blocks):
                self._add_block_widget(spec, section.id, i, dataframe)

        # ★ Прижимаем всё к верху — иначе одиночные виджеты растягиваются
        self._layout.addStretch()
        self._layout.setAlignment(Qt.AlignTop)

        if self._selected_id and self._selected_id in self._widgets:
            self._widgets[self._selected_id].set_selected(True)

    def _add_block_widget(self, spec, section_id, index, dataframe):
        w = make_block_widget(
            spec.type, spec.id, spec.config, dataframe, self._inner, self.theme,
        )
        w.clicked.connect(self._on_block_widget_clicked)
        w.resized.connect(self.block_resized.emit)
        w.delete_requested.connect(self.block_delete_requested.emit)
        w.duplicate_requested.connect(self.block_duplicate_requested.emit)
        w.move_up_requested.connect(self.block_move_up_requested.emit)
        w.move_down_requested.connect(self.block_move_down_requested.emit)
        # ★ Двойной клик / ПКМ «Редактировать текст» → проброс наверх
        w.edit_text_requested.connect(self.block_edit_text_requested.emit)

        # ★ Инлайн-редактирование — только у текстовых блоков.
        # Проверяем через hasattr, потому что у KPI / таблицы / divider
        # этих сигналов нет.
        if hasattr(w, "content_changed"):
            w.content_changed.connect(self.block_content_changed.emit)
            w.focus_in.connect(self.block_focus_in.emit)
            w.focus_out.connect(self.block_focus_out.emit)

        self._widgets[spec.id] = w
        self._positions[spec.id] = (section_id, index)
        self._layout.addWidget(w)

        # ★ Дивайдер всегда 18px
        if spec.type == "divider":
            w.setFixedHeight(18)

        # ★ min_height из config
        min_h = int(spec.config.get("min_height", 0))
        if min_h > 0:
            w.setMinimumHeight(min_h)
        else:
            w.setMinimumHeight(0)
                # ★ Ширина из config
        width_pct = int(spec.config.get("width", 100))
        if width_pct < 100:
            parent_w = self._inner.width() or 800
            available = max(200, parent_w - 160)
            target_w = int(available * width_pct / 100)
            w.setMaximumWidth(target_w)
        else:
            w.setMaximumWidth(16777215)
            
    def select_block(self, block_id: str | None):
        if self._selected_id and self._selected_id in self._widgets:
            self._widgets[self._selected_id].set_selected(False)
        self._selected_id = block_id
        if block_id and block_id in self._widgets:
            w = self._widgets[block_id]
            w.set_selected(True)
            self.ensureWidgetVisible(w, 20, 20)

    # ---------- Клики ----------

    def _on_block_widget_clicked(self, block_id: str):
        self.block_clicked.emit(block_id)

    def _on_section_widget_clicked(self, widget_id: str):
        if widget_id.startswith("__section__"):
            self.section_clicked.emit(widget_id[len("__section__"):])

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pos = event.position().toPoint()
            widget_under = self._widget_at(pos)
            if widget_under is None:
                # ★ Снять фокус со всех QTextEdit на холсте:
                # при клике по пустому месту редактор должен «закрыться».
                fw = QApplication.focusWidget()
                if fw is not None:
                    fw.clearFocus()
                self.empty_clicked.emit()
        super().mousePressEvent(event)

    # ---------- Drag-n-drop ----------

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-ea-block"):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if not event.mimeData().hasFormat("application/x-ea-block"):
            return super().dragMoveEvent(event)

        pos = event.position().toPoint()
        widget_under = self._widget_at(pos)
        source_id = bytes(event.mimeData().data("application/x-ea-block")).decode("utf-8")
        if widget_under and widget_under.block_id != source_id:
            if not widget_under.block_id.startswith("__section__"):
                self._set_drop_highlight(widget_under.block_id)
                event.acceptProposedAction()
                return

        self._set_drop_highlight(None)
        event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._set_drop_highlight(None)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        if not event.mimeData().hasFormat("application/x-ea-block"):
            return super().dropEvent(event)

        block_id = bytes(event.mimeData().data("application/x-ea-block")).decode("utf-8")
        pos = event.position().toPoint()

        widget_under = self._widget_at(pos)
        if widget_under and widget_under.block_id != block_id \
                and not widget_under.block_id.startswith("__section__"):
            self._set_drop_highlight(None)
            event.acceptProposedAction()
            self.block_merge_requested.emit(block_id, widget_under.block_id)
            return

        target = self._find_drop_target(pos)
        self._set_drop_highlight(None)
        if target is None:
            return
        target_section_id, new_index = target
        event.acceptProposedAction()
        self.block_moved.emit(block_id, target_section_id, new_index)

    # ---------- Поиск цели ----------

    def _widget_at(self, pos) -> BlockWidget | None:
        inner_pos = self._inner.mapFrom(self.viewport(), pos)
        for wid, w in self._widgets.items():
            if w is None:
                continue
            geo = w.geometry()
            if geo.contains(inner_pos):
                return w
        return None

    def _find_drop_target(self, pos) -> tuple[str, int] | None:
        inner_pos = self._inner.mapFrom(self.viewport(), pos)

        section_widgets = []
        for wid, w in self._widgets.items():
            sec_id, idx = self._positions.get(wid, (None, -1))
            if sec_id is None:
                continue
            if idx == -1:
                section_widgets.append((sec_id, w))

        if not section_widgets:
            return None

        current_section_id = None
        current_section_top = None
        for sec_id, w in section_widgets:
            y = w.geometry().top()
            if y <= inner_pos.y():
                if current_section_top is None or y > current_section_top:
                    current_section_top = y
                    current_section_id = sec_id

        if current_section_id is None:
            current_section_id = section_widgets[0][0]

        blocks_in_section = [
            (wid, w) for wid, w in self._widgets.items()
            if self._positions.get(wid, (None, -1))[0] == current_section_id
            and self._positions.get(wid, (None, -1))[1] != -1
        ]
        blocks_in_section.sort(key=lambda x: x[1].geometry().top())

        new_index = 0
        for _, w in blocks_in_section:
            mid_y = w.geometry().top() + w.geometry().height() // 2
            if inner_pos.y() >= mid_y:
                new_index += 1
            else:
                break

        return (current_section_id, new_index)

    # ---------- Подсветка ----------

    def _set_drop_highlight(self, target_block_id: str | None):
        if self._drop_target_id == target_block_id:
            return
        for wid, w in self._widgets.items():
            w.set_drop_highlight(False)
        self._drop_target_id = target_block_id
        if target_block_id and target_block_id in self._widgets:
            self._widgets[target_block_id].set_drop_highlight(True)