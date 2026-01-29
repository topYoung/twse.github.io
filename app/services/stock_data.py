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
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://mis.twse.com.tw/stock/fibest.jsp?stock=2330",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest"
        }
        
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, context=context, timeout=5) as response:
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
        
        # === 盤中即時數據整合 (僅針對日線 1d) ===
        if interval == '1d':
            from datetime import datetime
            now = datetime.now()
            # 判斷是否為盤中 (09:00 - 13:30)
            is_market_hours = (9 <= now.hour < 14) and now.weekday() < 5
            
            if is_market_hours:
                try:
                    from app.services.realtime_quotes import get_intraday_candle
                    intraday = get_intraday_candle(stock_code)
                    
                    if intraday and intraday['volume'] > 0:
                        today_ts = pd.Timestamp.now().normalize()
                        
                        # 檢查歷史數據最後一筆日期
                        last_date = pd.NaT
                        if not hist.empty:
                            last_date = hist.index[-1].normalize()
                        
                        today_row = pd.Series({
                            'Open': intraday['open'],
                            'High': intraday['high'],
                            'Low': intraday['low'],
                            'Close': intraday['close'],
                            'Volume': intraday['volume']
                        }, name=today_ts)
                        
                        if not hist.empty and last_date == today_ts:
                            # 如果 Yahoo 已經有今日數據，用即時數據覆蓋 (通常即時數據更準)
                            hist.iloc[-1] = today_row
                            # 重新計算因為覆蓋而可能變動的指標 (雖然這裡還沒算 MA)
                        else:
                            # 附加今日數據
                            hist = pd.concat([hist, pd.DataFrame([today_row])])
                            
                        # 確保索引排序
                        hist.sort_index(inplace=True)
                except Exception as e:
                    print(f"Error merging intraday data for {stock_code}: {e}")
                    pass

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

from typing import List, Dict

def search_stock_code(query: str, limit: int = 10) -> List[Dict]:
    """
    Search stock by code or name using twstock.
    Supports fuzzy matching for partial name search.
    Returns list of {code, name} or empty list.
    
    Args:
        query: Search keyword (code or name)
        limit: Maximum number of results to return
    """
    query = query.strip().upper()
    results = []
    
    if not query:
        return results
    
    # 1. Exact Code Match (highest priority)
    if query in twstock.codes:
        info = twstock.codes[query]
        results.append({"code": info.code, "name": info.name})
        return results
    
    # 2. Exact Name Match
    for code, info in twstock.codes.items():
        if info.name == query:
            results.append({"code": info.code, "name": info.name})
            if len(results) >= limit:
                break
    
    if results:
        return results
    
    # 3. Partial Code Match (code starts with query)
    for code, info in twstock.codes.items():
        if code.startswith(query):
            results.append({"code": info.code, "name": info.name})
            if len(results) >= limit:
                break
    
    # 4. Partial Name Match (name contains query)
    if len(results) < limit:
        for code, info in twstock.codes.items():
            if query in info.name:
                # Avoid duplicates
                if not any(r['code'] == code for r in results):
                    results.append({"code": info.code, "name": info.name})
                    if len(results) >= limit:
                        break
    
    return results


def get_stocks_realtime(stock_codes: List[str]) -> List[Dict]:
    """
    Batch fetch real-time data for multiple stocks.
    Uses TWSE MIS API for real-time quotes during market hours.
    
    Args:
        stock_codes: List of stock codes (e.g. ['2330', '2454'])
        
    Returns:
        List of stock data dicts with real-time information
    """
    results = []
    
    try:
        from app.services.realtime_quotes import get_realtime_quote
        from datetime import datetime
        
        now = datetime.now()
        is_market_hours = (9 <= now.hour < 14) and now.weekday() < 5
        
        for code in stock_codes:
            try:
                # Get stock name
                stock_name = code
                if code in twstock.codes:
                    stock_name = twstock.codes[code].name
                
                # Get real-time data if market is open
                if is_market_hours:
                    quote = get_realtime_quote(code)
                    if quote and quote.get('close'):
                        results.append({
                            'code': code,
                            'name': stock_name,
                            'price': float(quote.get('close', 0)),
                            'change': float(quote.get('change', 0)),
                            'change_percent': float(quote.get('change_percent', 0)),
                            'volume': int(quote.get('volume', 0)),
                            'bid_ask_ratio': float(quote.get('bid_ask_ratio', 0)),
                            'high': float(quote.get('high', 0)),
                            'low': float(quote.get('low', 0)),
                            'open': float(quote.get('open', 0))
                        })
                        continue
                
                # Fallback to yfinance for non-market hours or if MIS fails
                ticker_symbol = get_yahoo_ticker(code)
                ticker = yf.Ticker(ticker_symbol)
                hist = ticker.history(period='5d')
                
                if not hist.empty:
                    current = hist.iloc[-1]
                    prev = hist.iloc[-2] if len(hist) >= 2 else current
                    
                    results.append({
                        'code': code,
                        'name': stock_name,
                        'price': float(current['Close']),
                        'change': float(current['Close'] - prev['Close']),
                        'change_percent': float((current['Close'] - prev['Close']) / prev['Close'] * 100) if prev['Close'] != 0 else 0,
                        'volume': int(current['Volume']),
                        'bid_ask_ratio': 0,  # Not available from yfinance
                        'high': float(current['High']),
                        'low': float(current['Low']),
                        'open': float(current['Open'])
                    })
            except Exception as e:
                print(f"Error fetching data for {code}: {e}")
                continue
    
    except Exception as e:
        print(f"Error in get_stocks_realtime: {e}")
    
    return results
