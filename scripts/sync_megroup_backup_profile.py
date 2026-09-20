#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
scripts/sync_megroup_backup_profile.py
سكريبت مطابقة المستخدمين وإعدادات الشركة والثيم من نسخة الباك-أب إلى البيئة الحالية/الإنتاج
متوافق بنسبة 100% مع هيكلة قاعدة البيانات الجديدة
"""

import os
import sys
from pathlib import Path

# إعداد مسار المشروع
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(str(PROJECT_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "corporate_erp.settings")

import django
django.setup()

from django.db import transaction
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from users.models import Role
from core.models import SystemSetting

User = get_user_model()


def sync_roles_and_users():
    """
    1. مطابقة الأدوار والمستخدمين والصلاحيات
    """
    print("\n" + "="*60)
    print("👤 [1/3] جاري مطابقة الأدوار والمستخدمين والصلاحيات...")
    print("="*60)

    # 1.1 إنشاء / تحديث دور السكرتارية (Role 11)
    secretary_role, created = Role.objects.get_or_create(
        name="Secretery",
        defaults={
            "display_name": "سكرتارية",
            "description": "صلاحيات السكرتارية وإدارة الموظفين والمنتجات والمشتريات",
            "is_system_role": False,
            "is_active": True,
        }
    )
    if not created:
        secretary_role.display_name = "سكرتارية"
        secretary_role.is_active = True
        secretary_role.save()
    print(f"  ✅ الدور 'Secretery' (سكرتارية): {'تم إنشاؤه' if created else 'موجود ومحدث'}")

    # ربط صلاحيات دور السكرتارية بالـ codenames المتوافقة مع الهيكلة الجديدة
    secretary_permission_codenames = [
        "add_product", "change_product", "view_product",
        "add_purchase", "change_purchase", "view_purchase",
        "can_manage_contracts",
        "add_employee", "change_employee", "view_employee", "can_manage_employees",
        "can_process_payroll"
    ]
    matched_perms = Permission.objects.filter(codename__in=secretary_permission_codenames)
    secretary_role.permissions.set(matched_perms)
    print(f"     🔗 تم ربط {matched_perms.count()} صلاحية بالدور بنجاح.")

    # 1.2 مطابقة الأدوار الأساسية
    admin_role = Role.objects.filter(name="admin").first()

    # 1.3 مطابقة المستخدمين من الباك-أب
    users_data = [
        {
            "username": "mwheba",
            "first_name": "",
            "last_name": "",
            "email": "info@mwheba.com",
            "password_hash": "pbkdf2_sha256$600000$U9tb6zExgcUXDIZkiXG66P$tv4I4XCivT6l0RnthtDvf104bjLmC50jmt56dcDBzZ4=",
            "is_superuser": True,
            "is_staff": True,
            "is_active": True,
            "role": admin_role,
            "status": "active",
        },
        {
            "username": "ahmed",
            "first_name": "أحمد",
            "last_name": "فهد",
            "email": "ahmed@megroup-eg.com",
            "password_hash": "pbkdf2_sha256$600000$mRitjXFeBsRuLd1KQhgZOV$xfv/HBKaIZpyeM6qXRxqcaJy5zp0r67M4wdCO8ABQ9k=",
            "is_superuser": False,
            "is_staff": False,
            "is_active": True,
            "role": admin_role,
            "status": "active",
        },
        {
            "username": "salma",
            "first_name": "سلمى",
            "last_name": "قباري",
            "email": "info@megroup-eg.com",
            "password_hash": "pbkdf2_sha256$600000$vS5EQdGBgFFUU5wUO4SEt7$LV9LqU3l6FUsTBGYN0d4HrO7++kWaCoauQ7g/0kqhig=",
            "is_superuser": False,
            "is_staff": False,
            "is_active": True,
            "role": secretary_role,
            "status": "active",
        }
    ]

    for u_info in users_data:
        u_obj, u_created = User.objects.get_or_create(
            username=u_info["username"],
            defaults={
                "first_name": u_info["first_name"],
                "last_name": u_info["last_name"],
                "email": u_info["email"],
                "is_superuser": u_info["is_superuser"],
                "is_staff": u_info["is_staff"],
                "is_active": u_info["is_active"],
                "role": u_info["role"],
                "status": u_info["status"],
            }
        )
        # تعيين كلمة المرور المشفرة مباشرة لمنع إعادة تشفير الهاش
        u_obj.password = u_info["password_hash"]
        u_obj.first_name = u_info["first_name"]
        u_obj.last_name = u_info["last_name"]
        u_obj.email = u_info["email"]
        u_obj.is_superuser = u_info["is_superuser"]
        u_obj.is_staff = u_info["is_staff"]
        u_obj.is_active = u_info["is_active"]
        u_obj.role = u_info["role"]
        u_obj.status = u_info["status"]
        u_obj.save()
        print(f"  ✅ المستخدم '{u_obj.username}' ({u_obj.first_name} {u_obj.last_name}): {'تم إنشاؤه' if u_created else 'تم تحديثه ومطابقته بالهاش والصلاحيات'}")


def sync_company_profile():
    """
    2. مطابقة بيانات وهوية الشركة (Company Profile)
    """
    print("\n" + "="*60)
    print("🏢 [2/3] جاري مطابقة بيانات وهوية الشركة (Company Profile)...")
    print("="*60)

    company_settings = [
        {"key": "company_name", "value": "ME Group", "data_type": "string", "group": "general", "description": "اسم الشركة الرسمي"},
        {"key": "company_name_en", "value": "ME Group", "data_type": "string", "group": "general", "description": "اسم الشركة بالإنجليزية"},
        {"key": "company_address", "value": "الاسكندرية، مصر", "data_type": "string", "group": "general", "description": "عنوان الشركة الرئيسي"},
        {"key": "company_address_en", "value": "Alexandria, Egypt", "data_type": "string", "group": "general", "description": "عنوان الشركة بالإنجليزية"},
        {"key": "company_city", "value": "الإسكندرية", "data_type": "string", "group": "general", "description": "المدينة"},
        {"key": "company_state", "value": "الإسكندرية", "data_type": "string", "group": "general", "description": "المحافظة/الولاية"},
        {"key": "company_country", "value": "مصر", "data_type": "string", "group": "general", "description": "الدولة"},
        {"key": "company_postal_code", "value": "11511", "data_type": "string", "group": "general", "description": "الرمز البريدي"},
        {"key": "company_phone", "value": "+201234567890", "data_type": "string", "group": "general", "description": "رقم هاتف الشركة الرئيسي"},
        {"key": "company_mobile", "value": "+201012345678", "data_type": "string", "group": "general", "description": "رقم الموبايل الرئيسي"},
        {"key": "company_email", "value": "info@megroup-eg.com", "data_type": "string", "group": "general", "description": "البريد الإلكتروني الرسمي"},
        {"key": "company_website", "value": "www.megroup-eg.com", "data_type": "string", "group": "general", "description": "موقع الشركة الإلكتروني"},
        {"key": "company_tax_number", "value": "123-456-789", "data_type": "string", "group": "general", "description": "الرقم الضريبي"},
        {"key": "company_commercial_register", "value": "987654321", "data_type": "string", "group": "general", "description": "رقم السجل التجاري"},
        {"key": "company_legal_form", "value": "شركة ذات مسؤولية محدودة", "data_type": "string", "group": "general", "description": "الشكل القانوني"},
        {"key": "company_established_date", "value": "2020-01-01", "data_type": "date", "group": "general", "description": "تاريخ التأسيس"},
        {"key": "company_capital", "value": "1000000", "data_type": "decimal", "group": "general", "description": "رأس المال"},
        {"key": "company_industry", "value": "خدمات", "data_type": "string", "group": "general", "description": "مجال العمل"},
        {"key": "company_description", "value": "مؤسسة تعليمية متخصصة في تقديم خدمات تعليمية متميزة", "data_type": "string", "group": "general", "description": "وصف الشركة"},
        {"key": "company_slogan", "value": "نحو تميز مستدام في التعليم", "data_type": "string", "group": "general", "description": "شعار الشركة (Slogan)"},
        {"key": "company_working_hours", "value": "من الأحد إلى الخميس: 9 صباحاً - 5 مساءً", "data_type": "string", "group": "general", "description": "ساعات العمل"},
        {"key": "currency_symbol", "value": "ج.م", "data_type": "string", "group": "general", "description": "رمز العملة (عربي)"},
        {"key": "currency_symbol_en", "value": "EGP", "data_type": "string", "group": "general", "description": "رمز العملة (إنجليزي)"},
        {"key": "system_timezone", "value": "Africa/Cairo", "data_type": "string", "group": "general", "description": "المنطقة الزمنية"},
        {"key": "default_print_language", "value": "ar", "data_type": "string", "group": "general", "description": "لغة الطباعة الافتراضية"},
        {"key": "invoice_title_sale_en", "value": "TAX INVOICE", "data_type": "string", "group": "general", "description": "عنوان فاتورة المبيعات بالإنجليزية"},
        {"key": "invoice_title_quotation_en", "value": "QUOTATION", "data_type": "string", "group": "general", "description": "عنوان عرض السعر بالإنجليزية"},
        {"key": "receipt_paper_width", "value": "58", "data_type": "integer", "group": "general", "description": "عرض ورق الإيصالات (ملم)"},
    ]

    for item in company_settings:
        setting, _ = SystemSetting.objects.update_or_create(
            key=item["key"],
            defaults={
                "value": item["value"],
                "data_type": item["data_type"],
                "group": item["group"],
                "description": item["description"],
                "is_active": True,
            }
        )
        print(f"  🏢 {setting.key} = '{setting.value}'")


def sync_ui_theme_and_branding():
    """
    3. مطابقة الثيم والمظهر واللوجو والألوان (UI Theme & Branding)
    """
    print("\n" + "="*60)
    print("🎨 [3/3] جاري مطابقة الثيم والمظهر واللوجو والألوان (UI Theme & Branding)...")
    print("="*60)

    theme_settings = [
        # اللوجو والختم
        {"key": "company_logo", "value": "company/company_logo.png", "data_type": "string", "group": "general", "description": "لوجو الشركة الرئيسي"},
        {"key": "company_logo_light", "value": "company/company_logo_light.png", "data_type": "string", "group": "general", "description": "لوجو الشركة الفاتح"},
        {"key": "company_logo_mini", "value": "company/company_logo_mini.png", "data_type": "string", "group": "general", "description": "اللوجو المصغر"},
        {"key": "company_logo_path", "value": "img/logo.png", "data_type": "string", "group": "general", "description": "مسار اللوجو الثابت"},
        {"key": "company_stamp", "value": "company/company_stamp.png", "data_type": "string", "group": "general", "description": "ختم الشركة"},
        {"key": "enable_company_stamp", "value": "true", "data_type": "boolean", "group": "general", "description": "تفعيل ختم الشركة"},
        
        # درجات الألوان المعتمدة (Dark Slate Theme #3d3d3d)
        {"key": "color_primary", "value": "#3d3d3d", "data_type": "string", "group": "general", "description": "اللون الأساسي"},
        {"key": "color_primary_dark", "value": "#1a1a1a", "data_type": "string", "group": "general", "description": "اللون الأساسي الداكن"},
        {"key": "color_primary_light", "value": "#5c5c5c", "data_type": "string", "group": "general", "description": "اللون الأساسي الفاتح"},
        {"key": "color_primary_hover", "value": "#2b2b2b", "data_type": "string", "group": "general", "description": "لون التمرير الأساسي"},
        
        # ألوان الحالات والواجهة
        {"key": "color_success", "value": "#22c55e", "data_type": "string", "group": "general", "description": "لون النجاح"},
        {"key": "color_success_dark", "value": "#059669", "data_type": "string", "group": "general", "description": "لون النجاح الداكن"},
        {"key": "color_warning", "value": "#f59e0b", "data_type": "string", "group": "general", "description": "لون التحذير"},
        {"key": "color_warning_dark", "value": "#d97706", "data_type": "string", "group": "general", "description": "لون التحذير الداكن"},
        {"key": "color_danger", "value": "#ef4444", "data_type": "string", "group": "general", "description": "لون الخطر"},
        {"key": "color_danger_dark", "value": "#dc2626", "data_type": "string", "group": "general", "description": "لون الخطر الداكن"},
        {"key": "color_info", "value": "#0ea5e9", "data_type": "string", "group": "general", "description": "لون المعلومات"},
        {"key": "color_info_dark", "value": "#0284c7", "data_type": "string", "group": "general", "description": "لون المعلومات الداكن"},
        
        # ألوان الخلفيات والنصوص
        {"key": "color_bg_body", "value": "#f9fafb", "data_type": "string", "group": "general", "description": "خلفية الصفحة"},
        {"key": "color_text", "value": "#374151", "data_type": "string", "group": "general", "description": "لون النصوص الأساسي"},
        {"key": "color_bg_card", "value": "#ffffff", "data_type": "string", "group": "general", "description": "خلفية البطاقات"},
        {"key": "color_border", "value": "#e5e7eb", "data_type": "string", "group": "general", "description": "لون الحدود والخطوط الفاصلة"},
        {"key": "color_sidebar_bg", "value": "#ffffff", "data_type": "string", "group": "general", "description": "خلفية القائمة الجانبية"},
        {"key": "color_header_bg", "value": "#ffffff", "data_type": "string", "group": "general", "description": "خلفية الهيدر والناف بار"},
    ]

    for item in theme_settings:
        setting, _ = SystemSetting.objects.update_or_create(
            key=item["key"],
            defaults={
                "value": item["value"],
                "data_type": item["data_type"],
                "group": item["group"],
                "description": item["description"],
                "is_active": True,
            }
        )
        print(f"  🎨 {setting.key} = '{setting.value}'")


def clear_settings_cache():
    """مسح الكاش لضمان تطبيق الإعدادات فورياً"""
    try:
        from django.core.cache import cache
        cache.delete('global_settings_dict_v2')
        cache.delete('global_settings_dict')
        print("\n✨ تم تفريغ كاش الإعدادات (Settings Cache Flushed) بنجاح.")
    except Exception as e:
        print(f"  ⚠️ ملاحظة عند تفريغ الكاش: {e}")


def main():
    print("\n" + "="*70)
    print("🚀 بدء عملية مطابقة المستخدمين وبيانات وهوية الشركة والثيم من الباك-أب")
    print("="*70)

    with transaction.atomic():
        sync_roles_and_users()
        sync_company_profile()
        sync_ui_theme_and_branding()
        clear_settings_cache()

    print("\n" + "="*70)
    print("🎉 تم اكتمال المطابقة بنجاح 100% وبأمان تام دون أي تعارضات!")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
