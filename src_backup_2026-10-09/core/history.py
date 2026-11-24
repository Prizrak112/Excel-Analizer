"""
Менеджер истории команд (только Undo, без Redo).
"""

from abc import ABC, abstractmethod


# ============================================================
# Базовая команда
# ============================================================

class Command(ABC):
    """Базовый класс команды."""
    
    @abstractmethod
    def do(self):
        """Выполнить команду."""
        pass
    
    @abstractmethod
    def undo(self):
        """Отменить команду."""
        pass
    
    def description(self) -> str:
        """Описание команды для UI."""
        return "Действие"


# ============================================================
# Универсальная команда
# ============================================================

class CallbackCommand(Command):
    """
    Универсальная команда: do_func + undo_func.
    Используется для простых действий.
    """
    
    def __init__(self, do_func, undo_func, desc: str = "Действие"):
        self._do_func = do_func
        self._undo_func = undo_func
        self._desc = desc
    
    def do(self):
        self._do_func()
    
    def undo(self):
        self._undo_func()
    
    def description(self) -> str:
        return self._desc


# ============================================================
# Менеджер истории
# ============================================================

class HistoryManager:
    """
    Менеджер истории команд.
    Хранит только Undo-стек. Redo отсутствует.
    """
    
    DEFAULT_MAX_SIZE = 50
    
    def __init__(self, max_size: int = DEFAULT_MAX_SIZE):
        self._undo_stack: list[Command] = []
        self._max_size = max_size
    
    # ---------- Выполнение ----------
    
    def execute(self, command: Command):
        """
        Выполнить команду и добавить в историю.
        """
        try:
            command.do()
            self._push(command)
        except Exception as e:
            print(f"[HistoryManager] Ошибка выполнения: {e}")
            raise
    
    def push(self, command: Command):
        """
        Добавить уже выполненную команду в историю.
        Используется, если команда выполнилась где-то ещё.
        """
        self._push(command)
    
    def _push(self, command: Command):
        """Внутренняя логика добавления."""
        self._undo_stack.append(command)
        
        # Обрезаем стек, если превысили лимит
        while len(self._undo_stack) > self._max_size:
            self._undo_stack.pop(0)
    
    # ---------- Отмена ----------
    
    def undo(self) -> tuple[bool, str]:
        """
        Отменить последнее действие.
        Возвращает (успех, описание).
        """
        if not self._undo_stack:
            return False, "Нечего отменять"
        
        command = self._undo_stack.pop()
        
        try:
            command.undo()
            return True, command.description()
        except Exception as e:
            print(f"[HistoryManager] Ошибка отмены: {e}")
            # Возвращаем обратно при ошибке
            self._undo_stack.append(command)
            return False, f"Ошибка отмены: {e}"
    
    # ---------- Состояние ----------
    
    def can_undo(self) -> bool:
        """Есть ли что отменять?"""
        return len(self._undo_stack) > 0
    
    def get_last_description(self) -> str:
        """Описание последнего действия (для tooltip)."""
        if not self._undo_stack:
            return "Нет действий"
        return self._undo_stack[-1].description()
    
    def get_size(self) -> int:
        """Размер истории."""
        return len(self._undo_stack)
    
    def clear(self):
        """Очистить историю."""
        self._undo_stack.clear()
    
    def get_descriptions(self) -> list[str]:
        """Список описаний всех действий (для отладки)."""
        return [cmd.description() for cmd in self._undo_stack]