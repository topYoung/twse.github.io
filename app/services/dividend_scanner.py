"""
高股息股票掃描模組
使用本地 JSON 資料檔（從 WantGoo 抓取）+ 即時股價計算
"""

import os
import json
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
# from .categories import TECH_STOCKS, TRAD_STOCKS, STOCK_SUB_CATEGORIES # Unused if we scan all in DB
# from .stock_data import get_yahoo_ticker # Unused in new logic
from .realtime_quotes import get_realtime_prices_batch

# 股利資料檔案路徑
DIVIDEND_DATA_FILE = os.path.join(os.path.dirname(__file__), '../data/dividend_data.json')

# 全域變數用來快取資料
_DIVIDEND_DB_CACHE = {}
_LAST_RELOAD_TIME = 0
_FILE_MOD_TIME = 0

def load_dividend_database():
    """
    載入股利資料庫，支援 Hot-Reload
    檢查檔案修改時間，如果有更新則重新載入
    """
    global _DIVIDEND_DB_CACHE, _LAST_RELOAD_TIME, _FILE_MOD_TIME
    
    try:
        now = time.time()
        # 每 60 秒至少檢查一次檔案狀態，避免過於頻繁的 IO
        if now - _LAST_RELOAD_TIME < 60 and _DIVIDEND_DB_CACHE:
            return _DIVIDEND_DB_CACHE

        if not os.path.exists(DIVIDEND_DATA_FILE):
            print(f"Warning: Dividend data file not found: {DIVIDEND_DATA_FILE}")
            return {}

        # 檢查檔案修改時間
        mod_time = os.path.getmtime(DIVIDEND_DATA_FILE)
        
        # 如果檔案有變更，或者還沒載入過
        if mod_time > _FILE_MOD_TIME or not _DIVIDEND_DB_CACHE:
            print(f"[DividendScanner] Reloading dividend data from {DIVIDEND_DATA_FILE}")
            with open(DIVIDEND_DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 建立快速查詢的字典
                _DIVIDEND_DB_CACHE = {stock['code']: stock for stock in data['stocks']}
                _FILE_MOD_TIME = mod_time
                _LAST_RELOAD_TIME = now
        
        return _DIVIDEND_DB_CACHE

    except Exception as e:
        print(f"Error loading dividend data: {e}")
        return _DIVIDEND_DB_CACHE or {}


def get_dividend_info(stock_code):
    """
    取得單一股票的股利資訊 (從快取)
    """
    db = load_dividend_database()
    return db.get(stock_code)


def get_high_dividend_stocks(min_yield=3.0, top_n=50):
    """
    掃描並篩選高股息股票
    
    1. 從本地資料庫初步篩選 (threshold = min_yield - 0.5)
    2. 取得即時股價 (Real-time)
    3. 重新計算殖利率
    4. 排序並回傳
    """
    # 1. 載入並初步篩選
    db = load_dividend_database()
    candidates = []
    
    # 放寬標準，避免因為舊價格導致的高殖利率被漏掉
    # 但也要避免因為股價大漲導致殖利率大幅下降的股票混入太多
    # 不過我們之後會重算，所以這裡主要是減少 fetch 數量
    pre_filter_yield = max(0, min_yield - 1.0) 
    
    for code, info in db.items():
        # 基本過濾：有配息且殖利率大於門檻
        if info.get('cash_dividend', 0) > 0 and info.get('dividend_yield', 0) >= pre_filter_yield:
            candidates.append(info)
            
    if not candidates:
        return []

    # 2. 取得即時股價
    # 為了效能，我們只對 candidates 進行查詢
    # 如果 candidate 太多，可能需要限制數量 (例如最多查前 300 檔高殖利率的)
    if len(candidates) > 300:
        candidates.sort(key=lambda x: x.get('dividend_yield', 0), reverse=True)
        candidates = candidates[:300]
        
    candidate_codes = [c['code'] for c in candidates]
    
    # 批次取得即時行情 (這會使用 MIS API 或 Fallback)
    # Get batches if too many
    realtime_data_map = {}
    
    # 分批處理，避免 URL 過長或請求過大 (100 檔一批)
    # 使用新的 optimized batch function
    realtime_data_map = get_realtime_prices_batch(candidate_codes)
            
    # 3. 整合與重新計算
    final_results = []
    
    for info in candidates:
        code = info['code']
        quote = realtime_data_map.get(code)
        
        if not quote:
            continue
            
        current_price = quote['price']
        
        # 避免除以零
        if current_price <= 0:
            continue
            
        cash_dividend = info.get('cash_dividend', 0)
        
        # 重新計算殖利率: (現金股利 / 目前股價) * 100
        real_yield = (cash_dividend / current_price) * 100
        
        if real_yield < min_yield:
            continue
            
        # 組合結果
        stock_data = {
            'code': code,
            'name': quote['name'], # 使用即時行情的名稱 (通常較準確)
            'category': '其他', # 暫時預設，稍後可以優化分類
            'price': current_price,
            'change_percent': quote['change_percent'],
            'cash_dividend': cash_dividend,
            'stock_dividend': 0, # WantGoo 目前來源只有現金股利欄位較準確
            'total_dividend': cash_dividend,
            'dividend_yield': round(real_yield, 2), # 使用即時殖利率
            'ex_dividend_date': info.get('ex_dividend_date'),
            'original_yield': info.get('dividend_yield') # Debug/Reference 用
        }
        
        # 嘗試補充分類資訊
        # 這裡簡單處理，如果不影響效能的話
        if 'category' in quote and quote['category']:
             stock_data['category'] = quote['category'] # get_stocks_realtime 可能不回傳 category，視實作而定
        
        # 如果 get_stocks_realtime 沒有回傳 category，我們可以用之前的 map 或 db
        # 不過目前 frontend 不會因為沒有 category 原地爆炸，只是顯示'其他'
        
        final_results.append(stock_data)

    # 4. 排序 (殖利率由高到低)
    final_results.sort(key=lambda x: x['dividend_yield'], reverse=True)
    
    return final_results[:top_n]
