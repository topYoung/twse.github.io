import yfinance as yf
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
from .categories import TECH_STOCKS, TRAD_STOCKS, STOCK_SUB_CATEGORIES
from .stock_data import get_yahoo_ticker
from .yf_rate_limiter import fetch_stock_history
from .indicators import compute_kd, compute_rsi, compute_macd, compute_bias, compute_bollinger, compute_multi_rsi, compute_macd_with_trend
from .institutional_data import get_latest_institutional_data
from .realtime_quotes import get_realtime_quotes
import threading
import time
import math
from datetime import datetime

# Global Cache for Breakout Results
_breakout_cache = {
    "data": [],
    "last_update": 0
}
_cache_lock = threading.Lock()

# ============================================================
# 動態閾值計算函數（高優先級改進 1.1）
# ============================================================

def get_box_threshold(stock_code):
    """
    依產業特性調整盤整區間閾值
    高波動產業使用較寬閾值，低波動產業使用較嚴格閾值
    """
    category = STOCK_SUB_CATEGORIES.get(stock_code, '其他')
    
    # 高波動產業（半導體、IC設計、航運、生技等）
    high_volatility = ['IC設計', '記憶體', '航運', '生技', '矽光子', '能源']
    if any(cat in category for cat in high_volatility):
        return 0.20  # 20%
    
    # 低波動產業（金融、傳產、食品等）
    low_volatility = ['銀行', '保險', '證券', '食品', '水泥', '電力']
    if any(cat in category for cat in low_volatility):
        return 0.10  # 10%
    
    # 中等波動（晶圓代工、PCB、被動元件等）
    return 0.15  # 預設 15%


def get_inst_buy_threshold(stock_code, avg_volume):
    """
    依股票流通量調整法人買超門檻（高優先級改進 1.2）
    小型股使用較低門檻，大型股使用較高門檻
    
    Args:
        stock_code: 股票代碼
        avg_volume: 平均成交股數（非張數）
    
    Returns:
        法人買超門檻（股數）
    """
    # 將成交股數轉換為張數（1張 = 1000股）
    avg_volume_lots = avg_volume / 1000
    
    # 小型股：日均量 < 1000 張
    if avg_volume_lots < 1000:
        return 100000   # 100 張
    # 中型股：1000 - 5000 張
    elif avg_volume_lots < 5000:
        return 300000   # 300 張
    # 大型股：> 5000 張
    else:
        return 500000   # 500 張


def analyze_volume_trend(hist, days=5):
    """
    分析量能趨勢（高優先級改進 1.3）
    檢查量能是否呈現健康的遞增趨勢
    
    Args:
        hist: 歷史資料 DataFrame
        days: 分析天數
    
    Returns:
        dict: {
            'is_increasing': bool,
            'growth_rate': float,
            'is_healthy': bool
        }
    """
    if len(hist) < days:
        return {'is_increasing': False, 'growth_rate': 0, 'is_healthy': False}
    
    recent_vols = hist['Volume'].tail(days)
    
    # 檢查是否呈現遞增趨勢（至少 80% 的天數是遞增的）
    increasing_count = sum(1 for i in range(len(recent_vols)-1) 
                          if recent_vols.iloc[i] < recent_vols.iloc[i+1])
    is_increasing = increasing_count >= (days - 1) * 0.6  # 至少 60% 遞增
    
    # 計算量能變化率
    vol_growth_rate = (recent_vols.iloc[-1] / (recent_vols.iloc[0] + 1)) - 1
    
    # 健康放量：遞增且成長率 > 30%
    is_healthy = is_increasing and vol_growth_rate > 0.3
    
    return {
        'is_increasing': is_increasing,
        'growth_rate': round(vol_growth_rate, 2),
        'is_healthy': is_healthy
    }


def classify_volume_signal(today_vol, avg_vol):
    """
    根據成交量比率分類量能訊號
    
    Args:
        today_vol: 當日成交量
        avg_vol: 平均成交量
    
    Returns:
        str: 量能訊號標籤（'🔥 爆量上漲' / '📈 帶量上漲' / '⚠️ 量能不足' / '➡️ 量能持平'）
    """
    vol_ratio = today_vol / (avg_vol + 1)
    
    if vol_ratio >= 2.5:
        return '🔥 爆量上漲'
    elif vol_ratio >= 1.5:
        return '📈 帶量上漲'
    elif vol_ratio < 0.8:
        return '⚠️ 量能不足'
    else:
        return '➡️ 量能持平'


def detect_lower_shadow_after_decline(hist, decline_days=3, shadow_ratio=1.5):
    """
    偵測多日下跌後出現下引線（錘頭線/反彈訊號）
    
    Args:
        hist: 歷史資料 DataFrame
        decline_days: 檢查連續下跌天數（預設 3 天）
        shadow_ratio: 下影線/實體比率門檻（預設 1.5 倍）
    
    Returns:
        dict: {
            'has_lower_shadow': bool,
            'decline_count': int,
            'shadow_length': float,
            'body_length': float,
            'shadow_ratio': float
        }
    """
    if len(hist) < decline_days + 1:
        return {
            'has_lower_shadow': 0,
            'decline_count': 0,
            'shadow_length': 0.0,
            'body_length': 0.0,
            'shadow_ratio': 0.0
        }
    
    # 檢查前 N 天是否連續下跌
    # 邏輯：今天(iloc[-1])之前的幾天都是下跌趨勢
    # 改進：不包含今天(Today)的漲跌，因為今天是反轉日(可能收紅)，我們只看「過去」是否連跌
    # 我們需要 decline_days 個跌幅，所以需要前 decline_days + 1 天的資料 (比較用)
    
    # 確保有足夠資料：今日 + 前(N+1)天 -> 總共 N+2 天
    needed_days = decline_days + 2
    if len(hist) < needed_days:
        return {
            'has_lower_shadow': 0,
            'decline_count': 0,
            'check_days': decline_days,
            'shadow_length': 0.0,
            'body_length': 0.0,
            'shadow_ratio': 0.0
        }

    # 取出 "不包含今天" 的最後 (decline_days + 1) 天 Close
    prices_prior = hist['Close'].iloc[-(decline_days + 2) : -1]

    decline_count = 0
    # 從最後一天往前比對
    # prices_prior 索引：0 .. M
    # Loop i from M down to 1
    for i in range(len(prices_prior) - 1, 0, -1):
        curr = prices_prior.iloc[i]
        prev = prices_prior.iloc[i-1]
        
        if curr < prev:
            decline_count += 1
        else:
            break 
            
    # 額外確認：今天的 Low 最好是近幾日新低，增強「探底」意義 (Optional)
    # prev_lows = hist['Low'].iloc[-(decline_days + 2) : -1].min()
    # today_low = hist.iloc[-1]['Low']
    # is_new_low = today_low < prev_lows
            
    # 檢查最後一根 K 棒是否有下引線
    today = hist.iloc[-1]
    high = today['High']
    low = today['Low']
    close = today['Close']
    open_price = today['Open']
    
    body_top = max(close, open_price)
    body_bottom = min(close, open_price)
    
    # 計算下影線長度 (實體底部 - 最低價)
    lower_shadow_length = body_bottom - low
    
    # 計算上影線長度 (最高價 - 實體頂部)
    upper_shadow_length = high - body_top
    
    # 計算實體長度
    body_length = body_top - body_bottom
    
    # 計算比率（避免除以零）
    # 如果實體極小（十字線），我們給予較高的比率權重，但要確保有足夠長度
    if body_length > 0:
        shadow_ratio_value = lower_shadow_length / body_length
    else:
        # 實體為 0，如果下引線有長度，則視為無限大
        shadow_ratio_value = 999.0 if lower_shadow_length > 0 else 0
    
    # 判斷條件：
    # 1. 之前有下跌趨勢
    # 2. 下影線夠長 (相對實體)
    # 3. 下影線明顯長於上影線 (至少 2 倍，確保不是十字變盤線或長腳十字，而是偏多解讀的垂頭)
    has_lower_shadow = (
        decline_count >= decline_days and
        shadow_ratio_value >= shadow_ratio and
        lower_shadow_length > (upper_shadow_length * 1.5)
    )
    
    return {
        'has_lower_shadow': int(has_lower_shadow),
        'decline_count': int(decline_count),
        'check_days': decline_days,
        'shadow_length': round(float(lower_shadow_length), 2),
        'body_length': round(float(body_length), 2),
        'shadow_ratio': round(float(shadow_ratio_value), 2)
    }


def get_breakout_stocks(force_refresh=False):
    """
    Scans for stocks that:
    1. Have been consolidating for 15-60 days (Box range < 15%)
    2. Have triggered a breakout today (Change > 3% OR Price > Box High)
    3. Consider previous day's Institutional Sudden Buy
    4. Consider real-time Bid/Ask Volume Ratio (Only during market hours)
    """
    try:
        global _breakout_cache
        
        # Determine current market state
        now = datetime.now()
        current_time = time.time()  # Fix NameError
        # Market hours: Mon-Fri 09:00 - 13:30 (approx)
        is_market_hours = (9 <= now.hour < 14) and now.weekday() < 5
        is_pre_market = (8 <= now.hour < 9) and now.weekday() < 5
        
        # Cache duration strategy
        if is_market_hours:
            cache_duration = 180  # 盤中 3 分鐘更新一次 (因掃描需時約 2 分鐘)
        else:
            cache_duration = 1800 # 盤後 30 分鐘更新一次
        
        with _cache_lock:
            if not force_refresh and _breakout_cache["data"]:
                last_ts = _breakout_cache["last_update"]
                last_dt = datetime.fromtimestamp(last_ts)
                
                # Smart Refresh: Force update if we just transitioned into market hours
                was_pre_market = last_dt.hour < 9 and last_dt.date() == now.date()
                crossed_to_market = is_market_hours and was_pre_market
                is_new_day = last_dt.date() != now.date()
                
                if not crossed_to_market and not is_new_day and (current_time - last_ts < cache_duration):
                    res = _breakout_cache["data"]
                    if isinstance(res, list): # Backward compatibility
                        return {"stocks": res, "is_market_hours": is_market_hours, "is_pre_market": is_pre_market}
                    # Update current state if reusing cache
                    if isinstance(res, dict):
                        res["is_market_hours"] = is_market_hours
                        res["is_pre_market"] = is_pre_market
                    return res

        # 1. Gather all target stocks
        keys_from_map = list(STOCK_SUB_CATEGORIES.keys())
        all_stocks = list(set(TECH_STOCKS + TRAD_STOCKS + keys_from_map))
        
        # 2. Get latest institutional data (one-time fetch)
        inst_data = get_latest_institutional_data()
        
        # === 盤中批次獲取即時數據 (優化效能) ===
        intraday_data_map = {}
        if is_market_hours:
            from app.services.realtime_quotes import get_batch_intraday_candles
            # print(f"正在批次獲取 {len(all_stocks)} 檔股票的即時報價...")
            intraday_data_map = get_batch_intraday_candles(all_stocks)
        
        results = []
        
        # Use ThreadPool to scan fast
        try:
            # 降低併發數以減少系統負載 (改為 5)
            with ThreadPoolExecutor(max_workers=5) as executor:
                # 傳入 intraday_data
                futures = [executor.submit(check_breakout_v2, code, inst_data, intraday_data_map.get(code)) for code in all_stocks]
                for future in futures:
                    try:
                        res = future.result()
                        if res:
                            results.append(res)
                    except Exception as e:
                        print(f"Worker error: {e}")
                        continue
        except Exception as e:
            print(f"Scanning error: {e}")
        
        # 3. Apply Real-time Bid/Ask filter during market hours
        if is_market_hours and results:
            active_codes = [r['code'] for r in results]
            quotes = get_realtime_quotes(active_codes)
            
            filtered_results = []
            for r in results:
                q = quotes.get(r['code'])
                if q:
                    r['bid_vol'] = q['bid_vol']
                    r['ask_vol'] = q['ask_vol']
                    r['bid_ask_ratio'] = q['bid_ask_ratio']
                    
                    # Rule: Only consider if Buy >= Sell (for some sensitivity)
                    if q['bid_ask_ratio'] >= 1.0:
                        filtered_results.append(r)
                else:
                    filtered_results.append(r)
            results = filtered_results

        # Sort
        results.sort(key=lambda x: x['change_percent'], reverse=True)

        
        final_output = {
            "stocks": results,
            "is_market_hours": is_market_hours,
            "is_pre_market": is_pre_market,
            "last_update": current_time
        }
        
        with _cache_lock:
            _breakout_cache["data"] = final_output
            _breakout_cache["last_update"] = current_time
            
        return final_output
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "stocks": [],
            "error": str(e),
            "is_market_hours": False,
            "is_pre_market": False
        }

def check_breakout_v2(stock_code, inst_data_map, intraday_data=None):
    """
    Enhanced breakout check including institutional data.
    使用動態閾值提升精確性（已整合高優先級改進 1.1, 1.2, 1.3）
    Args:
        stock_code: 股票代碼
        inst_data_map: 法人數據
        intraday_data: 即時 K 棒數據 (選填)
    """
    try:
        inst = inst_data_map.get(stock_code, {})
        inst_net = inst.get('total', 0)
        
        ticker_symbol = get_yahoo_ticker(stock_code)
        
        hist = fetch_stock_history(stock_code, ticker_symbol, period="6mo", interval="1d")
        if hist.empty: return None
        
        # === 盤中時段整合即時數據 (使用批次獲取結果) ===
        if intraday_data:
            try:
                # 若有傳入即時數據且有成交量，則附加到歷史數據
                if intraday_data['volume'] > 0:
                    # 建立今日 K 棒 DataFrame
                    today_index = pd.Timestamp.now().normalize()  # 當日日期（00:00:00）
                    today_df = pd.DataFrame([{
                        'Open': intraday_data['open'],
                        'High': intraday_data['high'],
                        'Low': intraday_data['low'],
                        'Close': intraday_data['close'],
                        'Volume': intraday_data['volume']
                    }], index=[today_index])
                    
                    # 避免重複：檢查最後一根 K 棒日期
                    if not hist.empty:
                        last_date = hist.index[-1].normalize()
                        if last_date == today_index:
                            # 今日數據已存在（盤後 Yahoo 可能已更新），替換為即時數據
                            hist = hist[:-1]
                    
                    # 合併數據
                    hist = pd.concat([hist, today_df])
                    hist = hist.astype(float)  # 確保類型一致
                    
                    # print(f"[{stock_code}] 盤中數據已整合 - 現價: {intraday_data['close']}")
            except Exception as e:
                pass

        if len(hist) < 60: return None
        
        today = hist.iloc[-1]
        
        # === 動態閾值應用 ===
        # 1. 依產業調整盤整區間閾值（改進 1.1）
        box_threshold = get_box_threshold(stock_code)
        
        # 2. 依流通量調整法人買超門檻（改進 1.2）
        avg_vol = float(hist.iloc[-30:]['Volume'].mean())  # 最近30天平均量
        inst_threshold = get_inst_buy_threshold(stock_code, avg_vol)
        has_sudden_buy = inst_net > inst_threshold
        
        # Best box window (15 to 60 days)
        best_box = None
        best_amplitude = 99.0
        
        periods = [20, 30, 40, 60]
        for p in periods:
            if len(hist) < p + 1: continue
            data = hist.iloc[-(p+1):-1]
            high = data['Close'].max()
            low = data['Close'].min()
            amp = (high - low) / low
            if amp < best_amplitude:
                best_amplitude = amp
                best_box = (high, low, p)
        
        # 使用動態閾值判斷（不再是固定 0.15）
        if not best_box or best_amplitude > box_threshold:
            # 放寬：如果有法人大買且振幅在合理範圍內
            relaxed_threshold = box_threshold * 1.33  # 放寬 33%
            if not (has_sudden_buy and best_amplitude < relaxed_threshold):
                return None

        cons_high, cons_low, cons_days = best_box
        
        # Price Action
        current_price = today['Close']
        prev_close = hist.iloc[-2]['Close']
        change_percent = ((current_price - prev_close) / prev_close) * 100
        
        price_break = current_price > (cons_high * 1.005)
        strong_spike = change_percent >= 3.5

        # === 技術指標計算（加入多週期驗證）===
        # 基本指標
        k, d = compute_kd(hist)
        
        # === KD 低檔過濾 (新增) ===
        # 要求 KD 都在 35 以下
        if k is None or d is None or k > 35 or d > 35:
            return None
            
        rsi = compute_rsi(hist["Close"])
        macd_dif, macd_signal, macd_hist = compute_macd(hist["Close"])
        bias20 = compute_bias(hist["Close"], ma_period=20)
        bb_upper, bb_mid, bb_lower, bb_width = compute_bollinger(hist["Close"], period=20, std_mult=2.0)
        
        # 多週期指標（高優先級改進 3）
        multi_rsi = compute_multi_rsi(hist["Close"])
        macd_trend = compute_macd_with_trend(hist["Close"], trend_periods=5)

        
        # Volume Analysis - 加入趨勢分析（改進 1.3）
        today_vol = int(today["Volume"]) if not pd.isna(today["Volume"]) else 0
        avg_vol_period = float(hist.iloc[-(cons_days+1):-1]["Volume"].mean())
        vol_ratio = today_vol / (avg_vol_period + 1)
        
        # === 基本流動性過濾（新增：排除量太少的殭屍股假突破）===
        # 條件 1：今日成交量必須大於 50 萬股（500 張），確保突破具有實質資金參與
        # 條件 2：盤整期間的日均量大於 10 萬股（100 張），避免平時完全無交易的冷門股
        if today_vol < 500000 or avg_vol_period < 100000:
            return None
        
        # 量能趨勢分析
        vol_trend = analyze_volume_trend(hist, days=5)
        
        # 量能訊號分類
        volume_signal = classify_volume_signal(today_vol, avg_vol_period)
        
        # 下引線偵測（多日下跌後的反彈訊號 - 改為 lower shadow）
        lower_shadow_info = detect_lower_shadow_after_decline(hist, decline_days=3, shadow_ratio=1.5)

        # Low Base Check (Added)
        recent_60 = hist['Close'].iloc[-60:]
        low_60 = recent_60.min()
        high_60 = recent_60.max()
        position_pct = (current_price - low_60) / (high_60 - low_60) if high_60 > low_60 else 0.5
        is_low_base = position_pct < 0.30 # Under 30% of 60-day range
        
        # === 改進的有效性判斷（已移除漲幅限制）===
        is_valid = False
        reason = ""
        
        # 策略 1: 健康放量突破（優先）
        if vol_trend['is_healthy'] and (price_break or strong_spike):
            is_valid = True
            reason = "健康放量突破"
            if has_sudden_buy:
                reason = "法人+健康放量"
        # 策略 2: 一般突破（量比要求較高）
        elif (price_break or strong_spike) and vol_ratio >= 1.5:
            is_valid = True
            reason = "突破盤整區"
            if has_sudden_buy:
                reason = "法人大買+突破"
        # 策略 3: 法人主導（已移除漲幅限制，只要正漲即可）
        elif has_sudden_buy and change_percent > 0 and vol_ratio >= 1.0:
            is_valid = True
            reason = "法人佈局發動"
        # 策略 4: 帶量上漲（移除漲幅限制）
        elif vol_ratio >= 1.8 and change_percent > 0:
            is_valid = True
            reason = "帶量上漲"
        # 策略 5: 多日下跌後下引線（錘頭線）
        elif lower_shadow_info['has_lower_shadow']:
            is_valid = True
            reason = f"🔨 下跌後錘頭線"
        # 策略 6: 突破盤整區但量能不足（放寬條件）
        elif price_break and change_percent > 0:
            is_valid = True
            reason = "突破盤整區"
            
        if is_low_base and is_valid:
            reason = "💎 低檔" + reason
            
        if not is_valid: return None
        
        # Metadata
        import twstock
        name = stock_code
        if stock_code in twstock.codes:
            name = twstock.codes[stock_code].name
        category = STOCK_SUB_CATEGORIES.get(stock_code, '其他')
        if category == '其他' and stock_code in twstock.codes:
            info = twstock.codes[stock_code]
            if info.group: category = info.group.replace('業', '')
        
        import math
        def safe_round(v, d=2):
            if v is None or not math.isfinite(float(v)): return None
            return round(float(v), d)

        # === 技術診斷（整合多週期驗證）===
        diagnostics = []
        
        # 1. 過熱警示
        if rsi and rsi > 80: 
            diagnostics.append("⚠️ RSI過熱")
        elif rsi and rsi > 70 and multi_rsi['alignment'] == '空頭排列':
            diagnostics.append("⚠️ RSI頂背離")
            
        if bias20 and bias20 > 12: 
            diagnostics.append("⚠️ 乖離偏高")
        if k and k > 85: 
            diagnostics.append("⚠️ KD高檔")
        
        # 2. 多頭訊號
        if multi_rsi['alignment'] == '多頭排列':
            diagnostics.append("✅ RSI多頭排列")
        
        if macd_hist and macd_hist > 0:
            if macd_trend['trend'] == '擴張':
                diagnostics.append("🚀 動能加速擴張")
            else:
                diagnostics.append("🚀 動能擴張")
        elif macd_trend['trend'] == '收斂':
            diagnostics.append("⚠️ 動能收斂")
        
        if bb_width and bb_width > 0.20:
            diagnostics.append("📡 開口擴大")
            
        if is_low_base:
            diagnostics.append("💎 低位階")
        
        # 3. 量能診斷
        if vol_trend['is_healthy']:
            diagnostics.append("📈 健康放量")
        
        # 4. 下引線特徵
        if lower_shadow_info['has_lower_shadow']:
            diagnostics.append(f"🔨 下引線(比率{lower_shadow_info['shadow_ratio']}x)")

        # 5. MACD 雙重確認 (方案 C)
        # 判斷 MACD 是否符合剛翻紅或綠柱縮短 (類似 macd_scanner.py 的邏輯)
        if len(hist) >= 3 and is_valid:
            # 重新計算未平滑的 hist 以抓取最近三天的變化 (compute_macd 已回傳最新一天，如果需要前幾天我們自己算或從 hist 取)
            # 這裡我們用手動算一個簡單版的 DIF/DEA
            close_series = hist["Close"]
            ema_fast = close_series.ewm(span=12, adjust=False).mean()
            ema_slow = close_series.ewm(span=26, adjust=False).mean()
            dif = ema_fast - ema_slow
            dea = dif.ewm(span=9, adjust=False).mean()
            full_hist = dif - dea
            
            h_latest = full_hist.iloc[-1]
            h_prev = full_hist.iloc[-2]
            
            # 條件：剛翻紅 (昨天<=0，今天>0) 或是 綠柱縮短 (今天<0，昨天<0，且今天>昨天)
            # 加上 DIF 貼近零軸的條件 (|DIF| / price < 0.2)
            is_macd_starting = False
            dif_latest = dif.iloc[-1]
            if abs(dif_latest) / current_price < 0.2:
                if (h_prev <= 0 and h_latest > 0) or (h_latest < 0 and h_latest > h_prev):
                    is_macd_starting = True
            
            if is_macd_starting:
                diagnostics.insert(0, "🏆 MACD+突破 雙重確認")

        # === 起漲模式判斷（新增）===
        # 1. 判斷位階
        if position_pct < 0.30:
            position_level = "低檔"
        elif position_pct >= 0.70:
            position_level = "高檔"
        else:
            position_level = "中檔"
        
        # 2. 判斷盤整時間長度
        if cons_days <= 14:
            consolidation_period = "短期"
        else:
            consolidation_period = "長期"
        
        # 3. 組合起漲模式標記
        breakout_pattern = ""
        if position_level == "低檔" and consolidation_period == "長期":
            breakout_pattern = "💎 低檔長期盤整起漲"
        elif position_level == "低檔" and consolidation_period == "短期":
            breakout_pattern = "💎 低檔短期起漲"
        elif position_level == "高檔" and consolidation_period == "長期":
            breakout_pattern = "⚡ 高檔長期盤整起漲"
        elif position_level == "高檔" and consolidation_period == "短期":
            breakout_pattern = "⚡ 高檔短期起漲"
        else:
            # 中檔或其他情況
            if consolidation_period == "長期":
                breakout_pattern = "📅 長期盤整起漲"
            else:
                breakout_pattern = "⚡ 短期起漲"


        return {
            "code": stock_code,
            "name": name,
            "category": category,
            "price": safe_round(current_price, 2),
            "change_percent": safe_round(change_percent, 2),
            "reason": reason,
            "diagnostics": diagnostics,
            "volume": int(today_vol) if math.isfinite(today_vol) else 0,
            "vol_ratio": safe_round(vol_ratio, 1) or 0.0,
            "vol_trend_growth": safe_round(vol_trend['growth_rate'] * 100, 1),
            "volume_signal": volume_signal,  # 新增：量能訊號分類
            "inst_net": int(inst_net) if math.isfinite(inst_net) else 0,
            "box_days": int(cons_days),
            "amplitude": safe_round(best_amplitude * 100, 1) or 0.0,
            "box_threshold_used": safe_round(box_threshold * 100, 1),
            "position_pct": safe_round(position_pct * 100, 1) or 0.0,
            "lower_shadow": lower_shadow_info,  # 新增：下引線資訊
            "kd_k": safe_round(k, 1),
            "kd_d": safe_round(d, 1),
            "rsi": safe_round(rsi, 1),
            "macd_dif": safe_round(macd_dif, 3),
            "macd_signal": safe_round(macd_signal, 3),
            "macd_hist": safe_round(macd_hist, 3),
            "bias20": safe_round(bias20, 2),
            "bb_upper": safe_round(bb_upper, 2),
            "bb_mid": safe_round(bb_mid, 2),
            "bb_lower": safe_round(bb_lower, 2),
            "bb_width": safe_round(bb_width * 100, 2),
            "bid_vol": 0, "ask_vol": 0, "bid_ask_ratio": 1.0,
            "is_low_base": bool(is_low_base),
            # === 起漲模式相關欄位（新增）===
            "breakout_pattern": breakout_pattern,
            "position_level": position_level,
            "consolidation_period": consolidation_period
        }
    except Exception as e:
        print(f"Error checking breakout v2 {stock_code}: {e}")
        return None

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
        # Rule: Exclude if stock had > 1.5% rise more than 4 times in the last 7 days
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
                if change >= 0.015: # > 1.5%
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

    except Exception as e:
        print(f"Error checking downtrend {stock_code}: {e}")
        return None
