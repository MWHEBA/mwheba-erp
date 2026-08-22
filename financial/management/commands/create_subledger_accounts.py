# -*- coding: utf-8 -*-
"""
أمر إدارة موحد لإنشاء حسابات الأستاذ المساعد للعملاء والموردين
يربط الكيانات بشجرة الحسابات تحت حسابات المراقبة (11210 للعملاء و 21110 للموردين)
"""
from django.core.management.base import BaseCommand
from django.db import transaction
import logging

from financial.services.subledger_account_service import SubledgerAccountService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "إنشاء حسابات الأستاذ المساعد للعملاء والموردين الذين ليس لديهم حسابات محاسبية"

    def add_arguments(self, parser):
        parser.add_argument(
            "--type",
            type=str,
            choices=["suppliers", "customers", "all"],
            default="all",
            help="نوع الكيانات المراد معالجتها: suppliers أو customers أو all",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="تشغيل تجريبي دون حفظ أي تغييرات في قاعدة البيانات",
        )

    def handle(self, *args, **options):
        entity_type = options["type"]
        dry_run = options["dry_run"]

        self.stdout.write(self.style.NOTICE(f"بدء فحص ومعالجة حسابات الأستاذ المساعد (النوع: {entity_type}, تشغيل تجريبي: {dry_run})"))

        if entity_type in ["suppliers", "all"]:
            self.process_suppliers(dry_run)

        if entity_type in ["customers", "all"]:
            self.process_customers(dry_run)

        self.stdout.write(self.style.SUCCESS("[OK] اكتملت معالجة حسابات الأستاذ المساعد بنجاح."))

    def process_suppliers(self, dry_run: bool):
        from supplier.models import Supplier

        suppliers = Supplier.objects.filter(financial_account__isnull=True)
        total = suppliers.count()
        self.stdout.write(f"[INFO] تم العثور على {total} مورد بدون حساب محاسبي.")

        created_count = 0
        failed_count = 0

        for supplier in suppliers:
            if dry_run:
                self.stdout.write(f"  [DRY-RUN] سيتم إنشاء حساب للمورد: {supplier.name} ({supplier.code})")
                created_count += 1
                continue

            try:
                account = SubledgerAccountService.create_supplier_account(supplier)
                if account:
                    created_count += 1
                    self.stdout.write(self.style.SUCCESS(f"  [OK] تم إنشاء حساب للمورد: {supplier.name} -> {account.code}"))
                else:
                    failed_count += 1
                    self.stdout.write(self.style.ERROR(f"  [FAILED] فشل إنشاء حساب للمورد: {supplier.name}"))
            except Exception as e:
                failed_count += 1
                self.stdout.write(self.style.ERROR(f"  [ERROR] خطأ أثناء معالجة المورد {supplier.name}: {e}"))

        self.stdout.write(self.style.SUCCESS(f"ملخص الموردين: تم إنشاء {created_count}، فشل {failed_count} من إجمالي {total}."))

    def process_customers(self, dry_run: bool):
        from client.models import Customer

        customers = Customer.objects.filter(financial_account__isnull=True)
        total = customers.count()
        self.stdout.write(f"[INFO] تم العثور على {total} عميل بدون حساب محاسبي.")

        created_count = 0
        failed_count = 0

        for customer in customers:
            if dry_run:
                self.stdout.write(f"  [DRY-RUN] سيتم إنشاء حساب للعميل: {customer.name} ({customer.code})")
                created_count += 1
                continue

            try:
                account = SubledgerAccountService.create_customer_account(customer)
                if account:
                    created_count += 1
                    self.stdout.write(self.style.SUCCESS(f"  [OK] تم إنشاء حساب للعميل: {customer.name} -> {account.code}"))
                else:
                    failed_count += 1
                    self.stdout.write(self.style.ERROR(f"  [FAILED] فشل إنشاء حساب للعميل: {customer.name}"))
            except Exception as e:
                failed_count += 1
                self.stdout.write(self.style.ERROR(f"  [ERROR] خطأ أثناء معالجة العميل {customer.name}: {e}"))

        self.stdout.write(self.style.SUCCESS(f"ملخص العملاء: تم إنشاء {created_count}، فشل {failed_count} من إجمالي {total}."))
