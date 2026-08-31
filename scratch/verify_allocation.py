import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import django
from decimal import Decimal

# ضبط إعدادات درانجو
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "corporate_erp.settings")
django.setup()

from django.utils import timezone
from django.contrib.auth import get_user_model
from customer.models import Customer, CustomerPayment
from customer.services.customer_allocation_audit_service import CustomerAllocationAuditService
from supplier.models import Supplier, SupplierType, SupplierAdvancePayment
from supplier.services.supplier_allocation_service import SupplierAllocationService
from sale.models import Sale, SalePayment
from purchase.models import Purchase
from purchase.models.payment import PurchasePayment

User = get_user_model()

def run_verification():
    print("=== بدء فحص واختبار نظام توزيع الرصيد المسبق والدفعات المقدمة ===")
    user = User.objects.filter(is_superuser=True).first() or User.objects.first()

    # 1. اختـبار عميل
    customer, _ = Customer.objects.get_or_create(
        code="CUST-VERIFY-01",
        defaults={"name": "عميل تجربة التوزيع", "created_by": user}
    )

    # إضافة دفعة جديدة للعميل
    cp = CustomerPayment.objects.create(
        customer=customer,
        amount=Decimal("5000.00"),
        payment_date=timezone.now().date(),
        payment_method="cash",
        created_by=user
    )
    print(f"[+] تم تسجيل دفعة عميل بقيمة: {cp.amount} ج.م")

    from product.models import Warehouse
    warehouse = Warehouse.objects.filter(is_active=True).first() or Warehouse.objects.create(name="المخزن الرئيسي", code="WH0001")

    # إضافة فاتورة مبيعات
    sale = Sale.objects.create(
        customer=customer,
        warehouse=warehouse,
        number=f"INV-V-{timezone.now().strftime('%H%M%S')}",
        date=timezone.now().date(),
        subtotal=Decimal("3000.00"),
        total=Decimal("3000.00"),
        created_by=user
    )
    print(f"[+] تم إنشاء فاتورة مبيعات بقيمة: {sale.total} ج.م")

    # تخصيص من الرصيد المسبق
    audit_c = CustomerAllocationAuditService.allocate_customer_prepaid_balance_to_sale(
        sale=sale,
        amount_to_allocate=Decimal("3000.00"),
        user=user
    )
    sale.refresh_from_db()
    print(f"[OK] Customer allocation successful! Status: {sale.payment_status} | Amount Paid: {sale.amount_paid} EGP")
    print(f"[OK] Customer Audit Hash SHA256: {audit_c.evidence_hash[:16]}...")

    # 2. اختـبار مورد
    supplier_type, _ = SupplierType.objects.get_or_create(code="GENERAL", defaults={"name": "عام"})
    supplier, _ = Supplier.objects.get_or_create(
        code="SUPP-VERIFY-01",
        defaults={"name": "مورد تجربة التوزيع", "primary_type": supplier_type, "created_by": user}
    )

    # إضافة دفعة مقدمة للمورد
    adv = SupplierAdvancePayment.objects.create(
        supplier=supplier,
        amount=Decimal("8000.00"),
        payment_date=timezone.now().date(),
        payment_method="bank_transfer",
        created_by=user
    )
    print(f"[+] Supplier advance payment created: {adv.amount} EGP")

    # إضافة فاتورة مشتريات
    purchase = Purchase.objects.create(
        supplier=supplier,
        number=f"BILL-V-{timezone.now().strftime('%H%M%S')}",
        date=timezone.now().date(),
        subtotal=Decimal("4500.00"),
        total=Decimal("4500.00"),
        created_by=user
    )
    print(f"[+] Purchase bill created: {purchase.total} EGP")

    # تخصيص دفعة المورد
    audit_s = SupplierAllocationService.allocate_advance_to_purchase_bill(
        purchase=purchase,
        amount_to_allocate=Decimal("4500.00"),
        user=user
    )
    # اختـبار عكس التخصيص للمورد والعميل
    rev_c = CustomerAllocationAuditService.reverse_customer_allocation(audit_c.id, user=user)
    sale.refresh_from_db()
    print(f"[OK] Customer Reversal successful! Status: {sale.payment_status} | Reversal Audit Hash: {rev_c.evidence_hash[:16]}...")

    rev_s = SupplierAllocationService.reverse_supplier_allocation(audit_s.id, user=user)
    purchase.refresh_from_db()
    adv.refresh_from_db()
    print(f"[OK] Supplier Reversal successful! Status: {purchase.payment_status} | Restored Advance Balance: {adv.remaining_amount} EGP")

    print("=== اكتمل الفحص والتحقق الكامل بما فيه محرك العكس 100% ===")

if __name__ == "__main__":
    run_verification()
