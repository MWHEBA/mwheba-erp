# Generated manually to remove design services and category

from django.db import migrations


def remove_design_services(apps, schema_editor):
    """حذف جميع خدمات التصميم من قاعدة البيانات"""
    SupplierServiceTag = apps.get_model('supplier', 'SupplierServiceTag')
    
    # حذف جميع خدمات التصميم
    design_services = SupplierServiceTag.objects.filter(category='design')
    design_count = design_services.count()
    design_services.delete()
    
    print(f"تم حذف {design_count} خدمة تصميم من قاعدة البيانات")


def restore_design_services(apps, schema_editor):
    """استعادة خدمات التصميم (للتراجع)"""
    SupplierServiceTag = apps.get_model('supplier', 'SupplierServiceTag')
    
    # إعادة إنشاء خدمة التصميم الأساسية
    SupplierServiceTag.objects.get_or_create(
        name="تصميم وإخراج",
        defaults={
            'description': "خدمات التصميم والإخراج الفني",
            'category': "design",
            'color_code': "#FF6348",
            'display_order': 10,
            'estimated_duration': 3,
            'is_active': True,
            'requires_approval': True,
        }
    )


class Migration(migrations.Migration):

    dependencies = [
        ('supplier', '0033_alter_finishingservicedetails_finishing_type_and_more'),
    ]

    operations = [
        migrations.RunPython(
            remove_design_services,
            restore_design_services,
        ),
    ]
