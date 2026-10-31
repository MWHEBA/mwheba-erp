# -*- coding: utf-8 -*-
"""
FIN-SAL-INS-008: installment_views
شاشات وعمليات رادار التحصيل، السندات لأمر، ومطابقة مراقب الحسابات
"""
import json
from decimal import Decimal
from datetime import timedelta
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_GET
from django.http import JsonResponse, HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import gettext as _
from django.urls import reverse
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Sum, Q
from django.contrib import messages

from sale.models import Sale, SalePayment
from sale.models.installments import (
    InstallmentPlan,
    InstallmentItem,
    InstallmentCashStatus,
    PaperCoverage,
    PlanStatus,
    CollectionRadarSnapshot,
)
from cheques.models.cheque import Cheque
from customer.models import Customer
from financial.models import CostCenter, ChartOfAccounts
from financial.services.role_registry import AccountRoleRegistry, AccountRoleNames
from utils.arabic_numbers import amount_to_arabic_words
from users.decorators import require_permission

from sale.services.compliance_pack_service import CompliancePackService
from sale.services.collector_incentive_service import CollectorIncentiveService
from sale.services.debt_clearance_service import DebtClearanceCertificateService
from sale.services.early_settlement_service import EarlySettlementService
from sale.services.rework_dispute_service import ReworkDisputeService
from sale.services.penalty_waiver_service import PenaltyWaiverService
from sale.services.installment_engine import InstallmentEngine


@login_required
@require_permission('sale.view_installmentplan')
def installment_radar(request):
    """
    لوحة متابعة رادار التحصيل وجدولة الأقساط (Collection Radar UI)
    تدعم العزل الإقليمي بمراكز التكلفة، الفلاتر المتطورة، وكروت الـ KPI المستقلة
    """
    today = timezone.localdate()

    # 1. استخراج فلاتر البحث
    q = request.GET.get('q', '').strip()
    selected_customer = request.GET.get('customer', '').strip()
    selected_cost_center = request.GET.get('cost_center', '').strip()
    selected_collector = request.GET.get('collector', '').strip()
    selected_status = request.GET.get('cash_status', '').strip()
    selected_coverage = request.GET.get('paper_coverage', '').strip()
    selected_risk = request.GET.get('risk_level', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()

    # 2. بناء استعلام الأقساط الأساسي
    items_qs = InstallmentItem.objects.select_related(
        'plan', 'plan__sale', 'plan__sale__customer', 'plan__sale__cost_center',
        'linked_delivery_note'
    ).prefetch_related('cheques').order_by('due_date', 'installment_number')

    if q:
        items_qs = items_qs.filter(
            Q(plan__sale__number__icontains=q) |
            Q(plan__sale__customer__name__icontains=q) |
            Q(installment_number__icontains=q) |
            Q(notes__icontains=q)
        )

    if selected_customer:
        items_qs = items_qs.filter(plan__sale__customer_id=selected_customer)

    if selected_cost_center:
        items_qs = items_qs.filter(plan__sale__cost_center_id=selected_cost_center)

    if selected_collector:
        items_qs = items_qs.filter(plan__sale__salesman_id=selected_collector)

    if selected_status:
        items_qs = items_qs.filter(cash_status=selected_status)

    if selected_coverage:
        items_qs = items_qs.filter(paper_coverage=selected_coverage)

    if date_from:
        items_qs = items_qs.filter(due_date__gte=date_from)

    if date_to:
        items_qs = items_qs.filter(due_date__lte=date_to)

    if selected_risk == 'HIGH':
        # أقساط مكشوفة متأخرة أو متنازع عليها
        items_qs = items_qs.filter(
            Q(paper_coverage=PaperCoverage.UNCOVERED, due_date__lt=today) |
            Q(cash_status__in=[InstallmentCashStatus.OVERDUE, InstallmentCashStatus.BOUNCED, InstallmentCashStatus.LEGAL_ACTION])
        )
    elif selected_risk == 'MEDIUM':
        # أقساط مغطاة جزئياً أو يحل أجلها خلال 7 أيام
        items_qs = items_qs.filter(
            Q(paper_coverage=PaperCoverage.PARTIALLY_COVERED) |
            Q(due_date__gte=today, due_date__lte=today + timedelta(days=7))
        )
    elif selected_risk == 'LOW':
        items_qs = items_qs.filter(
            paper_coverage__in=[PaperCoverage.PORTFOLIO_CHEQUE, "FULLY_COVERED", PaperCoverage.BANK_LETTER_OF_GUARANTEE],
            due_date__gt=today + timedelta(days=7)
        )

    # 3. احتساب مؤشرات الـ KPI (استخدام أحدث لقطة سريعة إن وجدت أو الحساب اللحظي)
    cc_filter = selected_cost_center if selected_cost_center else None
    latest_snapshot = CollectionRadarSnapshot.objects.filter(
        snapshot_date=today,
        cost_center_id=cc_filter
    ).first()

    if latest_snapshot:
        due_portfolio_cheques_amount = latest_snapshot.total_due_today
        overdue_uncovered_amount = latest_snapshot.total_uncovered_overdue
        under_collection_amount = latest_snapshot.total_cheques_under_collection
        expected_cashflow_30d = latest_snapshot.expected_cashflow_30d
    else:
        # حساب لحظي
        cheques_base = Cheque.objects.filter(cheque_type="RECEIVABLE")
        if selected_cost_center:
            cheques_base = cheques_base.filter(cost_center_id=selected_cost_center)

        # شيكات بالخزينة مستحقة اليوم أو سابقة لم تودع
        due_portfolio_cheques_amount = cheques_base.filter(
            status__in=["IN_PORTFOLIO", "IN_SAFE"],
            due_date__lte=today
        ).aggregate(tot=Sum('amount'))['tot'] or Decimal("0.00")

        # شيكات بالبنوك برسم التحصيل
        under_collection_amount = cheques_base.filter(
            status__in=["UNDER_COLLECTION", "BANK_DEPOSITED"]
        ).aggregate(tot=Sum('amount'))['tot'] or Decimal("0.00")

        # أقساط مكشوفة متأخرة تجاوزت فترة السماح
        overdue_uncovered_amount = Decimal("0.00")
        all_uncovered = InstallmentItem.objects.filter(
            paper_coverage=PaperCoverage.UNCOVERED,
            due_date__lt=today
        ).select_related('plan')
        if selected_cost_center:
            all_uncovered = all_uncovered.filter(plan__sale__cost_center_id=selected_cost_center)

        for it in all_uncovered:
            grace_end = it.due_date + timedelta(days=it.grace_period_days or 0)
            if today > grace_end and it.remaining_balance > Decimal("0.00"):
                if it.cash_status not in [InstallmentCashStatus.COLLECTED, InstallmentCashStatus.WAIVED, InstallmentCashStatus.HOLD_REWORK]:
                    overdue_uncovered_amount += it.remaining_balance

        # التدفق النقدي الفعلي المتوقع 30 يوماً
        date_30d = today + timedelta(days=30)
        exp_qs = InstallmentItem.objects.filter(
            due_date__gte=today,
            due_date__lte=date_30d
        ).exclude(
            cash_status__in=[
                InstallmentCashStatus.HOLD_REWORK,
                InstallmentCashStatus.LEGAL_ACTION,
                InstallmentCashStatus.BOUNCED,
                InstallmentCashStatus.WAIVED,
                InstallmentCashStatus.COLLECTED
            ]
        )
        if selected_cost_center:
            exp_qs = exp_qs.filter(plan__sale__cost_center_id=selected_cost_center)
        expected_cashflow_30d = sum(it.remaining_balance for it in exp_qs)

    # 4. التصفح والترقيم (Pagination)
    paginator = Paginator(items_qs, 25)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # إضافة وسوم وبيانات مساعدة لكل سطر في الصفحة
    for it in page_obj:
        rem_balance = it.remaining_balance
        it.computed_remaining = rem_balance
        if rem_balance <= Decimal("0.00"):
            it.risk_badge = "success"
            it.risk_label = _("مسدد بالكامل")
        elif it.cash_status == InstallmentCashStatus.HOLD_REWORK:
            it.risk_badge = "info"
            it.risk_label = _("نزاع جودة وتصنيع")
        elif it.cash_status == InstallmentCashStatus.LEGAL_ACTION:
            it.risk_badge = "dark"
            it.risk_label = _("دعوى قضائية")
        elif it.due_date < today:
            it.risk_badge = "danger"
            days_late = (today - it.due_date).days
            it.risk_label = _(f"متأخر ({days_late} يوم)")
        elif it.paper_coverage == PaperCoverage.UNCOVERED:
            it.risk_badge = "warning"
            it.risk_label = _("مكشوف بدون شيك")
        else:
            it.risk_badge = "secondary"
            it.risk_label = _("سارٍ ومغطى")

    # 5. البيانات المساعدة للفلاتر
    customers = Customer.objects.filter(is_active=True).order_by('name')[:100]
    cost_centers = CostCenter.objects.filter(is_active=True).order_by('name')
    cash_statuses = InstallmentCashStatus.choices
    paper_coverages = PaperCoverage.choices

    breadcrumb_items = [
        {"title": _("الرئيسية"), "url": reverse("core:dashboard"), "icon": "fa-home"},
        {"title": _("المبيعات"), "url": reverse("sale:sale_list"), "icon": "fa-shopping-cart"},
        {"title": _("رادار التحصيل وجدولة الأقساط"), "active": True},
    ]

    header_buttons = [
        {
            "label": _("تصدير حزمة المطابقة (Excel)"),
            "url": reverse("sale:installment_compliance_export"),
            "icon": "fas fa-file-excel",
            "class": "btn-outline-success",
        },
    ]

    context = {
        "page_title": _("رادار التحصيل وجدولة الأقساط"),
        "page_subtitle": _("متابعة تدفقات أقساط المبيعات، الشيكات بالخزينة، التغطية الورقية، والمتأخرات الحرجة"),
        "breadcrumb_items": breadcrumb_items,
        "header_buttons": header_buttons,
        "page_obj": page_obj,
        "items": page_obj.object_list,
        # KPI Cards Values
        "due_portfolio_cheques_amount": due_portfolio_cheques_amount,
        "overdue_uncovered_amount": overdue_uncovered_amount,
        "under_collection_amount": under_collection_amount,
        "expected_cashflow_30d": expected_cashflow_30d,
        # Filter Context
        "customers": customers,
        "cost_centers": cost_centers,
        "cash_statuses": cash_statuses,
        "paper_coverages": paper_coverages,
        "q": q,
        "selected_customer": selected_customer,
        "selected_cost_center": selected_cost_center,
        "selected_collector": selected_collector,
        "selected_status": selected_status,
        "selected_coverage": selected_coverage,
        "selected_risk": selected_risk,
        "date_from": date_from,
        "date_to": date_to,
        "today": today,
    }

    # إذا كان الطلب AJAX يرجع جدول الأقساط والترقيم فقط
    if request.headers.get("x-requested-with") == "XMLHttpRequest" or request.GET.get("ajax") == "1":
        table_html = render_to_string("sale/installments/partials/radar_table.html", context, request=request)
        pagination_html = render_to_string("partials/pagination.html", {"page_obj": page_obj}, request=request)
        return JsonResponse({
            "table_html": table_html,
            "pagination_html": pagination_html,
            "due_portfolio_cheques_amount": f"{due_portfolio_cheques_amount:,.2f}",
            "overdue_uncovered_amount": f"{overdue_uncovered_amount:,.2f}",
            "under_collection_amount": f"{under_collection_amount:,.2f}",
            "expected_cashflow_30d": f"{expected_cashflow_30d:,.2f}",
        })

    return render(request, "sale/installments/radar.html", context)


@login_required
@require_POST
@require_permission('sale.add_salepayment')
def quick_collection_action(request, pk):
    """
    تسجيل تحصيل نقدي/ميداني سريع لقسط محدد وتوليد سند النقدية
    """
    item = get_object_or_404(InstallmentItem.objects.select_related('plan__sale'), pk=pk)
    amount_str = request.POST.get('amount', '').strip()
    payment_method = request.POST.get('payment_method', 'cash').strip()
    notes = request.POST.get('notes', '').strip()
    receipt_ref = request.POST.get('receipt_reference', '').strip()
    payment_date_str = request.POST.get('payment_date', '').strip()

    try:
        amount = Decimal(amount_str)
        if amount <= Decimal("0.00"):
            raise ValueError()
    except Exception:
        return JsonResponse({"status": "error", "message": _("يرجى إدخال مبلغ تحصيل صحيح أكبر من الصفر.")}, status=400)

    pay_date = timezone.datetime.strptime(payment_date_str, "%Y-%m-%d").date() if payment_date_str else timezone.localdate()

    cash_acc = None
    try:
        if payment_method == "bank":
            cash_acc = AccountRoleRegistry.get_account(AccountRoleNames.BANK_ACCOUNT)
        else:
            cash_acc = AccountRoleRegistry.get_account(AccountRoleNames.CASH_ACCOUNT)
    except Exception:
        cash_acc = ChartOfAccounts.objects.filter(is_active=True).first()

    with transaction.atomic():
        locked_it = InstallmentItem.objects.select_for_update().get(pk=item.pk)
        payment = InstallmentEngine.record_installment_payment(
            installment_item=locked_it,
            amount=amount,
            payment_date=pay_date,
            user=request.user,
            payment_method=payment_method,
            financial_account=cash_acc,
            reference_number=receipt_ref or f"RCV-INS-{locked_it.id}-{timezone.now().strftime('%H%M%S')}",
            notes=notes or f"تحصيل سريع للقسط #{locked_it.installment_number}",
        )
        locked_it.refresh_from_db()

    return JsonResponse({
        "status": "success",
        "message": _(f"تم تسجيل تحصيل مبلغ {amount:,.2f} ج.م للقسط #{locked_it.installment_number} بنجاح."),
        "payment_id": payment.id if payment else None,
        "cash_status": locked_it.cash_status,
        "paid_amount": float(locked_it.paid_amount),
        "remaining_balance": float(locked_it.remaining_balance),
    })


@login_required
@require_GET
@require_permission('sale.view_sale')
def promissory_note_print_view(request, pk):
    """
    طباعة السند لأمر وإقرار المديونية الموحد المحصن قانونياً (Promissory Note Print)
    يشتمل على التفقيط العربي، بيانات الكفيل الغارم، الموطن المختار، والمادة 232 تجاري
    """
    sale = get_object_or_404(
        Sale.objects.select_related('customer', 'currency', 'installment_plan'),
        pk=pk
    )

    if not hasattr(sale, 'installment_plan') or not sale.installment_plan:
        messages.error(request, _("هذه الفاتورة لا تحتوي على خطة تقسيط أو سندات لأمر."))
        return redirect('sale:sale_detail', pk=sale.pk)

    plan = sale.installment_plan
    items = list(plan.items.order_by('installment_number'))

    curr_code = sale.currency.code if sale.currency else "EGP"
    total_words = amount_to_arabic_words(sale.contract_total, curr_code)

    # تفقيط كل قسط
    for it in items:
        it.amount_words = amount_to_arabic_words(it.total_amount, curr_code)

    context = {
        "sale": sale,
        "plan": plan,
        "items": items,
        "customer": sale.customer,
        "total_words": total_words,
        "currency_code": curr_code,
        "today": timezone.localdate(),
    }

    return render(request, "sale/installments/promissory_note_print.html", context)


@login_required
@require_GET
@require_permission('financial.view_chartofaccounts')
def export_compliance_pack(request):
    """
    تصدير حزمة مطابقة مراقب الحسابات والفحص الضريبي لمحفظة التقسيط كملف Excel رسمي
    """
    output = CompliancePackService.export_excel_pack()
    filename = f"MWHEBA_Auditor_Installment_Compliance_{timezone.localdate()}.xlsx"

    response = HttpResponse(
        output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
@require_GET
def preview_installment_schedule(request):
    """
    معاينة جدول الأقساط حياً أثناء إنشاء أو تعديل الفاتورة عبر AJAX
    """
    try:
        sale_id = request.GET.get('sale_id')
        customer_id = request.GET.get('customer_id')
        subtotal = Decimal(str(request.GET.get('subtotal', '0') or '0'))
        discount = Decimal(str(request.GET.get('discount', '0') or '0'))
        total = Decimal(str(request.GET.get('total', '0') or '0'))
        number_of_installments = int(request.GET.get('number_of_installments', '1') or '1')
        markup_rate = Decimal(str(request.GET.get('markup_rate', '0') or '0'))
        down_payment = Decimal(str(request.GET.get('down_payment', '0') or '0'))
        frequency = request.GET.get('frequency', 'MONTHLY')
        start_date_str = request.GET.get('start_date')

        start_date = timezone.localdate()
        if start_date_str:
            try:
                from datetime import datetime
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass

        if sale_id:
            sale = Sale.objects.select_related('customer', 'sales_order').get(pk=sale_id)
        else:
            customer = Customer.objects.filter(pk=customer_id).first() if customer_id else None
            if subtotal <= 0 and total > 0:
                subtotal = total + discount
            sale = Sale(
                customer=customer,
                subtotal=subtotal,
                discount=discount,
                total=total
            )

        schedule_data = InstallmentEngine.calculate_installment_schedule(
            sale=sale,
            number_of_installments=number_of_installments,
            markup_rate=markup_rate,
            fresh_down_payment=down_payment,
            frequency=frequency,
            start_date=start_date,
        )

        items_payload = []
        for it in schedule_data['items']:
            items_payload.append({
                'installment_number': it['installment_number'],
                'due_date': it['due_date'].strftime('%Y-%m-%d'),
                'principal_amount': float(it['principal_amount']),
                'interest_amount': float(it['interest_amount']),
                'total_amount': float(it['total_amount']),
                'grace_period_days': it['grace_period_days'],
            })

        return JsonResponse({
            'success': True,
            'summary': {
                'tax_inclusive_claim': float(schedule_data['tax_inclusive_claim']),
                'effective_down_payment': float(schedule_data['effective_down_payment']),
                'net_financed_principal': float(schedule_data['net_financed_principal']),
                'total_markup': float(schedule_data['total_markup']),
                'contract_total': float(schedule_data['contract_total']),
                'total_scheduled_amount': float(schedule_data['total_scheduled_amount']),
            },
            'items': items_payload,
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)

