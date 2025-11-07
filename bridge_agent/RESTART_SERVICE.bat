@echo off
title Restart Bridge Agent Service
echo ========================================
echo Restarting Biometric Bridge Service
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

echo Stopping service...
nssm stop BiometricBridge
timeout /t 3 /nobreak >nul

echo Starting service...
nssm start BiometricBridge
timeout /t 3 /nobreak >nul

echo.
echo Checking status...
nssm status BiometricBridge

echo.
echo ========================================
echo Service restarted successfully!
echo ========================================
echo.
pause
