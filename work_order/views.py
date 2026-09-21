from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from users.decorators import require_permission
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.http import JsonResponse
from decimal import Decimal
from django.db.models import Sum, ProtectedError, Q

from .models import WorkOrder
from .forms import WorkOrderForm
from .decorators import check_work_orders_enabled
from customer.models import Customer, CustomerPayment
from sale.models import Sale, SalePayment, Quotation
from sale.models.return_model import SaleReturn
from purchase.models import Purchase
from purchase.models.return_model import PurchaseReturn
from financial.models import JournalEntry, ChartOfAccounts, FinancialTransaction
from governance.services.accounting_gateway import create_customer_payment_entry


@login_required
def api_customer_work_orders(request):
    """
    واجهة برمجية لاسترجاع أوامر الشغل الخاصة بعميل معين للدروب داون Select2
    """
    customer_id = request.GET.get('customer_id')
    q = request.GET.get('q', '').strip()
    
    queryset = WorkOrder.objects.exclude(status='cancelled').select_related('customer')
    if customer_id:
        queryset = queryset.filter(customer_id=customer_id)
        
    if q:
        queryset = queryset.filter(Q(number__icontains=q) | Q(customer__name__icontains=q))
        
    results = []
    for wo in queryset.order_by('-id')[:30]:
        results.append({
            "id": wo.id,
            "text": f"{wo.number} - {wo.customer.name} ({wo.get_status_display()})",
            "number": wo.number,
            "status": wo.status,
        })
        
    return JsonResponse({"results": results})


@login_required
@check_work_orders_enabled
@require_permission('work_order.change_workorder')
def work_order_change_status(request, pk):
    """
    تغيير حالة أمر الشغل مع التحقق من قيود الإلغاء وإعادة الفتح
    """
    work_order = get_object_or_404(WorkOrder, pk=pk)
    
    if request.method == "POST":
        new_status = request.POST.get("status")
        valid_statuses = [choice[0] for choice in WorkOrder.STATUS_CHOICES]
        
        if new_status not in valid_statuses:
            msg = _("حالة أمر الشغل غير صالحة.")
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": False, "message": msg}, status=400)
            messages.error(request, msg)
            return redirect("work_order:work_order_detail", pk=work_order.pk)
            
        # فحص القيود الصارمة عند الإلغاء
        if new_status == "cancelled":
            has_confirmed_sales = work_order.sales.filter(status='confirmed').exists()
            has_confirmed_purchases = work_order.purchases.filter(status='confirmed').exists()
            has_payments = work_order.payments.exists()
            has_approved_transactions = work_order.financial_transactions.filter(status='approved').exists()
            
            if has_confirmed_sales or has_confirmed_purchases or has_payments or has_approved_transactions:
                msg = _("لا يمكن إلغاء أمر الشغل لوجود مستندات مؤكدة أو دفعات مرتبطة به. يرجى إلغاء أو حذف المستندات المرتبطة أولاً.")
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return JsonResponse({"success": False, "message": msg}, status=400)
                messages.error(request, msg)
                return redirect("work_order:work_order_detail", pk=work_order.pk)
                
        work_order.status = new_status
        work_order.save(update_fields=["status", "updated_at"])
        
        success_msg = _("تم تحديث حالة أمر الشغل إلى: {}").format(work_order.get_status_display())
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"success": True, "message": success_msg, "status": work_order.status, "status_display": work_order.get_status_display()})
            
        messages.success(request, success_msg)
        return redirect("work_order:work_order_detail", pk=work_order.pk)
        
    return redirect("work_order:work_order_detail", pk=work_order.pk)


@login_required
@check_work_orders_enabled
@require_permission('work_order.view_workorder')
def work_order_list(request):
    """
    قائمة أوامر الشغل
    """
    queryset = WorkOrder.objects.all().select_related('customer', 'created_by')
    
    # الفلاتر
    status = request.GET.get('status')
    if status:
        queryset = queryset.filter(status=status)
        
    customer_id = request.GET.get('customer')
    if customer_id:
        queryset = queryset.filter(customer_id=customer_id)
        
    from core.utils import paginate_queryset
    pagination_context = paginate_queryset(queryset, request)
    page_obj = pagination_context["page_obj"]

    from .forms import WorkOrderForm
    context = {
        "work_orders": page_obj.object_list,
        "page_obj": page_obj,
        **pagination_context,
        "customers": Customer.objects.filter(is_active=True),
        "status_choices": WorkOrder.STATUS_CHOICES,
        "selected_status": status,
        "selected_customer": customer_id,
        "title": _("قائمة أوامر الشغل"),
        "page_title": _("أوامر الشغل"),
        "page_subtitle": _("متابعة طلبات المبيعات ومراكز تكلفة المشروعات"),
        "page_icon": "fas fa-tasks",
        "active_menu": "work_orders",
        "form": WorkOrderForm(),
        "header_buttons": [
            {
                "url": "#",
                "toggle": "modal",
                "target": "#workOrderModal",
                "icon": "fa-plus",
                "text": _("أمر شغل جديد"),
                "class": "btn-primary",
            }
        ],
        "breadcrumb_items": [
            {"title": _("الرئيسية"), "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": _("الإنتاج والتشغيل"), "url": reverse("work_order:work_order_list"), "icon": "fas fa-cogs"},
            {"title": _("أوامر الشغل"), "active": True},
        ]
    }
    return render(request, "work_order/work_order_list.html", context)


@login_required
@check_work_orders_enabled
@require_permission('work_order.add_workorder')
def work_order_create(request):
    """
    إنشاء أمر شغل جديد
    """
    customer_id = request.GET.get('customer_id')
    quotation_id = request.GET.get('quotation_id')

    if request.method == "POST":
        form = WorkOrderForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    work_order = form.save(commit=False)
                    work_order.created_by = request.user
                    work_order.save()
                    
                    # إذا تم تمرير عرض سعر، اربطه بأمر الشغل هذا
                    if quotation_id:
                        Quotation.objects.filter(id=quotation_id).update(work_order=work_order)
                        
                    messages.success(request, _("تم إنشاء أمر الشغل بنجاح: {}").format(work_order.number))
                    return redirect("work_order:work_order_detail", pk=work_order.pk)
            except Exception as e:
                messages.error(request, _("حدث خطأ أثناء حفظ أمر الشغل: {}").format(str(e)))
        else:
            error_msgs = []
            for field, errors in form.errors.items():
                error_msgs.append(f"{form.fields[field].label}: {', '.join(errors)}")
            messages.error(request, _("خطأ في البيانات: ") + " | ".join(error_msgs))
        return redirect("work_order:work_order_list")
    else:
        # إذا تم الاستدعاء عبر GET، قم بالتحويل لصفحة القائمة مع التمرير
        url = reverse("work_order:work_order_list")
        params = []
        if customer_id:
            params.append(f"customer_id={customer_id}")
        if quotation_id:
            params.append(f"quotation_id={quotation_id}")
        if params:
            url += "?" + "&".join(params)
        return redirect(url)


@login_required
@check_work_orders_enabled
@require_permission('work_order.change_workorder')
def work_order_edit(request, pk):
    """
    تعديل أمر شغل
    """
    work_order = get_object_or_404(WorkOrder, pk=pk)

    if work_order.status in ['completed', 'cancelled'] and not request.user.is_superuser:
        messages.error(request, _("لا يمكن تعديل أمر شغل مكتمل أو ملغي."))
        return redirect("work_order:work_order_detail", pk=work_order.pk)

    if request.method == "POST":
        form = WorkOrderForm(request.POST, instance=work_order)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, _("تم تحديث أمر الشغل بنجاح."))
                return redirect("work_order:work_order_detail", pk=work_order.pk)
            except Exception as e:
                messages.error(request, _("حدث خطأ أثناء حفظ أمر الشغل: {}").format(str(e)))
        else:
            error_msgs = []
            for field, errors in form.errors.items():
                error_msgs.append(f"{form.fields[field].label}: {', '.join(errors)}")
            messages.error(request, _("خطأ في البيانات: ") + " | ".join(error_msgs))
        return redirect("work_order:work_order_list")
    else:
        # التحويل لصفحة القائمة مع التعديل
        return redirect(reverse("work_order:work_order_list") + f"?edit_id={work_order.id}")


@login_required
@check_work_orders_enabled
@require_permission('work_order.delete_workorder')
def work_order_delete(request, pk):
    """
    حذف أمر شغل
    """
    work_order = get_object_or_404(WorkOrder, pk=pk)
    
    # فحص الارتباطات قبل الحذف
    if (
        work_order.sales.exists()
        or work_order.quotations.exists()
        or work_order.purchases.exists()
        or work_order.payments.exists()
        or work_order.financial_transactions.exists()
    ):
        messages.error(request, _("لا يمكن حذف أمر الشغل لوجود مستندات مالية أو تجارية أو مصروفات مرتبطة به."))
        return redirect("work_order:work_order_detail", pk=work_order.pk)

    if request.method == "POST":
        try:
            number = work_order.number
            work_order.delete()
            messages.success(request, _("تم حذف أمر الشغل {} بنجاح.").format(number))
            return redirect("work_order:work_order_list")
        except ProtectedError:
            messages.error(request, _("لا يمكن حذف أمر الشغل لأنه محمي ومقيد بسجلات أخرى في النظام."))
            return redirect("work_order:work_order_detail", pk=work_order.pk)

    return render(request, "work_order/work_order_confirm_delete.html", {"work_order": work_order})


@login_required
@check_work_orders_enabled
@require_permission('work_order.view_workorder')
def work_order_detail(request, pk):
    """
    تفاصيل أمر الشغل ولوحة معلومات مركز التكلفة
    حسابات مالية دقيقة وفق مبدأ الربح التشغيلي الإجمالي الصافي
    """
    work_order = get_object_or_404(WorkOrder.objects.select_related("customer", "created_by"), pk=pk)

    # 1. عروض الأسعار المرتبطة
    quotations = work_order.quotations.select_related("customer", "salesman", "currency", "created_by").all()

    # فحص الصلاحية المالية: تكاليف وهوامش ربح
    can_view_financials = (
        request.user.is_superuser
        or request.user.has_perm('printing_pricing.view_cost_breakdown')
        or request.user.has_perm('printing_pricing.view_profit_margins')
        or request.user.has_perm('financial.view_account')
    )

    if can_view_financials:
        # 2. فواتير المبيعات المؤكدة (الإيراد التشغيلي الصافي قبل الضريبة بالعملة المحلية)
        sales = work_order.sales.select_related("customer", "warehouse", "salesman", "currency", "created_by").filter(status='confirmed')
        sales_operating_egp = Decimal('0.00')
        for s in sales:
            ex_rate = s.exchange_rate if s.exchange_rate and s.exchange_rate > 0 else Decimal('1.000000')
            subtotal_net = (s.subtotal - s.discount) if (s.subtotal is not None and s.discount is not None) else (s.total or Decimal('0.00'))
            sales_operating_egp += (subtotal_net * ex_rate).quantize(Decimal('0.01'))

        # خصم مرتجعات المبيعات المؤكدة
        sale_returns = SaleReturn.objects.filter(sale__in=sales, status='confirmed').select_related("sale")
        sale_returns_operating_egp = Decimal('0.00')
        for sr in sale_returns:
            sr_ex_rate = sr.sale.exchange_rate if sr.sale and sr.sale.exchange_rate and sr.sale.exchange_rate > 0 else Decimal('1.000000')
            sr_subtotal_net = (sr.subtotal - sr.discount) if (sr.subtotal is not None and sr.discount is not None) else (sr.total or Decimal('0.00'))
            sale_returns_operating_egp += (sr_subtotal_net * sr_ex_rate).quantize(Decimal('0.01'))

        net_sales_revenue = sales_operating_egp - sale_returns_operating_egp

        # 3. فواتير المشتريات المؤكدة (تكلفة الخامات والخدمات الخارجية بالعملة المحلية)
        purchases = work_order.purchases.select_related("supplier", "warehouse", "currency", "created_by").filter(status='confirmed')
        raw_materials_egp = Decimal('0.00')
        services_egp = Decimal('0.00')

        for p in purchases:
            p_ex_rate = p.exchange_rate if p.exchange_rate and p.exchange_rate > 0 else Decimal('1.000000')
            p_subtotal_net = (p.subtotal - p.discount) if (p.subtotal is not None and p.discount is not None) else (p.total or Decimal('0.00'))
            amount_egp = (p_subtotal_net * p_ex_rate).quantize(Decimal('0.01'))
            if getattr(p, 'is_service', False):
                services_egp += amount_egp
            else:
                raw_materials_egp += amount_egp

        # خصم مرتجعات المشتريات المؤكدة
        purchase_returns = PurchaseReturn.objects.filter(purchase__in=purchases, status='confirmed').select_related("purchase")
        purchase_returns_egp = Decimal('0.00')
        for pr in purchase_returns:
            pr_ex_rate = pr.purchase.exchange_rate if pr.purchase and pr.purchase.exchange_rate and pr.purchase.exchange_rate > 0 else Decimal('1.000000')
            pr_subtotal_net = (pr.subtotal - pr.discount) if (pr.subtotal is not None and pr.discount is not None) else (pr.total or Decimal('0.00'))
            purchase_returns_egp += (pr_subtotal_net * pr_ex_rate).quantize(Decimal('0.01'))

        net_raw_materials_cost = max(Decimal('0.00'), raw_materials_egp - purchase_returns_egp)
        net_purchases_cost = net_raw_materials_cost + services_egp

        # 4. المعاملات والمصروفات المالية المباشرة المعتمدة
        financial_transactions = work_order.financial_transactions.select_related("category", "account", "to_account", "journal_entry").exclude(status__in=['cancelled', 'rejected'])
        incomes_direct = financial_transactions.filter(transaction_type='income')
        incomes_direct_total = incomes_direct.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        expenses_direct = financial_transactions.filter(transaction_type='expense')
        expenses_direct_total = expenses_direct.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        # 5. الحسابات المالية الكلية للربح التشغيلي
        total_revenue = net_sales_revenue + incomes_direct_total
        total_cost = net_purchases_cost + expenses_direct_total
        net_profit = total_revenue - total_cost
        profit_margin = ((net_profit / total_revenue) * Decimal('100.00')).quantize(Decimal('0.01')) if total_revenue > Decimal('0.00') else Decimal('0.00')

        # 6. نظام الدفعات المقدمة (الحصالة)
        payments = work_order.payments.select_related("financial_account", "created_by").all()
        total_deposits = payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        total_allocated = payments.aggregate(total=Sum('allocated_currency_amount_cached'))['total'] or Decimal('0.00')
        remaining_deposit = max(Decimal('0.00'), total_deposits - total_allocated)
    else:
        # حجب الاستعلامات والتفاصيل المالية لترشيد الأداء وحماية السرية
        sales = work_order.sales.none()
        purchases = work_order.purchases.none()
        financial_transactions = work_order.financial_transactions.none()
        incomes_direct = work_order.financial_transactions.none()
        expenses_direct = work_order.financial_transactions.none()
        sales_operating_egp = None
        net_sales_revenue = None
        net_raw_materials_cost = None
        services_egp = None
        net_purchases_cost = None
        incomes_direct_total = None
        expenses_direct_total = None
        total_revenue = None
        total_cost = None
        net_profit = None
        profit_margin = None
        payments = work_order.payments.none()
        total_deposits = None
        total_allocated = None
        remaining_deposit = None

    # حسابات نقدية/بنكية لتسجيل الدفعات
    from financial.services.account_helper import AccountHelperService
    cash_accounts = AccountHelperService.get_cash_and_bank_accounts() if can_view_financials else []

    context = {
        "work_order": work_order,
        "quotations": quotations,
        "sales": sales,
        "purchases": purchases,
        "financial_transactions": financial_transactions,
        "incomes_direct": incomes_direct,
        "expenses_direct": expenses_direct,
        "payments": payments,
        "can_view_financials": can_view_financials,
        
        "sales_total": net_sales_revenue,
        "sales_operating_egp": sales_operating_egp,
        "sale_returns_operating_egp": sale_returns_operating_egp,
        "net_sales_revenue": net_sales_revenue,
        
        "purchases_total": net_purchases_cost,
        "raw_materials_egp": raw_materials_egp,
        "purchase_returns_egp": purchase_returns_egp,
        "net_raw_materials_cost": net_raw_materials_cost,
        "services_egp": services_egp,
        "net_purchases_cost": net_purchases_cost,
        
        "incomes_direct_total": incomes_direct_total,
        "expenses_direct_total": expenses_direct_total,
        
        "total_revenue": total_revenue,
        "total_cost": total_cost,
        "net_profit": net_profit,
        "profit_margin": profit_margin,
        
        "total_deposits": total_deposits,
        "total_allocated": total_allocated,
        "remaining_deposit": remaining_deposit,
        "cash_accounts": cash_accounts,
    }
    
    from core.models import SystemSetting
    currency = SystemSetting.get_currency_symbol()
    est_cost_val = float(work_order.estimated_cost) if work_order.estimated_cost else 0.0
    est_cost_str = "{:,.2f}".format(est_cost_val)
    if est_cost_str.endswith(".00"):
        est_cost_str = est_cost_str[:-3]

    header_badges = [
        {
            "text": work_order.get_status_display(),
            "class": "bg-success" if work_order.status == 'completed' else (
                "bg-primary" if work_order.status == 'in_progress' else (
                    "bg-warning text-dark" if work_order.status == 'pending' else (
                        "bg-danger" if work_order.status == 'cancelled' else "bg-secondary"
                    )
                )
            ),
        },
        {
            "text": _("تاريخ البدء: {}").format(work_order.start_date.strftime("%Y-%m-%d") if work_order.start_date else "-"),
            "icon": "fas fa-calendar-alt",
            "class": "bg-light text-secondary border",
        },
        {
            "text": _("التسليم المتوقع: {}").format(work_order.delivery_date.strftime("%Y-%m-%d") if work_order.delivery_date else "-"),
            "icon": "fas fa-calendar-check",
            "class": "bg-light text-secondary border",
        },
    ]

    if can_view_financials:
        header_badges.append({
            "text": _("التكلفة التقديرية: {} {}").format(est_cost_str, currency),
            "icon": "fas fa-calculator",
            "class": "bg-light text-primary border",
        })

    is_closed = work_order.status in ['completed', 'cancelled']

    # بناء أزرار الترويسة بحسب الصلاحيات الفردية وحالة أمر الشغل
    dropdown_items = []
    if not is_closed:
        if request.user.is_superuser or request.user.has_perm('sale.add_quotation'):
            dropdown_items.append({
                "url": reverse("sale:quotation_create") + f"?work_order={work_order.id}",
                "icon": "fa-file-signature",
                "icon_class": "text-warning bg-warning-subtle",
                "text": _("عرض سعر"),
                "desc": _("إنشاء عرض سعر جديد لهذا العميل مرتبط بأمر الشغل"),
            })

        if request.user.is_superuser or request.user.has_perm('sale.add_sale'):
            dropdown_items.append({
                "url": reverse("sale:sale_create") + f"?work_order={work_order.id}",
                "icon": "fa-file-invoice-dollar",
                "icon_class": "text-success bg-success-subtle",
                "text": _("فاتورة مبيعات"),
                "desc": _("إصدار فاتورة مبيعات جديدة لطلب مستحقات أمر الشغل"),
            })

        if request.user.is_superuser or request.user.has_perm('purchase.add_purchase'):
            dropdown_items.append({
                "url": reverse("purchase:purchase_create") + f"?work_order={work_order.id}",
                "icon": "fa-file-invoice",
                "icon_class": "text-danger bg-danger-subtle",
                "text": _("فاتورة مشتريات"),
                "desc": _("تسجيل فاتورة شراء مواد أو خدمات خاصة بأمر الشغل"),
            })

        if can_view_financials:
            if request.user.is_superuser or request.user.has_perm('financial.add_expensetransaction'):
                dropdown_items.append({
                    "url": "javascript:void(0)",
                    "onclick": f"openQuickExpenseModal({work_order.id})",
                    "icon": "fa-money-bill-wave",
                    "icon_class": "text-danger bg-danger-subtle",
                    "text": _("مصروف مباشر"),
                    "desc": _("تسجيل مصروف تشغيلي مباشر لحساب أمر الشغل"),
                })

            if request.user.is_superuser or request.user.has_perm('financial.add_incometransaction'):
                dropdown_items.append({
                    "url": "javascript:void(0)",
                    "onclick": f"openQuickIncomeModal({work_order.id})",
                    "icon": "fa-hand-holding-usd",
                    "icon_class": "text-success bg-success-subtle",
                    "text": _("إيراد مباشر"),
                    "desc": _("تسجيل إيراد مباشر لحساب أمر الشغل"),
                })

        can_record_deposit = (
            request.user.is_superuser
            or request.user.has_perm('customer.add_customerpayment')
            or request.user.has_perm('financial.add_receiptvoucher')
            or request.user.has_perm('work_order.change_workorder')
        )
        if can_record_deposit and can_view_financials:
            if dropdown_items:
                dropdown_items.append({"divider": True})
            dropdown_items.append({
                "url": "#",
                "icon": "fa-piggy-bank",
                "icon_class": "text-info bg-info-subtle",
                "text": _("تسجيل دفعة مقدمة"),
                "desc": _("تسجيل دفعة مقدمة (عربون) من العميل لحساب أمر الشغل"),
                "data_toggle": "modal",
                "data_target": "#recordDepositModal",
            })

    status_items = []
    if request.user.is_superuser or request.user.has_perm('work_order.change_workorder'):
        if work_order.status != 'pending':
            status_items.append({
                "url": "javascript:void(0)",
                "onclick": "changeWorkOrderStatus('pending')",
                "icon": "fa-clock",
                "icon_class": "text-warning bg-warning-subtle",
                "text": _("قيد الانتظار"),
                "desc": _("إعادة تعيين أمر الشغل إلى قيد الانتظار"),
            })
        if work_order.status != 'in_progress':
            status_items.append({
                "url": "javascript:void(0)",
                "onclick": "changeWorkOrderStatus('in_progress')",
                "icon": "fa-play",
                "icon_class": "text-primary bg-primary-subtle",
                "text": _("قيد التشغيل"),
                "desc": _("بدء تشغيل وتنفيذ أمر الشغل"),
            })
        if work_order.status != 'completed':
            status_items.append({
                "url": "javascript:void(0)",
                "onclick": "changeWorkOrderStatus('completed')",
                "icon": "fa-check-circle",
                "icon_class": "text-success bg-success-subtle",
                "text": _("مكتمل"),
                "desc": _("إنهاء وإغلاق أمر الشغل بنجاح"),
            })
        if work_order.status != 'cancelled':
            if status_items:
                status_items.append({"divider": True})
            status_items.append({
                "url": "javascript:void(0)",
                "onclick": "changeWorkOrderStatus('cancelled', true)",
                "icon": "fa-ban",
                "icon_class": "text-danger bg-danger-subtle",
                "text": _("إلغاء أمر الشغل"),
                "desc": _("إلغاء أمر الشغل الحالي وإيقافه"),
            })

    header_buttons = []
    if status_items:
        header_buttons.append({
            "dropdown": True,
            "chic_dropdown": True,
            "icon": "fa-traffic-light",
            "text": _("تحديث الحالة"),
            "class": "btn-outline-primary",
            "items": status_items,
        })

    if not is_closed:
        if dropdown_items:
            header_buttons.append({
                "dropdown": True,
                "chic_dropdown": True,
                "icon": "fa-plus",
                "text": _("إضافة"),
                "class": "btn-primary",
                "items": dropdown_items,
            })

        header_buttons.append({
            "url": "#",
            "icon": "fa-ellipsis-v",
            "text": "",
            "class": "btn-outline-secondary",
            "id": "actions-menu-btn",
            "toggle": "modal",
            "target": "#actionsModal",
        })

    context.update({
        "title": _("أمر شغل {}").format(work_order.number),
        "page_title": _("أمر شغل {}").format(work_order.number),
        "page_subtitle": _('العميل: <a href="{}" class="text-decoration-none fw-bold text-primary"><i class="fas fa-user-tie me-1"></i>{}</a>').format(
            reverse("customer:customer_detail", kwargs={"pk": work_order.customer.id}),
            work_order.customer.name
        ),
        "page_icon": "fas fa-briefcase",
        "active_menu": "work_orders",
        "is_closed": is_closed,
        "header_badges": header_badges,
        "header_buttons": header_buttons,
        "breadcrumb_items": [
            {"title": _("الرئيسية"), "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": _("أوامر الشغل"), "url": reverse("work_order:work_order_list")},
            {"title": _("أمر شغل {}").format(work_order.number), "active": True},
        ]
    })
    return render(request, "work_order/work_order_detail.html", context)


@login_required
@check_work_orders_enabled
def work_order_record_deposit(request, pk):
    """
    تسجيل دفعة مقدمة (عربون) لأمر الشغل
    """
    has_deposit_perm = (
        request.user.is_superuser
        or request.user.has_perm('customer.add_customerpayment')
        or request.user.has_perm('financial.add_receiptvoucher')
        or request.user.has_perm('work_order.change_workorder')
    )
    if not has_deposit_perm:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.headers.get('Accept') == 'application/json':
            return JsonResponse({'success': False, 'error': _('ليس لديك صلاحية لتسجيل مدفوعات')}, status=403)
        return render(request, "core/permission_denied.html", {
            "title": _("غير مصرح"), "message": _("ليس لديك صلاحية لتسجيل مدفوعات")
        }, status=403)

    work_order = get_object_or_404(WorkOrder, pk=pk)

    if request.method == "POST":
        amount_str = request.POST.get("amount")
        payment_method = request.POST.get("payment_method")
        payment_date = request.POST.get("payment_date") or timezone.now().date().strftime("%Y-%m-%d")
        reference_number = request.POST.get("reference_number", "")
        notes = request.POST.get("notes", "")

        if not amount_str or not payment_method:
            messages.error(request, _("يرجى ملء جميع الحقول المطلوبة (المبلغ وطريقة الدفع)."))
            return redirect("work_order:work_order_detail", pk=work_order.pk)

        try:
            amount = Decimal(amount_str)
            if amount <= 0:
                raise ValueError(_("المبلغ يجب أن يكون أكبر من صفر"))
                
            with transaction.atomic():
                # 1. إنشاء سجل CustomerPayment
                payment = CustomerPayment.objects.create(
                    customer=work_order.customer,
                    work_order=work_order,
                    amount=amount,
                    payment_date=payment_date,
                    payment_method=payment_method,  # كود الحساب
                    reference_number=reference_number,
                    notes=notes,
                    created_by=request.user
                )

                # 2. إنشاء القيد المحاسبي للدفعة المقدمة
                create_customer_payment_entry(payment, request.user)
                
                messages.success(request, _("تم تسجيل الدفعة المقدمة بنجاح بقيمة {} ج.م وإنشاء القيد المحاسبي.").format(payment.amount))
        except Exception as e:
            messages.error(request, _("حدث خطأ أثناء معالجة الدفعة: {}").format(str(e)))

    return redirect("work_order:work_order_detail", pk=work_order.pk)
