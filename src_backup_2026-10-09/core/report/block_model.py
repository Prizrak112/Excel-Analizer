"""
Модели данных конструктора HTML-отчётов.

Block         — один блок на холсте (KPI, график, таблица, текст).
Step          — один шаг цепочки преобразований (filter/groupby/agg/...).
Source        — источник данных (xlsx/csv/py).
ReportProject — проект отчёта целиком (источники + блоки + настройки).
"""

from dataclasses import dataclass, field, asdict
from typing import Any
import uuid
import json


# ============================================================
# Утилита — генерация id
# ============================================================

def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


# ============================================================
# Шаг цепочки преобразований
# ============================================================

@dataclass
class Step:
    """
    Один шаг цепочки «Data → Filter → Group → Agg → Chart».

    kind:
      - "filter"   — params: {"column": "Статус", "op": "==", "value": "Завершён"}
                     оп: ==, !=, >, >=, <, <=, in, not_in, contains, is_null, not_null
      - "groupby"  — params: {"columns": ["Регион", "Дата"]}
      - "agg"      — params: {"column": "Продажи", "func": "sum"}
                     func: sum, mean, count, min, max, median, std, nunique
      - "sort"     — params: {"column": "Дата", "asc": True}
      - "limit"    — params: {"n": 100, "tail": False}
      - "rename"   — params: {"mapping": {"old": "new"}}
      - "dropna"   — params: {"subset": ["Колонка"]}
    """
    kind: str
    params: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"kind": self.kind, "params": dict(self.params)}

    @classmethod
    def from_dict(cls, d: dict) -> "Step":
        return cls(kind=d.get("kind", ""), params=dict(d.get("params", {})))


# ============================================================
# Блок
# ============================================================

@dataclass
class Block:
    """
    Один блок отчёта (KPI / график / таблица / текст) на холсте.

    Позиция — абсолютные пиксели (свободное позиционирование, как в Figma).
    """

    id: str = field(default_factory=lambda: _new_id("blk"))
    type: str = "chart"          # "kpi" | "chart" | "table" | "text"

    # ── Источник данных ──
    source_id: str = ""          # id из SourceManager
    sheet: str | None = None     # имя листа (для xlsx)
    # Если source_id пусто, можно указать напрямую:
    inline_data: list | None = None   # сырой dict-список (редкий случай)

    # ── Цепочка преобразований (дерево ветвлений) ──
    steps: list[Step] = field(default_factory=list)

    # ── Специфика типа ──
    chart_type: str | None = None       # "line" | "bar" | "pie" | "scatter" | "table"
    chart_config: dict = field(default_factory=dict)

    kpi_config: dict = field(default_factory=dict)
    table_config: dict = field(default_factory=dict)
    text_config: dict = field(default_factory=dict)

    # ── Стили блока на холсте ──
    style: dict = field(default_factory=dict)

    # ── Позиция на холсте (пиксели) ──
    x: int = 20
    y: int = 20
    width: int = 400
    height: int = 300
    z_index: int = 0

    # ── Метаданные ──
    name: str = ""               # отображаемое имя блока
    locked: bool = False         # заблокирован от перемещения

    def __post_init__(self):
        if not self.name:
            self.name = {
                "kpi": "KPI",
                "chart": f"График: {self.chart_type or 'line'}",
                "table": "Таблица",
                "text": "Текст",
            }.get(self.type, "Блок")

    # ── Сериализация ──

    def to_dict(self) -> dict:
        d = asdict(self)
        d["steps"] = [s.to_dict() for s in self.steps]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Block":
        d = dict(d)
        d["steps"] = [Step.from_dict(s) for s in d.get("steps", [])]
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ============================================================
# Источник
# ============================================================

@dataclass
class Source:
    """
    Источник данных.
    kind: "xlsx" | "csv" | "python"
    """
    id: str = field(default_factory=lambda: _new_id("src"))
    kind: str = "xlsx"
    path: str = ""
    display_name: str = ""

    # Кэш загруженных DataFrame. Ключ — имя листа для xlsx,
    # для csv/py — единственный ключ "data".
    _cache: dict = field(default_factory=dict, repr=False)

    # Для python-скриптов: вывод print() последнего запуска
    python_stdout: str = ""
    python_stderr: str = ""

    def __post_init__(self):
        if not self.display_name:
            import os
            self.display_name = os.path.basename(self.path) or "(без имени)"

    def sheet_names(self) -> list[str]:
        return list(self._cache.keys())

    def get_df(self, sheet: str | None = None):
        if not self._cache:
            return None
        if sheet is None:
            sheet = next(iter(self._cache.keys()), None)
        return self._cache.get(sheet)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "path": self.path,
            "display_name": self.display_name,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Source":
        return cls(
            id=d.get("id", _new_id("src")),
            kind=d.get("kind", "xlsx"),
            path=d.get("path", ""),
            display_name=d.get("display_name", ""),
        )


# ============================================================
# Проект отчёта
# ============================================================

@dataclass
class ReportProject:
    """Проект отчёта целиком."""
    title: str = "Отчёт"
    sources: list[Source] = field(default_factory=list)
    blocks: list[Block] = field(default_factory=list)

    theme: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.theme:
            self.theme = {
                "bg": "#FFFFFF",
                "text": "#1A1A1A",
                "accent": "#87C800",
                "font": "Inter, -apple-system, sans-serif",
                "page_width": 1200,
            }

    # ── Источники ──

    def add_source(self, src: Source):
        self.sources.append(src)

    def remove_source(self, src_id: str) -> bool:
        for i, s in enumerate(self.sources):
            if s.id == src_id:
                self.sources.pop(i)
                for b in self.blocks:
                    if b.source_id == src_id:
                        b.source_id = ""
                        b.sheet = None
                return True
        return False

    def get_source(self, src_id: str) -> Source | None:
        for s in self.sources:
            if s.id == src_id:
                return s
        return None

    # ── Блоки ──

    def add_block(self, block: Block):
        self.blocks.append(block)

    def remove_block(self, block_id: str) -> bool:
        for i, b in enumerate(self.blocks):
            if b.id == block_id:
                self.blocks.pop(i)
                return True
        return False

    def get_block(self, block_id: str) -> Block | None:
        for b in self.blocks:
            if b.id == block_id:
                return b
        return None

    def next_z(self) -> int:
        if not self.blocks:
            return 0
        return max(b.z_index for b in self.blocks) + 1

    # ── Сериализация ──

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "theme": dict(self.theme),
            "sources": [s.to_dict() for s in self.sources],
            "blocks": [b.to_dict() for b in self.blocks],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ReportProject":
        p = cls(
            title=d.get("title", "Отчёт"),
            theme=dict(d.get("theme", {})),
        )
        for sd in d.get("sources", []):
            p.sources.append(Source.from_dict(sd))
        for bd in d.get("blocks", []):
            p.blocks.append(Block.from_dict(bd))
        return p

    def save(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: str) -> "ReportProject":
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        return cls.from_dict(d)