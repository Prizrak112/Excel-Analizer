"""
Менеджер загруженных файлов.
Хранит несколько LoadedData + историю операций для каждого.
"""

import uuid
from dataclasses import dataclass
from src.core.data_loader import LoadedData
from src.core.history import HistoryManager
from src.core.operations import OperationHistory


@dataclass
class FileEntry:
    """Один загруженный файл + его состояние."""
    
    id: str
    data: LoadedData
    history: HistoryManager
    operations: OperationHistory
    display_name: str = ""
    is_modified: bool = False
    
    def __post_init__(self):
        if not self.display_name:
            from pathlib import Path
            self.display_name = Path(self.data.source_path).name


class FileManager:
    """Менеджер загруженных файлов."""
    
    def __init__(self):
        self._files: dict[str, FileEntry] = {}
        self._order: list[str] = []
        self._active_id: str | None = None
    
    # ---------- Добавление ----------
    
    def add_file(self, data: LoadedData) -> str:
        """Добавить файл. Возвращает его ID."""
        file_id = uuid.uuid4().hex[:8]
        
        entry = FileEntry(
            id=file_id,
            data=data,
            history=HistoryManager(max_size=50),
            operations=OperationHistory(),
        )
        
        self._files[file_id] = entry
        self._order.append(file_id)
        self._active_id = file_id
        
        print(f"[FileManager] Добавлен файл: {entry.display_name} (id={file_id})")
        return file_id
    
    # ---------- Получение ----------
    
    def get_active(self) -> FileEntry | None:
        if self._active_id is None:
            return None
        return self._files.get(self._active_id)
    
    def get_active_id(self) -> str | None:
        return self._active_id
    
    def get_file(self, file_id: str) -> FileEntry | None:
        return self._files.get(file_id)
    
    def get_all(self) -> list[FileEntry]:
        return [self._files[fid] for fid in self._order if fid in self._files]
    
    def count(self) -> int:
        return len(self._files)
    
    # ---------- Переключение ----------
    
    def set_active(self, file_id: str) -> bool:
        if file_id not in self._files:
            return False
        self._active_id = file_id
        print(f"[FileManager] Активный файл: {self._files[file_id].display_name}")
        return True
    
    # ---------- Удаление ----------
    
    def remove_file(self, file_id: str) -> bool:
        if file_id not in self._files:
            return False
        
        name = self._files[file_id].display_name
        del self._files[file_id]
        self._order.remove(file_id)
        
        if self._active_id == file_id:
            self._active_id = self._order[0] if self._order else None
        
        print(f"[FileManager] Удалён файл: {name}")
        return True
    
    def remove_all(self):
        self._files.clear()
        self._order.clear()
        self._active_id = None
    
    # ---------- Изменения ----------
    
    def mark_modified(self, file_id: str | None = None):
        fid = file_id or self._active_id
        if fid and fid in self._files:
            self._files[fid].is_modified = True
    
    def has_unsaved_changes(self) -> bool:
        return any(f.is_modified for f in self._files.values())

        # ---------- Восстановление из проекта ----------

    def restore_from_entries(
        self,
        entries: list,
        active_id: str | None = None,
    ) -> bool:
        """
        Полностью заменить текущее состояние набором FileEntry.
        Используется при открытии .eaproj.
        """
        self._files.clear()
        self._order.clear()
        self._active_id = None

        for entry in entries:
            self._files[entry.id] = entry
            self._order.append(entry.id)

        if active_id and active_id in self._files:
            self._active_id = active_id
        elif self._order:
            self._active_id = self._order[0]

        print(f"[FileManager] Восстановлено из проекта: {len(entries)} файлов")
        return True
    
    def mark_saved(self, file_id: str | None = None):
        """Пометить файл как сохранённый."""
        fid = file_id or self._active_id
        if fid and fid in self._files:
            self._files[fid].is_modified = False