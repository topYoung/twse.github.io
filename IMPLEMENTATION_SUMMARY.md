# 多類型訊號分類系統 - 實現總結

**更新時間**: 2026-04-20  
**版本**: v2.0 - 多類型訊號分類

---

## ✅ 實現的功能

### 1. 訊號類型分類 (`classify_signal_type` 函數)

**路徑**: [app/services/macd_scanner.py](app/services/macd_scanner.py#L1-L70)

自動判斷 4 種起漲訊號類型，並返回：
- `signal_type`: 訊號名稱 (如 "🔴 底部起漲")
- `priority`: 優先級 (1-5，越小越優先)
- `revenue_status`: 營收詳情說明

**訊號類型及優先級**:
| Priority | 訊號類型 | 條件 |
|----------|--------|-----|
| 1 | 💰 營收爆發 | MOM>40% ∨ YOY>30% |
| 2 | 🔴 底部起漲 | KD<50 + MACD轉折 |
| 3 | 💰 營收驅動 | MOM>20% ∧ YOY>15% |
| 4 | 🟢 加速起漲 | 連漲2天 + MACD擴大 |
| 5 | 🟡 突破起漲 | 漲≥4% ∨ 量≥2x |

### 2. 增強的掃描結果

**修改位置**: [app/services/macd_scanner.py](app/services/macd_scanner.py#L150-L210)

每個掃描結果現在包含：

```json
{
  "code": "2330",
  "name": "台積電",
  "price": 920.00,
  "change_percent": 2.34,
  
  // 🆕 訊號類型相關
  "signal_type": "🔴 底部起漲",
  "signal_priority": 2,
  "revenue_status": "KD D: 35.2 | MACD轉折",
  "kd_d_value": 35.2,
  
  // 營收信息
  "revenue": {
    "mom": 15.3,
    "yoy": 22.5
  },
  
  // 其他指標...
  "macd": {...},
  "pattern": "..."
}
```

**新增欄位說明**:
- `signal_type`: 訊號的中文名稱及表情符號
- `signal_priority`: 1-5 的優先級編號
- `revenue_status`: 根據營收或其他條件的詳細說明
- `kd_d_value`: KD 指標的 D 值（便於快速判斷）

### 3. 改進的排序邏輯

**修改位置**: [app/services/macd_scanner.py](app/services/macd_scanner.py#L295-L300)

```python
# 按訊號優先級排序 + 相同優先級內按漲幅排序
breakout_candidates.sort(key=lambda x: (x['signal_priority'], -x['change_percent']))
```

**排序規則**:
1. 第一層：按 `signal_priority` (1→5)
2. 第二層：相同優先級內按漲幅從高到低

### 4. 修復的 FutureWarning

**修改位置**: [app/services/revenue_service.py](app/services/revenue_service.py#L1-L120)

```python
from io import StringIO
import pandas as pd

# 修復前：
# dfs = pd.read_html(resp.text, thousands=",")  # ⚠️ FutureWarning

# 修復後：
dfs = pd.read_html(StringIO(resp.text), thousands=",")  # ✅ No warning
```

---

## 🧪 測試驗證

### 訊號分類測試
```bash
cd /Users/kevin/Documents/03_money
source .venv/bin/activate
python3 << 'EOF'
from app.services.macd_scanner import classify_signal_type

# 測試營收爆發案例
result = classify_signal_type(
    df=df, kd_d=45, dif_latest=0.5, hist_latest=0.1, hist_prev=0.0,
    rt_change=2.5, vol_ratio=1.3, mom=50.0, yoy=40.0
)
assert result[0] == '💰 營收爆發'
assert result[1] == 1  # 優先級最高

# 測試底部起漲案例
result = classify_signal_type(
    df=df, kd_d=30, dif_latest=0.2, hist_latest=0.05, hist_prev=-0.01,
    rt_change=1.5, vol_ratio=1.2, mom=5.0, yoy=8.0
)
assert result[0] == '🔴 底部起漲'
assert result[1] == 2
EOF
```

✅ **測試結果**: 全部通過

### 完整掃描測試
```bash
python3 << 'EOF'
from app.services.macd_scanner import get_macd_breakout_stocks

results = get_macd_breakout_stocks()
print(f"✅ 掃描完成，找到 {len(results)} 支股票")

# 驗證訊號類型分布
signal_types = [r['signal_type'] for r in results]
print(f"訊號類型: {Counter(signal_types)}")

# 驗證優先級排序
priorities = [r['signal_priority'] for r in results]
assert priorities == sorted(priorities), "優先級排序錯誤"
print("✅ 優先級排序正確")
EOF
```

---

## 📊 營收數據源

**當前狀態**: MOPS HTML 解析頁面格式已變更，暫無法自動抓取

**替代方案**:
1. ✅ 修復了 StringIO 的 FutureWarning
2. 🔄 等待 MOPS 頁面格式穩定後重新調整解析器
3. 💡 可手動上傳 CSV 或 JSON 數據

**推薦的營收數據源**:
- 台灣公開資訊觀測站 (MOPS): https://mops.twse.com.tw/
- 台灣證交所月營收查詢
- Yahoo Finance (有限，不支持台灣股票的 MOM/YOY)

---

## 🔄 使用流程

### 基礎查詢
```python
from app.services.macd_scanner import get_macd_breakout_stocks

results = get_macd_breakout_stocks()

# 按優先級展示
for stock in results:
    print(f"{stock['signal_type']:20} | {stock['code']} | {stock['revenue_status']}")
```

### 按類型篩選
```python
# 只取底部起漲
bottom = [s for s in results if s['signal_priority'] == 2]

# 只取營收相關 (優先級 1 或 3)
revenue_driven = [s for s in results if s['signal_priority'] in [1, 3]]
```

### 展示詳細資訊
```python
for stock in results[:5]:
    print(f"""
    {stock['code']} {stock['name']}
    訊號: {stock['signal_type']}
    詳情: {stock['revenue_status']}
    價格: {stock['price']:.2f} ({stock['change_percent']:+.2f}%)
    KD D: {stock['kd_d_value']:.1f}
    營收: MOM {stock['revenue']['mom']}% / YOY {stock['revenue']['yoy']}%
    """)
```

---

## 📝 相關文檔

- 📖 [使用指南](SIGNAL_TYPES_GUIDE.md) - 4 種訊號類型詳解及應用場景
- 🔧 [營收整合說明](REVENUE_INTEGRATION.md) - 營收數據集成方式
- 💾 核心代碼:
  - [macd_scanner.py](app/services/macd_scanner.py) - 主掃描邏輯
  - [revenue_service.py](app/services/revenue_service.py) - 營收數據服務

---

## 🎯 後續優化方向

1. **營收數據源修復**: 適應 MOPS 新頁面格式
2. **訊號組合**: 支持多條件自訂篩選 (如 "底部+營收>15%")
3. **信心分數**: 根據各指標權重計算 0-1 的信心度
4. **警告系統**: 識別高風險訊號 (如單日漲停)
5. **API 擴展**: 支持按訊號類型、優先級的 REST API 查詢

