"""
Sales Order Views - Enterprise Lifecycle Management
إدارة أوامر البيع - دورة حياة المستندات والموافقات والربط مع المخازن
"""
import json
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
from django.db import transaction
from django.db.models import Q, Sum
from django.template.loader import render_to_string
from django.http import JsonResponse

from sale.models.sales_models import SalesOrder, SalesOrderItem, DeliveryNote, SalesInvoice
from sale.models import Sale
from sale.models.quotation import Quotation
from sale.models.pricing import PriceList
from sale.services import SaleService
from sale.services.sales_service import SalesService
from product.models.product_core import Product
from product.models.stock_management import Warehouse
from customer.models import Customer
from core.models import SystemSetting
from financial.models import Currency, CostCenter
from financial.services.exchange_rate_service import ExchangeRateService
from financial.exceptions import FinancialCoreError

logger = logging.getLogger(__name__)


def check_sales_orders_enabled(view_func):
    def _wrapped_view(request, *args, **kwargs):
        from core.models import SystemSetting
        enabled = SystemSetting.get_bool('enable_sales_orders', False)
        if not enabled:
            return render(request, "core/permission_denied.html", {
                "title": _("ميزة معطلة"),
                "message": _("ميزة أوامر البيع غير مفعلة لهذا الحساب/الشركة. يرجى تفعيلها من الإعدادات أولاً.")
            })
        return view_func(request, *args, **kwargs)
    return _wrapped_view


@login_required
@check_sales_orders_enabled
def sales_order_list(request):
    """
    قائمة أوامر البيع مع الفلاتر والإحصائيات ودعم AJAX
    """
    queryset = SalesOrder.objects.select_related(
        "customer", "warehouse", "created_by", "quotation_reference", "salesman"
    ).all().order_by("-order_date", "-id")

    # فلاتر البحث
    customer_id = request.GET.get("customer")
    status = request.GET.get("status")
    warehouse_id = request.GET.get("warehouse")
    salesman_id = request.GET.get("salesman")
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")
    search_query = request.GET.get("q") or request.GET.get("search")

    if customer_id and customer_id.isdigit():
        queryset = queryset.filter(customer_id=int(customer_id))

    if status:
        queryset = queryset.filter(status=status)

    if warehouse_id and warehouse_id.isdigit():
        queryset = queryset.filter(warehouse_id=int(warehouse_id))

    if salesman_id and salesman_id.isdigit():
        queryset = queryset.filter(salesman_id=int(salesman_id))

    if date_from:
        queryset = queryset.filter(order_date__gte=date_from)

    if date_to:
        queryset = queryset.filter(order_date__lte=date_to)

    if search_query:
        from utils.search import smart_search_filter
        queryset = smart_search_filter(
            queryset,
            search_query,
            text_fields=['customer__name', 'customer__company_name'],
            code_fields=['order_number', 'customer__code', 'customer__phone']
        )

    # حساب الإحصائيات العامة
    all_orders = SalesOrder.objects.all()
    total_count = all_orders.count()
    total_value = all_orders.aggregate(total=Sum("total_amount"))["total"] or Decimal("0.00")
    draft_count = all_orders.filter(status__in=["DRAFT", "PENDING_APPROVAL"]).count()
    approved_count = all_orders.filter(status__in=["APPROVED", "CONFIRMED"]).count()
    delivered_count = all_orders.filter(status__in=["DELIVERED", "PARTIALLY_DELIVERED", "FULLY_DELIVERED", "COMPLETED"]).count()

    stats = {
        "total_count": total_count,
        "total_amount": total_value,
        "draft_count": draft_count,
        "approved_count": approved_count,
        "delivered_count": delivered_count,
    }

    # الترقيم الموحد SSR
    from core.utils import paginate_queryset
    pagination_context = paginate_queryset(queryset, request)
    page_obj = pagination_context["page_obj"]

    # Header & Breadcrumbs
    breadcrumb_items = [
        {"title": _("الرئيسية"), "url": reverse("core:dashboard"), "icon": "fa-home"},
        {"title": _("إدارة المبيعات"), "url": reverse("sale:sale_list"), "icon": "fa-shopping-cart"},
        {"title": _("أوامر البيع"), "active": True},
    ]

    header_buttons = [
        {
            "url": reverse("sale:sales_order_create"),
            "text": _("إنشاء أمر بيع جديد"),
            "label": _("إنشاء أمر بيع جديد"),
            "icon": "fa-plus",
            "class": "btn-primary",
        }
    ]

    from django.contrib.auth import get_user_model
    User = get_user_model()

    context = {
        "page_title": _("أوامر البيع"),
        "page_icon": "fas fa-clipboard-list",
        "page_subtitle": _("إدارة واعتماد أوامر البيع ومتابعة التسليم المخزني والفوترة"),
        **pagination_context,
        "sales_orders": page_obj.object_list,
        "stats": stats,
        "total_count": total_count,
        "total_value": total_value,
        "draft_count": draft_count,
        "approved_count": approved_count,
        "delivered_count": delivered_count,
        "status_choices": SalesOrder.STATUS_CHOICES,
        "customers": Customer.objects.filter(is_active=True).only("id", "name"),
        "warehouses": Warehouse.objects.filter(is_active=True).only("id", "name"),
        "salesmen": User.objects.filter(is_active=True).only("id", "first_name", "last_name", "username"),
        "breadcrumb_items": breadcrumb_items,
        "header_buttons": header_buttons,
        "search_query": search_query or "",
        "selected_customer": customer_id or "",
        "selected_warehouse": warehouse_id or "",
        "selected_salesman": salesman_id or "",
        "selected_status": status or "",
        "selected_date_from": date_from or "",
        "selected_date_to": date_to or "",
    }

    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.GET.get("ajax"):
        table_html = render_to_string("sale/partials/sales_order_table.html", context, request=request)
        pagination_html = render_to_string("partials/pagination.html", context, request=request)
        return JsonResponse({
            "table_html": table_html,
            "pagination_html": pagination_html,
        })

    return render(request, "sale/sales_order_list.html", context)


@login_required
@check_sales_orders_enabled
def sales_order_create(request, quotation_id=None):
    """
    إنشاء أمر بيع جديد (يدوياً أو من عرض سعر)
    """
    quotation = None
    if quotation_id:
        quotation = get_object_or_404(Quotation.objects.prefetch_related("items__product"), pk=quotation_id)
        if quotation.status == "rejected":
            messages.error(request, _("لا يمكن تحويل عرض سعر مرفوض إلى أمر بيع."))
            return redirect("sale:quotation_detail", pk=quotation.pk)

        # Check if already converted
        existing_so = SalesOrder.objects.filter(quotation_reference=quotation).exclude(status="CANCELLED").first()
        if existing_so:
            messages.warning(request, f"يوجد أمر بيع قائم بالفعل (#{existing_so.order_number}) مرتبط بعرض السعر هذا.")

    if request.method == "POST":
        customer_id = request.POST.get("customer")
        warehouse_id = request.POST.get("warehouse")
        from django.utils.dateparse import parse_date
        order_date_raw = request.POST.get("order_date")
        order_date = parse_date(order_date_raw) if order_date_raw else timezone.localdate()
        currency_input = request.POST.get("currency")
        from financial.models import Currency
        if currency_input and str(currency_input).isdigit():
            c_obj = Currency.objects.filter(id=int(currency_input)).first()
            currency_val = c_obj.code if c_obj else None
        elif currency_input:
            c_obj = Currency.objects.filter(code__iexact=str(currency_input).strip()).first()
            currency_val = c_obj.code if c_obj else str(currency_input).strip()
        else:
            c_obj = None
            currency_val = None

        if not currency_val:
            func_c = Currency.objects.filter(is_functional=True).first() or Currency.objects.first()
            currency_val = func_c.code if func_c else "EGP"

        exchange_rate_str = request.POST.get("exchange_rate", "1.000000")
        try:
            exchange_rate = Decimal(str(exchange_rate_str).replace(',', '').strip())
        except Exception:
            exchange_rate = Decimal("1.000000")

        price_list_id = request.POST.get("price_list")
        if price_list_id and str(price_list_id).isdigit():
            price_list_id = int(price_list_id)
        else:
            price_list_id = None

        salesman_id = request.POST.get("salesman")
        salesman = None
        if salesman_id and str(salesman_id).isdigit():
            from django.contrib.auth import get_user_model
            salesman = get_user_model().objects.filter(id=int(salesman_id)).first()

        cost_center_id = request.POST.get("cost_center")
        cost_center = None
        if cost_center_id and str(cost_center_id).isdigit():
            from financial.models import CostCenter
            cost_center = CostCenter.objects.filter(id=int(cost_center_id)).first()

        expected_delivery_date_raw = request.POST.get("expected_delivery_date")
        expected_delivery_date = parse_date(expected_delivery_date_raw) if expected_delivery_date_raw else None
        reservation_expiry_date_raw = request.POST.get("reservation_expiry_date")
        reservation_expiry_date = parse_date(reservation_expiry_date_raw) if reservation_expiry_date_raw else None
        shipping_method = request.POST.get("shipping_method", "PICKUP")
        shipping_address = request.POST.get("shipping_address", "")
        notes = request.POST.get("notes", "")

        discount_amount = Decimal(request.POST.get("discount", "0") or "0")
        discount_type = request.POST.get("discount_type", "fixed")
        adjustment_name = request.POST.get("adjustment_name", "").strip()
        adjustment_amount = Decimal(request.POST.get("adjustment_amount", "0") or "0")
        vat_rate = Decimal(request.POST.get("vat_rate", "14.00") or "14.00")
        tax_amount_val = request.POST.get("tax_amount")
        tax_amount = Decimal(tax_amount_val) if tax_amount_val else None

        wht_active = request.POST.get("wht_active") == "on" or request.POST.get("wht_active") == "true"
        wht_rate = Decimal(request.POST.get("wht_rate", "1.00") or "1.00")
        wht_amount_val = request.POST.get("wht_amount")
        wht_amount = Decimal(wht_amount_val) if wht_amount_val else None
        required_down_payment = Decimal(request.POST.get("required_down_payment", "0") or "0")
        down_payment_type = request.POST.get("down_payment_type", "fixed")
        instant_down_payment = request.POST.get("instant_down_payment") == "on"
        instant_treasury = request.POST.get("instant_treasury_account")
        instant_payment_method = request.POST.get("instant_payment_method", "cash")

        # Custom Fields
        custom_fields = SaleService.parse_custom_fields(request.POST.get("custom_fields_json", "[]"))

        from financial.models import Currency
        currency_code = "EGP"
        if currency_val:
            if str(currency_val).isdigit():
                curr_obj = Currency.objects.filter(id=int(currency_val)).first()
                if curr_obj:
                    currency_code = curr_obj.code
            else:
                currency_code = str(currency_val)

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
                    qty_str = str(quantities[i]).replace(',', '').strip() if i < len(quantities) and quantities[i] else "1"
                    qty = Decimal(qty_str) if qty_str else Decimal("1")
                    price_str = str(unit_prices[i]).replace(',', '').strip() if i < len(unit_prices) and unit_prices[i] else str(prod.selling_price)
                    price = Decimal(price_str) if price_str else prod.selling_price
                    disc_str = str(discounts[i]).replace(',', '').strip() if i < len(discounts) and discounts[i] else "0"
                    disc = Decimal(disc_str) if disc_str else Decimal("0")

                    if qty <= 0:
                        raise ValueError(_("الكمية يجب أن تكون أكبر من صفر (البند رقم {})").format(i + 1))

                    items_data.append({
                        "product": prod,
                        "ordered_qty": qty,
                        "unit_price": price,
                        "discount_percentage": disc,
                    })

            if not items_data:
                messages.error(request, _("يجب إضافة بند واحد على الأقل في أمر البيع."))
                return redirect(request.path)

            so = SalesService.create_sales_order(
                customer=customer,
                warehouse=warehouse,
                order_date=order_date,
                items_data=items_data,
                user=request.user,
                currency=currency_code,
                exchange_rate=exchange_rate,
                price_list_id=price_list_id,
                quotation_reference=quotation,
                salesman=salesman,
                cost_center=cost_center,
                expected_delivery_date=expected_delivery_date,
                reservation_expiry_date=reservation_expiry_date,
                shipping_method=shipping_method,
                shipping_address=shipping_address,
                discount_amount=discount_amount,
                discount_type=discount_type,
                adjustment_name=adjustment_name,
                adjustment_amount=adjustment_amount,
                vat_rate=vat_rate,
                tax_amount=tax_amount,
                wht_active=wht_active,
                wht_rate=wht_rate,
                wht_amount=wht_amount,
                required_down_payment=required_down_payment,
                down_payment_type=down_payment_type,
                notes=notes,
                custom_fields=custom_fields,
            )

            if quotation:
                quotation.status = "accepted"
                quotation.save(update_fields=["status"])

            # معالجة التحصيل الفوري للعربون إن طُلب وتوفرت صلاحية الخزينة
            if instant_down_payment and so.effective_required_down_payment > Decimal("0.00") and instant_treasury:
                try:
                    from customer.services.customer_allocation_audit_service import CustomerAllocationAuditService
                    curr_model = Currency.objects.filter(code=so.currency).first()
                    CustomerAllocationAuditService.create_prepaid_payment(
                        customer_id=so.customer_id,
                        amount=so.effective_required_down_payment,
                        payment_date=so.order_date,
                        payment_method=instant_payment_method,
                        financial_account_id=int(instant_treasury),
                        currency=curr_model,
                        user=request.user,
                        sales_order=so,
                        cost_center=so.cost_center,
                        salesman=so.salesman,
                        notes=f"تحصيل فوري لدفعة مقدمة أمر بيع #{so.order_number}"
                    )
                    messages.info(request, f"تم تحصيل الدفعة المقدمة المشترطة ({so.effective_required_down_payment} {so.currency}) بالخزينة فوراً.")
                except Exception as pay_err:
                    logger.warning(f"Failed instant down payment collection: {pay_err}")
                    messages.warning(request, f"تم إنشاء أمر البيع ولكن تعذر تسجيل حركة الخزينة الفورية: {str(pay_err)}")

            messages.success(request, f"تم إنشاء أمر البيع رقم {so.order_number} بنجاح.")
            return redirect("sale:sales_order_detail", pk=so.pk)

        except FinancialCoreError as fce:
            messages.error(request, f"خطأ حوكمة مبيعات: {str(fce)}")
        except Exception as e:
            logger.error(f"Error creating sales order: {e}", exc_info=True)
            messages.error(request, f"خطأ أثناء إنشاء أمر البيع: {str(e)}")

    from financial.models import Currency, CostCenter
    from financial.services.exchange_rate_service import ExchangeRateService
    currencies = list(Currency.objects.filter(is_active=True).order_by("code"))
    for c in currencies:
        c.current_rate = ExchangeRateService.get_exchange_rate(c)

    customers = Customer.objects.filter(is_active=True).order_by("name")
    warehouses = Warehouse.objects.filter(is_active=True).order_by("name")
    products = Product.objects.filter(is_active=True).order_by("name")
    price_lists = PriceList.objects.filter(is_active=True).order_by("name")
    cost_centers = CostCenter.objects.filter(is_active=True).order_by("code") if hasattr(CostCenter, "objects") else []

    from django.contrib.auth import get_user_model
    salesmen = get_user_model().objects.filter(is_active=True).order_by("first_name", "username")

    functional_curr = Currency.objects.filter(is_functional=True).first() or (currencies[0] if currencies else None)
    selected_curr = None
    if quotation and getattr(quotation, "currency", None):
        if isinstance(quotation.currency, Currency):
            selected_curr = quotation.currency
        else:
            selected_curr = Currency.objects.filter(code=str(quotation.currency)).first()
    if not selected_curr:
        selected_curr = functional_curr

    current_rate = Decimal("1.000000")
    if quotation and getattr(quotation, 'exchange_rate', None):
        current_rate = quotation.exchange_rate
    elif selected_curr:
        current_rate = ExchangeRateService.get_exchange_rate(selected_curr) or Decimal("1.000000")

    next_order_number = None
    try:
        from core.services.sequence_service import SequenceService
        from core.enums.document_types import DocumentType
        next_order_number = SequenceService.peek_next_number(DocumentType.SALES_ORDER)
    except Exception as e:
        logger.error(f"Error peeking next sales order number: {e}")

    breadcrumb_items = [
        {"title": _("الرئيسية"), "url": reverse("core:dashboard"), "icon": "fa-home"},
        {"title": _("أوامر البيع"), "url": reverse("sale:sales_order_list"), "icon": "fa-clipboard-list"},
        {"title": _("إنشاء أمر بيع"), "active": True},
    ]

    custom_fields_merged = SaleService.smart_merge_custom_fields('sales_order', quotation.custom_fields if quotation else [])

    from financial.services.account_helper import AccountHelperService
    cash_payment_accounts = AccountHelperService.get_cash_accounts()
    bank_payment_accounts = AccountHelperService.get_bank_accounts()
    treasury_accounts = AccountHelperService.get_cash_and_bank_accounts()

    context = {
        "page_title": _("إنشاء أمر بيع جديد"),
        "page_icon": "fas fa-cart-plus",
        "page_subtitle": _("إنشاء وتأكيد أمر بيع جديد وحجز المخزون"),
        "is_edit": False,
        "customers": customers,
        "selected_customer": quotation.customer if quotation else None,
        "warehouses": warehouses,
        "default_warehouse": getattr(quotation, "warehouse", None) or (warehouses.first() if warehouses.exists() else None),
        "products": products,
        "currencies": currencies,
        "price_lists": price_lists,
        "cost_centers": cost_centers,
        "salesmen": salesmen,
        "cash_payment_accounts": cash_payment_accounts,
        "bank_payment_accounts": bank_payment_accounts,
        "treasury_accounts": treasury_accounts,
        "quotation": quotation,
        "initial_notes": quotation.notes if quotation else "",
        "selected_currency_id": selected_curr.id if selected_curr else None,
        "selected_currency_is_foreign": not (selected_curr.is_functional) if selected_curr else False,
        "current_exchange_rate": current_rate,
        "functional_currency": functional_curr,
        "currency_symbol": selected_curr.symbol if selected_curr and selected_curr.symbol else (selected_curr.code if selected_curr else "ج.م"),
        "next_order_number": next_order_number,
        "allowed_item_types": "both",
        "custom_fields_json": json.dumps(custom_fields_merged),
        "custom_fields_display_mode": SystemSetting.get_setting('custom_fields_display_mode', 'expanded'),
        "enable_custom_fields": SystemSetting.get_setting('enable_custom_fields', 'true'),
        "breadcrumb_items": breadcrumb_items,
    }
    return render(request, "sale/sales_order_form.html", context)


@login_required
@check_sales_orders_enabled
def sales_order_edit(request, pk):
    """
    تعديل أمر بيع قائم (في حالة المسودة)
    """
    so = get_object_or_404(
        SalesOrder.objects.prefetch_related("items__product").select_related("customer", "warehouse"),
        pk=pk
    )

    if so.status not in ["DRAFT", "PENDING_APPROVAL"]:
        messages.error(request, _("لا يمكن تعديل أمر البيع بعد اعتماده أو تنفيذه جزئياً."))
        return redirect("sale:sales_order_detail", pk=so.pk)

    if request.method == "POST":
        customer_id = request.POST.get("customer")
        warehouse_id = request.POST.get("warehouse")
        from django.utils.dateparse import parse_date
        order_date_raw = request.POST.get("order_date")
        order_date = parse_date(order_date_raw) if order_date_raw else so.order_date
        expected_delivery_date_raw = request.POST.get("expected_delivery_date")
        expected_delivery_date = parse_date(expected_delivery_date_raw) if expected_delivery_date_raw else None
        reservation_expiry_date_raw = request.POST.get("reservation_expiry_date")
        reservation_expiry_date = parse_date(reservation_expiry_date_raw) if reservation_expiry_date_raw else None
        currency_input = request.POST.get("currency", so.currency)
        from financial.models import Currency
        if currency_input and str(currency_input).isdigit():
            c_obj = Currency.objects.filter(id=int(currency_input)).first()
            currency_val = c_obj.code if c_obj else None
        elif currency_input:
            c_obj = Currency.objects.filter(code__iexact=str(currency_input).strip()).first()
            currency_val = c_obj.code if c_obj else str(currency_input).strip()
        else:
            c_obj = None
            currency_val = None

        if not currency_val:
            func_c = Currency.objects.filter(is_functional=True).first() or Currency.objects.first()
            currency_val = func_c.code if func_c else (so.currency or "EGP")

        exchange_rate_str = request.POST.get("exchange_rate", str(so.exchange_rate))
        try:
            exchange_rate = Decimal(str(exchange_rate_str).replace(',', '').strip())
        except Exception:
            exchange_rate = Decimal("1.000000")

        # فحص قفل العميل في حال وجود دفعات مسددة
        if so.paid_down_payment > Decimal("0.00") and customer_id and int(customer_id) != so.customer_id:
            messages.error(request, _("لا يمكن تغيير العميل نظراً لوجود دفعات مسددة ومرتبطة بهذا الأمر."))
            return redirect("sale:sales_order_edit", pk=so.pk)

        salesman_id = request.POST.get("salesman")
        salesman = None
        if salesman_id and str(salesman_id).isdigit():
            from django.contrib.auth import get_user_model
            salesman = get_user_model().objects.filter(id=int(salesman_id)).first()

        cost_center_id = request.POST.get("cost_center")
        cost_center = None
        if cost_center_id and str(cost_center_id).isdigit():
            from financial.models import CostCenter
            cost_center = CostCenter.objects.filter(id=int(cost_center_id)).first()

        product_ids = request.POST.getlist("product[]")
        quantities = request.POST.getlist("quantity[]")
        unit_prices = request.POST.getlist("unit_price[]")
        discounts = request.POST.getlist("discount[]")

        try:
            customer = get_object_or_404(Customer, pk=customer_id)
            warehouse = get_object_or_404(Warehouse, pk=warehouse_id)

            with transaction.atomic():
                so.customer = customer
                so.warehouse = warehouse
                so.order_date = order_date
                so.salesman = salesman
                so.cost_center = cost_center
                so.currency = currency_val
                so.exchange_rate = exchange_rate
                so.expected_delivery_date = expected_delivery_date
                so.reservation_expiry_date = reservation_expiry_date
                so.shipping_method = request.POST.get("shipping_method", "PICKUP")
                so.shipping_address = request.POST.get("shipping_address", "")
                so.notes = request.POST.get("notes", "")

                so.discount_amount = Decimal(request.POST.get("discount", "0") or "0")
                so.discount_type = request.POST.get("discount_type", "fixed")
                so.adjustment_name = request.POST.get("adjustment_name", "").strip()
                so.adjustment_amount = Decimal(request.POST.get("adjustment_amount", "0") or "0")
                so.vat_rate = Decimal(request.POST.get("vat_rate", "14.00") or "14.00")
                so.wht_active = request.POST.get("wht_active") == "on" or request.POST.get("wht_active") == "true"
                so.wht_rate = Decimal(request.POST.get("wht_rate", "1.00") or "1.00")
                so.required_down_payment = Decimal(request.POST.get("required_down_payment", "0") or "0")
                so.down_payment_type = request.POST.get("down_payment_type", "fixed")
                so.custom_fields = SaleService.parse_custom_fields(request.POST.get("custom_fields_json", "[]"))

                # Recreate items
                so.items.all().delete()
                subtotal_val = Decimal("0.00")

                for i in range(len(product_ids)):
                    if product_ids[i] and str(product_ids[i]).isdigit():
                        p_id = int(product_ids[i])
                        prod = Product.objects.get(pk=p_id)
                        qty = Decimal(str(quantities[i]).replace(',', '').strip())
                        price = Decimal(str(unit_prices[i]).replace(',', '').strip())
                        disc = Decimal(str(discounts[i]).replace(',', '').strip() if discounts[i] else "0")

                        line_total = (qty * price * (Decimal("1.00") - (disc / Decimal("100.00")))).quantize(Decimal("0.01"))
                        subtotal_val += line_total

                        SalesOrderItem.objects.create(
                            sales_order=so,
                            product=prod,
                            ordered_qty=qty,
                            unit_price=price,
                            discount_percentage=disc,
                            line_total=line_total
                        )

                so.subtotal = subtotal_val
                eff_discount = (subtotal_val * (so.discount_amount / Decimal("100.00"))).quantize(Decimal("0.01")) if so.discount_type == "percentage" else min(so.discount_amount, subtotal_val)
                after_discount = max(Decimal("0.00"), subtotal_val - eff_discount)
                after_adj = after_discount + so.adjustment_amount

                calc_vat = (after_adj * (so.vat_rate / Decimal("100.00"))).quantize(Decimal("0.01")) if so.vat_rate else Decimal("0.00")
                calc_wht = (after_adj * (so.wht_rate / Decimal("100.00"))).quantize(Decimal("0.01")) if (so.wht_active and so.wht_rate) else Decimal("0.00")

                new_total = (after_adj + calc_vat - calc_wht).quantize(Decimal("0.01"))

                # حظر تقليص إجمالي أمر البيع لأقل من المحصل فعلياً
                if new_total < so.paid_down_payment:
                    raise ValueError(f"لا يمكن تقليص إجمالي أمر البيع ({new_total}) لأقل من المبالغ المحصلة فعلياً ({so.paid_down_payment}).")

                so.tax_amount = calc_vat
                so.wht_amount = calc_wht
                so.total_amount = new_total
                so.functional_amount = (so.total_amount * exchange_rate).quantize(Decimal("0.01"))
                so.save()

            messages.success(request, f"تم تحديث أمر البيع #{so.order_number} بنجاح.")
            return redirect("sale:sales_order_detail", pk=so.pk)
        except Exception as e:
            logger.error(f"Error updating sales order: {e}", exc_info=True)
            messages.error(request, f"خطأ أثناء تعديل أمر البيع: {str(e)}")

    from financial.models import Currency, CostCenter
    from django.contrib.auth import get_user_model
    currencies = list(Currency.objects.filter(is_active=True).order_by("code"))
    for c in currencies:
        c.current_rate = ExchangeRateService.get_exchange_rate(c)

    customers = Customer.objects.filter(is_active=True).order_by("name")
    warehouses = Warehouse.objects.filter(is_active=True).order_by("name")
    products = Product.objects.filter(is_active=True).order_by("name")
    price_lists = PriceList.objects.filter(is_active=True).order_by("name")
    cost_centers = CostCenter.objects.filter(is_active=True).order_by("code") if hasattr(CostCenter, "objects") else []
    salesmen = get_user_model().objects.filter(is_active=True).order_by("first_name", "username")

    functional_curr = Currency.objects.filter(is_functional=True).first() or (currencies[0] if currencies else None)
    curr_obj = Currency.objects.filter(code=so.currency).first() or functional_curr
    currency_symbol = curr_obj.symbol if curr_obj and curr_obj.symbol else (curr_obj.code if curr_obj else "ج.م")

    breadcrumb_items = [
        {"title": _("الرئيسية"), "url": reverse("core:dashboard"), "icon": "fa-home"},
        {"title": _("أوامر البيع"), "url": reverse("sale:sales_order_list"), "icon": "fa-clipboard-list"},
        {"title": f"تعديل أمر #{so.order_number}", "active": True},
    ]

    custom_fields_merged = SaleService.smart_merge_custom_fields('sales_order', so.custom_fields or [])

    from financial.services.account_helper import AccountHelperService
    cash_payment_accounts = AccountHelperService.get_cash_accounts()
    bank_payment_accounts = AccountHelperService.get_bank_accounts()
    treasury_accounts = AccountHelperService.get_cash_and_bank_accounts()

    context = {
        "page_title": f"تعديل أمر البيع #{so.order_number}",
        "page_icon": "fas fa-edit",
        "page_subtitle": f"تعديل بيانات وبنود أمر البيع رقم {so.order_number}",
        "so": so,
        "is_edit": True,
        "customers": customers,
        "selected_customer": so.customer,
        "warehouses": warehouses,
        "default_warehouse": so.warehouse,
        "products": products,
        "currencies": currencies,
        "price_lists": price_lists,
        "cost_centers": cost_centers,
        "salesmen": salesmen,
        "cash_payment_accounts": cash_payment_accounts,
        "bank_payment_accounts": bank_payment_accounts,
        "treasury_accounts": treasury_accounts,
        "quotation": so.quotation_reference if so else None,
        "initial_notes": so.notes if so else "",
        "selected_currency_id": curr_obj.id if curr_obj else None,
        "selected_currency_is_foreign": not (curr_obj.is_functional) if curr_obj else False,
        "current_exchange_rate": so.exchange_rate,
        "functional_currency": functional_curr,
        "currency_symbol": currency_symbol,
        "allowed_item_types": "both",
        "custom_fields_json": json.dumps(custom_fields_merged),
        "custom_fields_display_mode": SystemSetting.get_setting('custom_fields_display_mode', 'expanded'),
        "enable_custom_fields": SystemSetting.get_setting('enable_custom_fields', 'true'),
        "breadcrumb_items": breadcrumb_items,
    }
    return render(request, "sale/sales_order_form.html", context)


@login_required
@check_sales_orders_enabled
def sales_order_detail(request, pk):
    """
    عرض تفاصيل أمر البيع والبنود وإذون التسليم والدفعات المقدمة والفواتير المرتبطة
    """
    so = get_object_or_404(
        SalesOrder.objects.select_related(
            "customer", "warehouse", "created_by", "quotation_reference", "salesman", "cost_center", "price_list"
        ).prefetch_related(
            "items__product__unit", 
            "delivery_notes__warehouse", 
            "delivery_notes__created_by",
            "down_payments__financial_account"
        ),
        pk=pk
    )

    # التحقق من فواتير البيع المنشأة من هذا الأمر
    linked_sales = Sale.objects.filter(sales_order=so).select_related("customer", "warehouse", "created_by").order_by("-id")

    items = so.items.all()
    total_ordered_qty = sum(item.ordered_qty for item in items)
    total_delivered_qty = sum(item.delivered_qty for item in items)
    total_invoiced_qty = sum(item.invoiced_qty for item in items)
    total_remaining_qty = max(Decimal("0.00"), total_ordered_qty - total_delivered_qty)

    delivery_progress = round((total_delivered_qty / total_ordered_qty) * 100, 1) if total_ordered_qty > 0 else 0
    invoicing_progress = round((total_invoiced_qty / total_ordered_qty) * 100, 1) if total_ordered_qty > 0 else 0

    # حساب مرحلة دورة حياة المستند
    if so.status in ["INVOICED"] or (total_invoiced_qty >= total_ordered_qty and total_ordered_qty > 0):
        current_step = 4
    elif so.status in ["DELIVERED", "FULLY_DELIVERED"] or (total_delivered_qty >= total_ordered_qty and total_ordered_qty > 0):
        current_step = 3
    elif so.status in ["PARTIALLY_DELIVERED", "PARTIALLY_INVOICED"]:
        current_step = 2.5
    elif so.status in ["APPROVED", "CONFIRMED"]:
        current_step = 2
    else:
        current_step = 1

    breadcrumb_items = [
        {"title": _("الرئيسية"), "url": reverse("core:dashboard"), "icon": "fa-home"},
        {"title": _("المبيعات"), "url": reverse("sale:sale_list"), "icon": "fa-shopping-cart"},
        {"title": _("أوامر البيع"), "url": reverse("sale:sales_order_list"), "icon": "fa-clipboard-list"},
        {"title": f"{_('أمر بيع')} #{so.order_number}", "active": True},
    ]

    header_buttons = [
        {
            "url": reverse("sale:sales_order_print", args=[so.pk]),
            "text": _("طباعة أمر البيع"),
            "label": _("طباعة أمر البيع"),
            "icon": "fa-print",
            "class": "btn-outline-secondary",
            "target": "_blank",
        }
    ]

    if so.status in ["DRAFT", "PENDING_APPROVAL"]:
        header_buttons.append({
            "url": reverse("sale:sales_order_edit", args=[so.pk]),
            "text": _("تعديل أمر البيع"),
            "label": _("تعديل أمر البيع"),
            "icon": "fa-edit",
            "class": "btn-outline-primary",
        })
        header_buttons.append({
            "onclick": "confirmApproveOrder()",
            "text": _("اعتماد أمر البيع"),
            "label": _("اعتماد أمر البيع"),
            "icon": "fa-check",
            "class": "btn-success",
        })

    if so.status in ["APPROVED", "CONFIRMED", "PARTIALLY_DELIVERED"]:
        header_buttons.append({
            "url": f"{reverse('sale:delivery_note_create')}?so_id={so.pk}",
            "text": _("إصدار إذن تسليم"),
            "label": _("إصدار إذن تسليم"),
            "icon": "fa-truck",
            "class": "btn-info text-white",
        })
        header_buttons.append({
            "url": reverse("sale:sales_order_convert_to_sale", args=[so.pk]),
            "text": _("إصدار فاتورة مبيعات"),
            "label": _("إصدار فاتورة مبيعات"),
            "icon": "fa-file-invoice-dollar",
            "class": "btn-primary",
        })

    if so.status not in ["CANCELLED", "FULLY_DELIVERED", "INVOICED"]:
        header_buttons.append({
            "onclick": "confirmCancelOrder()",
            "text": _("إلغاء أمر البيع"),
            "label": _("إلغاء أمر البيع"),
            "icon": "fa-times-circle",
            "class": "btn-outline-danger",
        })

    can_collect_down_payment = (
        request.user.has_perm("financial.add_financialtransaction") or 
        request.user.is_superuser or 
        request.user.is_staff
    )
    can_override_down_payment = (
        request.user.has_perm("sale.change_salesorder") or 
        request.user.is_superuser
    )

    down_payments = so.down_payments.select_related("financial_account").order_by("-payment_date", "-id")

    from financial.services.account_helper import AccountHelperService
    cash_payment_accounts = AccountHelperService.get_cash_accounts()
    bank_payment_accounts = AccountHelperService.get_bank_accounts()
    treasury_accounts = AccountHelperService.get_cash_and_bank_accounts()

    context = {
        "page_title": f"{_('أمر بيع')} #{so.order_number}",
        "page_icon": "fas fa-clipboard-check",
        "page_subtitle": f"{_('تفاصيل ومتابعة أمر البيع رقم')} {so.order_number}",
        "so": so,
        "items": items,
        "delivery_notes": so.delivery_notes.all(),
        "linked_sales": linked_sales,
        "down_payments": down_payments,
        "cash_payment_accounts": cash_payment_accounts,
        "bank_payment_accounts": bank_payment_accounts,
        "treasury_accounts": treasury_accounts,
        "can_collect_down_payment": can_collect_down_payment,
        "can_override_down_payment": can_override_down_payment,
        "total_ordered_qty": total_ordered_qty,
        "total_delivered_qty": total_delivered_qty,
        "total_invoiced_qty": total_invoiced_qty,
        "total_remaining_qty": total_remaining_qty,
        "delivery_progress": delivery_progress,
        "invoicing_progress": invoicing_progress,
        "current_step": current_step,
        "breadcrumb_items": breadcrumb_items,
        "header_buttons": header_buttons,
    }
    return render(request, "sale/sales_order_detail.html", context)


@login_required
@require_POST
@check_sales_orders_enabled
def sales_order_collect_down_payment(request, pk):
    """
    تحصيل دفعة مقدمة / عربون لأمر البيع وتسجيل سند قبض مالي رسمي وقيد يومية بالخزينة
    """
    so = get_object_or_404(SalesOrder, pk=pk)

    can_collect = (
        request.user.has_perm("financial.add_financialtransaction") or 
        request.user.is_superuser or 
        request.user.is_staff
    )
    if not can_collect:
        messages.error(request, _("ليس لديك صلاحية تسجيل حركات الخزينة وسندات القبض."))
        return redirect("sale:sales_order_detail", pk=pk)

    if so.status in ["CANCELLED", "REJECTED", "CLOSED"]:
        messages.error(request, _("لا يمكن تحصيل دفعة مقدمة على أمر بيع ملغي أو مغلق."))
        return redirect("sale:sales_order_detail", pk=pk)

    amount_str = request.POST.get("amount", "0")
    try:
        amount = Decimal(str(amount_str).replace(',', '').strip())
    except Exception:
        amount = Decimal("0.00")

    if amount <= Decimal("0.00"):
        messages.error(request, _("مبلغ الدفعة المقدمة يجب أن يكون أكبر من صفر."))
        return redirect("sale:sales_order_detail", pk=pk)

    max_allowed = max(Decimal("0.00"), so.total_amount - so.paid_down_payment)
    if amount > max_allowed:
        messages.error(request, _("مبلغ الدفعة المقدمة ({} {}) يتجاوز المبلغ المتبقي من إجمالي أمر البيع ({} {}).").format(amount, so.currency_display, max_allowed, so.currency_display))
        return redirect("sale:sales_order_detail", pk=pk)

    financial_account_id = request.POST.get("financial_account")
    payment_method = request.POST.get("payment_method", "cash")
    payment_date = request.POST.get("payment_date") or timezone.now().date()
    notes = request.POST.get("notes", "").strip()

    try:
        with transaction.atomic():
            from customer.services.customer_allocation_audit_service import CustomerAllocationAuditService
            from financial.models import Currency
            curr_model = Currency.objects.filter(code=so.currency).first()

            payment = CustomerAllocationAuditService.create_prepaid_payment(
                customer_id=so.customer_id,
                amount=amount,
                payment_date=payment_date,
                payment_method=payment_method,
                financial_account_id=int(financial_account_id) if financial_account_id and str(financial_account_id).isdigit() else None,
                currency=curr_model,
                user=request.user,
                sales_order=so,
                cost_center=so.cost_center,
                salesman=so.salesman,
                notes=notes or f"سند قبض دفعة مقدمة عن أمر بيع #{so.order_number}"
            )

            messages.success(request, f"تم بنجاح تحصيل دفعة مقدمة بقيمة {amount} {so.currency} وإصدار سند قبض رقم #PAY-{payment.id}.")
    except Exception as e:
        logger.error(f"Error collecting down payment for SO #{so.order_number}: {e}", exc_info=True)
        messages.error(request, f"خطأ أثناء تسجيل سند القبض: {str(e)}")

    return redirect("sale:sales_order_detail", pk=pk)


@login_required
@require_POST
@check_sales_orders_enabled
def sales_order_override_down_payment(request, pk):
    """
    اعتماد تجاوز شرط الدفعة المقدمة إدارياً للصرف المخزني لحالات عملاء الـ VIP
    """
    so = get_object_or_404(SalesOrder, pk=pk)

    can_override = request.user.has_perm("sale.change_salesorder") or request.user.is_superuser
    if not can_override:
        messages.error(request, _("ليس لديك صلاحية اعتماد التجاوز الإداري لشروط المبيعات."))
        return redirect("sale:sales_order_detail", pk=pk)

    override_reason = request.POST.get("override_reason", "").strip() or "تجاوز إداري معتمد للصرف قبل اكتمال العربون"

    so.down_payment_override = True
    so.down_payment_override_by = request.user
    so.down_payment_override_reason = override_reason
    so.save(update_fields=["down_payment_override", "down_payment_override_by", "down_payment_override_reason"])

    messages.success(request, f"تم اعتماد التجاوز الإداري لشرط الدفعة المقدمة لأمر البيع #{so.order_number} بنجاح، ويمكن الآن إصدار إذن التسليم.")
    return redirect("sale:sales_order_detail", pk=pk)


@login_required
@require_POST
@check_sales_orders_enabled
def sales_order_confirm(request, pk):
    """
    اعتماد أمر البيع
    """
    so = get_object_or_404(SalesOrder, pk=pk)
    try:
        SalesService.approve_sales_order(so.id, request.user)
        messages.success(request, f"تم اعتماد أمر البيع #{so.order_number} بنجاح وحجز المخزون.")
    except Exception as e:
        messages.warning(request, str(e))
    return redirect("sale:sales_order_detail", pk=pk)


@login_required
@require_POST
@check_sales_orders_enabled
def sales_order_cancel(request, pk):
    """
    إلغاء أمر البيع وفك حجز المخزون
    """
    so = get_object_or_404(SalesOrder, pk=pk)
    try:
        SalesService.cancel_sales_order(so.id, request.user, reason="إلغاء يدوي من قبل المستخدم")
        messages.success(request, f"تم إلغاء أمر البيع #{so.order_number} وفك حجز المخزون بنجاح.")
    except Exception as e:
        messages.error(request, f"خطأ أثناء إلغاء أمر البيع: {str(e)}")
    return redirect("sale:sales_order_detail", pk=pk)


@login_required
@check_sales_orders_enabled
def sales_order_print(request, pk):
    """
    عرض قالب الطباعة الرسمي لأمر البيع (Contract / Sales Order Print View)
    """
    so = get_object_or_404(
        SalesOrder.objects.select_related("customer", "warehouse", "created_by", "salesman", "cost_center", "price_list", "quotation_reference")
        .prefetch_related("items__product__unit"),
        pk=pk
    )

    print_lang = request.GET.get("lang", "ar")
    is_english = print_lang == "en"
    print_dir = "ltr" if is_english else "rtl"

    company_name = SystemSetting.get_setting("company_name", "موهبة")
    company_address = SystemSetting.get_setting("company_address", "")
    company_phone = SystemSetting.get_setting("company_phone", "")
    company_tax_number = SystemSetting.get_setting("company_tax_number", "")
    company_logo = SystemSetting.get_setting("company_logo", "")
    company_stamp = SystemSetting.get_setting("company_stamp", "")
    company_email = SystemSetting.get_setting("company_email", "")
    company_website = SystemSetting.get_setting("company_website", "")

    status_map_ar = {
        "DRAFT": "مسودة",
        "PENDING_APPROVAL": "معلق الاعتماد",
        "APPROVED": "معتمد",
        "CONFIRMED": "مؤكد",
        "PARTIALLY_DELIVERED": "مسلم جزئياً",
        "FULLY_DELIVERED": "مسلم بالكامل",
        "PARTIALLY_INVOICED": "مفوتر جزئياً",
        "INVOICED": "مفوتر بالكامل",
        "CANCELLED": "ملغى",
    }
    status_map_en = {
        "DRAFT": "Draft",
        "PENDING_APPROVAL": "Pending Approval",
        "APPROVED": "Approved",
        "CONFIRMED": "Confirmed",
        "PARTIALLY_DELIVERED": "Partially Delivered",
        "FULLY_DELIVERED": "Fully Delivered",
        "PARTIALLY_INVOICED": "Partially Invoiced",
        "INVOICED": "Invoiced",
        "CANCELLED": "Cancelled",
    }

    status_map = status_map_en if is_english else status_map_ar
    translated_status = status_map.get(so.status, so.get_status_display())
    currency_symbol_active = so.currency_display

    amount_in_words = ""
    try:
        from utils.arabic_numbers import amount_to_arabic_words
        amount_in_words = amount_to_arabic_words(so.total_amount, currency=so.currency_code)
    except Exception:
        amount_in_words = ""

    has_item_discounts = any(item.discount_percentage > 0 for item in so.items.all())

    context = {
        "so": so,
        "items": so.items.all(),
        "company_name": company_name,
        "company_address": company_address,
        "company_phone": company_phone,
        "company_tax_number": company_tax_number,
        "company_logo": company_logo,
        "company_stamp": company_stamp,
        "company_email": company_email,
        "company_website": company_website,
        "title": f"{'Sales Order' if is_english else 'أمر بيع'} - {so.order_number}",
        "document_title": "Sales Order" if is_english else "أمر بيع وتوريد",
        "print_lang": print_lang,
        "print_dir": print_dir,
        "is_english": is_english,
        "currency_symbol_active": currency_symbol_active,
        "translated_status": translated_status,
        "has_item_discounts": has_item_discounts,
        "amount_in_words": amount_in_words,
    }
    return render(request, "sale/sales_order_print.html", context)


@login_required
@check_sales_orders_enabled
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
                "tax_rate": str(item.tax_rate or 0),
                "is_taxable": item.is_taxable,
            }
            for item in so.items.all()
        ]
    }
    request.session["prefill_sale_data"] = sale_data
    messages.info(request, f"تم نقل بيانات أمر البيع #{so.order_number} لإنشاء فاتورة مبيعات.")
    return redirect(f"{reverse('sale:sale_create')}?from_so={so.pk}")
