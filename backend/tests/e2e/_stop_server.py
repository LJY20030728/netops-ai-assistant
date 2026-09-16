# -*- coding: utf-8 -*-
"""查找并停止占用 8000 端口的 uvicorn 进程。"""
import subprocess

out = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | Where-Object { $_.CommandLine -like '*uvicorn*8000*' } | ForEach-Object { $_.ProcessId }"],
    capture_output=True, text=True
)
pids = [p for p in out.stdout.split() if p.isdigit()]
print("uvicorn pids:", pids)
for pid in pids:
    subprocess.run(["taskkill", "/PID", pid, "/F"], capture_output=True)
    print("killed", pid)
