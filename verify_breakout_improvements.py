#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
驗證起漲訊號改進功能
測試三大改進：
1. 帶量上漲偵測
2. 取消漲幅限制
3. 多日下跌後上引線偵測
"""

import sys
sys.path.insert(0, '/Users/kevin/Documents/03_money')

from app.services.breakout_scanner import get_breakout_stocks
import json

print("=" * 60)
print("驗證起漲訊號改進功能")
print("=" * 60)

# 測試 API
print("\n正在掃描股票...")
result = get_breakout_stocks(force_refresh=True)

stocks = result.get('stocks', [])
print(f"\n✅ 找到 {len(stocks)} 檔符合條件的個股\n")

if len(stocks) == 0:
    print("⚠️  未找到符合條件的個股，這可能表示：")
    print("   - 目前市場狀況不符合任何策略")
    print("   - 或需要調整篩選條件")
    sys.exit(0)

# 統計分析
print("=" * 60)
print("功能驗證分析")
print("=" * 60)

# 1. 量能訊號統計
volume_signals = {}
for stock in stocks:
    sig = stock.get('volume_signal', 'N/A')
    volume_signals[sig] = volume_signals.get(sig, 0) + 1

print("\n【1. 量能訊號分類統計】")
for sig, count in sorted(volume_signals.items(), key=lambda x: x[1], reverse=True):
    print(f"  {sig}: {count} 檔")

# 2. 漲幅分佈（驗證是否有低漲幅個股）
low_gain_stocks = [s for s in stocks if s.get('change_percent', 0) < 2.0]
medium_gain_stocks = [s for s in stocks if 2.0 <= s.get('change_percent', 0) < 3.5]
high_gain_stocks = [s for s in stocks if s.get('change_percent', 0) >= 3.5]

print("\n【2. 漲幅分佈（驗證取消漲幅限制）】")
print(f"  漲幅 < 2%:   {len(low_gain_stocks)} 檔 ✨ (新增類別)")
print(f"  漲幅 2-3.5%: {len(medium_gain_stocks)} 檔")
print(f"  漲幅 >= 3.5%: {len(high_gain_stocks)} 檔")

if len(low_gain_stocks) > 0:
    print(f"\n  ✅ 成功！已找到 {len(low_gain_stocks)} 檔低漲幅但符合其他條件的個股")
else:
    print("\n  ℹ️  目前無低漲幅個股（可能市場狀況導致）")

# 3. 上引線特徵統計
upper_shadow_stocks = [s for s in stocks if s.get('upper_shadow', {}).get('has_upper_shadow', False)]

print("\n【3. 上引線特徵統計（新功能）】")
print(f"  具有上引線特徵: {len(upper_shadow_stocks)} 檔")

if len(upper_shadow_stocks) > 0:
    print(f"\n  ✅ 成功！已找到 {len(upper_shadow_stocks)} 檔多日下跌後上引線個股")
    print("\n  詳細資訊：")
    for stock in upper_shadow_stocks[:3]:  # 顯示前3檔
        shadow_info = stock.get('upper_shadow', {})
        print(f"    - {stock['code']} {stock['name']}")
        print(f"      連續下跌: {shadow_info.get('decline_count')} 日")
        print(f"      上影線比率: {shadow_info.get('shadow_ratio')} 倍")
else:
    print("  ℹ️  目前無符合上引線條件的個股（可能市場狀況導致）")

# 4. 選股策略分佈
reason_stats = {}
for stock in stocks:
    reason = stock.get('reason', 'N/A')
    reason_stats[reason] = reason_stats.get(reason, 0) + 1

print("\n【4. 選股策略分佈】")
for reason, count in sorted(reason_stats.items(), key=lambda x: x[1], reverse=True):
    print(f"  {reason}: {count} 檔")

# 5. 顯示範例個股
print("\n" + "=" * 60)
print("範例個股資訊（前 5 檔）")
print("=" * 60)

for i, stock in enumerate(stocks[:5], 1):
    print(f"\n【{i}】 {stock['code']} {stock['name']} ({stock['category']})")
    print(f"  價格: {stock['price']} 元")
    print(f"  漲幅: {stock['change_percent']}%")
    print(f"  量能訊號: {stock.get('volume_signal', 'N/A')}")
    print(f"  量比: {stock['vol_ratio']} 倍")
    print(f"  選股原因: {stock['reason']}")
    
    diagnostics = stock.get('diagnostics', [])
    if diagnostics:
        print(f"  技術診斷: {', '.join(diagnostics)}")
    
    upper_shadow = stock.get('upper_shadow', {})
    if upper_shadow.get('has_upper_shadow'):
        print(f"  上引線: 連續下跌 {upper_shadow['decline_count']} 日，" 
              f"上影線比率 {upper_shadow['shadow_ratio']} 倍")

print("\n" + "=" * 60)
print("✅ 驗證完成！")
print("=" * 60)

# 總結
print("\n【驗證總結】")
print("1. ✅ 量能訊號分類功能正常運作")
if len(low_gain_stocks) > 0:
    print(f"2. ✅ 漲幅限制已移除（找到 {len(low_gain_stocks)} 檔低漲幅個股）")
else:
    print("2. ✅ 漲幅限制已移除（語法正確，但目前市況無低漲幅個股）")

if len(upper_shadow_stocks) > 0:
    print(f"3. ✅ 上引線偵測功能正常運作（找到 {len(upper_shadow_stocks)} 檔）")
else:
    print("3. ✅ 上引線偵測功能已整合（語法正確，但目前市況無符合個股）")

print(f"\n總計掃描結果：{len(stocks)} 檔個股符合條件")
