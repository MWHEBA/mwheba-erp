"""
خدمة الربط المحاسبي لأذون الصرف والاستلام
Voucher Accounting Service
"""
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from financial.models.chart_of_accounts import ChartOfAccounts
from financial.models.journal_entry import JournalEntry, JournalEntryLine
from product.models.inventory_movement import InventoryMovement


# خريطة ربط الأغراض بالحسابات المحاسبية (تدعم الأكواد المعيارية للشجرة النقية والأكواد التاريخية)
CONTRA_ACCOUNTS_MAP = {
    # أغراض الاستلام
    'supplies_gifts': ['49110', '42110', '40400', '41100'],   # إيرادات متنوعة / هدايا
    'inventory_gain': ['49110', '42110', '40400', '50800'],   # أرباح تسوية جردية / إيرادات أخرى

    # أغراض الصرف
    'office_supplies':       ['52500', '50300', '52100'],  # أدوات مكتبية ومطبوعات / مصروفات إدارية
    'educational_supplies':  ['52500', '50300', '52100'],  # مهمات وأدوات
    'activity_materials':    ['52500', '50300', '52100'],  # مهمات أنشطة
    'classroom_equipment':   ['52500', '50300', '12150'],  # مهمات وتجهيزات
    'maintenance':           ['52600', '50300', '52100'],  # صيانة ونظافة
    'cleaning':              ['52600', '50300', '52100'],  # صيانة ونظافة
    'samples':               ['52900', '50400', '52100'],  # دعاية وتسويق وعينات
    'exhibition':            ['52900', '50400', '52100'],  # معارض وتسويق
    'advertising':           ['52900', '50400', '52100'],  # إعلانات ودعاية
    'gifts':                 ['54900', '50500', '52900'],  # هدايا ومصروفات متنوعة
    'charity':               ['54900', '50500', '52100'],  # تبرعات ومصروفات متنوعة
    'damage':                ['54900', '50800', '51100'],  # خسائر تلف
    'expired':               ['54900', '50800', '51100'],  # خسائر انتهاء صلاحية
    'theft':                 ['54900', '50800', '51100'],  # خسائر عجز وسرقة
    'inventory_loss':        ['54900', '50800', '51100'],  # خسائر تسوية جردية
}


def get_inventory_account(product=None, warehouse=None):
    """
    الحصول على حساب المخزون هرمياً (Hierarchical Account Resolution):
    1. حساب المنتج المباشر
    2. حساب تصنيف المنتج
    3. حساب المخزن
    4. سجل أدوار الحسابات AccountRoleRegistry
    5. التراجع لأكواد المخزون المعيارية (11310 / 10400)
    6. التراجع لأي حساب أصول نشط
    """
    from financial.services.role_registry import AccountRoleRegistry

    # 1. حساب المنتج المباشر
    if product and hasattr(product, "inventory_account") and product.inventory_account:
        return product.inventory_account

    # 2. حساب تصنيف المنتج
    if product and hasattr(product, "category") and product.category and hasattr(product.category, "inventory_account") and product.category.inventory_account:
        return product.category.inventory_account

    # 3. حساب المخزن
    if warehouse and hasattr(warehouse, "inventory_account") and warehouse.inventory_account:
        return warehouse.inventory_account

    # 4. سجل أدوار الحسابات AccountRoleRegistry
    acc = (
        AccountRoleRegistry.get_account_by_role("INVENTORY_CONTROL_ACCOUNT")
        or AccountRoleRegistry.get_account_by_role("INVENTORY_GENERAL")
        or AccountRoleRegistry.get_account_by_role("INVENTORY_ASSET")
    )
    if acc and getattr(acc, "is_active", True):
        return acc

    # 5. التراجع لأكواد المخزون المعيارية
    fallback = ChartOfAccounts.objects.filter(
        code__in=['11310', '10400', '11300', '1040'],
        is_active=True
    ).first()
    if fallback:
        return fallback

    # 6. التراجع لأي حساب أصول نشط
    asset_fallback = ChartOfAccounts.objects.filter(
        account_type__category='asset',
        is_active=True
    ).order_by('code').first()
    if asset_fallback:
        return asset_fallback

    raise ValueError('حساب المخزون غير موجود في النظام. يرجى تهيئة الدليل المحاسبي.')


def get_contra_account(purpose_type, is_receipt=False):
    """الحصول على الحساب المقابل حسب الغرض مع دعم التراجع الذكي"""
    if purpose_type and purpose_type in CONTRA_ACCOUNTS_MAP:
        candidates = CONTRA_ACCOUNTS_MAP[purpose_type]
        if isinstance(candidates, str):
            candidates = [candidates]

        for code in candidates:
            acc = ChartOfAccounts.objects.filter(code=code, is_active=True).first()
            if acc:
                return acc

    # التراجع الذكي لنوع الحساب العام في حال عدم تطابق الكود المباشر
    if is_receipt or purpose_type in ['supplies_gifts', 'inventory_gain']:
        fallback = ChartOfAccounts.objects.filter(
            account_type__category='revenue',
            is_active=True
        ).order_by('code').first()
        if fallback:
            return fallback
    else:
        fallback = ChartOfAccounts.objects.filter(
            account_type__category='expense',
            is_active=True
        ).order_by('code').first()
        if fallback:
            return fallback

    # التراجع لأي حساب أرباح/خسائر أو حقوق ملكية
    general_fallback = ChartOfAccounts.objects.filter(is_active=True).first()
    if general_fallback:
        return general_fallback

    raise ValueError(
        f'الحساب المقابل للغرض ({purpose_type}) غير موجود في النظام. '
        f'يرجى التأكد من تهيئة الدليل المحاسبي.'
    )


@transaction.atomic
def create_receipt_voucher_entry(voucher):
    """
    إنشاء قيد محاسبي لإذن استلام
    
    القيد:
    مدين: المخزون (حساب المنتج)
    دائن: حساب مقابل حسب نوع الاستلام
    """
    if not voucher.is_approved:
        raise ValueError('لا يمكن إنشاء قيد لإذن غير معتمد')
    
    if voucher.journal_entry:
        return voucher.journal_entry  # القيد موجود مسبقاً
    
    # الحصول على الحسابات
    inventory_account = get_inventory_account(product=voucher.product, warehouse=getattr(voucher, 'warehouse', None))
    contra_account = voucher.contra_account or get_contra_account(voucher.purpose_type, is_receipt=True)
    
    # استخدام AccountingGateway
    from governance.services import AccountingGateway, JournalEntryLineData
    
    gateway = AccountingGateway()
    lines = [
        JournalEntryLineData(
            account_code=inventory_account.code,
            debit=voucher.total_cost,
            credit=Decimal('0.00'),
            description=f'{voucher.product.name} - {voucher.quantity} وحدة'
        ),
        JournalEntryLineData(
            account_code=contra_account.code,
            debit=Decimal('0.00'),
            credit=voucher.total_cost,
            description=f'{voucher.get_purpose_type_display()}'
        )
    ]
    
    # Get financial category from product if available
    financial_category = None
    financial_subcategory = None
    if hasattr(voucher.product, 'financial_category'):
        financial_category = voucher.product.financial_category
    if hasattr(voucher.product, 'financial_subcategory'):
        financial_subcategory = voucher.product.financial_subcategory
    
    entry = gateway.create_journal_entry(
        source_module='product',
        source_model='InventoryMovement',
        source_id=voucher.id,
        lines=lines,
        idempotency_key=f'JE:product:InventoryMovement:{voucher.id}:receipt',
        user=voucher.approved_by,
        date=voucher.movement_date.date() if hasattr(voucher.movement_date, 'date') else voucher.movement_date,
        description=f'إذن استلام - {voucher.product.name} - {voucher.get_purpose_type_display()}',
        reference=voucher.movement_number,
        entry_type='inventory',
        financial_category=financial_category,
        financial_subcategory=financial_subcategory
    )
    
    # ربط القيد بالحركة (استخدام update لتجنب validation)
    InventoryMovement.objects.filter(pk=voucher.pk).update(journal_entry=entry)
    
    return entry

@transaction.atomic
def create_issue_voucher_entry(voucher):
    """
    إنشاء قيد محاسبي لإذن صرف
    
    القيد:
    مدين: حساب مقابل حسب نوع الصرف
    دائن: المخزون (حساب المنتج)
    """
    if not voucher.is_approved:
        raise ValueError('لا يمكن إنشاء قيد لإذن غير معتمد')
    
    if voucher.journal_entry:
        return voucher.journal_entry  # القيد موجود مسبقاً
    
    # الحصول على الحسابات
    inventory_account = get_inventory_account(product=voucher.product, warehouse=getattr(voucher, 'warehouse', None))
    contra_account = voucher.contra_account or get_contra_account(voucher.purpose_type, is_receipt=False)
    
    # استخدام AccountingGateway
    from governance.services import AccountingGateway, JournalEntryLineData
    
    gateway = AccountingGateway()
    lines = [
        JournalEntryLineData(
            account_code=contra_account.code,
            debit=voucher.total_cost,
            credit=Decimal('0.00'),
            description=f'{voucher.get_purpose_type_display()}'
        ),
        JournalEntryLineData(
            account_code=inventory_account.code,
            debit=Decimal('0.00'),
            credit=voucher.total_cost,
            description=f'{voucher.product.name} - {voucher.quantity} وحدة'
        )
    ]
    
    # Get financial category from product if available
    financial_category = None
    financial_subcategory = None
    if hasattr(voucher.product, 'financial_category'):
        financial_category = voucher.product.financial_category
    if hasattr(voucher.product, 'financial_subcategory'):
        financial_subcategory = voucher.product.financial_subcategory
    
    entry = gateway.create_journal_entry(
        source_module='product',
        source_model='InventoryMovement',
        source_id=voucher.id,
        lines=lines,
        idempotency_key=f'JE:product:InventoryMovement:{voucher.id}:issue',
        user=voucher.approved_by,
        date=voucher.movement_date.date() if hasattr(voucher.movement_date, 'date') else voucher.movement_date,
        description=f'إذن صرف - {voucher.product.name} - {voucher.get_purpose_type_display()}',
        reference=voucher.movement_number,
        entry_type='inventory',
        financial_category=financial_category,
        financial_subcategory=financial_subcategory
    )
    
    # ربط القيد بالحركة (استخدام update لتجنب validation)
    InventoryMovement.objects.filter(pk=voucher.pk).update(journal_entry=entry)
    
    return entry
