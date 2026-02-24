import urllib.request
import json
import ssl
from lxml import html
import time
from typing import List, Dict, Optional

class WantGooService:
    """
    WantGoo (玩股網) 數據抓取服務
    """
    def __init__(self):
        self.base_url = "https://www.wantgoo.com"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7"
        }
        self.context = ssl._create_unverified_context()

    def _fetch_page(self, url: str) -> Optional[str]:
        """抓取網頁原始碼"""
        try:
            req = urllib.request.Request(url, headers=self.headers)
            with urllib.request.urlopen(req, context=self.context, timeout=10) as response:
                return response.read().decode('utf-8')
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            return None

    def get_major_investors_rank(self) -> List[Dict]:
        """
        獲取主力進出買賣超排行
        URL: https://www.wantgoo.com/stock/major-investors/net-buy-sell-rank
        """
        url = f"{self.base_url}/stock/major-investors/net-buy-sell-rank"
        content = self._fetch_page(url)
        if not content:
            return []

        tree = html.fromstring(content)
        results = []
        
        # 定位買超榜表格的行
        # 根據調研，表格中有 th 包含 "淨買超" 文字
        rows = tree.xpath('//table[.//th[contains(text(), "淨買超")]]/tbody/tr')
        
        for row in rows:
            try:
                cols = row.xpath('./td')
                if len(cols) < 6: continue
                
                # 1. 提取股票名稱與代號
                # 名稱在 <a> 標籤內，代號在 href="/stock/2330" 或 "/stock/etf/0050"
                a_tag = cols[1].xpath('.//a')[0]
                name = a_tag.text_content().strip()
                href = a_tag.get('href', '')
                # 從 href 提取最後一段作為代號
                code = href.split('/')[-1]
                
                # 2. 提取數值
                # 欄位：[0:排名, 1:股票, 2:淨買超(當日), 3:淨買超(累計), 4:收盤價, 5:漲跌%, 6:成交量]
                net_buy = cols[2].text_content().strip().replace(',', '')
                price = cols[4].text_content().strip()
                change_pct_raw = cols[5].text_content().strip()
                # 處理漲跌格式，例如 "(0.13%)" -> "0.13"
                change_pct = change_pct_raw.replace('%', '').replace('(', '').replace(')', '').replace('+', '')
                
                results.append({
                    "code": code,
                    "name": name,
                    "net_buy_sheets": int(net_buy) if net_buy.lstrip('-').isdigit() else 0,
                    "price": float(price) if price.replace('.', '').isdigit() else 0.0,
                    "change_percent": float(change_pct) if change_pct.replace('.', '').replace('-', '').isdigit() else 0.0
                })
            except Exception as e:
                print(f"Error parsing row: {e}")
                continue
                
        return results

    def get_eps_rank(self) -> List[Dict]:
        """
        獲取單季 EPS 排行
        URL: https://www.wantgoo.com/stock/ranking/most-recent-quarter-eps
        """
        url = f"{self.base_url}/stock/ranking/most-recent-quarter-eps"
        content = self._fetch_page(url)
        if not content:
            return []

        tree = html.fromstring(content)
        results = []
        
        # 定位 ID 為 rankingData 的 tbody
        rows = tree.xpath('//tbody[@id="rankingData"]/tr')
        for row in rows:
            try:
                cols = row.xpath('./td')
                if len(cols) < 5: continue
                
                # 欄位索引：[0:排名, 1:代號, 2:名稱, 3:價格, 4:單季EPS]
                code_tag = cols[1].xpath('.//a')
                code = code_tag[0].text_content().strip() if code_tag else cols[1].text_content().strip()
                
                name_tag = cols[2].xpath('.//a')
                name = name_tag[0].text_content().strip() if name_tag else cols[2].text_content().strip()
                
                eps = cols[4].text_content().strip().replace(',', '')
                
                results.append({
                    "code": code,
                    "name": name,
                    "eps": float(eps) if eps.replace('.', '').replace('-', '').isdigit() else 0.0
                })
            except Exception as e:
                print(f"Error parsing EPS row: {e}")
                continue
                
        return results

# 單例模式供外部調用
wantgoo_service = WantGooService()
