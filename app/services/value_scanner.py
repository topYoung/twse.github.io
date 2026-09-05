import requests
from typing import List, Dict

def scan_pe_stocks(min_pe: float = 10.0, max_pe: float = 20.0) -> List[Dict]:
    """
    掃描本益比在給定範圍內的上市股票
    """
    url = "https://www.twse.com.tw/exchangeReport/BWIBBU_d?response=json"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if 'data' not in data:
            return []
            
        results = []
        for row in data['data']:
            code = row[0]
            name = row[1]
            pe_str = row[5]
            
            # '-' 表示無本益比（通常是虧損）
            if pe_str == '-' or not pe_str:
                continue
                
            try:
                pe = float(pe_str.replace(',', ''))
                if min_pe <= pe <= max_pe:
                    results.append({
                        "code": code,
                        "name": name,
                        "pe": pe,
                        "close": float(row[2].replace(',', '')),
                        "yield": float(row[3].replace(',', '')),
                        "pb": float(row[6].replace(',', ''))
                    })
            except ValueError:
                continue
                
        # 依本益比由低至高排序
        results.sort(key=lambda x: x['pe'])
        return results
        
    except Exception as e:
        print(f"Error fetching PE data: {e}")
        return []
