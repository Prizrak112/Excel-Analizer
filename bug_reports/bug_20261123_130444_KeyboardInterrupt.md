# 🐞 Баг-репорт NexGrid: `KeyboardInterrupt`

- **Дата:** `2026-11-23T13:04:44.708087`
- **Место сбоя:** `Uncaught Exception (sys.excepthook)`
- **Ошибка:** ``
- **Файл:** `shibokensupport/signature/loader.py` (строка **68**, в `feature_imported`)

## 1. Traceback
```text
Traceback (most recent call last):
  File "C:\Users\v.ragimov\excel-analyzer\src\ui\constructor_tab.py", line 1139, in _on_preview
    self._push_preview(open_browser=True)
    ~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^
  File "C:\Users\v.ragimov\excel-analyzer\src\ui\constructor_tab.py", line 1164, in _push_preview
    body = render_report(self.report, ctx)
  File "C:\Users\v.ragimov\excel-analyzer\src\core\block_factory.py", line 489, in render_report
    raw_block_html = block_obj.render()
  File "C:\Users\v.ragimov\excel-analyzer\src\core\blocks.py", line 4911, in render
    l2_months, l2_badges, all_l2_vals = _pack_month_slices(
                                        ~~~~~~~~~~~~~~~~~~^
        l1_df, "_cmb_l2", sort_lvl2, f"Уровень 2 ({lvl2_col}): {l1_val}", 2
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    )
    ^
  File "C:\Users\v.ragimov\excel-analyzer\src\core\blocks.py", line 4889, in _pack_month_slices
    tr_m, hdr_m, _ = _build_combo_traces_for_df(
                     ~~~~~~~~~~~~~~~~~~~~~~~~~~^
        m_sub, x_key, level_sort_mode=s_mode, level_num=lvl_idx, apply_top_n=False
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    )
    ^
  File "C:\Users\v.ragimov\excel-analyzer\src\core\blocks.py", line 4685, in _build_combo_traces_for_df
    _eval_combo_formula(f_str, pt_i, computed_series_arrays, col_arrays_map, cnt_arr, cur_series_idx=idx_s)
    ~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\v.ragimov\excel-analyzer\src\core\blocks.py", line 4494, in _eval_combo_formula
    import math
  File "shibokensupport/signature/loader.py", line 68, in feature_imported
KeyboardInterrupt
```

## 2. Локальные переменные в точке падения
```json
{
  "args": "(<module 'math' (built-in)>,)",
  "kwds": "{}"
}
```

## 3. Состояние конструктора отчёта (Report)
```json
{
  "title": "Новый отчёт",
  "sections": [
    {
      "id": "9326f50f",
      "title": "Отчет",
      "blocks": [
        {
          "id": "a0c8f59e",
          "type": "container",
          "config": {
            "layout": "row",
            "gap": 14,
            "width": 100,
            "align": "left",
            "offset_x": 0,
            "children": [
              {
                "id": "0db22562",
                "type": "dashboard_filter",
                "config": {
                  "title": "Фильтр",
                  "filter_col": "Тип ТС",
                  "target_chart": "77e49155",
                  "width": 20,
                  "align": "left",
                  "offset_x": 0,
                  "source_file_name": "Грузовые премия.xlsx",
                  "source_sheet": "Лист_1",
                  "extra_target_charts": "7c3c69da"
                }
              },
              {
                "id": "77e49155",
                "type": "plotly_chart",
                "config": {
                  "title": "График данных",
                  "chart_type": "line",
                  "x_col": "Тип ТС",
                  "y_col": "Фактический расход ГСМ, л, Нормативный расход ГСМ, л",
                  "agg": "sum",
                  "sort_by": "value_desc",
                  "top_n": 20,
                  "row_start": 0,
                  "row_limit": 0,
                  "palette": "corporate",
                  "bg_color": "#ffffff",
                  "legend_pos": "right",
                  "show_legend": true,
                  "show_values": true,
                  "show_grid": true,
                  "width": 80,
                  "min_height": 260,
                  "align": "left",
                  "offset_x": 0,
                  "source_file_name": "ТС.xlsx",
                  "source_sheet": "Лист1",
                  "parent_group_col": "Тип ТС",
                  "model_col": "Модель ТС",
                  "date_col": "Месяц",
                  "fact_col": "Фактический расход ГСМ, л",
                  "norm_col": "Нормативный расход ГСМ, л",
                  "font_size": 16,
                  "show_axis_labels": false,
                  "show_title": false
                }
              }
            ]
          }
        },
        {
          "id": "7c3c69da",
          "type": "plotly_chart",
          "config": {
            "title": "График данных",
            "chart_type": "combo",
            "x_col": "Дата",
            "y_col": "",
            "agg": "sum",
            "sort_by": "value_desc",
            "top_n": 20,
            "row_start": 0,
            "row_limit": 0,
            "palette": "corporate",
            "bg_color": "#ffffff",
            "legend_pos": "right",
            "show_legend": true,
            "show_values": true,
            "show_grid": true,
            "width": 100,
            "min_height": 502,
            "align": "left",
            "offset_x": 0,
            "source_file_name": "ТС.xlsx",
            "source_sheet": "Лист1",
            "parent_group_col": "Тип ТС",
            "model_col": "Модель ТС",
            "date_col": "Месяц",
            "fact_col": "Фактический расход ГСМ, л",
            "norm_col": "Нормативный расход ГСМ, л",
            "calc_group_col": "Модель ТС",
            "plate_col": "",
            "pie_display_mode": "single_interactive",
            "show_axis_labels": false,
            "show_title": false,
            "font_size": 16,
            "pie_value_display": "formula_pct",
            "combo_series": [
              {
                "name": "Фактический расход ГСМ, л",
                "source_type": "formula",
                "col": "Фактический расход ГСМ, л",
                "formula": "S1 - S2",
                "agg": "sum",
                "plot_type": "bar",
                "y_axis": "y1",
                "color": "#2b7fff",
                "line_dash": "solid",
                "line_width": 3,
                "marker_size": 8,
                "opacity": 0.9,
                "show_labels": true,
                "suffix": "",
                "visible": true
              },
              {
                "name": "Нормативный расход ГСМ, л",
                "source_type": "formula",
                "col": "Нормативный расход ГСМ, л",
                "formula": "((S1 - S2) / S2) * 100",
                "agg": "sum",
                "plot_type": "line",
                "y_axis": "y2",
                "color": "#87C800",
                "line_dash": "solid",
                "line_width": 3,
                "marker_size": 8,
                "opacity": 1.0,
                "show_labels": true,
                "suffix": "",
                "visible": true
              }
            ],
            "combo_level1_col": "Пробег, км",
            "combo_level2_col": "Модель ТС",
            "combo_level3_col": "Гос. номер",
            "combo_highlight_overrun": true,
            "column_aliases": {
              "Фактический расход ГСМ, л": "Отклонение от норматива, л",
              "Нормативный расход ГСМ, л": "Процент отклонения от норматива"
            },
            "bar_text_angle": "0",
            "bar_text_pos": "inside"
          }
        },
        {
          "id": "461f9d7a",
          "type": "pivot_matrix",
          "config": {
            "title": "Сводная матрица",
            "row_group_col": "Тип ТС",
            "row_level2_col": "Модель ТС",
            "row_level3_col": "Гос. номер",
            "col_group_col": "Дата",
            "value_col": "Фактический расход ГСМ, л",
            "value_cols": [
              "Фактический расход ГСМ, л",
              "Нормативный расход ГСМ, л"
            ],
            "calc_cols": [
              {
                "name": "Отклонение",
                "formula": "A - B",
                "is_pct": false
              }
            ],
            "color_calc_enabled": true,
            "color_calc_scope": "calc_and_dev",
            "neg_color": "#16a34a",
            "pos_color": "#dc2626",
            "color_calc_bg": true,
            "sticky_header": true,
            "sticky_first_col": true,
            "max_table_height": 520,
            "show_search": true,
            "target_table": "1cf64955",
            "agg_func": "sum",
            "show_totals": true,
            "top_n": 30,
            "source_file_name": "Грузовые премия.xlsx",
            "source_sheet": "Лист_1"
          }
        },
        {
          "id": "55cc79de",
          "type": "plotly_chart",
          "config": {
            "title": "Дуты с перерасходом",
            "chart_type": "pie",
            "x_col": "",
            "y_col": "",
            "agg": "sum",
            "sort_by": "value_desc",
            "top_n": 12,
            "row_start": 0,
            "row_limit": 0,
            "palette": "corporate",
            "bg_color": "#ffffff",
            "legend_pos": "right",
            "show_legend": true,
            "show_values": true,
            "show_grid": true,
            "width": 100,
            "min_height": 260,
            "align": "left",
            "offset_x": 0,
            "source_file_name": "ТС.xlsx",
            "source_sheet": "Свод по машинам",
            "pie_display_mode": "dut_single_drill",
            "dut_col": "Оборудованы ДУТ (список логистов)?",
            "pct_col": "Перерасход/\nэкономия топлива по автомобилю за 1пг2026г (расчётно), %",
            "dut_pct_op": "ge",
            "parent_group_col": "Тип_ТС",
            "model_col": "Марка"
          }
        },
        {
          "id": "1cf64955",
          "type": "data_table",
          "config": {
            "title": "Реестр путевых листов",
            "source_file_name": "ТС.xlsx",
            "source_sheet": "Лист1",
            "max_rows": 20,
            "width": 100,
            "align": "left",
            "offset_x": 0
          }
        }
      ]
    }
  ]
}
```

## 4. Данные (DataFrame)
```json
{
  "loaded": true,
  "rows": 87522,
  "columns": {
    "Номер пл": "str",
    "Месяц": "str",
    "Тип ТС": "str",
    "Модель ТС": "str",
    "Гос. номер": "str",
    "Пробег, км": "float64",
    "Фактический расход ГСМ, л": "float64",
    "Нормативный расход ГСМ, л": "float64"
  }
}
```

## 5. Сгенерированный Python-скрипт на момент сбоя
```python
# Скрипт пуст
```
