import yfinance as yf
try:
    print("Fetching ^TWII...")
    ticker = yf.Ticker("^TWII")
    print(f"Info: {ticker.fast_info.last_price}")
    
    print("Fetching 2330.TW...")
    stock = yf.Ticker("2330.TW")
    hist = stock.history(period="5d")
    print(hist.tail())
except Exception as e:
    print(f"Error: {e}")
