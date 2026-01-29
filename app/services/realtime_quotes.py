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


def get_intraday_candle(stock_code: str) -> Optional[Dict]:
    """
    獲取單一股票的盤中即時 K 棒
    
    Args:
        stock_code: 股票代碼 (例如: '2330')
    
    Returns:
        {
            'open': float,
            'high': float,
            'low': float,
            'close': float,
            'volume': int,
            'yesterday_close': float,
            'change_percent': float
        }
        若獲取失敗則回傳 None
    """
    try:
        ex_ch = f"tse_{stock_code}.tw|otc_{stock_code}.tw"
        ts = int(time.time() * 1000)
        url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch={ex_ch}&json=1&delay=0&_{ts}"
        
        context = ssl._create_unverified_context()
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, context=context, timeout=5) as response:
            data = response.read().decode('utf-8')
            json_data = json.loads(data)
            
            if 'msgArray' not in json_data or len(json_data['msgArray']) == 0:
                return None
            
            info = json_data['msgArray'][0]
            
            def safe_float(v, default=0.0):
                if not v or v == '-': return default
                try: return float(v)
                except: return default
            
            def safe_int(v, default=0):
                if not v or v == '-': return default
                try: return int(v)
                except: return default
            
            yesterday_close = safe_float(info.get('y'))
            current_price = safe_float(info.get('z'), yesterday_close)  # 若無成交用昨收
            open_price = safe_float(info.get('o'), yesterday_close)
            high_price = safe_float(info.get('h'), current_price)
            low_price = safe_float(info.get('l'), current_price)
            volume = safe_int(info.get('v'))  # 成交量（張）
            
            # 計算漲幅
            change_percent = ((current_price - yesterday_close) / yesterday_close * 100) if yesterday_close > 0 else 0.0
            
            return {
                'open': open_price,
                'high': high_price,
                'low': low_price,
                'close': current_price,
                'volume': volume * 1000,  # 轉換為股數（1張=1000股）
                'yesterday_close': yesterday_close,
                'change_percent': round(change_percent, 2)
            }
    except Exception as e:
        print(f"Error fetching intraday candle for {stock_code}: {e}")
        return None


def get_batch_intraday_candles(stock_codes: List[str]) -> Dict[str, Optional[Dict]]:
    """
    批次獲取多檔股票的盤中即時 K 棒（優化效能）
    
    Args:
        stock_codes: 股票代碼列表
    
    Returns:
        {
            'stock_code': {candle_data},
            ...
        }
    """
    results = {}
    
    # 每次請求最多 5 檔 (降低被擋機率)
    chunk_size = 5
    for i in range(0, len(stock_codes), chunk_size):
        chunk = stock_codes[i:i + chunk_size]
        
        # Add conservative delay
        time.sleep(3.0)
        
        try:
            # 建立查詢字串
            ex_ch_list = []
            for code in chunk:
                ex_ch_list.append(f"tse_{code}.tw")
                ex_ch_list.append(f"otc_{code}.tw")
            
            ex_ch = "|".join(ex_ch_list)
            ts = int(time.time() * 1000)
            url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch={ex_ch}&json=1&delay=0&_{ts}"
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://mis.twse.com.tw/stock/fibest.jsp?stock=2330",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest"
            }
            
            context = ssl._create_unverified_context()
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, context=context, timeout=10) as response:
                data = response.read().decode('utf-8')
                json_data = json.loads(data)
                
                if 'msgArray' in json_data:
                    for info in json_data['msgArray']:
                        code = info.get('c')
                        if not code: continue
                        
                        def safe_float(v, default=0.0):
                            if not v or v == '-': return default
                            try: return float(v)
                            except: return default
                        
                        def safe_int(v, default=0):
                            if not v or v == '-': return default
                            try: return int(v)
                            except: return default
                        
                        yesterday_close = safe_float(info.get('y'))
                        current_price = safe_float(info.get('z'), yesterday_close)
                        open_price = safe_float(info.get('o'), yesterday_close)
                        high_price = safe_float(info.get('h'), current_price)
                        low_price = safe_float(info.get('l'), current_price)
                        volume = safe_int(info.get('v'))
                        
                        change_percent = ((current_price - yesterday_close) / yesterday_close * 100) if yesterday_close > 0 else 0.0
                        
                        results[code] = {
                            'open': open_price,
                            'high': high_price,
                            'low': low_price,
                            'close': current_price,
                            'volume': volume * 1000,
                            'yesterday_close': yesterday_close,
                            'change_percent': round(change_percent, 2)
                        }
        except Exception:
            # Silently ignore connection errors to prevent console spam
            # The system will fallback to historical data automatically
            pass
    
    # 填補未獲取到的股票
    for code in stock_codes:
        if code not in results:
            results[code] = None
    
    return results
