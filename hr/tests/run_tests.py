#!/usr/bin/env python
"""
سكريبت تشغيل اختبارات HR
=========================
يوفر واجهة سهلة لتشغيل الاختبارات المختلفة

الاستخدام:
    python run_tests.py                 # تشغيل جميع الاختبارات
    python run_tests.py models          # اختبارات النماذج فقط
    python run_tests.py services        # اختبارات الخدمات فقط
    python run_tests.py coverage        # مع تقرير التغطية
"""
import sys
import os
import subprocess

# إضافة المسار الرئيسي
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE_DIR)

# خريطة الاختبارات
TESTS_MAP = {
    'all': 'hr.tests',
    'models': 'hr.tests.test_models',
    'services': 'hr.tests.test_services',
    'views': 'hr.tests.test_views',
    'api': 'hr.tests.test_api',
    'forms': 'hr.tests.test_forms',
    'permissions': 'hr.tests.test_permissions',
    'reports': 'hr.tests.test_reports',
    'signals': 'hr.tests.test_signals',
    'serializers': 'hr.tests.test_serializers',
    'salary': 'hr.tests.test_salary_system',
    'advance': 'hr.tests.test_advance_system',
    'integration': 'hr.tests.test_integration',
}


def run_tests(test_name='all', with_coverage=False):
    """تشغيل الاختبارات"""
    
    test_path = TESTS_MAP.get(test_name, 'hr.tests')
    
    print("=" * 80)
    print(f"🧪 تشغيل اختبارات: {test_name}")
    print("=" * 80)
    print()
    
    if with_coverage:
        # تشغيل مع تقرير التغطية
        print("📊 تشغيل مع تقرير التغطية...")
        subprocess.run([
            'coverage', 'run',
            '--source=hr',
            'manage.py', 'test', test_path,
            '--verbosity=2'
        ])
        
        print("\n" + "=" * 80)
        print("📈 تقرير التغطية:")
        print("=" * 80)
        subprocess.run(['coverage', 'report'])
        
        print("\n💡 لعرض تقرير HTML:")
        print("   coverage html")
        print("   ثم افتح htmlcov/index.html")
    else:
        # تشغيل عادي
        subprocess.run([
            'python', 'manage.py', 'test', test_path,
            '--verbosity=2'
        ])
    
    print("\n" + "=" * 80)
    print("✅ انتهى التشغيل")
    print("=" * 80)


def show_help():
    """عرض المساعدة"""
    print("=" * 80)
    print("🧪 سكريبت تشغيل اختبارات HR")
    print("=" * 80)
    print()
    print("الاستخدام:")
    print("  python run_tests.py [test_name] [--coverage]")
    print()
    print("الاختبارات المتاحة:")
    for name, path in TESTS_MAP.items():
        print(f"  {name:15} → {path}")
    print()
    print("أمثلة:")
    print("  python run_tests.py                    # جميع الاختبارات")
    print("  python run_tests.py models             # اختبارات النماذج")
    print("  python run_tests.py services           # اختبارات الخدمات")
    print("  python run_tests.py advance            # اختبارات السلف")
    print("  python run_tests.py all --coverage     # مع تقرير التغطية")
    print()


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] in ['--help', '-h', 'help']:
        show_help()
    else:
        test_name = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] != '--coverage' else 'all'
        with_coverage = '--coverage' in sys.argv
        
        if test_name not in TESTS_MAP and test_name != 'all':
            print(f"❌ اختبار غير معروف: {test_name}")
            print()
            show_help()
            sys.exit(1)
        
        run_tests(test_name, with_coverage)
