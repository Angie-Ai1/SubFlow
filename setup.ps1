#Requires -Version 5.1
# SubFlow Interactive Setup — 互動式安裝腳本
# Run: .\setup.ps1

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=== SubFlow 安裝精靈 ===" -ForegroundColor Cyan
Write-Host ""

# ── 1. 檢查依賴 ──────────────────────────────────────────────────────────────
Write-Host "正在檢查必要工具..." -ForegroundColor Yellow
$missing = @()
foreach ($cmd in @("python", "poetry", "docker")) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        $missing += $cmd
    }
}
if ($missing.Count -gt 0) {
    Write-Host ""
    Write-Host "缺少以下工具，請先安裝後重新執行：" -ForegroundColor Red
    $missing | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
    Write-Host ""
    Write-Host "安裝說明請參考 docs/SETUP.md"
    exit 1
}
Write-Host "所有工具已就緒。" -ForegroundColor Green

# ── 2. 確認 .env 是否已存在 ───────────────────────────────────────────────────
Write-Host ""
if (Test-Path ".env") {
    $overwrite = Read-Host ".env 已存在，是否覆寫？[y/N]"
    if ($overwrite -notin @("y", "Y")) {
        Write-Host "已取消，保留現有 .env。" -ForegroundColor Yellow
        exit 0
    }
}

# ── 3. 收集使用者輸入 ──────────────────────────────────────────────────────────
Write-Host ""
Write-Host "=== MySQL 設定 ===" -ForegroundColor Yellow
Write-Host "（自訂密碼即可，之後不需要記住）"
$MYSQL_PASSWORD      = Read-Host "MySQL 應用密碼（MYSQL_PASSWORD）"
$MYSQL_ROOT_PASSWORD = Read-Host "MySQL Root 密碼（MYSQL_ROOT_PASSWORD）"

Write-Host ""
Write-Host "=== LINE Bot 設定 ===" -ForegroundColor Yellow
Write-Host "前往 https://developers.line.biz/console/ 建立 Messaging API Channel 後取得："
$LINE_TOKEN  = Read-Host "LINE_CHANNEL_ACCESS_TOKEN"
$LINE_SECRET = Read-Host "LINE_CHANNEL_SECRET"

Write-Host ""
Write-Host "=== Gmail 設定 ===" -ForegroundColor Yellow
Write-Host "請先前往 Google Cloud Console 啟用 Gmail API 並下載 credentials.json"
Write-Host "詳細步驟：docs/SETUP.md"
$GMAIL_ADDR = Read-Host "用於掃描收據的 Gmail 信箱"

# ── 4. 寫入 .env ──────────────────────────────────────────────────────────────
$envContent = @"
# ── Application ──────────────────────────
APP_ENV=development
APP_HOST=0.0.0.0
APP_PORT=8000
LOG_LEVEL=INFO

# ── MySQL ─────────────────────────────────
MYSQL_HOST=db
MYSQL_PORT=3306
MYSQL_DATABASE=subflow
MYSQL_USER=subflow_user
MYSQL_PASSWORD=$MYSQL_PASSWORD
MYSQL_ROOT_PASSWORD=$MYSQL_ROOT_PASSWORD

# SQLAlchemy connection string
DATABASE_URL=mysql+pymysql://subflow_user:$MYSQL_PASSWORD@db:3306/subflow

# ── LINE Bot ──────────────────────────────
LINE_CHANNEL_ACCESS_TOKEN=$LINE_TOKEN
LINE_CHANNEL_SECRET=$LINE_SECRET

# ── Google / Gmail API ────────────────────
GOOGLE_CREDENTIALS_PATH=credentials.json
GOOGLE_TOKEN_PATH=token.json
GMAIL_TARGET_ADDRESS=$GMAIL_ADDR

# ── Streamlit ─────────────────────────────
STREAMLIT_SERVER_PORT=8501
STREAMLIT_SERVER_ADDRESS=0.0.0.0

# ── Scheduler ─────────────────────────────
NOTIFY_DAYS_ADVANCE=3
CRON_NOTIFICATION_HOUR=9
"@

[System.IO.File]::WriteAllText((Join-Path $PWD ".env"), $envContent, [System.Text.Encoding]::UTF8)

# ── 5. 完成提示 ───────────────────────────────────────────────────────────────
Write-Host ""
Write-Host ".env 已成功建立！" -ForegroundColor Green
Write-Host ""
Write-Host "接下來的步驟："
Write-Host "  1. 將 credentials.json 放到專案根目錄（Gmail OAuth 憑證）"
Write-Host "  2. docker compose up -d --build"
Write-Host "  3. 在 LINE Developers Console 設定 Webhook URL（需搭配 ngrok）"
Write-Host ""
Write-Host "完整說明請參考 docs/SETUP.md"
Write-Host ""
