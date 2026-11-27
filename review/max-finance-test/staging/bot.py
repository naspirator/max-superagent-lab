"""Telegram v3: фото → суммы → ручные назначения → подтверждение."""
import asyncio,calendar,copy,hashlib,io,os,secrets
from datetime import date,datetime,timedelta
from pathlib import Path
import gspread
from PIL import Image
from dotenv import load_dotenv
from openai import AsyncOpenAI
from aiogram import Bot,Dispatcher,F,Router
from aiogram.filters import Command,CommandStart
from aiogram.types import Message,CallbackQuery,InlineKeyboardButton,InlineKeyboardMarkup,BufferedInputFile,InputMediaPhoto
import finance_v3 as f
import maxfinance_test
import ocr_v3
import sheets_v3
from reports import reports_router

BASE=Path(__file__).resolve().parent
load_dotenv(BASE/'.env')
TOKEN=os.getenv('TELEGRAM_BOT_TOKEN');API_KEY=os.getenv('VSEGPT_API_KEY')
ADMIN_ID=int(os.getenv('ADMIN_ID','0'));SHEET_ID=os.getenv('GOOGLE_SHEET_ID')
DATABASE=Path(os.getenv('FINANCE_DATABASE',str(BASE/'finance.db')))
store=f.Store(DATABASE)
client=AsyncOpenAI(api_key=API_KEY or 'not-configured',base_url='https://api.vsegpt.ru/v1',timeout=180,max_retries=0)
router=Router();drafts={};editing={};busy=set();saving=set();staff_sessions={}
db_lock=asyncio.Lock();sheet_lock=asyncio.Lock()
TEST_HANDLERS=None
LABELS={'beznal':'Безнал','nal':'Нал','itog':'Итог','employee':'Сотрудник','debt':'Долг','ignore':'Не учитывать',None:'Не назначено'}
SOURCES={'beznal':'Безнал','nal':'Нал','unknown':'Не указан'}

def button(text,data):return InlineKeyboardButton(text=text,callback_data=data)
def keyboard(rows):return InlineKeyboardMarkup(inline_keyboard=rows)
def cb(draft,action):return 'v3:'+draft.nonce+':'+action

def allowed(message):return bool(message.chat.type=='private' and message.from_user and ADMIN_ID and message.from_user.id==ADMIN_ID)
def cb_allowed(query):return bool(query.message and query.message.chat.type=='private' and ADMIN_ID and query.from_user.id==ADMIN_ID)
def staff_name(ident):
    for p in store.employees():
        if p['id']==ident:return p['name']
    return 'Недоступен'
def position_label(p):
    label=LABELS.get(p.category,'Не назначено')
    if p.category=='employee':label+=': '+staff_name(p.employee_id)+' / '+SOURCES.get(p.source,'?')
    return label

def items_text(draft,page=0):
    start=page*10;end=min(len(draft.positions),start+10)
    lines=[f'📋 Суммы · {draft.report_date}', 'Нажми сумму и назначь её.']
    if not draft.positions:lines.append('Сумм пока нет. Добавь вручную.')
    for i in range(start,end):
        p=draft.positions[i]
        lines.append(f'{i+1}. {p.display[:110]} — {position_label(p)}'+(' ⚠️' if p.uncertain and p.category!='ignore' else ''))
    if draft.warnings:
        lines.append('⚠️ '+ '; '.join(draft.warnings)[:350])
        lines.append('Сверь с фото. Затем нажми «Я сверил фото».')
    if len(draft.positions)>10:lines.append(f'Страница {page+1} из {(len(draft.positions)+9)//10}')
    return '\n'.join(lines)[:3500]

def items_keyboard(draft,page=0):
    start=page*10;end=min(len(draft.positions),start+10)
    rows=[[button(f'{i+1}. {draft.positions[i].display[:72]}',cb(draft,f'pos:{i}'))] for i in range(start,end)]
    pages=[]
    if page>0:pages.append(button('◀️',cb(draft,f'page:{page-1}')))
    if end<len(draft.positions):pages.append(button('▶️',cb(draft,f'page:{page+1}')))
    if pages:rows.append(pages)
    if draft.warnings:rows.append([button('Я сверил фото',cb(draft,'checked'))])
    if draft.image_bytes and draft.boundary is not None:
        rows.append([button('👀 Показать выбранную область',cb(draft,f'view_crop:{page}'))])
    if any(p.category is None for p in draft.positions):
        rows.append([button('Не учитывать нераспределённые',cb(draft,'ignore_pending'))])
    rows.extend([[button('➕ Добавить сумму',cb(draft,'add')),button('👥 Сотрудники',cb(draft,'staff'))],
                 [button('📅 Изменить дату',cb(draft,'date')),button('✅ Готово',cb(draft,'done'))],
                 [button('❌ Отмена',cb(draft,'cancel'))]])
    return keyboard(rows)

def choice_keyboard(draft,index):
    return keyboard([[button(LABELS[k],cb(draft,f'assign:{index}:{k}'))] for k in ('beznal','nal','itog','employee','debt','ignore')]+
                    [[button('✏️ Исправить сумму',cb(draft,f'edit:{index}')),button('↩️ Список',cb(draft,f'page:{index//10}'))]])

def employee_choice(draft,index,page=0):
    people=store.employees();start=page*20
    rows=[[button(p['name'],cb(draft,f'emp:{index}:{p["id"]}'))] for p in people[start:start+20]]
    nav=[]
    if page>0:nav.append(button('◀️',cb(draft,f'emplist:{index}:{page-1}')))
    if start+20<len(people):nav.append(button('▶️',cb(draft,f'emplist:{index}:{page+1}')))
    if nav:rows.append(nav)
    rows.append([button('➕ Добавить сотрудника',cb(draft,'staff')),button('↩️ Назад',cb(draft,f'pos:{index}'))])
    return keyboard(rows)

def boundary_keyboard(draft):
    return keyboard([[button('⬆️ −20%',cb(draft,'line:-20')),button('⬇️ +20%',cb(draft,'line:20'))],
                     [button('⬆️ −5%',cb(draft,'line:-5')),button('⬇️ +5%',cb(draft,'line:5'))],
                     [button('⬆️ −1%',cb(draft,'line:-1')),button('⬇️ +1%',cb(draft,'line:1'))],
                     [button('⬆️ −0,1%',cb(draft,'line:-0.1')),button('⬇️ +0,1%',cb(draft,'line:0.1'))],
                     [button('↙️ Наклон влево',cb(draft,'tilt:-1')),button('↘️ Наклон вправо',cb(draft,'tilt:1'))],
                     [button('↙️ Точный наклон',cb(draft,'tilt:-0.1')),button('↘️ Точный наклон',cb(draft,'tilt:0.1'))],
                     [button('Левый край −0,05%',cb(draft,'left:-0.05')),button('Левый край +0,05%',cb(draft,'left:0.05'))],
                     [button('Правый край −0,05%',cb(draft,'right:-0.05')),button('Правый край +0,05%',cb(draft,'right:0.05'))],
                     [button('✅ Начать с линии',cb(draft,'crop'))],[button('❌ Отмена',cb(draft,'cancel'))]])

def boundary_caption(draft):
    l,r=draft.boundary
    return ('Выбери надпись БН / Б/Н / BN / Безнал, с которой начать чтение. '
            'Если надписей несколько, выбери нужную. Поставь красную линию по верхнему краю выбранной строки. '
            'Проверь оба конца линии. Если метки нет, не подтверждай линию.\n'
            f'Левый край: {l*100:.2f}%, правый: {r*100:.2f}%')

async def refresh_boundary(message,draft):
    preview=await asyncio.to_thread(f.preview_boundary,draft.image_bytes,draft.boundary)
    await message.edit_media(media=InputMediaPhoto(media=BufferedInputFile(preview,filename='boundary.jpg'),caption=boundary_caption(draft)),reply_markup=boundary_keyboard(draft))

async def show_items(message,draft,page=0):
    await message.edit_text(items_text(draft,page),reply_markup=items_keyboard(draft,page))

def summary_text(draft):
    lines=['📋 ПРОВЕРЬ ПЕРЕД СОХРАНЕНИЕМ',f'📅 {draft.report_date}','']
    employees={};debts=[]
    for p in draft.positions:
        if p.category=='ignore':continue
        if p.category=='employee':
            key=(staff_name(p.employee_id),p.source)
            employees[key]=employees.get(key,f.Decimal(0))+p.amount
        elif p.category=='debt':debts.append(p.display)
        else:lines.append(LABELS[p.category]+': '+p.display)
    if employees:
        lines+=['','👥 Выплаты:']
        for (name,source),amount in sorted(employees.items()):lines.append(f'{name} · {SOURCES[source]}: {f.amount_text(amount)} ₽')
        by_name={}
        for (name,source),amount in employees.items():by_name[name]=by_name.get(name,f.Decimal(0))+amount
        for name,amount in sorted(by_name.items()):lines.append(f'Всего {name}: {f.amount_text(amount)} ₽')
    if debts:lines+=['','Долги:']+debts
    lines+=['','Проверь суммы, сотрудников и дату.']
    return '\n'.join(lines)

def split_summary(text):
    pages=[];page=''
    for line in text.splitlines(keepends=True):
        if page and len(page)+len(line)>3500:
            pages.append(page);page=''
        while len(line)>3500:
            pages.append(line[:3500]);line=line[3500:]
        page+=line
    if page:pages.append(page)
    return pages

def sync_everything():
    book=gspread.service_account(filename=str(BASE/'google_credentials.json')).open_by_key(SHEET_ID)
    return sheets_v3.sync(book,store)

async def sync_with_tracking():
    # Держим локальную запись закрытой на время получения и отправки снимка.
    async with db_lock:
        async with sheet_lock:
            snapshot=await asyncio.to_thread(store.pending_sync)
            try:
                result=await asyncio.to_thread(sync_everything)
            except Exception as exc:
                print("GOOGLE_SYNC_ERROR:", repr(exc), flush=True)
                await asyncio.to_thread(store.finish_sync,snapshot,False,type(exc).__name__)
                raise
            await asyncio.to_thread(store.finish_sync,snapshot,True)
            remaining=await asyncio.to_thread(store.pending_sync)
            return result, bool(remaining)

@router.message(CommandStart())
async def start(message:Message):
    if not allowed(message):return
    warning='\n⚠️ Есть данные, которые ожидают синхронизации. Нажми /sync.' if store.pending_sync() else ''
    await message.answer('Отправь фотографию отчёта. Выбери нужную БН, распредели суммы и подтверди отчёт.\n/help — инструкция и команды\n/back — вернуться к черновику\n/manual — ввод вручную\n/employees — сотрудники\n/cancel — отменить черновик\n/sync — повторная отправка в Google'+warning)

@router.message(Command('help'))
async def help_command(message:Message):
    if not allowed(message):return
    await message.answer('📖 Как работать с ботом\n'
        '1. Отправь фото и поставь линию у нужной надписи БН. Подтверди линию.\n'
        '2. Нажми сумму и выбери назначение. При необходимости исправь сумму или добавь пропущенную.\n'
        '3. Сверь фото, нажми «Готово» и проверь сводку. Сохранение произойдёт после подтверждения.\n\n'
        '/back — выйти из ввода и вернуться к текущему отчёту, сохранив черновик.\n'
        '/manual — начать отчёт без фото.\n/employees — список сотрудников.\n'
        '/day — отчёт за день; /day ГГГГ-ММ-ДД — за выбранную дату.\n'
        '/week — отчёт за неделю; /week ГГГГ-ММ-ДД — за неделю выбранной даты.\n'
        '/month — отчёт за месяц; /month ГГГГ-ММ — за выбранный месяц.\n'
        '/sync — повторить отправку в Google Таблицу.\n'
        '/cancel — отменить весь текущий черновик. Сохранённые отчёты останутся.')

@router.message(Command('back'))
async def back_to_report(message:Message):
    if not allowed(message):return
    uid=message.from_user.id
    if uid in saving or uid in busy:
        await message.answer('Идёт сохранение или распознавание. Дождись его завершения.');return
    editing.pop(uid,None);staff_sessions.pop(uid,None)
    draft=drafts.get(uid)
    if not draft:
        await message.answer('Текущего черновика нет. Отправь фото или /manual.');return
    menu=await message.answer(items_text(draft),reply_markup=items_keyboard(draft));draft.menu_id=menu.message_id

@router.message(Command('manual'))
async def manual_report(message:Message):
    if not allowed(message):return
    uid=message.from_user.id
    if uid in drafts or uid in busy:
        await message.answer('Сначала заверши или отмени предыдущий отчёт.');return
    nonce=secrets.token_hex(5)
    draft=f.Draft(message.date.astimezone(f.MSK).date().isoformat(),'manual:'+nonce,nonce,sent_at=message.date.isoformat())
    drafts[uid]=draft
    menu=await message.answer(items_text(draft),reply_markup=items_keyboard(draft));draft.menu_id=menu.message_id

@router.message(Command('cancel'))
async def cancel(message:Message):
    if not allowed(message):return
    uid=message.from_user.id
    if uid in saving:
        await message.answer('Идёт сохранение. Дождись результата.');return
    drafts.pop(uid,None);editing.pop(uid,None);staff_sessions.pop(uid,None)
    await message.answer('Текущий черновик отменён.')

@router.message(Command('sync'))
async def manual_sync(message:Message):
    if not allowed(message):return
    try:
        _,pending=await sync_with_tracking()
        await message.answer('⚠️ Новые изменения ожидают синхронизации. Повтори /sync.' if pending else 'Google Таблицы синхронизированы.')
    except ValueError:
        await message.answer('⚠️ Google Таблица содержит несогласованные данные. Проверь таблицу перед повтором /sync; локальная база сохранена.')
    except Exception:
        await message.answer('Не удалось обновить Google. Локальная база сохранена; повтори /sync.')

async def process_photo(message,bot,file):
    if TEST_HANDLERS is not None:
        try:
            if await TEST_HANDLERS.handle_photo(message,bot,file):return
        except Exception:
            if TEST_HANDLERS.is_test(message.from_user.id):
                await message.answer('⛔ Тестовый режим недоступен. Фото не отправлено в рабочий режим.')
                return
            raise
        if TEST_HANDLERS.is_test(message.from_user.id):return
    if not allowed(message):return
    uid=message.from_user.id
    if uid in busy or uid in drafts:
        await message.answer('Сначала заверши или отмени текущий отчёт.');return
    busy.add(uid)
    try:
        await message.answer('Открываю фотографию для выбора начала.')
        buffer=io.BytesIO();await bot.download(file,destination=buffer);data=buffer.getvalue()
        if len(data)>20*1024*1024:raise ValueError('Файл больше 20 МБ')
        with Image.open(io.BytesIO(data)) as src:
            if src.width*src.height>35_000_000 or src.width<2 or src.height<2:raise ValueError('Неподходящий размер фотографии')
        candidate=await asyncio.to_thread(f.detect_boundary,data)
        nonce=secrets.token_hex(5)
        draft=f.Draft(message.date.astimezone(f.MSK).date().isoformat(),file.file_id,nonce,
                      image_bytes=data,boundary=candidate or (.5,.5),photo_unique_id=getattr(file,'file_unique_id',''),
                      photo_hash=hashlib.sha256(data).hexdigest(),sent_at=message.date.isoformat())
        preview=await asyncio.to_thread(f.preview_boundary,data,draft.boundary)
        prefix='Найдена возможная метка. ' if candidate else 'Автоматически найти метку не удалось. '
        menu=await message.answer_photo(BufferedInputFile(preview,filename='boundary.jpg'),caption=prefix+boundary_caption(draft),reply_markup=boundary_keyboard(draft))
        draft.menu_id=menu.message_id;drafts[uid]=draft
    except Exception:
        await message.answer('Не удалось открыть изображение. Попробуй другое фото или /manual.')
    finally:busy.discard(uid)

@router.message(F.photo)
async def photo(message:Message,bot:Bot):await process_photo(message,bot,message.photo[-1])
@router.message(F.document)
async def document(message:Message,bot:Bot):
    if message.document.mime_type and message.document.mime_type.startswith('image/'):await process_photo(message,bot,message.document)
    elif allowed(message):await message.answer('Отправь изображение.')

def dates_keyboard(draft):
    return keyboard([[button('Сегодня',cb(draft,'day:0')),button('Вчера',cb(draft,'day:1'))],
                     [button('📅 Календарь',cb(draft,'calendar:'+datetime.now(f.MSK).strftime('%Y%m')))],
                     [button('Ввести дату',cb(draft,'dateinput')),button('↩️ Назад',cb(draft,'page:0'))]])

def calendar_keyboard(draft,year,month):
    first=date(year,month,1);previous=(first-timedelta(days=1)).replace(day=1);nxt=(first+timedelta(days=32)).replace(day=1)
    rows=[[button('◀️',cb(draft,'calendar:'+previous.strftime('%Y%m'))),button(first.strftime('%Y-%m'),cb(draft,'noop')),
           button('▶️',cb(draft,'calendar:'+nxt.strftime('%Y%m')))]]
    rows.append([button(x,cb(draft,'noop')) for x in ('Пн','Вт','Ср','Чт','Пт','Сб','Вс')])
    today=datetime.now(f.MSK).date()
    for week in calendar.monthcalendar(year,month):
        row=[]
        for day in week:
            selected=date(year,month,day) if day else None
            row.append(button(str(day) if day else '·',cb(draft,'pick:'+selected.strftime('%Y%m%d')) if selected and selected<=today else cb(draft,'noop')))
        rows.append(row)
    rows.append([button('↩️ Назад',cb(draft,'page:0'))]);return keyboard(rows)

def staff_keyboard(session):
    prefix='st:'+session['nonce']+':'
    rows=[];people=store.employees();page=session.get('page',0);start=page*20
    for person in people[start:start+20]:
        rows.append([button(person['name'],prefix+'noop'),button('✏️',prefix+'rename:'+str(person['id'])),button('Убрать',prefix+'remove:'+str(person['id']))])
    nav=[]
    if page>0:nav.append(button('◀️',prefix+'page:'+str(page-1)))
    if start+20<len(people):nav.append(button('▶️',prefix+'page:'+str(page+1)))
    if nav:rows.append(nav)
    rows.extend([[button('➕ Добавить сотрудника',prefix+'add')],[button('↩️ К отчёту',prefix+'back')]])
    return keyboard(rows)

async def open_staff(message,uid):
    session={'nonce':secrets.token_hex(5),'menu_id':None,'page':0}
    staff_sessions[uid]=session
    result=await message.answer('👥 Сотрудники. Выбери ✏️ для переименования или «Убрать». История выплат сохраняется.',reply_markup=staff_keyboard(session))
    session['menu_id']=result.message_id

@router.message(Command('employees'))
async def employees_command(message:Message):
    if not allowed(message):return
    if message.from_user.id in saving:
        await message.answer('Дождись сохранения отчёта.');return
    await open_staff(message,message.from_user.id)

@router.callback_query(F.data.startswith('st:'))
async def staff_callback(query:CallbackQuery):
    if not cb_allowed(query):await query.answer('Нет доступа',show_alert=True);return
    uid=query.from_user.id;session=staff_sessions.get(uid);parts=query.data.split(':')
    if not session or len(parts)<3 or parts[1]!=session['nonce'] or query.message.message_id!=session['menu_id'] or uid in saving:
        await query.answer('Кнопка больше не активна',show_alert=True);return
    await query.answer();action=parts[2]
    if action=='noop':return
    if action=='page':
        try:page=int(parts[3])
        except (IndexError,ValueError):return
        if page<0 or page>max(0,(len(store.employees())-1)//20):return
        session['page']=page
        await query.message.edit_text('👥 Сотрудники.',reply_markup=staff_keyboard(session));return
    if action=='back':
        if uid in editing and editing[uid][0] in ('staff_add','staff_rename'):editing.pop(uid,None)
        staff_sessions.pop(uid,None)
        draft=drafts.get(uid)
        if draft:
            menu=await query.message.answer(items_text(draft),reply_markup=items_keyboard(draft));draft.menu_id=menu.message_id
        else:await query.message.answer('Список сотрудников закрыт.')
        return
    if action=='add':
        editing[uid]=('staff_add',session['nonce'],None)
        await query.message.answer('Отправь имя нового сотрудника.');return
    if action in ('rename','remove'):
        try:ident=int(parts[3])
        except (IndexError,ValueError):return
        if action=='rename':
            editing[uid]=('staff_rename',session['nonce'],ident)
            await query.message.answer('Отправь новое имя сотрудника.');return
        try:store.remove_employee(ident)
        except ValueError as exc:await query.message.answer(str(exc));return
        draft=drafts.get(uid)
        if draft:draft.ready=False;draft.confirmed=False
        await query.message.edit_text('👥 Сотрудник убран. История выплат сохранена.',reply_markup=staff_keyboard(session))

@router.callback_query(F.data.startswith('v3:'))
async def on_callback(query:CallbackQuery):
    if not cb_allowed(query):await query.answer('Нет доступа',show_alert=True);return
    uid=query.from_user.id;draft=drafts.get(uid);parts=query.data.split(':')
    if not draft or len(parts)<3 or parts[1]!=draft.nonce or query.message.message_id!=draft.menu_id:
        await query.answer('Кнопка больше не активна',show_alert=True);return
    if uid in saving or uid in busy:
        await query.answer('Дождись завершения операции',show_alert=True);return
    if uid in editing:
        await query.answer('Бот ждёт ввод. Отправь значение или /back для возврата к отчёту.',show_alert=True);return
    await query.answer();action=parts[2]
    if action=='noop':return
    if action=='cancel':
        drafts.pop(uid,None);editing.pop(uid,None)
        try:await query.message.edit_reply_markup(reply_markup=None)
        except Exception:pass
        await query.message.answer('Отчёт отменён.');return
    if action in ('line','tilt','left','right'):
        if not draft.image_bytes or not draft.boundary:return
        try:
            if parts[3] not in ('-20','20','-5','5','-1','1','-0.1','0.1','-0.05','0.05'):return
            delta=float(parts[3])/100
        except (IndexError,ValueError):return
        left,right=draft.boundary
        if action=='line':left+=delta;right+=delta
        elif action=='tilt':left-=delta;right+=delta
        elif action=='left':left+=delta
        else:right+=delta
        if min(left,right)<0 or max(left,right)>.98:return
        draft.boundary=(left,right);await refresh_boundary(query.message,draft);return
    if action=='crop':
        if not draft.image_bytes or draft.boundary is None:return
        busy.add(uid)
        try:
            await query.message.edit_reply_markup(reply_markup=None)
            await query.message.answer('Распознаю только область ниже выбранной линии.')
            try:
                result=await ocr_v3.recognize(client,draft.image_bytes,draft.boundary)
                draft.positions=result.positions;draft.warnings=result.warnings
            except Exception:
                draft.positions=[];draft.warnings=['Распознавание не удалось. Сверь фото и добавь суммы вручную.']
        finally:busy.discard(uid)
        menu=await query.message.answer(items_text(draft),reply_markup=items_keyboard(draft));draft.menu_id=menu.message_id
        return
    if action=='page':
        try:page=int(parts[3])
        except (IndexError,ValueError):return
        if page<0 or page>max(0,(len(draft.positions)-1)//10):return
        await show_items(query.message,draft,page);return
    if action=='view_crop':
        try:page=int(parts[3])
        except (IndexError,ValueError):return
        if not draft.image_bytes or draft.boundary is None or page<0 or page>max(0,(len(draft.positions)-1)//10):return
        cropped,_=await asyncio.to_thread(f.crop_after_boundary,draft.image_bytes,draft.boundary)
        await query.message.edit_reply_markup(reply_markup=None)
        await query.message.answer_photo(BufferedInputFile(cropped,filename='selected-area.png'),caption='Выбранная область. Сверь суммы и вернись к списку ниже.')
        menu=await query.message.answer(items_text(draft,page),reply_markup=items_keyboard(draft,page));draft.menu_id=menu.message_id
        return
    if action=='ignore_pending':
        count=sum(p.category is None for p in draft.positions)
        if not count:await show_items(query.message,draft);return
        await query.message.edit_text(f'Не учитывать все нераспределённые позиции: {count}?',reply_markup=keyboard([
            [button('✅ Не учитывать',cb(draft,'ignore_pending_confirm'))],
            [button('↩️ Назад',cb(draft,'page:0'))]]));return
    if action=='ignore_pending_confirm':
        for p in draft.positions:
            if p.category is None:p.category='ignore'
        draft.ready=False;draft.confirmed=False
        await show_items(query.message,draft);return
    if action=='checked':
        if any(p.uncertain and p.category!='ignore' for p in draft.positions):
            await query.message.answer('Сначала исправь или явно исключи неразборчивые позиции.');return
        draft.warnings.clear();draft.ready=False;draft.confirmed=False
        await show_items(query.message,draft);return
    if action=='add':
        if len(draft.positions)>=100:await query.message.answer('Максимум 100 сумм.');return
        editing[uid]=('add',draft.nonce,None)
        await query.message.answer('Отправь сумму или выражение, например 1500+2000.');return
    if action=='staff':await open_staff(query.message,uid);return
    if action=='date':await query.message.edit_text('Выбери дату отчёта:',reply_markup=dates_keyboard(draft));return
    if action=='dateinput':
        editing[uid]=('date',draft.nonce,None);await query.message.answer('Отправь дату в формате ГГГГ-ММ-ДД.');return
    if action=='day':
        try:days=int(parts[3])
        except (IndexError,ValueError):return
        if days not in (0,1):return
        draft.report_date=(datetime.now(f.MSK).date()-timedelta(days=days)).isoformat();draft.ready=False;draft.confirmed=False
        await show_items(query.message,draft);return
    if action=='calendar':
        try:month=datetime.strptime(parts[3],'%Y%m').date().replace(day=1)
        except (IndexError,ValueError):return
        if month.year<2000 or month>datetime.now(f.MSK).date().replace(day=1):return
        await query.message.edit_text('Выбери дату отчёта:',reply_markup=calendar_keyboard(draft,month.year,month.month));return
    if action=='pick':
        try:selected=datetime.strptime(parts[3],'%Y%m%d').date()
        except (IndexError,ValueError):return
        if selected>datetime.now(f.MSK).date() or selected.year<2000:return
        draft.report_date=selected.isoformat();draft.ready=False;draft.confirmed=False
        await show_items(query.message,draft);return
    if action in ('pos','assign','emp','src','edit','term','emplist'):
        try:index=int(parts[3]);p=draft.positions[index]
        except (IndexError,ValueError):return
        if index<0:return
        if action=='pos':
            await query.message.edit_text(p.display+'\nСейчас: '+position_label(p)+'\nКуда назначить?',reply_markup=choice_keyboard(draft,index));return
        if action=='emplist':
            try:page=int(parts[4])
            except (IndexError,ValueError):return
            if page<0 or page>max(0,(len(store.employees())-1)//20):return
            await query.message.edit_text('Выбери сотрудника:',reply_markup=employee_choice(draft,index,page));return
        if action=='edit':
            rows=[[button('Изменить всё выражение',cb(draft,f'editall:{index}'))]]
            for n,t in enumerate(p.terms):rows.append([button(f'Слагаемое {n+1}: {f.amount_text(t)}',cb(draft,f'term:{index}:{n}'))])
            rows.append([button('↩️ Назад',cb(draft,f'pos:{index}'))])
            await query.message.edit_text('Что исправить?',reply_markup=keyboard(rows));return
        if action=='term':
            try:term=int(parts[4])
            except (IndexError,ValueError):return
            if not 0<=term<len(p.terms):return
            editing[uid]=('term',draft.nonce,(index,term));await query.message.answer('Введи новое значение слагаемого.');return
        if action=='assign':
            try:category=parts[4]
            except IndexError:return
            if category not in f.CATEGORIES:return
            if category!='ignore' and (p.uncertain or p.amount is None):
                await query.message.answer('Сначала исправь неясную сумму.');return
            if category=='employee':await query.message.edit_text('Выбери сотрудника:',reply_markup=employee_choice(draft,index));return
            if category in ('beznal','nal','itog') and any(n!=index and x.category==category for n,x in enumerate(draft.positions)):
                await query.message.answer('Эта категория уже назначена. Сначала переназначь прежнюю сумму.');return
            p.category=category;p.employee_id=None;p.source=None;draft.ready=False;draft.confirmed=False
            await show_items(query.message,draft,index//10);return
        if action=='emp':
            try:ident=int(parts[4])
            except (IndexError,ValueError):return
            if ident not in [x['id'] for x in store.employees()]:return
            await query.message.edit_text('Выбери источник выплаты:',reply_markup=keyboard([[button(SOURCES[k],cb(draft,f'src:{index}:{ident}:{k}'))] for k in f.SOURCES]+[[button('↩️ Назад',cb(draft,f'assign:{index}:employee'))]]));return
        if action=='src':
            try:ident=int(parts[4]);source=parts[5]
            except (IndexError,ValueError):return
            if source not in f.SOURCES or ident not in [x['id'] for x in store.employees()] or p.uncertain or p.amount is None:return
            p.category='employee';p.employee_id=ident;p.source=source;draft.ready=False;draft.confirmed=False
            await show_items(query.message,draft,index//10);return
    if action=='editall':
        try:index=int(parts[3]);draft.positions[index]
        except (IndexError,ValueError):return
        if index<0:return
        editing[uid]=('edit',draft.nonce,index);await query.message.answer('Отправь правильную сумму или выражение.');return
    if action=='done':
        try:draft.validate()
        except ValueError as exc:await query.message.answer('⛔ '+str(exc));return
        active={p['id'] for p in store.employees()}
        if any(p.category=='employee' and p.employee_id not in active for p in draft.positions):
            await query.message.answer('⛔ Сотрудник убран из списка. Переназначь его выплату.');return
        draft.ready=True;draft.confirmed=False
        pages=split_summary(summary_text(draft))
        confirmation=keyboard([[button('✅ Подтвердить и сохранить',cb(draft,'confirm'))],[button('↩️ Исправить',cb(draft,'page:0'))]])
        if len(pages)==1:
            await query.message.edit_text(pages[0],reply_markup=confirmation)
        else:
            await query.message.edit_text(pages[0],reply_markup=None)
            for page in pages[1:-1]:await query.message.answer(page)
            menu=await query.message.answer(pages[-1],reply_markup=confirmation);draft.menu_id=menu.message_id
        return
    if action in ('confirm','replace'):
        if not draft.ready:await query.message.answer('Сначала нажми «Готово».');return
        draft.confirmed=True;saving.add(uid);snapshot=copy.deepcopy(draft)
        try:
            async with db_lock:status=await asyncio.to_thread(store.save,snapshot,uid,action=='replace')
            if status=='exists':
                await query.message.edit_text('За эту дату уже есть отчёт. Заменить его?',reply_markup=keyboard([[button('⚠️ Подтвердить замену',cb(draft,'replace'))],[button('↩️ Назад',cb(draft,'page:0'))]]));return
            if status in ('duplicate_photo','already_saved','missing'):
                await query.message.answer({'duplicate_photo':'Эта фотография уже сохранена за другую дату.','already_saved':'Этот черновик уже сохранён.','missing':'Отчёт для замены не найден.'}[status]);return
            if status!='saved':raise ValueError('Неизвестный результат сохранения')
            drafts.pop(uid,None);editing.pop(uid,None)
            try:await query.message.edit_reply_markup(reply_markup=None)
            except Exception:pass
            try:await query.message.answer('✅ Отчёт за '+snapshot.report_date+' сохранён локально.')
            except Exception:pass
            try:
                _,pending=await sync_with_tracking()
                text='⚠️ Новые изменения ожидают синхронизации. Повтори /sync.' if pending else '✅ Google Таблица обновлена.'
                try:await query.message.answer(text)
                except Exception:pass
            except ValueError:
                try:await query.message.answer('⚠️ Google Таблица содержит несогласованные данные. Локальный отчёт сохранён; проверь таблицу перед /sync.')
                except Exception:pass
            except Exception:
                try:await query.message.answer('⚠️ Google Таблица не обновлена. Локальный отчёт сохранён; повтори /sync.')
                except Exception:pass
        except Exception as exc:
            draft.confirmed=False
            await query.message.answer('⛔ Не удалось сохранить отчёт. Проверь данные и повтори.')
        finally:saving.discard(uid)

@router.message(F.text)
async def handle_text(message:Message):
    if not allowed(message):return
    uid=message.from_user.id
    if uid in saving or uid in busy:
        await message.answer('Дождись завершения операции.');return
    state=editing.get(uid)
    if not state:
        await message.answer('Отправь фотографию или выбери действие в меню.');return
    kind,nonce,target=state;text=message.text.strip()
    if kind in ('staff_add','staff_rename'):
        session=staff_sessions.get(uid)
        if not session or session['nonce']!=nonce:
            editing.pop(uid,None);await message.answer('Меню сотрудников устарело.');return
        try:
            if kind=='staff_add':store.add_employee(text)
            else:store.rename_employee(target,text)
        except ValueError as exc:await message.answer('⛔ '+str(exc)+' Отправь другое имя или /back для возврата к отчёту.');return
        editing.pop(uid,None)
        draft=drafts.get(uid)
        if draft:draft.ready=False;draft.confirmed=False
        menu=await message.answer('👥 Список обновлён.',reply_markup=staff_keyboard(session));session['menu_id']=menu.message_id
        return
    draft=drafts.get(uid)
    if not draft or draft.nonce!=nonce:
        editing.pop(uid,None);await message.answer('Черновик устарел.');return
    try:
        if kind=='date':
            selected=date.fromisoformat(text)
            if selected>datetime.now(f.MSK).date() or selected.year<2000:raise ValueError('Дата вне допустимого диапазона')
            draft.report_date=selected.isoformat()
        elif kind=='add':draft.positions.append(f.Position.from_text(text,origin='manual'))
        elif kind=='edit':
            old=draft.positions[target]
            new=f.Position.from_text(text,bbox=old.bbox,origin='manual')
            new.category=old.category;new.employee_id=old.employee_id;new.source=old.source
            draft.positions[target]=new
        elif kind=='term':
            index,term=target;draft.positions[index].edit_term(term,text);draft.positions[index].origin='manual'
        else:raise ValueError('Неизвестное действие')
    except (ValueError,IndexError) as exc:
        await message.answer('⛔ '+str(exc)+' Попробуй ещё раз или /back для возврата к отчёту.');return
    draft.ready=False;draft.confirmed=False;editing.pop(uid,None)
    page=(target//10 if kind=='edit' else target[0]//10 if kind=='term' else max(0,(len(draft.positions)-1)//10) if kind=='add' else 0)
    menu=await message.answer(items_text(draft,page),reply_markup=items_keyboard(draft,page));draft.menu_id=menu.message_id

async def main():
    if os.getenv('FINANCE_ALLOW_POLLING')!='1':raise RuntimeError('Запуск заблокирован до отдельного разрешения пользователя')
    if not TOKEN or not API_KEY or not ADMIN_ID or not SHEET_ID:raise RuntimeError('Не заполнены настройки бота')
    store.initialize()
    bot=Bot(token=TOKEN);dp=Dispatcher()
    global TEST_HANDLERS
    try:
        TEST_HANDLERS=maxfinance_test.create_test_handlers(BASE,DATABASE,SHEET_ID,client,ADMIN_ID)
        dp.include_router(TEST_HANDLERS.router)
    except Exception as exc:
        TEST_HANDLERS=maxfinance_test.UnavailableTestMode(BASE)
        print('TEST_MODE_INIT_ERROR:',repr(exc),flush=True)
    dp.include_router(reports_router);dp.include_router(router)
    try:await dp.start_polling(bot)
    finally:await bot.session.close();await client.close()

if __name__=='__main__':asyncio.run(main())
