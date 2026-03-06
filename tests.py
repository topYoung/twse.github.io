"""
import asyncio
from app.services.macd_scanner import get_macd_breakout_stocks

async def test():
    res = get_macd_breakout_stocks()
    print(res[:2])

asyncio.run(test())
"""
