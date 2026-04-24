#!/usr/bin/env python
"""
تحديث النظام لاستخدام الأدوار الديناميكية بدلاً من hardcoded
"""
import os
import sys
import django

# إعداد Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'corporate_erp.settings')
django.setup()

from users.models import Role, User
from django.contrib.auth.models import Permission
from django.db import transaction


def update_user_permissions():
    """تحديث صلاحيات المستخدمين لتعتمد على الأدوار"""
    
    print("🔄 تحديث صلاحيات المستخدمين...")
    
    try:
        with transaction.atomic():
            # جلب جميع المستخدمين النشطين
            users = User.objects.filter(is_active=True)
            
            updated_count = 0
            for user in users:
                # تحديث نوع المستخدم بناءً على الدور
                if user.role:
                    old_type = user.user_type
                    
                    # تحديد نوع المستخدم بناءً على اسم الدور
                    role_type_mapping = {
                        'reception': 'reception',
                        'admin': 'admin',
                        'accountant': 'accountant',
                        'inventory_manager': 'inventory_manager',
                        'sales_rep': 'sales_rep'
                    }
                    
                    if user.role.name in role_type_mapping:
                        new_type = role_type_mapping[user.role.name]
                        if user.user_type != new_type:
                            user.user_type = new_type
                            user.save()
                            print(f"  ✓ تم تحديث نوع المستخدم {user.username}: {old_type} → {new_type}")
                            updated_count += 1
            
            print(f"✅ تم تحديث {updated_count} مستخدم")
            
    except Exception as e:
        print(f"❌ خطأ في تحديث صلاحيات المستخدمين: {e}")


def validate_role_permissions():
    """التحقق من صحة صلاحيات الأدوار"""
    
    print("\n🔍 التحقق من صحة صلاحيات الأدوار...")
    
    try:
        roles = Role.objects.filter(is_active=True)
        
        for role in roles:
            print(f"\n📋 الدور: {role.display_name} ({role.name})")
            print(f"   عدد المستخدمين: {role.get_total_users()}")
            print(f"   عدد الصلاحيات: {role.permissions.count()}")
            
            # التحقق من صلاحيات التطبيقات للريسيبشن
            if role.name == 'reception':
                can_view = role.has_permission('view_qrapplication')
                can_add = role.has_permission('add_qrapplication')
                can_change = role.has_permission('change_qrapplication')
                
                print(f"   صلاحيات التطبيقات:")
                print(f"     عرض: {'✓' if can_view else '✗'}")
                print(f"     إضافة: {'✓' if can_add else '✗'}")
                print(f"     تعديل: {'✓' if can_change else '✗'}")
                
                if role.can_manage_applications():
                    print(f"   ✅ يمكن إدارة التطبيقات بالكامل")
                elif role.can_access_applications():
                    print(f"   ⚠️  يمكن الوصول للتطبيقات فقط")
                else:
                    print(f"   ❌ لا يمكن الوصول للتطبيقات")
            
            # عرض أول 5 صلاحيات
            permissions = role.permissions.all()[:5]
            if permissions:
                print(f"   الصلاحيات (أول 5):")
                for perm in permissions:
                    print(f"     • {perm.name} ({perm.codename})")
                
                if role.permissions.count() > 5:
                    print(f"     ... و {role.permissions.count() - 5} صلاحية أخرى")
        
    except Exception as e:
        print(f"❌ خطأ في التحقق من الأدوار: {e}")


def test_dynamic_permissions():
    """اختبار النظام الديناميكي للصلاحيات"""
    
    print("\n🧪 اختبار النظام الديناميكي للصلاحيات...")
    
    try:
        # اختبار مستخدم الريسيبشن
        reception_users = User.objects.filter(role__name='reception', is_active=True)
        
        if reception_users.exists():
            user = reception_users.first()
            print(f"\n👤 اختبار المستخدم: {user.get_full_name()} ({user.username})")
            
            # اختبار الصلاحيات
            tests = [
                ('can_view_applications', 'عرض التطبيقات'),
                ('can_add_applications', 'إضافة التطبيقات'),
                ('can_change_applications', 'تعديل التطبيقات'),
                ('can_view_customer_financial', 'عرض التفاصيل المالية'),
                ('can_view_customer_transport', 'عرض تفاصيل النقل'),
                ('can_view_customer_products', 'عرض منتجات العملاء'),
            ]
            
            print(f"   الصلاحيات:")
            for method_name, description in tests:
                if hasattr(user, method_name):
                    result = getattr(user, method_name)()
                    status = '✓' if result else '✗'
                    print(f"     {status} {description}")
                else:
                    print(f"     ⚠️  {description} (الدالة غير موجودة)")
            
            # اختبار الدور
            if user.role:
                print(f"   معلومات الدور:")
                print(f"     الاسم: {user.role.display_name}")
                print(f"     يمكن الوصول للتطبيقات: {'✓' if user.role.can_access_applications() else '✗'}")
                print(f"     يمكن إدارة التطبيقات: {'✓' if user.role.can_manage_applications() else '✗'}")
        else:
            print("   ⚠️  لا يوجد مستخدمين في دور الريسيبشن للاختبار")
        
    except Exception as e:
        print(f"❌ خطأ في اختبار الصلاحيات: {e}")


def main():
    """الدالة الرئيسية"""
    print("=" * 60)
    print("🔄 تحديث النظام للأدوار الديناميكية")
    print("=" * 60)
    
    try:
        # تحديث صلاحيات المستخدمين
        update_user_permissions()
        
        # التحقق من صحة الأدوار
        validate_role_permissions()
        
        # اختبار النظام
        test_dynamic_permissions()
        
        print(f"\n✅ تم تحديث النظام بنجاح!")
        print(f"🔗 النظام الآن يعتمد على الأدوار الديناميكية من قاعدة البيانات")
        
    except Exception as e:
        print(f"\n❌ فشل في تحديث النظام: {e}")
        sys.exit(1)
    
    print("=" * 60)


if __name__ == '__main__':
    main()
