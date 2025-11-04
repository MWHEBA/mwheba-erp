@echo off
echo ========================================
echo Uninstalling Windows Service
echo ========================================
echo.

REM Check admin rights
net session >nul 2>&1
if errorlevel 1 (
    echo ERROR: Please run as Administrator!
    pause
    exit /b 1
)

REM Check if NSSM exists
if not exist "nssm.exe" (
    echo ERROR: NSSM not found!
    echo Please run install_service.bat first
    pause
    exit /b 1
)

echo Stopping service...
nssm stop BiometricBridge

echo Removing service...
nssm remove BiometricBridge confirm

echo.
echo ========================================
echo Service uninstalled successfully!
echo ========================================
echo.
pause
