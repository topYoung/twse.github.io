import yfinance as yf

def check_market():
    ticker = yf.Ticker("^TWII")
    # forcing no cache
    hist = ticker.history(period="5d", interval="1d")
    print("Recent history:")
    print(hist.tail())
    
    info = ticker.fast_info
    print(f"\nLast Price: {info.last_price}")
    print(f"Previous Close: {info.previous_close}")
    change = info.last_price - info.previous_close
    print(f"Calculated Change: {change}")

if __name__ == "__main__":
    check_market()
