# Create Self-Extracting Installer for Biometric Bridge Agent
# No external tools required - Pure PowerShell

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Creating Biometric Bridge Agent Installer" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Files to include
$files = @(
    "agent.py",
    "requirements.txt",
    "config.json",
    "README.md",
    "install_service.bat",
    "uninstall_service.bat"
)

# Check if all files exist
Write-Host "[1/3] Checking files..." -ForegroundColor Yellow
foreach ($file in $files) {
    if (-not (Test-Path $file)) {
        Write-Host "Error: $file not found!" -ForegroundColor Red
        exit 1
    }
    Write-Host "  [OK] $file" -ForegroundColor Green
}

# Create installer script
Write-Host ""
Write-Host "[2/3] Creating installer script..." -ForegroundColor Yellow

$installerScript = @'
@echo off
title Biometric Bridge Agent - Installer
color 0B

echo ========================================
echo Biometric Bridge Agent Installer
echo ========================================
echo.

REM Check admin rights
net session >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Administrator privileges required!
    echo.
    echo Please right-click this file and select:
    echo "Run as administrator"
    echo.
    pause
    exit /b 1
)

echo [OK] Running as Administrator
echo.

REM Set installation directory
set INSTALL_DIR=C:\BridgeAgent

echo Installation Directory: %INSTALL_DIR%
echo.

REM Create directory
if not exist "%INSTALL_DIR%" (
    echo Creating installation directory...
    mkdir "%INSTALL_DIR%"
)

REM Extract files
echo Extracting files...
echo.

REM This section will be replaced with actual file extraction
EXTRACT_FILES_HERE

echo.
echo [3/3] Installing Windows Service...
echo.

REM Run service installer
cd /d "%INSTALL_DIR%"
call install_service.bat

echo.
echo ========================================
echo Installation Complete!
echo ========================================
echo.
echo Location: %INSTALL_DIR%
echo.
echo The service is now running in the background.
echo.
pause
'@

# Read and encode files
Write-Host "  Encoding files..." -ForegroundColor Cyan
$extractCommands = ""

foreach ($file in $files) {
    $content = Get-Content $file -Raw -Encoding UTF8
    $encoded = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($content))
    
    $extractCommands += @"
echo Extracting $file...
powershell -Command "`$content = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('$encoded')); `$Utf8NoBom = New-Object System.Text.UTF8Encoding `$False; [System.IO.File]::WriteAllText('%INSTALL_DIR%\$file', `$content, `$Utf8NoBom)"
"@
    $extractCommands += "`r`n"
}

# Replace placeholder
$installerScript = $installerScript.Replace("EXTRACT_FILES_HERE", $extractCommands)

# Save installer (without BOM)
$installerPath = "BiometricBridgeAgent_Setup.bat"
$Utf8NoBomEncoding = New-Object System.Text.UTF8Encoding $False
[System.IO.File]::WriteAllText($installerPath, $installerScript, $Utf8NoBomEncoding)

Write-Host "  [OK] Installer created: $installerPath" -ForegroundColor Green

# Create info file
Write-Host ""
Write-Host "[3/3] Creating README..." -ForegroundColor Yellow

$readme = @"
========================================
Biometric Bridge Agent Installer
========================================

Installation Steps:
1. Right-click on BiometricBridgeAgent_Setup.bat
2. Select "Run as administrator"
3. Wait for installation to complete

The installer will:
- Extract files to C:\BridgeAgent
- Install Python dependencies
- Install and start Windows Service
- Configure auto-start with Windows

After installation:
- Edit C:\BridgeAgent\config.json to configure device settings
- Restart service: nssm restart BiometricBridge

Logs location: C:\BridgeAgent\
- service.log (output)
- service_error.log (errors)
- bridge_agent.log (sync logs)

========================================
"@

$readme | Out-File -FilePath "INSTALLER_README.txt" -Encoding UTF8 -Force

Write-Host "  [OK] README created" -ForegroundColor Green

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "SUCCESS! Installer created!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "File: BiometricBridgeAgent_Setup.bat" -ForegroundColor Cyan
Write-Host "Size: $((Get-Item $installerPath).Length / 1KB) KB" -ForegroundColor Cyan
Write-Host ""
Write-Host "To test: Right-click BiometricBridgeAgent_Setup.bat -> Run as administrator" -ForegroundColor Yellow
Write-Host ""
