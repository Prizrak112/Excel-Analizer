"""Одноразовый скрипт: качает Tabulator в src/assets/."""
from pathlib import Path
import urllib.request

URLS = {
    "tabulator.min.js":  "https://unpkg.com/tabulator-tables@6.3.0/dist/js/tabulator.min.js",
    "tabulator.min.css": "https://unpkg.com/tabulator-tables@6.3.0/dist/css/tabulator.min.css",
}

ASSETS = Path(__file__).parent / "src" / "assets"
ASSETS.mkdir(parents=True, exist_ok=True)

for name, url in URLS.items():
    dest = ASSETS / name
    print(f"Скачиваю {name} ...")
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            data = r.read()
        dest.write_bytes(data)
        print(f"  ✅ {dest}  ({len(data):,} байт)")
    except Exception as e:
        print(f"  ❌ Ошибка: {type(e).__name__}: {e}")

print("\nГотово.")