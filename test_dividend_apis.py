"""
測試多個可能的股利 API 端點
"""
import requests
import json

# 可能的股利相關 API
POSSIBLE_APIS = [
    ("公司基本資料", "https://openapi.twse.com.tw/v1/exchangeReport/t187ap03_L"),
    ("除權息預告", "https://openapi.twse.com.tw/v1/exchangeReport/TWT49U"),
    ("除權息公告", "https://openapi.twse.com.tw/v1/exchangeReport/TWT48U"),
    ("股利分派情形", "https://openapi.twse.com.tw/v1/opendata/t187ap05_L"),
]

def test_all_apis():
    for name, url in POSSIBLE_APIS:
        print(f"\n{'='*60}")
        print(f"測試: {name}")
        print(f"URL: {url}")
        print(f"{'='*60}")
        
        try:
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                if isinstance(data, list) and len(data) > 0:
                    print(f"✓ 成功! 資料筆數: {len(data)}")
                    print(f"\n第一筆資料欄位:")
                    print(list(data[0].keys()))
                    
                    # 檢查是否有股利相關欄位
                    dividend_keywords = ['股利', '現金', '股票', '除息', '除權']
                    found_fields = []
                    for key in data[0].keys():
                        if any(keyword in key for keyword in dividend_keywords):
                            found_fields.append(key)
                    
                    if found_fields:
                        print(f"\n✓ 找到股利相關欄位: {found_fields}")
                        print(f"\n第一筆完整資料:")
                        print(json.dumps(data[0], ensure_ascii=False, indent=2))
                    else:
                        print(f"\n✗ 無股利相關欄位")
                else:
                    print(f"資料格式: {type(data)}")
                    
            else:
                print(f"✗ HTTP {response.status_code}")
                
        except Exception as e:
            print(f"✗ 錯誤: {e}")

if __name__ == "__main__":
    test_all_apis()
