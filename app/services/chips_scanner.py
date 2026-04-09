import yfinance as yf
from app.services.institutional_data import get_latest_institutional_data
from app.services.stock_data import get_yahoo_ticker, get_stocks_realtime
from concurrent.futures import ThreadPoolExecutor

def scan_high_trust_ratio():
    """
    掃描近期投信大量買超且佔總股本比例較高 (投本比) 的潛力股
    """
    chips_data = get_latest_institutional_data()
    
    # 步驟 1: 找出投信買超大於 100 張 (100,000 股) 的候選股票
    candidates = []
    for code, stats in chips_data.items():
        if stats.get('trust', 0) > 100_000:
            candidates.append(code)
            
    results = []
    
    def fetch_and_calculate(code):
        try:
            ticker = get_yahoo_ticker(code)
            info = yf.Ticker(ticker).fast_info
            
            # 使用 fast_info 可以大幅增進速度
            shares_out = info.shares
            if not shares_out or shares_out == 0:
                return None
                
            trust_buy_shares = chips_data[code]['trust']
            ratio = (trust_buy_shares / shares_out) * 100
            
            # 過濾出投本比超過 0.1% 的股票
            if ratio >= 0.1:
                return {
                    'code': code,
                    'trust_net_buy': trust_buy_shares // 1000, # 轉換為張數
                    'trust_ratio': round(ratio, 2),
                    'shares_outstanding': shares_out
                }
        except Exception as e:
            pass
        return None
        
    # 步驟 2: 解析股數計算佔比
    with ThreadPoolExecutor(max_workers=10) as executor:
        for res in executor.map(fetch_and_calculate, candidates):
            if res:
                results.append(res)
                
    codes = [r['code'] for r in results]
    if not codes: 
        return []
        
    # 步驟 3: 結合即時盤中資料與產業別資訊
    realtime_data = get_stocks_realtime(codes)
    rt_map = {r['code']: r for r in realtime_data}
    
    final_results = []
    for r in results:
        rt = rt_map.get(r['code'], {})
        # 過濾掉太小或無效的冷門股
        if rt.get('price', 0) > 5 and rt.get('volume', 0) > 500:
            merged = {**rt, **r}
            final_results.append(merged)
            
    # 以投本比排序
    final_results.sort(key=lambda x: x['trust_ratio'], reverse=True)
    return final_results

def scan_dealer_net_buy():
    """
    掃描近期自營商大量買超的股票
    """
    chips_data = get_latest_institutional_data()
    
    candidates = []
    # 篩選自營商當日買超大於 500 張 (500,000 股) 的股票
    for code, stats in chips_data.items():
        if stats.get('dealer', 0) > 500_000:
            candidates.append({
                'code': code,
                'dealer_net_buy': stats['dealer'] // 1000 # 轉換為張數
            })
            
    codes = [c['code'] for c in candidates]
    if not codes: 
        return []
    
    realtime_data = get_stocks_realtime(codes)
    rt_map = {r['code']: r for r in realtime_data}
    
    final_results = []
    for c in candidates:
        rt = rt_map.get(c['code'], {})
        
        # 簡單過濾：量大於 1000 張
        if rt.get('price', 0) > 10 and rt.get('volume', 0) > 1000:
            merged = {**rt, **c}
            final_results.append(merged)
            
    # 依買超量排序
    final_results.sort(key=lambda x: x['dealer_net_buy'], reverse=True)
    return final_results
