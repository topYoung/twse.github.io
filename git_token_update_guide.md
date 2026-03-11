# 如何更新 Git (GitHub) Token

當你的 GitHub Personal Access Token (PAT) 過期時，你會在執行 `git push` 或 `git pull` 時遇到認證失敗的錯誤（例如 `Authentication failed` 或是 `403 Forbidden`）。

請依照以下兩個階段的步驟來更新您的 Token。

## 階段一：在 GitHub 重新生成 Token

1. 登入 [GitHub](https://github.com/) 網站。
2. 點擊右上角的大頭貼，選擇 **Settings**。
3. 在左側選單拉到最下方，點擊 **Developer settings**。
4. 在左側選單選擇 **Personal access tokens** -> **Tokens (classic)**（或是 Fine-grained tokens，依您之前的習慣）。
5. 點擊 **Generate new token** -> **Generate new token (classic)**。
6. 填寫 Token 的用途 (Note)，例如 `Macbook Pro 2026`。
7. 設定到期日 (Expiration)。
8. 勾選需要的權限（通常推拉程式碼至少需要勾選 `repo`）。
9. 滑到最下方點選 **Generate token**。
10. **重要**：立刻將產生的一串 Token（以 `ghp_` 開頭）**複製下來**！因為一旦離開此頁面，你將無法再次看到這串 Token。

---

## 階段二：在 Mac 上更新本地的 Git 憑證

因為您的作業系統是 Mac，系統預設會將密碼自動記憶在「鑰匙圈 (Keychain)」裡，所以即使在 GitHub 上換了新 Token，終端機還是會用舊的錯 Token 嘗試登入。

以下提供兩種更新 Mac 本地憑證的方法，擇一使用即可：

### 方法 A：透過「鑰匙圈存取」(Keychain Access) 應用程式（推薦，最直覺）

1. 打開 Mac 內建的「**鑰匙圈存取 (Keychain Access)**」應用程式（可以在 Spotlight 🔍 搜尋找到）。
2. 在右上角的搜尋框輸入 `github.com`。
3. 在搜尋結果中，找到種類為「**網際網路密碼 (Internet password)**」的項目（名稱通常是 `github.com`）。
4. 對著該項目**點擊兩下**打開詳細資訊視窗。
5. 勾選下方的「**顯示密碼**」，系統會要求您輸入 Mac 的開機密碼或指紋解鎖。
6. 解鎖後，將原有的舊 Token 刪除，並**貼上您剛剛複製的新 Token**。
7. 點擊「**儲存變更 (Save Changes)**」。
8. 回到終端機再次執行 `git push` 或 `git pull`，應該就能正常運作了！

### 方法 B：透過終端機 (Terminal) 清除舊快取

如果你不想開鑰匙圈，也可以直接在終端機強制刪除舊的憑證：

1. 開啟終端機，貼上並執行以下指令來刪除舊憑證：
   ```bash
   printf "protocol=https\nhost=github.com\n" | git credential-osxkeychain erase
   ```
2. 接著在您的專案中執行任何需要連線的指令，例如：
   ```bash
   git fetch
   ```
3. 系統這時會跳出提示要求您重新輸入帳號密碼：
   - **Username**: 輸入您的 `GitHub 帳號名稱`
   - **Password**: 貼上您剛剛複製的 **新 Token**（不是 GitHub 登入密碼喔！）

---

> **附註：使用 Git 遠端 URL 寫死的情況**
> 如果您當初是將 Token 寫死在 Git Remote URL 的話（不建議，因為較不安全），可以透過以下指令更新：
> ```bash
> # 請將裡面的 Username, 新Token, 與 RepoName 換成你自己的
> git remote set-url origin https://<YOUR_USERNAME>:<NEW_TOKEN>@github.com/<YOUR_USERNAME>/<REPO_NAME>.git
> ```
