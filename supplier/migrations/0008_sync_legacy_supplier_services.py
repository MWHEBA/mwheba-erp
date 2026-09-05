from decimal import Decimal
from django.db import migrations


def sync_legacy_supplier_services(apps, schema_editor):
    SupplierService = apps.get_model('supplier', 'SupplierService')
    
    for svc in SupplierService.objects.select_related(
        'dimension', 'machine', 'paper_type_ref', 'coating_type',
        'finishing_type', 'packaging_type', 'plate_size', 'paper_size',
        'paper_origin', 'paper_weight'
    ).iterator():
        attrs = svc.attributes if isinstance(svc.attributes, dict) else {}
        updated = False

        if svc.dimension and 'sheet_size' not in attrs:
            w = int(svc.dimension.width) if svc.dimension.width == int(svc.dimension.width) else float(svc.dimension.width)
            h = int(svc.dimension.height) if svc.dimension.height == int(svc.dimension.height) else float(svc.dimension.height)
            attrs['sheet_size'] = f"{w}x{h}"
            updated = True
            
        if svc.machine and 'machine_type' not in attrs:
            attrs['machine_type'] = svc.machine.name
            if svc.machine.colors_capacity:
                attrs['max_colors'] = svc.machine.colors_capacity
            updated = True
            
        if svc.paper_type_ref and 'paper_type' not in attrs:
            attrs['paper_type'] = svc.paper_type_ref.name
            updated = True
            
        if svc.coating_type and 'coating_type' not in attrs:
            attrs['coating_type'] = svc.coating_type.name
            updated = True
            
        if svc.finishing_type and 'finishing_type' not in attrs:
            attrs['finishing_type'] = svc.finishing_type.name
            updated = True
            
        if svc.packaging_type and 'packaging_type' not in attrs:
            attrs['packaging_type'] = svc.packaging_type.name
            updated = True
            
        if svc.plate_size and 'plate_size' not in attrs:
            attrs['plate_size'] = svc.plate_size.name
            updated = True
            
        if svc.paper_size:
            if 'parent_sheet_size' not in attrs:
                attrs['parent_sheet_size'] = svc.paper_size.name
                updated = True
            if 'sheet_size' not in attrs:
                w_p = int(svc.paper_size.width) if svc.paper_size.width == int(svc.paper_size.width) else float(svc.paper_size.width)
                h_p = int(svc.paper_size.height) if svc.paper_size.height == int(svc.paper_size.height) else float(svc.paper_size.height)
                attrs['sheet_size'] = f"{w_p}x{h_p}"
                updated = True
                
        if svc.paper_origin and 'origin' not in attrs:
            attrs['origin'] = svc.paper_origin.name
            updated = True
            
        if svc.gsm and 'gsm' not in attrs:
            attrs['gsm'] = svc.gsm
            updated = True
        elif svc.paper_weight and 'gsm' not in attrs:
            attrs['gsm'] = svc.paper_weight.gsm
            updated = True

        # تحديث base_price تلقائياً عند التسعير بالطن إذا كان مفقوداً أو صفر
        if svc.pricing_formula == 'PER_TON' and svc.price_per_ton and svc.paper_size and (not svc.base_price or svc.base_price == Decimal('0.00')):
            w = svc.paper_size.width
            h = svc.paper_size.height
            g = svc.gsm or (svc.paper_weight.gsm if svc.paper_weight else None)
            if w and h and g:
                sheet_weight_kg = (Decimal(str(w)) * Decimal(str(h)) * Decimal(str(g))) / Decimal('10000000')
                svc.base_price = (sheet_weight_kg * (Decimal(str(svc.price_per_ton)) / Decimal('1000'))).quantize(Decimal('0.0001'))
                updated = True

        if updated:
            svc.attributes = attrs
            svc.save(update_fields=['attributes', 'base_price'])


class Migration(migrations.Migration):
    dependencies = [
        ("supplier", "0007_supplier_is_pricing_supplier_and_more"),
    ]

    operations = [
        migrations.RunPython(sync_legacy_supplier_services, migrations.RunPython.noop),
    ]

