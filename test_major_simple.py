"""
簡單測試 get_major_investors_layout 函數
不依賴 FastAPI TestClient
"""
from app.services.layout_analyzer import get_major_investors_layout

def test_function():
    print("=" * 60)
    print("測試 get_major_investors_layout 函數")
    print("=" * 60)
    
    try:
        print("\n正在呼叫 get_major_investors_layout(days=3, top_n=10)...")
        results = get_major_investors_layout(days=3, top_n=10)
        
        print(f"\n✓ 回傳型別: {type(results)}")
        print(f"✓ 資料筆數: {len(results)}")
        
        if isinstance(results, list):
            print("✓ 成功回傳 list 型別")
            
            if len(results) > 0:
                print(f"\n前 3 筆資料範例：")
                for i, stock in enumerate(results[:3], 1):
                    print(f"\n  {i}. {stock.get('stock_name', 'N/A')} ({stock.get('stock_code', 'N/A')})")
                    print(f"     類別: {stock.get('category', 'N/A')}")
                    print(f"     合計買超: {stock.get('total_net', 0):,} 股")
                    print(f"     外資: {stock.get('details', {}).get('foreign', 0):,}")
                    print(f"     投信: {stock.get('details', {}).get('trust', 0):,}")
                    print(f"     自營: {stock.get('details', {}).get('dealer', 0):,}")
            else:
                print("\n⚠ 回傳空清單（可能無符合條件的股票）")
        else:
            print(f"✗ 回傳型別錯誤: 預期 list，實際 {type(results)}")
            print(f"內容: {results}")
            return False
            
        print("\n" + "=" * 60)
        print("測試通過 ✓")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"\n✗ 測試失敗: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_function()
    exit(0 if success else 1)
