"""
Управление источниками данных конструктора отчётов.
- Загрузка xlsx / csv / py.
- Кэш DataFrame по (source_id, sheet).
- Для python — запуск скрипта в subprocess, ожидание завершения,
  вывод сохраняется в Source.python_stdout / python_stderr.
"""

import os
import sys
import subprocess
import pandas as pd

from src.core.report.block_model import Source


class SourceManager:
    """Менеджер источников — загрузка и кэш."""

    def __init__(self):
        # Кэш: {source_id: {sheet_name: DataFrame}}
        self._cache: dict = {}

    # ============================================================
    # Загрузка
    # ============================================================

    def load_source(self, src: Source) -> tuple[bool, str]:
        """Загрузить источник. Возвращает (ok, message)."""
        if not src.path:
            return False, "Не указан путь к файлу"

        if not os.path.exists(src.path):
            return False, f"Файл не найден: {src.path}"

        try:
            if src.kind == "xlsx":
                return self._load_xlsx(src)
            elif src.kind == "csv":
                return self._load_csv(src)
            elif src.kind == "python":
                return self._load_python(src)
            else:
                return False, f"Неизвестный тип источника: {src.kind}"
        except Exception as e:
            import traceback
            traceback.print_exc()
            return False, f"{type(e).__name__}: {e}"

    # ── xlsx ──

    def _load_xlsx(self, src: Source) -> tuple[bool, str]:
        xls = pd.ExcelFile(src.path, engine="openpyxl")
        sheets = xls.sheet_names
        if not sheets:
            return False, "В файле нет листов"

        loaded = {}
        for sname in sheets:
            try:
                df = pd.read_excel(xls, sheet_name=sname)
                df = df.dropna(axis=1, how="all").dropna(axis=0, how="all")
                loaded[sname] = df
            except Exception as e:
                print(f"[SourceManager] Лист '{sname}' не загружен: {e}")

        if not loaded:
            return False, "Не удалось прочитать ни одного листа"

        src._cache = loaded
        self._cache[src.id] = loaded
        return True, f"Загружено листов: {len(loaded)}"

    # ── csv ──

    def _load_csv(self, src: Source) -> tuple[bool, str]:
        for enc in ("utf-8-sig", "utf-8", "cp1251"):
            for sep in (None, ",", ";", "\t"):
                try:
                    df = pd.read_csv(
                        src.path, encoding=enc, sep=sep,
                        engine="python" if sep is None else "c",
                    )
                    if len(df.columns) >= 1:
                        df = df.dropna(axis=1, how="all").dropna(axis=0, how="all")
                        src._cache = {"data": df}
                        self._cache[src.id] = src._cache
                        return True, f"Загружено: {len(df)} строк, {len(df.columns)} колонок"
                except Exception:
                    continue
        return False, "Не удалось прочитать csv"

    # ── python ──

    def _load_python(self, src: Source) -> tuple[bool, str]:
        """
        Запускаем .py в том же venv. Скрипт должен:
          - сохранить файл <script>_output.csv рядом, ИЛИ
          - напечатать JSON-список в stdout.
        """
        script = src.path
        base, _ = os.path.splitext(script)
        csv_out = base + "_output.csv"

        if os.path.exists(csv_out):
            try:
                df = pd.read_csv(csv_out)
                df = df.dropna(axis=1, how="all").dropna(axis=0, how="all")
                src._cache = {"data": df}
                self._cache[src.id] = src._cache
                return True, f"Загружено из {os.path.basename(csv_out)}"
            except Exception:
                pass

        python_exe = sys.executable
        try:
            res = subprocess.run(
                [python_exe, script],
                capture_output=True, text=True, timeout=120,
                cwd=os.path.dirname(script) or ".",
            )
        except subprocess.TimeoutExpired:
            return False, "Скрипт не завершился за 120 сек"

        src.python_stdout = res.stdout or ""
        src.python_stderr = res.stderr or ""

        if res.returncode != 0:
            return False, f"Скрипт упал (код {res.returncode}):\n{res.stderr[:500]}"

        if os.path.exists(csv_out):
            try:
                df = pd.read_csv(csv_out)
                df = df.dropna(axis=1, how="all").dropna(axis=0, how="all")
                src._cache = {"data": df}
                self._cache[src.id] = src._cache
                return True, f"Скрипт выполнен. Загружено из {os.path.basename(csv_out)}"
            except Exception as e:
                return False, f"csv создан, но не читается: {e}"

        import json
        try:
            data = json.loads(src.python_stdout.strip())
            if isinstance(data, list):
                df = pd.DataFrame(data)
                src._cache = {"data": df}
                self._cache[src.id] = src._cache
                return True, f"Скрипт выполнен. JSON из stdout: {len(df)} строк"
        except Exception:
            pass

        return False, (
            "Скрипт выполнен, но данных не найдено. "
            "Ожидается файл <script>_output.csv рядом или JSON в stdout."
        )

    # ============================================================
    # Получение DataFrame
    # ============================================================

    def get_df(self, src: Source, sheet: str | None = None) -> pd.DataFrame | None:
        cache = self._cache.get(src.id) or src._cache
        if not cache:
            return None
        if sheet is None:
            sheet = next(iter(cache.keys()), None)
        return cache.get(sheet)

    def get_sheets(self, src: Source) -> list[str]:
        cache = self._cache.get(src.id) or src._cache
        return list(cache.keys())

    # ============================================================
    # Очистка
    # ============================================================

    def unload(self, src_id: str):
        self._cache.pop(src_id, None)

    def clear(self):
        self._cache.clear()