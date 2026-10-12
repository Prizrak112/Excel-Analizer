"""Быстрый тест рендера отчёта в HTML без UI."""
import pandas as pd
from src.core.report.block_model import Block, Step, ReportProject, Source
from src.core.report.sources import SourceManager
from src.core.report.renderer import render_report

# ── Тестовые данные ──
df = pd.DataFrame({
    "Дата": pd.date_range("2024-01-01", periods=10),
    "Продажи": [100, 150, 120, 200, 180, 220, 190, 240, 260, 300],
    "Регион": ["Москва"] * 5 + ["СПб"] * 5,
})

# ── Source без файла — заполняем кэш вручную ──
src = Source(id="src_test", kind="xlsx", path="test.xlsx", display_name="test.xlsx")
src._cache = {"Лист1": df}

sm = SourceManager()
sm._cache["src_test"] = {"Лист1": df}

# ── Проект с 4 блоками ──
project = ReportProject(title="Тестовый отчёт")
project.sources.append(src)

# Блок 1: KPI
project.add_block(Block(
    type="kpi", source_id="src_test", sheet="Лист1",
    x=20, y=20, width=280, height=120, z_index=0,
    kpi_config={
        "column": "Продажи", "agg": "sum",
        "title": "Всего продаж", "suffix": " ₽",
    },
))

# Блок 2: Line
project.add_block(Block(
    type="chart", source_id="src_test", sheet="Лист1",
    x=320, y=20, width=600, height=320, z_index=1,
    chart_type="line",
    chart_config={"x": "Дата", "y": ["Продажи"], "title": "Продажи по датам"},
))

# Блок 3: Таблица
project.add_block(Block(
    type="table", source_id="src_test", sheet="Лист1",
    x=20, y=180, width=280, height=200, z_index=2,
    table_config={"columns": ["Дата", "Продажи"], "limit": 10},
))

# Блок 4: Текст
project.add_block(Block(
    type="text",
    x=20, y=400, width=400, height=150, z_index=3,
    text_config={"content": "## Заголовок\n\nЭто тестовый отчёт.\n- Пункт 1\n- Пункт 2"},
))

# ── Рендер ──
html = render_report(project, sm)
with open("test_report.html", "w", encoding="utf-8") as f:
    f.write(html)

print(f"OK. HTML сохранён: test_report.html ({len(html):,} байт)")
print("Открой его в браузере.")