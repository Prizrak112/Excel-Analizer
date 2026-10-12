"""
Защита приложения: пароль, хеширование, привязка к машине.
"""

import os
import json
import hashlib
import platform
from pathlib import Path
from datetime import datetime
import ctypes
from ctypes import wintypes


# ============================================================
# Пути
# ============================================================

CONFIG_DIR = Path.home() / ".excel-analyzer"
CONFIG_DIR.mkdir(exist_ok=True)
SECURITY_FILE = CONFIG_DIR / "security.json"
LICENSE_FILE = CONFIG_DIR / "license.json"


# ============================================================
# Хеширование пароля
# ============================================================

SALT = "ea_2026_v1_x9k2m"


def hash_password(password: str, salt: str = SALT) -> str:
    """SHA-256 хеш пароля с солью."""
    data = (salt + password).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def verify_password(password: str, stored_hash: str) -> bool:
    """Проверить пароль против сохранённого хеша."""
    return hash_password(password) == stored_hash


# ============================================================
# Стабильный machine_id — источники
# ============================================================

def _get_machine_guid() -> str | None:
    """
    Основной источник: MachineGuid из реестра Windows.
    HKLM\\SOFTWARE\\Microsoft\\Cryptography\\MachineGuid
    Генерируется один раз при установке Windows, не меняется
    при смене сети, переименовании ПК, обновлениях.
    """
    if platform.system() != "Windows":
        return None
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        )
        value, _ = winreg.QueryValueEx(key, "MachineGuid")
        winreg.CloseKey(key)
        return str(value).strip() if value else None
    except Exception:
        return None


def _get_volume_serial(drive: str = "C:\\") -> str | None:
    """
    Серийный номер тома C: через WinAPI.
    Не зависит от локали Windows и не требует wmic.
    """
    if platform.system() != "Windows":
        return None
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetVolumeInformationW.argtypes = [
            wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
            ctypes.POINTER(wintypes.DWORD), wintypes.LPWSTR, wintypes.DWORD,
        ]
        kernel32.GetVolumeInformationW.restype = wintypes.BOOL

        volume_name = ctypes.create_unicode_buffer(1024)
        fs_name = ctypes.create_unicode_buffer(1024)
        serial = wintypes.DWORD()
        max_component = wintypes.DWORD()
        flags = wintypes.DWORD()

        ok = kernel32.GetVolumeInformationW(
            drive, volume_name, len(volume_name),
            ctypes.byref(serial), ctypes.byref(max_component),
            ctypes.byref(flags), fs_name, len(fs_name),
        )
        if ok:
            return f"{serial.value:08X}"
    except Exception:
        pass
    return None


def _get_cpu_id() -> str | None:
    """
    ProcessorId процессора из реестра Windows.
    Не требует wmic (который удалён в новых версиях Windows).
    """
    if platform.system() != "Windows":
        return None
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            0, winreg.KEY_READ,
        )
        value, _ = winreg.QueryValueEx(key, "ProcessorId")
        winreg.CloseKey(key)
        return str(value).strip() if value else None
    except Exception:
        return None


# ============================================================
# Хранилище безопасности
# ============================================================

class SecurityStore:
    """Хранилище пароля и настроек безопасности."""

    def __init__(self):
        self._data = self._load()

    def _load(self) -> dict:
        if SECURITY_FILE.exists():
            try:
                with open(SECURITY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save(self):
        with open(SECURITY_FILE, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    # ---------- Пароль ----------

    def has_password(self) -> bool:
        """Установлен ли пароль?"""
        return "password_hash" in self._data

    def set_password(self, password: str):
        """Установить пароль (сохраняется только хеш)."""
        self._data["password_hash"] = hash_password(password)
        self._data["password_set_at"] = datetime.now().isoformat()
        self._save()

    def check_password(self, password: str) -> bool:
        """Проверить пароль."""
        stored = self._data.get("password_hash")
        if not stored:
            return False
        return verify_password(password, stored)

    def reset_password(self):
        """Удалить пароль (для отладки)."""
        self._data.pop("password_hash", None)
        self._save()

    # ---------- Привязка к ПК ----------

    def get_machine_id(self) -> str:
        """
        Стабильный уникальный ID машины.

        Используется ПЕРВЫЙ доступный источник:

          1. MachineGuid (реестр Windows) — самый стабильный
          2. Серийный номер тома C:      — если нет MachineGuid
          3. ProcessorId CPU             — если нет первых двух
          4. Fallback: hostname + OS     — крайний случай

        Если комбинировать источники в один хеш, то изменение
        любого из них ломает лицензию,
        даже когда MachineGuid остаётся тем же.

        MAC-адрес (uuid.getnode) НЕ используется — он меняется
        при смене Wi-Fi/Ethernet/VPN.
        """
        # 1. MachineGuid — основной источник
        guid = _get_machine_guid()
        if guid:
            source = f"guid:{guid}"
        else:
            # 2. Серийный номер тома C:
            serial = _get_volume_serial()
            if serial:
                source = f"vol:{serial}"
            else:
                # 3. ProcessorId
                cpu = _get_cpu_id()
                if cpu:
                    source = f"cpu:{cpu}"
                else:
                    # 4. Fallback
                    source = f"node:{platform.node()}|os:{platform.platform()}"

        raw = f"ExcelAnalyzer::machine_id::v2|{source}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def has_license(self) -> bool:
        """Есть ли файл лицензии?"""
        return LICENSE_FILE.exists()

    def create_license(self):
        """Создать лицензию для текущей машины."""
        license_data = {
            "machine_id": self.get_machine_id(),
            "created_at": datetime.now().isoformat(),
            "hostname": platform.node(),
            "os": platform.system() + " " + platform.release(),
        }
        with open(LICENSE_FILE, "w", encoding="utf-8") as f:
            json.dump(license_data, f, indent=2)

    def verify_license(self) -> bool:
        """Проверить, что лицензия подходит этой машине."""
        if not LICENSE_FILE.exists():
            return False

        try:
            with open(LICENSE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("machine_id") == self.get_machine_id()
        except Exception:
            return False

    def delete_license(self):
        """Удалить лицензию."""
        if LICENSE_FILE.exists():
            LICENSE_FILE.unlink()

    # ---------- Логи попыток ----------

    def log_failed_attempt(self):
        """Записать неудачную попытку входа."""
        attempts = self._data.get("failed_attempts", [])
        attempts.append({
            "time": datetime.now().isoformat(),
            "machine_id": self.get_machine_id(),
        })
        self._data["failed_attempts"] = attempts[-100:]
        self._save()

    def get_failed_attempts(self) -> list:
        """Получить список неудачных попыток."""
        return self._data.get("failed_attempts", [])

    def clear_failed_attempts(self):
        """Очистить логи попыток."""
        self._data["failed_attempts"] = []
        self._save()


# ============================================================
# Глобальный экземпляр
# ============================================================

_security = None


def get_security() -> SecurityStore:
    """Получить глобальный экземпляр SecurityStore."""
    global _security
    if _security is None:
        _security = SecurityStore()
    return _security