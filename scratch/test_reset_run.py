import os
import sys
import django

sys.path.insert(0, r"c:\Users\UTD\Desktop\MWHEBA ERP")
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'corporate_erp.settings')
django.setup()

from django.apps import apps
from decimal import Decimal
from core.services.system_reset_service import SystemResetService

print("Running test reset...")
# We will inspect how safe_delete behaves on all these models
summary = SystemResetService.reset_test_transactions()
print(f"Summary total keys: {len(summary)}, total deleted: {sum(summary.values())}")
for k, v in summary.items():
    if v > 0:
        print(f"  {k}: {v}")
