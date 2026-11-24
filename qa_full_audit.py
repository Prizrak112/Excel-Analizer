"""Автоматический баг-тест ядра NexGrid, Инспектора, анимаций и автономного экспорта."""

import ast
import subprocess
import sys
import tempfile
import time
import warnings
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RESULTS: list[tuple[str, bool, str]] = []


def run_test(name: str, fn):
    t0 = time.perf_counter()
    try:
        info = fn() or "OK"
        dt = time.perf_counter() - t0
        RESULTS.append((name, True, f"{info} ({dt:.2f}s)"))
        print(f"✅ [PASS] {name} — {info} ({dt:.2f}s)")
    except Exception as exc:
        dt = time.perf_counter() - t0
        RESULTS.append((name, False, f"{type(exc).__name__}: {exc}"))
        print(f"❌ [FAIL] {name} — {type(exc).__name__}: {exc} ({dt:.2f}s)")


def make_test_dataframes():
    rows = []
    months = ["2026-01-15", "2026-02-15", "2026-03-15", "2026-04-15"]
    groups = ["Электроника", "Мебель", "Одежда"]
    subgroups = {
        "Электроника": ["Ноутбуки", "Смартфоны"],
        "Мебель": ["Столы", "Кресла"],
        "Одежда": ["Куртки", "Обувь"],
    }
    for m_idx, dt in enumerate(months):
        for g in groups:
            for sg in subgroups[g]:
                for item_i in range(1, 5):
                    norm = 100.0 + m_idx * 15 + item_i * 10
                    fact = norm * (1.12 if (item_i % 2 == 0) else 0.94)
                    rows.append({
                        "Категория": g,
                        "Подкатегория": sg,
                        "Артикул": f"{g[:2].upper()}-{sg[:2].upper()}-{item_i:03d}",
                        "Дата": dt,
                        "Факт": round(fact, 2),
                        "План": round(norm, 2),
                        "Отклонение_%": round(((fact - norm) / norm) * 100, 2),
                        "Контроль": "Да" if item_i % 2 == 0 else "Нет",
                    })
    df_main = pd.DataFrame(rows)
    df_other = pd.DataFrame({"Другой_столбец": ["A", "B"], "Сумма": [10, 20]})
    return df_main, df_other


class MockFileManager:
    def __init__(self, df_main: pd.DataFrame, df_other: pd.DataFrame):
        self._sheets = {
            "sales.xlsx": {
                "Сводка": df_other,
                "Данные": df_main,
            }
        }

    def get_files_dict(self):
        return {k: list(v.keys()) for k, v in self._sheets.items()}

    def get_default_file_and_sheet(self):
        return "sales.xlsx", "Сводка"

    def get_dataframe(self, file_name="", sheet_name=""):
        sheets = self._sheets.get(file_name) or self._sheets["sales.xlsx"]
        return sheets.get(sheet_name) if sheet_name in sheets else next(iter(sheets.values()))

    def find_dataframe_with_column(self, col_name: str):
        for sh_map in self._sheets.values():
            for df in sh_map.values():
                if col_name in df.columns:
                    return df
        return None


# ── Тест 1: Синтаксис и дубли классов в ключевых модулях ──
def test_syntax_and_duplicates():
    targets = [
        ROOT / "src" / "core" / "blocks.py",
        ROOT / "src" / "core" / "block_factory.py",
        ROOT / "src" / "core" / "code_generator.py",
        ROOT / "src" / "ui" / "block_inspector.py",
        ROOT / "src" / "ui" / "constructor_tab.py",
    ]
    checked = 0
    for path in targets:
        if not path.is_file():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        cls_names = [n.name for n in tree.body if isinstance(n, ast.ClassDef)]
        dups = {c for c in cls_names if cls_names.count(c) > 1}
        assert not dups, f"Дубликаты классов в {path.name}: {dups}"
        checked += 1
    return f"проверено файлов: {checked}, дублей классов нет"


# ── Тест 2: Отсутствие бага с вылетающей подсказкой и наличие анимаций ──
def test_animation_assets():
    from src.core import blocks
    assets = getattr(blocks, "_CHART_ANIM_ASSETS_HTML", "")
    assert assets, "_CHART_ANIM_ASSETS_HTML не найден в blocks.py"
    assert ".hoverlayer .hovertext" not in assets or "transition:" not in assets.split(".hoverlayer .hovertext")[1].split("}")[0], \
        "Остался CSS transition на .hoverlayer .hovertext (подсказка будет вылетать из угла!)"
    for token in ("eaPieSpin", "_eaAnimatedPlotlyReact", "_eaUpdateHeaderAnimated", "toggleEaChartCard", "data-anim-style"):
        assert token in assets or token in Path(blocks.__file__).read_text(encoding="utf-8"), f"Не найден элемент анимации: {token}"
    return "подсказка исправлена, движок анимаций на месте"


# ── Тест 3: Скорость комбо-графика с 3 уровнями погружения и формулами ──
def test_combo_chart_speed_and_formulas():
    from src.core.block_factory import RenderContext, render_report
    from src.core.report_model import Report, ReportBlock

    df_main, df_other = make_test_dataframes()
    fm = MockFileManager(df_main, df_other)
    rep = Report(title="QA Combo")
    rep.file_manager = fm
    sec = rep.add_section("Аналитика")
    sec.add_block(ReportBlock.create("plotly_chart", {
        "title": "Комбо QA",
        "chart_type": "combo",
        "source_file_name": "sales.xlsx",
        "source_sheet": "Данные",
        "combo_level1_col": "Категория",
        "combo_level2_col": "Подкатегория",
        "combo_level3_col": "Артикул",
        "date_col": "Дата",
        "fact_col": "Факт",
        "norm_col": "План",
        "anim_style": "cascade",
        "anim_speed": 700,
        "combo_series": [
            {"name": "Отклонение", "source_type": "formula", "formula": "A - B", "plot_type": "bar", "y_axis": "y1", "color": "#2b7fff", "visible": True},
            {"name": "Тренд %", "source_type": "formula", "formula": "((A - B) / B) * 100", "plot_type": "line", "y_axis": "y2", "color": "#87C800", "suffix": "%", "visible": True},
        ],
    }))
    t0 = time.perf_counter()
    html = render_report(rep, RenderContext(dataframe=df_other, report=rep, file_manager=fm))
    dt = time.perf_counter() - t0
    assert "Ошибка построения графика" not in html, "В HTML комбо-графика вернулась ошибка"
    assert 'data-anim-style="cascade"' in html and 'data-anim-speed="700"' in html, "Настройки анимации не попали в HTML"
    assert dt < 3.0, f"Слишком долгий рендер комбо-графика: {dt:.2f}s"
    return f"3 уровня + формулы собраны за {dt:.2f}s"


# ── Тест 4: Срез с битым листом (проверка автоподбора от привязанного графика) ──
def test_filter_broken_sheet_fallback():
    from src.core.block_factory import RenderContext, render_report
    from src.core.report_model import Report, ReportBlock

    df_main, df_other = make_test_dataframes()
    fm = MockFileManager(df_main, df_other)
    rep = Report(title="QA Filter")
    rep.file_manager = fm
    sec = rep.add_section("Срез")

    ch = ReportBlock.create("plotly_chart", {
        "title": "Тренд",
        "chart_type": "line",
        "source_file_name": "sales.xlsx",
        "source_sheet": "Данные",
        "x_col": "Категория",
        "y_col": "Факт, План",
        "date_col": "Дата",
        "parent_group_col": "Категория",
    })
    flt = ReportBlock.create("dashboard_filter", {
        "title": "Фильтр категорий",
        "filter_col": "Категория",
        "target_chart": ch.id,
        "source_file_name": "Несуществующий.xlsx",
        "source_sheet": "Битый_лист",
    })
    sec.add_block(ReportBlock.create("container", {"layout": "row", "children": [flt, ch]}))

    html = render_report(rep, RenderContext(dataframe=df_other, report=rep, file_manager=fm))
    assert "(Выберите колонку в Инспекторе)" not in html, "Срез пустой — не сработал подбор листа от target_chart!"
    assert "Электроника" in html and "Мебель" in html, "Категории не попали в HTML среза"
    return "срез корректно подтянул категории даже с битым source_sheet"


# ── Тест 5: Сводная матрица — нет PerformanceWarning и работают формулы ──
def test_pivot_no_warnings():
    from src.core.block_factory import RenderContext, render_report
    from src.core.report_model import Report, ReportBlock

    df_main, df_other = make_test_dataframes()
    fm = MockFileManager(df_main, df_other)
    rep = Report(title="QA Pivot")
    rep.file_manager = fm
    sec = rep.add_section("Сводная")
    sec.add_block(ReportBlock.create("pivot_matrix", {
        "title": "Матрица QA",
        "source_file_name": "sales.xlsx",
        "source_sheet": "Данные",
        "row_group_col": "Категория",
        "row_level2_col": "Подкатегория",
        "row_level3_col": "Артикул",
        "col_group_col": "Дата",
        "value_col": "Факт",
        "value_cols": ["Факт", "План"],
        "calc_cols": [{"name": "Откл %", "formula": "((A - B) / B) * 100", "is_pct": True}],
        "color_calc_enabled": True,
    }))

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        html = render_report(rep, RenderContext(dataframe=df_main, report=rep, file_manager=fm))

    perf_warns = [w for w in caught if "PerformanceWarning" in w.category.__name__ or "lexsort" in str(w.message)]
    assert not perf_warns, f"Обнаружены PerformanceWarning ({len(perf_warns)} шт.)!"
    assert "Ошибка расчета сводной матрицы" not in html, "Ошибка в рендере сводной"
    assert "ea-piv-row-l3" in html, "Не сгенерировался 3-й уровень раскрытия"
    return "0 PerformanceWarning, 3 уровня и формулы OK"


# ── Тест 6: Двухфакторная круговая (раскручивание + 3 уровня) ──
def test_dual_pie_render():
    from src.core.block_factory import RenderContext, render_report
    from src.core.report_model import Report, ReportBlock

    df_main, df_other = make_test_dataframes()
    fm = MockFileManager(df_main, df_other)
    rep = Report(title="QA Pie")
    rep.file_manager = fm
    sec = rep.add_section("Круг")
    sec.add_block(ReportBlock.create("plotly_chart", {
        "title": "Контроль и порог",
        "chart_type": "pie",
        "pie_display_mode": "dut_single_drill",
        "source_file_name": "sales.xlsx",
        "source_sheet": "Данные",
        "dut_col": "Контроль",
        "pct_col": "Отклонение_%",
        "parent_group_col": "Категория",
        "model_col": "Подкатегория",
        "plate_col": "Артикул",
        "anim_style": "spin",
        "anim_speed": 1000,
    }))
    html = render_report(rep, RenderContext(dataframe=df_main, report=rep, file_manager=fm))
    assert 'data-anim-style="spin"' in html and 'data-anim-speed="1000"' in html, "Не пробросились атрибуты spin/1000"
    assert "dutdata" in html, "Не сгенерировался JSON-пакет круговой диаграммы"
    return "dut_single_drill + spin/1000ms OK"


# ── Тест 7: Автономный экспорт .py-скрипта и его реальный запуск ──
def test_standalone_code_export_execution():
    from src.core.code_generator import generate_report_script
    from src.core.report_model import Report, ReportBlock

    df_main, df_other = make_test_dataframes()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        xlsx_path = tmp_dir / "qa_data.xlsx"
        with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
            df_other.to_excel(writer, sheet_name="Сводка", index=False)
            df_main.to_excel(writer, sheet_name="Данные", index=False)

        fm = MockFileManager(df_main, df_other)
        rep = Report(title="QA Export")
        rep.file_manager = fm
        sec = rep.add_section("Экспорт")
        ch = ReportBlock.create("plotly_chart", {
            "title": "График экспорта",
            "chart_type": "line",
            "source_file_name": "qa_data.xlsx",
            "source_sheet": "Данные",
            "x_col": "Категория",
            "y_col": "Факт, План",
            "date_col": "Дата",
            "parent_group_col": "Категория",
            "anim_style": "auto",
            "anim_speed": 480,
        })
        flt = ReportBlock.create("dashboard_filter", {
            "title": "Фильтр",
            "filter_col": "Категория",
            "target_chart": ch.id,
            "source_file_name": "Битый.xlsx",
            "source_sheet": "Нет_листа",
        })
        sec.add_block(ReportBlock.create("container", {"layout": "row", "children": [flt, ch]}))

        script_code = generate_report_script(rep, file_name=str(xlsx_path), sheet_name="Сводка")
        script_code = script_code.replace("OPEN_IN_BROWSER = True", "OPEN_IN_BROWSER = False")
        py_path = tmp_dir / "qa_generated_report.py"
        py_path.write_text(script_code, encoding="utf-8")

        proc = subprocess.run(
            [sys.executable, str(py_path)],
            cwd=str(tmp_dir),
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert proc.returncode == 0, f"Выгруженный скрипт упал:\n{proc.stderr or proc.stdout}"
        out_html = tmp_dir / "final_dashboard_report.html"
        assert out_html.is_file(), "final_dashboard_report.html не создался"
        html_txt = out_html.read_text(encoding="utf-8")
        assert "(Выберите колонку в Инспекторе)" not in html_txt, "В выгруженном HTML сломан Срез!"
        assert "Электроника" in html_txt and "ea-chart-card" in html_txt, "В выгруженном HTML нет данных или анимаций"
        return f"HTML создан ({out_html.stat().st_size // 1024} КБ), срез и анимации работают"


# ── Тест 8: Наличие всех вкладок и настроек анимаций в BlockInspector (без падений Qt) ──
def test_inspector_ui_smoke():
    from PySide6.QtWidgets import QApplication
    from src.config.theme import get_theme
    from src.core.report_model import Report, ReportBlock
    from src.ui.block_inspector import BlockInspector

    app = QApplication.instance() or QApplication(sys.argv)
    df_main, df_other = make_test_dataframes()
    fm = MockFileManager(df_main, df_other)
    rep = Report(title="QA UI")
    rep.file_manager = fm

    insp = BlockInspector(get_theme())
    insp.report_ref = rep
    insp.file_manager = fm
    insp.set_dataframe(df_main)

    block_types_to_test = [
        ("plotly_chart", {"chart_type": "bar", "anim_style": "auto", "anim_speed": 480}),
        ("plotly_chart", {"chart_type": "combo"}),
        ("plotly_chart", {"chart_type": "pie", "pie_display_mode": "dut_single_drill"}),
        ("pivot_matrix", {}),
        ("dashboard_filter", {}),
        ("data_table", {}),
        ("paragraph", {}),
        ("kpi_row", {}),
        ("decomposition", {}),
        ("geo_map", {}),
        ("divider", {}),
    ]
    for bt, cfg in block_types_to_test:
        blk = ReportBlock.create(bt, cfg)
        insp.show_block(blk)
    insp.show_empty()
    app.processEvents()
    return f"проверено {len(block_types_to_test)} типов блоков без ошибок Qt"


if __name__ == "__main__":
    print("=== ЗАПУСК БАГ-ТЕСТА NEXGRID ===\n")
    run_test("1. Синтаксис и отсутствие дублей классов", test_syntax_and_duplicates)
    run_test("2. Анимации и фикс вылетающей подсказки", test_animation_assets)
    run_test("3. Комбо-график (формулы + 3 уровня + скорость)", test_combo_chart_speed_and_formulas)
    run_test("4. Срез данных (автоподбор листа при битой привязке)", test_filter_broken_sheet_fallback)
    run_test("5. Сводная матрица (0 PerformanceWarning + формулы)", test_pivot_no_warnings)
    run_test("6. Двухфакторный круг + настройки spin/speed", test_dual_pie_render)
    run_test("7. Выгрузка .py и реальный запуск генератора HTML", test_standalone_code_export_execution)
    run_test("8. Smoke-тест BlockInspector по всем типам блоков", test_inspector_ui_smoke)

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    print(f"\n=== ИТОГ: {passed}/{total} тестов пройдено ===")
    sys.exit(0 if passed == total else 1)