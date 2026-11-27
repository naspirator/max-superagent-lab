import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI

sys.path.insert(0, r"E:\MAX-FINANCE-TEST\staging")
from maxfinance_test.ocr import propose_boundary

load_dotenv(r"E:\MAX-FINANCE-TEST\prod-src\max-finance-stage\.env")


async def main():
    client = AsyncOpenAI(
        api_key=os.getenv("VSEGPT_API_KEY"),
        base_url="https://api.vsegpt.ru/v1",
        timeout=120,
        max_retries=0,
    )
    for name in sys.argv[1:]:
        data = (Path(r"E:\MAX-FINANCE-TEST\testdata") / name).read_bytes()
        y = await propose_boundary(client, data)
        print(name, y)
    await client.close()


asyncio.run(main())
