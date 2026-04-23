"""
三大法人（外資、投信、自營商）資料獲取模組
從台灣證交所 API 獲取買賣超資料並實作快取機制
"""

import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import json
import os
from pathlib import Path
from collections import defaultdict

# 快取目錄
CACHE_DIR = Path(__file__).parent.parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

# 證交所 API URLs
TWSE_APIS = {
    'foreign': 'https://www.twse.com.tw/fund/TWT38U',  # 外資
    'trust': 'https://www.twse.com.tw/fund/TWT44U',    # 投信
    'dealer': 'https://www.twse.com.tw/fund/TWT43U'    # 自營商
}

# 法人中文名稱對應
INVESTOR_NAMES = {
    'foreign': '外資',
    'trust': '投信',
    'dealer': '自營商'
}


def get_cache_path(investor_type: str, date: str) -> Path:
    """取得快取檔案路徑"""
    return CACHE_DIR / f"{investor_type}_{date}.json"


def load_from_cache(investor_type: str, date: str) -> Optional[Dict]:
    """從快取載入資料"""
    cache_path = get_cache_path(investor_type, date)
    if cache_path.exists():
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"快取載入失敗: {e}")
    return None


def save_to_cache(investor_type: str, date: str, data: Dict):
    """儲存資料到快取"""
    cache_path = get_cache_path(investor_type, date)
    try:
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"快取儲存失敗: {e}")


def fetch_institutional_data(investor_type: str, date: str) -> Optional[Dict]:
    """
    獲取指定日期的法人買賣超資料
    
    Args:
        investor_type: 'foreign', 'trust', 或 'dealer'
        date: 日期格式 'YYYYMMDD'
    
    Returns:
        資料字典或 None
    """
    # 先檢查快取
    cached_data = load_from_cache(investor_type, date)
    if cached_data:
        print(f"從快取載入 {investor_type} {date} 資料")
        return cached_data
    
    # 從 API 獲取
    if investor_type not in TWSE_APIS:
        print(f"無效的法人類型: {investor_type}")
        return None
    
    url = TWSE_APIS[investor_type]
    params = {
        'response': 'json',
        'date': date
    }
    
    try:
        print(f"正在獲取 {INVESTOR_NAMES[investor_type]} {date} 資料...")
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        # 檢查資料是否有效
        if 'stat' in data and data['stat'] == 'OK' and 'data' in data:
            # 儲存到快取
            save_to_cache(investor_type, date, data)
            return data
        else:
            print(f"API 回傳資料無效: {data.get('stat', 'unknown')}")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"API 請求失敗: {e}")
        return None
    except Exception as e:
        print(f"資料處理錯誤: {e}")
        return None


def parse_institutional_data(raw_data: Dict) -> List[Dict]:
    """
    解析證交所 API 回傳的資料
    
    Returns:
        股票買賣超清單，每個元素包含：
        {
            'stock_code': 股票代碼,
            'stock_name': 股票名稱,
            'buy': 買進股數,
            'sell': 賣出股數,
            'net': 買賣超股數（正數為買超，負數為賣超）
        }
    """
    if not raw_data or 'data' not in raw_data:
        return []
    
    parsed_data = []
    
    for row in raw_data['data']:
        if not row or len(row) < 5:
            continue
        
        try:
            # 證交所 API 資料列可能有不同格式，通常代碼在 index 0 或 1
            # 範例一：[證券代號, 證券名稱, 買進股數, 賣出股數, 買賣超股數]
            # 範例二：[' ', 證券代號, 證券名稱, 買進股數, 賣出股數, 買賣超股數]
            
            offset = 0
            # 檢查第一個欄位是否為純數字代碼，若不是且第二個欄位是，則偏移為 1
            first_col = str(row[0]).strip()
            second_col = str(row[1]).strip()
            
            if not (first_col.isdigit() and len(first_col) == 4):
                if second_col.isdigit() and len(second_col) == 4:
                    offset = 1
                else:
                    continue # 都不是有效代碼則跳過
            
            stock_code = str(row[offset]).strip()
            stock_name = str(row[offset + 1]).strip()
            
            # 移除千分位逗號並轉換為數字
            buy_shares = int(row[offset + 2].replace(',', '')) if row[offset + 2] and row[offset + 2] != '--' else 0
            sell_shares = int(row[offset + 3].replace(',', '')) if row[offset + 3] and row[offset + 3] != '--' else 0
            net_shares = int(row[offset + 4].replace(',', '')) if row[offset + 4] and row[offset + 4] != '--' else 0
            
            parsed_data.append({
                'stock_code': stock_code,
                'stock_name': stock_name,
                'buy': buy_shares,
                'sell': sell_shares,
                'net': net_shares
            })

                
        except (ValueError, IndexError) as e:
            print(f"解析資料列失敗: {row}, 錯誤: {e}")
            continue
    
    return parsed_data


def fetch_historical_data(investor_type: str, days: int = 90) -> Dict[str, List[Dict]]:
    """
    獲取指定天數的歷史資料
    
    Args:
        investor_type: 'foreign', 'trust', 或 'dealer'
        days: 回溯天數（預設90天，約3個月）
    
    Returns:
        {
            'date1': [股票資料],
            'date2': [股票資料],
            ...
        }
    """
    historical_data = {}
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    from concurrent.futures import ThreadPoolExecutor, as_completed

    dates_to_fetch = []
    current_date = start_date
    while current_date <= end_date:
        # Skip weekends (0-4 is Mon-Fri)
        if current_date.weekday() < 5:
            date_str = current_date.strftime('%Y%m%d')
            dates_to_fetch.append(date_str)
        current_date += timedelta(days=1)
    
    print(f"Preparing to fetch {len(dates_to_fetch)} days of data...")
    
    def fetch_and_parse(date_str):
        raw_data = fetch_institutional_data(investor_type, date_str)
        if raw_data:
            return date_str, parse_institutional_data(raw_data)
        return date_str, None

    # Use ThreadPoolExecutor for parallel fetching
    # Limit workers to avoid overwhelming the server (改為 5)
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_date = {executor.submit(fetch_and_parse, d): d for d in dates_to_fetch}
        
        for future in as_completed(future_to_date):
            date_str, parsed = future.result()
            if parsed:
                historical_data[date_str] = parsed
    
    print(f"成功獲取 {len(historical_data)} 個交易日資料")
    return historical_data


def get_investor_summary(investor_type: str, days: int = 30) -> Dict:
    """
    取得法人近期摘要資訊
    
    Returns:
        {
            'name': 法人名稱,
            'total_net_buy': 總買超金額（概估）,
            'active_stocks': 有交易的股票數量,
            'buy_days': 買超天數,
            'sell_days': 賣超天數
        }
    """
    historical_data = fetch_historical_data(investor_type, days)
    
    total_net = 0
    active_stocks = set()
    buy_days = 0
    sell_days = 0
    
    for date_str, stocks in historical_data.items():
        daily_net = sum(stock['net'] for stock in stocks)
        
        if daily_net > 0:
            buy_days += 1
        elif daily_net < 0:
            sell_days += 1
        
        total_net += daily_net
        
        for stock in stocks:
            if stock['net'] != 0:
                active_stocks.add(stock['stock_code'])
    
    return {
        'type': investor_type,
        'name': INVESTOR_NAMES[investor_type],
        'total_net_shares': total_net,
        'active_stocks': len(active_stocks),
        'buy_days': buy_days,
        'sell_days': sell_days,
        'days': days
    }

def fetch_tpex_daily(date_str: str) -> Optional[Dict]:
    """獲取上櫃 (TPEx) 的三大法人買賣超資料"""
    # 轉換西元年 20260408 -> 民國年 115/04/08
    year = int(date_str[:4]) - 1911
    month = date_str[4:6]
    day = date_str[6:8]
    roc_date = f"{year}/{month}/{day}"
    
    url = f"https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php?l=zh-tw&o=json&se=EW&t=D&d={roc_date}"
    cache_path = CACHE_DIR / f"tpex_{date_str}.json"
    
    if cache_path.exists():
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
            
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # 簡單驗證有資料
        if 'tables' in data and len(data['tables']) > 0 and 'data' in data['tables'][0]:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
            return data
    except Exception as e:
        print(f"TPEx Fetch error for {date_str}: {e}")
    return None

def parse_tpex_data(raw_data: Dict) -> Dict[str, Dict]:
    """解析 TPEx JSON 資料，回傳 {code: {foreign, trust, dealer, total}}"""
    results = {}
    if not raw_data or 'tables' not in raw_data or not raw_data['tables']:
        return results
        
    table_data = raw_data['tables'][0].get('data', [])
    for row in table_data:
        try:
            code = str(row[0]).strip()
            # 如果不是 4 碼數字代碼，跳過
            if not (code.isdigit() and len(code) == 4):
                continue
            # 欄位：[10:外資合計買賣超, 13:投信買賣超, 22:自營商合計買賣超]
            foreign = int(row[10].replace(',', '')) if len(row) > 10 else 0
            trust = int(row[13].replace(',', '')) if len(row) > 13 else 0
            dealer = int(row[22].replace(',', '')) if len(row) > 22 else 0
            
            results[code] = {
                'foreign': foreign,
                'trust': trust,
                'dealer': dealer,
                'total': foreign + trust + dealer
            }
        except Exception:
            continue
    return results

def get_5day_institutional_data(stock_code: str) -> Dict:
    """
    讀取最近 5 個交易日的快取檔案，統計特定股票的投信/外資買超情況。

    Returns:
        {
            'trust_days': int,          # 投信買超天數 (net > 0)
            'trust_increasing': bool,   # 投信買超張數是否持續放大 (最近3日遞增)
            'trust_daily': list[int],   # 投信每日買賣超股數 (最近5日，舊→新)
            'foreign_days': int,        # 外資買超天數
            'foreign_increasing': bool, # 外資買超張數是否持續放大
            'foreign_daily': list[int], # 外資每日買賣超股數
        }
    """
    result = {
        'trust_days': 0, 'trust_increasing': False, 'trust_daily': [],
        'foreign_days': 0, 'foreign_increasing': False, 'foreign_daily': [],
    }

    def _find_last_n_cache_files(investor_type: str, n: int = 5) -> list:
        """找最近 n 個有效快取檔（依日期降冪排序後取前 n 個）"""
        pattern = f"{investor_type}_*.json"
        files = sorted(CACHE_DIR.glob(pattern), reverse=True)
        valid = []
        for f in files:
            # 檔名格式：{type}_YYYYMMDD.json
            stem = f.stem  # e.g. "trust_20260415"
            parts = stem.split('_')
            if len(parts) == 2 and parts[1].isdigit() and len(parts[1]) == 8:
                valid.append(f)
                if len(valid) >= n:
                    break
        return list(reversed(valid))  # 由舊到新排列

    for inv_type, key_prefix in [('trust', 'trust'), ('foreign', 'foreign')]:
        files = _find_last_n_cache_files(inv_type, 5)
        daily_nets = []
        for cache_file in files:
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    raw = json.load(f)
                parsed = parse_institutional_data(raw)
                net = 0
                for row in parsed:
                    if row.get('stock_code', '') == stock_code:
                        net = row.get('net', 0)
                        break
                daily_nets.append(net)
            except Exception:
                daily_nets.append(0)

        buy_days = sum(1 for v in daily_nets if v > 0)
        # 持續放大：最後3日都 > 0 且逐日遞增
        increasing = False
        if len(daily_nets) >= 3:
            last3 = daily_nets[-3:]
            increasing = all(v > 0 for v in last3) and last3[0] < last3[1] < last3[2]

        result[f'{key_prefix}_days'] = buy_days
        result[f'{key_prefix}_increasing'] = increasing
        result[f'{key_prefix}_daily'] = daily_nets

    return result


def get_latest_institutional_data() -> Dict[str, Dict]:
    """
    獲取最近一個交易日的所有法人買賣超資料
    Returns:
        {
            'stock_code': {
                'foreign': net_shares,
                'trust': net_shares,
                'dealer': net_shares,
                'total': net_shares
            }
        }
    """
    combined_data = defaultdict(lambda: {'foreign': 0, 'trust': 0, 'dealer': 0, 'total': 0})
    
    # 嘗試從今天往回找最近有資料的一天
    date = datetime.now()
    found_data = False
    
    for i in range(10): # 最多往回找 10 天
        current_date = (date - timedelta(days=i)).strftime('%Y%m%d')
        
        day_results = {}
        for inv in ['foreign', 'trust', 'dealer']:
            raw = fetch_institutional_data(inv, current_date)
            if raw:
                day_results[inv] = parse_institutional_data(raw)
                
        # 加上上櫃 TPEx 資料
        tpex_raw = fetch_tpex_daily(current_date)
        tpex_parsed = parse_tpex_data(tpex_raw) if tpex_raw else {}
        
        if day_results or tpex_parsed:
            # TWSE (上市) 整理
            for inv, stocks in day_results.items():
                for s in stocks:
                    code = s['stock_code']
                    net = s['net']
                    combined_data[code][inv] = net
                    combined_data[code]['total'] += net
                    
            # TPEx (上櫃) 整理
            for code, stats in tpex_parsed.items():
                for inv in ['foreign', 'trust', 'dealer', 'total']:
                    combined_data[code][inv] += stats[inv]
                    
            found_data = True
            break
            
    return dict(combined_data) if found_data else {}


def get_5day_institutional_bulk() -> Dict[str, Dict]:
    """
    讀取最近 5 個交易日的快取，批次取得所有股票的 5 日合計買賣超。
    比逐支呼叫 get_5day_institutional_data 快很多。
    Returns: {code: {'foreign': X, 'trust': Y, 'dealer': Z, 'total': W}} (單位: 股)
    """
    result: Dict[str, Dict] = defaultdict(lambda: {'foreign': 0, 'trust': 0, 'dealer': 0, 'total': 0})

    def _find_last_n_files(investor_type: str, n: int = 5) -> list:
        files = sorted(CACHE_DIR.glob(f"{investor_type}_*.json"), reverse=True)
        valid = []
        for f in files:
            parts = f.stem.split('_')
            if len(parts) == 2 and parts[1].isdigit() and len(parts[1]) == 8:
                valid.append(f)
                if len(valid) >= n:
                    break
        return valid

    # TWSE：外資 / 投信 / 自營商
    for inv_type in ['foreign', 'trust', 'dealer']:
        for cache_file in _find_last_n_files(inv_type, 5):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    raw = json.load(f)
                for row in parse_institutional_data(raw):
                    code = row.get('stock_code', '')
                    net  = row.get('net', 0)
                    if code:
                        result[code][inv_type] += net
                        result[code]['total']   += net
            except Exception:
                pass

    # TPEx（上櫃）
    for cache_file in sorted(CACHE_DIR.glob("tpex_*.json"), reverse=True)[:5]:
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            for code, stats in parse_tpex_data(raw).items():
                for inv in ['foreign', 'trust', 'dealer']:
                    result[code][inv]    += stats[inv]
                result[code]['total'] += stats['total']
        except Exception:
            pass

    return {k: dict(v) for k, v in result.items()}

