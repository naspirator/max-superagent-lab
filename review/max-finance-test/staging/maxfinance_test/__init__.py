"""MAX FINANCE TEST — тестовый режим действующего бота.

Пакет намеренно не импортирует рабочие sheets_v3/reports и не открывает
рабочую базу на запись. Единственное чтение рабочей базы — копирование
сотрудников и обозначений при первом создании тестового хранилища.
"""
from .aliases import AliasBook, DEFAULT_ALIASES
from .integration import UnavailableTestMode, create_test_handlers
from .model import Item, Report
from .ocr import ENGINE_VERSION
from .store import IsolationError, ModeStore

__all__ = [
    "AliasBook", "DEFAULT_ALIASES", "ENGINE_VERSION", "IsolationError", "Item",
    "Report", "ModeStore", "UnavailableTestMode", "create_test_handlers",
]
