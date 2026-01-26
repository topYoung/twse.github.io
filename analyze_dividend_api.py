"""
詳細測試 t187ap45_L API 的資料結構
"""
import requests
import json

API_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap45_L"

def analyze_api():
    print("正在取得股利分派資料...\n")
    
    try:
        response = requests.get(API_URL, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            print(f"✓ 成功取得資料")
            print(f"總筆數: {len(data)}")
            
            # 找出有實際股利資料的項目
            valid_items = []
            for item in data:
                # 檢查是否有公司代號且有股利資料
                if item.get('公司代號') and item['公司代號'] not in [None, 'null', '']:
                    # 檢查是否有現金股利欄位
                    cash_div_field = item.get('股東配發-盈餘分配之現金股利(元/股)')
                    if cash_div_field and cash_div_field not in [None, 'null', '', '0', '0.0']:
                        valid_items.append(item)
            
            print(f"有效股利資料筆數: {len(valid_items)}")
            
            if valid_items:
                print(f"\n前 5 筆有效資料:")
                for i, item in enumerate(valid_items[:5]):
                    print(f"\n[{i+1}] {item.get('公司代號')} - {item.get('公司名稱')}")
                    print(f"    股利年度: {item.get('股利年度')}")
                    print(f"    現金股利: {item.get('股東配發-盈餘分配之現金股利(元/股)')}")
                    print(f"    股票股利: {item.get('股東配發-盈餘轉增資配股(元/股)')}")
                
                # 顯示所有欄位名稱
                print(f"\n完整欄位列表:")
                for key in valid_items[0].keys():
                    print(f"  - {key}")
                    
                # 尋找台積電
                print(f"\n搜尋台積電 (2330)...")
                tsmc = [item for item in valid_items if item.get('公司代號') == '2330']
                if tsmc:
                    print(f"✓ 找到台積電股利資料:")
                    print(json.dumps(tsmc[0], ensure_ascii=False, indent=2))
                else:
                    print(f"✗ 台積電不在有效資料中")
                    
            else:
                print(f"\n✗ 沒有找到有效的股利資料")
                print(f"檢查前 3 筆原始資料:")
                for i, item in enumerate(data[:3]):
                    print(f"\n[{i+1}]")
                    print(json.dumps(item, ensure_ascii=False, indent=2))
                    
    except Exception as e:
        print(f"✗ 錯誤: {e}")

if __name__ == "__main__":
    analyze_api()
