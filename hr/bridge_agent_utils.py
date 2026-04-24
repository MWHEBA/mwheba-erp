"""
أدوات مساعدة لـ Bridge Agent - معزولة لتجنب مشاكل الأمان في cPanel
"""
import os
import json
import secrets
import socket
import zipfile
from io import BytesIO
from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


def generate_agent_config(device, request):
    """توليد ملف إعدادات Bridge Agent"""
    # استخدام المفتاح السري من BRIDGE_AGENTS في settings
    valid_agents = getattr(settings, 'BRIDGE_AGENTS', {})
    agent_secret = valid_agents.get(device.device_code)
    
    # إذا لم يكن موجوداً، نولد واحد جديد
    if not agent_secret:
        agent_secret = secrets.token_urlsafe(32)
        logger.warning(
            f"Generated new secret for {device.device_code}. "
            f"Add to .env: BRIDGE_AGENTS={device.device_code}:{agent_secret}"
        )
    
    # إنشاء ملف config.json
    config = {
        "device_ip": device.ip_address,
        "device_port": device.port,
        "server_url": request.build_absolute_uri('/').rstrip('/'),
        "agent_code": device.device_code,
        "agent_secret": agent_secret,
        "sync_interval": 5,
        "log_level": "INFO"
    }
    
    return config, agent_secret


def create_agent_zip_package(device, config):
    """إنشاء ملف ZIP يحتوي على Bridge Agent وإعداداته"""
    # إنشاء ملف ZIP في الذاكرة
    zip_buffer = BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # إضافة config.json
        zip_file.writestr('bridge_agent/config.json', json.dumps(config, indent=4, ensure_ascii=False))
        
        # إضافة ملفات Bridge Agent من المجلد
        bridge_agent_path = os.path.join(settings.BASE_DIR, 'bridge_agent')
        
        # قائمة الملفات المطلوبة
        files_to_include = [
            'agent.py',
            'requirements.txt',
            'install_service.bat',
            'uninstall_service.bat',
            'README.md',
            'INSTALLER_README.txt'
        ]
        
        for filename in files_to_include:
            file_path = os.path.join(bridge_agent_path, filename)
            if os.path.exists(file_path):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        zip_file.writestr(f'bridge_agent/{filename}', f.read())
                except UnicodeDecodeError:
                    # للملفات الثنائية
                    with open(file_path, 'rb') as f:
                        zip_file.writestr(f'bridge_agent/{filename}', f.read())
        
        # إضافة ملف الإعداد الرئيسي إذا كان موجوداً
        installer_path = os.path.join(settings.BASE_DIR, 'bridge_agent', 'BiometricBridgeAgent_Setup.bat')
        if os.path.exists(installer_path):
            with open(installer_path, 'r', encoding='utf-8') as f:
                zip_file.writestr('BiometricBridgeAgent_Setup.bat', f.read())
        
        # إضافة ملف تعليمات
        instructions = f"""
تعليمات تثبيت Bridge Agent
============================

1. فك ضغط هذا الملف في مجلد على الجهاز المحلي
2. تأكد من تثبيت Python 3.8 أو أحدث
3. افتح Command Prompt كمسؤول
4. انتقل لمجلد bridge_agent
5. نفذ الأمر: pip install -r requirements.txt
6. نفذ الأمر: python agent.py

للتثبيت كخدمة Windows:
- نفذ: install_service.bat

معلومات الجهاز:
- الكود: {device.device_code}
- IP: {device.ip_address}
- Port: {device.port}

ملاحظة: احتفظ بملف config.json في مكان آمن
"""
        zip_file.writestr('INSTRUCTIONS.txt', instructions)
    
    zip_buffer.seek(0)
    return zip_buffer


def create_download_response(device, zip_buffer):
    """إنشاء استجابة HTTP لتحميل الملف"""
    response = HttpResponse(zip_buffer.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="bridge_agent_{device.device_code}.zip"'
    return response


def test_device_connection(device):
    """
    اختبار الاتصال بماكينة البصمة
    
    Args:
        device: كائن BiometricDevice
        
    Returns:
        tuple: (success: bool, message: str, details: dict)
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((device.ip_address, device.port))
        sock.close()
        
        if result == 0:
            # نجح الاتصال
            device.last_connection = timezone.now()
            device.status = 'active'
            device.save()
            
            return (
                True,
                'تم الاتصال بالماكينة بنجاح',
                {
                    'ip': device.ip_address,
                    'port': device.port,
                    'response_time': 'أقل من 5 ثواني'
                }
            )
        else:
            # فشل الاتصال
            device.status = 'error'
            device.save()
            
            return (False, 'فشل الاتصال بالماكينة', {})
            
    except Exception as e:
        logger.error(f"خطأ في اختبار الاتصال بالماكينة {device.device_code}: {str(e)}")
        return (False, f'خطأ: {str(e)}', {})
