"""
Сохранение и загрузка проектов .eaproj.

Формат: ZIP с двумя файлами:
    manifest.json   — открытая служебная информация (без данных и путей)
    payload.enc     — зашифрованный блоб: pickle → zlib → AES-256-GCM
"""

import io
import os
import json
import pickle
import zlib
import zipfile
from datetime import datetime
from pathlib import Path

from src.core.crypto import (
    encrypt_blob,
    decrypt_blob,
    derive_machine_key,
    derive_password_key,
    generate_salt,
    make_password_check,
    is_crypto_available,
)
from src.core.data_loader import LoadedData
from src.core.file_manager import FileEntry
from src.core.history import HistoryManager
from src.core.operations import OperationHistory, Operation


FORMAT_VERSION = 1
APP_NAME = "Excel Analyzer"
PICKLE_PROTOCOL = 5
ZLIB_LEVEL = 6


# ============================================================
# Ошибки
# ============================================================

class ProjectError(Exception):
    """Ошибка сохранения/загрузки проекта."""


class WrongPasswordError(ProjectError):
    """Неверный пароль для .eaproj."""


class WrongMachineError(ProjectError):
    """Проект зашифрован для другого ПК."""


# ============================================================
# Сериализация одной записи
# ============================================================

def _entry_to_dict(entry: FileEntry) -> dict:
    """Превратить FileEntry в словарь для pickle."""
    data = entry.data

    # DataFrame — через pickle в bytes
    df_bytes = pickle.dumps(data.dataframe, protocol=PICKLE_PROTOCOL)

    return {
        "id": entry.id,
        "display_name": entry.display_name,
        "is_modified": entry.is_modified,
        # LoadedData
        "source_path": data.source_path,
        "sheet_name": data.sheet_name,
        "dataframe_pickle": df_bytes,
        "columns": list(data.columns),
        "dtypes": dict(data.dtypes),
        "rows_count": data.rows_count,
        "cols_count": data.cols_count,
        "column_order": list(data.column_order),
        "visible_columns": list(data.visible_columns),
        "column_meta": dict(data.column_meta),
        "column_filters": dict(data.column_filters),
        # История операций
        "operations": entry.operations.to_list(),
    }


def _dict_to_entry(d: dict) -> FileEntry:
    """Восстановить FileEntry из словаря."""
    import pandas as pd

    df = pickle.loads(d["dataframe_pickle"])

    data = LoadedData(
        source_path=d["source_path"],
        sheet_name=d.get("sheet_name"),
        dataframe=df,
        columns=list(d["columns"]),
        dtypes=dict(d["dtypes"]),
        rows_count=int(d["rows_count"]),
        cols_count=int(d["cols_count"]),
        column_order=list(d.get("column_order", [])),
        visible_columns=list(d.get("visible_columns", [])),
        column_meta=dict(d.get("column_meta", {})),
        column_filters=dict(d.get("column_filters", {})),
    )

    # Восстанавливаем привязку операций к файлу
    ops = OperationHistory.from_list(d.get("operations", []))
    data.file_id = d["id"]
    data.operations = ops

    entry = FileEntry(
        id=d["id"],
        data=data,
        history=HistoryManager(max_size=50),  # пустая — Undo не сохраняется между сессиями
        operations=ops,
        display_name=d.get("display_name", Path(d["source_path"]).name),
        is_modified=bool(d.get("is_modified", False)),
    )
    return entry


# ============================================================
# Проверка содержимого
# ============================================================

def _build_manifest(
    entries: list[dict],
    encryption: str,
    salt_hex: str,
    check: str,
    extra: dict,
) -> dict:
    files_meta = []
    for d in entries:
        files_meta.append({
            "id": d["id"],
            "name": Path(d["source_path"]).name if d["source_path"] else d["display_name"],
            "rows": d["rows_count"],
            "cols": d["cols_count"],
        })

    return {
        "app": APP_NAME,
        "format_version": FORMAT_VERSION,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "encryption": encryption,       # "machine" | "password"
        "salt": salt_hex,
        "check": check,
        "file_count": len(entries),
        "files": files_meta,
        "extra": {
            "active_tab": int(extra.get("active_tab", 0)),
            "theme": extra.get("theme", "dark"),
        },
    }


# ============================================================
# Публичный API
# ============================================================

class ProjectIO:
    """Статические методы для сохранения/загрузки .eaproj."""

    @staticmethod
    def save(
        path: str,
        entries: list[FileEntry],
        active_file_id: str | None = None,
        extra: dict | None = None,
        password: str | None = None,
    ) -> tuple[bool, str]:
        """
        Сохранить проект.

        path — куда сохранить (.eaproj)
        entries — список FileEntry
        active_file_id — какой файл сделать активным
        extra — dict с active_tab, theme и т.п.
        password — если задан, режим password; иначе machine

        Возвращает (успех, сообщение).
        """
        if not is_crypto_available():
            return False, "Библиотека 'cryptography' не установлена"

        if not entries:
            return False, "Нет открытых файлов для сохранения"

        extra = extra or {}

        try:
            # 1. Сериализуем всё в один словарь
            entries_dicts = [_entry_to_dict(e) for e in entries]

            state = {
                "app": APP_NAME,
                "format_version": FORMAT_VERSION,
                "created_at": datetime.now().isoformat(),
                "active_file_id": active_file_id,
                "files": entries_dicts,
                "extra": dict(extra),
            }

            # 2. Сжатие + шифрование
            raw = pickle.dumps(state, protocol=PICKLE_PROTOCOL)
            compressed = zlib.compress(raw, level=ZLIB_LEVEL)

            if password:
                encryption = "password"
                salt = generate_salt()
                key = derive_password_key(password, salt)
                salt_hex = salt.hex()
                check = make_password_check(key)
            else:
                encryption = "machine"
                salt = generate_salt()
                # Ключ привязан к machine_id
                key = derive_machine_key()
                # В manifest пишем соль — она используется только для информации
                salt_hex = salt.hex()
                check = make_password_check(key)

            encrypted = encrypt_blob(compressed, key)

            # 3. manifest.json (открытый)
            manifest = _build_manifest(entries_dicts, encryption, salt_hex, check, extra)
            manifest_bytes = json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8")

            # 4. Упаковка в ZIP
            tmp = str(path) + ".tmp"
            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr("manifest.json", manifest_bytes)
                z.writestr("payload.enc", encrypted)

            # Атомарная замена
            os.replace(tmp, path)

            size_kb = os.path.getsize(path) / 1024
            return True, (
                f"Проект сохранён ({size_kb:.0f} КБ, "
                f"{'пароль' if password else 'машина'})"
            )

        except Exception as e:
            import traceback
            traceback.print_exc()
            return False, f"Ошибка сохранения: {type(e).__name__}: {e}"

    @staticmethod
    def load(
        path: str,
        password: str | None = None,
    ) -> tuple[dict | None, str]:
        """
        Загрузить проект.

        Возвращает (state, сообщение).
        state — словарь:
            {
                "entries": [FileEntry, ...],
                "active_file_id": str | None,
                "extra": dict,
                "manifest": dict,
            }
        При ошибке state=None, а сообщение — причина.
        """
        if not is_crypto_available():
            return None, "Библиотека 'cryptography' не установлена"

        if not os.path.exists(path):
            return None, f"Файл не найден: {path}"

        try:
            with zipfile.ZipFile(path, "r") as z:
                # 1. manifest
                try:
                    manifest_bytes = z.read("manifest.json")
                    manifest = json.loads(manifest_bytes.decode("utf-8"))
                except KeyError:
                    return None, "Неверный формат файла: нет manifest.json"

                # 2. payload.enc
                try:
                    encrypted = z.read("payload.enc")
                except KeyError:
                    return None, "Неверный формат файла: нет payload.enc"

            # 3. Проверка версии
            fmt_ver = int(manifest.get("format_version", 0))
            if fmt_ver != FORMAT_VERSION:
                return None, (
                    f"Формат проекта не поддерживается "
                    f"(v{fmt_ver}, ожидается v{FORMAT_VERSION})"
                )

            encryption = manifest.get("encryption", "machine")
            salt_hex = manifest.get("salt", "")
            expected_check = manifest.get("check", "")

            # 4. Определяем ключ
            if encryption == "password":
                if not password:
                    return None, "PASSWORD_REQUIRED"
                salt = bytes.fromhex(salt_hex)
                key = derive_password_key(password, salt)
            elif encryption == "machine":
                key = derive_machine_key()
            else:
                return None, f"Неизвестный режим шифрования: {encryption}"

            # 5. Проверка правильности ключа
            actual_check = make_password_check(key)
            if actual_check != expected_check:
                if encryption == "password":
                    return None, "PASSWORD_WRONG"
                else:
                    return None, "MACHINE_MISMATCH"

            # 6. Расшифровка
            try:
                compressed = decrypt_blob(encrypted, key)
            except Exception:
                if encryption == "password":
                    return None, "PASSWORD_WRONG"
                else:
                    return None, "MACHINE_MISMATCH"

            # 7. Декомпрессия + распаковка
            raw = zlib.decompress(compressed)
            state = pickle.loads(raw)

            # 8. Восстановление FileEntry
            entries = [_dict_to_entry(d) for d in state.get("files", [])]

            return {
                "entries": entries,
                "active_file_id": state.get("active_file_id"),
                "extra": state.get("extra", {}),
                "manifest": manifest,
            }, "OK"

        except Exception as e:
            import traceback
            traceback.print_exc()
            return None, f"Ошибка чтения: {type(e).__name__}: {e}"

    # ---------- Быстрая проверка (без расшифровки) ----------

    @staticmethod
    def peek(path: str) -> dict | None:
        """Прочитать только manifest — без расшифровки."""
        if not os.path.exists(path):
            return None
        try:
            with zipfile.ZipFile(path, "r") as z:
                mb = z.read("manifest.json")
                return json.loads(mb.decode("utf-8"))
        except Exception:
            return None