import yfinance as yf
from app.services.institutional_data import get_latest_institutional_data
from app.services.stock_data import get_yahoo_ticker, get_stocks_realtime
from concurrent.futures import ThreadPoolExecutor

def test_scan():
    print("Loading chips data...")
    chips_data = get_latest_institutional_data()
    print(f"Total chips data records: {len(chips_data)}")
    
    candidates = []
    for code, stats in chips_data.items():
        if stats['trust'] > 100_000:
            candidates.append(code)
            
    print(f"Found {len(candidates)} stocks with trust net buy > 100 lots.")
    
    results = []
    def fetch_and_calculate(code):
        try:
            ticker = get_yahoo_ticker(code)
            info = yf.Ticker(ticker).fast_info
            # fast_info has shares
            shares_out = info.shares
            if not shares_out or shares_out == 0:
                return None
                
            trust_buy_shares = chips_data[code]['trust']
            ratio = (trust_buy_shares / shares_out) * 100
            
            if ratio >= 0.05: # threshold 0.05%
                return {
                    'code': code,
                    'trust_net_buy': trust_buy_shares // 1000,
                    'trust_ratio': round(ratio, 2)
                }
        except Exception as e:
            # print(f"Error {code}: {e}")
            pass
        return None
        
    print("Calculating trust ratios...")
    with ThreadPoolExecutor(max_workers=10) as executor:
        for res in executor.map(fetch_and_calculate, candidates):
            if res:
                results.append(res)
                
    results.sort(key=lambda x: x['trust_ratio'], reverse=True)
    print("Top 5 results:")
    for r in results[:5]:
        print(r)

if __name__ == "__main__":
    test_scan()
