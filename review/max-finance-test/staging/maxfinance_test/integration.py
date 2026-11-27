"""Подключение тестового режима к действующему боту.

Модуль не запускает второго polling-обработчика и не создаёт второго бота.
Он добавляет маршруты и отдельное хранилище внутрь существующего процесса.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from pathlib import Path

from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.filters import Command
from aiogram.types import Message

from .handlers import ModeHandlers
from .store import TEST_DB_NAME, ModeStore


class UnavailableTestMode:
    """Fail-closed заглушка: при сбое TEST фото и команды не уходят в WORK."""

    def __init__(self, base: Path | str):
        self.root = Path(os.getenv("FINANCE_TEST_DIR", str(Path(base) / "test-mode"))).resolve()
        self.router = Router()
        self.router.message.register(
            self.blocked_command,
            Command("sync", "manual", "employees", "cancel", "back", "day", "week", "month", "start", "help"),
        )
        self.router.callback_query.register(
            self.blocked_callback, F.data.startswith("v3:") | F.data.startswith("st:")
        )
        # Свободный текст тоже не должен доходить до WORK: в рабочем режиме
        # он может изменить сотрудников или состояние черновика.
        self.router.message.register(self.blocked_text, F.text)

    def is_test(self, user_id: int) -> bool:
        path = self.root / TEST_DB_NAME
        sentinel = self.root / "active" / str(int(user_id))
        if sentinel.is_file():
            return True
        if not path.is_file():
            # Тестовое хранилище уже создавалось, но база исчезла: режим
            # пользователя неизвестен. Рабочие операции в таком состоянии
            # запрещены (fail closed), пока администратор не восстановит базу.
            # Если каталога тестового режима нет вовсе, режим ни разу не
            # включался и рабочая обработка разрешена.
            return self.root.is_dir()
        try:
            with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True)) as db:
                row = db.execute("SELECT value FROM settings WHERE key=?", (f"mode:{int(user_id)}",)).fetchone()
                return bool(row and row[0] == "TEST")
        except sqlite3.Error:
            # Файл есть, но прочитать режим нельзя: fail closed.
            return True

    async def handle_photo(self, message, bot, file) -> bool:
        if not self.is_test(message.from_user.id):
            return False
        await message.answer(
            "⛔ Тестовый режим временно недоступен. Фотография НЕ отправлена в рабочий режим. "
            "Сообщи администратору; рабочие данные не изменены."
        )
        return True

    async def blocked_command(self, message: Message) -> None:
        if not message.from_user or not self.is_test(message.from_user.id):
            raise SkipHandler
        await message.answer(
            "⛔ Тестовый режим временно недоступен. Рабочая команда отключена; "
            "рабочие данные и Google-таблица не изменяются."
        )

    async def blocked_text(self, message: Message) -> None:
        if not message.from_user or not self.is_test(message.from_user.id):
            raise SkipHandler
        await message.answer(
            "⛔ Тестовый режим временно недоступен. Текстовый ввод отключён; "
            "рабочие данные не изменяются."
        )

    async def blocked_callback(self, query) -> None:
        if not query.from_user or not self.is_test(query.from_user.id):
            raise SkipHandler
        await query.answer("Тестовый режим недоступен; рабочая кнопка отключена", show_alert=True)


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
