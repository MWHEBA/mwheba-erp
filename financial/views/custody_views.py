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

from decimal import Decimal
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

from users.decorators import require_permission
from core.enums.document_types import DocumentType
from core.services.sequence_service import SequenceService
from financial.models.currency import Currency
from financial.models.chart_of_accounts import ChartOfAccounts
from financial.models.cost_center import CostCenter
from financial.models.custody import (
    EmployeeCustodyAdvance,
    CustodyAdvanceStatus,
    SettlementLineType,
    PettyCashSettlement,
    SettlementStatus,
    PettyCashSettlementLine,
    SettlementLineStatus,
    CustodyTransfer,
    PettyCashCount,
)
from financial.services.custody_service import CustodyManagementService
from hr.models.employee import Employee
from hr.models.work_location import WorkLocation
from supplier.models import Supplier


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

    employees = Employee.objects.filter(is_active=True).order_by("name")

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

        with transaction.atomic():
            advance = EmployeeCustodyAdvance.objects.create(
                advance_number=adv_number,
                employee=employee,
                user=request.user,
                source_treasury=treasury,
                amount=amount,
                current_balance=amount,
                currency=currency,
                exchange_rate=currency.exchange_rate if hasattr(currency, 'exchange_rate') else Decimal("1.000000"),
                issue_date=timezone.now().date(),
                due_date=due_date or (timezone.now().date() + timezone.timedelta(days=30)),
                purpose=purpose,
                is_per_diem_split=is_per_diem,
                per_diem_amount=per_diem_amount,
                status=CustodyAdvanceStatus.ACTIVE,
                notes=notes,
            )

            # إذا رُفع ملف سند الأمانة
            if "signed_acknowledgment_file" in request.FILES:
                advance.signed_acknowledgment_file = request.FILES["signed_acknowledgment_file"]
                advance.save(update_fields=["signed_acknowledgment_file"])

            # صرف العهدة وتوليد القيد المحاسبي
            CustodyManagementService.disburse_advance(
                advance=advance,
                disbursed_by_user=request.user,
                notes=notes
            )

        messages.success(request, f"تم تسجيل وصرف العهدة النقدية بنجاح برقم {adv_number}")
        return redirect("financial:custody_advance_list")

    employees = Employee.objects.filter(is_active=True).order_by("name")
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
    return render(request, "financial/custody/settlement_list.html", context)


@login_required
def settlement_create_view(request):
    """إنشاء وتسجيل سند تسوية عهدة متعدد البنود والضرائب والموردين"""
    if request.method == "POST":
        employee_id = request.POST.get("employee_id")
        advance_id = request.POST.get("custody_advance_id")
        settlement_date = request.POST.get("settlement_date") or timezone.now().date()
        returned_cash = Decimal(request.POST.get("cash_returned_to_treasury", "0") or "0")
        notes = request.POST.get("notes", "")

        employee = get_object_or_404(Employee, id=employee_id)
        advance = get_object_or_404(EmployeeCustodyAdvance, id=advance_id) if advance_id else None

        set_number = SequenceService.get_next_number(DocumentType.CUSTODY_SETTLEMENT)

        with transaction.atomic():
            settlement = PettyCashSettlement.objects.create(
                settlement_number=set_number,
                custody_advance=advance,
                employee=employee,
                settlement_date=settlement_date,
                cash_returned_to_treasury=returned_cash,
                status=SettlementStatus.SUBMITTED,
                submitted_by=request.user,
                notes=notes,
            )

            # معالجة بنود التسوية الديناميكية
            line_types = request.POST.getlist("line_type[]")
            expense_accounts = request.POST.getlist("expense_account_id[]")
            amounts = request.POST.getlist("amount[]")
            tax_amounts = request.POST.getlist("tax_amount[]")
            wht_rates = request.POST.getlist("wht_rate[]")
            wht_amounts = request.POST.getlist("wht_amount[]")
            discount_amounts = request.POST.getlist("discount_amount[]")
            invoice_numbers = request.POST.getlist("invoice_number[]")
            invoice_dates = request.POST.getlist("invoice_date[]")
            descriptions = request.POST.getlist("description[]")
            cost_center_ids = request.POST.getlist("cost_center_id[]")
            supplier_ids = request.POST.getlist("supplier_id[]")

            total_expenses = Decimal("0.00")
            total_vat = Decimal("0.00")
            total_wht = Decimal("0.00")
            total_discounts = Decimal("0.00")

            func_currency = Currency.objects.filter(is_functional=True).first()

            for i in range(len(amounts)):
                if not amounts[i] or Decimal(amounts[i]) <= 0:
                    continue

                amt = Decimal(amounts[i])
                tax_amt = Decimal(tax_amounts[i]) if i < len(tax_amounts) and tax_amounts[i] else Decimal("0.00")
                wht_r = Decimal(wht_rates[i]) if i < len(wht_rates) and wht_rates[i] else Decimal("0.00")
                wht_amt = Decimal(wht_amounts[i]) if i < len(wht_amounts) and wht_amounts[i] else Decimal("0.00")
                disc_amt = Decimal(discount_amounts[i]) if i < len(discount_amounts) and discount_amounts[i] else Decimal("0.00")

                acc_id = expense_accounts[i] if i < len(expense_accounts) and expense_accounts[i] else None
                expense_acc = ChartOfAccounts.objects.filter(id=acc_id).first() if acc_id else None

                cc_id = cost_center_ids[i] if i < len(cost_center_ids) and cost_center_ids[i] else None
                cost_cntr = CostCenter.objects.filter(id=cc_id).first() if cc_id else None

                sup_id = supplier_ids[i] if i < len(supplier_ids) and supplier_ids[i] else None
                sup_obj = Supplier.objects.filter(id=sup_id).first() if sup_id else None

                PettyCashSettlementLine.objects.create(
                    settlement=settlement,
                    line_number=i + 1,
                    line_type=line_types[i] if i < len(line_types) and line_types[i] else SettlementLineType.DIRECT_EXPENSE,
                    expense_account=expense_acc,
                    cost_center=cost_cntr,
                    supplier=sup_obj,
                    invoice_number=invoice_numbers[i] if i < len(invoice_numbers) else "",
                    invoice_date=invoice_dates[i] if (i < len(invoice_dates) and invoice_dates[i]) else timezone.now().date(),
                    currency=func_currency,
                    amount=amt,
                    tax_amount=tax_amt,
                    wht_rate=wht_r,
                    wht_amount=wht_amt,
                    discount_amount=disc_amt,
                    description=descriptions[i] if i < len(descriptions) else "مصروف عهدة",
                )

                total_expenses += amt
                total_vat += tax_amt
                total_wht += wht_amt
                total_discounts += disc_amt

            settlement.total_expenses = total_expenses
            settlement.total_tax = total_vat
            settlement.total_wht = total_wht
            settlement.total_discounts_earned = total_discounts
            settlement.total_settled_amount = total_expenses
            settlement.save()

            # ترحيل التسوية فورياً إذا كان يملك الصلاحية
            if request.POST.get("action") == "post_now" and (request.user.is_superuser or request.user.has_perm("financial.add_journalentry")):
                CustodyManagementService.post_settlement(
                    settlement=settlement,
                    approved_by_user=request.user,
                    notes=notes
                )
                messages.success(request, f"تم حفظ وترحيل سند تسوية العهدة بنجاح برقم {set_number}")
            else:
                messages.success(request, f"تم حفظ سند تسوية العهدة بنجاح برقم {set_number} وبانتظار الاعتماد.")

        return redirect("financial:custody_settlement_list")

    employees = Employee.objects.filter(is_active=True).order_by("name")
    advances = EmployeeCustodyAdvance.objects.filter(status__in=[CustodyAdvanceStatus.ACTIVE, CustodyAdvanceStatus.PARTIALLY_SETTLED])
    expense_accounts = ChartOfAccounts.objects.filter(account_type__category="expense", is_active=True).order_by("code")
    cost_centers = CostCenter.objects.filter(is_active=True).order_by("code")
    suppliers = Supplier.objects.filter(is_active=True).order_by("name")

    context = {
        "page_title": "إنشاء سند تسوية عهدة نقدية",
        "page_subtitle": "تسجيل فواتير ومصروفات التسوية واحتساب الضرائب والخصومات بدقة",
        "page_icon": "fas fa-receipt",
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": "سندات التسوية", "url": reverse("financial:custody_settlement_list"), "icon": "fas fa-receipt"},
            {"title": "إنشاء تسوية جديدة", "active": True},
        ],
        "employees": employees,
        "advances": advances,
        "expense_accounts": expense_accounts,
        "cost_centers": cost_centers,
        "suppliers": suppliers,
        "line_types": SettlementLineType.choices,
    }
    return render(request, "financial/custody/settlement_form.html", context)


@login_required
@require_POST
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
def transfer_create_view(request):
    """تسجيل مناقلة عهدة جديدة بين موظفين"""
    if request.method == "POST":
        from_emp_id = request.POST.get("from_employee_id")
        to_emp_id = request.POST.get("to_employee_id")
        amount = Decimal(request.POST.get("amount", "0"))
        notes = request.POST.get("notes", "")

        from_emp = get_object_or_404(Employee, id=from_emp_id)
        to_emp = get_object_or_404(Employee, id=to_emp_id)
        func_currency = Currency.objects.filter(is_functional=True).first()

        trf_num = SequenceService.get_next_number(DocumentType.CUSTODY_TRANSFER)

        with transaction.atomic():
            transfer = CustodyTransfer.objects.create(
                transfer_number=trf_num,
                from_employee=from_emp,
                to_employee=to_emp,
                amount=amount,
                currency=func_currency,
                transfer_date=timezone.now().date(),
                notes=notes,
            )

            CustodyManagementService.transfer_custody(
                transfer=transfer,
                approved_by_user=request.user,
                notes=notes
            )

        messages.success(request, f"تم اعتماد مناقلة العهدة بنجاح برقم {trf_num}")
        return redirect("financial:custody_transfer_list")

    employees = Employee.objects.filter(is_active=True).order_by("name")
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
        gl_balance = Decimal(request.POST.get("gl_balance", "0"))
        pending_vouchers = Decimal(request.POST.get("pending_vouchers_amount", "0"))
        notes = request.POST.get("notes", "")

        employee = get_object_or_404(Employee, id=employee_id)
        custody_acc = ChartOfAccounts.objects.filter(id=account_id).first() if account_id else None

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

    employees = Employee.objects.filter(is_active=True).order_by("name")
    custody_accounts = ChartOfAccounts.objects.filter(is_custody_account=True, is_active=True).order_by("code")

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
