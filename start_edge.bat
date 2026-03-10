@echo off
echo ====================================
echo   Starting IoT-PDM Edge Device
echo ====================================
echo.

REM Check if running Mosquitto locally
echo [1/2] Checking MQTT broker...
netstat -an | findstr ":1883" >nul
if %errorlevel% equ 0 (
    echo    ^> MQTT broker already running
) else (
    echo    ^> Starting Mosquitto...
    REM Uncomment if using local broker:
    REM start "" "C:\Program Files\mosquitto\mosquitto.exe" -c "C:\Program Files\mosquitto\mosquitto.conf"
    echo    ^> Using public broker (broker.hivemq.com)
)

echo.
echo [2/2] Starting Backend Server...
cd /d D:\IOT-Proj\IoT-PDM\backend
call d:\IOT-Proj\.venv\Scripts\Activate.ps1
start "IoT-PDM Backend" python server.py

echo.
echo ====================================
echo   Edge Device Started Successfully!
echo ====================================
echo.
echo Backend running in separate window
echo Press Ctrl+C in backend window to stop
echo.
pause
