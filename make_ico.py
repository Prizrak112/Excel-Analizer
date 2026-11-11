from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPixmap, QPainter, QColor, QPen, QPolygonF
from PySide6.QtCore import Qt, QPointF
import math
import sys

app = QApplication(sys.argv)

# Создаем холст высокого разрешения для четкой иконки (256x256)
pixmap = QPixmap(256, 256)
pixmap.fill(Qt.transparent)

painter = QPainter(pixmap)
painter.setRenderHint(QPainter.Antialiasing)

# Рисуем фирменный гексагон NEXGRID
cx, cy = 128.0, 128.0
radius = 95.0

hex_poly = QPolygonF([
    QPointF(cx + radius * math.cos(math.radians(60 * i - 30)),
            cy + radius * math.sin(math.radians(60 * i - 30)))
    for i in range(6)
])

# Зеленый контур логотипа
painter.setPen(QPen(QColor("#87C800"), 14, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
painter.setBrush(QColor(135, 200, 0, 45))
painter.drawPolygon(hex_poly)

painter.end()

# Сохраняем как logo.ico
pixmap.save("logo.ico", "ICO")
print("Файл logo.ico успешно сгенерирован!")