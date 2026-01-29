## Bug 修復記錄

### 問題：前端顯示「擷取失敗：請檢查網址 (資料格式錯誤)」

**根本原因**：JSON 序列化失敗

```
TypeError: Object of type bool is not JSON serializable
```

**問題分析**：

在 `detect_upper_shadow_after_decline()` 函數中，回傳的 `upper_shadow` 字典包含：

```python
{
    'has_upper_shadow': has_upper_shadow,  # Python bool 類型
    ...
}
```

雖然 FastAPI 通常會自動處理 Python 的 bool 類型，但在某些情況下（特別是嵌套在字典中時），標準的 `json.dumps()` 可能無法正確序列化 Python 的 `bool` 類型。

**修復方案**：

將所有回傳值明確轉換為 JSON 可序列化的基本類型：

```python
return {
    'has_upper_shadow': int(has_upper_shadow),  # bool → int (0/1)
    'decline_count': int(decline_count),        # 確保是 int
    'shadow_length': round(float(shadow_length), 2),  # 確保是 float
    'body_length': round(float(body_length), 2),
    'shadow_ratio': round(float(shadow_ratio_value), 2)
}
```

**修改檔案**：
- [`app/services/breakout_scanner.py`](file:///Users/kevin/Documents/03_money/app/services/breakout_scanner.py#L153-L196)

**驗證結果**：

```bash
✅ JSON 序列化成功！
回傳資料包含 25 檔個股

檢查 upper_shadow 欄位類型:
  has_upper_shadow: 0 (type: int)
  decline_count: 0 (type: int)
```

問題已完全解決，API 現在可以正常回傳資料給前端。

---

