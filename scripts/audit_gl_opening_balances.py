#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Phase 0 Read-Only Audit Script for MWHEBA ERP
فحص استقصائي تحليلي شامل لقاعدة البيانات (للقراءة فقط بنسبة 100%)
لفحص الأرصدة الافتتاحية، الحسابات اليتيمة، المكررة، والسحب على المكشوف، والفترات المحاسبية.
"""

import os
import sys
import io
from decimal import Decimal
from datetime import date

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# ضبط بيئة دجانجو
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "corporate_erp.settings")

import django
django.setup()

from django.db.models import Sum, Q, Count
from django.utils import timezone

from financial.models.chart_of_accounts import ChartOfAccounts
from financial.models.journal_entry import JournalEntry, JournalEntryLine
from financial.models.opening_balance import OpeningBalanceBatch, OpeningBalanceLine
from financial.models.fiscal_year import FiscalYear
from financial.models.journal_entry import AccountingPeriod
from financial.services.period_control_service import PeriodControlService
from financial.services.role_registry import AccountRoleRegistry
from customer.models import Customer, CustomerTransaction
from supplier.models import Supplier, SupplierTransaction

def run_phase_0_audit():
    print("=" * 80)
    print("  تقرير الفحص الاستقصائي التحليلي الشامل - المرحلة صفر (Phase 0 Read-Only Audit)")
    print("  MWHEBA ERP - General Ledger Single Source of Truth (Pure GL SSOT)")
    print("  تاريخ ووقت الفحص:", timezone.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 80)

    # -------------------------------------------------------------------------
    # 1. حصر الحسابات التي لها opening_balance != 0
    # -------------------------------------------------------------------------
    accounts_with_op = ChartOfAccounts.objects.exclude(opening_balance=Decimal("0.00")).order_by('code')
    total_accounts = ChartOfAccounts.objects.count()
    op_count = accounts_with_op.count()
    print(f"\n[1] إجمالي الحسابات المسجلة بدليل الحسابات: {total_accounts}")
    print(f"    عدد الحسابات التي تمتلك opening_balance != 0: {op_count}")
    
    total_op_val = accounts_with_op.aggregate(total=Sum('opening_balance'))['total'] or Decimal('0.00')
    print(f"    إجمالي مبالغ الأرصدة الافتتاحية المسجلة على الموديل: {total_op_val:,.2f} ج.م")

    # -------------------------------------------------------------------------
    # 2. حصر الحسابات التي تمتلك قيداً مرحلاً مطابقاً (entry_type='opening' أو reference يبدأ بـ OPB-)
    # -------------------------------------------------------------------------
    opening_jes = JournalEntry.objects.filter(
        status='posted'
    ).filter(
        Q(entry_type='opening') | Q(reference__startswith='OPB-') | Q(source_module='OPENING_BALANCE')
    )
    print(f"\n[2] عدد قيود اليومية الافتتاحية المرحلة في النظام: {opening_jes.count()}")
    for je in opening_jes[:10]:
        print(f"    - قيد: {je.number} | تاريخ: {je.date} | مرجع: {je.reference} | بيان: {je.description[:50]}")
    if opening_jes.count() > 10:
        print(f"    ... و {opening_jes.count() - 10} قيود أخرى.")

    opening_je_account_ids = set(
        JournalEntryLine.objects.filter(
            journal_entry__in=opening_jes
        ).values_list('account_id', flat=True).distinct()
    )
    print(f"    عدد الحسابات التي تملك قيوداً افتتاحية مرحلة في الدفتر: {len(opening_je_account_ids)}")

    # -------------------------------------------------------------------------
    # 3. حصر الحسابات اليتيمة (Orphan Accounts)
    # (تمتلك opening_balance != 0 في الموديل ولكن ليس لها أي قيد افتتاحي مرحل)
    # -------------------------------------------------------------------------
    orphan_accounts = []
    has_both_accounts = []
    
    for acc in accounts_with_op:
        if acc.id not in opening_je_account_ids:
            orphan_accounts.append(acc)
        else:
            has_both_accounts.append(acc)

    print(f"\n[3] نتيجة مطابقة الحسابات:")
    print(f"    ✅ حسابات مزدوجة (لها رصيد على الموديل وقيد مرحل في الدفتر): {len(has_both_accounts)}")
    print(f"    ⚠️ حسابات يتيمة (Orphan: لها رصيد على الموديل وبدون قيد دفتري): {len(orphan_accounts)}")

    if orphan_accounts:
        print("\n    تفاصيل الحسابات اليتيمة (تتطلب توليد قيود Backfill في المرحلة 1):")
        for o_acc in orphan_accounts:
            nature = o_acc.nature if hasattr(o_acc, 'nature') else (o_acc.account_type.nature if o_acc.account_type else 'unknown')
            curr = o_acc.currency.code if o_acc.currency else 'EGP'
            print(f"      * [{o_acc.code}] {o_acc.name} | النوع: {nature} | الرصيد: {o_acc.opening_balance:,.2f} {curr} | التاريخ: {o_acc.opening_balance_date}")
    else:
        print("    ✨ رائع: لا توجد أي حسابات يتيمة بدون قيود دفترية!")

    # -------------------------------------------------------------------------
    # 4. فحص الحسابات المكررة (أكثر من قيد OPB أو دفعات + فردي)
    # -------------------------------------------------------------------------
    print(f"\n[4] فحص تكرار القيود الافتتاحية لنفس الحساب:")
    duplicate_candidates = (
        JournalEntryLine.objects.filter(journal_entry__in=opening_jes)
        .values('account_id')
        .annotate(cnt=Count('id'))
        .filter(cnt__gt=1)
    )
    dup_count = duplicate_candidates.count()
    print(f"    عدد الحسابات التي ظهرت في أكثر من سطر قيد افتتاحي: {dup_count}")
    for d in duplicate_candidates[:5]:
        acc = ChartOfAccounts.objects.get(pk=d['account_id'])
        print(f"      - حساب [{acc.code}] {acc.name}: تكرر {d['cnt']} مرات في القيود الافتتاحية.")

    # -------------------------------------------------------------------------
    # 5. فحص وجود قيود تدوير سنوية سابقة (OPN-)
    # -------------------------------------------------------------------------
    print(f"\n[5] فحص قيود التدوير السنوي (OPN- / Rollover Entries):")
    opn_jes = JournalEntry.objects.filter(status='posted', reference__startswith='OPN-')
    print(f"    عدد قيود التدوير السنوي OPN- المرحلة: {opn_jes.count()}")
    for opn in opn_jes:
        print(f"      - قيد تدوير: {opn.number} | تاريخ: {opn.date} | مرجع: {opn.reference}")

    # -------------------------------------------------------------------------
    # 6. فحص حسابات العملة الأجنبية ومطابقة سعر الصرف
    # -------------------------------------------------------------------------
    print(f"\n[6] فحص حسابات العملات الأجنبية وأسعار الصرف:")
    foreign_accounts = ChartOfAccounts.objects.filter(is_active=True).exclude(currency__isnull=True).exclude(currency__code='EGP')
    print(f"    عدد حسابات العملات الأجنبية النشطة: {foreign_accounts.count()}")
    for fa in foreign_accounts:
        curr = fa.currency.code if fa.currency else 'N/A'
        op_foreign = fa.opening_balance_foreign or Decimal("0.00")
        rate = fa.opening_balance_rate or Decimal("1.000000")
        local_equiv = (op_foreign * rate).quantize(Decimal("0.01"))
        print(f"      * [{fa.code}] {fa.name} ({curr}): أجنبي={op_foreign:,.2f} | سعر الصرف={rate} | المعادل={local_equiv:,.2f} ج.م | الحقل المحلي={fa.opening_balance:,.2f} ج.م")

    # -------------------------------------------------------------------------
    # 7. فحص أثر المضاعفة الحالي في LedgerQueryService وشجرة الحسابات
    # -------------------------------------------------------------------------
    print(f"\n[7] فحص الحسابات المتأثرة بمضاعفة الرصيد حالياً:")
    doubled_accounts = []
    for acc in has_both_accounts:
        # حساب له رصيد على الموديل وقيد في الدفتر
        doubled_accounts.append(acc)
    print(f"    عدد الحسابات المهددة بالمضاعفة إذا جُمع الحقل مع الدفتر: {len(doubled_accounts)}")
    for d_acc in doubled_accounts[:5]:
        curr = d_acc.currency.code if d_acc.currency else 'EGP'
        print(f"      - [{d_acc.code}] {d_acc.name}: الرصيد المسجل={d_acc.opening_balance:,.2f} {curr}")

    # -------------------------------------------------------------------------
    # 8. فحص حالة اتزان الميزانية العمومية وميزان المراجعة الحالية
    # -------------------------------------------------------------------------
    print(f"\n[8] فحص اتزان دفتر الأستاذ العام التراكمي الشامل (GL Balance Equilibrium):")
    gl_totals = JournalEntryLine.objects.filter(journal_entry__status='posted').aggregate(
        total_dr=Sum('debit'),
        total_cr=Sum('credit')
    )
    total_dr = gl_totals['total_dr'] or Decimal('0.00')
    total_cr = gl_totals['total_cr'] or Decimal('0.00')
    diff = total_dr - total_cr
    print(f"    إجمالي المدين المرحل في الدفتر: {total_dr:,.2f} ج.م")
    print(f"    إجمالي الدائن المرحل في الدفتر: {total_cr:,.2f} ج.م")
    print(f"    الفارق بين المدين والدائن: {diff:,.2f} ج.م {'(✅ متزن 100%)' if diff == 0 else '(⚠️ غير متزن!)'}")

    # -------------------------------------------------------------------------
    # 9. فحص القيود المسجلة بعد 2030-12-31
    # -------------------------------------------------------------------------
    print(f"\n[9] فحص قيود الأفق الزمني المستقبلي (> 2030-12-31):")
    future_lines = JournalEntryLine.objects.filter(journal_entry__date__gt=date(2030, 12, 31))
    print(f"    عدد القيود المسجلة بعد عام 2030: {future_lines.count()}")

    # -------------------------------------------------------------------------
    # 10. فحص الحسابات اليتيمة غير المؤرخة (Null opening_balance_date)
    # -------------------------------------------------------------------------
    print(f"\n[10] فحص الحسابات ذات التاريخ الافتتاحي الفارغ (Null Opening Date):")
    null_date_accounts = ChartOfAccounts.objects.exclude(opening_balance=Decimal("0.00")).filter(opening_balance_date__isnull=True)
    print(f"    عدد الحسابات التي لها رصيد وتاريخها فارغ: {null_date_accounts.count()}")
    for nda in null_date_accounts:
        print(f"      - [{nda.code}] {nda.name} | الرصيد: {nda.opening_balance:,.2f}")

    # -------------------------------------------------------------------------
    # 11. فحص تقاطع قيود المخزون الافتتاحية
    # -------------------------------------------------------------------------
    print(f"\n[11] فحص تقاطع قيود المخزون الافتتاحية:")
    inv_opening_jes = JournalEntry.objects.filter(
        status='posted',
        source_module='product'
    ).filter(
        Q(description__icontains='رصيد افتتاحي') | Q(description__icontains='افتتاحي')
    )
    print(f"    قيود استلام مخزني رصيد افتتاحي من المخازن: {inv_opening_jes.count()}")
    
    inv_batch_lines = OpeningBalanceLine.objects.filter(line_type='INVENTORY')
    print(f"    سطور مخزون مدرجة في دفعات الأرصدة المالية: {inv_batch_lines.count()}")

    # -------------------------------------------------------------------------
    # 12. فحص ارتباط الحسابات اليتيمة بسجلات عملاء أو موردين
    # -------------------------------------------------------------------------
    print(f"\n[12] فحص ارتباط الحسابات اليتيمة بالعملاء والموردين:")
    orphan_customer_accounts = []
    orphan_supplier_accounts = []
    for o_acc in orphan_accounts:
        cust = Customer.objects.filter(financial_account=o_acc).first()
        if cust:
            orphan_customer_accounts.append((o_acc, cust))
        supp = Supplier.objects.filter(financial_account=o_acc).first()
        if supp:
            orphan_supplier_accounts.append((o_acc, supp))
    print(f"    حسابات عملاء يتيمة: {len(orphan_customer_accounts)}")
    for a, c in orphan_customer_accounts:
        print(f"      * عميل: {c.name} (كود الحساب: {a.code}) | الرصيد: {a.opening_balance:,.2f}")
    print(f"    حسابات موردين يتيمة: {len(orphan_supplier_accounts)}")
    for a, s in orphan_supplier_accounts:
        print(f"      * مورد: {s.name} (كود الحساب: {a.code}) | الرصيد: {a.opening_balance:,.2f}")

    # -------------------------------------------------------------------------
    # 13. فحص الأرصدة السالبة (السحب على المكشوف Overdraft)
    # -------------------------------------------------------------------------
    print(f"\n[13] فحص الحسابات ذات الأرصدة الافتتاحية السالبة (Overdraft):")
    negative_accounts = ChartOfAccounts.objects.filter(opening_balance__lt=Decimal("0.00"))
    print(f"    عدد الحسابات ذات الرصيد الافتتاحي السالب: {negative_accounts.count()}")
    for na in negative_accounts:
        print(f"      - [{na.code}] {na.name} | الرصيد: {na.opening_balance:,.2f} ج.م")

    # -------------------------------------------------------------------------
    # 14. فحص حالة الفترات المحاسبية المقفلة
    # -------------------------------------------------------------------------
    print(f"\n[14] فحص السنوات والفترات المحاسبية المقفلة:")
    fiscal_years = FiscalYear.objects.all().order_by('start_date')
    print(f"    إجمالي السنوات المالية المسجلة: {fiscal_years.count()}")
    for fy in fiscal_years:
        print(f"      - سنة {fy.year_code} ({fy.name}): من {fy.start_date} إلى {fy.end_date} | الحالة: {fy.status}")
    
    closed_periods = AccountingPeriod.objects.filter(status__in=['closed', 'hard_closed'])
    print(f"    عدد الفترات المحاسبية المقفلة: {closed_periods.count()}")
    for cp in closed_periods[:5]:
        print(f"      - فترة مقفلة: {cp.name} ({cp.start_date} إلى {cp.end_date})")

    # -------------------------------------------------------------------------
    # 15. فحص حساب الأرصدة الافتتاحية في حقوق الملكية (Role Registry)
    # -------------------------------------------------------------------------
    print(f"\n[15] فحص حساب وسيط الأرصدة الافتتاحية (Equity Clearing Account):")
    try:
        opening_equity = AccountRoleRegistry.get_account("OPENING_BALANCE_EQUITY")
        print(f"    ✅ تم العثور على الحساب من RoleRegistry: [{opening_equity.code}] {opening_equity.name}")
    except Exception as e:
        print(f"    ⚠️ لم يتم حل الحساب عبر AccountRoleRegistry: {str(e)}")
        eq_acc = ChartOfAccounts.objects.filter(code='31010').first()
        if eq_acc:
            print(f"    ℹ️ تم العثور على الحساب المباشر بالكود 31010: {eq_acc.name}")
        else:
            print(f"    ❌ تحذير حرج: الحساب 31010 غير موجود!")

    print("\n" + "=" * 80)
    print("  نهاية تقرير التدقيق - كافة البيانات مستخرجة للقراءة فقط دون أي تعديل.")
    print("=" * 80)

if __name__ == '__main__':
    run_phase_0_audit()
