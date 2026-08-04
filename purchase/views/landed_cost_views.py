from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.translation import gettext as _
from django.core.paginator import Paginator
from django.utils import timezone

from product.models.landed_cost import LandedCostDocument, LandedCostAllocation
from supplier.models import Supplier


@login_required
def landed_cost_list(request):
    """عرض قائمة مستندات التكاليف الإضافية والشحن والجمارك"""
    docs = LandedCostDocument.objects.select_related('supplier', 'created_by').order_by('-created_at')
    paginator = Paginator(docs, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, 'purchase/landed_cost_list.html', {'page_obj': page_obj})


@login_required
def landed_cost_create(request):
    """إنشاء مستند تكاليف إضافية جديد (شحن / جمارك / خدمات تشغيل)"""
    if request.method == "POST":
        shipment_ref = request.POST.get("shipment_reference", "")
        supplier_id = request.POST.get("supplier")
        allocation_method = request.POST.get("allocation_method", "VALUE")
        total_cost = Decimal(request.POST.get("total_landed_cost", "0.00"))

        supplier = Supplier.objects.filter(pk=supplier_id).first() if supplier_id else None

        voucher_num = f"LCV-{timezone.now().strftime('%Y%m%d%H%M%S')}"

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
