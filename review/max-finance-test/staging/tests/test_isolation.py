import ast
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

from maxfinance_test.handlers import ModeHandlers
from maxfinance_test.integration import UnavailableTestMode
from maxfinance_test.model import Item, Report
from maxfinance_test.store import IsolationError, ModeStore


def prod_db(tmp_path):
    path = tmp_path / "prod" / "finance.db"
    path.parent.mkdir()
    connection = sqlite3.connect(path)
    connection.executescript(
        "CREATE TABLE staff_v3(id INTEGER PRIMARY KEY,name TEXT,active INTEGER);"
        "CREATE TABLE staff_alias_v3(alias TEXT PRIMARY KEY,staff_id INTEGER);"
    )
    connection.execute("INSERT INTO staff_v3 VALUES (1,'ПЕТ',1)")
    connection.execute("INSERT INTO staff_alias_v3 VALUES ('П',1)")
    connection.commit()
    connection.close()
    return path


def test_test_sheet_cannot_equal_prod_sheet(tmp_path):
    with pytest.raises(IsolationError):
        ModeStore(tmp_path / "test", prod_db=prod_db(tmp_path), prod_sheet_id="SAME", test_sheet_id="SAME")


def test_test_db_cannot_be_prod_db(tmp_path):
    prod = prod_db(tmp_path)
    with pytest.raises(IsolationError):
        ModeStore(prod.parent, prod_db=prod)


def test_test_package_has_no_google_or_prod_sync_calls():
    package = Path(__file__).resolve().parents[1] / "maxfinance_test"
    forbidden = ("gspread", "sheets_v3", "sync_with_tracking", "sync_everything")
    for path in package.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                assert not any(word in name for word in forbidden), (path.name, name)


class FakeUser:
    id = 1


class FakeChat:
    type = "private"


class FakeMessage:
    def __init__(self):
        self.from_user = FakeUser()
        self.chat = FakeChat()
        self.answers = []
        self.message_id = 1

    async def answer(self, text, reply_markup=None):
        self.answers.append(text)
        return self

    async def edit_reply_markup(self, reply_markup=None):
        return True


class FakeQuery:
    def __init__(self):
        self.from_user = FakeUser()
        self.message = FakeMessage()
        self.data = ""

    async def answer(self, text="", show_alert=False):
        return None


@pytest.mark.asyncio
async def test_confirm_writes_only_to_test_store(tmp_path):
    prod = prod_db(tmp_path)
    store = ModeStore(tmp_path / "test", prod_db=prod, prod_sheet_id="PROD")
    store.initialize()
    store.set_setting("mode:1", "TEST")
    photo = b"photo-bytes"
    photo_path = tmp_path / "photo.jpg"
    photo_path.write_bytes(photo)
    report = Report("2026-11-27", photo_reviewed=True, photo_sha=__import__("hashlib").sha256(photo).hexdigest(),
                    photo_path=str(photo_path), items=[
        Item([Decimal("1000")], category="nal"),
    ], version=1)
    store.save_draft(1, report)
    handlers = ModeHandlers(store, client=None, admin_id=1)
    query = FakeQuery()
    query.data = f"tt:{report.nonce}:confirm"
    await handlers.on_callback(query)
    assert len(store.examples()) == 1
    assert store.load_draft(1) is None
    assert not any("Google" in x and "не отправлено" not in x for x in query.message.answers)


@pytest.mark.asyncio
async def test_unavailable_test_mode_fails_closed(tmp_path):
    root = tmp_path / "test-mode"
    store = ModeStore(root)
    store.initialize()
    store.set_setting("mode:1", "TEST")
    guard = UnavailableTestMode(tmp_path)
    message = FakeMessage()
    handled = await guard.handle_photo(message, None, None)
    assert handled is True
    assert any("НЕ отправлена" in text for text in message.answers)


@pytest.mark.asyncio
async def test_draft_and_line_survive_new_handler_instance(tmp_path):
    prod = prod_db(tmp_path)
    store = ModeStore(tmp_path / "test", prod_db=prod)
    store.initialize()
    store.set_setting("mode:1", "TEST")
    report = Report("2026-11-27", photo_reviewed=True, photo_sha="abc", items=[Item([Decimal("1000")], category="nal")], version=1)
    store.save_draft(1, report)
    store.save_line("abc", (0.61, 0.61))
    again = ModeHandlers(ModeStore(store.root), client=None, admin_id=1)
    loaded = again.store.load_draft(1)
    assert loaded is not None
    assert loaded.items[0].amount == Decimal("1000")
    assert again.store.get_line("abc") == (0.61, 0.61)
