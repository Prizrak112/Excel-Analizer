"""Скачивает canvas-datagrid с нескольких зеркал, с таймаутом."""
import urllib.request
from pathlib import Path

URLS = [
    "https://cdn.jsdelivr.net/npm/canvas-datagrid@1.6.2/dist/canvas-datagrid.js",
    "https://unpkg.com/canvas-datagrid@1.6.2/dist/canvas-datagrid.js",
    "https://cdnjs.cloudflare.com/ajax/libs/canvas-datagrid/1.6.2/canvas-datagrid.js",
]

DEST = Path("src/assets/canvas-datagrid.js")
DEST.parent.mkdir(parents=True, exist_ok=True)

for url in URLS:
    print(f"Пробую: {url}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = r.read()
        if len(data) < 10_000:
            print(f"  ⚠ Файл слишком маленький ({len(data)} байт) — пропускаю")
            continue
        DEST.write_bytes(data)
        print(f"  ✅ Сохранён: {DEST}  ({len(data):,} байт)")
        break
    except Exception as e:
        print(f"  ❌ {type(e).__name__}: {e}")

if DEST.exists():
    print(f"\nГотово: {DEST}  ({DEST.stat().st_size:,} байт)")
else:
    print("\nНе удалось скачать ни с одного зеркала.")