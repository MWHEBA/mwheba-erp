"""
أمر Django لتفعيل نظام تزامن المدفوعات
يقوم بإنشاء قواعد التزامن وربط signals المدفوعات
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.contenttypes.models import ContentType
import logging

from financial.models.payment_sync import PaymentSyncRule
from sale.models import SalePayment
from purchase.models import PurchasePayment

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "تفعيل نظام تزامن المدفوعات مع إنشاء القواعد الأساسية"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="إعادة إنشاء القواعد حتى لو كانت موجودة",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("🔄 بدء تفعيل نظام تزامن المدفوعات..."))

        try:
            with transaction.atomic():
                # 1. إنشاء قواعد تزامن المبيعات
                self.create_sale_payment_sync_rules(options["force"])

                # 2. إنشاء قواعد تزامن المشتريات
                self.create_purchase_payment_sync_rules(options["force"])

                # 3. التحقق من النظام
                self.verify_sync_system()

                self.stdout.write(
                    self.style.SUCCESS("✅ تم تفعيل نظام تزامن المدفوعات بنجاح!")
                )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"❌ خطأ في تفعيل نظام التزامن: {str(e)}")
            )
            logger.error(f"خطأ في تفعيل نظام التزامن: {str(e)}")
            raise

    def create_sale_payment_sync_rules(self, force=False):
        """إنشاء قواعد تزامن دفعات المبيعات"""
        self.stdout.write("💰 إنشاء قواعد تزامن دفعات المبيعات...")

        rules_data = [
            {
                "name": "تزامن دفعات المبيعات عند الإنشاء",
                "description": "تزامن دفعات المبيعات مع النظام المحاسبي عند إنشائها",
                "source_model": "sale_payment",
                "trigger_event": "on_create",
                "sync_to_journal_entry": True,
                "sync_to_balance_cache": True,
                "conditions": {},
                "mapping_rules": {
                    "account_mapping": {
                        "cash": "1001",  # الصندوق
                        "bank": "1002",  # البنك
                        "receivable": "1201",  # العملاء
                    }
                },
                "priority": 1,
            },
            {
                "name": "تزامن دفعات المبيعات عند التحديث",
                "description": "تزامن دفعات المبيعات عند تحديث المبلغ أو طريقة الدفع",
                "source_model": "sale_payment",
                "trigger_event": "on_update",
                "sync_to_journal_entry": True,
                "sync_to_balance_cache": True,
                "conditions": {},
                "mapping_rules": {
                    "account_mapping": {
                        "cash": "1001",
                        "bank": "1002",
                        "receivable": "1201",
                    }
                },
                "priority": 2,
            },
        ]

        created_count = 0
        for rule_data in rules_data:
            rule, created = PaymentSyncRule.objects.get_or_create(
                name=rule_data["name"], defaults=rule_data
            )

            if created or force:
                if force and not created:
                    # تحديث البيانات الموجودة
                    for key, value in rule_data.items():
                        if key != "name":
                            setattr(rule, key, value)
                    rule.save()

                created_count += 1
                self.stdout.write(f"  ✓ {rule.name}")

        self.stdout.write(f"💰 تم إنشاء/تحديث {created_count} قاعدة تزامن للمبيعات")

    def create_purchase_payment_sync_rules(self, force=False):
        """إنشاء قواعد تزامن دفعات المشتريات"""
        self.stdout.write("🛒 إنشاء قواعد تزامن دفعات المشتريات...")

        rules_data = [
            {
                "name": "تزامن دفعات المشتريات عند الإنشاء",
                "description": "تزامن دفعات المشتريات مع النظام المحاسبي عند إنشائها",
                "source_model": "purchase_payment",
                "trigger_event": "on_create",
                "sync_to_journal_entry": True,
                "sync_to_balance_cache": True,
                "conditions": {},
                "mapping_rules": {
                    "account_mapping": {
                        "cash": "1001",  # الصندوق
                        "bank": "1002",  # البنك
                        "payable": "2101",  # الموردين
                    }
                },
                "priority": 1,
            },
            {
                "name": "تزامن دفعات المشتريات عند التحديث",
                "description": "تزامن دفعات المشتريات عند تحديث المبلغ أو طريقة الدفع",
                "source_model": "purchase_payment",
                "trigger_event": "on_update",
                "sync_to_journal_entry": True,
                "sync_to_balance_cache": True,
                "conditions": {},
                "mapping_rules": {
                    "account_mapping": {
                        "cash": "1001",
                        "bank": "1002",
                        "payable": "2101",
                    }
                },
                "priority": 2,
            },
        ]

        created_count = 0
        for rule_data in rules_data:
            rule, created = PaymentSyncRule.objects.get_or_create(
                name=rule_data["name"], defaults=rule_data
            )

            if created or force:
                if force and not created:
                    # تحديث البيانات الموجودة
                    for key, value in rule_data.items():
                        if key != "name":
                            setattr(rule, key, value)
                    rule.save()

                created_count += 1
                self.stdout.write(f"  ✓ {rule.name}")

        self.stdout.write(f"🛒 تم إنشاء/تحديث {created_count} قاعدة تزامن للمشتريات")

    def verify_sync_system(self):
        """التحقق من نظام التزامن"""
        self.stdout.write("🔍 التحقق من نظام التزامن...")

        # التحقق من وجود قواعد التزامن
        active_rules = PaymentSyncRule.objects.filter(is_active=True).count()
        self.stdout.write(f"  ✓ قواعد التزامن النشطة: {active_rules}")

        # التحقق من قواعد المبيعات
        sale_rules = PaymentSyncRule.objects.filter(
            source_model="sale_payment", is_active=True
        ).count()
        self.stdout.write(f"  ✓ قواعد تزامن المبيعات: {sale_rules}")

        # التحقق من قواعد المشتريات
        purchase_rules = PaymentSyncRule.objects.filter(
            source_model="purchase_payment", is_active=True
        ).count()
        self.stdout.write(f"  ✓ قواعد تزامن المشتريات: {purchase_rules}")

        # اختبار خدمة التزامن
        try:
            from financial.services.payment_sync_service import PaymentSyncService

            sync_service = PaymentSyncService()
            self.stdout.write("  ✓ خدمة التزامن متاحة وجاهزة")
        except Exception as e:
            self.stdout.write(f"  ❌ خطأ في خدمة التزامن: {str(e)}")

        if active_rules >= 4:
            self.stdout.write("🔍 نظام التزامن جاهز للعمل!")
        else:
            self.stdout.write("⚠️ نظام التزامن يحتاج إعداد إضافي")
