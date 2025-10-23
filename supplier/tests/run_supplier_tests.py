#!/usr/bin/env python
"""
سكريبت تشغيل اختبارات الموردين
يقوم بتشغيل جميع الاختبارات وعرض تقرير شامل
"""

import os
import sys
import django

# إضافة المسار الرئيسي للمشروع
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

# إعداد Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mwheba_erp.settings')
django.setup()

from django.test.utils import get_runner
from django.conf import settings
from django.core.management import call_command


def run_tests():
    """تشغيل الاختبارات"""
    
    print("=" * 80)
    print("🚀 بدء تشغيل اختبارات نظام الموردين")
    print("=" * 80)
    print()
    
    # تشغيل الاختبارات
    TestRunner = get_runner(settings)
    test_runner = TestRunner(verbosity=2, interactive=False, keepdb=False)
    
    # تشغيل جميع اختبارات supplier
    test_labels = [
        "supplier.tests.test_supplier_complete",
        "supplier.tests.test_forms",
        "supplier.tests.test_signals",
        "supplier.tests.test_apis"
    ]
    
    failures = test_runner.run_tests(test_labels)
    
    print()
    print("=" * 80)
    
    if failures:
        print(f"❌ فشل {failures} اختبار")
        print("=" * 80)
        sys.exit(1)
    else:
        print("✅ جميع الاختبارات نجحت!")
        print("=" * 80)
        sys.exit(0)


if __name__ == '__main__':
    run_tests()
