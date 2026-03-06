import asyncio
from app.services.stock_data import get_filtered_stocks, get_stock_history_bulk, get_stocks_realtime
from app.services.macd_scanner import get_macd_breakout_stocks

async def main():
    res = get_macd_breakout_stocks()
    print(f"Total found: {len(res)}")
    for r in res[:5]:
        print(r)

if __name__ == "__main__":
    asyncio.run(main())
