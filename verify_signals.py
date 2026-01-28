import sys
import os

# Add parent directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from app.services.realtime_quotes import get_realtime_quotes
    from app.services.institutional_data import get_latest_institutional_data
    from app.services.breakout_scanner import get_breakout_stocks
    
    print("--- Testing Realtime Quotes ---")
    quotes = get_realtime_quotes(['2330', '2108'])
    print(f"Quotes result: {quotes}")
    
    print("\n--- Testing Institutional Data ---")
    inst = get_latest_institutional_data()
    print(f"Found {len(inst)} stocks with institutional data")
    if '2330' in inst:
        print(f"2330 Inst Data: {inst['2330']}")
        
    print("\n--- Testing Breakout Scanner (Cache Test) ---")
    import time
    start = time.time()
    res1 = get_breakout_stocks(force_refresh=True)
    end1 = time.time()
    print(f"First scan (forced): {end1 - start:.2f}s")
    
    start = time.time()
    res2 = get_breakout_stocks(force_refresh=False)
    end2 = time.time()
    print(f"Second scan (cached): {end2 - start:.2f}s")
    
    if end2 - start < 0.1:
        print("SUCCESS: Cache hit confirmed!")
    else:
        print("WARNING: Cache hit not evident.")

    print(f"Market Status: Hours={res1.get('is_market_hours')}, Pre={res1.get('is_pre_market')}")
    print(f"Found {len(res1.get('stocks', []))} candidates")
    
    for b in res1.get('stocks', [])[:5]:
        diag = ", ".join(b.get('diagnostics', []))
        print(f"- {b['name']} ({b['code']}): {b['reason']} | Diag: [{diag}] | Pos: {b['position_pct']}%")

except Exception as e:
    print(f"Verification failed: {e}")
    import traceback
    traceback.print_exc()
