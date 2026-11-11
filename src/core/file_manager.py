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
    def get_files_dict(self) -> dict[str, list[str]]:
        """
        Возвращает словарь вида:
        { "Имя_файла.xlsx": ["Лист1", "Лист2"] }
        для удобного отображения в инспекторе.
        """
        result = {}
        for entry in self.get_all():
            # Извлекаем чистое имя файла из source_path или display_name
            import os
            file_name = os.path.basename(entry.data.source_path) if entry.data.source_path else "Проект"
            sheet_name = getattr(entry.data, "sheet_name", None) or "Sheet1"
            
            if file_name not in result:
                result[file_name] = []
            if sheet_name not in result[file_name]:
                result[file_name].append(sheet_name)
        return result
    
    def add_file(self, data: LoadedData) -> str:
        """Добавить файл с учетом выбранного листа. Возвращает его ID."""
        import os
        sheet_name = data.sheet_name or "Sheet1"
        
        # Проверяем, не открыт ли уже этот же файл с этим же листом
        for fid, existing_entry in self._files.items():
            if (existing_entry.data.source_path == data.source_path and 
                (existing_entry.data.sheet_name or "Sheet1") == sheet_name):
                self._active_id = fid
                print(f"[FileManager] Лист уже открыт, активирован существующий: {existing_entry.display_name} [{sheet_name}] (id={fid})")
                return fid

        # Иначе генерируем уникальный ID для новой комбинации файл + лист
        file_id = uuid.uuid4().hex[:8]
        
        # Безопасно получаем имя файла через стандартный os.path (без зависимостей от Path)
        base_name = os.path.basename(data.source_path)
        display_name = f"{base_name} [{sheet_name}]"
        
        entry = FileEntry(
            id=file_id,
            data=data,
            history=HistoryManager(max_size=50),
            operations=OperationHistory(),
            display_name=display_name,
        )
        
        self._files[file_id] = entry
        self._order.append(file_id)
        self._active_id = file_id
        
        print(f"[FileManager] Добавлен файл: {display_name} (id={file_id})")
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
        else:
            self._active_id = None

        print(f"[FileManager] Восстановлено из проекта: {len(entries)} файлов")
        return True
    
    def mark_saved(self, file_id: str | None = None):
        """Пометить файл как сохранённый."""
        fid = file_id or self._active_id
        if fid and fid in self._files:
            self._files[fid].is_modified = False

    # ============================================================
    # Доступ к файлам и листам для Конструктора
    # ============================================================

    def get_files_dict(self) -> dict[str, list[str]]:
        """
        Возвращает словарь {имя_файла: [список_всех_листов]}.
        Собирает открытые листы в памяти, extra_sheets и все листы исходного Excel-файла.
        """
        import os
        from src.core.data_loader import DataLoader

        if not hasattr(self, "_excel_sheets_cache"):
            self._excel_sheets_cache = {}

        result: dict[str, list[str]] = {}
        for entry in self.get_all():
            src_path = entry.data.source_path or ""
            file_name = os.path.basename(src_path) if src_path else entry.display_name
            if file_name not in result:
                result[file_name] = []

            # 1. Листы уже в памяти LoadedData (активный + extra_sheets)
            for s_name in entry.data.list_sheets():
                if s_name and s_name not in result[file_name]:
                    result[file_name].append(s_name)

            # 2. Все остальные листы из самого файла Excel на диске
            if src_path and os.path.exists(src_path):
                if src_path not in self._excel_sheets_cache:
                    try:
                        self._excel_sheets_cache[src_path] = DataLoader.get_excel_sheets(src_path)
                    except Exception:
                        self._excel_sheets_cache[src_path] = []
                for disk_sheet in self._excel_sheets_cache[src_path]:
                    if disk_sheet not in result[file_name]:
                        result[file_name].append(disk_sheet)

        return result

    def get_default_file_and_sheet(self) -> tuple[str, str]:
        """Возвращает (имя_файла, имя_листа) по умолчанию для новых блоков."""
        import os
        active = self.get_active()
        if active and active.data:
            f_name = os.path.basename(active.data.source_path) if active.data.source_path else active.display_name
            s_name = active.data.sheet_name or "Sheet1"
            return f_name, s_name

        files_dict = self.get_files_dict()
        for f_name, sheets in files_dict.items():
            if sheets:
                return f_name, sheets[0]
            return f_name, "Sheet1"
        return "", ""

    def get_dataframe(self, file_name: str = "", sheet_name: str = ""):
        """
        Возвращает DataFrame для конкретного файла и листа (независимо от активного файла).
        Если лист ещё не был открыт в Редакторе, прозрачно загружает и кэширует его из файла.
        """
        import os
        from src.core.data_loader import DataLoader

        if not hasattr(self, "_lazy_loaded_sheets"):
            self._lazy_loaded_sheets = {}

        entries = self.get_all()
        if not entries:
            return None

        def _apply_renames(data_obj, df, s_name):
            if df is None:
                return None
            cur_s = data_obj.sheet_name or "Sheet1"
            if s_name == cur_s and getattr(data_obj, "column_meta", None):
                rename_map = {
                    c: data_obj.get_display_name(c)
                    for c in df.columns
                    if data_obj.get_display_name(c) != c
                }
                if rename_map:
                    return df.rename(columns=rename_map)
            elif s_name in getattr(data_obj, "sheet_states", {}):
                saved_meta = data_obj.sheet_states[s_name].get("column_meta", {})
                rename_map = {
                    c: saved_meta[c].get("display_name", c)
                    for c in df.columns
                    if c in saved_meta and saved_meta[c].get("display_name")
                }
                if rename_map:
                    return df.rename(columns=rename_map)
            return df

        # Фильтруем записи по имени файла (если указано)
        matched_entries = []
        for entry in entries:
            src_path = entry.data.source_path or ""
            base_name = os.path.basename(src_path) if src_path else entry.display_name
            if not file_name or file_name == base_name or file_name == entry.display_name:
                matched_entries.append(entry)

        if not matched_entries:
            matched_entries = entries

        # Если лист не задан — берем первый найденный в подходящем файле
        if not sheet_name:
            first_entry = matched_entries[0]
            s_name = first_entry.data.sheet_name or "Sheet1"
            return _apply_renames(first_entry.data, first_entry.data.dataframe, s_name)

        # 1. Ищем лист среди уже загруженных FileEntry и их extra_sheets
        for entry in matched_entries:
            cur_sheet = entry.data.sheet_name or "Sheet1"
            if cur_sheet == sheet_name:
                return _apply_renames(entry.data, entry.data.dataframe, sheet_name)
            if sheet_name in entry.data.extra_sheets:
                return _apply_renames(entry.data, entry.data.extra_sheets[sheet_name], sheet_name)

        # 2. Если лист есть в Excel-файле на диске, но не был открыт в Редакторе — подгружаем
        for entry in matched_entries:
            src_path = entry.data.source_path
            if src_path and os.path.exists(src_path):
                cache_key = (src_path, sheet_name)
                if cache_key not in self._lazy_loaded_sheets:
                    try:
                        loaded = DataLoader.load(src_path, sheet_name)
                        self._lazy_loaded_sheets[cache_key] = loaded.dataframe
                    except Exception as e:
                        print(f"[FileManager] Не удалось подгрузить лист '{sheet_name}' из '{src_path}': {e}")
                        self._lazy_loaded_sheets[cache_key] = None
                if self._lazy_loaded_sheets[cache_key] is not None:
                    return self._lazy_loaded_sheets[cache_key]

        return None

    # ---------- Доступ к файлам и листам для Конструктора ----------

    def get_files_dict(self) -> dict[str, list[str]]:
        """
        Возвращает словарь {имя_файла: [список_всех_листов]}.
        Собирает открытые листы в памяти, extra_sheets и все листы исходного Excel-файла.
        """
        import os
        from src.core.data_loader import DataLoader

        if not hasattr(self, "_excel_sheets_cache"):
            self._excel_sheets_cache = {}

        result: dict[str, list[str]] = {}
        for entry in self.get_all():
            src_path = entry.data.source_path or ""
            file_name = os.path.basename(src_path) if src_path else entry.display_name
            if file_name not in result:
                result[file_name] = []

            # 1. Листы уже в памяти LoadedData (активный + extra_sheets)
            for s_name in entry.data.list_sheets():
                if s_name and s_name not in result[file_name]:
                    result[file_name].append(s_name)

            # 2. Все остальные листы из самого файла Excel на диске
            if src_path and os.path.exists(src_path):
                if src_path not in self._excel_sheets_cache:
                    try:
                        self._excel_sheets_cache[src_path] = DataLoader.get_excel_sheets(src_path)
                    except Exception:
                        self._excel_sheets_cache[src_path] = []
                for disk_sheet in self._excel_sheets_cache[src_path]:
                    if disk_sheet not in result[file_name]:
                        result[file_name].append(disk_sheet)

        return result

    def get_default_file_and_sheet(self) -> tuple[str, str]:
        """Возвращает (имя_файла, имя_листа) по умолчанию для новых блоков."""
        import os
        active = self.get_active()
        if active and active.data:
            f_name = os.path.basename(active.data.source_path) if active.data.source_path else active.display_name
            s_name = active.data.sheet_name or "Sheet1"
            return f_name, s_name

        files_dict = self.get_files_dict()
        for f_name, sheets in files_dict.items():
            if sheets:
                return f_name, sheets[0]
            return f_name, "Sheet1"
        return "", ""

    def get_dataframe(self, file_name: str = "", sheet_name: str = ""):
        """
        Возвращает DataFrame для конкретного файла и листа (независимо от активного файла).
        Если лист ещё не был открыт в Редакторе, прозрачно загружает и кэширует его из файла.
        """
        import os
        from src.core.data_loader import DataLoader

        if not hasattr(self, "_lazy_loaded_sheets"):
            self._lazy_loaded_sheets = {}

        entries = self.get_all()
        if not entries:
            return None

        def _apply_renames(data_obj, df, s_name):
            if df is None:
                return None
            cur_s = data_obj.sheet_name or "Sheet1"
            if s_name == cur_s and getattr(data_obj, "column_meta", None):
                rename_map = {
                    c: data_obj.get_display_name(c)
                    for c in df.columns
                    if data_obj.get_display_name(c) != c
                }
                if rename_map:
                    return df.rename(columns=rename_map)
            elif s_name in getattr(data_obj, "sheet_states", {}):
                saved_meta = data_obj.sheet_states[s_name].get("column_meta", {})
                rename_map = {
                    c: saved_meta[c].get("display_name", c)
                    for c in df.columns
                    if c in saved_meta and saved_meta[c].get("display_name")
                }
                if rename_map:
                    return df.rename(columns=rename_map)
            return df

        matched_entries = []
        for entry in entries:
            src_path = entry.data.source_path or ""
            base_name = os.path.basename(src_path) if src_path else entry.display_name
            if not file_name or file_name == base_name or file_name == entry.display_name:
                matched_entries.append(entry)

        if not matched_entries:
            matched_entries = entries

        if not sheet_name:
            first_entry = matched_entries[0]
            s_name = first_entry

    # ---------- Доступ к файлам и листам для Конструктора ----------

    def get_files_dict(self) -> dict[str, list[str]]:
        """
        Возвращает словарь {имя_файла: [список_всех_листов]}.
        Собирает открытые листы в памяти, extra_sheets и все листы исходного Excel-файла.
        """
        import os
        from src.core.data_loader import DataLoader

        if not hasattr(self, "_excel_sheets_cache"):
            self._excel_sheets_cache = {}

        result: dict[str, list[str]] = {}
        for entry in self.get_all():
            src_path = entry.data.source_path or ""
            file_name = os.path.basename(src_path) if src_path else entry.display_name
            if file_name not in result:
                result[file_name] = []

            # 1. Листы уже в памяти LoadedData (активный + extra_sheets)
            for s_name in entry.data.list_sheets():
                if s_name and s_name not in result[file_name]:
                    result[file_name].append(s_name)

            # 2. Все остальные листы из самого файла Excel на диске
            if src_path and os.path.exists(src_path):
                if src_path not in self._excel_sheets_cache:
                    try:
                        self._excel_sheets_cache[src_path] = DataLoader.get_excel_sheets(src_path)
                    except Exception:
                        self._excel_sheets_cache[src_path] = []
                for disk_sheet in self._excel_sheets_cache[src_path]:
                    if disk_sheet not in result[file_name]:
                        result[file_name].append(disk_sheet)

        return result

    def get_default_file_and_sheet(self) -> tuple[str, str]:
        """Возвращает (имя_файла, имя_листа) по умолчанию для новых блоков."""
        import os
        active = self.get_active()
        if active and active.data:
            f_name = os.path.basename(active.data.source_path) if active.data.source_path else active.display_name
            s_name = active.data.sheet_name or "Sheet1"
            return f_name, s_name

        files_dict = self.get_files_dict()
        for f_name, sheets in files_dict.items():
            if sheets:
                return f_name, sheets[0]
            return f_name, "Sheet1"
        return "", ""

    def get_dataframe(self, file_name: str = "", sheet_name: str = ""):
        """
        Возвращает DataFrame для конкретного файла и листа (независимо от активного файла).
        Если лист ещё не был открыт в Редакторе, прозрачно загружает и кэширует его из файла.
        """
        import os
        from src.core.data_loader import DataLoader

        if not hasattr(self, "_lazy_loaded_sheets"):
            self._lazy_loaded_sheets = {}

        entries = self.get_all()
        if not entries:
            return None

        def _apply_renames(data_obj, df, s_name):
            if df is None:
                return None
            cur_s = data_obj.sheet_name or "Sheet1"
            if s_name == cur_s and getattr(data_obj, "column_meta", None):
                rename_map = {
                    c: data_obj.get_display_name(c)
                    for c in df.columns
                    if data_obj.get_display_name(c) != c
                }
                if rename_map:
                    return df.rename(columns=rename_map)
            elif s_name in getattr(data_obj, "sheet_states", {}):
                saved_meta = data_obj.sheet_states[s_name].get("column_meta", {})
                rename_map = {
                    c: saved_meta[c].get("display_name", c)
                    for c in df.columns
                    if c in saved_meta and saved_meta[c].get("display_name")
                }
                if rename_map:
                    return df.rename(columns=rename_map)
            return df

        # Фильтруем записи по имени файла (если указано)
        matched_entries = []
        for entry in entries:
            src_path = entry.data.source_path or ""
            base_name = os.path.basename(src_path) if src_path else entry.display_name
            if not file_name or file_name == base_name or file_name == entry.display_name:
                matched_entries.append(entry)

        if not matched_entries:
            matched_entries = entries

        # Если лист не задан — берем первый найденный в подходящем файле
        if not sheet_name:
            first_entry = matched_entries[0]
            s_name = first_entry.data.sheet_name or "Sheet1"
            return _apply_renames(first_entry.data, first_entry.data.dataframe, s_name)

        # 1. Ищем лист среди уже загруженных FileEntry и их extra_sheets
        for entry in matched_entries:
            cur_sheet = entry.data.sheet_name or "Sheet1"
            if cur_sheet == sheet_name:
                return _apply_renames(entry.data, entry.data.dataframe, sheet_name)
            if sheet_name in entry.data.extra_sheets:
                return _apply_renames(entry.data, entry.data.extra_sheets[sheet_name], sheet_name)

        # 2. Если лист есть в Excel-файле на диске, но не был открыт в Редакторе — подгружаем
        for entry in matched_entries:
            src_path = entry.data.source_path
            if src_path and os.path.exists(src_path):
                cache_key = (src_path, sheet_name)
                if cache_key not in self._lazy_loaded_sheets:
                    try:
                        loaded = DataLoader.load(src_path, sheet_name)
                        self._lazy_loaded_sheets[cache_key] = loaded.dataframe
                    except Exception as e:
                        print(f"[FileManager] Не удалось подгрузить лист '{sheet_name}' из '{src_path}': {e}")
                        self._lazy_loaded_sheets[cache_key] = None
                if self._lazy_loaded_sheets[cache_key] is not None:
                    return self._lazy_loaded_sheets[cache_key]

        return None