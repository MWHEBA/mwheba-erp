#!/usr/bin/env python3
"""
✅ Security Package Update Script
سكريبت لتحديث المكتبات غير الآمنة تلقائياً
"""

import subprocess
import sys
import logging
from datetime import datetime

# إعداد التسجيل
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/security_updates.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# قائمة المكتبات التي يجب تحديثها للأمان
SECURITY_PACKAGES = {
    'gunicorn': '>=23.0.0',
    'django-select2': '>=8.2.4',
    'urllib3': '>=2.5.0',
    'requests': '>=2.32.3',
    'xhtml2pdf': '>=0.2.16',
    'djangorestframework': '>=3.15.2',
    'django-ratelimit': '>=4.1.0',
    'redis': '>=5.2.0',
    'django-redis': '>=5.4.0',
}

def run_command(command):
    """تشغيل أمر shell وإرجاع النتيجة"""
    try:
        result = subprocess.run(
            command, 
            shell=True, 
            capture_output=True, 
            text=True, 
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed: {command}")
        logger.error(f"Error: {e.stderr}")
        return None

def check_package_version(package_name):
    """التحقق من إصدار المكتبة الحالي"""
    try:
        result = run_command(f"pip show {package_name}")
        if result:
            for line in result.split('\n'):
                if line.startswith('Version:'):
                    return line.split(':')[1].strip()
    except Exception as e:
        logger.error(f"Error checking version for {package_name}: {e}")
    return None

def update_package(package_name, version_spec):
    """تحديث مكتبة معينة"""
    logger.info(f"🔄 تحديث {package_name} إلى {version_spec}")
    
    current_version = check_package_version(package_name)
    if current_version:
        logger.info(f"   الإصدار الحالي: {current_version}")
    
    # تحديث المكتبة
    command = f"pip install '{package_name}{version_spec}'"
    result = run_command(command)
    
    if result is not None:
        new_version = check_package_version(package_name)
        if new_version:
            logger.info(f"   ✅ تم التحديث إلى: {new_version}")
        else:
            logger.info(f"   ✅ تم التحديث بنجاح")
        return True
    else:
        logger.error(f"   ❌ فشل في تحديث {package_name}")
        return False

def main():
    """الدالة الرئيسية"""
    logger.info("=" * 60)
    logger.info(f"🔒 بدء تحديث المكتبات الأمنية - {datetime.now()}")
    logger.info("=" * 60)
    
    success_count = 0
    total_count = len(SECURITY_PACKAGES)
    
    for package_name, version_spec in SECURITY_PACKAGES.items():
        try:
            if update_package(package_name, version_spec):
                success_count += 1
        except Exception as e:
            logger.error(f"خطأ في تحديث {package_name}: {e}")
    
    logger.info("=" * 60)
    logger.info(f"📊 النتائج النهائية:")
    logger.info(f"   ✅ تم تحديث: {success_count}/{total_count} مكتبة")
    logger.info(f"   ❌ فشل في: {total_count - success_count}/{total_count} مكتبة")
    
    if success_count == total_count:
        logger.info("🎉 تم تحديث جميع المكتبات بنجاح!")
    else:
        logger.warning("⚠️ بعض المكتبات لم يتم تحديثها - يرجى المراجعة")
    
    # تحديث requirements.txt
    logger.info("📝 تحديث requirements.txt...")
    result = run_command("pip freeze > requirements.txt")
    if result is not None:
        logger.info("✅ تم تحديث requirements.txt")
    else:
        logger.error("❌ فشل في تحديث requirements.txt")
    
    logger.info("=" * 60)

if __name__ == "__main__":
    main()