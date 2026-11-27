"""Регрессии по замечаниям третьего цикла ChatGPT.

Эти проверки воспроизводят конкретные сценарии, которые раньше проходили
неверно. Они не заменяют независимую приёмку, но фиксируют исправления.
"""
import asyncio
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from maxfinance_test.ensemble import merge_amounts
from maxfinance_test.handlers import ModeHandlers, _item_index
from maxfinance_test.integration import UnavailableTestMode
from maxfinance_test.model import Item, Report
from maxfinance_test.store import ModeStore


class FakeUser:
    id = 1


class FakeChat:
    type = "private"


class FakeMessage:
    message_id = 5

    def __init__(self):
        self.chat = FakeChat()

    async def answer(self, *args, **kwargs):
        return self

    async def edit_text(self, *args, **kwargs):
        return self


class FakeQuery:
    def __init__(self, data):
        self.data = data
        self.from_user = FakeUser()
        self.message = FakeMessage()

    async def answer(self, *args, **kwargs):
        return None


class FakeTextMessage:
    def __init__(self, uid):
        self.from_user = SimpleNamespace(id=uid)
        self.chat = SimpleNamespace(type="private")
        self.text = "привет"
        self.answers = []

    async def answer(self, text, **kwargs):
        self.answers.append(text)
        return self


def make_store(tmp_path: Path) -> ModeStore:
    store = ModeStore(tmp_path / "test")
    store.initialize()
    return store


def test_mode_marker_is_written_by_set_setting_and_survives_db_loss(tmp_path):
    root = tmp_path / "test-mode"
    store = ModeStore(root)
    store.initialize()
    store.set_setting("mode:1", "TEST")
    assert (root / "active" / "1").is_file()

    # База тестового режима исчезла. Маркер обязан удержать fail-closed.
    (root / "test_finance.db").rename(root / "moved.db")
    guard = UnavailableTestMode(tmp_path)
    assert guard.is_test(1) is True
    # Маркера нет, но тестовое хранилище существовало: режим неизвестен,
    # поэтому рабочая обработка тоже запрещена.
    assert guard.is_test(2) is True


def test_unavailable_guard_allows_work_only_if_test_store_never_existed(tmp_path):
    # Каталога тестового режима нет: режим никогда не включался, рабочие
    # команды не блокируются.
    guard = UnavailableTestMode(tmp_path / "clean-install")
    assert guard.is_test(1) is False


def test_recreated_db_after_marker_loss_fails_closed(tmp_path):
    root = tmp_path / "test-mode"
    store = ModeStore(root)
    store.initialize()
    store.set_setting("mode:1", "TEST")
    # Имитируем потерю БД и маркера: режим был установлен, но пользователь
    # больше нигде не отмечен.
    (root / "test_finance.db").unlink()
    for marker in (root / "active").glob("*"):
        marker.unlink()
    again = ModeStore(root)
    again.initialize()
    assert again.recovered is True
    handlers = ModeHandlers(again, client=None, admin_id=1)
    assert handlers.is_test(1) is True
    assert handlers.is_test(2) is True
    assert UnavailableTestMode(tmp_path).is_test(2) is True


def test_first_install_is_not_recovered(tmp_path):
    store = ModeStore(tmp_path / "fresh-mode")
    store.initialize()
    assert store.recovered is False
    handlers = ModeHandlers(store, client=None, admin_id=1)
    assert handlers.is_test(1) is False


def test_recovered_mode_blocks_sync_text_and_photo(tmp_path):
    root = tmp_path / "test-mode"
    store = ModeStore(root)
    store.initialize()
    store.set_setting("mode:1", "TEST")
    (root / "test_finance.db").unlink()
    for marker in (root / "active").glob("*"):
        marker.unlink()

    # Перезапуск бота после потери БД: initialize() создаёт пустую базу.
    again = ModeStore(root)
    again.initialize()
    handlers = ModeHandlers(again, client=None, admin_id=1)

    sync = FakeTextMessage(1)
    asyncio.run(handlers.cmd_blocked(sync))
    assert sync.answers and "отключена" in sync.answers[0]

    text = FakeTextMessage(1)
    asyncio.run(handlers.on_text(text))
    assert text.answers and "потеряна" in text.answers[0]

    photo = FakeTextMessage(3)
    handled = asyncio.run(handlers.handle_photo(photo, None, None))
    assert handled is True
    assert photo.answers and "НЕ отправлена" in photo.answers[0]


def test_unavailable_mode_blocks_free_text_for_test_user(tmp_path):
    from aiogram.dispatcher.event.bases import SkipHandler

    root = tmp_path / "test-mode"
    store = ModeStore(root)
    store.initialize()
    store.set_setting("mode:1", "TEST")
    guard = UnavailableTestMode(tmp_path)

    message = FakeTextMessage(1)
    asyncio.run(guard.blocked_text(message))
    assert message.answers and "отключён" in message.answers[0]

    # Пользователь без режима TEST — обычный рабочий пользователь.
    with pytest.raises(SkipHandler):
        asyncio.run(guard.blocked_text(FakeTextMessage(2)))

    # Если база исчезла, режим неизвестен: блокируются все.
    (root / "test_finance.db").rename(root / "moved.db")
    unknown = UnavailableTestMode(tmp_path)
    stranger = FakeTextMessage(2)
    asyncio.run(unknown.blocked_text(stranger))
    assert stranger.answers

    # Если тестового хранилища нет вовсе, текст проходит в рабочий режим.
    clean = UnavailableTestMode(tmp_path / "clean-install")
    with pytest.raises(SkipHandler):
        asyncio.run(clean.blocked_text(FakeTextMessage(3)))


def test_numeric_item_id_is_not_treated_as_index(tmp_path):
    report = Report(
        "2026-11-27",
        photo_reviewed=True,
        items=[Item([Decimal("1000")], category="nal")],
    )
    report.items[0].item_id = "123456789012"
    assert _item_index(report, "123456789012") == 0
    # Обычный числовой индекс по-прежнему работает.
    assert _item_index(report, "0") == 0


def test_staff_card_callback_reaches_card_not_list(tmp_path):
    store = make_store(tmp_path)
    store.set_setting("mode:1", "TEST")
    handlers = ModeHandlers(store, client=None, admin_id=1)
    calls = []

    async def fake_staff_action(query, action, args, uid, nonce):
        calls.append((action, list(args)))

    async def fake_send(*args, **kwargs):
        return None

    handlers._staff_action = fake_staff_action
    handlers._send = fake_send
    query = FakeQuery("tt:nonce:staff:3")

    import asyncio

    asyncio.run(handlers.on_callback(query))
    assert calls == [("staff", ["3"])]


def test_add_employee_after_deactivating_max_id(tmp_path):
    store = make_store(tmp_path)
    people = store.staff(active_only=False)
    max_id = max(person["id"] for person in people)
    store.remove_employee(max_id)
    new_id = store.add_employee("НОВ")
    assert new_id == max_id + 1
    assert any(person["name"] == "НОВ" for person in store.staff())


def test_ensemble_does_not_turn_minus_into_plus(tmp_path):
    report = Report(
        "2026-11-27",
        photo_reviewed=True,
        items=[
            Item(
                [Decimal("500")],
                ["-"],
                category="debt",
                uncertain=True,
                bbox=(0.0, 0.0, 1.0, 1.0),
            )
        ],
    )
    old = [SimpleNamespace(terms=[500], bbox=(0.0, 0.0, 1.0, 1.0))]
    # Воспроизводим «сырой» вход парсера: минус в terms, плюс в signs.
    report.items[0].terms = [Decimal("-500")]
    report.items[0].signs = ["+"]
    merged, replaced = merge_amounts(report, old)
    assert replaced == 0
    assert merged.items[0].amount == Decimal("-500")
    assert merged.items[0].signs == ["+"]
