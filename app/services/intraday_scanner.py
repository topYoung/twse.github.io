import time
import threading
from datetime import datetime
from typing import List, Dict, Optional
from .categories import TECH_STOCKS, TRAD_STOCKS, STOCK_SUB_CATEGORIES
from .realtime_quotes import get_realtime_prices_batch, get_batch_intraday_candles

# Global Cache
_intraday_cache = {
    "data": [],
    "last_update": 0
}
_cache_lock = threading.Lock()

def get_intraday_strength_stocks(force_refresh: bool = False) -> Dict:
    """
    掃描盤中分時強勢股
    條件：
    1. 當前價格 > 開盤價 (紅棒)
    2. 當前價格 > 昨收價 (漲)
    3. 漲幅 > 2%
    4. 價格位於當日高點附近 (回檔幅度 < 20%)
    5. 成交量 > 100 張 (基本門檻)
    """
    global _intraday_cache
    
    now = datetime.now()
    current_time = time.time()
    
    # 判斷是否為市場交易時間 (09:00 - 13:30)
    is_market_hours = (9 <= now.hour < 14) and now.weekday() < 5
    
    # 快取策略：盤中 90 秒更新一次，盤後 30 分鐘更新一次
    cache_duration = 90 if is_market_hours else 1800
    
    with _cache_lock:
        if not force_refresh and _intraday_cache["data"]:
            last_ts = _intraday_cache["last_update"]
            if current_time - last_ts < cache_duration:
                return {
                    "stocks": _intraday_cache["data"],
                    "is_market_hours": is_market_hours,
                    "last_update": last_ts
                }

    # 1. 準備目標股票清單
    keys_from_map = list(STOCK_SUB_CATEGORIES.keys())
    all_stocks = list(set(TECH_STOCKS + TRAD_STOCKS + keys_from_map))
    
    # 2. 第一階段：快速過濾 (獲取價格與漲幅)
    # 使用 get_realtime_prices_batch，每 25 檔一個 chunk
    # print(f"Intraday Scanner: Quick filtering {len(all_stocks)} stocks...")
    quick_quotes = get_realtime_prices_batch(all_stocks)
    
    # 初篩：漲幅 > 2%
    potential_codes = [
        code for code, data in quick_quotes.items() 
        if data.get('change_percent', 0) > 2.0
    ]
    
    if not potential_codes:
        return {
            "stocks": [],
            "is_market_hours": is_market_hours,
            "last_update": current_time
        }
    
    # 3. 第二階段：詳細分析 (獲取 OHLC 與成交量)
    # print(f"Intraday Scanner: Detailed scanning {len(potential_codes)} potential stocks...")
    detailed_data = get_batch_intraday_candles(potential_codes)
    
    results = []
    for code in potential_codes:
        candle = detailed_data.get(code)
        if not candle:
            continue
            
        price = candle['close']
        open_price = candle['open']
        high = candle['high']
        low = candle['low']
        yesterday_close = candle['yesterday_close']
        volume = candle['volume'] / 1000  # 轉換為張數
        
        # 篩選邏輯
        # 1. 不能低於開盤價且必須上漲
        if price < open_price or price <= yesterday_close:
            continue
            
        # 2. 基本成交量過濾 (100 張)
        if volume < 100:
            continue
            
        # 3. 盤中位階 (位於當日高檔)
        # (High - Price) / (High - Low) < 0.2
        amplitude = high - low
        if amplitude > 0:
            rebound_ratio = (high - price) / amplitude
            if rebound_ratio > 0.2:
                continue
        
        # 通過篩選
        name = quick_quotes.get(code, {}).get('name', code)
        category = STOCK_SUB_CATEGORIES.get(code, '其他')
        
        results.append({
            "code": code,
            "name": name,
            "category": category,
            "price": price,
            "open": open_price,
            "high": high,
            "low": low,
            "change_percent": candle['change_percent'],
            "volume": int(volume),
            "rebound_ratio": round((high - price) / amplitude, 2) if amplitude > 0 else 0,
            "tags": ["☀️ 分時強勢", "📈 突破平盤" if open_price <= yesterday_close else "🚀 強勢開高"]
        })
    
    # 排序：漲幅由高到低
    results.sort(key=lambda x: x['change_percent'], reverse=True)
    
    # 更新快取
    with _cache_lock:
        _intraday_cache["data"] = results
        _intraday_cache["last_update"] = current_time
        
    return {
        "stocks": results,
        "is_market_hours": is_market_hours,
        "last_update": current_time
    }

if __name__ == "__main__":
    # Test
    print("Testing Intraday Strength Scanner...")
    res = get_intraday_strength_stocks(force_refresh=True)
    print(f"Found {len(res['stocks'])} stocks.")
    for s in res['stocks'][:5]:
        print(f"{s['code']} {s['name']}: {s['change_percent']}% (Vol: {s['volume']})")
