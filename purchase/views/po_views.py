import json
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.translation import gettext as _
from django.core.paginator import Paginator
from django.urls import reverse
from django.http import JsonResponse
from django.db import transaction
from django.db.models import Sum, Count, Q
from django.template.loader import render_to_string

from purchase.models.procurement_models import (
    PurchaseOrder,
    PurchaseOrderItem,
    GoodsReceivedNote,
    ApprovalRule,
    ApprovalRequest
)
from purchase.services.procurement_service import ProcurementService
from supplier.models import Supplier
from product.models import Warehouse, Product, ProductVariant, Unit
from core.services.sequence_service import SequenceService
from core.enums.document_types import DocumentType
from financial.exceptions import FinancialCoreError


@login_required
def po_list(request):
    """عرض قائمة أوامر الشراء المحوكمة (PO List View)"""
    orders = PurchaseOrder.objects.select_related(
        "supplier", "warehouse", "created_by", "approved_by"
    ).prefetch_related("items", "grns").order_by("-order_date", "-id")

    # Filters
    supplier_id = request.GET.get("supplier")
    if supplier_id:
        orders = orders.filter(supplier_id=supplier_id)

    warehouse_id = request.GET.get("warehouse")
    if warehouse_id:
        orders = orders.filter(warehouse_id=warehouse_id)

    status_filter = request.GET.get("status")
    if status_filter:
        orders = orders.filter(status=status_filter)

    date_from = request.GET.get("date_from")
    if date_from:
        orders = orders.filter(order_date__gte=date_from)

    date_to = request.GET.get("date_to")
    if date_to:
        orders = orders.filter(order_date__lte=date_to)

    search_query = request.GET.get("q", "").strip()
    if search_query:
        orders = orders.filter(
            Q(order_number__icontains=search_query) |
            Q(supplier__name__icontains=search_query)
        )

    # KPI Statistics
    total_count = orders.count()
    approved_count = orders.filter(status="APPROVED").count()
    partially_received_count = orders.filter(status="PARTIALLY_RECEIVED").count()
    completed_count = orders.filter(status__in=["FULLY_RECEIVED", "COMPLETED"]).count()
    total_value = orders.aggregate(val=Sum("total_amount"))["val"] or Decimal("0.00")

    # Pagination
    paginator = Paginator(orders, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    suppliers = Supplier.objects.filter(is_active=True)
    warehouses = Warehouse.objects.filter(is_active=True) if hasattr(Warehouse, "is_active") else Warehouse.objects.all()

    breadcrumb_items = [
        {"title": _("الرئيسية"), "url": reverse("core:dashboard"), "icon": "fa-home"},
        {"title": _("المشتريات"), "url": reverse("purchase:purchase_list"), "icon": "fa-shopping-cart"},
        {"title": _("أوامر الشراء"), "active": True}
    ]

    header_buttons = [
        {
            "url": reverse("purchase:po_create"),
            "text": _("إنشاء أمر شراء جديد"),
            "icon": "fa-plus",
            "class": "btn-primary",
        }
    ]

    context = {
        "orders": page_obj,
        "page_obj": page_obj,
        "suppliers": suppliers,
        "warehouses": warehouses,
        "total_count": total_count,
        "approved_count": approved_count,
        "partially_received_count": partially_received_count,
        "completed_count": completed_count,
        "total_value": total_value,
        "status_choices": PurchaseOrder.STATUS_CHOICES,
        "breadcrumb_items": breadcrumb_items,
        "header_buttons": header_buttons,
        "page_title": _("أوامر الشراء"),
        "page_subtitle": _("إدارة واعتماد أوامر الشراء ومتابعة التوريدات والاستلام المخزني"),
        "page_icon": "fas fa-file-invoice",
    }

    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.GET.get("ajax"):
        table_html = render_to_string("purchase/partials/po_table_partial.html", context, request=request)
        pagination_html = render_to_string("partials/pagination.html", {"page_obj": page_obj}, request=request)
        return JsonResponse({"table_html": table_html, "pagination_html": pagination_html})

    return render(request, "purchase/po_list.html", context)


@login_required
def po_create(request):
    """إنشاء أمر شراء جديد (PO Create) مع دعم الحوكمة والمعايير المحاسبية الموحدة"""
    from purchase.forms import PurchaseOrderForm
    from financial.models import Currency, CostCenter
    from core.models import SystemSetting
    from work_order.models import WorkOrder
    from product.models import Category

    # قراءة أمر الشغل إذا تم تمريره
    work_order_id = request.GET.get("work_order") or request.POST.get("work_order")
    selected_work_order = None
    selected_supplier = None
    if work_order_id:
        try:
            selected_work_order = WorkOrder.objects.get(id=work_order_id)
            if hasattr(selected_work_order, "supplier") and selected_work_order.supplier:
                selected_supplier = selected_work_order.supplier
        except WorkOrder.DoesNotExist:
            pass

    duplicate_from_id = request.GET.get("duplicate_from")
    duplicate_po = None
    if duplicate_from_id:
        duplicate_po = PurchaseOrder.objects.filter(pk=duplicate_from_id).prefetch_related("items__product", "items__unit").first()
        if duplicate_po and not selected_supplier:
            selected_supplier = duplicate_po.supplier

    form = PurchaseOrderForm(request.POST or None, user=request.user)
    if duplicate_po and request.method == "GET":
        initial_data = {
            "supplier": duplicate_po.supplier_id,
            "warehouse": duplicate_po.warehouse_id,
            "currency": duplicate_po.currency_id,
            "exchange_rate": duplicate_po.exchange_rate,
            "cost_center": duplicate_po.cost_center_id,
            "discount": duplicate_po.discount,
            "discount_type": duplicate_po.discount_type,
            "tax_active": duplicate_po.tax_active,
            "vat_active": duplicate_po.vat_active,
            "vat_rate": duplicate_po.vat_rate,
            "wht_active": duplicate_po.wht_active,
            "wht_rate": duplicate_po.wht_rate,
            "adjustment_name": duplicate_po.adjustment_name,
            "adjustment_type": duplicate_po.adjustment_type,
            "adjustment_amount": duplicate_po.adjustment_amount,
            "payment_terms": duplicate_po.payment_terms,
            "notes": duplicate_po.notes,
        }
        form = PurchaseOrderForm(initial=initial_data, user=request.user)

    if request.method == "POST":
        supplier_id = request.POST.get("supplier")
        warehouse_id = request.POST.get("warehouse") or None
        order_date = request.POST.get("order_date") or timezone.now().date()
        delivery_due_date = request.POST.get("delivery_due_date") or None
        currency_id = request.POST.get("currency")
        exchange_rate_val = Decimal(str(request.POST.get("exchange_rate") or "1.000000"))
        cost_source_policy = request.POST.get("cost_source_policy", "PO_PRICE")
        cost_center_id = request.POST.get("cost_center") or None
        payment_terms = request.POST.get("payment_terms") or ""
        notes = request.POST.get("notes") or ""

        discount_val = Decimal(str(request.POST.get("discount") or "0.00"))
        discount_type = request.POST.get("discount_type", "fixed")
        tax_active = request.POST.get("tax_active") in ["on", "true", "1", True]
        vat_active = request.POST.get("vat_active") in ["on", "true", "1", True] or tax_active
        vat_rate_val = Decimal(str(request.POST.get("vat_rate") or "14.00"))
        wht_active = request.POST.get("wht_active") in ["on", "true", "1", True]
        wht_rate_val = Decimal(str(request.POST.get("wht_rate") or "1.00"))

        adjustment_name = request.POST.get("adjustment_name") or ""
        adjustment_type = request.POST.get("adjustment_type", "add")
        adjustment_amount_val = Decimal(str(request.POST.get("adjustment_amount") or "0.00"))

        product_ids = request.POST.getlist("product[]") or request.POST.getlist("product_id[]")
        quantities = request.POST.getlist("quantity[]")
        unit_prices = request.POST.getlist("unit_price[]") or request.POST.getlist("unit_cost[]")
        item_discounts = request.POST.getlist("discount[]") or request.POST.getlist("item_discount[]")
        variants = request.POST.getlist("variant[]")
        units = request.POST.getlist("unit[]")

        valid_indices = [i for i in range(len(product_ids)) if product_ids[i]]
        if not supplier_id or not order_date or not valid_indices:
            messages.error(request, _("يرجى ملء جميع الحقول الإلزامية وإضافة بند واحد على الأقل."))
            return redirect("purchase:po_create")

        supplier = get_object_or_404(Supplier, pk=supplier_id)
        warehouse = Warehouse.objects.filter(pk=warehouse_id).first() if warehouse_id else None
        currency_obj = Currency.objects.filter(pk=currency_id).first() if currency_id else Currency.objects.filter(is_functional=True).first()
        cost_center = CostCenter.objects.filter(pk=cost_center_id).first() if cost_center_id else None

        custom_fields_data = []
        try:
            cf_json = request.POST.get("custom_fields_json", "[]")
            if cf_json:
                custom_fields_data = json.loads(cf_json)
        except Exception:
            custom_fields_data = []

        try:
            with transaction.atomic():
                po_num = ProcurementService.generate_po_number(date=order_date, warehouse=warehouse)

                po = PurchaseOrder.objects.create(
                    order_number=po_num,
                    supplier=supplier,
                    warehouse=warehouse,
                    order_date=order_date,
                    delivery_due_date=delivery_due_date,
                    currency=currency_obj,
                    exchange_rate=exchange_rate_val,
                    cost_source_policy=cost_source_policy,
                    cost_center=cost_center,
                    payment_terms=payment_terms,
                    notes=notes,
                    status="DRAFT",
                    custom_fields=custom_fields_data,
                    subtotal=Decimal("0.00"),
                    total_amount=Decimal("0.00"),
                    functional_amount=Decimal("0.00"),
                    created_by=request.user
                )

                subtotal_amt = Decimal("0.00")
                for i in valid_indices:
                    p_id = int(product_ids[i])
                    product = Product.objects.filter(pk=p_id).first()
                    if not product:
                        continue
                    qty = Decimal(str(quantities[i] if i < len(quantities) and quantities[i] else "1.0000"))
                    price = Decimal(str(unit_prices[i] if i < len(unit_prices) and unit_prices[i] else "0.00"))
                    line_disc = Decimal(str(item_discounts[i] if i < len(item_discounts) and item_discounts[i] else "0.00"))
                    variant_id = variants[i] if i < len(variants) and variants[i] else None
                    unit_id = units[i] if i < len(units) and units[i] else None
                    unit_obj = Unit.objects.filter(pk=unit_id).first() if unit_id else getattr(product, "unit", None)
                    line_total = max(Decimal("0.00"), (qty * price) - line_disc).quantize(Decimal("0.01"))
                    PurchaseOrderItem.objects.create(
                        purchase_order=po,
                        product=product,
                        variant_id=variant_id,
                        unit=unit_obj,
                        ordered_qty=qty,
                        unit_price=price,
                        discount=line_disc,
                        total_price=line_total
                    )
                    subtotal_amt += line_total

                po.subtotal = subtotal_amt
                po.discount = discount_val
                po.discount_type = discount_type
                doc_discount_amt = (subtotal_amt * (po.discount / Decimal("100.00"))).quantize(Decimal("0.01")) if po.discount_type == "percentage" else po.discount
                net_commercial = max(Decimal("0.00"), subtotal_amt - doc_discount_amt)
                po.tax_active = vat_active
                po.vat_active = vat_active
                po.vat_rate = vat_rate_val
                po.tax_amount = (net_commercial * (po.vat_rate / Decimal("100.00"))).quantize(Decimal("0.01")) if po.vat_active else Decimal("0.00")
                po.wht_active = wht_active
                po.wht_rate = wht_rate_val
                po.wht_amount = (net_commercial * (po.wht_rate / Decimal("100.00"))).quantize(Decimal("0.01")) if po.wht_active else Decimal("0.00")
                po.adjustment_name = adjustment_name
                po.adjustment_type = adjustment_type
                po.adjustment_amount = adjustment_amount_val
                adj_val = po.adjustment_amount if po.adjustment_type == "add" else -po.adjustment_amount
                grand_total = max(Decimal("0.00"), net_commercial + po.tax_amount - po.wht_amount + adj_val).quantize(Decimal("0.01"))
                po.total_amount = grand_total
                po.total_foreign = grand_total
                po.functional_amount = (grand_total * po.exchange_rate).quantize(Decimal("0.01"))
                po.save()
                action = request.POST.get("action", "save_draft")
                if action == "submit_approval":
                    po.status = "SUBMITTED"
                    po.save()
                    messages.success(request, _(f"تم إنشاء أمر الشراء #{po.order_number} وتقديمه للاعتماد بنجاح."))
                else:
                    po.status = "DRAFT"
                    messages.success(request, _(f"تم إنشاء مسودة أمر الشراء #{po.order_number} بنجاح."))
                return redirect("purchase:po_detail", pk=po.id)
        except FinancialCoreError as e:
            messages.error(request, str(e))
            return redirect("purchase:po_create")
        except Exception as e:
            messages.error(request, _(f"حدث خطأ غير متوقع أثناء حفظ أمر الشراء: {e}"))
            return redirect("purchase:po_create")

    suppliers = Supplier.objects.filter(is_active=True).order_by("name")
    warehouses = Warehouse.objects.filter(is_active=True).order_by("name")
    products = Product.objects.filter(is_active=True).order_by("name")
    product_categories = Category.objects.filter(is_active=True).order_by("name")
    cost_centers = CostCenter.objects.filter(is_active=True).order_by("code")
    currencies = Currency.objects.filter(is_active=True).order_by("-is_functional", "code")
    active_currencies = currencies
    functional_currency = Currency.objects.filter(is_functional=True).first()
    
    enable_tax = SystemSetting.get_setting("enable_tax", True)
    if isinstance(enable_tax, str):
        enable_tax = enable_tax.lower() in ["true", "1", "yes", "نعم"]
    settings_dict = {"enable_tax": enable_tax, "default_tax_rate": SystemSetting.get_setting("default_tax_rate", 14)}
    breadcrumb_items = [
        {"title": _("الرئيسية"), "url": reverse("core:dashboard"), "icon": "fa-home"},
        {"title": _("أوامر الشراء"), "url": reverse("purchase:po_list"), "icon": "fa-file-invoice"},
        {"title": _("إنشاء جديد"), "active": True}
    ]
    currency_symbol = duplicate_po.currency.symbol if duplicate_po and duplicate_po.currency and duplicate_po.currency.symbol else (functional_currency.symbol if functional_currency else "ج.م")
    selected_curr_id = duplicate_po.currency_id if duplicate_po else (functional_currency.id if functional_currency else None)
    selected_curr_is_foreign = bool(duplicate_po.currency and not duplicate_po.currency.is_functional) if duplicate_po else False
    selected_ex_rate = str(duplicate_po.exchange_rate) if duplicate_po else "1.000000"
    context = {
        "po": duplicate_po,
        "is_duplicate": bool(duplicate_po),
        "form": form,
        "suppliers": suppliers,
        "selected_supplier": selected_supplier,
        "warehouses": warehouses,
        "products": products,
        "product_categories": product_categories,
        "cost_centers": cost_centers,
        "currencies": currencies,
        "active_currencies": active_currencies,
        "functional_currency": functional_currency,
        "selected_currency_id": selected_curr_id,
        "selected_currency_is_foreign": selected_curr_is_foreign,
        "current_exchange_rate": selected_ex_rate,
        "currency_symbol": currency_symbol,
        "settings": settings_dict,
        "custom_fields_json": json.dumps(duplicate_po.custom_fields if duplicate_po else []),
        "breadcrumb_items": breadcrumb_items,
        "page_title": _("إنشاء أمر شراء جديد"),
        "page_subtitle": _("إنشاء أمر شراء جديد وتحديد المورد والمخزن والبنود والشروط التعاقدية"),
        "page_icon": "fas fa-file-invoice",
    }
    return render(request, "purchase/po_form.html", context)


@login_required
def po_edit(request, pk):
    """تعديل أمر شراء قائم مع تطبيق خوارزمية التحديث غير المدمر وحوكمة الحالات"""
    from purchase.forms import PurchaseOrderForm
    from financial.models import Currency, CostCenter
    from core.models import SystemSetting
    from product.models import Category

    po = get_object_or_404(
        PurchaseOrder.objects.select_related("supplier", "warehouse", "currency", "cost_center")
        .prefetch_related("items__product", "items__unit"),
        pk=pk
    )

    if po.status in ["FULLY_RECEIVED", "COMPLETED", "CANCELLED"]:
        messages.error(request, _("لا يمكن تعديل أمر الشراء في حالته الحالية."))
        return redirect("purchase:po_detail", pk=po.id)

    form = PurchaseOrderForm(request.POST or None, instance=po, user=request.user)

    if request.method == "POST":
        supplier_id = request.POST.get("supplier")
        warehouse_id = request.POST.get("warehouse") or None
        order_date = request.POST.get("order_date") or po.order_date
        delivery_due_date = request.POST.get("delivery_due_date") or None
        currency_id = request.POST.get("currency")
        exchange_rate_val = Decimal(str(request.POST.get("exchange_rate") or "1.000000"))
        cost_source_policy = request.POST.get("cost_source_policy", "PO_PRICE")
        cost_center_id = request.POST.get("cost_center") or None
        payment_terms = request.POST.get("payment_terms") or ""
        notes = request.POST.get("notes") or ""

        discount_val = Decimal(str(request.POST.get("discount") or "0.00"))
        discount_type = request.POST.get("discount_type", "fixed")
        tax_active = request.POST.get("tax_active") in ["on", "true", "1", True]
        vat_active = request.POST.get("vat_active") in ["on", "true", "1", True] or tax_active
        vat_rate_val = Decimal(str(request.POST.get("vat_rate") or "14.00"))
        wht_active = request.POST.get("wht_active") in ["on", "true", "1", True]
        wht_rate_val = Decimal(str(request.POST.get("wht_rate") or "1.00"))

        adjustment_name = request.POST.get("adjustment_name") or ""
        adjustment_type = request.POST.get("adjustment_type", "add")
        adjustment_amount_val = Decimal(str(request.POST.get("adjustment_amount") or "0.00"))

        item_ids = request.POST.getlist("item_id[]")
        product_ids = request.POST.getlist("product[]") or request.POST.getlist("product_id[]")
        quantities = request.POST.getlist("quantity[]")
        unit_prices = request.POST.getlist("unit_price[]") or request.POST.getlist("unit_cost[]")
        item_discounts = request.POST.getlist("discount[]") or request.POST.getlist("item_discount[]")
        variants = request.POST.getlist("variant[]")
        units = request.POST.getlist("unit[]")

        valid_indices = [i for i in range(len(product_ids)) if product_ids[i]]
        if not supplier_id or not order_date or not valid_indices:
            messages.error(request, _("يرجى ملء جميع الحقول الإلزامية وإضافة بند واحد على الأقل."))
            return redirect("purchase:po_edit", pk=po.id)

        supplier = get_object_or_404(Supplier, pk=supplier_id)
        warehouse = Warehouse.objects.filter(pk=warehouse_id).first() if warehouse_id else None
        currency_obj = Currency.objects.filter(pk=currency_id).first() if currency_id else Currency.objects.filter(is_functional=True).first()
        cost_center = CostCenter.objects.filter(pk=cost_center_id).first() if cost_center_id else None

        custom_fields_data = po.custom_fields
        try:
            cf_json = request.POST.get("custom_fields_json")
            if cf_json:
                custom_fields_data = json.loads(cf_json)
        except Exception:
            custom_fields_data = po.custom_fields

        try:
            with transaction.atomic():
                po.supplier = supplier
                po.warehouse = warehouse
                po.order_date = order_date
                po.delivery_due_date = delivery_due_date
                po.currency = currency_obj
                po.exchange_rate = exchange_rate_val
                po.cost_source_policy = cost_source_policy
                po.cost_center = cost_center
                po.payment_terms = payment_terms
                po.notes = notes
                po.custom_fields = custom_fields_data

                existing_items = {item.id: item for item in po.items.all()}
                submitted_item_ids = set()
                subtotal_amt = Decimal("0.00")

                for i in valid_indices:
                    p_id = int(product_ids[i])
                    product = Product.objects.filter(pk=p_id).first()
                    if not product:
                        continue

                    raw_item_id = item_ids[i] if i < len(item_ids) and item_ids[i] else None
                    item_id_val = int(raw_item_id) if raw_item_id and str(raw_item_id).isdigit() else None

                    qty = Decimal(str(quantities[i] if i < len(quantities) and quantities[i] else "1.0000"))
                    price = Decimal(str(unit_prices[i] if i < len(unit_prices) and unit_prices[i] else "0.00"))
                    line_disc = Decimal(str(item_discounts[i] if i < len(item_discounts) and item_discounts[i] else "0.00"))
                    variant_id = variants[i] if i < len(variants) and variants[i] else None
                    unit_id = units[i] if i < len(units) and units[i] else None
                    unit_obj = Unit.objects.filter(pk=unit_id).first() if unit_id else getattr(product, "unit", None)
                    line_total = max(Decimal("0.00"), (qty * price) - line_disc).quantize(Decimal("0.01"))

                    if item_id_val and item_id_val in existing_items:
                        item = existing_items[item_id_val]
                        submitted_item_ids.add(item.id)
                        if qty < item.received_qty:
                            raise FinancialCoreError(_(f"لا يمكن تقليل كمية الصنف {product.name} عن الكمية المستلمة بالفعل ({item.received_qty})."))
                        item.product = product
                        item.ordered_qty = qty
                        item.unit_price = price
                        item.discount = line_disc
                        item.total_price = line_total
                        item.unit = unit_obj
                        item.variant_id = variant_id
                        item.save()
                    else:
                        new_item = PurchaseOrderItem.objects.create(
                            purchase_order=po,
                            product=product,
                            variant_id=variant_id,
                            unit=unit_obj,
                            ordered_qty=qty,
                            unit_price=price,
                            discount=line_disc,
                            total_price=line_total
                        )
                        submitted_item_ids.add(new_item.id)
                    subtotal_amt += line_total

                for it_id, item in existing_items.items():
                    if it_id not in submitted_item_ids:
                        if item.received_qty > 0:
                            raise FinancialCoreError(_(f"لا يمكن حذف الصنف {item.product.name} لوجود استلامات مخزنية مسجلة عليه ({item.received_qty})."))
                        item.delete()

                po.subtotal = subtotal_amt
                po.discount = discount_val
                po.discount_type = discount_type
                doc_discount_amt = (subtotal_amt * (po.discount / Decimal("100.00"))).quantize(Decimal("0.01")) if po.discount_type == "percentage" else po.discount
                net_commercial = max(Decimal("0.00"), subtotal_amt - doc_discount_amt)
                po.tax_active = vat_active
                po.vat_active = vat_active
                po.vat_rate = vat_rate_val
                po.tax_amount = (net_commercial * (po.vat_rate / Decimal("100.00"))).quantize(Decimal("0.01")) if po.vat_active else Decimal("0.00")
                po.wht_active = wht_active
                po.wht_rate = wht_rate_val
                po.wht_amount = (net_commercial * (po.wht_rate / Decimal("100.00"))).quantize(Decimal("0.01")) if po.wht_active else Decimal("0.00")
                po.adjustment_name = adjustment_name
                po.adjustment_type = adjustment_type
                po.adjustment_amount = adjustment_amount_val
                adj_val = po.adjustment_amount if po.adjustment_type == "add" else -po.adjustment_amount
                grand_total = max(Decimal("0.00"), net_commercial + po.tax_amount - po.wht_amount + adj_val).quantize(Decimal("0.01"))
                po.total_amount = grand_total
                po.total_foreign = grand_total
                po.functional_amount = (grand_total * po.exchange_rate).quantize(Decimal("0.01"))
                po.save()

                action = request.POST.get("action", "save_draft")
                if action == "submit_approval":
                    po.status = "SUBMITTED"
                    po.approved_by = None
                    po.save()
                    messages.success(request, _(f"تم تحديث أمر الشراء #{po.order_number} وإعادة تقديمه للاعتماد."))
                else:
                    if po.status == "APPROVED":
                        po.status = "DRAFT"
                        po.approved_by = None
                        po.save()
                        messages.warning(request, _(f"تم تعديل أمر الشراء #{po.order_number} وإعادته لحالة المسودة لإعادة اعتماده."))
                    else:
                        messages.success(request, _(f"تم تحديث أمر الشراء #{po.order_number} بنجاح."))
                return redirect("purchase:po_detail", pk=po.id)
        except FinancialCoreError as e:
            messages.error(request, str(e))
            return redirect("purchase:po_edit", pk=po.id)
        except Exception as e:
            messages.error(request, _(f"حدث خطأ غير متوقع أثناء تحديث أمر الشراء: {e}"))
            return redirect("purchase:po_edit", pk=po.id)

    suppliers = Supplier.objects.filter(is_active=True).order_by("name")
    warehouses = Warehouse.objects.filter(is_active=True).order_by("name")
    products = Product.objects.filter(is_active=True).order_by("name")
    product_categories = Category.objects.filter(is_active=True).order_by("name")
    cost_centers = CostCenter.objects.filter(is_active=True).order_by("code")
    currencies = Currency.objects.filter(is_active=True).order_by("-is_functional", "code")
    active_currencies = currencies
    functional_currency = Currency.objects.filter(is_functional=True).first()
    
    enable_tax = SystemSetting.get_setting("enable_tax", True)
    if isinstance(enable_tax, str):
        enable_tax = enable_tax.lower() in ["true", "1", "yes", "نعم"]
    settings_dict = {"enable_tax": enable_tax, "default_tax_rate": SystemSetting.get_setting("default_tax_rate", 14)}
    breadcrumb_items = [
        {"title": _("الرئيسية"), "url": reverse("core:dashboard"), "icon": "fa-home"},
        {"title": _("أوامر الشراء"), "url": reverse("purchase:po_list"), "icon": "fa-file-invoice"},
        {"title": f"#{po.order_number}", "url": reverse("purchase:po_detail", kwargs={"pk": po.id})},
        {"title": _("تعديل"), "active": True}
    ]
    currency_symbol = po.currency.symbol if po.currency and po.currency.symbol else (functional_currency.symbol if functional_currency else "ج.م")
    is_foreign = bool(po.currency and not po.currency.is_functional)
    context = {
        "po": po,
        "is_duplicate": False,
        "form": form,
        "suppliers": suppliers,
        "selected_supplier": po.supplier,
        "warehouses": warehouses,
        "products": products,
        "product_categories": product_categories,
        "cost_centers": cost_centers,
        "currencies": currencies,
        "active_currencies": active_currencies,
        "functional_currency": functional_currency,
        "selected_currency_id": po.currency_id or (functional_currency.id if functional_currency else None),
        "selected_currency_is_foreign": is_foreign,
        "current_exchange_rate": str(po.exchange_rate),
        "currency_symbol": currency_symbol,
        "settings": settings_dict,
        "custom_fields_json": json.dumps(po.custom_fields or []),
        "breadcrumb_items": breadcrumb_items,
        "page_title": _(f"تعديل أمر الشراء #{po.order_number}"),
        "page_subtitle": _("تعديل بنود وتفاصيل أمر الشراء"),
        "page_icon": "fas fa-edit",
    }
    return render(request, "purchase/po_form.html", context)


@login_required
def po_detail(request, pk):
    """تفاصيل أمر الشراء مع التتبع الرباعي ودورة الحياة (PO Detail View)"""
    po = get_object_or_404(
        PurchaseOrder.objects.select_related("supplier", "warehouse", "currency", "created_by", "approved_by")
        .prefetch_related("items__product", "items__unit", "grns__warehouse", "grns__journal_entry"),
        pk=pk
    )

    total_ordered_qty = sum(item.ordered_qty for item in po.items.all())
    total_received_qty = sum(item.received_qty for item in po.items.all())
    total_billed_qty = sum(item.billed_qty for item in po.items.all())
    total_remaining_qty = max(Decimal("0.0000"), total_ordered_qty - total_received_qty)

    receipt_progress = 0
    if total_ordered_qty > 0:
        receipt_progress = min(100, int((total_received_qty / total_ordered_qty) * 100))

    breadcrumb_items = [
        {"title": _("الرئيسية"), "url": reverse("core:dashboard"), "icon": "fa-home"},
        {"title": _("المشتريات"), "url": reverse("purchase:purchase_list"), "icon": "fa-shopping-cart"},
        {"title": _("أوامر الشراء"), "url": reverse("purchase:po_list"), "icon": "fa-file-invoice"},
        {"title": f"#{po.order_number}", "active": True}
    ]

    header_buttons = []
    if po.status in ["DRAFT", "SUBMITTED"]:
        header_buttons.append({
            "url": reverse("purchase:po_edit", kwargs={"pk": po.id}),
            "text": _("تعديل"),
            "icon": "fa-edit",
            "class": "btn-outline-secondary",
        })
    header_buttons.append({
        "url": reverse("purchase:po_duplicate", kwargs={"pk": po.id}),
        "text": _("تكرار"),
        "icon": "fa-copy",
        "class": "btn-outline-primary",
    })
    header_buttons.append({
        "url": reverse("purchase:po_print", kwargs={"pk": po.id}),
        "text": _("طباعة"),
        "icon": "fa-print",
        "class": "btn-info",
        "target": "_blank"
    })
    header_buttons.append({
        "dropdown": True,
        "icon": "fa-share-alt",
        "text": _("مشاركة"),
        "class": "btn-success",
        "items": [
            {
                "url": reverse("purchase:po_pdf_download", kwargs={"pk": po.id}),
                "icon": "fas fa-file-download text-primary",
                "text": _("تحميل PDF")
            },
            {
                "onclick": f"if(window.shareWhatsAppPDF) {{ shareWhatsAppPDF('{po.supplier.phone if po.supplier and po.supplier.phone else ''}', '{po.order_number}', 'أمر شراء', '{reverse('purchase:po_pdf_download', kwargs={'pk': po.pk})}', '{reverse('purchase:po_print', kwargs={'pk': po.pk})}'); }}",
                "icon": "fab fa-whatsapp text-success",
                "text": _("إرسال واتساب للمورد")
            },
            {
                "onclick": f"if(window.sendEmailPDF) {{ sendEmailPDF('{reverse('purchase:po_email_pdf', kwargs={'pk': po.pk})}', '{po.supplier.email if po.supplier and po.supplier.email else ''}', '{po.order_number}', 'أمر شراء', '{reverse('purchase:po_pdf_download', kwargs={'pk': po.pk})}', '{reverse('purchase:po_print', kwargs={'pk': po.pk})}'); }}",
                "icon": "far fa-envelope text-primary",
                "text": _("إرسال بريد إلكتروني")
            }
        ]
    })
    if po.status in ["APPROVED", "PARTIALLY_RECEIVED"] and total_remaining_qty > 0:
        header_buttons.append({
            "url": f"{reverse('purchase:grn_create')}?po_id={po.id}",
            "text": _("استلام بضاعة (GRN)"),
            "icon": "fa-truck-loading",
            "class": "btn-success fw-bold",
        })
    if po.status in ["APPROVED", "PARTIALLY_RECEIVED", "FULLY_RECEIVED", "COMPLETED"]:
        header_buttons.append({
            "url": f"{reverse('purchase:purchase_create')}?from_po={po.id}",
            "text": _("إنشاء فاتورة مشتريات"),
            "icon": "fa-file-invoice-dollar",
            "class": "btn-primary",
        })
    if po.status in ["DRAFT", "CANCELLED"]:
        header_buttons.append({
            "url": reverse("purchase:po_delete", kwargs={"pk": po.id}),
            "text": _("حذف"),
            "icon": "fa-trash-alt",
            "class": "btn-outline-danger",
        })

    context = {
        "po": po,
        "total_ordered_qty": total_ordered_qty,
        "total_received_qty": total_received_qty,
        "total_billed_qty": total_billed_qty,
        "total_remaining_qty": total_remaining_qty,
        "receipt_progress": receipt_progress,
        "breadcrumb_items": breadcrumb_items,
        "header_buttons": header_buttons,
        "page_title": _(f"أمر الشراء #{po.order_number}"),
        "page_subtitle": _("متابعة دورة حياة أمر الشراء وتوريدات المخازن والمطابقة المالية"),
        "page_icon": "fas fa-file-invoice",
    }
    return render(request, "purchase/po_detail.html", context)


@login_required
def po_print(request, pk):
    """طباعة وتصدير أمر الشراء الرسمي للمورد (PO Print View)"""
    po = get_object_or_404(
        PurchaseOrder.objects.select_related("supplier", "warehouse", "currency", "created_by", "approved_by")
        .prefetch_related("items__product", "items__unit"),
        pk=pk
    )

    currency_symbol = po.currency.symbol if po.currency and po.currency.symbol else "ج.م"

    context = {
        "po": po,
        "currency_symbol": currency_symbol,
        "page_title": _(f"أمر شراء #{po.order_number} - {po.supplier.name}"),
    }
    return render(request, "purchase/po_print.html", context)


@login_required
def po_pdf_download(request, pk):
    """تصدير وتحميل أمر الشراء كملف PDF رسمي"""
    from utils.pdf_utils import generate_pdf_from_html, generate_guaranteed_pdf_response

    po = get_object_or_404(
        PurchaseOrder.objects.select_related("supplier", "warehouse", "currency", "created_by", "approved_by")
        .prefetch_related("items__product", "items__unit"),
        pk=pk
    )
    currency_symbol = po.currency.symbol if po.currency and po.currency.symbol else "ج.م"

    context = {
        "po": po,
        "currency_symbol": currency_symbol,
        "page_title": f"أمر شراء #{po.order_number} - {po.supplier.name}",
    }

    try:
        html_content = render_to_string("purchase/po_print.html", context, request=request)
        pdf_response = generate_pdf_from_html(
            html_content, request=request, filename=f"PO_{po.order_number}.pdf", doc_type="purchase_order", context=context
        )
        if pdf_response:
            return pdf_response
    except Exception:
        pass

    return generate_guaranteed_pdf_response("purchase_order", context, filename=f"PO_{po.order_number}.pdf")


@login_required
def po_email_pdf(request, pk):
    """إرسال أمر الشراء عبر البريد الإلكتروني للمورد مباشرة"""
    po = get_object_or_404(PurchaseOrder.objects.select_related("supplier"), pk=pk)
    supplier_email = po.supplier.email if po.supplier and po.supplier.email else None
    if not supplier_email:
        return JsonResponse({"success": False, "message": _("لا يوجد بريد إلكتروني مسجل للمورد.")}, status=400)

    try:
        from utils.email_utils import send_email
        subject = f"أمر شراء #{po.order_number} - مؤسسة موهبة"
        body = (
            f"السادة / {po.supplier.name} المحترمين،\n\n"
            f"مرفق لسيادتكم أمر الشراء رقم #{po.order_number} بإجمالي {po.total_amount} {po.currency.symbol if po.currency else 'ج.م'}.\n\n"
            f"رابط أمر الشراء المباشر:\n{request.build_absolute_uri(reverse('purchase:po_print', kwargs={'pk': po.pk}))}\n\n"
            f"شاكرين حسن تعاونكم معنا."
        )
        send_email(subject, body, [supplier_email])
        return JsonResponse({"success": True, "message": _("تم إرسال أمر الشراء للمورد عبر البريد الإلكتروني بنجاح!")})
    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)


@login_required
def po_duplicate(request, pk):
    """تكرار أمر الشراء لإنشاء أمر جديد بنفس البنود والأسعار"""
    po = get_object_or_404(PurchaseOrder, pk=pk)
    return redirect(f"{reverse('purchase:po_create')}?duplicate_from={po.id}")


@login_required
def po_delete(request, pk):
    """حذف أمر الشراء إذا كان مسودة أو ملغى ولم تُسجل عليه أي أذون استلام"""
    po = get_object_or_404(PurchaseOrder.objects.prefetch_related("grns"), pk=pk)

    if po.grns.exists() or po.status in ["PARTIALLY_RECEIVED", "FULLY_RECEIVED", "COMPLETED"]:
        messages.error(request, _("لا يمكن حذف أمر شراء مسجل عليه أذون استلام مخزنية (GRN)."))
        return redirect("purchase:po_detail", pk=po.id)

    if request.method == "POST":
        with transaction.atomic():
            po.items.all().delete()
            po.delete()
        messages.success(request, _(f"تم حذف أمر الشراء #{po.order_number} بنجاح."))
        return redirect("purchase:po_list")

    context = {
        "po": po,
        "page_title": _(f"حذف أمر الشراء #{po.order_number}"),
        "page_icon": "fas fa-trash-alt",
        "breadcrumb_items": [
            {"title": _("الرئيسية"), "url": reverse("core:dashboard"), "icon": "fa-home"},
            {"title": _("أوامر الشراء"), "url": reverse("purchase:po_list"), "icon": "fa-file-invoice"},
            {"title": f"#{po.order_number}", "url": reverse("purchase:po_detail", kwargs={"pk": po.id})},
            {"title": _("حذف"), "active": True},
        ]
    }
    return render(request, "purchase/po_confirm_delete.html", context)


@login_required
def po_submit(request, pk):
    """تقديم أمر الشراء للاعتماد (POST only)"""
    if request.method != "POST":
        return JsonResponse({"success": False, "message": _("طلب غير صالح.")}, status=405)

    po = get_object_or_404(PurchaseOrder, pk=pk)
    if po.status != "DRAFT":
        return JsonResponse({"success": False, "message": _("يمكن تقديم المسودة فقط للاعتماد.")}, status=400)

    po.status = "SUBMITTED"
    po.save(update_fields=["status"])
    messages.success(request, _(f"تم تقديم أمر الشراء #{po.order_number} للاعتماد بنجاح."))
    return redirect("purchase:po_detail", pk=po.id)


@login_required
def po_approve(request, pk):
    """اعتماد أمر الشراء (POST only)"""
    if request.method != "POST":
        return JsonResponse({"success": False, "message": _("طلب غير صالح.")}, status=405)

    po = get_object_or_404(PurchaseOrder, pk=pk)
    if po.status not in ["DRAFT", "SUBMITTED"]:
        return JsonResponse({"success": False, "message": _("أمر الشراء معتمد مسبقاً أو ملغي.")}, status=400)

    try:
        ProcurementService.approve_purchase_order(po.id, user=request.user)
        messages.success(request, _(f"تم اعتماد أمر الشراء #{po.order_number} بنجاح، وأصبح جاهزاً للاستلام المخزني."))
    except Exception as e:
        messages.error(request, _(f"فشل اعتماد أمر الشراء: {str(e)}"))

    return redirect("purchase:po_detail", pk=po.id)


@login_required
def po_short_close(request, pk):
    """الإغلاق المبكر لأمر الشراء عند تعذر استكمال التوريد (POST only)"""
    if request.method != "POST":
        return JsonResponse({"success": False, "message": _("طلب غير صالح.")}, status=405)

    po = get_object_or_404(PurchaseOrder, pk=pk)
    if po.status not in ["APPROVED", "PARTIALLY_RECEIVED"]:
        return JsonResponse({"success": False, "message": _("لا يمكن إغلاق أمر الشراء في حالته الحالية.")}, status=400)

    reason = request.POST.get("reason", "").strip() or _("إغلاق مبكر بطلب الإدارة")

    po.status = "FULLY_RECEIVED"
    po.save(update_fields=["status"])

    messages.warning(request, _(f"تم إنهاء وإغلاق أمر الشراء #{po.order_number} رسمياً وتصفير الكميات المعلقة. السبب: {reason}"))
    return redirect("purchase:po_detail", pk=po.id)


@login_required
def po_cancel(request, pk):
    """إلغاء أمر الشراء (POST only)"""
    if request.method != "POST":
        return JsonResponse({"success": False, "message": _("طلب غير صالح.")}, status=405)

    po = get_object_or_404(PurchaseOrder, pk=pk)
    if po.status in ["PARTIALLY_RECEIVED", "FULLY_RECEIVED"]:
        return JsonResponse({"success": False, "message": _("لا يمكن إلغاء أمر تم استلام بضائع منه.")}, status=400)

    reason = request.POST.get("reason", "").strip() or _("إلغاء بطلب الإدارة")
    po.status = "CANCELLED"
    po.save(update_fields=["status"])

    messages.info(request, _(f"تم إلغاء أمر الشراء #{po.order_number}. السبب: {reason}"))
    return redirect("purchase:po_detail", pk=po.id)
