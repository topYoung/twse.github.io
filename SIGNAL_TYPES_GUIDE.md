# 多類型起漲訊號完整指南

## 概述

重新設計的掃描器現在支持 **4 種起漲訊號類型**，根據不同的市場驅動機制來分類，並按優先級自動排序。

---

## 📊 四種訊號類型

### 1️⃣ **💰 營收爆發** (Priority = 1 - 最優先)

**定義**: 基本面高增長驅動的起漲  
**核心條件**:
- **月營收增率 (MOM) > 40%** 或 **年營收增率 (YOY) > 30%**  

**特點**:
- 營收加速是起漲最強的基本面支撐
- 極少見，但一旦出現通常表示轉機
- 需結合技術面驗證，避免追高

**案例**:
```json
{
  "code": "2330",
  "name": "台積電",
  "signal_type": "💰 營收爆發",
  "price": 920.00,
  "change_percent": 2.5,
  "revenue": {"mom": 45.3, "yoy": 35.2},
  "revenue_status": "MOM: 45.3% | YOY: 35.2% ⭐⭐⭐"
}
```

---

### 2️⃣ **🔴 底部起漲** (Priority = 2)

**定義**: 從低位點反彈的經典起漲訊號  
**核心條件**:
- **KD 指標 D ≤ 50** (低檔位置)
- **MACD 轉折** (剛翻紅或綠縮短)
- 伴隨量能突破

**特點**:
- 最常見的起漲模式
- 風險報酬比佳（進場點在底部）
- 需確認盤整期充分

**技術判斷**:
```
價格走勢: 盤整期 → MACD轉折 → 量能突破
KD位置:   D ≤ 50      →  D > 50（向上穿越）
MACD:     負值縮短    →  轉正或綠轉紅
```

**案例**:
```json
{
  "code": "6568",
  "name": "宏觀",
  "signal_type": "🔴 底部起漲",
  "price": 225.00,
  "change_percent": 1.5,
  "kd_d_value": 35.2,
  "revenue_status": "KD D: 35.2 | MACD轉折"
}
```

---

### 3️⃣ **💰 營收驅動** (Priority = 3)

**定義**: 中等幅度營收增長支撐的起漲  
**核心條件**:
- **月營收增率 (MOM) 20-40%** 且 **年營收增率 (YOY) > 15%**
- 或單獨 **MOM > 20%** 表示短期動能

**特點**:
- 基本面驅動力度中等
- 通常伴隨技術面突破
- 營收可作為主要篩選條件

**使用場景**:
- 尋找受惠於產業景氣的股票
- 驗證量能突破的可持續性
- 與技術面形成雙重確認

**案例**:
```json
{
  "code": "3008",
  "name": "大立光",
  "signal_type": "💰 營收驅動",
  "price": 2605.00,
  "change_percent": 3.2,
  "revenue": {"mom": 28.5, "yoy": 22.0},
  "revenue_status": "MOM: 28.5% | YOY: 22.0% ✅"
}
```

---

### 4️⃣ **🟢 加速起漲** (Priority = 4)

**定義**: 趨勢中的連續強勢突破  
**核心條件**:
- **連漲 2 天或以上**
- **MACD 正向擴大** (hist > 0 且持續增大)
- KD > 50 (向上趨勢)

**特點**:
- 反映短期技術面強勢
- 適合短線跟風策略
- 需注意高位風險

**技術特徵**:
```
連續漲幅: 日 K 連紅
MACD:    柱狀體正向擴張
量能:    維持高於平均
KD:      在 50-100 區間持續向上
```

---

### 5️⃣ **🟡 突破起漲** (Priority = 5)

**定義**: 技術位置突破驅動的強勢起漲  
**核心條件**:
- **漲幅 ≥ 4%** 或
- **成交量比 ≥ 2x** (量能爆發)
- MACD 轉折或正向

**特點**:
- 大幅價量突破
- 可能是單日事件驅動
- 需警惕回檔風險

**風險提示**:
- 單日大漲容易見頂
- 需觀察隔日表現確認
- 建議分批進場

---

## 🎯 使用指南

### 優先級排序規則

```
1️⃣ 營收爆發 (MOM>40% or YOY>30%)     ← 最優先
2️⃣ 底部起漲 (KD<50 + MACD轉折)       
3️⃣ 營收驅動 (MOM>20% + YOY>15%)      
4️⃣ 加速起漲 (連漲2天 + MACD擴大)     
5️⃣ 突破起漲 (漲≥4% 或 量≥2x)        ← 最後
```

**特別注意**:
- 同優先級內按**漲幅從高到低**排序
- 營收數據缺失時，該訊號類型自動判斷為其他類型

### API 查詢示例

#### 基礎查詢 - 取得所有起漲訊號
```python
from app.services.macd_scanner import get_macd_breakout_stocks

results = get_macd_breakout_stocks()

# 按訊號類型分類
for stock in results[:10]:
    print(f"{stock['code']} | {stock['signal_type']:15} | {stock['revenue_status']}")
```

#### 按訊號類型篩選
```python
results = get_macd_breakout_stocks()

# 只取底部起漲
bottom_breakouts = [s for s in results if '底部' in s['signal_type']]

# 只取營收相關
revenue_signals = [s for s in results if '營收' in s['signal_type']]

# 只取 KD < 50 的底部起漲
bottom_and_low_kd = [s for s in results 
                      if '底部' in s['signal_type'] 
                      and s['kd_d_value'] < 50]
```

#### 查詢單支股票的營收數據
```python
from app.services.revenue_service import get_stock_revenue

revenue = get_stock_revenue('2330')
print(f"MOM: {revenue['mom']:.1f}% | YOY: {revenue['yoy']:.1f}%")
```

### 完整結果結構

```json
{
  "code": "2330",
  "name": "台積電",
  "price": 920.00,
  "change_percent": 2.34,
  "volume": 5000000,
  "vol_ratio": 1.25,
  "signal_type": "🔴 底部起漲",
  "signal_priority": 2,
  "revenue_status": "KD D: 35.2 | MACD轉折",
  "kd_d_value": 35.2,
  "macd": {
    "dif": 0.85,
    "dea": 0.72,
    "hist": 0.13
  },
  "revenue": {
    "mom": 15.3,
    "yoy": 22.5
  },
  "pattern": "🏆 綠縮短 + 量價突破"
}
```

---

## 📈 實戰應用場景

### 情景 1: 尋找最強的起漲訊號
```python
# 優先檢查營收爆發和底部起漲
strong_signals = [s for s in results 
                  if s['signal_priority'] <= 2]
```

### 情景 2: 結合基本面和技術面
```python
# 營收不錯 + 技術面起漲
quality_breakouts = [s for s in results 
                     if s['revenue']['mom'] is not None 
                     and s['revenue']['mom'] > 10]
```

### 情景 3: 低風險進場點
```python
# 底部起漲 + KD 極低 + 漲幅溫和
safe_entry = [s for s in results 
              if '底部' in s['signal_type']
              and s['kd_d_value'] < 30
              and s['change_percent'] < 5]
```

### 情景 4: 短線跟風機會
```python
# 加速起漲 + 已有漲幅 + 量能維持
trend_follow = [s for s in results 
               if '加速' in s['signal_type']
               and s['vol_ratio'] > 1.2]
```

---

## ⚠️ 重要提示

1. **營收數據可能滯後**: MOPS 月營收通常在月初 10 日前後公告
2. **訊號不是買點**: 需搭配風險管理、進場點位規劃
3. **優先級排序非推薦**: 應根據個人風險偏好選擇訊號類型
4. **量能驗證重要**: 無量的價格突破容易反轉

---

## 🔧 自訂優先級

若要改變排序邏輯，修改 [app/services/macd_scanner.py](app/services/macd_scanner.py) 的 `classify_signal_type` 函數中的 `priority` 值即可。

