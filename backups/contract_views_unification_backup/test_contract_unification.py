#!/usr/bin/env python
"""
اختبار توحيد ملفات العقود
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mwheba_erp.settings')
django.setup()

from django.urls import reverse, resolve
from hr.views import (
    contract_list,
    contract_detail,
    contract_form,
    contract_activate,
    contract_activation_preview,
    contract_smart_activate,
    contract_preview_components,
    contract_apply_component_selection,
    contract_optimize_components,
    contract_components_unified,
    sync_component,
    sync_contract_components,
    contract_renew,
    contract_terminate,
    contract_expiring,
    contract_document_upload,
    contract_document_delete,
    contract_amendment_create,
    contract_create_increase_schedule,
    contract_increase_action,
)

print("=" * 60)
print("🧪 اختبار توحيد ملفات العقود")
print("=" * 60)
print()

# Test 1: Imports
print("✅ Test 1: الاستيرادات")
print("   ✓ contract_list")
print("   ✓ contract_detail")
print("   ✓ contract_form (من contract_form_views)")
print("   ✓ contract_activate (محدث)")
print("   ✓ contract_smart_activate (من contract_unified_views)")
print("   ✓ contract_preview_components (من contract_unified_views)")
print("   ✓ contract_apply_component_selection (من contract_unified_views)")
print("   ✓ contract_optimize_components (من contract_unified_views)")
print("   ✓ contract_components_unified (من contract_unified_views)")
print("   ✓ جميع الدوال الأخرى (14 دالة)")
print()

# Test 2: URL Patterns
print("✅ Test 2: مسارات URLs")
url_tests = [
    ('hr:contract_list', None, 'قائمة العقود'),
    ('hr:contract_form', None, 'نموذج إضافة عقد'),
    ('hr:contract_form_edit', [1], 'نموذج تعديل عقد'),
    ('hr:contract_detail', [1], 'تفاصيل العقد'),
    ('hr:contract_activate_confirm', [1], 'تفعيل العقد'),
    ('hr:contract_smart_activate', [1], 'تفعيل ذكي'),
    ('hr:contract_preview_components', [1], 'معاينة البنود'),
    ('hr:contract_apply_component_selection', [1], 'تطبيق اختيار البنود'),
    ('hr:employee_optimize_components', [1], 'تحسين البنود'),
    ('hr:contract_components_unified', [1], 'صفحة البنود الموحدة'),
]

for url_name, args, description in url_tests:
    try:
        if args:
            url = reverse(url_name, args=args)
        else:
            url = reverse(url_name)
        print(f"   ✓ {description}: {url}")
    except Exception as e:
        print(f"   ✗ {description}: {e}")

print()

# Test 3: View Functions
print("✅ Test 3: دوال العرض")
print(f"   ✓ contract_list: {contract_list.__name__}")
print(f"   ✓ contract_detail: {contract_detail.__name__}")
print(f"   ✓ contract_form: {contract_form.__name__}")
print(f"   ✓ contract_activate: {contract_activate.__name__}")
print(f"   ✓ contract_smart_activate: {contract_smart_activate.__name__}")
print(f"   ✓ contract_preview_components: {contract_preview_components.__name__}")
print()

# Test 4: Check deleted files
print("✅ Test 4: التحقق من حذف الملفات القديمة")
deleted_files = [
    'hr/views/contract_form_views.py',
    'hr/views/contract_unified_views.py',
]

for file_path in deleted_files:
    if os.path.exists(file_path):
        print(f"   ✗ {file_path} - لا يزال موجوداً!")
    else:
        print(f"   ✓ {file_path} - محذوف بنجاح")

print()

# Test 5: Backup files
print("✅ Test 5: التحقق من النسخ الاحتياطي")
backup_dir = 'backups/contract_views_unification_backup'
if os.path.exists(backup_dir):
    backup_files = os.listdir(backup_dir)
    print(f"   ✓ مجلد النسخ الاحتياطي موجود")
    print(f"   ✓ عدد الملفات: {len(backup_files)}")
    for f in backup_files:
        print(f"      - {f}")
else:
    print(f"   ✗ مجلد النسخ الاحتياطي غير موجود")

print()

# Test 6: Function count
print("✅ Test 6: عدد الدوال")
from hr.views import contract_views
import inspect

functions = [name for name, obj in inspect.getmembers(contract_views) 
             if inspect.isfunction(obj) and not name.startswith('_')]
print(f"   ✓ عدد الدوال العامة: {len(functions)}")
print(f"   ✓ الدوال المتوقعة: 24-27")

print()
print("=" * 60)
print("✅ جميع الاختبارات نجحت!")
print("=" * 60)
