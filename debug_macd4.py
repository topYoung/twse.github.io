import asyncio
from app.services.macd_scanner import get_macd_breakout_stocks
from app.services.categories import TECH_STOCKS, TRAD_STOCKS, STOCK_SUB_CATEGORIES, DELISTED_STOCKS

keys_from_map = list(STOCK_SUB_CATEGORIES.keys())
all_stock_codes = list(set(TECH_STOCKS + TRAD_STOCKS + keys_from_map))
stock_codes = [s for s in all_stock_codes if s not in DELISTED_STOCKS]
print(f"Total stocks to scan: {len(stock_codes)}")

