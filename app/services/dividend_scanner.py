"""
高股息股票掃描模組
分析股票的股利發放情況，篩選高殖利率標的
使用台灣證交所公開資料
"""

import yfinance as yf
import pandas as pd
import requests
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from .categories import TECH_STOCKS, TRAD_STOCKS, STOCK_SUB_CATEGORIES
from .stock_data import get_yahoo_ticker
import twstock


# 台灣證交所股利資料 API
TWSE_DIVIDEND_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/t187ap03_L"


def get_dividend_info(stock_code):
    """
    取得單一股票的股利資訊
    使用台灣證交所資料
    
    Returns:
        {
            'cash_dividend': float,  # 現金股利
            'stock_dividend': float,  # 股票股利
            'total_dividend': float,  # 總股利
            'dividend_yield': float,  # 殖利率 (%)
            'ex_dividend_date': str   # 最近除息日
        }
    """
    try:
        # 取得當前價格
        ticker_symbol = get_yahoo_ticker(stock_code)
        ticker = yf.Ticker(ticker_symbol)
        hist = ticker.history(period="5d")
        
        if hist.empty:
            return None
            
        current_price = hist['Close'].iloc[-1]
        
        # 從證交所取得股利資料
        # 使用最近年度資料
        current_year = datetime.now().year
        
        # 嘗試取得最近兩年的股利資料
        cash_div = 0
        stock_div = 0
        ex_date = None
        
        for year in [current_year, current_year - 1]:
            try:
                params = {
                    'response': 'json',
                    'date': f'{year}0101'  # 使用年初日期查詢該年度資料
                }
                
                response = requests.get(TWSE_DIVIDEND_URL, params=params, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if 'data' in data and data['data']:
                        # 尋找該股票代號的資料
                        for row in data['data']:
                            if row[0] == stock_code:  # 股票代號在第一欄
                                # 資料格式: [代號, 名稱, 除息日, 現金股利, 股票股利, ...]
                                try:
                                    cash_div = float(row[3]) if row[3] and row[3] != '-' else 0
                                    stock_div = float(row[4]) if row[4] and row[4] != '-' else 0
                                    ex_date = row[2] if row[2] and row[2] != '-' else None
                                    break
                                except (ValueError, IndexError):
                                    continue
                
                if cash_div > 0 or stock_div > 0:
                    break  # 找到資料就停止
                    
            except Exception:
                continue
        
        # 如果證交所沒資料，嘗試用 twstock 的資料
        if cash_div == 0 and stock_div == 0:
            try:
                if stock_code in twstock.codes:
                    # twstock 沒有直接的股利資料，這裡只是示例
                    # 實際上可能需要其他資料源
                    pass
            except Exception:
                pass
        
        total_dividend = cash_div + stock_div
        
        # 計算殖利率
        dividend_yield = (total_dividend / current_price * 100) if current_price > 0 and total_dividend > 0 else 0
        
        return {
            'cash_dividend': round(float(cash_div), 2),
            'stock_dividend': round(float(stock_div), 2),
            'total_dividend': round(float(total_dividend), 2),
            'dividend_yield': round(float(dividend_yield), 2),
            'ex_dividend_date': ex_date
        }
        
    except Exception as e:
        # print(f"Error getting dividend for {stock_code}: {e}")
        return None


def get_high_dividend_stocks(min_yield=3.0, top_n=50):
    """
    掃描並篩選高股息股票
    
    Args:
        min_yield: 最低殖利率門檻 (%)
        top_n: 回傳前 N 檔股票
    
    Returns:
        股票清單，依殖利率排序
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
        ticker_symbol = get_yahoo_ticker(stock_code)
        ticker = yf.Ticker(ticker_symbol)
        
        # 取得當前價格
        hist = ticker.history(period="1mo")
        if len(hist) < 5:
            return None
            
        today = hist.iloc[-1]
        current_price = today['Close']
        prev_close = hist.iloc[-2]['Close']
        change_percent = ((current_price - prev_close) / prev_close) * 100
        
        # 取得股利資訊
        div_info = get_dividend_info(stock_code)
        if not div_info or div_info['dividend_yield'] < min_yield:
            return None
        
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
            'stock_dividend': div_info['stock_dividend'],
            'total_dividend': div_info['total_dividend'],
            'dividend_yield': div_info['dividend_yield'],
            'ex_dividend_date': div_info['ex_dividend_date']
        }
        
    except Exception:
        return None

