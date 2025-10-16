from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.translation import gettext as _
from django.contrib.auth import get_user_model

# استيراد النماذج
from client.models import Customer, CustomerPayment
from supplier.models import Supplier
from product.models import (
    Product,
    ProductImage,
    ProductVariant,
    Stock,
    StockMovement,
    SerialNumber,
)
from sale.models import Sale, SaleItem, SalePayment, SaleReturn, SaleReturnItem
from purchase.models import (
    Purchase,
    PurchaseItem,
    PurchasePayment,
    PurchaseReturn,
    PurchaseReturnItem,
)

# استيراد آمن للنماذج المالية
try:
    from financial.models import (
        JournalEntry,
        JournalEntryLine,
        AccountingPeriod,
        BalanceSnapshot,
        AccountBalanceCache,
        BalanceAuditLog,
        BalanceReconciliation,
        PaymentSyncOperation,
        PaymentSyncLog,
        PaymentSyncError,
        BankReconciliation,
        BankReconciliationItem,
        CategoryBudget,
    )
except ImportError as e:
    print(f"تحذير: لا يمكن استيراد بعض النماذج المالية: {e}")
    # تعريف نماذج فارغة كبديل
    class DummyModel:
        @classmethod
        def objects(cls):
            return cls

        @classmethod
        def all(cls):
            return cls

        @classmethod
        def delete(cls):
            return (0, {})

        @classmethod
        def count(cls):
            return 0

    JournalEntry = JournalEntryLine = AccountingPeriod = DummyModel
    BalanceSnapshot = (
        AccountBalanceCache
    ) = BalanceAuditLog = BalanceReconciliation = DummyModel
    PaymentSyncOperation = PaymentSyncLog = PaymentSyncError = DummyModel
    BankReconciliation = BankReconciliationItem = CategoryBudget = DummyModel

User = get_user_model()


class Command(BaseCommand):
    help = "حذف جميع البيانات التشغيلية مع الحفاظ على البيانات الأساسية للنظام"

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="تأكيد حذف البيانات (مطلوب لتنفيذ الأمر)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="عرض ما سيتم حذفه دون تنفيذ الحذف الفعلي",
        )

    def handle(self, *args, **options):
        if not options["confirm"] and not options["dry_run"]:
            self.stdout.write(
                self.style.ERROR(
                    "يجب استخدام --confirm لتأكيد الحذف أو --dry-run لمعاينة العملية"
                )
            )
            return

        if options["dry_run"]:
            self.stdout.write(
                self.style.WARNING("وضع المعاينة - لن يتم حذف أي بيانات فعلياً")
            )
            self.preview_deletion()
        else:
            self.stdout.write(
                self.style.WARNING("تحذير: سيتم حذف جميع البيانات التشغيلية نهائياً!")
            )
            response = input('هل أنت متأكد؟ اكتب "نعم" للمتابعة: ')
            if response.lower() in ["نعم", "yes", "y"]:
                self.clear_operational_data()
            else:
                self.stdout.write(self.style.SUCCESS("تم إلغاء العملية"))

    def preview_deletion(self):
        """معاينة البيانات التي سيتم حذفها"""
        self.stdout.write(
            self.style.HTTP_INFO("\n=== معاينة البيانات المراد حذفها ===\n")
        )

        # عد البيانات
        counts = self.get_data_counts()

        self.stdout.write(self.style.HTTP_INFO("البيانات التشغيلية:"))
        for model_name, count in counts["operational"].items():
            if count > 0:
                self.stdout.write(f"  - {model_name}: {count} سجل")

        self.stdout.write(self.style.HTTP_INFO("\nالبيانات الأساسية (ستبقى):"))
        for model_name, count in counts["preserved"].items():
            if count > 0:
                self.stdout.write(f"  - {model_name}: {count} سجل")

    def get_data_counts(self):
        """حساب عدد السجلات في كل نموذج"""
        from product.models import Category, Brand, Unit

        operational_counts = {
            "العملاء": Customer.objects.count(),
            "مدفوعات العملاء": CustomerPayment.objects.count(),
            "الموردين": Supplier.objects.count(),
            "المنتجات": Product.objects.count(),
            "صور المنتجات": ProductImage.objects.count(),
            "متغيرات المنتجات": ProductVariant.objects.count(),
            "تصنيفات المنتجات": Category.objects.count(),
            "الأنواع": Brand.objects.count(),
            "وحدات القياس": Unit.objects.count(),
            "المخزون": Stock.objects.count(),
            "حركات المخزون": StockMovement.objects.count(),
            "فواتير المبيعات": Sale.objects.count(),
            "بنود المبيعات": SaleItem.objects.count(),
            "مدفوعات المبيعات": SalePayment.objects.count(),
            "مرتجعات المبيعات": SaleReturn.objects.count(),
            "بنود مرتجعات المبيعات": SaleReturnItem.objects.count(),
            "فواتير المشتريات": Purchase.objects.count(),
            "بنود المشتريات": PurchaseItem.objects.count(),
            "مدفوعات المشتريات": PurchasePayment.objects.count(),
            "مرتجعات المشتريات": PurchaseReturn.objects.count(),
            "بنود مرتجعات المشتريات": PurchaseReturnItem.objects.count(),
            "القيود المحاسبية": JournalEntry.objects.count(),
            "بنود القيود": JournalEntryLine.objects.count(),
            "لقطات الأرصدة": BalanceSnapshot.objects.count(),
            "ذاكرة تخزين الأرصدة": AccountBalanceCache.objects.count(),
            "سجل مراجعة الأرصدة": BalanceAuditLog.objects.count(),
            "تسوية الأرصدة": BalanceReconciliation.objects.count(),
            "عمليات تزامن المدفوعات": PaymentSyncOperation.objects.count(),
            "سجل تزامن المدفوعات": PaymentSyncLog.objects.count(),
            "أخطاء تزامن المدفوعات": PaymentSyncError.objects.count(),
            "التسوية البنكية": BankReconciliation.objects.count(),
            "بنود التسوية البنكية": BankReconciliationItem.objects.count(),
            "ميزانيات التصنيفات": CategoryBudget.objects.count(),
            "الأرقام التسلسلية": SerialNumber.objects.count(),
        }

        # استيراد النماذج الأساسية
        from product.models import Warehouse
        from financial.models import AccountType, ChartOfAccounts, AccountGroup
        from financial.models import JournalEntryTemplate, JournalEntryTemplateLine
        from financial.models import PaymentSyncRule
        from users.models import User
        from core.models import SystemSetting, Notification

        # استيراد آمن للنماذج الاختيارية
        try:
            from financial.models import FinancialCategory

            financial_categories_count = FinancialCategory.objects.count()
        except ImportError:
            financial_categories_count = 0

        preserved_counts = {
            "المخازن": Warehouse.objects.count(),
            "أنواع الحسابات": AccountType.objects.count(),
            "دليل الحسابات": ChartOfAccounts.objects.count(),
            "مجموعات الحسابات": AccountGroup.objects.count(),
            "التصنيفات المالية": financial_categories_count,
            "الفترات المحاسبية": AccountingPeriod.objects.count(),
            "قوالب القيود": JournalEntryTemplate.objects.count(),
            "بنود قوالب القيود": JournalEntryTemplateLine.objects.count(),
            "قواعد تزامن المدفوعات": PaymentSyncRule.objects.count(),
            "المستخدمين": User.objects.count(),
            "إعدادات النظام": SystemSetting.objects.count(),
            "الإشعارات": Notification.objects.count(),
        }

        return {"operational": operational_counts, "preserved": preserved_counts}

    def clear_operational_data(self):
        """حذف البيانات التشغيلية"""
        self.stdout.write(
            self.style.HTTP_INFO("\n=== بدء عملية حذف البيانات التشغيلية ===\n")
        )

        try:
            with transaction.atomic():
                # حذف البيانات بالترتيب الصحيح لتجنب مشاكل المفاتيح الخارجية

                # 1. حذف البيانات المالية أولاً
                self.stdout.write("حذف البيانات المالية...")
                self.delete_financial_data()

                # 2. حذف بيانات المبيعات والمشتريات
                self.stdout.write("حذف بيانات المبيعات والمشتريات...")
                self.delete_sales_purchase_data()

                # 3. حذف بيانات المخزون
                self.stdout.write("حذف بيانات المخزون...")
                self.delete_inventory_data()

                # 4. حذف بيانات المنتجات
                self.stdout.write("حذف بيانات المنتجات...")
                self.delete_product_data()

                # 5. حذف بيانات العملاء والموردين
                self.stdout.write("حذف بيانات العملاء والموردين...")
                self.delete_client_supplier_data()

                # 6. إعادة تعيين الأرصدة الافتتاحية للحسابات
                self.stdout.write("إعادة تعيين الأرصدة الافتتاحية...")
                self.reset_account_balances()

                # 7. حذف الأرقام التسلسلية
                self.stdout.write("حذف الأرقام التسلسلية...")
                SerialNumber.objects.all().delete()

                self.stdout.write(
                    self.style.SUCCESS("\n✅ تم حذف جميع البيانات التشغيلية بنجاح!")
                )

                # عرض ملخص البيانات المتبقية
                self.show_remaining_data()

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"❌ حدث خطأ أثناء حذف البيانات: {str(e)}")
            )
            raise

    def delete_financial_data(self):
        """حذف البيانات المالية التشغيلية"""
        # حذف بنود القيود أولاً
        deleted_lines = JournalEntryLine.objects.all().delete()[0]
        self.stdout.write(f"  - تم حذف {deleted_lines} بند قيد")

        # حذف القيود المحاسبية
        deleted_entries = JournalEntry.objects.all().delete()[0]
        self.stdout.write(f"  - تم حذف {deleted_entries} قيد محاسبي")

        # ملاحظة: الفترات المحاسبية لن يتم حذفها (حسب الطلب)
        self.stdout.write("  - تم الاحتفاظ بالفترات المحاسبية")

        # حذف بيانات الأرصدة
        BalanceSnapshot.objects.all().delete()
        AccountBalanceCache.objects.all().delete()
        BalanceAuditLog.objects.all().delete()
        BalanceReconciliation.objects.all().delete()

        # حذف بيانات تزامن المدفوعات
        PaymentSyncOperation.objects.all().delete()
        PaymentSyncLog.objects.all().delete()
        PaymentSyncError.objects.all().delete()

        # حذف بيانات التسوية البنكية
        BankReconciliationItem.objects.all().delete()
        BankReconciliation.objects.all().delete()

        # حذف ميزانيات التصنيفات
        deleted_budgets = CategoryBudget.objects.all().delete()[0]
        self.stdout.write(f"  - تم حذف {deleted_budgets} ميزان فئة")

        self.stdout.write("  ✅ تم حذف البيانات المالية")

    def delete_sales_purchase_data(self):
        """حذف بيانات المبيعات والمشتريات"""
        # حذف مرتجعات المبيعات
        SaleReturnItem.objects.all().delete()
        SaleReturn.objects.all().delete()

        # حذف مدفوعات المبيعات
        SalePayment.objects.all().delete()

        # حذف بنود المبيعات
        SaleItem.objects.all().delete()

        # حذف فواتير المبيعات
        deleted_sales = Sale.objects.all().delete()[0]
        self.stdout.write(f"  - تم حذف {deleted_sales} فاتورة مبيعات")

        # حذف مرتجعات المشتريات
        PurchaseReturnItem.objects.all().delete()
        PurchaseReturn.objects.all().delete()

        # حذف مدفوعات المشتريات
        PurchasePayment.objects.all().delete()

        # حذف بنود المشتريات
        PurchaseItem.objects.all().delete()

        # حذف فواتير المشتريات
        deleted_purchases = Purchase.objects.all().delete()[0]
        self.stdout.write(f"  - تم حذف {deleted_purchases} فاتورة مشتريات")


        self.stdout.write("  ✅ تم حذف بيانات المبيعات والمشتريات")

    def delete_inventory_data(self):
        """حذف بيانات المخزون"""
        # حذف حركات المخزون
        deleted_movements = StockMovement.objects.all().delete()[0]
        self.stdout.write(f"  - تم حذف {deleted_movements} حركة مخزون")

        # حذف أرصدة المخزون
        deleted_stock = Stock.objects.all().delete()[0]
        self.stdout.write(f"  - تم حذف {deleted_stock} رصيد مخزون")

        self.stdout.write("  ✅ تم حذف بيانات المخزون")

    def delete_product_data(self):
        """حذف بيانات المنتجات"""
        from product.models import Category, Brand, Unit

        # حذف متغيرات المنتجات
        ProductVariant.objects.all().delete()

        # حذف صور المنتجات
        ProductImage.objects.all().delete()

        # حذف المنتجات
        deleted_products = Product.objects.all().delete()[0]
        self.stdout.write(f"  - تم حذف {deleted_products} منتج")

        # حذف تصنيفات المنتجات
        deleted_categories = Category.objects.all().delete()[0]
        self.stdout.write(f"  - تم حذف {deleted_categories} فئة منتج")

        # حذف الأنواع
        deleted_brands = Brand.objects.all().delete()[0]
        self.stdout.write(f"  - تم حذف {deleted_brands} علامة تجارية")

        # حذف وحدات القياس
        deleted_units = Unit.objects.all().delete()[0]
        self.stdout.write(f"  - تم حذف {deleted_units} وحدة قياس")

        self.stdout.write("  ✅ تم حذف بيانات المنتجات والإعدادات المرتبطة")

    def delete_client_supplier_data(self):
        """حذف بيانات العملاء والموردين"""
        # حذف مدفوعات العملاء
        CustomerPayment.objects.all().delete()

        # حذف العملاء
        deleted_customers = Customer.objects.all().delete()[0]
        self.stdout.write(f"  - تم حذف {deleted_customers} عميل")

        # حذف الموردين
        deleted_suppliers = Supplier.objects.all().delete()[0]
        self.stdout.write(f"  - تم حذف {deleted_suppliers} مورد")

        self.stdout.write("  ✅ تم حذف بيانات العملاء والموردين")

    def reset_account_balances(self):
        """إعادة تعيين الأرصدة الافتتاحية للحسابات إلى الصفر"""
        from financial.models import ChartOfAccounts

        # إعادة تعيين جميع الأرصدة الافتتاحية إلى الصفر
        updated_accounts = ChartOfAccounts.objects.update(
            opening_balance=0.00, opening_balance_date=None
        )

        self.stdout.write(f"  - تم إعادة تعيين أرصدة {updated_accounts} حساب")
        self.stdout.write("  ✅ تم إعادة تعيين الأرصدة الافتتاحية")

    def show_remaining_data(self):
        """عرض البيانات المتبقية بعد الحذف"""
        self.stdout.write(
            self.style.HTTP_INFO("\n=== البيانات الأساسية المتبقية ===\n")
        )

        counts = self.get_data_counts()

        for model_name, count in counts["preserved"].items():
            if count > 0:
                self.stdout.write(f"✅ {model_name}: {count} سجل")

        self.stdout.write(
            self.style.SUCCESS("\n🎉 تم الاحتفاظ بجميع البيانات الأساسية للنظام")
        )
        self.stdout.write(
            self.style.HTTP_INFO(
                "\nيمكنك الآن البدء بإدخال بيانات جديدة على نظام نظيف!"
            )
        )
