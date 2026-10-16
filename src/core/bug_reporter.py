"""
Автоматический генератор баг-репортов для NexGrid.
Сохраняет диагностические файлы (.md и .json) в папку bug_reports/ для быстрой починки багов.
"""

import sys
import json
import platform
import traceback
from pathlib import Path
from datetime import datetime


class BugReporter:
    REPORTS_DIR = Path("bug_reports")
    _context_callbacks: list = []
    _installed: bool = False

    @classmethod
    def register_context_provider(cls, provider_fn):
        """Регистрирует колбэк, возвращающий словарь состояния вкладки (report, dataframe и т.д.)."""
        if provider_fn not in cls._context_callbacks:
            cls._context_callbacks.append(provider_fn)
        if not cls._installed:
            cls.install_excepthook()

    @classmethod
    def install_excepthook(cls):
        cls.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        sys.excepthook = cls._excepthook
        cls._installed = True

    @classmethod
    def _excepthook(cls, exc_type, exc_value, exc_tb):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        cls.capture_exception(exc_value, where="Uncaught Exception (sys.excepthook)", tb=exc_tb)

    @classmethod
    def capture_exception(
        cls,
        exc: BaseException,
        where: str = "",
        extra: dict | None = None,
        tb=None,
    ) -> Path | None:
        try:
            cls.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
            now = datetime.now()
            ts = now.strftime("%Y%m%d_%H%M%S")
            exc_name = type(exc).__name__

            if tb is None:
                tb = exc.__traceback__

            tb_str = "".join(traceback.format_exception(type(exc), exc, tb))

            # Собираем локальные переменные из фрейма, где упала ошибка
            crash_frame_info = {}
            if tb is not None:
                cur = tb
                while cur.tb_next is not None:
                    cur = cur.tb_next
                f = cur.tb_frame
                crash_frame_info = {
                    "file": f.f_code.co_filename,
                    "line": cur.tb_lineno,
                    "function": f.f_code.co_name,
                    "locals": {},
                }
                for k, v in f.f_locals.items():
                    if k.startswith("__"):
                        continue
                    try:
                        crash_frame_info["locals"][k] = repr(v)[:500]
                    except Exception:
                        crash_frame_info["locals"][k] = "<unserializable>"

            # Собираем контекст из зарегистрированных вкладок
            merged_ctx = {}
            for cb in cls._context_callbacks:
                try:
                    data = cb() or {}
                    merged_ctx.update(data)
                except Exception as e:
                    merged_ctx["context_error"] = str(e)

            payload = {
                "timestamp": now.isoformat(),
                "where": where,
                "exception_type": exc_name,
                "exception_message": str(exc),
                "system": {
                    "python": sys.version,
                    "platform": platform.platform(),
                },
                "crash_frame": crash_frame_info,
                "traceback": tb_str,
                "dataframe_info": merged_ctx.get("dataframe_info", {}),
                "report_state": merged_ctx.get("report_state", {}),
                "extra": extra or {},
            }

            base_name = f"bug_{ts}_{exc_name}"
            json_path = cls.REPORTS_DIR / f"{base_name}.json"
            md_path = cls.REPORTS_DIR / f"{base_name}.md"

            json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            md_path.write_text(
                cls._format_markdown(payload, merged_ctx.get("generated_code", "")),
                encoding="utf-8",
            )
            print(f"[BugReporter] Отчёт об ошибке сохранён: {md_path}")
            return md_path

        except Exception as err:
            print(f"[BugReporter] Не удалось записать баг-репорт: {err}")
            return None

    @staticmethod
    def _format_markdown(payload: dict, code: str) -> str:
        cf = payload.get("crash_frame", {})
        
        # Предварительно извлекаем все данные, чтобы не ломать f-строку
        exc_type = payload.get("exception_type", "?")
        ts = payload.get("timestamp", "?")
        where = payload.get("where", "?")
        exc_msg = payload.get("exception_message", "?")
        
        file_path = cf.get("file", "?")
        line_num = cf.get("line", "?")
        func_name = cf.get("function", "?")
        
        tb_text = payload.get("traceback", "").strip()
        
        locals_json = json.dumps(cf.get("locals", {}), ensure_ascii=False, indent=2)
        report_json = json.dumps(payload.get("report_state", {}), ensure_ascii=False, indent=2)
        df_json = json.dumps(payload.get("dataframe_info", {}), ensure_ascii=False, indent=2)
        
        code_text = code if code else "# Скрипт пуст"
        
        # Безопасная сборка строк без тройных кавычек
        return (
            f"# 🐞 Баг-репорт NexGrid: `{exc_type}`\n\n"
            f"- **Дата:** `{ts}`\n"
            f"- **Место сбоя:** `{where}`\n"
            f"- **Ошибка:** `{exc_msg}`\n"
            f"- **Файл:** `{file_path}` (строка **{line_num}**, в `{func_name}`)\n\n"
            f"## 1. Traceback\n"
            f"```text\n{tb_text}\n```\n\n"
            f"## 2. Локальные переменные в точке падения\n"
            f"```json\n{locals_json}\n```\n\n"
            f"## 3. Состояние конструктора отчёта (Report)\n"
            f"```json\n{report_json}\n```\n\n"
            f"## 4. Данные (DataFrame)\n"
            f"```json\n{df_json}\n```\n\n"
            f"## 5. Сгенерированный Python-скрипт на момент сбоя\n"
            f"```python\n{code_text}\n```\n"
        )