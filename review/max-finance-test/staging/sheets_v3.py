"""Синхронизация в совместимые вкладки. Вызывается только после подтверждения."""
from collections import defaultdict,Counter
from decimal import Decimal,InvalidOperation
from contextlib import closing
import json
import gspread
from finance_v3 import sheet_number

HEADERS=['Дата','Безнал','Наличные','Итог','Безнал исходный','Вычеты безнал','Нал исходный','Вычеты нал']
EMPLOYEE_HEADERS=['Дата','Сотрудник','Источник','Сумма']
TOTAL_HEADERS=['Дата','Сотрудник','Безнал','Наличные','Не указан','Всего']
DEBT_HEADERS=['Дата','Сумма','Исходная запись']
LEGACY_SUMMARY_HEADERS=['Сотрудник','Безнал','Наличные','Всего']

def legacy_summary(rows):
    totals=defaultdict(lambda:{'beznal':Decimal(0),'nal':Decimal(0),'unknown':Decimal(0)})
    for _,name,source,amount in rows:
        totals[name][source if source in ('beznal','nal') else 'unknown']+=Decimal(amount)
    return [[name,sheet_number(t['beznal']),sheet_number(t['nal']),
             sheet_number(sum(t.values(),Decimal(0)))] for name,t in sorted(totals.items())]

def employee_totals(rows):
    grouped=defaultdict(lambda:{'beznal':Decimal(0),'nal':Decimal(0),'unknown':Decimal(0)})
    for day,name,source,amount in rows:
        if source not in ('beznal','nal','unknown'):source='unknown'
        grouped[(day,name)][source]+=Decimal(amount)
    result=[]
    for (day,name),amounts in sorted(grouped.items()):
        result.append([day,name,*[sheet_number(amounts[k]) for k in ('beznal','nal','unknown')],sheet_number(sum(amounts.values(),Decimal(0)))])
    return result

def get_sheet(book,name,headers):
    try:sheet=book.worksheet(name)
    except gspread.WorksheetNotFound:sheet=book.add_worksheet(title=name,rows=200,cols=len(headers))
    header=sheet.row_values(1)
    if header and header!=headers:raise ValueError('Заголовки вкладки «'+name+'» изменены')
    if not header:
        sheet.update(range_name=f'A1:{chr(64+len(headers))}1',values=[headers]);sheet.freeze(rows=1)
    return sheet

def replace_table(sheet,headers,rows):
    existing=sheet.get_all_values();old_count=max(0,len(existing)-1)
    needed=max(200,len(rows)+2,old_count+2)
    if sheet.row_count<needed:sheet.add_rows(needed-sheet.row_count)
    last=chr(64+len(headers))
    if rows:sheet.update(range_name=f'A2:{last}{len(rows)+1}',values=rows,value_input_option='RAW')
    if old_count>len(rows):sheet.batch_clear([f'A{len(rows)+2}:{last}{old_count+1}'])

def canonical(row,width,numeric_columns):
    values=list(row[:width])+['']*max(0,width-len(row))
    result=[]
    for i,value in enumerate(values):
        text='' if value is None else str(value).strip()
        if i in numeric_columns and text:
            try:
                number=Decimal(text.replace('\u00a0','').replace('\u202f','').replace(' ','').replace(',','.'))
                if number.is_finite():text=format(number.normalize(),'f')
            except InvalidOperation:pass
        result.append(text)
    return tuple(result)

def guard_table(current,desired,previous,width,numeric_columns,name):
    if any(any(str(x).strip() for x in row[width:]) for row in current):
        raise ValueError('Вкладка «'+name+'» содержит данные за пределами управляемых столбцов')
    now=Counter(canonical(row,width,numeric_columns) for row in current if any(str(x).strip() for x in row))
    target=Counter(canonical(row,width,numeric_columns) for row in desired)
    old=Counter(canonical(row,width,numeric_columns) for row in (previous or []))
    if any(count>max(target[row],old[row]) for row,count in now.items()):
        raise ValueError('Вкладка «'+name+'» содержит непризнанные изменения; синхронизация остановлена')

def pending_revisions(store,payouts):
    if not hasattr(store,'pending_sync') or not hasattr(store,'connect'):return {},payouts
    pending={entity[7:] for entity,_ in store.pending_sync() if entity.startswith('report:')}
    if not pending:return {},payouts
    revisions={};previous=[row for row in payouts if row[0] not in pending]
    with closing(store.connect()) as db:
        for day in pending:
            item=db.execute('SELECT snapshot_json FROM report_revision_details WHERE report_date=? ORDER BY id DESC LIMIT 1',(day,)).fetchone()
            if not item:
                previous.extend(row for row in payouts if row[0]==day);continue
            snap=json.loads(item[0]);report=snap.get('report')
            if not isinstance(report,dict) or report.get('report_date')!=day:
                raise ValueError('Невозможно проверить историю заменённого отчёта')
            columns=('report_date','beznal','nal','itog','beznal_gross','beznal_deductions','nal_gross','nal_deductions')
            revisions[day]=[report.get(c) for c in columns]
            legacy=snap.get('legacy_payouts',snap.get('employees',[]))
            for p in legacy:
                previous.append((day,p['employee_code'],p['payment_type'],Decimal(str(p['amount']))))
            for p in snap.get('v3_payouts',[]):
                previous.append((day,p['name_at_save'],p['source'],Decimal(p['amount_cents'])/100))
    return revisions,previous

def sync(book,store):
    try:sheet=book.worksheet('Все записи')
    except gspread.WorksheetNotFound:
        sheet=book.sheet1
        if sheet.row_values(1) not in ([],HEADERS[:4]):raise ValueError('Первый лист содержит другие данные')
        sheet.update_title('Все записи')
    header=sheet.row_values(1)
    if not header:sheet.update(range_name='A1:H1',values=[HEADERS])
    else:
        if header[:4]!=HEADERS[:4] or (header[4:8] and header[4:8]!=HEADERS[4:4+len(header[4:8])]):raise ValueError('Заголовки финансовой вкладки изменены')
        if header[4:8]!=HEADERS[4:8]:sheet.update(range_name='E1:H1',values=[HEADERS[4:]])
    current=sheet.get_all_values();date_rows={}
    for number,row in enumerate(current[1:],2):
        if row and row[0]:
            if row[0] in date_rows:raise ValueError('Повтор даты в Google Таблице')
            date_rows[row[0]]=number
    report_rows=store.all_reports();payouts=store.all_payouts()
    snapshots=store.sheet_snapshots()
    revisions,previous_payouts=pending_revisions(store,payouts)
    report_by_date={row[0]:row for row in report_rows}
    old_report_by_date={row[0]:row for row in snapshots.get('Все записи',[]) if row}
    for row in current[1:]:
        if not row or not row[0] or row[0] not in report_by_date:continue
        value=canonical(row,8,set(range(1,8)))
        allowed=[canonical(report_by_date[row[0]],8,set(range(1,8)))]
        if row[0] in old_report_by_date:allowed.append(canonical(old_report_by_date[row[0]],8,set(range(1,8))))
        if row[0] in revisions:allowed.append(canonical(revisions[row[0]],8,set(range(1,8))))
        if value not in allowed:raise ValueError('Отчёт за '+row[0]+' изменён в Google; синхронизация остановлена')
    names={'beznal':'Безнал','nal':'Наличные','unknown':'Не указан'}
    employee_rows=[[day,name,names.get(source,'Не указан'),sheet_number(amount)] for day,name,source,amount in payouts]
    previous_employee_rows=[[day,name,names.get(source,'Не указан'),sheet_number(amount)] for day,name,source,amount in previous_payouts]
    total_rows=employee_totals(payouts)
    debt_rows=[[day,sheet_number(amount),raw] for day,amount,raw in store.debts()]
    targets=[('Сотрудники',EMPLOYEE_HEADERS,employee_rows,{3}),
             ('Итого сотрудников',TOTAL_HEADERS,total_rows,{2,3,4,5}),
             ('Долги',DEBT_HEADERS,debt_rows,{1})]
    try:legacy_sheet=book.worksheet('Сводка сотрудников')
    except gspread.WorksheetNotFound:legacy_sheet=None
    if legacy_sheet is not None:
        header=legacy_sheet.row_values(1)
        if header and header!=LEGACY_SUMMARY_HEADERS:raise ValueError('Заголовки сводки сотрудников изменены')
        with closing(store.connect()) as db:
            legacy=db.execute('SELECT p.report_date,COALESCE(s.name,p.employee_code),p.payment_type,p.amount FROM employee_payouts p LEFT JOIN staff_alias_v3 a ON a.alias=p.employee_code LEFT JOIN staff_v3 s ON s.id=a.staff_id').fetchall()
        baseline=snapshots.get('Сводка сотрудников',legacy_summary(previous_payouts if revisions else legacy))
        rows=legacy_summary(payouts)
        guard_table(legacy_sheet.get_all_values()[1:],rows,baseline,4,{1,2,3},'Сводка сотрудников')
        targets.append(('Сводка сотрудников',LEGACY_SUMMARY_HEADERS,rows,{1,2,3}))
    target_sheets=[]
    for name,headers,rows,numeric in targets:
        target=get_sheet(book,name,headers)
        previous=baseline if name=='Сводка сотрудников' else snapshots.get(name)
        if name=='Сотрудники' and previous is None:previous=previous_employee_rows
        guard_table(target.get_all_values()[1:],rows,previous,len(headers),numeric,name)
        target_sheets.append((target,headers,rows))
    updates=[];appends=[]
    for row in report_rows:
        vals=['' if v is None else v for v in row]
        if row[0] in date_rows:updates.append({'range':f'A{date_rows[row[0]]}:H{date_rows[row[0]]}','values':[vals]})
        else:appends.append(vals)
    if updates:sheet.batch_update(updates,value_input_option='RAW')
    if appends:sheet.append_rows(appends,value_input_option='RAW')
    for target,headers,rows in target_sheets:replace_table(target,headers,rows)
    store.save_sheet_snapshots({'Все записи':[list(row) for row in report_rows],
                                **{name:rows for name,_,rows,_ in targets}})
