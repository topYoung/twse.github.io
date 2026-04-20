#!/usr/bin/env python3
import sys
sys.path.insert(0, '/Users/kevin/Documents/03_money')

from app.services.macd_scanner import get_macd_breakout_stocks

print("\n" + "=" * 100)
print("🚀 開始掃描起漲訊號...")
print("⏳ 這可能需要 2-5 分鐘，取決於網絡速度...\n")
print("=" * 100)

try:
    results = get_macd_breakout_stocks()
    print(f"\n✅ 掃描完成！找到 {len(results)} 支起漲股票\n")
    
    # 檢查 6568 是否在結果中
    found_6568 = any(r['code'] == '6568' for r in results)
    print(f"📊 6568 (宏觀) 在結果中？ {'✅ 是' if found_6568 else '❌ 否'}\n")
    
    # 顯示前 15 支
    print("=" * 100)
    print("前 15 支起漲訊號:")
    print("=" * 100)
    for i, stock in enumerate(results[:15], 1):
        print(f"{i:2}. {stock['code']} {stock['name']:8} - 收: {stock['price']:7.1f}, 漲: {stock['change_percent']:+6.1f}%, 量比: {stock['volume_ratio']:5.1f}x")
    
    # 如果有 6568，單獨顯示
    if found_6568:
        print("\n" + "=" * 100)
        print("🎯 6568 宏觀 詳細信息:")
        print("=" * 100)
        stock_6568 = next(r for r in results if r['code'] == '6568')
        for k, v in stock_6568.items():
            print(f"  {k:20}: {v}")
    else:
        print("\n❌ 6568 未被起漲訊號掃描器抓到")
        print("\n📋 可能的原因:")
        print("  1. 前一天漲幅 < 5%，但盤整條件被嚴格條件過濾")
        print("  2. MACD 未翻紅或還在反轉中")
        print("  3. KD D 值 > 40（嚴格模式）或 > 50（寬鬆模式）")
        print("  4. 今天漲幅 < 2.5% 或量能 < 1.5x")

except Exception as e:
    print(f"❌ 掃描失敗: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 100)
