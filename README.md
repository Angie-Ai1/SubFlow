# SubFlow — Subscription Management Automation

> 自動化訂閱管理系統：整合 Gmail 收據解析、LINE Bot 通知與 Streamlit 管理後台。

---

## 專案目標

現代人訂閱服務繁多（串流、SaaS、雲端儲存等），帳單分散於各信箱難以追蹤。  
SubFlow 的目標是：

1. **自動擷取**：透過 Gmail API 定期掃描收據郵件並解析金額、服務名稱、週期。
2. **手動補齊**：提供 Streamlit 後台讓使用者手動新增或修正訂閱記錄。
3. **正規化儲存**：將所有資料統一寫入 MySQL，維持一致的資料模型。
4. **主動通知**：透過 LINE Bot 在每次扣款前發送提醒，或於異常時即時告警。

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
| 管理後台 | Streamlit |
| 容器化 | Docker + Docker Compose |
| 套件管理 | Poetry |
| 代碼風格 | Ruff (linting) + Black (formatting) |
| CI/CD | GitHub Actions |

---

## 架構說明

```
SubFlow/
├── app/
│   ├── webhook/        # LINE Bot Webhook handler (FastAPI router)
│   ├── parsers/        # Gmail receipt parser logic
│   └── dashboard/      # Streamlit pages & components
│
├── database/
│   ├── models.py       # SQLAlchemy ORM models
│   ├── migrations/     # Alembic migration scripts
│   └── init/           # SQL scripts run on first Docker DB start
│
├── utils/
│   └── logger_config.py  # 全域 Logger — 所有模組共用
│
├── docker/
│   └── Dockerfile
│
├── tests/              # pytest test suite
│
├── .github/
│   └── workflows/
│       └── ci.yml      # Lint → Test pipeline
│
├── docker-compose.yml  # MySQL + App + Dashboard containers
├── pyproject.toml      # Poetry deps + Ruff/Black config
├── .env.example        # Environment variable template
└── .gitignore
```

### 資料流

```
Gmail API ──► Gmail Parser ──► MySQL (SQLAlchemy)
                                      │
Manual Input (Streamlit) ─────────────┘
                                      │
                               Scheduler / Trigger
                                      │
                               LINE Bot Notification
```

---

## 快速開始

### 前置需求

- Docker Desktop 4.x+
- Python 3.11+ (本地開發用)
- Poetry (`pip install poetry`)
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

```bash
poetry install
poetry run uvicorn app.main:app --reload          # API server
poetry run streamlit run app/dashboard/main.py    # Dashboard
```

### 4. 執行測試

```bash
poetry run pytest
```

### 5. 代碼風格檢查

```bash
poetry run ruff check .
poetry run black --check .
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
| `LOG_LEVEL` | 日誌等級 (DEBUG/INFO/WARNING/ERROR) |

---

## CI/CD

推送至 `main` / `develop` 或發 PR 時，GitHub Actions 自動執行：

1. **Lint**：Ruff + Black check
2. **Test**：pytest（搭配 MySQL service container）

詳見 [`.github/workflows/ci.yml`](.github/workflows/ci.yml)。

---

## License

MIT
