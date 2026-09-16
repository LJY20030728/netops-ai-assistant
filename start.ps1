# 一键启动 NetOps AI Assistant（Windows PowerShell）
# 首次运行会自动创建 venv 并完成知识库入库；之后重复运行只启动服务。
# 使用：右键"使用 PowerShell 运行"，或在本目录执行  .\start.ps1
# 停止：在窗口内按 Ctrl+C

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

if (-not (Test-Path .venv\Scripts\python.exe)) {
    Write-Host "[1/3] 创建虚拟环境 .venv ..."
    python -m venv .venv
}

$py = "$PSScriptRoot\.venv\Scripts\python.exe"

if (-not (Test-Path backend\data\meta.json)) {
    Write-Host "[2/3] 首次运行：知识库入库..."
    Push-Location backend
    & $py -m app.rag.ingest
    Pop-Location
} else {
    Write-Host "[2/3] 知识库已存在，跳过入库（如需重灌请删除 backend\data）"
}

Write-Host "[3/3] 启动服务 -> http://127.0.0.1:8000  (Ctrl+C 停止)"
& $py -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir backend
