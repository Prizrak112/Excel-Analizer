"""Холст Конструктора — Страница отчёта с жесткими полями и свободным позиционированием блоков."""

from PySide6.QtWidgets import (
    QScrollArea, QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QApplication,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QColor, QPen

from src.ui.block_widgets import make_block_widget, BlockWidget


class _PageSheet(QFrame):
    """Лист страницы с визуальной сеткой и жесткими полями (Page Margins)."""

    PAGE_MARGIN_X = 44
    PAGE_MARGIN_Y = 36

    def __init__(self, parent=None):
        super().__init__(parent)
        self.show_grid = True
        self.setStyleSheet(
            "_PageSheet { background: #ffffff; border: 1px solid #cfd4dc; border-radius: 10px; }"
        )

    def available_content_width(self) -> int:
        return max(240, self.width() - self.PAGE_MARGIN_X * 2)

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.show_grid:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)

        left_m = self.PAGE_MARGIN_X
        right_m = self.width() - self.PAGE_MARGIN_X
        top_m = self.PAGE_MARGIN_Y
        bot_m = self.height() - self.PAGE_MARGIN_Y
        avail = max(1, right_m - left_m)

        # Вертикальные направляющие 12-колоночной сетки (25%, 50%, 75%)
        grid_pen = QPen(QColor(43, 127, 255, 22), 1, Qt.DotLine)
        p.setPen(grid_pen)
        for col in range(1, 12):
            gx = int(left_m + (avail * col / 12))
            p.drawLine(gx, top_m, gx, bot_m)

        # Жесткие границы полей страницы (левый и правый барьер)
        margin_pen = QPen(QColor(135, 200, 0, 75), 1, Qt.DashLine)
        p.setPen(margin_pen)
        p.drawLine(left_m, 12, left_m, self.height() - 12)
        p.drawLine(right_m, 12, right_m, self.height() - 12)
        p.end()


class Canvas(QScrollArea):
    """Холст блоков с листом фиксированных полей, свободным положением по X (лево/центр/право/offset)
    и постоянным пересчетом ширины (10..100%)."""

    block_clicked = Signal(str)
    section_clicked = Signal(str)
    block_moved = Signal(str, str, int)             # block_id, target_section_id, new_index
    block_merge_requested = Signal(str, str)        # source_id, target_id
    block_resized = Signal(str, int, int)           # block_id, width_pct, min_height_px
    block_live_resized = Signal(str, int, int)      # block_id, width_pct, min_height_px (во время тяги)
    block_position_changed = Signal(str, str, int)  # block_id, align, offset_x_pct
    empty_clicked = Signal()

    block_delete_requested = Signal(str)
    block_duplicate_requested = Signal(str)
    block_move_up_requested = Signal(str)
    block_move_down_requested = Signal(str)
    block_edit_text_requested = Signal(str)

    block_content_changed = Signal(str, str)
    block_focus_in = Signal(str)
    block_focus_out = Signal(str)

    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self._widgets: dict[str, BlockWidget] = {}
        self._row_containers: dict[str, QWidget] = {}
        self._specs_by_id: dict[str, object] = {}
        self._selected_id: str | None = None
        self._positions: dict[str, tuple[str, int]] = {}
        self._drop_target_id: str | None = None

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setStyleSheet("QScrollArea { background:#dde1e7; border:none; }")
        self.setAcceptDrops(True)

        # ★ Троттлинг ресайза (предотвращает фризы UI при изменении размера окна)
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(50)  # срабатывает через 50мс после остановки перетаскивания
        self._resize_timer.timeout.connect(self._sync_all_block_geometries)

        # Внешний стол вокруг страницы
        self._desk = QWidget()
        self._desk.setStyleSheet("background:#dde1e7;")
        self._desk.setAcceptDrops(True)
        desk_lay = QVBoxLayout(self._desk)
        desk_lay.setContentsMargins(36, 28, 36, 28)
        desk_lay.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        # Сам белый лист с жесткими полями
        self._inner = _PageSheet(self._desk)
        self._inner.setMinimumWidth(680)
        self._inner.setMaximumWidth(1280)
        self._inner.setAcceptDrops(True)

        self._layout = QVBoxLayout(self._inner)
        self._layout.setContentsMargins(
            _PageSheet.PAGE_MARGIN_X,
            _PageSheet.PAGE_MARGIN_Y,
            _PageSheet.PAGE_MARGIN_X,
            _PageSheet.PAGE_MARGIN_Y,
        )
        self._layout.setSpacing(14)
        self._layout.setAlignment(Qt.AlignTop)

        desk_lay.addWidget(self._inner)
        self.setWidget(self._desk)

    def available_content_width(self) -> int:
        return self._inner.available_content_width()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resize_timer.start()

    def _sync_all_block_geometries(self):
        """Пересчитывает пиксельную ширину и горизонтальный отступ всех блоков при ресайзе окна."""
        avail_w = self.available_content_width()
        for bid, w in self._widgets.items():
            if bid.startswith("__section__"):
                w.setFixedWidth(avail_w)
                continue
            spec = self._specs_by_id.get(bid)
            cfg = (spec.config if spec and hasattr(spec, "config") else getattr(w, "_config", {})) or {}
            self._apply_block_box_geometry(bid, w, cfg, avail_w)

    def _apply_block_box_geometry(self, block_id: str, w: BlockWidget, cfg: dict, avail_w: int | None = None):
        if avail_w is None:
            avail_w = self.available_content_width()

        width_pct = max(15, min(100, int(cfg.get("width", 100))))
        align = cfg.get("align", "left")
        offset_pct = max(0, min(100 - width_pct, int(cfg.get("offset_x", 0))))

        target_w = int(avail_w * width_pct / 100)
        w.setFixedWidth(target_w)

        row_wrap = self._row_containers.get(block_id)
        if row_wrap is not None and row_wrap.layout() is not None:
            rlay = row_wrap.layout()
            top_m = int(cfg.get("margin_top", 0))
            bot_m = int(cfg.get("margin_bottom", 14))
            if width_pct >= 100:
                left_px = 0
            elif align == "center":
                left_px = max(0, (avail_w - target_w) // 2)
            elif align == "right":
                left_px = max(0, avail_w - target_w)
            elif align == "custom":
                left_px = max(0, min(avail_w - target_w, int(avail_w * offset_pct / 100)))
            else:
                left_px = 0
            rlay.setContentsMargins(left_px, top_m, 0, max(0, bot_m - 14))

    def rebuild(self, report, dataframe=None):
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._widgets.clear()
        self._row_containers.clear()
        self._specs_by_id.clear()
        self._positions.clear()

        if not report.sections:
            hint = QLabel("Кликните по листу, чтобы создать первый раздел отчёта")
            hint.setAlignment(Qt.AlignCenter)
            hint.setStyleSheet("color:#94a3b8; font-size:14px; padding:80px; background:transparent;")
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

        self._layout.addStretch()
        self._layout.setAlignment(Qt.AlignTop)
        self._sync_all_block_geometries()

        if self._selected_id and self._selected_id in self._widgets:
            self._widgets[self._selected_id].set_selected(True)

    def _add_block_widget(self, spec, section_id, index, dataframe):
        row_wrap = QWidget(self._inner)
        row_wrap.setStyleSheet("background: transparent; border: none;")
        row_lay = QHBoxLayout(row_wrap)
        row_lay.setContentsMargins(0, 0, 0, 0)
        row_lay.setSpacing(0)
        row_lay.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        w = make_block_widget(
            spec.type, spec.id, spec.config, dataframe, row_wrap, self.theme,
        )
        w.clicked.connect(self._on_block_widget_clicked)
        w.live_resized.connect(self._on_block_live_resized)
        w.resized.connect(self._on_block_final_resized)
        w.position_changed.connect(self._on_block_position_changed)
        w.delete_requested.connect(self.block_delete_requested.emit)
        w.duplicate_requested.connect(self.block_duplicate_requested.emit)
        w.move_up_requested.connect(self.block_move_up_requested.emit)
        w.move_down_requested.connect(self.block_move_down_requested.emit)
        w.edit_text_requested.connect(self.block_edit_text_requested.emit)

        if hasattr(w, "content_changed"):
            w.content_changed.connect(self.block_content_changed.emit)
            w.focus_in.connect(self.block_focus_in.emit)
            w.focus_out.connect(self.block_focus_out.emit)

        row_lay.addWidget(w)
        row_lay.addStretch(1)

        self._widgets[spec.id] = w
        self._row_containers[spec.id] = row_wrap
        self._specs_by_id[spec.id] = spec
        self._positions[spec.id] = (section_id, index)
        self._layout.addWidget(row_wrap)

        if spec.type == "divider":
            w.setFixedHeight(18)

        min_h = int(spec.config.get("min_height", 0))
        if min_h > 0:
            w.setMinimumHeight(min_h)
        elif spec.type != "plotly_chart":
            w.setMinimumHeight(0)

        self._apply_block_box_geometry(spec.id, w, spec.config)

    def _sync_inspector_widgets(self, block_id: str, width_pct: int, min_h: int):
        """Напрямую синхронизирует ползунок и спинбокс ширины/высоты в BlockInspector."""
        win = self.window()
        if win is not None:
            from src.ui.block_inspector import BlockInspector
            for inspector in win.findChildren(BlockInspector):
                inspector.sync_live_geometry(block_id, width_pct, min_h)

    def _on_block_live_resized(self, block_id: str, width_pct: int, min_h: int):
        spec = self._specs_by_id.get(block_id)
        if spec is not None:
            spec.config["width"] = width_pct
            spec.config["min_height"] = min_h
        w = self._widgets.get(block_id)
        if w is not None:
            self._apply_block_box_geometry(block_id, w, spec.config if spec else w._config)
        self._sync_inspector_widgets(block_id, width_pct, min_h)
        self.block_live_resized.emit(block_id, width_pct, min_h)

    def _on_block_final_resized(self, block_id: str, width_pct: int, min_h: int):
        spec = self._specs_by_id.get(block_id)
        if spec is not None:
            spec.config["width"] = width_pct
            spec.config["min_height"] = min_h
        w = self._widgets.get(block_id)
        if w is not None:
            self._apply_block_box_geometry(block_id, w, spec.config if spec else w._config)
        self._sync_inspector_widgets(block_id, width_pct, min_h)
        self.block_resized.emit(block_id, width_pct, min_h)

    def _on_block_position_changed(self, block_id: str, align: str, offset_x: int):
        spec = self._specs_by_id.get(block_id)
        if spec is not None:
            spec.config["align"] = align
            spec.config["offset_x"] = offset_x
        w = self._widgets.get(block_id)
        if w is not None:
            self._apply_block_box_geometry(block_id, w, spec.config if spec else w._config)
        self.block_position_changed.emit(block_id, align, offset_x)
        self.block_clicked.emit(block_id)

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
                fw = QApplication.focusWidget()
                if fw is not None:
                    fw.clearFocus()
                self.empty_clicked.emit()
        super().mousePressEvent(event)

    # ---------- Drag-n-drop (Свободное позиционирование на странице и объединение в ряд) ----------

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
        hotspot_x = 0
        if event.mimeData().hasFormat("application/x-ea-hotspot-x"):
            try:
                hotspot_x = int(bytes(event.mimeData().data("application/x-ea-hotspot-x")).decode("utf-8"))
            except ValueError:
                hotspot_x = 0

        pos = event.position().toPoint()
        widget_under = self._widget_at(pos)

        # Если бросили поверх другого блока — объединяем их рядом в контейнер
        if widget_under and widget_under.block_id != block_id \
                and not widget_under.block_id.startswith("__section__"):
            self._set_drop_highlight(None)
            event.acceptProposedAction()
            self.block_merge_requested.emit(block_id, widget_under.block_id)
            return

        # Вычисляем свободную горизонтальную позицию X внутри листа, куда пользователь поставил блок
        inner_pos = self._inner.mapFrom(self.viewport(), pos)
        spec = self._specs_by_id.get(block_id)
        if spec is not None and hasattr(spec, "config"):
            w_pct = int(spec.config.get("width", 100))
            if w_pct < 100:
                avail_w = self.available_content_width()
                drop_left_px = max(0, inner_pos.x() - _PageSheet.PAGE_MARGIN_X - hotspot_x)
                raw_offset_pct = max(0, min(100 - w_pct, int(round(drop_left_px / avail_w * 100))))
                center_pct = (100 - w_pct) // 2

                # Умное примагничивание к левому краю, центру или правому краю (если близко, иначе точный custom X)
                if raw_offset_pct <= 4:
                    spec.config["align"] = "left"
                    spec.config["offset_x"] = 0
                elif abs(raw_offset_pct - center_pct) <= 5:
                    spec.config["align"] = "center"
                    spec.config["offset_x"] = center_pct
                elif raw_offset_pct >= (100 - w_pct - 4):
                    spec.config["align"] = "right"
                    spec.config["offset_x"] = 100 - w_pct
                else:
                    spec.config["align"] = "custom"
                    spec.config["offset_x"] = raw_offset_pct

        target = self._find_drop_target(pos)
        self._set_drop_highlight(None)
        if target is None:
            return
        target_section_id, new_index = target
        event.acceptProposedAction()
        self.block_moved.emit(block_id, target_section_id, new_index)

    # ---------- Поиск цели ----------

    def _widget_at(self, pos) -> BlockWidget | None:
        for wid, w in self._widgets.items():
            if w is None or not w.isVisible():
                continue
            local_pt = w.mapFrom(self.viewport(), pos)
            if w.rect().contains(local_pt):
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

        blocks_in_section = []
        for wid, w in self._widgets.items():
            sec_id, idx = self._positions.get(wid, (None, -1))
            if sec_id == current_section_id and idx != -1:
                wrap = self._row_containers.get(wid, w)
                blocks_in_section.append((wid, wrap))

        blocks_in_section.sort(key=lambda x: x[1].geometry().top())

        new_index = 0
        for _, wrap in blocks_in_section:
            mid_y = wrap.geometry().top() + wrap.geometry().height() // 2
            if inner_pos.y() >= mid_y:
                new_index += 1
            else:
                break

        return (current_section_id, new_index)

    def _set_drop_highlight(self, target_block_id: str | None):
        if self._drop_target_id == target_block_id:
            return
        for wid, w in self._widgets.items():
            w.set_drop_highlight(False)
        self._drop_target_id = target_block_id
        if target_block_id and target_block_id in self._widgets:
            self._widgets[target_block_id].set_drop_highlight(True)