"""
Рендерер блоков отчёта в HTML.
Принимает список блоков → возвращает HTML.
"""

from src.core.blocks import Block


class Renderer:
    """Рендерит список блоков в HTML."""

    def __init__(self):
        self.blocks: list[Block] = []
        self.raw_items: list[str] = []

    def add(self, block: Block):
        self.blocks.append(block)

    def add_raw(self, html: str):
        self.raw_items.append(html)

    def clear(self):
        self.blocks.clear()
        self.raw_items.clear()

    def render(self) -> str:
        html_parts = []
        for block in self.blocks:
            try:
                html_parts.append(block.render())
            except Exception as e:
                html_parts.append(self._render_error(block, e))
        html_parts.extend(self.raw_items)
        return "\n".join(html_parts)

    def _render_error(self, block: Block, error: Exception) -> str:
        return f'''
        <div class="block">
            <div class="block-card error">
                <div class="block-error-title">⚠️ Ошибка в блоке</div>
                <div><b>Тип:</b> {block.type}</div>
                <div><b>ID:</b> {block.id}</div>
                <div><b>Ошибка:</b> {type(error).__name__}: {error}</div>
            </div>
        </div>
        '''


def render_blocks(blocks: list[Block]) -> str:
    r = Renderer()
    for b in blocks:
        r.add(b)
    return r.render()