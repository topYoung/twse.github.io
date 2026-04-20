import pandas as pd
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor

from app.services.stock_data import get_filtered_stocks, get_stock_history, get_stocks_realtime
from app.services.indicators import compute_macd, compute_kd
from app.services.revenue_service import get_revenue_map


def compute_bollinger(close_series: pd.Series, period: int = 20, std_mult: float = 2.0):
    """
    計算布林通道相關指標
    返回: (bbw, bbw_ema3, percent_b) 皆為 pd.Series
    - bbw: 布林帶寬 (upper-lower)/middle * 100
    - bbw_ema3: BBW 的 3 日 EMA
    - percent_b: %B = (close - lower) / (upper - lower) * 100
    """
    sma = close_series.rolling(period).mean()
    std = close_series.rolling(period).std(ddof=0)
    upper = sma + std_mult * std
    lower = sma - std_mult * std
    bbw = (upper - lower) / sma * 100
    bbw_ema3 = bbw.ewm(span=3, adjust=False).mean()
    bb_range = upper - lower
    percent_b = ((close_series - lower) / bb_range * 100).where(bb_range > 0)
    return bbw, bbw_ema3, percent_b


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

    # 批次載入營收、法人數據（只載一次，避免重複 I/O）
    revenue_map = get_revenue_map()

    from app.services.institutional_data import get_latest_institutional_data
    inst_map = get_latest_institutional_data()   # {code: {foreign, trust, dealer, total}}
    
    # 定義判斷條件常數
    # DIF 和 DEA 差異小於價格的多少比例視為「差距小」
    # 對於大部分股票，DIF/DEA 的絕對值大約是價格的 0~5% 不等，差距(hist)則更小
    # 我們以 hist 絕對值與收盤價比例小於 0.005 (0.5%) 作為一組參考，或是 hist 的變化趨勢

    def process_stock(code: str, df: pd.DataFrame) -> Dict[str, Any]:
        """以布林帶寬 + MACD 判斷起漲訊號"""
        try:
            if df is None or df.empty or len(df) < 35:
                return None
            if 'Close' not in df.columns:
                return None

            close_series = df['Close']
            close_latest = float(close_series.iloc[-1])
            if close_latest == 0:
                return None

            # === 布林通道 ===
            bbw, bbw_ema3, percent_b = compute_bollinger(close_series)
            bbw_latest    = bbw.iloc[-1]
            bbw_prev      = bbw.iloc[-2]
            bbw_ema_latest= bbw_ema3.iloc[-1]
            pb_latest     = percent_b.iloc[-1]   # %B 最新值

            if pd.isna(bbw_latest) or pd.isna(pb_latest):
                return None

            # === MACD ===
            ema_fast = close_series.ewm(span=12, adjust=False).mean()
            ema_slow = close_series.ewm(span=26, adjust=False).mean()
            dif  = ema_fast - ema_slow
            dea  = dif.ewm(span=9, adjust=False).mean()
            hist = dif - dea

            hist_latest = float(hist.iloc[-1])
            hist_prev   = float(hist.iloc[-2])
            dif_latest  = float(dif.iloc[-1])
            dea_latest  = float(dea.iloc[-1])

            if pd.isna(hist_latest) or pd.isna(hist_prev):
                return None

            # === 布林條件 ===
            bb_expanding   = bbw_latest > bbw_prev                        # BBW 持續擴大
            bb_above_ema   = bbw_latest > bbw_ema_latest                  # BBW 突破自身 EMA

            # === MACD 條件 ===
            macd_just_pos  = (hist_prev <= 0) and (hist_latest > 0)       # OSC 剛翻正
            macd_converging= (hist_latest < 0 and                          # 負柱快速縮短
                              hist_latest > hist_prev and
                              abs(hist_latest) / close_latest < 0.008)    # 距離 0 < 0.8%
            macd_expanding = (hist_latest > 0) and (hist_latest > hist_prev)  # 正柱擴大

            # === 訊號分類 ===
            # 已起漲：BBW 突破 EMA + %B > 80% + MACD 翻正或正向擴大
            if (bb_expanding and bb_above_ema and
                    (macd_just_pos or macd_expanding) and
                    pb_latest > 80):
                signal_type = '🚀 已起漲'
                signal_priority = 1
                signal_desc = (f"%B:{pb_latest:.0f}% | "
                               f"BBW:{bbw_latest:.1f}%>EMA:{bbw_ema_latest:.1f}% | "
                               f"{'MACD剛翻正' if macd_just_pos else 'MACD正向擴大'}")

            # 即將起漲：BBW 開始擴大 + %B > 60% + MACD 即將翻正
            elif (bb_expanding and
                      (macd_converging or macd_just_pos) and
                      pb_latest > 60):
                signal_type = '⚡ 即將起漲'
                signal_priority = 2
                signal_desc = (f"%B:{pb_latest:.0f}% | "
                               f"BBW擴大:{bbw_latest:.1f}% | "
                               f"OSC收斂中:{hist_latest:.2f}")
            else:
                return None

            # === 量能過濾 ===
            volume_latest = int(df['Volume'].iloc[-1]) if 'Volume' in df.columns else 0
            if volume_latest < 500_000:   # 最少 500 張
                return None

            vol_5d_avg = float(df['Volume'].iloc[-6:-1].mean()) if len(df) >= 6 else float(volume_latest)
            vol_ratio  = (volume_latest / vol_5d_avg) if vol_5d_avg > 0 else 1.0
            if vol_ratio < 1.2:           # 量比至少 1.2x
                return None

            rt_change = ((close_latest - float(df['Close'].iloc[-2])) /
                         float(df['Close'].iloc[-2]) * 100) if len(df) > 1 else 0.0

            # KD
            k_val, d_val = compute_kd(df)
            kd_d = round(float(d_val), 1) if d_val is not None else None

            # 營收
            revenue_info = revenue_map.get(code, {})
            mom = revenue_info.get('mom')
            yoy = revenue_info.get('yoy')

            # 三大法人（最新一日）
            inst = inst_map.get(code, {})
            inst_foreign = inst.get('foreign', 0)   # 外資淨買超（股）
            inst_trust   = inst.get('trust',   0)   # 投信淨買超
            inst_dealer  = inst.get('dealer',  0)   # 自營商淨買超
            inst_total   = inst.get('total',   0)   # 三大合計

            # 高低檔位置（近 60 日）
            window = df['Close'].iloc[-60:] if len(df) >= 60 else df['Close']
            low60  = float(window.min())
            high60 = float(window.max())
            price_range = high60 - low60
            position_pct = round((close_latest - low60) / price_range * 100, 1) if price_range > 0 else 50.0
            if position_pct <= 35:
                position_label = '🟢 低檔'
            elif position_pct >= 65:
                position_label = '🔴 高檔'
            else:
                position_label = '🟡 中間'

            return {
                'code': code,
                'name': stock_info_map[code]['name'],
                'price': float(close_latest),
                'change_percent': float(rt_change),
                'volume': int(volume_latest),
                'vol_ratio': round(float(vol_ratio), 2),
                'signal_type': signal_type,
                'signal_priority': signal_priority,
                'signal_desc': signal_desc,
                'macd': {
                    'dif':  float(round(dif_latest,  2)),
                    'dea':  float(round(dea_latest,  2)),
                    'hist': float(round(hist_latest, 2))
                },
                'bollinger': {
                    'bbw':       round(float(bbw_latest),     2),
                    'bbw_ema':   round(float(bbw_ema_latest), 2),
                    'percent_b': round(float(pb_latest),      1)
                },
                'kd_d_value': kd_d,
                'institutional': {
                    'foreign': int(inst_foreign),
                    'trust':   int(inst_trust),
                    'dealer':  int(inst_dealer),
                    'total':   int(inst_total)
                },
                'position': {
                    'pct':   position_pct,
                    'label': position_label,
                    'low60': round(low60,  2),
                    'high60': round(high60, 2)
                },
                'revenue': {
                    'mom': round(mom, 2) if mom is not None else None,
                    'yoy': round(yoy, 2) if yoy is not None else None
                }
            }

        except Exception:
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
    
    # 已起漲優先，相同優先級內按漲幅排序
    breakout_candidates.sort(key=lambda x: (x['signal_priority'], -x['change_percent']))
    
    # 套用進階過濾 (高槓桿/高本益比/流動性/弱勢)
    from app.services.advanced_filters import filter_stocks
    breakout_candidates = filter_stocks(breakout_candidates)
    
    return breakout_candidates

