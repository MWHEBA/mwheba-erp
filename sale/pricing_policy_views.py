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
from django.http import JsonResponse
from django.template.loader import render_to_string

from sale.models.pricing import PriceList, PriceListItem, DiscountRule, PricingAuditLog
from product.models.product_core import Product, Category
from client.models import Customer

logger = logging.getLogger(__name__)


def check_pricing_permissions(view_func):
    """
    التحقق من صلاحية المستخدم لإدارة قوائم الأسعار وقواعد الخصم (RBAC Guard)
    """
    def _wrapped(request, *args, **kwargs):
        u = request.user
        if not (u.is_superuser or u.is_staff or u.has_perm("sale.manage_pricing") or u.groups.filter(name__in=["Managers", "Admins", "CFO", "Sales Manager"]).exists()):
            messages.error(request, _("عفواً، لا تملك الصلاحيات الإدارية الكافية للوصول لسياسات الأسعار والخصومات."))
            return redirect("sale:sale_list")
        return view_func(request, *args, **kwargs)
    return _wrapped


# ==================== قوائم الأسعار (Price Lists) ====================

@login_required
def price_list_list(request):
    """
    قائمة قوائم أسعار المبيعات مع الفلاتر والإحصائيات والجدول الموحد ودعم AJAX
    """
    price_lists = PriceList.objects.annotate(items_count=Count("items")).order_by("-is_active", "name", "-id")

    # فلاتر البحث
    q = request.GET.get("q") or request.GET.get("search")
    if q:
        price_lists = price_lists.filter(
            Q(name__icontains=q) |
            Q(description__icontains=q) |
            Q(customer_type__icontains=q)
        )

    currency = request.GET.get("currency")
    if currency:
        price_lists = price_lists.filter(currency=currency)

    status = request.GET.get("status")
    if status in ["active", "1"]:
        price_lists = price_lists.filter(is_active=True)
    elif status in ["inactive", "0"]:
        price_lists = price_lists.filter(is_active=False)

    # إحصائيات KPI
    all_pl = PriceList.objects.all()
    stats = {
        "total_count": all_pl.count(),
        "active_count": all_pl.filter(is_active=True).count(),
        "total_items": PriceListItem.objects.count(),
        "default_count": all_pl.filter(is_default=True).count() if hasattr(PriceList, 'is_default') else 0,
    }

    from core.utils import paginate_queryset
    pagination_context = paginate_queryset(price_lists, request)
    page_obj = pagination_context["page_obj"]

    breadcrumb_items = [
        {"title": _("الرئيسية"), "url": reverse("core:dashboard"), "icon": "fa-home"},
        {"title": _("المبيعات"), "url": reverse("sale:sale_list"), "icon": "fa-shopping-cart"},
        {"title": _("قوائم الأسعار"), "active": True},
    ]

    header_buttons = [
        {
            "url": reverse("sale:price_list_create"),
            "text": _("إنشاء قائمة أسعار"),
            "icon": "fa-plus",
            "class": "btn-primary",
        },
        {
            "url": reverse("sale:discount_rule_list"),
            "text": _("قواعد الخصم"),
            "icon": "fa-percentage",
            "class": "btn-outline-secondary",
        }
    ]

    # إعداد headers للجدول الموحد
    price_list_headers = [
        {
            'key': 'id',
            'label': '#',
            'class': 'text-center',
            'width': '4%'
        },
        {
            'key': 'name',
            'label': _('اسم القائمة'),
            'class': 'text-start fw-bold',
            'format': 'html',
            'width': '25%'
        },
        {
            'key': 'currency',
            'label': _('العملة'),
            'class': 'text-center',
            'format': 'html',
            'width': '10%'
        },
        {
            'key': 'customer_type',
            'label': _('فئة العملاء'),
            'class': 'text-center',
            'format': 'html',
            'width': '15%'
        },
        {
            'key': 'effective_from',
            'label': _('تاريخ السريان'),
            'class': 'text-center',
            'format': 'html',
            'width': '14%'
        },
        {
            'key': 'items_count',
            'label': _('عدد البنود'),
            'class': 'text-center',
            'format': 'html',
            'width': '10%'
        },
        {
            'key': 'status',
            'label': _('الحالة'),
            'class': 'text-center',
            'format': 'html',
            'width': '10%'
        },
        {
            'key': 'actions',
            'label': _('الإجراءات'),
            'class': 'text-center col-actions',
            'format': 'html',
            'width': '1%'
        }
    ]

    # بناء بيانات الجدول الموحد
    price_lists_data = []
    for pl in page_obj:
        name_html = f'<div class="fw-bold text-primary mb-0"><i class="fas fa-tags me-1 text-muted"></i>{pl.name}</div>'
        currency_html = f'<span class="badge bg-light text-dark border fw-bold">{pl.currency}</span>'
        cust_type_html = f'<span class="badge bg-light text-secondary border">{pl.customer_type or "الكل"}</span>'
        eff_date_html = pl.effective_from.strftime("%Y-%m-%d") if pl.effective_from else "-"

        items_html = f'<span class="badge bg-info text-white">{pl.items_count} بنود</span>'

        if pl.is_active:
            status_html = '<span class="badge bg-success">نشطة</span>'
        else:
            status_html = '<span class="badge bg-secondary">معطلة</span>'

        detail_url = reverse("sale:price_list_detail", args=[pl.pk])
        edit_url = reverse("sale:price_list_edit", args=[pl.pk])

        actions_html = f'''
        <div class="btn-group btn-group-sm" onclick="event.stopPropagation();">
            <a href="{detail_url}" class="btn btn-outline-secondary" title="عرض التفاصيل">
                <i class="fas fa-eye"></i>
            </a>
            <a href="{edit_url}" class="btn btn-outline-primary" title="تعديل">
                <i class="fas fa-edit"></i>
            </a>
        </div>
        '''

        price_lists_data.append({
            'id': pl.id,
            'name': name_html,
            'currency': currency_html,
            'customer_type': cust_type_html,
            'effective_from': eff_date_html,
            'items_count': items_html,
            'status': status_html,
            'actions': actions_html,
            'row_click_url': detail_url,
        })

    context = {
        "page_title": _("قوائم أسعار المبيعات"),
        "page_subtitle": _("إدارة وتخصيص لوائح الأسعار المعتمدة لمختلف فئات العملاء والعملات"),
        "page_icon": "fas fa-tags",
        "price_lists": page_obj.object_list,
        "price_lists_data": price_lists_data,
        "price_list_headers": price_list_headers,
        "page_obj": page_obj,
        "stats": stats,
        **pagination_context,
        "breadcrumb_items": breadcrumb_items,
        "header_buttons": header_buttons,
    }

    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.GET.get("ajax"):
        table_html = render_to_string("sale/pricing/partials/price_list_table.html", context, request=request)
        pagination_html = render_to_string("partials/pagination.html", context, request=request)
        return JsonResponse({
            "table_html": table_html,
            "pagination_html": pagination_html,
        })

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
@check_pricing_permissions
def discount_rule_list(request):
    """
    قائمة قواعد وسياسات الخصم مع الفلاتر والإحصائيات ودعم AJAX الموحد
    """
    rules = DiscountRule.objects.select_related("customer", "category", "product").order_by("-is_active", "priority", "-id")

    # فلاتر البحث
    q = request.GET.get("q") or request.GET.get("search")
    if q:
        rules = rules.filter(
            Q(rule_name__icontains=q) |
            Q(customer__name__icontains=q) |
            Q(category__name__icontains=q) |
            Q(product__name__icontains=q)
        )

    rule_type = request.GET.get("rule_type")
    if rule_type:
        rules = rules.filter(rule_type=rule_type)

    customer_id = request.GET.get("customer")
    if customer_id and customer_id.isdigit():
        rules = rules.filter(customer_id=int(customer_id))

    category_id = request.GET.get("category")
    if category_id and category_id.isdigit():
        rules = rules.filter(category_id=int(category_id))

    status = request.GET.get("status")
    if status in ["active", "1"]:
        rules = rules.filter(is_active=True)
    elif status in ["inactive", "0"]:
        rules = rules.filter(is_active=False)

    # حساب إحصائيات KPI العامة
    all_rules = DiscountRule.objects.all()
    stats = {
        "total_count": all_rules.count(),
        "active_count": all_rules.filter(is_active=True).count(),
        "percentage_count": all_rules.filter(rule_type="PERCENTAGE").count(),
        "fixed_count": all_rules.filter(rule_type__in=["FIXED_AMOUNT", "TIERED_QUANTITY"]).count(),
    }

    from core.utils import paginate_queryset
    pagination_context = paginate_queryset(rules, request)
    page_obj = pagination_context["page_obj"]

    breadcrumb_items = [
        {"title": _("الرئيسية"), "url": reverse("core:dashboard"), "icon": "fa-home"},
        {"title": _("المبيعات"), "url": reverse("sale:sale_list"), "icon": "fa-shopping-cart"},
        {"title": _("قواعد الخصم"), "active": True},
    ]

    header_buttons = [
        {
            "url": reverse("sale:discount_rule_create"),
            "text": _("إضافة قاعدة خصم"),
            "icon": "fa-plus",
            "class": "btn-primary",
        },
        {
            "url": reverse("sale:price_list_list"),
            "text": _("قوائم الأسعار"),
            "icon": "fa-tags",
            "class": "btn-outline-secondary",
        }
    ]

    customers = Customer.objects.filter(is_active=True).only("id", "name").order_by("name")
    categories = Category.objects.all().order_by("name")
    products = Product.objects.filter(is_active=True).only("id", "name", "sku").order_by("name")

    # إعداد headers للجدول الموحد
    discount_rule_headers = [
        {
            'key': 'id',
            'label': '#',
            'class': 'text-center',
            'width': '4%'
        },
        {
            'key': 'rule_name',
            'label': _('اسم القاعدة والنطاق'),
            'class': 'text-start',
            'format': 'html',
            'width': '22%'
        },
        {
            'key': 'rule_type',
            'label': _('نوع القاعدة'),
            'class': 'text-center',
            'format': 'html',
            'width': '10%'
        },
        {
            'key': 'target',
            'label': _('الهدف المستهدف'),
            'class': 'text-start',
            'format': 'html',
            'width': '20%'
        },
        {
            'key': 'discount_value',
            'label': _('قيمة الخصم'),
            'class': 'text-center',
            'format': 'html',
            'width': '10%'
        },
        {
            'key': 'min_order_amount',
            'label': _('الحد الأدنى'),
            'class': 'text-center',
            'format': 'html',
            'width': '10%'
        },
        {
            'key': 'validity_period',
            'label': _('فترة السريان'),
            'class': 'text-center',
            'format': 'html',
            'width': '12%'
        },
        {
            'key': 'priority',
            'label': _('الأولوية'),
            'class': 'text-center',
            'format': 'html',
            'width': '6%'
        },
        {
            'key': 'status',
            'label': _('الحالة'),
            'class': 'text-center',
            'format': 'html',
            'width': '8%'
        },
        {
            'key': 'actions',
            'label': _('الإجراءات'),
            'class': 'text-center col-actions',
            'format': 'html',
            'width': '1%'
        }
    ]

    # بناء بيانات الجدول الموحد
    rules_data = []
    for r in page_obj:
        scope_badge = '<span class="badge bg-light text-secondary border ms-1">بند</span>' if r.scope == "ITEM" else '<span class="badge bg-info-subtle text-info border ms-1">فاتورة</span>'
        rule_name_html = f'<div class="fw-bold text-primary mb-0"><i class="fas fa-percentage me-1 text-muted"></i>{r.rule_name} {scope_badge}</div>'

        if r.rule_type == "PERCENTAGE":
            rule_type_html = '<span class="badge bg-light text-primary border"><i class="fas fa-percent me-1"></i>نسبة مئوية</span>'
            discount_value_html = f'<span class="fw-bold text-success fs-6">{r.discount_percentage}%</span>'
        elif r.rule_type == "FIXED_AMOUNT":
            rule_type_html = '<span class="badge bg-light text-success border"><i class="fas fa-money-bill-wave me-1"></i>مبلغ ثابت</span>'
            discount_value_html = f'<span class="fw-bold text-success fs-6">{r.value:.2f} ج.م</span>'
        else:
            rule_type_html = '<span class="badge bg-light text-warning border"><i class="fas fa-layer-group me-1"></i>شريحة كمية</span>'
            discount_value_html = f'<span class="fw-bold text-success fs-6">{r.discount_percentage}%</span>'

        target_parts = []
        if r.product:
            target_parts.append(f'<div class="text-primary fw-semibold"><i class="fas fa-box text-muted me-1"></i>{r.product.name}</div>')
        if r.category:
            target_parts.append(f'<div class="text-dark small"><i class="fas fa-tags text-muted me-1"></i>{r.category.name}</div>')
        if r.customer:
            target_parts.append(f'<div class="text-muted small"><i class="fas fa-user text-muted me-1"></i>{r.customer.name}</div>')
        if not target_parts:
            target_html = '<span class="badge bg-light text-secondary border">كافة العملاء والأصناف</span>'
        else:
            target_html = "".join(target_parts)

        if r.min_order_amount > 0:
            min_amount_html = f'<span class="fw-semibold text-dark">{r.min_order_amount:.2f}</span>'
        else:
            min_amount_html = '<span class="text-muted">-</span>'

        from_d = r.effective_date.strftime("%Y-%m-%d") if r.effective_date else "-"
        to_d = r.expiry_date.strftime("%Y-%m-%d") if r.expiry_date else "مستمر"
        validity_html = f'<div class="small"><span class="text-muted">من:</span> {from_d}</div><div class="small text-muted"><span>إلى:</span> {to_d}</div>'

        priority_html = f'<span class="badge rounded-pill bg-light text-dark border fw-bold">{r.priority}</span>'

        if r.is_active:
            status_html = '<span class="badge bg-success">نشطة</span>'
            toggle_title = "تعطيل"
            toggle_icon = "fa-ban text-warning"
        else:
            status_html = '<span class="badge bg-secondary">معطلة</span>'
            toggle_title = "تفعيل"
            toggle_icon = "fa-check text-success"

        edit_url = reverse("sale:discount_rule_edit", args=[r.pk])
        toggle_url = reverse("sale:discount_rule_toggle", args=[r.pk])
        delete_url = reverse("sale:discount_rule_delete", args=[r.pk])

        actions_html = f'''
        <div class="btn-group btn-group-sm" onclick="event.stopPropagation();">
            <a href="{edit_url}" class="btn btn-outline-primary" title="تعديل">
                <i class="fas fa-edit"></i>
            </a>
            <button type="button" class="btn btn-outline-secondary toggle-rule-btn" data-url="{toggle_url}" title="{toggle_title}">
                <i class="fas {toggle_icon}"></i>
            </button>
            <button type="button" class="btn btn-outline-danger delete-rule-btn" data-url="{delete_url}" data-name="{r.rule_name}" title="حذف">
                <i class="fas fa-trash-alt"></i>
            </button>
        </div>
        '''

        rules_data.append({
            'id': r.id,
            'rule_name': rule_name_html,
            'rule_type': rule_type_html,
            'target': target_html,
            'discount_value': discount_value_html,
            'min_order_amount': min_amount_html,
            'validity_period': validity_html,
            'priority': priority_html,
            'status': status_html,
            'actions': actions_html,
            'row_click_url': edit_url,
        })

    context = {
        "page_title": _("قواعد وسياسات الخصم"),
        "page_subtitle": _("إدارة سياسات وقواعد الخصم التلقائية الممنوحة للعملاء وفئات ومنتجات المبيعات"),
        "page_icon": "fas fa-percentage",
        "rules": page_obj.object_list,
        "rules_data": rules_data,
        "discount_rule_headers": discount_rule_headers,
        "page_obj": page_obj,
        "stats": stats,
        "customers": customers,
        "categories": categories,
        "products": products,
        "rule_types": DiscountRule.RULE_TYPES,
        **pagination_context,
        "breadcrumb_items": breadcrumb_items,
        "header_buttons": header_buttons,
    }

    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.GET.get("ajax"):
        table_html = render_to_string("sale/pricing/partials/discount_rule_table.html", context, request=request)
        pagination_html = render_to_string("partials/pagination.html", context, request=request)
        return JsonResponse({
            "table_html": table_html,
            "pagination_html": pagination_html,
        })

    return render(request, "sale/pricing/discount_rule_list.html", context)


@login_required
@check_pricing_permissions
def discount_rule_create(request):
    """
    إنشاء قاعدة خصم جديدة
    """
    if request.method == "POST":
        rule_name = request.POST.get("rule_name")
        rule_type = request.POST.get("rule_type", "PERCENTAGE")
        scope = request.POST.get("scope", "ITEM")
        aggregation_type = request.POST.get("aggregation_type", "LINE_ONLY")
        customer_id = request.POST.get("customer") or None
        category_id = request.POST.get("category") or None
        product_id = request.POST.get("product") or None
        discount_percentage = Decimal(request.POST.get("discount_percentage", "0.00") or "0.00")
        value = Decimal(request.POST.get("value", "0.00") or "0.00")
        min_order_amount = Decimal(request.POST.get("min_order_amount", "0.00") or "0.00")
        priority = int(request.POST.get("priority", "10") or "10")
        effective_date = request.POST.get("effective_date") or timezone.now().date()
        expiry_date = request.POST.get("expiry_date") or None
        is_active = request.POST.get("is_active") in ["on", "true", "1", True]

        try:
            rule = DiscountRule.objects.create(
                rule_name=rule_name,
                rule_type=rule_type,
                scope=scope,
                aggregation_type=aggregation_type,
                customer_id=customer_id,
                category_id=category_id,
                product_id=product_id,
                discount_percentage=discount_percentage,
                value=value,
                min_order_amount=min_order_amount,
                priority=priority,
                effective_date=effective_date,
                expiry_date=expiry_date,
                is_active=is_active
            )
            messages.success(request, f"تم إنشاء قاعدة الخصم '{rule.rule_name}' بنجاح ✅")
            return redirect("sale:discount_rule_list")

        except Exception as e:
            logger.error(f"Error creating discount rule: {e}", exc_info=True)
            messages.error(request, f"خطأ أثناء إنشاء قاعدة الخصم: {str(e)}")

    customers = Customer.objects.filter(is_active=True).only("id", "name").order_by("name")
    categories = Category.objects.all().order_by("name")
    products = Product.objects.filter(is_active=True).only("id", "name", "sku").order_by("name")

    breadcrumb_items = [
        {"title": _("الرئيسية"), "url": reverse("core:dashboard"), "icon": "fa-home"},
        {"title": _("قواعد الخصم"), "url": reverse("sale:discount_rule_list"), "icon": "fa-percentage"},
        {"title": _("إضافة قاعدة خصم"), "active": True},
    ]

    header_buttons = [
        {
            "url": reverse("sale:discount_rule_list"),
            "label": _("العودة للقائمة"),
            "icon": "fa-arrow-right",
            "class": "btn-secondary",
        }
    ]

    context = {
        "page_title": _("إضافة قاعدة خصم جديدة"),
        "page_subtitle": _("تعريف قاعدة خصم تجارية جديدة وتحديد شروط الاستحقاق"),
        "page_icon": "fas fa-percentage",
        "customers": customers,
        "categories": categories,
        "products": products,
        "rule_types": DiscountRule.RULE_TYPES,
        "scope_choices": DiscountRule.SCOPE_CHOICES,
        "aggregation_choices": DiscountRule.AGGREGATION_CHOICES,
        "breadcrumb_items": breadcrumb_items,
        "header_buttons": header_buttons,
    }
    return render(request, "sale/pricing/discount_rule_form.html", context)


@login_required
@check_pricing_permissions
def discount_rule_edit(request, pk):
    """
    تعديل قاعدة خصم قائمة
    """
    rule = get_object_or_404(DiscountRule, pk=pk)

    if request.method == "POST":
        rule.rule_name = request.POST.get("rule_name", rule.rule_name)
        rule.rule_type = request.POST.get("rule_type", rule.rule_type)
        rule.scope = request.POST.get("scope", getattr(rule, "scope", "ITEM"))
        rule.aggregation_type = request.POST.get("aggregation_type", getattr(rule, "aggregation_type", "LINE_ONLY"))
        rule.customer_id = request.POST.get("customer") or None
        rule.category_id = request.POST.get("category") or None
        rule.product_id = request.POST.get("product") or None
        rule.discount_percentage = Decimal(request.POST.get("discount_percentage", "0.00") or "0.00")
        rule.value = Decimal(request.POST.get("value", "0.00") or "0.00")
        rule.min_order_amount = Decimal(request.POST.get("min_order_amount", "0.00") or "0.00")
        rule.priority = int(request.POST.get("priority", "10") or "10")
        rule.effective_date = request.POST.get("effective_date") or rule.effective_date
        rule.expiry_date = request.POST.get("expiry_date") or None
        rule.is_active = request.POST.get("is_active") in ["on", "true", "1", True]

        try:
            rule.save()
            messages.success(request, f"تم تحديث قاعدة الخصم '{rule.rule_name}' بنجاح ✅")
            return redirect("sale:discount_rule_list")
        except Exception as e:
            logger.error(f"Error updating discount rule: {e}", exc_info=True)
            messages.error(request, f"خطأ أثناء تعديل قاعدة الخصم: {str(e)}")

    customers = Customer.objects.filter(is_active=True).only("id", "name").order_by("name")
    categories = Category.objects.all().order_by("name")
    products = Product.objects.filter(is_active=True).only("id", "name", "sku").order_by("name")

    breadcrumb_items = [
        {"title": _("الرئيسية"), "url": reverse("core:dashboard"), "icon": "fa-home"},
        {"title": _("قواعد الخصم"), "url": reverse("sale:discount_rule_list"), "icon": "fa-percentage"},
        {"title": f"تعديل: {rule.rule_name}", "active": True},
    ]

    header_buttons = [
        {
            "url": reverse("sale:discount_rule_list"),
            "label": _("العودة للقائمة"),
            "icon": "fa-arrow-right",
            "class": "btn-secondary",
        }
    ]

    context = {
        "page_title": _("تعديل قاعدة الخصم"),
        "page_subtitle": _(f"تعديل محددات وشروط قاعدة الخصم #{rule.id}"),
        "page_icon": "fas fa-edit",
        "rule": rule,
        "customers": customers,
        "categories": categories,
        "products": products,
        "rule_types": DiscountRule.RULE_TYPES,
        "scope_choices": DiscountRule.SCOPE_CHOICES,
        "aggregation_choices": DiscountRule.AGGREGATION_CHOICES,
        "breadcrumb_items": breadcrumb_items,
        "header_buttons": header_buttons,
    }
    return render(request, "sale/pricing/discount_rule_form.html", context)


@login_required
@require_POST
def discount_rule_toggle_status(request, pk):
    """
    تغيير حالة قاعدة الخصم (تفعيل / تعطيل)
    """
    rule = get_object_or_404(DiscountRule, pk=pk)
    rule.is_active = not rule.is_active
    rule.save(update_fields=["is_active"])

    status_str = "تفعيل" if rule.is_active else "تعطيل"
    messages.success(request, f"تم {status_str} قاعدة الخصم '{rule.rule_name}' بنجاح ✅")

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({
            "success": True,
            "is_active": rule.is_active,
            "message": f"تم {status_str} قاعدة الخصم بنجاح"
        })
    return redirect("sale:discount_rule_list")


@login_required
@require_POST
def discount_rule_delete(request, pk):
    """
    حذف قاعدة الخصم
    """
    rule = get_object_or_404(DiscountRule, pk=pk)
    rule_name = rule.rule_name
    rule.delete()
    messages.success(request, f"تم حذف قاعدة الخصم '{rule_name}' بنجاح 🗑️")

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({
            "success": True,
            "message": f"تم حذف قاعدة الخصم '{rule_name}' بنجاح"
        })
    return redirect("sale:discount_rule_list")
