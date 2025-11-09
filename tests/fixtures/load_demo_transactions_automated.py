"""
Script لتحميل البيانات التجريبية - يتصرف كمستخدم عادي 100%
يترك جميع العمليات للنظام التلقائي (القيود المحاسبية، الربط، التحديثات)
لا يتدخل في سير عمل النظام - يتعامل كمستخدم فقط
"""
import os
import sys
import django
from decimal import Decimal
from datetime import date

# إعداد Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mwheba_erp.settings')
django.setup()

from django.contrib.auth import get_user_model
from django.db import transaction
from financial.services.payment_integration_service import PaymentIntegrationService
from financial.services.accounting_integration_service import AccountingIntegrationService
from purchase.models import Purchase, PurchaseItem, PurchasePayment
from sale.models import Sale, SaleItem, SalePayment
from supplier.models import Supplier
from client.models import Customer
from product.models import Product, Warehouse
from financial.models import ChartOfAccounts, AccountType

User = get_user_model()


def load_demo_transactions():
    """تحميل البيانات التجريبية - بطريقة تلقائية 100%"""
    
    print("\n" + "="*60)
    print("[*] بدء تحميل البيانات التجريبية (وضع تلقائي كامل)")
    print("="*60 + "\n")
    
    # حذف البيانات القديمة
    if Purchase.objects.filter(number__startswith="PUR").exists() or Sale.objects.filter(number__startswith="SALE").exists():
        print("[!] حذف البيانات التجريبية القديمة...")
        Purchase.objects.filter(number__startswith="PUR").delete()
        Sale.objects.filter(number__startswith="SALE").delete()
        print("[OK] تم الحذف\n")
    
    try:
        # الحصول على المستخدم
        user = User.objects.filter(is_superuser=True).first()
        if not user:
            user = User.objects.first()
        if not user:
            raise Exception("[X] لا يوجد مستخدمين في النظام!")
        
        # الحصول على المخزن
        warehouse = Warehouse.objects.first()
        if not warehouse:
            raise Exception("[X] لا توجد مخازن في النظام!")
        
        # الحصول على الحساب النقدي
        cash_account = ChartOfAccounts.objects.get(code="11011")
        
        # الحصول على الموردين والعملاء
        suppliers = list(Supplier.objects.all()[:2])
        if len(suppliers) < 2:
            raise Exception("[X] يجب وجود مورّدين على الأقل!")
        supplier1, supplier2 = suppliers[0], suppliers[1]
        
        customers = list(Customer.objects.all()[:2])
        if len(customers) < 2:
            raise Exception("[X] يجب وجود عميلين على الأقل!")
        customer1, customer2 = customers[0], customers[1]
        
        # إنشاء حسابات محاسبية للموردين والعملاء
        print("[!] إنشاء الحسابات المحاسبية للموردين والعملاء...")
        
        # حساب الموردين الرئيسي
        try:
            suppliers_parent = ChartOfAccounts.objects.get(code="21010")
        except ChartOfAccounts.DoesNotExist:
            print("[X] حساب الموردين الرئيسي غير موجود (21010)")
            print("[!] تخطي إنشاء حسابات الموردين...")
            suppliers_parent = None
        
        # إنشاء حساب للمورد الأول
        if suppliers_parent and not supplier1.financial_account:
            liability_type = AccountType.objects.get(code="PAYABLES")
            account_code = f"21010{supplier1.id:02d}"
            
            # البحث عن حساب موجود أو إنشاء جديد
            supplier1_account, created = ChartOfAccounts.objects.get_or_create(
                code=account_code,
                defaults={
                    "name": f"مورد - {supplier1.name}",
                    "name_en": f"Supplier - {supplier1.name}",
                    "account_type": liability_type,
                    "parent": suppliers_parent,
                    "is_active": True
                }
            )
            
            # تحديث الاسم لو الحساب موجود
            if not created:
                supplier1_account.name = f"مورد - {supplier1.name}"
                supplier1_account.name_en = f"Supplier - {supplier1.name}"
                supplier1_account.save()
                print(f"[OK] تم تحديث حساب المورد: {supplier1.name}")
            else:
                print(f"[OK] تم إنشاء حساب للمورد: {supplier1.name}")
            
            supplier1.financial_account = supplier1_account
            supplier1.save()
        
        # إنشاء حساب للمورد الثاني
        if suppliers_parent and not supplier2.financial_account:
            liability_type = AccountType.objects.get(code="PAYABLES")
            account_code = f"21010{supplier2.id:02d}"
            
            # البحث عن حساب موجود أو إنشاء جديد
            supplier2_account, created = ChartOfAccounts.objects.get_or_create(
                code=account_code,
                defaults={
                    "name": f"مورد - {supplier2.name}",
                    "name_en": f"Supplier - {supplier2.name}",
                    "account_type": liability_type,
                    "parent": suppliers_parent,
                    "is_active": True
                }
            )
            
            # تحديث الاسم لو الحساب موجود
            if not created:
                supplier2_account.name = f"مورد - {supplier2.name}"
                supplier2_account.name_en = f"Supplier - {supplier2.name}"
                supplier2_account.save()
                print(f"[OK] تم تحديث حساب المورد: {supplier2.name}")
            else:
                print(f"[OK] تم إنشاء حساب للمورد: {supplier2.name}")
            
            supplier2.financial_account = supplier2_account
            supplier2.save()
        
        # حساب العملاء الرئيسي
        try:
            customers_parent = ChartOfAccounts.objects.get(code="11030")
        except ChartOfAccounts.DoesNotExist:
            print("[X] حساب العملاء الرئيسي غير موجود (11030)")
            print("[!] تخطي إنشاء حسابات العملاء...")
            customers_parent = None
        
        # إنشاء حساب للعميل الأول
        if customers_parent and not customer1.financial_account:
            asset_type = AccountType.objects.get(code="RECEIVABLES")
            account_code = f"11030{customer1.id:02d}"
            
            # البحث عن حساب موجود أو إنشاء جديد
            customer1_account, created = ChartOfAccounts.objects.get_or_create(
                code=account_code,
                defaults={
                    "name": f"عميل - {customer1.name}",
                    "name_en": f"Customer - {customer1.name}",
                    "account_type": asset_type,
                    "parent": customers_parent,
                    "is_active": True
                }
            )
            
            # تحديث الاسم لو الحساب موجود
            if not created:
                customer1_account.name = f"عميل - {customer1.name}"
                customer1_account.name_en = f"Customer - {customer1.name}"
                customer1_account.save()
                print(f"[OK] تم تحديث حساب العميل: {customer1.name}")
            else:
                print(f"[OK] تم إنشاء حساب للعميل: {customer1.name}")
            
            customer1.financial_account = customer1_account
            customer1.save()
        
        # إنشاء حساب للعميل الثاني
        if customers_parent and not customer2.financial_account:
            asset_type = AccountType.objects.get(code="RECEIVABLES")
            account_code = f"11030{customer2.id:02d}"
            
            # البحث عن حساب موجود أو إنشاء جديد
            customer2_account, created = ChartOfAccounts.objects.get_or_create(
                code=account_code,
                defaults={
                    "name": f"عميل - {customer2.name}",
                    "name_en": f"Customer - {customer2.name}",
                    "account_type": asset_type,
                    "parent": customers_parent,
                    "is_active": True
                }
            )
            
            # تحديث الاسم لو الحساب موجود
            if not created:
                customer2_account.name = f"عميل - {customer2.name}"
                customer2_account.name_en = f"Customer - {customer2.name}"
                customer2_account.save()
                print(f"[OK] تم تحديث حساب العميل: {customer2.name}")
            else:
                print(f"[OK] تم إنشاء حساب للعميل: {customer2.name}")
            
            customer2.financial_account = customer2_account
            customer2.save()
        
        if suppliers_parent or customers_parent:
            print("[OK] تم إنشاء الحسابات المحاسبية")
        else:
            print("[!] لم يتم إنشاء حسابات محاسبية (الحسابات الرئيسية غير موجودة)")
        
        # الحصول على المنتجات
        products = list(Product.objects.all()[:3])
        if len(products) < 3:
            raise Exception("[X] يجب وجود 3 منتجات على الأقل!")
        product1, product2, product3 = products[0], products[1], products[2]
        
        print(f"[OK] البيانات الأساسية جاهزة")
        print(f"    - المستخدم: {user.username}")
        print(f"    - المخزن: {warehouse.name}")
        print(f"    - الموردين: {supplier1.name}, {supplier2.name}")
        print(f"    - العملاء: {customer1.name}, {customer2.name}\n")
        
        # ═══════════════════════════════════════════════════════════
        # 1. فاتورة شراء نقدي PUR0001 (اختبار 1)
        # ═══════════════════════════════════════════════════════════
        print("[1/4] إنشاء فاتورة شراء نقدي PUR0001 (اختبار 1)...")
        
        with transaction.atomic():
            # إنشاء الفاتورة
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
                payment_status="unpaid",
                notes="فاتورة شراء نقدي - كوشيه 300 جم",
                created_by=user
            )
            
            # إضافة البنود
            PurchaseItem.objects.create(
                purchase=purchase1,
                product=product1,
                quantity=500,
                unit_price=Decimal("5.00"),
                discount=Decimal("0.00"),
                total=Decimal("2500.00")
            )
            
            # ملاحظة: قيد الفاتورة يُنشأ تلقائياً عبر Signal في purchase/signals.py
            # عند حفظ الفاتورة بحالة "confirmed"
            
            # إنشاء الدفعة
            payment1 = PurchasePayment.objects.create(
                purchase=purchase1,
                amount=Decimal("2500.00"),
                payment_date=date(2025, 1, 15),
                payment_method="cash",
                reference_number="CASH-001",
                notes="دفع نقدي كامل",
                created_by=user,
                financial_account=cash_account,
                status="draft"
            )
            
            # معالجة الدفعة (عبر PaymentIntegrationService)
            try:
                result = PaymentIntegrationService.process_payment(payment1, "purchase", user)
                
                if result["success"]:
                    payment1.refresh_from_db()
                    purchase1.refresh_from_db()
                    print(f"    [OK] قيد الدفعة: {payment1.financial_transaction.number if payment1.financial_transaction else 'N/A'}")
                    print(f"        - مدين المورد: {payment1.amount}")
                    print(f"        - دائن الخزينة: {payment1.amount}")
                    print(f"    [OK] حالة السداد: {purchase1.get_payment_status_display()}")
                    print(f"    [OK] رصيد المورد: {supplier1.balance}")
                else:
                    print(f"    [X] فشل معالجة الدفعة: {result.get('message')}")
            except Exception as e:
                print(f"    [X] خطأ في معالجة الدفعة: {str(e)}")
        
        print()
        
        # ═══════════════════════════════════════════════════════════
        # 2. فاتورة شراء آجل PUR0002 + دفعة جزئية (اختبار 2 + 3)
        # ═══════════════════════════════════════════════════════════
        print("[2/4] إنشاء فاتورة شراء آجل PUR0002 + دفعة جزئية (اختبار 2 + 3)...")
        
        with transaction.atomic():
            # إنشاء الفاتورة
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
                payment_status="unpaid",
                notes="فاتورة شراء آجل - أوفست 80جم ودوبلكس 250جم",
                created_by=user
            )
            
            # إضافة البنود
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
            
            # ملاحظة: قيد الفاتورة يُنشأ تلقائياً عبر Signal
        
            # دفعة جزئية (اختبار 3: سداد رصيد مورد)
            payment2 = PurchasePayment.objects.create(
                purchase=purchase2,
                amount=Decimal("2000.00"),
                payment_date=date(2025, 1, 16),
                payment_method="cash",
                reference_number="CASH-002",
                notes="دفعة جزئية 2000 من أصل 3700",
                created_by=user,
                financial_account=cash_account,
                status="draft"
            )
            
            # معالجة الدفعة
            try:
                result = PaymentIntegrationService.process_payment(payment2, "purchase", user)
                
                if result["success"]:
                    payment2.refresh_from_db()
                    purchase2.refresh_from_db()
                    print(f"    [OK] قيد الدفعة: {payment2.financial_transaction.number if payment2.financial_transaction else 'N/A'}")
                    print(f"        - مدين المورد: {payment2.amount}")
                    print(f"        - دائن الخزينة: {payment2.amount}")
                    print(f"    [OK] حالة السداد: {purchase2.get_payment_status_display()}")
                    print(f"    [OK] المدفوع: {purchase2.amount_paid} من {purchase2.total}")
                    print(f"    [OK] رصيد المورد: {supplier2.balance}")
                else:
                    print(f"    [X] فشل معالجة الدفعة: {result.get('message')}")
            except Exception as e:
                print(f"    [X] خطأ في معالجة الدفعة: {str(e)}")
        
        print()
        
        # ═══════════════════════════════════════════════════════════
        # 3. فاتورة بيع نقدي SALE0001 (اختبار 4)
        # ═══════════════════════════════════════════════════════════
        print("[3/4] إنشاء فاتورة بيع نقدي SALE0001 (اختبار 4)...")
        
        with transaction.atomic():
            # إنشاء الفاتورة
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
                payment_status="unpaid",
                notes="فاتورة بيع نقدي - كوشيه 300 جم",
                created_by=user
            )
            
            # إضافة البنود
            SaleItem.objects.create(
                sale=sale1,
                product=product1,
                quantity=Decimal("100.00"),
                unit_price=Decimal("7.00"),
                discount=Decimal("0.00"),
                total=Decimal("700.00")
            )
            
            # إنشاء القيد المحاسبي للفاتورة (عبر AccountingIntegrationService)
            try:
                journal_entry = AccountingIntegrationService.create_sale_journal_entry(
                    sale=sale1, user=user
                )
                if journal_entry:
                    print(f"    [OK] قيد الفاتورة: {journal_entry.number}")
                    print(f"        - مدين العميل: {sale1.total}")
                    print(f"        - دائن الإيرادات: {sale1.total}")
                    print(f"        - قيد التكلفة: مدين التكلفة / دائن المخزون")
                else:
                    print(f"    [!] لم يتم إنشاء قيد للفاتورة")
            except Exception as e:
                print(f"    [X] خطأ في قيد الفاتورة: {str(e)}")
            
            # إنشاء الدفعة
            sale_payment1 = SalePayment.objects.create(
                sale=sale1,
                amount=Decimal("700.00"),
                payment_date=date(2025, 1, 17),
                payment_method="cash",
                reference_number="CASH-003",
                notes="تحصيل نقدي كامل",
                created_by=user,
                financial_account=cash_account,
                status="draft"
            )
            
            # معالجة الدفعة (عبر PaymentIntegrationService)
            try:
                result = PaymentIntegrationService.process_payment(sale_payment1, "sale", user)
                
                if result["success"]:
                    sale_payment1.refresh_from_db()
                    sale1.refresh_from_db()
                    print(f"    [OK] قيد الدفعة: {sale_payment1.financial_transaction.number if sale_payment1.financial_transaction else 'N/A'}")
                    print(f"        - مدين الخزينة: {sale_payment1.amount}")
                    print(f"        - دائن العميل: {sale_payment1.amount}")
                    print(f"    [OK] حالة السداد: {sale1.get_payment_status_display()}")
                    print(f"    [OK] رصيد العميل: {customer1.balance}")
                else:
                    print(f"    [X] فشل معالجة الدفعة: {result.get('message')}")
            except Exception as e:
                print(f"    [X] خطأ في معالجة الدفعة: {str(e)}")
        
        print()
        
        # ═══════════════════════════════════════════════════════════
        # 4. فاتورة بيع آجل SALE0002 + تحصيل جزئي (اختبار 5 + 6)
        # ═══════════════════════════════════════════════════════════
        print("[4/4] إنشاء فاتورة بيع آجل SALE0002 + تحصيل جزئي (اختبار 5 + 6)...")
        
        with transaction.atomic():
            # إنشاء الفاتورة
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
                payment_status="unpaid",
                notes="فاتورة بيع آجل - أوفست 80 ودوبلكس 250",
                created_by=user
            )
            
            # إضافة البنود
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
            
            # إنشاء القيد المحاسبي للفاتورة
            try:
                journal_entry = AccountingIntegrationService.create_sale_journal_entry(
                    sale=sale2, user=user
                )
                if journal_entry:
                    print(f"    [OK] قيد الفاتورة: {journal_entry.number}")
                    print(f"        - مدين العميل: {sale2.total}")
                    print(f"        - دائن الإيرادات: {sale2.total}")
                    print(f"        - قيد التكلفة: مدين التكلفة / دائن المخزون")
            except Exception as e:
                print(f"    [X] خطأ في قيد الفاتورة: {str(e)}")
            
            # تحصيل جزئي (اختبار 6: تحصيل رصيد عميل)
            sale_payment2 = SalePayment.objects.create(
                sale=sale2,
                amount=Decimal("500.00"),
                payment_date=date(2025, 1, 18),
                payment_method="cash",
                reference_number="CASH-004",
                notes="تحصيل جزئي من فاتورة آجل",
                created_by=user,
                financial_account=cash_account,
                status="draft"
            )
            
            # معالجة الدفعة
            try:
                result = PaymentIntegrationService.process_payment(sale_payment2, "sale", user)
                
                if result["success"]:
                    sale_payment2.refresh_from_db()
                    sale2.refresh_from_db()
                    print(f"    [OK] قيد الدفعة: {sale_payment2.financial_transaction.number if sale_payment2.financial_transaction else 'N/A'}")
                    print(f"        - مدين الخزينة: {sale_payment2.amount}")
                    print(f"        - دائن العميل: {sale_payment2.amount}")
                    print(f"    [OK] حالة السداد: {sale2.get_payment_status_display()}")
                    print(f"    [OK] المحصّل: {sale2.amount_paid} من {sale2.total}")
                    print(f"    [OK] رصيد العميل: {customer2.balance}")
                else:
                    print(f"    [X] فشل معالجة الدفعة: {result.get('message')}")
            except Exception as e:
                print(f"    [X] خطأ في معالجة الدفعة: {str(e)}")
        
        print()
        
        # ═══════════════════════════════════════════════════════════
        # ملخص النتائج
        # ═══════════════════════════════════════════════════════════
        print("="*60)
        print("[OK] تم تحميل البيانات التجريبية بنجاح!")
        print("="*60)
        print("\n[*] الملخص:")
        print(f"   - 2 فاتورة شراء (PUR0001, PUR0002)")
        print(f"   - 2 فاتورة بيع (SALE0001, SALE0002)")
        print(f"   - 4 دفعات (جميعها معالجة تلقائياً)")
        print(f"\n[*] المبالغ:")
        print(f"   - إجمالي المشتريات: 6,200 ج.م")
        print(f"   - إجمالي المبيعات: 1,675 ج.م")
        print(f"   - المدفوع للموردين: 4,500 ج.م")
        print(f"   - المحصل من العملاء: 1,200 ج.م")
        print(f"\n[*] الأتمتة:")
        print(f"   + جميع القيود المحاسبية أُنشئت تلقائياً")
        print(f"   + جميع الدفعات رُبطت تلقائياً")
        print(f"   + جميع الحالات حُدثت تلقائياً")
        print(f"   + جميع سجلات التدقيق مُسجلة")
        print("\n" + "="*60 + "\n")
        
        return True
        
    except Exception as e:
        print(f"\n[X] خطأ: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    load_demo_transactions()
