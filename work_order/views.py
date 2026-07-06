from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from decimal import Decimal
from django.db.models import Sum

from .models import WorkOrder
from .forms import WorkOrderForm
from .decorators import check_work_orders_enabled
from client.models import Customer, CustomerPayment
from sale.models import Sale, SalePayment, Quotation
from purchase.models import Purchase
from financial.models import JournalEntry, ChartOfAccounts
from governance.services.accounting_gateway import create_customer_payment_entry


@login_required
@check_work_orders_enabled
def work_order_list(request):
    """
    قائمة أوامر الشغل
    """
    if not request.user.has_perm('sale.view_quotation') and not request.user.is_superuser and not request.user.is_admin:
        return render(request, "core/permission_denied.html", {
            "title": _("غير مصرح"), "message": _("ليس لديك صلاحية لعرض أوامر الشغل")
        })

    queryset = WorkOrder.objects.all().select_related('customer', 'created_by')
    
    # الفلاتر
    status = request.GET.get('status')
    if status:
        queryset = queryset.filter(status=status)
        
    customer_id = request.GET.get('customer')
    if customer_id:
        queryset = queryset.filter(customer_id=customer_id)

    from .forms import WorkOrderForm
    context = {
        "work_orders": queryset,
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
            {"title": _("المبيعات"), "url": reverse("sale:sale_list"), "icon": "fas fa-shopping-cart"},
            {"title": _("أوامر الشغل"), "active": True},
        ]
    }
    return render(request, "work_order/work_order_list.html", context)


@login_required
@check_work_orders_enabled
def work_order_create(request):
    """
    إنشاء أمر شغل جديد
    """
    if not request.user.has_perm('sale.add_quotation') and not request.user.is_superuser and not request.user.is_admin:
        return render(request, "core/permission_denied.html", {
            "title": _("غير مصرح"), "message": _("ليس لديك صلاحية لإنشاء أمر شغل")
        })

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
def work_order_edit(request, pk):
    """
    تعديل أمر شغل
    """
    if not request.user.has_perm('sale.change_quotation') and not request.user.is_superuser and not request.user.is_admin:
        return render(request, "core/permission_denied.html", {
            "title": _("غير مصرح"), "message": _("ليس لديك صلاحية لتعديل أمر شغل")
        })

    work_order = get_object_or_404(WorkOrder, pk=pk)

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
def work_order_delete(request, pk):
    """
    حذف أمر شغل
    """
    if not request.user.has_perm('sale.delete_quotation') and not request.user.is_superuser and not request.user.is_admin:
        return render(request, "core/permission_denied.html", {
            "title": _("غير مصرح"), "message": _("ليس لديك صلاحية لحذف أمر شغل")
        })

    work_order = get_object_or_404(WorkOrder, pk=pk)
    
    # فحص الارتباطات قبل الحذف
    if work_order.sales.exists() or work_order.quotations.exists() or work_order.purchases.exists() or work_order.payments.exists():
        messages.error(request, _("لا يمكن حذف أمر الشغل هذا لوجود مستندات مالية أو تجارية مرتبطة به."))
        return redirect("work_order:work_order_detail", pk=work_order.pk)

    if request.method == "POST":
        number = work_order.number
        work_order.delete()
        messages.success(request, _("تم حذف أمر الشغل {} بنجاح.").format(number))
        return redirect("work_order:work_order_list")

    return render(request, "work_order/work_order_confirm_delete.html", {"work_order": work_order})


@login_required
@check_work_orders_enabled
def work_order_detail(request, pk):
    """
    تفاصيل أمر الشغل ولوحة معلومات مركز التكلفة
    """
    if not request.user.has_perm('sale.view_quotation') and not request.user.is_superuser and not request.user.is_admin:
        return render(request, "core/permission_denied.html", {
            "title": _("غير مصرح"), "message": _("ليس لديك صلاحية لعرض تفاصيل أمر الشغل")
        })

    work_order = get_object_or_404(WorkOrder, pk=pk)

    # 1. عروض الأسعار المرتبطة
    quotations = work_order.quotations.all()

    # 2. فواتير المبيعات المرتبطة (إيرادات)
    sales = work_order.sales.filter(status='confirmed')
    sales_total = sales.aggregate(total=Sum('total'))['total'] or Decimal('0.00')

    # 3. فواتير المشتريات المرتبطة (تكلفة خامات)
    purchases = work_order.purchases.filter(status='confirmed')
    purchases_total = purchases.aggregate(total=Sum('total'))['total'] or Decimal('0.00')

    # 4. المصروفات والإيرادات المباشرة
    financial_transactions = work_order.financial_transactions.filter(status='approved')
    incomes_direct = financial_transactions.filter(transaction_type='income')
    incomes_direct_total = incomes_direct.aggregate(total=Sum('net_amount'))['total'] or Decimal('0.00')
    
    expenses_direct = financial_transactions.filter(transaction_type='expense')
    expenses_direct_total = expenses_direct.aggregate(total=Sum('net_amount'))['total'] or Decimal('0.00')

    # 5. الحسابات المالية الكلية
    total_revenue = sales_total + incomes_direct_total
    total_cost = purchases_total + expenses_direct_total
    net_profit = total_revenue - total_cost
    profit_margin = (net_profit / total_revenue * 100) if total_revenue > 0 else Decimal('0.00')

    # 6. نظام الدفعات المقدمة (الحصالة)
    payments = work_order.payments.all()
    total_deposits = payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    # حساب المستهلك من الدفعات المقدمة في فواتير المبيعات
    total_allocated = Decimal('0.00')
    for payment in payments:
        total_allocated += payment.allocations.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
    remaining_deposit = total_deposits - total_allocated

    # حسابات نقدية/بنكية لتسجيل الدفعات
    cash_accounts = ChartOfAccounts.objects.filter(
        account_type__code__in=['cash', 'bank'],
        is_active=True
    ).order_by('code')

    context = {
        "work_order": work_order,
        "quotations": quotations,
        "sales": sales,
        "purchases": purchases,
        "financial_transactions": financial_transactions,
        "incomes_direct": incomes_direct,
        "expenses_direct": expenses_direct,
        "payments": payments,
        
        "sales_total": sales_total,
        "purchases_total": purchases_total,
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

    context.update({
        "title": _("تفاصيل أمر الشغل - {}").format(work_order.number),
        "page_title": work_order.number,
        "page_subtitle": _('العميل: <a href="{}" class="text-decoration-none fw-bold text-primary"><i class="fas fa-user-tie me-1"></i>{}</a>').format(
            reverse("client:customer_detail", kwargs={"pk": work_order.customer.id}),
            work_order.customer.name
        ),
        "page_icon": "fas fa-briefcase",
        "active_menu": "work_orders",
        "header_badges": [
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
            {
                "text": _("التكلفة التقديرية: {} {}").format(est_cost_str, currency),
                "icon": "fas fa-calculator",
                "class": "bg-light text-primary border",
            }
        ],
        "header_buttons": [
            {
                "dropdown": True,
                "chic_dropdown": True,
                "icon": "fa-plus",
                "text": _("إضافة"),
                "class": "btn-primary",
                "items": [
                    {
                        "url": reverse("sale:quotation_create") + f"?work_order={work_order.id}",
                        "icon": "fa-file-signature",
                        "icon_class": "text-warning bg-warning-subtle",
                        "text": _("عرض سعر"),
                        "desc": _("إنشاء عرض سعر جديد لهذا العميل مرتبط بأمر الشغل"),
                    },
                    {
                        "url": reverse("sale:sale_create") + f"?work_order={work_order.id}",
                        "icon": "fa-file-invoice-dollar",
                        "icon_class": "text-success bg-success-subtle",
                        "text": _("فاتورة مبيعات"),
                        "desc": _("إصدار فاتورة مبيعات جديدة لطلب مستحقات أمر الشغل"),
                    },
                    {
                        "url": reverse("purchase:purchase_create") + f"?work_order={work_order.id}",
                        "icon": "fa-file-invoice",
                        "icon_class": "text-danger bg-danger-subtle",
                        "text": _("فاتورة مشتريات"),
                        "desc": _("تسجيل فاتورة شراء مواد أو خدمات خاصة بأمر الشغل"),
                    },
                    {
                        "divider": True,
                    },
                    {
                        "url": "#",
                        "icon": "fa-piggy-bank",
                        "icon_class": "text-info bg-info-subtle",
                        "text": _("تسجيل دفعة مقدمة"),
                        "desc": _("تسجيل دفعة مقدمة (عربون) من العميل لحساب أمر الشغل"),
                        "data_toggle": "modal",
                        "data_target": "#recordDepositModal",
                    }
                ]
            },
            {
                "url": "#",
                "icon": "fa-ellipsis-v",
                "text": "",
                "class": "btn-outline-secondary",
                "id": "actions-menu-btn",
                "toggle": "modal",
                "target": "#actionsModal",
            }
        ],
        "breadcrumb_items": [
            {"title": _("الرئيسية"), "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": _("أوامر الشغل"), "url": reverse("work_order:work_order_list")},
            {"title": work_order.number, "active": True},
        ]
    })
    return render(request, "work_order/work_order_detail.html", context)


@login_required
@check_work_orders_enabled
def work_order_record_deposit(request, pk):
    """
    تسجيل دفعة مقدمة (عربون) لأمر الشغل
    """
    if not request.user.has_perm('sale.add_quotation') and not request.user.is_superuser and not request.user.is_admin:
        return render(request, "core/permission_denied.html", {
            "title": _("غير مصرح"), "message": _("ليس لديك صلاحية لتسجيل مدفوعات")
        })

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
