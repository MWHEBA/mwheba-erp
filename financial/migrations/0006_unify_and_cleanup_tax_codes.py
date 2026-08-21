from django.db import migrations
from decimal import Decimal


def unify_and_cleanup_tax_codes(apps, schema_editor):
    TaxCode = apps.get_model('financial', 'TaxCode')
    Product = apps.get_model('product', 'Product')
    TaxRule = apps.get_model('financial', 'TaxRule')
    TaxDeterminationAudit = apps.get_model('financial', 'TaxDeterminationAudit')
    TaxCalculationLine = apps.get_model('financial', 'TaxCalculationLine')
    TaxAccountMapping = apps.get_model('financial', 'TaxAccountMapping')
    TaxRateHistory = apps.get_model('financial', 'TaxRateHistory')

    presets = [
        {
            "code": "VAT14",
            "name": "ضريبة القيمة المضافة 14%",
            "tax_type": "VAT",
            "tax_nature": "OUTPUT",
            "rate": Decimal("14.0000"),
            "recoverability_percentage": Decimal("100.00"),
            "eta_tax_type": "T1",
            "is_default": True,
            "is_active": True,
            "is_recoverable": True,
        },
        {
            "code": "VAT14_IN",
            "name": "ضريبة القيمة المضافة على المشتريات (مدخلات) 14%",
            "tax_type": "VAT",
            "tax_nature": "INPUT",
            "rate": Decimal("14.0000"),
            "recoverability_percentage": Decimal("100.00"),
            "eta_tax_type": "T1",
            "is_default": False,
            "is_active": True,
            "is_recoverable": True,
        },
        {
            "code": "VAT_NON_REC",
            "name": "ضريبة مدخلات غير قابلة للاسترداد (سيارات وضيافة) 14%",
            "tax_type": "VAT",
            "tax_nature": "NON_RECOVERABLE",
            "rate": Decimal("14.0000"),
            "recoverability_percentage": Decimal("0.00"),
            "is_recoverable": False,
            "eta_tax_type": "T1",
            "is_default": False,
            "is_active": True,
        },
        {
            "code": "TABLE_05",
            "name": "ضريبة الجدول (سلع وخدمات خاصة) 5%",
            "tax_type": "EXCISE",
            "tax_nature": "OUTPUT",
            "rate": Decimal("5.0000"),
            "recoverability_percentage": Decimal("100.00"),
            "eta_tax_type": "T2",
            "is_default": False,
            "is_active": True,
            "is_recoverable": True,
        },
        {
            "code": "ZERO_RATED",
            "name": "ضريبة بسعر صفر (صادرات ومناطق حرة) 0%",
            "tax_type": "ZERO_RATED",
            "tax_nature": "OUTPUT",
            "rate": Decimal("0.0000"),
            "recoverability_percentage": Decimal("100.00"),
            "eta_tax_type": "T1",
            "is_default": False,
            "is_active": True,
            "is_recoverable": True,
        },
        {
            "code": "EXEMPT",
            "name": "معفى من الضريبة بنص القانون 0%",
            "tax_type": "EXEMPT",
            "tax_nature": "OUTPUT",
            "rate": Decimal("0.0000"),
            "recoverability_percentage": Decimal("100.00"),
            "eta_tax_type": "T1",
            "is_default": False,
            "is_active": True,
            "is_recoverable": True,
        },
        {
            "code": "WHT_01",
            "name": "خصم وتحصيل - توريدات ومقاولات (1%)",
            "tax_type": "WITHHOLDING",
            "tax_nature": "WITHHOLDING",
            "rate": Decimal("1.0000"),
            "recoverability_percentage": Decimal("100.00"),
            "eta_tax_type": "T4",
            "is_default": True,
            "is_active": True,
            "is_recoverable": True,
        },
        {
            "code": "WHT_03",
            "name": "خصم وتحصيل - خدمات (3%)",
            "tax_type": "WITHHOLDING",
            "tax_nature": "WITHHOLDING",
            "rate": Decimal("3.0000"),
            "recoverability_percentage": Decimal("100.00"),
            "eta_tax_type": "T4",
            "is_default": False,
            "is_active": True,
            "is_recoverable": True,
        },
        {
            "code": "WHT_05",
            "name": "خصم وتحصيل - مهن حرة واستشارات (5%)",
            "tax_type": "WITHHOLDING",
            "tax_nature": "WITHHOLDING",
            "rate": Decimal("5.0000"),
            "recoverability_percentage": Decimal("100.00"),
            "eta_tax_type": "T4",
            "is_default": False,
            "is_active": True,
            "is_recoverable": True,
        }
    ]

    for p in presets:
        TaxCode.objects.update_or_create(code=p["code"], defaults=p)

    legacy_mappings = [
        ("VAT0", "ZERO_RATED"),
        ("WHT1", "WHT_01"),
    ]

    for old_code, target_code in legacy_mappings:
        old_obj = TaxCode.objects.filter(code=old_code).first()
        target_obj = TaxCode.objects.filter(code=target_code).first()
        if old_obj and target_obj and old_obj.id != target_obj.id:
            Product.objects.filter(tax_code=old_obj).update(tax_code=target_obj)
            TaxRule.objects.filter(tax_code=old_obj).update(tax_code=target_obj)
            TaxDeterminationAudit.objects.filter(tax_code=old_obj).update(tax_code=target_obj)
            TaxCalculationLine.objects.filter(tax_code=old_obj).update(tax_code=target_obj)
            TaxAccountMapping.objects.filter(tax_code=old_obj).update(tax_code=target_obj)
            TaxRateHistory.objects.filter(tax_code=old_obj).update(tax_code=target_obj)
            old_obj.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('financial', '0005_taxcode_is_default_alter_taxrule_code'),
        ('product', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(unify_and_cleanup_tax_codes, migrations.RunPython.noop),
    ]
