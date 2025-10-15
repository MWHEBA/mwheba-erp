# Generated migration for unifying offset printing data

from django.db import migrations


def normalize_offset_data(apps, schema_editor):
    """تطبيع بيانات الأوفست الموجودة لتتطابق مع المرجعية"""
    OffsetPrintingDetails = apps.get_model('supplier', 'OffsetPrintingDetails')
    
    # خريطة تحويل أنواع الماكينات القديمة للجديدة
    machine_type_mapping = {
        'heidelberg_sm52': 'sm52',
        'heidelberg_sm74': 'sm74', 
        'heidelberg_sm102': 'sm102',
        'komori_ls40': 'ls40',
        'komori_ls29': 'ls29',
        'ryobi_524': 'ryobi_524',
        'ryobi_520': 'ryobi_520',
        'ryobi_750': 'ryobi_750',
        'gto_52': 'gto52',
        'other': 'other'
    }
    
    # خريطة تحويل مقاسات الماكينات القديمة للجديدة  
    sheet_size_mapping = {
        "35x50": "quarter_sheet",
        "50x70": "half_sheet",
        "70x100": "full_sheet", 
        "custom": "custom"
    }
    
    # تطبيع أنواع الماكينات
    for old_type, new_type in machine_type_mapping.items():
        OffsetPrintingDetails.objects.filter(machine_type=old_type).update(machine_type=new_type)
    
    # تطبيع مقاسات الماكينات
    for old_size, new_size in sheet_size_mapping.items():
        OffsetPrintingDetails.objects.filter(sheet_size=old_size).update(sheet_size=new_size)
    
    print(f"تم تطبيع {OffsetPrintingDetails.objects.count()} سجل من بيانات الأوفست")


def reverse_normalize_offset_data(apps, schema_editor):
    """عكس تطبيع البيانات في حالة التراجع"""
    OffsetPrintingDetails = apps.get_model('supplier', 'OffsetPrintingDetails')
    
    # خريطة عكسية لأنواع الماكينات
    reverse_machine_mapping = {
        'sm52': 'heidelberg_sm52',
        'sm74': 'heidelberg_sm74',
        'sm102': 'heidelberg_sm102', 
        'ls40': 'komori_ls40',
        'ls29': 'komori_ls29',
        'ryobi_524': 'ryobi_524',
        'ryobi_520': 'ryobi_520',
        'ryobi_750': 'ryobi_750',
        'gto52': 'gto_52',
        'other': 'other'
    }
    
    # خريطة عكسية لمقاسات الماكينات
    reverse_size_mapping = {
        "quarter_sheet": "35x50",
        "half_sheet": "50x70", 
        "full_sheet": "70x100",
        "custom": "custom"
    }
    
    # عكس تطبيع أنواع الماكينات
    for new_type, old_type in reverse_machine_mapping.items():
        OffsetPrintingDetails.objects.filter(machine_type=new_type).update(machine_type=old_type)
    
    # عكس تطبيع مقاسات الماكينات
    for new_size, old_size in reverse_size_mapping.items():
        OffsetPrintingDetails.objects.filter(sheet_size=new_size).update(sheet_size=old_size)


class Migration(migrations.Migration):

    dependencies = [
        ('supplier', '0026_update_coating_terminology'),
    ]

    operations = [
        migrations.RunPython(
            normalize_offset_data,
            reverse_normalize_offset_data,
            hints={'target_db': 'default'}
        ),
    ]
