import yfinance as yf
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
from .categories import TECH_STOCKS, TRAD_STOCKS, STOCK_SUB_CATEGORIES
from .stock_data import get_yahoo_ticker
from .yf_rate_limiter import fetch_stock_history
from .institutional_data import get_latest_institutional_data
from .realtime_quotes import get_realtime_quotes
import threading
import time
from datetime import datetime

# Global Cache
_momentum_cache = {
    "data": [],
    "last_update": 0
}
_cache_lock = threading.Lock()

def check_consecutive_rise(stock_code, min_days=2):
    """
    檢查股票是否連續上漲
    
    Args:
        stock_code: 股票代碼
        min_days: 最小連漲天數
        
    Returns:
        dict or None: 符合條件則回傳股票資訊，否則 None
    """
    try:
        ticker_symbol = get_yahoo_ticker(stock_code)
        # 取這幾天的資料，多取一點以確保有足夠的歷史來計算連漲
        # 假設最大連漲不超過 20 天，取 1 個月應該夠
        hist = fetch_stock_history(stock_code, ticker_symbol, period="1mo", interval="1d")
        
        if hist.empty or len(hist) < min_days + 1:
            return None
            
        # 取得最新收盤價
        current_price = hist['Close'].iloc[-1]
        
        # 簡單過濾：價格低於 10 元的雞蛋水餃股通常波動大且風險高，可考慮過濾
        # 這裡先不過濾，讓使用者自己看
        
        # 過濾成交量：取近 5 日均量，若小於 500 張則忽略
        avg_volume = hist['Volume'].tail(5).mean()
        if avg_volume < 500 * 1000: # 500 張
            return None

        # 計算連漲天數
        consecutive_days = 0
        total_increase_pct = 0.0
        
        # 從最後一天往前遍歷
        # prices: List of close prices
        prices = hist['Close'].tolist()
        dates = hist.index.tolist()
        
        # 檢查是否為上漲 (今日 > 昨日)
        # 注意：i 是從最後一個元素的 index
        for i in range(len(prices) - 1, 0, -1):
            if prices[i] > prices[i-1]:
                consecutive_days += 1
            else:
                break
                
        if consecutive_days < min_days:
            return None
            
        # 計算累積漲幅
        start_price = prices[len(prices) - 1 - consecutive_days]
        end_price = prices[-1]
        total_increase = end_price - start_price
        total_increase_pct = (total_increase / start_price) * 100
        
        # 準備回傳資料
        stock_name = stock_code
        category = '其他'
        if stock_code in STOCK_SUB_CATEGORIES:
            category = STOCK_SUB_CATEGORIES[stock_code]
            
        # 嘗試取得即時漲跌 (如果市場開盤中)
        change = prices[-1] - prices[-2]
        change_pct = (change / prices[-2]) * 100
        
        return {
            "code": stock_code,
            "name": stock_name,
            "category": category,
            "price": round(current_price, 2),
            "change": round(change, 2),
            "change_percent": round(change_pct, 2),
            "volume": int(hist['Volume'].iloc[-1]),
            "consecutive_days": consecutive_days,
            "total_increase_pct": round(total_increase_pct, 2),
            "tags": [f"🔥連漲{consecutive_days}天", f"累積+{round(total_increase_pct,1)}%"]
        }

    except Exception as e:
        # print(f"Error checking {stock_code}: {e}")
        return None

def get_momentum_stocks(min_days=2, force_refresh=False):
    """
    掃描連漲股票（支援快取）
    """
    global _momentum_cache
    
    # Determine cache duration based on market status
    now = datetime.now()
    current_time = time.time()
    
    # Market hours: 09:00 - 13:35 (approx)
    is_market_hours = (9 <= now.hour < 14) and now.weekday() < 5
    
    if is_market_hours:
        cache_duration = 300  # 5 minutes during market
    else:
        cache_duration = 3600 # 1 hour during off-hours (or until next open)
        
    with _cache_lock:
        last_ts = _momentum_cache["last_update"]
        # Handle initial state 0
        last_dt = datetime.fromtimestamp(last_ts) if last_ts > 0 else datetime.min
        
        # Smart Refresh Logic:
        # 1. Force refresh if we just crossed into market hours (09:00)
        was_pre_market = last_dt.hour < 9 and last_dt.date() == now.date()
        crossed_to_market = is_market_hours and was_pre_market
        
        # 2. Force refresh if it's a new day and we haven't scanned yet
        is_new_day = last_dt.date() != now.date()

        if not force_refresh and not crossed_to_market and not is_new_day and (current_time - last_ts < cache_duration):
             # print(f"Using cached momentum results (Age: {int(current_time - last_ts)}s)")
             return _momentum_cache["data"]

    print(f"Scanning for momentum stocks... (Market Open: {is_market_hours})")
    
    # 準備股票清單
    keys_from_map = list(STOCK_SUB_CATEGORIES.keys())
    all_stocks = list(set(TECH_STOCKS + TRAD_STOCKS + keys_from_map))
    
    results = []
    
    # 多執行緒掃描 (限制 max_workers=5 避免限流)
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(check_consecutive_rise, code, min_days) for code in all_stocks]
        for future in futures:
            res = future.result()
            if res:
                results.append(res)
    
    # 補充法人資料（非必要，但為了資訊豐富度）
    try:
        inst_data = get_latest_institutional_data()
        for stock in results:
            code = stock['code']
            if code in inst_data:
                stock['institutional'] = inst_data[code]
                # 檢查主要法人買賣超
                total_buy = inst_data[code]['total']
                if total_buy > 200000: # 買超大於 200 張
                    stock['tags'].append("🦈法人買超")
    except Exception as e:
        print(f"Error enriching institutional data: {e}")

    # 補充中文名稱
    try:
        import twstock
        for stock in results:
            if stock['code'] in twstock.codes:
                stock['name'] = twstock.codes[stock['code']].name
    except:
        pass

    # 排序：優先顯示連漲天數多，且近期漲幅大的
    results.sort(key=lambda x: (x['consecutive_days'], x['change_percent']), reverse=True)
    
    # Update cache
    with _cache_lock:
        _momentum_cache["data"] = results
        _momentum_cache["last_update"] = current_time
        
    return results
