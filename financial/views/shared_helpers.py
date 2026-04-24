# financial/views/shared_helpers.py
# دوال مساعدة مشتركة بين المصروفات والإيرادات

from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from django.db import transaction
from datetime import datetime
from decimal import Decimal

from ..models import (
    ChartOfAccounts,
    AccountingPeriod,
    JournalEntry,
    JournalEntryLine,
)


def validate_transaction_data(data, transaction_type='expense'):
    """
    التحقق من صحة بيانات المعاملة (مصروف أو إيراد)
    
    Args:
        data: dict - البيانات المراد التحقق منها
        transaction_type: str - نوع المعاملة ('expense' أو 'income')
    
    Returns:
        tuple: (is_valid, errors, cleaned_data)
    """
    errors = {}
    cleaned_data = {}
    
    # التحقق من الوصف
    description = data.get('description', '').strip()
    if not description:
        field_name = 'وصف المصروف' if transaction_type == 'expense' else 'وصف الإيراد'
        errors['description'] = [_(f'{field_name} مطلوب')]
    else:
        cleaned_data['description'] = description
    
    # التحقق من المبلغ
    amount = data.get('amount')
    if not amount:
        errors['amount'] = [_('المبلغ مطلوب')]
    else:
        try:
            amount = Decimal(str(amount))
            if amount <= 0:
                errors['amount'] = [_('المبلغ يجب أن يكون أكبر من صفر')]
            else:
                cleaned_data['amount'] = amount
        except (ValueError, TypeError, Decimal.InvalidOperation):
            errors['amount'] = [_('المبلغ غير صحيح')]
    
    # التحقق من التاريخ
    date_field = f'{transaction_type}_date'
    transaction_date = data.get(date_field)
    if not transaction_date:
        field_name = 'تاريخ المصروف' if transaction_type == 'expense' else 'تاريخ الإيراد'
        errors[date_field] = [_(f'{field_name} مطلوب')]
    else:
        try:
            if isinstance(transaction_date, str):
                transaction_date = datetime.strptime(transaction_date, '%Y-%m-%d').date()
            cleaned_data['date'] = transaction_date
        except (ValueError, TypeError):
            errors[date_field] = [_('تاريخ غير صحيح')]
    
    # التحقق من التصنيف المالي
    category_field = 'financial_category'
    category_id = data.get(category_field)
    if not category_id:
        errors[category_field] = [_('التصنيف المالي مطلوب')]
    else:
        cleaned_data['category_id'] = category_id
    
    # التحقق من حساب الدفع/الاستلام
    payment_field = 'payment_account' if transaction_type == 'expense' else 'receipt_account'
    payment_value = data.get(payment_field)
    if not payment_value:
        field_name = 'الخزينة'
        errors[payment_field] = [_(f'{field_name} مطلوبة')]
    else:
        # قد يكون ID أو code - نحاول نحدد
        cleaned_data['payment_account_value'] = payment_value
    
    # الملاحظات (اختيارية)
    notes = data.get('notes', '').strip()
    cleaned_data['notes'] = notes
    
    is_valid = len(errors) == 0
    return is_valid, errors, cleaned_data


def get_active_accounting_period(transaction_date):
    """
    الحصول على الفترة المحاسبية النشطة للتاريخ المحدد
    
    Args:
        transaction_date: date - تاريخ المعاملة
    
    Returns:
        AccountingPeriod or None
    """
    return AccountingPeriod.objects.filter(
        status='open',
        start_date__lte=transaction_date,
        end_date__gte=transaction_date
    ).first()


def create_journal_entry_for_expense(cleaned_data, user):
    """
    إنشاء قيد محاسبي للمصروف عبر AccountingGateway
    
    Args:
        cleaned_data: dict - البيانات المنظفة
        user: User - المستخدم الذي أنشأ القيد
    
    Returns:
        JournalEntry - القيد المحاسبي المُنشأ
    
    Raises:
        Exception - في حالة حدوث خطأ
    """
    from ..models import FinancialCategory, FinancialSubcategory
    from governance.services import AccountingGateway, JournalEntryLineData
    
    # الحصول على التصنيف المالي - قد يكون تصنيف رئيسي أو فرعي
    category_id = cleaned_data['category_id']
    financial_category = None
    financial_subcategory = None
    
    # محاولة جلب التصنيف الفرعي أولاً
    try:
        financial_subcategory = FinancialSubcategory.objects.get(id=category_id)
        financial_category = financial_subcategory.parent_category
    except FinancialSubcategory.DoesNotExist:
        # إذا لم يكن فرعي، فهو تصنيف رئيسي
        financial_category = get_object_or_404(FinancialCategory, id=category_id)
    
    if not financial_category.default_expense_account:
        raise ValueError(_('التصنيف المالي المحدد ليس له حساب مصروفات افتراضي'))
    
    expense_account = financial_category.default_expense_account
    
    # الحصول على حساب الدفع - قد يكون ID أو code
    payment_value = cleaned_data['payment_account_value']
    try:
        # محاولة جلبه كـ ID أولاً
        payment_account = ChartOfAccounts.objects.get(id=int(payment_value))
    except (ValueError, ChartOfAccounts.DoesNotExist):
        # إذا فشل، نجربه كـ code
        payment_account = get_object_or_404(ChartOfAccounts, code=payment_value, is_active=True)
    
    # إنشاء FinancialTransaction أولاً لاستخدامه كـ source
    from ..models import AccountingPeriod, FinancialTransaction
    from django.utils import timezone
    
    # الحصول على الفترة المحاسبية
    active_period = AccountingPeriod.objects.filter(
        start_date__lte=cleaned_data['date'],
        end_date__gte=cleaned_data['date'],
        status='open'
    ).first()
    
    if not active_period:
        raise ValueError(_('لا توجد فترة محاسبية نشطة لهذا التاريخ'))
    
    # إنشاء FinancialTransaction كـ source للقيد
    transaction = FinancialTransaction.objects.create(
        transaction_type='expense',
        title=cleaned_data['description'],
        description=cleaned_data.get('notes', ''),
        account=expense_account,
        to_account=payment_account,
        amount=cleaned_data['amount'],
        date=cleaned_data['date'],
        category=financial_category
    )
    
    # إنشاء القيد عبر AccountingGateway
    gateway = AccountingGateway()
    
    lines = [
        JournalEntryLineData(
            account_code=expense_account.code,
            debit=cleaned_data['amount'],
            credit=Decimal('0'),
            description=cleaned_data['description']
        ),
        JournalEntryLineData(
            account_code=payment_account.code,
            debit=Decimal('0'),
            credit=cleaned_data['amount'],
            description=cleaned_data['description']
        )
    ]
    
    # استخدام FinancialTransaction كـ source
    journal_entry = gateway.create_journal_entry(
        source_module='financial',
        source_model='FinancialTransaction',
        source_id=transaction.id,
        lines=lines,
        idempotency_key=f'JE:financial:FinancialTransaction:{transaction.id}:create',
        user=user,
        date=cleaned_data['date'],
        description=cleaned_data['description'],
        financial_category=financial_category,
        financial_subcategory=financial_subcategory
    )
    
    # حفظ الملاحظات إذا كانت موجودة
    if cleaned_data.get('notes'):
        journal_entry.notes = cleaned_data['notes']
        journal_entry.save(update_fields=['notes'])
    
    # ملاحظة: القيد يتم ترحيله تلقائياً عند الإنشاء عبر AccountingGateway
    # لا حاجة لاستدعاء post_journal_entry - القيد يُنشأ بحالة 'posted' مباشرة
    
    return journal_entry


def create_journal_entry_for_income(cleaned_data, user):
    """
    إنشاء قيد محاسبي للإيراد عبر AccountingGateway
    
    Args:
        cleaned_data: dict - البيانات المنظفة
        user: User - المستخدم الذي أنشأ القيد
    
    Returns:
        JournalEntry - القيد المحاسبي المُنشأ
    
    Raises:
        Exception - في حالة حدوث خطأ
    """
    from ..models import FinancialCategory, FinancialSubcategory
    from governance.services import AccountingGateway, JournalEntryLineData
    
    # الحصول على التصنيف المالي - قد يكون تصنيف رئيسي أو فرعي
    category_id = cleaned_data['category_id']
    financial_category = None
    financial_subcategory = None
    
    # محاولة جلب التصنيف الفرعي أولاً
    try:
        financial_subcategory = FinancialSubcategory.objects.get(id=category_id)
        financial_category = financial_subcategory.parent_category
    except FinancialSubcategory.DoesNotExist:
        # إذا لم يكن فرعي، فهو تصنيف رئيسي
        financial_category = get_object_or_404(FinancialCategory, id=category_id)
    
    if not financial_category.default_revenue_account:
        raise ValueError(_('التصنيف المالي المحدد ليس له حساب إيرادات افتراضي'))
    
    income_account = financial_category.default_revenue_account
    
    # الحصول على حساب الاستلام - قد يكون ID أو code
    payment_value = cleaned_data['payment_account_value']
    try:
        # محاولة جلبه كـ ID أولاً
        receipt_account = ChartOfAccounts.objects.get(id=int(payment_value))
    except (ValueError, ChartOfAccounts.DoesNotExist):
        # إذا فشل، نجربه كـ code
        receipt_account = get_object_or_404(ChartOfAccounts, code=payment_value, is_active=True)
    
    # إنشاء FinancialTransaction أولاً لاستخدامه كـ source
    from ..models import AccountingPeriod, FinancialTransaction
    from django.utils import timezone
    
    # الحصول على الفترة المحاسبية
    active_period = AccountingPeriod.objects.filter(
        start_date__lte=cleaned_data['date'],
        end_date__gte=cleaned_data['date'],
        status='open'
    ).first()
    
    if not active_period:
        raise ValueError(_('لا توجد فترة محاسبية نشطة لهذا التاريخ'))
    
    # إنشاء FinancialTransaction كـ source للقيد
    transaction = FinancialTransaction.objects.create(
        transaction_type='income',
        title=cleaned_data['description'],
        description=cleaned_data.get('notes', ''),
        account=income_account,
        to_account=receipt_account,
        amount=cleaned_data['amount'],
        date=cleaned_data['date'],
        category=financial_category
    )
    
    # إنشاء القيد عبر AccountingGateway
    gateway = AccountingGateway()
    
    lines = [
        JournalEntryLineData(
            account_code=receipt_account.code,
            debit=cleaned_data['amount'],
            credit=Decimal('0'),
            description=cleaned_data['description']
        ),
        JournalEntryLineData(
            account_code=income_account.code,
            debit=Decimal('0'),
            credit=cleaned_data['amount'],
            description=cleaned_data['description']
        )
    ]
    
    # استخدام FinancialTransaction كـ source
    journal_entry = gateway.create_journal_entry(
        source_module='financial',
        source_model='FinancialTransaction',
        source_id=transaction.id,
        lines=lines,
        idempotency_key=f'JE:financial:FinancialTransaction:{transaction.id}:create',
        user=user,
        date=cleaned_data['date'],
        description=cleaned_data['description'],
        financial_category=financial_category,
        financial_subcategory=financial_subcategory
    )
    
    # حفظ الملاحظات إذا كانت موجودة
    if cleaned_data.get('notes'):
        journal_entry.notes = cleaned_data['notes']
        journal_entry.save(update_fields=['notes'])
    
    # ملاحظة: القيد يتم ترحيله تلقائياً عند الإنشاء عبر AccountingGateway
    # لا حاجة لاستدعاء post_journal_entry - القيد يُنشأ بحالة 'posted' مباشرة
    
    return journal_entry


def prepare_list_context(entries, entry_type='expense'):
    """
    تحضير البيانات المحسنة لقائمة المصروفات أو الإيرادات
    
    Args:
        entries: QuerySet - القيود المحاسبية
        entry_type: str - نوع القيد ('expense' أو 'income')
    
    Returns:
        list - قائمة القيود المحسنة
    """
    enhanced_entries = []
    
    for entry in entries:
        if entry_type == 'expense':
            # المصروفات: المدين في حسابات المصروفات
            lines = entry.lines.filter(
                account__account_type__category="expense", 
                debit__gt=0
            )
            amount = sum(line.debit for line in lines)
            amount_key = 'expense_amount'
            accounts_key = 'expense_accounts'
        else:
            # الإيرادات: الدائن في حسابات الإيرادات
            lines = entry.lines.filter(
                account__account_type__category="revenue", 
                credit__gt=0
            )
            amount = sum(line.credit for line in lines)
            amount_key = 'income_amount'
            accounts_key = 'income_accounts'
        
        # استخدام التصنيف الفرعي أولاً، ثم الرئيسي، ثم محاولة الاستنتاج
        if entry.financial_subcategory:
            financial_category = entry.financial_subcategory.name
        elif entry.financial_category:
            financial_category = entry.financial_category.name
        else:
            # محاولة استنتاج التصنيف من الحساب المحاسبي المستخدم
            first_line = lines.first()
            if first_line and first_line.account:
                # البحث عن تصنيف مالي يستخدم هذا الحساب
                from ..models import FinancialCategory
                
                if entry_type == 'expense':
                    category = FinancialCategory.objects.filter(
                        default_expense_account=first_line.account,
                        is_active=True
                    ).first()
                else:
                    category = FinancialCategory.objects.filter(
                        default_revenue_account=first_line.account,
                        is_active=True
                    ).first()
                
                financial_category = category.name if category else first_line.account.name
            else:
                financial_category = "غير محدد"
        
        enhanced_entry = {
            "id": entry.id,
            "number": entry.number,
            "date": entry.date,
            "description": entry.description,
            amount_key: amount,
            accounts_key: financial_category,
            "status": entry.status,
            "entry_type": entry.entry_type,
        }
        enhanced_entries.append(enhanced_entry)
    
    return enhanced_entries
