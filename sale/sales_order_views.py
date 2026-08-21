"""
Sales Order Views - Enterprise Lifecycle Management
إدارة أوامر البيع - دورة حياة المستندات والموافقات والربط مع المخازن
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

from sale.models.sales_models import SalesOrder, SalesOrderItem, DeliveryNote, SalesInvoice
from sale.models import Sale
from sale.models.quotation import Quotation
from sale.services.sales_service import SalesService
from product.models.product_core import Product
from product.models.stock_management import Warehouse
from client.models import Customer
from financial.exceptions import FinancialCoreError

logger = logging.getLogger(__name__)


@login_required
def sales_order_list(request):
    """
    قائمة أوامر البيع مع الفلاتر والإحصائيات ودعم AJAX
    """
    queryset = SalesOrder.objects.select_related("customer", "warehouse", "created_by", "quotation_reference").all().order_by("-order_date", "-id")

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
        queryset = queryset.filter(order_date__gte=date_from)

    if date_to:
        queryset = queryset.filter(order_date__lte=date_to)

    if search_query:
        queryset = queryset.filter(
            Q(order_number__icontains=search_query) |
            Q(customer__name__icontains=search_query)
        )

    # حساب الإحصائيات العامة
    all_orders = SalesOrder.objects.all()
    stats = {
        "total_count": all_orders.count(),
        "total_amount": all_orders.aggregate(total=Sum("total_amount"))["total"] or Decimal("0.00"),
        "draft_count": all_orders.filter(status__in=["DRAFT", "PENDING_APPROVAL"]).count(),
        "approved_count": all_orders.filter(status__in=["APPROVED", "CONFIRMED"]).count(),
        "delivered_count": all_orders.filter(status__in=["DELIVERED", "PARTIALLY_DELIVERED", "COMPLETED"]).count(),
    }

    # الترقيم
    paginator = Paginator(queryset, 25)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # Header & Breadcrumbs
    breadcrumb_items = [
        {"title": _("الرئيسية"), "url": reverse("core:dashboard"), "icon": "fa-home"},
        {"title": _("إدارة المبيعات"), "url": reverse("sale:sale_list"), "icon": "fa-shopping-cart"},
        {"title": _("أوامر البيع"), "active": True},
    ]

    header_buttons = [
        {
            "url": reverse("sale:sales_order_create"),
            "label": _("إنشاء أمر بيع جديد"),
            "icon": "fa-plus",
            "class": "btn-primary",
        }
    ]

    context = {
        "page_title": _("أوامر البيع"),
        "page_obj": page_obj,
        "sales_orders": page_obj.object_list,
        "stats": stats,
        "customers": Customer.objects.filter(is_active=True).only("id", "name"),
        "warehouses": Warehouse.objects.filter(is_active=True).only("id", "name"),
        "breadcrumb_items": breadcrumb_items,
        "header_buttons": header_buttons,
    }

    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.GET.get("ajax"):
        table_html = render_to_string("sale/partials/sales_order_table.html", context, request=request)
        pagination_html = render_to_string("partials/pagination.html", {"page_obj": page_obj}, request=request)
        return JsonResponse({
            "table_html": table_html,
            "pagination_html": pagination_html,
        })

    return render(request, "sale/sales_order_list.html", context)


@login_required
def sales_order_create(request, quotation_id=None):
    """
    إنشاء أمر بيع جديد (يدوياً أو من عرض سعر)
    """
    quotation = None
    if quotation_id:
        quotation = get_object_or_404(Quotation, pk=quotation_id)

    if request.method == "POST":
        customer_id = request.POST.get("customer")
        warehouse_id = request.POST.get("warehouse")
        order_date = request.POST.get("order_date") or timezone.now().date()
        currency = request.POST.get("currency", "EGP")
        exchange_rate = Decimal(request.POST.get("exchange_rate", "1.000000"))

        product_ids = request.POST.getlist("product[]")
        quantities = request.POST.getlist("quantity[]")
        unit_prices = request.POST.getlist("unit_price[]")
        discounts = request.POST.getlist("discount[]")

        try:
            customer = get_object_or_404(Customer, pk=customer_id)
            warehouse = get_object_or_404(Warehouse, pk=warehouse_id)

            items_data = []
            for i in range(len(product_ids)):
                if product_ids[i] and str(product_ids[i]).isdigit():
                    p_id = int(product_ids[i])
                    prod = Product.objects.get(pk=p_id)
                    qty = Decimal(str(quantities[i])) if i < len(quantities) and quantities[i] else Decimal("1")
                    price = Decimal(str(unit_prices[i])) if i < len(unit_prices) and unit_prices[i] else prod.selling_price
                    disc = Decimal(str(discounts[i])) if i < len(discounts) and discounts[i] else Decimal("0")

                    items_data.append({
                        "product": prod,
                        "ordered_qty": qty,
                        "unit_price": price,
                        "discount_percentage": disc,
                    })

            if not items_data:
                messages.error(request, _("يجب إضافة بند واحد على الأقل في أمر البيع."))
                return redirect("sale:sales_order_create")

            so = SalesService.create_sales_order(
                customer=customer,
                warehouse=warehouse,
                order_date=order_date,
                items_data=items_data,
                user=request.user,
                currency=currency,
                exchange_rate=exchange_rate,
                quotation_reference=quotation
            )

            if quotation:
                quotation.status = "accepted"
                quotation.save(update_fields=["status"])

            messages.success(request, f"تم إنشاء أمر البيع رقم {so.order_number} بنجاح.")
            return redirect("sale:sales_order_detail", pk=so.pk)

        except FinancialCoreError as fce:
            messages.error(request, f"خطأ حوكمة مبيعات: {str(fce)}")
        except Exception as e:
            logger.error(f"Error creating sales order: {e}", exc_info=True)
            messages.error(request, f"خطأ أثناء إنشاء أمر البيع: {str(e)}")

    customers = Customer.objects.filter(is_active=True).only("id", "name", "phone")
    warehouses = Warehouse.objects.filter(is_active=True).only("id", "name")
    products = Product.objects.filter(is_active=True).only("id", "name", "sku", "selling_price")

    breadcrumb_items = [
        {"title": _("الرئيسية"), "url": reverse("core:dashboard"), "icon": "fa-home"},
        {"title": _("أوامر البيع"), "url": reverse("sale:sales_order_list"), "icon": "fa-clipboard-list"},
        {"title": _("إنشاء أمر بيع"), "active": True},
    ]

    context = {
        "page_title": _("إنشاء أمر بيع جديد"),
        "customers": customers,
        "warehouses": warehouses,
        "products": products,
        "quotation": quotation,
        "breadcrumb_items": breadcrumb_items,
    }
    return render(request, "sale/sales_order_form.html", context)


@login_required
def sales_order_detail(request, pk):
    """
    عرض تفاصيل أمر البيع والبنود وإذون التسليم والفواتير المرتبطة
    """
    so = get_object_or_404(
        SalesOrder.objects.select_related("customer", "warehouse", "created_by", "quotation_reference")
        .prefetch_related("items__product", "delivery_notes", "invoices"),
        pk=pk
    )

    # التحقق من فواتير البيع المنشأة من هذا الأمر
    linked_sales = Sale.objects.filter(sales_order=so).order_by("-id")

    breadcrumb_items = [
        {"title": _("الرئيسية"), "url": reverse("core:dashboard"), "icon": "fa-home"},
        {"title": _("أوامر البيع"), "url": reverse("sale:sales_order_list"), "icon": "fa-clipboard-list"},
        {"title": f"{_('أمر بيع')} #{so.order_number}", "active": True},
    ]

    header_buttons = []
    if so.status in ["DRAFT", "PENDING_APPROVAL"]:
        header_buttons.append({
            "url": reverse("sale:sales_order_confirm", args=[so.pk]),
            "label": _("اعتماد أمر البيع"),
            "icon": "fa-check",
            "class": "btn-success",
            "is_post": True,
        })

    if so.status in ["APPROVED", "CONFIRMED", "PARTIALLY_DELIVERED"]:
        header_buttons.append({
            "url": f"{reverse('sale:delivery_note_create')}?so_id={so.pk}",
            "label": _("إصدار إذن تسليم"),
            "icon": "fa-truck",
            "class": "btn-info text-white",
        })
        header_buttons.append({
            "url": reverse("sale:sales_order_convert_to_sale", args=[so.pk]),
            "label": _("إصدار فاتورة مبيعات"),
            "icon": "fa-file-invoice-dollar",
            "class": "btn-primary",
        })

    context = {
        "page_title": f"{_('أمر بيع')} #{so.order_number}",
        "so": so,
        "items": so.items.all(),
        "delivery_notes": so.delivery_notes.all(),
        "linked_sales": linked_sales,
        "breadcrumb_items": breadcrumb_items,
        "header_buttons": header_buttons,
    }
    return render(request, "sale/sales_order_detail.html", context)


@login_required
@require_POST
def sales_order_confirm(request, pk):
    """
    اعتماد أمر البيع
    """
    so = get_object_or_404(SalesOrder, pk=pk)
    try:
        SalesService.approve_sales_order(so.id, request.user)
        messages.success(request, f"تم اعتماد أمر البيع #{so.order_number} بنجاح.")
    except Exception as e:
        messages.error(request, f"خطأ أثناء الاعتماد: {str(e)}")
    return redirect("sale:sales_order_detail", pk=pk)


@login_required
@require_POST
def sales_order_cancel(request, pk):
    """
    إلغاء أمر البيع
    """
    so = get_object_or_404(SalesOrder, pk=pk)
    if so.status in ["DELIVERED", "COMPLETED"]:
        messages.error(request, _("لا يمكن إلغاء أمر بيع تم تسليمه."))
    else:
        so.status = "CANCELLED"
        so.save(update_fields=["status"])
        messages.success(request, f"تم إلغاء أمر البيع #{so.order_number}.")
    return redirect("sale:sales_order_detail", pk=pk)


@login_required
def sales_order_convert_to_sale(request, pk):
    """
    تحويل أمر البيع إلى فاتورة مبيعات مباشرة مع ربط sales_order
    """
    so = get_object_or_404(SalesOrder.objects.prefetch_related("items__product"), pk=pk)

    # توجيه إلى صفحة إنشاء الفاتورة مع تعبئة البيانات مسبقاً
    sale_data = {
        "customer": so.customer_id,
        "sales_order": so.id,
        "warehouse": so.warehouse_id,
        "currency": so.currency,
        "exchange_rate": str(so.exchange_rate),
        "items": [
            {
                "product_id": item.product_id,
                "product_name": item.product.name,
                "quantity": str(item.ordered_qty - item.invoiced_qty if (item.ordered_qty - item.invoiced_qty) > 0 else item.ordered_qty),
                "unit_price": str(item.unit_price),
                "discount": str(item.discount_percentage),
            }
            for item in so.items.all()
        ]
    }
    request.session["prefill_sale_data"] = sale_data
    messages.info(request, f"تم نقل بيانات أمر البيع #{so.order_number} لإنشاء فاتورة مبيعات.")
    return redirect(f"{reverse('sale:sale_create')}?from_so={so.pk}")
