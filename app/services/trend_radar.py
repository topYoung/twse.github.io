import yfinance as yf
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
from app.services.categories import TECH_STOCKS, TRAD_STOCKS, STOCK_SUB_CATEGORIES
from app.services.stock_data import get_yahoo_ticker
from app.services.yf_rate_limiter import fetch_stock_history
from app.services.indicators import compute_kd, compute_rsi, compute_macd, compute_macd_with_trend
from app.services.institutional_data import get_latest_institutional_data
from app.services.breakout_scanner import detect_lower_shadow_after_decline, analyze_volume_trend
import threading
import time
from datetime import datetime
import math

_trend_radar_cache = {
    "data": None,
    "last_update": 0
}
_cache_lock = threading.Lock()

def get_trend_radar_stocks(force_refresh=False, tech_only=True):
    global _trend_radar_cache
    now = datetime.now()
    current_time = time.time()

    is_market_hours = (9 <= now.hour < 14) and now.weekday() < 5
    cache_duration = 300 if is_market_hours else 1800

    # tech_only 不同時，快取視為失效
    cache_key = f'tech_only={tech_only}'
    with _cache_lock:
        if not force_refresh and _trend_radar_cache["data"]:
            if (current_time - _trend_radar_cache["last_update"] < cache_duration
                    and _trend_radar_cache.get('cache_key') == cache_key):
                return _trend_radar_cache["data"]

    keys_from_map = list(STOCK_SUB_CATEGORIES.keys())
    if tech_only:
        all_stocks = list(set(TECH_STOCKS + keys_from_map))
    else:
        all_stocks = list(set(TECH_STOCKS + TRAD_STOCKS + keys_from_map))
    inst_data = get_latest_institutional_data()

    potential_results = []
    strong_results = []

    try:
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(check_trend_radar, code, inst_data) for code in all_stocks]
            for future in futures:
                try:
                    res = future.result()
                    if res:
                        if res['type'] == 'potential':
                            potential_results.append(res)
                        elif res['type'] == 'strong':
                            strong_results.append(res)
                        elif res['type'] == 'both':
                            potential_results.append(res)
                            strong_results.append(res)
                except Exception as e:
                    pass
    except Exception as e:
        print(f"Trend Radar scanning error: {e}")

    # Sorting options
    potential_results.sort(key=lambda x: x['rsi'] or 0)
    strong_results.sort(key=lambda x: x['rsi'] or 0, reverse=True)

    # 套用進階過濾 (高槓桿/高本益比/流動性/弱勢)
    from app.services.advanced_filters import filter_stocks
    potential_results = filter_stocks(potential_results)
    strong_results = filter_stocks(strong_results)

    final_output = {
        "status": "success",
        "data": {
            "potential": potential_results,
            "strong": strong_results
        },
        "last_update": current_time
    }

    with _cache_lock:
        _trend_radar_cache["data"] = final_output
        _trend_radar_cache["last_update"] = current_time
        _trend_radar_cache["cache_key"] = cache_key

    return final_output

def safe_round(v, d=2):
    if v is None or not math.isfinite(float(v)): return None
    return round(float(v), d)

def check_trend_radar(stock_code, inst_data_map):
    try:
        inst = inst_data_map.get(stock_code, {})
        inst_net = inst.get('total', 0)
        
        ticker_symbol = get_yahoo_ticker(stock_code)
        hist = fetch_stock_history(stock_code, ticker_symbol, period="6mo", interval="1d")
        if hist.empty or len(hist) < 60: return None
        
        today = hist.iloc[-1]
        current_price = float(today['Close'])
        prev_close = float(hist.iloc[-2]['Close'])
        change_percent = ((current_price - prev_close) / prev_close) * 100
        
        # Volume
        today_vol = float(today["Volume"])
        avg_vol_5 = float(hist.iloc[-6:-1]["Volume"].mean())
        if today_vol < 200000 or avg_vol_5 < 100000: # Filter out extremely illiquid stocks
            return None
        vol_increase = today_vol > avg_vol_5
        
        # Indicators
        k, d = compute_kd(hist)
        rsi = compute_rsi(hist["Close"], period=14)
        macd_dif, macd_signal, macd_hist = compute_macd(hist["Close"])
        macd_trend = compute_macd_with_trend(hist["Close"], trend_periods=3)
        
        # Moving Averages
        ma5 = float(hist['Close'].rolling(window=5).mean().iloc[-1])
        ma10 = float(hist['Close'].rolling(window=10).mean().iloc[-1])
        ma20 = float(hist['Close'].rolling(window=20).mean().iloc[-1])
        
        # Position pct (60 days)
        recent_60 = hist['Close'].iloc[-60:]
        low_60 = float(recent_60.min())
        high_60 = float(recent_60.max())
        position_pct = (current_price - low_60) / (high_60 - low_60) if high_60 > low_60 else 0.5
        
        # Price Action
        is_red_k = current_price >= float(today['Open'])
        lower_shadow_info = detect_lower_shadow_after_decline(hist, decline_days=2, shadow_ratio=1.5)
        has_lower_shadow = lower_shadow_info['has_lower_shadow'] == 1
        
        # MACD Logic
        macd_starting = False
        if len(hist['Close']) >= 3:
            h_latest = float(macd_trend.get('hist_series', [0])[-1] or 0)
            h_prev = float(macd_trend.get('hist_series', [0,0])[-2] or 0)
            if (h_prev <= 0 and h_latest > 0) or (h_latest < 0 and h_latest > h_prev):
                macd_starting = True
                
        # 🎯 潛龍伏淵 (Potential Breakout)
        is_potential = False
        potential_reason = []
        
        # 1. 計算連漲天數
        consecutive_rise_days = 0
        for i in range(len(hist) - 1, 0, -1):
            if float(hist.iloc[i]['Close']) > float(hist.iloc[i-1]['Close']):
                consecutive_rise_days += 1
            else:
                break
                
        # 2. 法人動態判斷 (偷偷佈局：任一法人買超 > 0)
        inst_foreign = inst.get('foreign', 0)
        inst_trust = inst.get('trust', 0)
        inst_dealer = inst.get('dealer', 0)
        cond_sneaky_inst = (inst_foreign > 0 or inst_trust > 0 or inst_dealer > 0)
        
        cond_level_safe = position_pct <= 0.40 or (current_price >= ma20 and prev_close < ma20) or (abs(current_price - ma20) / ma20 < 0.02)
        cond_not_overbought = (consecutive_rise_days <= 3)
        cond_macd_kd_rsi = macd_starting and (d is not None and d <= 40) and (rsi is not None and 40 <= rsi <= 75)
        cond_support = cond_sneaky_inst and vol_increase
        cond_k_shape = is_red_k or has_lower_shadow
        
        if cond_level_safe and cond_not_overbought and cond_macd_kd_rsi and cond_support and cond_k_shape:
            is_potential = True
            potential_reason.append("低檔起漲 / 法人佈局")

        # 🚀 乘風破浪 (Strong Momentum)
        is_strong = False
        strong_reason = []
        
        cond_ma_alignment = current_price > ma5 > ma10 > ma20
        cond_rsi_strong = (rsi is not None and 55 <= rsi <= 75)
        cond_macd_strong = macd_trend['trend'] == '擴張' and macd_hist is not None and macd_hist > 0
        
        vol_info = analyze_volume_trend(hist, days=5)
        cond_healthy_vol = vol_info['is_healthy']
        cond_momentum = (current_price > prev_close and prev_close > float(hist.iloc[-3]['Close'])) or inst_net > 200
        
        if cond_ma_alignment and cond_rsi_strong and cond_macd_strong and cond_healthy_vol and cond_momentum:
            is_strong = True
            strong_reason.append("均線多頭 / 量價健康")
            
        if not is_potential and not is_strong:
            return None
            
        import twstock
        category = STOCK_SUB_CATEGORIES.get(stock_code, '其他')
        name = twstock.codes[stock_code].name if stock_code in twstock.codes else stock_code
            
        result_type = 'both' if (is_potential and is_strong) else ('potential' if is_potential else 'strong')
        reason_str = " | ".join(potential_reason + strong_reason)

        return {
            "code": stock_code,
            "name": name,
            "category": category,
            "price": safe_round(current_price, 2),
            "change_percent": safe_round(change_percent, 2),
            "reason": reason_str,
            "volume": int(today_vol),
            "inst_net": int(inst_net),
            "rsi": safe_round(rsi, 1),
            "kd_k": safe_round(k, 1),
            "kd_d": safe_round(d, 1),
            "macd_hist": safe_round(macd_hist, 3),
            "position_pct": safe_round(position_pct * 100, 1),
            "type": result_type
        }
    except Exception as e:
        return None
