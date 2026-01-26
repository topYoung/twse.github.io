import yfinance as yf
import pandas as pd
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor
from .categories import TECH_STOCKS, TRAD_STOCKS, STOCK_SUB_CATEGORIES
import twstock
import urllib.request
import json
import ssl
import time

def fetch_mis_index_data():
    """
    Fetches real-time data from TWSE MIS API for the Weighted Index (tse_t00.tw).
    Returns a dict with processed data or None if failed.
    """
    try:
        # Prevent caching with timestamp
        ts = int(time.time() * 1000)
        url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_t00.tw&json=1&delay=0&_={ts}"
        
        # Bypass SSL verification for this specific request if needed (often needed for TWSE MIS)
        context = ssl._create_unverified_context()
        
        with urllib.request.urlopen(url, context=context, timeout=5) as response:
            data = response.read().decode('utf-8')
            json_data = json.loads(data)
            
            if 'msgArray' in json_data and len(json_data['msgArray']) > 0:
                info = json_data['msgArray'][0]
                
                # 'z' is latest trade price, 'y' is previous close
                # Sometimes 'z' might be '-' if no trade yet, but for index it usually has value during market hours
                price_str = info.get('z', '0')
                prev_close_str = info.get('y', '0')
                
                # Check for validity
                if price_str == '-' or prev_close_str == '-':
                    return None
                    
                current_price = float(price_str)
                prev_close = float(prev_close_str)

                # Fix: If pre-market or error causes price to be 0, return None to trigger fallback
                if current_price <= 0:
                    return None
                
                change = current_price - prev_close
                percent_change = (change / prev_close) * 100 if prev_close != 0 else 0
                
                return {
                    "price": round(current_price, 2),
                    "change": round(change, 2),
                    "percent_change": round(percent_change, 2)
                }
    except Exception as e:
        print(f"Error fetching MIS index: {e}")
        return None
    
    return None

def get_market_index():
    """Fetches the current real-time data for Taiwan Weighted Index."""
    # 1. Try Real-time MIS API first
    mis_data = fetch_mis_index_data()
    if mis_data:
        return mis_data

    # 2. Fallback to yfinance (Delayed)
    try:
        ticker = yf.Ticker("^TWII")
        
        # Use history to get the actual data which is often more up-to-date than fast_info
        # Fetch 5 days to ensure we have previous day even after weekends
        hist = ticker.history(period="5d")
        
        if hist.empty:
             # Fallback
             return {"price": 0, "change": 0, "percent_change": 0}

        # Current is the last row
        current_price = hist['Close'].iloc[-1]
        
        # Previous close
        # If we have at least 2 days, use the 2nd to last close
        if len(hist) >= 2:
            prev_close = hist['Close'].iloc[-2]
        else:
            # Fallback to metadata if history is too short (rare)
            prev_close = ticker.info.get('previousClose', current_price)
        
        change = current_price - prev_close
        percent_change = (change / prev_close) * 100 if prev_close != 0 else 0
        
        return {
            "price": round(current_price, 2),
            "change": round(change, 2),
            "percent_change": round(percent_change, 2)
        }
    except Exception as e:
        print(f"Error fetching index: {e}")
        return {"price": 0, "change": 0, "percent_change": 0}

def calculate_ma(hist_data, window=20):
    return hist_data['Close'].rolling(window=window).mean().iloc[-1]

def get_yahoo_ticker(stock_code):
    """
    Returns the Yahoo Finance ticker symbol for a given stock code.
    Taipei Exchange (OTC) stocks need .TWO suffix.
    Taiwan Stock Exchange (TWSE) stocks need .TW suffix.
    """
    try:
        if stock_code in twstock.codes:
            info = twstock.codes[stock_code]
            if info.market == '上櫃':
                return f"{stock_code}.TWO"
    except Exception:
        pass
    
    # Default to .TW for '上市' or unknown
    return f"{stock_code}.TW"

def process_stock(stock_code):
    """
    Fetches data for a single stock and checks if it's near MA.
    Returns dict if valid, None otherwise.
    """
    try:
        ticker_symbol = get_yahoo_ticker(stock_code)
        ticker = yf.Ticker(ticker_symbol)
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
    period_map = {'1d': '3y', '1wk': '5y', '1mo': '10y'} # Increased to 3y for denser view
    
    api_interval = valid_intervals.get(interval, '1d')
    api_period = period_map.get(interval, '1y')
    
    try:
        ticker_symbol = get_yahoo_ticker(stock_code)
        ticker = yf.Ticker(ticker_symbol)
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
        
        # Get stock info (name and category)
        stock_name = stock_code
        category = '其他'
        
        # Try to resolve Chinese name and category
        if stock_code in twstock.codes:
            info = twstock.codes[stock_code]
            stock_name = info.name
            if info.group:
                category = info.group.replace('業', '')
        
        # Check sub-categories override
        if stock_code in STOCK_SUB_CATEGORIES:
             category = STOCK_SUB_CATEGORIES[stock_code]

        return {
            "info": {
                "name": stock_name,
                "category": category
            },
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

def search_stock_code(query: str):
    """
    Search stock by code or name using twstock.
    Returns {code, name} or None.
    """
    query = query.strip()
    
    # 1. Direct Code Match
    if query in twstock.codes:
        info = twstock.codes[query]
        return {"code": info.code, "name": info.name}
        
    # 2. Name Match (Iterate all)
    # This is slightly heavy but twstock.codes is not huge (~2000 items)
    for code, info in twstock.codes.items():
        if info.name == query:
             return {"code": info.code, "name": info.name}
             
    # 3. Partial Name Match (optional, pick first)
    # for code, info in twstock.codes.items():
    #    if query in info.name:
    #         return {"code": info.code, "name": info.name}
             
    return None

