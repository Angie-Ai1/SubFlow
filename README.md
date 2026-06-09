# SubFlow — Subscription Management Automation

> 自動化訂閱管理系統：整合 Gmail 收據解析、LINE Bot 通知與 Streamlit 管理後台。

---

## 專案目標

現代人訂閱服務繁多（串流、SaaS、雲端儲存等），帳單分散於各信箱難以追蹤。  
SubFlow 的目標是：

1. **自動擷取**：透過 Gmail API 定期掃描收據郵件，解析金額、服務名稱、計費週期。
2. **手動補齊**：提供 Streamlit 後台讓使用者手動新增或修正訂閱記錄。
3. **正規化儲存**：所有資料統一寫入 MySQL，維持一致的資料模型。
4. **主動通知**：透過 LINE Bot 查詢訂閱清單、搜尋、停用，並於扣款前主動推播提醒。

---

## 技術棧

| 層次 | 技術 |
|---|---|
| 語言 | Python 3.11 |
| Web / Webhook | FastAPI + Uvicorn |
| 通知 | LINE Messaging API (line-bot-sdk v3) |
| 郵件解析 | Google Gmail API (google-api-python-client) |
| 資料庫 ORM | SQLAlchemy 2.x + Alembic |
| 資料庫 | MySQL 8.4 |
| 管理後台 | Streamlit + Altair |
| 排程 | APScheduler（每日推播 + 每 6 小時 Gmail 掃描） |
| 容器化 | Docker + Docker Compose |
| 套件管理 | Poetry |
| 代碼風格 | Ruff (linting) + Black (formatting) |
| CI/CD | GitHub Actions |

---

## 架構說明

```
SubFlow/
├── app/
│   ├── main.py             # FastAPI 入口點 + APScheduler lifespan
│   ├── config.py           # Pydantic Settings（讀 .env）
│   ├── webhook/
│   │   ├── router.py       # POST /webhook/callback（LINE Webhook）
│   │   ├── handlers.py     # FollowEvent / UnfollowEvent / MessageEvent 處理
│   │   ├── line_client.py  # MessagingApi 單例
│   │   └── notifier.py     # 排程推播：扣款提醒 / Gmail 掃描觸發
│   ├── parsers/
│   │   ├── gmail_auth.py   # OAuth2 認證（token 快取 + 自動 refresh）
│   │   ├── gmail_fetcher.py# 分頁抓取收據信件（最多 2000 封）
│   │   ├── receipt_parser.py# 解析金額、服務名稱、幣別、日期
│   │   └── importer.py     # 完整 pipeline：fetch → parse → dedup → save
│   └── dashboard/
│       ├── main.py         # Streamlit 頁面（訂閱清單 / 帳單紀錄 / 月支出圖表）
│       └── db.py           # Dashboard 查詢層（@st.cache_data）
│
├── database/
│   ├── base.py             # SQLAlchemy DeclarativeBase
│   ├── session.py          # Engine / SessionFactory / get_db / check_connection
│   ├── models.py           # Subscription / BillingRecord / LineUser ORM 模型
│   └── migrations/         # Alembic migration scripts
│
├── utils/
│   └── logger_config.py    # 全域 Logger（console + RotatingFile）
│
├── scripts/
│   └── gmail_scan.py       # 本地 CLI：手動觸發 Gmail 掃描（--dry-run 支援）
│
├── docker/
│   └── Dockerfile
│
├── tests/                  # pytest test suite（80 tests，SQLite in-memory）
│
├── .github/
│   └── workflows/
│       └── ci.yml          # Lint → Test pipeline
│
├── run.ps1                 # 啟動腳本（api / dashboard / gmail-scan / test 四模式）
├── docker-compose.yml      # MySQL + App + Dashboard containers
├── pyproject.toml          # Poetry deps + Ruff / Black config
├── .env.example            # 環境變數範本
└── .gitignore
```

### 資料流

```
Gmail API ──► gmail_fetcher ──► receipt_parser ──► importer ──► MySQL
                                                                   │
Manual Input (Streamlit Dashboard) ────────────────────────────────┘
                                                                   │
                                                        LINE Bot Query / Notify
```

### API 端點

| Method | Path | 說明 |
|---|---|---|
| `GET` | `/health` | 服務健康檢查 |
| `POST` | `/webhook/callback` | LINE Webhook callback |
| `POST` | `/ops/gmail-import` | 手動觸發 Gmail 收據匯入 |

### 資料模型

| 資料表 | 說明 |
|---|---|
| `subscriptions` | 訂閱主檔（名稱、金額、週期、下次扣款日） |
| `billing_records` | 每筆扣款紀錄，含 `gmail_message_id` 防重複匯入 |
| `line_users` | 已追蹤 LINE Bot 的使用者 |

---

## 快速開始

### 事前準備

| 工具 | 說明 |
|---|---|
| [Docker Desktop](https://www.docker.com/products/docker-desktop) | 執行 MySQL + App 容器 |
| Python 3.11+ | 本地開發 / Migration 用 |
| Poetry（`pip install poetry`） | 套件管理 |
| [ngrok](https://ngrok.com/download) | LINE Bot 本地開發用（讓 LINE 能打到你的電腦） |
| LINE Developer 帳號 | 建立 Messaging API Channel |
| Google Cloud 帳號 | 啟用 Gmail API、建立 OAuth2 憑證 |

---

### Step 1 — Clone & 安裝依賴

```bash
git clone https://github.com/your-org/subflow.git
cd subflow

# 安裝 Python 依賴（自動建立 .venv）
poetry install

# 複製環境變數範本
cp .env.example .env
```

---

### Step 2 — 設定 .env

用編輯器打開 `.env`，填入以下三類設定：

**MySQL 密碼**（自訂即可）
```env
MYSQL_PASSWORD=your_strong_password
MYSQL_ROOT_PASSWORD=your_root_password
DATABASE_URL=mysql+pymysql://subflow_user:your_strong_password@db:3306/subflow
```
> `MYSQL_HOST=db` 不要改，這是 Docker 內部 hostname。

**LINE Bot**（Step 3 取得後填入）
```env
LINE_CHANNEL_ACCESS_TOKEN=...
LINE_CHANNEL_SECRET=...
```

**Gmail API**（Step 4 取得後填入）
```env
GOOGLE_CREDENTIALS_PATH=credentials.json
GOOGLE_TOKEN_PATH=token.json
GMAIL_TARGET_ADDRESS=your_email@gmail.com
```

---

### Step 3 — 設定 LINE Bot

1. 前往 [LINE Developers Console](https://developers.line.biz/console/)，建立 **Provider → Messaging API Channel**
2. 取得並填入 `.env`：
   - **Basic settings 頁** → Channel secret → `LINE_CHANNEL_SECRET`
   - **Messaging API 頁** → Issue channel access token → `LINE_CHANNEL_ACCESS_TOKEN`
3. 在 Messaging API 頁面：
   - 開啟「**Use webhook**」
   - 關閉「Auto-reply messages」
   - Webhook URL 暫時留空（ngrok 啟動後再填）

---

### Step 4 — 設定 Gmail API（OAuth2）

**4-1. 建立 OAuth2 憑證**

1. 前往 [Google Cloud Console](https://console.cloud.google.com/)，新建（或選擇現有）專案
2. 搜尋並啟用 **Gmail API**
3. **APIs & Services → Credentials → Create Credentials → OAuth client ID**
   - Application type：**Desktop app**
4. 下載 JSON 檔，**重新命名為 `credentials.json`**，放在專案根目錄

**4-2. 設定 OAuth 同意畫面**

1. **OAuth consent screen** → External → 填入 App name
2. **Scopes** 加入：`https://www.googleapis.com/auth/gmail.readonly`
3. **Test users** 加入自己的 Gmail 帳號

**4-3. 首次授權**

```powershell
# 會自動開啟瀏覽器進行 OAuth 授權，完成後產生 token.json
.\run.ps1 -Mode gmail-scan -Max 10 -DryRun
```

> ⚠️ `credentials.json` 和 `token.json` 已加入 `.gitignore`，不會上傳 GitHub，每次 clone 後需重新放置。

---

### Step 5 — 啟動 Docker 服務

```bash
# 第一次啟動（build image，約需幾分鐘）
docker compose up -d --build

# 確認三個服務都在跑
docker compose ps
```

正常狀態：

```
NAME                 STATUS
subflow_db           running (healthy)
subflow_app          running
subflow_dashboard    running
```

---

### Step 6 — 執行資料庫 Migration

等 DB container healthy（約 30 秒）後執行：

```powershell
# 設定本機連線用的 DATABASE_URL（port 3307 是 Docker 對外映射的 port）
$env:DATABASE_URL = "mysql+pymysql://subflow_user:your_strong_password@localhost:3307/subflow"
.venv\Scripts\python.exe -m alembic upgrade head
```

成功輸出：
```
INFO  [alembic] Running upgrade -> 9afad140d8a2, initial schema
INFO  [alembic] Running upgrade 9afad140d8a2 -> c7d8e9f0a1b2, add subscribed_since
```

---

### Step 7 — 連結 LINE Bot Webhook

```powershell
# 在另一個終端啟動 ngrok
ngrok http 8000
```

複製 `https://<xxx>.ngrok-free.app` 的 URL，填入 LINE Developers Console：
- **Messaging API → Webhook URL**：`https://<xxx>.ngrok-free.app/webhook/callback`
- 點「**Verify**」，顯示 Success 代表連線正常

---

### Step 8 — 驗證一切正常

```powershell
# API 健康檢查
curl http://localhost:8000/health
# → {"status":"ok"}

# 執行全套測試
.\run.ps1 -Mode test
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

詳見 [`.env.example`](.env.example)。關鍵變數：

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

## LINE Bot 指令

| 輸入 | 功能 |
|---|---|
| `訂閱清單` / `清單` / `list` | 列出所有啟用中的訂閱及下次扣款日 |
| `即將到期` / `到期` / `upcoming` | 列出 N 天內扣款的訂閱（N = NOTIFY_DAYS_ADVANCE） |
| `搜尋 <名稱>` / `search <名稱>` | 模糊搜尋訂閱（含停用中，標記狀態） |
| `停用 <名稱>` / `disable <名稱>` | 停用符合名稱的啟用中訂閱 |
| `說明` / `help` / `?` | 顯示完整指令說明 |
| `選單` / `menu` | 顯示快速按鈕選單 |

Quick Reply 按鈕自動附於說明、選單、錯誤回應等訊息底部。

---

## 本機開發（不使用 Docker App Container）

```powershell
# 只啟動 DB（本機跑 API）
docker compose up db -d

# 啟動 FastAPI（port 8000）
.\run.ps1 -Mode api

# 啟動 Streamlit Dashboard（port 8501）
.\run.ps1 -Mode dashboard

# Gmail 掃描（dry-run，只解析不寫 DB）
.\run.ps1 -Mode gmail-scan -Max 100 -DryRun

# Gmail 掃描（實際寫入 DB）
.\run.ps1 -Mode gmail-scan -Max 500

# 執行測試
.\run.ps1 -Mode test
```

> 所有執行日誌會同步寫入 `logs/` 目錄。

### 代碼風格檢查

```bash
poetry run ruff check .
poetry run black --check .
```

### 新增資料庫 Migration

```bash
poetry run alembic revision --autogenerate -m "描述變更"
poetry run alembic upgrade head
```

---

## CI/CD

推送至 `main` / `develop` 或發 PR 時，GitHub Actions 自動執行：

1. **Lint**：Ruff + Black check
2. **Test**：pytest（搭配 MySQL service container）

詳見 [`.github/workflows/ci.yml`](.github/workflows/ci.yml)。

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
.\run.ps1 -Mode gmail-scan -Max 5 -DryRun
```

---

## License

MIT
