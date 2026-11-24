"""
Демонстрационные блоки для проверки рендеринга.
Позже заменим на данные из Excel.
"""

from src.core.blocks import (
    SectionTitleBlock, ParagraphBlock, KpiRowBlock, KpiCard,
    ListBlock, DividerBlock,
)


def get_demo_blocks_set_1() -> list:
    """Первый набор блоков."""
    return [
        SectionTitleBlock(
            id="s1",
            title="Общая аналитика ГСМ"
        ),
        ParagraphBlock(
            id="p1",
            text=(
                "Это демонстрационный отчёт. Здесь показано, "
                "как приложение рендерит блоки в стиле твоего отчёта ГСМ.\n\n"
                "Стили полностью соответствуют оригинальному HTML — "
                "зелёные акценты, карточки с тенью, скруглённые углы."
            )
        ),
        KpiRowBlock(
            id="kpi1",
            cards=[
                KpiCard(label="Всего ТС", value="1 234"),
                KpiCard(label="Оснащено ГЛОНАСС", value="85.3%", accent=True),
                KpiCard(label="Типов ТС", value="29"),
                KpiCard(label="Моделей", value="142"),
            ]
        ),
        DividerBlock(id="d1"),
        SectionTitleBlock(
            id="s2",
            title="Что уже работает"
        ),
        ListBlock(
            id="l1",
            items=[
                "✅ Каркас приложения (меню, тулбар, панели)",
                "✅ QWebEngineView — встроенный браузер",
                "✅ QWebChannel — мост JS ↔ Python",
                "✅ Рендеринг блоков в HTML",
                "✅ Стили из отчёта ГСМ",
                "⏳ Загрузка данных из Excel (следующий шаг)",
                "⏳ Настройка блоков через UI",
                "⏳ Экспорт в HTML-файл",
            ]
        ),
    ]


def get_demo_blocks_set_2() -> list:
    """Второй набор блоков — для проверки кнопки 'Перерендерить'."""
    return [
        SectionTitleBlock(
            id="s1",
            title="Автоматизированные датчики учёта"
        ),
        ParagraphBlock(
            id="p1",
            text=(
                "Это <b>второй набор блоков</b>. Он показывает, "
                "что рендеринг работает динамически — Python генерирует HTML "
                "по запросу из JavaScript.\n\n"
                "В будущем здесь будут реальные данные из твоего Excel."
            )
        ),
        KpiRowBlock(
            id="kpi1",
            cards=[
                KpiCard(label="Система ГЛОНАСС", value="1 042 из 1 234"),
                KpiCard(label="Расходомеры", value="986 из 1 042", accent=True),
                KpiCard(label="Одометры", value="1 018 из 1 042"),
                KpiCard(label="ДУТ", value="325 из 1 042"),
            ]
        ),
        DividerBlock(id="d1"),
        SectionTitleBlock(
            id="s2",
            title="Наблюдения"
        ),
        ListBlock(
            id="l1",
            items=[
                "84.5% ТС оснащены системой ГЛОНАСС",
                "94.6% из оснащённых имеют расходомеры",
                "97.7% из оснащённых имеют одометры",
                "31.2% из оснащённых имеют датчики ДУТ",
            ]
        ),
    ]