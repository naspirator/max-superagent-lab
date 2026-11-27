"""Интеграционные проверки через настоящий диспетчер aiogram.

Обработчики вызываются не напрямую, а через `Dispatcher.feed_update`, как в
рабочем боте: обновление проходит по роутерам, а ответы уходят в сессию Bot.
Роутеры повторяют порядок `bot.py`: сначала тестовый роутер, затем рабочие
обработчики.
"""
import asyncio

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.session.base import BaseSession
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.filters import Command
from aiogram.types import Message, Update

from maxfinance_test.handlers import ModeHandlers
from maxfinance_test.store import ModeStore

DATE = 1732776000


class RecordingSession(BaseSession):
    """Сессия Bot без сети: запоминает исходящие методы и возвращает Message."""

    def __init__(self):
        super().__init__()
        self.sent = []

    async def close(self):
        return None

    async def stream_content(self, *args, **kwargs):
        if False:  # pragma: no cover - абстрактный генератор
            yield b""

    async def make_request(self, bot, method, timeout=None):
        self.sent.append(method)
        name = type(method).__name__
        if name in ("SendMessage", "EditMessageText"):
            return Message.model_validate(
                {
                    "message_id": 1,
                    "date": DATE,
                    "chat": {"id": 1, "type": "private"},
                    "text": getattr(method, "text", "") or "",
                },
                context={"bot": bot},
            )
        return True

    def texts(self):
        return [
            m.text for m in self.sent
            if type(m).__name__ in ("SendMessage", "EditMessageText")
        ]


def make_update(uid, text=None, photo=False, update_id=1):
    message = {
        "message_id": 10,
        "date": DATE,
        "chat": {"id": uid, "type": "private"},
        "from": {"id": uid, "is_bot": False, "first_name": "T"},
    }
    if text is not None:
        message["text"] = text
    if photo:
        message["photo"] = [
            {"file_id": "f1", "file_unique_id": "u1", "width": 10, "height": 10}
        ]
    return Update.model_validate({"update_id": update_id, "message": message})


def build_dispatcher(handlers):
    """Роутеры в порядке bot.py: тестовый, фото, рабочие обработчики."""
    calls = []
    dp = Dispatcher()
    dp.include_router(handlers.router)

    photo_router = Router()

    @photo_router.message(F.photo)
    async def test_photo(message: Message, bot: Bot):
        # Повторяет ветку process_photo из bot.py: тестовый режим сначала.
        if await handlers.handle_photo(message, bot, None):
            return
        # Не тестовый пользователь — обновление уходит следующему роутеру
        # (в боте это продолжение process_photo, а не отдельный хендлер).
        raise SkipHandler

    dp.include_router(photo_router)

    work = Router()

    @work.message(Command("sync"))
    async def work_sync(message: Message):
        calls.append("sync")
        await message.answer("рабочий sync")

    @work.message(F.text)
    async def work_text(message: Message):
        calls.append("text")
        await message.answer("рабочий текст")

    @work.message(F.photo)
    async def work_photo(message: Message):
        calls.append("photo")
        await message.answer("рабочее фото")

    dp.include_router(work)
    return dp, calls


def recovered_store(tmp_path):
    root = tmp_path / "test-mode"
    store = ModeStore(root)
    store.initialize()
    store.set_setting("mode:1", "TEST")
    (root / "test_finance.db").unlink()
    for marker in (root / "active").glob("*"):
        marker.unlink()
    # Обычное обращение к хранилищу после потери БД создаёт пустой файл.
    store.connect().close()
    again = ModeStore(root)
    again.initialize()
    assert again.recovered is True
    return again


def run_updates(store, tmp_path):
    handlers = ModeHandlers(store, client=None, admin_id=1)
    dp, calls = build_dispatcher(handlers)
    session = RecordingSession()
    bot = Bot(token="42:TEST", session=session)

    async def go():
        await dp.feed_update(bot, make_update(1, "/sync"))
        await dp.feed_update(bot, make_update(1, "привет", update_id=2))
        await dp.feed_update(bot, make_update(1, photo=True, update_id=3))
        await session.close()

    asyncio.run(go())
    return calls, session.texts()


def test_dispatcher_blocks_sync_text_and_photo_after_db_loss(tmp_path):
    store = recovered_store(tmp_path)
    calls, texts = run_updates(store, tmp_path)
    assert calls == []
    joined = "\n".join(texts)
    assert "отключена" in joined
    assert "потеряна" in joined or "отключён" in joined
    assert "НЕ отправлена" in joined


def test_dispatcher_blocks_when_meta_survives_but_settings_table_is_lost(tmp_path):
    import sqlite3

    store = recovered_store(tmp_path)
    with sqlite3.connect(store.db_path) as db:
        db.execute("DROP TABLE settings")
        db.commit()
    again = ModeStore(store.root)
    again.initialize()
    assert again.recovered is True
    calls, texts = run_updates(again, tmp_path)
    assert calls == []
    assert "отключена" in "\n".join(texts)


def test_dispatcher_allows_work_user_without_test_marker(tmp_path):
    store = ModeStore(tmp_path / "clean-mode")
    store.initialize()
    handlers = ModeHandlers(store, client=None, admin_id=1)
    dp, calls = build_dispatcher(handlers)
    session = RecordingSession()
    bot = Bot(token="42:TEST", session=session)

    async def go():
        await dp.feed_update(bot, make_update(5, "/sync"))
        await dp.feed_update(bot, make_update(5, "привет", update_id=2))
        await dp.feed_update(bot, make_update(5, photo=True, update_id=3))
        await session.close()

    asyncio.run(go())
    assert calls == ["sync", "text", "photo"]
