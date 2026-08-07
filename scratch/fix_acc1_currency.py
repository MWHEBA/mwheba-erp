import os
import sys
import django

sys.path.append(os.path.dirname(os.path.abspath(__file__)) + "/..")
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'corporate_erp.settings')
django.setup()

from financial.models import ChartOfAccounts, Currency

acc1 = ChartOfAccounts.objects.filter(pk=1).first()
if acc1:
    egp = Currency.objects.filter(code="EGP").first()
    acc1.currency = None  # Or EGP default
    acc1.save(update_fields=["currency"])
    print(f"FIXED Account #1 ID=1 ({acc1.code}): Currency reset to None (EGP Functional Base Currency).")

accounts = ChartOfAccounts.objects.filter(is_cash_account=True) | ChartOfAccounts.objects.filter(is_bank_account=True)
for acc in accounts:
    print(f"ID: {acc.id}, Code: {acc.code}, Currency FK: {acc.currency.code if acc.currency else 'None (EGP Default)'}, Is Foreign: {acc.is_foreign_currency}")
