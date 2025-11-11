# Generated migration for chart of accounts

from django.db import migrations
from django.utils import timezone


def load_chart_of_accounts(apps, schema_editor):
    AccountType = apps.get_model('financial', 'AccountType')
    ChartOfAccounts = apps.get_model('financial', 'ChartOfAccounts')
    
    # Create AccountTypes
    account_types_data = [
        {'pk': 1, 'code': 'ASSET', 'name': 'الأصول', 'category': 'asset', 'nature': 'debit', 'parent_id': None, 'level': 1},
        {'pk': 2, 'code': 'CURRENT_ASSET', 'name': 'الأصول المتداولة', 'category': 'asset', 'nature': 'debit', 'parent_id': 1, 'level': 2},
        {'pk': 3, 'code': 'CASH', 'name': 'الخزينة', 'category': 'asset', 'nature': 'debit', 'parent_id': 2, 'level': 3},
        {'pk': 4, 'code': 'BANK', 'name': 'البنوك', 'category': 'asset', 'nature': 'debit', 'parent_id': 2, 'level': 3},
        {'pk': 5, 'code': 'RECEIVABLES', 'name': 'العملاء', 'category': 'asset', 'nature': 'debit', 'parent_id': 2, 'level': 3},
        {'pk': 6, 'code': 'INVENTORY', 'name': 'المخزون', 'category': 'asset', 'nature': 'debit', 'parent_id': 2, 'level': 3},
        {'pk': 7, 'code': 'LIABILITY', 'name': 'الخصوم', 'category': 'liability', 'nature': 'credit', 'parent_id': None, 'level': 1},
        {'pk': 8, 'code': 'CURRENT_LIABILITY', 'name': 'الخصوم المتداولة', 'category': 'liability', 'nature': 'credit', 'parent_id': 7, 'level': 2},
        {'pk': 9, 'code': 'PAYABLES', 'name': 'الموردون', 'category': 'liability', 'nature': 'credit', 'parent_id': 8, 'level': 3},
        {'pk': 10, 'code': 'EQUITY', 'name': 'حقوق الملكية', 'category': 'equity', 'nature': 'credit', 'parent_id': None, 'level': 1},
        {'pk': 11, 'code': 'CAPITAL', 'name': 'رأس المال', 'category': 'equity', 'nature': 'credit', 'parent_id': 10, 'level': 2},
        {'pk': 12, 'code': 'PARTNER_ACCOUNT', 'name': 'حساب جاري الشريك', 'category': 'equity', 'nature': 'credit', 'parent_id': 10, 'level': 2},
        {'pk': 13, 'code': 'REVENUE', 'name': 'الإيرادات', 'category': 'revenue', 'nature': 'credit', 'parent_id': None, 'level': 1},
        {'pk': 14, 'code': 'SALES_REVENUE', 'name': 'إيرادات المبيعات', 'category': 'revenue', 'nature': 'credit', 'parent_id': 13, 'level': 2},
        {'pk': 15, 'code': 'OTHER_REVENUE', 'name': 'إيرادات متنوعة', 'category': 'revenue', 'nature': 'credit', 'parent_id': 13, 'level': 2},
        {'pk': 16, 'code': 'EXPENSE', 'name': 'المصروفات', 'category': 'expense', 'nature': 'debit', 'parent_id': None, 'level': 1},
        {'pk': 17, 'code': 'COGS', 'name': 'تكلفة البضاعة المباعة', 'category': 'expense', 'nature': 'debit', 'parent_id': 16, 'level': 2},
        {'pk': 18, 'code': 'OTHER_EXPENSE', 'name': 'مصروفات متنوعة', 'category': 'expense', 'nature': 'debit', 'parent_id': 16, 'level': 2},
    ]
    
    for data in account_types_data:
        AccountType.objects.update_or_create(
            pk=data['pk'],
            defaults={
                'code': data['code'],
                'name': data['name'],
                'category': data['category'],
                'nature': data['nature'],
                'parent_id': data['parent_id'],
                'level': data['level'],
                'is_active': True,
                'created_at': timezone.now(),
                'updated_at': timezone.now(),
            }
        )
    
    # Create Chart of Accounts
    accounts_data = [
        {'pk': 15, 'code': '10000', 'name': 'الأصول', 'name_en': '', 'account_type_id': 1, 'parent_id': None, 'is_leaf': False, 'is_cash_account': False, 'is_bank_account': False},
        {'pk': 1, 'code': '11011', 'name': 'الصندوق الرئيسي', 'name_en': 'Main Cash Box', 'account_type_id': 3, 'parent_id': 15, 'is_leaf': True, 'is_cash_account': True, 'is_bank_account': False},
        {'pk': 2, 'code': '11021', 'name': 'البنك الأهلي', 'name_en': 'National Bank', 'account_type_id': 4, 'parent_id': 15, 'is_leaf': True, 'is_cash_account': False, 'is_bank_account': True},
        {'pk': 3, 'code': '11030', 'name': 'العملاء', 'name_en': 'Customers', 'account_type_id': 5, 'parent_id': 15, 'is_leaf': False, 'is_cash_account': False, 'is_bank_account': False},
        {'pk': 13, 'code': '1103001', 'name': 'عميل - راقيات الابداع', 'name_en': '', 'account_type_id': 5, 'parent_id': 3, 'is_leaf': True, 'is_cash_account': False, 'is_bank_account': False},
        {'pk': 4, 'code': '11051', 'name': 'مخزون البضاعة', 'name_en': 'Inventory', 'account_type_id': 6, 'parent_id': 15, 'is_leaf': True, 'is_cash_account': False, 'is_bank_account': False},
        {'pk': 16, 'code': '20000', 'name': 'الخصوم', 'name_en': '', 'account_type_id': 7, 'parent_id': None, 'is_leaf': False, 'is_cash_account': False, 'is_bank_account': False},
        {'pk': 5, 'code': '21010', 'name': 'الموردون', 'name_en': 'Suppliers', 'account_type_id': 9, 'parent_id': 16, 'is_leaf': False, 'is_cash_account': False, 'is_bank_account': False},
        {'pk': 14, 'code': '2101001', 'name': 'مورد - مخزن مكة', 'name_en': '', 'account_type_id': 9, 'parent_id': 5, 'is_leaf': True, 'is_cash_account': False, 'is_bank_account': False},
        {'pk': 21, 'code': '21020', 'name': 'مستحقات الرواتب', 'name_en': 'Salaries Payable', 'account_type_id': 8, 'parent_id': 16, 'is_leaf': True, 'is_cash_account': False, 'is_bank_account': False},
        {'pk': 20, 'code': '22010', 'name': 'القروض طويلة الأجل', 'name_en': 'Long-term Loans', 'account_type_id': 7, 'parent_id': 16, 'is_leaf': True, 'is_cash_account': False, 'is_bank_account': False},
        {'pk': 17, 'code': '30000', 'name': 'حقوق الملكية', 'name_en': '', 'account_type_id': 10, 'parent_id': None, 'is_leaf': False, 'is_cash_account': False, 'is_bank_account': False},
        {'pk': 6, 'code': '31010', 'name': 'رأس المال', 'name_en': 'Capital', 'account_type_id': 11, 'parent_id': 17, 'is_leaf': True, 'is_cash_account': False, 'is_bank_account': False},
        {'pk': 7, 'code': '31020', 'name': 'جاري الشريك - محمد يوسف', 'name_en': 'Partner Current Account - Mohamed Youssef', 'account_type_id': 12, 'parent_id': 17, 'is_leaf': True, 'is_cash_account': False, 'is_bank_account': False},
        {'pk': 18, 'code': '40000', 'name': 'الإيرادات', 'name_en': '', 'account_type_id': 13, 'parent_id': None, 'is_leaf': False, 'is_cash_account': False, 'is_bank_account': False},
        {'pk': 8, 'code': '41010', 'name': 'إيرادات المبيعات', 'name_en': 'Sales Revenue', 'account_type_id': 14, 'parent_id': 18, 'is_leaf': True, 'is_cash_account': False, 'is_bank_account': False},
        {'pk': 9, 'code': '42010', 'name': 'إيرادات متنوعة', 'name_en': 'Other Revenue', 'account_type_id': 15, 'parent_id': 18, 'is_leaf': True, 'is_cash_account': False, 'is_bank_account': False},
        {'pk': 19, 'code': '50000', 'name': 'المصروفات', 'name_en': '', 'account_type_id': 16, 'parent_id': None, 'is_leaf': False, 'is_cash_account': False, 'is_bank_account': False},
        {'pk': 10, 'code': '51010', 'name': 'تكلفة البضاعة المباعة', 'name_en': 'Cost of Goods Sold', 'account_type_id': 17, 'parent_id': 19, 'is_leaf': True, 'is_cash_account': False, 'is_bank_account': False},
        {'pk': 11, 'code': '52010', 'name': 'مصروفات الشحن', 'name_en': 'Shipping Expenses', 'account_type_id': 18, 'parent_id': 19, 'is_leaf': True, 'is_cash_account': False, 'is_bank_account': False},
        {'pk': 22, 'code': '52020', 'name': 'الرواتب والأجور', 'name_en': 'Salaries and Wages', 'account_type_id': 18, 'parent_id': 19, 'is_leaf': True, 'is_cash_account': False, 'is_bank_account': False},
        {'pk': 23, 'code': '53010', 'name': 'المصروفات التسويقية', 'name_en': 'Marketing Expenses', 'account_type_id': 18, 'parent_id': 19, 'is_leaf': True, 'is_cash_account': False, 'is_bank_account': False},
        {'pk': 12, 'code': '54010', 'name': 'مصروفات متنوعة', 'name_en': 'General Expenses', 'account_type_id': 18, 'parent_id': 19, 'is_leaf': True, 'is_cash_account': False, 'is_bank_account': False},
    ]
    
    for data in accounts_data:
        ChartOfAccounts.objects.update_or_create(
            pk=data['pk'],
            defaults={
                'code': data['code'],
                'name': data['name'],
                'name_en': data['name_en'],
                'account_type_id': data['account_type_id'],
                'parent_id': data['parent_id'],
                'is_active': True,
                'is_leaf': data['is_leaf'],
                'is_cash_account': data['is_cash_account'],
                'is_bank_account': data['is_bank_account'],
                'opening_balance': 0.0,
                'created_at': timezone.now(),
                'updated_at': timezone.now(),
            }
        )


class Migration(migrations.Migration):

    dependencies = [
        ('financial', '0002_initial'),
    ]

    operations = [
        migrations.RunPython(load_chart_of_accounts),
    ]
