# Generated manually to remove design supplier type

from django.db import migrations


def remove_design_supplier_type(apps, schema_editor):
    """حذف نوع مورد التصميم من قاعدة البيانات"""
    SupplierType = apps.get_model('supplier', 'SupplierType')
    
    # حذف نوع مورد التصميم
    design_types = SupplierType.objects.filter(code='design')
    design_count = design_types.count()
    design_types.delete()
    
    print(f"تم حذف {design_count} نوع مورد تصميم من قاعدة البيانات")


def restore_design_supplier_type(apps, schema_editor):
    """استعادة نوع مورد التصميم (للتراجع)"""
    SupplierType = apps.get_model('supplier', 'SupplierType')
    
    # إعادة إنشاء نوع مورد التصميم
    SupplierType.objects.get_or_create(
        code="design",
        defaults={
            'name': "تصميم",
            'description': "موردي خدمات التصميم والإخراج الفني",
            'icon': "fa-palette",
            'color': "#FF6348",
            'is_active': True,
            'display_order': 10,
        }
    )


class Migration(migrations.Migration):

    dependencies = [
        ('supplier', '0035_remove_design_from_laser'),
    ]

    operations = [
        migrations.RunPython(
            remove_design_supplier_type,
            restore_design_supplier_type,
        ),
    ]
