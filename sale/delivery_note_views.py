"""
Delivery Note Views - Warehouse & Sales Fulfillment Management
إدارة إذون تسليم البضائع والربط المخزني والمحاسبي وقيد تكلفة البضاعة المباعة
"""
import logging
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.utils import timezone
from django.utils.translation import gettext as _
from django.urls import reverse
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.template.loader import render_to_string
from django.http import JsonResponse

from sale.models.sales_models import DeliveryNote, DeliveryNoteItem, SalesOrder, SalesOrderItem
from sale.models import Sale
from sale.services.sales_service import SalesService
from product.models.stock_management import Warehouse
from client.models import Customer
from financial.models import JournalEntry
from financial.exceptions import FinancialCoreError

logger = logging.getLogger(__name__)


@login_required
def delivery_note_list(request):
    """
    قائمة إذون تسليم البضاعة مع الفلاتر والإحصائيات ودعم AJAX
    """
    queryset = DeliveryNote.objects.select_related("customer", "warehouse", "sales_order", "created_by").all().order_by("-delivery_date", "-id")

    # فلاتر البحث
    customer_id = request.GET.get("customer")
    status = request.GET.get("status")
    warehouse_id = request.GET.get("warehouse")
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")
    search_query = request.GET.get("search")

    if customer_id and customer_id.isdigit():
        queryset = queryset.filter(customer_id=int(customer_id))

    if status:
        queryset = queryset.filter(status=status)

    if warehouse_id and warehouse_id.isdigit():
        queryset = queryset.filter(warehouse_id=int(warehouse_id))

    if date_from:
        queryset = queryset.filter(delivery_date__gte=date_from)

    if date_to:
        queryset = queryset.filter(delivery_date__lte=date_to)

    if search_query:
        queryset = queryset.filter(
            Q(delivery_number__icontains=search_query) |
            Q(customer__name__icontains=search_query) |
            Q(sales_order__order_number__icontains=search_query)
        )

    # حساب الإحصائيات العامة
    all_dns = DeliveryNote.objects.all()
    stats = {
        "total_count": all_dns.count(),
        "draft_count": all_dns.filter(status="DRAFT").count(),
        "delivered_count": all_dns.filter(status__in=["DELIVERED", "CONFIRMED"]).count(),
        "invoiced_count": all_dns.filter(status="INVOICED").count(),
    }

    # الترقيم الموحد SSR
    from core.utils import paginate_queryset
    pagination_context = paginate_queryset(queryset, request)
    page_obj = pagination_context["page_obj"]

    # Header & Breadcrumbs
    breadcrumb_items = [
        {"title": _("الرئيسية"), "url": reverse("core:dashboard"), "icon": "fa-home"},
        {"title": _("إدارة المبيعات"), "url": reverse("sale:sale_list"), "icon": "fa-shopping-cart"},
        {"title": _("إذون تسليم البضاعة"), "active": True},
    ]

    header_buttons = [
        {
            "url": reverse("sale:delivery_note_create"),
            "label": _("إصدار إذن تسليم جديد"),
            "icon": "fa-plus",
            "class": "btn-primary",
        }
    ]

    context = {
        "page_title": _("إذون تسليم البضاعة"),
        **pagination_context,
        "delivery_notes": page_obj.object_list,
        "stats": stats,
        "customers": Customer.objects.filter(is_active=True).only("id", "name"),
        "warehouses": Warehouse.objects.filter(is_active=True).only("id", "name"),
        "breadcrumb_items": breadcrumb_items,
        "header_buttons": header_buttons,
    }

    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.GET.get("ajax"):
        table_html = render_to_string("sale/partials/delivery_note_table.html", context, request=request)
        pagination_html = render_to_string("partials/pagination.html", context, request=request)
        return JsonResponse({
            "table_html": table_html,
            "pagination_html": pagination_html,
        })

    return render(request, "sale/delivery_note_list.html", context)


@login_required
def delivery_note_create(request):
    """
    إنشاء إذن تسليم جديد لأمر بيع معتمد
    """
    so_id = request.GET.get("so_id") or request.POST.get("sales_order")
    sales_order = None
    if so_id and str(so_id).isdigit():
        sales_order = get_object_or_404(
            SalesOrder.objects.select_related("customer", "warehouse").prefetch_related("items__product"),
            pk=int(so_id)
        )

    if request.method == "POST":
        delivery_date = request.POST.get("delivery_date") or timezone.now().date()
        so_item_ids = request.POST.getlist("so_item_id[]")
        delivered_qtys = request.POST.getlist("delivered_qty[]")

        try:
            if not sales_order:
                so_id_post = request.POST.get("sales_order")
                sales_order = get_object_or_404(SalesOrder, pk=so_id_post)

            items_data = []
            for i in range(len(so_item_ids)):
                if so_item_ids[i] and str(so_item_ids[i]).isdigit():
                    so_item_id = int(so_item_ids[i])
                    qty = Decimal(str(delivered_qtys[i])) if i < len(delivered_qtys) and delivered_qtys[i] else Decimal("0")
                    if qty > Decimal("0"):
                        items_data.append({
                            "so_item_id": so_item_id,
                            "delivered_qty": qty,
                        })

            if not items_data:
                messages.error(request, _("يجب تحديد كمية تسليم موجبة لبند واحد على الأقل."))
                return redirect(f"{reverse('sale:delivery_note_create')}?so_id={sales_order.pk}")

            dn = SalesService.deliver_goods(
                so_id=sales_order.id,
                delivery_date=delivery_date,
                items_data=items_data,
                user=request.user
            )

            messages.success(request, f"تم إصدار إذن التسليم #{dn.delivery_number} وترحيل حركة المخزون وقيد التكلفة بنجاح.")
            return redirect("sale:delivery_note_detail", pk=dn.pk)

        except FinancialCoreError as fce:
            messages.error(request, f"خطأ حوكمة التسليم: {str(fce)}")
        except Exception as e:
            logger.error(f"Error issuing delivery note: {e}", exc_info=True)
            messages.error(request, f"خطأ أثناء إصدار إذن التسليم: {str(e)}")

    # أوامر البيع القابلة للتسليم
    available_orders = SalesOrder.objects.filter(
        status__in=["APPROVED", "CONFIRMED", "PARTIALLY_DELIVERED"]
    ).select_related("customer", "warehouse")

    breadcrumb_items = [
        {"title": _("الرئيسية"), "url": reverse("core:dashboard"), "icon": "fa-home"},
        {"title": _("إذون تسليم البضاعة"), "url": reverse("sale:delivery_note_list"), "icon": "fa-truck"},
        {"title": _("إصدار إذن تسليم"), "active": True},
    ]

    context = {
        "page_title": _("إصدار إذن تسليم بضاعة"),
        "sales_order": sales_order,
        "available_orders": available_orders,
        "breadcrumb_items": breadcrumb_items,
    }
    return render(request, "sale/delivery_note_form.html", context)


@login_required
def delivery_note_detail(request, pk):
    """
    عرض تفاصيل إذن التسليم والبنود وقيد التكلفة وفواتير المبيعات المرتبطة
    """
    dn = get_object_or_404(
        DeliveryNote.objects.select_related("customer", "warehouse", "sales_order", "created_by")
        .prefetch_related("items__so_item__product"),
        pk=pk
    )

    # البحث عن القيد المحاسبي المرتبط
    cogs_entry = JournalEntry.objects.filter(
        source_model="DeliveryNote",
        source_id=dn.id
    ).first()

    # فواتير المبيعات المنشأة من هذا الإذن
    linked_sales = Sale.objects.filter(delivery_note=dn).order_by("-id")

    breadcrumb_items = [
        {"title": _("الرئيسية"), "url": reverse("core:dashboard"), "icon": "fa-home"},
        {"title": _("إذون تسليم البضاعة"), "url": reverse("sale:delivery_note_list"), "icon": "fa-truck"},
        {"title": f"{_('إذن تسليم')} #{dn.delivery_number}", "active": True},
    ]

    header_buttons = []
    if dn.status in ["DELIVERED", "CONFIRMED"]:
        header_buttons.append({
            "url": reverse("sale:delivery_note_convert_to_sale", args=[dn.pk]),
            "label": _("إصدار فاتورة مبيعات"),
            "icon": "fa-file-invoice-dollar",
            "class": "btn-primary",
        })

    context = {
        "page_title": f"{_('إذن تسليم')} #{dn.delivery_number}",
        "dn": dn,
        "items": dn.items.all(),
        "cogs_entry": cogs_entry,
        "linked_sales": linked_sales,
        "breadcrumb_items": breadcrumb_items,
        "header_buttons": header_buttons,
    }
    return render(request, "sale/delivery_note_detail.html", context)


@login_required
def delivery_note_convert_to_sale(request, pk):
    """
    تحويل إذن التسليم إلى فاتورة مبيعات مع تفعيل Double-COGS Guard
    """
    dn = get_object_or_404(
        DeliveryNote.objects.select_related("sales_order", "customer", "warehouse")
        .prefetch_related("items__so_item__product"),
        pk=pk
    )

    sale_data = {
        "customer": dn.customer_id,
        "delivery_note": dn.id,
        "sales_order": dn.sales_order_id if dn.sales_order else None,
        "warehouse": dn.warehouse_id,
        "currency": dn.sales_order.currency if dn.sales_order else "EGP",
        "exchange_rate": str(dn.sales_order.exchange_rate) if dn.sales_order else "1.000000",
        "items": [
            {
                "product_id": item.so_item.product_id,
                "product_name": item.so_item.product.name,
                "quantity": str(item.delivered_qty),
                "unit_price": str(item.so_item.unit_price),
                "discount": str(item.so_item.discount_percentage),
            }
            for item in dn.items.all()
        ]
    }
    request.session["prefill_sale_data"] = sale_data
    messages.info(request, f"تم تجهيز فاتورة مبيعات لإذن التسليم #{dn.delivery_number} مع حماية كبح التكلفة المزدوجة.")
    return redirect(f"{reverse('sale:sale_create')}?from_dn={dn.pk}")
