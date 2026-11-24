# 🐞 Баг-репорт NexGrid: `AttributeError`

- **Дата:** `2026-10-28T08:28:58.383724`
- **Место сбоя:** `Uncaught Exception (sys.excepthook)`
- **Ошибка:** `'BlockInspector' object has no attribute '_field_str'`
- **Файл:** `C:\Users\v.ragimov\excel-analyzer\src\ui\block_inspector.py` (строка **407**, в `show_block`)

## 1. Traceback
```text
Traceback (most recent call last):
  File "C:\Users\v.ragimov\excel-analyzer\src\ui\constructor_tab.py", line 684, in _on_add_block
    self._on_block_selected(block.id)
    ~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^
  File "C:\Users\v.ragimov\excel-analyzer\src\ui\constructor_tab.py", line 741, in _on_block_selected
    self.inspector.show_block(block)
    ~~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^
  File "C:\Users\v.ragimov\excel-analyzer\src\ui\block_inspector.py", line 407, in show_block
    self._field_str("Заголовок графика", "title", cfg)
    ^^^^^^^^^^^^^^^
AttributeError: 'BlockInspector' object has no attribute '_field_str'. Did you mean: '_field_int'?
```

## 2. Локальные переменные в точке падения
```json
{
  "self": "<src.ui.block_inspector.BlockInspector(0x1741b890760) at 0x000001747DA10280>",
  "block": "ReportBlock(id='0570c7df', type='decomposition', config={'width': 100, 'align': 'left', 'offset_x': 0, 'source_file_name': 'Факт с регламентом.xlsx', 'source_sheet': 'Полный отчёт'})",
  "b_name": "'decomposition'",
  "cfg": "{'width': 100, 'align': 'left', 'offset_x': 0, 'source_file_name': 'Факт с регламентом.xlsx', 'source_sheet': 'Полный отчёт'}",
  "row_geo": "<PySide6.QtWidgets.QHBoxLayout(0x1741e62fd90) at 0x000001741E1F9A40>",
  "cols": "['Месяц', 'Январь_ГСМ(регламент)', 'Январь_НормативныйРасходГСМ', 'Январь_ФактическийРасходГСМ', 'Январь_Пробег', 'Январь_Расход_glonas', 'Январь_Пробег_glonas', 'Февраль_ГСМ(регламент)', 'Февраль_НормативныйРасходГСМ', 'Февраль_ФактическийРасходГСМ', 'Февраль_Пробег', 'Февраль_Расход_glonas', 'Февраль_Пробег_glonas', 'Март_ГСМ(регламент)', 'Март_НормативныйРасходГСМ', 'Март_ФактическийРасходГСМ', 'Март_Пробег', 'Март_Расход_glonas', 'Март_Пробег_glonas', 'Апрель_ГСМ(регламент)', 'Апрель_Нормати"
}
```

## 3. Состояние конструктора отчёта (Report)
```json
{}
```

## 4. Данные (DataFrame)
```json
{}
```

## 5. Сгенерированный Python-скрипт на момент сбоя
```python
# Скрипт пуст
```
