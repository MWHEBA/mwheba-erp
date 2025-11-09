"""
Script لتحميل البيانات التجريبية للمعاملات مع القيود المحاسبية
"""
import os
import sys
import django
from decimal import Decimal
from datetime import datetime, date
from django.utils import timezone

# إعداد Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mwheba_erp.settings')
django.setup()

from django.contrib.auth import get_user_model
from financial.models import JournalEntry, JournalEntryLine, AccountingPeriod, ChartOfAccounts
from purchase.models import Purchase, PurchaseItem, PurchasePayment
from sale.models import Sale, SaleItem, SalePayment
from supplier.models import Supplier
from client.models import Customer
from product.models import Product, Warehouse

User = get_user_model()

def make_aware(dt):
    """تحويل datetime إلى timezone-aware"""
    return timezone.make_aware(dt) if timezone.is_naive(dt) else dt

def load_demo_transactions():
    """تحميل البيانات التجريبية"""
    
    print("🔄 بدء تحميل البيانات التجريبية...")
    
    # التحقق من وجود بيانات سابقة
    if JournalEntry.objects.filter(number__startswith="JE-2025-").exists():
        print("⚠️  البيانات التجريبية موجودة بالفعل. سيتم حذفها وإعادة إنشائها...")
        JournalEntry.objects.filter(number__startswith="JE-2025-").delete()
        Purchase.objects.filter(number__startswith="PUR").delete()
        Sale.objects.filter(number__startswith="SALE").delete()
        print("✅ تم حذف البيانات القديمة")
    
    # الحصول على البيانات المطلوبة
    try:
        user = User.objects.get(pk=1)
        period = AccountingPeriod.objects.get(pk=1)
        warehouse = Warehouse.objects.get(pk=1)
        
        # الحسابات
        cash_account = ChartOfAccounts.objects.get(code="11011")  # الصندوق الرئيسي
        purchases_account = ChartOfAccounts.objects.get(code="51010")  # تكلفة البضاعة المباعة
        sales_account = ChartOfAccounts.objects.get(code="41010")  # إيرادات المبيعات
        
        # الموردين والعملاء (يجب أن يكون لهم حسابات محاسبية من الفكستشرز)
        supplier1 = Supplier.objects.get(pk=3)  # شركة الورق السعودية
        supplier2 = Supplier.objects.get(pk=2)  # مطابع الخليج
        customer1 = Customer.objects.get(pk=1)  # راقيات الإبداع
        customer2 = Customer.objects.get(pk=2)  # تراست بلس
        
        # التحقق من وجود الحسابات المحاسبية
        if not supplier1.financial_account:
            raise Exception(f"❌ المورد {supplier1.name} ليس له حساب محاسبي!")
        if not supplier2.financial_account:
            raise Exception(f"❌ المورد {supplier2.name} ليس له حساب محاسبي!")
        if not customer1.financial_account:
            raise Exception(f"❌ العميل {customer1.name} ليس له حساب محاسبي!")
        if not customer2.financial_account:
            raise Exception(f"❌ العميل {customer2.name} ليس له حساب محاسبي!")
        
        print(f"✅ جميع العملاء والموردين لديهم حسابات محاسبية")
        
        # المنتجات
        product1 = Product.objects.get(pk=1)
        product2 = Product.objects.get(pk=2)
        product3 = Product.objects.get(pk=3)
        
    except Exception as e:
        print(f"❌ خطأ في الحصول على البيانات الأساسية: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 1. فاتورة شراء نقدي PUR0001
    print("📝 إنشاء فاتورة شراء نقدي PUR0001...")
    je1 = JournalEntry.objects.create(
        number="JE-2025-0001",
        date=date(2025, 1, 15),
        entry_type="automatic",
        description="فاتورة شراء نقدي - كوشيه 300 جم - PUR0001",
        reference="PUR0001",
        status="posted",
        accounting_period=period,
        created_by=user,
        posted_at=make_aware(datetime(2025, 1, 15, 10, 0)),
        posted_by=user
    )
    JournalEntryLine.objects.create(
        journal_entry=je1,
        account=purchases_account,
        description="مشتريات - كوشيه 300 جم",
        debit=Decimal("2500.00"),
        credit=Decimal("0.00")
    )
    JournalEntryLine.objects.create(
        journal_entry=je1,
        account=cash_account,
        description="دفع نقدي - فاتورة PUR0001",
        debit=Decimal("0.00"),
        credit=Decimal("2500.00")
    )
    
    purchase1 = Purchase.objects.create(
        number="PUR0001",
        date=date(2025, 1, 15),
        status="confirmed",
        supplier=supplier1,
        warehouse=warehouse,
        subtotal=Decimal("2500.00"),
        discount=Decimal("0.00"),
        tax=Decimal("0.00"),
        total=Decimal("2500.00"),
        payment_method="cash",
        payment_status="paid",
        notes="فاتورة شراء نقدي - كوشيه 300 جم",
        journal_entry=je1,
        created_by=user
    )
    PurchaseItem.objects.create(
        purchase=purchase1,
        product=product1,
        quantity=500,
        unit_price=Decimal("5.00"),
        discount=Decimal("0.00"),
        total=Decimal("2500.00")
    )
    PurchasePayment.objects.create(
        purchase=purchase1,
        amount=Decimal("2500.00"),
        payment_date=date(2025, 1, 15),
        payment_method="cash",
        reference_number="CASH-001",
        notes="دفع نقدي كامل",
        created_by=user,
        financial_account=cash_account,
        financial_transaction=je1,
        financial_status="synced",
        status="posted",
        posted_at=make_aware(datetime(2025, 1, 15, 10, 5)),
        posted_by=user
    )
    print("✅ تم إنشاء PUR0001")
    
    # 2. فاتورة شراء آجل PUR0002
    print("📝 إنشاء فاتورة شراء آجل PUR0002...")
    je2 = JournalEntry.objects.create(
        number="JE-2025-0002",
        date=date(2025, 1, 16),
        entry_type="automatic",
        description="فاتورة شراء آجل - أوفست 80جم ودوبلكس 250جم - PUR0002",
        reference="PUR0002",
        status="posted",
        accounting_period=period,
        created_by=user,
        posted_at=make_aware(datetime(2025, 1, 16, 11, 0)),
        posted_by=user
    )
    JournalEntryLine.objects.create(
        journal_entry=je2,
        account=purchases_account,
        description="مشتريات - أوفست 80جم ودوبلكس 250جم",
        debit=Decimal("3700.00"),
        credit=Decimal("0.00")
    )
    JournalEntryLine.objects.create(
        journal_entry=je2,
        account=supplier2.financial_account,  # حساب المورد الفردي
        description=f"ذمم دائنة - {supplier2.name}",
        debit=Decimal("0.00"),
        credit=Decimal("3700.00")
    )
    
    purchase2 = Purchase.objects.create(
        number="PUR0002",
        date=date(2025, 1, 16),
        status="confirmed",
        supplier=supplier2,
        warehouse=warehouse,
        subtotal=Decimal("3700.00"),
        discount=Decimal("0.00"),
        tax=Decimal("0.00"),
        total=Decimal("3700.00"),
        payment_method="credit",
        payment_status="partially_paid",
        notes="فاتورة شراء آجل - أوفست 80جم ودوبلكس 250جم",
        journal_entry=je2,
        created_by=user
    )
    PurchaseItem.objects.create(
        purchase=purchase2,
        product=product2,
        quantity=1000,
        unit_price=Decimal("2.50"),
        discount=Decimal("0.00"),
        total=Decimal("2500.00")
    )
    PurchaseItem.objects.create(
        purchase=purchase2,
        product=product3,
        quantity=300,
        unit_price=Decimal("4.00"),
        discount=Decimal("0.00"),
        total=Decimal("1200.00")
    )
    
    # دفعة جزئية
    je3 = JournalEntry.objects.create(
        number="JE-2025-0003",
        date=date(2025, 1, 16),
        entry_type="automatic",
        description="دفعة جزئية من فاتورة آجل - PUR0002",
        reference="CASH-002",
        status="posted",
        accounting_period=period,
        created_by=user,
        posted_at=make_aware(datetime(2025, 1, 16, 11, 10)),
        posted_by=user
    )
    JournalEntryLine.objects.create(
        journal_entry=je3,
        account=supplier2.financial_account,  # حساب المورد الفردي
        description=f"تسديد جزئي - {supplier2.name}",
        debit=Decimal("2000.00"),
        credit=Decimal("0.00")
    )
    JournalEntryLine.objects.create(
        journal_entry=je3,
        account=cash_account,
        description="دفع نقدي",
        debit=Decimal("0.00"),
        credit=Decimal("2000.00")
    )
    
    PurchasePayment.objects.create(
        purchase=purchase2,
        amount=Decimal("2000.00"),
        payment_date=date(2025, 1, 16),
        payment_method="cash",
        reference_number="CASH-002",
        notes="دفعة جزئية من فاتورة آجل",
        created_by=user,
        financial_account=cash_account,
        financial_transaction=je3,
        financial_status="synced",
        status="posted",
        posted_at=make_aware(datetime(2025, 1, 16, 11, 10)),
        posted_by=user
    )
    print("✅ تم إنشاء PUR0002")
    
    # 3. فاتورة بيع نقدي SALE0001
    print("📝 إنشاء فاتورة بيع نقدي SALE0001...")
    je4 = JournalEntry.objects.create(
        number="JE-2025-0004",
        date=date(2025, 1, 17),
        entry_type="automatic",
        description="فاتورة بيع نقدي - كوشيه 300 جم - SALE0001",
        reference="SALE0001",
        status="posted",
        accounting_period=period,
        created_by=user,
        posted_at=make_aware(datetime(2025, 1, 17, 14, 0)),
        posted_by=user
    )
    JournalEntryLine.objects.create(
        journal_entry=je4,
        account=cash_account,
        description="تحصيل نقدي - SALE0001",
        debit=Decimal("700.00"),
        credit=Decimal("0.00")
    )
    JournalEntryLine.objects.create(
        journal_entry=je4,
        account=sales_account,
        description="إيراد مبيعات - كوشيه 300 جم",
        debit=Decimal("0.00"),
        credit=Decimal("700.00")
    )
    
    sale1 = Sale.objects.create(
        number="SALE0001",
        date=date(2025, 1, 17),
        status="confirmed",
        customer=customer1,
        warehouse=warehouse,
        subtotal=Decimal("700.00"),
        discount=Decimal("0.00"),
        tax=Decimal("0.00"),
        total=Decimal("700.00"),
        payment_method="cash",
        payment_status="paid",
        notes="فاتورة بيع نقدي - كوشيه 300 جم",
        journal_entry=je4,
        created_by=user
    )
    SaleItem.objects.create(
        sale=sale1,
        product=product1,
        quantity=Decimal("100.00"),
        unit_price=Decimal("7.00"),
        discount=Decimal("0.00"),
        total=Decimal("700.00")
    )
    SalePayment.objects.create(
        sale=sale1,
        amount=Decimal("700.00"),
        payment_date=date(2025, 1, 17),
        payment_method="cash",
        reference_number="CASH-003",
        notes="تحصيل نقدي كامل",
        created_by=user,
        financial_account=cash_account,
        financial_transaction=je4,
        financial_status="synced",
        status="posted",
        posted_at=make_aware(datetime(2025, 1, 17, 14, 5)),
        posted_by=user
    )
    print("✅ تم إنشاء SALE0001")
    
    # 4. فاتورة بيع آجل SALE0002
    print("📝 إنشاء فاتورة بيع آجل SALE0002...")
    je5 = JournalEntry.objects.create(
        number="JE-2025-0005",
        date=date(2025, 1, 18),
        entry_type="automatic",
        description="فاتورة بيع آجل - أوفست 80 ودوبلكس 250 - SALE0002",
        reference="SALE0002",
        status="posted",
        accounting_period=period,
        created_by=user,
        posted_at=make_aware(datetime(2025, 1, 18, 15, 0)),
        posted_by=user
    )
    JournalEntryLine.objects.create(
        journal_entry=je5,
        account=customer2.financial_account,  # حساب العميل الفردي
        description=f"ذمم مدينة - {customer2.name}",
        debit=Decimal("975.00"),
        credit=Decimal("0.00")
    )
    JournalEntryLine.objects.create(
        journal_entry=je5,
        account=sales_account,
        description="إيراد مبيعات - أوفست ودوبلكس",
        debit=Decimal("0.00"),
        credit=Decimal("975.00")
    )
    
    sale2 = Sale.objects.create(
        number="SALE0002",
        date=date(2025, 1, 18),
        status="confirmed",
        customer=customer2,
        warehouse=warehouse,
        subtotal=Decimal("975.00"),
        discount=Decimal("0.00"),
        tax=Decimal("0.00"),
        total=Decimal("975.00"),
        payment_method="credit",
        payment_status="partially_paid",
        notes="فاتورة بيع آجل - أوفست 80 ودوبلكس 250",
        journal_entry=je5,
        created_by=user
    )
    SaleItem.objects.create(
        sale=sale2,
        product=product2,
        quantity=Decimal("200.00"),
        unit_price=Decimal("3.50"),
        discount=Decimal("0.00"),
        total=Decimal("700.00")
    )
    SaleItem.objects.create(
        sale=sale2,
        product=product3,
        quantity=Decimal("50.00"),
        unit_price=Decimal("5.50"),
        discount=Decimal("0.00"),
        total=Decimal("275.00")
    )
    
    # تحصيل جزئي
    je6 = JournalEntry.objects.create(
        number="JE-2025-0006",
        date=date(2025, 1, 18),
        entry_type="automatic",
        description="تحصيل جزئي من فاتورة آجل - SALE0002",
        reference="CASH-004",
        status="posted",
        accounting_period=period,
        created_by=user,
        posted_at=make_aware(datetime(2025, 1, 18, 15, 10)),
        posted_by=user
    )
    JournalEntryLine.objects.create(
        journal_entry=je6,
        account=cash_account,
        description="تحصيل نقدي",
        debit=Decimal("500.00"),
        credit=Decimal("0.00")
    )
    JournalEntryLine.objects.create(
        journal_entry=je6,
        account=customer2.financial_account,  # حساب العميل الفردي
        description=f"تسديد جزئي - {customer2.name}",
        debit=Decimal("0.00"),
        credit=Decimal("500.00")
    )
    
    SalePayment.objects.create(
        sale=sale2,
        amount=Decimal("500.00"),
        payment_date=date(2025, 1, 18),
        payment_method="cash",
        reference_number="CASH-004",
        notes="تحصيل جزئي من فاتورة آجل",
        created_by=user,
        financial_account=cash_account,
        financial_transaction=je6,
        financial_status="synced",
        status="posted",
        posted_at=make_aware(datetime(2025, 1, 18, 15, 10)),
        posted_by=user
    )
    print("✅ تم إنشاء SALE0002")
    
    print("\n✅ تم تحميل جميع البيانات التجريبية بنجاح!")
    print(f"   - 2 فاتورة شراء")
    print(f"   - 2 فاتورة بيع")
    print(f"   - 6 قيود محاسبية")
    print(f"   - 4 دفعات")
    
    return True

if __name__ == "__main__":
    try:
        load_demo_transactions()
    except Exception as e:
        print(f"\n❌ خطأ: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
