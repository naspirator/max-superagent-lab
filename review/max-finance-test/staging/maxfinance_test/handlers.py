"""Telegram-интерфейс тестового режима.



Все обработчики работают только с ModeStore. Ни один путь отсюда не

вызывает синхронизацию рабочей Google-таблицы.

"""

from __future__ import annotations



import hashlib

import io

import re

from datetime import date, datetime, timedelta, timezone

from pathlib import Path



from aiogram import Bot, F, Router

from aiogram.dispatcher.event.bases import SkipHandler

from aiogram.filters import Command

from aiogram.types import (

    BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,

    InputMediaPhoto, Message,

)

from PIL import Image



from . import ui

from .aliases import AliasBook

from .ensemble import recognize_ensemble

from .line import detect_boundary_candidates, preview_boundary

from .model import CATEGORIES, HEADER_CATEGORIES, Item, Report, ReportError

from .money import MoneyError, format_amount, parse_amount, parse_expression

from .ocr import OcrError, propose_boundary, recognize

from .store import ModeStore

from .training import example_hint

from .ui import cbd, keyboard



MSK = timezone(timedelta(hours=3))

MAX_PHOTO = 20 * 1024 * 1024





def today() -> date:

    return datetime.now(MSK).date()





def _button(text: str, data: str) -> InlineKeyboardButton:

    return InlineKeyboardButton(text=text, callback_data=data)





def _line_keyboard(nonce: str) -> InlineKeyboardMarkup:

    return keyboard([

        [_button("⬆️ −20%", cbd(nonce, "line:-20")), _button("⬇️ +20%", cbd(nonce, "line:20"))],

        [_button("⬆️ −5%", cbd(nonce, "line:-5")), _button("⬇️ +5%", cbd(nonce, "line:5"))],

        [_button("⬆️ −1%", cbd(nonce, "line:-1")), _button("⬇️ +1%", cbd(nonce, "line:1"))],

        [_button("↖️ Наклон влево", cbd(nonce, "tilt:-1")), _button("↗️ Наклон вправо", cbd(nonce, "tilt:1"))],

        [_button("Левый край −0,1%", cbd(nonce, "left:-0.1")), _button("Левый край +0,1%", cbd(nonce, "left:0.1"))],

        [_button("Правый край −0,1%", cbd(nonce, "right:-0.1")), _button("Правый край +0,1%", cbd(nonce, "right:0.1"))],

        [_button("✅ Начать с линии", cbd(nonce, "crop"))],

        [_button("❌ Отменить", cbd(nonce, "cancel"))],

    ])





def _line_caption(report: Report) -> str:

    left, right = report.boundary or (0.5, 0.5)

    return (

        "✂️ Линия начала распознавания\n"

        "Всё выше линии игнорируется. Поставь линию по верхнему краю финансового блока. "

        "Б/Н в верхней таблице работ не должен становиться началом.\n"

        f"Левый край: {left * 100:.2f}% · правый: {right * 100:.2f}%\n"

        "После изменения линия сохранится для этой фотографии даже после перезапуска."

    )





class ModeHandlers:

    def __init__(self, store: ModeStore, client, admin_id: int):

        self.store = store

        self.client = client

        self.admin_id = int(admin_id)

        self.sessions: dict[int, dict] = {}

        self.editing: dict[int, tuple[str, object]] = {}

        self.busy: set[int] = set()

        self.router = Router()

        self._register()



    # ---------- доступ и режим ----------



    def _mode_file(self, uid: int) -> Path:
        return self.store.root / "active" / str(int(uid))

    def _mark_mode(self, uid: int, mode: str) -> None:
        folder = self.store.root / "active"
        folder.mkdir(parents=True, exist_ok=True)
        path = self._mode_file(uid)
        if mode == "TEST":
            path.write_text("TEST", encoding="utf-8")
        elif path.exists():
            path.unlink()

    def is_test(self, user_id: int) -> bool:
        return self.store.setting(f"mode:{int(user_id)}", "WORK") == "TEST"



    def _allowed(self, message: Message) -> bool:

        return bool(

            message.chat.type == "private" and message.from_user

            and self.admin_id and message.from_user.id == self.admin_id

        )



    def _cb_allowed(self, query: CallbackQuery) -> bool:

        return bool(

            query.message and query.message.chat.type == "private" and query.from_user

            and self.admin_id and query.from_user.id == self.admin_id

        )



    def _nonce(self, uid: int) -> str:

        session = self.sessions.setdefault(uid, {})

        if "nonce" not in session:

            session["nonce"] = "main" + secrets_token()

        return session["nonce"]



    def _draft(self, uid: int) -> Report | None:

        return self.store.load_draft(uid)



    def _save(self, uid: int, report: Report) -> None:

        report.version = max(1, report.version)

        self.store.save_draft(uid, report)

        self.store.set_setting("has_draft", "1")



    def _drop(self, uid: int) -> None:

        self.store.delete_draft(uid)

        self.store.set_setting("has_draft", "0")

        self.editing.pop(uid, None)



    async def _send(self, target, text: str, markup=None) -> Message:

        if hasattr(target, "message") and getattr(target, "message", None) is not None:

            try:

                await target.message.edit_reply_markup(reply_markup=None)

            except Exception:

                pass

            return await target.message.answer(text, reply_markup=markup)

        return await target.answer(text, reply_markup=markup)



    # ---------- команды ----------



    def _register(self) -> None:

        router = self.router

        router.message.register(self.cmd_test, Command("test"))

        router.message.register(self.cmd_work, Command("work"))

        router.message.register(self.cmd_back, Command("testback"))

        router.message.register(self.cmd_help, Command("testhelp"))

        router.message.register(

            self.cmd_blocked,

            Command("sync", "manual", "employees", "cancel", "back", "day", "week", "month", "start", "help"),

        )

        router.callback_query.register(

            self.blocked_prod_callback, F.data.startswith("v3:") | F.data.startswith("st:")

        )

        router.callback_query.register(self.on_callback, F.data.startswith("tt:"))

        router.message.register(self.on_text, F.text & ~F.text.startswith("/"))



    async def cmd_test(self, message: Message) -> None:

        if not self._allowed(message):

            return

        uid = message.from_user.id

        self.store.set_setting(f"mode:{uid}", "TEST")
        self._mark_mode(uid, "TEST")

        draft = self._draft(uid)

        if draft:

            self.sessions.setdefault(uid, {})["nonce"] = draft.nonce

            await message.answer(

                ui.items_text(draft, 0, self.store.alias_book(), self.store),

                reply_markup=ui.items_keyboard(draft, 0, draft.nonce),

            )

            return

        nonce = self._nonce(uid)

        await message.answer(

            ui.main_text(self.store),

            reply_markup=ui.main_keyboard(nonce, has_draft=False),

        )



    async def cmd_work(self, message: Message) -> None:

        if not self._allowed(message):

            return

        uid = message.from_user.id

        self.store.set_setting(f"mode:{uid}", "WORK")
        self._mark_mode(uid, "WORK")

        self.editing.pop(uid, None)

        await message.answer(

            "Рабочий режим включён. Тестовые данные остались в отдельной базе; "

            "рабочие настройки и записи не менялись."

        )



    async def cmd_back(self, message: Message) -> None:

        if not self._allowed(message):

            return

        uid = message.from_user.id

        self.editing.pop(uid, None)

        draft = self._draft(uid)

        if not draft:

            await message.answer("Тестового черновика нет. /test — открыть тестовый режим.")

            return

        await message.answer(

            ui.items_text(draft, 0, self.store.alias_book(), self.store),

            reply_markup=ui.items_keyboard(draft, 0, draft.nonce),

        )



    async def cmd_help(self, message: Message) -> None:

        if not self._allowed(message):

            return

        await message.answer(

            "🧪 MAX FINANCE TEST\n\n"

            "/test — тестовый режим\n/work — рабочий режим\n/testhelp — эта справка\n"

            "/testback — вернуться к тестовому черновику\n\n"

            "Отправь фото, подтверди линию, проверь каждую позицию. "

            "Любую сумму, знак, сотрудника и категорию можно изменить. "

            "В рабочую таблицу тестовые данные не попадают."

        )



    async def cmd_blocked(self, message: Message) -> None:

        """В тестовом режиме рабочие команды не должны менять PROD."""

        uid = message.from_user.id if message.from_user else 0

        if not self.is_test(uid):

            raise SkipHandler

        command = (message.text or "").split(maxsplit=1)[0].lstrip("/").split("@")[0].lower()

        if command == "start":

            draft = self._draft(uid)

            nonce = draft.nonce if draft else self._nonce(uid)

            await message.answer(

                ui.main_text(self.store), reply_markup=ui.main_keyboard(nonce, has_draft=bool(draft))

            )

            return

        await message.answer(

            "⛔ В тестовом режиме рабочая команда /" + command + " отключена. "

            "Рабочие данные и Google-таблица не затрагиваются. /work — вернуться в рабочий режим."

        )



    async def blocked_prod_callback(self, query: CallbackQuery) -> None:

        if not query.from_user or not self.is_test(query.from_user.id):

            raise SkipHandler

        await query.answer("В тестовом режиме рабочая кнопка отключена", show_alert=True)



    # ---------- фото ----------



    async def handle_photo(self, message: Message, bot: Bot, file) -> bool:

        uid = message.from_user.id

        if not self.is_test(uid) or not self._allowed(message):

            return False

        if uid in self.busy:

            await message.answer("Дождись завершения текущей операции.")

            return True

        if self._draft(uid):

            await message.answer("Сначала заверши или отмени текущий тестовый отчёт. /testback — вернуться к нему.")

            return True

        self.busy.add(uid)

        try:

            await message.answer("🧪 Тестовый режим. Открываю фотографию для выбора линии.")

            buffer = io.BytesIO()

            await bot.download(file, destination=buffer)

            data = buffer.getvalue()

            if len(data) > MAX_PHOTO:

                raise ValueError("Файл больше 20 МБ")

            with Image.open(io.BytesIO(data)) as src:

                if src.width * src.height > 35_000_000 or src.width < 2 or src.height < 2:

                    raise ValueError("Неподходящий размер фотографии")

                src.verify()

            sha = hashlib.sha256(data).hexdigest()

            path = self.store.input_dir / (sha + ".img")

            path.write_bytes(data)

            boundary = self.store.get_line(sha)

            candidate = None

            if boundary is None:

                candidates = detect_boundary_candidates(data)

                candidate = candidates[0] if candidates else None

                if candidate is None:

                    proposed = await propose_boundary(self.client, data)

                    if proposed is not None:

                        candidate = (proposed, proposed)

                boundary = candidate or (0.5, 0.5)

            report = Report(

                report_date=today().isoformat(),

                photo_sha=sha,

                photo_path=str(path),

                boundary=(float(boundary[0]), float(boundary[1])),

                version=1,

                created_at=datetime.now(MSK).isoformat(),

            )

            self._save(uid, report)

            self.sessions.setdefault(uid, {})["nonce"] = report.nonce

            preview = preview_boundary(data, report.boundary)

            prefix = "Найдена возможная метка. " if candidate else ""

            await message.answer_photo(

                BufferedInputFile(preview, filename="boundary.jpg"),

                caption=prefix + _line_caption(report),

                reply_markup=_line_keyboard(report.nonce),

            )

        except Exception:

            await message.answer("Не удалось открыть изображение. Попробуй другое фото или добавь позиции вручную через /test.")

        finally:

            self.busy.discard(uid)

        return True



    # ---------- callbacks ----------



    async def on_callback(self, query: CallbackQuery) -> None:

        if not self._cb_allowed(query):

            await query.answer("Нет доступа", show_alert=True)

            return

        uid = query.from_user.id

        if not self.is_test(uid):

            await query.answer("Открой тестовый режим командой /test", show_alert=True)

            return

        parts = query.data.split(":")

        if len(parts) < 3:

            await query.answer()

            return

        nonce, action = parts[1], parts[2]

        args = parts[3:]

        if uid in self.busy:

            await query.answer("Дождись завершения операции", show_alert=True)

            return

        if uid in self.editing and action not in ("back", "menu"):

            await query.answer("Бот ждёт ввод. Отправь значение или /testback.", show_alert=True)

            return

        await query.answer()

        draft = self._draft(uid)

        if action in ("menu",):

            self.editing.pop(uid, None)

            await self._send(query, ui.main_text(self.store), ui.main_keyboard(self._nonce(uid), bool(draft)))

            return

        if action == "work":

            self.store.set_setting(f"mode:{uid}", "WORK")
            self._mark_mode(uid, "WORK")

            self.editing.pop(uid, None)

            await self._send(query, "Рабочий режим включён. Тестовые данные не затронули рабочие записи.")

            return

        if action == "linehelp":

            await self._send(

                query,

                "✂️ Линия задаётся для каждой фотографии и сохраняется по отпечатку снимка. "

                "Меняй её кнопками, пока не совпадёт с началом финансового блока. "

                "Верхняя таблица работ, включая Б/Н в ней, остаётся выше линии.",

                keyboard([[ui.button("🏠 Меню", cbd(self._nonce(uid), "menu"))]]),

            )

            return

        if action == "examples":

            await self._send(

                query, ui.examples_text(self.store),

                keyboard([[ui.button("🏠 Меню", cbd(self._nonce(uid), "menu"))]]),

            )

            return

        if action == "staff":

            await self._send(query, ui.staff_text(self.store), ui.staff_keyboard(self.store, self._nonce(uid)))

            return

        if action.startswith("staff") or action.startswith("aliasadd") or action.startswith("aliasdel"):

            await self._staff_action(query, action, args, uid, nonce)

            return

        if not draft:

            await self._send(query, "Тестового черновика нет. Отправь фотографию.", ui.main_keyboard(self._nonce(uid)))

            return

        if draft.nonce != nonce:

            await query.answer("Кнопка устарела", show_alert=True)

            return

        try:

            await self._dispatch(query, draft, action, args, uid)

        except (ReportError, MoneyError, ValueError) as exc:

            await query.message.answer("⛔ " + str(exc))

        except Exception as exc:

            await query.message.answer("⛔ Не удалось выполнить действие. Черновик сохранён.")



    async def _dispatch(self, query: CallbackQuery, report: Report, action: str, args: list[str], uid: int) -> None:

        nonce = report.nonce

        book = self.store.alias_book()

        if action in ("line", "tilt", "left", "right"):

            if not report.boundary or not report.photo_path:

                return

            if not args:

                return

            try:

                delta = float(args[0]) / 100

            except ValueError:

                return

            left, right = report.boundary

            if action == "line":

                left += delta

                right += delta

            elif action == "tilt":

                left -= delta

                right += delta

            elif action == "left":

                left += delta

            else:

                right += delta

            if min(left, right) < 0 or max(left, right) > 0.98:

                return

            report.push_undo()

            report.boundary = (left, right)

            if report.items:

                report.ocr_stale = True

            self.store.save_line(report.photo_sha, report.boundary)

            self._save(uid, report)

            data = Path(report.photo_path).read_bytes()

            preview = preview_boundary(data, report.boundary)

            await query.message.edit_media(

                media=InputMediaPhoto(

                    media=BufferedInputFile(preview, filename="boundary.jpg"),

                    caption=_line_caption(report),

                ),

                reply_markup=_line_keyboard(nonce),

            )

            return

        if action == "crop":

            await self._recognize(query, report, uid)

            return

        if action == "page":

            page = _int(args, 0, 0)

            await self._send(query, ui.items_text(report, page, book, self.store), ui.items_keyboard(report, page, nonce))

            return

        if action == "item":

            index = _item_index(report, args[0] if args else None)

            if not 0 <= index < len(report.items):

                return

            await self._send(query, ui.item_text(report, index, book), ui.item_keyboard(report, index, nonce))

            return

        if action == "amount":

            index = _item_index(report, args[0] if args else None)

            self._require(index, report)

            self.editing[uid] = ("amount", report.items[index].item_id)

            await self._send(query, "Введи сумму или выражение, например 1500 или 6000+1450−500.", None)

            return

        if action == "terms":

            index = _item_index(report, args[0] if args else None)

            self._require(index, report)

            await self._send(query, ui.terms_text(report, index), ui.terms_keyboard(report, index, nonce))

            return

        if action == "term":

            index = _item_index(report, args[0] if args else None)

            term = _int(args, 1, -1)

            self._require(index, report)

            if not 0 <= term < len(report.items[index].terms):

                return

            await self._send(

                query,

                f"Слагаемое {term + 1}: {format_amount(report.items[index].terms[term])} ₽",

                ui.term_keyboard(report.items[index].item_id, term, nonce),

            )

            return

        if action == "termvalue":

            index = _item_index(report, args[0] if args else None)

            term = _int(args, 1, -1)

            self._require(index, report)

            self.editing[uid] = ("termvalue", (report.items[index].item_id, term))

            await self._send(query, "Введи новое значение слагаемого.", None)

            return

        if action in ("signplus", "signminus"):

            index = _item_index(report, args[0] if args else None)

            term = _int(args, 1, -1)

            report.set_sign(index, term, "+" if action == "signplus" else "-")

            self._save(uid, report)

            await self._send(query, ui.terms_text(report, index), ui.terms_keyboard(report, index, nonce))

            return

        if action == "termdel":

            index = _item_index(report, args[0] if args else None)

            term = _int(args, 1, -1)

            report.remove_term(index, term)

            self._save(uid, report)

            await self._send(query, ui.terms_text(report, index), ui.terms_keyboard(report, index, nonce))

            return

        if action == "addterm":

            index = _item_index(report, args[0] if args else None)

            self._require(index, report)

            self.editing[uid] = ("addterm", report.items[index].item_id)

            await self._send(query, "Введи число. Для вычитания начни с минуса, например −500.", None)

            return

        if action == "employee":

            index = _item_index(report, args[0] if args else None)

            self._require(index, report)

            await self._send(

                query, "Выбери сотрудника:",

                ui.employees_keyboard(book, report.items[index].item_id, nonce, 0),

            )

            return

        if action == "emppage":

            index = _item_index(report, args[0] if args else None)

            page = _int(args, 1, 0)

            await self._send(query, "Выбери сотрудника:", ui.employees_keyboard(book, report.items[index].item_id, nonce, page))

            return

        if action == "setemp":

            index = _item_index(report, args[0] if args else None)

            employee_id = _int(args, 1, 0)

            if employee_id and employee_id not in {p["id"] for p in self.store.staff()}:

                raise ReportError("Сотрудник неактивен или не найден")

            report.set_employee(index, employee_id or None)

            self._save(uid, report)

            await self._send(query, ui.item_text(report, index, book), ui.item_keyboard(report, index, nonce))

            return

        if action == "alias":

            index = _item_index(report, args[0] if args else None)

            self._require(index, report)

            self.editing[uid] = ("alias", report.items[index].item_id)

            await self._send(query, "Введи буквенное обозначение с фото (П, Р, В, Т, Д, Л, ДИМ…).", None)

            return

        if action in ("category", "setcat"):

            index = _item_index(report, args[0] if args else None)

            self._require(index, report)

            if action == "category":

                await self._send(query, "Выбери категорию:", ui.categories_keyboard(report.items[index].item_id, nonce))

            else:

                category = args[1] if len(args) > 1 else ""

                if category not in CATEGORIES:

                    return

                report.set_category(index, category)

                self._save(uid, report)

                await self._send(query, ui.item_text(report, index, book), ui.item_keyboard(report, index, nonce))

            return

        if action in ("source", "setsrc"):

            index = _item_index(report, args[0] if args else None)

            self._require(index, report)

            if action == "source":

                await self._send(query, "Выбери источник выплаты:", ui.sources_keyboard(report.items[index].item_id, nonce))

            else:

                source = args[1] if len(args) > 1 else ""

                report.set_source(index, source)

                self._save(uid, report)

                await self._send(query, ui.item_text(report, index, book), ui.item_keyboard(report, index, nonce))

            return

        if action == "split":

            index = _item_index(report, args[0] if args else None)

            self._require(index, report)

            await self._send(query, "Где разделить позицию?", ui.split_keyboard(report, index, nonce))

            return

        if action == "splitat":

            index = _item_index(report, args[0] if args else None)

            at = _int(args, 1, 0)

            left, right = report.split_item(index, at)

            report.items[left].origin = "manual"

            report.items[right].origin = "manual"

            self._save(uid, report)

            await self._send(query, ui.items_text(report, left // ui.PAGE_SIZE, book, self.store),

                            ui.items_keyboard(report, left // ui.PAGE_SIZE, nonce))

            return

        if action == "splitamount":

            index = _item_index(report, args[0] if args else None)

            self._require(index, report)

            self.editing[uid] = ("splitamount", report.items[index].item_id)

            await self._send(query, "Введи две суммы через пробел или плюс: 1500 2000.", None)

            return

        if action == "merge":

            index = _item_index(report, args[0] if args else None)

            self._require(index, report)

            await self._send(query, "С какой позицией объединить?", ui.merge_keyboard(report, index, nonce, book))

            return

        if action == "mergeat":

            index = _item_index(report, args[0] if args else None)

            other = _item_index(report, args[1] if len(args) > 1 else None)

            target = report.merge_items(index, other)

            self._save(uid, report)

            await self._send(query, ui.items_text(report, target // ui.PAGE_SIZE, book, self.store),

                            ui.items_keyboard(report, target // ui.PAGE_SIZE, nonce))

            return

        if action == "up":

            index = _item_index(report, args[0] if args else None)

            report.move_item(index, -1)

            self._save(uid, report)

            await self._send(query, ui.items_text(report, (index - 1) // ui.PAGE_SIZE, book, self.store),

                            ui.items_keyboard(report, (index - 1) // ui.PAGE_SIZE, nonce))

            return

        if action == "down":

            index = _item_index(report, args[0] if args else None)

            report.move_item(index, 1)

            self._save(uid, report)

            await self._send(query, ui.items_text(report, (index + 1) // ui.PAGE_SIZE, book, self.store),

                            ui.items_keyboard(report, (index + 1) // ui.PAGE_SIZE, nonce))

            return

        if action == "delete":

            index = _item_index(report, args[0] if args else None)

            report.delete_item(index)

            self._save(uid, report)

            page = max(0, index - 1) // ui.PAGE_SIZE

            await self._send(query, ui.items_text(report, page, book, self.store), ui.items_keyboard(report, page, nonce))

            return

        if action == "add":

            self.editing[uid] = ("add", None)

            await self._send(query, "Введи сумму или выражение новой позиции: 1500 или 6000+1450−500.", None)

            return

        if action == "totals":

            await self._send(query, ui.totals_text(report), ui.totals_keyboard(nonce))

            return

        if action == "total":

            category = args[0] if args else ""

            if category not in HEADER_CATEGORIES:

                return

            self.editing[uid] = ("total", category)

            await self._send(

                query,

                "Введи итог категории вручную или отправь «сброс», чтобы вернуть вычисленный. "

                "Суммы сотрудников при этом не изменятся.",

                None,

            )

            return

        if action == "date":

            self.editing[uid] = ("date", None)

            await self._send(query, "Введи дату отчёта в формате ГГГГ-ММ-ДД.", None)

            return

        if action == "lineedit":

            data = Path(report.photo_path).read_bytes() if report.photo_path else b""

            if not data or not report.boundary:

                return

            preview = preview_boundary(data, report.boundary)

            await query.message.answer_photo(

                BufferedInputFile(preview, filename="boundary.jpg"),

                caption=_line_caption(report), reply_markup=_line_keyboard(nonce),

            )

            return

        if action == "ackphoto":

            report.ocr_complete = True

            report.photo_reviewed = True

            report.warnings = [w for w in report.warnings if "Полнота" not in w]

            self._save(uid, report)

            await self._send(query, ui.items_text(report, 0, book, self.store), ui.items_keyboard(report, 0, nonce))

            return

        if action == "rerun":

            if report.items:

                await self._send(

                    query,

                    "Перераспознать фотографию? Текущие позиции сохранятся в истории изменений (Undo).",

                    keyboard([

                        [ui.button("✅ Перераспознать", cbd(nonce, "rerunyes"))],

                        [ui.button("↩️ Назад", cbd(nonce, "page:0"))],

                    ]),

                )

                return

            await self._recognize(query, report, uid)

            return

        if action == "rerunyes":

            await self._recognize(query, report, uid)

            return

        if action == "undo":

            report.undo()

            if report.boundary and report.photo_sha:

                self.store.save_line(report.photo_sha, report.boundary)

            self._save(uid, report)

            await self._send(query, ui.items_text(report, 0, book, self.store), ui.items_keyboard(report, 0, nonce))

            return

        if action == "review":

            report.validate({p["id"] for p in self.store.staff()})

            await self._send(query, ui.summary_text(report, book), ui.confirm_keyboard(nonce, report.version))

            return

        if action == "confirm":

            shown = _int(args, 0, -1)

            if shown != report.version:
                raise ReportError("Сводка устарела: отчёт изменился после её показа. Нажми «Проверить» заново.")

            await self._confirm(query, report, uid)

            return

        if action == "cancel":

            await self._send(

                query,

                "Отменить весь тестовый отчёт? Рабочие данные это не затронет.",

                keyboard([

                    [ui.button("✅ Да, отменить", cbd(nonce, "cancelyes"))],

                    [ui.button("↩️ Нет", cbd(nonce, "page:0"))],

                ]),

            )

            return

        if action == "cancelyes":

            self._drop(uid)

            await self._send(query, "Тестовый отчёт отменён. Рабочая таблица не изменялась.", ui.main_keyboard(self._nonce(uid)))

            return

        if action == "resume":

            await self._send(query, ui.items_text(report, 0, book, self.store), ui.items_keyboard(report, 0, nonce))

            return

        if action == "newphoto":

            await self._send(query, "Отправь фотографию отчёта в этот чат.")

            return

        if action in ("staffadd", "staffrename", "aliasadd", "aliasdel", "staffremove", "staff") or action.startswith("aliasdelat"):

            await self._staff_action(query, action, args, uid, nonce)

            return

        if action == "back":

            self.editing.pop(uid, None)

            await self._send(query, ui.items_text(report, 0, book, self.store), ui.items_keyboard(report, 0, nonce))

            return



    async def _staff_action(self, query: CallbackQuery, action: str, args: list[str], uid: int, nonce: str) -> None:

        if action == "staffadd":

            self.editing[uid] = ("staffadd", None)

            await self._send(query, "Введи имя нового сотрудника.", None)

            return

        if action == "staffrename":

            employee_id = _int(args, 0, 0)

            self.editing[uid] = ("staffrename", employee_id)

            await self._send(query, "Введи новое имя сотрудника.", None)

            return

        if action == "aliasadd":

            employee_id = _int(args, 0, 0)

            self.editing[uid] = ("aliasadd", employee_id)

            await self._send(query, "Введи буквенное обозначение для этого сотрудника.", None)

            return

        if action == "aliasdel":

            employee_id = _int(args, 0, 0)

            aliases = self.store.alias_book().aliases_for(employee_id)

            rows = [[ui.button(alias, cbd(nonce, f"aliasdelat:{employee_id}:{alias}"))] for alias in aliases]

            rows.append([ui.button("↩️ Назад", cbd(nonce, f"staff:{employee_id}"))])

            await self._send(query, "Какую букву убрать?", keyboard(rows))

            return

        if action.startswith("aliasdelat"):

            employee_id = _int(args, 0, 0)

            alias = args[1] if len(args) > 1 else ""

            self.store.remove_alias(alias)

            await self._send(query, "Обозначение убрано.", ui.staff_card_keyboard(employee_id, nonce))

            return

        if action == "staffremove":

            employee_id = _int(args, 0, 0)

            self.store.remove_employee(employee_id)

            await self._send(query, "Сотрудник убран из активных. История сохранена.", ui.staff_keyboard(self.store, nonce))

            return

        if action == "staff":

            employee_id = _int(args, 0, 0)

            await self._send(query, ui.staff_card_text(self.store, employee_id), ui.staff_card_keyboard(employee_id, nonce))

            return



    # ---------- распознавание и подтверждение ----------



    async def _recognize(self, query: CallbackQuery, report: Report, uid: int) -> None:

        if not report.photo_path or not report.boundary:

            await query.message.answer("Сначала выбери линию.")

            return

        self.busy.add(uid)

        try:

            await query.message.answer("🔎 Распознаю область ниже линии. Рабочая таблица не затрагивается.")

            data = Path(report.photo_path).read_bytes()

            book = self.store.alias_book()

            try:

                from ocr_v3 import recognize as old_recognize

            except Exception:

                old_recognize = None

            if old_recognize is not None:

                result = await recognize_ensemble(

                    self.client, data, report.boundary, book, example_hint(self.store), old_recognize

                )

            else:

                result = await recognize(self.client, data, report.boundary, book, example_hint(self.store))

            report.push_undo()

            report.items = result.items

            report.warnings = result.warnings

            report.engine_version = result.engine_version

            report.ocr_complete = result.ocr_complete

            report.ocr_stale = False

            report.photo_reviewed = False

            report.ocr_snapshot = {

                "items": [item.to_json() for item in result.items],

                "warnings": list(result.warnings),

            }

            self._save(uid, report)

            await query.message.answer(

                ui.items_text(report, 0, book, self.store),

                reply_markup=ui.items_keyboard(report, 0, report.nonce),

            )

        except OcrError as exc:

            report.push_undo()

            report.items = []

            report.warnings = [str(exc) + " Добавь позиции вручную."]

            report.ocr_complete = False

            report.ocr_stale = False

            report.photo_reviewed = False

            self._save(uid, report)

            await query.message.answer(

                "⚠️ " + str(exc) + "\nЧерновик сохранён. Можно добавить позиции вручную.",

                reply_markup=ui.items_keyboard(report, 0, report.nonce),

            )

        finally:

            self.busy.discard(uid)



    async def _confirm(self, query: CallbackQuery, report: Report, uid: int) -> None:

        try:

            report.validate({p["id"] for p in self.store.staff()})

            photo = Path(report.photo_path).read_bytes() if report.photo_path else b""

            original = None

            if report.ocr_snapshot:

                original = Report(

                    report_date=report.report_date,

                    boundary=report.boundary,

                    items=[Item.from_json(x) for x in report.ocr_snapshot.get("items", [])],

                    version=1,

                )

            example_id = self.store.record_confirmed(report, original, photo, uid, "train")

        except Exception as exc:

            await query.message.answer("⛔ " + str(exc))

            return

        self._drop(uid)

        await query.message.answer(

            "✅ Тестовый отчёт подтверждён и сохранён в базу примеров.\n"

            f"ID примера: {example_id}\n"

            "В рабочую Google-таблицу ничего не отправлено."

        )



    # ---------- текст ----------



    async def on_text(self, message: Message) -> None:

        uid = message.from_user.id

        if not self.is_test(uid):

            raise SkipHandler

        if not self._allowed(message):

            return

        state = self.editing.get(uid)

        if not state:

            await message.answer("🧪 Тестовый режим. Отправь фотографию или нажми /test для меню.")

            return

        kind, target = state

        text = (message.text or "").strip()

        try:

            if kind in ("staffadd", "staffrename", "aliasadd"):

                await self._text_staff(message, uid, kind, target, text)

                return

            report = self._draft(uid)

            if not report:

                self.editing.pop(uid, None)

                await message.answer("Черновик устарел. /test")

                return

            if kind in ("amount", "alias", "addterm", "splitamount"):

                index = report.index_of(str(target))

            elif kind == "termvalue":

                item_id, term = target

                index = report.index_of(str(item_id))

            if kind == "amount":

                terms, signs = parse_expression(text)

                report.set_terms(index, terms, signs)

                await self._after_text(message, uid, report, index)

            elif kind == "termvalue":

                report.set_term(index, int(term), text)

                await self._after_text(message, uid, report, index, terms=True)

            elif kind == "addterm":

                sign = "-" if text.startswith(("-", "−")) else "+"

                value = text[1:].strip() if sign == "-" else text

                report.add_term(index, value, sign)

                await self._after_text(message, uid, report, index, terms=True)

            elif kind == "alias":

                resolution = self.store.alias_book().resolve(text)

                report.set_alias(index, text)

                if resolution.status == "resolved" and resolution.employee_id:

                    report.set_employee(index, resolution.employee_id)

                await self._after_text(message, uid, report, index)

            elif kind == "date":

                report.set_date(text)

                await self._after_text(message, uid, report, 0)

            elif kind == "total":

                if text.lower() in ("сброс", "reset"):

                    report.set_category_total(str(target), None)

                else:

                    report.set_category_total(str(target), text)

                await self._after_text(message, uid, report, 0, totals=True)

            elif kind == "splitamount":

                left_text, right_text = _two_amounts(text)

                item = report.items[index]

                report.push_undo()

                first = Item(terms=[parse_amount(left_text)], category=item.category,
                             employee_id=item.employee_id, alias=item.alias, source=item.source,
                             uncertain=item.uncertain, struck=item.struck, origin="manual",
                             raw=item.raw, note=item.note)
                second = Item(terms=[parse_amount(right_text)], category=item.category,
                              employee_id=item.employee_id, alias=item.alias, source=item.source,
                              uncertain=item.uncertain, struck=item.struck, origin="manual",
                              raw=item.raw, note=item.note)

                report.items[index:index + 1] = [first, second]

                self._save(uid, report)

                self.editing.pop(uid, None)

                await message.answer(

                    ui.items_text(report, index // ui.PAGE_SIZE, self.store.alias_book(), self.store),

                    reply_markup=ui.items_keyboard(report, index // ui.PAGE_SIZE, report.nonce),

                )

            elif kind == "add":

                terms, signs = parse_expression(text)

                report.add_item(Item(terms=terms, signs=signs, origin="manual"))

                index = len(report.items) - 1

                self._save(uid, report)

                self.editing.pop(uid, None)

                await message.answer(

                    "Позиция добавлена. Назначь категорию.",

                    reply_markup=ui.categories_keyboard(report.items[index].item_id, report.nonce),

                )

            else:

                raise ReportError("Неизвестное действие")

            self.editing.pop(uid, None)

        except (ValueError, MoneyError, ReportError) as exc:

            await message.answer("⛔ " + str(exc) + " Попробуй ещё раз или /testback.")



    async def _text_staff(self, message: Message, uid: int, kind: str, target, text: str) -> None:

        if kind == "staffadd":

            employee_id = self.store.add_employee(text)

            self.editing.pop(uid, None)

            await message.answer("Сотрудник добавлен.", reply_markup=ui.staff_card_keyboard(employee_id, self._nonce(uid)))

            return

        if kind == "staffrename":

            self.store.rename_employee(int(target), text)

            self.editing.pop(uid, None)

            await message.answer("Имя изменено.", reply_markup=ui.staff_card_keyboard(int(target), self._nonce(uid)))

            return

        if kind == "aliasadd":

            self.store.add_alias(text, int(target))

            self.editing.pop(uid, None)

            await message.answer("Обозначение добавлено.", reply_markup=ui.staff_card_keyboard(int(target), self._nonce(uid)))



    async def _after_text(self, message: Message, uid: int, report: Report, index: int,

                          terms: bool = False, totals: bool = False) -> None:

        self._save(uid, report)

        self.editing.pop(uid, None)

        if totals:

            await message.answer(ui.totals_text(report), reply_markup=ui.totals_keyboard(report.nonce))

            return

        if terms:

            await message.answer(ui.terms_text(report, index), reply_markup=ui.terms_keyboard(report, index, report.nonce))

            return

        await message.answer(

            ui.item_text(report, index, self.store.alias_book()),

            reply_markup=ui.item_keyboard(report, index, report.nonce),

        )



    @staticmethod

    def _require(index: int, report: Report) -> None:

        if not 0 <= index < len(report.items):

            raise ReportError("Позиция не найдена")





def secrets_token() -> str:

    import secrets

    return secrets.token_hex(4)





def _int(args: list[str], position: int, default: int) -> int:

    try:

        return int(args[position])

    except (IndexError, ValueError):

        return default





def _item_index(report: Report, value) -> int:

    if value is None:

        raise ReportError("Позиция не найдена")

    text = str(value)

    try:

        return int(text)

    except ValueError:

        return report.index_of(text)





def _two_amounts(text: str) -> tuple[str, str]:

    number = r"(?:\d{1,3}(?:[ \u00a0]\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)"

    match = re.fullmatch(r"\s*(" + number + r")\s*[+\s]\s*(" + number + r")\s*", text)

    if not match:

        raise ReportError("Введи две суммы через пробел или плюс")

    left, right = match.group(1).strip(), match.group(2).strip()

    parse_amount(left)

    parse_amount(right)

    return left, right





__all__ = ["ModeHandlers"]

