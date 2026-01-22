import yfinance as yf
import time

def test_index():
    print("Fetching ^TWII info...")
    ticker = yf.Ticker("^TWII")
    
    print(f"Fast Info Last Price: {ticker.fast_info.last_price}")
    print(f"Fast Info Previous Close: {ticker.fast_info.previous_close}")
    
    # Try fetching history 1d
    hist = ticker.history(period="1d")
    if not hist.empty:
        print(f"History Last Close: {hist['Close'].iloc[-1]}")
        print(f"History Last Price (High/Low/Open): {hist.iloc[-1]}")
    else:
        print("History is empty")

test_index()
