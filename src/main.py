"""
Точка входа приложения NexGrid.
Проверка пароля и лицензии перед запуском.
"""

import sys
import os
import math

# Отключаем GPU-синхронизацию — иначе приложение зависает при закрытии
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu-vsync --disable-gpu"
os.environ["QT_OPENGL"] = "software"

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QSplashScreen
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont, QPolygonF, QPen
from PySide6.QtCore import Qt, QTimer, QPointF, QEventLoop

from src.config.app_info import APP_NAME, APP_AUTHOR
from src.config.theme import LIGHT_THEME, DARK_THEME, set_theme
from src.config.settings import get_settings
from src.config.security import get_security
from src.ui.password_dialog import PasswordDialog
from src.ui.main_window import MainWindow


class AnimatedSplashScreen(QSplashScreen):
    """Кастомный Splash Screen с анимированным вращающимся логотипом."""
    def __init__(self):
        super().__init__()
        self.angle = 0
        
        # Таймер для анимации (обновление каждые ~16 мс = 60 FPS)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(16)
        
        self.update_frame()

    def update_frame(self):
        # Увеличиваем угол вращения
        self.angle = (self.angle + 2) % 360
        
        pixmap = QPixmap(540, 340)
        pixmap.fill(QColor("#1A1D24"))  # Тёмный графитовый фон
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 1. Текст NEXGRID
        font_text = QFont("Century Gothic", 34, QFont.Bold)
        font_text.setLetterSpacing(QFont.AbsoluteSpacing, 8)
        painter.setFont(font_text)
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(pixmap.rect().adjusted(0, 50, 0, 50), Qt.AlignCenter, "NEXGRID")
        
        # 2. Подпись
        font_sub = QFont("Segoe UI", 10)
        painter.setFont(font_sub)
        painter.setPen(QColor("#8B93A7"))
        painter.drawText(pixmap.rect().adjusted(0, 130, 0, 130), Qt.AlignCenter, "Загрузка модулей и сборка интерфейса...")
        
        # 3. Рисуем вращающийся правильный 6-угольник
        painter.translate(pixmap.width() / 2, pixmap.height() / 2 - 60)
        painter.rotate(self.angle)
        
        poly = QPolygonF()
        radius = 35
        for i in range(6):
            # Математический расчет углов 6-угольника (со сдвигом -30 градусов для ровной стойки)
            angle_rad = math.radians(i * 60 - 30)
            x = radius * math.cos(angle_rad)
            y = radius * math.sin(angle_rad)
            poly.append(QPointF(x, y))
            
        pen = QPen(QColor("#87C800"))
        pen.setWidth(5)
        pen.setJoinStyle(Qt.MiterJoin)
        painter.setPen(pen)
        painter.drawPolygon(poly)
        
        painter.end()
        self.setPixmap(pixmap)


def load_saved_theme():
    """Загрузить тему из настроек."""
    settings = get_settings()
    name = settings.get_theme_name()
    if name == "dark":
        set_theme(DARK_THEME)
        print("[main] Загружена тёмная тема")
    else:
        set_theme(LIGHT_THEME)
        print("[main] Загружена светлая тема")


def check_license(security) -> bool:
    """Проверить лицензию (привязка к ПК)."""
    if not security.has_license():
        print("[main] Создание лицензии для текущего ПК...")
        security.create_license()
        print(f"[main] Machine ID: {security.get_machine_id()}")
        return True
    
    if not security.verify_license():
        print("[main] Лицензия не подходит для этого ПК")
        QMessageBox.critical(
            None,
            "Ошибка лицензии",
            "Эта копия приложения не предназначена\nдля данного компьютера.\n\n"
            "Обратитесь к разработчику."
        )
        return False
    
    return True


def check_password(security) -> bool:
    """Проверить пароль. При первом запуске — установить."""
    from src.config.theme import get_theme
    theme = get_theme()
    
    if not security.has_password():
        print("[main] Установка пароля (первый запуск)...")
        dialog = PasswordDialog(security, theme, mode="setup")
    else:
        print("[main] Запрос пароля...")
        dialog = PasswordDialog(security, theme, mode="login")
    
    result = dialog.exec()
    
    if result != QDialog.Accepted:
        print("[main] Доступ отклонён")
        return False
    
    print("[main] Пароль принят")
    return True


def main():
    """Запуск приложения."""
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_AUTHOR)
    
    # 1. Запускаем АНИМИРОВАННЫЙ Splash Screen
    splash = AnimatedSplashScreen()
    splash.show()
    app.processEvents()
    
    load_saved_theme()
    security = get_security()
    
    if not check_license(security):
        return 1
    
    # 2. Крутим заставку 2.5 секунды перед вводом пароля
    loop = QEventLoop()
    QTimer.singleShot(2500, loop.quit)
    loop.exec()
    
    # 3. Прячем сплеш-скрин и запрашиваем пароль
    splash.hide()
        
    if not check_password(security):
        return 1
    
    print("[main] Запуск основного окна...")
    window = MainWindow()
    window.show()
    
    splash.finish(window)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()