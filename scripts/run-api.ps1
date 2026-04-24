$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

if (-not $env:AOP_DATABASE_URL -and -not (Test-Path -LiteralPath "config.toml")) {
    Write-Host "数据库未配置。"
    Write-Host "请创建 config.toml 文件或设置 AOP_DATABASE_URL 环境变量。"
    Write-Host "参考示例: Copy-Item config.toml.example config.toml"
    exit 1
}

uv run uvicorn agent_platform.main:app --reload
