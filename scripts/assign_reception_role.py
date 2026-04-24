#!/usr/bin/env python
"""
تعيين دور الريسيبشن للمستخدمين
"""
import os
import sys
import django

# إعداد Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'corporate_erp.settings')
django.setup()

from users.models import Role, User
from django.db import transaction


def assign_reception_role(username):
    """تعيين دور الريسيبشن لمستخدم معين"""
    
    try:
        with transaction.atomic():
            # الحصول على الدور
            role = Role.objects.get(name='reception')
            
            # الحصول على المستخدم
            user = User.objects.get(username=username)
            
            # تعيين الدور
            user.role = role
            user.user_type = 'reception'  # تحديث نوع المستخدم أيضاً
            user.save()
            
            print(f"✅ تم تعيين دور الريسيبشن للمستخدم: {user.get_full_name()} ({user.username})")
            print(f"📋 الصلاحيات المتاحة: {role.permissions.count()} صلاحية")
            
            return True
            
    except Role.DoesNotExist:
        print("❌ دور الريسيبشن غير موجود. يرجى تشغيل create_reception_role.py أولاً")
        return False
    except User.DoesNotExist:
        print(f"❌ المستخدم '{username}' غير موجود")
        return False
    except Exception as e:
        print(f"❌ خطأ في تعيين الدور: {e}")
        return False


def list_reception_users():
    """عرض قائمة المستخدمين في دور الريسيبشن"""
    
    try:
        role = Role.objects.get(name='reception')
        users = User.objects.filter(role=role, is_active=True)
        
        if users.exists():
            print(f"👥 المستخدمين في دور الريسيبشن ({users.count()}):")
            for user in users:
                print(f"   • {user.get_full_name()} ({user.username}) - {user.email}")
        else:
            print("ℹ️  لا يوجد مستخدمين في دور الريسيبشن حالياً")
            
    except Role.DoesNotExist:
        print("❌ دور الريسيبشن غير موجود")


def main():
    """الدالة الرئيسية"""
    print("=" * 60)
    print("👤 تعيين دور الريسيبشن للمستخدمين")
    print("=" * 60)
    
    if len(sys.argv) > 1:
        username = sys.argv[1]
        assign_reception_role(username)
    else:
        print("📋 الاستخدام:")
        print("   python assign_reception_role.py <username>")
        print("\n📋 مثال:")
        print("   python assign_reception_role.py reception_user")
    
    print("\n" + "=" * 60)
    list_reception_users()
    print("=" * 60)


if __name__ == '__main__':
    main()