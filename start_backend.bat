@echo off
rem NetOps AI Assistant - backend launcher (double-click to run)
cd /d "%~dp0backend"
set DEVICE_MODE=real
echo [NetOps] Starting backend (DEVICE_MODE=real, GLM-4.5-Air)...
echo [NetOps] Open http://127.0.0.1:8000 in browser after startup.
echo [NetOps] Close this window or press Ctrl+C to stop the backend.
echo [NetOps] Logs: backend\data\server_stdout.log / server_stderr.log
"..\.venv\Scripts\python.exe" -X faulthandler -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level info 1>> "%~dp0backend\data\server_stdout.log" 2>> "%~dp0backend\data\server_stderr.log"
echo [NetOps] Backend exited with code %ERRORLEVEL%. See logs above.
pause
