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
