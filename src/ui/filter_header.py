"""
Кастомный заголовок QTableView.
Содержит только воронку фильтра справа.
"""

from PySide6.QtWidgets import QHeaderView
from PySide6.QtCore import Qt, Signal, QPoint, QRect
from PySide6.QtGui import QPainter, QColor, QPolygon


class FilterHeader(QHeaderView):
    """Заголовок с иконкой фильтра."""

    filter_clicked = Signal(int)         # logical index

    FUNNEL_WIDTH = 24

    def __init__(self, orientation, theme, parent=None):
        super().__init__(orientation, parent)
        self.theme = theme
        self._filtered_indices: set[int] = set()

        self.setSectionsClickable(True)
        self.setHighlightSections(False)

        self.setStretchLastSection(False)
        self.setCascadingSectionResizes(False)
        self.setMinimumSectionSize(self.FUNNEL_WIDTH + 20)

    def set_filtered_indices(self, indices: set):
        self._filtered_indices = set(indices or [])
        self.viewport().update()

    def set_sort_state(self, sort_state: list):
        # Оставляем метод для совместимости, но визуально в шапке не рисуем
        pass

    def paintSection(self, painter: QPainter, rect: QRect, logicalIndex: int):
        super().paintSection(painter, rect, logicalIndex)

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)

        cx_funnel = rect.right() - self.FUNNEL_WIDTH // 2 - 4
        cy = rect.top() + rect.height() // 2

        # ── Только воронка фильтра справа ──
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

        painter.restore()

    def sizeHint(self):
        return super().sizeHint()

    def sectionSizeFromContents(self, logicalIndex: int):
        return super().sectionSizeFromContents(logicalIndex)

    def resizeEvent(self, event):
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

            # Клик строго по воронке фильтра
            if pos.x() >= funnel_start:
                self.filter_clicked.emit(index)
                return

        super().mousePressEvent(event)