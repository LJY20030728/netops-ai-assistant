# -*- coding: utf-8 -*-
"""Patch ci.ps1: guard Test-Suite against $ErrorActionPreference='Stop' + native stderr."""
from pathlib import Path

p = Path(__file__).resolve().parents[1] / "ci.ps1"
raw = p.read_bytes()
has_bom = raw.startswith(b"\xef\xbb\xbf")
text = raw.decode("utf-8-sig" if has_bom else "utf-8")

old = """    Push-Location $Backend
    & $Py -X utf8 (Join-Path $Backend $testScript) 2>&1 | Out-Null
    $code = $LASTEXITCODE
    Pop-Location"""
new = """    Push-Location $Backend
    # 测试脚本可能向 stderr 写预期输出（如仿真 SSH 的 Socket 10054 模拟场景），
    # 避免 $ErrorActionPreference='Stop' 把 native stderr 误判为异常而中断 CI。
    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & $Py -X utf8 (Join-Path $Backend $testScript) 2>&1 | Out-Null
    $code = $LASTEXITCODE
    $ErrorActionPreference = $prevEAP
    Pop-Location"""
assert old in text, "pattern not found"
text = text.replace(old, new)
p.write_bytes(("\ufeff" + text if has_bom else text).encode("utf-8"))
print("ci.ps1 patched OK (EAP guard)")
