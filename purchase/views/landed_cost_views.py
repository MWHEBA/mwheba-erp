from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.translation import gettext as _
from django.core.paginator import Paginator
from django.utils import timezone

from product.models.landed_cost import LandedCostDocument, LandedCostAllocation
from supplier.models import Supplier


from django.urls import reverse

@login_required
def landed_cost_list(request):
    """عرض قائمة مستندات التكاليف الإضافية والشحن والجمارك"""
    docs = LandedCostDocument.objects.select_related('supplier', 'created_by').order_by('-created_at')

    supplier_id = request.GET.get('supplier')
    if supplier_id:
        docs = docs.filter(supplier_id=supplier_id)

    status = request.GET.get('status')
    if status:
        docs = docs.filter(status=status)

    allocation_method = request.GET.get('allocation_method')
    if allocation_method:
        docs = docs.filter(allocation_method=allocation_method)

    from core.utils import paginate_queryset
    pagination_context = paginate_queryset(docs, request)
    page_obj = pagination_context["page_obj"]

    suppliers = Supplier.objects.filter(is_active=True)

    header_buttons = [
        {
            'url': reverse('purchase:landed_cost_create'),
            'icon': 'fa-plus',
            'text': _('مستند تكاليف إضافية جديد'),
            'class': 'btn-primary',
        }
    ]

    breadcrumb_items = [
        {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
        {'title': _('المشتريات'), 'url': reverse('purchase:purchase_list'), 'icon': 'fa-shopping-bag'},
        {'title': _('مستندات التكاليف الإضافية (Landed Cost)'), 'active': True}
    ]

    return render(request, 'purchase/landed_cost_list.html', {
        'page_obj': page_obj,
        'docs': page_obj.object_list,
        **pagination_context,
        'suppliers': suppliers,
        'header_buttons': header_buttons,
        'breadcrumb_items': breadcrumb_items,
        'title': _('مستندات التكاليف الإضافية (Landed Cost)'),
    })



from purchase.services.landed_cost_allocation_service import LandedCostAllocationService
from purchase.models.procurement_models import GoodsReceivedNote


@login_required
def landed_cost_create(request):
    """إنشاء وتوزيع مستند تكاليف إضافية (شحن / جمارك / خدمات تشغيل) وفق IAS 2"""
    if request.method == "POST":
        grn_id = request.POST.get("grn_id")
        freight_amount = Decimal(request.POST.get("freight_amount", "0.00") or "0.00")
        customs_amount = Decimal(request.POST.get("customs_amount", "0.00") or "0.00")
        other_fees = Decimal(request.POST.get("other_fees", "0.00") or "0.00")
        allocation_method = request.POST.get("allocation_method", "VALUE")
        shipment_ref = request.POST.get("shipment_reference", "")
        supplier_id = request.POST.get("supplier")

        total_cost = freight_amount + customs_amount + other_fees
        if total_cost <= Decimal("0.00"):
            total_cost = Decimal(request.POST.get("total_landed_cost", "0.00") or "0.00")

        supplier = Supplier.objects.filter(pk=supplier_id).first() if supplier_id else None
        voucher_num = f"LCV-{timezone.now().strftime('%Y%m%d%H%M%S')}"

        if grn_id:
            try:
                res = LandedCostAllocationService.allocate_landed_costs(
                    grn_id=int(grn_id),
                    freight_amount=freight_amount,
                    customs_amount=customs_amount,
                    other_fees=other_fees,
                    allocation_method=allocation_method,
                    user=request.user
                )
                if res.get("status") == "ALLOCATED":
                    doc = LandedCostDocument.objects.create(
                        voucher_number=voucher_num,
                        shipment_reference=shipment_ref,
                        supplier=supplier,
                        allocation_method=allocation_method,
                        total_landed_cost=total_cost,
                        journal_entry_id=res.get("journal_entry_id"),
                        created_by=request.user,
                        status="POSTED"
                    )
                    messages.success(request, _(f"تم توزيع التكاليف الإضافية بنجاح على إذن الاستلام وتوليد القيد المحاسبي #{res.get('journal_entry_id')}."))
                    return redirect("purchase:grn_detail", pk=grn_id)
                else:
                    messages.error(request, _(f"تعذر التوزيع: {res.get('message')}"))
                    return redirect("purchase:grn_detail", pk=grn_id)
            except Exception as e:
                messages.error(request, _(f"حدث خطأ أثناء توزيع التكاليف: {str(e)}"))
                return redirect("purchase:grn_detail", pk=grn_id)

        doc = LandedCostDocument.objects.create(
            voucher_number=voucher_num,
            shipment_reference=shipment_ref,
            supplier=supplier,
            allocation_method=allocation_method,
            total_landed_cost=total_cost,
            created_by=request.user,
            status="DRAFT"
        )

        messages.success(request, _("تم إنشاء مستند التكاليف الإضافية رقم {} بنجاح").format(doc.voucher_number))
        return redirect("purchase:landed_cost_list")

    suppliers = Supplier.objects.filter(is_active=True)
    return render(request, "purchase/landed_cost_form.html", {
        "suppliers": suppliers,
    })
