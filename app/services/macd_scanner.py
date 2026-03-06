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
    all_stocks = get_filtered_stocks()
    if not all_stocks:
        return []
    
    # 建立以股號為 key 的字典方便對照資訊
    stock_info_map = {s['code']: s for s in all_stocks}
    stock_codes = list(stock_info_map.keys())
    
    # 2. 獲取盤中即時報價，確認當日狀況
    realtime_data = get_stocks_realtime(stock_codes)
    realtime_map = {d['code']: d for d in realtime_data}
    
    history_data = {}
    
    # 3. 取得近期歷史價格 (至少需要 40 天來計算 MACD)
    def fetch_history(code: str):
        try:
            hist_dict = get_stock_history(code, interval='1d')
            # 轉換為 DataFrame 給後續處理
            if hist_dict and 'candlestick' in hist_dict and len(hist_dict['candlestick']) > 0:
                data = []
                for item in hist_dict['candlestick']:
                    # {'time': '2023-01-01', 'open': ..., 'high': ..., 'low': ..., 'close': ..., 'volume': ...}
                    data.append({
                        'Date': pd.to_datetime(item['time']),
                        'Open': item['open'],
                        'High': item['high'],
                        'Low': item['low'],
                        'Close': item['close'],
                        'Volume': item['volume']
                    })
                df = pd.DataFrame(data)
                df.set_index('Date', inplace=True)
                return code, df
        except Exception as e:
            pass
        return code, None
        
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(fetch_history, code) for code in stock_codes]
        for future in futures:
            code, df = future.result()
            if df is not None:
                history_data[code] = df
                

    
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
            # 情境 B：剛翻紅，確認金叉 (hist_prev <= 0 且 hist_latest > 0 且 hist_latest 的值極小)
            
            is_green_shrinking = (hist_latest < 0) and (hist_latest > hist_prev) and (hist_prev > hist_prev2)
            is_just_red = (hist_prev <= 0) and (hist_latest > 0)
            
            # 收斂條件：兩線差距很小 (DIF 與 DEA 差距佔股價的比例要夠小)
            # hist 其實就是 DIF - DEA，確保這個差距小於目前股價的 0.8%
            is_converging = abs(hist_latest) / close_latest < 0.008
            
            # 放寬條件：只要綠柱縮短或剛翻紅，並且 DIF 不要離 0 太遠 (例如 |DIF| < price * 0.05)
            is_dif_near_zero = abs(dif_latest) / close_latest < 0.05

            if (is_green_shrinking or is_just_red) and is_converging and is_dif_near_zero:
                
                # 可選：限制 DIF 不能太高，若 DIF 很高表示在高檔，可能只是高檔震盪。
                # 我們偏好 DIF < 0 或稍微大於 0 (低基期起漲)
                # 若只想找真的低檔起漲，可以加上 dif_latest < (close_latest * 0.05) 等等
                
                # 補充即時資訊
                rt_info = realtime_map.get(code, {})
                rt_price = rt_info.get('price', close_latest)
                rt_change = rt_info.get('change_percent', 0.0)
                rt_volume = rt_info.get('volume', volume_latest)
                
                pattern_desc = ""
                if is_just_red:
                    pattern_desc = "🔴 剛翻紅 (黃金交叉)"
                elif is_green_shrinking:
                    pattern_desc = "🟢 綠柱縮短 (即將金叉)"
                
                # 簡單過濾：排除成交量太小或無流動性的標的 (例如當日成交量 > 100 張)
                if rt_volume < 100:
                    return None
                    
                return {
                    'code': code,
                    'name': stock_info_map[code]['name'],
                    'price': rt_price,
                    'change_percent': rt_change,
                    'volume': rt_volume,
                    'macd': {
                        'dif': round(dif_latest, 2),
                        'dea': round(dea_latest, 2),
                        'hist': round(hist_latest, 2)
                    },
                    'pattern': pattern_desc,
                    'is_just_red': is_just_red
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

