import asyncio
from app.services.macd_scanner import get_macd_breakout_stocks

async def main():
    try:
        res = get_macd_breakout_stocks()
        print(f"Total found: {len(res)}")
        for r in res[:5]:
            print(r)
    except Exception as e:
        print(f"Error test api: {e}")

if __name__ == "__main__":
    asyncio.run(main())
