import asyncio
from app.services.macd_scanner import get_macd_breakout_stocks

async def main():
    res = get_macd_breakout_stocks()
    print(f"Total found: {len(res)}")
    for r in res[:2]:
        print(r)

if __name__ == "__main__":
    asyncio.run(main())
