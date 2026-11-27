"""Дневные, недельные и месячные сводки для v2 и v3."""
import os,sqlite3
from contextlib import closing
from calendar import monthrange
from datetime import date,datetime,timedelta
from decimal import Decimal
from pathlib import Path
from dotenv import load_dotenv
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from finance_v3 import Store,MSK,amount_text

BASE=Path(__file__).resolve().parent
load_dotenv(BASE/'.env')
DATABASE=Path(os.getenv('FINANCE_DATABASE',str(BASE/'finance.db')))
ADMIN_ID=int(os.getenv('ADMIN_ID','0'))
reports_router=Router()

def format_summary(title,start,end):
    with closing(sqlite3.connect(DATABASE)) as db:
        rows=db.execute('SELECT d.beznal,d.nal,d.itog,v.report_date,v.beznal_cents,v.nal_cents,v.itog_cents FROM daily_reports d LEFT JOIN report_amounts_v3 v ON v.report_date=d.report_date WHERE d.report_date BETWEEN ? AND ?',(start.isoformat(),end.isoformat())).fetchall()
    if not rows:return '📊 '+title+'\nЗа этот период финансовых отчётов нет.'
    totals=[Decimal(0)]*3;present=[False]*3
    for row in rows:
        for i in range(3):
            value=(Decimal(row[4+i])/100 if row[4+i] is not None else None) if row[3] is not None else (Decimal(str(row[i])) if row[i] is not None else None)
            if value is not None:totals[i]+=value;present[i]=True
    period=start.strftime('%d.%m.%Y') if start==end else f'{start:%d.%m.%Y} — {end:%d.%m.%Y}'
    lines=[f'📊 {title}',f'📅 {period}',f'📄 Дней с отчётами: {len(rows)}','']
    for label,val,exists in zip(('💳 Безнал','💵 Наличные','📈 Итог'),totals,present):
        lines.append(label+': '+(amount_text(val)+' ₽' if exists else '—'))
    if any(row[3] is None for row in rows):
        lines.append('⚠️ В старых отчётах сохранены прежние значения, в том числе после вычетов.')
    employees=Store(DATABASE).employee_summaries(start.isoformat(),end.isoformat())
    lines+=['','👥 ВЫПЛАТЫ СОТРУДНИКАМ']
    if not employees:lines.append('Выплат не записано.')
    for p in employees:
        lines.append(f"• {p['name']}: безнал {amount_text(p['beznal'])}, нал {amount_text(p['nal'])}, не указан {amount_text(p['unknown'])}; всего {amount_text(p['total'])} ₽")
    debts=[(day,amount) for day,amount,_ in Store(DATABASE).debts() if start.isoformat()<=day<=end.isoformat()]
    if debts:
        lines+=['','📌 Долги:']+[f'{day}: {amount_text(amount)} ₽' for day,amount in debts]
    result='\n'.join(lines)
    return result if len(result)<4000 else 'Слишком много сотрудников. Посмотри вкладку «Итого сотрудников» в Google Таблице.'

def allowed(message):return message.chat.type=='private' and message.from_user and ADMIN_ID and message.from_user.id==ADMIN_ID

def argument(message):return (message.text or '').partition(' ')[2].strip()

@reports_router.message(Command('day'))
async def day_report(message:Message):
    if not allowed(message):return
    try:selected=date.fromisoformat(argument(message)) if argument(message) else datetime.now(MSK).date()
    except ValueError:
        await message.answer('Формат: /day 2026-10-21');return
    await message.answer(format_summary('ДНЕВНОЙ ОТЧЁТ',selected,selected))

@reports_router.message(Command('week'))
async def week_report(message:Message):
    if not allowed(message):return
    try:selected=date.fromisoformat(argument(message)) if argument(message) else datetime.now(MSK).date()
    except ValueError:
        await message.answer('Формат: /week 2026-10-21');return
    start=selected-timedelta(days=selected.weekday())
    await message.answer(format_summary('НЕДЕЛЬНЫЙ ОТЧЁТ',start,start+timedelta(days=6)))

@reports_router.message(Command('month'))
async def month_report(message:Message):
    if not allowed(message):return
    try:selected=datetime.strptime(argument(message),'%Y-%m').date() if argument(message) else datetime.now(MSK).date()
    except ValueError:
        await message.answer('Формат: /month 2026-10');return
    await message.answer(format_summary('МЕСЯЧНЫЙ ОТЧЁТ',selected.replace(day=1),selected.replace(day=monthrange(selected.year,selected.month)[1])))
