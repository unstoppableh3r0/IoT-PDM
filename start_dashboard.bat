@echo off
echo ====================================
echo   Starting IoT-PDM Dashboard
echo ====================================
echo.

echo [1/2] Starting Frontend Server...
cd /d D:\IOT-Proj\IoT-PDM\frontend
start "IoT-PDM Dashboard" npm run dev

echo.
echo [2/2] Waiting for frontend to start...
timeout /t 8 /nobreak >nul

echo.
echo [3/3] Opening browser...
start http://localhost:5173

echo.
echo ====================================
echo   Dashboard Started Successfully!
echo ====================================
echo.
echo Dashboard URL: http://localhost:5173
echo Frontend running in separate window
echo Press Ctrl+C in frontend window to stop
echo.
pause
