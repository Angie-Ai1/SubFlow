# SubFlow — Subscription Management Automation

> 一個指令啟動，自動從 Gmail 解析訂閱帳單、LINE Bot 扣款前提醒、Streamlit 後台一覽所有費用。

---

## 三秒快速啟動

**前提：已安裝 Docker Desktop**

```powershell
# 1. Clone
git clone https://github.com/your-org/subflow.git
cd subflow

# 2. 互動式建立 .env（腳本會引導你輸入 LINE / Gmail API Key）
.\setup.ps1

# 3. 啟動所有服務（含自動 DB Migration）
docker compose up -d --build
```

```bash
# 確認服務狀態（三個服務都應顯示 running）
docker compose ps

# 查看啟動日誌（若服務沒反應可用此除錯）
docker compose logs -f app
```

完成後開啟：
- **後台**：http://localhost:8501
- **API**：http://localhost:8000/docs

---

## 需要準備的 API Key

| 服務 | 用途 | 取得方式 |
|---|---|---|
| LINE Messaging API | Bot 通知 + Webhook | [LINE Developers Console](https://developers.line.biz/console/) |
| Google Gmail API | 自動解析收據郵件 | [Google Cloud Console](https://console.cloud.google.com/) → 啟用 Gmail API |

詳細申請步驟請見 **[docs/SETUP.md](docs/SETUP.md)**。

---

## 核心功能

| 功能 | 說明 |
|---|---|
| Gmail 自動解析 | 每 6 小時掃描信箱，擷取訂閱金額、服務名稱、計費週期 |
| LINE Bot 查詢 | 輸入「訂閱清單」、「即將到期」、「搜尋 Netflix」即可查詢 |
| 扣款前推播提醒 | 每日定時推播即將扣款的訂閱（可設定提前天數） |
| Streamlit 後台 | 視覺化管理訂閱、查看月支出趨勢、手動新增記錄 |

---

## LINE Bot 指令

| 輸入 | 功能 |
|---|---|
| `訂閱清單` / `list` | 列出所有啟用中的訂閱及下次扣款日 |
| `即將到期` / `upcoming` | 列出 N 天內扣款的訂閱 |
| `搜尋 <名稱>` / `search <名稱>` | 模糊搜尋訂閱 |
| `停用 <名稱>` / `disable <名稱>` | 停用訂閱 |
| `說明` / `help` | 顯示完整指令說明 |

---

## 技術棧

| 層次 | 技術 |
|---|---|
| Web / Webhook | FastAPI + Uvicorn |
| 通知 | LINE Messaging API (line-bot-sdk v3) |
| 郵件解析 | Google Gmail API |
| 資料庫 | MySQL 8.4 + SQLAlchemy 2.x + Alembic |
| 管理後台 | Streamlit + Altair |
| 排程 | APScheduler |
| 容器化 | Docker + Docker Compose |
| 套件管理 | Poetry |
| CI/CD | GitHub Actions（Lint + Test） |

---

## 文檔

- **[docs/SETUP.md](docs/SETUP.md)** — 完整安裝教學（LINE Bot、Gmail OAuth、ngrok 設定）
- **[.env.example](.env.example)** — 所有環境變數說明

---

## License

MIT
