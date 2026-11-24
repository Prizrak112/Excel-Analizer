"""
Кастомный заголовок QTableView.
Содержит: воронку фильтра ▼ и стрелку сортировки ⇅.
"""

from PySide6.QtWidgets import QHeaderView
from PySide6.QtCore import Qt, Signal, QPoint, QRect
from PySide6.QtGui import QPainter, QColor, QPolygon, QFont


class FilterHeader(QHeaderView):
    """Заголовок с иконкой фильтра и стрелкой сортировки."""

    filter_clicked = Signal(int)         # logical index
    sort_clicked = Signal(int, bool)     # logical index, shift

    FUNNEL_WIDTH = 20
    SORT_ARROW_WIDTH = 20

    def __init__(self, orientation, theme, parent=None):
        super().__init__(orientation, parent)
        self.theme = theme
        self._filtered_indices: set[int] = set()
        # [(col_idx, asc), ...] — порядок = порядок в сортировке
        self._sort_state: list[tuple[int, bool]] = []

        self.setSectionsClickable(True)
        self.setHighlightSections(False)

        # Никаких авто-ресайзов — только вручную
        self.setStretchLastSection(False)
        self.setCascadingSectionResizes(False)
        self.setMinimumSectionSize(self.FUNNEL_WIDTH + self.SORT_ARROW_WIDTH + 40)

    # ============================================================
    # Публичный API
    # ============================================================

    def set_filtered_indices(self, indices: set):
        self._filtered_indices = set(indices or [])
        self.viewport().update()

    def set_sort_state(self, sort_state: list):
        """sort_state: [(col_idx, asc), ...]"""
        self._sort_state = list(sort_state)
        self.viewport().update()

    # ============================================================
    # Отрисовка
    # ============================================================

    def paintSection(self, painter: QPainter, rect: QRect, logicalIndex: int):
        super().paintSection(painter, rect, logicalIndex)

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)

        cx_funnel = rect.right() - self.FUNNEL_WIDTH // 2 - 4
        cy = rect.top() + rect.height() // 2

        # ── Воронка фильтра (самая правая) ──
        if logicalIndex in self._filtered_indices:
            funnel_color = QColor(self.theme.primary)
        else:
            funnel_color = QColor("#8fa7c4")

        painter.setBrush(funnel_color)
        triangle = QPolygon([
            QPoint(cx_funnel - 5, cy - 3),
            QPoint(cx_funnel + 5, cy - 3),
            QPoint(cx_funnel, cy + 4),
        ])
        painter.drawPolygon(triangle)

        # ── Стрелка сортировки (слева от воронки) ──
        sort_rank = None
        sort_asc = True
        for i, (idx, asc) in enumerate(self._sort_state):
            if idx == logicalIndex:
                sort_rank = i + 1
                sort_asc = asc
                break

        cx_arrow = cx_funnel - self.FUNNEL_WIDTH // 2 - self.SORT_ARROW_WIDTH // 2 - 2

        if sort_rank is not None:
            arrow_color = QColor(self.theme.primary)
        else:
            arrow_color = QColor("#8fa7c4")

        painter.setBrush(arrow_color)

        # Рисуем стрелку вверх или вниз
        if sort_asc:
            arrow = QPolygon([
                QPoint(cx_arrow - 5, cy + 3),
                QPoint(cx_arrow + 5, cy + 3),
                QPoint(cx_arrow, cy - 4),
            ])
        else:
            arrow = QPolygon([
                QPoint(cx_arrow - 5, cy - 3),
                QPoint(cx_arrow + 5, cy - 3),
                QPoint(cx_arrow, cy + 4),
            ])
        painter.drawPolygon(arrow)

        # Если сортировка мульти — рядом с стрелкой рисуем номер
        if sort_rank is not None and len(self._sort_state) > 1:
            painter.setPen(QColor(self.theme.primary))
            font = QFont()
            font.setPointSize(8)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(
                QRect(cx_arrow + 6, cy - 6, 12, 12),
                Qt.AlignLeft | Qt.AlignVCenter,
                str(sort_rank),
            )

        painter.restore()

    # ============================================================
    # Мышь
    # ============================================================
    # ============================================================
    # Размеры секций — не даём Qt растягивать колонки
    # ============================================================

    def sizeHint(self):
        """Не даём заголовку «хотеть» больше места, чем у него есть."""
        s = super().sizeHint()
        return s

    def sectionSizeFromContents(self, logicalIndex: int):
        """
        Ширина секции по содержимому — но БЕЗ учёта наших дорисованных
        иконок в правом краю. Иначе Qt будет расширять колонку при hover.
        """
        # Возвращаем размер, который Qt вычислил сам для текста,
        # без «+FUNNEL+ARROW».
        return super().sectionSizeFromContents(logicalIndex)

    def resizeEvent(self, event):
        """
        При resize viewport НЕ даём Qt переразложить секции.
        Сохраняем ширины, которые задал пользователь (или мы через setColumnWidth).
        """
        sizes = [self.sectionSize(i) for i in range(self.count())]
        super().resizeEvent(event)
        for i, w in enumerate(sizes):
            if i < self.count():
                self.resizeSection(i, w)

    def mousePressEvent(self, event):
        pos = event.position().toPoint()
        index = self.logicalIndexAt(pos)

        if index >= 0:
            left = self.sectionViewportPosition(index)
            width = self.sectionSize(index)
            right = left + width

            funnel_start = right - self.FUNNEL_WIDTH
            arrow_start = funnel_start - self.SORT_ARROW_WIDTH

            # Клик по воронке
            if pos.x() >= funnel_start:
                self.filter_clicked.emit(index)
                return

            # Клик по стрелке сортировки
            if pos.x() >= arrow_start:
                shift = bool(event.modifiers() & Qt.ShiftModifier)
                self.sort_clicked.emit(index, shift)
                return

        # Иначе — базовое поведение (выбор колонки)
        super().mousePressEvent(event)