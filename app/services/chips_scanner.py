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


def scan_foreign_surge(min_recent_buy: int = 500, zscore_threshold: float = 2.0, zscore_days: int = 252):
    """
    掃描外資「突然」大量買超的股票。

    改進版：使用 252 日時間序列 Z-Score 偵測異常買超。
        Z = (今日淨買超 - N日均值) / N日標準差

    相較舊版「倍數法」的優勢：
    - 自動適應各股波動特性（大型股與小型股買超量級差異大）
    - 同時考量均值與離散程度，統計意義明確
    - Z >= 2 表示距均值 2 個標準差，歷史約 2.5% 機率出現

    Args:
        min_recent_buy: 最低近日買超門檻 (張，預設 500 張)
        zscore_threshold: Z-Score 門檻 (預設 2.0)
        zscore_days: 計算 Z-Score 的歷史天數 (預設 252 個交易日，約 1 年)

    Returns:
        外資突然大買的股票清單，依 Z-Score 由大到小排序
    """
    import statistics
    from app.services.institutional_data import fetch_historical_data

    # calendar days = 交易日 × 1.5 以涵蓋週末、假日、長假
    calendar_days = int(zscore_days * 1.5) + 30
    historical_data = fetch_historical_data('foreign', days=calendar_days)

    if not historical_data:
        return []

    sorted_dates = sorted(historical_data.keys(), reverse=True)
    if len(sorted_dates) < 5:
        return []

    # 最近一個交易日
    recent_date = sorted_dates[0]
    recent_stocks_list = historical_data.get(recent_date, [])
    if not recent_stocks_list:
        return []

    recent_stocks = {s['stock_code']: s for s in recent_stocks_list}

    # 歷史基準：排除最近 1 天，取前面 zscore_days 個交易日
    baseline_dates = sorted_dates[1:zscore_days + 1]

    # 對每支股票建立 net buy 時間序列（含負值/0，正確反映分佈）
    all_stock_nets: dict = {code: [] for code in recent_stocks}

    for date_str in baseline_dates:
        day_map = {s['stock_code']: s['net'] for s in historical_data.get(date_str, [])}
        for code in recent_stocks:
            all_stock_nets[code].append(day_map.get(code, 0))

    # 計算 Z-Score 並篩選
    surge_candidates = []
    for code, stock_data in recent_stocks.items():
        recent_net = stock_data['net']
        recent_net_lots = recent_net // 1000  # 股 → 張

        if recent_net_lots < min_recent_buy:
            continue

        net_series = all_stock_nets.get(code, [])
        if len(net_series) < 20:  # 至少 20 個交易日才有統計意義
            continue

        mean_val = statistics.mean(net_series)
        std_val = statistics.stdev(net_series) if len(net_series) >= 2 else 0

        # std floor：防止極小 std 導致 Z 值虛高
        # floor = max(|mean| × 30%, 10,000 股 = 10 張)
        std_floor = max(abs(mean_val) * 0.30, 10_000)
        effective_std = max(std_val, std_floor)

        z_score = (recent_net - mean_val) / effective_std

        # 篩選：Z-Score 達標，或絕對大量（>= 5000 張，不論 Z 值）
        if z_score >= zscore_threshold or recent_net_lots >= 5000:
            surge_candidates.append({
                'code': code,
                'name': stock_data['stock_name'],
                'foreign_net_buy': recent_net_lots,
                'hist_mean': round(mean_val / 1000, 1),   # 張
                'hist_std': round(std_val / 1000, 1),     # 張
                'z_score': round(z_score, 2),
                'date': recent_date,
            })

    if not surge_candidates:
        return []

    # 結合即時盤中資料
    codes = [c['code'] for c in surge_candidates]
    realtime_data = get_stocks_realtime(codes)
    rt_map = {r['code']: r for r in realtime_data}

    final_results = []
    for c in surge_candidates:
        rt = rt_map.get(c['code'], {})
        if rt.get('price', 0) > 5 and rt.get('volume', 0) > 200:
            final_results.append({**rt, **c})

    # 依 Z-Score 由大到小排序
    final_results.sort(key=lambda x: x['z_score'], reverse=True)
    return final_results
