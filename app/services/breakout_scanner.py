import yfinance as yf
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
from .categories import TECH_STOCKS, TRAD_STOCKS, STOCK_SUB_CATEGORIES
from .stock_data import get_yahoo_ticker
from .indicators import compute_kd, compute_rsi, compute_macd, compute_bias, compute_bollinger

def get_breakout_stocks():
    """
    Scans for stocks that:
    1. Have been consolidating for 20 days (Box range < 15%)
    2. Have triggered a breakout today (Change > 4% OR Price > Box High)
    """
    
    # 1. Gather all target stocks
    keys_from_map = list(STOCK_SUB_CATEGORIES.keys())
    all_stocks = list(set(TECH_STOCKS + TRAD_STOCKS + keys_from_map))
    
    results = []
    
    # Use ThreadPool to scan fast
    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = [executor.submit(check_breakout, code) for code in all_stocks]
        for future in futures:
            res = future.result()
            if res:
                results.append(res)
    
    # Sort by "Strength" (Today's Change %)
    results.sort(key=lambda x: x['change_percent'], reverse=True)
    return results

def check_breakout(stock_code):
    try:
        ticker_symbol = get_yahoo_ticker(stock_code)
        ticker = yf.Ticker(ticker_symbol)
        
        # Need enough history for indicators (MACD slow 26 + signal 9) and BB/BIAS (20)
        hist = ticker.history(period="3mo")
        
        if len(hist) < 60:
            return None
            
        # Extract data
        today = hist.iloc[-1]
        
        # Consolidation Period: Last 20 days EXCLUDING today
        # If listed for short time, take what we have
        cons_data = hist.iloc[-21:-1] 
        
        if cons_data.empty:
            return None
            
        cons_high = cons_data['Close'].max()
        cons_low = cons_data['Close'].min()
        cons_avg = cons_data['Close'].mean()
        
        # 1. Check Consolidation (Box)
        # Range amplitude = (High - Low) / Low
        box_amplitude = (cons_high - cons_low) / cons_low
        
        # Threshold: 12% box (adjustable)
        if box_amplitude > 0.12: 
            return None

        # --- EXCLUSION LOGIC START ---
        # Rule: Exclude if stock had > 3% rise more than 4 times in the last 7 days
        # This prevents chasing stocks that are already overheated
        
        # Get last 7 trading days excluding today
        recent_7_days = hist.iloc[-8:-1] 
        
        big_rise_count = 0
        if not recent_7_days.empty:
            # We need day-over-day change for these 7 days. 
            # Note: hist contains 'Close' for each day.
            # pct_change() computes change from previous element.
            
            # Use data from -9 to -1 to get full 7 days change (since first element needs previous to calc change)
            # Or easier: just take pct_change of a slice and count
            recent_changes = hist['Close'].iloc[-9:-1].pct_change().dropna()
            
            # Allow some tolerance for "last 7 days" window mapping, 
            # taking last 7 computed changes
            recent_changes = recent_changes.tail(7)
            
            for change in recent_changes:
                if change >= 0.03: # > 3%
                    big_rise_count += 1
        
        if big_rise_count >= 4:
            return None
        # --- EXCLUSION LOGIC END ---
            
        # 2. Check Breakout Signal (price action)
        current_price = today['Close']
        prev_close = hist.iloc[-2]['Close']
        change_percent = ((current_price - prev_close) / prev_close) * 100
        
        is_breakout = False
        reason = ""
        
        # Indicators (computed on full history up to today)
        k, d = compute_kd(hist)
        rsi = compute_rsi(hist["Close"])
        macd_dif, macd_signal, macd_hist = compute_macd(hist["Close"])
        bias20 = compute_bias(hist["Close"], ma_period=20)
        bb_upper, bb_mid, bb_lower, bb_width = compute_bollinger(hist["Close"], period=20, std_mult=2.0)

        # Volume stats
        today_vol = int(today["Volume"]) if not pd.isna(today["Volume"]) else 0
        avg_vol = float(cons_data["Volume"].mean()) if not cons_data.empty else 0.0
        vol_ratio = (today_vol / (avg_vol + 1)) if avg_vol is not None else 0.0

        # Breakout conditions:
        # - price breaks box high OR strong spike
        # - volume confirms
        # - KD/RSI/MACD aligned (参考技术指标常用解释)
        # - BB squeeze (optional) to favor "盘整后突破"
        price_break = current_price > (cons_high * 1.01)
        strong_spike = change_percent >= 3.0

        # Basic indicator alignment
        kd_ok = (k is not None and d is not None and k >= d and k >= 20)
        rsi_ok = (rsi is not None and rsi >= 50 and rsi <= 80)
        macd_ok = (macd_dif is not None and macd_signal is not None and macd_dif >= macd_signal)
        vol_ok = vol_ratio >= 1.5
        bb_ok = (bb_width is not None and bb_width <= 0.12)  # band squeeze
        bb_break = (bb_upper is not None and current_price >= bb_upper)

        # Decide inclusion
        if (strong_spike or price_break) and vol_ok and kd_ok and rsi_ok and macd_ok:
            is_breakout = True
            # Prefer more specific reason labels for UI badge
            if bb_ok and (bb_break or price_break):
                reason = "布林收斂突破"
            elif strong_spike:
                reason = "長紅突破"
            else:
                reason = "突破盤整區間"
        else:
            return None
            
        if not is_breakout:
            return None
            
        # Basic filter: Volume check? (Optional, maybe skip for now to catch all)
        # if today['Volume'] < 500000: return None # Filter low volume?
        
        # Get Name
        import twstock
        name = stock_code
        category = '其他'
        if stock_code in STOCK_SUB_CATEGORIES:
             category = STOCK_SUB_CATEGORIES[stock_code]
             
        if stock_code in twstock.codes:
            info = twstock.codes[stock_code]
            name = info.name
            if category == '其他' and info.group:
                category = info.group.replace('業', '')
        
        return {
            "code": stock_code,
            "name": name,
            "category": category,
            "price": round(float(current_price), 2),
            "change_percent": round(float(change_percent), 2),
            "box_low": round(float(cons_low), 2),
            "box_high": round(float(cons_high), 2),
            "amplitude": round(float(box_amplitude) * 100, 1), # %
            "reason": reason,
            # New fields for UI
            "volume": today_vol,
            "vol_ratio": round(vol_ratio, 1),  # Volume vs Avg
            "kd_k": None if k is None else round(k, 1),
            "kd_d": None if d is None else round(d, 1),
            "rsi": None if rsi is None else round(rsi, 1),
            "macd_dif": None if macd_dif is None else round(macd_dif, 3),
            "macd_signal": None if macd_signal is None else round(macd_signal, 3),
            "macd_hist": None if macd_hist is None else round(macd_hist, 3),
            "bias20": None if bias20 is None else round(bias20, 2),
            "bb_upper": None if bb_upper is None else round(bb_upper, 2),
            "bb_mid": None if bb_mid is None else round(bb_mid, 2),
            "bb_lower": None if bb_lower is None else round(bb_lower, 2),
            "bb_width": None if bb_width is None else round(bb_width * 100, 2),  # %
        }
        
    except Exception as e:
        # print(f"Error checking breakout {stock_code}: {e}")
        return None

def is_volume_shrinking(hist, days=3, ma_vol_days=5):
    """
    Check if volume is shrinking or low relative to average.
    Returns (True/False, reason)
    """
    if len(hist) < days + ma_vol_days:
        return False, "Not enough data"
        
    recent = hist.tail(days)
    prev = hist.iloc[-(days + ma_vol_days):-days]
    
    current_vol = recent['Volume'].mean()
    avg_vol = prev['Volume'].mean()
    
    # 1. Volume shrinking order (last > current)
    # 2. OR Current volume < Average Volume * 0.8
    is_shrinking = hist['Volume'].iloc[-1] < hist['Volume'].iloc[-2]
    is_low_vol = current_vol < avg_vol * 0.8
    
    return (is_shrinking or is_low_vol), f"VolRatio: {round(current_vol/avg_vol, 2)}"

def get_rebound_stocks():
    """
    Scans for stocks that:
    1. Are at a low base (Price is < 20% above 60-day Low)
    2. Have low volatility (Consolidation)
    3. Are turning up (Price > MA20, MA5 turning up)
    """
    keys_from_map = list(STOCK_SUB_CATEGORIES.keys())
    all_stocks = list(set(TECH_STOCKS + TRAD_STOCKS + keys_from_map))
    
    results = []
    
    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = [executor.submit(check_rebound, code) for code in all_stocks]
        for future in futures:
            res = future.result()
            if res:
                results.append(res)
    
    # Sort by "Distance from Low" (closer to low is better for 'Low Base' validation, 
    # but we might want 'Stronger Rebound' so maybe sort by MA diff)
    # Let's sort by "Diff from MA20" (Strength of rebound)
    results.sort(key=lambda x: x['ma_diff_pct'], reverse=True)
    return results

def check_rebound(stock_code):
    try:
        ticker_symbol = get_yahoo_ticker(stock_code)
        ticker = yf.Ticker(ticker_symbol)
        
        # Need ~60 days for Low Base check
        hist = ticker.history(period="3mo")
        
        if len(hist) < 60:
            return None
            
        today = hist.iloc[-1]
        current_price = today['Close']
        
        # --- NEW LOGIC: Wash Trading (Pullback to MA + Shrinking Volume) ---
        # 1. Identify Uptrend Baseline: Price > MA60
        last_60 = hist.iloc[-60:]
        ma60 = last_60['Close'].rolling(window=60).mean().iloc[-1]
        
        # If below MA60, maybe use original "Low Base" logic?
        # Let's combine strategies.
        
        ma20 = last_60['Close'].rolling(window=20).mean().iloc[-1]
        ma10 = last_60['Close'].rolling(window=10).mean().iloc[-1]
        
        reason = ""
        is_rebound = False
        
        low_60 = last_60['Close'].min()
        high_60 = last_60['Close'].max()
        position_pct = (current_price - low_60) / (high_60 - low_60) if high_60 > low_60 else 0.5
        ma_diff_pct = (current_price - ma20) / ma20

        # Strategy A: Wash Trading (Strong Trend Pullback)
        # - Price > MA60 (Long term up)
        # - Pullback: Recent 3 days have at least 1-2 down days, or price dropped from local high
        # - Support: Close to MA10 or MA20 (within 2-3%)
        # - Volume: Shrinking
        
        is_uptrend = current_price > ma60
        near_support = abs(current_price - ma20)/ma20 < 0.04 or abs(current_price - ma10)/ma10 < 0.04
        
        vol_shrinking, vol_msg = is_volume_shrinking(hist, days=3)
        
        # Check Pullback (High of last 10 days > Current Price * 1.02)
        local_high = hist['Close'].iloc[-10:].max()
        is_pullback = local_high > current_price * 1.02
        
        if is_uptrend and near_support and vol_shrinking and is_pullback:
            is_rebound = True
            reason = "主力洗盤(量縮回檔守均線)"
            
        # Strategy B: Original Low Base Rebound
        # - Low position (< 30%)
        # - Regain MA20
        elif position_pct < 0.3 and current_price > ma20 and ma_diff_pct < 0.05:
            is_rebound = True
            reason = "低檔轉強(站回月線)"
            
        if not is_rebound:
            return None
                 
        import twstock
        name = stock_code
        category = '其他'
        if stock_code in STOCK_SUB_CATEGORIES:
             category = STOCK_SUB_CATEGORIES[stock_code]
        if stock_code in twstock.codes:
            info = twstock.codes[stock_code]
            name = info.name
            if category == '其他' and info.group:
                category = info.group.replace('業', '')
        
        # If reason is Wash Trading, give it a high "Low Base" score to prioritize (or sort by ma_diff)
        # We preserve original fields
        
        return {
            "code": stock_code,
            "name": name,
            "price": round(current_price, 2),
            "low_60": round(low_60, 2),
            "position_pct": round(position_pct * 100, 1),
            "ma20": round(ma20, 2),
            "ma_diff_pct": round(ma_diff_pct * 100, 1),
            "category": category,
            "reason": reason # Add reason field to API response? Original script.js might not show it in rebound card, but good to have
        }
    except Exception:
        return None

def get_downtrend_stocks():
    """
    Scans for stocks that:
    1. Are at a relatively high level
    2. Showing signs of weakness (Distribution or Reversal indicator)
    """
    keys_from_map = list(STOCK_SUB_CATEGORIES.keys())
    all_stocks = list(set(TECH_STOCKS + TRAD_STOCKS + keys_from_map))
    
    results = []
    
    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = [executor.submit(check_downtrend, code) for code in all_stocks]
        for future in futures:
            res = future.result()
            if res:
                results.append(res)
    
    # Sort: Prioritize "Distribution" (High Vol Stagnation) or High RSI
    results.sort(key=lambda x: (x.get('is_distribution', False), x['rsi'] if x['rsi'] is not None else 0), reverse=True)
    return results

def check_downtrend(stock_code):
    try:
        ticker_symbol = get_yahoo_ticker(stock_code)
        ticker = yf.Ticker(ticker_symbol)
        
        hist = ticker.history(period="3mo")
        
        if len(hist) < 60:
            return None
            
        today = hist.iloc[-1]
        current_price = today['Close']
        
        ma20 = hist['Close'].rolling(window=20).mean().iloc[-1]
        if current_price < ma20:
             return None # Trend already broken, looking for top reversal
             
        k, d = compute_kd(hist)
        rsi = compute_rsi(hist["Close"])
        today_vol = int(today["Volume"]) if not pd.isna(today["Volume"]) else 0
        avg_vol = hist['Volume'].iloc[-21:-1].mean()
        
        reason = ""
        is_downtrend = False
        is_distribution = False
        
        # Strategy A: Distribution (High Volume Stagnation)
        # - Price High (near 20 day high)
        # - Volume High (> 1.5x Avg)
        # - Price Move Small (< 1% or Doji)
        high_20 = hist['Close'].iloc[-20:].max()
        near_high = current_price > high_20 * 0.95
        high_vol = today_vol > avg_vol * 1.5
        small_move = abs(today['Close'] - today['Open']) / today['Open'] < 0.01
        
        if near_high and high_vol and small_move:
            is_downtrend = True
            is_distribution = True
            reason = "高檔爆量滯漲(出貨訊號)"
            
        # Strategy B: Technical Weakness (K<D + Weakness)
        # - K < D
        # - RSI > 60 (Overbought context) OR Divergence (Hard to check)
        elif k is not None and d is not None and k < d and k < 80: # K crossed down
             if rsi and rsi > 60:
                 is_downtrend = True
                 reason = "指標高檔背離/轉弱"
        
        if not is_downtrend:
            return None
            
        # 3. Gather Other Indicators for Display
        macd_dif, macd_signal, macd_hist = compute_macd(hist["Close"])
        bias20 = compute_bias(hist["Close"], ma_period=20)
        bb_upper, bb_mid, bb_lower, bb_width = compute_bollinger(hist["Close"], period=20, std_mult=2.0)
        
        
        # Get Name
        import twstock
        name = stock_code
        category = '其他'
        if stock_code in STOCK_SUB_CATEGORIES:
             category = STOCK_SUB_CATEGORIES[stock_code]
        if stock_code in twstock.codes:
            info = twstock.codes[stock_code]
            name = info.name
            if category == '其他' and info.group:
                category = info.group.replace('業', '')

        return {
            "code": stock_code,
            "name": name,
            "category": category,
            "price": round(float(current_price), 2),
            "change_percent": round(float((today['Close'] - hist.iloc[-2]['Close'])/hist.iloc[-2]['Close']*100), 2),
            "volume": today_vol,
            "kd_k": round(k, 1) if k else None,
            "kd_d": round(d, 1) if d else None,
            "rsi": round(rsi, 1) if rsi else None,
            "macd_dif": round(macd_dif, 3) if macd_dif else None,
            "macd_signal": round(macd_signal, 3) if macd_signal else None,
            "macd_hist": round(macd_hist, 3) if macd_hist else None,
            "bias20": round(bias20, 2) if bias20 else None,
            "bb_upper": round(bb_upper, 2) if bb_upper else None,
            "bb_lower": round(bb_lower, 2) if bb_lower else None,
            "bb_width": round(bb_width * 100, 2) if bb_width else None,
            "reason": reason, # New field
            "is_distribution": is_distribution
        }

    except Exception:
        return None
