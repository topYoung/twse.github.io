import urllib.request
import json
import ssl
import time
from typing import Dict, List, Optional

def get_realtime_quotes(stock_codes: List[str]) -> Dict[str, Dict]:
    """
    獲取多檔股票的即時行情（包含等買、等賣數量）
    Args:
        stock_codes: 股票代碼列表 (例如: ['2330', '2317'])
    Returns:
        {
            'stock_code': {
                'bid_vol': 總等買量,
                'ask_vol': 總等賣量,
                'bid_ask_ratio': 買賣比,
                'price': 現價
            }
        }
    """
    if not stock_codes:
        return {}

    results = {}
    
    # TWSE MIS API limits number of stocks per request, usually around 20-50
    # We group them into chunks of 20
    chunk_size = 20
    for i in range(0, len(stock_codes), chunk_size):
        chunk = stock_codes[i:i + chunk_size]
        
        # 判斷是上市還是上櫃 (目前簡單假設，實際應從 twstock 或其他來源判斷)
        # 這裡為了簡化，我們先嘗試 tse, 若無資料再試 otc (或根據代碼長度/範圍)
        # 更準確做法是先查表
        
        # 建立查詢字串 (ex_ch=tse_2330.tw|tse_2317.tw)
        ex_ch_list = []
        for code in chunk:
            ex_ch_list.append(f"tse_{code}.tw")
            ex_ch_list.append(f"otc_{code}.tw")
            
        ex_ch = "|".join(ex_ch_list)
        ts = int(time.time() * 1000)
        url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch={ex_ch}&json=1&delay=0&_={ts}"

        try:
            context = ssl._create_unverified_context()
            with urllib.request.urlopen(url, context=context, timeout=5) as response:
                data = response.read().decode('utf-8')
                json_data = json.loads(data)
                
                if 'msgArray' in json_data:
                    for info in json_data['msgArray']:
                        code = info.get('c')
                        if not code: continue
                        
                        # 'g' 是等買量 (掛單量，多個價位以 '_' 分隔)
                        # 'f' 是等賣量
                        # 'z' 是現價, 'y' 是昨收
                        
                        def sum_volumes(vol_str):
                            if not vol_str or vol_str == '-': return 0
                            try:
                                return sum(int(v) for v in vol_str.split('_') if v and v != '-')
                            except:
                                return 0

                        def safe_float(v, default=0.0):
                            if not v or v == '-': return default
                            try: return float(v)
                            except: return default

                        bid_vol = sum_volumes(info.get('g', '0'))
                        ask_vol = sum_volumes(info.get('f', '0'))
                        price = safe_float(info.get('z', info.get('y', 0)))
                        
                        results[code] = {
                            'bid_vol': bid_vol,
                            'ask_vol': ask_vol,
                            'bid_ask_ratio': round(bid_vol / ask_vol, 2) if ask_vol > 0 else (bid_vol if bid_vol > 0 else 1.0),
                            'price': price
                        }
        except Exception as e:
            print(f"Error fetching realtime quotes for chunk {chunk}: {e}")
            
    return results
