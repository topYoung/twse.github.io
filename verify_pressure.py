
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from app.services.pressure_scanner import check_pressure_reduction, get_pressure_stocks
import pandas as pd

print("Testing check_pressure_reduction...")

# Test a known stock code (e.g., TSMC 2330, but we need one that might fit, or we just check if it runs without error)
# Since market conditions change, we can't guarantee a hit, but we can check if it returns valid structure or None.

results = get_pressure_stocks(min_days=2, force_refresh=True)

print(f"Scanned {len(results)} stocks matching the criteria.")

if results:
    print("Top 3 results:")
    for stock in results[:3]:
        print(stock)
else:
    print("No stocks found matching criteria (this is possible depending on market conditions).")
