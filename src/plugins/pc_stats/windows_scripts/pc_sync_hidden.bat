@echo off
setlocal enabledelayedexpansion

:: ==========================================
:: CONFIGURATION SECTION
:: ==========================================
:: Change these to match your Raspberry Pi setup
set "DEST_USER=pi"
set "DEST_HOST=raspberrypi.local"
set "DEST_PATH=/home/pi/pc_stats.txt"
set "WORKING_DIR=C:\PiTools"
set "SYNC_INTERVAL=60"
:: ==========================================

cd /d "%WORKING_DIR%"

:loop
if not exist "%WORKING_DIR%\sync_active.txt" exit

:: 1. Performance Stats
for /f "tokens=2 delims==" %%a in ('wmic cpu get loadpercentage /value') do set "cpu=%%a"
for /f "tokens=2 delims==" %%a in ('wmic os get freephysicalmemory /value') do set /a "mem=%%a / 1024"
set "gpu=0"
for /f "tokens=1" %%g in ('nvidia-smi --query-gpu^=utilization.gpu --format^=csv^,noheader^,nounits 2^>nul') do set "gpu=%%g"

:: 2. SSD Space
for /f "tokens=1" %%d in ('powershell -command "[math]::round(((Get-Volume -DriveLetter C).SizeRemaining / 1GB), 1)"') do set "disk=%%d"

:: 3. Network IPs
for /f "tokens=1" %%i in ('powershell -command "(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -notlike '*Loopback*' -and $_.InterfaceAlias -notlike '*Virtual*' }).IPAddress | Select-Object -First 1"') do set "localip=%%i"
for /f "tokens=1" %%e in ('powershell -command "(Invoke-WebRequest -uri 'https://api.ipify.org').Content"') do set "extip=%%e"

:: 4. Active Window
for /f "usebackq tokens=*" %%w in (`powershell -command "$title = (Get-Process | Where-Object { $_.MainWindowTitle }).MainWindowTitle | Select-Object -First 1; if ($title.Length -gt 20) { $title.Substring(0,20) } else { $title }"`) do set "win=%%w"

:: Build Data File
echo cpu: %cpu%%% > pc_stats.txt
echo gpu: %gpu%%% >> pc_stats.txt
echo ram: %mem%MB >> pc_stats.txt
echo ssd: %disk%GB Free >> pc_stats.txt
echo localip: %localip% >> pc_stats.txt
echo extip: %extip% >> pc_stats.txt
echo focus: %win% >> pc_stats.txt

:: Transfer to Pi
scp -q -o ConnectTimeout=5 pc_stats.txt %DEST_USER%@%DEST_HOST%:%DEST_PATH% >nul 2>&1
del pc_stats.txt

timeout /t %SYNC_INTERVAL% /nobreak >nul
goto loop
