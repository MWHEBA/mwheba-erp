"""
أمر تسكين الصلاحيات المبدئية للخزن والحسابات البنكية للمستخدمين
Zero-Downtime Day-1 Treasury Access Seeding Command
"""

import logging
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from financial.models.chart_of_accounts import ChartOfAccounts
from financial.models.treasury_access import TreasuryAccessAuditLog, UserTreasuryAccess
from financial.services.account_helper import AccountHelperService

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    help = "تسكين أولي لصلاحيات الخزن والحسابات البنكية للمدراء الماليين والكاشيرات الحاليين لضمان استمرارية العمل بدون أي انقطاع"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="إعادة إسناد وتحديث الصلاحيات للمستخدمين حتى لو كانت مسندة مسبقاً",
        )

    def handle(self, *args, **options):
        force = options.get("force", False)
        self.stdout.write(self.style.NOTICE("Starting initial treasury access seeding..."))

        cash_accounts = list(AccountHelperService.get_cash_accounts())
        bank_accounts = list(AccountHelperService.get_bank_accounts())
        all_treasuries = cash_accounts + bank_accounts

        if not all_treasuries:
            self.stdout.write(self.style.WARNING("Warning: No cash or bank accounts found in the system."))
            return

        total_assigned = 0
        superusers = User.objects.filter(is_superuser=True, is_active=True)
        staff_users = User.objects.filter(is_staff=True, is_active=True).exclude(id__in=superusers.values_list("id", flat=True))

        with transaction.atomic():
            # 1. إسناد كامل الصلاحيات (إيداع + صرف) للسوبر أدمن والمدراء
            for su in superusers:
                for trsy in all_treasuries:
                    access, created = UserTreasuryAccess.objects.get_or_create(
                        user=su,
                        treasury=trsy,
                        defaults={
                            "can_deposit": True,
                            "can_disburse": True,
                            "is_default": (trsy == cash_accounts[0] if cash_accounts else False),
                            "notes": "Initial seeding for superuser",
                        },
                    )
                    if created or force:
                        if force and not created:
                            access.can_deposit = True
                            access.can_disburse = True
                            access.save()
                        total_assigned += 1
                        TreasuryAccessAuditLog.objects.create(
                            user=su,
                            treasury=trsy,
                            action="ASSIGNED" if created else "UPDATED",
                            new_permissions={"can_deposit": True, "can_disburse": True},
                            notes="Initial seeding for superuser",
                        )

            # 2. إسناد الخزينة النقدية الافتراضية بصلاحية الإيداع لكافة المستخدمين النشطين الحاليين
            if cash_accounts:
                default_cash = AccountHelperService.get_default_cash_account() or cash_accounts[0]
                other_users = User.objects.filter(is_active=True).exclude(
                    id__in=superusers.values_list("id", flat=True)
                )

                for u in other_users:
                    access, created = UserTreasuryAccess.objects.get_or_create(
                        user=u,
                        treasury=default_cash,
                        defaults={
                            "can_deposit": True,
                            "can_disburse": False,
                            "is_default": True,
                            "notes": "Initial default deposit treasury seeding",
                        },
                    )
                    if created:
                        total_assigned += 1
                        TreasuryAccessAuditLog.objects.create(
                            user=u,
                            treasury=default_cash,
                            action="ASSIGNED",
                            new_permissions={"can_deposit": True, "can_disburse": False},
                            notes="Initial default deposit treasury seeding",
                        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Initial treasury access seeding completed successfully. {total_assigned} records created/updated."
            )
        )
