import asyncio
import os
import sys

from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv(r"E:\MAX-FINANCE-TEST\prod-src\max-finance-stage\.env")
key = os.getenv("VSEGPT_API_KEY")
print("key_present", bool(key))


async def main():
    client = AsyncOpenAI(api_key=key, base_url="https://api.vsegpt.ru/v1", timeout=60, max_retries=0)
    response = await client.chat.completions.create(
        model="vis-google/gemini-2.5-flash",
        messages=[{"role": "user", "content": "Ответь одним словом: работает"}],
        max_tokens=10,
        temperature=0,
    )
    print("RESP", repr(response.choices[0].message.content), response.choices[0].finish_reason)
    await client.close()


try:
    asyncio.run(main())
except Exception as exc:
    print("ERROR", type(exc).__name__, str(exc)[:500])
    sys.exit(1)
