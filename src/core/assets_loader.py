"""
Загрузка встроенных ассетов (Tabulator и др.) для экспорта HTML.

Файлы лежат в src/assets/ и читаются один раз, потом кешируются.
Используется в template_engine для вшивания JS/CSS в автономный HTML.
"""

from functools import lru_cache
from pathlib import Path
import sys


def _resolve_assets_dir() -> Path:
    """Находит папку src/assets при обычном запуске и внутри PyInstaller --onefile."""
    candidates: list[Path] = []

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        base = Path(meipass)
        candidates.append(base / "src" / "assets")
        candidates.append(base / "assets")

    file_path = globals().get("__file__")
    if file_path:
        candidates.append(Path(file_path).resolve().parent.parent / "assets")

    exe_dir = Path(sys.executable).resolve().parent
    candidates.append(exe_dir / "src" / "assets")
    candidates.append(Path.cwd() / "src" / "assets")

    for cand in candidates:
        if cand.is_dir():
            return cand
    return candidates[0] if candidates else Path("src/assets")


_ASSETS_DIR = _resolve_assets_dir()


@lru_cache(maxsize=8)
def load_asset(name: str) -> str:
    """
    Прочитать ассет из src/assets/name как UTF-8.
    Возвращает пустую строку, если файл не найден.
    """
    path = _ASSETS_DIR / name
    if not path.is_file():
        print(f"[assets_loader] Ассет не найден: {path}")
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"[assets_loader] Не удалось прочитать {path}: {e}")
        return ""


def tabulator_css() -> str:
    """CSS Tabulator (для вставки в <style>)."""
    return load_asset("tabulator.min.css")


def tabulator_js() -> str:
    """JS Tabulator (для вставки в <script>)."""
    return load_asset("tabulator.min.js")

def canvas_datagrid_js() -> str:
    """JS canvas-datagrid (для вставки в <script>)."""
    return load_asset("canvas-datagrid.js")


def assets_dir() -> Path:
    """Путь к папке с ассетами (для диагностики)."""
    return _ASSETS_DIR