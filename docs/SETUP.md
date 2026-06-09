# SubFlow — 完整安裝教學

本文件涵蓋從零開始的完整設定流程。如果你只想快速啟動，請先看 [README](../README.md)。

---

## 事前準備

| 工具 | 說明 |
|---|---|
| [Docker Desktop](https://www.docker.com/products/docker-desktop) | 執行 MySQL + App 容器（**唯一推薦啟動方式**） |
| Python 3.11+ | 僅本地開發需要 |
| Poetry（`pip install poetry`） | 僅本地開發需要 |
| [ngrok](https://ngrok.com/download) | LINE Bot 開發用（讓 LINE 能連回你的電腦） |
| LINE Developer 帳號 | 建立 Messaging API Channel |
| Google Cloud 帳號 | 啟用 Gmail API、建立 OAuth2 憑證 |

---

## Step 1 — Clone 專案

```bash
git clone https://github.com/your-org/subflow.git
cd subflow
```

---

## Step 2 — 建立 .env（互動式腳本）

**Windows（推薦）：**
```powershell
.\setup.ps1
```

**手動建立：**
```bash
cp .env.example .env
# 用編輯器開啟 .env 填入各欄位
```

腳本會引導你輸入以下三類設定，完成後自動寫入 `.env`：

---

## Step 3 — 設定 LINE Bot

1. 前往 [LINE Developers Console](https://developers.line.biz/console/)，建立 **Provider → Messaging API Channel**
2. 取得並填入 `.env`：
   - **Basic settings 頁** → Channel secret → `LINE_CHANNEL_SECRET`
   - **Messaging API 頁** → Issue channel access token → `LINE_CHANNEL_ACCESS_TOKEN`
3. 在 Messaging API 頁面：
   - 開啟「**Use webhook**」
   - 關閉「Auto-reply messages」
   - Webhook URL 暫時留空（ngrok 啟動後再填）

---

## Step 4 — 設定 Gmail API（OAuth2）

### 4-1. 建立 OAuth2 憑證

1. 前往 [Google Cloud Console](https://console.cloud.google.com/)，新建（或選擇現有）專案
2. 搜尋並啟用 **Gmail API**
3. **APIs & Services → Credentials → Create Credentials → OAuth client ID**
   - Application type：**Desktop app**
4. 下載 JSON 檔，**重新命名為 `credentials.json`**，放在專案根目錄

### 4-2. 設定 OAuth 同意畫面

1. **OAuth consent screen** → External → 填入 App name
2. **Scopes** 加入：`https://www.googleapis.com/auth/gmail.readonly`
3. **Test users** 加入自己的 Gmail 帳號

### 4-3. 首次授權（產生 token.json）

```powershell
# 安裝依賴（如尚未執行）
poetry install

# 觸發 OAuth 流程：會自動開啟瀏覽器授權，完成後產生 token.json
.venv\Scripts\python.exe scripts\gmail_scan.py --max 10 --dry-run
```

> `credentials.json` 和 `token.json` 已加入 `.gitignore`，不會上傳 GitHub，每次 clone 後需重新放置。

---

## Step 5 — 啟動 Docker 服務

```bash
# 第一次啟動（build image，約需幾分鐘）
docker compose up -d --build

# 確認三個服務都在執行
docker compose ps
```

正常狀態：

```
NAME                 STATUS
subflow_db           running (healthy)
subflow_app          running
subflow_dashboard    running
```

> **資料庫 Migration 已自動執行**：`app` 服務啟動時會自動執行 `alembic upgrade head`，不需要手動跑。

---

## Step 6 — 連結 LINE Bot Webhook

```powershell
# 在另一個終端啟動 ngrok
ngrok http 8000
```

複製 `https://<xxx>.ngrok-free.app` 的 URL，填入 LINE Developers Console：
- **Messaging API → Webhook URL**：`https://<xxx>.ngrok-free.app/webhook/callback`
- 點「**Verify**」，顯示 Success 代表連線正常

---

## Step 7 — 驗證一切正常

```powershell
# API 健康檢查
curl http://localhost:8000/health
# → {"status":"ok","env":"development"}

# 執行全套測試
.venv\Scripts\python.exe -m pytest
# → 80 passed
```

瀏覽器開啟 `http://localhost:8501` 應顯示 Streamlit 管理後台。

---

## 服務端點

| 服務 | URL |
|---|---|
| FastAPI | http://localhost:8000 |
| Swagger Docs | http://localhost:8000/docs |
| Streamlit 後台 | http://localhost:8501 |
| MySQL（本機） | localhost:3307 |

---

## 環境變數說明

| 變數 | 說明 |
|---|---|
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE Bot 長期存取 Token |
| `LINE_CHANNEL_SECRET` | 用於驗證 Webhook 簽名 |
| `DATABASE_URL` | SQLAlchemy 連線字串（Docker 內用 `db` hostname） |
| `GOOGLE_CREDENTIALS_PATH` | OAuth2 credentials.json 路徑（預設：`credentials.json`） |
| `GOOGLE_TOKEN_PATH` | OAuth token 快取路徑（首次認證後自動產生） |
| `GMAIL_TARGET_ADDRESS` | 用於掃描收據的 Gmail 信箱 |
| `NOTIFY_DAYS_ADVANCE` | 扣款前幾天推播提醒（預設 3） |
| `CRON_NOTIFICATION_HOUR` | 每日推播時間（24h，預設 9） |
| `LOG_LEVEL` | 日誌等級（DEBUG / INFO / WARNING / ERROR） |

---

## 本機開發（不使用 Docker App Container）

```powershell
# 只啟動 DB（本機跑 API）
docker compose up db -d

# 手動跑 Migration
$env:DATABASE_URL = "mysql+pymysql://subflow_user:<密碼>@localhost:3307/subflow"
.venv\Scripts\python.exe -m alembic upgrade head

# 啟動 FastAPI（port 8000）
.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 啟動 Streamlit Dashboard（port 8501）
.venv\Scripts\python.exe -m streamlit run app/dashboard/main.py

# Gmail 掃描（dry-run）
.venv\Scripts\python.exe scripts\gmail_scan.py --max 100 --dry-run
```

---

## 疑難排解

**`app` container 一直重啟**
DB 還沒 ready，等 `subflow_db` 變成 `(healthy)` 後 app 會自動重連。
```bash
docker compose logs app --tail 20
```

**Alembic upgrade 失敗 / Access denied**
確認 `$env:DATABASE_URL` 的密碼與 `.env` 中 `MYSQL_PASSWORD` 一致，且 port 用 `3307`（本機對外）。

**Gmail 授權出現「This app isn't verified」**
正常現象（開發階段 OAuth 未審核）。點「Advanced → Go to SubFlow (unsafe)」繼續授權。

**`credentials.json not found`**
確認檔案放在**專案根目錄**（與 `pyproject.toml` 同層），且 `.env` 中 `GOOGLE_CREDENTIALS_PATH=credentials.json`。

**LINE Bot 收不到訊息**
1. 確認 ngrok URL 已填入 LINE Developers Console Webhook URL
2. LINE Official Account Manager → 回應設定 → 回應方式改為「Webhook」，並關閉「自動回應訊息」

**重新 clone 後 `token.json` 遺失**
`token.json` 未納入 git。重新執行一次 Gmail scan dry-run 即可觸發瀏覽器重新授權：
```powershell
.venv\Scripts\python.exe scripts\gmail_scan.py --max 5 --dry-run
```

**啟動時看到 `未設定必要環境變數` 錯誤**
代表 `.env` 有欄位未填入。對照錯誤訊息中的變數名稱，回到 Step 3 / Step 4 補齊設定。
