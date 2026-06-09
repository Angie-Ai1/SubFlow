#Requires -Version 5.1
# SubFlow Interactive Setup — 互動式安裝腳本
# Run: .\setup.ps1

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=== SubFlow 安裝精靈 ===" -ForegroundColor Cyan
Write-Host ""

# ── Helper：必填輸入，空白則重問 ─────────────────────────────────────────────
function Read-Required {
    param(
        [string]$Prompt,
        [int]$MinLength = 1,
        [string]$Pattern = "",
        [string]$PatternHint = ""
    )
    while ($true) {
        $value = (Read-Host $Prompt).Trim()
        if ($value.Length -lt $MinLength) {
            if ($MinLength -eq 1) {
                Write-Host "  ✗ 不可空白，請重新輸入。" -ForegroundColor Red
            } else {
                Write-Host "  ✗ 最少需 $MinLength 個字元，請重新輸入。" -ForegroundColor Red
            }
            continue
        }
        if ($Pattern -ne "" -and $value -notmatch $Pattern) {
            Write-Host "  ✗ 格式不正確（$PatternHint），請重新輸入。" -ForegroundColor Red
            continue
        }
        return $value
    }
}

# ── 1. 檢查依賴，缺少時顯示下載連結 ─────────────────────────────────────────
$toolInfo = [ordered]@{
    "python" = @{ Link = "https://www.python.org/downloads/";                Note = "安裝時勾選「Add Python to PATH」" }
    "poetry" = @{ Link = "https://python-poetry.org/docs/#installation";     Note = "安裝後重開終端機" }
    "docker" = @{ Link = "https://www.docker.com/products/docker-desktop/";  Note = "安裝後啟動 Docker Desktop" }
}

Write-Host "正在檢查必要工具..." -ForegroundColor Yellow
$missing = @()
foreach ($cmd in $toolInfo.Keys) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        $missing += $cmd
    }
}

if ($missing.Count -gt 0) {
    Write-Host ""
    Write-Host "缺少以下工具，請安裝後重新執行本腳本：" -ForegroundColor Red
    foreach ($cmd in $missing) {
        Write-Host ""
        Write-Host "  ✗ $cmd" -ForegroundColor Red
        Write-Host "    下載：$($toolInfo[$cmd].Link)" -ForegroundColor Cyan
        Write-Host "    提示：$($toolInfo[$cmd].Note)"
    }
    Write-Host ""
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
Write-Host "（自訂即可，建議 8 字元以上）"
$MYSQL_PASSWORD      = Read-Required "MySQL 應用密碼（MYSQL_PASSWORD）" -MinLength 8
$MYSQL_ROOT_PASSWORD = Read-Required "MySQL Root 密碼（MYSQL_ROOT_PASSWORD）" -MinLength 8

Write-Host ""
Write-Host "=== LINE Bot 設定 ===" -ForegroundColor Yellow
Write-Host "前往以下網址建立 Messaging API Channel 後取得："
Write-Host "  https://developers.line.biz/console/" -ForegroundColor Cyan
Write-Host ""

$LINE_TOKEN = Read-Required "LINE_CHANNEL_ACCESS_TOKEN"
# LINE access token 通常超過 150 字元，偏短可能是貼錯
if ($LINE_TOKEN.Length -lt 100) {
    Write-Host "  ⚠  Token 長度偏短（典型值 > 150 字元），請確認是否完整貼上。" -ForegroundColor Yellow
}

$LINE_SECRET = Read-Required "LINE_CHANNEL_SECRET"
# LINE channel secret 固定為 32 位小寫英數字
if ($LINE_SECRET -notmatch "^[0-9a-f]{32}$") {
    Write-Host "  ⚠  Channel Secret 通常為 32 位小寫英數字，請確認是否正確。" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Gmail 設定 ===" -ForegroundColor Yellow
Write-Host "請先前往 Google Cloud Console 啟用 Gmail API 並下載 credentials.json"
Write-Host "  https://console.cloud.google.com/" -ForegroundColor Cyan
Write-Host "詳細步驟：docs/SETUP.md"
Write-Host ""

# 信箱格式強制驗證
$GMAIL_ADDR = Read-Required "用於掃描收據的 Gmail 信箱" `
    -Pattern "^[^@\s]+@[^@\s]+\.[^@\s]+$" `
    -PatternHint "需為有效的電子郵件格式，例如 yourname@gmail.com"

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
