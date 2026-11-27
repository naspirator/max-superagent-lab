"""Подключение тестового режима к действующему боту.

Модуль не запускает второго polling-обработчика и не создаёт второго бота.
Он добавляет маршруты и отдельное хранилище внутрь существующего процесса.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from pathlib import Path

from .handlers import ModeHandlers
from .store import TEST_DB_NAME, ModeStore


class UnavailableTestMode:
    """Fail-closed заглушка: при сбое TEST фото не уходит в рабочий режим."""

    def __init__(self, base: Path | str):
        self.root = Path(os.getenv("FINANCE_TEST_DIR", str(Path(base) / "test-mode"))).resolve()

    def is_test(self, user_id: int) -> bool:
        path = self.root / TEST_DB_NAME
        if not path.is_file():
            return False
        try:
            with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True)) as db:
                row = db.execute("SELECT value FROM settings WHERE key=?", (f"mode:{int(user_id)}",)).fetchone()
                return bool(row and row[0] == "TEST")
        except sqlite3.Error:
            return False

    async def handle_photo(self, message, bot, file) -> bool:
        if not self.is_test(message.from_user.id):
            return False
        await message.answer(
            "⛔ Тестовый режим временно недоступен. Фотография НЕ отправлена в рабочий режим. "
            "Сообщи администратору; рабочие данные не изменены."
        )
        return True


def create_test_handlers(base: Path | str, prod_db: Path | str | None,
                         prod_sheet_id: str | None, client, admin_id: int) -> ModeHandlers:
    root = Path(os.getenv("FINANCE_TEST_DIR", str(Path(base) / "test-mode"))).resolve()
    test_sheet_id = os.getenv("TEST_GOOGLE_SHEET_ID") or None
    store = ModeStore(
        root,
        prod_db=prod_db,
        prod_sheet_id=prod_sheet_id,
        test_sheet_id=test_sheet_id,
    )
    store.initialize()
    store.audit(None, "test_mode_initialized", f"root={root}")
    return ModeHandlers(store, client, admin_id)


__all__ = ["UnavailableTestMode", "create_test_handlers"]
