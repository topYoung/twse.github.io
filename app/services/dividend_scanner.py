"""
高股息股票掃描模組
使用本地 JSON 資料檔（從 WantGoo 抓取）
"""

import yfinance as yf
import json
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from .categories import TECH_STOCKS, TRAD_STOCKS, STOCK_SUB_CATEGORIES
from .stock_data import get_yahoo_ticker
import twstock


# 股利資料檔案路徑
DIVIDEND_DATA_FILE = os.path.join(os.path.dirname(__file__), '../data/dividend_data.json')


def load_dividend_database():
    """載入股利資料庫"""
    try:
        if os.path.exists(DIVIDEND_DATA_FILE):
            with open(DIVIDEND_DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 建立快速查詢的字典
                return {stock['code']: stock for stock in data['stocks']}
        else:
            print(f"Warning: Dividend data file not found: {DIVIDEND_DATA_FILE}")
            return {}
    except Exception as e:
        print(f"Error loading dividend data: {e}")
        return {}


# 載入股利資料庫（全域變數，只載入一次）
DIVIDEND_DB = load_dividend_database()


def get_dividend_info(stock_code):
    """
    取得單一股票的股利資訊
    從本地資料庫查詢
    
    Returns:
        {
            'cash_dividend': float,
            'dividend_yield': float,
            'ex_dividend_date': str
        }
    """
    try:
        # 從資料庫查詢
        if stock_code in DIVIDEND_DB:
            div_data = DIVIDEND_DB[stock_code]
            return {
                'cash_dividend': div_data['cash_dividend'],
                'dividend_yield': div_data['dividend_yield'],
                'ex_dividend_date': div_data.get('ex_dividend_date')
            }
        
        # 如果資料庫沒有，返回空值
        return {
            'cash_dividend': 0,
            'dividend_yield': 0,
            'ex_dividend_date': None
        }
        
    except Exception as e:
        return None


def get_high_dividend_stocks(min_yield=3.0, top_n=50):
    """
    掃描並篩選高股息股票
    """
    keys_from_map = list(STOCK_SUB_CATEGORIES.keys())
    all_stocks = list(set(TECH_STOCKS + TRAD_STOCKS + keys_from_map))
    
    results = []
    
    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = [executor.submit(check_dividend, code, min_yield) for code in all_stocks]
        for future in futures:
            res = future.result()
            if res:
                results.append(res)
    
    # 依殖利率排序
    results.sort(key=lambda x: x['dividend_yield'], reverse=True)
    return results[:top_n]


def check_dividend(stock_code, min_yield=3.0):
    """
    檢查單一股票是否符合高股息條件
    """
    try:
        # 取得股利資訊
        div_info = get_dividend_info(stock_code)
        if not div_info or div_info['dividend_yield'] < min_yield:
            return None
        
        # 取得當前價格
        ticker_symbol = get_yahoo_ticker(stock_code)
        ticker = yf.Ticker(ticker_symbol)
        hist = ticker.history(period="1mo")
        
        if len(hist) < 5:
            return None
            
        today = hist.iloc[-1]
        current_price = today['Close']
        prev_close = hist.iloc[-2]['Close']
        change_percent = ((current_price - prev_close) / prev_close) * 100
        
        # 取得股票名稱和分類
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
            'code': stock_code,
            'name': name,
            'category': category,
            'price': round(float(current_price), 2),
            'change_percent': round(float(change_percent), 2),
            'cash_dividend': div_info['cash_dividend'],
            'stock_dividend': 0,  # WantGoo 資料沒有區分股票股利
            'total_dividend': div_info['cash_dividend'],
            'dividend_yield': div_info['dividend_yield'],
            'ex_dividend_date': div_info['ex_dividend_date']
        }
        
    except Exception:
        return None
