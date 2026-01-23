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
        strong_spike = change_percent >= 4.0

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
        
        # 1. Check Low Base
        # Find 60-day Low
        last_60 = hist.iloc[-60:]
        low_60 = last_60['Close'].min()
        high_60 = last_60['Close'].max()
        
        # Position in range (0 = Low, 1 = High)
        position = (current_price - low_60) / (high_60 - low_60) if high_60 > low_60 else 0.5
        
        # Must be in lower 30% of recent range to be considered "Low Base"
        if position > 0.3:
            return None
            
        # 2. Check Trend Reversal
        ma20 = last_60['Close'].rolling(window=20).mean().iloc[-1]
        ma5 = last_60['Close'].rolling(window=5).mean().iloc[-1]
        
        # Must be above MA20 (Support regained)
        if current_price < ma20:
             return None
             
        # MA5 should be > MA20 (Golden Cross or close to it) OR Price > MA20 by small margin
        # Let's say we want Price to be just crossing or slightly above
        ma_diff = (current_price - ma20) / ma20
        
        # Filter: Price shouldn't be TOO high above MA20 (don't chase high)
        if ma_diff > 0.08: # > 8% above MA20 might be too late
             return None
             
        # 3. Check Volatility (Consolidation)
        # Standard Deviation of last 20 days < Threshold?
        # Or simple box range of last 10 days
        last_10 = hist.iloc[-11:-1] # Exclude today
        if not last_10.empty:
             range_10 = (last_10['Close'].max() - last_10['Close'].min()) / last_10['Close'].min()
             # If moved > 15% in last 10 days, too volatile, skipping
             if range_10 > 0.15:
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

        return {
            "code": stock_code,
            "name": name,
            "price": round(current_price, 2),
            "low_60": round(low_60, 2),
            "position_pct": round(position * 100, 1),
            "ma20": round(ma20, 2),
            "ma_diff_pct": round(ma_diff * 100, 1),
            "category": category
        }
    except Exception:
        return None
