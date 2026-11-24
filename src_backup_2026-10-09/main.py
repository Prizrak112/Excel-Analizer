"""
Точка входа приложения Excel Analyzer.
Проверка пароля и лицензии перед запуском.
"""

import sys
import os

# Отключаем GPU-синхронизацию — иначе приложение зависает при закрытии
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu-vsync --disable-gpu"
os.environ["QT_OPENGL"] = "software"

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from src.config.app_info import APP_NAME, APP_AUTHOR
from src.config.theme import LIGHT_THEME, DARK_THEME, set_theme
from src.config.settings import get_settings
from src.config.security import get_security
from src.ui.password_dialog import PasswordDialog
from src.ui.main_window import MainWindow


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
    
    # ← Загружаем сохранённую тему
    load_saved_theme()
    
    security = get_security()
    
    if not check_license(security):
        return 1
    
    if not check_password(security):
        return 1
    
    print("[main] Запуск основного окна...")
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()