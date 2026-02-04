
import sys
import os
import json
import time

sys.path.append(os.getcwd())

try:
    from app.services.divergence_scanner import get_divergence_stocks
    
    print("--- Testing Divergence Scanner (Refined) ---")
    print("Conditions: 5 days, Min Net Buy 100 sheets, Max Price Change 1.0%\n")
    
    start_time = time.time()
    # Test with new default parameters logic (using explicit args here to be sure)
    results = get_divergence_stocks(days=5, min_net_buy=100, max_price_change=1.0)
    end_time = time.time()
    
    print(f"\nExecution Time: {end_time - start_time:.2f} seconds")
    print(f"Found {len(results)} stocks\n")
    
    if results:
        print(f"{'Code':<8} {'Name':<10} {'Price':<8} {'Change%':<8} {'Net Buy(Sheet)':<15} {'Main Investor'}")
        print("-" * 70)
        
        for stock in results[:10]: # Show top 10
            details = stock['details']
            main_inv = max(details, key=details.get)
            print(f"{stock['code']:<8} {stock['name']:<10} {stock['price']:<8} {stock['price_change_pct']:<8} {stock['total_net']/1000:<15.0f} {main_inv}")
            
    else:
        print("No stocks found matching the criteria.")

except Exception as e:
    print(f"ERROR: {e}")
