#!/usr/bin/env python
"""
سكريبت تشغيل الاختبارات الشامل لنظام MWHEBA ERP
يوفر خيارات متعددة لتشغيل الاختبارات مع تقارير مفصلة
"""

import os
import sys
import subprocess
import time
from datetime import datetime

def print_header():
    """طباعة رأس التقرير"""
    print("=" * 80)
    print("🧪 نظام الاختبارات الشامل - MWHEBA ERP")
    print("=" * 80)
    print(f"📅 التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

def print_section(title):
    """طباعة عنوان قسم"""
    print(f"\n📋 {title}")
    print("-" * 60)

def run_command(command, description):
    """تشغيل أمر مع عرض النتائج"""
    print(f"🔄 {description}...")
    start_time = time.time()
    
    try:
        result = subprocess.run(
            command, 
            shell=True, 
            capture_output=True, 
            text=True,
            timeout=300  # 5 دقائق كحد أقصى
        )
        
        end_time = time.time()
        duration = end_time - start_time
        
        if result.returncode == 0:
            print(f"✅ {description} - مكتمل ({duration:.2f}s)")
            return True, result.stdout
        else:
            print(f"❌ {description} - فشل ({duration:.2f}s)")
            print(f"خطأ: {result.stderr}")
            return False, result.stderr
            
    except subprocess.TimeoutExpired:
        print(f"⏰ {description} - انتهت المهلة الزمنية")
        return False, "انتهت المهلة الزمنية"
    except Exception as e:
        print(f"💥 {description} - خطأ غير متوقع: {str(e)}")
        return False, str(e)

def test_all_apps():
    """تشغيل اختبارات جميع التطبيقات"""
    print_section("اختبار جميع التطبيقات")
    
    apps = [
        'core',
        'product', 
        'printing_pricing',
        'financial',
        'purchase',
        'sale',
        'utils',
        'services'
    ]
    
    results = {}
    total_start = time.time()
    
    for app in apps:
        success, output = run_command(
            f'python manage.py test {app}',
            f'اختبار تطبيق {app}'
        )
        results[app] = {'success': success, 'output': output}
    
    total_end = time.time()
    total_duration = total_end - total_start
    
    # عرض ملخص النتائج
    print_section("ملخص النتائج")
    passed = sum(1 for r in results.values() if r['success'])
    failed = len(results) - passed
    
    print(f"📊 إجمالي التطبيقات: {len(apps)}")
    print(f"✅ نجح: {passed}")
    print(f"❌ فشل: {failed}")
    print(f"⏱️  الوقت الإجمالي: {total_duration:.2f} ثانية")
    
    if failed > 0:
        print("\n🔍 التطبيقات التي فشلت:")
        for app, result in results.items():
            if not result['success']:
                print(f"  - {app}: {result['output'][:100]}...")
    
    return results

def test_specific_app(app_name):
    """تشغيل اختبارات تطبيق محدد"""
    print_section(f"اختبار تطبيق {app_name}")
    
    success, output = run_command(
        f'python manage.py test {app_name} -v 2',
        f'اختبار {app_name} مع تفاصيل'
    )
    
    if success:
        print(f"✅ اختبار {app_name} مكتمل بنجاح")
    else:
        print(f"❌ فشل اختبار {app_name}")
        print("تفاصيل الخطأ:")
        print(output)
    
    return success

def test_with_coverage():
    """تشغيل الاختبارات مع تقرير التغطية"""
    print_section("اختبار مع تقرير التغطية")
    
    # تحقق من وجود coverage
    success, _ = run_command('pip show coverage', 'التحقق من وجود coverage')
    
    if not success:
        print("📦 تثبيت coverage...")
        install_success, _ = run_command('pip install coverage', 'تثبيت coverage')
        if not install_success:
            print("❌ فشل تثبيت coverage")
            return False
    
    # تشغيل الاختبارات مع coverage
    success, output = run_command(
        'coverage run --source="." manage.py test',
        'تشغيل الاختبارات مع تتبع التغطية'
    )
    
    if success:
        # إنشاء تقرير التغطية
        run_command('coverage report', 'إنشاء تقرير التغطية')
        run_command('coverage html', 'إنشاء تقرير HTML للتغطية')
        print("📄 تقرير التغطية متاح في: htmlcov/index.html")
    
    return success

def run_specific_test(test_path):
    """تشغيل اختبار محدد"""
    print_section(f"تشغيل اختبار محدد: {test_path}")
    
    success, output = run_command(
        f'python manage.py test {test_path} -v 2',
        f'تشغيل {test_path}'
    )
    
    if success:
        print("✅ الاختبار مكتمل بنجاح")
    else:
        print("❌ فشل الاختبار")
        print(output)
    
    return success

def check_test_structure():
    """فحص هيكل ملفات الاختبار"""
    print_section("فحص هيكل الاختبارات")
    
    apps = ['core', 'product', 'printing_pricing', 'financial', 'purchase', 'sale', 'utils', 'services']
    
    for app in apps:
        test_dir = f"{app}/tests"
        if os.path.exists(test_dir):
            test_files = [f for f in os.listdir(test_dir) if f.startswith('test_') and f.endswith('.py')]
            print(f"📁 {app}: {len(test_files)} ملف اختبار")
            for file in test_files:
                print(f"   - {file}")
        else:
            print(f"⚠️  {app}: مجلد الاختبارات غير موجود")

def main():
    """الدالة الرئيسية"""
    print_header()
    
    if len(sys.argv) < 2:
        print("🔧 الاستخدام:")
        print("  python run_tests.py all              # تشغيل جميع الاختبارات")
        print("  python run_tests.py app <name>       # تشغيل اختبارات تطبيق محدد")
        print("  python run_tests.py coverage         # تشغيل مع تقرير التغطية")
        print("  python run_tests.py test <path>      # تشغيل اختبار محدد")
        print("  python run_tests.py structure        # فحص هيكل الاختبارات")
        return
    
    command = sys.argv[1].lower()
    
    if command == 'all':
        results = test_all_apps()
        failed_count = sum(1 for r in results.values() if not r['success'])
        sys.exit(failed_count)
        
    elif command == 'app' and len(sys.argv) > 2:
        app_name = sys.argv[2]
        success = test_specific_app(app_name)
        sys.exit(0 if success else 1)
        
    elif command == 'coverage':
        success = test_with_coverage()
        sys.exit(0 if success else 1)
        
    elif command == 'test' and len(sys.argv) > 2:
        test_path = sys.argv[2]
        success = run_specific_test(test_path)
        sys.exit(0 if success else 1)
        
    elif command == 'structure':
        check_test_structure()
        
    else:
        print("❌ أمر غير صحيح")
        sys.exit(1)

if __name__ == '__main__':
    main()
