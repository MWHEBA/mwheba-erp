import os
import sys
import django

sys.path.append(os.path.dirname(os.path.abspath(__file__)) + "/..")
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'corporate_erp.settings')
django.setup()

from financial.models import ChartOfAccounts

accounts = ChartOfAccounts.objects.filter(is_cash_account=True) | ChartOfAccounts.objects.filter(is_bank_account=True)
print(f"Total Cash/Bank Accounts: {accounts.count()}")
for acc in accounts:
    print(f"ID: {acc.id}, Code: {acc.code}, Currency FK: {acc.currency.code if acc.currency else 'None (EGP Default)'}, Is Foreign: {acc.is_foreign_currency}")
