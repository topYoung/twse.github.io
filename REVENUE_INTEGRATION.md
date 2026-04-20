# 營收增率整合說明

## 功能描述

已成功整合營收數據到 MACD 起漲訊號掃描器中，新增以下功能：

### 1. 營收數據來源
- **服務**: `app/services/revenue_service.py`
- **數據源**: 台灣公開資訊觀測站 (MOPS)
- **覆蓋**: 上市 + 上櫃公司
- **快取**: 6 小時 TTL（減少重複抓取）

### 2. 計算指標

| 指標 | 代號 | 說明 |
|-----|------|------|
| 月營收增率 | MOM | Month-on-Month: 當月 vs 上個月 |
| 年營收增率 | YOY | Year-on-Year: 當月 vs 去年同月 |

### 3. 修改的檔案

#### [app/services/macd_scanner.py](app/services/macd_scanner.py)

**導入營收服務**:
```python
from app.services.revenue_service import get_revenue_map
```

**掃描流程中新增營收檢查**:
- 在掃描前先取得所有股票的營收數據
- 在返回結果中添加 `revenue` 欄位
- 自動標記營收加速的訊號（月增>10% 或 年增>20%）

**返回數據結構範例**:
```json
{
  "code": "2464",
  "name": "盟立",
  "price": 79.0,
  "change_percent": 7.6,
  "pattern": "🚀 MACD走強 + 量價突破 💰 月增>10%",
  "revenue": {
    "mom": 15.3,    // 月營收增率 %
    "yoy": 22.5     // 年營收增率 %
  }
}
```

### 4. 使用方式

#### API 查詢
```python
from app.services.revenue_service import get_stock_revenue

# 查詢單一股票的營收數據
revenue_data = get_stock_revenue('2464')
# Returns: {"mom": 15.3, "yoy": 22.5, "revenue": 280000000}
```

#### MACD 掃描
```python
from app.services.macd_scanner import get_macd_breakout_stocks

results = get_macd_breakout_stocks()
for stock in results:
    print(f"{stock['code']} | MOM: {stock['revenue']['mom']}% | YOY: {stock['revenue']['yoy']}%")
```

### 5. 篩選邏輯

掃描結果中會自動標記營收加速：
- ✅ **月增 > 10%**: 短期營收動能強
- ✅ **年增 > 20%**: 中期營收成長穩定

### 6. 完整掃描條件

現在起漲訊號的判斷結合以下條件：

**技術面** (7 個條件):
1. MACD 轉折 (剛翻紅 / 綠縮短 / 正向擴大)
2. MACD 收斂 (hist < 5%)
3. DIF 零軸 (|DIF| < 20%)
4. 盤整背景 (最近15天波動平穩)
5. KD 低檔 (D ≤ 80)
6. 價格突破 (≥2.5% 或 ≥4%)
7. 量能突破 (≥1.5x 或 ≥1.2x)

**基本面** (新增):
- 月營收增率 (MOM) - 短期動能
- 年營收增率 (YOY) - 中期趨勢

---

## 已知問題

### MOPS 解析問題
目前 MOPS 網站無法正常解析 (HTML 格式可能已更新)，暫無法自動取得營收數據。

**替代方案**:
1. 手動從[公開資訊觀測站](https://mops.twse.com.tw/)下載
2. 使用第三方 API (如 Finlab)
3. 待 MOPS 頁面格式穩定後修復解析器

---

## 後續優化方向

1. **營收作為篩選條件**: 可將高營收增率作為必要條件 (非可選)
2. **営收加權排序**: 結合營收增率對結果進行加權排序
3. **營收異常偵測**: 識別營收突然暴增的訊號
4. **區間營收**:累計營收 (YTD) 與同期比較

