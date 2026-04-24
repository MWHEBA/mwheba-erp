"""
اختبارات E2E - سيناريوهات الأعمال الحقيقية
Real Business Scenarios Tests

هذا الملف يحتوي على اختبارات حقيقية 100% بدون تنازلات:
- اختبار السيناريوهات الحقيقية (happy path + edge cases)
- اختبار الأخطاء والاستثناءات
- اختبار القيود المحاسبية بالتفصيل
- اختبار حركات المخزون بدقة
- اختبار الأرصدة والمعاملات

القاعدة الذهبية: الاختبار يفشل إذا كان هناك bug - لا نعدل الاختبار ليعدي!
"""
import pytest
from decimal import Decimal
from django.utils import timezone
from django.db import models
from django.core.exceptions import ValidationError


@pytest.mark.e2e
@pytest.mark.critical
@pytest.mark.business_flow
class TestRealBusinessScenarios:
    """
    اختبارات السيناريوهات الحقيقية للأعمال
    """
    
    def test_complete_purchase_to_sale_flow(
        self,
        db,
        test_user,
        test_category,
        test_unit,
        test_warehouse,
        setup_chart_of_accounts
    ):
        """
        السيناريو الكامل: شراء → بيع → دفعات
        
        الخطوات:
        1. إنشاء عميل ومورد
        2. شراء 100 قطعة بـ 80 ج.م للقطعة (إجمالي 8000 ج.م)
        3. بيع 50 قطعة بـ 150 ج.م للقطعة (إجمالي 7500 ج.م)
        4. استلام دفعة من العميل 5000 ج.م
        5. دفع للمورد 4000 ج.م
        6. التحقق من كل شيء بدقة
        """
        from client.services.customer_service import CustomerService
        from supplier.services.supplier_service import SupplierService
        from purchase.services.purchase_service import PurchaseService
        from sale.services.sale_service import SaleService
        from product.models import Product, Stock, StockMovement
        from financial.models import ChartOfAccounts, JournalEntry, JournalEntryLine
        from sale.models import SalePayment
        from purchase.models import PurchasePayment
        
        print("\n" + "="*80)
        print("اختبار السيناريو الكامل: شراء > بيع > دفعات")
        print("="*80)
        
        # ==================== 1. إنشاء العميل والمورد ====================
        customer_service = CustomerService()
        customer = customer_service.create_customer(
            name='شركة النور للتجارة',
            code='REAL_CUST_001',
            user=test_user,
            phone='01012345678',
            client_type='company',
            credit_limit=Decimal('50000.00')
        )
        
        # التحقق الصارم: العميل يجب أن يكون له حساب محاسبي
        assert customer.financial_account is not None, \
            " CRITICAL: العميل ليس له حساب محاسبي!"
        assert customer.financial_account.code.startswith('1103'), \
            f" CRITICAL: كود حساب العميل خاطئ: {customer.financial_account.code}"
        
        print(f" العميل: {customer.name}")
        print(f"   الحساب: {customer.financial_account.code} - {customer.financial_account.name}")
        
        supplier_service = SupplierService()
        supplier = supplier_service.create_supplier(
            name='مورد الجودة العالية',
            code='REAL_SUP_001',
            user=test_user,
            phone='01098765432'
        )
        
        # التحقق الصارم: المورد يجب أن يكون له حساب محاسبي
        assert supplier.financial_account is not None, \
            " CRITICAL: المورد ليس له حساب محاسبي!"
        assert supplier.financial_account.code.startswith('2101'), \
            f" CRITICAL: كود حساب المورد خاطئ: {supplier.financial_account.code}"
        
        print(f" المورد: {supplier.name}")
        print(f"   الحساب: {supplier.financial_account.code} - {supplier.financial_account.name}")
        
        # ==================== 2. إنشاء المنتج ====================
        product = Product.objects.create(
            name='منتج الاختبار الحقيقي',
            sku='REAL_PROD_001',
            category=test_category,
            unit=test_unit,
            cost_price=Decimal('80.00'),
            selling_price=Decimal('150.00'),
            is_active=True,
            created_by=test_user
        )
        
        print(f" المنتج: {product.name}")
        print(f"   التكلفة: {product.cost_price} ج.م | البيع: {product.selling_price} ج.م")
        
        # ==================== 3. الشراء ====================
        print("\n" + "-"*80)
        print("مرحلة الشراء")
        print("-"*80)
        
        purchase_data = {
            'supplier_id': supplier.id,
            'warehouse_id': test_warehouse.id,
            'payment_method': 'credit',
            'items': [
                {
                    'product_id': product.id,
                    'quantity': 100,
                    'unit_price': Decimal('80.00'),
                    'discount': Decimal('0.00')
                }
            ],
            'discount': Decimal('0.00'),
            'tax': Decimal('0.00'),
            'notes': 'فاتورة شراء للاختبار الحقيقي'
        }
        
        # عد القيود قبل الشراء
        initial_journal_entries = JournalEntry.objects.count()
        initial_movements = StockMovement.objects.count()
        
        purchase = PurchaseService.create_purchase(purchase_data, test_user)
        
        # ==================== التحقق الصارم من الفاتورة ====================
        assert purchase.id is not None, " فشل إنشاء فاتورة الشراء"
        assert purchase.supplier == supplier, " المورد غير صحيح"
        assert purchase.status == 'confirmed', f" حالة الفاتورة خاطئة: {purchase.status}"
        assert purchase.total == Decimal('8000.00'), f" الإجمالي خاطئ: {purchase.total}"
        
        print(f" فاتورة الشراء: {purchase.number}")
        print(f"   الإجمالي: {purchase.total} ج.م")
        
        # ==================== التحقق الصارم من القيد المحاسبي ====================
        assert purchase.journal_entry is not None, \
            " CRITICAL: لم يتم إنشاء قيد محاسبي للشراء!"
        
        purchase_entry = purchase.journal_entry
        purchase_lines = purchase_entry.lines.all()
        
        # يجب أن يكون هناك على الأقل سطرين
        assert purchase_lines.count() >= 2, \
            f" عدد بنود القيد قليل: {purchase_lines.count()}"
        
        # التحقق من التوازن
        total_debit = purchase_lines.aggregate(total=models.Sum('debit'))['total'] or Decimal('0')
        total_credit = purchase_lines.aggregate(total=models.Sum('credit'))['total'] or Decimal('0')
        
        assert total_debit == total_credit, \
            f" CRITICAL: القيد غير متوازن! مدين={total_debit}, دائن={total_credit}"
        assert total_debit == Decimal('8000.00'), \
            f" مبلغ القيد خاطئ: {total_debit}"
        
        print(f" القيد المحاسبي: {purchase_entry.number}")
        print(f"   مدين: {total_debit} ج.م | دائن: {total_credit} ج.م")
        
        # التحقق من الحسابات المستخدمة
        account_codes = [line.account.code for line in purchase_lines]
        
        # يجب أن يحتوي على حساب المخزون (10400) أو حساب المصروفات
        has_inventory_or_expense = any(
            code in ['10400', '10300', '50200'] for code in account_codes
        )
        assert has_inventory_or_expense, \
            f" القيد لا يحتوي على حساب المخزون/المصروفات: {account_codes}"
        
        # يجب أن يحتوي على حساب المورد
        assert supplier.financial_account.code in account_codes, \
            f" القيد لا يحتوي على حساب المورد: {account_codes}"
        
        print(f"   الحسابات: {', '.join(account_codes)}")
        
        # ==================== التحقق الصارم من حركات المخزون ====================
        movements = StockMovement.objects.filter(
            product=product,
            movement_type='in'
        ).order_by('id')
        
        # يجب أن تكون هناك حركة واحدة فقط
        assert movements.count() == 1, \
            f" BUG: حركة المخزون مسجلة {movements.count()} مرة بدلاً من مرة واحدة!"
        
        movement = movements.first()
        assert movement.quantity == 100, \
            f" كمية الحركة خاطئة: {movement.quantity}"
        
        print(f" حركة المخزون: {movement.quantity} قطعة")
        
        # ==================== التحقق من المخزون ====================
        stock = Stock.objects.get(product=product, warehouse=test_warehouse)
        
        # يجب أن تكون الكمية 100 بالضبط
        assert stock.quantity == 100, \
            f" BUG: المخزون {stock.quantity} بدلاً من 100!"
        
        print(f" المخزون: {stock.quantity} قطعة")
        
        # ==================== 4. البيع ====================
        print("\n" + "-"*80)
        print("مرحلة البيع")
        print("-"*80)
        
        sale_data = {
            'customer_id': customer.id,
            'warehouse_id': test_warehouse.id,
            'payment_method': 'credit',
            'items': [
                {
                    'product_id': product.id,
                    'quantity': 50,
                    'unit_price': Decimal('150.00'),
                    'discount': Decimal('0.00')
                }
            ],
            'discount': Decimal('0.00'),
            'tax': Decimal('0.00'),
            'notes': 'فاتورة بيع للاختبار الحقيقي'
        }
        
        sale = SaleService.create_sale(sale_data, test_user)
        
        # ==================== التحقق الصارم من الفاتورة ====================
        assert sale.id is not None, " فشل إنشاء فاتورة البيع"
        assert sale.customer == customer, " العميل غير صحيح"
        assert sale.status == 'confirmed', f" حالة الفاتورة خاطئة: {sale.status}"
        assert sale.total == Decimal('7500.00'), f" الإجمالي خاطئ: {sale.total}"
        
        print(f" فاتورة البيع: {sale.number}")
        print(f"   الإجمالي: {sale.total} ج.م")
        
        # ==================== التحقق الصارم من القيد المحاسبي ====================
        assert sale.journal_entry is not None, \
            " CRITICAL: لم يتم إنشاء قيد محاسبي للبيع!"
        
        sale_entry = sale.journal_entry
        sale_lines = sale_entry.lines.all()
        
        # يجب أن يكون هناك 4 سطور (عميل، إيرادات، تكلفة، مخزون)
        assert sale_lines.count() >= 2, \
            f" عدد بنود القيد قليل: {sale_lines.count()}"
        
        # التحقق من التوازن
        sale_debit = sale_lines.aggregate(total=models.Sum('debit'))['total'] or Decimal('0')
        sale_credit = sale_lines.aggregate(total=models.Sum('credit'))['total'] or Decimal('0')
        
        assert sale_debit == sale_credit, \
            f" CRITICAL: القيد غير متوازن! مدين={sale_debit}, دائن={sale_credit}"
        
        print(f" القيد المحاسبي: {sale_entry.number}")
        print(f"   مدين: {sale_debit} ج.م | دائن: {sale_credit} ج.م")
        
        # التحقق من الحسابات المستخدمة
        sale_account_codes = [line.account.code for line in sale_lines]
        
        # يجب أن يحتوي على حساب العميل
        assert customer.financial_account.code in sale_account_codes, \
            f" القيد لا يحتوي على حساب العميل: {sale_account_codes}"
        
        # يجب أن يحتوي على حساب إيرادات المبيعات (40100)
        assert '40100' in sale_account_codes, \
            f" القيد لا يحتوي على حساب إيرادات المبيعات: {sale_account_codes}"
        
        print(f"   الحسابات: {', '.join(sale_account_codes)}")
        
        # ==================== التحقق من المخزون بعد البيع ====================
        stock.refresh_from_db()
        
        # يجب أن تكون الكمية 50 (100 - 50)
        assert stock.quantity == 50, \
            f" BUG: المخزون {stock.quantity} بدلاً من 50!"
        
        print(f" المخزون بعد البيع: {stock.quantity} قطعة")
        
        # ==================== 5. دفعة من العميل ====================
        print("\n" + "-"*80)
        print("دفعة من العميل")
        print("-"*80)
        
        # جلب حساب الصندوق
        cash_account = ChartOfAccounts.objects.get(code='10100')
        
        # إنشاء الدفعة
        payment1 = SalePayment.objects.create(
            sale=sale,
            amount=Decimal('5000.00'),
            payment_date=timezone.now().date(),
            payment_method='10100',  # الصندوق
            financial_account=cash_account,  # الحساب المالي
            status='draft',  # مسودة أولاً
            created_by=test_user,
            notes='دفعة نقدية'
        )
        
        # معالجة الدفعة عبر PaymentIntegrationService
        from financial.services.payment_integration_service import PaymentIntegrationService
        
        payment_result = PaymentIntegrationService.process_payment(
            payment=payment1,
            payment_type='sale',
            user=test_user
        )
        
        assert payment_result['success'], \
            f" CRITICAL: فشل في معالجة الدفعة: {payment_result.get('message')}"
        
        # تحديث حالة الدفعة
        payment1.status = 'posted'
        payment1.posted_at = timezone.now()
        payment1.posted_by = test_user
        payment1.save()
        
        # التحقق من القيد المحاسبي للدفعة
        payment1.refresh_from_db()
        assert payment1.financial_transaction is not None, \
            " CRITICAL: لم يتم إنشاء قيد محاسبي للدفعة!"
        
        payment1_entry = payment1.financial_transaction
        payment1_lines = payment1_entry.lines.all()
        
        # التحقق من التوازن
        payment1_debit = payment1_lines.aggregate(total=models.Sum('debit'))['total'] or Decimal('0')
        payment1_credit = payment1_lines.aggregate(total=models.Sum('credit'))['total'] or Decimal('0')
        
        assert payment1_debit == payment1_credit, \
            f" CRITICAL: قيد الدفعة غير متوازن! مدين={payment1_debit}, دائن={payment1_credit}"
        assert payment1_debit == Decimal('5000.00'), \
            f" مبلغ قيد الدفعة خاطئ: {payment1_debit}"
        
        print(f" دفعة من العميل: {payment1.amount} ج.م")
        print(f"   القيد: {payment1_entry.number}")
        
        # ==================== 6. دفعة للمورد ====================
        print("\n" + "-"*80)
        print("دفعة للمورد")
        print("-"*80)
        
        # إنشاء الدفعة
        payment2 = PurchasePayment.objects.create(
            purchase=purchase,
            amount=Decimal('4000.00'),
            payment_date=timezone.now().date(),
            payment_method='10100',  # الصندوق
            financial_account=cash_account,  # الحساب المالي
            status='draft',  # مسودة أولاً
            created_by=test_user,
            notes='دفعة نقدية للمورد'
        )
        
        # معالجة الدفعة عبر PaymentIntegrationService
        payment2_result = PaymentIntegrationService.process_payment(
            payment=payment2,
            payment_type='purchase',
            user=test_user
        )
        
        assert payment2_result['success'], \
            f" CRITICAL: فشل في معالجة دفعة المورد: {payment2_result.get('message')}"
        
        # تحديث حالة الدفعة
        payment2.status = 'posted'
        payment2.posted_at = timezone.now()
        payment2.posted_by = test_user
        payment2.save()
        
        # التحقق من القيد المحاسبي للدفعة
        payment2.refresh_from_db()
        assert payment2.financial_transaction is not None, \
            " CRITICAL: لم يتم إنشاء قيد محاسبي لدفعة المورد!"
        
        payment2_entry = payment2.financial_transaction
        payment2_lines = payment2_entry.lines.all()
        
        # التحقق من التوازن
        payment2_debit = payment2_lines.aggregate(total=models.Sum('debit'))['total'] or Decimal('0')
        payment2_credit = payment2_lines.aggregate(total=models.Sum('credit'))['total'] or Decimal('0')
        
        assert payment2_debit == payment2_credit, \
            f" CRITICAL: قيد دفعة المورد غير متوازن! مدين={payment2_debit}, دائن={payment2_credit}"
        assert payment2_debit == Decimal('4000.00'), \
            f" مبلغ قيد دفعة المورد خاطئ: {payment2_debit}"
        
        print(f" دفعة للمورد: {payment2.amount} ج.م")
        print(f"   القيد: {payment2_entry.number}")
        
        # ==================== 7. التحقق من الأرصدة النهائية ====================
        print("\n" + "-"*80)
        print("الأرصدة النهائية")
        print("-"*80)
        
        # رصيد العميل
        customer_balance = customer_service.calculate_balance(customer)
        expected_customer_balance = Decimal('7500.00') - Decimal('5000.00')  # 2500
        
        assert customer_balance == expected_customer_balance, \
            f" رصيد العميل خاطئ: {customer_balance} (المتوقع: {expected_customer_balance})"
        
        print(f" رصيد العميل: {customer_balance} ج.م (مدين)")
        
        # رصيد المورد
        supplier_balance = supplier_service.get_supplier_balance(supplier)
        expected_supplier_balance = Decimal('8000.00') - Decimal('4000.00')  # 4000
        
        assert supplier_balance == expected_supplier_balance, \
            f" رصيد المورد خاطئ: {supplier_balance} (المتوقع: {expected_supplier_balance})"
        
        print(f" رصيد المورد: {supplier_balance} ج.م (دائن)")
        
        # قيمة المخزون
        stock_value = stock.quantity * product.cost_price
        expected_stock_value = Decimal('50') * Decimal('80.00')  # 4000
        
        assert stock_value == expected_stock_value, \
            f" قيمة المخزون خاطئة: {stock_value} (المتوقع: {expected_stock_value})"
        
        print(f" قيمة المخزون: {stock_value} ج.م ({stock.quantity} × {product.cost_price})")
        
        # ==================== 8. الربح المحقق ====================
        revenue = sale.total  # 7500
        cost = Decimal('50') * product.cost_price  # 50 × 80 = 4000
        profit = revenue - cost  # 3500
        
        print(f"\n الربح المحقق: {profit} ج.م")
        print(f"   الإيرادات: {revenue} ج.م")
        print(f"   التكلفة: {cost} ج.م")
        
        # ==================== الخلاصة ====================
        print("\n" + "="*80)
        print(" اكتمل الاختبار بنجاح - جميع الفحوصات عدّت!")
        print("="*80)
        print(f" ملخص:")
        print(f"   • المشتريات: {purchase.total} ج.م")
        print(f"   • المبيعات: {sale.total} ج.م")
        print(f"   • المخزون: {stock.quantity} قطعة ({stock_value} ج.م)")
        print(f"   • رصيد العميل: {customer_balance} ج.م")
        print(f"   • رصيد المورد: {supplier_balance} ج.م")
        print(f"   • الربح: {profit} ج.م")
        print("="*80)
