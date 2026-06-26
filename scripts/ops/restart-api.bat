@echo off
echo ===== 重启 Quant API Server =====

:: 杀掉旧进程
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000"') do (
  if not "%%a"=="" taskkill /F /PID %%a >nul 2>&1
)
echo [OK] Killed old server on :8000

:: 等 2 秒
ping -n 3 127.0.0.1 >nul

:: 启动新服务
cd /d E:\hermes\workspace\Quant
set PYTHONPATH=E:\hermes\workspace\Quant
set DATABASE_URL=sqlite:///E:/hermes/workspace/Quant/quant/storage/quant.db

echo [OK] Starting uvicorn on :8000...
start /B "" "E:\hermes\workspace\Quant\quant\.venv\Scripts\python.exe" -m uvicorn apps.api.main:app --host 0.0.0.0 --port 8000

:: 等启动完成
ping -n 5 127.0.0.1 >nul

:: 验证
echo.
echo [CHECK] Testing /api/watchlist...
powershell -Command "try { $r = Invoke-WebRequest -Uri 'http://localhost:8000/api/watchlist' -UseBasicParsing -TimeoutSec 3; Write-Host '  OK: '$r.Content } catch { Write-Host '  FAIL: '$_ }"

echo.
echo ===== DONE =====
pause
