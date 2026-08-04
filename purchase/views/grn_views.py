from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.translation import gettext as _
from django.core.paginator import Paginator
from django.utils import timezone

from purchase.models.procurement_models import GoodsReceivedNote, GoodsReceivedNoteItem
from purchase.models.purchase import Purchase
from supplier.models import Supplier
from product.models import Warehouse, Product


@login_required
def grn_list(request):
    """عرض أذون استلام الخامات والبضائع GRN"""
    grns = GoodsReceivedNote.objects.select_related('supplier', 'warehouse', 'purchase').order_by('-received_date')
    paginator = Paginator(grns, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, 'purchase/grn_list.html', {'page_obj': page_obj})


@login_required
def grn_create(request, purchase_id=None):
    """إنشاء إذن استلام بضائع جديد GRN"""
    purchase_obj = None
    if purchase_id:
        purchase_obj = get_object_or_404(Purchase, pk=purchase_id)

    if request.method == "POST":
        supplier_id = request.POST.get("supplier")
        warehouse_id = request.POST.get("warehouse")
        purchase_id_post = request.POST.get("purchase")
        delivery_ref = request.POST.get("supplier_delivery_note_ref", "")

        supplier = get_object_or_404(Supplier, pk=supplier_id)
        warehouse = get_object_or_404(Warehouse, pk=warehouse_id)
        linked_purchase = Purchase.objects.filter(pk=purchase_id_post).first() if purchase_id_post else purchase_obj

        from core.services.sequence_service import SequenceService
        from core.enums.document_types import DocumentType
        try:
            grn_num = SequenceService.get_next_number(DocumentType.GRN) if hasattr(DocumentType, 'GRN') else f"GRN-{timezone.now().strftime('%Y%m%d%H%M%S')}"
        except Exception:
            grn_num = f"GRN-{timezone.now().strftime('%Y%m%d%H%M%S')}"

        grn = GoodsReceivedNote.objects.create(
            grn_number=grn_num,
            supplier=supplier,
            warehouse=warehouse,
            purchase=linked_purchase,
            supplier_delivery_note_ref=delivery_ref,
            status="RECEIVED"
        )

        product_ids = request.POST.getlist("product[]")
        quantities = request.POST.getlist("quantity[]")
        unit_prices = request.POST.getlist("unit_price[]")

        for i in range(len(product_ids)):
            if not product_ids[i]:
                continue
            product = Product.objects.filter(pk=product_ids[i]).first()
            if not product:
                continue
            qty = Decimal(quantities[i]) if i < len(quantities) and quantities[i] else Decimal("1.0000")
            price = Decimal(unit_prices[i]) if i < len(unit_prices) and unit_prices[i] else Decimal("0.00")
            total = qty * price

            GoodsReceivedNoteItem.objects.create(
                grn=grn,
                product=product,
                received_qty=qty,
                unit_price=price,
                total_cost=total
            )

        messages.success(request, _("تم إنشاء إذن الاستلام رقم {} بنجاح").format(grn.grn_number))
        return redirect("purchase:grn_detail", pk=grn.pk)

    suppliers = Supplier.objects.filter(is_active=True)
    warehouses = Warehouse.objects.all()
    products = Product.objects.filter(is_active=True)
    return render(request, "purchase/grn_form.html", {
        "purchase": purchase_obj,
        "suppliers": suppliers,
        "warehouses": warehouses,
        "products": products,
    })


@login_required
def grn_detail(request, pk):
    """تفاصيل إذن الاستلام GRN"""
    grn = get_object_or_404(GoodsReceivedNote.objects.select_related('supplier', 'warehouse', 'purchase').prefetch_related('items__product'), pk=pk)
    return render(request, 'purchase/grn_detail.html', {'grn': grn})
