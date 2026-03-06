import pandas as pd
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor

from app.services.stock_data import get_filtered_stocks, get_stock_history, get_stocks_realtime
from app.services.indicators import compute_macd

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
    
    def fetch_history(code: str):
        try:
            ticker_symbol = get_yahoo_ticker(code)
            ticker = yf.Ticker(ticker_symbol)
            df = ticker.history(period="3mo")
            if not df.empty and len(df) > 30:
                # 確保時區與格式正確
                if df.index.tz is not None:
                    df.index = df.index.tz_localize(None)
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
            
            # 判斷邏輯
            # 情境 A：綠柱縮短，即將金叉 (hist_prev < 0 且 hist_latest < 0 且 hist_latest > hist_prev)
            # 情境 B：剛翻紅，確認金叉 (hist_prev <= 0 且 hist_latest > 0)
            
            is_green_shrinking = (hist_latest < 0) and (hist_latest > hist_prev) 
            is_just_red = (hist_prev <= 0) and (hist_latest > 0)
            
            # 放寬收斂條件：兩線差距不超過目前股價的一定比例 (例如 10% 以內算合理範圍，因為 DIF/DEA 數值可能較大)
            # 也可以直接看 hist 絕對值是否夠小，代表兩線接近
            is_converging = abs(hist_latest) / close_latest < 0.05
            
            # 放寬條件：DIF 不要離 0 太遠 (例如 |DIF| < price * 0.2)
            is_dif_near_zero = abs(dif_latest) / close_latest < 0.2

            if (is_green_shrinking or is_just_red) and is_converging and is_dif_near_zero:
                
                # 補充即時資訊 (現在直接依賴 df 最後一筆)
                rt_price = close_latest
                rt_change = (close_latest - df['Close'].iloc[-2]) / df['Close'].iloc[-2] * 100 if len(df) > 1 else 0.0
                rt_volume = volume_latest
                
                pattern_desc = ""
                if is_just_red:
                    pattern_desc = "🔴 剛翻紅 (黃金交叉)"
                elif is_green_shrinking:
                    pattern_desc = "🟢 綠柱縮短 (即將金叉)"
                
                # 簡單過濾：排除成交量太小或無流動性的標的 (例如當日成交量 > 100 張)
                if rt_volume < 50:
                    return None
                    
                return {
                    'code': code,
                    'name': stock_info_map[code]['name'],
                    'price': float(rt_price),
                    'change_percent': float(rt_change),
                    'volume': int(rt_volume),
                    'macd': {
                        'dif': float(round(dif_latest, 2)),
                        'dea': float(round(dea_latest, 2)),
                        'hist': float(round(hist_latest, 2))
                    },
                    'pattern': pattern_desc,
                    'is_just_red': bool(is_just_red)
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
    
    # 優先排序：先按照剛翻紅排前面，然後按照漲幅排序
    breakout_candidates.sort(key=lambda x: (not x['is_just_red'], -x['change_percent']))
    
    return breakout_candidates

