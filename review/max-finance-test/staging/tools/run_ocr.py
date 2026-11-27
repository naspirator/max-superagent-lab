import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI

sys.path.insert(0, r"E:\MAX-FINANCE-TEST\staging")
from maxfinance_test.aliases import AliasBook, DEFAULT_ALIASES
from maxfinance_test.ocr import recognize
from maxfinance_test.store import ModeStore

BOUNDARIES = {
    "20260912_192015.jpg": 0.615,
    "20261121_205236.jpg": 0.585,
    "20261122_211228.jpg": 0.565,
    "20261123_211146.jpg": 0.770,
    "20261125_214435.jpg": 0.730,
    "20261126_210217.jpg": 0.600,
}

load_dotenv(r"E:\MAX-FINANCE-TEST\prod-src\max-finance-stage\.env")


async def main():
    store = ModeStore(r"E:\MAX-FINANCE-TEST\runtime-test-mode")
    store.initialize()
    book = store.alias_book()
    client = AsyncOpenAI(api_key=os.getenv("VSEGPT_API_KEY"), base_url="https://api.vsegpt.ru/v1",
                         timeout=180, max_retries=0)
    for name in sys.argv[1:]:
        data = (Path(r"E:\MAX-FINANCE-TEST\testdata") / name).read_bytes()
        y = BOUNDARIES[name]
        report = await recognize(client, data, (y, y), book)
        print("=" * 70)
        print(name, "boundary", y, "engine", report.engine_version)
        print("warnings:", report.warnings)
        for item in report.items:
            print(
                f"  {item.category or '-':9} {format(item.amount, 'f'):>9} "
                f"src={item.source or '-':7} alias={item.alias!r:8} "
                f"unc={item.uncertain} struck={item.struck} raw={item.raw[:80]!r} note={item.note[:60]!r}"
            )
    await client.close()


asyncio.run(main())
