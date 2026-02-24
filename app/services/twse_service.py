
import requests
import json
from datetime import datetime, timedelta
import ssl
import urllib.request

TWSE_EX_DIVIDEND_URL = "https://www.twse.com.tw/rwd/zh/exRight/TWT48U"

def parse_roc_date(roc_date_str):
    """
    Parses a ROC date string like "115年02月09日" or "115年02月09日(some link)" to a datetime object.
    Returns datetime object or None if parsing fails.
    """
    try:
        # Remove potential link content in brackets or parentheses
        if '(' in roc_date_str:
            roc_date_str = roc_date_str.split('(')[0]
        
        # Simple parsing for "YYY年MM月DD日"
        date_part = roc_date_str.replace('年', '-').replace('月', '-').replace('日', '')
        parts = date_part.split('-')
        
        if len(parts) >= 3:
            year = int(parts[0]) + 1911
            month = int(parts[1])
            day = int(parts[2])
            return datetime(year, month, day)
            
    except Exception as e:
        print(f"Error parsing date {roc_date_str}: {e}")
    
    return None

def fetch_ex_dividend_stocks(days=30):
    """
    Fetches ex-dividend stocks from TWSE for the next `days` days.
    """
    try:
        # Use requests to fetch the JSON data
        response = requests.get(TWSE_EX_DIVIDEND_URL, timeout=10)
        
        if response.status_code != 200:
            print(f"Failed to fetch TWSE data: Status {response.status_code}")
            return []
            
        json_data = response.json()
        
        if 'data' not in json_data:
            return []
            
        results = []
        today = datetime.now()
        target_date = today + timedelta(days=days)
        
        # Data format example from TWSE:
        # [
        #   "115年02月09日",  # Date (0)
        #   "2338",           # Code (1)
        #   "光罩",           # Name (2)
        #   "權",             # Type (3)
        #   "0.00000000",     # Cash Dividend (4)
        #   "0.18048408",     # Stock Dividend (5)
        #   ...
        # ]
        
        for row in json_data['data']:
            if len(row) < 6:
                continue
                
            raw_date = row[0]
            code = row[1]
            name = row[2]
            div_type = row[3]
            
            # Parse Date
            ex_date = parse_roc_date(raw_date)
            
            if ex_date:
                # Filter by date range (Today <= ExDate <= TargetDate)
                # We also include today in case there are records for today
                if today.date() <= ex_date.date() <= target_date.date():
                    
                    # Clean up dividend values
                    try:
                        cash_div = float(row[4].replace(',', ''))
                    except:
                        cash_div = 0.0
                        
                    try:
                        stock_div = float(row[5].replace(',', ''))
                    except:
                        stock_div = 0.0
                    
                    results.append({
                        "date": ex_date.strftime('%Y-%m-%d'),
                        "code": code,
                        "name": name,
                        "type": div_type,
                        "cash_dividend": cash_div,
                        "stock_dividend": stock_div,
                        "raw_date": raw_date
                    })
        
        # Sort by date
        results.sort(key=lambda x: x['date'])
        
        return results

    except Exception as e:
        print(f"Error fetching ex-dividend stocks: {e}")
        return []

if __name__ == "__main__":
    # Test only
    stocks = fetch_ex_dividend_stocks()
    print(f"Found {len(stocks)} stocks:")
    for stock in stocks:
        print(stock)
