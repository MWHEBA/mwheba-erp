#!/usr/bin/env python
"""
ملخص شامل لدور الريسيبشن والصلاحيات
"""
import os
import sys
import django

# إعداد Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'corporate_erp.settings')
django.setup()

from users.models import Role, User
from django.contrib.contenttypes.models import ContentType


def display_reception_role_summary():
    """عرض ملخص شامل لدور الريسيبشن"""
    
    print("=" * 80)
    print("📋 ملخص شامل لدور الريسيبشن - نظام إدارة الشركة")
    print("=" * 80)
    
    try:
        # الحصول على دور الريسيبشن
        reception_role = Role.objects.get(name='reception')
        
        print(f"🏷️  معلومات الدور:")
        print(f"   الاسم: {reception_role.name}")
        print(f"   الاسم المعروض: {reception_role.display_name}")
        print(f"   الوصف: {reception_role.description}")
        print(f"   دور نظام: {'نعم' if reception_role.is_system_role else 'لا'}")
        print(f"   نشط: {'نعم' if reception_role.is_active else 'لا'}")
        print(f"   إجمالي الصلاحيات: {reception_role.permissions.count()}")
        
        # المستخدمين في الدور
        reception_users = User.objects.filter(role=reception_role, is_active=True)
        print(f"\n👥 المستخدمين في الدور ({reception_users.count()}):")
        if reception_users.exists():
            for user in reception_users:
                print(f"   • {user.get_full_name()} ({user.username}) - {user.email}")
        else:
            print("   لا يوجد مستخدمين نشطين في هذا الدور")
        
        # تصنيف الصلاحيات
        user_content_type = ContentType.objects.get_for_model(User)
        
        # الصلاحيات المخصصة
        custom_permissions = reception_role.permissions.filter(content_type=user_content_type)
        print(f"\n🔐 الصلاحيات المخصصة ({custom_permissions.count()}):")
        
        # تجميع الصلاحيات حسب الفئة
        permission_categories = {
            'التطبيقات': [],
            'العملاء': [],
            'النقل والباصات': [],
            'الأنشطة': [],
            'المنتجات': [],
            'عامة': []
        }
        
        for perm in custom_permissions:
            codename = perm.codename.lower()
            if 'application' in codename:
                permission_categories['التطبيقات'].append(perm)
            elif 'customer' in codename or 'client' in codename:
                permission_categories['العملاء'].append(perm)
            elif 'transportation' in codename or 'bus' in codename:
                permission_categories['النقل والباصات'].append(perm)
            elif 'activity' in codename:
                permission_categories['الأنشطة'].append(perm)
            elif 'product' in codename:
                permission_categories['المنتجات'].append(perm)
            else:
                permission_categories['عامة'].append(perm)
        
        for category, perms in permission_categories.items():
            if perms:
                print(f"\n   📂 {category} ({len(perms)} صلاحية):")
                for perm in perms:
                    print(f"      • {perm.name}")
        
        # الصلاحيات العادية (Django)
        django_permissions = reception_role.permissions.exclude(content_type=user_content_type)
        print(f"\n🔧 صلاحيات Django ({django_permissions.count()}):")
        
        # تجميع صلاحيات Django حسب التطبيق
        django_apps = {}
        for perm in django_permissions:
            app_label = perm.content_type.app_label
            if app_label not in django_apps:
                django_apps[app_label] = []
            django_apps[app_label].append(perm)
        
        for app_label, perms in django_apps.items():
            app_name_ar = {
                'qr_applications': 'التطبيقات الإلكترونية',
                'client': 'العملاء',
                'transportation': 'النقل',
                'product': 'المنتجات',
                'activities': 'الأنشطة',
                'financial': 'المالية'
            }.get(app_label, app_label)
            
            print(f"\n   📱 {app_name_ar} ({len(perms)} صلاحية):")
            for perm in perms[:5]:
                print(f"      • {perm.name}")
            if len(perms) > 5:
                print(f"      ... و {len(perms) - 5} صلاحية أخرى")
        
        # اختبار الصلاحيات مع مستخدم
        if reception_users.exists():
            test_user = reception_users.first()
            print(f"\n🧪 اختبار الصلاحيات مع المستخدم: {test_user.get_full_name()}")
            
            # اختبار الدوال المخصصة
            permission_tests = [
                ('can_manage_applications', 'إدارة التطبيقات'),
                ('can_view_customer_financial', 'عرض التفاصيل المالية للعملاء'),
                ('can_view_customer_transport', 'عرض تفاصيل النقل'),
                ('can_view_customer_products', 'عرض منتجات العملاء'),
                ('can_view_customer_activities', 'عرض أنشطة العملاء'),
                ('can_access_reception_dashboard', 'الوصول للوحة تحكم الريسيبشن'),
                ('can_generate_reception_reports', 'إنشاء تقارير الريسيبشن'),
            ]
            
            print(f"   النتائج:")
            for method_name, description in permission_tests:
                if hasattr(test_user, method_name):
                    result = getattr(test_user, method_name)()
                    status = '✅' if result else '❌'
                    print(f"      {status} {description}")
                else:
                    print(f"      ⚠️  {description} (الدالة غير موجودة)")
        
        # معلومات إضافية
        print(f"\n📊 إحصائيات إضافية:")
        print(f"   تاريخ الإنشاء: {reception_role.created_at.strftime('%Y-%m-%d %H:%M')}")
        print(f"   آخر تحديث: {reception_role.updated_at.strftime('%Y-%m-%d %H:%M')}")
        
        # نصائح للاستخدام
        print(f"\n💡 نصائح للاستخدام:")
        print(f"   • يمكن تعديل صلاحيات الدور من: /users/permissions/")
        print(f"   • لإضافة مستخدم جديد للدور: python scripts/assign_reception_role.py <username>")
        print(f"   • لإنشاء مستخدم ريسيبشن جديد: python scripts/create_reception_user.py")
        
        print(f"\n🔗 روابط مفيدة:")
        print(f"   • لوحة إدارة الصلاحيات: http://127.0.0.1:8000/users/permissions/")
        print(f"   • تسجيل الدخول: http://127.0.0.1:8000/login/")
        print(f"   • إدارة التطبيقات: http://127.0.0.1:8000/qr-applications/")
        
    except Role.DoesNotExist:
        print("❌ دور الريسيبشن غير موجود!")
        print("💡 يرجى تشغيل: python scripts/create_reception_role.py")
    
    except Exception as e:
        print(f"❌ خطأ في عرض ملخص الدور: {e}")
    
    print("=" * 80)


def main():
    """الدالة الرئيسية"""
    display_reception_role_summary()


if __name__ == '__main__':
    main()
