@echo off
title Bridge Agent - Service Installer
echo ========================================
echo Installing as Windows Service
echo ========================================
echo.

REM Check admin rights
net session >nul 2>&1
if errorlevel 1 (
    echo.
    echo [ERROR] Please run as Administrator!
    echo.
    echo Right-click on this file and select "Run as administrator"
    echo.
    pause
    exit /b 1
)

echo [1/4] Checking NSSM...
echo.

REM Download NSSM if not exists
if not exist "nssm.exe" (
    echo NSSM not found. Downloading...
    echo.
    echo This may take a few moments...
    echo.
    
    REM Download using PowerShell with progress
    powershell -ExecutionPolicy Bypass -Command "try { $ProgressPreference = 'SilentlyContinue'; Invoke-WebRequest -Uri 'https://nssm.cc/ci/nssm-2.24-101-g897c7ad.zip' -OutFile 'nssm.zip' -UseBasicParsing; exit 0 } catch { Write-Host $_.Exception.Message; exit 1 }"
    
    if errorlevel 1 (
        echo.
        echo [ERROR] Failed to download NSSM automatically.
        echo.
        echo Please:
        echo 1. Download NSSM from: https://nssm.cc/download
        echo 2. Extract nssm.exe from win64 folder
        echo 3. Copy nssm.exe to this folder
        echo 4. Run this script again
        echo.
        pause
        exit /b 1
    )
    
    if not exist "nssm.zip" (
        echo.
        echo [ERROR] Download failed - nssm.zip not found
        echo.
        pause
        exit /b 1
    )
    
    echo [2/4] Extracting NSSM...
    powershell -ExecutionPolicy Bypass -Command "try { Expand-Archive -Path 'nssm.zip' -DestinationPath '.' -Force; exit 0 } catch { Write-Host $_.Exception.Message; exit 1 }"
    
    if errorlevel 1 (
        echo.
        echo [ERROR] Failed to extract NSSM
        echo.
        pause
        exit /b 1
    )
    
    REM Copy nssm.exe from extracted folder
    if exist "nssm-2.24-101-g897c7ad\win64\nssm.exe" (
        copy "nssm-2.24-101-g897c7ad\win64\nssm.exe" "nssm.exe" >nul
        echo NSSM extracted successfully!
        echo.
    ) else (
        echo.
        echo [ERROR] Could not find nssm.exe in extracted files
        echo.
        dir /s /b nssm*.exe
        echo.
        pause
        exit /b 1
    )
    
    REM Cleanup
    if exist "nssm.zip" del nssm.zip
    if exist "nssm-2.24-101-g897c7ad" rmdir /s /q nssm-2.24-101-g897c7ad
    
) else (
    echo NSSM already exists. Skipping download.
    echo.
)

echo [3/4] Checking Python...
set CURRENT_DIR=%~dp0

REM Find Python executable
where python >nul 2>&1
if errorlevel 1 (
    echo.
    echo [ERROR] Python not found in PATH!
    echo.
    echo Please install Python from: https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation
    echo.
    pause
    exit /b 1
)

REM Get Python path
for /f "tokens=*" %%i in ('where python') do set PYTHON_PATH=%%i

echo Found Python: %PYTHON_PATH%
echo.

REM Install Python dependencies
echo Installing Python dependencies...
echo.
"%PYTHON_PATH%" -m pip install --upgrade pip >nul 2>&1
"%PYTHON_PATH%" -m pip install -r "%CURRENT_DIR%requirements.txt" --quiet

if errorlevel 1 (
    echo.
    echo [WARNING] Failed to install some dependencies
    echo The service may not work properly
    echo.
) else (
    echo Dependencies installed successfully!
    echo.
)

echo [4/4] Installing Windows Service...
echo.

REM Check if service already exists
nssm status BiometricBridge >nul 2>&1
if not errorlevel 1 (
    echo Service already exists. Removing old service...
    nssm stop BiometricBridge >nul 2>&1
    nssm remove BiometricBridge confirm >nul 2>&1
    timeout /t 2 /nobreak >nul
    echo.
)

REM Install service with Python
nssm install BiometricBridge "%PYTHON_PATH%" "%CURRENT_DIR%agent.py"

if errorlevel 1 (
    echo.
    echo [ERROR] Failed to install service
    echo.
    pause
    exit /b 1
)

REM Configure service
nssm set BiometricBridge AppDirectory "%CURRENT_DIR:~0,-1%"
nssm set BiometricBridge DisplayName "Biometric Bridge Agent"
nssm set BiometricBridge Description "Connects ZKTeco device to remote server"
nssm set BiometricBridge Start SERVICE_AUTO_START
nssm set BiometricBridge AppStdout "%CURRENT_DIR:~0,-1%\service.log"
nssm set BiometricBridge AppStderr "%CURRENT_DIR:~0,-1%\service_error.log"

REM Set environment to allow network access
nssm set BiometricBridge AppEnvironmentExtra "PYTHONUNBUFFERED=1"
nssm set BiometricBridge ObjectName LocalSystem
nssm set BiometricBridge Type SERVICE_WIN32_OWN_PROCESS

REM Set timeouts for long-running service
nssm set BiometricBridge AppStopMethodSkip 0
nssm set BiometricBridge AppStopMethodConsole 30000
nssm set BiometricBridge AppExit Default Restart
nssm set BiometricBridge AppRestartDelay 5000

echo.
echo Verifying configuration...
echo ----------------------------------------
nssm get BiometricBridge Application
nssm get BiometricBridge AppParameters
nssm get BiometricBridge AppDirectory
echo ----------------------------------------
echo.

REM Start the service
echo Starting service...
nssm start BiometricBridge

timeout /t 3 /nobreak >nul

nssm status BiometricBridge | find "SERVICE_RUNNING" >nul
if errorlevel 1 (
    echo.
    echo [WARNING] Service installed but not running
    echo.
    echo Checking logs...
    timeout /t 2 /nobreak >nul
    
    if exist "%CURRENT_DIR%bridge_agent.log" (
        echo.
        echo Last 10 lines from bridge_agent.log:
        echo ----------------------------------------
        powershell -Command "Get-Content '%CURRENT_DIR%bridge_agent.log' -Tail 10"
        echo ----------------------------------------
    )
    echo.
) else (
    echo.
    echo ========================================
    echo [SUCCESS] Service is running!
    echo ========================================
    echo.
)

echo.
echo Useful commands:
echo   Start:   nssm start BiometricBridge
echo   Stop:    nssm stop BiometricBridge
echo   Restart: nssm restart BiometricBridge
echo   Status:  nssm status BiometricBridge
echo   Remove:  nssm remove BiometricBridge confirm
echo.
echo Logs location: %CURRENT_DIR%
echo   - service.log (output)
echo   - service_error.log (errors)
echo.
pause
