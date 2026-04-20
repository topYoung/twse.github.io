import pandas as pd
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor

from app.services.stock_data import get_filtered_stocks, get_stock_history, get_stocks_realtime
from app.services.indicators import compute_macd, compute_kd
from app.services.revenue_service import get_revenue_map


def classify_signal_type(df: pd.DataFrame, kd_d: float, dif_latest: float, hist_latest: float, hist_prev: float, 
                         rt_change: float, vol_ratio: float, mom: float = None, yoy: float = None) -> tuple:
    """
    根據多種條件分類訊號類型
    返回: (signal_type, priority, revenue_status)
    
    優先級排序（越小越優先）：
    1. 營收驅動 MOM > 40% (priority=1)
    2. 底部起漲 (priority=2)  
    3. 營收驅動 MOM 20-40% (priority=3)
    4. 加速起漲 (priority=4)
    5. 突破起漲 (priority=5)
    """
    signal_types = []
    
    # 計算連漲天數
    consecutive_up_days = 0
    if len(df) >= 3:
        for i in range(-2, -4, -1):  # 最後2天
            if i >= -len(df):
                if df['Close'].iloc[i] > df['Close'].iloc[i-1]:
                    consecutive_up_days += 1
                else:
                    break
    
    # 判斷各類型訊號
    results = []
    
    # 類型1: 營收驅動 (優先級最高)
    if mom is not None and yoy is not None:
        if mom > 40 or yoy > 30:
            results.append({
                'type': '💰 營收爆發',
                'priority': 1,
                'revenue_status': f"MOM: {mom:.1f}% | YOY: {yoy:.1f}% ⭐⭐⭐"
            })
        elif mom > 20 and yoy > 15:
            results.append({
                'type': '💰 營收驅動',
                'priority': 3,
                'revenue_status': f"MOM: {mom:.1f}% | YOY: {yoy:.1f}% ✅"
            })
    
    # 類型2: 底部起漲 (KD < 50 + MACD轉折)
    if kd_d < 50:
        is_turning = (hist_latest > hist_prev > 0) or (hist_prev <= 0 < hist_latest)
        if is_turning:
            results.append({
                'type': '🔴 底部起漲',
                'priority': 2,
                'revenue_status': f"KD D: {kd_d:.1f} | MACD轉折"
            })
    
    # 類型3: 加速起漲 (連漲2天 + MACD正向擴大)
    if consecutive_up_days >= 2:
        if hist_latest > 0 and hist_latest > hist_prev:
            results.append({
                'type': '🟢 加速起漲',
                'priority': 4,
                'revenue_status': f"連漲{consecutive_up_days}天 | MACD擴大"
            })
    
    # 類型4: 突破起漲 (漲≥4% + 量≥2x)
    if rt_change >= 4.0 and vol_ratio >= 2.0:
        results.append({
            'type': '🟡 突破起漲',
            'priority': 5,
            'revenue_status': f"漲幅: {rt_change:.1f}% | 量比: {vol_ratio:.1f}x"
        })
    
    # 回傳優先級最高的訊號類型
    if results:
        best = min(results, key=lambda x: x['priority'])
        return best['type'], best['priority'], best['revenue_status']
    
    return '其他訊號', 99, ""


def is_after_consolidation(close_series: pd.Series, hist: pd.Series, dif: pd.Series, close_latest: float, rt_change: float = None) -> bool:
    """
    判斷是否為長期盤整後才出現 MACD 起漲訊號（公開函數，供 theme_scanner 等複用）。
    改進版：根據當日漲幅動態調整盤整條件
    - 低漲幅 (<5%)：嚴格盤整檢查（溫和突破模式）
    - 高漲幅 (>=5%)：寬鬆盤整檢查（事件驅動模式）
    
    參數:
        rt_change: 當日漲幅百分比 (可選，用於動態調整)
    """
    # 確保 close_latest 是浮點數，不是 Series
    if isinstance(close_latest, pd.Series):
        close_latest = float(close_latest.iloc[-1]) if len(close_latest) > 0 else 0
    else:
        close_latest = float(close_latest)
    
    if close_latest == 0:
        return False
    
    # 根據漲幅動態調整門檻
    if rt_change is not None and rt_change >= 5.0:
        # 高振幅模式：放寬條件（漲停或大漲情景）
        hist_threshold = 0.20  # 20% (原 12%)
        dif_range_threshold = 0.12  # 12% (原 8%)
    else:
        # 正常模式：維持較嚴格
        hist_threshold = 0.12  # 12%
        dif_range_threshold = 0.08  # 8%
    
    # 前 15 日柱狀體的波動幅度
    window_hist = hist.iloc[-18:-3] if len(hist) >= 18 else hist
    if len(window_hist) < 5:
        return False
    
    # 條件 1：MACD 柱最大絕對值
    hist_max = float(window_hist.abs().max()) if len(window_hist) > 0 else 0
    hist_max_ratio = hist_max / close_latest
    if hist_max_ratio > hist_threshold:
        return False
    
    # 條件 2：DIF 最近震盪幅度
    window_dif = dif.iloc[-23:-3] if len(dif) >= 23 else dif
    if len(window_dif) >= 5:
        dif_range = float(window_dif.abs().max()) - float(window_dif.abs().min())
        dif_range_ratio = dif_range / close_latest
        if dif_range_ratio > dif_range_threshold:
            return False
    
    return True



def get_macd_breakout_stocks() -> List[Dict[str, Any]]:
    """
    掃描全市場股票，找出 MACD 將要黃金交叉（起漲）的股票。
    條件：
    1. DIF 與 DEA 差距極小 (DIF - DEA 即 histogram 非常靠近 0)
    2. 柱狀體 (Histogram) 由綠縮短，或是剛翻紅
    3. 成交量、價格等基本過濾條件
    """
    # 1. 取得全市場股票基本資訊
    # 1. 取得全市場股票基本資訊 (不要用 get_filtered_stocks 因為它會過濾掉遠離均線的股票)
    from app.services.categories import TECH_STOCKS, TRAD_STOCKS, STOCK_SUB_CATEGORIES, DELISTED_STOCKS
    import twstock
    
    keys_from_map = list(STOCK_SUB_CATEGORIES.keys())
    all_stock_codes = list(set(TECH_STOCKS + TRAD_STOCKS + keys_from_map))
    stock_codes = [s for s in all_stock_codes if s not in DELISTED_STOCKS]
    
    if not stock_codes:
        return []
        
    stock_info_map = {}
    for code in stock_codes:
        name = code
        if code in twstock.codes:
            name = twstock.codes[code].name
        stock_info_map[code] = {'name': name}
    
    # 2. 移除個別 get_stocks_realtime 呼叫，避免盤後觸發大量 target rate limit。
    # 所有需要的最新股價與成交量直接從後續的 history_data (yf.download 批次拿到的資料) 取得
    
    # 3. 取得近期歷史價格 (至少需要 40 天來計算 MACD)
    import yfinance as yf
    from concurrent.futures import ThreadPoolExecutor
    from app.services.stock_data import get_yahoo_ticker
    from app.services.yf_rate_limiter import fetch_stock_history
    
    def fetch_history(code: str):
        try:
            ticker_symbol = get_yahoo_ticker(code)
            df = fetch_stock_history(code, ticker_symbol, period="3mo", interval="1d")
            if not df.empty and len(df) > 30:
                return code, df
        except Exception:
            pass
        return code, None
        
    history_data = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(fetch_history, code) for code in stock_codes]
        for future in futures:
            try:
                code, df = future.result()
                if df is not None:
                    history_data[code] = df
            except Exception:
                pass
    
    breakout_candidates = []
    
    # 先取得營收數據（含月營收增率 MOM 和年營收增率 YOY）
    revenue_map = get_revenue_map()
    
    # 定義判斷條件常數
    # DIF 和 DEA 差異小於價格的多少比例視為「差距小」
    # 對於大部分股票，DIF/DEA 的絕對值大約是價格的 0~5% 不等，差距(hist)則更小
    # 我們以 hist 絕對值與收盤價比例小於 0.005 (0.5%) 作為一組參考，或是 hist 的變化趨勢

    def process_stock(code: str, df: pd.DataFrame) -> Dict[str, Any]:
        """處理單檔股票的技術指標計算與判斷"""
        try:
            if df is None or df.empty or len(df) < 35:
                return None
            
            # 確保資料為時間序列且有收盤價
            if 'Close' not in df.columns:
                return None
                
            close_series = df['Close']
            
            # 使用我們提供的指標模組計算 MACD
            # 因為我們要看歷史走勢，需要算整條序列的 MACD，所以自己算一下 vector 版本的
            fast = 12
            slow = 26
            signal = 9
            
            ema_fast = close_series.ewm(span=fast, adjust=False).mean()
            ema_slow = close_series.ewm(span=slow, adjust=False).mean()
            dif = ema_fast - ema_slow
            dea = dif.ewm(span=signal, adjust=False).mean()
            hist = dif - dea
            
            # 取出近三日的 MACD 柱狀體與價格
            hist_latest = hist.iloc[-1]
            hist_prev = hist.iloc[-2]
            hist_prev2 = hist.iloc[-3]
            
            dif_latest = dif.iloc[-1]
            dea_latest = dea.iloc[-1]
            close_latest = close_series.iloc[-1]
            
            if pd.isna(hist_latest) or pd.isna(hist_prev) or close_latest == 0:
                return None
                
            # 計算前幾日的量縮或價格狀況
            volume_latest = df['Volume'].iloc[-1] if 'Volume' in df.columns else 0
            
            # 判斷邏輯（寬鬆版）
            # 情境 A：綠柱縮短，即將金叉 (hist_prev < 0 且 hist_latest < 0 且 hist_latest > hist_prev)
            # 情境 B：剛翻紅，確認金叉 (hist_prev <= 0 且 hist_latest > 0)
            # 情境 C：MACD 為正且擴大（走強行情）
            
            is_green_shrinking = (hist_latest < 0) and (hist_latest > hist_prev) 
            is_just_red = (hist_prev <= 0) and (hist_latest > 0)
            is_macd_positive_expanding = (hist_latest > 0) and (hist_latest > hist_prev)
            
            # 放寬收斂條件：兩線差距不超過目前股價的一定比例 (例如 10% 以內算合理範圍，因為 DIF/DEA 數值可能較大)
            # 也可以直接看 hist 絕對值是否夠小，代表兩線接近
            is_converging = abs(hist_latest) / close_latest < 0.05
            
            # 放寬條件：DIF 不要離 0 太遠 (例如 |DIF| < price * 0.2)
            is_dif_near_zero = abs(dif_latest) / close_latest < 0.2

            # 盤整期過濾：確保訊號出現前有一段橫盤整理
            # 注意：傳入 rt_change 以支持動態調整（高振幅模式）
            consolidation = is_after_consolidation(close_series, hist, dif, close_latest, rt_change=rt_change)

            # === KD 過濾（寬鬆版：D <= 80 以容納更多走強股票）===
            k, d = compute_kd(df)
            kd_ok = False
            
            if k is not None and d is not None:
                # 統一標準：D <= 80（包含超買情況）
                kd_ok = (d <= 80)

            if (is_green_shrinking or is_just_red or is_macd_positive_expanding) and is_converging and is_dif_near_zero and consolidation and kd_ok:
                
                # 補充即時資訊 (現在直接依賴 df 最後一筆)
                rt_price = close_latest
                rt_change = (close_latest - df['Close'].iloc[-2]) / df['Close'].iloc[-2] * 100 if len(df) > 1 else 0.0
                rt_volume = volume_latest
                
                # === 量能過濾 ===
                # 1. 絕對量：今日成交量至少 500 張（500,000 股），排除冷門股
                MIN_VOLUME_SHARES = 500_000  # 500 張
                if rt_volume < MIN_VOLUME_SHARES:
                    return None
                
                # 2. 計算 5 日均量比，與截圖 VOL 5T 對應
                vol_5d_avg = float(df['Volume'].iloc[-6:-1].mean()) if len(df) >= 6 else float(rt_volume)
                vol_ratio = (rt_volume / vol_5d_avg) if vol_5d_avg > 0 else 1.0
                
                # === 方案 A 新增加的「突破」與「量能」條件 ===
                # 分層判斷：根據漲幅動態調整量價條件
                if rt_change >= 5.0:
                    # 高振幅模式：放寬量價要求（漲停或大漲情景）
                    price_breakout_ok = (rt_change >= 4.0)  # 漲幅 >= 4%
                    volume_breakout_ok = (vol_ratio >= 1.2)  # 量能 >= 1.2x
                else:
                    # 正常模式：嚴格量價要求
                    price_breakout_ok = (rt_change >= 2.5)  # 漲幅 >= 2.5%
                    volume_breakout_ok = (vol_ratio >= 1.5)  # 量能 >= 1.5x
                
                if not (price_breakout_ok and volume_breakout_ok):
                    return None
                
                # 取得營收數據
                revenue_info = revenue_map.get(code, {})
                mom = revenue_info.get('mom')  # 月營收增率
                yoy = revenue_info.get('yoy')  # 年營收增率
                
                # 分類訊號類型
                signal_type, priority, revenue_status = classify_signal_type(
                    df, d, dif_latest, hist_latest, hist_prev, rt_change, vol_ratio, mom, yoy
                )
                
                pattern_desc = ""
                if is_just_red:
                    pattern_desc = "🏆 剛翻紅 + 量價突破"
                elif is_green_shrinking:
                    pattern_desc = "🏆 綠縮短 + 量價突破"
                elif is_macd_positive_expanding:
                    pattern_desc = "🚀 MACD走強 + 量價突破"
                
                # 標記營收加速
                if mom is not None and mom > 10:
                    pattern_desc += " 💰 月增>10%"
                if yoy is not None and yoy > 20:
                    pattern_desc += " 📈 年增>20%"
                    
                return {
                    'code': code,
                    'name': stock_info_map[code]['name'],
                    'price': float(rt_price),
                    'change_percent': float(rt_change),
                    'volume': int(rt_volume),
                    'vol_5d_avg': int(vol_5d_avg),
                    'vol_ratio': round(float(vol_ratio), 2),
                    'signal_type': signal_type,
                    'signal_priority': priority,
                    'revenue_status': revenue_status,
                    'macd': {
                        'dif': float(round(dif_latest, 2)),
                        'dea': float(round(dea_latest, 2)),
                        'hist': float(round(hist_latest, 2))
                    },
                    'kd_d_value': round(float(d), 1),
                    'pattern': pattern_desc,
                    'is_just_red': bool(is_just_red),
                    'revenue': {
                        'mom': round(mom, 2) if mom is not None else None,  # 月營收增率 %
                        'yoy': round(yoy, 2) if yoy is not None else None   # 年營收增率 %
                    }
                }
            return None
            
        except Exception as e:
            # 忽略個別股票的計算錯誤
            return None

    # 多線程加速處理
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = []
        for code, df in history_data.items():
            futures.append(executor.submit(process_stock, code, df))
            
        for future in futures:
            res = future.result()
            if res:
                breakout_candidates.append(res)
    
    # 按訊號優先級排序 + 相同優先級內按漲幅排序
    breakout_candidates.sort(key=lambda x: (x['signal_priority'], -x['change_percent']))
    
    # 套用進階過濾 (高槓桿/高本益比/流動性/弱勢)
    from app.services.advanced_filters import filter_stocks
    breakout_candidates = filter_stocks(breakout_candidates)
    
    return breakout_candidates

