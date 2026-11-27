import os
import sys

from dotenv import load_dotenv
import gspread

BASE = r"E:\MAX-FINANCE-TEST\prod-src\max-finance-stage"
load_dotenv(os.path.join(BASE, ".env"))
sheet_id = os.getenv("GOOGLE_SHEET_ID")
print("sheet_id_present", bool(sheet_id))
try:
    book = gspread.service_account(filename=os.path.join(BASE, "google_credentials.json")).open_by_key(sheet_id)
    print("SPREADSHEET_OK", book.title)
    for worksheet in book.worksheets():
        values = worksheet.get_all_values()
        print("SHEET", worksheet.title, "rows", len(values), "header", values[0][:8] if values else [])
except Exception as exc:
    print("SPREADSHEET_ERROR", type(exc).__name__, str(exc)[:500])
    sys.exit(1)
