import json
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

from maxfinance_test import ui
from maxfinance_test.aliases import AliasBook, DEFAULT_ALIASES
from maxfinance_test.handlers import ModeHandlers, _two_amounts
from maxfinance_test.model import Item, Report
from maxfinance_test.store import ModeStore


@pytest.fixture
def env(tmp_path):
    prod = tmp_path / "prod" / "finance.db"
    prod.parent.mkdir()
    connection = sqlite3.connect(prod)
    connection.executescript(
        "CREATE TABLE staff_v3(id INTEGER PRIMARY KEY,name TEXT,active INTEGER);"
        "CREATE TABLE staff_alias_v3(alias TEXT PRIMARY KEY,staff_id INTEGER);"
    )
    staff = [(1, "ПЕТ", 1), (2, "РОС", 1), (3, "ДИМ", 1), (4, "ОЛИ", 1),
             (5, "ТОЛ", 1), (6, "ДАН", 1), (7, "ВЛА", 1)]
    connection.executemany("INSERT INTO staff_v3 VALUES (?,?,?)", staff)
    connection.executemany("INSERT INTO staff_alias_v3 VALUES (?,?)", [(n, i) for i, n, _ in staff])
    connection.commit()
    connection.close()
    store = ModeStore(tmp_path / "test", prod_db=prod)
    store.initialize()
    return store


def sample_report():
    return Report(
        "2026-11-27",
        items=[
            Item([Decimal("12000")], category="beznal"),
            Item([Decimal("10050")], category="nal"),
            Item([Decimal("7150")], category="employee", employee_id=1, source="nal", alias="П"),
            Item([Decimal("500")], category="expense"),
        ],
        version=1,
    )


def test_items_text_and_keyboard_cover_every_action(env):
    report = sample_report()
    book = env.alias_book()
    text = ui.items_text(report, 0, book, env)
    assert "MAX FINANCE TEST" in text
    assert "Безнал" in text and "Наличные" in text
    markup = ui.items_keyboard(report, 0, report.nonce)
    datas = [b.callback_data for row in markup.inline_keyboard for b in row]
    for action in ("add", "totals", "date", "lineedit", "rerun", "undo", "review", "cancel"):
        assert any(d.endswith(":" + action) for d in datas), action
    assert all(len(d.encode()) <= 64 for d in datas)


def test_item_keyboard_exposes_every_edit(env):
    report = sample_report()
    markup = ui.item_keyboard(report, 0, report.nonce)
    datas = [b.callback_data for row in markup.inline_keyboard for b in row]
    for action in ("amount", "terms", "employee", "alias", "category", "source",
                   "split", "merge", "up", "down", "delete"):
        assert any(f":{action}:" in d for d in datas), action


def test_terms_and_signs_keyboard(env):
    report = Report("2026-11-27", photo_reviewed=True, items=[Item([Decimal("6000"), Decimal("1450")], ["+", "+"])])
    markup = ui.terms_keyboard(report, 0, report.nonce)
    datas = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert any(":term:" in d and d.endswith(":0") for d in datas)
    assert any("addterm" in d for d in datas)
    term_markup = ui.term_keyboard(0, 1, report.nonce)
    term_datas = [b.callback_data for row in term_markup.inline_keyboard for b in row]
    assert any("signminus" in d for d in term_datas)


def test_manual_total_shows_discrepancy_and_keeps_employee(env):
    report = sample_report()
    report.set_category_total("nal", 11000)
    text = ui.totals_text(report)
    assert "расхождение 950" in text
    assert "не меняются" in text
    assert report.employee_total_for(1) == Decimal("7150")


def test_summary_does_not_invent_itog(env):
    report = sample_report()
    text = ui.summary_text(report, env.alias_book())
    assert "Итог" not in text
    assert "в рабочую google-таблицу ничего не будет отправлено" in text.lower()


def test_examples_and_staff_text(env):
    assert "Подтверждённых примеров: 0" in ui.examples_text(env)
    text = ui.staff_text(env)
    assert "ПЕТ" in text and "П" in text


def test_two_amounts_parser():
    assert _two_amounts("1500 2000") == ("1500", "2000")
    assert _two_amounts("1500+2000") == ("1500", "2000")
    assert _two_amounts("1 500,50 2 000") == ("1 500,50", "2 000")
    with pytest.raises(Exception):
        _two_amounts("1500")


class FakeUser:
    id = 1


class FakeChat:
    type = "private"


class FakeMessage:
    def __init__(self, text=""):
        self.text = text
        self.from_user = FakeUser()
        self.chat = FakeChat()
        self.answers = []
        self.message_id = 10

    async def answer(self, text, reply_markup=None):
        self.answers.append((text, reply_markup))
        return self

    async def edit_reply_markup(self, reply_markup=None):
        return True

    async def edit_media(self, media, reply_markup=None):
        return True


class FakeQuery:
    def __init__(self, data):
        self.data = data
        self.from_user = FakeUser()
        self.message = FakeMessage()
        self.answered = []

    async def answer(self, text="", show_alert=False):
        self.answered.append(text)


@pytest.mark.asyncio
async def test_text_amount_edit_flow(env):
    store = env
    store.set_setting("mode:1", "TEST")
    report = sample_report()
    store.save_draft(1, report)
    handlers = ModeHandlers(store, client=None, admin_id=1)
    handlers.editing[1] = ("amount", report.items[0].item_id)
    message = FakeMessage("11000+1500")
    await handlers.on_text(message)
    loaded = store.load_draft(1)
    assert loaded.items[0].amount == Decimal("12500")
    assert loaded.items[0].origin == "manual"


@pytest.mark.asyncio
async def test_callback_category_and_undo(env):
    store = env
    store.set_setting("mode:1", "TEST")
    report = sample_report()
    store.save_draft(1, report)
    handlers = ModeHandlers(store, client=None, admin_id=1)
    query = FakeQuery(f"tt:{report.nonce}:setcat:3:debt")
    await handlers.on_callback(query)
    loaded = store.load_draft(1)
    assert loaded.items[3].category == "debt"
    undo = FakeQuery(f"tt:{report.nonce}:undo")
    await handlers.on_callback(undo)
    loaded = store.load_draft(1)
    assert loaded.items[3].category == "expense"


@pytest.mark.asyncio
async def test_callback_uses_item_id_and_rejects_deleted_item(env):
    store = env
    store.set_setting("mode:1", "TEST")
    report = sample_report()
    store.save_draft(1, report)
    handlers = ModeHandlers(store, client=None, admin_id=1)
    item_id = report.items[0].item_id
    query = FakeQuery(f"tt:{report.nonce}:setcat:{item_id}:debt")
    await handlers.on_callback(query)
    loaded = store.load_draft(1)
    index = loaded.index_of(item_id)
    assert loaded.items[index].category == "debt"

    delete = FakeQuery(f"tt:{report.nonce}:delete:{item_id}")
    await handlers.on_callback(delete)
    old = FakeQuery(f"tt:{report.nonce}:item:{item_id}")
    await handlers.on_callback(old)
    assert any("не существует" in answer[0] for answer in old.message.answers)


@pytest.mark.asyncio
async def test_callback_rejects_wrong_nonce(env):
    store = env
    store.set_setting("mode:1", "TEST")
    report = sample_report()
    store.save_draft(1, report)
    handlers = ModeHandlers(store, client=None, admin_id=1)
    query = FakeQuery("tt:deadbeef:setcat:0:nal")
    await handlers.on_callback(query)
    assert any("устарела" in x for x in query.answered)
