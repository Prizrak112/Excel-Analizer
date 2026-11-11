"""
Автоматически сгенерированный скрипт отчёта: Новый отчёт
"""

import pandas as pd
import plotly.express as px
import plotly.io as pio
from pathlib import Path

# Указываем ваш актуальный файл
FILE_PATH = 'Факт с регламентом_processed.xlsx'
SHEET_NAME = 'Экономия'

try:
    df = pd.read_excel(FILE_PATH, sheet_name=SHEET_NAME)
except FileNotFoundError:
    print(f"Ошибка: Файл '{FILE_PATH}' не найден в текущей папке. Убедитесь, что он лежит рядом со скриптом.")
    exit()

def wrap_positioned_block(html: str, width: int = 100, align: str = 'left', offset_x: int = 0, margin_top: int = 0, margin_bottom: int = 14, min_height: int = 0) -> str:
    min_h_css = f'min-height:{min_height}px;' if min_height > 0 else ''
    if width >= 100:
        return f'<div style="width:100%; margin-top:{margin_top}px; margin-bottom:{margin_bottom}px; {min_h_css}">{html}</div>'
    justify = 'center' if align == 'center' else ('flex-end' if align == 'right' else 'flex-start')
    ml = f'{offset_x}%' if (align == 'custom' and offset_x > 0) else '0'
    return (
        f'<div style="display:flex; width:100%; justify-content:{justify}; margin-top:{margin_top}px; margin-bottom:{margin_bottom}px;">'
        f'<div style="width:{width}%; max-width:{width}%; margin-left:{ml}; {min_h_css} box-sizing:border-box;">{html}</div></div>'
    )

html_parts = []

# ==================== РАЗДЕЛ 1: 📊 Перерасход ====================
html_parts.append('<h1 class="section-title">📊 Перерасход</h1>')

_container_items_s1 = []
_work_df_s1 = df.copy()
_tc_col_s1 = _work_df_s1.columns[0] # Колонка с типами ТС (слева)

# --- Левый блок (Фильтр / список ТС для Перерасхода) ---
_tc_vals_s1 = _work_df_s1[_tc_col_s1].dropna().astype(str).tolist()
_items_html_s1 = '<div style="padding: 8px 12px; background: #87C800; color: white; border-radius: 6px; cursor: pointer; margin-bottom: 4px; font-weight: bold;">Все значения</div>'
for _v in _tc_vals_s1[:15]:
    _items_html_s1 += f'<div style="padding: 8px 12px; cursor: pointer; border-radius: 6px; margin-bottom: 4px; color: #333;">{_v}</div>'

block_html_s1_filter = f'<div class="block"><div class="block-card" style="padding: 16px; background: #ffffff;"><div style="font-weight: bold; font-size: 14px; color: #003F0B; margin-bottom: 12px; border-bottom: 2px solid #87C800; padding-bottom: 4px;">Фильтр ТС</div><div style="font-size: 13px;">{_items_html_s1}</div></div></div>'
_container_items_s1.append(wrap_positioned_block(block_html_s1_filter, width=20, align='left', offset_x=0, margin_top=0, margin_bottom=14, min_height=0))

# --- Правый блок (График Перерасхода) ---
_numeric_cols_s1 = _work_df_s1.select_dtypes(include=['number']).columns
_over_col = _numeric_cols_s1[0] if len(_numeric_cols_s1) > 0 else _tc_col_s1

_plot_df_s1 = _work_df_s1[[_tc_col_s1, _over_col]].dropna()
_fig_s1 = px.line(_plot_df_s1, x=_tc_col_s1, y=_over_col, title='Распределение данных (Перерасход)', markers=True)
_fig_s1.update_traces(line=dict(color='#2b7fff', width=3))
_fig_s1.update_layout(plot_bgcolor='#ffffff', paper_bgcolor='#ffffff', showlegend=True, xaxis=dict(showgrid=True, tickangle=-25), yaxis=dict(showgrid=True))

block_html_s1_chart = '<div class="block"><div class="block-card" style="padding:16px; background:#ffffff; border-radius:8px;">' + pio.to_html(_fig_s1, include_plotlyjs='cdn', full_html=False) + '</div></div>'
_container_items_s1.append(wrap_positioned_block(block_html_s1_chart, width=80, align='left', offset_x=0, margin_top=0, margin_bottom=14, min_height=260))

block_html_s1_row = f'<div class="container-row" style="display:flex; flex-direction:row; gap:14px;">{"".join(_container_items_s1)}</div>'
html_parts.append(wrap_positioned_block(block_html_s1_row, width=100, align='left', offset_x=0, margin_top=0, margin_bottom=14, min_height=0))


# ==================== РАЗДЕЛ 2: 📊 Экономия ====================
html_parts.append('<h1 class="section-title">📊 Экономия</h1>')

_container_items_s2 = []
_work_df_s2 = df.copy()
_tc_col_s2 = _work_df_s2.columns[0]  
_econ_col = 'Итог_Экономия(факт)'

if _econ_col in _work_df_s2.columns:
    _work_df_s2[_econ_col] = pd.to_numeric(_work_df_s2[_econ_col], errors='coerce').fillna(0)
    # Фильтрация: значение >= 5
    _filtered_df_s2 = _work_df_s2[_work_df_s2[_econ_col] >= 5]
    
    # --- Левый блок (Список ТС с экономией >= 5%) ---
    _tc_vals_s2 = _filtered_df_s2[_tc_col_s2].dropna().astype(str).tolist()
    _items_html_s2 = '<div style="padding: 8px 12px; background: #87C800; color: white; border-radius: 6px; cursor: pointer; margin-bottom: 4px; font-weight: bold;">Все значения</div>'
    for _v in _tc_vals_s2:
        _items_html_s2 += f'<div style="padding: 8px 12px; cursor: pointer; border-radius: 6px; margin-bottom: 4px; color: #333;">{_v}</div>'
    
    block_html_s2_filter = f'<div class="block"><div class="block-card" style="padding: 16px; background: #ffffff;"><div style="font-weight: bold; font-size: 14px; color: #003F0B; margin-bottom: 12px; border-bottom: 2px solid #87C800; padding-bottom: 4px;">Фильтр ТС (>= 5%)</div><div style="font-size: 13px;">{_items_html_s2}</div></div></div>'
    _container_items_s2.append(wrap_positioned_block(block_html_s2_filter, width=20, align='left', offset_x=0, margin_top=0, margin_bottom=14, min_height=0))

    # --- Правый блок (График Экономии) ---
    _fig_s2 = px.bar(
        _filtered_df_s2, 
        x=_tc_col_s2, 
        y=_econ_col, 
        title='Типы ТС с экономией (факт) >= 5%',
        text=_econ_col
    )
    _fig_s2.update_traces(marker_color='#87C800', textposition='outside')
    _fig_s2.update_layout(
        plot_bgcolor='#ffffff', 
        paper_bgcolor='#ffffff', 
        xaxis=dict(showgrid=True, tickangle=-25), 
        yaxis=dict(showgrid=True)
    )
    
    block_html_s2_chart = '<div class="block"><div class="block-card" style="padding:16px; background:#ffffff; border-radius:8px;">' + pio.to_html(_fig_s2, include_plotlyjs='cdn', full_html=False) + '</div></div>'
    _container_items_s2.append(wrap_positioned_block(block_html_s2_chart, width=80, align='left', offset_x=0, margin_top=0, margin_bottom=14, min_height=260))

block_html_s2_row = f'<div class="container-row" style="display:flex; flex-direction:row; gap:14px;">{"".join(_container_items_s2)}</div>'
html_parts.append(wrap_positioned_block(block_html_s2_row, width=100, align='left', offset_x=0, margin_top=0, margin_bottom=14, min_height=0))


# ==================== Сборка HTML ====================
full_html = '<!DOCTYPE html><html><head><meta charset="utf-8">' \
    + '<title>Новый отчёт</title>' \
    + '<style>body{font-family:Segoe UI,Arial,sans-serif;background:#f4f6f9;margin:0;padding:32px;}' \
    + '.section-title{color:#003F0B;border-bottom:2px solid #87C800;padding-bottom:8px;margin-top:24px;}' \
    + '.block-card{background:#fff;border:1px solid #e0e0e5;border-radius:8px;padding:16px;}</style></head>' \
    + '<body><div style="max-width:1200px;margin:0 auto;background:#fff;padding:36px 44px;border-radius:10px;">' + '\n'.join(html_parts) + '</div></body></html>'

output_path = Path('report_output.html')
output_path.write_text(full_html, encoding='utf-8')
print(f'Отчёт успешно сохранён: {output_path.resolve()}')