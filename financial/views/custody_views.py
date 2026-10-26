"""
Enterprise Custody Management Views (شاشات وإجراءات إدارة وحوكمة عهد الموظفين)
----------------------------------------------------------------------------
Covers:
- Employee Custody Advances (قائمة وإنشاء وتفاصيل وصرف العهد والسلف)
- Petty Cash Settlements (قائمة وإنشاء واعتماد وترحيل التسويات متعددة السطور)
- Custody Transfers (مناقلات العهد والأمانات بين الموظفين)
- Physical Cash Counts (محاضر الجرد الفعلي وفئات النقدية)
- Printing Templates (طباعة سندات الصرف والتسوية A4 وحراري 80mm)
"""

from decimal import Decimal, InvalidOperation
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_GET
from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.utils import timezone
from django.urls import reverse
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Sum, Q, Count

from django.template.loader import render_to_string
from users.decorators import require_permission
from core.enums.document_types import DocumentType
from core.services.sequence_service import SequenceService
from financial.models.currency import Currency
from financial.models.chart_of_accounts import ChartOfAccounts
from financial.models.cost_center import CostCenter
from financial.models.journal_entry import JournalEntry
from financial.models.custody import (
    EmployeeCustodyAdvance,
    CustodyAdvanceStatus,
    SettlementLineType,
    PettyCashSettlement,
    SettlementStatus,
    PettyCashSettlementLine,
    SettlementLineStatus,
    VarianceRouting,
    CustodyTransfer,
    PettyCashCount,
)
from financial.services.custody_service import CustodyManagementService
from hr.models.employee import Employee
from hr.models.work_location import WorkLocation
from supplier.models import Supplier
from purchase.models import Purchase


def safe_decimal(val, default="0.00") -> Decimal:
    """تحويل آمن إلى Decimal لمنع أخطاء 500 InvalidOperation"""
    if val is None:
        return Decimal(default)
    try:
        val_str = str(val).strip().replace(",", "")
        return Decimal(val_str) if val_str else Decimal(default)
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)



# =============================================================================
# 1. العهد والسلف النقدية (Employee Custody Advances)
# =============================================================================

@login_required
def advance_list_view(request):
    """عرض قائمة العهد النقدية مع الفلاتر والإحصائيات والبحث"""
    qs = EmployeeCustodyAdvance.objects.select_related(
        "employee", "source_treasury", "currency", "work_location"
    ).all().order_by("-issue_date", "-id")

    # فلاتر البحث
    search_q = request.GET.get("q", "").strip()
    if search_q:
        qs = qs.filter(
            Q(advance_number__icontains=search_q)
            | Q(employee__name__icontains=search_q)
            | Q(purpose__icontains=search_q)
        )

    status_filter = request.GET.get("status")
    if status_filter:
        qs = qs.filter(status=status_filter)

    employee_filter = request.GET.get("employee")
    if employee_filter:
        qs = qs.filter(employee_id=employee_filter)

    # إحصائيات سريعة
    total_active_advances = qs.filter(status=CustodyAdvanceStatus.ACTIVE).aggregate(tot=Sum("amount"))["tot"] or Decimal("0.00")
    total_current_balance = qs.filter(status__in=[CustodyAdvanceStatus.ACTIVE, CustodyAdvanceStatus.PARTIALLY_SETTLED]).aggregate(tot=Sum("current_balance"))["tot"] or Decimal("0.00")
    count_overdue = qs.filter(status=CustodyAdvanceStatus.OVERDUE).count()

    paginator = Paginator(qs, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    employees = Employee.objects.active().order_by("name")

    context = {
        "page_title": "إدارة عهد وسلف الموظفين",
        "page_subtitle": "متابعة أرصدة العهد النقدية المؤقتة والمستديمة وحالات الصرف والتسوية",
        "page_icon": "fas fa-hand-holding-usd",
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": "الإدارة المالية", "url": reverse("financial:chart_of_accounts_list"), "icon": "fas fa-money-bill-wave"},
            {"title": "عهد وسلف الموظفين", "active": True},
        ],
        "header_buttons": [
            {
                "url": reverse("financial:custody_advance_create"),
                "icon": "fas fa-plus",
                "text": "طلب صرف عهدة جديدة",
                "class": "btn-primary",
            },
            {
                "url": reverse("financial:custody_settlement_list"),
                "icon": "fas fa-receipt",
                "text": "سندات التسوية",
                "class": "btn-outline-secondary me-2",
            },
        ],
        "advances": page_obj,
        "page_obj": page_obj,
        "employees": employees,
        "total_active_advances": total_active_advances,
        "total_current_balance": total_current_balance,
        "count_overdue": count_overdue,
        "selected_status": status_filter,
        "selected_employee": employee_filter,
        "search_q": search_q,
    }

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        table_html = render_to_string("financial/custody/partials/advance_table.html", context, request=request)
        pagination_html = render_to_string("partials/pagination.html", {"page_obj": page_obj}, request=request)
        summary_html = render_to_string("financial/custody/partials/advance_summary.html", context, request=request)
        return JsonResponse({
            "table_html": table_html,
            "pagination_html": pagination_html,
            "summary_html": summary_html,
        })

    return render(request, "financial/custody/advance_list.html", context)


@login_required
def advance_create_view(request):
    """طلب وتسجيل صرف عهدة نقدية جديدة للموظف"""
    if request.method == "POST":
        employee_id = request.POST.get("employee_id")
        treasury_id = request.POST.get("source_treasury_id")
        amount = Decimal(request.POST.get("amount", "0"))
        currency_id = request.POST.get("currency_id")
        due_date = request.POST.get("due_date")
        purpose = request.POST.get("purpose", "").strip()
        is_per_diem = request.POST.get("is_per_diem_split") == "on"
        per_diem_amount = Decimal(request.POST.get("per_diem_amount", "0")) if is_per_diem else Decimal("0.00")
        notes = request.POST.get("notes", "")

        employee = get_object_or_404(Employee, id=employee_id)
        treasury = get_object_or_404(ChartOfAccounts, id=treasury_id)
        currency = get_object_or_404(Currency, id=currency_id) if currency_id else Currency.objects.filter(is_functional=True).first()

        adv_number = SequenceService.get_next_number(DocumentType.CUSTODY_ADVANCE)

        # R1: تحديد سعر الصرف للعملة الأجنبية بدقة من المدخلات أو جدول أسعار الصرف الرسمي
        rate_from_post = request.POST.get("exchange_rate")
        calc_rate = None
        if rate_from_post:
            try:
                parsed_rate = Decimal(str(rate_from_post).strip())
                if parsed_rate > 0:
                    calc_rate = parsed_rate
            except Exception:
                calc_rate = None

        if not calc_rate:
            from financial.services.exchange_rate_service import ExchangeRateService
            calc_rate = ExchangeRateService.get_exchange_rate(currency, date=timezone.localdate())

        if not calc_rate or calc_rate <= 0:
            calc_rate = Decimal("1.000000")

        work_location_id = request.POST.get("work_location_id")
        work_location = WorkLocation.objects.filter(id=work_location_id).first() if work_location_id else None

        with transaction.atomic():
            advance = EmployeeCustodyAdvance.objects.create(
                advance_number=adv_number,
                employee=employee,
                user=request.user,
                source_treasury=treasury,
                work_location=work_location,
                amount=amount,
                settlement_principal_amount=amount - (per_diem_amount if is_per_diem else Decimal("0.00")),
                current_balance=amount - (per_diem_amount if is_per_diem else Decimal("0.00")),
                currency=currency,
                exchange_rate=calc_rate,
                issue_date=timezone.localdate(),
                due_date=due_date or (timezone.localdate() + timezone.timedelta(days=30)),
                purpose=purpose,
                is_per_diem_split=is_per_diem,
                per_diem_amount=per_diem_amount,
                status=CustodyAdvanceStatus.PENDING_APPROVAL,
                notes=notes,
            )

            # إذا رُفع ملف سند الأمانة المسبق
            if "signed_acknowledgment_file" in request.FILES:
                advance.signed_acknowledgment_file = request.FILES["signed_acknowledgment_file"]
                advance.save(update_fields=["signed_acknowledgment_file"])

        messages.success(request, f"تم تسجيل طلب صرف العهدة النقدية بنجاح برقم {adv_number}. بانتظار صرف النقدية رسمياً من الخزينة.")
        return redirect("financial:custody_advance_list")

    employees = Employee.objects.active().order_by("name")
    treasuries = ChartOfAccounts.objects.filter(is_cash_account=True, is_active=True).order_by("code")
    currencies = Currency.objects.filter(is_active=True).order_by("-is_functional")
    locations = WorkLocation.objects.all()

    context = {
        "page_title": "طلب صرف عهدة نقدية للموظف",
        "page_subtitle": "تسجيل سند صرف سلفة أو عهدة مؤقتة أو مأمورية عمل",
        "page_icon": "fas fa-hand-holding-usd",
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": "عهد وسلف الموظفين", "url": reverse("financial:custody_advance_list"), "icon": "fas fa-hand-holding-usd"},
            {"title": "صرف عهدة جديدة", "active": True},
        ],
        "employees": employees,
        "treasuries": treasuries,
        "currencies": currencies,
        "locations": locations,
    }
    return render(request, "financial/custody/advance_form.html", context)


@login_required
@require_POST
@require_permission("financial.can_disburse_custody")
def advance_disburse_action(request, pk):
    """صرف العهدة النقدية وتوليد القيد المحاسبي وحفظ حركة الخزينة وتثبيت أصل التمويل"""
    from django.core.exceptions import ValidationError
    from financial.services.treasury_security_service import TreasurySecurityService
    advance = get_object_or_404(EmployeeCustodyAdvance, pk=pk)

    source_treasury = advance.source_treasury or AccountRoleRegistry.get_account(AccountRoleNames.DEFAULT_CASH_DRAWER)
    if source_treasury:
        allowed, sec_msg = TreasurySecurityService.can_user_disburse(
            user=request.user,
            treasury_id=source_treasury.id,
            amount=advance.amount * (advance.exchange_rate or Decimal("1.000000")),
        )
        if not allowed:
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"status": "error", "message": f"حظر أمني: {sec_msg}"}, status=403)
            messages.error(request, f"حظر أمني: {sec_msg}")
            return redirect("financial:custody_advance_list")

    if "signed_acknowledgment_file" in request.FILES:
        advance.signed_acknowledgment_file = request.FILES["signed_acknowledgment_file"]
        advance.save(update_fields=["signed_acknowledgment_file"])

    try:
        journal_entry = CustodyManagementService.disburse_advance(
            advance=advance,
            disbursed_by_user=request.user,
            notes=request.POST.get("notes", ""),
        )
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({
                "status": "success",
                "message": f"تم صرف العهدة النقدية {advance.advance_number} بنجاح برقم قيد {journal_entry.number}",
            })
        messages.success(request, f"تم صرف العهدة النقدية {advance.advance_number} بنجاح برقم قيد {journal_entry.number}")
        return redirect("financial:custody_advance_list")
    except ValidationError as ve:
        err_msg = ve.message if hasattr(ve, "message") else str(ve)
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"status": "error", "message": err_msg}, status=400)
        messages.error(request, err_msg)
        return redirect("financial:custody_advance_list")
    except Exception as e:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"status": "error", "message": str(e)}, status=400)
        messages.error(request, f"حدث خطأ أثناء صرف العهدة: {str(e)}")
        return redirect("financial:custody_advance_list")


@login_required
def advance_detail_view(request, pk):
    """عرض تفاصيل سند العهدة النقدية والتسويات والقيود المرتبطة"""
    advance = get_object_or_404(
        EmployeeCustodyAdvance.objects.select_related(
            "employee", "source_treasury", "custody_account", "currency", "user", "work_location"
        ),
        pk=pk,
    )
    settlements = advance.settlements.select_related("employee", "currency", "journal_entry").all().order_by("-settlement_date")
    journal_entries = JournalEntry.objects.filter(reference=advance.advance_number).order_by("-date", "-id")
    treasuries = ChartOfAccounts.objects.filter(is_cash_account=True, is_active=True).order_by("code")

    import uuid
    context = {
        "page_title": f"تفاصيل سند العهدة {advance.advance_number}",
        "page_subtitle": f"الموظف: {advance.employee.name} | الحالة: {advance.get_status_display()}",
        "page_icon": "fas fa-hand-holding-usd",
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": "عهد وسلف الموظفين", "url": reverse("financial:custody_advance_list"), "icon": "fas fa-hand-holding-usd"},
            {"title": advance.advance_number, "active": True},
        ],
        "advance": advance,
        "settlements": settlements,
        "journal_entries": journal_entries,
        "treasuries": treasuries,
        "topup_id_token": f"TOP-{advance.id}-{uuid.uuid4().hex[:8]}",
    }
    return render(request, "financial/custody/advance_detail.html", context)


@login_required
@require_POST
@require_permission("financial.can_disburse_custody")
def advance_top_up_action(request, pk):
    """تعزيز رصيد السلفة النقدية بمبلغ إضافي وتوليد قيد صرف تعزيزي"""
    advance = get_object_or_404(EmployeeCustodyAdvance, pk=pk)
    try:
        additional_amount = safe_decimal(request.POST.get("additional_amount", "0"))
        treasury_account_id = request.POST.get("treasury_account_id")
        treasury_account = ChartOfAccounts.objects.filter(id=treasury_account_id).first() or advance.source_treasury
        notes = request.POST.get("notes", "").strip()
        topup_id = request.POST.get("topup_id", "").strip()
        if not topup_id:
            raise ValidationError("حظر حوكمة: كود طلب التعزيز (topup_id) مفقود في النموذج لمنع تكرار الصرف.")
        journal_entry = CustodyManagementService.top_up_advance(
            advance=advance,
            amount=additional_amount,
            treasury_account=treasury_account,
            user=request.user,
            notes=notes,
            topup_id=topup_id,
        )
        return JsonResponse({
            "status": "success",
            "message": f"تم تعزيز رصيد العهدة بمبلغ {additional_amount} بنجاح برقم قيد {journal_entry.number}",
        })
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)


@login_required
@require_POST
@require_permission("financial.can_disburse_custody")
def advance_cancel_action(request, pk):
    """إلغاء طلب العهدة قبل الصرف الفعلي"""
    advance = get_object_or_404(EmployeeCustodyAdvance, pk=pk)
    if advance.status not in [CustodyAdvanceStatus.DRAFT, CustodyAdvanceStatus.PENDING_APPROVAL]:
        return JsonResponse({"status": "error", "message": "لا يمكن إلغاء عهدة تم صرفها مسبقاً."}, status=400)

    advance.status = CustodyAdvanceStatus.CANCELLED
    advance.save(update_fields=["status"])
    return JsonResponse({
        "status": "success",
        "message": f"تم إلغاء طلب العهدة {advance.advance_number} بنجاح.",
    })


# =============================================================================
# 2. تسويات العهد والمصروفات (Petty Cash Settlements)
# =============================================================================

@login_required
def settlement_list_view(request):
    """عرض قائمة سندات تسوية العهد النقدية"""
    qs = PettyCashSettlement.objects.select_related(
        "employee", "custody_advance", "custody_account", "journal_entry"
    ).all().order_by("-settlement_date", "-id")

    search_q = request.GET.get("q", "").strip()
    if search_q:
        qs = qs.filter(
            Q(settlement_number__icontains=search_q)
            | Q(employee__name__icontains=search_q)
            | Q(notes__icontains=search_q)
        )

    status_filter = request.GET.get("status")
    if status_filter:
        qs = qs.filter(status=status_filter)

    total_posted_settlements = qs.filter(status=SettlementStatus.POSTED).aggregate(tot=Sum("total_settled_amount"))["tot"] or Decimal("0.00")
    pending_count = qs.filter(status=SettlementStatus.SUBMITTED).count()

    paginator = Paginator(qs, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "page_title": "سندات تسوية العهد النقدية",
        "page_subtitle": "مراجعة وتدقيق واعتماد فواتير ومصروفات تسوية عهد الموظفين",
        "page_icon": "fas fa-receipt",
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": "عهد وسلف الموظفين", "url": reverse("financial:custody_advance_list"), "icon": "fas fa-hand-holding-usd"},
            {"title": "سندات التسوية", "active": True},
        ],
        "header_buttons": [
            {
                "url": reverse("financial:custody_settlement_create"),
                "icon": "fas fa-plus",
                "text": "إنشاء سند تسوية جديد",
                "class": "btn-primary",
            },
        ],
        "settlements": page_obj,
        "page_obj": page_obj,
        "total_posted_settlements": total_posted_settlements,
        "pending_count": pending_count,
        "selected_status": status_filter,
        "search_q": search_q,
    }

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        table_html = render_to_string("financial/custody/partials/settlement_table.html", context, request=request)
        pagination_html = render_to_string("partials/pagination.html", {"page_obj": page_obj}, request=request)
        summary_html = render_to_string("financial/custody/partials/settlement_summary.html", context, request=request)
        return JsonResponse({
            "table_html": table_html,
            "pagination_html": pagination_html,
            "summary_html": summary_html,
        })

    return render(request, "financial/custody/settlement_list.html", context)


def _save_settlement_lines_and_totals(request, settlement, is_edit=False):
    """حفظ ومعالجة بنود التسوية والمرفقات واحتساب الإجماليات بدقة ومطابقة"""
    existing_line_files = {}
    if is_edit:
        for ln in settlement.lines.all():
            if ln.receipt_file:
                existing_line_files[str(ln.id)] = ln.receipt_file
        settlement.lines.all().delete()

    line_types = request.POST.getlist("line_type[]") or request.POST.getlist("line_type")
    expense_accounts = request.POST.getlist("expense_account_id[]") or request.POST.getlist("line_expense_acc[]") or request.POST.getlist("expense_account_id")
    amounts = request.POST.getlist("amount[]") or request.POST.getlist("line_amount[]") or request.POST.getlist("amount")
    tax_amounts = request.POST.getlist("tax_amount[]") or request.POST.getlist("line_tax_amount[]") or request.POST.getlist("tax_amount")
    wht_rates = request.POST.getlist("wht_rate[]") or request.POST.getlist("line_wht_rate[]") or request.POST.getlist("wht_rate")
    wht_amounts = request.POST.getlist("wht_amount[]") or request.POST.getlist("line_wht_amount[]") or request.POST.getlist("wht_amount")
    discount_amounts = request.POST.getlist("discount_amount[]") or request.POST.getlist("line_discount_amount[]") or request.POST.getlist("discount_amount")
    line_currency_ids = request.POST.getlist("line_currency_id[]") or request.POST.getlist("line_currency_id")
    line_exchange_rates = request.POST.getlist("line_exchange_rate[]") or request.POST.getlist("line_exchange_rate")
    invoice_numbers = request.POST.getlist("invoice_number[]") or request.POST.getlist("invoice_number")
    invoice_dates = request.POST.getlist("invoice_date[]") or request.POST.getlist("invoice_date")
    descriptions = request.POST.getlist("description[]") or request.POST.getlist("line_desc[]") or request.POST.getlist("description")
    cost_center_ids = request.POST.getlist("cost_center_id[]")
    supplier_ids = request.POST.getlist("supplier_id[]")
    supplier_names = request.POST.getlist("supplier_name[]")
    supplier_tax_ids = request.POST.getlist("supplier_tax_id[]")
    purchase_invoice_ids = request.POST.getlist("purchase_invoice_id[]")
    row_uids = request.POST.getlist("row_uid[]") or request.POST.getlist("row_uid")
    existing_line_ids = request.POST.getlist("existing_line_id[]") or request.POST.getlist("existing_line_id")
    receipt_files = request.FILES.getlist("receipt_file[]")
    all_files_match_rows = (len(receipt_files) == len(amounts))

    for i in range(len(amounts)):
        amt = safe_decimal(amounts[i])
        if amt <= 0:
            continue

        tax_amt = safe_decimal(tax_amounts[i]) if i < len(tax_amounts) else Decimal("0.00")
        wht_r = safe_decimal(wht_rates[i]) if i < len(wht_rates) else Decimal("0.00")
        wht_amt = safe_decimal(wht_amounts[i]) if i < len(wht_amounts) else Decimal("0.00")
        disc_amt = safe_decimal(discount_amounts[i]) if i < len(discount_amounts) else Decimal("0.00")

        acc_id = expense_accounts[i] if i < len(expense_accounts) and expense_accounts[i] else None
        expense_acc = ChartOfAccounts.objects.filter(id=acc_id).first() if acc_id else None

        cc_id = cost_center_ids[i] if i < len(cost_center_ids) and cost_center_ids[i] else None
        cost_cntr = CostCenter.objects.filter(id=cc_id).first() if cc_id else None

        sup_id = supplier_ids[i] if i < len(supplier_ids) and supplier_ids[i] else None
        sup_obj = Supplier.objects.filter(id=sup_id).first() if sup_id else None

        sup_name = supplier_names[i] if i < len(supplier_names) else ""
        sup_tax = supplier_tax_ids[i] if i < len(supplier_tax_ids) else ""

        p_inv_id = purchase_invoice_ids[i] if i < len(purchase_invoice_ids) and purchase_invoice_ids[i] else None
        p_inv = Purchase.objects.filter(id=p_inv_id).first() if p_inv_id else None

        # ربط المرفق بهوية السطر الصريحة لمنع اختلاط المرفقات في الحقول الفارغة
        uid = row_uids[i] if i < len(row_uids) else str(i)
        uploaded_file = (
            request.FILES.get(f"receipt_file_{uid}")
            or request.FILES.get(f"receipt_file_{i}")
            or (receipt_files[i] if all_files_match_rows else None)
        )
        existing_id = existing_line_ids[i] if i < len(existing_line_ids) else None
        line_file = uploaded_file or (existing_line_files.get(str(existing_id)) if existing_id else None)

        line_cur_id = line_currency_ids[i] if i < len(line_currency_ids) and line_currency_ids[i] else None
        line_cur = Currency.objects.filter(id=line_cur_id).first() if line_cur_id else settlement.currency
        line_r_val = safe_decimal(line_exchange_rates[i]) if i < len(line_exchange_rates) and line_exchange_rates[i] else Decimal("1.000000")
        if line_r_val <= 0:
            line_r_val = Decimal("1.000000")

        PettyCashSettlementLine.objects.create(
            settlement=settlement,
            line_number=i + 1,
            line_type=line_types[i] if i < len(line_types) and line_types[i] else SettlementLineType.DIRECT_EXPENSE,
            expense_account=expense_acc,
            cost_center=cost_cntr,
            supplier=sup_obj,
            supplier_name=sup_name,
            supplier_tax_id=sup_tax,
            purchase_invoice=p_inv,
            receipt_file=line_file,
            invoice_number=invoice_numbers[i] if i < len(invoice_numbers) else "",
            invoice_date=invoice_dates[i] if (i < len(invoice_dates) and invoice_dates[i]) else timezone.localdate(),
            currency=line_cur,
            exchange_rate=line_r_val,
            amount=amt,
            tax_amount=tax_amt,
            wht_rate=wht_r,
            wht_amount=wht_amt,
            discount_amount=disc_amt,
            description=descriptions[i] if i < len(descriptions) else "مصروف عهدة",
        )

    # احتساب إجماليات التسوية بدقة عبر محرك الحساب المركزي
    totals = CustodyManagementService.calculate_settlement_totals(settlement)
    settlement.total_expenses = totals.get("total_gross_expenses", Decimal("0.00"))
    settlement.total_tax = totals["total_vat"]
    settlement.total_wht = totals["total_wht"]
    settlement.total_discounts_earned = totals["total_discounts"]
    settlement.total_settled_amount = totals["expenses_absorbed"]
    settlement.refunds_collected = totals["refunds_collected"]
    settlement.eligible_replenishment_amount = totals["eligible_replenishment_amount"]
    settlement.save()


@login_required
def settlement_create_view(request):
    """إنشاء وتسجيل سند تسوية عهدة متعدد البنود والضرائب والموردين والعملات"""
    if request.method == "POST":
        employee_id = request.POST.get("employee_id")
        advance_id = request.POST.get("custody_advance_id") or request.POST.get("advance_id")
        custody_account_id = request.POST.get("custody_account_id")
        settlement_date = request.POST.get("settlement_date") or timezone.localdate()
        returned_cash = safe_decimal(request.POST.get("cash_returned_to_treasury", "0"))
        shortage_amount = safe_decimal(request.POST.get("shortage_amount", "0"))
        variance_routing = request.POST.get("variance_routing", VarianceRouting.HR_DEDUCTION)
        notes = request.POST.get("notes", "")
        action = request.POST.get("action", "")

        advance = get_object_or_404(EmployeeCustodyAdvance, id=advance_id) if advance_id else None
        if not employee_id and advance:
            employee = advance.employee
        else:
            employee = get_object_or_404(Employee, id=employee_id)

        custody_acc = None
        if custody_account_id:
            custody_acc = get_object_or_404(ChartOfAccounts, id=custody_account_id)
        elif advance:
            from financial.services.role_registry import AccountRoleRegistry, AccountRoleNames
            custody_acc = getattr(advance, "custody_account", None) or AccountRoleRegistry.get_account(AccountRoleNames.CUSTODY_TEMPORARY_CONTROL)

        set_number = SequenceService.get_next_number(DocumentType.CUSTODY_SETTLEMENT)
        initial_status = SettlementStatus.DRAFT if action == "save_draft" else SettlementStatus.SUBMITTED

        func_currency = Currency.objects.filter(is_functional=True).first()
        settlement_curr = advance.currency if (advance and advance.currency) else (custody_acc.currency if (custody_acc and custody_acc.currency) else func_currency)

        with transaction.atomic():
            settlement = PettyCashSettlement.objects.create(
                settlement_number=set_number,
                custody_advance=advance,
                custody_account=custody_acc,
                employee=employee,
                currency=settlement_curr,
                settlement_date=settlement_date,
                cash_returned_to_treasury=returned_cash,
                shortage_amount=shortage_amount,
                variance_routing=variance_routing,
                status=initial_status,
                submitted_by=request.user,
                notes=notes,
            )

            _save_settlement_lines_and_totals(request, settlement, is_edit=False)

            # ترحيل التسوية فورياً إذا كان يملك الصلاحية وطلب ذلك
            if action == "post_now" and (request.user.is_superuser or request.user.has_perm("financial.can_post_settlement")):
                CustodyManagementService.post_settlement(
                    settlement=settlement,
                    approved_by_user=request.user,
                    notes=notes
                )
                messages.success(request, f"تم حفظ وترحيل سند تسوية العهدة بنجاح برقم {set_number}")
            elif action == "save_draft":
                messages.success(request, f"تم حفظ مسودة سند تسوية العهدة بنجاح برقم {set_number}. يمكنك استكمال البنود لاحقاً.")
            else:
                messages.success(request, f"تم تسجيل وإرسال سند تسوية العهدة بنجاح برقم {set_number} وبانتظار المراجعة والاعتماد.")

        return redirect("financial:custody_settlement_list")

    employees = Employee.objects.active().order_by("name")
    advances = EmployeeCustodyAdvance.objects.filter(status__in=[CustodyAdvanceStatus.ACTIVE, CustodyAdvanceStatus.PARTIALLY_SETTLED])
    custody_accounts = ChartOfAccounts.objects.filter(is_custody_account=True, is_active=True).order_by("code")
    currencies = Currency.objects.filter(is_active=True).order_by("-is_functional")
    expense_accounts = ChartOfAccounts.objects.filter(account_type__category="expense", is_active=True).order_by("code")
    cost_centers = CostCenter.objects.filter(is_active=True).order_by("code")
    suppliers = Supplier.objects.filter(is_active=True).order_by("name")
    purchases = Purchase.objects.filter(payment_status__in=['pending', 'partial']).order_by('-date')[:50]

    context = {
        "page_title": "إنشاء سند تسوية عهدة نقدية",
        "page_subtitle": "تسجيل فواتير ومصروفات التسوية واحتساب الضرائب والخصومات بدقة",
        "page_icon": "fas fa-receipt",
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": "سندات التسوية", "url": reverse("financial:custody_settlement_list"), "icon": "fas fa-receipt"},
            {"title": "إنشاء تسوية جديدة", "active": True},
        ],
        "today_date": timezone.localdate().strftime("%Y-%m-%d"),
        "employees": employees,
        "advances": advances,
        "custody_accounts": custody_accounts,
        "currencies": currencies,
        "variance_routing_choices": VarianceRouting.choices,
        "expense_accounts": expense_accounts,
        "cost_centers": cost_centers,
        "suppliers": suppliers,
        "purchases": purchases,
        "line_types": SettlementLineType.choices,
    }
    return render(request, "financial/custody/settlement_form.html", context)


@login_required
def settlement_edit_view(request, pk):
    """تعديل واستكمال مسودة سند تسوية العهدة قبل الإرسال للاعتماد"""
    settlement = get_object_or_404(PettyCashSettlement, pk=pk)
    if settlement.status != SettlementStatus.DRAFT:
        messages.error(request, "لا يمكن تعديل سند تسوية غير مسودة؛ السند تم إرساله أو اعتماده مسبقاً.")
        return redirect("financial:custody_settlement_detail", pk=settlement.pk)

    if request.method == "POST":
        action = request.POST.get("action", "")
        settlement_date = request.POST.get("settlement_date") or timezone.localdate()
        returned_cash = safe_decimal(request.POST.get("cash_returned_to_treasury", "0"))
        shortage_amount = safe_decimal(request.POST.get("shortage_amount", "0"))
        variance_routing = request.POST.get("variance_routing", VarianceRouting.HR_DEDUCTION)
        notes = request.POST.get("notes", "")

        with transaction.atomic():
            settlement.settlement_date = settlement_date
            settlement.cash_returned_to_treasury = returned_cash
            settlement.shortage_amount = shortage_amount
            settlement.variance_routing = variance_routing
            settlement.notes = notes
            settlement.save(update_fields=[
                "settlement_date", "cash_returned_to_treasury", "shortage_amount",
                "variance_routing", "notes"
            ])

            _save_settlement_lines_and_totals(request, settlement, is_edit=True)

            if action == "post_now" and (request.user.is_superuser or request.user.has_perm("financial.can_post_settlement")):
                CustodyManagementService.post_settlement(
                    settlement=settlement,
                    approved_by_user=request.user,
                    notes=notes,
                )
                messages.success(request, f"تم اعتماد وترحيل سند تسوية العهدة بنجاح برقم {settlement.settlement_number}")
            elif action in ["post_now", "submit"]:
                settlement.status = SettlementStatus.SUBMITTED
                settlement.submitted_by = request.user
                settlement.save(update_fields=["status", "submitted_by"])
                messages.success(request, f"تم حفظ وإرسال سند تسوية العهدة {settlement.settlement_number} بنجاح للمراجعة والاعتماد.")
            else:  # save_draft
                messages.success(request, f"تم تحديث مسودة سند تسوية العهدة {settlement.settlement_number} بنجاح.")

        return redirect("financial:custody_settlement_detail", pk=settlement.pk)

    employees = Employee.objects.active().order_by("name")
    advances = EmployeeCustodyAdvance.objects.filter(status__in=[CustodyAdvanceStatus.ACTIVE, CustodyAdvanceStatus.PARTIALLY_SETTLED])
    custody_accounts = ChartOfAccounts.objects.filter(is_custody_account=True, is_active=True).order_by("code")
    currencies = Currency.objects.filter(is_active=True).order_by("-is_functional")
    expense_accounts = ChartOfAccounts.objects.filter(account_type__category="expense", is_active=True).order_by("code")
    cost_centers = CostCenter.objects.filter(is_active=True).order_by("code")
    suppliers = Supplier.objects.filter(is_active=True).order_by("name")
    purchases = Purchase.objects.filter(payment_status__in=['pending', 'partial']).order_by('-date')[:50]

    context = {
        "page_title": f"تعديل واستكمال مسودة سند التسوية: {settlement.settlement_number}",
        "page_subtitle": "تعديل بنود ومصروفات ومرفقات المسودة وحفظها أو إرسالها للاعتماد",
        "page_icon": "fas fa-edit",
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": "تسويات العهد", "url": reverse("financial:custody_settlement_list"), "icon": "fas fa-file-invoice-dollar"},
            {"title": settlement.settlement_number, "url": reverse("financial:custody_settlement_detail", kwargs={"pk": settlement.pk}), "icon": "fas fa-receipt"},
            {"title": "تعديل المسودة", "active": True},
        ],
        "today_date": timezone.localdate().strftime("%Y-%m-%d"),
        "settlement": settlement,
        "is_edit": True,
        "employees": employees,
        "advances": advances,
        "custody_accounts": custody_accounts,
        "currencies": currencies,
        "variance_routing_choices": VarianceRouting.choices,
        "expense_accounts": expense_accounts,
        "cost_centers": cost_centers,
        "suppliers": suppliers,
        "purchases": purchases,
        "line_types": SettlementLineType.choices,
    }
    return render(request, "financial/custody/settlement_form.html", context)


@login_required
@require_POST
def settlement_submit_action(request, pk):
    """إرسال سند تسوية مسودة للمراجعة والاعتماد المالي"""
    settlement = get_object_or_404(PettyCashSettlement, pk=pk)
    if settlement.status != SettlementStatus.DRAFT:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"status": "error", "message": "لا يمكن إرسال تسوية غير مسودة للمراجعة."}, status=400)
        messages.error(request, "لا يمكن إرسال تسوية غير مسودة للمراجعة.")
        return redirect("financial:custody_settlement_detail", pk=settlement.pk)

    if not settlement.lines.filter(amount__gt=Decimal("0.00")).exists():
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"status": "error", "message": "لا يمكن إرسال تسوية بدون بنود مصروفات صحيحة."}, status=400)
        messages.error(request, "لا يمكن إرسال تسوية بدون بنود مصروفات صحيحة.")
        return redirect("financial:custody_settlement_detail", pk=settlement.pk)

    settlement.status = SettlementStatus.SUBMITTED
    settlement.submitted_by = request.user
    settlement.save(update_fields=["status", "submitted_by"])

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({
            "status": "success",
            "message": f"تم إرسال سند تسوية العهدة {settlement.settlement_number} بنجاح للمراجعة والاعتماد.",
        })
    messages.success(request, f"تم إرسال سند تسوية العهدة {settlement.settlement_number} للمراجعة والاعتماد.")
    return redirect("financial:custody_settlement_detail", pk=settlement.pk)


@login_required
@require_POST
@require_permission("financial.can_post_settlement")
def settlement_post_action(request, pk):
    """اعتماد وترحيل سند تسوية عهدة عبر AJAX أو الزر السريع"""
    settlement = get_object_or_404(PettyCashSettlement, pk=pk)
    try:
        journal_entry = CustodyManagementService.post_settlement(
            settlement=settlement,
            approved_by_user=request.user,
        )
        return JsonResponse({
            "status": "success",
            "message": f"تم ترحيل تسوية العهدة {settlement.settlement_number} بنجاح برقم قيد {journal_entry.number}",
        })
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)


@login_required
@require_POST
@require_permission("financial.can_reverse_settlement")
def settlement_reverse_action(request, pk):
    """عكس وإلغاء تسوية مرحلة مع استرجاع متناظر لأرصدة السلفة وقيود اليومية"""
    settlement = get_object_or_404(PettyCashSettlement, pk=pk)
    reason = request.POST.get("reason", "").strip() or f"عكس تسوية {settlement.settlement_number}"
    reversal_date = request.POST.get("reversal_date")
    try:
        reversal_entry = CustodyManagementService.reverse_settlement(
            settlement=settlement,
            reversed_by=request.user,
            reason=reason,
            reversal_date=reversal_date,
        )
        return JsonResponse({
            "status": "success",
            "message": f"تم عكس تسوية العهدة {settlement.settlement_number} بنجاح بقيد عكسي رقم {reversal_entry.number}",
        })
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)


@login_required
@require_POST
@require_permission("financial.can_disburse_custody")
def settlement_replenish_action(request, pk):
    """استعاضة منصرفات الصندوق المستديم وإصدار شيك/قيد تمويل من الخزينة"""
    settlement = get_object_or_404(PettyCashSettlement, pk=pk)
    treasury_account_id = request.POST.get("treasury_account_id")
    treasury_account = get_object_or_404(ChartOfAccounts, pk=treasury_account_id) if treasury_account_id else None

    try:
        replenishment_entry = CustodyManagementService.replenish_settlement(
            settlement=settlement,
            treasury_account=treasury_account,
            created_by=request.user,
        )
        return JsonResponse({
            "status": "success",
            "message": f"تمت استعاضة الصندوق المستديم للتسوية {settlement.settlement_number} بنجاح بقيد رقم {replenishment_entry.number}",
        })
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)


@login_required
def settlement_detail_view(request, pk):
    """عرض تفاصيل سند تسوية العهدة والمصروفات والقيود المرتبطة"""
    settlement = get_object_or_404(
        PettyCashSettlement.objects.select_related(
            "employee", "custody_advance", "custody_account", "currency",
            "journal_entry", "reversal_entry", "replenishment_entry", "submitted_by"
        ),
        pk=pk,
    )
    lines = settlement.lines.select_related(
        "expense_account", "cost_center", "supplier", "purchase_invoice"
    ).all().order_by("line_number")
    treasuries = ChartOfAccounts.objects.filter(is_cash_account=True, is_active=True).order_by("code")

    context = {
        "page_title": f"تفاصيل سند تسوية العهدة {settlement.settlement_number}",
        "page_subtitle": f"الموظف: {settlement.employee.name} | الحالة: {settlement.get_status_display()}",
        "page_icon": "fas fa-receipt",
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": "سندات التسوية", "url": reverse("financial:custody_settlement_list"), "icon": "fas fa-receipt"},
            {"title": settlement.settlement_number, "active": True},
        ],
        "settlement": settlement,
        "lines": lines,
        "treasuries": treasuries,
    }
    return render(request, "financial/custody/settlement_detail.html", context)


@login_required
@require_POST
@require_permission("financial.can_post_settlement")
def settlement_reject_action(request, pk):
    """رفض سند تسوية العهدة مع بيان السبب المسبب"""
    settlement = get_object_or_404(PettyCashSettlement, pk=pk)
    if settlement.status != SettlementStatus.SUBMITTED:
        return JsonResponse({"status": "error", "message": "لا يمكن رفض تسوية غير معلقة للمراجعة."}, status=400)

    rejection_reason = request.POST.get("rejection_reason", "").strip()
    if not rejection_reason:
        return JsonResponse({"status": "error", "message": "يرجى كتابة سبب الرفض المسبب إجبارياً."}, status=400)

    settlement.status = SettlementStatus.REJECTED
    settlement.rejection_reason = rejection_reason
    settlement.save(update_fields=["status", "rejection_reason"])

    return JsonResponse({
        "status": "success",
        "message": f"تم رفض سند التسوية {settlement.settlement_number} بنجاح وتدوين السبب.",
    })


@login_required
@require_POST
@require_permission("financial.can_post_settlement")
def settlement_line_review_action(request, pk, line_id):
    """مراجعة واعتماد أو تعديل أو رفض بند تسوية منفرد قبل ترحيل القيد"""
    settlement = get_object_or_404(PettyCashSettlement, pk=pk)
    if settlement.status not in [SettlementStatus.SUBMITTED, SettlementStatus.DRAFT]:
        return JsonResponse({"status": "error", "message": "لا يمكن تعديل بنود تسوية تم اعتمادها أو ترحيلها مسبقاً."}, status=400)

    line = get_object_or_404(PettyCashSettlementLine, pk=line_id, settlement=settlement)
    action_type = (request.POST.get("action_type") or request.POST.get("action") or "approve").lower()
    reason_input = (request.POST.get("rejection_reason") or request.POST.get("reason") or "").strip()

    try:
        with transaction.atomic():
            if action_type == "reject":
                line.status = SettlementLineStatus.REJECTED
                line.approved_amount = Decimal("0.00")
                line.rejection_reason = reason_input or "مرفوض من المراجع المالي"
            elif action_type == "adjust":
                adj_amt = safe_decimal(request.POST.get("approved_amount", line.amount))
                if adj_amt < 0 or adj_amt > line.amount:
                    return JsonResponse({"status": "error", "message": "المبلغ المعتمد يجب أن يكون بين الصفر ومبلغ البند الأصلي."}, status=400)
                line.approved_amount = adj_amt
                line.status = SettlementLineStatus.ADJUSTED if adj_amt < line.amount else SettlementLineStatus.APPROVED
                line.rejection_reason = reason_input
            else:  # approve
                line.status = SettlementLineStatus.APPROVED
                line.approved_amount = line.amount
                line.rejection_reason = ""

            line.save(update_fields=["status", "approved_amount", "rejection_reason"])

            # إعادة احتساب إجماليات التسوية
            totals = CustodyManagementService.calculate_settlement_totals(settlement)
            settlement.total_expenses = totals.get("total_gross_expenses", totals["gross_net_expenses"])
            settlement.total_tax = totals["total_vat"]
            settlement.total_wht = totals["total_wht"]
            settlement.total_discounts_earned = totals["total_discounts"]
            settlement.total_settled_amount = totals["expenses_absorbed"]
            settlement.refunds_collected = totals["refunds_collected"]
            settlement.eligible_replenishment_amount = totals["eligible_replenishment_amount"]
            settlement.save()

        return JsonResponse({
            "status": "success",
            "message": f"تم تحديث حالة البند رقم {line.line_number} بنجاح إلى ({line.get_status_display()}).",
            "line_status": line.status,
            "line_status_display": line.get_status_display(),
            "approved_amount": str(line.approved_amount),
        })
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)


# =============================================================================
# 3. مناقلات العهد النقدية (Custody Transfers)
# =============================================================================

@login_required
def transfer_list_view(request):
    """عرض قائمة مناقلات وتحويلات العهد بين الموظفين"""
    qs = CustodyTransfer.objects.select_related("from_employee", "to_employee", "currency").all().order_by("-transfer_date", "-id")

    paginator = Paginator(qs, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "page_title": "مناقلات وتحويلات العهد النقدية",
        "page_subtitle": "سندات تسليم وتسلم العهد والمناقلة بين الموظفين بالمواقع",
        "page_icon": "fas fa-exchange-alt",
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": "عهد وسلف الموظفين", "url": reverse("financial:custody_advance_list"), "icon": "fas fa-hand-holding-usd"},
            {"title": "مناقلات العهد", "active": True},
        ],
        "header_buttons": [
            {
                "url": reverse("financial:custody_transfer_create"),
                "icon": "fas fa-plus",
                "text": "مناقلة عهدة جديدة",
                "class": "btn-primary",
            },
        ],
        "transfers": page_obj,
        "page_obj": page_obj,
    }
    return render(request, "financial/custody/transfer_list.html", context)


@login_required
@require_permission("financial.can_disburse_custody")
def transfer_create_view(request):
    """تسجيل مناقلة عهدة جديدة بين موظفين"""
    if request.method == "POST":
        from_emp_id = request.POST.get("from_employee_id")
        to_emp_id = request.POST.get("to_employee_id")
        from_adv_id = request.POST.get("from_advance_id")
        to_adv_id = request.POST.get("to_advance_id")
        currency_id = request.POST.get("currency_id")
        amount = safe_decimal(request.POST.get("amount", "0"))
        signed_file = request.FILES.get("signed_transfer_file")
        notes = request.POST.get("notes", "")

        from_emp = get_object_or_404(Employee, id=from_emp_id)
        to_emp = get_object_or_404(Employee, id=to_emp_id)
        from_adv = EmployeeCustodyAdvance.objects.filter(id=from_adv_id).first() if from_adv_id else None
        to_adv = EmployeeCustodyAdvance.objects.filter(id=to_adv_id).first() if to_adv_id else None

        currency = Currency.objects.filter(id=currency_id).first() if currency_id else (
            from_adv.currency if from_adv else Currency.objects.filter(is_functional=True).first()
        )

        trf_num = SequenceService.get_next_number(DocumentType.CUSTODY_TRANSFER)

        try:
            with transaction.atomic():
                transfer = CustodyTransfer.objects.create(
                    transfer_number=trf_num,
                    from_employee=from_emp,
                    to_employee=to_emp,
                    from_advance=from_adv,
                    to_advance=to_adv,
                    amount=amount,
                    currency=currency,
                    signed_transfer_file=signed_file,
                    transfer_date=timezone.localdate(),
                    notes=notes,
                )

                CustodyManagementService.transfer_custody(
                    transfer=transfer,
                    approved_by_user=request.user,
                    notes=notes
                )

            messages.success(request, f"تم اعتماد مناقلة العهدة بنجاح برقم {trf_num}")
            return redirect("financial:custody_transfer_list")
        except Exception as e:
            messages.error(request, f"فشلت المناقلة: {str(e)}")

    employees = Employee.objects.active().order_by("name")
    active_advances = EmployeeCustodyAdvance.objects.filter(
        status__in=[CustodyAdvanceStatus.ACTIVE, CustodyAdvanceStatus.PARTIALLY_SETTLED]
    ).select_related("employee", "currency")
    currencies = Currency.objects.filter(is_active=True).order_by("-is_functional")

    context = {
        "page_title": "مناقلة عهدة نقدية بين موظفين",
        "page_subtitle": "تحويل مسؤولية العهدة المالية من موظف لآخر مع إثبات القيد المحاسبي",
        "page_icon": "fas fa-exchange-alt",
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": "مناقلات العهد", "url": reverse("financial:custody_transfer_list"), "icon": "fas fa-exchange-alt"},
            {"title": "مناقلة جديدة", "active": True},
        ],
        "employees": employees,
        "active_advances": active_advances,
        "currencies": currencies,
    }
    return render(request, "financial/custody/transfer_form.html", context)


# =============================================================================
# 4. محاضر الجرد الفعلي للنقدية (Physical Cash Counts)
# =============================================================================

@login_required
def count_list_view(request):
    """عرض محاضر الجرد الفعلي للعهد النقدية"""
    qs = PettyCashCount.objects.select_related("employee", "custody_account", "auditor").all().order_by("-count_date", "-id")

    paginator = Paginator(qs, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "page_title": "محاضر جرد العهد النقدية",
        "page_subtitle": "الجرد الفعلي المفاجئ والدوري لصناديق العهد وتفقيط النقدية",
        "page_icon": "fas fa-calculator",
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": "عهد وسلف الموظفين", "url": reverse("financial:custody_advance_list"), "icon": "fas fa-hand-holding-usd"},
            {"title": "محاضر الجرد", "active": True},
        ],
        "header_buttons": [
            {
                "url": reverse("financial:custody_count_create"),
                "icon": "fas fa-plus",
                "text": "تسجيل محضر جرد جديد",
                "class": "btn-primary",
            },
        ],
        "counts": page_obj,
        "page_obj": page_obj,
    }
    return render(request, "financial/custody/count_list.html", context)


@login_required
def count_create_view(request):
    """تسجيل محضر جرد فعلي وتفقيط الفئات النقدية"""
    if request.method == "POST":
        employee_id = request.POST.get("employee_id")
        account_id = request.POST.get("custody_account_id")
        employee = get_object_or_404(Employee, id=employee_id)
        custody_acc = ChartOfAccounts.objects.filter(id=account_id).first() if account_id else None
        # احتساب الرصيد الدفتري لحظياً وسيرفر-سايد من دفتر الأستاذ العام لمنع ثغرات التلاعب بالرصيد
        curr_type = "foreign" if (custody_acc and custody_acc.currency and not getattr(custody_acc.currency, "is_functional", True)) else "local"
        gl_balance = custody_acc.get_balance(date_to=timezone.localdate(), include_opening=True, currency_type=curr_type) if custody_acc else Decimal("0.00")
        pending_vouchers = Decimal(request.POST.get("pending_vouchers_amount", "0"))
        notes = request.POST.get("notes", "")

        # تفقيط الفئات النقدية
        denominations_data = {
            "200": int(request.POST.get("denom_200", 0) or 0),
            "100": int(request.POST.get("denom_100", 0) or 0),
            "50": int(request.POST.get("denom_50", 0) or 0),
            "20": int(request.POST.get("denom_20", 0) or 0),
            "10": int(request.POST.get("denom_10", 0) or 0),
            "5": int(request.POST.get("denom_5", 0) or 0),
            "1": int(request.POST.get("denom_1", 0) or 0),
        }

        count_num = SequenceService.get_next_number(DocumentType.CUSTODY_COUNT)

        with transaction.atomic():
            count_obj = PettyCashCount.objects.create(
                count_number=count_num,
                custody_account=custody_acc,
                employee=employee,
                count_date=timezone.now(),
                auditor=request.user,
                gl_balance=gl_balance,
                actual_cash_amount=Decimal("0.00"),
                pending_vouchers_amount=pending_vouchers,
                notes=notes,
            )

            CustodyManagementService.record_petty_cash_count(
                count_obj=count_obj,
                denominations_data=denominations_data,
            )

        messages.success(request, f"تم حفظ محضر الجرد الفعلي بنجاح برقم {count_num} (النتيجة: {count_obj.get_variance_type_display()})")
        return redirect("financial:custody_count_list")

    employees = Employee.objects.active().order_by("name")
    custody_accounts = ChartOfAccounts.objects.filter(is_custody_account=True, is_active=True).order_by("code")
    for ca in custody_accounts:
        try:
            curr_type = "foreign" if (ca.currency and not getattr(ca.currency, "is_functional", True)) else "local"
            ca.cached_gl_balance = ca.get_balance(date_to=timezone.localdate(), include_opening=True, currency_type=curr_type)
        except Exception:
            ca.cached_gl_balance = Decimal("0.00")

    context = {
        "page_title": "تسجيل محضر جرد فعلي للعهدة",
        "page_subtitle": "تفقيط النقدية الموجودة بالدرج ومطابقتها مع الرصيد الدفتري",
        "page_icon": "fas fa-calculator",
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": "محاضر الجرد", "url": reverse("financial:custody_count_list"), "icon": "fas fa-calculator"},
            {"title": "تسجيل جرد جديد", "active": True},
        ],
        "employees": employees,
        "custody_accounts": custody_accounts,
    }
    return render(request, "financial/custody/count_form.html", context)


@login_required
@require_POST
@require_permission("financial.can_post_settlement")
def count_adjust_action(request, pk):
    """تسوية فروق الجرد الفعلي (عجز / زيادة) وقيدها في الحسابات العامة"""
    count = get_object_or_404(PettyCashCount, pk=pk)
    adjustment_type = request.POST.get("adjustment_type", "hr_deduction")
    try:
        journal_entry = CustodyManagementService.adjust_count(
            count=count,
            adjustment_type=adjustment_type,
            user=request.user,
        )
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({
                "status": "success",
                "message": f"تمت تسوية فروق الجرد {count.count_number} بنجاح بقيد رقم {journal_entry.number}",
            })
        messages.success(request, f"تمت تسوية فروق محضر الجرد {count.count_number} بنجاح بقيد رقم {journal_entry.number}")
        return redirect("financial:custody_count_list")
    except Exception as e:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"status": "error", "message": str(e)}, status=400)
        messages.error(request, f"فشلت تسوية فروق الجرد: {e}")
        return redirect("financial:custody_count_list")


# =============================================================================
# 5. شاشات الطباعة الرسمية (Print Views)
# =============================================================================

@login_required
def print_advance_view(request, pk):
    """قالب طباعة سند صرف عهدة نقدية A4 + حراري"""
    advance = get_object_or_404(EmployeeCustodyAdvance, pk=pk)
    is_thermal = request.GET.get("format") == "thermal"

    context = {
        "advance": advance,
        "is_thermal": is_thermal,
        "page_title": f"سند صرف عهدة {advance.advance_number}",
    }
    return render(request, "financial/custody/print_advance.html", context)


@login_required
def print_settlement_view(request, pk):
    """قالب طباعة سند تسوية عهدة ومصروفات A4 + حراري"""
    settlement = get_object_or_404(PettyCashSettlement, pk=pk)
    lines = settlement.lines.select_related("expense_account", "cost_center", "supplier").all()
    is_thermal = request.GET.get("format") == "thermal"

    context = {
        "settlement": settlement,
        "lines": lines,
        "is_thermal": is_thermal,
        "page_title": f"سند تسوية عهدة {settlement.settlement_number}",
    }
    return render(request, "financial/custody/print_settlement.html", context)
