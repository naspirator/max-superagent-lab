import os

import requests
from dotenv import load_dotenv

load_dotenv(r"E:\MAX-FINANCE-TEST\prod-src\max-finance-stage\.env")
token = os.getenv("TELEGRAM_BOT_TOKEN")
response = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=30)
data = response.json()
print("HTTP", response.status_code, "OK", data.get("ok"))
if data.get("ok"):
    bot = data["result"]
    print("BOT_ID", bot.get("id"), "USERNAME", bot.get("username"), "NAME", bot.get("first_name"))
else:
    print("ERROR", data.get("description"))
