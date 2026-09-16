# -*- coding: utf-8 -*-
# run_tests.ps1 — NetOps AI Assistant 一键测试编排（Windows PowerShell）
# 用法（项目根目录）：
#   powershell -ExecutionPolicy Bypass -File backend\tests\run_tests.ps1
# 说明：所有后端实例在脚本内起、测、停（跨进程的 Start-Process 服务可能被系统回收，
#       因此"起服务+跑测试+清理"必须放在同一个进程生命周期内）。
$ErrorActionPreference = "Continue"
$Root = (Resolve-Path "$PSScriptRoot\..\..").Path
$Backend = Join-Path $Root "backend"
$Py = Join-Path $Root ".venv\Scripts\python.exe"
$Docker = "C:\Users\Curry\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
$env:PYTHONPATH = $Backend

$Summary = @()

function Stop-AllUvicorn {
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -match 'uvicorn' } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 2
}

function Start-Backend([string]$Mode, [int]$Port) {
    $env:DEVICE_MODE = $Mode
    $p = Start-Process -FilePath $Py -ArgumentList "-X","utf8","-m","uvicorn","app.main:app","--host","127.0.0.1","--port","$Port" `
        -WorkingDirectory $Backend -RedirectStandardOutput (Join-Path $Root "tools\uvicorn_out.log") `
        -RedirectStandardError (Join-Path $Root "tools\uvicorn_err.log") -WindowStyle Hidden -PassThru
    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Seconds 1
        try {
            $h = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/health" -UseBasicParsing -TimeoutSec 3
            return $p
        } catch {}
    }
    Write-Host "[FAIL] backend $Mode port ${Port} start timeout" -ForegroundColor Red
    return $null
}

function Start-AuthServer([int]$Port) {
    $p = Start-Process -FilePath $Py -ArgumentList "-X","utf8","tests\_auth_server.py" `
        -WorkingDirectory $Backend -RedirectStandardOutput (Join-Path $Root "tools\auth_out.log") `
        -RedirectStandardError (Join-Path $Root "tools\auth_err.log") -WindowStyle Hidden -PassThru
    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Seconds 1
        try {
            $null = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/health" -UseBasicParsing -TimeoutSec 3
            return $p
        } catch {}
    }
    return $null
}

function Stop-Proc($p) {
    if ($p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
}

function Run-Test([string]$Name, [string]$Script) {
    Write-Host "`n===== $Name =====" -ForegroundColor Cyan
    $tmp = Join-Path $env:TEMP ("testout_" + [guid]::NewGuid().ToString("N") + ".txt")
    Push-Location $Backend
    & $Py -X utf8 "tests\$Script" *> $tmp
    Pop-Location
    $out = Get-Content $tmp -Raw -Encoding UTF8
    Remove-Item $tmp -Force -ErrorAction SilentlyContinue
    $m = [regex]::Match($out, "(\d+) 通过(?:，(\d+) 失败)?")
    if ($m.Success) {
        $pass = [int]$m.Groups[1].Value
        $fail = if ($m.Groups[2].Success) { [int]$m.Groups[2].Value } else { 0 }
        $script:Summary += [PSCustomObject]@{ 测试 = $Name; 通过 = $pass; 失败 = $fail; 状态 = if ($fail -eq 0) { "PASS" } else { "FAIL" } }
        Write-Host "  结果：$pass 通过，$fail 失败" -ForegroundColor $(if ($fail -eq 0) { "Green" } else { "Red" })
    } else {
        $tail = ($out -split "`n" | Where-Object { $_ -match 'FAIL|Error|Traceback' } | Select-Object -Last 3) -join " | "
        $script:Summary += [PSCustomObject]@{ 测试 = $Name; 通过 = 0; 失败 = 1; 状态 = "FAIL(无结果输出)" }
        Write-Host "  无法解析结果：$tail" -ForegroundColor Red
    }
}

# 0. 前置检查
Write-Host "===== 前置检查 =====" -ForegroundColor Cyan
$dv = & $Docker version --format "{{.Server.Version}}" 2>&1
Write-Host "  Docker 引擎: $($dv -join '')"
$containers = & $Docker ps --filter "name=frr" --format "{{.Names}}" 2>&1
Write-Host "  FRR 容器: $($containers -join ', ')"
if (($containers -join '' ) -notmatch 'frr[123]') {
    Write-Host "  [WARN] FRR 容器未全部运行，先执行 docker compose -f docker-compose.frr.yml up -d"
}

# 参数：-Quick 只跑快速回归组（无 LLM，分钟级）；默认 Full 全量（含真实模型调用，10-30 分钟）
param([switch]$Quick)

# 1. real 模式组
Stop-AllUvicorn
$p = Start-Backend "real" 8000
if ($p) {
    Run-Test "FRR 故障实验室（真实容器）" "test_frr_lab.py"
    Run-Test "FRR 端到端（协议收敛）" "test_frr_e2e.py"
    Run-Test "工程 API" "test_engineering_api.py"
    if (-not $Quick) {
        Run-Test "安全层（注入/审计/guard）" "test_security_api.py"
        Run-Test "RAG 扩展（8 场景命中）" "test_rag_expanded.py"
    }
    Stop-Proc $p
}

# 2. simulate 模式组（场景切换）
Stop-AllUvicorn
$p = Start-Backend "simulate" 8000
if ($p) {
    Run-Test "仿真场景切换 API" "test_scenarios_api.py"
    Stop-Proc $p
}

# 3. auth 实例组（RBAC，仅 Full）
if (-not $Quick) {
    Stop-AllUvicorn
    $p = Start-AuthServer 8001
    if ($p) {
        Run-Test "RBAC 权限矩阵（8001）" "test_rbac_api.py"
        Stop-Proc $p
    }
}

# 4. 恢复 real 演示环境
Stop-AllUvicorn
$p = Start-Backend "real" 8000
if ($p) { Write-Host "`n演示环境已恢复：DEVICE_MODE=real @ 127.0.0.1:8000" -ForegroundColor Green }

# 5. 汇总
Write-Host "`n===================== 汇总 =====================" -ForegroundColor Cyan
$Summary | Format-Table -AutoSize
$totalFail = ($Summary | Measure-Object -Property 失败 -Sum).Sum
$totalPass = ($Summary | Measure-Object -Property 通过 -Sum).Sum
Write-Host "合计：$totalPass 通过 / $totalFail 失败" -ForegroundColor $(if ($totalFail -eq 0) { "Green" } else { "Red" })
exit $totalFail
