import twstock
import yfinance as yf
import time
import pandas as pd

def get_all_stock_codes():
    # Get all stocks from twstock
    # codes is a dict: filter for stocks only
    all_codes = []
    
    for code, info in twstock.codes.items():
        # type 股票: '股票', type ETF: 'ETF', etc.
        # We only want '股票' and market '上市' or '上櫃'
        if info.type == '股票': 
            suffix = '.TW' if info.market == '上市' else '.TWO'
            all_codes.append(f"{code}{suffix}")
            
    return all_codes

try:
    print("--- 1. Getting Stock List ---")
    start_time = time.time()
    all_stocks = get_all_stock_codes()
    print(f"Total Common Stocks found: {len(all_stocks)}")
    print(f"Sample: {all_stocks[:5]}")
    
    # Test batch download for 100 stocks
    test_batch = all_stocks[:100]
    print(f"\n--- 2. Testing Batch Download for {len(test_batch)} stocks ---")
    t0 = time.time()
    
    # threads=True uses multi-threading
    data = yf.download(test_batch, period="1mo", interval="1d", threads=True, progress=False)
    
    dt = time.time() - t0
    print(f"Time taken: {dt:.2f} seconds")
    print(f"Data shape: {data.shape}")
    
    # Check data integrity (Accessing 'Close' for one stock)
    # yfinance multi-index columns: (Price, Ticker)
    sample_ticker = test_batch[0]
    # Check if we can access data easily
    try:
        # Handling multi-level columns in newer yfinance
        # Usually it's data['Close'][ticker]
        close_prices = data['Close']
        print(f"Close prices shape: {close_prices.shape}")
        
    except Exception as e:
        print(f"Data access error: {e}")

    # Estimate full scan time
    est_time = (len(all_stocks) / 100) * dt
    print(f"\nEstimated time for {len(all_stocks)} stocks: {est_time:.2f} seconds (Linear extrapolation)")
    print("Note: Batch size can be larger (e.g. 1000), which might be faster per stock.")

except Exception as e:
    print(f"Error: {e}")
