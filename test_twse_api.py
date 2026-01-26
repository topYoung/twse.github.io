"""
測試證交所 OpenAPI 實際返回的資料格式
"""
import requests
import json

TWSE_DIVIDEND_URL = "https://openapi.twse.com.tw/v1/exchangeReport/t187ap03_L"

def test_api_response():
    print("正在取得證交所股利資料...\n")
    
    try:
        response = requests.get(TWSE_DIVIDEND_URL, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            print(f"✓ API 回應成功")
            print(f"資料類型: {type(data)}")
            print(f"資料筆數: {len(data) if isinstance(data, list) else 'N/A'}")
            
            if isinstance(data, list) and len(data) > 0:
                print(f"\n第一筆資料範例:")
                print(json.dumps(data[0], ensure_ascii=False, indent=2))
                
                print(f"\n所有欄位名稱:")
                print(list(data[0].keys()))
                
                # 尋找台積電 2330
                print(f"\n搜尋台積電 (2330)...")
                for item in data:
                    if item.get('公司代號') == '2330':
                        print(f"✓ 找到台積電:")
                        print(json.dumps(item, ensure_ascii=False, indent=2))
                        break
                else:
                    print(f"✗ 未找到台積電")
                    
        else:
            print(f"✗ HTTP 錯誤: {response.status_code}")
            
    except Exception as e:
        print(f"✗ 錯誤: {e}")

if __name__ == "__main__":
    test_api_response()
