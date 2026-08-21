"""
Purchase Invoice Views
عرض وإدارة فواتير المشتريات
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from django.urls import reverse
from django.core.paginator import Paginator
from django.db.models import Sum
from decimal import Decimal
import logging

from purchase.models import Purchase, PurchasePayment, PurchaseItem
from purchase.forms import PurchaseForm
from product.models import Product, Warehouse
from supplier.models import Supplier
from core.models import SystemSetting

logger = logging.getLogger(__name__)


@login_required
def purchase_list(request):
    """
    عرض قائمة فواتير المشتريات
    """
    purchases_query = Purchase.objects.with_list_details().all().order_by("-date", "-id")

    # تصفية حسب المورد
    supplier = request.GET.get("supplier")
    if supplier:
        purchases_query = purchases_query.filter(supplier_id=supplier)

    # تصفية حسب المخزن
    warehouse = request.GET.get("warehouse")
    if warehouse:
        purchases_query = purchases_query.filter(warehouse_id=warehouse)

    # تصفية حسب حالة الدفع
    payment_status = request.GET.get("payment_status")
    if payment_status:
        purchases_query = purchases_query.filter(payment_status=payment_status)
    
    # تصفية حسب نوع الفاتورة (خدمة/منتج)
    is_service = request.GET.get("is_service")
    if is_service == "true":
        purchases_query = purchases_query.filter(is_service=True)
    elif is_service == "false":
        purchases_query = purchases_query.filter(is_service=False)
    
    # تصفية حسب نوع الخدمة
    service_type = request.GET.get("service_type")
    if service_type:
        purchases_query = purchases_query.filter(service_type=service_type)

    # تصفية حسب التاريخ
    date_from = request.GET.get("date_from")
    if date_from:
        purchases_query = purchases_query.filter(date__gte=date_from)

    date_to = request.GET.get("date_to")
    if date_to:
        purchases_query = purchases_query.filter(date__lte=date_to)

    # التصدير المزدوج: تصدير كافة فواتير المشتريات المفلترة من الباك إند
    if request.GET.get('export') == 'excel':
        from utils.export import export_queryset_to_excel
        return export_queryset_to_excel(
            purchases_query,
            filename="purchase_invoices_export.xlsx",
            fields=["number", "created_at", "supplier.name", "total", "amount_paid", "amount_due", "payment_status"],
            headers=["رقم الفاتورة", "التاريخ", "المورد", "الإجمالي", "المدفوع", "المتبقي", "حالة الدفع"]
        )

    # Whitelist الفرز الأمني
    allowed_sort_fields = {
        'number': 'number',
        'created_at': 'created_at',
        'supplier.name': 'supplier__name',
        'warehouse.name': 'warehouse__name',
        'total': 'total',
        'amount_due': 'amount_due',
        'payment_status': 'payment_status',
    }

    # الترقيم والفرز الـ SSR عبر المحرك المركزي
    from core.utils import paginate_queryset, render_paginated_response
    pagination_data = paginate_queryset(
        purchases_query,
        request,
        default_per_page=25,
        allowed_sort_fields=allowed_sort_fields
    )

    purchases = pagination_data['page_obj']

    # إحصائيات للعرض في الصفحة
    paid_purchases_count = Purchase.objects.filter(payment_status="paid").count()
    partially_paid_purchases_count = Purchase.objects.filter(
        payment_status="partially_paid"
    ).count()
    unpaid_purchases_count = Purchase.objects.filter(payment_status="unpaid").count()

    # عدد الفواتير المرتجعة
    returned_purchases_count = (
        Purchase.objects.filter(returns__status="confirmed").distinct().count()
    )

    # إجمالي المشتريات
    total_amount = Purchase.objects.aggregate(Sum("total"))["total__sum"] or 0
    
    # إحصائيات الخدمات
    services_count = Purchase.objects.filter(is_service=True).count()
    products_count = Purchase.objects.filter(is_service=False).count()
    courses_count = Purchase.objects.filter(service_type='course').count()

    # الحصول على قائمة الموردين للفلترة
    suppliers = Supplier.objects.filter(is_active=True).order_by("name")

    # تعريف عناوين أعمدة الجدول
    purchase_headers = [
        {
            "key": "number",
            "label": _("رقم الفاتورة"),
            "sortable": True,
            "class": "text-center",
            "format": "reference",
            "variant": "highlight-code",
            "app": "purchase",
        },
        {
            "key": "created_at",
            "label": _("التاريخ والوقت"),
            "sortable": True,
            "class": "text-center",
            "format": "datetime_12h",
        },
        {"key": "supplier.name", "label": _("المورد"), "sortable": True, "class": "fw-bold"},
        {"key": "warehouse.name", "label": _("المخزن"), "sortable": True},
        {
            "key": "total",
            "label": _("الإجمالي"),
            "sortable": True,
            "class": "text-center",
            "format": "currency",
            "decimals": 2,
        },
        {
            "key": "amount_due",
            "label": _("المتبقي"),
            "sortable": True,
            "class": "text-center",
            "format": "currency",
            "variant": "text-danger",
        },

        {
            "key": "payment_status",
            "label": _("حالة الدفع"),
            "sortable": True,
            "class": "text-center",
            "format": "status",
        },

        {
            "key": "actions",
            "label": _(u"الإجراءات"),
            "sortable": False,
            "class": "text-center text-nowrap",
            "width": "1%",
        },
    ]

    # تحضير بيانات الجدول
    table_data = []
    for purchase in purchases:
        actions = []
        actions.append({
            'url': reverse('purchase:purchase_detail', args=[purchase.pk]),
            'icon': 'fa-eye',
            'label': 'عرض التفاصيل',
            'class': 'action-view',
        })
        if purchase.payment_status != 'paid':
            actions.append({
                'url': reverse('purchase:purchase_add_payment', args=[purchase.pk]),
                'icon': 'fa-money-bill-wave',
                'label': 'إضافة دفعة',
                'class': 'action-paid',
            })
        if purchase.payment_status == 'paid':
            actions.append({
                'url': reverse('purchase:purchase_print', args=[purchase.pk]),
                'icon': 'fa-print',
                'label': 'طباعة',
                'class': 'action-print',
                'target': '_blank',
            })
        actions.append({
            'url': reverse('purchase:purchase_duplicate', args=[purchase.pk]),
            'icon': 'fa-copy',
            'label': 'نسخ الفاتورة',
            'class': 'action-copy',
        })
        
        row_data = {
            'id': purchase.id,
            'number': purchase.number,
            'created_at': purchase.created_at,
            'supplier.name': purchase.supplier.name if purchase.supplier else 'غير محدد',
            'supplier': purchase.supplier.name if purchase.supplier else 'غير محدد',
            'supplier_name': purchase.supplier.name if purchase.supplier else 'غير محدد',
            'warehouse.name': purchase.warehouse.name if purchase.warehouse else ('خدمية' if purchase.is_service else 'غير محدد'),
            'warehouse': purchase.warehouse.name if purchase.warehouse else ('خدمية' if purchase.is_service else 'غير محدد'),
            'warehouse_name': purchase.warehouse.name if purchase.warehouse else ('خدمية' if purchase.is_service else 'غير محدد'),
            'total': purchase.total,
            'amount_due': purchase.amount_due,
            'currency_symbol': purchase.currency_symbol,
            'payment_status': purchase.payment_status,
            'actions': actions
        }
        table_data.append(row_data)

    context = {
        **pagination_data,
        "purchases": purchases,
        "table_headers": purchase_headers,
        "table_data": table_data,
        "paid_purchases_count": paid_purchases_count,
        "partially_paid_purchases_count": partially_paid_purchases_count,
        "unpaid_purchases_count": unpaid_purchases_count,
        "returned_purchases_count": returned_purchases_count,
        "total_amount": total_amount,
        "suppliers": suppliers,
        "warehouses": Warehouse.objects.filter(is_active=True).order_by("name"),
        "purchase_headers": purchase_headers,
        "services_count": services_count,
        "products_count": products_count,
        "courses_count": courses_count,
        "service_types": Purchase.SERVICE_TYPES,
        "show_export": True,
        "page_title": "فواتير المشتريات",
        "page_subtitle": "قائمة بجميع فواتير المشتريات في النظام",
        "page_icon": "fas fa-shopping-cart",
        "header_buttons": [
            {
                "url": reverse("purchase:purchase_create"),
                "icon": "fa-plus",
                "text": "إضافة فاتورة",
                "class": "btn-primary",
            }
        ],
        "breadcrumb_items": [
            {
                "title": _("الرئيسية"),
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {"title": _("المشتريات"), "active": True},
        ],
    }

    return render_paginated_response(
        request,
        "purchase/purchase_list.html",
        context,
        table_template_name="components/data_table.html"
    )


@login_required
def purchase_create(request, supplier_id=None):
    """
    إنشاء فاتورة مشتريات جديدة
    يمكن تمرير معرف المورد لاختياره تلقائياً
    """
    # التحقق من وجود المورد إذا تم تمرير معرفه
    selected_supplier = None
    is_service_invoice = False
    
    # قراءة أمر الشغل إذا تم تمريره
    work_order_id = request.GET.get('work_order') or request.POST.get('work_order')
    selected_work_order = None
    if work_order_id:
        from work_order.models import WorkOrder
        try:
            selected_work_order = WorkOrder.objects.get(id=work_order_id)
        except WorkOrder.DoesNotExist:
            pass
    
    # قراءة أمر الشراء إذا تم تمريره للتحويل
    from_po_id = request.GET.get('from_po')
    selected_po = None
    duplicate_items = None
    is_duplicate = False
    duplicate_from = ""
    if from_po_id:
        from purchase.models.procurement_models import PurchaseOrder
        try:
            selected_po = PurchaseOrder.objects.prefetch_related('items__product', 'items__unit').get(id=from_po_id)
            selected_supplier = selected_po.supplier
            selected_work_order = selected_po.work_order
            is_duplicate = True
            duplicate_from = f"أمر الشراء #{selected_po.order_number}"
            
            po_items_list = []
            for item in selected_po.items.all():
                qty = float(item.ordered_qty - item.billed_qty if item.ordered_qty > item.billed_qty else item.ordered_qty)
                po_items_list.append({
                    "product_id": item.product_id,
                    "name": item.product.name,
                    "code": item.product.sku or "",
                    "quantity": qty,
                    "unit_price": float(item.unit_price),
                    "discount": float(item.discount),
                    "total": float(item.total_price),
                    "unit": item.unit.name if item.unit else (item.product.unit.name if getattr(item.product, 'unit', None) else "")
                })
            duplicate_items = json.dumps(po_items_list)
        except PurchaseOrder.DoesNotExist:
            pass

    # قراءة إذن الاستلام إذا تم تمريره للتحويل (GRN to Purchase Invoice Flow)
    from_grn_id = request.GET.get('from_grn')
    selected_grn = None
    if from_grn_id and not is_duplicate:
        from purchase.models.procurement_models import GoodsReceivedNote
        try:
            selected_grn = GoodsReceivedNote.objects.prefetch_related('items__product', 'supplier', 'purchase_order').get(id=from_grn_id)
            selected_supplier = selected_grn.supplier
            if selected_grn.purchase_order:
                selected_po = selected_grn.purchase_order
                selected_work_order = selected_po.work_order
            is_duplicate = True
            duplicate_from = f"إذن استلام البضاعة #{selected_grn.grn_number}"

            grn_items_list = []
            for item in selected_grn.items.all():
                qty = float(item.received_qty - item.billed_qty if item.received_qty > item.billed_qty else item.received_qty)
                grn_items_list.append({
                    "product_id": item.product_id,
                    "name": item.product.name,
                    "code": item.product.sku or "",
                    "quantity": qty,
                    "unit_price": float(item.unit_price),
                    "discount": 0.0,
                    "total": float(Decimal(str(qty)) * item.unit_price),
                    "unit": item.product.unit.name if getattr(item.product, 'unit', None) else ""
                })
            duplicate_items = json.dumps(grn_items_list)
        except GoodsReceivedNote.DoesNotExist:
            pass

    if supplier_id and not selected_supplier:
        try:
            selected_supplier = Supplier.objects.get(id=supplier_id, is_active=True)
            # تحديد نوع الفاتورة من إعدادات نوع المورد
            if selected_supplier.primary_type and hasattr(selected_supplier.primary_type, 'settings') and selected_supplier.primary_type.settings:
                is_service_invoice = selected_supplier.primary_type.settings.is_service_provider
            else:
                # Fallback للطريقة القديمة
                is_service_invoice = selected_supplier.is_service_provider()
        except Supplier.DoesNotExist:
            messages.error(request, "المورد المحدد غير موجود أو غير نشط")
            return redirect("purchase:purchase_list")
    
    # فلترة المنتجات حسب نوع المورد
    # استثناء المنتجات المجمعة - لا يمكن شراؤها من الموردين
    if is_service_invoice:
        # موردين خدميين → عرض الخدمات فقط
        products = Product.objects.filter(is_active=True, is_service=True).order_by("name")
    else:
        # موردين عامين → عرض المنتجات فقط (ليس خدمات وليس مجمعة)
        products = Product.objects.filter(is_active=True, is_service=False, is_bundle=False).order_by("name")

    if request.method == "POST":
        form = PurchaseForm(request.POST)

        if form.is_valid():
            try:
                with transaction.atomic():
                    # إنشاء فاتورة المشتريات
                    purchase = form.save(commit=False)
                    purchase.subtotal = Decimal(request.POST.get("subtotal", 0))
                    purchase.total = Decimal(request.POST.get("total", 0))
                    purchase.created_by = request.user
                    
                    # معالجة نوع الفاتورة (نقدي/آجل)
                    invoice_type = request.POST.get("invoice_type", "")
                    if invoice_type == "credit":
                        # فاتورة آجلة: تعيين payment_method كـ credit
                        purchase.payment_method = "credit"
                    elif invoice_type == "cash":
                        # فاتورة نقدية: استخدام payment_method من الفورم (account code)
                        # القيمة موجودة بالفعل في form.cleaned_data
                        pass
                    
                    # تعيين حقول الخدمة تلقائياً من نوع المورد
                    purchase.auto_set_service_fields()
                    
                    # التأكد من عدم وجود مخزن للفواتير الخدمية
                    if purchase.is_service:
                        purchase.warehouse = None
                    
                    if selected_work_order:
                        purchase.work_order = selected_work_order
                    
                    # معالجة العملة وسعر الصرف مع الحوكمة المالية
                    currency_id = request.POST.get("currency")
                    if currency_id:
                        from financial.models import Currency
                        curr_obj = Currency.objects.filter(id=currency_id).first() if str(currency_id).isdigit() else Currency.objects.filter(code=currency_id).first()
                        if curr_obj:
                            purchase.currency = curr_obj

                    if purchase.currency and not purchase.currency.is_functional:
                        from financial.services.exchange_rate_service import ExchangeRateService
                        sys_rate = Decimal(str(ExchangeRateService.get_exchange_rate(purchase.currency) or 1.0))
                        purchase.exchange_rate = sys_rate
                        purchase.total_foreign = purchase.total
                        purchase.total_functional = (purchase.total * sys_rate).quantize(Decimal("0.01"))
                    else:
                        purchase.exchange_rate = Decimal("1.000000")
                        purchase.total_foreign = Decimal("0.00")
                        purchase.total_functional = purchase.total

                    purchase.save()

                    # إضافة بنود الفاتورة
                    product_ids = request.POST.getlist("product[]")
                    quantities = request.POST.getlist("quantity[]")
                    unit_prices = request.POST.getlist("unit_price[]")
                    discounts = request.POST.getlist("discount[]")

                    for i in range(len(product_ids)):
                        if product_ids[i] and str(product_ids[i]).isdigit():
                            product = get_object_or_404(Product, id=product_ids[i])
                            try:
                                raw_qty = quantities[i] if i < len(quantities) and quantities[i] else "1"
                                quantity = Decimal(str(raw_qty))
                            except (ValueError, TypeError):
                                quantity = Decimal("1")

                            try:
                                raw_price = unit_prices[i] if i < len(unit_prices) and unit_prices[i] else "0"
                                unit_price = Decimal(str(raw_price).replace(',', ''))
                            except (ValueError, TypeError):
                                unit_price = Decimal("0")

                            try:
                                raw_disc = discounts[i] if i < len(discounts) and discounts[i] else "0"
                                discount = Decimal(str(raw_disc).replace(',', ''))
                            except (ValueError, TypeError):
                                discount = Decimal("0")

                            # إنشاء بند فاتورة
                            item = PurchaseItem(
                                purchase=purchase,
                                product=product,
                                quantity=quantity,
                                unit_price=unit_price,
                                discount=discount,
                                total=(quantity * unit_price) - discount,
                            )
                            item.save()

                            # إنشاء السعر الاسترشادي المبدئي إذا لم يكن مسجلاً
                            if purchase.currency and not purchase.currency.is_functional and unit_price > Decimal("0"):
                                from product.services.indicative_price_service import IndicativePriceService
                                IndicativePriceService.create_if_missing(
                                    product=product,
                                    currency=purchase.currency,
                                    price=unit_price,
                                    price_type="cost",
                                    user=request.user
                                )

                    # إعادة حساب إجماليات الفاتورة والضرائب المتعددة
                    subtotal = sum(item.total for item in purchase.items.all())
                    purchase.subtotal = subtotal
                    net_taxable_base = max(Decimal('0'), subtotal - purchase.discount)

                    tax_active = request.POST.get('tax_active') in ['on', 'true', True]
                    vat_active = request.POST.get('vat_active') in ['on', 'true', True] or tax_active
                    from core.models import SystemSetting
                    default_tax_rate_str = str(SystemSetting.get_setting('default_tax_rate', '14.00') or '14.00')
                    vat_rate = Decimal(str(request.POST.get('vat_rate', default_tax_rate_str) or default_tax_rate_str))
                    wht_active = request.POST.get('wht_active') in ['on', 'true', True]
                    wht_rate = Decimal(str(request.POST.get('wht_rate', '1.00') or '1.00'))

                    purchase.tax_active = tax_active
                    purchase.vat_active = vat_active
                    purchase.vat_rate = vat_rate
                    purchase.wht_active = wht_active
                    purchase.wht_rate = wht_rate

                    if vat_active and tax_active:
                        purchase.tax = (net_taxable_base * vat_rate / Decimal("100.00")).quantize(Decimal("0.01"))
                    else:
                        purchase.tax = Decimal("0.00")

                    if wht_active:
                        purchase.wht_amount = (net_taxable_base * wht_rate / Decimal("100.00")).quantize(Decimal("0.01"))
                    else:
                        purchase.wht_amount = Decimal("0.00")

                    gross_total = net_taxable_base + purchase.tax
                    purchase.total = max(Decimal('0'), gross_total - purchase.wht_amount)

                    if purchase.currency and not purchase.currency.is_functional:
                        purchase.total_foreign = purchase.total
                        purchase.total_functional = (purchase.total * purchase.exchange_rate).quantize(Decimal("0.01"))
                    else:
                        purchase.total_foreign = Decimal("0.00")
                        purchase.total_functional = purchase.total

                    purchase.save()

                    # إنشاء حركات المخزون للفواتير غير الخدمية
                    if not purchase.is_service:
                        try:
                            from purchase.services.purchase_service import PurchaseService
                            PurchaseService._create_stock_movements(purchase, request.user)
                            logger.info(f"✅ تم إنشاء حركات المخزون للفاتورة: {purchase.number}")
                        except Exception as e:
                            logger.error(f"❌ خطأ في إنشاء حركات المخزون: {str(e)}")
                            raise

                    # إنشاء القيد المحاسبي لفاتورة المشتريات
                    try:
                        from purchase.services.purchase_service import PurchaseService
                        journal_entry = PurchaseService._create_purchase_journal_entry(purchase, request.user)
                        if journal_entry:
                            purchase.journal_entry = journal_entry
                            purchase.save(update_fields=['journal_entry'])
                            logger.info(f"✅ تم إنشاء وربط القيد المحاسبي: {journal_entry.number} للفاتورة: {purchase.number}")
                    except Exception as e:
                        logger.error(f"❌ خطأ في إنشاء القيد المحاسبي لفاتورة المشتريات {purchase.number}: {str(e)}")
                        raise

                    # إنشاء دفعة تلقائية للفواتير النقدية فقط (غير مرحلة)
                    if invoice_type == "cash" and purchase.payment_method not in ["credit", ""]:
                        # payment_method هو account code (مثل 10100)
                        payment_account_code = purchase.payment_method
                        if payment_account_code:
                            try:
                                from purchase.services.purchase_service import PurchaseService
                                
                                # استخدام PurchaseService.process_payment للتوحيد
                                # الدفعة تُنشأ غير مرحلة (draft) عشان المستخدم يراجعها ويرحلها
                                payment_data = {
                                    'amount': purchase.total,
                                    'payment_date': purchase.date,
                                    'payment_method': payment_account_code,
                                    'notes': 'دفعة تلقائية - فاتورة نقدية'
                                }
                                
                                payment = PurchaseService.process_payment(
                                    purchase=purchase,
                                    payment_data=payment_data,
                                    user=request.user,
                                    auto_post=False  # الدفعة غير مرحلة
                                )
                                
                                logger.info(
                                    f"✅ تم إنشاء دفعة غير مرحلة للفاتورة النقدية: {purchase.number}"
                                )
                                messages.info(
                                    request,
                                    "تم إنشاء دفعة غير مرحلة - يرجى مراجعتها وترحيلها من صفحة تفاصيل الفاتورة"
                                )

                            except Exception as e:
                                logger.error(
                                    f"❌ خطأ في إنشاء الدفعة التلقائية: {str(e)}"
                                )
                                messages.warning(
                                    request,
                                    f"تم إنشاء الفاتورة لكن فشل إنشاء الدفعة التلقائية: {str(e)}",
                                )
                        else:
                            messages.warning(
                                request, "تحذير: لم يتم اختيار خزينة للفاتورة النقدية"
                            )

                    messages.success(request, "تم إنشاء فاتورة المشتريات بنجاح")
                    return redirect("purchase:purchase_list")

            except Exception as e:
                messages.error(request, str(e))
        else:
            messages.error(request, "يرجى تصحيح الأخطاء الموجودة في النموذج")
    else:
        # إنشاء رقم فاتورة مشتريات جديد
        last_purchase = Purchase.objects.order_by("-id").first()
        next_number = f"PUR{(last_purchase.id + 1 if last_purchase else 1):04d}"

        initial_data = {
            "date": timezone.now().date(),
            "number": next_number,
        }
        # إضافة المورد المحدد إلى البيانات الافتراضية
        if selected_supplier:
            initial_data["supplier"] = selected_supplier
            if hasattr(selected_supplier, 'default_currency') and selected_supplier.default_currency:
                initial_data["currency"] = selected_supplier.default_currency
        if selected_work_order:
            initial_data["work_order"] = selected_work_order
        if selected_po:
            if selected_po.warehouse:
                initial_data["warehouse"] = selected_po.warehouse
            if selected_po.currency:
                initial_data["currency"] = selected_po.currency
            if selected_po.cost_center:
                initial_data["cost_center"] = selected_po.cost_center
            initial_data["discount"] = selected_po.discount
            initial_data["tax_active"] = selected_po.tax_active
            initial_data["vat_active"] = selected_po.vat_active
            initial_data["vat_rate"] = selected_po.vat_rate
            initial_data["wht_active"] = selected_po.wht_active
            initial_data["wht_rate"] = selected_po.wht_rate
            initial_data["adjustment_name"] = selected_po.adjustment_name
            initial_data["adjustment_type"] = selected_po.adjustment_type
            initial_data["adjustment_amount"] = selected_po.adjustment_amount
            
        form = PurchaseForm(initial=initial_data)

    # جلب البيانات المطلوبة للقوائم المنسدلة (مطلوب في كل الحالات)
    suppliers = Supplier.objects.filter(is_active=True).order_by("name")
    warehouses = Warehouse.objects.filter(is_active=True).order_by("name")

    # جلب التصنيفات للمودال
    from product.models import Category
    if is_service_invoice:
        product_categories = Category.objects.filter(
            is_active=True, products__is_active=True, products__is_service=True
        ).distinct().order_by("name")
    else:
        product_categories = Category.objects.filter(
            is_active=True, products__is_active=True, products__is_service=False, products__is_bundle=False
        ).distinct().order_by("name")
    
    # إضافة أول مخزن متاح كافتراضي للنموذج الجديد
    if request.method == "GET" and warehouses.exists() and "warehouse" not in form.initial:
        form.initial["warehouse"] = warehouses.first()

    # إنشاء رقم فاتورة مشتريات جديد
    last_purchase = Purchase.objects.order_by("-id").first()
    next_purchase_number = f"PUR{(last_purchase.id + 1 if last_purchase else 1):04d}"

    from financial.models import Currency
    context = {
        "form": form,
        "products": products,
        "product_categories": product_categories,
        "suppliers": suppliers,
        "warehouses": warehouses,
        "currencies": Currency.objects.filter(is_active=True).order_by("code"),
        "next_purchase_number": next_purchase_number,
        "selected_supplier": selected_supplier,
        "is_service_invoice": is_service_invoice,
        "supplier_type_code": selected_supplier.get_primary_type_code() if selected_supplier else None,
        "default_warehouse": warehouses.first() if warehouses.exists() else None,
        "duplicate_items": duplicate_items,
        "is_duplicate": is_duplicate,
        "duplicate_from": duplicate_from,
        "duplicate_discount": str(selected_po.discount) if selected_po else "0",
        "duplicate_discount_type": selected_po.discount_type if selected_po else "fixed",
        "duplicate_adjustment_name": selected_po.adjustment_name if selected_po else "",
        "duplicate_adjustment_type": selected_po.adjustment_type if selected_po else "add",
        "duplicate_adjustment_amount": str(selected_po.adjustment_amount) if selected_po else "0",
        "page_title": "إضافة فاتورة مشتريات" + (f" - {selected_supplier.name}" if selected_supplier else ""),
        "page_subtitle": "إضافة فاتورة مشتريات جديدة إلى النظام",
        "page_icon": "fas fa-plus-circle",
        "header_buttons": ([
            {
                "url": reverse("supplier:supplier_detail", kwargs={"pk": selected_supplier.pk}),
                "icon": "fa-arrow-right",
                "text": "العودة لتفاصيل المورد",
                "class": "btn-secondary",
            },
        ] if selected_supplier else []),
        "breadcrumb_items": [
            {"title": _("الرئيسية"), "url": reverse("core:dashboard"), "icon": "fa-home"},
            *([
                {"title": _("أوامر الشغل"), "url": reverse("work_order:work_order_list"), "icon": "fa-briefcase"},
                {"title": selected_work_order.number, "url": reverse("work_order:work_order_detail", kwargs={"pk": selected_work_order.pk}), "icon": "fa-file-alt"},
            ] if selected_work_order else [
                {"title": _("المشتريات"), "url": reverse("purchase:purchase_list"), "icon": "fa-shopping-bag"},
            ] + ([{
                "title": selected_supplier.name,
                "url": reverse("supplier:supplier_detail", kwargs={"pk": selected_supplier.pk}),
                "icon": "fa-truck",
            }] if selected_supplier else [])),
            {"title": _("إضافة فاتورة مشتريات"), "active": True, "icon": "fa-plus-circle"},
        ],
    }

    return render(request, "purchase/purchase_form.html", context)


@login_required
def purchase_detail(request, pk):
    """
    عرض تفاصيل فاتورة المشتريات
    """
    purchase = get_object_or_404(Purchase.objects.with_details(), pk=pk)
    # الحصول على المدفوعات مرتبة حسب تاريخ الإنشاء من الأحدث إلى الأقدم
    payments = purchase.payments.all().order_by("-created_at")

    # فحص إذا كان يجب عرض SweetAlert للترحيل
    show_post_alert = request.session.pop("show_post_alert", None)
    
    # تحديد نوع الفاتورة للعنوان
    invoice_type_name = "فاتورة خدمات" if purchase.is_service_invoice else "فاتورة مشتريات"

    context = {
        "purchase": purchase,
        "payments": payments,
        "title": f"{invoice_type_name} {purchase.number}",
        "page_title": f"{invoice_type_name} {purchase.number}",
        "page_subtitle": _('المورد: <a href="{}" class="text-decoration-none fw-bold text-primary"><i class="fas fa-truck me-1"></i>{}</a>').format(
            reverse("supplier:supplier_detail", args=[purchase.supplier.pk]),
            purchase.supplier.name
        ),
        "page_icon": purchase.invoice_type_icon,
        "show_post_alert": show_post_alert,
        "header_buttons": ([{
            "url": reverse("purchase:purchase_add_payment", kwargs={"pk": purchase.pk}),
            "icon": "fa-money-bill",
            "text": "إضافة دفعة",
            "class": "btn-success",
        }] if purchase.payment_status != 'paid' else []) + [
            {
                "url": reverse("purchase:purchase_print", kwargs={"pk": purchase.pk}),
                "icon": "fa-print",
                "text": "طباعة",
                "class": "btn-info",
            },
            {
                "dropdown": True,
                "icon": "fa-file-pdf",
                "text": "مشاركة",
                "class": "btn-success",
                "items": [
                    {
                        "onclick": f"downloadDocumentPDF('{reverse('purchase:purchase_pdf_download', kwargs={'pk': purchase.pk})}', '{reverse('purchase:purchase_print', kwargs={'pk': purchase.pk})}', '{purchase.number}')",
                        "icon": "fas fa-file-download text-primary",
                        "text": "تحميل PDF"
                    },
                    {
                        "onclick": f"shareWhatsAppPDF('{purchase.supplier.phone if purchase.supplier and purchase.supplier.phone else ''}', '{purchase.number}', 'فاتورة مشتريات', '{reverse('purchase:purchase_pdf_download', kwargs={'pk': purchase.pk})}', '{reverse('purchase:purchase_print', kwargs={'pk': purchase.pk})}')",
                        "icon": "fab fa-whatsapp text-success",
                        "text": "إرسال واتساب"
                    },
                    {
                        "onclick": f"sendEmailPDF('{reverse('purchase:purchase_email_pdf', kwargs={'pk': purchase.pk})}', '{purchase.supplier.email if purchase.supplier and purchase.supplier.email else ''}', '{purchase.number}', 'فاتورة مشتريات', '{reverse('purchase:purchase_pdf_download', kwargs={'pk': purchase.pk})}', '{reverse('purchase:purchase_print', kwargs={'pk': purchase.pk})}')",
                        "icon": "far fa-envelope text-primary",
                        "text": "إرسال بريد"
                    }
                ]
            },
            {
                "url": reverse("purchase:purchase_duplicate", kwargs={"pk": purchase.pk}),
                "icon": "fa-copy",
                "text": "نسخ",
                "class": "btn-outline-primary",
            },
            {
                "url": "#",
                "icon": "fa-ellipsis-v",
                "text": "",
                "class": "btn-outline-secondary",
                "toggle": "modal",
                "target": "#actionsModal",
            },
        ],
        "header_badges": [
            *([{"text": purchase.work_order.number, "class": "bg-info text-white", "icon": "fas fa-tasks", "url": reverse("work_order:work_order_detail", kwargs={"pk": purchase.work_order.pk})}] if hasattr(purchase, 'work_order') and purchase.work_order else []),
            *([{"text": purchase.get_status_display(), "class": "bg-warning text-dark" if purchase.status == 'draft' else "bg-danger text-white", "icon": "fas fa-info-circle"}] if purchase.status != 'confirmed' else []),
        ],
        "breadcrumb_items": [
            {
                "title": "لوحة التحكم",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-tachometer-alt",
            },
            *([
                {"title": "أوامر الشغل", "url": reverse("work_order:work_order_list"), "icon": "fas fa-tasks"},
                {"title": f"أمر شغل {purchase.work_order.number}", "url": reverse("work_order:work_order_detail", kwargs={"pk": purchase.work_order.pk})},
            ] if hasattr(purchase, 'work_order') and purchase.work_order else [
                {
                    "title": "المشتريات",
                    "url": reverse("purchase:purchase_list"),
                    "icon": "fas fa-shopping-basket",
                },
                {
                    "title": purchase.supplier.name,
                    "url": reverse("supplier:supplier_detail", args=[purchase.supplier.pk]),
                    "icon": "fas fa-truck",
                },
            ]),
            {"title": f"{invoice_type_name} {purchase.number}", "active": True},
        ],
    }
    return render(request, "purchase/purchase_detail.html", context)


@login_required
def allocate_supplier_prepaid_balance(request, pk):
    """
    تخصيص وتسوية رصيد مسبق/دفعة مقدمة للمورد على فاتورة مشتريات بنسبة 1:1 للعملات المتطابقة
    """
    purchase = get_object_or_404(Purchase, pk=pk)
    if not purchase.supplier:
        messages.error(request, _("لا يوجد مورد مرتبط بهذه الفاتورة."))
        return redirect("purchase:purchase_detail", pk=purchase.pk)

    if request.method == "POST":
        amount_str = request.POST.get("amount")
        is_auto = request.POST.get("auto_fifo") == "true"

        try:
            from financial.services.partner_advance_service import PartnerAdvanceService
            from decimal import Decimal

            target_currency = purchase.currency
            if not target_currency:
                from financial.services.exchange_rate_service import ExchangeRateService
                target_currency = ExchangeRateService.get_functional_currency()

            payment = purchase.supplier.advance_payments.filter(currency=target_currency).order_by("payment_date").first()
            if not payment:
                payment = purchase.supplier.advance_payments.order_by("payment_date").first()

            if not payment:
                messages.error(request, "لا تتوفر أي دفعات مقدمة مسجلة ومتاحة للمورد.")
                return redirect("purchase:purchase_detail", pk=purchase.pk)

            available = PartnerAdvanceService.get_available_balance(purchase.supplier, currency=target_currency)
            open_amount = purchase.amount_due

            if is_auto:
                alloc_amount = min(available, open_amount)
            else:
                alloc_amount = Decimal(amount_str) if amount_str else Decimal("0.00")

            if alloc_amount <= Decimal("0.00"):
                messages.error(request, "يرجى إدخال مبلغ تخصيص أكبر من صفر.")
            elif alloc_amount > available:
                messages.error(request, f"المبلغ المطلوب ({alloc_amount}) يتجاوز الرصيد المسبق المتاح للمورد ({available}).")
            else:
                settlement = PartnerAdvanceService.allocate(
                    partner=purchase.supplier,
                    payment=payment,
                    invoice=purchase,
                    amount=alloc_amount,
                    user=request.user,
                )
                messages.success(request, f"تم تخصيص تسوية رصيد مسبق بمبلغ {alloc_amount} بنجاح.")
        except Exception as e:
            messages.error(request, f"حدث خطأ أثناء تخصيص الرصيد المسبق: {str(e)}")

    return redirect("purchase:purchase_detail", pk=purchase.pk)


@login_required
def purchase_update(request, pk):
    """
    تعديل فاتورة مشتريات مع دعم القيود التصحيحية للفواتير المرحّلة
    """
    purchase = get_object_or_404(Purchase, pk=pk)

    # التحقق من الصلاحيات
    if not request.user.has_perm("purchase.change_purchase"):
        messages.error(request, "ليس لديك صلاحية لتعديل فواتير المشتريات")
        return redirect("purchase:purchase_list")

    # منع تعديل الفواتير المدفوعة بالكامل
    if purchase.payment_status == "paid":
        messages.error(request, "لا يمكن تعديل فاتورة مدفوعة بالكامل")
        return redirect("purchase:purchase_detail", pk=purchase.pk)

    # التحقق من حالة القيد المحاسبي
    has_posted_entry = (
        purchase.journal_entry and 
        purchase.journal_entry.status == 'posted'
    )

    # حفظ القيم الأصلية للمقارنة (قبل التعديل)
    original_total = purchase.total

    # الحصول على البنود الأصلية قبل التعديل
    original_items = {}
    for item in purchase.items.all():
        original_items[item.product.id] = item.quantity

    if request.method == "POST":
        from purchase.forms import PurchaseUpdateForm
        form = PurchaseForm(request.POST, instance=purchase)
        if form.is_valid():
            try:
                # استيراد StockMovement محلياً لتجنب مشاكل الاستيراد الدائري
                from product.models import StockMovement
                
                with transaction.atomic():
                    updated_purchase = form.save(commit=False)

                    # الحصول على قيمة الضريبة من النموذج (إذا كانت مقدمة) وتحويلها إلى Decimal
                    tax_value = Decimal(form.cleaned_data.get("tax", 0) or 0)

                    # معالجة بنود الفاتورة
                    product_ids = request.POST.getlist("product[]")
                    quantities = request.POST.getlist("quantity[]")
                    unit_prices = request.POST.getlist("unit_price[]")
                    discounts = request.POST.getlist("discount[]")

                    # تتبع البنود المحفوظة لحذف أي بنود محذوفة
                    saved_item_ids = []

                    # حساب المجموع الفرعي
                    subtotal = Decimal("0")

                    # إنشاء قاموس للكميات الجديدة
                    new_items = {}

                    # حفظ البنود
                    for i in range(len(product_ids)):
                        if not product_ids[i] or not str(product_ids[i]).isdigit():  # تخطي البنود الفارغة
                            continue

                        product = get_object_or_404(Product, id=product_ids[i])
                        try:
                            raw_qty = quantities[i] if i < len(quantities) and quantities[i] else "1"
                            quantity = Decimal(str(raw_qty))
                        except (ValueError, TypeError):
                            quantity = Decimal("1")

                        try:
                            raw_price = unit_prices[i] if i < len(unit_prices) and unit_prices[i] else "0"
                            unit_price = Decimal(str(raw_price).replace(',', ''))
                        except (ValueError, TypeError):
                            unit_price = Decimal("0")

                        try:
                            raw_disc = discounts[i] if i < len(discounts) and discounts[i] else "0"
                            discount = Decimal(str(raw_disc).replace(',', ''))
                        except (ValueError, TypeError):
                            discount = Decimal("0")

                        # حساب إجمالي البند
                        item_total = (quantity * unit_price) - discount
                        subtotal += item_total

                        # البحث عن البند الموجود أو إنشاء بند جديد
                        item, created = PurchaseItem.objects.update_or_create(
                            purchase=purchase,
                            product=product,
                            defaults={
                                "quantity": quantity,
                                "unit_price": unit_price,
                                "discount": discount,
                                "total": item_total,
                            },
                        )

                        saved_item_ids.append(item.id)
                        # حفظ الكمية وسعر الوحدة الجديدة في القاموس
                        new_items[product.id] = (quantity, unit_price)

                    # حذف البنود الغير موجودة في النموذج
                    PurchaseItem.objects.filter(purchase=purchase).exclude(
                        id__in=saved_item_ids
                    ).delete()

                    # تحديث المجموع الفرعي والإجمالي
                    updated_purchase.subtotal = subtotal
                    updated_purchase.tax = tax_value
                    updated_purchase.total = (
                        subtotal - Decimal(updated_purchase.discount) + tax_value
                    )

                    # حفظ التعديلات
                    updated_purchase.save()

                    # تعريف رقم المرجع الرئيسي
                    main_reference = f"PURCHASE-{updated_purchase.number}"

                    # معالجة المنتجات المضافة أو التي تغيرت كميتها - استخدام MovementService
                    from governance.services import MovementService
                    
                    movement_service = MovementService()
                    
                    for product_id, (new_quantity, item_unit_price) in new_items.items():
                        original_quantity = original_items.get(product_id, 0)
                        quantity_diff = new_quantity - original_quantity

                        if quantity_diff != 0:  # فقط إذا كان هناك تغيير في الكمية
                            product = Product.objects.get(id=product_id)
                            
                            # تخطي الخدمات
                            if product.is_service:
                                continue

                            # استخدام MovementService بدلاً من التحديث المباشر
                            try:
                                if quantity_diff > 0:  # زيادة الكمية
                                    movement = movement_service.process_movement(
                                        product_id=product_id,
                                        quantity_change=Decimal(str(quantity_diff)),
                                        movement_type='in',
                                        source_reference=f"PUR-EDIT-{updated_purchase.number}",
                                        idempotency_key=f"purchase_edit_{updated_purchase.id}_{product_id}_increase_{timezone.now().timestamp()}",
                                        user=request.user,
                                        unit_cost=item_unit_price if (item_unit_price and item_unit_price > 0) else (product.cost_price if (product and product.cost_price and product.cost_price > 0) else Decimal('0.01')),
                                        document_number=updated_purchase.number,
                                        notes=f"زيادة كمية منتج في تعديل فاتورة مشتريات رقم {updated_purchase.number}"
                                    )
                                else:  # نقص الكمية
                                    movement = movement_service.process_movement(
                                        product_id=product_id,
                                        quantity_change=-Decimal(str(abs(quantity_diff))),
                                        movement_type='out',
                                        source_reference=f"PUR-EDIT-{updated_purchase.number}",
                                        idempotency_key=f"purchase_edit_{updated_purchase.id}_{product_id}_decrease_{timezone.now().timestamp()}",
                                        user=request.user,
                                        document_number=updated_purchase.number,
                                        notes=f"نقص كمية منتج في تعديل فاتورة مشتريات رقم {updated_purchase.number}"
                                    )
                                
                                logger.info(
                                    f"✅ تم تحديث المخزون عبر MovementService: {movement.id} - "
                                    f"المنتج {product.name} - الفرق: {quantity_diff}"
                                )
                            except Exception as e:
                                logger.error(f"❌ خطأ في تحديث المخزون عبر MovementService: {str(e)}")
                                raise

                    # معالجة المنتجات المحذوفة - استخدام MovementService
                    for product_id, original_quantity in original_items.items():
                        if product_id not in new_items:  # إذا كان المنتج موجود سابقًا وتم حذفه
                            product = Product.objects.get(id=product_id)
                            
                            # تخطي الخدمات
                            if product.is_service:
                                continue

                            # استخدام MovementService لخصم الكمية المحذوفة
                            try:
                                movement = movement_service.process_movement(
                                    product_id=product_id,
                                    quantity_change=-Decimal(str(original_quantity)),
                                    movement_type='out',
                                    source_reference=f"PUR-EDIT-DELETE-{updated_purchase.number}",
                                    idempotency_key=f"purchase_edit_{updated_purchase.id}_{product_id}_delete_{timezone.now().timestamp()}",
                                    user=request.user,
                                    document_number=updated_purchase.number,
                                    notes=f"حذف منتج من فاتورة مشتريات رقم {updated_purchase.number}"
                                )
                                
                                logger.info(
                                    f"✅ تم خصم المخزون عبر MovementService: {movement.id} - "
                                    f"المنتج {product.name} - الكمية: {original_quantity}"
                                )
                            except Exception as e:
                                logger.error(f"❌ خطأ في خصم المخزون عبر MovementService: {str(e)}")
                                raise

                    # تحديث مديونية المورد (يتم تنفيذه من خلال الإشارة في signals.py)

                    # إنشاء قيد تصحيحي إذا كانت الفاتورة مرحّلة
                    if has_posted_entry:
                        try:
                            from financial.services.accounting_integration_service import (
                                AccountingIntegrationService,
                            )
                            
                            adjustment_entry = AccountingIntegrationService.create_purchase_adjustment_entry(
                                purchase=updated_purchase,
                                old_total=original_total,
                                user=request.user
                            )
                            
                            if adjustment_entry:
                                messages.success(
                                    request,
                                    f"تم تعديل فاتورة المشتريات بنجاح وإنشاء قيد تصحيحي: {adjustment_entry.number}"
                                )
                                logger.info(
                                    f"✅ تم إنشاء قيد تصحيحي {adjustment_entry.number} "
                                    f"لتعديل فاتورة {updated_purchase.number}"
                                )
                            else:
                                messages.success(
                                    request,
                                    "تم تعديل فاتورة المشتريات بنجاح (لا توجد فروقات تتطلب قيد تصحيحي)"
                                )
                        except Exception as e:
                            logger.error(f"❌ خطأ في إنشاء القيد التصحيحي: {str(e)}")
                            messages.warning(
                                request,
                                f"تم تعديل الفاتورة لكن فشل إنشاء القيد التصحيحي: {str(e)}"
                            )
                    else:
                        messages.success(request, _("تم تعديل فاتورة المشتريات بنجاح"))
                    
                return redirect("purchase:purchase_detail", pk=pk)
            except Exception as e:
                messages.error(request, f"حدث خطأ أثناء تعديل الفاتورة: {str(e)}")
                logger.error(f"Error updating purchase: {str(e)}")
        else:
            # طباعة أخطاء النموذج بشكل مفصل
            logger.error(f"Form errors: {form.errors}")
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"خطأ في الحقل {field}: {error}")
    else:
        from purchase.forms import PurchaseUpdateForm
        form = PurchaseUpdateForm(instance=purchase)

    # جلب البيانات المطلوبة للقوائم المنسدلة
    suppliers = Supplier.objects.filter(is_active=True).order_by("name")
    warehouses = Warehouse.objects.filter(is_active=True).order_by("name")
    products = Product.objects.filter(is_active=True).order_by("name")

    from financial.models import Currency
    currencies_qs = Currency.objects.filter(is_active=True).order_by("code")

    context = {
        "form": form,
        "purchase": purchase,
        "products": products,
        "suppliers": suppliers,
        "warehouses": warehouses,
        "currencies": currencies_qs,
        "active_currencies": currencies_qs,
        "title": "تعديل فاتورة مشتريات",
        "page_title": f"تعديل فاتورة مشتريات - {purchase.number}",
        "page_icon": "fas fa-edit",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "فواتير المشتريات",
                "url": reverse("purchase:purchase_list"),
                "icon": "fas fa-shopping-cart",
            },
            {"title": f"تعديل {purchase.number}", "active": True},
        ],
    }

    return render(request, "purchase/purchase_form.html", context)


@login_required
def purchase_delete(request, pk):
    """
    حذف فاتورة المشتريات
    """
    purchase = get_object_or_404(Purchase, pk=pk)

    # التحقق مما إذا كانت الفاتورة لها مرتجعات مؤكدة
    has_confirmed_returns = purchase.returns.filter(status="confirmed").exists()

    if has_confirmed_returns:
        messages.error(request, "لا يمكن حذف الفاتورة لأنها تحتوي على مرتجعات مؤكدة")
        return redirect("purchase:purchase_detail", pk=purchase.pk)

    # التحقق من وجود دفعات مرحلة
    has_posted_payments = purchase.payments.filter(status="posted").exists()

    if has_posted_payments:
        messages.error(
            request,
            "لا يمكن حذف الفاتورة لأنها تحتوي على دفعات مرحلة. يجب إلغاء ترحيل الدفعات أولاً."
        )
        return redirect("purchase:purchase_detail", pk=purchase.pk)

    if request.method == "POST":
        try:
            # استيراد Stock محلياً لتجنب مشاكل الاستيراد الدائري
            from product.models import Stock
            
            # التحقق من المخزون المتاح قبل الحذف
            insufficient_stock_items = []
            for item in purchase.items.all():
                stock = Stock.objects.filter(
                    product=item.product,
                    warehouse=purchase.warehouse
                ).first()
                
                current_quantity = stock.quantity if stock else 0
                
                if current_quantity < item.quantity:
                    insufficient_stock_items.append({
                        'product': item.product.name,
                        'required': item.quantity,
                        'available': current_quantity,
                        'sold': item.quantity - current_quantity
                    })
            
            # إذا كان هناك منتجات تم بيعها، منع الحذف
            if insufficient_stock_items:
                error_message = "لا يمكن حذف الفاتورة - تم بيع جزء من المنتجات:\n\n"
                for item_info in insufficient_stock_items:
                    error_message += (
                        f"• {item_info['product']}: "
                        f"الكمية المطلوب إرجاعها {item_info['required']}، "
                        f"المتاح في المخزون {item_info['available']}، "
                        f"تم بيع {item_info['sold']}\n"
                    )
                error_message += "\nيجب إنشاء مرتجع مشتريات بدلاً من حذف الفاتورة."
                messages.error(request, error_message)
                return redirect("purchase:purchase_detail", pk=purchase.pk)
            
            with transaction.atomic():
                # signal handle_deleted_purchase_item سيتولى إنشاء الحركات المعاكسة

                # إلغاء ترحيل وحذف القيد المحاسبي المرتبط بالفاتورة إذا وُجد
                journal_entry_info = ""
                if purchase.journal_entry:
                    journal_entry = purchase.journal_entry
                    journal_entry_number = journal_entry.number
                    journal_entry_status = journal_entry.status
                    
                    # إلغاء ترحيل القيد أولاً إذا كان مرحلاً
                    if journal_entry_status == "posted":
                        try:
                            journal_entry.status = "draft"
                            journal_entry.save(update_fields=['status'])
                            logger.info(f"✅ تم إلغاء ترحيل القيد المحاسبي {journal_entry_number}")
                            journal_entry_info = f" وتم إلغاء ترحيل وحذف القيد المحاسبي {journal_entry_number}"
                        except Exception as e:
                            logger.error(f"❌ فشل في إلغاء ترحيل القيد {journal_entry_number}: {e}")
                            journal_entry_info = f" وتم حذف القيد المحاسبي {journal_entry_number} (فشل إلغاء الترحيل)"
                    else:
                        journal_entry_info = f" وتم حذف القيد المحاسبي {journal_entry_number}"
                    
                    # حذف القيد المحاسبي وخطوطه
                    journal_entry.delete()
                    logger.info(f"✅ تم حذف القيد المحاسبي {journal_entry_number} المرتبط بفاتورة المشتريات {purchase.number}")

                # حذف الفاتورة (CASCADE سيحذف البنود و signals ستعالج المخزون)
                purchase_number = purchase.number
                purchase.delete()

                messages.success(
                    request,
                    f"تم حذف فاتورة المشتريات {purchase_number} بنجاح{journal_entry_info}. تم إرجاع المخزون بشكل صحيح.",
                )
                return redirect("purchase:purchase_list")

        except Exception as e:
            messages.error(request, f"حدث خطأ أثناء حذف الفاتورة: {str(e)}")
            return redirect("purchase:purchase_detail", pk=purchase.pk)

    context = {
        "purchase": purchase,
        "page_title": f"حذف فاتورة {purchase.number}",
        "page_subtitle": f"{purchase.supplier.name} | {purchase.date.strftime('%d-%m-%Y')}",
        "page_icon": "fas fa-trash",
        "breadcrumb_items": [
            {
                "title": "لوحة التحكم",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-tachometer-alt",
            },
            {
                "title": "المشتريات",
                "url": reverse("purchase:purchase_list"),
                "icon": "fas fa-shopping-basket",
            },
            {
                "title": f"فاتورة {purchase.number}",
                "url": reverse("purchase:purchase_detail", kwargs={"pk": purchase.pk}),
                "icon": "fas fa-file-invoice",
            },
            {"title": "حذف", "active": True},
        ],
    }

    return render(request, "purchase/purchase_confirm_delete.html", context)


def get_purchase_print_context(request, pk):
    purchase = get_object_or_404(Purchase, pk=pk)
    items = purchase.items.all().select_related('product', 'product__unit', 'product__category')

    default_lang = SystemSetting.get_default_print_language()
    print_lang = request.GET.get('lang', default_lang).lower()
    if print_lang not in ['ar', 'en']:
        print_lang = 'ar'
    
    is_english = (print_lang == 'en')
    is_bilingual = False
    print_dir = 'ltr' if is_english else 'rtl'
    from django.utils import timezone
    today = timezone.now().date()
    year = timezone.now().year
    currency_symbol_active = getattr(purchase, 'currency', None) or SystemSetting.get_currency_symbol()
    status_map = {
        'paid': 'مدفوع بالكامل' if not is_english else 'PAID',
        'unpaid': 'غير مدفوع' if not is_english else 'UNPAID',
        'partial': 'مدفوع جزئياً' if not is_english else 'PARTIALLY PAID',
        'draft': 'مسودة' if not is_english else 'DRAFT'
    }
    status_code = getattr(purchase, 'payment_status', getattr(purchase, 'status', 'unpaid'))
    translated_status = status_map.get(str(status_code).lower(), str(status_code))

    context = {
        "purchase": purchase,
        "items": items,
        "title": f"طباعة فاتورة المشتريات - {purchase.number}",
        "today": today,
        "year": year,
        "print_lang": print_lang,
        "print_dir": print_dir,
        "is_english": is_english,
        "is_bilingual": is_bilingual,
        "currency_symbol_active": currency_symbol_active,
        "translated_status": translated_status,
        "has_item_discounts": purchase.has_item_discounts,
    }
    return purchase, context


@login_required
def purchase_print(request, pk):
    """
    طباعة فاتورة المشتريات (عربي / إنجليزي / ثنائي اللغة)
    """
    purchase, context = get_purchase_print_context(request, pk)
    return render(request, "purchase/purchase_print.html", context)


@login_required
def purchase_pdf_download(request, pk):
    """
    تصدير/تنزيل فاتورة مشتريات مباشرة كـ PDF بنسق نقي
    """
    from django.template.loader import render_to_string
    from utils.pdf_utils import generate_pdf_from_html, generate_guaranteed_pdf_response
    
    purchase, context = get_purchase_print_context(request, pk)
    
    try:
        html_content = render_to_string("purchase/purchase_print.html", context, request=request)
        pdf_response = generate_pdf_from_html(html_content, request=request, filename=f"{purchase.number}.pdf", doc_type="purchase", context=context)
        
        if pdf_response:
            return pdf_response
    except Exception as e:
        logger.error(f"Purchase PDF generation error for {purchase.number}: {e}")
        
    return generate_guaranteed_pdf_response("purchase", context, filename=f"{purchase.number}.pdf")


@login_required
def purchase_email_pdf(request, pk):
    """
    إرسال فاتورة المشتريات عبر البريد الإلكتروني للمورد مباشرة
    """
    from django.http import JsonResponse
    purchase = get_object_or_404(Purchase, pk=pk)
    supplier_email = purchase.supplier.email if purchase.supplier and purchase.supplier.email else None
    if not supplier_email:
        return JsonResponse({'success': False, 'message': 'لا يوجد بريد إلكتروني مسجل للمورد'}, status=400)
    
    try:
        from utils.email_utils import send_email
        subject = f"فاتورة مشتريات #{purchase.number}"
        body = f"مرحباً {purchase.supplier.name}،\n\nيرجى الاطلاع على فاتورة المشتريات الخاصة بكم رقم #{purchase.number}.\n\nرابط الفاتورة المباشر:\n{request.build_absolute_uri(reverse('purchase:purchase_print', kwargs={'pk': purchase.pk}))}\n\nشكراً لتعاملكم معنا."
        send_email(subject, body, [supplier_email])
        return JsonResponse({'success': True, 'message': 'تم إرسال البريد بنجاح!'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@login_required
def purchase_duplicate(request, pk):
    """
    نسخ فاتورة مشتريات - فتح صفحة الإنشاء مع تحميل بيانات الفاتورة الأصلية
    المستخدم يراجع ويعدّل ثم يحفظ
    """
    original = get_object_or_404(Purchase, pk=pk)

    # تحديد نوع الفاتورة
    is_service_invoice = original.is_service_invoice
    selected_supplier = original.supplier

    # فلترة المنتجات حسب نوع المورد مع تضمين المنتجات في الفاتورة الأصلية
    original_item_product_ids = list(original.items.values_list("product_id", flat=True))

    from django.db import models
    if is_service_invoice:
        products = Product.objects.filter(models.Q(is_active=True, is_service=True) | models.Q(id__in=original_item_product_ids)).order_by("name")
    else:
        products = Product.objects.filter(models.Q(is_active=True, is_service=False, is_bundle=False) | models.Q(id__in=original_item_product_ids)).order_by("name")

    suppliers = Supplier.objects.filter(is_active=True).order_by("name")
    warehouses = Warehouse.objects.filter(is_active=True).order_by("name")

    # جلب التصنيفات للمودال
    from product.models import Category
    if is_service_invoice:
        product_categories = Category.objects.filter(
            is_active=True, products__is_active=True, products__is_service=True
        ).distinct().order_by("name")
    else:
        product_categories = Category.objects.filter(
            is_active=True, products__is_active=True, products__is_service=False, products__is_bundle=False
        ).distinct().order_by("name")

    # رقم الفاتورة الجديد
    last_purchase = Purchase.objects.order_by("-id").first()
    next_purchase_number = f"PUR{(last_purchase.id + 1 if last_purchase else 1):04d}"

    # تحديد نوع الفاتورة وحساب الدفع والدفعة المقدمة
    first_payment = original.payments.order_by("id").first()
    payment_account_code = ""
    if first_payment:
        payment_account_code = first_payment.payment_method or (
            first_payment.financial_account.code if first_payment.financial_account else ""
        )

    down_payment_amount = 0

    if original.payment_method == "credit":
        invoice_type = "credit"
    elif original.payment_method == "credit_with_downpayment":
        invoice_type = "credit_with_downpayment"
        if first_payment:
            down_payment_amount = float(first_payment.amount)
    else:
        invoice_type = "cash"
        if not payment_account_code and original.payment_method not in ["cash", "bank_transfer", "check"]:
            payment_account_code = original.payment_method

    # بيانات الخصم والتسوية
    discount_val = float(original.discount) if getattr(original, 'discount', 0) else 0
    discount_type = getattr(original, 'discount_type', 'fixed') or "fixed"

    adj_name = getattr(original, 'adjustment_name', '') or ""
    adj_amount = float(getattr(original, 'adjustment_amount', 0)) if getattr(original, 'adjustment_amount', 0) else 0
    adj_type = "subtract" if adj_amount < 0 else "add"
    abs_adj_amount = abs(adj_amount)

    # تحضير بيانات البنود للـ template متضمنة الاسم والكود
    import json
    duplicate_items = json.dumps([
        {
            "product_id": item.product.id,
            "code": getattr(item.product, 'code', None) or getattr(item.product, 'sku', '') or getattr(item.product, 'barcode', '') or "",
            "name": item.product.name,
            "quantity": float(item.quantity),
            "unit_price": float(item.unit_price),
            "discount": float(item.discount),
            "total": float(item.total),
            "is_service": item.product.is_service,
        }
        for item in original.items.all()
    ])

    form = PurchaseForm(initial={
        "date": timezone.now().date(),
        "supplier": original.supplier,
        "warehouse": original.warehouse,
        "discount": discount_val,
        "discount_type": discount_type,
        "adjustment_name": adj_name,
        "adjustment_type": adj_type,
        "adjustment_amount": abs_adj_amount,
        "notes": original.notes,
        "payment_method": payment_account_code,
        "invoice_type": invoice_type,
        "down_payment_amount": down_payment_amount,
        "financial_category": original.financial_category,
    })

    context = {
        "form": form,
        "products": products,
        "product_categories": product_categories,
        "suppliers": suppliers,
        "warehouses": warehouses,
        "next_purchase_number": next_purchase_number,
        "selected_supplier": selected_supplier,
        "is_service_invoice": is_service_invoice,
        "supplier_type_code": selected_supplier.get_primary_type_code() if selected_supplier else None,
        "default_warehouse": original.warehouse or (warehouses.first() if warehouses.exists() else None),
        # بيانات النسخ
        "is_duplicate": True,
        "duplicate_from": original.number,
        "duplicate_items": duplicate_items,
        "duplicate_invoice_type": invoice_type,
        "duplicate_payment_method": payment_account_code,
        "duplicate_down_payment_amount": down_payment_amount,
        "duplicate_financial_category_id": f"cat_{original.financial_category.id}" if original.financial_category else None,
        "duplicate_discount": discount_val,
        "duplicate_discount_type": discount_type,
        "duplicate_adjustment_name": adj_name,
        "duplicate_adjustment_type": adj_type,
        "duplicate_adjustment_amount": abs_adj_amount,
        "page_title": f"نسخ فاتورة - {original.number}",
        "page_subtitle": f"نسخة من فاتورة {original.number} | {original.supplier.name}",
        "page_icon": "fas fa-copy",
        "header_buttons": [
            {
                "url": reverse("purchase:purchase_detail", kwargs={"pk": original.pk}),
                "icon": "fa-arrow-right",
                "text": "العودة للفاتورة الأصلية",
                "class": "btn-secondary",
            },
        ],
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": "المشتريات", "url": reverse("purchase:purchase_list"), "icon": "fas fa-shopping-bag"},
            {"title": original.number, "url": reverse("purchase:purchase_detail", kwargs={"pk": original.pk}), "icon": "fas fa-file-invoice"},
            {"title": "نسخ الفاتورة", "active": True},
        ],
    }

    return render(request, "purchase/purchase_form.html", context)
