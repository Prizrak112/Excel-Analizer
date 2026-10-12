"""
Шифрование данных для .eaproj.
AES-256-GCM + HKDF (machine) + Scrypt (password).

Формат зашифрованного блока:
    [12 байт nonce][ciphertext + 16 байт GCM-tag]
"""

import os
import json
import hashlib
from pathlib import Path

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    from cryptography.hazmat.primitives import hashes
    _CRYPTO_OK = True
except ImportError:
    _CRYPTO_OK = False


CONFIG_DIR = Path.home() / ".excel-analyzer"
SECURITY_FILE = CONFIG_DIR / "security.json"

# Параметры Scrypt (медленный — защита от брутфорса)
SCRYPT_N = 2 ** 14   # 16384
SCRYPT_R = 8
SCRYPT_P = 1

NONCE_LEN = 12
KEY_LEN = 32   # 256 бит
SALT_LEN = 16


def is_crypto_available() -> bool:
    return _CRYPTO_OK


def _require_crypto():
    if not _CRYPTO_OK:
        raise RuntimeError(
            "Библиотека 'cryptography' не установлена.\n"
            "Установите: pip install cryptography"
        )


# ============================================================
# Соль для machine-режима (хранится в security.json)
# ============================================================

def _load_security() -> dict:
    if SECURITY_FILE.exists():
        try:
            with open(SECURITY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_security(data: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(SECURITY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_or_create_machine_salt() -> bytes:
    """Соль для HKDF. Одна на всю машину/профиль."""
    data = _load_security()
    salt_hex = data.get("machine_id_salt")
    if salt_hex:
        return bytes.fromhex(salt_hex)

    salt = os.urandom(SALT_LEN)
    data["machine_id_salt"] = salt.hex()
    _save_security(data)
    return salt


# ============================================================
# Ключи
# ============================================================

def derive_machine_key() -> bytes:
    """
    Ключ, привязанный к машине.
    Из machine_id + machine_salt через HKDF-SHA256.
    """
    _require_crypto()

    from src.config.security import get_security
    machine_id = get_security().get_machine_id()

    salt = get_or_create_machine_salt()

    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=KEY_LEN,
        salt=salt,
        info=b"excel-analyzer::project::machine::v1",
    )
    return hkdf.derive(machine_id.encode("utf-8"))


def derive_password_key(password: str, salt: bytes) -> bytes:
    """
    Ключ из пароля пользователя через Scrypt.
    salt — хранится в manifest.json (не секрет).
    """
    _require_crypto()

    kdf = Scrypt(
        salt=salt,
        length=KEY_LEN,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
    )
    return kdf.derive(password.encode("utf-8"))


def generate_salt() -> bytes:
    return os.urandom(SALT_LEN)


# ============================================================
# Шифрование / расшифровка
# ============================================================

def encrypt_blob(plaintext: bytes, key: bytes) -> bytes:
    """
    AES-256-GCM.
    Результат: [nonce(12)][ciphertext][tag(16)]
    """
    _require_crypto()

    if len(key) != KEY_LEN:
        raise ValueError(f"Ключ должен быть {KEY_LEN} байт, получено {len(key)}")

    nonce = os.urandom(NONCE_LEN)
    aes = AESGCM(key)
    ciphertext = aes.encrypt(nonce, plaintext, associated_data=None)
    return nonce + ciphertext


def decrypt_blob(blob: bytes, key: bytes) -> bytes:
    """
    Расшифровка AES-256-GCM.
    Бросает ValueError, если ключ не подходит или данные повреждены.
    """
    _require_crypto()

    if len(key) != KEY_LEN:
        raise ValueError(f"Ключ должен быть {KEY_LEN} байт")

    if len(blob) < NONCE_LEN + 16:
        raise ValueError("Данные слишком короткие для GCM")

    nonce = blob[:NONCE_LEN]
    ciphertext = blob[NONCE_LEN:]

    aes = AESGCM(key)
    try:
        return aes.decrypt(nonce, ciphertext, associated_data=None)
    except Exception as e:
        raise ValueError(f"Не удалось расшифровать (неверный ключ или повреждены данные)") from e


# ============================================================
# Проверка пароля-маркера
# ============================================================

def make_password_check(password_key: bytes) -> str:
    """
    Короткий хэш для проверки правильности пароля.
    Не даёт узнать ключ, но позволяет отличить верный пароль от неверного
    до расшифровки всего файла.
    """
    return hashlib.sha256(password_key + b"::check::v1").hexdigest()[:16]