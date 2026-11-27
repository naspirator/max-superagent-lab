import hashlib
import io
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

import maxfinance_test.handlers as handlers_module
from maxfinance_test.handlers import ModeHandlers
from maxfinance_test.model import Item, Report
from maxfinance_test.store import ModeStore


def make_store(tmp_path):
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
    store.set_setting("mode:1", "TEST")
    return store


class FakeUser:
    id = 1


class FakeChat:
    type = "private"


class FakeFile:
    file_id = "file-1"
    file_unique_id = "unique-1"


class FakeBot:
    async def download(self, file, destination):
        from PIL import Image
        buffer = io.BytesIO()
        Image.new("RGB", (40, 40), "white").save(buffer, format="JPEG")
        destination.write(buffer.getvalue())


class FakeMessage:
    def __init__(self):
        self.from_user = FakeUser()
        self.chat = FakeChat()
        self.answers = []
        self.photos = []
        self.message_id = 5

    async def answer(self, text, reply_markup=None):
        self.answers.append(text)
        return self

    async def answer_photo(self, photo, caption=None, reply_markup=None):
        self.photos.append((caption, reply_markup))
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
        self.answers = []

    async def answer(self, text="", show_alert=False):
        self.answers.append(text)


@pytest.mark.asyncio
async def test_end_to_end_photo_edit_confirm_without_prod(monkeypatch, tmp_path):
    store = make_store(tmp_path)
    report = Report(
        report_date=__import__("datetime").date.today().isoformat(),
        items=[
            Item([Decimal("36800")], category="beznal"),
            Item([Decimal("4500")], category="employee", employee_id=1, source="beznal", alias="П"),
        ],
        version=1,
    )

    monkeypatch.setattr(handlers_module, "detect_boundary_candidates", lambda data: [(0.6, 0.6)])
    monkeypatch.setattr(handlers_module, "preview_boundary", lambda data, boundary: b"preview")

    async def fake_recognize(*args, **kwargs):
        return report

    monkeypatch.setattr(handlers_module, "recognize_ensemble", fake_recognize)

    handlers = ModeHandlers(store, client=None, admin_id=1)
    message = FakeMessage()
    handled = await handlers.handle_photo(message, FakeBot(), FakeFile())
    assert handled is True
    assert message.photos
    draft = store.load_draft(1)
    assert draft is not None and draft.boundary == (0.6, 0.6)

    crop = FakeQuery(f"tt:{draft.nonce}:crop")
    await handlers.on_callback(crop)
    draft = store.load_draft(1)
    assert len(draft.items) == 2

    # Ручная правка суммы и категории.
    amount = FakeQuery(f"tt:{draft.nonce}:setcat:0:nal")
    await handlers.on_callback(amount)
    draft = store.load_draft(1)
    assert draft.items[0].category == "nal"

    handlers.editing[1] = ("amount", 0)
    text_message = FakeMessage()
    text_message.text = "30000+800"
    await handlers.on_text(text_message)
    draft = store.load_draft(1)
    assert draft.items[0].amount == Decimal("30800")

    # Добавляем вторую категорию, чтобы пройти проверку.
    confirm = FakeQuery(f"tt:{draft.nonce}:confirm")
    await handlers.on_callback(confirm)
    assert len(store.examples()) == 1
    assert store.load_draft(1) is None
    example = store.examples()[0]
    assert "amount_changed" in example["error_types"] or "category_changed" in example["error_types"]
    # В рабочей базе ничего не появилось.
    with sqlite3.connect(tmp_path / "prod" / "finance.db") as db:
        assert db.execute("SELECT COUNT(*) FROM staff_v3").fetchone()[0] == 7


@pytest.mark.asyncio
async def test_prod_sync_command_is_blocked_in_test_mode(tmp_path):
    store = make_store(tmp_path)
    handlers = ModeHandlers(store, client=None, admin_id=1)
    message = FakeMessage()
    message.text = "/sync"
    await handlers.cmd_blocked(message)
    assert message.answers and "отключена" in message.answers[0]


def test_line_persists_for_same_photo(tmp_path):
    store = make_store(tmp_path)
    store.set_setting("mode:1", "TEST")
    store.save_line("sha-line", (0.5, 0.5))
    store.save_line("sha-line", (0.45, 0.45))
    assert store.get_line("sha-line") == (0.45, 0.45)
    again = ModeStore(store.root)
    again.initialize()
    assert again.get_line("sha-line") == (0.45, 0.45)


@pytest.mark.asyncio
async def test_ocr_failure_keeps_draft_and_allows_manual(monkeypatch, tmp_path):
    store = make_store(tmp_path)
    handlers = ModeHandlers(store, client=None, admin_id=1)
    image = tmp_path / "input.img"
    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGB", (40, 40), "white").save(buffer, format="JPEG")
    image.write_bytes(buffer.getvalue())

    async def broken(*args, **kwargs):
        from maxfinance_test.ocr import OcrError
        raise OcrError("Сервис распознавания недоступен: TimeoutError")

    monkeypatch.setattr(handlers_module, "recognize_ensemble", broken)
    report = Report("2026-11-27", photo_sha="sha-error", photo_path=str(image), boundary=(0.5, 0.5), version=1)
    store.save_draft(1, report)
    query = FakeQuery(f"tt:{report.nonce}:crop")
    await handlers.on_callback(query)
    loaded = store.load_draft(1)
    assert loaded is not None
    assert loaded.items == []
    assert any("недоступен" in warning for warning in loaded.warnings)
    assert any("добавить позиции" in answer.lower() for answer in query.message.answers)


def test_confirm_duplicate_is_rejected(tmp_path):
    store = make_store(tmp_path)
    report = Report("2026-11-27", items=[Item([Decimal("1000")], category="nal")])
    store.record_confirmed(report, None, b"same", 1)
    with pytest.raises(ValueError):
        store.record_confirmed(report, None, b"same", 1)
