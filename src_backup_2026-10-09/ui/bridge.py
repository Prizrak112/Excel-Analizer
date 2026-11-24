"""
Мост между JavaScript (в HTML) и Python.
"""

from PySide6.QtCore import QObject, Slot, Signal

from src.core.renderer import Renderer
from src.core.blocks import (
    SectionTitleBlock, ParagraphBlock, KpiRowBlock, KpiCard,
    DividerBlock, DataTableBlock,
)
from src.core.data_loader import DataLoader, LoadedData
from src.config.app_info import APP_NAME, APP_VERSION


class WebBridge(QObject):
    """Объект-мост."""
    
    file_loaded = Signal(object)
    columns_changed = Signal()
    column_meta_changed = Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_data: LoadedData | None = None
    
    # ---------- Загрузка ----------
    
    def load_file(self, filepath: str, sheet_name: str | int = 0) -> LoadedData:
        data = DataLoader.load(filepath, sheet_name)
        self.current_data = data
        self.file_loaded.emit(data)
        return data
    
    @Slot(result=bool)
    def has_data(self) -> bool:
        return self.current_data is not None
    
    # ---------- Видимость ----------
    
    @Slot(str, bool)
    def set_column_visible(self, column: str, visible: bool):
        if self.current_data is None:
            return
        self.current_data.toggle_column(column, visible)
        self.columns_changed.emit()
    
    @Slot()
    def show_all_columns(self):
        if self.current_data is None:
            return
        self.current_data.show_all_columns()
        self.columns_changed.emit()
    
    @Slot()
    def hide_all_columns(self):
        if self.current_data is None:
            return
        self.current_data.hide_all_columns()
        self.columns_changed.emit()
    
    # ---------- Мета-данные ----------
    
    @Slot(str, str, str, bool)
    def update_column(self, name: str, display_name: str, role: str, visible: bool):
        print(f"[Bridge] update_column: name='{name}', display='{display_name}', role='{role}', visible={visible}")
        
        if self.current_data is None:
            return
        
        if display_name and display_name != name:
            self.current_data.set_display_name(name, display_name)
        else:
            if name in self.current_data.column_meta:
                self.current_data.column_meta[name].pop("display_name", None)
        
        auto_role = self.current_data._detect_role(name)
        if role != auto_role:
            self.current_data.set_role(name, role)
        else:
            if name in self.current_data.column_meta:
                self.current_data.column_meta[name].pop("custom_role", None)
        
        self.current_data.toggle_column(name, visible)
        
        self.column_meta_changed.emit(name)
        self.columns_changed.emit()
    
    @Slot(str, str)
    def cast_column(self, name: str, new_dtype: str):
        print(f"[Bridge] cast_column: '{name}' → {new_dtype}")
        
        if self.current_data is None:
            return False, "Нет данных"
        
        ok, message = self.current_data.cast_column(name, new_dtype)
        
        if ok:
            if name in self.current_data.column_meta:
                self.current_data.column_meta[name].pop("custom_role", None)
            self.column_meta_changed.emit(name)
            self.columns_changed.emit()
        
        return ok, message
    
    # ---------- Разделение ----------
    
    @Slot(str, str, dict, list, bool)
    def split_column(self, column: str, mode: str, params: dict, new_names: list, delete_original: bool):
        print(f"[Bridge] split_column: '{column}', mode='{mode}'")
        
        if self.current_data is None:
            return False, "Нет данных"
        
        ok, message = self.current_data.split_column(
            column, mode, params, new_names, delete_original
        )
        
        if ok:
            self.columns_changed.emit()
        
        return ok, message
    
    @Slot(str, list, list, bool)
    def split_column_by_rules(self, column: str, rules: list, new_names: list, delete_original: bool):
        """Разделение по правилам (визуальный режим)."""
        print(f"[Bridge] split_column_by_rules: '{column}', rules={len(rules)}, names={new_names}")
        
        if self.current_data is None:
            return False, "Нет данных"
        
        ok, message = self.current_data.split_by_rules(
            column, rules, new_names, delete_original
        )
        
        if ok:
            self.columns_changed.emit()
        
        return ok, message
    
    # ---------- Порядок ----------
    
    @Slot(list)
    def reorder_columns(self, new_order: list):
        if self.current_data is None:
            return
        self.current_data.reorder_visible_columns(new_order)
        self.columns_changed.emit()
    
    # ---------- Рендеринг ----------
    
    @Slot(result=str)
    def get_report_html(self) -> str:
        return self.get_data_preview_html()
    
    @Slot(result=str)
    def get_data_preview_html(self) -> str:
        if self.current_data is None:
            return self._empty_html("Данные не загружены")
        return self._render_data_preview(self.current_data)
    
    @Slot(result=str)
    def get_visible_columns_json(self) -> str:
        import json
        if self.current_data is None:
            return "[]"
        return json.dumps(self.current_data.visible_columns, ensure_ascii=False)
    
    @Slot(result=str)
    def get_columns_info_json(self) -> str:
        import json
        if self.current_data is None:
            return "[]"
        return json.dumps(
            self.current_data.get_columns_info(),
            ensure_ascii=False
        )
    
    def _render_data_preview(self, data: LoadedData) -> str:
        from pathlib import Path
        
        renderer = Renderer()
        
        renderer.add(SectionTitleBlock(id="data_title", title="Данные из файла"))
        
        filename = Path(data.source_path).name
        renderer.add(ParagraphBlock(
            id="data_info",
            raw_html=True,
            text=(
                f"<b>Файл:</b> {filename}<br>"
                f"<b>Лист:</b> {data.sheet_name or '—'}<br>"
                f"<b>Строк:</b> {data.rows_count:,}<br>"
                f"<b>Колонок:</b> {data.cols_count}"
            )
        ))
        
        columns_info = data.get_columns_info()
        n_numeric = sum(1 for c in columns_info if c["role"] == "numeric")
        n_category = sum(1 for c in columns_info if c["role"] == "category")
        n_text = sum(1 for c in columns_info if c["role"] == "text")
        n_date = sum(1 for c in columns_info if c["role"] == "date")
        
        cards = [
            KpiCard(label="Строк", value=f"{data.rows_count:,}"),
            KpiCard(label="Колонок", value=str(data.cols_count), accent=True),
            KpiCard(label="Числовых", value=str(n_numeric)),
            KpiCard(label="Категорий", value=str(n_category)),
            KpiCard(label="Текстовых", value=str(n_text)),
        ]
        if n_date > 0:
            cards.append(KpiCard(label="Даты", value=str(n_date)))
        
        renderer.add(KpiRowBlock(id="data_kpi", cards=cards))
        renderer.add(DividerBlock(id="data_divider"))
        renderer.add(SectionTitleBlock(id="data_table_title", title="Первые строки"))
        
        df_renamed = data.get_renamed_preview(20)
        renderer.add(DataTableBlock(
            id="data_table",
            dataframe=df_renamed,
            visible_columns=None
        ))
        
        return renderer.render()
    
    def _empty_html(self, message: str) -> str:
        return f'''
        <div class="block">
            <div class="block-card" style="text-align:center; padding: 60px 20px;">
                <p style="color:#888; font-size: 14px;">{message}</p>
                <p style="color:#888; font-size: 13px; margin-top: 12px;">
                    Используй <b>Файл → Открыть</b> или кнопку <b>📂 Открыть</b> на панели инструментов.
                </p>
            </div>
        </div>
        '''