#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Command: backfill_opening_balances
معالجة وهجرة الحسابات القديمة اليتيمة وتوليد قيود افتتاحية محوكمة متزنة عبر AccountingGateway
(Phase 1.1 Implementation - Single Source of Truth)
"""

import logging
from decimal import Decimal
from datetime import date
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.cache import cache

from financial.models.chart_of_accounts import ChartOfAccounts
from financial.models.journal_entry import JournalEntry, JournalEntryLine, AccountingPeriod
from financial.models.fiscal_year import FiscalYear
from financial.services.period_control_service import PeriodControlService
from financial.services.role_registry import AccountRoleRegistry
from financial.services.exchange_rate_service import ExchangeRateService
from governance.services.accounting_gateway import AccountingGateway, JournalEntryLineData
from customer.models import Customer, CustomerTransaction
from supplier.models import Supplier, SupplierTransaction

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    help = "توليد قيود افتتاحية محوكمة للحسابات القديمة اليتيمة لنقل الأرصدة للأستاذ العام"

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="تنفيذ الهجرة فعلياً على قاعدة البيانات (الوضع الافتراضي هو المحاكاة Dry Run)",
        )
        parser.add_argument(
            "--username",
            type=str,
            default=None,
            help="اسم المستخدم المنسوب له ترحيل القيود (افتراضياً المدير التنفيذي / superuser)",
        )

    def handle(self, *args, **options):
        is_apply = options.get("apply", False)
        username = options.get("username")

        self.stdout.write(self.style.MIGRATE_HEADING("=" * 80))
        self.stdout.write(self.style.MIGRATE_HEADING("  تشغيل معالج هجرة الأرصدة الافتتاحية للأستاذ العام (Phase 1 Backfill)"))
        self.stdout.write(f"  الوضع: {'تنفيذ فعلي (APPLY)' if is_apply else 'محاكاة فقط (DRY RUN)'}")
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 80))

        # 1. تحديد المستخدم المنفذ
        user = None
        if username:
            user = User.objects.filter(username=username).first()
        if not user:
            user = User.objects.filter(is_superuser=True).first() or User.objects.first()

        if not user:
            self.stderr.write(self.style.ERROR("[ERROR] خطأ: لم يتم العثور على أي مستخدم في النظام لنسب القيود إليه!"))
            return

        # 2. حل حساب وسيط الأرصدة الافتتاحية في حقوق الملكية
        try:
            opening_equity_account = AccountRoleRegistry.get_account("OPENING_BALANCE_EQUITY")
        except Exception:
            opening_equity_account = ChartOfAccounts.objects.filter(code="31010", is_active=True).first()

        if not opening_equity_account:
            self.stderr.write(self.style.ERROR("[CRITICAL] خطأ حرج: لم يتم العثور على حساب وسيط الأرصدة الافتتاحية (31010)!"))
            return

        self.stdout.write(f"  حساب وسيط حقوق الملكية: [{opening_equity_account.code}] {opening_equity_account.name}")

        # 3. حصر الحسابات ذات الأرصدة الافتتاحية
        candidate_accounts = ChartOfAccounts.objects.exclude(opening_balance=Decimal("0.00")).order_by("code")

        # حصر الحسابات التي تملك قيوداً افتتاحية مسبقة
        existing_opening_account_ids = set(
            JournalEntryLine.objects.filter(
                journal_entry__status="posted"
            ).filter(
                Q(journal_entry__entry_type="opening")
                | Q(journal_entry__reference__startswith="OPB-")
                | Q(journal_entry__reference__startswith="MIG-OPB-")
                | Q(journal_entry__source_module="OPENING_BALANCE")
                | Q(journal_entry__source_module="OPENING_BALANCE_MIGRATION")
            ).values_list("account_id", flat=True).distinct()
        )

        orphan_accounts = [acc for acc in candidate_accounts if acc.id not in existing_opening_account_ids]

        self.stdout.write(f"  إجمالي الحسابات التي تحمل رصيداً في الموديل: {candidate_accounts.count()}")
        self.stdout.write(f"  الحسابات التي تمتلك قيوداً مرحلة بالفعل: {len(existing_opening_account_ids)}")
        self.stdout.write(self.style.WARNING(f"  الحسابات اليتيمة المستهدفة بالمعالجة: {len(orphan_accounts)}"))

        if not orphan_accounts:
            self.stdout.write(self.style.SUCCESS("[OK] ممتاز: لا توجد أي حسابات يتيمة تحتاج إلى توليد قيود افتتاحية!"))
            self._invalidate_caches()
            return

        # 4. معالجة وتوليد القيود للحسابات اليتيمة
        gateway = AccountingGateway()
        processed_count = 0
        skipped_count = 0

        # أقدم سنة مالية نشطة كمرجع للتواريخ الفارغة
        oldest_fy = FiscalYear.objects.all().order_by("start_date").first()
        default_op_date = oldest_fy.start_date if oldest_fy else date(2026, 1, 1)

        for acc in orphan_accounts:
            op_balance = acc.opening_balance
            if not op_balance or op_balance == Decimal("0.00"):
                continue

            # تحديد تاريخ القيد
            op_date = acc.opening_balance_date or default_op_date

            # فحص إقفال الفترة المحاسبية
            is_open, period = PeriodControlService.validate_period_open(op_date)
            if not is_open:
                # إذا كانت الفترة مقفلة، نرحل القيد في أول يوم من أول فترة مفتوحة
                open_period = AccountingPeriod.objects.filter(status="open", start_date__gte=op_date).order_by("start_date").first()
                if open_period:
                    op_date = open_period.start_date
                else:
                    op_date = date.today()
                self.stdout.write(self.style.WARNING(f"    [WARN] تم تعديل تاريخ قيد الحساب [{acc.code}] إلى {op_date} لإقفال الفترة القديمة."))

            # تحديد العملة وسعر الصرف والمبالغ
            curr_code = acc.currency.code if acc.currency else "EGP"
            is_foreign = bool(acc.currency and curr_code != "EGP")
            base_amount = abs(op_balance).quantize(Decimal("0.01"))

            if is_foreign:
                if acc.opening_balance_foreign and acc.opening_balance_foreign != Decimal("0.00"):
                    foreign_amt = abs(acc.opening_balance_foreign).quantize(Decimal("0.01"))
                    rate = (acc.opening_balance_rate or (base_amount / foreign_amt if foreign_amt > 0 else Decimal("1.000000"))).quantize(Decimal("0.000001"))
                else:
                    rate = acc.opening_balance_rate or Decimal("1.000000")
                    if rate == Decimal("1.000000"):
                        try:
                            rate = ExchangeRateService.get_rate(curr_code, "EGP", date=op_date)
                        except Exception:
                            rate = Decimal("1.000000")
                    foreign_amt = (base_amount / rate).quantize(Decimal("0.01")) if rate > 0 else base_amount
            else:
                foreign_amt = base_amount
                rate = Decimal("1.000000")

            # تحديد التوجيه المحاسبي مع احترام إشارة السحب على المكشوف
            nature = getattr(acc, "nature", None)
            if not nature and acc.account_type:
                nature = acc.account_type.nature

            # القاعدة الصارمة:
            # (أصل مدين وموجب -> مدين) | (أصل مدين ومكشوف سالب -> دائن)
            # (التزام دائن وموجب -> دائن) | (التزام دائن ومكشوف سالب -> مدين)
            if nature == "debit":
                account_is_debit = (op_balance > 0)
            else:
                account_is_debit = (op_balance < 0)

            lines_data = []
            if account_is_debit:
                # الحساب مدين، الأرصدة الافتتاحية دائنة
                lines_data.append(JournalEntryLineData(
                    account_code=acc.code,
                    debit=base_amount,
                    credit=Decimal("0.00"),
                    description=f"رصيد افتتاحي مؤسس لـ {acc.name}",
                    currency=curr_code,
                    exchange_rate=rate,
                    foreign_debit=foreign_amt,
                    foreign_credit=Decimal("0.00"),
                ))
                lines_data.append(JournalEntryLineData(
                    account_code=opening_equity_account.code,
                    debit=Decimal("0.00"),
                    credit=base_amount,
                    description=f"مقابل رصيد افتتاحي لـ {acc.name}",
                    currency="EGP",
                    exchange_rate=Decimal("1.000000"),
                    foreign_debit=Decimal("0.00"),
                    foreign_credit=base_amount,
                ))
            else:
                # الحساب دائن، الأرصدة الافتتاحية مدينة
                lines_data.append(JournalEntryLineData(
                    account_code=acc.code,
                    debit=Decimal("0.00"),
                    credit=base_amount,
                    description=f"رصيد افتتاحي (دائن/مكشوف) لـ {acc.name}",
                    currency=curr_code,
                    exchange_rate=rate,
                    foreign_debit=Decimal("0.00"),
                    foreign_credit=foreign_amt,
                ))
                lines_data.append(JournalEntryLineData(
                    account_code=opening_equity_account.code,
                    debit=base_amount,
                    credit=Decimal("0.00"),
                    description=f"مقابل رصيد افتتاحي (دائن/مكشوف) لـ {acc.name}",
                    currency="EGP",
                    exchange_rate=Decimal("1.000000"),
                    foreign_debit=base_amount,
                    foreign_credit=Decimal("0.00"),
                ))

            self.stdout.write(
                f"  -> معالجة [{acc.code}] {acc.name}: المبلغ={foreign_amt:,.2f} {curr_code} | "
                f"المعادل={base_amount:,.2f} ج.م | الاتجاه={'مدين' if account_is_debit else 'دائن'}"
            )

            if is_apply:
                try:
                    with transaction.atomic():
                        je = gateway.create_journal_entry(
                            source_module="financial",
                            source_model="ChartOfAccounts",
                            source_id=acc.id,
                            entry_type="opening",
                            date=op_date,
                            description=f"قيد رصيد افتتاحي هجرة محوكم لـ {acc.name}",
                            reference=f"MIG-OPB-{acc.code}",
                            lines=lines_data,
                            idempotency_key=f"JE:MIGRATION:OPB:{acc.id}",
                            user=user,
                        )

                        # مزامنة الأستاذ المساعد للعملاء أو الموردين
                        self._sync_subledgers(acc, je, op_balance, base_amount, foreign_amt, curr_code, rate, op_date)

                        processed_count += 1
                except Exception as e:
                    self.stderr.write(self.style.ERROR(f"    [ERROR] فشل ترحيل الحساب [{acc.code}]: {str(e)}"))
                    skipped_count += 1
            else:
                processed_count += 1

        if is_apply:
            self._invalidate_caches()
            self.stdout.write(self.style.SUCCESS(f"\n[OK] اكتملت الهجرة بنجاح: تم ترحيل {processed_count} قيداً، وتخطي {skipped_count}."))
        else:
            self.stdout.write(self.style.WARNING(f"\n[INFO] انتهت المحاكاة (Dry Run): {processed_count} قيداً جاهزاً للترحيل. شغل الأمر بـ --apply للتنفيذ."))

    def _sync_subledgers(self, acc, je, op_balance, base_amount, foreign_amt, curr_code, rate, op_date):
        """مزامنة سطور الأستاذ المساعد للعميل أو المورد إن وجد"""
        # عميل
        customer = Customer.objects.filter(financial_account=acc).first()
        if customer:
            is_debit = (op_balance > 0)
            CustomerTransaction.objects.get_or_create(
                customer=customer,
                reference_type="OPENING_BALANCE",
                reference_id=str(je.id),
                defaults={
                    "transaction_type": "INVOICE" if is_debit else "ADVANCE",
                    "transaction_number": f"OPN-CUST-{acc.code}",
                    "issue_date": op_date,
                    "due_date": op_date,
                    "currency": curr_code,
                    "foreign_amount": foreign_amt or base_amount,
                    "exchange_rate": rate,
                    "functional_amount": base_amount,
                    "open_amount_foreign": foreign_amt or base_amount,
                    "open_amount_functional": base_amount,
                    "open_amount": base_amount,
                    "status": "OPEN",
                }
            )

        # مورد
        supplier = Supplier.objects.filter(financial_account=acc).first()
        if supplier:
            is_credit = (op_balance > 0)
            SupplierTransaction.objects.get_or_create(
                supplier=supplier,
                transaction_number=f"OPN-SUPP-{acc.code}",
                defaults={
                    "transaction_type": "BILL" if is_credit else "ADVANCE",
                    "transaction_number": f"OPN-SUPP-{acc.code}",
                    "issue_date": op_date,
                    "due_date": op_date,
                    "currency": curr_code,
                    "foreign_amount": foreign_amt or base_amount,
                    "exchange_rate": rate,
                    "functional_amount": base_amount,
                    "open_amount_foreign": foreign_amt or base_amount,
                    "open_amount_functional": base_amount,
                    "open_amount": base_amount,
                    "status": "OPEN",
                }
            )

    def _invalidate_caches(self):
        """إبطال الكاش المحاسبي ذرّياً للتأكد من قراءة البيانات الدفترية الطازجة"""
        try:
            cache.delete_pattern("account_balance_*")
        except AttributeError:
            # في حال كان الكاش لا يدعم delete_pattern (مثل LocMemCache)
            cache.clear()
        self.stdout.write("  [OK] تم إبطال كاش الأرصدة المحاسبية ذرّياً.")
