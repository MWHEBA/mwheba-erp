import logging
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models import SystemSetting
from client.models import Customer
from product.models import Product, Warehouse, Stock
from sale.models import Quotation, QuotationItem, Sale
from sale.forms import QuotationForm
from sale.services.sale_service import SaleService

logger = logging.getLogger(__name__)


def check_quotations_enabled(view_func):
    def _wrapped_view(request, *args, **kwargs):
        enabled = SystemSetting.get_setting('enable_quotations', 'false') == 'true'
        if not enabled:
            return render(request, "core/permission_denied.html", {
                "title": _("ميزة معطلة"),
                "message": _("ميزة عروض الأسعار غير مفعلة لهذا الحساب/الشركة. يرجى تفعيلها من الإعدادات أولاً.")
            })
        return view_func(request, *args, **kwargs)
    return _wrapped_view


@login_required
@check_quotations_enabled
def quotation_list(request):
    if not request.user.has_perm('sale.view_quotation') and not request.user.is_superuser and not request.user.is_admin:
        return render(request, "core/permission_denied.html", {
            "title": _("غير مصرح"), "message": _("ليس لديك صلاحية لعرض عروض الأسعار")
        })

    search = request.GET.get('search', '')
    customer_id = request.GET.get('customer', '')
    status = request.GET.get('status', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    quotations_qs = Quotation.objects.all().order_by('-date', '-number')

    if search:
        quotations_qs = quotations_qs.filter(
            Q(number__icontains=search) |
            Q(customer__name__icontains=search) |
            Q(notes__icontains=search)
        )
    if customer_id:
        quotations_qs = quotations_qs.filter(customer_id=customer_id)
    if status:
        quotations_qs = quotations_qs.filter(status=status)
    if date_from:
        quotations_qs = quotations_qs.filter(date__gte=date_from)
    if date_to:
        quotations_qs = quotations_qs.filter(date__lte=date_to)

    paginator = Paginator(quotations_qs, 25)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    customers = Customer.objects.filter(is_active=True).order_by('name')
    
    # الإحصائيات
    total_quotes_count = quotations_qs.count()
    draft_count = quotations_qs.filter(status='draft').count()
    sent_count = quotations_qs.filter(status='sent').count()
    accepted_count = quotations_qs.filter(status='accepted').count()

    context = {
        "quotations": page_obj,
        "page_obj": page_obj,
        "paginator": paginator,
        "customers": customers,
        "total_quotes_count": total_quotes_count,
        "draft_count": draft_count,
        "sent_count": sent_count,
        "accepted_count": accepted_count,
        "active_menu": "sales",
        "page_title": _("عروض الأسعار"),
        "page_subtitle": _("إدارة عروض أسعار العملاء ومتابعتها وتصديرها"),
        "page_icon": "fas fa-file-signature",
        "header_buttons": [
            {
                "url": reverse("sale:quotation_create"),
                "icon": "fa-plus",
                "text": _("إضافة عرض سعر"),
                "class": "btn-primary",
            }
        ],
        "breadcrumb_items": [
            {"title": _("الرئيسية"), "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": _("المبيعات"), "url": reverse("sale:sale_list"), "icon": "fas fa-shopping-cart"},
            {"title": _("عروض الأسعار"), "active": True},
        ]
    }
    return render(request, "sale/quotation_list.html", context)


@login_required
@check_quotations_enabled
def quotation_create(request, customer_id=None):
    if not request.user.has_perm('sale.add_quotation') and not request.user.is_superuser and not request.user.is_admin:
        return render(request, "core/permission_denied.html", {
            "title": _("غير مصرح"), "message": _("ليس لديك صلاحية لإنشاء عروض أسعار")
        })

    selected_customer = None
    if customer_id:
        selected_customer = get_object_or_404(Customer, id=customer_id, is_active=True)

    # قراءة أمر الشغل إذا تم تمريره
    work_order_id = request.GET.get('work_order')
    selected_work_order = None
    if work_order_id:
        from work_order.models import WorkOrder
        try:
            selected_work_order = WorkOrder.objects.get(id=work_order_id)
            selected_customer = selected_work_order.customer
        except WorkOrder.DoesNotExist:
            pass

    if request.method == "POST":
        form = QuotationForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    quotation = form.save(commit=False)
                    quotation.created_by = request.user
                    quotation.save()

                    # حفظ البنود
                    product_ids = request.POST.getlist("product[]")
                    quantities = request.POST.getlist("quantity[]")
                    unit_prices = request.POST.getlist("unit_price[]")
                    discounts = request.POST.getlist("discount[]")

                    subtotal = Decimal("0")
                    total_discount = Decimal("0")

                    for i in range(len(product_ids)):
                        if product_ids[i] and quantities[i] and unit_prices[i]:
                            prod_id = int(product_ids[i])
                            product = Product.objects.get(id=prod_id)
                            qty = Decimal(quantities[i])
                            price = Decimal(unit_prices[i].replace(',', ''))
                            if price <= 0:
                                raise ValueError(_("سعر المنتج يجب أن يكون أكبر من صفر (البند رقم {})").format(i + 1))
                            if qty <= 0:
                                raise ValueError(_("الكمية يجب أن تكون أكبر من صفر (البند رقم {})").format(i + 1))
                            item_disc = Decimal(discounts[i] if discounts[i] else '0')
                            item_total = (qty * price) - item_disc

                            QuotationItem.objects.create(
                                quotation=quotation,
                                product=product,
                                quantity=qty,
                                unit_price=price,
                                discount=item_disc,
                                total=item_total
                            )

                            subtotal += qty * price
                            total_discount += item_disc

                            # التحقق من إجمالي المخزون في جميع المخازن لإصدار تنبيه
                            from django.db.models import Sum
                            stock_sum = Stock.objects.filter(product=product, warehouse__is_active=True).aggregate(total_qty=Sum("quantity"))
                            stock_qty = stock_sum.get("total_qty") or 0
                            if not product.is_service and stock_qty < qty:
                                messages.warning(
                                    request,
                                    _("تنبيه: المنتج '{}' غير متوفر بالكمية المطلوبة في الفروع/المستودعات (المتوفر كلياً: {}، المطلوب: {})").format(
                                        product.name, stock_qty, qty
                                    )
                                )

                    # تحديث قيم الإجماليات
                    quotation.subtotal = subtotal
                    quotation.discount = total_discount
                    if quotation.tax_active:
                        default_tax_rate = Decimal(SystemSetting.get_setting('default_tax_rate', '14'))
                        quotation.tax = ((subtotal - total_discount) * default_tax_rate / 100).quantize(Decimal("0.01"))
                    else:
                        quotation.tax = Decimal("0")
                    quotation.total = subtotal - total_discount + quotation.tax
                    quotation.save()

                messages.success(request, _("تم إنشاء عرض السعر بنجاح"))
                return redirect("sale:quotation_detail", pk=quotation.pk)

            except Exception as e:
                logger.error(f"Error creating quotation: {str(e)}")
                messages.error(request, _("حدث خطأ أثناء حفظ عرض السعر: {}").format(str(e)))
    else:
        initial_data = {}
        if selected_customer:
            initial_data["customer"] = selected_customer
        if selected_work_order:
            initial_data["work_order"] = selected_work_order
        form = QuotationForm(initial=initial_data)

    customers = Customer.objects.filter(is_active=True).order_by('name')
    warehouses = Warehouse.objects.filter(is_active=True).order_by('name')
    products = Product.objects.filter(is_active=True).order_by('name')

    # جلب نوع البنود المسموح بها والتصنيفات للمودال
    from product.models import Category
    allowed_item_types = SystemSetting.get_setting('sale_invoice_item_types', 'both')
    
    category_filter = Q(is_active=True, products__is_active=True, products__is_bundle=False)
    if allowed_item_types == 'products':
        category_filter &= Q(products__is_service=False)
    elif allowed_item_types == 'services':
        category_filter &= Q(products__is_service=True)
        
    product_categories = Category.objects.filter(category_filter).distinct().order_by("name")

    # توليد الرقم القادم للعرض
    next_quotation_number = None
    try:
        from product.models import SerialNumber
        serial, created = SerialNumber.objects.get_or_create(
            document_type="quotation",
            year=timezone.now().year,
            defaults={"prefix": "QT", "last_number": 0},
        )
        last_quotation = Quotation.objects.order_by("-id").first()
        last_number = 0
        if last_quotation and last_quotation.number:
            try:
                last_number = int(last_quotation.number.replace("QT", ""))
            except (ValueError, AttributeError):
                pass
        next_number = max(serial.last_number, last_number) + 1
        next_quotation_number = f"{serial.prefix}{next_number:04d}"
    except Exception as e:
        logger.error(f"Error generating next quotation number: {str(e)}")

    context = {
        "form": form,
        "customers": customers,
        "warehouses": warehouses,
        "products": products,
        "selected_customer": selected_customer,
        "default_warehouse": warehouses.first() if warehouses.exists() else None,
        "next_quotation_number": next_quotation_number,
        "allowed_item_types": allowed_item_types,
        "product_categories": product_categories,
        "page_title": _("إضافة عرض سعر"),
        "page_subtitle": _("إضافة عرض سعر جديد لعميل محدد مع تفاصيل البنود والكميات"),
        "page_icon": "fas fa-file-signature",
        "active_menu": "sales",
        "breadcrumb_items": [
            {"title": _("الرئيسية"), "url": reverse("core:dashboard"), "icon": "fa-home"},
            *([
                {"title": _("أوامر الشغل"), "url": reverse("work_order:work_order_list"), "icon": "fa-briefcase"},
                {"title": selected_work_order.number, "url": reverse("work_order:work_order_detail", kwargs={"pk": selected_work_order.pk}), "icon": "fa-file-alt"},
            ] if selected_work_order else [
                {"title": _("المبيعات"), "url": reverse("sale:sale_list"), "icon": "fa-shopping-cart"},
                {"title": _("عروض الأسعار"), "url": reverse("sale:quotation_list"), "icon": "fa-file-signature"},
            ]),
            {"title": _("إضافة عرض سعر"), "active": True, "icon": "fa-plus-circle"},
        ]
    }
    return render(request, "sale/quotation_form.html", context)


@login_required
@check_quotations_enabled
def quotation_edit(request, pk):
    if not request.user.has_perm('sale.change_quotation') and not request.user.is_superuser and not request.user.is_admin:
        return render(request, "core/permission_denied.html", {
            "title": _("غير مصرح"), "message": _("ليس لديك صلاحية لتعديل عروض الأسعار")
        })

    quotation = get_object_or_404(Quotation, pk=pk)
    
    # قفل التعديل إذا تحول أو قبل
    if quotation.converted_to_sale or quotation.status == 'accepted':
        messages.error(request, _("لا يمكن تعديل عرض السعر لأنه مقبول أو تم تحويله بالفعل إلى فاتورة بيع."))
        return redirect("sale:quotation_detail", pk=quotation.pk)

    if request.method == "POST":
        form = QuotationForm(request.POST, instance=quotation)
        if form.is_valid():
            try:
                with transaction.atomic():
                    quotation = form.save()

                    # مسح البنود السابقة وحفظ الجديدة
                    quotation.items.all().delete()

                    product_ids = request.POST.getlist("product[]")
                    quantities = request.POST.getlist("quantity[]")
                    unit_prices = request.POST.getlist("unit_price[]")
                    discounts = request.POST.getlist("discount[]")

                    subtotal = Decimal("0")
                    total_discount = Decimal("0")

                    for i in range(len(product_ids)):
                        if product_ids[i] and quantities[i] and unit_prices[i]:
                            prod_id = int(product_ids[i])
                            product = Product.objects.get(id=prod_id)
                            qty = Decimal(quantities[i])
                            price = Decimal(unit_prices[i].replace(',', ''))
                            if price <= 0:
                                raise ValueError(_("سعر المنتج يجب أن يكون أكبر من صفر (البند رقم {})").format(i + 1))
                            if qty <= 0:
                                raise ValueError(_("الكمية يجب أن تكون أكبر من صفر (البند رقم {})").format(i + 1))
                            item_disc = Decimal(discounts[i] if discounts[i] else '0')
                            item_total = (qty * price) - item_disc

                            QuotationItem.objects.create(
                                quotation=quotation,
                                product=product,
                                quantity=qty,
                                unit_price=price,
                                discount=item_disc,
                                total=item_total
                            )

                            subtotal += qty * price
                            total_discount += item_disc

                            # التحقق من إجمالي المخزون في جميع المخازن لإصدار تنبيه
                            from django.db.models import Sum
                            stock_sum = Stock.objects.filter(product=product, warehouse__is_active=True).aggregate(total_qty=Sum("quantity"))
                            stock_qty = stock_sum.get("total_qty") or 0
                            if not product.is_service and stock_qty < qty:
                                messages.warning(
                                    request,
                                    _("تنبيه: المنتج '{}' غير متوفر بالكمية المطلوبة في الفروع/المستودعات (المتوفر كلياً: {}، المطلوب: {})").format(
                                        product.name, stock_qty, qty
                                    )
                                )

                    # تحديث القيم
                    quotation.subtotal = subtotal
                    quotation.discount = total_discount
                    if quotation.tax_active:
                        default_tax_rate = Decimal(SystemSetting.get_setting('default_tax_rate', '14'))
                        quotation.tax = ((subtotal - total_discount) * default_tax_rate / 100).quantize(Decimal("0.01"))
                    else:
                        quotation.tax = Decimal("0")
                    quotation.total = subtotal - total_discount + quotation.tax
                    quotation.save()

                messages.success(request, _("تم تعديل عرض السعر بنجاح"))
                return redirect("sale:quotation_detail", pk=quotation.pk)

            except Exception as e:
                logger.error(f"Error editing quotation: {str(e)}")
                messages.error(request, _("حدث خطأ أثناء تعديل عرض السعر: {}").format(str(e)))
    else:
        form = QuotationForm(instance=quotation)

    customers = Customer.objects.filter(is_active=True).order_by('name')
    warehouses = Warehouse.objects.filter(is_active=True).order_by('name')
    products = Product.objects.filter(is_active=True).order_by('name')
    
    # جلب نوع البنود المسموح بها والتصنيفات للمودال
    from product.models import Category
    allowed_item_types = SystemSetting.get_setting('sale_invoice_item_types', 'both')
    
    category_filter = Q(is_active=True, products__is_active=True, products__is_bundle=False)
    if allowed_item_types == 'products':
        category_filter &= Q(products__is_service=False)
    elif allowed_item_types == 'services':
        category_filter &= Q(products__is_service=True)
        
    product_categories = Category.objects.filter(category_filter).distinct().order_by("name")

    # تهيئة البنود الحالية لواجهة الجافاسكريبت
    current_items = []
    for item in quotation.items.all():
        current_items.append({
            'product_id': item.product.id,
            'product_name': item.product.name,
            'quantity': float(item.quantity),
            'unit_price': float(item.unit_price),
            'discount': float(item.discount),
            'total': float(item.total),
            'is_service': item.product.is_service,
        })
    import json
    current_items_json = json.dumps(current_items)

    context = {
        "form": form,
        "quotation": quotation,
        "customers": customers,
        "warehouses": warehouses,
        "products": products,
        "current_items_json": current_items_json,
        "allowed_item_types": allowed_item_types,
        "product_categories": product_categories,
        "page_title": _("تعديل عرض سعر: {}").format(quotation.number),
        "page_subtitle": _("تعديل تفاصيل وعناصر عرض السعر القائم"),
        "page_icon": "fas fa-file-signature",
        "active_menu": "sales",
        "breadcrumb_items": [
            {"title": _("الرئيسية"), "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": _("المبيعات"), "url": reverse("sale:sale_list"), "icon": "fas fa-shopping-cart"},
            {"title": _("عروض الأسعار"), "url": reverse("sale:quotation_list")},
            {"title": quotation.number, "url": reverse("sale:quotation_detail", kwargs={"pk": quotation.pk})},
            {"title": _("تعديل"), "active": True},
        ]
    }
    return render(request, "sale/quotation_form.html", context)


@login_required
@check_quotations_enabled
def quotation_detail(request, pk):
    if not request.user.has_perm('sale.view_quotation') and not request.user.is_superuser and not request.user.is_admin:
        return render(request, "core/permission_denied.html", {
            "title": _("غير مصرح"), "message": _("ليس لديك صلاحية لعرض تفاصيل عروض الأسعار")
        })

    quotation = get_object_or_404(Quotation, pk=pk)
    items = quotation.items.all()

    # شارات الهيدر
    header_badges = [
        {"text": quotation.number, "class": "bg-primary", "icon": "fas fa-hashtag"},
        {"text": quotation.get_status_display(), "class": f"bg-{get_status_color(quotation.status)}", "icon": "fas fa-info-circle"}
    ]
    if quotation.converted_to_sale:
        header_badges.append({
            "text": _("محول لفاتورة: {}").format(quotation.converted_to_sale.number),
            "class": "bg-success",
            "icon": "fas fa-link",
            "url": reverse("sale:sale_detail", kwargs={"pk": quotation.converted_to_sale.pk})
        })

    # أزرار الهيدر
    header_buttons = [
        {
            "url": reverse("sale:quotation_print", kwargs={"pk": quotation.pk}),
            "icon": "fa-print",
            "text": _("طباعة"),
            "class": "btn-outline-secondary",
            "target": "_blank",
        }
    ]
    if not quotation.converted_to_sale:
        header_buttons.append({
            "url": "#",
            "icon": "fa-ellipsis-v",
            "text": "",
            "class": "btn-outline-secondary",
            "id": "actions-menu-btn",
            "toggle": "modal",
            "target": "#actionsModal",
        })

    context = {
        "quotation": quotation,
        "items": items,
        "warehouses": Warehouse.objects.filter(is_active=True).order_by('name'),
        "page_title": quotation.number,
        "page_subtitle": _("تفاصيل عرض السعر للعميل والبنود والكميات"),
        "page_icon": "fas fa-file-signature",
        "header_badges": header_badges,
        "header_buttons": header_buttons,
        "active_menu": "sales",
        "breadcrumb_items": [
            {"title": _("الرئيسية"), "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": _("المبيعات"), "url": reverse("sale:sale_list"), "icon": "fas fa-shopping-cart"},
            {"title": _("عروض الأسعار"), "url": reverse("sale:quotation_list")},
            {"title": quotation.number, "active": True},
        ]
    }
    return render(request, "sale/quotation_detail.html", context)


@login_required
@check_quotations_enabled
def quotation_delete(request, pk):
    if not request.user.has_perm('sale.delete_quotation') and not request.user.is_superuser and not request.user.is_admin:
        return render(request, "core/permission_denied.html", {
            "title": _("غير مصرح"), "message": _("ليس لديك صلاحية لحذف عروض الأسعار")
        })

    quotation = get_object_or_404(Quotation, pk=pk)
    
    if quotation.converted_to_sale:
        messages.error(request, _("لا يمكن حذف عرض السعر لأنه تم تحويله إلى فاتورة بيع بالفعل."))
        return redirect("sale:quotation_detail", pk=quotation.pk)

    if request.method == "POST":
        quotation.delete()
        messages.success(request, _("تم حذف عرض السعر بنجاح"))
        return redirect("sale:quotation_list")

    context = {
        "quotation": quotation,
        "page_title": _("حذف عرض السعر: {}").format(quotation.number),
        "page_icon": "fas fa-trash-alt",
        "breadcrumb_items": [
            {"title": _("الرئيسية"), "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": _("عروض الأسعار"), "url": reverse("sale:quotation_list")},
            {"title": quotation.number, "url": reverse("sale:quotation_detail", kwargs={"pk": quotation.pk})},
            {"title": _("حذف"), "active": True},
        ]
    }
    return render(request, "sale/quotation_confirm_delete.html", context)


@login_required
@check_quotations_enabled
def quotation_print(request, pk):
    if not request.user.has_perm('sale.view_quotation') and not request.user.is_superuser and not request.user.is_admin:
        return render(request, "core/permission_denied.html", {
            "title": _("غير مصرح"), "message": _("ليس لديك صلاحية لعرض أو طباعة عروض الأسعار")
        })

    quotation = get_object_or_404(Quotation, pk=pk)
    items = quotation.items.all()
    
    # جلب إعدادات الشركة
    company_name = SystemSetting.objects.filter(key="company_name").values_list("value", flat=True).first() or "مؤسسة موهبة"
    company_address = SystemSetting.objects.filter(key="company_address").values_list("value", flat=True).first() or ""
    company_phone = SystemSetting.objects.filter(key="company_phone").values_list("value", flat=True).first() or ""
    company_tax_number = SystemSetting.objects.filter(key="company_tax_number").values_list("value", flat=True).first() or ""
    company_logo = SystemSetting.objects.filter(key="company_logo").values_list("value", flat=True).first() or ""
    company_email = SystemSetting.objects.filter(key="company_email").values_list("value", flat=True).first() or ""
    company_website = SystemSetting.objects.filter(key="company_website").values_list("value", flat=True).first() or ""

    context = {
        "quotation": quotation,
        "items": items,
        "company_name": company_name,
        "company_address": company_address,
        "company_phone": company_phone,
        "company_tax_number": company_tax_number,
        "company_logo": company_logo,
        "company_email": company_email,
        "company_website": company_website,
        "title": f"عرض سعر - {quotation.number}",
    }
    return render(request, "sale/quotation_print.html", context)


@login_required
@check_quotations_enabled
def quotation_convert_to_sale(request, pk):
    if not request.user.has_perm('sale.convert_quotation') and not request.user.is_superuser and not request.user.is_admin:
        return render(request, "core/permission_denied.html", {
            "title": _("غير مصرح"), "message": _("ليس لديك صلاحية لتحويل عروض الأسعار")
        })

    quotation = get_object_or_404(Quotation, pk=pk)

    if quotation.converted_to_sale:
        messages.error(request, _("تم تحويل عرض السعر هذا بالفعل لفاتورة رقم: {}").format(quotation.converted_to_sale.number))
        return redirect("sale:quotation_detail", pk=quotation.pk)

    try:
        with transaction.atomic():
            # تحضير بيانات الفاتورة
            warehouse_id = request.POST.get('warehouse')
            if not warehouse_id:
                active_wh = Warehouse.objects.filter(is_active=True).first()
                warehouse_id = active_wh.id if active_wh else None
            
            if not warehouse_id:
                raise ValueError(_("يرجى تحديد المخزن لإصدار الفاتورة."))

            sale_data = {
                'date': timezone.now().date(),
                'customer_id': quotation.customer.id,
                'warehouse_id': int(warehouse_id),
                'discount': quotation.discount,
                'tax': quotation.tax,
                'notes': quotation.notes or '',
                'payment_method': 'credit',  # آجل كافتراضي
                'items': []
            }

            for item in quotation.items.all():
                sale_data['items'].append({
                    'product_id': item.product.id,
                    'quantity': item.quantity,
                    'unit_price': item.unit_price,
                    'discount': item.discount
                })

            # إنشاء الفاتورة من خلال SaleService
            sale = SaleService.create_sale(data=sale_data, user=request.user)

            # ربط المستندات متبادلاً
            sale.quotation = quotation
            sale.save()

            quotation.converted_to_sale = sale
            quotation.status = 'accepted'
            quotation.save()

        messages.success(request, _("تم تحويل عرض السعر بنجاح إلى فاتورة مبيعات رقم {}").format(sale.number))
        return redirect("sale:sale_detail", pk=sale.pk)

    except Exception as e:
        logger.error(f"Error converting quotation to sale: {str(e)}")
        messages.error(request, _("حدث خطأ أثناء تحويل عرض السعر لفاتورة: {}").format(str(e)))
        return redirect("sale:quotation_detail", pk=quotation.pk)


@login_required
@check_quotations_enabled
def check_product_stock(request):
    product_id = request.GET.get('product_id')
    warehouse_id = request.GET.get('warehouse_id')
    if not product_id:
        return JsonResponse({'available_qty': 0, 'price': 0, 'is_service': False})
    try:
        product = Product.objects.get(id=product_id)
        available_qty = 0
        if warehouse_id:
            stock = Stock.objects.filter(product_id=product_id, warehouse_id=warehouse_id).first()
            available_qty = stock.quantity if stock else 0
        return JsonResponse({
            'available_qty': float(available_qty),
            'price': float(product.selling_price),
            'is_service': product.is_service
        })
    except Exception:
        return JsonResponse({'available_qty': 0, 'price': 0, 'is_service': False})


def get_status_color(status):
    colors = {
        'draft': 'secondary',
        'sent': 'info',
        'accepted': 'success',
        'rejected': 'danger',
        'expired': 'warning'
    }
    return colors.get(status, 'secondary')
