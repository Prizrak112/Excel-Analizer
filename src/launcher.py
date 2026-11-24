import base64
import hashlib
import os
import sys
import traceback
from importlib.abc import Loader, MetaPathFinder
from importlib.util import spec_from_loader

import ctypes
from cryptography.fernet import Fernet, InvalidToken
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QInputDialog, QLineEdit, QMessageBox


_APP_KEY = None
BASE_DIR = getattr(
    sys,
    "_MEIPASS",
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Хранилище расшифрованных исходников в RAM (нужно для вкладки «Код» в Конструкторе)
sys._nexgrid_sources = {}


class InvalidPasswordError(ImportError):
    """Исключение именно при неверном пароле / повреждённом .enc файле."""


def get_key(password: str) -> bytes:
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


class _VirtualPackageLoader(Loader):
    """Загрузчик-заглушка для пакетов src.ui / src.core, если __init__.enc отсутствует."""

    def __init__(self, pkg_dir: str):
        self.pkg_dir = pkg_dir

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        module.__path__ = [self.pkg_dir]


class EncryptedModuleLoader(Loader):
    def __init__(self, fullname: str, path: str, is_package: bool = False):
        self.fullname = fullname
        self.path = path
        self.is_package = is_package

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        global _APP_KEY
        cipher = Fernet(_APP_KEY)
        try:
            with open(self.path, "rb") as f:
                encrypted_data = f.read()
            decrypted_code = cipher.decrypt(encrypted_data).decode("utf-8")
        except InvalidToken as exc:
            raise InvalidPasswordError(
                f"Неверный пароль при расшифровке {self.fullname}"
            ) from exc

        module.__file__ = self.path
        if self.is_package:
            module.__path__ = [os.path.dirname(self.path)]

        sys._nexgrid_sources[self.fullname] = decrypted_code
        code_obj = compile(decrypted_code, self.path, "exec")
        exec(code_obj, module.__dict__)


class EncryptedModuleFinder(MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname != "src" and not fullname.startswith("src."):
            return None

        parts = fullname.split(".")
        pkg_enc = os.path.join(BASE_DIR, *parts, "__init__.enc")
        if os.path.isfile(pkg_enc):
            return spec_from_loader(
                fullname,
                EncryptedModuleLoader(fullname, pkg_enc, is_package=True),
                is_package=True,
            )

        mod_enc = os.path.join(BASE_DIR, *parts) + ".enc"
        if os.path.isfile(mod_enc):
            return spec_from_loader(
                fullname,
                EncryptedModuleLoader(fullname, mod_enc, is_package=False),
                is_package=False,
            )

        pkg_dir = os.path.join(BASE_DIR, *parts)
        if os.path.isdir(pkg_dir):
            return spec_from_loader(
                fullname,
                _VirtualPackageLoader(pkg_dir),
                is_package=True,
            )

        return None


def _clear_encrypted_modules():
    for name in list(sys.modules.keys()):
        if name == "src" or name.startswith("src."):
            sys.modules.pop(name, None)
    sys._nexgrid_sources.clear()


def _find_runtime_icon() -> str:
    for rel in ("logo.ico", os.path.join("assets", "logo.ico"), os.path.join("src", "assets", "logo.ico")):
        cand = os.path.join(BASE_DIR, rel)
        if os.path.isfile(cand):
            return cand
    return ""


def main():
    global _APP_KEY

    # Отдельный AppUserModelID, чтобы Windows показывал logo.ico на панели задач
    if os.name == "nt":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("NexGrid.App.1.0")
        except Exception:
            pass

    app = QApplication(sys.argv)

    icon_file = _find_runtime_icon()
    if icon_file:
        app.setWindowIcon(QIcon(icon_file))

    finder = EncryptedModuleFinder()
    sys.meta_path.insert(0, finder)

    max_attempts = 5
    for attempt in range(1, max_attempts + 1):
        prompt = "Введите пароль администратора для расшифровки ядра:"
        if attempt > 1:
            prompt = f"Неверный пароль. Осталось попыток: {max_attempts - attempt + 1}\nВведите пароль:"

        pwd, ok = QInputDialog.getText(
            None,
            "NexGrid — Авторизация",
            prompt,
            QLineEdit.Password,
        )
        if not ok or not pwd:
            sys.exit(0)

        _APP_KEY = get_key(pwd)
        try:
            from src.config.theme import get_theme  # noqa: F401
            from src.ui.main_window import MainWindow

            window = MainWindow()
            window.show()
            sys.exit(app.exec())
        except InvalidPasswordError:
            _clear_encrypted_modules()
            if attempt >= max_attempts:
                QMessageBox.critical(
                    None,
                    "Отказ в доступе",
                    "Превышено число попыток. Неверный пароль или файлы повреждены.",
                )
                sys.exit(1)
        except Exception as exc:
            QMessageBox.critical(
                None,
                "Ошибка запуска программы",
                f"{type(exc).__name__}: {exc}\n\n{traceback.format_exc()}",
            )
            sys.exit(1)


if __name__ == "__main__":
    main()