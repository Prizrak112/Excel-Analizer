import sys
import os
import base64
import hashlib
from importlib.abc import Loader, MetaPathFinder
from importlib.util import spec_from_loader
from cryptography.fernet import Fernet
from PySide6.QtWidgets import QApplication, QMessageBox, QInputDialog, QLineEdit

_APP_KEY = None

def get_key(password: str) -> bytes:
    digest = hashlib.sha256(password.encode('utf-8')).digest()
    return base64.urlsafe_b64encode(digest)

class EncryptedModuleLoader(Loader):
    def __init__(self, fullname, path):
        self.fullname = fullname
        self.path = path

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        global _APP_KEY
        cipher = Fernet(_APP_KEY)
        try:
            with open(self.path, "rb") as f:
                encrypted_data = f.read()
            # Расшифровка происходит исключительно в оперативной памяти
            decrypted_code = cipher.decrypt(encrypted_data).decode('utf-8')
            exec(decrypted_code, module.__dict__)
        except Exception as e:
            raise ImportError(f"Не удалось расшифровать модуль {self.fullname}: Неверный пароль или файл поврежден.")

class EncryptedModuleFinder(MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname.startswith("src.ui.") or fullname.startswith("src.core."):
            rel_path = fullname.replace(".", os.sep) + ".enc"
            if os.path.exists(rel_path):
                return spec_from_loader(fullname, EncryptedModuleLoader(fullname, rel_path))
        return None

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Запрос пароля администратора до импорта основного кода
    pwd, ok = QInputDialog.getText(
        None, "Авторизация", 
        "Введите пароль администратора для расшифровки ядра:",
        QLineEdit.Password
    )
    
    if ok and pwd:
        _APP_KEY = get_key(pwd)
        
        # Регистрируем in-memory загрузчик в систему импортов Python
        sys.meta_path.insert(0, EncryptedModuleFinder())
        
        try:
            # Модули прозрачно загружаются из .enc файлов!
            from src.config.theme import get_theme
            from src.ui.main_window import MainWindow
            
            window = MainWindow()
            window.show()
            sys.exit(app.exec())
        except ImportError as e:
            QMessageBox.critical(None, "Отказ в доступе", "Неверный пароль администратора или файлы повреждены!")
            sys.exit(1)
    else:
        sys.exit(0)