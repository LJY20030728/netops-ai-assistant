﻿# NetOps AI Assistant · 一键 CI（本地全量回归）
# 用法（PowerShell）：
#   powershell -ExecutionPolicy Bypass -File .\ci.ps1
# 流程：语法检查 → 确保 8000（主服务）与 8001（鉴权实例）在线（缺失则拉起，结束按标记清理）
#      → 单元测试（不依赖服务） → API 集成测试（依赖对应服务） → 汇总
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root 'backend'
$Py = Join-Path $Root '.venv\Scripts\python.exe'   # venv 位于项目根
$Base = 'http://127.0.0.1:8000'
$BaseAuth = 'http://127.0.0.1:8001'

$PASS = 0; $FAIL = 0; $SKIP = 0
$StartedByUs = @{ 8000 = $false; 8001 = $false }

function Ensure-Service($port) {
    $health = "http://127.0.0.1:$port/api/health"
    try { $null = Invoke-RestMethod -Uri $health -TimeoutSec 5; Write-Host "  $port 已在运行，直接复用。"; return }
    catch {}
    Write-Host "  $port 未运行，正在启动..."
    $args = @('-m','uvicorn','app.main:app','--host','127.0.0.1','--port',"$port",'--app-dir',$Backend)
    if ($port -eq 8001) {   # 鉴权实例：开启认证并注入令牌→角色映射（子进程继承）
        $env:AUTH_ENABLED = 'true'
        $env:API_TOKENS = '{"viewer-tok":"viewer","op-tok":"operator","admin-tok":"admin"}'
    }
    $p = Start-Process -FilePath $Py -ArgumentList $args -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $Backend "ci_out_$port.log") `
        -RedirectStandardError  (Join-Path $Backend "ci_err_$port.log") -PassThru
    Remove-Item Env:AUTH_ENABLED -ErrorAction SilentlyContinue
    Remove-Item Env:API_TOKENS -ErrorAction SilentlyContinue
    $global:StartedByUs["$port"] = $true
    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 1
        try { $null = Invoke-RestMethod -Uri $health -TimeoutSec 2; $ready = $true; break } catch {}
    }
    if (-not $ready) {
        Write-Host "  $port 30 秒内未就绪，日志尾部：" -ForegroundColor Red
        if (Test-Path (Join-Path $Backend "ci_err_$port.log")) { Get-Content (Join-Path $Backend "ci_err_$port.log") -Tail 20 }
        if ($StartedByUs["$port"]) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
        exit 1
    }
    Write-Host "  $port 就绪。"
}

function Test-Suite($name, $testScript, $needsServer, $port = 8000) {
    Write-Host "`n===== $name =====" -ForegroundColor Cyan
    if ($needsServer) {
        $health = "http://127.0.0.1:$port/api/health"
        try { $null = Invoke-RestMethod -Uri $health -TimeoutSec 5 }
        catch { Write-Host "  [SKIP] $testScript（$port 未就绪）" -ForegroundColor Yellow; $global:SKIP++; return }
    }
    Push-Location $Backend
    # 测试脚本可能向 stderr 写预期输出（如仿真 SSH 的 Socket 10054 模拟场景），
    # 避免 $ErrorActionPreference='Stop' 把 native stderr 误判为异常而中断 CI。
    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & $Py -X utf8 (Join-Path $Backend $testScript) 2>&1 | Out-Null
    $code = $LASTEXITCODE
    $ErrorActionPreference = $prevEAP
    Pop-Location
    if ($code -eq 0) { $global:PASS++; Write-Host "  [PASS] $name" -ForegroundColor Green }
    else { $global:FAIL++; Write-Host "  [FAIL] $name（exit=$code）" -ForegroundColor Red }
}

Write-Host "== 1/3 语法检查（compileall）==" -ForegroundColor Cyan
Push-Location $Backend
& $Py -m compileall -q app tests
if ($LASTEXITCODE -ne 0) { Pop-Location; Write-Host '语法检查失败，中止 CI' -ForegroundColor Red; exit 1 }
Pop-Location

Write-Host "`n== 2/3 确保服务在线 ==" -ForegroundColor Cyan
Ensure-Service 8000
Ensure-Service 8001

Write-Host "`n== 3/3 测试套件 ==" -ForegroundColor Cyan
Test-Suite '安全层单元测试'        'tests\test_security_unit.py'        $false
Test-Suite '场景库单元测试'        'tests\test_scenarios_unit.py'       $false
Test-Suite '多设备协同+时序推理'   'tests\test_multi_device.py'         $false
Test-Suite '仿真 SSH×Netmiko 真实链路' 'tests\test_sim_ssh.py'          $false
Test-Suite '安全层 API 测试'       'tests\test_security_api.py'         $true
Test-Suite 'RBAC API 测试'         'tests\test_rbac_api.py'             $true 8001
Test-Suite '认证 /auth/me 测试'    'tests\test_auth_me.py'              $true 8001
Test-Suite '场景 API 测试'         'tests\test_scenarios_api.py'        $true
Test-Suite '场景 RBAC 测试'        'tests\test_scenarios_rbac.py'       $true 8001
Test-Suite 'RAG 冒烟测试'          'tests\test_rag_smoke.py'            $true
Test-Suite 'RAG 扩充检索测试'      'tests\test_rag_expanded.py'         $true
Test-Suite '入库幂等测试'          'tests\test_ingest_idempotent.py'    $true

Write-Host "`n清理：停止本次 CI 拉起的服务。"
foreach ($port in @(8000, 8001)) {
    if ($StartedByUs["$port"]) {
        Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*app.main:app*$port*" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    }
}

Write-Host "`n===== CI 汇总：$PASS 通过 / $FAIL 失败 / $SKIP 跳过 =====" -ForegroundColor $(if ($FAIL -eq 0) { 'Green' } else { 'Red' })
if ($FAIL -gt 0) { exit 1 }
