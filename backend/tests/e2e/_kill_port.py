# -*- coding: utf-8 -*-
"""按端口杀进程。"""
import subprocess
import sys

port = sys.argv[1] if len(sys.argv) > 1 else "8001"
ps = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     f"Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess"],
    capture_output=True, text=True
)
pids = [p for p in ps.stdout.split() if p.isdigit()]
for pid in pids:
    subprocess.run(["taskkill", "/PID", pid, "/F"], capture_output=True)
    print("killed", pid)
print("done")
