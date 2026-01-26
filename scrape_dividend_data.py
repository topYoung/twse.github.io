"""
從 WantGoo 網站抓取股利資料
使用 Playwright 處理 JavaScript 動態載入
抓取所有 10 頁的股利殖利率資料並存成 JSON
"""
from playwright.sync_api import sync_playwright
import json
import time
from datetime import datetime

BASE_URL = "https://www.wantgoo.com/stock/dividend-yield"

def scrape_dividend_page_playwright(page, page_num):
    """使用 Playwright 抓取單一頁面的股利資料"""
    url = f"{BASE_URL}?page={page_num}" if page_num > 1 else BASE_URL
    
    print(f"正在抓取第 {page_num} 頁: {url}")
    
    try:
        page.goto(url, wait_until='networkidle', timeout=30000)
        
        # 等待表格載入
        page.wait_for_selector('table tbody tr', timeout=15000)
        
        # 使用 JavaScript 提取資料
        stocks = page.evaluate('''() => {
            const rows = Array.from(document.querySelectorAll('table tbody tr'));
            
            return rows.map(row => {
                const cells = Array.from(row.querySelectorAll('td'));
                
                // 確保有足夠的欄位
                if (cells.length < 10) return null;
                
                return {
                    code: cells[1]?.innerText.trim(),
                    name: cells[2]?.innerText.trim(),
                    dividend_yield: cells[4]?.innerText.trim(),
                    cash_dividend: cells[8]?.innerText.trim(),
                    ex_dividend_date: cells[9]?.innerText.trim()
                };
            }).filter(item => item !== null && item.code);
        }''')
        
        # 清理資料
        cleaned_stocks = []
        for stock in stocks:
            try:
                # 清理殖利率（移除 %）
                yield_str = stock['dividend_yield'].replace('%', '').replace(',', '').strip()
                dividend_yield = float(yield_str) if yield_str and yield_str != '-' else 0
                
                # 清理現金股利
                div_str = stock['cash_dividend'].replace(',', '').strip()
                cash_dividend = float(div_str) if div_str and div_str != '-' else 0
                
                cleaned_stocks.append({
                    'code': stock['code'],
                    'name': stock['name'],
                    'cash_dividend': cash_dividend,
                    'dividend_yield': dividend_yield,
                    'ex_dividend_date': stock['ex_dividend_date'] if stock['ex_dividend_date'] != '-' else None
                })
            except Exception as e:
                print(f"  ✗ 清理資料錯誤: {e}, 資料: {stock}")
                continue
        
        print(f"  ✓ 成功抓取 {len(cleaned_stocks)} 筆資料")
        return cleaned_stocks
        
    except Exception as e:
        print(f"  ✗ 錯誤: {e}")
        return []

def scrape_all_pages_playwright(total_pages=10):
    """使用 Playwright 抓取所有頁面的股利資料"""
    all_stocks = []
    
    print(f"開始使用 Playwright 抓取 WantGoo 股利資料（共 {total_pages} 頁）\n")
    
    with sync_playwright() as p:
        # 啟動瀏覽器（headless 模式）
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        # 設定 User-Agent
        page.set_extra_http_headers({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
        
        for page_num in range(1, total_pages + 1):
            stocks = scrape_dividend_page_playwright(page, page_num)
            all_stocks.extend(stocks)
            
            # 避免請求過快
            if page_num < total_pages:
                time.sleep(1)
        
        browser.close()
    
    print(f"\n總共抓取 {len(all_stocks)} 筆股利資料")
    return all_stocks

def save_to_json(data, filename='app/data/dividend_data.json'):
    """儲存資料為 JSON 檔案"""
    import os
    
    # 確保目錄存在
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    
    # 加入更新時間
    output = {
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_count': len(data),
        'stocks': data
    }
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\n✓ 資料已儲存至: {filename}")

if __name__ == "__main__":
    # 抓取所有資料
    dividend_data = scrape_all_pages_playwright(total_pages=10)
    
    if dividend_data:
        # 儲存為 JSON
        save_to_json(dividend_data)
        
        # 顯示前 10 筆資料
        print(f"\n前 10 筆資料預覽:")
        for stock in dividend_data[:10]:
            print(f"  {stock['code']} {stock['name']}: 現金股利 {stock['cash_dividend']}, 殖利率 {stock['dividend_yield']}%, 除息日 {stock['ex_dividend_date']}")
    else:
        print("\n✗ 沒有抓取到任何資料")

