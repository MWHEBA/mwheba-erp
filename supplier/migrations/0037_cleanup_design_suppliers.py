# Generated manually to cleanup suppliers with design type

from django.db import migrations


def cleanup_design_suppliers(apps, schema_editor):
    """تنظيف الموردين المرتبطين بنوع التصميم"""
    Supplier = apps.get_model('supplier', 'Supplier')
    
    # البحث عن الموردين الذين نوعهم الأساسي كان تصميم وتحديثهم
    suppliers_updated = 0
    for supplier in Supplier.objects.filter(primary_type__isnull=True):
        # إذا كان النوع الأساسي فارغ، نضع نوع "أخرى"
        try:
            SupplierType = apps.get_model('supplier', 'SupplierType')
            other_type = SupplierType.objects.filter(code='other').first()
            if other_type:
                supplier.primary_type = other_type
                supplier.save()
                suppliers_updated += 1
        except:
            pass
    
    print(f"تم تحديث {suppliers_updated} مورد كان مرتبط بنوع التصميم")


def reverse_cleanup_design_suppliers(apps, schema_editor):
    """عكس التنظيف (للتراجع)"""
    pass  # لا نحتاج لعكس هذا التنظيف


class Migration(migrations.Migration):

    dependencies = [
        ('supplier', '0036_remove_design_supplier_type'),
    ]

    operations = [
        migrations.RunPython(
            cleanup_design_suppliers,
            reverse_cleanup_design_suppliers,
        ),
    ]
