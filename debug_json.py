import yfinance as yf
from app.services.stock_data import get_stock_history
import json
import numpy as np

def test_serialization():
    stock_code = "2330"
    data = get_stock_history(stock_code, '1d')
    try:
        json_str = json.dumps(data)
        print("Serialization Successful")
    except TypeError as e:
        print(f"Serialization Failed: {e}")
        # Check types
        if data:
            print("Type of open:", type(data[0]['open']))

if __name__ == "__main__":
    test_serialization()
