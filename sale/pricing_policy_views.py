"""
Pricing & Sales Policy Views
إدارة قوائم الأسعار وقواعد الخصم وسياسات التسعير المحوكمة
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
from django.db.models import Q, Count

from sale.models.pricing import PriceList, PriceListItem, DiscountRule, PricingAuditLog
from product.models.product_core import Product, Category
from client.models import Customer

logger = logging.getLogger(__name__)


# ==================== قوائم الأسعار (Price Lists) ====================

@login_required
def price_list_list(request):
    """
    قائمة قوائم أسعار المبيعات
    """
    price_lists = PriceList.objects.annotate(items_count=Count("items")).order_by("-is_active", "name")

    from core.utils import paginate_queryset
    pagination_context = paginate_queryset(price_lists, request)
    page_obj = pagination_context["page_obj"]

    breadcrumb_items = [
        {"title": _("الرئيسية"), "url": reverse("core:dashboard"), "icon": "fa-home"},
        {"title": _("إدارة المبيعات"), "url": reverse("sale:sale_list"), "icon": "fa-shopping-cart"},
        {"title": _("قوائم الأسعار"), "active": True},
    ]

    header_buttons = [
        {
            "url": reverse("sale:price_list_create"),
            "label": _("إنشاء قائمة أسعار"),
            "icon": "fa-plus",
            "class": "btn-primary",
        },
        {
            "url": reverse("sale:discount_rule_list"),
            "label": _("قواعد الخصم"),
            "icon": "fa-percentage",
            "class": "btn-outline-info",
        }
    ]

    context = {
        "page_title": _("قوائم أسعار المبيعات"),
        "price_lists": page_obj.object_list,
        "page_obj": page_obj,
        **pagination_context,
        "breadcrumb_items": breadcrumb_items,
        "header_buttons": header_buttons,
    }
    return render(request, "sale/pricing/price_list_list.html", context)


@login_required
def price_list_detail(request, pk):
    """
    تفاصيل قائمة الأسعار والبنود المسجلة بها
    """
    price_list = get_object_or_404(PriceList.objects.prefetch_related("items__product"), pk=pk)

    breadcrumb_items = [
        {"title": _("الرئيسية"), "url": reverse("core:dashboard"), "icon": "fa-home"},
        {"title": _("قوائم الأسعار"), "url": reverse("sale:price_list_list"), "icon": "fa-tags"},
        {"title": price_list.name, "active": True},
    ]

    header_buttons = [
        {
            "url": reverse("sale:price_list_edit", kwargs={"pk": price_list.pk}),
            "label": _("تعديل القائمة"),
            "icon": "fa-edit",
            "class": "btn-outline-secondary",
        }
    ]

    context = {
        "page_title": f"{_('قائمة أسعار')} - {price_list.name}",
        "price_list": price_list,
        "items": price_list.items.select_related("product").all(),
        "breadcrumb_items": breadcrumb_items,
        "header_buttons": header_buttons,
    }
    return render(request, "sale/pricing/price_list_detail.html", context)


@login_required
def price_list_create(request):
    """
    إنشاء قائمة أسعار جديدة مع بنود الأسعار
    """
    if request.method == "POST":
        name = request.POST.get("name")
        currency = request.POST.get("currency", "EGP")
        customer_type = request.POST.get("customer_type", "ALL")
        effective_from = request.POST.get("effective_from") or timezone.now().date()
        effective_to = request.POST.get("effective_to") or None

        product_ids = request.POST.getlist("product[]")
        prices = request.POST.getlist("price[]")
        min_qtys = request.POST.getlist("min_qty[]")

        try:
            pl = PriceList.objects.create(
                name=name,
                currency=currency,
                customer_type=customer_type,
                effective_from=effective_from,
                effective_to=effective_to,
                status="ACTIVE",
                is_active=True
            )

            for i in range(len(product_ids)):
                if product_ids[i] and str(product_ids[i]).isdigit():
                    p_id = int(product_ids[i])
                    pr = Decimal(str(prices[i])) if i < len(prices) and prices[i] else Decimal("0")
                    mq = Decimal(str(min_qtys[i])) if i < len(min_qtys) and min_qtys[i] else Decimal("1")
                    PriceListItem.objects.create(
                        price_list=pl,
                        product_id=p_id,
                        unit_price=pr,
                        min_quantity=mq
                    )

            messages.success(request, f"تم إنشاء قائمة الأسعار '{pl.name}' بنجاح.")
            return redirect("sale:price_list_detail", pk=pl.pk)

        except Exception as e:
            logger.error(f"Error creating price list: {e}")
            messages.error(request, f"خطأ أثناء إنشاء قائمة الأسعار: {str(e)}")

    products = Product.objects.filter(is_active=True).only("id", "name", "sku", "selling_price")

    breadcrumb_items = [
        {"title": _("الرئيسية"), "url": reverse("core:dashboard"), "icon": "fa-home"},
        {"title": _("قوائم الأسعار"), "url": reverse("sale:price_list_list"), "icon": "fa-tags"},
        {"title": _("إنشاء قائمة أسعار"), "active": True},
    ]

    context = {
        "page_title": _("إنشاء قائمة أسعار جديدة"),
        "products": products,
        "breadcrumb_items": breadcrumb_items,
    }
    return render(request, "sale/pricing/price_list_form.html", context)


@login_required
def price_list_edit(request, pk):
    """
    تعديل قائمة الأسعار الحالية
    """
    price_list = get_object_or_404(PriceList.objects.prefetch_related("items__product"), pk=pk)

    if request.method == "POST":
        price_list.name = request.POST.get("name", price_list.name)
        price_list.currency = request.POST.get("currency", price_list.currency)
        price_list.customer_type = request.POST.get("customer_type", price_list.customer_type)
        price_list.effective_from = request.POST.get("effective_from") or price_list.effective_from
        price_list.effective_to = request.POST.get("effective_to") or None
        price_list.is_active = request.POST.get("is_active") == "on"

        product_ids = request.POST.getlist("product[]")
        prices = request.POST.getlist("price[]")
        min_qtys = request.POST.getlist("min_qty[]")

        try:
            price_list.save()
            price_list.items.all().delete()

            for i in range(len(product_ids)):
                if product_ids[i] and str(product_ids[i]).isdigit():
                    p_id = int(product_ids[i])
                    pr = Decimal(str(prices[i])) if i < len(prices) and prices[i] else Decimal("0")
                    mq = Decimal(str(min_qtys[i])) if i < len(min_qtys) and min_qtys[i] else Decimal("1")
                    PriceListItem.objects.create(
                        price_list=price_list,
                        product_id=p_id,
                        unit_price=pr,
                        min_quantity=mq
                    )

            messages.success(request, f"تم تحديث قائمة الأسعار '{price_list.name}' بنجاح.")
            return redirect("sale:price_list_detail", pk=price_list.pk)

        except Exception as e:
            logger.error(f"Error editing price list: {e}")
            messages.error(request, f"خطأ أثناء تعديل قائمة الأسعار: {str(e)}")

    products = Product.objects.filter(is_active=True).only("id", "name", "sku", "selling_price")

    breadcrumb_items = [
        {"title": _("الرئيسية"), "url": reverse("core:dashboard"), "icon": "fa-home"},
        {"title": _("قوائم الأسعار"), "url": reverse("sale:price_list_list"), "icon": "fa-tags"},
        {"title": f"{_('تعديل')} {price_list.name}", "active": True},
    ]

    context = {
        "page_title": f"{_('تعديل قائمة أسعار')} - {price_list.name}",
        "price_list": price_list,
        "products": products,
        "items": price_list.items.all(),
        "breadcrumb_items": breadcrumb_items,
    }
    return render(request, "sale/pricing/price_list_form.html", context)


# ==================== قواعد الخصم (Discount Rules) ====================

@login_required
def discount_rule_list(request):
    """
    قائمة قواعد وسياسات الخصم
    """
    rules = DiscountRule.objects.select_related("customer", "category").order_by("-is_active", "priority")

    from core.utils import paginate_queryset
    pagination_context = paginate_queryset(rules, request)
    page_obj = pagination_context["page_obj"]

    breadcrumb_items = [
        {"title": _("الرئيسية"), "url": reverse("core:dashboard"), "icon": "fa-home"},
        {"title": _("إدارة المبيعات"), "url": reverse("sale:sale_list"), "icon": "fa-shopping-cart"},
        {"title": _("قواعد الخصم"), "active": True},
    ]

    header_buttons = [
        {
            "url": reverse("sale:discount_rule_create"),
            "label": _("إضافة قاعدة خصم"),
            "icon": "fa-plus",
            "class": "btn-primary",
        },
        {
            "url": reverse("sale:price_list_list"),
            "label": _("قوائم الأسعار"),
            "icon": "fa-tags",
            "class": "btn-outline-secondary",
        }
    ]

    context = {
        "page_title": _("قواعد وسياسات الخصم"),
        "rules": page_obj.object_list,
        "page_obj": page_obj,
        **pagination_context,
        "breadcrumb_items": breadcrumb_items,
        "header_buttons": header_buttons,
    }
    return render(request, "sale/pricing/discount_rule_list.html", context)


@login_required
def discount_rule_create(request):
    """
    إنشاء قاعدة خصم جديدة
    """
    if request.method == "POST":
        rule_name = request.POST.get("rule_name")
        rule_type = request.POST.get("rule_type", "PERCENTAGE")
        customer_id = request.POST.get("customer") or None
        category_id = request.POST.get("category") or None
        discount_percentage = Decimal(request.POST.get("discount_percentage", "0.00"))
        value = Decimal(request.POST.get("value", "0.00"))
        min_order_amount = Decimal(request.POST.get("min_order_amount", "0.00"))
        priority = int(request.POST.get("priority", "10"))
        effective_date = request.POST.get("effective_date") or timezone.now().date()
        expiry_date = request.POST.get("expiry_date") or None

        try:
            rule = DiscountRule.objects.create(
                rule_name=rule_name,
                rule_type=rule_type,
                customer_id=customer_id,
                category_id=category_id,
                discount_percentage=discount_percentage,
                value=value,
                min_order_amount=min_order_amount,
                priority=priority,
                effective_date=effective_date,
                expiry_date=expiry_date,
                is_active=True
            )
            messages.success(request, f"تم إنشاء قاعدة الخصم '{rule.rule_name}' بنجاح.")
            return redirect("sale:discount_rule_list")

        except Exception as e:
            logger.error(f"Error creating discount rule: {e}")
            messages.error(request, f"خطأ أثناء إنشاء قاعدة الخصم: {str(e)}")

    customers = Customer.objects.filter(is_active=True).only("id", "name")
    categories = Category.objects.all()

    breadcrumb_items = [
        {"title": _("الرئيسية"), "url": reverse("core:dashboard"), "icon": "fa-home"},
        {"title": _("قواعد الخصم"), "url": reverse("sale:discount_rule_list"), "icon": "fa-percentage"},
        {"title": _("إضافة قاعدة خصم"), "active": True},
    ]

    context = {
        "page_title": _("إضافة قاعدة خصم جديدة"),
        "customers": customers,
        "categories": categories,
        "breadcrumb_items": breadcrumb_items,
    }
    return render(request, "sale/pricing/discount_rule_form.html", context)
