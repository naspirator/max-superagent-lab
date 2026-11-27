"""Извлечение сумм и локальное хранилище v3."""
import io, json, math, re, shutil, sqlite3, subprocess, secrets
from collections import defaultdict
from contextlib import closing
from dataclasses import dataclass,field
from datetime import date,datetime,timezone,timedelta
from decimal import Decimal
from pathlib import Path
from PIL import Image,ImageDraw,ImageOps

DEFAULT_EMPLOYEES=('ПЕТ','РОС','ДИМ','ОЛИ','ТОЛ','ДАН','ВЛА')
CATEGORIES=('beznal','nal','itog','employee','debt','ignore')
SOURCES=('beznal','nal','unknown')
MSK=timezone(timedelta(hours=3))

def find_first_label(rows,width,height):
    if not width or not height:return None
    candidates=[]
    for row in rows:
        text=str(row.get('text','')).strip().upper().replace(' ','')
        if not re.search(r'(?<![А-ЯЁA-Z])(Б/Н|БН|BN|БЕЗНАЛ)(?![А-ЯЁA-Z])',text):continue
        try:
            confidence=float(row['confidence']);top=int(row['top'])
            left=int(row['left']);w=int(row['width']);h=int(row['height'])
        except (KeyError,TypeError,ValueError):return None
        if not 0<=top<height or not 0<=left<width or w<=0 or h<=0:return None
        candidates.append((top,confidence))
    if not candidates:return None
    top,confidence=min(candidates)
    if confidence<85:return None
    return (top/height,top/height)

def detect_boundary(image_bytes):
    executable=shutil.which('tesseract')
    if not executable:return None
    try:
        with Image.open(io.BytesIO(image_bytes)) as src:image=ImageOps.exif_transpose(src).convert('RGB')
        buf=io.BytesIO();image.save(buf,format='PNG')
        # Только классический OCR (OEM 0). Нейросетевые модели видят лишь обрезанную область.
        result=subprocess.run([executable,'stdin','stdout','-l','rus+eng','--oem','0','tsv'],input=buf.getvalue(),stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=45,check=True)
        import csv
        rows=[]
        for row in csv.DictReader(io.StringIO(result.stdout.decode('utf-8',errors='replace')),delimiter='\t'):
            rows.append({'text':row.get('text'),'confidence':row.get('conf'),'left':row.get('left'),'top':row.get('top'),'width':row.get('width'),'height':row.get('height')})
        return find_first_label(rows,*image.size)
    except (OSError,ValueError,subprocess.SubprocessError):return None

def crop_after_boundary(image_bytes,boundary):
    if not isinstance(boundary,(tuple,list)) or len(boundary)!=2:raise ValueError('Укажите границу БН')
    if any(not isinstance(v,(int,float)) or not math.isfinite(v) or not 0<=v<1 for v in boundary):raise ValueError('Неверная граница')
    if len(image_bytes)>20*1024*1024:raise ValueError('Файл больше 20 МБ')
    with Image.open(io.BytesIO(image_bytes)) as src:
        if src.width*src.height>35_000_000:raise ValueError('Изображение больше 35 мегапикселей')
        image=ImageOps.exif_transpose(src).convert('RGB')
    w,h=image.size
    if w<2 or h<2:raise ValueError('Слишком маленькое изображение')
    left,right=boundary;ly=math.ceil(left*h);ry=math.ceil(right*h);top=min(ly,ry)
    if top>=h-1:raise ValueError('Граница ниже листа')
    mask=Image.new('1',(w,h),0);draw=ImageDraw.Draw(mask)
    for x in range(w):
        start=math.ceil(ly+(ry-ly)*x/(w-1))
        if start<h:draw.line((x,start,x,h-1),fill=1)
    filtered=Image.new('RGB',(w,h),'white');filtered.paste(image,(0,0),mask)
    filtered=filtered.crop((0,top,w,h));output=io.BytesIO();filtered.save(output,format='PNG')
    return output.getvalue(),{'left':left,'right':right,'top':top,'width':w,'height':h}

def preview_boundary(image_bytes,boundary):
    with Image.open(io.BytesIO(image_bytes)) as src:image=ImageOps.exif_transpose(src).convert('RGB')
    width,height=image.size
    ImageDraw.Draw(image).line((0,round(boundary[0]*height),width-1,round(boundary[1]*height)),fill='red',width=max(3,width//300))
    image.thumbnail((1400,1400));out=io.BytesIO();image.save(out,format='JPEG',quality=88)
    return out.getvalue()

def parse_amount(text):
    if not isinstance(text,(str,int)) or isinstance(text,bool):raise ValueError('Введите сумму цифрами')
    value=re.sub(r'\s','',str(text)).replace(',','.')
    if not re.fullmatch(r'\d{1,9}(?:\.\d{1,2})?',value):raise ValueError('Неверная сумма')
    number=Decimal(value)
    if number>Decimal('100000000'):raise ValueError('Сумма слишком большая')
    return number

def amount_text(value):
    txt=f'{Decimal(value):,.2f}'.replace(',',' ')
    return txt[:-3] if txt.endswith('.00') else txt.replace('.',',')

@dataclass
class Position:
    terms:tuple[str,...]
    raw:str
    bbox:tuple|None=None
    category:str|None=None
    employee_id:int|None=None
    source:str|None=None
    uncertain:bool=False
    origin:str='ocr'
    @classmethod
    def from_text(cls,text,**kwargs):
        if not isinstance(text,str):raise ValueError('Неверное выражение')
        value=re.sub(r'\s','',text).replace('＋','+').replace('＝','=').replace(',','.')
        pieces=value.split('=')
        if len(pieces)>2:raise ValueError('Неразборчивый знак равенства')
        parts=pieces[0].split('+')
        if not parts or len(parts)>30:raise ValueError('Неверное число слагаемых')
        numbers=[parse_amount(x) for x in parts];total=sum(numbers,Decimal(0))
        if total>Decimal('100000000'):raise ValueError('Сумма слишком большая')
        if len(pieces)==2 and parse_amount(pieces[1])!=total:raise ValueError('Написанный результат не совпадает с суммой слагаемых')
        return cls(tuple(format(n,'f') for n in numbers),text,**kwargs)
    @property
    def amount(self):return sum((Decimal(t) for t in self.terms),Decimal(0)) if self.terms else None
    @property
    def display(self):
        if self.amount is None:return 'Неясно: '+self.raw[:100]
        result=amount_text(self.amount)+' ₽'
        if len(self.terms)>1:result+=' ('+' + '.join(amount_text(v) for v in self.terms)+')'
        if self.uncertain:result+=' [проверь: '+self.raw[:70]+']'
        return result
    def edit_term(self,index,value):
        if index<0 or index>=len(self.terms):raise ValueError('Слагаемое не найдено')
        values=list(self.terms);values[index]=format(parse_amount(value),'f')
        updated=Position.from_text('+'.join(values));self.terms=updated.terms;self.raw='+'.join(values)

@dataclass
class Extraction:
    positions:list[Position]=field(default_factory=list)
    warnings:list[str]=field(default_factory=list)

def valid_box(b):
    return (isinstance(b,list) and len(b)==4 and all(type(x) in (float,int) and math.isfinite(x) and 0<=x<=1 for x in b) and b[0]<b[2] and b[1]<b[3])

def parse_ocr(content,geometry):
    if not isinstance(content,str) or len(content)>120000:raise ValueError('Пустой или слишком большой ответ')
    text=content.strip()
    if text.startswith('```'):
        match=re.fullmatch(r'```(?:json)?\s*([\s\S]*?)\s*```',text)
        if not match:raise ValueError('Неполный JSON')
        text=match[1]
    def unique(pairs):
        d={}
        for k,v in pairs:
            if k in d:raise ValueError('Повторяющийся ключ JSON')
            d[k]=v
        return d
    data=json.loads(text,object_pairs_hook=unique,parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Недопустимое число')))
    if not isinstance(data,dict) or not isinstance(data.get('items'),list) or len(data['items'])>100:raise ValueError('Некорректный список сумм')
    result=Extraction();by_id={};records=[]
    for row in data['items']:
        if isinstance(row,dict):
            raw_box=row.get('bbox')
            if (isinstance(raw_box,list) and len(raw_box)==4 and
                all(type(x) in (int,float) and math.isfinite(x) and 0<=x<=1000 for x in raw_box)
                and any(x>1 for x in raw_box)):
                row=dict(row,bbox=[x/1000 for x in raw_box])
        if not isinstance(row,dict) or not isinstance(row.get('id'),str) or row['id'] in by_id or not valid_box(row.get('bbox')):
            result.warnings.append('Некорректная позиция или координаты; проверьте лист ниже границы.');continue
        box=row['bbox'];height=geometry['height'];top=geometry['top'];top_y=top+box[1]*(height-top)
        line=lambda x:height*(geometry['left']+(geometry['right']-geometry['left'])*x)
        if top_y+1e-8<max(line(box[0]),line(box[2])):
            result.warnings.append('Позиция пересекает границу; проверьте начало области.');continue
        expr=row.get('expression')
        try:p=Position.from_text(expr,bbox=tuple(box),uncertain=row.get('uncertain') is not False)
        except (ValueError,TypeError):
            # Не вычисляем неизвестные операции. Отдельные цифры показываем
            # только как требующие подтверждения, а не как принятые значения.
            if (isinstance(expr,str) and '+' not in expr and '＋' not in expr and
                re.fullmatch(r'[0-9\s.,=＝−-]+',expr)):
                parts=re.findall(r'\d+(?:[.,]\d{1,2})?',expr)
                if 1<len(parts)<=30:
                    try:
                        candidates=[Position.from_text(x,bbox=tuple(box),uncertain=True) for x in parts]
                        for candidate in candidates:
                            candidate.raw=expr;records.append((row,candidate))
                        by_id[row['id']]=candidates[0]
                        result.warnings.append('Строка содержит неясные знаки: проверьте каждое число вручную.')
                        continue
                    except ValueError:pass
            p=Position((),str(expr or 'неразборчиво')[:100],tuple(box),uncertain=True)
            result.warnings.append('Есть неразборчивая сумма; исправьте её вручную.')
        by_id[row['id']]=p;records.append((row,p))
    skipped=set()
    for row,p in records:
        target=row.get('result_of')
        if target is None:continue
        original=by_id.get(target)
        same_line=(original is not None and original.bbox and p.bbox and
                   max(original.bbox[1],p.bbox[1])<min(original.bbox[3],p.bbox[3]) and
                   original.bbox[2]-.02<=p.bbox[0]<=original.bbox[2]+.2)
        try:
            relation=str(row.get('relation_text') or '')
            evidence=Position.from_text(relation) if '=' in relation else None
            supported=evidence is not None and original is not None and evidence.terms==original.terms and evidence.amount==p.amount
        except ValueError:supported=False
        if same_line and supported and original is not p and not p.uncertain and len(original.terms)>1 and len(p.terms)==1 and original.amount is not None and p.amount==original.amount:skipped.add(row['id'])
        else:
            p.uncertain=True;result.warnings.append('Результат выражения не подтверждён; проверьте повтор.')
    result.positions=[p for row,p in records if row['id'] not in skipped]
    result.positions.sort(key=lambda p:(p.bbox[1],p.bbox[0]))
    if data.get('complete') is not True:result.warnings.append('Полнота чтения не подтверждена; сверьте фото.')
    if not result.positions:result.warnings.append('Суммы не найдены. Добавьте их вручную.')
    return result

@dataclass
class Draft:
    report_date:str
    file_id:str
    nonce:str
    positions:list[Position]=field(default_factory=list)
    warnings:list[str]=field(default_factory=list)
    ready:bool=False
    confirmed:bool=False
    image_bytes:bytes=b''
    boundary:tuple|None=None
    photo_unique_id:str=''
    photo_hash:str=''
    sent_at:str=''
    menu_id:int|None=None
    def validate(self):
        try:selected=date.fromisoformat(self.report_date)
        except (TypeError,ValueError):raise ValueError('Неверная дата')
        if selected>datetime.now(MSK).date():raise ValueError('Дата в будущем')
        if self.warnings:raise ValueError('Проверьте предупреждения')
        if not self.positions:raise ValueError('Добавьте суммы')
        if len(self.positions)>100:raise ValueError('Слишком много позиций')
        categories=defaultdict(int)
        for p in self.positions:
            if p.category not in CATEGORIES:raise ValueError('Распределите каждую сумму')
            if p.category=='ignore':continue
            if p.uncertain or p.amount is None:raise ValueError('Исправьте неясные суммы')
            if p.category in ('beznal','nal','itog'):categories[p.category]+=1
            if p.category=='employee' and (not p.employee_id or p.source not in SOURCES):raise ValueError('Укажите сотрудника и источник')
        if any(n>1 for n in categories.values()):raise ValueError('Для Безнала, Нала и Итога выберите по одной позиции')
        if all(p.category=='ignore' for p in self.positions):raise ValueError('Нет учитываемых сумм')
        return True

def cents(amount):return int(Decimal(amount)*100)
def sheet_number(amount):
    value=Decimal(amount)
    return int(value) if value==value.to_integral_value() else float(value)

class Store:
    def __init__(self,path):self.path=Path(path)
    def connect(self):return sqlite3.connect(self.path,timeout=30)
    def initialize(self):
        with closing(self.connect()) as db,db:
            db.execute('CREATE TABLE IF NOT EXISTS daily_reports (id INTEGER PRIMARY KEY AUTOINCREMENT, report_date TEXT NOT NULL UNIQUE, beznal INTEGER, nal INTEGER, itog INTEGER, telegram_user_id INTEGER, photo_file_id TEXT, created_at TEXT NOT NULL)')
            columns={row[1] for row in db.execute('PRAGMA table_info(daily_reports)')}
            for key in ('sent_at','updated_at','photo_unique_id','photo_hash','beznal_gross','nal_gross','beznal_deductions','nal_deductions'):
                if key not in columns:db.execute(f'ALTER TABLE daily_reports ADD COLUMN {key} '+('INTEGER' if key.endswith(('gross','deductions')) else 'TEXT'))
            db.execute('CREATE TABLE IF NOT EXISTS employee_payouts (id INTEGER PRIMARY KEY AUTOINCREMENT, report_date TEXT NOT NULL,employee_code TEXT NOT NULL,payment_type TEXT NOT NULL,amount INTEGER NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP)')
            db.execute('CREATE TABLE IF NOT EXISTS report_save_tokens (nonce TEXT PRIMARY KEY, report_date TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS report_revision_details (id INTEGER PRIMARY KEY AUTOINCREMENT,report_date TEXT NOT NULL,snapshot_json TEXT NOT NULL,replaced_at TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS report_history (id INTEGER PRIMARY KEY AUTOINCREMENT,report_date TEXT,beznal INTEGER,nal INTEGER,itog INTEGER,photo_file_id TEXT,replaced_at TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS staff_v3 (id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL UNIQUE COLLATE NOCASE,active INTEGER NOT NULL DEFAULT 1)')
            db.execute('CREATE TABLE IF NOT EXISTS staff_alias_v3 (alias TEXT PRIMARY KEY COLLATE NOCASE,staff_id INTEGER NOT NULL REFERENCES staff_v3(id))')
            db.execute('CREATE TABLE IF NOT EXISTS meta_v3 (key TEXT PRIMARY KEY,value TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS report_items_v3 (id INTEGER PRIMARY KEY AUTOINCREMENT,report_date TEXT NOT NULL,position INTEGER NOT NULL,terms_json TEXT NOT NULL,category TEXT NOT NULL,staff_id INTEGER,source TEXT,amount_cents INTEGER NOT NULL,raw TEXT NOT NULL,origin TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS payouts_v3 (id INTEGER PRIMARY KEY AUTOINCREMENT,report_date TEXT NOT NULL,staff_id INTEGER NOT NULL,source TEXT NOT NULL,amount_cents INTEGER NOT NULL,name_at_save TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS report_amounts_v3 (report_date TEXT PRIMARY KEY,beznal_cents INTEGER,nal_cents INTEGER,itog_cents INTEGER)')
            db.execute('CREATE TABLE IF NOT EXISTS sync_outbox_v3 (entity TEXT PRIMARY KEY,version TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,last_error TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS sheet_snapshots_v3 (sheet TEXT PRIMARY KEY,rows_json TEXT NOT NULL)')
            if not db.execute("SELECT 1 FROM meta_v3 WHERE key='staff_initialized'").fetchone():
                for name in DEFAULT_EMPLOYEES:
                    db.execute('INSERT OR IGNORE INTO staff_v3(name) VALUES (?)',(name,))
                    staff_id=db.execute('SELECT id FROM staff_v3 WHERE name=?',(name,)).fetchone()[0]
                    db.execute('INSERT OR IGNORE INTO staff_alias_v3 VALUES (?,?)',(name,staff_id))
                db.execute("INSERT INTO meta_v3 VALUES ('staff_initialized','1')")
            for (name,) in db.execute('SELECT DISTINCT employee_code FROM employee_payouts WHERE employee_code IS NOT NULL').fetchall():
                if db.execute('SELECT 1 FROM staff_alias_v3 WHERE alias=?',(name,)).fetchone():continue
                normalized=' '.join(name.strip().upper().split())
                match=db.execute('SELECT staff_id FROM staff_alias_v3 WHERE alias=?',(normalized,)).fetchone()
                if match:staff_id=match[0]
                else:
                    db.execute('INSERT OR IGNORE INTO staff_v3(name,active) VALUES (?,0)',(normalized,))
                    staff_id=db.execute('SELECT id FROM staff_v3 WHERE name=?',(normalized,)).fetchone()[0]
                db.execute('INSERT OR IGNORE INTO staff_alias_v3 VALUES (?,?)',(name,staff_id))
    def employees(self,active=True):
        with closing(self.connect()) as db:
            db.row_factory=sqlite3.Row
            return [dict(row) for row in db.execute('SELECT id,name,active FROM staff_v3 WHERE active=? ORDER BY id',(int(active),))]
    def add_employee(self,name):
        name=self._name(name)
        with closing(self.connect()) as db,db:
            alias=db.execute('SELECT staff_id FROM staff_alias_v3 WHERE alias=?',(name,)).fetchone()
            if alias:
                status=db.execute('SELECT active,name FROM staff_v3 WHERE id=?',(alias[0],)).fetchone()
                if status and not status[0] and status[1].casefold()==name.casefold():
                    db.execute('UPDATE staff_v3 SET active=1 WHERE id=?',(alias[0],));self._dirty(db,'staff');return alias[0]
                raise ValueError('Имя уже используется или принадлежит истории другого сотрудника')
            try:cur=db.execute('INSERT INTO staff_v3(name) VALUES (?)',(name,))
            except sqlite3.IntegrityError as exc:raise ValueError('Сотрудник уже существует') from exc
            db.execute('INSERT INTO staff_alias_v3 VALUES (?,?)',(name,cur.lastrowid));self._dirty(db,'staff');return cur.lastrowid
    def rename_employee(self,staff_id,name):
        name=self._name(name)
        with closing(self.connect()) as db,db:
            row=db.execute('SELECT name FROM staff_v3 WHERE id=? AND active=1',(staff_id,)).fetchone()
            if not row:raise ValueError('Сотрудник не найден')
            alias=db.execute('SELECT staff_id FROM staff_alias_v3 WHERE alias=?',(name,)).fetchone()
            if alias and alias[0]!=staff_id:raise ValueError('Имя принадлежит другому сотруднику')
            try:db.execute('UPDATE staff_v3 SET name=? WHERE id=?',(name,staff_id))
            except sqlite3.IntegrityError as exc:raise ValueError('Имя уже используется') from exc
            db.execute('INSERT OR IGNORE INTO staff_alias_v3 VALUES (?,?)',(name,staff_id))
            self._dirty(db,'staff')
    def remove_employee(self,staff_id):
        with closing(self.connect()) as db,db:
            if not db.execute('UPDATE staff_v3 SET active=0 WHERE id=? AND active=1',(staff_id,)).rowcount:raise ValueError('Сотрудник не найден')
            self._dirty(db,'staff')

    @staticmethod
    def _dirty(db,entity,version=None):
        version=version or secrets.token_hex(16)
        db.execute('INSERT INTO sync_outbox_v3(entity,version,attempts,last_error) VALUES (?,?,0,NULL) ON CONFLICT(entity) DO UPDATE SET version=excluded.version,attempts=0,last_error=NULL',(entity,version))

    def pending_sync(self):
        with closing(self.connect()) as db:
            return db.execute('SELECT entity,version FROM sync_outbox_v3 ORDER BY entity').fetchall()

    def finish_sync(self,snapshot,success,error=None):
        with closing(self.connect()) as db,db:
            for entity,version in snapshot:
                if success:db.execute('DELETE FROM sync_outbox_v3 WHERE entity=? AND version=?',(entity,version))
                else:db.execute('UPDATE sync_outbox_v3 SET attempts=attempts+1,last_error=? WHERE entity=? AND version=?',((error or 'SyncError')[:100],entity,version))

    def sheet_snapshots(self):
        with closing(self.connect()) as db:
            return {name:json.loads(rows) for name,rows in db.execute('SELECT sheet,rows_json FROM sheet_snapshots_v3')}

    def save_sheet_snapshots(self,snapshots):
        with closing(self.connect()) as db,db:
            for name,rows in snapshots.items():
                db.execute('INSERT INTO sheet_snapshots_v3(sheet,rows_json) VALUES (?,?) ON CONFLICT(sheet) DO UPDATE SET rows_json=excluded.rows_json',(name,json.dumps(rows,ensure_ascii=False)))
    @staticmethod
    def _name(name):
        value=' '.join(str(name).strip().upper().split())
        if not re.fullmatch(r'[А-ЯЁA-Z][А-ЯЁA-Z .-]{0,39}',value):raise ValueError('Имя: до 40 букв, пробел или дефис')
        return value
    def save(self,draft,user_id,replace=False):
        if not draft.ready or not draft.confirmed:raise ValueError('Нужно сначала нажать Готово и подтвердить отчёт')
        draft.validate();now=datetime.now(MSK).isoformat()
        fields={p.category:p.amount for p in draft.positions if p.category in ('beznal','nal','itog')}
        with closing(self.connect()) as db,db:
            db.execute('BEGIN IMMEDIATE');db.row_factory=sqlite3.Row
            if db.execute('SELECT 1 FROM report_save_tokens WHERE nonce=?',(draft.nonce,)).fetchone():return 'already_saved'
            existing=db.execute('SELECT * FROM daily_reports WHERE report_date=?',(draft.report_date,)).fetchone()
            if draft.file_id and db.execute('SELECT 1 FROM daily_reports WHERE photo_file_id=? AND report_date!=?',(draft.file_id,draft.report_date)).fetchone():return 'duplicate_photo'
            if draft.photo_unique_id and db.execute('SELECT 1 FROM daily_reports WHERE photo_unique_id=? AND report_date!=?',(draft.photo_unique_id,draft.report_date)).fetchone():return 'duplicate_photo'
            if draft.photo_hash and db.execute('SELECT 1 FROM daily_reports WHERE photo_hash=? AND report_date!=?',(draft.photo_hash,draft.report_date)).fetchone():return 'duplicate_photo'
            if existing and not replace:return 'exists'
            if replace and not existing:return 'missing'
            for p in draft.positions:
                if p.category=='employee' and not db.execute('SELECT 1 FROM staff_v3 WHERE id=? AND active=1',(p.employee_id,)).fetchone():raise ValueError('Сотрудник больше недоступен')
            if existing:
                snapshot={'report':dict(existing),'legacy_payouts':[dict(r) for r in db.execute('SELECT * FROM employee_payouts WHERE report_date=?',(draft.report_date,))],
                          'v3_items':[dict(r) for r in db.execute('SELECT * FROM report_items_v3 WHERE report_date=?',(draft.report_date,))],
                          'v3_payouts':[dict(r) for r in db.execute('SELECT * FROM payouts_v3 WHERE report_date=?',(draft.report_date,))]}
                db.execute('INSERT INTO report_revision_details(report_date,snapshot_json,replaced_at) VALUES (?,?,?)',(draft.report_date,json.dumps(snapshot,ensure_ascii=False),now))
                db.execute('INSERT INTO report_history(report_date,beznal,nal,itog,photo_file_id,replaced_at) VALUES (?,?,?,?,?,?)',(draft.report_date,existing['beznal'],existing['nal'],existing['itog'],existing['photo_file_id'],now))
                for table in ('employee_payouts','report_items_v3','payouts_v3','report_amounts_v3'):db.execute(f'DELETE FROM {table} WHERE report_date=?',(draft.report_date,))
                db.execute('DELETE FROM daily_reports WHERE report_date=?',(draft.report_date,))
            v=[sheet_number(fields[k]) if k in fields else None for k in ('beznal','nal','itog')]
            db.execute('INSERT INTO daily_reports(report_date,beznal,nal,itog,telegram_user_id,photo_file_id,created_at,sent_at,updated_at,photo_unique_id,photo_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?)',(draft.report_date,*v,user_id,draft.file_id,now,draft.sent_at,now,draft.photo_unique_id,draft.photo_hash))
            db.execute('INSERT INTO report_amounts_v3 VALUES (?,?,?,?)',(draft.report_date,*(cents(fields[k]) if k in fields else None for k in ('beznal','nal','itog'))))
            for i,p in enumerate(draft.positions):
                if p.category=='ignore':continue
                db.execute('INSERT INTO report_items_v3(report_date,position,terms_json,category,staff_id,source,amount_cents,raw,origin) VALUES (?,?,?,?,?,?,?,?,?)',(draft.report_date,i,json.dumps(p.terms,ensure_ascii=False),p.category,p.employee_id,p.source,cents(p.amount),p.raw,p.origin))
                if p.category=='employee':
                    name=db.execute('SELECT name FROM staff_v3 WHERE id=?',(p.employee_id,)).fetchone()[0]
                    db.execute('INSERT INTO payouts_v3(report_date,staff_id,source,amount_cents,name_at_save) VALUES (?,?,?,?,?)',(draft.report_date,p.employee_id,p.source,cents(p.amount),name))
            db.execute('INSERT INTO report_save_tokens VALUES (?,?)',(draft.nonce,draft.report_date))
            self._dirty(db,'report:'+draft.report_date,draft.nonce)
        return 'saved'
    def get_report(self,day):
        with closing(self.connect()) as db:return db.execute('SELECT report_date,beznal,nal,itog FROM daily_reports WHERE report_date=?',(day,)).fetchone()
    def employee_summaries(self,start,end):
        group=defaultdict(lambda:dict(beznal=Decimal(0),nal=Decimal(0),unknown=Decimal(0)))
        with closing(self.connect()) as db:
            rows=db.execute('SELECT s.name,p.source,p.amount_cents FROM payouts_v3 p JOIN staff_v3 s ON s.id=p.staff_id WHERE p.report_date BETWEEN ? AND ?',(start,end)).fetchall()
            rows += [(name,kind,int(Decimal(str(amount))*100)) for name,kind,amount in db.execute('SELECT COALESCE(s.name,p.employee_code),p.payment_type,p.amount FROM employee_payouts p LEFT JOIN staff_alias_v3 a ON a.alias=p.employee_code LEFT JOIN staff_v3 s ON s.id=a.staff_id WHERE p.report_date BETWEEN ? AND ?',(start,end)).fetchall()]
        for name,kind,amount in rows:
            if kind not in SOURCES:kind='unknown'
            group[name][kind]+=Decimal(amount)/100
        return [dict(name=name,**values,total=sum(values.values(),Decimal(0))) for name,values in sorted(group.items())]
    def all_payouts(self):
        with closing(self.connect()) as db:
            new=db.execute('SELECT p.report_date,s.name,p.source,p.amount_cents FROM payouts_v3 p JOIN staff_v3 s ON s.id=p.staff_id ORDER BY p.report_date,p.id').fetchall()
            old=db.execute('SELECT p.report_date,COALESCE(s.name,p.employee_code),p.payment_type,p.amount FROM employee_payouts p LEFT JOIN staff_alias_v3 a ON a.alias=p.employee_code LEFT JOIN staff_v3 s ON s.id=a.staff_id ORDER BY p.report_date,p.id').fetchall()
        return sorted([(day,name,source,Decimal(amount)/100) for day,name,source,amount in new]+[(day,name,source,Decimal(str(amount))) for day,name,source,amount in old])
    def all_reports(self):
        with closing(self.connect()) as db:return db.execute('SELECT report_date,beznal,nal,itog,beznal_gross,beznal_deductions,nal_gross,nal_deductions FROM daily_reports ORDER BY report_date').fetchall()
    def debts(self):
        with closing(self.connect()) as db:return [(r[0],Decimal(r[1])/100,r[2]) for r in db.execute("SELECT report_date,amount_cents,raw FROM report_items_v3 WHERE category='debt' ORDER BY report_date,position")]
