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
    
    # التحقق من الحسابات
    account_field = f'{transaction_type}_account'
    account_id = data.get(account_field)
    if not account_id:
        field_name = 'حساب المصروف' if transaction_type == 'expense' else 'حساب الإيراد'
        errors[account_field] = [_(f'{field_name} مطلوب')]
    else:
        cleaned_data['account_id'] = account_id
    
    # التحقق من حساب الدفع/الاستلام
    payment_field = 'payment_account' if transaction_type == 'expense' else 'receipt_account'
    payment_id = data.get(payment_field)
    if not payment_id:
        field_name = 'الخزينة'
        errors[payment_field] = [_(f'{field_name} مطلوبة')]
    else:
        cleaned_data['payment_account_id'] = payment_id
    
    # الملاحظات (اختيارية)
    notes = data.get('notes', '').strip()
    cleaned_data['notes'] = notes
    
    # الترحيل التلقائي (اختياري)
    auto_post = data.get('auto_post') == '1' or data.get('auto_post') is True
    cleaned_data['auto_post'] = auto_post
    
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
    إنشاء قيد محاسبي للمصروف
    
    Args:
        cleaned_data: dict - البيانات المنظفة
        user: User - المستخدم الذي أنشأ القيد
    
    Returns:
        JournalEntry - القيد المحاسبي المُنشأ
    
    Raises:
        Exception - في حالة حدوث خطأ
    """
    # الحصول على الحسابات
    expense_account = get_object_or_404(ChartOfAccounts, id=cleaned_data['account_id'])
    payment_account = get_object_or_404(ChartOfAccounts, id=cleaned_data['payment_account_id'])
    
    # الحصول على الفترة المحاسبية
    active_period = get_active_accounting_period(cleaned_data['date'])
    if not active_period:
        raise ValueError(_('لا توجد فترة محاسبية نشطة لهذا التاريخ'))
    
    # إنشاء القيد المحاسبي
    with transaction.atomic():
        # تحديد الحالة بناءً على الترحيل التلقائي
        status = 'posted' if cleaned_data.get('auto_post', False) else 'draft'
        
        journal_entry = JournalEntry.objects.create(
            date=cleaned_data['date'],
            description=cleaned_data['description'],
            notes=cleaned_data.get('notes', ''),
            accounting_period=active_period,
            created_by=user,
            status=status
        )
        
        # سطر المدين (حساب المصروف)
        JournalEntryLine.objects.create(
            journal_entry=journal_entry,
            account=expense_account,
            debit=cleaned_data['amount'],
            credit=Decimal('0'),
            description=cleaned_data['description']
        )
        
        # سطر الدائن (الخزينة)
        JournalEntryLine.objects.create(
            journal_entry=journal_entry,
            account=payment_account,
            debit=Decimal('0'),
            credit=cleaned_data['amount'],
            description=cleaned_data['description']
        )
    
    return journal_entry


def create_journal_entry_for_income(cleaned_data, user):
    """
    إنشاء قيد محاسبي للإيراد
    
    Args:
        cleaned_data: dict - البيانات المنظفة
        user: User - المستخدم الذي أنشأ القيد
    
    Returns:
        JournalEntry - القيد المحاسبي المُنشأ
    
    Raises:
        Exception - في حالة حدوث خطأ
    """
    # الحصول على الحسابات
    income_account = get_object_or_404(ChartOfAccounts, id=cleaned_data['account_id'])
    receipt_account = get_object_or_404(ChartOfAccounts, id=cleaned_data['payment_account_id'])
    
    # الحصول على الفترة المحاسبية
    active_period = get_active_accounting_period(cleaned_data['date'])
    if not active_period:
        raise ValueError(_('لا توجد فترة محاسبية نشطة لهذا التاريخ'))
    
    # إنشاء القيد المحاسبي
    with transaction.atomic():
        # تحديد الحالة بناءً على الترحيل التلقائي
        status = 'posted' if cleaned_data.get('auto_post', False) else 'draft'
        
        journal_entry = JournalEntry.objects.create(
            date=cleaned_data['date'],
            description=cleaned_data['description'],
            notes=cleaned_data.get('notes', ''),
            accounting_period=active_period,
            created_by=user,
            status=status
        )
        
        # سطر المدين (الخزينة)
        JournalEntryLine.objects.create(
            journal_entry=journal_entry,
            account=receipt_account,
            debit=cleaned_data['amount'],
            credit=Decimal('0'),
            description=cleaned_data['description']
        )
        
        # سطر الدائن (حساب الإيراد)
        JournalEntryLine.objects.create(
            journal_entry=journal_entry,
            account=income_account,
            debit=Decimal('0'),
            credit=cleaned_data['amount'],
            description=cleaned_data['description']
        )
    
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
        
        accounts = ", ".join([line.account.name for line in lines])
        
        enhanced_entry = {
            "id": entry.id,
            "number": entry.number,
            "date": entry.date,
            "description": entry.description,
            amount_key: amount,
            accounts_key: accounts,
            "status": entry.status,
            "entry_type": entry.entry_type,
        }
        enhanced_entries.append(enhanced_entry)
    
    return enhanced_entries
