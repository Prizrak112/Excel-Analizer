"""
Глобальные настройки приложения.
Хранятся в ~/.excel-analyzer/settings.json
"""

import json
from pathlib import Path


SETTINGS_DIR = Path.home() / ".excel-analyzer"
SETTINGS_DIR.mkdir(exist_ok=True)
SETTINGS_FILE = SETTINGS_DIR / "settings.json"


class Settings:
    """Глобальные настройки приложения."""

    DEFAULTS = {
        "theme": "light",
        "language": "ru",
        "autosave": True,
        "autosave_interval": 300,
        "last_project_dir": "",       # последняя папка для .eaproj
        "last_project_file": "",      # последний открытый/сохранённый .eaproj
    }

    def __init__(self):
        self._data = self._load()

    def _load(self) -> dict:
        if SETTINGS_FILE.exists():
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    result = dict(self.DEFAULTS)
                    result.update(data)
                    return result
            except Exception:
                return dict(self.DEFAULTS)
        return dict(self.DEFAULTS)

    def _save(self):
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[Settings] Ошибка сохранения: {e}")

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value):
        self._data[key] = value
        self._save()

    # ---------- Тема ----------

    def get_theme_name(self) -> str:
        return self.get("theme", "light")

    def set_theme_name(self, name: str):
        self.set("theme", name)

    # ---------- Проекты .eaproj ----------

    def get_last_project_dir(self) -> str:
        """Последняя папка, где сохраняли/открывали проект."""
        return self.get("last_project_dir", "") or ""

    def set_last_project_dir(self, path: str):
        """Запомнить папку проекта."""
        self.set("last_project_dir", str(path) if path else "")

    def get_last_project_file(self) -> str:
        """Последний открытый/сохранённый файл .eaproj."""
        return self.get("last_project_file", "") or ""

    def set_last_project_file(self, path: str):
        """Запомнить путь к файлу проекта."""
        self.set("last_project_file", str(path) if path else "")


_settings = None


def get_settings() -> Settings:
    """Глобальный экземпляр настроек."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings