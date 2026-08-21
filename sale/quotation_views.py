import json
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

    quotations_qs = Quotation.objects.with_list_details().all().order_by('-date', '-number')

    if search:
        quotations_qs = quotations_qs.filter(
            Q(number__icontains=search) |
            Q(customer__name__icontains=search) |
            Q(notes__icontains=search)
        )
    salesman_id = request.GET.get('salesman', '')
    if customer_id:
        quotations_qs = quotations_qs.filter(customer_id=customer_id)
    if salesman_id:
        quotations_qs = quotations_qs.filter(Q(salesman_id=salesman_id) | Q(created_by_id=salesman_id))
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
    from django.contrib.auth import get_user_model
    User = get_user_model()
    salesmen = User.objects.filter(is_active=True).order_by('first_name', 'username')
    
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
        "salesmen": salesmen,
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
        form = QuotationForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                with transaction.atomic():
                    quotation = form.save(commit=False)
                    quotation.created_by = request.user
                    if not quotation.salesman_id:
                        quotation.salesman = request.user
                    quotation.custom_fields = SaleService.parse_custom_fields(request.POST.get('custom_fields_json', '[]'))
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
                            item_disc = Decimal(discounts[i]) if i < len(discounts) and discounts[i] else Decimal("0")
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
                                    _("تنبيه: المنتج '{}' غير متوفر بالكمية المطلوبة في الفروع/المخازن (المتوفر كلياً: {}، المطلوب: {})").format(
                                        product.name, stock_qty, qty
                                    )
                                )

                    # تحديث قيم الإجماليات والعملة
                    quotation.subtotal = subtotal
                    quotation.discount = total_discount
                    if quotation.tax_active:
                        default_tax_rate = Decimal(SystemSetting.get_setting('default_tax_rate', '14'))
                        quotation.tax = ((subtotal - total_discount) * default_tax_rate / 100).quantize(Decimal("0.01"))
                    else:
                        quotation.tax = Decimal("0")
                    quotation.total = subtotal - total_discount + quotation.tax

                    currency_id = request.POST.get("currency")
                    if currency_id:
                        from financial.models import Currency
                        curr_obj = Currency.objects.filter(id=currency_id).first() if str(currency_id).isdigit() else Currency.objects.filter(code=currency_id).first()
                        if curr_obj:
                            quotation.currency = curr_obj
                    elif quotation.customer and quotation.customer.default_currency:
                        quotation.currency = quotation.customer.default_currency

                    if quotation.currency and not quotation.currency.is_functional:
                        from financial.services.exchange_rate_service import ExchangeRateService
                        posted_rate = request.POST.get("exchange_rate")
                        sys_rate = Decimal(str(posted_rate or ExchangeRateService.get_exchange_rate(quotation.currency) or 1.0))
                        quotation.exchange_rate = sys_rate
                        quotation.total_foreign = quotation.total
                        quotation.total_functional = (quotation.total * sys_rate).quantize(Decimal("0.01"))
                    else:
                        quotation.exchange_rate = Decimal("1.000000")
                        quotation.total_foreign = Decimal("0.00")
                        quotation.total_functional = quotation.total

                    quotation.save()

                messages.success(request, _("تم إنشاء عرض السعر بنجاح"))
                return redirect("sale:quotation_detail", pk=quotation.pk)

            except Exception as e:
                logger.error(f"Error creating quotation: {str(e)}")
                messages.error(request, _("حدث خطأ أثناء حفظ عرض السعر: {}").format(str(e)))
    else:
        default_quote_notes = SystemSetting.get_setting('default_quotation_notes', '')
        if not default_quote_notes:
            default_quote_notes = SystemSetting.get_setting('default_sale_invoice_notes', '')
        initial_data = {
            "notes": default_quote_notes
        }
        if selected_customer:
            initial_data["customer"] = selected_customer
            if selected_customer.default_currency:
                initial_data["currency"] = selected_customer.default_currency.pk
        if selected_work_order:
            initial_data["work_order"] = selected_work_order
        form = QuotationForm(initial=initial_data, user=request.user)

    from financial.models import Currency
    currencies = Currency.objects.filter(is_active=True).order_by("code")
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

    # معاينة الرقم القادم للعرض بدون حجز
    next_quotation_number = None
    try:
        from core.services.sequence_service import SequenceService
        from core.enums.document_types import DocumentType
        next_quotation_number = SequenceService.peek_next_number(DocumentType.SALES_ORDER)
    except Exception as e:
        logger.error(f"Error generating next quotation number: {str(e)}")

    custom_fields_merged = SaleService.smart_merge_custom_fields('quotation', [])
    context = {
        "form": form,
        "customers": customers,
        "warehouses": warehouses,
        "products": products,
        "currencies": currencies,
        "selected_customer": selected_customer,
        "default_warehouse": warehouses.first() if warehouses.exists() else None,
        "next_quotation_number": next_quotation_number,
        "custom_fields_json": json.dumps(custom_fields_merged),
        "custom_fields_display_mode": SystemSetting.get_setting('custom_fields_display_mode', 'expanded'),
        "enable_custom_fields": SystemSetting.get_setting('enable_custom_fields', 'true'),
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
        form = QuotationForm(request.POST, instance=quotation, user=request.user)
        if form.is_valid():
            try:
                with transaction.atomic():
                    quotation = form.save(commit=False)
                    quotation.custom_fields = SaleService.parse_custom_fields(request.POST.get('custom_fields_json', '[]'))
                    quotation.save()

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
                                    _("تنبيه: المنتج '{}' غير متوفر بالكمية المطلوبة في الفروع/المخازن (المتوفر كلياً: {}، المطلوب: {})").format(
                                        product.name, stock_qty, qty
                                    )
                                )

                    # تحديث القيم والعملة
                    quotation.subtotal = subtotal
                    quotation.discount = total_discount
                    if quotation.tax_active:
                        default_tax_rate = Decimal(SystemSetting.get_setting('default_tax_rate', '14'))
                        quotation.tax = ((subtotal - total_discount) * default_tax_rate / 100).quantize(Decimal("0.01"))
                    else:
                        quotation.tax = Decimal("0")
                    quotation.total = subtotal - total_discount + quotation.tax

                    currency_id = request.POST.get("currency")
                    if currency_id:
                        from financial.models import Currency
                        curr_obj = Currency.objects.filter(id=currency_id).first() if str(currency_id).isdigit() else Currency.objects.filter(code=currency_id).first()
                        if curr_obj:
                            quotation.currency = curr_obj
                    elif quotation.customer and quotation.customer.default_currency:
                        quotation.currency = quotation.customer.default_currency

                    if quotation.currency and not quotation.currency.is_functional:
                        from financial.services.exchange_rate_service import ExchangeRateService
                        posted_rate = request.POST.get("exchange_rate")
                        sys_rate = Decimal(str(posted_rate or ExchangeRateService.get_exchange_rate(quotation.currency) or 1.0))
                        quotation.exchange_rate = sys_rate
                        quotation.total_foreign = quotation.total
                        quotation.total_functional = (quotation.total * sys_rate).quantize(Decimal("0.01"))
                    else:
                        quotation.exchange_rate = Decimal("1.000000")
                        quotation.total_foreign = Decimal("0.00")
                        quotation.total_functional = quotation.total

                    quotation.save()

                messages.success(request, _("تم تعديل عرض السعر بنجاح"))
                return redirect("sale:quotation_detail", pk=quotation.pk)

            except Exception as e:
                logger.error(f"Error editing quotation: {str(e)}")
                messages.error(request, _("حدث خطأ أثناء تعديل عرض السعر: {}").format(str(e)))
    else:
        form = QuotationForm(instance=quotation, user=request.user)

    from financial.models import Currency
    currencies = Currency.objects.filter(is_active=True).order_by("code")
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
    custom_fields_merged = SaleService.smart_merge_custom_fields('quotation', quotation.custom_fields)

    context = {
        "form": form,
        "quotation": quotation,
        "customers": customers,
        "warehouses": warehouses,
        "products": products,
        "currencies": currencies,
        "current_items_json": current_items_json,
        "custom_fields_json": json.dumps(custom_fields_merged),
        "custom_fields_display_mode": SystemSetting.get_setting('custom_fields_display_mode', 'expanded'),
        "enable_custom_fields": SystemSetting.get_setting('enable_custom_fields', 'true'),
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

    quotation = get_object_or_404(Quotation.objects.with_details(), pk=pk)
    items = quotation.items.all()

    # شارات الهيدر
    header_badges = [
        {"text": quotation.number, "class": "bg-primary", "icon": "fas fa-hashtag"},
        {"text": quotation.get_status_display(), "class": f"bg-{get_status_color(quotation.status)}", "icon": "fas fa-info-circle"}
    ]
    if hasattr(quotation, 'work_order') and quotation.work_order:
        header_badges.append({
            "text": quotation.work_order.number,
            "class": "bg-info text-white",
            "icon": "fas fa-tasks",
            "url": reverse("work_order:work_order_detail", kwargs={"pk": quotation.work_order.pk})
        })
    if quotation.converted_to_sale:
        header_badges.append({
            "text": _("محول لفاتورة: {}").format(quotation.converted_to_sale.number),
            "class": "bg-success",
            "icon": "fas fa-link",
            "url": reverse("sale:sale_detail", kwargs={"pk": quotation.converted_to_sale.pk})
        })

    # أزرار الهيدر
    header_buttons = []
    if hasattr(quotation, 'work_order') and quotation.work_order:
        header_buttons.append({
            "url": reverse("work_order:work_order_detail", kwargs={"pk": quotation.work_order.pk}),
            "icon": "fa-tasks",
            "text": _("عرض أمر الشغل"),
            "class": "btn-outline-info",
        })

    header_buttons.extend([
        *([{
            "url": reverse("sale:quotation_edit", kwargs={"pk": quotation.pk}),
            "icon": "fa-edit",
            "text": _("تعديل"),
            "class": "btn-outline-secondary",
        }] if not quotation.converted_to_sale else []),
        {
            "url": reverse("sale:quotation_print", kwargs={"pk": quotation.pk}),
            "icon": "fa-print",
            "text": _("طباعة"),
            "class": "btn-info",
            "target": "_blank",
        },
        {
            "dropdown": True,
            "icon": "fa-file-pdf",
            "text": _("مشاركة"),
            "class": "btn-success",
            "items": [
                {
                    "onclick": f"downloadDocumentPDF('{reverse('sale:quotation_pdf_download', kwargs={'pk': quotation.pk})}', '{reverse('sale:quotation_print', kwargs={'pk': quotation.pk})}', '{quotation.number}')",
                    "icon": "fas fa-file-download text-primary",
                    "text": _("تحميل PDF")
                },
                {
                    "onclick": f"shareWhatsAppPDF('{quotation.customer.phone if quotation.customer and quotation.customer.phone else ''}', '{quotation.number}', 'عرض سعر', '{reverse('sale:quotation_pdf_download', kwargs={'pk': quotation.pk})}', '{reverse('sale:quotation_print', kwargs={'pk': quotation.pk})}')",
                    "icon": "fab fa-whatsapp text-success",
                    "text": _("إرسال واتساب")
                },
                {
                    "onclick": f"sendEmailPDF('{reverse('sale:quotation_email_pdf', kwargs={'pk': quotation.pk})}', '{quotation.customer.email if quotation.customer and quotation.customer.email else ''}', '{quotation.number}', 'عرض سعر', '{reverse('sale:quotation_pdf_download', kwargs={'pk': quotation.pk})}', '{reverse('sale:quotation_print', kwargs={'pk': quotation.pk})}')",
                    "icon": "far fa-envelope text-primary",
                    "text": _("إرسال بريد")
                }
            ]
        }
    ])
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
        "title": _("عرض سعر {}").format(quotation.number),
        "page_title": _("عرض سعر {}").format(quotation.number),
        "page_subtitle": _('العميل: <a href="{}" class="text-decoration-none fw-bold text-primary"><i class="fas fa-user-tie me-1"></i>{}</a>').format(
            reverse("client:customer_detail", kwargs={"pk": quotation.customer.id}),
            quotation.customer.name
        ),
        "page_icon": "fas fa-file-signature",
        "header_badges": header_badges,
        "header_buttons": header_buttons,
        "active_menu": "sales",
        "breadcrumb_items": [
            {"title": _("الرئيسية"), "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            *([
                {"title": _("أوامر الشغل"), "url": reverse("work_order:work_order_list"), "icon": "fas fa-tasks"},
                {"title": _("أمر شغل {}").format(quotation.work_order.number), "url": reverse("work_order:work_order_detail", kwargs={"pk": quotation.work_order.pk})},
            ] if hasattr(quotation, 'work_order') and quotation.work_order else [
                {"title": _("المبيعات"), "url": reverse("sale:sale_list"), "icon": "fas fa-shopping-cart"},
                {"title": _("عروض الأسعار"), "url": reverse("sale:quotation_list")},
            ]),
            {"title": _("عرض سعر {}").format(quotation.number), "active": True},
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


def get_quotation_print_context(request, pk):
    quotation = get_object_or_404(Quotation, pk=pk)
    items = quotation.items.all().select_related('product', 'product__unit', 'product__category')
    from core.models import SystemSetting
    
    default_lang = SystemSetting.get_default_print_language()
    print_lang = request.GET.get('lang', default_lang).lower()
    if print_lang not in ['ar', 'en']:
        print_lang = 'ar'
    
    is_english = (print_lang == 'en')
    is_bilingual = False
    print_dir = 'ltr' if is_english else 'rtl'

    company_name = SystemSetting.objects.filter(key="company_name").values_list("value", flat=True).first() or "مؤسسة موهبة"
    company_address = SystemSetting.objects.filter(key="company_address").values_list("value", flat=True).first() or ""
    company_phone = SystemSetting.objects.filter(key="company_phone").values_list("value", flat=True).first() or ""
    company_tax_number = SystemSetting.objects.filter(key="company_tax_number").values_list("value", flat=True).first() or ""
    company_logo = SystemSetting.objects.filter(key="company_logo").values_list("value", flat=True).first() or ""
    company_email = SystemSetting.objects.filter(key="company_email").values_list("value", flat=True).first() or ""
    company_website = SystemSetting.objects.filter(key="company_website").values_list("value", flat=True).first() or ""

    if is_english:
        company_name_active = SystemSetting.get_setting('company_name_en') or SystemSetting.get_setting('site_name_en') or company_name
        company_address_active = SystemSetting.get_company_address_en() or company_address
        invoice_title_active = SystemSetting.get_invoice_title_quotation_en()
        default_notes = SystemSetting.get_quotation_notes_en()
        currency_symbol_active = quotation.currency if (hasattr(quotation, 'currency') and quotation.currency and quotation.currency != 'ج.م') else SystemSetting.get_currency_symbol_en()
        status_map = {
            'draft': 'DRAFT',
            'sent': 'SENT',
            'approved': 'APPROVED',
            'rejected': 'REJECTED',
            'expired': 'EXPIRED',
            'converted': 'CONVERTED'
        }
    elif is_bilingual:
        company_name_en = SystemSetting.get_setting('company_name_en') or SystemSetting.get_setting('site_name_en') or ''
        company_name_active = f"{company_name} / {company_name_en}" if company_name_en else company_name
        company_address_active = company_address
        invoice_title_active = "عرض سعر / Quotation"
        default_notes = SystemSetting.get_setting('default_quotation_notes', '')
        currency_symbol_active = getattr(quotation, 'currency', None) or SystemSetting.get_currency_symbol()
        status_map = {
            'draft': 'مسودة / DRAFT',
            'sent': 'تم الإرسال / SENT',
            'approved': 'مقبول / APPROVED',
            'rejected': 'مرفوض / REJECTED',
            'expired': 'منتهي / EXPIRED',
            'converted': 'تم التحويل / CONVERTED'
        }
    else:
        company_name_active = company_name
        company_address_active = company_address
        invoice_title_active = "عرض سعر"
        default_notes = SystemSetting.get_setting('default_quotation_notes', '')
        currency_symbol_active = getattr(quotation, 'currency', None) or SystemSetting.get_currency_symbol()
        status_map = {
            'draft': 'مسودة',
            'sent': 'تم الإرسال',
            'approved': 'مقبول',
            'rejected': 'مرفوض',
            'expired': 'منتهي',
            'converted': 'تم التحويل'
        }

    status_code = getattr(quotation, 'status', 'draft')
    translated_status = status_map.get(str(status_code).lower(), str(status_code))

    context = {
        "quotation": quotation,
        "items": items,
        "company_name": company_name_active,
        "company_address": company_address_active,
        "company_phone": company_phone,
        "company_tax_number": company_tax_number,
        "company_logo": company_logo,
        "company_email": company_email,
        "company_website": company_website,
        "title": f"{invoice_title_active} - {quotation.number}",
        "document_title": invoice_title_active,
        "print_lang": print_lang,
        "print_dir": print_dir,
        "is_english": is_english,
        "is_bilingual": is_bilingual,
        "currency_symbol_active": currency_symbol_active,
        "default_notes": default_notes,
        "translated_status": translated_status,
        "has_item_discounts": quotation.has_item_discounts,
        "salesman_name": quotation.salesman_display_name,
    }
    return quotation, context


@login_required
def quotation_print(request, pk):
    """
    طباعة عرض السعر (عربي / إنجليزي / ثنائي اللغة)
    """
    quotation, context = get_quotation_print_context(request, pk)
    return render(request, "sale/quotation_print.html", context)


@login_required
def quotation_pdf_download(request, pk):
    """
    تصدير/تنزيل عرض سعر مباشرة كـ PDF بنسق نقي
    """
    from django.template.loader import render_to_string
    from utils.pdf_utils import generate_pdf_from_html, generate_guaranteed_pdf_response
    
    quotation, context = get_quotation_print_context(request, pk)
    
    try:
        html_content = render_to_string("sale/quotation_print.html", context, request=request)
        pdf_response = generate_pdf_from_html(html_content, request=request, filename=f"{quotation.number}.pdf", doc_type="quotation", context=context)
        
        if pdf_response:
            return pdf_response
    except Exception as e:
        logger.error(f"Quotation PDF generation error for {quotation.number}: {e}")
        
    return generate_guaranteed_pdf_response("quotation", context, filename=f"{quotation.number}.pdf")


@login_required
def quotation_email_pdf(request, pk):
    """
    إرسال عرض السعر عبر البريد الإلكتروني للعميل مباشرة
    """
    from django.http import JsonResponse
    quotation = get_object_or_404(Quotation, pk=pk)
    customer_email = quotation.customer.email if quotation.customer and quotation.customer.email else None
    if not customer_email:
        return JsonResponse({'success': False, 'message': 'لا يوجد بريد إلكتروني مسجل للعميل'}, status=400)
    
    try:
        from utils.email_utils import send_email
        subject = f"عرض سعر #{quotation.number}"
        body = f"مرحباً {quotation.customer.name}،\n\nيرجى الاطلاع على عرض السعر الخاص بكم رقم #{quotation.number}.\n\nرابط عرض السعر المباشر:\n{request.build_absolute_uri(reverse('sale:quotation_print', kwargs={'pk': quotation.pk}))}\n\nشكراً لتعاملكم معنا."
        send_email(subject, body, [customer_email])
        return JsonResponse({'success': True, 'message': 'تم إرسال البريد بنجاح!'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


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

            # التحقق الفعلي من توفر الرصيد المخزني لجميع البنود قبل التحويل
            from product.models import Stock
            insufficient_items = []
            for item in quotation.items.all():
                if not item.product.is_service and not item.product.is_bundle:
                    stock_rec = Stock.objects.filter(product_id=item.product.id, warehouse_id=int(warehouse_id)).first()
                    current_stock = stock_rec.quantity if stock_rec else Decimal("0")
                    if current_stock < item.quantity:
                        req_val = item.quantity
                        req_fmt = f"{req_val:.0f}" if req_val % 1 == 0 else f"{req_val:.2f}"
                        curr_fmt = f"{current_stock:.0f}" if current_stock % 1 == 0 else f"{current_stock:.2f}"
                        insufficient_items.append(f"• {item.product.name} (المطلوب: {req_fmt} | المتوفر: {curr_fmt})")
            
            if insufficient_items:
                msg_body = "تعذر تحويل عرض السعر لفاتورة: الكمية المتاحة في المخزن المحدد لا تكفي لتغطية الكميات المطلوبة في الفاتورة.<br>يرجى اختيار مخزن آخر به كميات كافية أو إضافة رصيد مخزني أولاً.<br><br><b>البنود التي بها عجز:</b><br>" + "<br>".join(insufficient_items)
                messages.error(request, msg_body)
                return redirect("sale:quotation_detail", pk=quotation.pk)

            from financial.services.exchange_rate_service import ExchangeRateService
            current_rate = Decimal("1.000000")
            if quotation.currency and not quotation.currency.is_functional:
                current_rate = Decimal(str(ExchangeRateService.get_exchange_rate(quotation.currency) or quotation.exchange_rate or 1.0))

            sale_data = {
                'date': timezone.now().date(),
                'customer_id': quotation.customer.id,
                'warehouse_id': int(warehouse_id),
                'salesman': quotation.salesman or quotation.created_by,
                'discount': quotation.discount,
                'adjustment_name': getattr(quotation, 'adjustment_name', ''),
                'adjustment_amount': getattr(quotation, 'adjustment_amount', Decimal("0.00")),
                'tax': quotation.tax,
                'tax_active': getattr(quotation, 'tax_active', True),
                'vat_active': getattr(quotation, 'vat_active', True),
                'vat_rate': getattr(quotation, 'vat_rate', Decimal("14.00")),
                'wht_active': getattr(quotation, 'wht_active', False),
                'wht_rate': getattr(quotation, 'wht_rate', Decimal("1.00")),
                'wht_amount': getattr(quotation, 'wht_amount', Decimal("0.00")),
                'notes': quotation.notes or '',
                'currency_id': quotation.currency_id if hasattr(quotation, 'currency_id') and quotation.currency_id else None,
                'exchange_rate': current_rate,
                'payment_method': 'credit',  # آجل كافتراضي
                'custom_fields': SaleService.smart_merge_custom_fields('sale', quotation.custom_fields),
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

            # ربط المستندات متبادلاً مع حفظ لقطات المقارنة المالية
            sale.quotation = quotation
            if hasattr(sale, 'source_quotation_rate'):
                sale.source_quotation_rate = quotation.exchange_rate
            if hasattr(sale, 'source_quotation_base_snapshot'):
                sale.source_quotation_base_snapshot = quotation.total
            sale.save()

            # إنشاء السعر الاسترشادي المبدئي للمنتجات بالعملة الأجنبية عند الاعتماد والتحويل الفعلي فقط
            if quotation.currency and not quotation.currency.is_functional:
                from product.services.indicative_price_service import IndicativePriceService
                for item in quotation.items.all():
                    if item.unit_price > Decimal("0"):
                        IndicativePriceService.create_if_missing(
                            product=item.product,
                            currency=quotation.currency,
                            price=item.unit_price,
                            price_type='selling',
                            user=request.user
                        )

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
