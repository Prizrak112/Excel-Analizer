"""
Модель операций редактора.
Каждая команда создаёт Operation — запись о том, что сделал пользователь.
Из этих записей собирается .eaproj (инструкция).
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime


# ============================================================
# Operation — одна запись
# ============================================================

@dataclass
class Operation:
    """
    Одна операция пользователя.
    
    type: "delete_columns" | "rename_column" | 
          "cast_column" | "reorder_columns" | "toggle_column" | 
          "split_column" | "filter" | ...
    """
    
    type: str
    params: dict = field(default_factory=dict)
    id: str = ""
    timestamp: str = ""
    source_file_id: str = ""
    undone: bool = False
    
    def __post_init__(self):
        if not self.id:
            self.id = uuid.uuid4().hex[:8]
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
    
    def to_dict(self) -> dict:
        """Сериализация в JSON."""
        return {
            "id": self.id,
            "type": self.type,
            "params": self.params,
            "timestamp": self.timestamp,
            "source_file_id": self.source_file_id,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Operation":
        """Десериализация из JSON."""
        return cls(
            id=data.get("id", ""),
            type=data.get("type", ""),
            params=data.get("params", {}),
            timestamp=data.get("timestamp", ""),
            source_file_id=data.get("source_file_id", ""),
        )
    
    def describe(self) -> str:
        """Краткое описание для отображения."""
        t = self.type
        p = self.params
        
        if t == "toggle_column":
            action = "Показать" if p.get("visible") else "Скрыть"
            return f"{action} колонку «{p.get('column', '?')}»"
        
        elif t == "rename_column":
            return f"Переименовать «{p.get('column', '?')}» → «{p.get('new_name', '?')}»"
        
        elif t == "cast_column":
            return f"Преобразовать «{p.get('column', '?')}» в {p.get('new_dtype', '?')}"
        
        elif t == "reorder_columns":
            return "Изменить порядок колонок"
        
        elif t == "split_column":
            col = p.get("column", "?")
            mode = p.get("mode", "?")
            names = p.get("new_names", [])
            return f"Разделить «{col}» ({mode}) на {len(names)} частей"
        
        elif t == "delete_columns":
            cols = p.get("columns", [])
            return f"Удалить колонки: {', '.join(cols)}"
        
        elif t == "delete_rows":
            rows = p.get("rows", [])
            return f"Удалить {len(rows)} строк"
        
        elif t == "filter":
            col = p.get("column", "?")
            op = p.get("op", "?")
            val = p.get("value", "?")
            return f"Фильтр: {col} {op} {val}"
        
        elif t == "remove_duplicates":
            cols = p.get("columns", [])
            return f"Удалить дубликаты по {len(cols)} колонкам"
        
        elif t == "merge":
            sources = p.get("sources", [])
            return f"Объединить {len(sources)} файлов"
        
        elif t == "normalize_text":
            cols = p.get("columns", [])
            direction = p.get("direction", "lat2cyr")
            dir_label = "лат→кир" if direction == "lat2cyr" else "кир→лат"
            if len(cols) == 1:
                return f"Нормализовать «{cols[0]}» ({dir_label})"
            return f"Нормализовать {len(cols)} колонок ({dir_label})"
        
        elif t == "extract_text":
            cols = p.get("columns", [])
            pattern = p.get("pattern", "")
            if len(cols) == 1:
                return f"Извлечь по шаблону из «{cols[0]}»: {pattern}"
            return f"Извлечь по шаблону из {len(cols)} колонок: {pattern}"
        
        return f"Операция: {t}"


# ============================================================
# OperationHistory — история операций файла
# ============================================================

class OperationHistory:
    """История операций для одного файла."""
    
    def __init__(self):
        self._operations: list[Operation] = []
    
    # ---------- Добавление ----------
    
    def add(self, op: Operation):
        """Добавить операцию."""
        self._operations.append(op)
        print(f"[OpHistory] + {op.describe()}")
    
    def add_new(self, op_type: str, params: dict, file_id: str = "") -> Operation:
        """Создать и добавить операцию."""
        op = Operation(
            type=op_type,
            params=params,
            source_file_id=file_id,
        )
        self.add(op)
        return op
    
    # ---------- Получение ----------
    
    def get_all(self) -> list[Operation]:
        return list(self._operations)
    
    def count(self) -> int:
        return len(self._operations)
    
    def is_empty(self) -> bool:
        return len(self._operations) == 0
    
    def get_last(self) -> Operation | None:
        if self._operations:
            return self._operations[-1]
        return None
    
    # ---------- Отмена ----------
    
    def pop_last(self) -> Operation | None:
        """Удалить последнюю операцию (при undo)."""
        if self._operations:
            op = self._operations.pop()
            print(f"[OpHistory] − {op.describe()}")
            return op
        return None
    
    # ---------- Очистка ----------
    
    def clear(self):
        self._operations.clear()
        print("[OpHistory] Очищено")
    
    # ---------- Сериализация ----------
    
    def to_list(self) -> list[dict]:
        """Сериализация в список словарей."""
        return [op.to_dict() for op in self._operations]
    
    @classmethod
    def from_list(cls, data: list) -> "OperationHistory":
        """Десериализация."""
        history = cls()
        for op_data in data:
            history._operations.append(Operation.from_dict(op_data))
        return history


# ============================================================
# Глобальные типы операций (для валидации)
# ============================================================

OPERATION_TYPES = {
    # Данные
    "toggle_column":    "Показать/скрыть колонку",
    "rename_column":    "Переименовать колонку",
    "cast_column":      "Преобразовать тип",
    "reorder_columns":  "Порядок колонок",
    "split_column":     "Разделить колонку",
    "delete_columns":   "Удалить колонки",
    "delete_rows":      "Удалить строки",
    "filter":           "Фильтр",
    "remove_duplicates":"Удалить дубликаты",
    "merge":            "Объединить файлы",
    "add_column":       "Добавить колонку",
    "rename_file":      "Переименовать файл",
    "normalize_text":   "Нормализовать текст",
    "extract_text":     "Извлечь по шаблону",
}