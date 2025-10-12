"""
Management command لإنشاء حسابات محاسبية للموردين والعملاء الموجودين
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from supplier.models import Supplier
from client.models import Customer
from financial.services.supplier_customer_account_service import (
    SupplierCustomerAccountService,
)


class Command(BaseCommand):
    help = "إنشاء حسابات محاسبية للموردين والعملاء الموجودين"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="عرض ما سيحدث بدون تنفيذ فعلي",
        )
        parser.add_argument(
            "--suppliers-only",
            action="store_true",
            help="إنشاء حسابات للموردين فقط",
        )
        parser.add_argument(
            "--customers-only",
            action="store_true",
            help="إنشاء حسابات للعملاء فقط",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        suppliers_only = options["suppliers_only"]
        customers_only = options["customers_only"]

        if dry_run:
            self.stdout.write(
                self.style.WARNING("🔍 وضع المعاينة - لن يتم تنفيذ أي تغييرات")
            )

        # معالجة الموردين
        if not customers_only:
            self.process_suppliers(dry_run)

        # معالجة العملاء
        if not suppliers_only:
            self.process_customers(dry_run)

        self.stdout.write(self.style.SUCCESS("\n✅ اكتملت العملية بنجاح!"))

    def process_suppliers(self, dry_run):
        """معالجة الموردين"""
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.HTTP_INFO("📦 معالجة الموردين"))
        self.stdout.write("=" * 60)

        suppliers = Supplier.objects.filter(financial_account__isnull=True)
        total = suppliers.count()

        self.stdout.write(f"\n📊 عدد الموردين بدون حسابات: {total}")

        if total == 0:
            self.stdout.write(
                self.style.SUCCESS("✅ جميع الموردين لديهم حسابات محاسبية")
            )
            return

        success_count = 0
        error_count = 0

        for supplier in suppliers:
            try:
                if not dry_run:
                    with transaction.atomic():
                        account = (
                            SupplierCustomerAccountService.create_supplier_account(
                                supplier
                            )
                        )
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"✅ {supplier.name} → {account.code} - {account.name}"
                            )
                        )
                        success_count += 1
                else:
                    self.stdout.write(
                        f"📋 سيتم إنشاء حساب للمورد: {supplier.name} (كود: {supplier.code})"
                    )
                    success_count += 1
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"❌ خطأ في المورد {supplier.name}: {str(e)}")
                )
                error_count += 1

        self.stdout.write("\n" + "-" * 60)
        self.stdout.write(f"✅ نجح: {success_count}")
        self.stdout.write(f"❌ فشل: {error_count}")
        self.stdout.write("-" * 60)

    def process_customers(self, dry_run):
        """معالجة العملاء"""
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.HTTP_INFO("👥 معالجة العملاء"))
        self.stdout.write("=" * 60)

        customers = Customer.objects.filter(financial_account__isnull=True)
        total = customers.count()

        self.stdout.write(f"\n📊 عدد العملاء بدون حسابات: {total}")

        if total == 0:
            self.stdout.write(self.style.SUCCESS("✅ جميع العملاء لديهم حسابات محاسبية"))
            return

        success_count = 0
        error_count = 0

        for customer in customers:
            try:
                if not dry_run:
                    with transaction.atomic():
                        account = (
                            SupplierCustomerAccountService.create_customer_account(
                                customer
                            )
                        )
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"✅ {customer.name} → {account.code} - {account.name}"
                            )
                        )
                        success_count += 1
                else:
                    self.stdout.write(
                        f"📋 سيتم إنشاء حساب للعميل: {customer.name} (كود: {customer.code})"
                    )
                    success_count += 1
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"❌ خطأ في العميل {customer.name}: {str(e)}")
                )
                error_count += 1

        self.stdout.write("\n" + "-" * 60)
        self.stdout.write(f"✅ نجح: {success_count}")
        self.stdout.write(f"❌ فشل: {error_count}")
        self.stdout.write("-" * 60)
