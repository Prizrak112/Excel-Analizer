"""Шифрует ядро (src/core, src/ui) паролем и собирает NexGrid в единый dist/NexGrid.exe."""

import base64
import getpass
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

from cryptography.fernet import Fernet


ROOT = Path(__file__).resolve().parent
LAUNCHER_SCRIPT = ROOT / "src" / "launcher.py"
APP_NAME = "NexGrid"
STAGE_DIR = ROOT / "_enc_stage"


def find_icon_path() -> Path | None:
    """Ищет logo.ico (или icon.ico) в корне проекта и папках ресурсов."""
    candidates = [
        ROOT / "logo.ico",
        ROOT / "assets" / "logo.ico",
        ROOT / "src" / "assets" / "logo.ico",
        ROOT / "resources" / "logo.ico",
        ROOT / "src" / "logo.ico",
        ROOT / "assets" / "icon.ico",
    ]
    for p in candidates:
        if p.is_file():
            return p
    return None


def make_fernet_key(password: str) -> bytes:
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_package_tree(src_root: Path, stage_root: Path, cipher: Fernet) -> tuple[list[tuple[Path, str]], list[str]]:
    """Шифрует ВСЕ .py внутри src/ (core, ui, config и др.), кроме самого launcher.py."""
    data_entries: list[tuple[Path, str]] = []
    subpackages: list[str] = []

    launcher_resolved = LAUNCHER_SCRIPT.resolve()

    # Шифруем все .py файлы в src/ (включая src/config/*, src/core/*, src/ui/* и т.д.)
    for py_file in src_root.rglob("*.py"):
        if "__pycache__" in py_file.parts:
            continue
        if py_file.resolve() == launcher_resolved:
            continue

        rel_py = py_file.relative_to(ROOT)
        enc_rel = rel_py.with_suffix(".enc")
        enc_dest = stage_root / enc_rel
        enc_dest.parent.mkdir(parents=True, exist_ok=True)

        enc_dest.write_bytes(cipher.encrypt(py_file.read_bytes()))

        dest_folder = str(enc_rel.parent).replace("\\", "/")
        data_entries.append((enc_dest, dest_folder))

        if len(rel_py.parts) >= 3:
            sub_name = f"src.{rel_py.parts[1]}"
            if sub_name not in subpackages:
                subpackages.append(sub_name)

    return data_entries, subpackages


def main():
    if not LAUNCHER_SCRIPT.is_file():
        print(f"❌ Не найден файл загрузчика: {LAUNCHER_SCRIPT}")
        sys.exit(1)

    # Проверяем PyInstaller
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("📦 Устанавливаю PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    pwd = getpass.getpass("Задайте пароль шифрования для сборки .exe: ")
    pwd2 = getpass.getpass("Повторите пароль: ")
    if not pwd or pwd != pwd2:
        print("❌ Пароль пустой или не совпадает.")
        sys.exit(1)

    if STAGE_DIR.exists():
        shutil.rmtree(STAGE_DIR)
    STAGE_DIR.mkdir(parents=True, exist_ok=True)

    try:
        cipher = Fernet(make_fernet_key(pwd))
        enc_entries, enc_subpkgs = encrypt_package_tree(ROOT / "src", STAGE_DIR, cipher)
        print(f"🔐 Зашифровано модулей: {len(enc_entries)} (пакеты: {', '.join(enc_subpkgs)})")

        icon_path = find_icon_path()
        if icon_path:
            print(f"🖼 Найден логотип: {icon_path}")
        else:
            print("⚠ Файл logo.ico не найден! Положите logo.ico в корень проекта или в папку assets/.")

        sep = ";" if os.name == "nt" else ":"
        cmd = [
            sys.executable, "-m", "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onefile",
            "--windowed",
            f"--name={APP_NAME}",
            f"--paths={ROOT}",
            # ── Запрещаем класть открытый байткод пакетов src.* внутрь .exe ──
            "--exclude-module=src",
            *[f"--exclude-module={pkg}" for pkg in enc_subpkgs],
            # ── Принудительно упаковываем зависимости, которые используются внутри .enc ──
            "--collect-data=plotly",
            "--collect-data=tzdata",
            "--collect-all=python_calamine",
            "--collect-submodules=narwhals",
            "--collect-submodules=waitress",
            "--collect-submodules=cryptography",
            "--hidden-import=_cffi_backend",
            "--hidden-import=PySide6.QtCore",
            "--hidden-import=PySide6.QtGui",
            "--hidden-import=PySide6.QtWidgets",
            "--hidden-import=pandas",
            "--hidden-import=pandas.io.excel._calamine",
            "--hidden-import=pandas.io.excel._openpyxl",
            "--hidden-import=numpy",
            "--hidden-import=openpyxl",
            "--hidden-import=openpyxl.cell._writer",
            "--hidden-import=et_xmlfile",
            "--hidden-import=dateutil",
            "--hidden-import=packaging",
            "--hidden-import=jinja2",
            "--hidden-import=markupsafe",
            "--hidden-import=plotly",
            "--hidden-import=plotly.express",
            "--hidden-import=plotly.graph_objects",
            "--hidden-import=plotly.io",
            "--hidden-import=plotly.subplots",
            # pywin32 (если не используется в проекте — эти 5 строк можно убрать для ускорения сборки)
            "--hidden-import=win32api",
            "--hidden-import=win32con",
            "--hidden-import=win32gui",
            "--hidden-import=win32com.client",
            "--hidden-import=pythoncom",
            "--hidden-import=pywintypes",
            # Стандартные модули, вызываемые внутри .enc
            "--hidden-import=http.server",
            "--hidden-import=socketserver",
            "--hidden-import=webbrowser",
            "--hidden-import=threading",
            "--hidden-import=dataclasses",
            "--hidden-import=json",
            "--hidden-import=re",
            "--hidden-import=math",
            "--hidden-import=zlib",
            "--hidden-import=ast",
            "--hidden-import=uuid",
            "--hidden-import=hmac",
            "--hidden-import=secrets",
            "--hidden-import=inspect",
            "--hidden-import=copy",
            "--hidden-import=contextlib",
            "--hidden-import=subprocess",
            "--hidden-import=site",
            "--hidden-import=importlib.util",
            "--hidden-import=csv",
            # Уменьшаем размер .exe за счёт неиспользуемых модулей
            "--exclude-module=PySide6.QtWebEngineCore",
            "--exclude-module=PySide6.QtWebEngineWidgets",
            "--exclude-module=PySide6.Qt3DCore",
            "--exclude-module=PySide6.Qt3DRender",
            "--exclude-module=PySide6.QtMultimedia",
            "--exclude-module=PySide6.QtQuick",
            "--exclude-module=PySide6.QtQml",
            "--exclude-module=tkinter",
            "--exclude-module=matplotlib",
        ]

        # Добавляем все зашифрованные .enc файлы
        for enc_file, dest_folder in enc_entries:
            cmd.append(f"--add-data={enc_file}{sep}{dest_folder}")

        # Добавляем статические ресурсы (иконки, JS/CSS для таблиц)
        for res_dir_name in ("assets", "resources", "src/assets"):
            res_dir = ROOT / res_dir_name
            if res_dir.is_dir():
                cmd.append(f"--add-data={res_dir}{sep}{res_dir_name}")

        if icon_path is not None:
            cmd.append(f"--icon={icon_path}")
            # Кладём logo.ico и внутрь _MEIPASS, чтобы иконка была на окнах и панели задач
            cmd.append(f"--add-data={icon_path}{sep}.")

        cmd.append(str(LAUNCHER_SCRIPT))

        print("🚀 Сборка единого зашифрованного файла...")
        subprocess.check_call(cmd, cwd=str(ROOT))

        exe_path = ROOT / "dist" / (f"{APP_NAME}.exe" if os.name == "nt" else APP_NAME)
        print(f"\n✅ Готово! Зашифрованный файл собран: {exe_path}")
    finally:
        if STAGE_DIR.exists():
            shutil.rmtree(STAGE_DIR, ignore_errors=True)


if __name__ == "__main__":
    main()