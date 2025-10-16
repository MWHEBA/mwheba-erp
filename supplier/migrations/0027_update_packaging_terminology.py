# Generated to update packaging terminology from "تغليف" to "تقفيل"

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("supplier", "0026_update_coating_terminology"),
    ]

    operations = [
        # هذا Migration يوثق تحديث المصطلحات من "تغليف" إلى "تقفيل"
        # التغييرات تمت في:
        # 1. supplier/models.py - جميع المراجع لـ "تغليف"
        # 2. تحديث البيانات في قاعدة البيانات
        # 3. تحديث الـ fixtures إذا لزم الأمر
        
        # لا توجد تغييرات في هيكل قاعدة البيانات، فقط تحديث المصطلحات
        migrations.RunSQL(
            # تحديث أي بيانات موجودة تحتوي على "تغليف" في الوصف
            """
            UPDATE supplier_suppliertype 
            SET name = REPLACE(name, 'تغليف', 'تقفيل')
            WHERE name LIKE '%تغليف%';
            """,
            reverse_sql="""
            UPDATE supplier_suppliertype 
            SET name = REPLACE(name, 'تقفيل', 'تغليف')
            WHERE name LIKE '%تقفيل%';
            """
        ),
        
        migrations.RunSQL(
            # تحديث أي خدمات تحتوي على "تغليف مخصص"
            """
            UPDATE supplier_specializedservice 
            SET name = REPLACE(name, 'تغليف مخصص', 'تقفيل مخصص')
            WHERE name LIKE '%تغليف مخصص%';
            """,
            reverse_sql="""
            UPDATE supplier_specializedservice 
            SET name = REPLACE(name, 'تقفيل مخصص', 'تغليف مخصص')
            WHERE name LIKE '%تقفيل مخصص%';
            """
        ),
        
    ]
