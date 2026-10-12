"""
Модель отчёта.
Описывает структуру: Report → Section → ReportBlock.
НЕ рендерит HTML — только хранит данные.
"""

import uuid
from dataclasses import dataclass, field


# ============================================================
# Блок отчёта
# ============================================================

@dataclass
class ReportBlock:
    """
    Один блок отчёта.
    Тип определяет, как рендерить.
    Config — параметры блока.
    """
    id: str
    type: str                    # см. BLOCK_TYPES в block_factory.py
    config: dict = field(default_factory=dict)
    
    @classmethod
    def create(cls, block_type: str, config: dict | None = None) -> "ReportBlock":
        """Создать блок с авто-ID."""
        return cls(
            id=_generate_id(),
            type=block_type,
            config=config or {},
        )

    # ---------- Размеры ----------

    def get_width(self) -> int:
        """Ширина блока в % (25 / 33 / 50 / 66 / 75 / 100)."""
        return int(self.config.get("width", 100))

    def get_margin_top(self) -> int:
        return int(self.config.get("margin_top", 0))

    def get_margin_bottom(self) -> int:
        return int(self.config.get("margin_bottom", 14))

    def get_min_height(self) -> int:
        return int(self.config.get("min_height", 0))


# ============================================================
# Раздел отчёта
# ============================================================

@dataclass
class Section:
    """Раздел отчёта: заголовок + список блоков."""
    id: str
    title: str
    icon: str = "📊"
    expanded: bool = True
    blocks: list[ReportBlock] = field(default_factory=list)
    
    @classmethod
    def create(cls, title: str, icon: str = "📊") -> "Section":
        return cls(id=_generate_id(), title=title, icon=icon)
    
    def add_block(self, block: ReportBlock):
        self.blocks.append(block)
    
    def remove_block(self, block_id: str):
        self.blocks = [b for b in self.blocks if b.id != block_id]
    
    def get_block(self, block_id: str) -> ReportBlock | None:
        for b in self.blocks:
            if b.id == block_id:
                return b
        return None
    
    def move_block(self, block_id: str, new_index: int):
        block = self.get_block(block_id)
        if block is None:
            return
        self.blocks.remove(block)
        new_index = max(0, min(new_index, len(self.blocks)))
        self.blocks.insert(new_index, block)


# ============================================================
# Отчёт целиком
# ============================================================

@dataclass
class Report:
    """Отчёт: список разделов + общие настройки."""
    title: str = "Новый отчёт"
    sections: list[Section] = field(default_factory=list)
    theme: str = "gsm_green"
    
    # ---------- Разделы ----------
    
    def add_section(self, title: str, icon: str = "📊") -> Section:
        section = Section.create(title, icon)
        self.sections.append(section)
        return section
    
    def remove_section(self, section_id: str):
        self.sections = [s for s in self.sections if s.id != section_id]
    
    def get_section(self, section_id: str) -> Section | None:
        for s in self.sections:
            if s.id == section_id:
                return s
        return None
    
    def move_section(self, section_id: str, new_index: int):
        section = self.get_section(section_id)
        if section is None:
            return
        self.sections.remove(section)
        new_index = max(0, min(new_index, len(self.sections)))
        self.sections.insert(new_index, section)
    
    # ---------- Поиск ----------
    
    def find_block(self, block_id: str) -> tuple[Section, ReportBlock] | None:
        """
        Найти блок во всём отчёте (включая вложенные в контейнеры).
        Возвращает (раздел, блок).
        """
        for section in self.sections:
            found = _find_block_recursive(section.blocks, block_id)
            if found is not None:
                return (section, found)
        return None
    
    def find_block_parent(self, block_id: str) -> tuple[Section, list[ReportBlock], ReportBlock] | None:
        """
        Найти блок И его родительский список (для вложенных — children контейнера).
        Возвращает (section, parent_list, block).
        """
        for section in self.sections:
            result = _find_block_parent_recursive(section.blocks, block_id, section)
            if result is not None:
                return result
        return None

    # ---------- Перемещение ----------

    def move_block_across(self, block_id: str, target_section_id: str, new_index: int) -> bool:
        """Переместить блок в другой раздел (или в тот же)."""
        src = self.find_block_parent(block_id)
        if src is None:
            return False
        src_section, src_list, block = src

        target_section = self.get_section(target_section_id)
        if target_section is None:
            return False

        # Убираем из старого списка
        src_list.remove(block)

        # Вставляем в новый (только на верхнем уровне раздела)
        new_index = max(0, min(new_index, len(target_section.blocks)))
        target_section.blocks.insert(new_index, block)
        return True

    # ---------- Слияние ----------

    def merge_blocks(self, source_id: str, target_id: str, layout: str = "row") -> bool:
        """
        Слить два блока в контейнер.
        source_id — блок, который тащат.
        target_id — блок, на который упало.
        Результат: контейнер с [target, source] вместо target.
        """
        if source_id == target_id:
            return False

        src = self.find_block_parent(source_id)
        tgt = self.find_block_parent(target_id)
        if src is None or tgt is None:
            return False

        src_section, src_list, src_block = src
        tgt_section, tgt_list, tgt_block = tgt

        # Нельзя сливать блок в его же потомка
        if _contains_block(src_block, target_id):
            return False

        # Создаём контейнер
        container = ReportBlock.create("container", {
            "layout": layout,
            "gap": 14,
            "children": [tgt_block, src_block],
        })

        # Заменяем target на container в его списке
        tgt_idx = tgt_list.index(tgt_block)
        tgt_list[tgt_idx] = container

        # Удаляем source из его списка
        src_list.remove(src_block)

        return True

    # ---------- Статистика ----------

    def is_empty(self) -> bool:
        return len(self.sections) == 0

    def get_stats(self) -> dict:
        total_blocks = sum(_count_blocks(s.blocks) for s in self.sections)
        return {
            "sections": len(self.sections),
            "blocks": total_blocks,
        }


# ============================================================
# Утилиты
# ============================================================

def _generate_id() -> str:
    return uuid.uuid4().hex[:8]


def _find_block_recursive(blocks: list, block_id: str) -> ReportBlock | None:
    """Ищет блок в списке, включая children контейнеров."""
    for b in blocks:
        if b.id == block_id:
            return b
        if b.type == "container":
            found = _find_block_recursive(b.config.get("children", []), block_id)
            if found is not None:
                return found
    return None


def _find_block_parent_recursive(blocks: list, block_id: str, section) -> tuple | None:
    """Ищет блок и его родительский список."""
    for b in blocks:
        if b.id == block_id:
            return (section, blocks, b)
        if b.type == "container":
            found = _find_block_parent_recursive(
                b.config.get("children", []), block_id, section,
            )
            if found is not None:
                return found
    return None


def _contains_block(container_block: ReportBlock, block_id: str) -> bool:
    """Проверяет, содержит ли container_block блок с данным id (рекурсивно)."""
    if container_block.type != "container":
        return False
    for child in container_block.config.get("children", []):
        if child.id == block_id:
            return True
        if _contains_block(child, block_id):
            return True
    return False


def _count_blocks(blocks: list) -> int:
    """Считает блоки рекурсивно (включая детей контейнеров)."""
    total = 0
    for b in blocks:
        total += 1
        if b.type == "container":
            total += _count_blocks(b.config.get("children", []))
    return total