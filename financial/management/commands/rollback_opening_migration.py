#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Command: rollback_opening_migration
أمر التراجع السريع المحوكم لعكس وإلغاء كافة قيود هجرة الأرصدة الافتتاحية ذرّياً
(Rollback Guarantee for Phase 1 Migration)
"""

import logging
from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.auth import get_user_model
from django.core.cache import cache

from financial.models.journal_entry import JournalEntry
from governance.services.accounting_gateway import AccountingGateway
from customer.models import CustomerTransaction
from supplier.models import SupplierTransaction

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    help = "عكس وإلغاء قيود هجرة الأرصدة الافتتاحية المولدة بواسطة MIG-OPB"

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="تنفيذ العكس فعلياً على قاعدة البيانات",
        )
        parser.add_argument(
            "--reference-prefix",
            type=str,
            default="MIG-OPB-",
            help="بادئة المرجع للقيود المستهدفة بالعكس (افتراضياً MIG-OPB-)",
        )
        parser.add_argument(
            "--reason",
            type=str,
            default="تراجع محوكم عن قيود هجرة الأرصدة الافتتاحية",
            help="سبب القيد العكسي",
        )

    def handle(self, *args, **options):
        is_apply = options.get("apply", False)
        prefix = options.get("reference_prefix", "MIG-OPB-")
        reason = options.get("reason")

        self.stdout.write(self.style.MIGRATE_HEADING("=" * 80))
        self.stdout.write(self.style.MIGRATE_HEADING("  تشغيل أداة التراجع العكسي لقيود الهجرة (Rollback Migration)"))
        self.stdout.write(f"  الوضع: {'تنفيذ فعلي (APPLY)' if is_apply else 'محاكاة فقط (DRY RUN)'}")
        self.stdout.write(f"  بادئة البحث: {prefix}")
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 80))

        user = User.objects.filter(is_superuser=True).first() or User.objects.first()

        # البحث عن قيود الهجرة المرحلة
        migration_entries = JournalEntry.objects.filter(
            status="posted",
            reference__startswith=prefix
        ).order_by("-id")

        total_entries = migration_entries.count()
        self.stdout.write(f"  عدد قيود الهجرة المطلوب عكسها: {total_entries}")

        if total_entries == 0:
            self.stdout.write(self.style.SUCCESS("[OK] لا توجد أي قيود هجرة مرحلة مطابقة للبادئة."))
            return

        gateway = AccountingGateway()
        reversed_count = 0
        failed_count = 0

        for je in migration_entries:
            self.stdout.write(f"  -> قيد رقم [{je.number}] | مرجع: {je.reference} | تاريخ: {je.date}")

            if is_apply:
                try:
                    with transaction.atomic():
                        # عكس القيد عبر البوابة المحاسبية
                        gateway.reverse_journal_entry(
                            journal_entry=je,
                            user=user,
                            reason=reason,
                        )

                        # إزالة أو عكس سطور الأستاذ المساعد التابعة إن وجدت
                        CustomerTransaction.objects.filter(
                            reference_type="OPENING_BALANCE",
                            reference_id=str(je.id)
                        ).delete()

                        acc_code = je.reference.replace(prefix, "") if je.reference else ""
                        if acc_code:
                            SupplierTransaction.objects.filter(
                                transaction_number=f"OPN-SUPP-{acc_code}"
                            ).delete()

                        reversed_count += 1
                except Exception as e:
                    self.stderr.write(self.style.ERROR(f"    [ERROR] فشل عكس القيد [{je.number}]: {str(e)}"))
                    failed_count += 1
            else:
                reversed_count += 1

        if is_apply:
            try:
                cache.delete_pattern("account_balance_*")
            except AttributeError:
                cache.clear()
            self.stdout.write(self.style.SUCCESS(f"\n[OK] اكتملت عملية التراجع: تم عكس {reversed_count} قيداً بنجاح، وفشل {failed_count}."))
        else:
            self.stdout.write(self.style.WARNING(f"\n[INFO] انتهت المحاكاة: {reversed_count} قيداً جاهزاً للعكس. شغل الأمر بـ --apply للتنفيذ."))
