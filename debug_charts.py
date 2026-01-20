import yfinance as yf
from app.services.stock_data import get_stock_history

def test_intervals():
    stock_code = "2330"
    intervals = ['1d', '1wk', '1mo']
    
    for interval in intervals:
        print(f"--- Testing {interval} ---")
        data = get_stock_history(stock_code, interval)
        print(f"Got {len(data)} records")
        if data:
            print("First record:", data[0])
            print("Last record:", data[-1])
        else:
            # Try raw yfinance to see error
            try:
                ticker = yf.Ticker(f"{stock_code}.TW")
                # map logic from service
                valid_intervals = {'1d': '1d', '1wk': '1wk', '1mo': '1mo'}
                period_map = {'1d': '1y', '1wk': '2y', '1mo': '5y'} 
                
                api_interval = valid_intervals.get(interval, '1d')
                api_period = period_map.get(interval, '1y')
                
                print(f"Raw fetch params: period={api_period}, interval={api_interval}")
                hist = ticker.history(period=api_period, interval=api_interval)
                print("Raw head:\n", hist.head())
                print("Raw tail:\n", hist.tail())
            except Exception as e:
                print(f"Raw Error: {e}")
        print("\n")

if __name__ == "__main__":
    test_intervals()
