# 專案操作指南 (macOS)

本文件說明如何管理 Python 虛擬環境以及如何使用 Git 提交更新。

## 1. 虛擬環境 (Python venv) 管理

### 建立虛擬環境
在專案根目錄執行以下指令：
```bash
python3 -m venv venv
```

### 啟動虛擬環境
啟動後，終端機提示字元前會出現 `(venv)`：
```bash
source venv/bin/activate
```

### 安裝依賴套件
啟動虛擬環境後，安裝專案所需套件：
```bash
pip install -r requirements.txt
```

### 解除虛擬環境 (Deactivate)
當不需要使用虛擬環境時：
```bash
deactivate
```

---

## 2. Git 檔案更新與提交步驟

執行更新前，請確保已進入正確的專案目錄。

### 第一步：檢查變更狀態
```bash
git status
```

### 第二步：加入變更檔案
加入所有變更：
```bash
git add .
```
或是加入特定檔案：
```bash
git add <檔案路徑>
```

### 第三步：提交變更 (Commit)
請遵循專案定義的繁體中文規範：

**格式建議：**
`類型: 簡短描述`

**格式範例：**
```bash
git commit -m "Fix: 修正某個功能錯誤

說明：
- 為什麼改：描述原因
- 改了什麼：描述修改內容
- 是否有影響：描述影響範圍"
```

### 第四步：推送到遠端倉庫 (Push)
```bash
git push
```

---

## 3. 啟動開發伺服器 (FastAPI)

啟動虛擬環境後執行：
```bash
python -m uvicorn app.main:app --reload
```
然後在瀏覽器開啟：`http://localhost:8000`
