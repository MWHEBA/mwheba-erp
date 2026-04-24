# -*- coding: utf-8 -*-
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse, Http404
from django.db.models import Q, Sum, Count, F
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.template.loader import render_to_string
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.db import transaction, models
from django.core.exceptions import ValidationError
from ..models import (
    Product,
    Category,
    Warehouse,
    Stock,
    StockMovement,
    InventoryMovement,
    Unit,
    ProductImage,
    ProductVariant,
    SupplierProductPrice,
    PriceHistory,
    BundleComponent,
)
from ..forms import (
    ProductForm,
    CategoryForm,
    WarehouseForm,
    StockMovementForm,
    UnitForm,
    ProductImageForm,
    ProductVariantForm,
    ProductSearchForm,
    BundleForm,
    BundleComponentForm,
    BundleComponentFormSet,
)
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.utils import timezone
import csv
from io import BytesIO
from django.views.decorators.http import require_POST
from django.core.exceptions import ValidationError
import logging
from decimal import Decimal
from datetime import datetime, timedelta
from django.db.models import Avg, Max, Min
from core.models import SystemSetting

# استيراد نماذج المشتريات للتحقق من الارتباطات
try:
    from purchase.models import PurchaseItem
except ImportError:
    PurchaseItem = None


def get_product_sales_statistics(product):
    """
    حساب إحصائيات المبيعات للمنتج (من sale.models)
    """
    try:
        from sale.models import SaleItem
        from decimal import Decimal
        from financial.models import AccountingPeriod
        from django.db.models import Count
        from django.db.models.functions import TruncMonth

        current_period = (
            AccountingPeriod.objects.filter(status="open")
            .order_by("-start_date")
            .first()
        )

        sale_items = SaleItem.objects.filter(product=product).select_related("sale", "sale__customer")

        if current_period:
            sale_items = sale_items.filter(
                sale__date__gte=current_period.start_date,
                sale__date__lte=current_period.end_date,
            )

        total_sold_quantity = sale_items.aggregate(Sum("quantity"))["quantity__sum"] or 0
        total_sales_value = sale_items.aggregate(
            total=Sum(F('quantity') * F('unit_price'))
        )["total"] or Decimal('0')
        total_sales_count = sale_items.count()
        average_sale_price = (
            sale_items.aggregate(Avg("unit_price"))["unit_price__avg"] or Decimal('0')
        )

        last_sales = sale_items.order_by("-sale__date")[:5]

        top_customers = (
            sale_items.values("sale__customer__id")
            .annotate(total_quantity=Sum("quantity"))
            .order_by("-total_quantity")[:5]
        )

        monthly_sales = (
            sale_items.annotate(month=TruncMonth("sale__date"))
            .values("month")
            .annotate(
                total_quantity=Sum("quantity"),
                total_value=Sum(F('quantity') * F('unit_price'))
            )
            .order_by("month")
        )

        best_selling_month = None
        if monthly_sales:
            best_selling_month = max(monthly_sales, key=lambda x: x["total_quantity"])

        last_sale_date = None
        if sale_items.exists():
            last_item = sale_items.order_by("-sale__date").first()
            if last_item:
                last_sale_date = last_item.sale.date

        return {
            "total_sold_quantity": total_sold_quantity,
            "total_sales_value": float(total_sales_value),
            "total_sales_count": total_sales_count,
            "average_sale_price": float(average_sale_price),
            "last_sales": last_sales,
            "top_customers": top_customers,
            "monthly_sales": monthly_sales,
            "best_selling_month": best_selling_month,
            "last_sale_date": last_sale_date,
            "period_name": current_period.name if current_period else None,
        }

    except ImportError:
        return {
            "total_sold_quantity": 0,
            "total_sales_value": 0,
            "total_sales_count": 0,
            "average_sale_price": 0,
            "last_sales": [],
            "top_customers": [],
            "monthly_sales": [],
            "best_selling_month": None,
            "last_sale_date": None,
            "period_name": None,
        }


def get_product_purchase_statistics(product):
    """
    حساب إحصائيات المشتريات للمنتج
    """
    # TODO: Implement purchase statistics
    return {}


logger = logging.getLogger(__name__)


@login_required
def _calculate_bundle_stock_from_prefetch(bundle_product):
    """
    حساب مخزون المنتج المجمع من الـ prefetched data بدون queries إضافية
    """
    components = bundle_product.components.all()
    if not components:
        return 0
    min_bundles = float('inf')
    for component in components:
        if not component.component_product.is_active:
            return 0
        comp_stock = sum(s.quantity for s in component.component_product.stocks.all())
        if comp_stock <= 0:
            return 0
        min_bundles = min(min_bundles, comp_stock // component.required_quantity)
    return int(min_bundles) if min_bundles != float('inf') else 0


def product_list(request):
    """
    عرض قائمة المنتجات (بدون الخدمات) - مع Ajax search و DB-level pagination
    """
    try:
        # استرجاع المنتجات مع كل البيانات المطلوبة في query واحدة
        products = (
            Product.objects.select_related("category", "unit", "created_by", "updated_by")
            .prefetch_related(
                "stocks",
                "images",
                "components__component_product__stocks",  # للـ bundles
            )
            .filter(is_service=False)
            .annotate(
                total_stock=Sum("stocks__quantity"),
                components_count=Count("components", distinct=True),
            )
            .order_by("name")
        )

        # قراءة معاملات البحث والفلترة
        search_query = request.GET.get("search", "").strip()
        category_id  = request.GET.get("category", "")
        product_type = request.GET.get("product_type", "")
        min_price    = request.GET.get("min_price", "")
        max_price    = request.GET.get("max_price", "")
        in_stock     = request.GET.get("in_stock", "")

        # is_active: افتراضي "active" لو مفيش أي params
        status = request.GET.get("status", "active" if not request.GET else "")

        # تطبيق الفلاتر
        if search_query:
            products = products.filter(
                Q(name__icontains=search_query) |
                Q(sku__icontains=search_query) |
                Q(description__icontains=search_query)
            )
        if status == "active":
            products = products.filter(is_active=True)
        elif status == "inactive":
            products = products.filter(is_active=False)
        if category_id:
            products = products.filter(category_id=category_id)
        if product_type == "regular":
            products = products.filter(is_bundle=False)
        elif product_type == "bundle":
            products = products.filter(is_bundle=True)
        if min_price:
            try:
                products = products.filter(selling_price__gte=Decimal(min_price))
            except Exception:
                pass
        if max_price:
            try:
                products = products.filter(selling_price__lte=Decimal(max_price))
            except Exception:
                pass
        if in_stock:
            products = products.filter(stocks__quantity__gt=0).distinct()

        # معالجة تصدير PDF
        if request.GET.get('export') == 'pdf':
            return export_products_pdf_weasy(request, products)

        # تعريف أعمدة جدول المنتجات
        product_headers = [
            {"key": "bulk_checkbox", "label": "☑", "sortable": False, "class": "text-center bulk-checkbox-col", "format": "html", "width": "40px"},
            {"key": "image", "label": "الصورة", "sortable": False, "class": "text-center", "format": "html", "width": "80px"},
            {"key": "name_with_sku", "label": "اسم المنتج", "sortable": True, "class": "text-start", "format": "html"},
            {"key": "product_type", "label": "النوع", "sortable": True, "class": "text-center", "format": "html", "width": "100px"},
            {"key": "category", "label": "التصنيف", "sortable": True, "class": "text-center", "format": "html", "width": "120px"},
            {"key": "sale_price", "label": "سعر البيع", "sortable": True, "class": "text-center", "format": "html", "width": "120px"},
            {"key": "current_stock", "label": "المخزون", "sortable": True, "class": "text-center", "format": "html", "width": "120px"},
            {"key": "is_active", "label": "الحالة", "sortable": True, "class": "text-center", "format": "html", "width": "90px"},
        ]

        action_buttons = [
            {"url": "product:product_detail", "icon": "fa-eye", "label": "عرض التفاصيل", "class": "action-view", "title": "عرض تفاصيل المنتج"},
            {"url": "product:product_edit", "icon": "fa-edit", "label": "تعديل", "class": "action-edit", "title": "تعديل المنتج"},
        ]

        # DB-level pagination
        paginator = Paginator(products, 25)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        def build_table_data(page):
            rows = []
            for product in page:
                if product.is_bundle:
                    components_count = product.components_count
                    product_type_html = f'<span class="badge bg-info" title="منتج مجمع يحتوي على {components_count} مكون"><i class="fas fa-boxes me-1"></i>مجمع</span>'
                    detail_url = reverse("product:bundle_detail", args=[product.pk])
                else:
                    product_type_html = '<span class="badge bg-secondary"><i class="fas fa-box me-1"></i>عادي</span>'
                    detail_url = reverse("product:product_detail", args=[product.pk])

                primary_image = None
                for img in product.images.all():
                    if img.is_primary:
                        primary_image = img
                        break
                if primary_image is None:
                    for img in product.images.all():
                        primary_image = img
                        break

                image_html = (
                    f'<img src="{primary_image.image.url}" alt="{product.name}" style="width:50px;height:50px;object-fit:cover;border-radius:8px;border:1px solid #dee2e6;">'
                    if primary_image else
                    '<div style="width:50px;height:50px;background:#f8f9fa;border-radius:8px;border:1px solid #dee2e6;display:flex;align-items:center;justify-content:center;margin:auto;"><i class="fas fa-image text-muted"></i></div>'
                )
                sku_html = f'<div style="font-size:0.75rem;color:var(--text-muted);"><i class="fas fa-barcode me-1" style="font-size:0.7rem;"></i>{product.sku}</div>' if product.sku else ''
                name_html = f'<div style="font-weight:500;">{product.name}</div>{sku_html}'
                category_html = f'<span class="badge bg-light text-dark">{product.category.name}</span>' if product.category else '-'
                price_html = f'<span style="font-weight:600;">{product.selling_price:,.2f}</span> <small class="text-muted">ج.م</small>'

                stock_val = product.total_stock or 0
                if product.is_bundle:
                    stock_val = _calculate_bundle_stock_from_prefetch(product)

                if stock_val <= 0:
                    stock_html = '<span class="badge bg-secondary-subtle text-secondary border border-secondary opacity-50 fw-bold"><i class="fas fa-boxes me-1"></i>0</span>'
                elif stock_val <= (product.min_stock or 0):
                    stock_html = f'<span class="badge bg-warning text-dark">{stock_val}</span>'
                else:
                    stock_html = f'<span class="badge bg-success">{stock_val}</span>'

                status_html = '<span class="badge bg-success">نشط</span>' if product.is_active else '<span class="badge bg-danger">غير نشط</span>'

                rows.append({
                    "id": product.id,
                    "bulk_checkbox": f'<input type="checkbox" class="row-checkbox" value="{product.id}">',
                    "image": image_html,
                    "name_with_sku": name_html,
                    "product_type": f'<span>{product_type_html}</span>',
                    "category": category_html,
                    "sale_price": price_html,
                    "current_stock": stock_html,
                    "is_active": status_html,
                    "row_click_url": detail_url,
                })
            return rows

        table_data = build_table_data(page_obj)

        # Ajax response
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            table_html = render_to_string('product/partials/product_table.html', {
                'table_data': table_data,
                'product_headers': product_headers,
                'action_buttons': action_buttons,
            }, request=request)
            pagination_html = render_to_string('partials/pagination.html', {
                'page_obj': page_obj,
                'align': 'center',
            }, request=request) if paginator.num_pages > 1 else ''
            return JsonResponse({
                'table_html': table_html,
                'pagination_html': pagination_html,
                'count': paginator.count,
            })

        context = {
            "products": page_obj,
            "page_obj": page_obj,
            "paginator": paginator,
            "table_data": table_data,
            "product_headers": product_headers,
            "action_buttons": action_buttons,
            "primary_key": "id",
            "categories": Category.objects.filter(is_active=True).order_by('name'),
            "current_search": search_query,
            "current_status": status,
            "current_category": category_id,
            "current_product_type": product_type,
            "current_min_price": min_price,
            "current_max_price": max_price,
            "current_in_stock": in_stock,
            "page_title": "قائمة المنتجات",
            "page_subtitle": "إدارة منتجات النظام وتصنيفاتها وأسعارها",
            "page_icon": "fas fa-boxes",
            "header_buttons": [
                {"url": reverse("product:product_create"), "icon": "fa-plus", "text": "إضافة منتج عادي", "class": "btn-success"},
                {"url": reverse("product:bundle_create"), "icon": "fa-boxes", "text": "إنشاء منتج مجمع", "class": "btn-info"},
                {"url": reverse("product:service_list"), "icon": "fa-concierge-bell", "text": "الخدمات", "class": "btn-outline-success"},
                {"url": reverse("product:bundle_list"), "icon": "fa-list", "text": "المنتجات المجمعة", "class": "btn-outline-primary"},
            ],
            "breadcrumb_items": [
                {"title": "الرئيسية", "url": reverse("core:dashboard"), "icon": "fas fa-home"},
                {"title": "المنتجات", "active": True},
            ],
        }

        return render(request, "product/product_list.html", context)
    except Exception as e:
        messages.error(request, f"حدث خطأ أثناء تحميل المنتجات: {str(e)}")
        return render(
            request,
            "product/product_list.html",
            {
                "products": [],
                "page_title": "قائمة المنتجات - خطأ",
                "page_icon": "fas fa-exclamation-triangle",
                "breadcrumb_items": [
                    {"title": "الرئيسية", "url": reverse("core:dashboard"), "icon": "fas fa-home"},
                    {"title": "المنتجات", "active": True},
                ],
                "error_message": str(e),
            },
        )


@login_required
@require_POST
def product_bulk_edit(request):
    """
    تعديل جماعي للمنتجات - الأسعار والحالة والتصنيف
    """
    product_ids = request.POST.getlist('product_ids')
    field = request.POST.get('field')
    value = request.POST.get('value', '').strip()

    if not product_ids:
        return JsonResponse({'success': False, 'error': 'لم يتم تحديد أي منتجات'})

    if not field:
        return JsonResponse({'success': False, 'error': 'لم يتم تحديد الحقل المراد تعديله'})

    allowed_fields = {
        'selling_price', 'cost_price',
        'is_active', 'category',
    }
    if field not in allowed_fields:
        return JsonResponse({'success': False, 'error': 'حقل غير مسموح بتعديله'})

    products = Product.objects.filter(id__in=product_ids, is_service=False)
    count = products.count()

    if count == 0:
        return JsonResponse({'success': False, 'error': 'لم يتم العثور على المنتجات المحددة'})

    try:
        with transaction.atomic():
            if field in ('selling_price', 'cost_price'):
                try:
                    decimal_value = Decimal(value)
                    if decimal_value < 0:
                        return JsonResponse({'success': False, 'error': 'القيمة يجب أن تكون موجبة'})
                except Exception:
                    return JsonResponse({'success': False, 'error': 'قيمة السعر غير صحيحة'})
                products.update(**{field: decimal_value})

            elif field == 'is_active':
                if value not in ('true', 'false'):
                    return JsonResponse({'success': False, 'error': 'قيمة الحالة غير صحيحة'})
                products.update(is_active=(value == 'true'))

            elif field == 'category':
                try:
                    category = Category.objects.get(pk=int(value), is_active=True)
                except (Category.DoesNotExist, ValueError):
                    return JsonResponse({'success': False, 'error': 'التصنيف غير موجود'})
                products.update(category=category)

        field_labels = {
            'selling_price': 'سعر البيع',
            'cost_price': 'سعر التكلفة',
            'is_active': 'الحالة',
            'category': 'التصنيف',
        }
        return JsonResponse({
            'success': True,
            'message': f'تم تحديث {field_labels.get(field, field)} لـ {count} منتج بنجاح'
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': f'حدث خطأ: {str(e)}'})


@login_required
def product_create(request):
    """
    إضافة منتج أو خدمة جديدة
    """
    # تحديد نوع العنصر من الـ GET parameter
    is_service = request.GET.get('is_service', 'false').lower() == 'true'
    
    if request.method == "POST":
        form = ProductForm(request.POST, request.FILES, is_service=is_service)
        if form.is_valid():
            product = form.save(commit=False)
            product.created_by = request.user
            product.save()

            # معالجة الصور
            images = request.FILES.getlist("images")
            for image in images:
                ProductImage.objects.create(
                    product=product,
                    image=image,
                    is_primary=not ProductImage.objects.filter(
                        product=product
                    ).exists(),
                )

            # رسالة نجاح ديناميكية
            item_type = "الخدمة" if product.is_service else "المنتج"
            messages.success(request, f'تم إضافة {item_type} "{product.name}" بنجاح')

            if "save_and_continue" in request.POST:
                # إعادة التوجيه مع نفس الـ parameter
                redirect_url = reverse("product:product_create")
                if product.is_service:
                    redirect_url += "?is_service=true"
                return redirect(redirect_url)
            else:
                # توجيه ديناميكي حسب النوع
                if product.is_service:
                    return redirect("product:service_list")
                else:
                    return redirect("product:product_list")
    else:
        # تمرير is_service للفورم
        form = ProductForm(is_service=is_service)

    # عناوين ديناميكية حسب النوع
    if is_service:
        page_title = "إضافة خدمة جديدة"
        page_subtitle = "إضافة خدمة جديدة إلى قاعدة البيانات"
        page_icon = "fas fa-concierge-bell"
        breadcrumb_title = "إضافة خدمة"
        breadcrumb_parent_title = "الخدمات"
        breadcrumb_parent_url = reverse("product:service_list")
    else:
        page_title = "إضافة منتج جديد"
        page_subtitle = "إضافة منتج جديد إلى قاعدة البيانات"
        page_icon = "fas fa-box-open"
        breadcrumb_title = "إضافة منتج"
        breadcrumb_parent_title = "المنتجات"
        breadcrumb_parent_url = reverse("product:product_list")

    context = {
        "form": form,
        "page_title": page_title,
        "page_subtitle": page_subtitle,
        "page_icon": page_icon,
        "is_service": is_service,
        "header_buttons": [
            {
                "url": breadcrumb_parent_url,
                "icon": "fa-arrow-left",
                "text": "العودة للقائمة",
                "class": "btn-outline-secondary",
            },
        ],
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": breadcrumb_parent_title,
                "url": breadcrumb_parent_url,
                "icon": "fas fa-boxes" if not is_service else "fas fa-concierge-bell",
            },
            {"title": breadcrumb_title, "active": True},
        ],
    }

    return render(request, "product/product_form.html", context)


@login_required
def service_list(request):
    """
    عرض قائمة الخدمات فقط
    """
    try:
        # استرجاع الخدمات فقط
        services = (
            Product.objects.select_related("category", "unit")
            .prefetch_related("stocks")
            .filter(is_service=True)
            .all()
        )

        # البحث البسيط
        search_query = request.GET.get("search", "")
        if search_query:
            services = services.filter(name__icontains=search_query)

        # تطبيق التصفية
        filter_form = ProductSearchForm(request.GET)
        
        if filter_form.is_valid():
            if filter_form.cleaned_data.get('name'):
                services = services.filter(name__icontains=filter_form.cleaned_data['name'])
            
            if filter_form.cleaned_data.get('category'):
                services = services.filter(category=filter_form.cleaned_data['category'])
            
            if filter_form.cleaned_data.get('min_price'):
                services = services.filter(selling_price__gte=filter_form.cleaned_data['min_price'])
            
            if filter_form.cleaned_data.get('max_price'):
                services = services.filter(selling_price__lte=filter_form.cleaned_data['max_price'])
            
            if filter_form.cleaned_data.get('is_active'):
                services = services.filter(is_active=True)

        # تعريف أعمدة جدول الخدمات
        service_headers = [
            {
                "key": "image",
                "label": "الصورة",
                "sortable": False,
                "class": "text-center",
                "template": "components/cells/product_image.html",
                "width": "80px",
            },
            {
                "key": "name_with_sku",
                "label": "اسم الخدمة",
                "sortable": True,
                "class": "text-start",
                "template": "components/cells/product_name_with_sku.html",
            },
            {
                "key": "category",
                "label": "التصنيف",
                "sortable": True,
                "class": "text-center",
                "template": "components/cells/product_category.html",
                "width": "120px",
            },
            {
                "key": "sale_price",
                "label": "السعر",
                "sortable": True,
                "class": "text-center",
                "template": "components/cells/product_price.html",
                "width": "120px",
            },
            {
                "key": "is_active",
                "label": "الحالة",
                "sortable": True,
                "class": "text-center",
                "template": "components/cells/product_status.html",
                "width": "90px",
            },
        ]

        # تحضير بيانات الجدول
        table_data = []
        
        for service in services:
            detail_url = reverse("product:product_detail", args=[service.pk])
            
            row_data = {
                "id": service.id,
                "image": service,
                "name_with_sku": service,
                "name": service.name,
                "sku": service.sku,
                "category": service.category,
                "sale_price": service.selling_price,
                "is_active": service.is_active,
                "row_click_url": detail_url,
            }
            table_data.append(row_data)
        
        # تعريف أزرار الإجراءات
        action_buttons = [
            {
                "url": "product:product_detail",
                "icon": "fa-eye",
                "label": "عرض التفاصيل",
                "class": "action-view",
                "title": "عرض تفاصيل الخدمة"
            },
            {
                "url": "product:product_edit",
                "icon": "fa-edit",
                "label": "تعديل",
                "class": "action-edit",
                "title": "تعديل الخدمة"
            },
        ]

        context = {
            "products": services,
            "table_data": table_data,
            "filter_form": filter_form,
            "product_headers": service_headers,
            "action_buttons": action_buttons,
            "primary_key": "id",
            
            "page_title": "قائمة الخدمات",
            "page_subtitle": "إدارة الخدمات المقدمة في النظام",
            "page_icon": "fas fa-concierge-bell",
            "header_buttons": [
                {
                    "url": reverse("product:product_create") + "?is_service=true",
                    "icon": "fa-plus",
                    "text": "إضافة خدمة",
                    "class": "btn-success",
                },
                {
                    "url": reverse("product:product_list"),
                    "icon": "fa-boxes",
                    "text": "المنتجات",
                    "class": "btn-outline-primary",
                },
            ],
            "breadcrumb_items": [
                {
                    "title": "الرئيسية",
                    "url": reverse("core:dashboard"),
                    "icon": "fas fa-home",
                },
                {"title": "الخدمات", "active": True},
            ],
        }

        return render(request, "product/service_list.html", context)
    except Exception as e:
        messages.error(request, f"حدث خطأ أثناء تحميل الخدمات: {str(e)}")
        return render(
            request,
            "product/service_list.html",
            {
                "products": Product.objects.none(),
                "filter_form": ProductSearchForm(),
                "page_title": "قائمة الخدمات - خطأ",
                "page_icon": "fas fa-exclamation-triangle",
                "breadcrumb_items": [
                    {
                        "title": "الرئيسية",
                        "url": reverse("core:dashboard"),
                        "icon": "fas fa-home",
                    },
                    {"title": "الخدمات", "active": True},
                ],
                "error_message": str(e),
            },
        )


@login_required
def product_create_modal(request):
    """
    إضافة منتج جديد عبر المودال
    """
    if request.method == "POST":
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            product = form.save(commit=False)
            product.created_by = request.user
            product.save()

            # معالجة الصور
            images = request.FILES.getlist("images")
            for image in images:
                ProductImage.objects.create(
                    product=product,
                    image=image,
                    is_primary=not ProductImage.objects.filter(
                        product=product
                    ).exists(),
                )

            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': f'تم إضافة المنتج "{product.name}" بنجاح',
                    'product_id': product.id,
                    'product_name': product.name
                })
            else:
                messages.success(request, f'تم إضافة المنتج "{product.name}" بنجاح')
                return redirect("product:product_list")
        else:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'errors': form.errors
                })
    else:
        form = ProductForm()

    context = {
        "form": form,
        "page_title": "إضافة منتج جديد",
        "is_modal": True,
    }

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        html = render_to_string("product/product_modal_form.html", context, request=request)
        return JsonResponse({'html': html})
    
    return render(request, "product/product_modal_form.html", context)


@login_required
def product_edit(request, pk):
    """
    تعديل منتج أو خدمة
    """
    product = get_object_or_404(Product, pk=pk)

    if request.method == "POST":
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            product = form.save(commit=False)
            product.updated_by = request.user
            product.save()

            # معالجة الصور
            images = request.FILES.getlist("images")
            for image in images:
                ProductImage.objects.create(
                    product=product,
                    image=image,
                    is_primary=not ProductImage.objects.filter(
                        product=product
                    ).exists(),
                )

            # رسالة نجاح ديناميكية
            item_type = "الخدمة" if product.is_service else "المنتج"
            messages.success(request, f'تم تحديث {item_type} "{product.name}" بنجاح')
            
            # توجيه ديناميكي حسب النوع
            if product.is_service:
                return redirect("product:service_list")
            else:
                return redirect("product:product_list")
    else:
        form = ProductForm(instance=product)

    # عناوين ديناميكية حسب النوع
    if product.is_service:
        item_type = "الخدمة"
        page_icon = "fas fa-concierge-bell"
        breadcrumb_parent_title = "الخدمات"
        breadcrumb_parent_url = reverse("product:service_list")
    else:
        item_type = "المنتج"
        page_icon = "fas fa-edit"
        breadcrumb_parent_title = "المنتجات"
        breadcrumb_parent_url = reverse("product:product_list")

    context = {
        "form": form,
        "product": product,
        "title": f"تعديل {item_type}: {product.name}",
        "page_title": f"تعديل {item_type}: {product.name}",
        "page_subtitle": f"تعديل بيانات {item_type} الحالي",
        "page_icon": page_icon,
        "is_service": product.is_service,
        "header_buttons": [
            {
                "url": breadcrumb_parent_url,
                "icon": "fa-arrow-left",
                "text": "العودة للقائمة",
                "class": "btn-outline-secondary",
            },
        ],
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": breadcrumb_parent_title,
                "url": breadcrumb_parent_url,
                "icon": "fas fa-boxes" if not product.is_service else "fas fa-concierge-bell",
            },
            {"title": f"تعديل: {product.name}", "active": True},
        ],
    }

    return render(request, "product/product_form.html", context)


@login_required
def product_detail(request, pk):
    """
    عرض تفاصيل المنتج
    """
    product = get_object_or_404(
        Product.objects.select_related("category", "unit", "default_supplier"),
        pk=pk,
    )

    # الحصول على المخزون الحالي للمنتج في كل مخزن
    stock_items = Stock.objects.filter(product=product).select_related("warehouse")

    # آخر حركات المخزون
    stock_movements = (
        StockMovement.objects.filter(product=product)
        .select_related("warehouse", "destination_warehouse", "created_by")
        .order_by("-timestamp")[:10]
    )

    # إجمالي المخزون
    total_stock = stock_items.aggregate(total=Sum("quantity"))["total"] or 0

    # أسعار الموردين (مرتبة حسب السعر)
    try:
        supplier_prices = (
            SupplierProductPrice.objects.filter(product=product, is_active=True)
            .select_related("supplier")
            .order_by("cost_price", "-is_default")
        )
    except:
        supplier_prices = []

    # إحصائيات المبيعات
    sales_stats = get_product_sales_statistics(product)

    context = {
        "product": product,
        "stock_items": stock_items,
        "stock_movements": stock_movements,
        "total_stock": total_stock,
        "supplier_prices": supplier_prices,
        "sales_stats": sales_stats,
        "title": product.name,
        
        # بيانات الهيدر
        "page_title": product.name,
        "page_subtitle": f'{product.sku} • {product.category.name}',
        "page_icon": "fas fa-box",
        
        # أزرار الهيدر
        "header_buttons": [
            {
                "url": reverse("product:product_edit", kwargs={"pk": product.pk}),
                "icon": "fa-edit",
                "text": "تعديل",
                "class": "btn-primary",
            },
            {
                "url": reverse("product:product_delete", kwargs={"pk": product.pk}),
                "icon": "fa-trash-alt",
                "text": "حذف",
                "class": "btn-danger",
            },
            {
                "url": reverse("product:product_list"),
                "icon": "fa-arrow-right",
                "text": "العودة للقائمة",
                "class": "btn-outline-secondary",
            },
        ],
        
        # البريدكرمب
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": "المنتجات", "url": reverse("product:product_list"), "icon": "fas fa-box"},
            {"title": product.name, "active": True},
        ],
    }

    return render(request, "product/product_detail.html", context)


@login_required
@require_POST
def product_image_upload(request, pk):
    """
    رفع صورة للمنتج من صفحة التفاصيل
    """
    product = get_object_or_404(Product, pk=pk)
    
    try:
        # التحقق من وجود ملف الصورة
        if 'image' not in request.FILES:
            return JsonResponse({'success': False, 'message': 'لم يتم اختيار صورة'})
        
        image_file = request.FILES['image']
        alt_text = request.POST.get('alt_text', '')
        is_primary = request.POST.get('is_primary') == 'on'
        
        # إذا كانت الصورة رئيسية، إلغاء تفعيل الصور الرئيسية الأخرى
        if is_primary:
            ProductImage.objects.filter(product=product, is_primary=True).update(is_primary=False)
        
        # إنشاء الصورة الجديدة
        product_image = ProductImage.objects.create(
            product=product,
            image=image_file,
            alt_text=alt_text,
            is_primary=is_primary
        )
        
        return JsonResponse({
            'success': True,
            'message': 'تم رفع الصورة بنجاح',
            'image_url': product_image.image.url
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'حدث خطأ أثناء رفع الصورة: {str(e)}'
        })


@login_required
def product_delete(request, pk):
    """
    حذف منتج - حذف فعلي إذا لم يكن مرتبط بمعاملات، وإلا تعطيل فقط
    """
    product = get_object_or_404(Product, pk=pk)

    # فحص المعاملات المرتبطة
    has_movements = InventoryMovement.objects.filter(product=product).exists()
    
    has_purchase_items = (
        PurchaseItem is not None
        and PurchaseItem.objects.filter(product=product).exists()
    )
    
    # التحقق من وجود مكونات Bundle
    has_bundle_components = False
    try:
        from product.models.product_core import BundleComponent
        has_bundle_components = BundleComponent.objects.filter(
            models.Q(bundle_product=product) | models.Q(component_product=product)
        ).exists()
    except ImportError:
        pass
    
    # التحقق من وجود أسعار موردين
    has_supplier_prices = False
    try:
        from product.models.supplier_pricing import SupplierProductPrice
        has_supplier_prices = SupplierProductPrice.objects.filter(product=product).exists()
    except ImportError:
        pass
    
    # التحقق من وجود حجوزات مخزون
    has_reservations = False
    try:
        from product.models.reservation_system import StockReservation
        has_reservations = StockReservation.objects.filter(product=product).exists()
    except ImportError:
        pass

    # تحديد إذا كان المنتج مرتبط بأي معاملات
    has_transactions = (
        has_movements or has_purchase_items or 
        has_bundle_components or has_supplier_prices or has_reservations
    )
    can_delete_permanently = not has_transactions

    if request.method == "POST":
        action = request.POST.get('action', 'deactivate')
        
        if action == 'delete' and can_delete_permanently:
            # حذف نهائي
            product_name = product.name
            product.delete()
            messages.success(request, f"تم حذف المنتج '{product_name}' نهائياً")
        else:
            # تعطيل فقط
            product.is_active = False
            product.save()
            messages.warning(request, "تم تعطيل المنتج (لا يمكن الحذف النهائي لوجود معاملات مرتبطة)")
        
        return redirect("product:product_list")

    # إعداد معلومات المعاملات للعرض
    transactions_info = []
    if has_movements:
        movements_count = InventoryMovement.objects.filter(product=product).count()
        transactions_info.append(f"{movements_count} حركة مخزنية")
    if has_purchase_items:
        purchases_count = PurchaseItem.objects.filter(product=product).count()
        transactions_info.append(f"{purchases_count} فاتورة مشتريات")
    if has_bundle_components:
        from product.models.product_core import BundleComponent
        bundles_count = BundleComponent.objects.filter(
            models.Q(bundle_product=product) | models.Q(component_product=product)
        ).count()
        transactions_info.append(f"{bundles_count} مكون Bundle")
    if has_supplier_prices:
        from product.models.supplier_pricing import SupplierProductPrice
        prices_count = SupplierProductPrice.objects.filter(product=product).count()
        transactions_info.append(f"{prices_count} سعر مورد")
    if has_reservations:
        from product.models.reservation_system import StockReservation
        reservations_count = StockReservation.objects.filter(product=product).count()
        transactions_info.append(f"{reservations_count} حجز مخزون")

    context = {
        "product": product,
        "can_delete_permanently": can_delete_permanently,
        "has_transactions": has_transactions,
        "transactions_info": transactions_info,
        "page_title": f"حذف المنتج: {product.name}",
        "page_icon": "fas fa-box-open",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "المنتجات",
                "url": reverse("product:product_list"),
                "icon": "fas fa-boxes",
            },
            {
                "title": product.name,
                "url": reverse("product:product_detail", kwargs={"pk": product.pk}),
            },
            {"title": "حذف", "active": True},
        ],
    }

    return render(request, "product/product_delete.html", context)


@login_required
def bundle_detail(request, pk):
    """
    عرض تفاصيل المنتج المجمع مع تفصيل المكونات والمخزون المحسوب
    Requirements: 7.3, 7.4
    """
    import logging
    logger = logging.getLogger('product')
    
    from django.conf import settings
    from ..services.bundle_query_optimizer import BundleQueryOptimizer
    from ..services.stock_calculation_engine import StockCalculationEngine
    
    # الحصول على المنتج المجمع بشكل محسن
    bundle = BundleQueryOptimizer.get_bundle_with_stock_info(pk)
    
    if not bundle:
        logger.warning(f"المنتج المجمع رقم {pk} غير موجود أو ليس منتج مجمع")
        messages.error(request, "المنتج المجمع غير موجود")
        return redirect("product:bundle_list")
    
    
    try:
        
        # الحصول على تفصيل مخزون المنتج المجمع من التخزين المؤقت أو حساب جديد
        bundle_stock_breakdown = StockCalculationEngine.get_bundle_stock_breakdown(bundle)
        
        # حساب إحصائيات المكونات باستخدام البيانات المحسنة
        components_data = []
        total_components = 0
        available_components = 0
        
        # استخدام البيانات المحسنة من الاستعلام
        for component in getattr(bundle, 'components_with_stock', bundle.components.all()):
            comp_product = component.component_product
            comp_stock = getattr(component, 'component_stock', comp_product.current_stock)
            required_qty = component.required_quantity
            
            # حساب كم وحدة من المنتج المجمع يمكن تكوينها من هذا المكون
            possible_bundles = getattr(component, 'possible_bundles', 
                                     comp_stock // required_qty if required_qty > 0 else 0)
            
            # حالة توفر المكون
            availability_status = "متاح" if comp_stock >= required_qty else "غير متاح"
            availability_class = "success" if comp_stock >= required_qty else "danger"
            
            # جلب البدائل المتاحة للمكون (إذا كان النظام مفعل)
            alternatives = []
            alternatives_count = 0
            if settings.MIGRATION_FLAGS.get('BUNDLE_ALTERNATIVES_ENABLED', False):
                from product.models import BundleComponentAlternative
                alternatives = BundleComponentAlternative.objects.filter(
                    bundle_component=component,
                    is_active=True
                ).select_related('alternative_product', 'alternative_product__category').order_by('display_order', 'id')
                alternatives_count = alternatives.count()
            
            components_data.append({
                'component': component,
                'product': comp_product,
                'current_stock': comp_stock,
                'required_quantity': required_qty,
                'possible_bundles': int(possible_bundles),
                'availability_status': availability_status,
                'availability_class': availability_class,
                'stock_ratio': (comp_stock / required_qty * 100) if required_qty > 0 else 0,
                'alternatives': alternatives,
                'alternatives_count': alternatives_count,
            })
            
            total_components += 1
            if comp_stock >= required_qty:
                available_components += 1
        
        # إحصائيات سريعة للمنتج المجمع
        calculated_stock = bundle.calculated_stock
        components_count = bundle.components.count()
        availability_percentage = (available_components / total_components * 100) if total_components > 0 else 0
        
        # إعداد السياق
        context = {
            "bundle": bundle,
            "components_data": components_data,
            "bundle_stock_breakdown": bundle_stock_breakdown,
            "calculated_stock": calculated_stock,
            "components_count": components_count,
            "total_components": total_components,
            "available_components": available_components,
            "availability_percentage": availability_percentage,
            
            # بيانات الهيدر الموحد
            "title": f"تفاصيل المنتج المجمع: {bundle.name}",
            "page_title": bundle.name,
            "page_subtitle": f"كود المنتج: {bundle.sku} • {components_count} مكون",
            "page_icon": "fas fa-boxes",
            
            # أزرار الهيدر
            "header_buttons": [
                {
                    "url": reverse("product:product_edit", args=[bundle.pk]),
                    "icon": "fa-edit",
                    "text": "تعديل المنتج",
                    "class": "btn-primary",
                },
                {
                    "url": reverse("product:bundle_list"),
                    "icon": "fa-arrow-right",
                    "text": "العودة للقائمة",
                    "class": "btn-outline-secondary",
                },
            ],
            
            # مسار التنقل
            "breadcrumb_items": [
                {
                    "title": "الرئيسية",
                    "url": reverse("core:dashboard"),
                    "icon": "fas fa-home",
                },
                {
                    "title": "المنتجات",
                    "url": reverse("product:product_list"),
                    "icon": "fas fa-boxes",
                },
                {
                    "title": "المنتجات المجمعة",
                    "url": reverse("product:bundle_list"),
                    "icon": "fas fa-boxes",
                },
                {"title": f"تفاصيل: {bundle.name}", "active": True},
            ],
        }

        return render(request, "product/bundle_detail.html", context)
        
    except Exception as e:
        # في حالة حدوث أي خطأ، نعرض صفحة خطأ مع رسالة واضحة
        messages.error(request, f"حدث خطأ أثناء تحميل تفاصيل المنتج المجمع: {str(e)}")
        return redirect("product:bundle_list")


@login_required
def bundle_list(request):
    """
    عرض قائمة المنتجات المجمعة
    Requirements: 7.1, 7.2, 7.5
    """
    try:
        from ..services.bundle_query_optimizer import BundleQueryOptimizer
        
        # استخدام الاستعلام المحسن
        bundles = BundleQueryOptimizer.get_bundles_for_listing(active_only=False)

        # البحث البسيط
        search_query = request.GET.get("search", "")
        if search_query:
            bundles = bundles.filter(
                Q(name__icontains=search_query) | Q(sku__icontains=search_query)
            )

        # فلتر التصنيف
        category_id = request.GET.get("category")
        if category_id:
            bundles = bundles.filter(category_id=category_id)

        # فلتر الحالة
        status = request.GET.get("status")
        if status == "active":
            bundles = bundles.filter(is_active=True)
        elif status == "inactive":
            bundles = bundles.filter(is_active=False)

        # إحصائيات سريعة محسنة
        stats = BundleQueryOptimizer.get_bundle_sales_stats()
        total_bundles = stats.get('total_bundles', 0)
        active_bundles = stats.get('active_bundles', 0)
        inactive_bundles = total_bundles - active_bundles

        # تعريف أعمدة جدول المنتجات المجمعة
        bundle_headers = [
            {
                "key": "sku",
                "label": "كود المنتج",
                "sortable": True,
                "class": "text-center",
                "template": "components/cells/product_sku.html",
                "width": "120px",
            },
            {"key": "name", "label": "اسم المنتج المجمع", "sortable": True, "class": "text-start"},
            {
                "key": "category",
                "label": "التصنيف",
                "sortable": True,
                "class": "text-center",
                "template": "components/cells/product_category.html",
                "width": "120px",
            },
            {
                "key": "components_count",
                "label": "عدد المكونات",
                "sortable": True,
                "class": "text-center",
                "format": "html",
                "width": "120px",
            },
            {
                "key": "selling_price",
                "label": "سعر البيع",
                "sortable": True,
                "class": "text-center",
                "template": "components/cells/product_price.html",
                "width": "120px",
            },
            {
                "key": "calculated_stock",
                "label": "المخزون المحسوب",
                "sortable": True,
                "class": "text-center",
                "format": "html",
                "width": "120px",
            },
            {
                "key": "is_active",
                "label": "الحالة",
                "sortable": True,
                "class": "text-center",
                "format": "status",
                "width": "90px",
            },
            {
                "key": "actions",
                "label": "الإجراءات",
                "class": "text-center",
                "width": "150px",
            },
        ]

        # تحضير بيانات الجدول
        table_data = []
        for bundle in bundles:
            # حساب عدد المكونات
            components_count = bundle.components.count()
            
            # حساب المخزون المحسوب
            calculated_stock = bundle.calculated_stock
            
            # تحضير أزرار الإجراءات
            actions = [
                {
                    "url": reverse("product:bundle_detail", args=[bundle.pk]),
                    "icon": "fas fa-eye",
                    "label": "عرض التفاصيل",
                    "class": "btn-outline-info btn-sm",
                    "title": "عرض تفاصيل المنتج المجمع"
                },
                {
                    "url": reverse("product:product_edit", args=[bundle.pk]),
                    "icon": "fas fa-edit",
                    "label": "تعديل",
                    "class": "btn-outline-primary btn-sm",
                    "title": "تعديل المنتج المجمع"
                },
            ]

            row_data = {
                "id": bundle.id,
                "sku": bundle.sku,
                "name": bundle.name,
                "category": bundle.category,
                "components_count": f'<span class="badge bg-info">{components_count} مكون</span>',
                "selling_price": bundle.selling_price,
                "calculated_stock": f'<span class="badge bg-{"success" if calculated_stock > 0 else "warning"}">{calculated_stock}</span>',
                "is_active": bundle.is_active,
                "actions": actions,
            }
            table_data.append(row_data)

        # إعداد السياق
        context = {
            "bundles": bundles,
            "table_data": table_data,
            "bundle_headers": bundle_headers,
            "primary_key": "id",
            "search_query": search_query,
            "total_bundles": total_bundles,
            "active_bundles": active_bundles,
            "inactive_bundles": inactive_bundles,
            
            # بيانات الهيدر الموحد
            "title": "المنتجات المجمعة",
            "page_title": "المنتجات المجمعة",
            "page_subtitle": "إدارة المنتجات المركبة والمجمعة",
            "page_icon": "fas fa-boxes",
            
            # أزرار الهيدر
            "header_buttons": [
                {
                    "url": reverse("product:bundle_create"),
                    "icon": "fa-plus",
                    "text": "إنشاء منتج مجمع",
                    "class": "btn-success",
                },
                {
                    "url": reverse("product:product_list"),
                    "icon": "fa-list",
                    "text": "جميع المنتجات",
                    "class": "btn-outline-primary",
                },
            ],
            
            # مسار التنقل
            "breadcrumb_items": [
                {
                    "title": "الرئيسية",
                    "url": reverse("core:dashboard"),
                    "icon": "fas fa-home",
                },
                {
                    "title": "المنتجات",
                    "url": reverse("product:product_list"),
                    "icon": "fas fa-boxes",
                },
                {"title": "المنتجات المجمعة", "active": True},
            ],
            
            # فلاتر للقالب
            "categories": Category.objects.filter(is_active=True).order_by("name"),
        }

        return render(request, "product/bundle_list.html", context)
        
    except Exception as e:
        # في حالة حدوث أي خطأ، نعرض صفحة بسيطة مع رسالة الخطأ
        messages.error(request, f"حدث خطأ أثناء تحميل المنتجات المجمعة: {str(e)}")
        return render(
            request,
            "product/bundle_list.html",
            {
                "bundles": Product.objects.none(),
                "table_data": [],
                "bundle_headers": [],
                "page_title": "المنتجات المجمعة - خطأ",
                "page_icon": "fas fa-exclamation-triangle",
                "breadcrumb_items": [
                    {
                        "title": "الرئيسية",
                        "url": reverse("core:dashboard"),
                        "icon": "fas fa-home",
                    },
                    {
                        "title": "المنتجات",
                        "url": reverse("product:product_list"),
                        "icon": "fas fa-boxes",
                    },
                    {"title": "المنتجات المجمعة", "active": True},
                ],
                "error_message": str(e),
            },
        )


@login_required
def category_list(request):
    """
    عرض قائمة تصنيفات المنتجات
    """
    categories = Category.objects.all()

    # بحث
    search_query = request.GET.get("search", "")
    if search_query:
        categories = categories.filter(name__icontains=search_query)

    # التصنيفات حسب الحالة
    status = request.GET.get("status", "")
    if status == "active":
        categories = categories.filter(is_active=True)
    elif status == "inactive":
        categories = categories.filter(is_active=False)

    # إجمالي التصنيفات والتصنيفات النشطة
    total_categories = Category.objects.count()
    active_categories = Category.objects.filter(is_active=True).count()

    # التصنيفات الرئيسية (التي ليس لها أب)
    root_categories = categories.filter(parent__isnull=True)

    # ترقيم الصفحات
    paginator = Paginator(categories, 30)
    page = request.GET.get("page")

    try:
        categories = paginator.page(page)
    except PageNotAnInteger:
        categories = paginator.page(1)
    except EmptyPage:
        categories = paginator.page(paginator.num_pages)

    # تعريف أعمدة جدول الفئات
    category_headers = [
        {"key": "name", "label": "اسم الفئة", "sortable": True, "class": "text-start"},
        {
            "key": "description",
            "label": "الوصف",
            "sortable": True,
            "class": "text-start",
        },
        {
            "key": "parent.name",
            "label": "الفئة الأب",
            "sortable": True,
            "class": "text-center",
            "width": "120px",
        },
        {
            "key": "products_count",
            "label": "عدد المنتجات",
            "sortable": True,
            "class": "text-center",
            "template": "components/cells/products_count.html",
            "width": "120px",
        },
        {
            "key": "is_active",
            "label": "الحالة",
            "sortable": True,
            "class": "text-center",
            "template": "components/cells/product_status.html",
            "width": "90px",
        },
    ]

    # أزرار الإجراءات
    category_actions = [
        {
            "url": "product:category_detail",
            "icon": "fa-eye",
            "label": "عرض",
            "class": "action-view",
        },
        {
            "url": "product:category_edit",
            "icon": "fa-edit",
            "label": "تعديل",
            "class": "action-edit",
        },
        {
            "url": "product:category_delete",
            "icon": "fa-trash",
            "label": "حذف",
            "class": "action-delete",
        },
    ]

    context = {
        "categories": categories,
        "category_headers": category_headers,
        "category_actions": category_actions,
        "primary_key": "id",
        "root_categories": root_categories,
        "total_categories": total_categories,
        "active_categories": active_categories,
        "search_query": search_query,
        "status": status,
        "page_title": "تصنيفات المنتجات",
        "page_subtitle": "إدارة التصنيفات للمنتجات وتنظيمها",
        "page_icon": "fas fa-tags",
        "header_buttons": [
            {
                "url": reverse("product:category_create"),
                "icon": "fa-plus",
                "text": "إضافة تصنيف",
                "class": "btn-primary",
            },
        ],
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "المنتجات",
                "url": reverse("product:product_list"),
                "icon": "fas fa-boxes",
            },
            {"title": "التصنيفات", "active": True},
        ],
    }

    return render(request, "product/category_list.html", context)


@login_required
def category_create(request):
    """
    إضافة فئة منتجات جديدة
    """
    if request.method == "POST":
        form = CategoryForm(request.POST)
        if form.is_valid():
            category = form.save()
            messages.success(request, f'تم إضافة التصنيف "{category.name}" بنجاح')
            return redirect("product:category_list")
    else:
        form = CategoryForm()

    context = {
        "form": form,
        "page_title": "إضافة فئة جديدة",
        "page_subtitle": "إضافة تصنيف جديد للمنتجات",
        "page_icon": "fas fa-folder-plus",
        "object_type": "فئة",
        "list_url": reverse("product:category_list"),
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "المنتجات",
                "url": reverse("product:product_list"),
                "icon": "fas fa-boxes",
            },
            {
                "title": "التصنيفات",
                "url": reverse("product:category_list"),
                "icon": "fas fa-tags",
            },
            {"title": "إضافة فئة", "active": True},
        ],
    }

    return render(request, "product/category_form.html", context)


@login_required
def category_edit(request, pk):
    """
    تعديل فئة منتجات
    """
    category = get_object_or_404(Category, pk=pk)

    if request.method == "POST":
        form = CategoryForm(request.POST, instance=category)
        if form.is_valid():
            category = form.save()
            messages.success(request, f'تم تحديث التصنيف "{category.name}" بنجاح')
            return redirect("product:category_list")
    else:
        form = CategoryForm(instance=category)

    context = {
        "form": form,
        "category": category,
        "page_title": f"تعديل التصنيف: {category.name}",
        "page_subtitle": "تحديث بيانات التصنيف",
        "page_icon": "fas fa-edit",
        "object_type": "فئة",
        "list_url": reverse("product:category_list"),
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "المنتجات",
                "url": reverse("product:product_list"),
                "icon": "fas fa-boxes",
            },
            {
                "title": "التصنيفات",
                "url": reverse("product:category_list"),
                "icon": "fas fa-tags",
            },
            {"title": f"تعديل: {category.name}", "active": True},
        ],
    }

    return render(request, "product/category_form.html", context)


@login_required
def category_delete(request, pk):
    """
    حذف فئة منتجات
    """
    category = get_object_or_404(Category, pk=pk)

    if request.method == "POST":
        name = category.name
        category.delete()
        messages.success(request, f'تم حذف التصنيف "{name}" بنجاح')
        return redirect("product:category_list")

    context = {
        "category": category,
        "title": f"حذف التصنيف: {category.name}",
    }

    return render(request, "product/category_confirm_delete.html", context)


@login_required
def category_detail(request, pk):
    """
    عرض تفاصيل فئة منتجات
    """
    category = get_object_or_404(Category, pk=pk)

    # الحصول على المنتجات في هذا التصنيف
    products = Product.objects.filter(category=category).select_related("unit")

    # التصنيفات الفرعية
    subcategories = Category.objects.filter(parent=category)

    context = {
        "category": category,
        "products": products,
        "subcategories": subcategories,
        "title": category.name,
        "page_title": category.name,
        "page_subtitle": "معلومات وإحصائيات التصنيف",
        "page_icon": "fas fa-folder",
        "header_buttons": [
            {
                "url": f"/products/categories/{category.pk}/edit/",
                "icon": "fa-edit",
                "text": "تعديل",
                "class": "btn-primary",
            },
            {
                "url": f"/products/categories/{category.pk}/delete/",
                "icon": "fa-trash",
                "text": "حذف",
                "class": "btn-danger",
            },
        ],
        "breadcrumb_items": [
            {"title": "التصنيفات", "url": "/products/categories/", "icon": "fas fa-folder"},
        ],
    }
    
    # إضافة التصنيف الأب إذا وجد
    if category.parent:
        context["breadcrumb_items"].append(
            {"title": category.parent.name, "url": f"/products/categories/{category.parent.pk}/"}
        )
    
    # إضافة التصنيف الحالي
    context["breadcrumb_items"].append({"title": category.name, "active": True})

    return render(request, "product/category_detail.html", context)



@login_required
def unit_list(request):
    """
    عرض قائمة وحدات القياس
    """
    units = Unit.objects.all()

    # البحث البسيط
    search_query = request.GET.get("search", "")
    if search_query:
        units = units.filter(name__icontains=search_query)

    # تعريف أعمدة جدول الوحدات
    unit_headers = [
        {"key": "name", "label": "اسم الوحدة", "sortable": True, "class": "text-start"},
        {
            "key": "symbol",
            "label": "الرمز",
            "sortable": True,
            "class": "text-center",
            "width": "100px",
        },
        {
            "key": "description",
            "label": "الوصف",
            "sortable": True,
            "class": "text-start",
        },
        {
            "key": "products_count",
            "label": "عدد المنتجات",
            "sortable": True,
            "class": "text-center",
            "template": "components/cells/products_count.html",
            "width": "120px",
        },
        {
            "key": "is_active",
            "label": "الحالة",
            "sortable": True,
            "class": "text-center",
            "template": "components/cells/product_status.html",
            "width": "90px",
        },
    ]

    # أزرار الإجراءات - إزالة زر الإضافة لأنه موجود في الـ header
    unit_actions = [
        {
            "url": "product:unit_detail",
            "icon": "fa-eye",
            "label": "عرض",
            "class": "action-view",
        },
        {
            "url": "product:unit_edit",
            "icon": "fa-edit",
            "label": "تعديل",
            "class": "action-edit",
        },
        {
            "url": "product:unit_delete",
            "icon": "fa-trash",
            "label": "حذف",
            "class": "action-delete",
        },
    ]

    context = {
        "units": units,
        "unit_headers": unit_headers,
        "unit_actions": unit_actions,
        "primary_key": "id",
        "title": "وحدات القياس",
        "page_title": "وحدات القياس",
        "page_subtitle": "إدارة وحدات القياس للمنتجات",
        "page_icon": "fas fa-balance-scale",
        "header_buttons": [
            {
                "url": reverse("product:unit_create"),
                "icon": "fa-plus",
                "text": "إضافة وحدة قياس",
                "class": "btn-primary",
            },
        ],
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "المنتجات",
                "url": reverse("product:product_list"),
                "icon": "fas fa-boxes",
            },
            {"title": "وحدات القياس", "active": True},
        ],
    }

    return render(request, "product/unit_list.html", context)


@login_required
def unit_create(request):
    """
    إضافة وحدة قياس جديدة
    """
    if request.method == "POST":
        form = UnitForm(request.POST)
        if form.is_valid():
            unit = form.save()
            messages.success(request, f'تم إضافة وحدة القياس "{unit.name}" بنجاح')
            return redirect("product:unit_list")
    else:
        form = UnitForm()

    context = {
        "form": form,
        "page_title": "إضافة وحدة قياس جديدة",
        "page_subtitle": "أدخل البيانات المطلوبة ثم اضغط حفظ",
        "page_icon": "fas fa-balance-scale",
        "header_buttons": [
            {
                "url": reverse("product:unit_list"),
                "icon": "fa-arrow-right",
                "text": "العودة للقائمة",
                "class": "btn-secondary",
            },
        ],
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "المنتجات",
                "url": reverse("product:product_list"),
                "icon": "fas fa-boxes",
            },
            {
                "title": "وحدات القياس",
                "url": reverse("product:unit_list"),
                "icon": "fas fa-balance-scale",
            },
            {"title": "إضافة وحدة", "active": True},
        ],
    }

    return render(request, "product/unit_form.html", context)


@login_required
def unit_edit(request, pk):
    """
    تعديل وحدة قياس
    """
    unit = get_object_or_404(Unit, pk=pk)

    if request.method == "POST":
        form = UnitForm(request.POST, instance=unit)
        if form.is_valid():
            unit = form.save()
            messages.success(request, f'تم تحديث وحدة القياس "{unit.name}" بنجاح')
            return redirect("product:unit_list")
    else:
        form = UnitForm(instance=unit)

    context = {
        "form": form,
        "unit": unit,
        "title": f"تعديل وحدة القياس: {unit.name}",
        "page_title": f"تعديل وحدة القياس: {unit.name}",
        "page_subtitle": "أدخل التعديلات المطلوبة ثم اضغط حفظ",
        "page_icon": "fas fa-balance-scale",
        "header_buttons": [
            {
                "url": reverse("product:unit_list"),
                "icon": "fa-arrow-right",
                "text": "العودة للقائمة",
                "class": "btn-secondary",
            },
        ],
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": "المنتجات", "url": reverse("product:product_list"), "icon": "fas fa-boxes"},
            {"title": "وحدات القياس", "url": reverse("product:unit_list"), "icon": "fas fa-balance-scale"},
            {"title": f"تعديل: {unit.name}", "active": True},
        ],
    }

    return render(request, "product/unit_form.html", context)


@login_required
def unit_delete(request, pk):
    """
    حذف وحدة قياس
    """
    unit = get_object_or_404(Unit, pk=pk)

    if request.method == "POST":
        name = unit.name
        unit.delete()
        messages.success(request, f'تم حذف وحدة القياس "{name}" بنجاح')
        return redirect("product:unit_list")

    context = {
        "unit": unit,
        "title": f"حذف وحدة القياس: {unit.name}",
    }

    return render(request, "product/unit_confirm_delete.html", context)


@login_required
def unit_detail(request, pk):
    """
    عرض تفاصيل وحدة قياس
    """
    unit = get_object_or_404(Unit, pk=pk)

    # الحصول على المنتجات التي تستخدم هذه الوحدة
    products = Product.objects.filter(unit=unit).select_related("category")

    context = {
        "unit": unit,
        "products": products,
        "title": unit.name,
        "page_title": f"تفاصيل وحدة القياس: {unit.name}",
        "page_subtitle": f"الرمز: {unit.symbol}",
        "page_icon": "fas fa-balance-scale",
        "header_buttons": [
            {
                "url": reverse("product:unit_edit", args=[unit.pk]),
                "icon": "fa-edit",
                "text": "تعديل",
                "class": "btn-warning",
            },
            {
                "url": reverse("product:unit_list"),
                "icon": "fa-arrow-right",
                "text": "العودة للقائمة",
                "class": "btn-secondary",
            },
        ],
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": "المنتجات", "url": reverse("product:product_list"), "icon": "fas fa-boxes"},
            {"title": "وحدات القياس", "url": reverse("product:unit_list"), "icon": "fas fa-balance-scale"},
            {"title": unit.name, "active": True},
        ],
    }

    return render(request, "product/unit_detail.html", context)


@login_required
def warehouse_list(request):
    """
    عرض قائمة المخازن
    """
    warehouses = Warehouse.objects.all().prefetch_related("stocks").annotate(
        product_count=Count("stocks"),
        total_quantity=Sum("stocks__quantity")
    )

    # بحث
    search_query = request.GET.get("search", "")
    if search_query:
        warehouses = warehouses.filter(
            Q(name__icontains=search_query)
            | Q(code__icontains=search_query)
            | Q(location__icontains=search_query)
        )

    # الحالة
    status = request.GET.get("status", "")
    if status == "active":
        warehouses = warehouses.filter(is_active=True)
    elif status == "inactive":
        warehouses = warehouses.filter(is_active=False)

    # إحصائيات
    total_warehouses = Warehouse.objects.count()
    active_warehouses = Warehouse.objects.filter(is_active=True).count()

    # تحويل QuerySet إلى list of dicts للجدول الموحد
    warehouses_data = []
    for w in warehouses:
        warehouses_data.append({
            'id': w.id,
            'code': w.code,
            'name': w.name,
            'location': w.location or '-',
            'manager_name': str(w.manager) if w.manager else '-',
            'product_count': f'<span class="badge bg-info">{w.product_count or 0}</span>',
            'total_quantity': f'<span class="badge bg-secondary">{w.total_quantity or 0}</span>',
            'is_active': w.is_active,
        })

    # تعريف أعمدة جدول المخازن
    warehouse_headers = [
        {
            "key": "code",
            "label": "كود المخزن",
            "sortable": True,
            "class": "text-center",
            "width": "10%",
        },
        {
            "key": "name",
            "label": "اسم المخزن",
            "sortable": True,
            "class": "text-start",
            "width": "25%",
        },
        {
            "key": "location",
            "label": "الموقع",
            "sortable": True,
            "class": "text-center",
            "width": "20%",
        },
        {
            "key": "manager_name",
            "label": "الشخص المسؤول",
            "sortable": True,
            "class": "text-center",
            "width": "20%",
        },
        {
            "key": "product_count",
            "label": "عدد المنتجات",
            "sortable": True,
            "class": "text-center",
            "width": "10%",
            "format": "html",
        },
        {
            "key": "total_quantity",
            "label": "إجمالي الكمية",
            "sortable": True,
            "class": "text-center",
            "width": "10%",
            "format": "html",
        },
        {
            "key": "is_active",
            "label": "الحالة",
            "sortable": True,
            "class": "text-center",
            "template": "components/cells/product_status.html",
            "width": "5%",
        },
    ]

    context = {
        "warehouses": warehouses_data,
        "warehouse_headers": warehouse_headers,
        "primary_key": "id",
        "total_warehouses": total_warehouses,
        "active_warehouses": active_warehouses,
        "page_title": "المخازن",
        "page_subtitle": "إدارة المخازن ومواقع التخزين",
        "page_icon": "fas fa-warehouse",
        "header_buttons": [
            {
                "url": reverse("product:warehouse_create"),
                "icon": "fa-plus",
                "text": "إضافة مخزن",
                "class": "btn-success",
            },
        ],
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {"title": "المخزون", "url": "#", "icon": "fas fa-boxes"},
            {"title": "المخازن", "active": True},
        ],
    }

    return render(request, "product/warehouse_list.html", context)


@login_required
def warehouse_create(request):
    """
    إضافة مخزن جديد
    """
    if request.method == "POST":
        form = WarehouseForm(request.POST)
        if form.is_valid():
            warehouse = form.save()
            messages.success(request, f'تم إضافة المخزن "{warehouse.name}" بنجاح')
            return redirect("product:warehouse_list")
    else:
        form = WarehouseForm()

    context = {
        "form": form,
        "page_title": "إضافة مخزن جديد",
        "page_subtitle": "إضافة مخزن جديد لتخزين المنتجات",
        "page_icon": "fas fa-warehouse",
        "object_type": "مخزن",
        "list_url": reverse("product:warehouse_list"),
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {"title": "المخزون", "url": "#", "icon": "fas fa-boxes"},
            {
                "title": "المخازن",
                "url": reverse("product:warehouse_list"),
                "icon": "fas fa-warehouse",
            },
            {"title": "إضافة مخزن", "active": True},
        ],
    }

    return render(request, "product/warehouse_form.html", context)


@login_required
def warehouse_edit(request, pk):
    """
    تعديل مخزن
    """
    warehouse = get_object_or_404(Warehouse, pk=pk)

    if request.method == "POST":
        form = WarehouseForm(request.POST, instance=warehouse)
        if form.is_valid():
            warehouse = form.save()
            messages.success(request, f'تم تحديث المخزن "{warehouse.name}" بنجاح')
            return redirect("product:warehouse_list")
    else:
        form = WarehouseForm(instance=warehouse)

    context = {
        "form": form,
        "warehouse": warehouse,
        "page_title": f"تعديل المخزن: {warehouse.name}",
        "page_subtitle": "تحديث بيانات المخزن",
        "page_icon": "fas fa-edit",
        "object_type": "مخزن",
        "list_url": reverse("product:warehouse_list"),
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {"title": "المخزون", "url": "#", "icon": "fas fa-boxes"},
            {
                "title": "المخازن",
                "url": reverse("product:warehouse_list"),
                "icon": "fas fa-warehouse",
            },
            {"title": f"تعديل: {warehouse.name}", "active": True},
        ],
    }

    return render(request, "product/warehouse_form.html", context)


@login_required
def warehouse_toggle_active(request, pk):
    """
    تفعيل أو تعطيل مخزن
    """
    if request.method != "POST":
        return redirect("product:warehouse_detail", pk=pk)

    warehouse = get_object_or_404(Warehouse, pk=pk)
    warehouse.is_active = not warehouse.is_active
    warehouse.save()

    if warehouse.is_active:
        messages.success(request, f'تم تفعيل المخزن "{warehouse.name}" بنجاح')
    else:
        messages.warning(request, f'تم تعطيل المخزن "{warehouse.name}" بنجاح')

    return redirect("product:warehouse_detail", pk=pk)


@login_required
def warehouse_detail(request, pk):
    """
    عرض تفاصيل المخزن
    """
    warehouse = get_object_or_404(Warehouse, pk=pk)

    # الأرصدة المتاحة في المخزن
    stocks = Stock.objects.filter(warehouse=warehouse).select_related(
        "product", "product__category", "product__unit"
    )

    # المنتجات المتاحة للإضافة إلى المخزن
    all_products = Product.objects.filter(is_active=True).select_related(
        "category", "unit"
    )

    # المخازن الأخرى للتحويل
    other_warehouses = Warehouse.objects.filter(is_active=True).exclude(pk=warehouse.pk)

    # آخر حركات المخزون في هذا المخزن
    recent_movements = (
        StockMovement.objects.filter(warehouse=warehouse)
        .select_related("product", "warehouse", "destination_warehouse", "created_by")
        .order_by("-timestamp")[:10]
    )

    # إحصائيات المخزون
    total_products = stocks.count()
    in_stock_products = stocks.filter(quantity__gt=0).count()
    low_stock_products = stocks.filter(
        quantity__gt=0, quantity__lt=F("product__min_stock")
    ).count()
    out_of_stock_products = stocks.filter(quantity__lte=0).count()

    # تحويل QuerySet إلى list of dictionaries للجدول الموحد
    stock_data = []
    for stock in stocks:
        # تحديد حالة المخزون
        if stock.quantity <= 0:
            status = "نفذ"
            status_class = "danger"
        elif stock.quantity < stock.product.min_stock:
            status = "منخفض"
            status_class = "warning"
        else:
            status = "متوفر"
            status_class = "success"
        
        stock_data.append({
            'id': stock.id,
            'product.sku': stock.product.sku,
            'product.name': stock.product.name,
            'product.category.name': stock.product.category.name if stock.product.category else '-',
            'quantity': stock.quantity,
            'product.unit.name': stock.product.unit.name if stock.product.unit else '-',
            'status': status,
            'status_class': status_class,
            'updated_at': stock.updated_at,
        })

    # إعداد headers للجدول الموحد
    stock_headers = [
        {"key": "product.sku", "label": "كود المنتج", "sortable": True},
        {"key": "product.name", "label": "اسم المنتج", "sortable": True},
        {"key": "product.category.name", "label": "الفئة", "sortable": True},
        {"key": "quantity", "label": "الكمية", "sortable": True, "class": "text-center"},
        {"key": "product.unit.name", "label": "الوحدة", "sortable": False, "class": "text-center"},
        {"key": "status", "label": "الحالة", "sortable": True, "format": "status"},
        {
            "key": "updated_at",
            "label": "آخر تحديث",
            "sortable": True,
            "format": "datetime",
            "class": "text-center"
        },
    ]

    # إعداد action buttons (معطلة مؤقتاً لأن الروابط غير جاهزة)
    stock_action_buttons = []

    context = {
        "warehouse": warehouse,
        "stocks": stock_data,  # استخدام stock_data بدلاً من stocks QuerySet
        "stock_data": stock_data,  # إضافة للتوافق
        "stock_headers": stock_headers,
        "stock_action_buttons": stock_action_buttons,
        "primary_key": "id",
        "all_products": all_products,
        "other_warehouses": other_warehouses,
        "recent_movements": recent_movements,
        "total_products": total_products,
        "in_stock_products": in_stock_products,
        "low_stock_products": low_stock_products,
        "out_of_stock_products": out_of_stock_products,
        "page_title": warehouse.name,
        "page_subtitle": "إدارة ومتابعة حركة المخزون",
        "page_icon": "fas fa-warehouse",
        "header_buttons": [
            {
                "url": reverse("product:warehouse_edit", args=[warehouse.pk]),
                "icon": "fa-edit",
                "text": "تعديل",
                "class": "btn-primary",
            },
            {
                "onclick": f"toggleWarehouseActive({warehouse.pk}, {'true' if warehouse.is_active else 'false'})",
                "icon": "fa-ban" if warehouse.is_active else "fa-check-circle",
                "text": "تعطيل" if warehouse.is_active else "تفعيل",
                "class": "btn-warning" if warehouse.is_active else "btn-success",
            },
        ],
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {"title": "المخزون", "url": "#", "icon": "fas fa-boxes"},
            {
                "title": "المخازن",
                "url": reverse("product:warehouse_list"),
                "icon": "fas fa-warehouse",
            },
            {"title": warehouse.name, "active": True},
        ],
    }

    return render(request, "product/warehouse_detail.html", context)


@login_required
def stock_list(request):
    """
    عرض قائمة المخزون
    """
    stocks = Stock.objects.all().select_related(
        "product", "product__category", "product__unit", "warehouse"
    )

    # فلترة حسب المخزن
    warehouse_id = request.GET.get("warehouse")
    if warehouse_id:
        stocks = stocks.filter(warehouse_id=warehouse_id)

    # فلترة حسب المنتج
    product_id = request.GET.get("product")
    if product_id:
        stocks = stocks.filter(product_id=product_id)

    # فلترة حسب الكمية
    stock_status = request.GET.get("stock_status")
    if stock_status == "in_stock":
        stocks = stocks.filter(quantity__gt=0)
    elif stock_status == "out_of_stock":
        stocks = stocks.filter(quantity__lte=0)
    elif stock_status == "low_stock":
        stocks = stocks.filter(quantity__gt=0, quantity__lt=F("product__min_stock"))

    # المخازن والمنتجات لعناصر التصفية
    warehouses = Warehouse.objects.filter(is_active=True)
    products = Product.objects.filter(is_active=True).select_related("category")

    # ترقيم الصفحات
    paginator = Paginator(stocks, 20)
    page = request.GET.get("page")
    try:
        stocks = paginator.page(page)
    except PageNotAnInteger:
        stocks = paginator.page(1)
    except EmptyPage:
        stocks = paginator.page(paginator.num_pages)

    # تعريف أعمدة جدول المخزون
    stock_headers = [
        {
            "key": "product.name",
            "label": "المنتج",
            "sortable": True,
            "class": "text-start",
        },
        {
            "key": "product.category.name",
            "label": "الفئة",
            "sortable": True,
            "class": "text-center",
            "template": "components/cells/product_category.html",
            "width": "120px",
        },
        {
            "key": "warehouse.name",
            "label": "المخزن",
            "sortable": True,
            "class": "text-center",
            "width": "120px",
        },
        {
            "key": "quantity",
            "label": "الكمية المتاحة",
            "sortable": True,
            "class": "text-center",
            "template": "components/cells/stock_quantity.html",
            "width": "120px",
        },
        {
            "key": "updated_at",
            "label": "آخر تحديث",
            "sortable": True,
            "class": "text-center",
            "format": "datetime_12h",
            "width": "150px",
        },
    ]

    # أزرار الإجراءات
    stock_actions = [
        {
            "url": "product:stock_detail",
            "icon": "fa-eye",
            "label": "عرض",
            "class": "action-view",
        },
    ]

    context = {
        "stocks": stocks,
        "stock_headers": stock_headers,
        "stock_actions": stock_actions,
        "primary_key": "id",
        "warehouses": warehouses,
        "products": products,
        "warehouse_id": warehouse_id,
        "product_id": product_id,
        "stock_status": stock_status,
        "page_title": "جرد المخزون",
        "page_subtitle": "مراقبة المخزون وإدارة الكميات المتاحة من المنتجات",
        "page_icon": "fas fa-clipboard-list",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {"title": "المخزون", "url": "#", "icon": "fas fa-boxes"},
            {"title": "جرد المخزون", "active": True},
        ],
    }

    return render(request, "product/stock_list.html", context)


@login_required
def stock_detail(request, pk):
    """
    عرض تفاصيل المخزون
    """
    try:
        stock = get_object_or_404(Stock, pk=pk)

        # حركات المخزون مرتبة من الأقدم للأحدث لحساب الرصيد
        # تحديد عدد الحركات لتجنب مشاكل الأداء
        movements = StockMovement.objects.filter(
            product=stock.product, warehouse=stock.warehouse
        ).select_related('created_by').order_by("timestamp")[:500]  # آخر 500 حركة
        
        # حساب الرصيد قبل وبعد كل حركة
        current_balance = Decimal('0')
        movements_list = []
        
        for movement in movements:
            movement.quantity_before = current_balance
            
            # تحديث الرصيد حسب نوع الحركة
            if movement.movement_type in ['in', 'transfer_in', 'return_in']:
                current_balance += Decimal(str(movement.quantity))
            elif movement.movement_type in ['out', 'transfer_out', 'return_out']:
                current_balance -= Decimal(str(movement.quantity))
            elif movement.movement_type == 'adjustment':
                # التعديل يضبط الرصيد مباشرة
                current_balance = Decimal(str(movement.quantity))
            
            movement.quantity_after = current_balance
            movements_list.append(movement)
        
        # عكس الترتيب لعرض الأحدث أولاً
        movements_list.reverse()

        context = {
            "stock": stock,
            "movements": movements_list,
            "title": stock.product.name,
            "page_title": stock.product.name,
            "page_subtitle": f"المخزن: {stock.warehouse.name}",
            "page_icon": "fas fa-box",
            "header_buttons": [
                {
                    "url": reverse("product:stock_adjust", args=[stock.pk]),
                    "icon": "fa-balance-scale",
                    "text": "تسوية المخزون",
                    "class": "btn-primary",
                },
                {
                    "url": reverse("product:stock_list"),
                    "icon": "fa-arrow-right",
                    "text": "قائمة المخزون",
                    "class": "btn-outline-secondary",
                },
            ],
            "breadcrumb_items": [
                {
                    "title": "الرئيسية",
                    "url": reverse("core:dashboard"),
                    "icon": "fas fa-home",
                },
                {"title": "المخزون", "url": "#", "icon": "fas fa-boxes"},
                {
                    "title": "قائمة المخزون",
                    "url": reverse("product:stock_list"),
                    "icon": "fas fa-list",
                },
                {"title": stock.product.name, "active": True},
            ],
        }

        return render(request, "product/stock_detail.html", context)
        
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in stock_detail view for stock {pk}: {str(e)}")
        messages.error(request, f"حدث خطأ في عرض تفاصيل المخزون")
        return redirect('product:stock_list')


@login_required
def stock_adjust(request, pk):
    """
    تسوية المخزون
    """
    try:
        stock = get_object_or_404(Stock, pk=pk)

        if request.method == "POST":
            try:
                new_quantity = Decimal(request.POST.get("quantity", 0))
                notes = request.POST.get("notes", "")
                
                # التحقق من صحة الكمية
                if new_quantity < 0:
                    messages.error(request, "الكمية يجب أن تكون صفر أو أكثر")
                    return redirect("product:stock_adjust", pk=pk)
                
                # حفظ الكمية القديمة
                old_quantity = stock.quantity

                # إنشاء حركة تسوية
                movement = StockMovement.objects.create(
                    product=stock.product,
                    warehouse=stock.warehouse,
                    movement_type="adjustment",
                    quantity=new_quantity,
                    quantity_before=old_quantity,
                    quantity_after=new_quantity,
                    notes=notes,
                    created_by=request.user,
                )

                # تحديث المخزون
                stock.quantity = new_quantity
                stock.save()

                messages.success(request, "تم تسوية المخزون بنجاح")
                return redirect("product:stock_detail", pk=stock.pk)
                
            except ValueError as e:
                logger = logging.getLogger(__name__)
                logger.error(f"Invalid quantity in stock_adjust for stock {pk}: {str(e)}")
                messages.error(request, "الكمية المدخلة غير صحيحة")
                return redirect("product:stock_adjust", pk=pk)
                
            except Exception as e:
                logger = logging.getLogger(__name__)
                logger.error(f"Error creating stock adjustment for stock {pk}: {str(e)}")
                messages.error(request, "حدث خطأ أثناء تسوية المخزون. يرجى المحاولة مرة أخرى")
                return redirect("product:stock_adjust", pk=pk)

        context = {
            "stock": stock,
            "title": f"تسوية المخزون: {stock.product.name}",
            "page_title": "تسوية المخزون",
            "page_subtitle": f"{stock.product.name} - {stock.warehouse.name}",
            "page_icon": "fas fa-balance-scale",
            "header_buttons": [
                {
                    "url": reverse("product:stock_detail", args=[stock.pk]),
                    "icon": "fa-arrow-right",
                    "text": "العودة للتفاصيل",
                    "class": "btn-outline-secondary",
                },
            ],
            "breadcrumb_items": [
                {
                    "title": "الرئيسية",
                    "url": reverse("core:dashboard"),
                    "icon": "fas fa-home",
                },
                {"title": "المخزون", "url": "#", "icon": "fas fa-boxes"},
                {
                    "title": "قائمة المخزون",
                    "url": reverse("product:stock_list"),
                    "icon": "fas fa-list",
                },
                {
                    "title": stock.product.name,
                    "url": reverse("product:stock_detail", args=[stock.pk]),
                    "icon": "fas fa-box",
                },
                {"title": "تسوية المخزون", "active": True},
            ],
        }

        return render(request, "product/stock_adjust.html", context)
        
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in stock_adjust view for stock {pk}: {str(e)}")
        messages.error(request, "حدث خطأ في الوصول لصفحة التسوية")
        return redirect("product:stock_list")


@login_required
def stock_movement_list(request):
    """
    عرض قائمة حركات المخزون
    يعرض جميع الحركات من:
    1. InventoryMovement (الأذون المعتمدة)
    2. StockMovement (المشتريات والمبيعات والحركات الأخرى)
    """
    from product.models.inventory_movement import InventoryMovement
    from django.db.models import Q, Value, CharField, F
    from itertools import chain
    
    # الحصول على حركات StockMovement (المشتريات والمبيعات)
    stock_movements = (
        StockMovement.objects.all()
        .select_related("product", "warehouse", "destination_warehouse", "created_by")
        .annotate(
            source_type=Value('stock_movement', output_field=CharField()),
            movement_number_display=Value('', output_field=CharField()),
            voucher_type_display=Value('none', output_field=CharField()),
        )
        .order_by("-timestamp")
    )
    
    # الحصول على الأذون المعتمدة من InventoryMovement
    inventory_movements = (
        InventoryMovement.objects.filter(is_approved=True)
        .select_related("product", "warehouse", "created_by", "approved_by")
        .annotate(
            source_type=Value('inventory_movement', output_field=CharField()),
            movement_number_display=F('movement_number'),
            voucher_type_display=F('voucher_type'),
        )
        .order_by("-movement_date")
    )

    # تصفية حسب البحث
    search_query = request.GET.get("search", "")
    if search_query:
        stock_movements = stock_movements.filter(
            Q(reference_number__icontains=search_query)
            | Q(product__name__icontains=search_query)
        )
        inventory_movements = inventory_movements.filter(
            Q(movement_number__icontains=search_query)
            | Q(product__name__icontains=search_query)
            | Q(party_name__icontains=search_query)
        )

    # تصفية حسب المخزن
    warehouse_id = request.GET.get("warehouse")
    if warehouse_id:
        stock_movements = stock_movements.filter(
            Q(warehouse_id=warehouse_id) | Q(destination_warehouse_id=warehouse_id)
        )
        inventory_movements = inventory_movements.filter(warehouse_id=warehouse_id)

    # تصفية حسب المنتج
    product_id = request.GET.get("product")
    if product_id:
        stock_movements = stock_movements.filter(product_id=product_id)
        inventory_movements = inventory_movements.filter(product_id=product_id)

    # تصفية حسب نوع الحركة
    movement_type = request.GET.get("movement_type")
    if movement_type:
        stock_movements = stock_movements.filter(movement_type=movement_type)
        inventory_movements = inventory_movements.filter(movement_type=movement_type)
    
    # تصفية حسب نوع الإذن
    voucher_type = request.GET.get("voucher_type")
    if voucher_type:
        if voucher_type == 'none':
            # عرض StockMovement فقط (المشتريات والمبيعات)
            inventory_movements = inventory_movements.none()
        else:
            # عرض InventoryMovement فقط (الأذون)
            stock_movements = stock_movements.none()
            inventory_movements = inventory_movements.filter(voucher_type=voucher_type)

    # تصفية حسب التاريخ
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")
    if date_from:
        stock_movements = stock_movements.filter(timestamp__date__gte=date_from)
        inventory_movements = inventory_movements.filter(movement_date__date__gte=date_from)
    if date_to:
        stock_movements = stock_movements.filter(timestamp__date__lte=date_to)
        inventory_movements = inventory_movements.filter(movement_date__date__lte=date_to)
    
    # دمج القوائم وترتيبها حسب التاريخ
    # تحويل QuerySets إلى قوائم
    stock_list = list(stock_movements)
    inventory_list = list(inventory_movements)
    
    # دمج القوائم
    all_movements = stock_list + inventory_list
    
    # ترتيب حسب التاريخ (الأقدم أولاً للحساب الصحيح)
    all_movements.sort(
        key=lambda x: x.timestamp if hasattr(x, 'timestamp') else x.movement_date,
        reverse=False  # الأقدم أولاً
    )
    
    # حساب الرصيد بعد كل حركة بشكل تراكمي
    from product.models.stock_management import Stock
    from collections import defaultdict
    
    # تتبع الرصيد لكل منتج في كل مخزن
    stock_tracker = defaultdict(lambda: defaultdict(int))
    
    # تهيئة الرصيد الحالي لكل منتج/مخزن
    for movement in all_movements:
        key = (movement.product.id, movement.warehouse.id)
        if key not in stock_tracker or stock_tracker[key] == 0:
            try:
                stock = Stock.objects.get(product=movement.product, warehouse=movement.warehouse)
                stock_tracker[key] = stock.quantity
            except Stock.DoesNotExist:
                stock_tracker[key] = 0
    
    # حساب الرصيد بعد كل حركة بالعكس (من الأحدث للأقدم)
    # نبدأ من الرصيد الحالي ونطرح/نضيف عكسياً
    for movement in reversed(all_movements):
        key = (movement.product.id, movement.warehouse.id)
        current_balance = stock_tracker[key]
        
        # إذا كان quantity_after موجود ومش صفر، نستخدمه
        if hasattr(movement, 'quantity_after') and movement.quantity_after is not None and movement.quantity_after > 0:
            # نستخدم القيمة الموجودة
            stock_tracker[key] = movement.quantity_before if hasattr(movement, 'quantity_before') else current_balance
        else:
            # نحسب الرصيد قبل الحركة
            if movement.movement_type in ["in", "transfer_in", "adjustment_in", "return_in", "found"]:
                # كانت حركة وارد، يبقى الرصيد قبلها = الرصيد الحالي - الكمية
                movement.quantity_after = current_balance
                stock_tracker[key] = current_balance - movement.quantity
            elif movement.movement_type in ["out", "transfer_out", "adjustment_out", "return_out", "damaged", "expired", "lost"]:
                # كانت حركة صادر، يبقى الرصيد قبلها = الرصيد الحالي + الكمية
                movement.quantity_after = current_balance
                stock_tracker[key] = current_balance + movement.quantity
            else:
                movement.quantity_after = current_balance
        
        # حساب الفرق للتسوية (adjustment)
        if movement.movement_type == 'adjustment':
            if hasattr(movement, 'quantity_before') and hasattr(movement, 'quantity_after'):
                movement.adjustment_diff = movement.quantity_after - movement.quantity_before
            else:
                movement.adjustment_diff = 0
    
    # ترتيب حسب التاريخ (الأحدث أولاً للعرض)
    all_movements.sort(
        key=lambda x: x.timestamp if hasattr(x, 'timestamp') else x.movement_date,
        reverse=True
    )
    
    # حساب الإحصائيات من القوائم المدمجة
    total_movements = len(all_movements)
    total_quantity = sum(m.quantity for m in all_movements)
    
    # عدد الحركات حسب النوع
    in_movements = sum(1 for m in all_movements if m.movement_type in ["in", "transfer_in", "adjustment_in", "return_in", "found"])
    out_movements = sum(1 for m in all_movements if m.movement_type in ["out", "transfer_out", "adjustment_out", "return_out", "damaged", "expired", "lost"])
    
    # عدد الأذون
    receipt_vouchers = sum(1 for m in all_movements if hasattr(m, 'voucher_type') and m.voucher_type == "receipt")
    issue_vouchers = sum(1 for m in all_movements if hasattr(m, 'voucher_type') and m.voucher_type == "issue")
    
    # Pagination
    from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
    paginator = Paginator(all_movements, 30)
    page = request.GET.get("page")
    try:
        movements = paginator.page(page)
    except PageNotAnInteger:
        movements = paginator.page(1)
    except EmptyPage:
        movements = paginator.page(paginator.num_pages)

    # إحصائيات (تم حسابها أعلاه من القوائم المدمجة)

    # كل المخازن والمنتجات لقائمة الاختيار
    warehouses = Warehouse.objects.filter(is_active=True)
    products = Product.objects.filter(is_active=True).select_related("category")

    context = {
        "active_menu": "product",
        "title": "حركات المخزون",
        "movements": movements,
        "warehouses": warehouses,
        "products": products,
        "total_movements": total_movements,
        "total_quantity": total_quantity,
        "in_movements": in_movements,
        "out_movements": out_movements,
        "receipt_vouchers": receipt_vouchers,
        "issue_vouchers": issue_vouchers,
        "page_title": "حركات المخزون",
        "page_subtitle": "جميع حركات المخزون من الأذون والمشتريات والمبيعات",
        "page_icon": "fas fa-exchange-alt",
        "header_buttons": [
            {
                "url": reverse("product:receipt_voucher_list"),
                "icon": "fa-file-import",
                "text": "أذون الاستلام",
                "class": "btn-success",
            },
            {
                "url": reverse("product:issue_voucher_list"),
                "icon": "fa-file-export",
                "text": "أذون الصرف",
                "class": "btn-danger",
            },
        ],
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {"title": "المخزون", "url": "#", "icon": "fas fa-boxes"},
            {"title": "حركات المخزون", "active": True},
        ],
    }

    return render(request, "product/stock_movement_list.html", context)


@login_required
def stock_movement_create(request):
    """
    إضافة حركة مخزون جديدة
    """
    if request.method == "POST":
        form = StockMovementForm(request.POST)
        if form.is_valid():
            movement = form.save(commit=False)
            movement.created_by = request.user
            # تعيين نوع المستند للحركات اليدوية
            movement.document_type = "other"
            movement.save()

            messages.success(request, f"تم إضافة حركة المخزون بنجاح")
            return redirect("product:stock_movement_list")
    else:
        form = StockMovementForm()

    context = {
        "form": form,
        "title": "إضافة حركة مخزون جديدة",
    }

    return render(request, "product/stock_movement_form.html", context)


@login_required
def stock_movement_detail(request, pk):
    """
    عرض تفاصيل حركة المخزون
    """
    movement = get_object_or_404(
        StockMovement.objects.select_related(
            "product",
            "product__category",
            "product__unit",
            "warehouse",
            "destination_warehouse",
            "created_by",
        ),
        pk=pk,
    )

    # حساب المخزون قبل وبعد الحركة
    if movement.movement_type in ["in", "transfer_in"]:
        previous_stock = movement.quantity_before
        current_stock = movement.quantity_after
    elif movement.movement_type in ["out", "transfer_out"]:
        previous_stock = movement.quantity_before
        current_stock = movement.quantity_after
    else:  # adjustment
        previous_stock = movement.quantity_before
        current_stock = movement.quantity_after

    # حركات متعلقة بنفس المنتج في نفس المخزن
    related_movements = (
        StockMovement.objects.filter(
            product=movement.product, warehouse=movement.warehouse
        )
        .select_related("product", "warehouse", "destination_warehouse", "created_by")
        .order_by("-timestamp")[:10]
    )

    context = {
        "movement": movement,
        "previous_stock": previous_stock,
        "current_stock": current_stock,
        "related_movements": related_movements,
        "page_title": f"تفاصيل حركة المخزون #{movement.reference_number or movement.id}",
        "page_subtitle": f"{movement.product.name} | {movement.timestamp.strftime('%d-%m-%Y %H:%M')}",
        "page_icon": "fas fa-exchange-alt",
        "header_buttons": [
            {
                "onclick": "window.print()",
                "icon": "fa-print",
                "text": "طباعة",
                "class": "btn-outline-secondary",
            },
        ] if not movement.document_type or movement.document_type == 'adjustment' else [
            {
                "url": reverse("product:stock_movement_delete", kwargs={"pk": movement.pk}),
                "icon": "fa-trash",
                "text": "حذف",
                "class": "btn-danger",
            },
            {
                "onclick": "window.print()",
                "icon": "fa-print",
                "text": "طباعة",
                "class": "btn-outline-secondary",
            },
        ],
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "حركات المخزون",
                "url": reverse("product:stock_movement_list"),
                "icon": "fas fa-exchange-alt",
            },
            {"title": f"تفاصيل الحركة #{movement.reference_number or movement.id}", "active": True},
        ],
    }

    return render(request, "product/stock_movement_detail.html", context)


@login_required
def stock_movement_delete(request, pk):
    """
    حذف حركة مخزون
    """
    movement = get_object_or_404(StockMovement, pk=pk)

    # جمع معلومات العناصر المرتبطة بهذه الحركة
    related_objects = {}

    if request.method == "POST":
        # استرجاع معلومات المخزن والمنتج قبل الحذف
        warehouse = movement.warehouse
        product = movement.product

        # الغاء تأثير حركة المخزون
        if movement.movement_type == "in":
            # إذا كانت حركة إضافة، نقوم بخصم الكمية
            stock = Stock.objects.get(warehouse=warehouse, product=product)
            stock.quantity -= Decimal(movement.quantity)
            stock.save()
        elif movement.movement_type == "out":
            # إذا كانت حركة سحب، نقوم بإضافة الكمية
            stock = Stock.objects.get(warehouse=warehouse, product=product)
            stock.quantity += Decimal(movement.quantity)
            stock.save()
        elif movement.movement_type == "transfer" and movement.destination_warehouse:
            # إذا كانت حركة تحويل، نقوم بعكس التحويل
            source_stock = Stock.objects.get(warehouse=warehouse, product=product)
            dest_stock = Stock.objects.get(
                warehouse=movement.destination_warehouse, product=product
            )

            source_stock.quantity += Decimal(movement.quantity)
            dest_stock.quantity -= Decimal(movement.quantity)

            source_stock.save()
            dest_stock.save()

        # حذف حركة المخزون
        movement.delete()

        messages.success(request, _("تم حذف حركة المخزون بنجاح"))
        return redirect("product:stock_movement_list")

    context = {
        "object": movement,
        "related_objects": related_objects,
        "back_url": reverse("product:stock_movement_list"),
        "title": _("حذف حركة المخزون"),
    }

    return render(request, "product/stock_movement_confirm_delete.html", context)


@login_required
@require_POST
def add_stock_movement(request):
    """
    واجهة برمجة لإضافة حركة مخزون (إضافة/سحب/تعديل/تحويل)

    معلمات الطلب:
    - product_id: معرف المنتج
    - warehouse_id: معرف المخزن
    - movement_type: نوع الحركة (in, out, adjustment, transfer)
    - quantity: الكمية
    - destination_warehouse: معرف المخزن المستلم (للتحويل فقط)
    - reference_number: رقم المرجع (اختياري)
    - notes: ملاحظات (اختياري)

    الاستجابة:
    - success: حالة النجاح (true/false)
    - message: رسالة نجاح أو خطأ
    - movement_id: معرف حركة المخزون الجديدة (في حالة النجاح)
    - current_stock: المخزون الحالي بعد التحديث (في حالة النجاح)
    """
    try:
        # التحقق من وجود المعلمات الأساسية
        product_id = request.POST.get("product_id") or request.POST.get("product")
        warehouse_id = request.POST.get("warehouse_id")
        movement_type = request.POST.get("movement_type")
        quantity = request.POST.get("quantity")

        # التحقق من وجود جميع المعلمات المطلوبة
        if not all([product_id, warehouse_id, movement_type, quantity]):
            return JsonResponse(
                {
                    "success": False,
                    "error": _(
                        "جميع الحقول مطلوبة: product_id, warehouse_id, movement_type, quantity"
                    ),
                }
            )

        # التحقق من صحة البيانات
        try:
            product = Product.objects.get(pk=product_id)
        except Product.DoesNotExist:
            return JsonResponse({"success": False, "error": _("المنتج غير موجود")})

        try:
            warehouse = Warehouse.objects.get(pk=warehouse_id)
        except Warehouse.DoesNotExist:
            return JsonResponse({"success": False, "error": _("المخزن غير موجود")})

        # التحقق من صحة الكمية
        try:
            quantity = Decimal(quantity)
            if quantity <= 0:
                return JsonResponse(
                    {"success": False, "error": _("يجب أن تكون الكمية أكبر من صفر")}
                )
        except ValueError:
            return JsonResponse(
                {"success": False, "error": _("الكمية يجب أن تكون رقمًا صحيحًا")}
            )

        # التحقق من نوع الحركة
        if movement_type not in ["in", "out", "adjustment", "transfer"]:
            return JsonResponse(
                {
                    "success": False,
                    "error": _(
                        "نوع الحركة غير صحيح. القيم المقبولة: in, out, adjustment, transfer"
                    ),
                }
            )

        # الحصول على المخزون الحالي أو إنشاء سجل جديد
        stock, created = Stock.objects.get_or_create(
            product=product, warehouse=warehouse, defaults={"quantity": 0}
        )

        # حفظ المخزون الحالي قبل التعديل
        current_stock = stock.quantity

        # تنفيذ عملية المخزون
        if movement_type == "in":
            # إضافة مخزون
            stock.quantity += Decimal(quantity)
            message = _("تمت إضافة {} وحدة من {} إلى المخزون").format(
                quantity, product.name
            )

        elif movement_type == "out":
            # سحب مخزون
            if stock.quantity < Decimal(quantity):
                return JsonResponse(
                    {
                        "success": False,
                        "error": _(
                            "الكمية غير كافية في المخزون. المتاح حالياً: {}"
                        ).format(stock.quantity),
                    }
                )

            stock.quantity -= Decimal(quantity)
            message = _("تم سحب {} وحدة من {} من المخزون").format(
                quantity, product.name
            )

        elif movement_type == "adjustment":
            # تعديل المخزون (تعيين قيمة محددة)
            old_quantity = stock.quantity
            stock.quantity = Decimal(quantity)
            message = _("تم تعديل مخزون {} من {} إلى {}").format(
                product.name, old_quantity, quantity
            )

        elif movement_type == "transfer":
            # تحويل مخزون بين المخازن
            destination_warehouse_id = request.POST.get("destination_warehouse")

            if not destination_warehouse_id:
                return JsonResponse(
                    {"success": False, "error": _("يجب تحديد المخزن المستلم للتحويل")}
                )

            if destination_warehouse_id == warehouse_id:
                return JsonResponse(
                    {"success": False, "error": _("لا يمكن التحويل إلى نفس المخزن")}
                )

            try:
                destination_warehouse = Warehouse.objects.get(
                    pk=destination_warehouse_id
                )
            except Warehouse.DoesNotExist:
                return JsonResponse(
                    {"success": False, "error": _("المخزن المستلم غير موجود")}
                )

            # التحقق من كفاية المخزون
            if stock.quantity < Decimal(quantity):
                return JsonResponse(
                    {
                        "success": False,
                        "error": _(
                            "الكمية غير كافية للتحويل. المتاح حالياً: {}"
                        ).format(stock.quantity),
                    }
                )

            # خصم من المخزن المصدر
            stock.quantity -= Decimal(quantity)

            # إضافة إلى المخزن المستلم
            dest_stock, created = Stock.objects.get_or_create(
                product=product,
                warehouse=destination_warehouse,
                defaults={"quantity": Decimal("0")},
            )

            dest_before = dest_stock.quantity
            dest_stock.quantity += Decimal(quantity)
            dest_stock.save()

            message = _("تم تحويل {} وحدة من {} من {} إلى {}").format(
                quantity, product.name, warehouse.name, destination_warehouse.name
            )

        # حفظ التغييرات
        stock.save()

        # إنشاء سجل حركة المخزون
        movement = StockMovement.objects.create(
            product=product,
            warehouse=warehouse,
            movement_type=movement_type,
            quantity=quantity,
            quantity_before=current_stock,
            quantity_after=stock.quantity,
            reference_number=request.POST.get("reference_number", ""),
            notes=request.POST.get("notes", ""),
            created_by=request.user,
        )

        # إذا كانت حركة تحويل، حفظ المخزن المستلم
        if movement_type == "transfer" and "destination_warehouse" in locals():
            movement.destination_warehouse = destination_warehouse
            movement.save()

            # إنشاء سجل حركة للمخزن المستلم
            StockMovement.objects.create(
                product=product,
                warehouse=destination_warehouse,
                movement_type="transfer_in",
                quantity=quantity,
                quantity_before=dest_before,
                quantity_after=dest_stock.quantity,
                reference_number=request.POST.get("reference_number", ""),
                notes=_("تحويل من مخزن {}").format(warehouse.name),
                created_by=request.user,
            )

        # تسجيل الحركة في سجل النظام

        return JsonResponse(
            {
                "success": True,
                "message": message,
                "movement_id": movement.id,
                "current_stock": stock.quantity,
            }
        )

    except ValidationError as e:
        logger.warning("Validation error in add_stock_movement: %s", str(e))
        return JsonResponse({"success": False, "error": "خطأ في العملية"})
    except Exception as e:
        # سجل الخطأ ولكن لا ترسل تفاصيل للمستخدم
        logger.error("Error in add_stock_movement: %s", str(e), exc_info=True)
        return JsonResponse(
            {
                "success": False,
                "error": _(
                    "حدث خطأ أثناء تنفيذ العملية. يرجى المحاولة مرة أخرى لاحقًا."
                ),
            }
        )


@login_required
def export_stock_movements(request):
    """
    تصدير حركات المخزون كملف CSV
    """
    # الحصول على الحركات مع تطبيق الفلاتر
    movements = (
        StockMovement.objects.all()
        .select_related(
            "product",
            "product__category",
            "warehouse",
            "destination_warehouse",
            "created_by",
        )
        .order_by("-timestamp")
    )

    # تطبيق الفلاتر
    warehouse_id = request.GET.get("warehouse")
    if warehouse_id:
        movements = movements.filter(
            Q(warehouse_id=warehouse_id) | Q(destination_warehouse_id=warehouse_id)
        )

    product_id = request.GET.get("product")
    if product_id:
        movements = movements.filter(product_id=product_id)

    movement_type = request.GET.get("movement_type")
    if movement_type:
        movements = movements.filter(movement_type=movement_type)

    date_from = request.GET.get("date_from")
    if date_from:
        movements = movements.filter(timestamp__date__gte=date_from)

    date_to = request.GET.get("date_to")
    if date_to:
        movements = movements.filter(timestamp__date__lte=date_to)

    # تصدير CSV
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="stock_movements.csv"'

    writer = csv.writer(response)
    writer.writerow(
        [
            "ID",
            "المنتج",
            "المخزن",
            "النوع",
            "الكمية",
            "المخزون قبل",
            "المخزون بعد",
            "المخزن المستلم",
            "رقم المرجع",
            "ملاحظات",
            "التاريخ",
        ]
    )

    for movement in movements:
        writer.writerow(
            [
                movement.id,
                movement.product.name,
                movement.warehouse.name,
                movement.get_movement_type_display(),
                movement.quantity,
                movement.quantity_before,
                movement.quantity_after,
                movement.destination_warehouse.name
                if movement.destination_warehouse
                else "",
                movement.reference_number,
                movement.notes,
                movement.timestamp.strftime("%Y-%m-%d %H:%M"),
            ]
        )

    return response


@login_required
def export_warehouse_inventory_all(request):
    """
    تصدير المخزون من جميع المخازن أو حسب التصفية
    """
    # جلب المخزون
    stocks = Stock.objects.all().select_related(
        "product", "product__category", "warehouse"
    )

    # التصفية حسب المخزن إذا تم تحديده
    warehouse_id = request.GET.get("warehouse")
    if warehouse_id and warehouse_id.isdigit():
        stocks = stocks.filter(warehouse_id=warehouse_id)

    # التصفية حسب المنتج إذا تم تحديده
    product_id = request.GET.get("product")
    if product_id and product_id.isdigit():
        stocks = stocks.filter(product_id=product_id)

    # التصفية حسب الكمية
    min_quantity = request.GET.get("min_quantity")
    if min_quantity and min_quantity.isdigit():
        stocks = stocks.filter(quantity__gte=min_quantity)

    max_quantity = request.GET.get("max_quantity")
    if max_quantity and max_quantity.isdigit():
        stocks = stocks.filter(quantity__lte=max_quantity)

    # تحديد نوع التصدير
    export_format = request.GET.get("format", "csv")

    if export_format == "csv":
        # تصدير CSV
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="inventory.csv"'

        writer = csv.writer(response)
        writer.writerow(
            [
                "رقم المنتج",
                "اسم المنتج",
                "كود المنتج",
                "المخزن",
                "التصنيف",
                "الكمية",
                "الحد الأدنى",
                "الحد الأقصى",
                "حالة المخزون",
            ]
        )

        for stock in stocks:
            # تحديد حالة المخزون
            if stock.quantity <= 0:
                status = "نفذ من المخزون"
            elif stock.quantity < stock.product.min_stock:
                status = "مخزون منخفض"
            elif stock.quantity > stock.product.max_stock:
                status = "مخزون زائد"
            else:
                status = "مخزون جيد"

            writer.writerow(
                [
                    stock.product.id,
                    stock.product.name,
                    stock.product.sku,
                    stock.warehouse.name,
                    stock.product.category.name if stock.product.category else "",
                    stock.quantity,
                    stock.product.min_stock,
                    stock.product.max_stock,
                    status,
                ]
            )

        return response

    # يمكن إضافة تصدير PDF هنا لاحقاً
    return redirect("product:stock_list")


@login_required
def export_warehouse_inventory(request, warehouse_id=None):
    """
    تصدير مخزون مخزن معين
    """
    # إذا لم يتم تحديد رقم المخزن، نحاول جلبه من الاستعلام
    if warehouse_id is None:
        warehouse_id = request.GET.get("warehouse")
        if not warehouse_id or not warehouse_id.isdigit():
            # إذا لم يتم تحديد مخزن، نستخدم دالة تصدير كل المخزون
            return export_warehouse_inventory_all(request)

    warehouse = get_object_or_404(Warehouse, pk=warehouse_id)
    stocks = Stock.objects.filter(warehouse=warehouse).select_related("product")

    # التصفية حسب المنتج إذا تم تحديده
    product_id = request.GET.get("product")
    if product_id and product_id.isdigit():
        stocks = stocks.filter(product_id=product_id)

    # تصدير CSV
    response = HttpResponse(content_type="text/csv")
    response[
        "Content-Disposition"
    ] = f'attachment; filename="{warehouse.name}_inventory.csv"'

    writer = csv.writer(response)
    writer.writerow(
        [
            "رقم المنتج",
            "اسم المنتج",
            "كود المنتج",
            "التصنيف",
            "الكمية",
            "الحد الأدنى",
            "الحد الأقصى",
            "حالة المخزون",
        ]
    )

    for stock in stocks:
        # تحديد حالة المخزون
        if stock.quantity <= 0:
            status = "نفذ من المخزون"
        elif stock.quantity < stock.product.min_stock:
            status = "مخزون منخفض"
        elif stock.quantity > stock.product.max_stock:
            status = "مخزون زائد"
        else:
            status = "مخزون جيد"

        writer.writerow(
            [
                stock.product.id,
                stock.product.name,
                stock.product.sku,
                stock.product.category.name if stock.product.category else "",
                stock.quantity,
                stock.product.min_stock,
                stock.product.max_stock,
                status,
            ]
        )

    return response


@login_required
def low_stock_products(request):
    """
    عرض المنتجات ذات المخزون المنخفض
    """
    # الحصول على المنتجات ذات المخزون المنخفض
    low_stock_items = Stock.objects.filter(
        quantity__gt=0, quantity__lt=F("product__min_stock")
    ).select_related(
        "product", "product__category", "product__unit", "warehouse"
    )

    context = {
        "low_stock_items": low_stock_items,
        "title": _("المنتجات ذات المخزون المنخفض"),
    }

    return render(request, "product/low_stock.html", context)


@login_required
def add_product_image(request):
    """
    إضافة صورة منتج من خلال AJAX
    """
    if request.method == "POST":
        try:
            product_id = request.POST.get("product_id")
            image = request.FILES.get("image")
            alt_text = request.POST.get("alt_text", "")
            is_primary = request.POST.get("is_primary") == "on"

            if not product_id or not image:
                return JsonResponse({"success": False, "error": _("بيانات غير كاملة")})

            # التأكد من وجود المنتج
            product = get_object_or_404(Product, pk=product_id)

            # إذا كانت الصورة الأساسية، نقوم بإلغاء تحديد الصور الأساسية الأخرى
            if is_primary:
                ProductImage.objects.filter(product=product, is_primary=True).update(
                    is_primary=False
                )

            # إنشاء صورة جديدة
            product_image = ProductImage.objects.create(
                product=product, image=image, alt_text=alt_text, is_primary=is_primary
            )

            return JsonResponse(
                {
                    "success": True,
                    "id": product_image.id,
                    "url": product_image.image.url,
                }
            )

        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Error in add_product_image: {str(e)}", exc_info=True)
            return JsonResponse({"success": False, "error": _("حدث خطأ أثناء إضافة الصورة")})

    return JsonResponse({"success": False, "error": _("طريقة طلب غير صحيحة")})


@login_required
def export_products_pdf_weasy(request, products):
    """
    تصدير قائمة المنتجات إلى PDF باستخدام ReportLab (محسّن للعربي)
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch, cm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.lib.enums import TA_CENTER, TA_RIGHT
        from django.utils import timezone
        from io import BytesIO
        import os
        
        # الحصول على التوقيت المحلي
        from utils.helpers import get_system_timezone
        local_tz = get_system_timezone()
        now_local = timezone.now().astimezone(local_tz)
        
        # إنشاء buffer للـ PDF
        buffer = BytesIO()
        
        # إنشاء المستند
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=0.5*cm,
            leftMargin=0.5*cm,
            topMargin=1*cm,
            bottomMargin=1.5*cm
        )
        
        # تسجيل الخطوط العربية
        font_dir = os.path.join(settings.BASE_DIR, 'static', 'fonts')
        tajawal_regular = os.path.join(font_dir, 'Tajawal-Regular.ttf')
        tajawal_bold = os.path.join(font_dir, 'Tajawal-Bold.ttf')
        
        try:
            if os.path.exists(tajawal_regular):
                pdfmetrics.registerFont(TTFont('Tajawal', tajawal_regular))
            if os.path.exists(tajawal_bold):
                pdfmetrics.registerFont(TTFont('Tajawal-Bold', tajawal_bold))
            font_name = 'Tajawal'
        except:
            font_name = 'Helvetica'  # Fallback font
        
        # إعداد الأنماط
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontName=font_name,
            fontSize=18,
            alignment=TA_CENTER,
            spaceAfter=15,
            textColor=colors.HexColor('#344767')
        )
        
        info_style = ParagraphStyle(
            'InfoStyle',
            parent=styles['Normal'],
            fontName=font_name,
            fontSize=9,
            alignment=TA_RIGHT,
            textColor=colors.HexColor('#6c757d')
        )
        
        # بناء محتوى الـ PDF
        story = []
        
        # إضافة العنوان
        story.append(Paragraph('قائمة المنتجات', title_style))
        story.append(Spacer(1, 0.2*inch))
        
        # إضافة معلومات التقرير
        currency = SystemSetting.get_currency_symbol()
        info_text = f'تاريخ الطباعة: {now_local.strftime("%d/%m/%Y - %H:%M")} | إجمالي المنتجات: {products.count()} منتج'
        story.append(Paragraph(info_text, info_style))
        story.append(Spacer(1, 0.1*inch))
        
        # إضافة الفلاتر المطبقة (إن وجدت)
        filters_applied = []
        
        if request.GET.get('name'):
            filters_applied.append(f"الاسم: {request.GET.get('name')}")
        
        if request.GET.get('category'):
            try:
                from product.models import Category
                category = Category.objects.get(id=request.GET.get('category'))
                filters_applied.append(f"التصنيف: {category.name}")
            except:
                pass
        
        if request.GET.get('min_price'):
            filters_applied.append(f"السعر الأدنى: {request.GET.get('min_price')} {currency}")
        
        if request.GET.get('max_price'):
            filters_applied.append(f"السعر الأقصى: {request.GET.get('max_price')} {currency}")
        
        if request.GET.get('is_active'):
            filters_applied.append("الحالة: نشط فقط")
        
        if request.GET.get('in_stock'):
            filters_applied.append("المخزون: متوفر فقط")
        
        if filters_applied:
            filters_text = ' • '.join(filters_applied)
            filter_style = ParagraphStyle(
                'FilterStyle',
                parent=styles['Normal'],
                fontName=font_name,
                fontSize=8,
                alignment=TA_RIGHT,
                textColor=colors.HexColor('#344767'),
                backColor=colors.HexColor('#f8f9fa'),
                borderPadding=5
            )
            story.append(Paragraph(f'<b>الفلاتر:</b> {filters_text}', filter_style))
            story.append(Spacer(1, 0.1*inch))
        
        # إعداد بيانات الجدول
        table_data = [
            ['#', 'كود المنتج', 'اسم المنتج', 'التصنيف', 'سعر البيع', 'المخزون', 'الحالة']
        ]
        
        # إضافة صفوف المنتجات (بدون الصور لتبسيط الـ PDF)
        for idx, product in enumerate(products, 1):
            total_stock = product.stocks.aggregate(total=Sum('quantity'))['total'] or 0
            status = 'نشط' if product.is_active else 'غير نشط'
            
            row = [
                str(idx),
                product.sku,
                product.name,
                product.category.name if product.category else '-',
                f'{product.selling_price:.2f} {currency}',
                str(int(total_stock)),
                status
            ]
            table_data.append(row)
        
        # إنشاء الجدول
        table = Table(table_data, colWidths=[0.7*cm, 2.5*cm, 5*cm, 3*cm, 2.5*cm, 2*cm, 2*cm])
        
        # تنسيق الجدول
        table_style = TableStyle([
            # تنسيق العناوين
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#344767')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), font_name),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('TOPPADDING', (0, 0), (-1, 0), 10),
            
            # تنسيق البيانات
            ('FONTNAME', (0, 1), (-1, -1), font_name),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 1), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ])
        
        # تلوين صف الحالة حسب القيمة
        for i, row in enumerate(table_data[1:], 1):
            if row[-1] == 'نشط':
                table_style.add('TEXTCOLOR', (-1, i), (-1, i), colors.HexColor('#28a745'))
            else:
                table_style.add('TEXTCOLOR', (-1, i), (-1, i), colors.HexColor('#dc3545'))
        
        table.setStyle(table_style)
        story.append(table)
        
        # إضافة footer
        story.append(Spacer(1, 0.3*inch))
        footer_style = ParagraphStyle(
            'FooterStyle',
            parent=styles['Normal'],
            fontName=font_name,
            fontSize=7,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#6c757d')
        )
        footer_text = f'تم الإنشاء بواسطة نظام Corporate ERP - جميع الحقوق محفوظة © {now_local.year}'
        story.append(Paragraph(footer_text, footer_style))
        
        # بناء الـ PDF
        doc.build(story)
        
        # الحصول على محتوى الـ PDF
        pdf_content = buffer.getvalue()
        buffer.close()
        
        # إرجاع الاستجابة - فتح في المتصفح بدلاً من التحميل
        response = HttpResponse(pdf_content, content_type='application/pdf')
        response['Content-Disposition'] = 'inline; filename="products_list.pdf"'
        return response
        
    except ImportError as e:
        messages.error(request, f"مكتبة ReportLab غير مثبتة: {str(e)}")
        return redirect("product:product_list")
    except Exception as e:
        messages.error(request, f"خطأ في تصدير PDF: {str(e)}")
        return redirect("product:product_list")


@login_required
@require_POST
def delete_product_image(request, pk):
    """
    حذف صورة منتج
    ✅ SECURITY: Removed @csrf_exempt, using proper CSRF protection
    """
    try:
        image = get_object_or_404(ProductImage, pk=pk)
        product_id = image.product.id
        image.delete()

        # إذا تم حذف الصورة الرئيسية، اجعل أول صورة أخرى رئيسية
        if image.is_primary:
            first_image = ProductImage.objects.filter(product_id=product_id).first()
            if first_image:
                first_image.is_primary = True
                first_image.save()

        return JsonResponse({"success": True, "message": "تم حذف الصورة بنجاح"})
    except ProductImage.DoesNotExist:
        return JsonResponse({"success": False, "error": "الصورة غير موجودة"})
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in delete_product_image: {str(e)}", exc_info=True)
        return JsonResponse({"success": False, "error": _("حدث خطأ أثناء حذف الصورة")})

    return JsonResponse({"success": False, "error": _("طريقة طلب غير مدعومة")})
def get_stock_by_warehouse(request):
    """
    API للحصول على المخزون المتاح في مخزن معين
    """
    warehouse_id = request.GET.get("warehouse")

    # تسجيل معلومات الطلب للتشخيص

    if not warehouse_id:
        logger.warning("API المخزون: لم يتم توفير معرف المخزن")
        return JsonResponse({}, status=400)

    try:
        # التحقق من وجود المخزن
        warehouse = get_object_or_404(Warehouse, id=warehouse_id)

        # الحصول على المخزون المتاح في المخزن المحدد
        stocks = Stock.objects.filter(warehouse=warehouse).values(
            "product_id", "quantity"
        )

        # بناء قاموس به المنتجات والمخزون المتاح
        stock_data = {}
        for stock in stocks:
            stock_data[str(stock["product_id"])] = stock["quantity"]

        return JsonResponse(stock_data)

    except Exception as e:
        logger.error(f"خطأ في API المخزون: {str(e)}")
        return JsonResponse({"error": str(e)}, status=500)


@login_required
def get_products_for_invoice(request):
    """
    API لجلب المنتجات المناسبة لفاتورة البيع أو الشراء
    - show_all=false (افتراضي): المنتجات اللي ليها stock > 0 في المخزن المحدد فقط
    - show_all=true: كل المنتجات النشطة
    - type=sale: منتجات البيع (مش خدمات، مش bundles)
    - type=purchase: منتجات الشراء (مش bundles)
    - type=service: خدمات فقط
    """
    warehouse_id = request.GET.get("warehouse")
    show_all = request.GET.get("show_all", "false") == "true"
    product_type = request.GET.get("type", "sale")

    try:
        # فلترة المنتجات حسب النوع
        if product_type == "service":
            qs = Product.objects.filter(is_active=True, is_service=True)
        elif product_type == "purchase":
            qs = Product.objects.filter(is_active=True, is_service=False, is_bundle=False)
        else:  # sale
            qs = Product.objects.filter(is_active=True, is_service=False, is_bundle=False)

        # جلب بيانات المخزون
        stock_map = {}
        if warehouse_id:
            stocks = Stock.objects.filter(
                warehouse_id=warehouse_id,
                product__in=qs
            ).values("product_id", "quantity")
            stock_map = {str(s["product_id"]): float(s["quantity"]) for s in stocks}

        # فلترة حسب المخزون لو مش show_all
        if not show_all and warehouse_id and product_type != "service":
            product_ids_with_stock = [pid for pid, qty in stock_map.items() if qty > 0]
            qs = qs.filter(id__in=product_ids_with_stock)

        products = []
        for p in qs.select_related('category').order_by("name"):
            products.append({
                "id": p.id,
                "name": p.name,
                "selling_price": float(p.selling_price) if hasattr(p, 'selling_price') and p.selling_price else 0,
                "cost_price": float(p.cost_price) if hasattr(p, 'cost_price') and p.cost_price else 0,
                "stock": stock_map.get(str(p.id), 0),
                "category_id": p.category_id,
                "category_name": p.category.name if p.category else "",
            })

        return JsonResponse({"products": products})

    except Exception as e:
        logger.error(f"خطأ في API المنتجات: {str(e)}")
        return JsonResponse({"error": str(e)}, status=500)


# دوال مساعدة لحذف المخزن
def _check_warehouse_dependencies(warehouse):
    """
    التحقق من الارتباطات الموجودة للمخزن
    """
    dependencies = {
        "has_dependencies": False,
        "stock_movements": 0,
        "sales": 0,
        "purchases": 0,
        "stocks": 0,
        "details": [],
    }

    try:
        # حركات المخزون
        stock_movements = StockMovement.objects.filter(warehouse=warehouse)
        dependencies["stock_movements"] = stock_movements.count()
        if dependencies["stock_movements"] > 0:
            dependencies["has_dependencies"] = True
            dependencies["details"].append(
                f"{dependencies['stock_movements']} حركة مخزون"
            )

        # المبيعات - تم إزالة Sale module

        # المشتريات
        try:
            from purchase.models import Purchase

            purchases = Purchase.objects.filter(warehouse=warehouse)
            dependencies["purchases"] = purchases.count()
            if dependencies["purchases"] > 0:
                dependencies["has_dependencies"] = True
                dependencies["details"].append(
                    f"{dependencies['purchases']} فاتورة مشتريات"
                )
        except ImportError:
            pass

        # المخزون الحالي
        stocks = Stock.objects.filter(warehouse=warehouse, quantity__gt=0)
        dependencies["stocks"] = stocks.count()
        if dependencies["stocks"] > 0:
            dependencies["has_dependencies"] = True
            dependencies["details"].append(f"{dependencies['stocks']} منتج بمخزون متاح")

    except Exception as e:
        logger.error(f"خطأ في فحص ارتباطات المخزن: {str(e)}")

    return dependencies


def _transfer_warehouse_data(source_warehouse, target_warehouse, user):
    """
    نقل بيانات المخزن من مخزن إلى آخر
    """
    try:
        from django.db import transaction

        with transaction.atomic():
            # نقل المخزون
            stocks = Stock.objects.filter(warehouse=source_warehouse)
            for stock in stocks:
                target_stock, created = Stock.objects.get_or_create(
                    product=stock.product,
                    warehouse=target_warehouse,
                    defaults={"quantity": 0},
                )

                if stock.quantity > 0:
                    # إنشاء حركة نقل
                    StockMovement.objects.create(
                        product=stock.product,
                        warehouse=source_warehouse,
                        destination_warehouse=target_warehouse,
                        movement_type="transfer",
                        quantity=stock.quantity,
                        notes=f"نقل من المخزن المحذوف: {source_warehouse.name}",
                        created_by=user,
                        document_type="transfer",
                        reference_number=f"TRANSFER-{source_warehouse.code}-{target_warehouse.code}",
                    )

                    # تحديث المخزون في المخزن المستهدف
                    target_stock.quantity += stock.quantity
                    target_stock.save()

                # حذف المخزون من المخزن المصدر
                stock.delete()

            # تحديث حركات المخزون القديمة (تغيير المرجع فقط)
            StockMovement.objects.filter(warehouse=source_warehouse).update(
                notes=F("notes") + f" [المخزن الأصلي: {source_warehouse.name} - محذوف]"
            )

            # تحديث المشتريات لتشير للمخزن الجديد (تم إزالة Sale module)

            try:
                from purchase.models import Purchase

                purchases_count = Purchase.objects.filter(
                    warehouse=source_warehouse
                ).count()
                if purchases_count > 0:
                    Purchase.objects.filter(warehouse=source_warehouse).update(
                        warehouse=target_warehouse
                    )
            except ImportError:
                pass

        return True

    except Exception as e:
        logger.error(f"خطأ في نقل بيانات المخزن: {str(e)}")
        return False


def _force_delete_warehouse(warehouse):
    """
    حذف قسري للمخزن مع جميع البيانات المرتبطة
    تحذير: هذه العملية خطيرة ولا يمكن التراجع عنها
    """
    try:
        from django.db import transaction

        with transaction.atomic():
            # حذف المخزون
            Stock.objects.filter(warehouse=warehouse).delete()

            # حذف حركات المخزون
            StockMovement.objects.filter(warehouse=warehouse).delete()
            StockMovement.objects.filter(destination_warehouse=warehouse).delete()

            # حذف المشتريات المرتبطة بالمخزن (تم إزالة Sale module)

            try:
                from purchase.models import Purchase

                purchases_to_delete = Purchase.objects.filter(warehouse=warehouse)
                purchases_count = purchases_to_delete.count()
                if purchases_count > 0:
                    logger.warning(
                        f"سيتم حذف {purchases_count} فاتورة مشتريات مرتبطة بالمخزن {warehouse.name}"
                    )
                    # حذف عناصر المشتريات أولاً
                    try:
                        from purchase.models import PurchaseItem

                        PurchaseItem.objects.filter(
                            purchase__warehouse=warehouse
                        ).delete()
                    except ImportError:
                        pass
                    # حذف مدفوعات المشتريات
                    try:
                        from purchase.models import PurchasePayment

                        PurchasePayment.objects.filter(
                            purchase__warehouse=warehouse
                        ).delete()
                    except ImportError:
                        pass
                    # حذف فواتير المشتريات
                    purchases_to_delete.delete()
            except ImportError:
                pass

            # حذف المخزن
            warehouse.delete()

    except Exception as e:
        logger.error(f"خطأ في الحذف القسري للمخزن: {str(e)}")
        raise e


@login_required
def product_stock_view(request, pk):
    """
    عرض مخزون المنتج في جميع المخازن
    """
    product = get_object_or_404(
        Product.objects.select_related("category", "unit"), pk=pk
    )

    # الحصول على المخزون الحالي للمنتج في كل مخزن
    stock_items = Stock.objects.filter(product=product).select_related("warehouse")

    # آخر حركات المخزون
    stock_movements = (
        StockMovement.objects.filter(product=product)
        .select_related("warehouse", "destination_warehouse", "created_by")
        .order_by("-timestamp")[:20]
    )

    # إجمالي المخزون
    total_stock = stock_items.aggregate(total=Sum("quantity"))["total"] or 0

    # المخازن المتاحة لإضافة المخزون
    warehouses = Warehouse.objects.filter(is_active=True)

    context = {
        "product": product,
        "stock_items": stock_items,
        "stock_movements": stock_movements,
        "total_stock": total_stock,
        "warehouses": warehouses,
        "page_title": f"مخزون المنتج: {product.name}",
        "page_icon": "fas fa-boxes",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "المنتجات",
                "url": reverse("product:product_list"),
                "icon": "fas fa-box",
            },
            {
                "title": product.name,
                "url": reverse("product:product_detail", args=[product.pk]),
                "icon": "fas fa-info-circle",
            },
            {"title": "المخزون", "active": True},
        ],
    }

    return render(request, "product/product_stock.html", context)


# ==================== APIs أسعار الموردين ====================


@login_required
@require_POST
def add_supplier_price_api(request):
    """
    API لإضافة سعر مورد جديد لمنتج
    ✅ SECURITY: Removed @csrf_exempt, using proper CSRF protection
    """
    try:
        import json
        from product.services.pricing_service import PricingService
        from supplier.models import Supplier

        data = json.loads(request.body)
        product_id = data.get("product_id")
        supplier_id = data.get("supplier_id")
        cost_price = Decimal(str(data.get("cost_price", 0)))
        notes = data.get("notes", "")

        # التحقق من صحة البيانات
        if not all([product_id, supplier_id, cost_price]):
            return JsonResponse({"success": False, "message": "بيانات مطلوبة مفقودة"})

        # الحصول على المنتج والمورد
        product = get_object_or_404(Product, pk=product_id)
        supplier = get_object_or_404(Supplier, pk=supplier_id)

        # إضافة السعر
        supplier_price = PricingService.update_supplier_price(
            product=product,
            supplier=supplier,
            new_price=cost_price,
            user=request.user,
            reason="manual_update",
            notes=notes,
        )

        if supplier_price:
            return JsonResponse(
                {
                    "success": True,
                    "message": f"تم إضافة سعر المورد {supplier.name} بنجاح",
                    "data": {
                        "id": supplier_price.id,
                        "supplier_name": supplier.name,
                        "cost_price": float(supplier_price.cost_price),
                        "is_default": supplier_price.is_default,
                        "last_purchase_date": supplier_price.last_purchase_date.strftime(
                            "%d/%m/%Y"
                        )
                        if supplier_price.last_purchase_date
                        else None,
                    },
                }
            )
        else:
            return JsonResponse(
                {"success": False, "message": "فشل في إضافة سعر المورد"}
            )

    except Exception as e:
        logger.error(f"خطأ في إضافة سعر المورد: {e}")
        return JsonResponse({"success": False, "message": "حدث خطأ غير متوقع"})


@login_required
@require_POST
def edit_supplier_price_api(request, pk):
    """
    API لتعديل سعر مورد موجود
    ✅ SECURITY: Removed @csrf_exempt, using proper CSRF protection
    """
    try:
        import json
        from product.services.pricing_service import PricingService

        # الحصول على سعر المورد
        supplier_price = get_object_or_404(SupplierProductPrice, pk=pk)

        data = json.loads(request.body)
        new_price = Decimal(str(data.get("cost_price", 0)))
        notes = data.get("notes", "")

        if new_price <= 0:
            return JsonResponse(
                {"success": False, "message": "السعر يجب أن يكون أكبر من صفر"}
            )

        # تحديث السعر
        updated_price = PricingService.update_supplier_price(
            product=supplier_price.product,
            supplier=supplier_price.supplier,
            new_price=new_price,
            user=request.user,
            reason="manual_update",
            notes=notes,
        )

        if updated_price:
            return JsonResponse(
                {
                    "success": True,
                    "message": f"تم تحديث سعر المورد {supplier_price.supplier.name} بنجاح",
                    "data": {
                        "id": updated_price.id,
                        "cost_price": float(updated_price.cost_price),
                        "is_default": updated_price.is_default,
                    },
                }
            )
        else:
            return JsonResponse(
                {"success": False, "message": "فشل في تحديث سعر المورد"}
            )

    except Exception as e:
        logger.error(f"خطأ في تعديل سعر المورد: {e}")
        return JsonResponse({"success": False, "message": "حدث خطأ غير متوقع"})


@login_required
@require_POST
def set_default_supplier_api(request, pk):
    """
    API لتعيين مورد كافتراضي
    ✅ SECURITY: Removed @csrf_exempt, using proper CSRF protection
    """
    try:
        from product.services.pricing_service import PricingService

        # الحصول على سعر المورد
        supplier_price = get_object_or_404(SupplierProductPrice, pk=pk)

        # تعيين المورد كافتراضي
        success = PricingService.set_default_supplier(
            product=supplier_price.product,
            supplier=supplier_price.supplier,
            user=request.user,
        )

        if success:
            return JsonResponse(
                {
                    "success": True,
                    "message": f"تم تعيين {supplier_price.supplier.name} كمورد افتراضي",
                    "data": {
                        "supplier_id": supplier_price.supplier.id,
                        "supplier_name": supplier_price.supplier.name,
                    },
                }
            )
        else:
            return JsonResponse(
                {"success": False, "message": "فشل في تعيين المورد الافتراضي"}
            )

    except Exception as e:
        logger.error(f"خطأ في تعيين المورد الافتراضي: {e}")
        return JsonResponse({"success": False, "message": "حدث خطأ غير متوقع"})


@login_required
def supplier_price_history_api(request, pk):
    """
    API لعرض تاريخ أسعار مورد معين
    """
    try:
        from product.services.pricing_service import PricingService

        # الحصول على سعر المورد
        supplier_price = get_object_or_404(SupplierProductPrice, pk=pk)

        # الحصول على تاريخ الأسعار
        price_history = PricingService.get_price_history(
            product=supplier_price.product, supplier=supplier_price.supplier, limit=20
        )

        history_data = []
        for history in price_history:
            history_data.append(
                {
                    "id": history.id,
                    "old_price": float(history.old_price)
                    if history.old_price
                    else None,
                    "new_price": float(history.new_price),
                    "change_amount": float(history.change_amount)
                    if history.change_amount
                    else 0,
                    "change_percentage": float(history.change_percentage)
                    if history.change_percentage
                    else 0,
                    "change_reason": history.get_change_reason_display(),
                    "change_date": history.change_date.strftime("%d/%m/%Y %H:%M"),
                    "changed_by": history.changed_by.get_full_name()
                    or history.changed_by.username,
                    "purchase_reference": history.purchase_reference,
                    "notes": history.notes,
                    "is_increase": history.is_price_increase,
                    "is_decrease": history.is_price_decrease,
                }
            )

        return JsonResponse(
            {
                "success": True,
                "data": {
                    "supplier_name": supplier_price.supplier.name,
                    "product_name": supplier_price.product.name,
                    "current_price": float(supplier_price.cost_price),
                    "history": history_data,
                },
            }
        )

    except Exception as e:
        logger.error(f"خطأ في عرض تاريخ الأسعار: {e}")
        return JsonResponse({"success": False, "message": "حدث خطأ غير متوقع"})


@login_required
def product_price_comparison_api(request, product_id):
    """
    API لعرض مقارنة أسعار جميع الموردين لمنتج معين
    """
    try:
        from product.services.pricing_service import PricingService

        product = get_object_or_404(Product, pk=product_id)

        # الحصول على مقارنة الأسعار
        price_comparison = PricingService.get_price_comparison(product)
        
        if not price_comparison:
            return JsonResponse(
                {
                    "success": True,
                    "data": {
                        "product_name": product.name,
                        "product_cost_price": float(product.cost_price),
                        "suppliers_count": 0,
                        "cheapest_price": 0,
                        "most_expensive_price": 0,
                        "comparison": [],
                    },
                }
            )

        comparison_data = []
        for comparison in price_comparison:
            comparison_data.append(
                {
                    "supplier_id": comparison["supplier"].id,
                    "supplier_name": comparison["supplier"].name,
                    "price": float(comparison["price"]),
                    "is_default": comparison["is_default"],
                    "last_purchase_date": comparison["last_purchase_date"].strftime(
                        "%d/%m/%Y"
                    )
                    if comparison["last_purchase_date"]
                    else None,
                    "last_purchase_quantity": comparison["last_purchase_quantity"],
                    "price_difference": float(comparison["price_difference"]),
                    "price_difference_percent": float(
                        comparison["price_difference_percent"]
                    ),
                    "days_since_last_purchase": comparison["days_since_last_purchase"],
                    "notes": comparison["notes"],
                }
            )

        return JsonResponse(
            {
                "success": True,
                "data": {
                    "product_name": product.name,
                    "product_cost_price": float(product.cost_price),
                    "suppliers_count": len(comparison_data),
                    "cheapest_price": min([c["price"] for c in comparison_data])
                    if comparison_data
                    else 0,
                    "most_expensive_price": max([c["price"] for c in comparison_data])
                    if comparison_data
                    else 0,
                    "comparison": comparison_data,
                },
            }
        )

    except Exception as e:
        logger.error(f"خطأ في مقارنة الأسعار: {e}")
        return JsonResponse({"success": False, "message": "حدث خطأ غير متوقع"})


# ==================== Bundle Creation Views ====================

@login_required
def _save_component_alternatives(request, bundle, components):
    """
    حفظ البدائل للمكونات من البيانات المرسلة
    """
    import json
    from product.models import BundleComponentAlternative
    
    # حذف البدائل القديمة
    BundleComponentAlternative.objects.filter(
        bundle_component__bundle_product=bundle
    ).delete()
    
    # جلب بيانات البدائل من POST
    alternatives_data = request.POST.get('component_alternatives')
    if not alternatives_data:
        return
    
    try:
        alternatives_dict = json.loads(alternatives_data)
    except json.JSONDecodeError:
        return
    
    # حفظ البدائل الجديدة
    # نستخدم product_id كـ key (الـ frontend بيبعت البيانات بالـ product_id)
    for component in components:
        component_product_id = str(component.component_product_id)
        
        if component_product_id not in alternatives_dict:
            continue
        
        alternatives = alternatives_dict[component_product_id]
        for alt_data in alternatives:
            if not alt_data.get('product_id'):
                continue
            
            try:
                alternative_product = Product.objects.get(
                    id=alt_data['product_id'],
                    is_active=True,
                    is_bundle=False
                )
                
                BundleComponentAlternative.objects.create(
                    bundle_component=component,
                    alternative_product=alternative_product,
                    price_adjustment=alt_data.get('price_adjustment', 0),
                    display_order=alt_data.get('display_order', 0),
                    is_default=alt_data.get('is_default', False),
                    is_active=True
                )
            except Product.DoesNotExist:
                continue


def bundle_create(request):
    """
    إنشاء منتج مجمع جديد مع مكوناته
    Requirements: 1.1, 1.2, 1.3
    """
    if request.method == "POST":
        form = BundleForm(request.POST)
        formset = BundleComponentFormSet(request.POST)
        
        # طباعة الأخطاء للتشخيص
        if not form.is_valid():
            print("Form errors:", form.errors)
        if not formset.is_valid():
            print("Formset errors:", formset.errors)
            print("Formset non_form_errors:", formset.non_form_errors())
        
        if form.is_valid() and formset.is_valid():
            try:
                with transaction.atomic():
                    # حفظ المنتج المجمع
                    bundle = form.save(commit=False)
                    bundle.created_by = request.user
                    bundle.is_bundle = True  # تعيين is_bundle قبل الحفظ
                    bundle.save()
                    
                    # حفظ المكونات
                    formset.instance = bundle
                    components = formset.save()
                    
                    # حفظ البدائل (إذا كان النظام مفعل)
                    if settings.MIGRATION_FLAGS.get('BUNDLE_ALTERNATIVES_ENABLED', False):
                        _save_component_alternatives(request, bundle, components)
                    
                    # التحقق من وجود مكونات (فقط المكونات غير المحذوفة)
                    active_components = [c for c in components if not getattr(c, '_state', None) or not c._state.adding or not getattr(c, 'DELETE', False)]
                    if not active_components and not bundle.components.exists():
                        # إذا لم توجد مكونات، أضف رسالة تحذير لكن لا تمنع الحفظ
                        messages.warning(
                            request, 
                            f'تم إنشاء المنتج المجمع "{bundle.name}" بدون مكونات. يرجى إضافة المكونات لاحقاً.'
                        )
                    else:
                        messages.success(
                            request, 
                            f'تم إنشاء المنتج المجمع "{bundle.name}" بنجاح مع {len(active_components)} مكون'
                        )
                    
                    # إعادة التوجيه حسب الزر المضغوط
                    if "save_and_continue" in request.POST:
                        return redirect("product:bundle_create")
                    elif "save_and_view" in request.POST:
                        return redirect("product:bundle_detail", pk=bundle.pk)
                    else:
                        return redirect("product:bundle_list")
                        
            except ValidationError as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, f"حدث خطأ أثناء إنشاء المنتج المجمع: {str(e)}")
                print(f"Exception in bundle_create: {e}")
        else:
            # إضافة رسائل الأخطاء
            if form.errors:
                for field, errors in form.errors.items():
                    for error in errors:
                        messages.error(request, f"خطأ في {field}: {error}")
            
            if formset.errors:
                for i, form_errors in enumerate(formset.errors):
                    if form_errors:
                        for field, errors in form_errors.items():
                            for error in errors:
                                messages.error(request, f"خطأ في المكون {i+1} - {field}: {error}")
            
            if formset.non_form_errors():
                for error in formset.non_form_errors():
                    messages.error(request, f"خطأ في المكونات: {error}")
    else:
        form = BundleForm()
        formset = BundleComponentFormSet()
        
        # تأكد من أن الـ instance في الـ form هو منتج مجمع
        form.instance.is_bundle = True
    
    # إحصائيات سريعة للمساعدة
    total_products = Product.objects.filter(is_active=True, is_bundle=False).count()
    total_categories = Category.objects.filter(is_active=True).count()
    
    context = {
        "form": form,
        "formset": formset,
        "total_products": total_products,
        "total_categories": total_categories,
        
        # بيانات الهيدر الموحد
        "title": "إنشاء منتج مجمع جديد",
        "page_title": "إنشاء منتج مجمع جديد",
        "page_subtitle": "إنشاء منتج مركب من عدة منتجات فردية",
        "page_icon": "fas fa-boxes",
        
        # أزرار الهيدر
        "header_buttons": [
            {
                "url": reverse("product:bundle_list"),
                "icon": "fa-arrow-right",
                "text": "العودة للقائمة",
                "class": "btn-outline-secondary",
            },
            {
                "url": reverse("product:product_list"),
                "icon": "fa-list",
                "text": "جميع المنتجات",
                "class": "btn-outline-primary",
            },
        ],
        
        # مسار التنقل
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "المنتجات",
                "url": reverse("product:product_list"),
                "icon": "fas fa-boxes",
            },
            {
                "title": "المنتجات المجمعة",
                "url": reverse("product:bundle_list"),
                "icon": "fas fa-boxes",
            },
            {"title": "إنشاء منتج مجمع", "active": True},
        ],
    }
    
    return render(request, "product/bundle_form.html", context)


@login_required
def bundle_edit(request, pk):
    """
    تعديل منتج مجمع ومكوناته
    Requirements: 1.6, 1.7
    """
    bundle = get_object_or_404(Product, pk=pk, is_bundle=True)
    
    # فحص استخدام المنتج المجمع في الطلبات الموجودة
    from ..services.bundle_manager import BundleManager
    usage_info = BundleManager.check_bundle_usage_in_orders(bundle)
    
    if request.method == "POST":
        form = BundleForm(request.POST, instance=bundle)
        formset = BundleComponentFormSet(request.POST, instance=bundle)
        
        if form.is_valid() and formset.is_valid():
            try:
                with transaction.atomic():
                    # تحليل التغييرات في المكونات
                    new_components_data = []
                    for form_instance in formset.forms:
                        if form_instance.cleaned_data and not form_instance.cleaned_data.get('DELETE', False):
                            new_components_data.append({
                                'component_product_id': form_instance.cleaned_data['component_product'].id,
                                'required_quantity': form_instance.cleaned_data['required_quantity']
                            })
                    
                    # تحليل التغييرات
                    changes_analysis = BundleManager.analyze_component_changes(
                        bundle, new_components_data
                    )
                    
                    # التحقق من التغييرات المدمرة مع الطلبات الموجودة
                    if (changes_analysis['is_destructive'] and 
                        not usage_info['can_modify_safely'] and 
                        not request.POST.get('confirm_destructive_changes')):
                        
                        # إرجاع تحذير للمستخدم
                        context = {
                            "form": form,
                            "formset": formset,
                            "bundle": bundle,
                            "usage_info": usage_info,
                            "changes_analysis": changes_analysis,
                            "requires_confirmation": True,
                            "warning_message": usage_info.get('warning_message'),
                            
                            # بيانات الهيدر الموحد
                            "title": f"تعديل المنتج المجمع: {bundle.name}",
                            "page_title": f"تعديل: {bundle.name}",
                            "page_subtitle": f"كود المنتج: {bundle.sku} • تحذير: تغييرات مدمرة",
                            "page_icon": "fas fa-exclamation-triangle",
                            
                            # أزرار الهيدر
                            "header_buttons": [
                                {
                                    "url": reverse("product:bundle_detail", args=[bundle.pk]),
                                    "icon": "fa-eye",
                                    "text": "عرض التفاصيل",
                                    "class": "btn-info",
                                },
                                {
                                    "url": reverse("product:bundle_list"),
                                    "icon": "fa-arrow-right",
                                    "text": "العودة للقائمة",
                                    "class": "btn-outline-secondary",
                                },
                            ],
                            
                            # مسار التنقل
                            "breadcrumb_items": [
                                {
                                    "title": "الرئيسية",
                                    "url": reverse("core:dashboard"),
                                    "icon": "fas fa-home",
                                },
                                {
                                    "title": "المنتجات",
                                    "url": reverse("product:product_list"),
                                    "icon": "fas fa-boxes",
                                },
                                {
                                    "title": "المنتجات المجمعة",
                                    "url": reverse("product:bundle_list"),
                                    "icon": "fas fa-boxes",
                                },
                                {"title": f"تعديل: {bundle.name}", "active": True},
                            ],
                        }
                        
                        return render(request, "product/bundle_form.html", context)
                    
                    # حفظ المنتج المجمع
                    bundle = form.save()
                    
                    # حفظ المكونات
                    components = formset.save()
                    
                    # حفظ البدائل (إذا كان النظام مفعل)
                    if settings.MIGRATION_FLAGS.get('BUNDLE_ALTERNATIVES_ENABLED', False):
                        _save_component_alternatives(request, bundle, components)
                    
                    # التحقق من وجود مكونات
                    active_components = [c for c in components if not c._state.adding or not getattr(c, 'DELETE', False)]
                    if not active_components:
                        raise ValidationError("يجب أن يحتوي المنتج المجمع على مكون واحد على الأقل")
                    
                    # رسالة نجاح مع تفاصيل التغييرات
                    success_message = f'تم تحديث المنتج المجمع "{bundle.name}" بنجاح'
                    if changes_analysis['has_changes']:
                        success_message += f". التغييرات: {', '.join(changes_analysis['change_summary'])}"
                    
                    messages.success(request, success_message)
                    
                    # إعادة التوجيه حسب الزر المضغوط
                    if "save_and_continue" in request.POST:
                        return redirect("product:bundle_edit", pk=bundle.pk)
                    elif "save_and_view" in request.POST:
                        return redirect("product:bundle_detail", pk=bundle.pk)
                    else:
                        return redirect("product:bundle_list")
                        
            except ValidationError as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, f"حدث خطأ أثناء تحديث المنتج المجمع: {str(e)}")
    else:
        form = BundleForm(instance=bundle)
        formset = BundleComponentFormSet(instance=bundle)
    
    # إحصائيات المنتج المجمع
    components_count = bundle.components.count()
    calculated_stock = bundle.calculated_stock
    
    # جلب البدائل الموجودة (إذا كان النظام مفعل)
    existing_alternatives = {}
    if settings.MIGRATION_FLAGS.get('BUNDLE_ALTERNATIVES_ENABLED', False):
        import json
        from product.models import BundleComponentAlternative
        for component in bundle.components.all():
            alternatives = BundleComponentAlternative.objects.filter(
                bundle_component=component,
                is_active=True
            ).select_related('alternative_product').order_by('display_order')
            
            if alternatives.exists():
                existing_alternatives[str(component.component_product_id)] = [
                    {
                        'product_id': alt.alternative_product_id,
                        'product_name': alt.alternative_product.name,
                        'product_price': float(alt.alternative_product.selling_price),
                        'price_adjustment': float(alt.price_adjustment),
                        'display_order': alt.display_order,
                        'is_default': alt.is_default,
                    }
                    for alt in alternatives
                ]
    
    context = {
        "form": form,
        "formset": formset,
        "bundle": bundle,
        "components_count": components_count,
        "calculated_stock": calculated_stock,
        "usage_info": usage_info,
        "requires_confirmation": False,
        "existing_alternatives": json.dumps(existing_alternatives) if existing_alternatives else '{}',
        
        # بيانات الهيدر الموحد
        "title": f"تعديل المنتج المجمع: {bundle.name}",
        "page_title": f"تعديل: {bundle.name}",
        "page_subtitle": f"كود المنتج: {bundle.sku} • {components_count} مكون",
        "page_icon": "fas fa-edit",
        
        # أزرار الهيدر
        "header_buttons": [
            {
                "url": reverse("product:bundle_detail", args=[bundle.pk]),
                "icon": "fa-eye",
                "text": "عرض التفاصيل",
                "class": "btn-info",
            },
            {
                "url": reverse("product:bundle_list"),
                "icon": "fa-arrow-right",
                "text": "العودة للقائمة",
                "class": "btn-outline-secondary",
            },
        ],
        
        # مسار التنقل
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "المنتجات",
                "url": reverse("product:product_list"),
                "icon": "fas fa-boxes",
            },
            {
                "title": "المنتجات المجمعة",
                "url": reverse("product:bundle_list"),
                "icon": "fas fa-boxes",
            },
            {"title": f"تعديل: {bundle.name}", "active": True},
        ],
    }
    
    return render(request, "product/bundle_form.html", context)


# ==================== AJAX Views for Dynamic Components ====================

@login_required
def get_available_products_ajax(request):
    """
    إرجاع المنتجات المتاحة للإضافة كمكونات (AJAX)
    """
    bundle_id = request.GET.get('bundle_id')
    search_term = request.GET.get('term', '')
    exclude_ids = request.GET.get('exclude_ids', '')
    
    # تصفية المنتجات المتاحة
    products = Product.objects.filter(
        is_active=True,
        is_bundle=False,
        name__icontains=search_term
    )
    
    # استبعاد المنتج المجمع نفسه
    if bundle_id:
        products = products.exclude(pk=bundle_id)
        
        # استبعاد المكونات المضافة مسبقاً
        existing_components = BundleComponent.objects.filter(
            bundle_product_id=bundle_id
        ).values_list('component_product_id', flat=True)
        products = products.exclude(pk__in=existing_components)
    
    # استبعاد المنتجات المحددة (المختارة في المكونات/البدائل الأخرى)
    if exclude_ids:
        exclude_list = [int(x) for x in exclude_ids.split(',') if x.strip().isdigit()]
        products = products.exclude(pk__in=exclude_list)
    
    # تحضير البيانات للإرجاع
    results = []
    for product in products[:50]:  # حد أقصى 50 نتيجة
        results.append({
            'id': product.id,
            'text': f"{product.name} ({product.sku})",
            'name': product.name,
            'sku': product.sku,
            'category': product.category.name,
            'current_stock': float(product.current_stock),
            'unit': product.unit.name,
            'selling_price': float(product.selling_price),
        })
    
    return JsonResponse({
        'success': True,
        'results': results,
        'products': results  # للتوافق مع الكود الجديد
    })


@login_required
def get_product_info_ajax(request, product_id):
    """
    إرجاع معلومات منتج معين (AJAX)
    """
    try:
        product = get_object_or_404(Product, pk=product_id, is_active=True, is_bundle=False)
        
        data = {
            'success': True,
            'product': {
                'id': product.id,
                'name': product.name,
                'sku': product.sku,
                'category': product.category.name,
                'current_stock': product.current_stock,
                'unit': product.unit.name,
                'cost_price': float(product.cost_price),
                'selling_price': float(product.selling_price),
            }
        }
        
        return JsonResponse(data)
        
    except Product.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'المنتج غير موجود أو غير نشط'
        })


# ==================== Helper Functions ====================

def _check_warehouse_dependencies(warehouse):
    """
    فحص الارتباطات الخاصة بالمخزن قبل الحذف
    """
    dependencies = {
        "has_dependencies": False,
        "stocks_count": 0,
        "movements_count": 0,
        "non_zero_stocks": 0,
    }

    # فحص المخزون
    stocks = Stock.objects.filter(warehouse=warehouse)
    dependencies["stocks_count"] = stocks.count()
    dependencies["non_zero_stocks"] = stocks.filter(quantity__gt=0).count()

    # فحص حركات المخزون
    movements = StockMovement.objects.filter(
        Q(warehouse=warehouse) | Q(destination_warehouse=warehouse)
    )
    dependencies["movements_count"] = movements.count()

    # تحديد وجود ارتباطات
    dependencies["has_dependencies"] = (
        dependencies["stocks_count"] > 0 or dependencies["movements_count"] > 0
    )

    return dependencies


def _transfer_warehouse_data(source_warehouse, target_warehouse, user):
    """
    نقل بيانات المخزن من مخزن إلى آخر
    """
    try:
        with transaction.atomic():
            # نقل المخزون
            stocks = Stock.objects.filter(warehouse=source_warehouse)
            for stock in stocks:
                target_stock, created = Stock.objects.get_or_create(
                    product=stock.product,
                    warehouse=target_warehouse,
                    defaults={"quantity": 0, "created_by": user},
                )
                target_stock.quantity += stock.quantity
                target_stock.save()

                # إنشاء حركة تحويل
                StockMovement.objects.create(
                    product=stock.product,
                    warehouse=source_warehouse,
                    destination_warehouse=target_warehouse,
                    movement_type="transfer",
                    quantity=stock.quantity,
                    notes=f"تحويل من مخزن محذوف: {source_warehouse.name}",
                    created_by=user,
                )

            return True

    except Exception as e:
        logger.error(f"Error transferring warehouse data: {e}")
        return False


def _force_delete_warehouse(warehouse):
    """
    حذف قسري للمخزن وجميع البيانات المرتبطة
    """
    with transaction.atomic():
        # حذف المخزون
        Stock.objects.filter(warehouse=warehouse).delete()

        # حذف حركات المخزون
        StockMovement.objects.filter(
            Q(warehouse=warehouse) | Q(destination_warehouse=warehouse)
        ).delete()

        # حذف المخزن
        warehouse.delete()

@login_required
@require_POST
def generate_sku_ajax(request):
    """
    توليد كود المنتج تلقائياً عبر AJAX
    """
    try:
        category_id = request.POST.get('category_id')
        if not category_id:
            return JsonResponse({
                'success': False, 
                'error': 'يجب تحديد التصنيف'
            })
        
        category = get_object_or_404(Category, id=category_id)
        new_sku = Product.generate_sku(category)
        
        return JsonResponse({
            'success': True,
            'sku': new_sku,
            'message': f'تم توليد الكود: {new_sku}'
        })
        
    except Exception as e:
        logger.error(f"خطأ في توليد الكود: {e}")
        return JsonResponse({
            'success': False,
            'error': 'حدث خطأ في توليد الكود'
        })