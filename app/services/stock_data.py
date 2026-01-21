import yfinance as yf
import pandas as pd
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor
from .categories import TECH_STOCKS, TRAD_STOCKS, STOCK_SUB_CATEGORIES
import twstock

def get_market_index():
    """Fetches the current real-time data for Taiwan Weighted Index."""
    try:
        # ^TWII is the ticker for Taiwan Weighted Index
        valid_tickers = ['^TWII'] 
        ticker = yf.Ticker("^TWII")
        # Get fast info first if possible, or Today's data
        # 'regularMarketPrice' is often in fast_info
        
        # fast_info is newer and faster in yfinance
        price = ticker.fast_info.last_price
        prev_close = ticker.fast_info.previous_close
        
        change = price - prev_close
        percent_change = (change / prev_close) * 100
        
        return {
            "price": round(price, 2),
            "change": round(change, 2),
            "percent_change": round(percent_change, 2)
        }
    except Exception as e:
        print(f"Error fetching index: {e}")
        return {"price": 0, "change": 0, "percent_change": 0}

def calculate_ma(hist_data, window=20):
    return hist_data['Close'].rolling(window=window).mean().iloc[-1]

def process_stock(stock_code):
    """
    Fetches data for a single stock and checks if it's near MA.
    Returns dict if valid, None otherwise.
    """
    try:
        ticker = yf.Ticker(f"{stock_code}.TW")
        # specific period=2mo to get enough data for MA20 or MA60
        hist = ticker.history(period="3mo")
        
        if len(hist) < 60:
            return None
            
        current_price = hist['Close'].iloc[-1]
        
        # Calculate MA20 (Monthly trend line roughly) or MA60 (Quarterly)
        ma20 = hist['Close'].rolling(window=20).mean().iloc[-1]
        
        if pd.isna(ma20):
            return None

        # Calculate proximity: within 3% range?
        diff_percent = abs((current_price - ma20) / ma20) * 100
        
        if diff_percent <= 3.0: 
            # Get last 15 points for sparkline
            sparkline_data = hist['Close'].tail(15).tolist()
            
            # Fetch Chinese Name and Industry Group
            stock_name = stock_code # default
            industry_group = '其他'
            
            # 1. Check Sub-category Map first
            if stock_code in STOCK_SUB_CATEGORIES:
                industry_group = STOCK_SUB_CATEGORIES[stock_code]
                # Also try to get name from twstock if possible
                if stock_code in twstock.codes:
                    stock_name = twstock.codes[stock_code].name
            
            # 2. Fallback to twstock group
            elif stock_code in twstock.codes:
                unique_code_info = twstock.codes[stock_code]
                stock_name = unique_code_info.name
                if unique_code_info.group:
                    industry_group = unique_code_info.group.replace('業', '') # Remove suffix
                else:
                    industry_group = '其他'

            return {
                "code": stock_code,
                "name": stock_name,
                "category": industry_group,
                "price": round(current_price, 2),
                "ma20": round(ma20, 2),
                "diff_percent": round(diff_percent, 2),
                "change": round(current_price - hist['Close'].iloc[-2], 2),
                "sparkline": sparkline_data
            }
        return None
        
    except Exception as e:
        return None

def get_filtered_stocks():
    """
    Returns ALL stocks within range, sorted by proximity.
    Grouped by industry is handled in frontend.
    """
    results = []
    
    # Combined list of all monitored stocks
    # Using Sub-categories keys if exists to ensure we cover them? 
    # Actually categories.py lists are just subsets. 
    # We should probably ensure we scan STOCK_SUB_CATEGORIES keys as well if they are not in TECH/TRAD?
    # But for now assuming TECH/TRAD covers most. 
    # Let's verify if we need to add keys from STOCK_SUB_CATEGORIES to all_stocks
    
    # Merge lists
    keys_from_map = list(STOCK_SUB_CATEGORIES.keys())
    all_stocks = list(set(TECH_STOCKS + TRAD_STOCKS + keys_from_map))
    
    # Increase workers to speed up fetching
    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = [executor.submit(process_stock, code) for code in all_stocks]
        for future in futures:
            res = future.result()
            if res:
                results.append(res)
                
    # Sort by 'proximity' (diff_percent) ascending
    results.sort(key=lambda x: x['diff_percent'])
    
    return results

def get_stock_history(stock_code, interval='1d'):
    """
    Fetch history for charts.
    interval: 1d, 1wk, 1mo
    """
    valid_intervals = {'1d': '1d', '1wk': '1wk', '1mo': '1mo'}
    period_map = {'1d': '1y', '1wk': '2y', '1mo': '5y'} # Enough data for charts
    
    api_interval = valid_intervals.get(interval, '1d')
    api_period = period_map.get(interval, '1y')
    
    try:
        ticker = yf.Ticker(f"{stock_code}.TW")
        hist = ticker.history(period=api_period, interval=api_interval)
        
        # Calculate Moving Averages
        hist['MA5'] = hist['Close'].rolling(window=5).mean()
        hist['MA10'] = hist['Close'].rolling(window=10).mean()
        hist['MA20'] = hist['Close'].rolling(window=20).mean()
        hist['MA60'] = hist['Close'].rolling(window=60).mean()
        
        # Format for Lightweight Charts: { time: '2019-04-11', open: 80.01, high: 96.63, low: 76.6, close: 80.29 }
        candlestick_data = []
        ma5_data = []
        ma10_data = []
        ma20_data = []
        ma60_data = []
        
        for date, row in hist.iterrows():
            # Check for NaNs
            if pd.isna(row['Open']) or pd.isna(row['Close']):
                continue
                
            time_str = date.strftime('%Y-%m-%d')
            
            # Candlestick data
            candlestick_data.append({
                "time": time_str,
                "open": float(row['Open']),
                "high": float(row['High']),
                "low": float(row['Low']),
                "close": float(row['Close']),
                "volume": int(row['Volume'])
            })
            
            # MA data (only if not NaN)
            if not pd.isna(row['MA5']):
                ma5_data.append({"time": time_str, "value": float(row['MA5'])})
            if not pd.isna(row['MA10']):
                ma10_data.append({"time": time_str, "value": float(row['MA10'])})
            if not pd.isna(row['MA20']):
                ma20_data.append({"time": time_str, "value": float(row['MA20'])})
            if not pd.isna(row['MA60']):
                ma60_data.append({"time": time_str, "value": float(row['MA60'])})
        
        return {
            "candlestick": candlestick_data,
            "ma5": ma5_data,
            "ma10": ma10_data,
            "ma20": ma20_data,
            "ma60": ma60_data
        }
    except Exception as e:
        print(f"Error history {stock_code}: {e}")
        return {
            "candlestick": [],
            "ma5": [],
            "ma10": [],
            "ma20": [],
            "ma60": []
        }

