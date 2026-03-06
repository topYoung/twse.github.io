import yfinance as yf
from app.services.categories import TECH_STOCKS, TRAD_STOCKS, STOCK_SUB_CATEGORIES, DELISTED_STOCKS
from app.services.stock_data import get_yahoo_ticker

keys_from_map = list(STOCK_SUB_CATEGORIES.keys())
all_stock_codes = list(set(TECH_STOCKS + TRAD_STOCKS + keys_from_map))
stock_codes = [s for s in all_stock_codes if s not in DELISTED_STOCKS][:20]

yahoo_tickers = [get_yahoo_ticker(code) for code in stock_codes]
bulk_data = yf.download(yahoo_tickers, period='60d', interval='1d', group_by='ticker', threads=True, progress=False)

print(f"Downloaded shape: {bulk_data.shape}")
code = stock_codes[0]
ticker = yahoo_tickers[0]
if ticker in bulk_data.columns.levels[0]:
    df = bulk_data[ticker].dropna(subset=['Close'])
    print(f"{ticker} data points: {len(df)}")
    if len(df) > 0:
        print(f"Sample close price: {df['Close'].iloc[-1]}")
