import yfinance as yf
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict

def get_recent_net_sell_streaks(investor_type: str, days: int = 5) -> set:
    """取得最近幾日連續賣超的股票集合"""
    from app.services.institutional_data import fetch_historical_data
    # 獲取最近 10 天，確保能湊滿 5 個交易日
    hist_data = fetch_historical_data(investor_type, days=15)
    
    if not hist_data:
        return set()
        
    sorted_dates = sorted(hist_data.keys(), reverse=True)
    recent_dates = sorted_dates[:days]
    
    if len(recent_dates) < days:
        return set()
        
    consecutive_sell = set()
    first_day = True
    
    for d in recent_dates:
        day_sells = set()
        for stock in hist_data[d]:
            if stock['net'] < 0:
                day_sells.add(stock['stock_code'])
                
        if first_day:
            consecutive_sell = day_sells
            first_day = False
        else:
            consecutive_sell = consecutive_sell.intersection(day_sells)
            
    return consecutive_sell

def filter_stocks(candidates: List[Dict]) -> List[Dict]:
    """
    進行進階過濾，剔除高槓桿、高本益比、虧損或技術籌碼弱勢的個股
    """
    if not candidates:
        return []

    try:
        from app.services.stock_data import get_yahoo_ticker
    except ImportError:
        def get_yahoo_ticker(code):
            return f"{code}.TW"

    # 1. 預先取得籌碼資料 (近5日連續賣超)
    try:
        foreign_continuous_sells = get_recent_net_sell_streaks('foreign', 5)
        trust_continuous_sells = get_recent_net_sell_streaks('trust', 5)
        continuous_sell_stocks = foreign_continuous_sells.union(trust_continuous_sells)
    except Exception as e:
        print(f"Error fetching institutional sell data: {e}")
        continuous_sell_stocks = set()

    valid_candidates = []

    def check_stock(candidate: Dict):
        code = candidate.get('code')
        if not code:
            return candidate

        try:
            ticker_symbol = get_yahoo_ticker(code)
            t = yf.Ticker(ticker_symbol)
            
            # 使用 fast_info 跟 info
            info = t.info
            
            # 1. 基本面（高槓桿）： 負債比率 > 60% (Debt to Equity > 150%)
            dte = info.get('debtToEquity')
            if dte is not None and dte > 150:
                print(f"[{code}] Filtered out by High Leverage: D/E={dte}")
                return None
                
            # 2. 基本面（高本益比或虧損）： 本益比 > 40 倍 或 近四季 EPS 為負數
            pe = info.get('trailingPE')
            eps = info.get('trailingEps')
            
            if (pe is not None and pe > 40) or (eps is not None and eps < 0):
                print(f"[{code}] Filtered out by PE/EPS: PE={pe}, EPS={eps}")
                return None
                
            # 3. 技術與籌碼面（弱勢）：股價在季線（60MA）之下，且季線下彎 ＋ 近 5 日投信或外資連續賣超
            if code in continuous_sell_stocks:
                hist = t.history(period="4mo")
                if len(hist) >= 60:
                    ma60 = hist['Close'].rolling(window=60).mean()
                    latest_ma60 = ma60.iloc[-1]
                    prev_ma60 = ma60.iloc[-2]
                    current_price = hist['Close'].iloc[-1]
                    
                    if current_price < latest_ma60 and latest_ma60 < prev_ma60:
                        print(f"[{code}] Filtered out by Weak Trend + Inst Sell: Price={current_price:.2f}, 60MA={latest_ma60:.2f}")
                        return None
            
            return candidate
        except Exception as e:
            print(f"[{code}] Error during validation, keeping stock: {e}")
            return candidate

    # 使用多執行緒加速檢查
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = executor.map(check_stock, candidates)
        for res in futures:
            if res is not None:
                valid_candidates.append(res)
                
    return valid_candidates
