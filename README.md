# SubFlow — Subscription Management Automation

> 自動化訂閱管理系統：整合 Gmail 收據解析、LINE Bot 通知與 Streamlit 管理後台。

---

## 專案目標

現代人訂閱服務繁多（串流、SaaS、雲端儲存等），帳單分散於各信箱難以追蹤。  
SubFlow 的目標是：

1. **自動擷取**：透過 Gmail API 定期掃描收據郵件，解析金額、服務名稱、計費週期。
2. **手動補齊**：提供 Streamlit 後台讓使用者手動新增或修正訂閱記錄。
3. **正規化儲存**：所有資料統一寫入 MySQL，維持一致的資料模型。
4. **主動通知**：透過 LINE Bot 查詢訂閱清單，後續擴充扣款前提醒功能。

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
| 容器化 | Docker + Docker Compose |
| 套件管理 | Poetry |
| 代碼風格 | Ruff (linting) + Black (formatting) |
| CI/CD | GitHub Actions |

---

## 架構說明

```
SubFlow/
├── app/
│   ├── main.py             # FastAPI 入口點，掛載所有 router
│   ├── config.py           # Pydantic Settings（讀 .env）
│   ├── webhook/
│   │   ├── router.py       # LINE Webhook endpoint
│   │   ├── handlers.py     # FollowEvent / UnfollowEvent / MessageEvent 處理
│   │   └── line_client.py  # MessagingApi 單例
│   ├── parsers/
│   │   ├── gmail_auth.py   # OAuth2 / Service Account 認證
│   │   ├── gmail_fetcher.py# 抓取收據信件（關鍵字過濾）
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
│   └── logger_config.py    # 全域 Logger（結構化 JSON 可選）
│
├── scripts/
│   └── gmail_scan.py       # 本地 CLI：手動觸發 Gmail 掃描（--dry-run 支援）
│
├── docker/
│   └── Dockerfile
│
├── tests/                  # pytest test suite
│
├── .github/
│   └── workflows/
│       └── ci.yml          # Lint → Test pipeline
│
├── run.ps1                 # 啟動腳本（api / dashboard / gmail-scan 三模式）
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
| `POST` | `/webhook/line` | LINE Webhook callback |
| `POST` | `/ops/gmail-import` | 手動觸發 Gmail 收據匯入 |

### 資料模型

| 資料表 | 說明 |
|---|---|
| `subscriptions` | 訂閱主檔（名稱、金額、週期、下次扣款日） |
| `billing_records` | 每筆扣款紀錄，含 `gmail_message_id` 防重複匯入 |
| `line_users` | 已追蹤 LINE Bot 的使用者 |

---

## 快速開始

### 前置需求

- Docker Desktop 4.x+
- Python 3.11+（本地開發用）
- Poetry（`pip install poetry`）
- LINE Developer 帳號 + Messaging API Channel
- Google Cloud Project + Gmail API 已啟用

### 1. Clone & 設定環境變數

```bash
git clone https://github.com/your-org/subflow.git
cd subflow
cp .env.example .env
# 編輯 .env，填入 LINE、MySQL、Google 憑證
```

### 2. 啟動容器

```bash
docker compose up -d --build
```

服務啟動後：
- FastAPI (LINE Webhook)：`http://localhost:8000`
- Streamlit 後台：`http://localhost:8501`
- MySQL：`localhost:3306`

### 3. 本地開發（不使用 Docker）

**安裝依賴**

```bash
poetry install
```

**啟動 API server**

```powershell
.\run.ps1 -Mode api
```

**啟動 Dashboard**

```powershell
.\run.ps1 -Mode dashboard
```

**手動觸發 Gmail 掃描**

```powershell
.\run.ps1 -Mode gmail-scan -Max 50          # 掃描最近 50 封
.\run.ps1 -Mode gmail-scan -DryRun          # 只解析，不寫入 DB
```

> 所有執行日誌會同步寫入 `logs/` 目錄。

### 4. 執行測試

```powershell
.\run.ps1 -Mode api   # 確認環境後 Ctrl+C
poetry run pytest
```

### 5. 代碼風格檢查

```bash
poetry run ruff check .
poetry run black --check .
```

### 6. 資料庫 Migration

```bash
# 產生新 migration
poetry run alembic revision --autogenerate -m "描述變更"
# 套用至最新版本
poetry run alembic upgrade head
```

---

## 環境變數說明

詳見 [`.env.example`](.env.example)。關鍵變數：

| 變數 | 說明 |
|---|---|
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE Bot 長期存取 Token |
| `LINE_CHANNEL_SECRET` | 用於驗證 Webhook 簽名 |
| `DATABASE_URL` | SQLAlchemy 連線字串 |
| `GOOGLE_CREDENTIALS_PATH` | OAuth2 credentials.json 路徑 |
| `GOOGLE_TOKEN_PATH` | OAuth token 快取路徑（首次認證後自動產生） |
| `GMAIL_TARGET_ADDRESS` | 用於掃描收據的 Gmail 信箱 |
| `LOG_LEVEL` | 日誌等級（DEBUG / INFO / WARNING / ERROR） |

---

## LINE Bot 指令

| 輸入 | 功能 |
|---|---|
| `訂閱清單` / `清單` / `list` | 列出所有啟用中的訂閱及下次扣款日 |
| `說明` / `help` / `?` | 顯示指令說明 |

---

## CI/CD

推送至 `main` / `develop` 或發 PR 時，GitHub Actions 自動執行：

1. **Lint**：Ruff + Black check
2. **Test**：pytest（搭配 MySQL service container）

詳見 [`.github/workflows/ci.yml`](.github/workflows/ci.yml)。

---

## License

MIT
