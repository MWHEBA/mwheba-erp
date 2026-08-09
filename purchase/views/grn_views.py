from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.translation import gettext as _
from django.core.paginator import Paginator
from django.urls import reverse
from django.http import JsonResponse

from purchase.models.procurement_models import GoodsReceivedNote, PurchaseOrder
from purchase.models.purchase import Purchase
from purchase.services.grn_application_service import GRNApplicationService
from purchase.services.grni_subledger_service import GRNISubledgerService
from supplier.models import Supplier
from product.models import Warehouse, Product
from financial.exceptions import FinancialCoreError


@login_required
def grn_list(request):
    """عرض أذون استلام المشتريات (GRN)"""
    grns = GoodsReceivedNote.objects.select_related('supplier', 'warehouse', 'purchase', 'purchase_order', 'journal_entry').order_by('-received_date', '-id')

    supplier_id = request.GET.get('supplier')
    if supplier_id:
        grns = grns.filter(supplier_id=supplier_id)

    warehouse_id = request.GET.get('warehouse')
    if warehouse_id:
        grns = grns.filter(warehouse_id=warehouse_id)

    status_filter = request.GET.get('status')
    if status_filter:
        grns = grns.filter(status=status_filter)

    date_from = request.GET.get('date_from')
    if date_from:
        grns = grns.filter(received_date__date__gte=date_from)

    date_to = request.GET.get('date_to')
    if date_to:
        grns = grns.filter(received_date__date__lte=date_to)

    paginator = Paginator(grns, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    suppliers = Supplier.objects.filter(is_active=True)
    warehouses = Warehouse.objects.filter(is_active=True) if hasattr(Warehouse, 'is_active') else Warehouse.objects.all()

    # مؤشرات تعتيق GRNI المستحقة
    grni_summary = {}
    try:
        grni_summary = GRNISubledgerService.get_open_grni_summary()
    except Exception:
        pass

    header_buttons = [
        {
            'url': reverse('purchase:grn_create'),
            'icon': 'fa-plus',
            'text': _('إذن استلام مشتريات جديد (GRN)'),
            'class': 'btn-primary',
        }
    ]

    breadcrumb_items = [
        {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
        {'title': _('المشتريات'), 'url': reverse('purchase:purchase_list'), 'icon': 'fa-shopping-bag'},
        {'title': _('إذونات استلام المشتريات (GRN)'), 'active': True}
    ]

    return render(request, 'purchase/grn_list.html', {
        'page_obj': page_obj,
        'suppliers': suppliers,
        'warehouses': warehouses,
        'grni_summary': grni_summary,
        'header_buttons': header_buttons,
        'breadcrumb_items': breadcrumb_items,
        'title': _('إذونات استلام المشتريات (GRN)'),
    })


@login_required
def grn_create(request, purchase_id=None):
    """إنشاء إذن استلام مشتريات جديد (GRN)"""
    purchase_obj = None
    if purchase_id:
        purchase_obj = get_object_or_404(Purchase, pk=purchase_id)

    po_id_param = request.GET.get("po_id")
    po_obj = None
    if po_id_param:
        po_obj = PurchaseOrder.objects.filter(pk=po_id_param).first()

    if request.method == "POST":
        po_id = request.POST.get("purchase_order") or (po_obj.id if po_obj else None)
        supplier_id = request.POST.get("supplier")
        warehouse_id = request.POST.get("warehouse")
        delivery_ref = request.POST.get("supplier_delivery_note_ref", "")
        action = request.POST.get("action", "save_draft")

        product_ids = request.POST.getlist("product[]")
        po_item_ids = request.POST.getlist("po_item[]")
        quantities = request.POST.getlist("quantity[]")
        unit_prices = request.POST.getlist("unit_price[]")

        items_data = []
        for i in range(len(product_ids)):
            if not product_ids[i]:
                continue
            qty = Decimal(quantities[i]) if i < len(quantities) and quantities[i] else Decimal("0.0000")
            if qty <= Decimal("0.0000"):
                continue
            price = Decimal(unit_prices[i]) if i < len(unit_prices) and unit_prices[i] else Decimal("0.00")
            po_item_id = po_item_ids[i] if i < len(po_item_ids) and po_item_ids[i] else None

            items_data.append({
                "product_id": product_ids[i],
                "po_item_id": po_item_id,
                "received_qty": qty,
                "unit_price": price
            })

        auto_post = (action == "post")
        is_direct_override = request.POST.get("is_direct_override") == "true"

        try:
            grn = GRNApplicationService.create_grn(
                po_id=po_id,
                warehouse_id=warehouse_id,
                supplier_id=supplier_id,
                delivery_note_ref=delivery_ref,
                items_data=items_data,
                user=request.user,
                is_direct_override=is_direct_override,
                auto_post=auto_post
            )
            messages.success(request, _("تم إنشاء إذن الاستلام رقم {} بنجاح (الحالة: {})").format(grn.grn_number, grn.get_status_display()))
            return redirect("purchase:grn_detail", pk=grn.pk)
        except FinancialCoreError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, _("حدث خطأ أثناء حفظ إذن الاستلام: {}").format(str(e)))

    suppliers = Supplier.objects.filter(is_active=True)
    warehouses = Warehouse.objects.filter(is_active=True) if hasattr(Warehouse, 'is_active') else Warehouse.objects.all()
    approved_pos = PurchaseOrder.objects.filter(status__in=["APPROVED", "PARTIALLY_RECEIVED"]).select_related("supplier", "warehouse")
    products = Product.objects.filter(is_active=True)

    breadcrumb_items = [
        {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
        {'title': _('المشتريات'), 'url': reverse('purchase:purchase_list'), 'icon': 'fa-shopping-bag'},
        {'title': _('إذونات استلام المشتريات (GRN)'), 'url': reverse('purchase:grn_list')},
        {'title': _('إذن استلام جديد'), 'active': True}
    ]

    return render(request, "purchase/grn_form.html", {
        "purchase": purchase_obj,
        "po_obj": po_obj,
        "approved_pos": approved_pos,
        "suppliers": suppliers,
        "warehouses": warehouses,
        "products": products,
        "breadcrumb_items": breadcrumb_items,
        "title": _("إذن استلام مشتريات جديد (GRN)"),
    })


@login_required
def grn_detail(request, pk):
    """تفاصيل إذن استلام المشتريات (GRN)"""
    grn = get_object_or_404(
        GoodsReceivedNote.objects.select_related('supplier', 'warehouse', 'purchase', 'purchase_order', 'journal_entry')
        .prefetch_related('items__product', 'audit_logs__action_by', 'posting_logs'),
        pk=pk
    )

    breadcrumb_items = [
        {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
        {'title': _('المشتريات'), 'url': reverse('purchase:purchase_list'), 'icon': 'fa-shopping-bag'},
        {'title': _('إذونات استلام المشتريات (GRN)'), 'url': reverse('purchase:grn_list')},
        {'title': f"GRN #{grn.grn_number}", 'active': True}
    ]

    return render(request, 'purchase/grn_detail.html', {
        'grn': grn,
        'breadcrumb_items': breadcrumb_items,
        'title': _("تفاصيل إذن استلام المشتريات #{}").format(grn.grn_number)
    })


@login_required
def grn_submit(request, pk):
    """تقديم إذن الاستلام للمراجعة (DRAFT -> SUBMITTED)"""
    if request.method == "POST":
        reason = request.POST.get("reason", "")
        try:
            grn = GRNApplicationService.submit_grn(grn_id=pk, user=request.user, reason=reason)
            messages.success(request, _("تم تقديم إذن الاستلام #{ } للمراجعة بنجاح.").format(grn.grn_number))
        except FinancialCoreError as e:
            messages.error(request, str(e))
    return redirect("purchase:grn_detail", pk=pk)


@login_required
def grn_approve(request, pk):
    """اعتماد إذن الاستلام (SUBMITTED -> APPROVED)"""
    if request.method == "POST":
        reason = request.POST.get("reason", "")
        try:
            grn = GRNApplicationService.approve_grn(grn_id=pk, user=request.user, reason=reason)
            messages.success(request, _("تم اعتماد إذن الاستلام #{} بنجاح.").format(grn.grn_number))
        except FinancialCoreError as e:
            messages.error(request, str(e))
    return redirect("purchase:grn_detail", pk=pk)


@login_required
def grn_post(request, pk):
    """الترحيل النهائي المالي والمخزني لإذن الاستلام (APPROVED -> POSTED)"""
    if request.method == "POST":
        reason = request.POST.get("reason", "")
        try:
            grn = GRNApplicationService.post_grn(grn_id=pk, user=request.user, reason=reason)
            messages.success(request, _("تم ترحيل إذن الاستلام #{} مخزنياً ومالياً بنجاح والقيد المحاسبي مرتبط.").format(grn.grn_number))
        except FinancialCoreError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, _("حدث خطأ أثناء الترحيل: {}").format(str(e)))
    return redirect("purchase:grn_detail", pk=pk)


@login_required
def grn_reverse(request, pk):
    """عكس إذن استلام مرحل (POSTED -> REVERSED)"""
    if request.method == "POST":
        reason = request.POST.get("reason", "")
        if not reason:
            messages.error(request, _("يلزم إدخال سبب واضح وموثق لعكس إذن الاستلام."))
            return redirect("purchase:grn_detail", pk=pk)
        try:
            grn = GRNApplicationService.reverse_grn(grn_id=pk, user=request.user, reason=reason)
            messages.success(request, _("تم عكس إذن الاستلام #{} والقيد المعاكس تم ترحيله بنجاح.").format(grn.grn_number))
        except FinancialCoreError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, _("حدث خطأ أثناء إجراء العكس: {}").format(str(e)))
    return redirect("purchase:grn_detail", pk=pk)
