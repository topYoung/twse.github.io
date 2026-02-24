
import yfinance as yf
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
from .categories import TECH_STOCKS, TRAD_STOCKS, STOCK_SUB_CATEGORIES
from .stock_data import get_yahoo_ticker
from .institutional_data import get_latest_institutional_data
import threading
import time
from datetime import datetime

# Global Cache
_pressure_cache = {
    "data": [],
    "last_update": 0
}
_cache_lock = threading.Lock()

def check_pressure_reduction(stock_code, min_days=2):
    """
    檢查股票是否連跌但賣壓變小 (上影線變短或消失)
    
    Args:
        stock_code: 股票代碼
        min_days: 最小連跌天數
        
    Returns:
        dict or None: 符合條件則回傳股票資訊，否則 None
    """
    try:
        ticker_symbol = get_yahoo_ticker(stock_code)
        ticker = yf.Ticker(ticker_symbol)
        hist = ticker.history(period="1mo")
        
        if len(hist) < min_days + 1:
            return None
            
        # 取得最新收盤價
        current_price = hist['Close'].iloc[-1]
        
        # 過濾成交量：平均大於 500 張
        avg_volume = hist['Volume'].tail(5).mean()
        if avg_volume < 500 * 1000:
            return None

        # 資料準備
        closes = hist['Close'].tolist()
        opens = hist['Open'].tolist()
        highs = hist['High'].tolist()
        
        # 1. 檢查連跌
        # CHECK: 從最後一天往前，每天收盤價都比前一天低
        consecutive_drop_days = 0
        for i in range(len(closes) - 1, 0, -1):
            if closes[i] < closes[i-1]:
                consecutive_drop_days += 1
            else:
                break
                
        if consecutive_drop_days < min_days:
            # 2. 檢查短期大跌 (3天跌 10%以上)
            # 取最近 4 筆資料 (包含今天與 3 天前)
            if len(closes) >= 4:
                price_3_days_ago = closes[-4]
                total_drop_3d = (closes[-1] - price_3_days_ago) / price_3_days_ago
                if total_drop_3d > -0.10: # 沒跌超過 10%
                    return None
                is_sharp_drop = True
            else:
                return None
        else:
            is_sharp_drop = False

        # 3. 檢查賣壓 (上影線)
        # 邏輯：檢查「今天」的上影線是否比「昨天」短，或是今天幾乎沒有上影線
        today_idx = -1
        yesterday_idx = -2
        
        def get_upper_shadow(idx):
            # Upper Shadow = High - Max(Open, Close)
            body_top = max(opens[idx], closes[idx])
            return highs[idx] - body_top

        today_shadow = get_upper_shadow(today_idx)
        yesterday_shadow = get_upper_shadow(yesterday_idx)
        
        # 判斷條件：
        # A. 今天上影線 < 昨天上影線 (賣壓減弱)
        # OR
        # B. 今天上影線非常短 (幾乎無賣壓)
        
        # 計算上影線佔比 (相對於股價)
        today_shadow_ratio = today_shadow / closes[today_idx]
        
        is_pressure_reduced = (today_shadow < yesterday_shadow)
        is_no_pressure = (today_shadow_ratio < 0.003) # 0.3% 以內視為幾乎無上影線
        
        if not (is_pressure_reduced or is_no_pressure):
            return None
            
        # 準備回傳資料
        stock_name = stock_code
        category = '其他'
        if stock_code in STOCK_SUB_CATEGORIES:
            category = STOCK_SUB_CATEGORIES[stock_code]
            
        change = closes[-1] - closes[-2]
        change_pct = (change / closes[-2]) * 100
        
        tags = []
        if consecutive_drop_days >= min_days:
            tags.append(f"📉連跌{consecutive_drop_days}天")
        
        # 這裡檢查 is_sharp_drop 變數 (假設在上面定義)
        if 'is_sharp_drop' in locals() and is_sharp_drop:
            tags.append("💥短期大跌")

        if is_no_pressure:
            tags.append("✨賣壓消失")
        elif is_pressure_reduced:
            tags.append("🛡️賣壓減輕")

        return {
            "code": stock_code,
            "name": stock_name,
            "category": category,
            "price": round(current_price, 2),
            "change": round(change, 2),
            "change_percent": round(change_pct, 2),
            "volume": int(hist['Volume'].iloc[-1]),
            "consecutive_drop_days": consecutive_drop_days,
            "is_sharp_drop": is_sharp_drop if 'is_sharp_drop' in locals() else False,
            "today_shadow_ratio": round(today_shadow_ratio * 100, 2),
            "tags": tags
        }


    except Exception as e:
        return None

def get_pressure_stocks(min_days=2, force_refresh=False):
    """
    掃描賣壓減輕股票
    """
    global _pressure_cache
    
    now = datetime.now()
    current_time = time.time()
    
    is_market_hours = (9 <= now.hour < 14) and now.weekday() < 5
    
    if is_market_hours:
        cache_duration = 300 
    else:
        cache_duration = 3600
        
    with _cache_lock:
        last_ts = _pressure_cache["last_update"]
        if not force_refresh and (current_time - last_ts < cache_duration):
             return _pressure_cache["data"]

    print(f"Scanning for pressure reduced stocks...")
    
    keys_from_map = list(STOCK_SUB_CATEGORIES.keys())
    all_stocks = list(set(TECH_STOCKS + TRAD_STOCKS + keys_from_map))
    
    results = []
    
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(check_pressure_reduction, code, min_days) for code in all_stocks]
        for future in futures:
            res = future.result()
            if res:
                results.append(res)
    
    # Enrich names
    try:
        import twstock
        for stock in results:
            if stock['code'] in twstock.codes:
                stock['name'] = twstock.codes[stock['code']].name
    except:
        pass

    # Sort: Consecutive drop days (feature is finding reversal, so maybe more drop days is interesting?), or maybe just grouping.
    # Let's sort by drop days desc first
    results.sort(key=lambda x: x['consecutive_drop_days'], reverse=True)
    
    with _cache_lock:
        _pressure_cache["data"] = results
        _pressure_cache["last_update"] = current_time
        
    return results
