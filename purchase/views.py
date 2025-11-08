from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from django.http import JsonResponse, HttpResponseRedirect
from django.urls import reverse
from purchase.models import (
    Purchase,
    PurchasePayment,
    PurchaseItem,
    PurchaseReturn,
    PurchaseReturnItem,
)
from .forms import (
    PurchaseForm,
    PurchaseItemForm,
    PurchasePaymentForm,
    PurchasePaymentEditForm,
    PurchaseReturnForm,
    PurchaseUpdateForm,
)
from product.models import Product, Warehouse, Stock
from decimal import Decimal
import logging
from django.db import models
from django.core.paginator import Paginator
from django.db.models import Sum
from supplier.models import Supplier
from datetime import datetime

logger = logging.getLogger(__name__)


@login_required
def purchase_list(request):
    """
    عرض قائمة فواتير المشتريات
    """
    # الاستعلام الأساسي مع ترتيب تنازلي حسب التاريخ ثم الرقم
    purchases_query = Purchase.objects.all().order_by("-date", "-id")

    # تصفية حسب المورد
    supplier = request.GET.get("supplier")
    if supplier:
        purchases_query = purchases_query.filter(supplier_id=supplier)

    # تصفية حسب حالة الدفع
    payment_status = request.GET.get("payment_status")
    if payment_status:
        purchases_query = purchases_query.filter(payment_status=payment_status)

    # تصفية حسب التاريخ
    date_from = request.GET.get("date_from")
    if date_from:
        purchases_query = purchases_query.filter(date__gte=date_from)

    date_to = request.GET.get("date_to")
    if date_to:
        purchases_query = purchases_query.filter(date__lte=date_to)

    # التصفح والترقيم
    paginator = Paginator(purchases_query, 25)  # 25 فاتورة في كل صفحة
    page = request.GET.get("page")
    purchases = paginator.get_page(page)

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
        {"key": "supplier.name", "label": _("المورد"), "sortable": True},
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
            "key": "payment_method",
            "label": _("طريقة الدفع"),
            "sortable": True,
            "class": "text-center",
            "template": "components/cells/purchase_payment_method.html",
        },
        {
            "key": "payment_status",
            "label": _("حالة الدفع"),
            "sortable": True,
            "class": "text-center",
            "format": "status",
        },
        {
            "key": "return_status",
            "label": _("حالة الإرجاع"),
            "sortable": True,
            "class": "text-center",
            "format": "status",
        },
    ]

    # تعريف أزرار الإجراءات للجدول
    purchase_actions = [
        {
            "url": "purchase:purchase_detail",
            "icon": "fa-eye",
            "label": _("عرض"),
            "class": "action-view",
        },
        {
            "url": "purchase:purchase_edit",
            "icon": "fa-edit",
            "label": _("تعديل"),
            "class": "action-edit",
            "condition": "not_fully_paid",
        },
        {
            "url": "purchase:purchase_delete",
            "icon": "fa-trash",
            "label": _("حذف"),
            "class": "action-delete",
            "condition": "no_posted_payments",
        },
        {
            "url": "purchase:purchase_add_payment",
            "icon": "fa-money-bill",
            "label": _("إضافة دفعة"),
            "class": "action-paid",
            "condition": "not_fully_paid",
        },
    ]

    context = {
        "purchases": purchases,
        "paid_purchases_count": paid_purchases_count,
        "partially_paid_purchases_count": partially_paid_purchases_count,
        "unpaid_purchases_count": unpaid_purchases_count,
        "returned_purchases_count": returned_purchases_count,
        "total_amount": total_amount,
        "suppliers": suppliers,
        "purchase_headers": purchase_headers,
        "purchase_actions": purchase_actions,
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
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {"title": "المشتريات", "url": "#", "icon": "fas fa-truck"},
            {"title": "فواتير المشتريات", "active": True},
        ],
    }

    return render(request, "purchase/purchase_list.html", context)


@login_required
def purchase_create(request, supplier_id=None):
    """
    إنشاء فاتورة مشتريات جديدة
    يمكن تمرير معرف المورد لاختياره تلقائياً
    """
    products = Product.objects.filter(is_active=True).order_by("name")
    
    # التحقق من وجود المورد إذا تم تمرير معرفه
    selected_supplier = None
    if supplier_id:
        try:
            selected_supplier = Supplier.objects.get(id=supplier_id, is_active=True)
        except Supplier.DoesNotExist:
            messages.error(request, "المورد المحدد غير موجود أو غير نشط")
            return redirect("purchase:purchase_list")

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
                    purchase.save()

                    # إضافة بنود الفاتورة
                    product_ids = request.POST.getlist("product[]")
                    quantities = request.POST.getlist("quantity[]")
                    unit_prices = request.POST.getlist("unit_price[]")
                    discounts = request.POST.getlist("discount[]")

                    for i in range(len(product_ids)):
                        if product_ids[i]:  # تخطي الصفوف الفارغة
                            product = get_object_or_404(Product, id=product_ids[i])
                            quantity = int(float(quantities[i]))
                            unit_price = Decimal(unit_prices[i])
                            discount = (
                                Decimal(discounts[i]) if discounts[i] else Decimal("0")
                            )

                            # إنشاء بند فاتورة
                            # Signal سيتولى إنشاء حركة المخزون تلقائياً
                            item = PurchaseItem(
                                purchase=purchase,
                                product=product,
                                quantity=quantity,
                                unit_price=unit_price,
                                discount=discount,
                                total=(Decimal(quantity) * unit_price) - discount,
                            )
                            item.save()

                    # إنشاء دفعة تلقائية للفواتير النقدية
                    if purchase.payment_method == "cash":
                        financial_account_id = request.POST.get("financial_account")
                        if financial_account_id:
                            try:
                                from financial.models.chart_of_accounts import (
                                    ChartOfAccounts,
                                )

                                financial_account = ChartOfAccounts.objects.get(
                                    id=financial_account_id
                                )

                                # إنشاء دفعة تلقائية بالمبلغ الكامل
                                payment = PurchasePayment.objects.create(
                                    purchase=purchase,
                                    amount=purchase.total,
                                    payment_date=purchase.date,
                                    payment_method="cash",
                                    financial_account=financial_account,
                                    created_by=request.user,
                                    notes="دفعة تلقائية - فاتورة نقدية",
                                    status="posted",
                                )

                                # إنشاء قيد محاسبي للدفعة
                                from financial.services.accounting_integration_service import (
                                    AccountingIntegrationService,
                                )

                                journal_entry = AccountingIntegrationService.create_payment_journal_entry(
                                    payment=payment,
                                    payment_type="purchase_payment",
                                    user=request.user,
                                )

                                if journal_entry:
                                    payment.financial_transaction = journal_entry
                                    payment.financial_status = "synced"
                                    payment.save(
                                        update_fields=[
                                            "financial_transaction",
                                            "financial_status",
                                        ]
                                    )
                                    logger.info(
                                        f"✅ تم إنشاء دفعة تلقائية وقيد محاسبي للفاتورة النقدية: {purchase.number}"
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
                messages.error(request, f"حدث خطأ أثناء إنشاء الفاتورة: {str(e)}")
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
            
        form = PurchaseForm(initial=initial_data)

    # جلب البيانات المطلوبة للقوائم المنسدلة (مطلوب في كل الحالات)
    suppliers = Supplier.objects.filter(is_active=True).order_by("name")
    warehouses = Warehouse.objects.filter(is_active=True).order_by("name")
    
    # إضافة أول مخزن متاح كافتراضي للنموذج الجديد
    if request.method == "GET" and warehouses.exists():
        form.initial["warehouse"] = warehouses.first()

    # إنشاء رقم فاتورة مشتريات جديد
    last_purchase = Purchase.objects.order_by("-id").first()
    next_purchase_number = f"PUR{(last_purchase.id + 1 if last_purchase else 1):04d}"

    # إضافة متغيرات عنوان الصفحة
    context = {
        "form": form,
        "products": products,
        "suppliers": suppliers,  # إضافة قائمة الموردين للقالب
        "warehouses": warehouses,  # إضافة قائمة المخازن للقالب
        "next_purchase_number": next_purchase_number,  # إضافة رقم الفاتورة التالي للقالب
        "selected_supplier": selected_supplier,  # إضافة المورد المحدد للسياق
        "default_warehouse": warehouses.first() if warehouses.exists() else None,  # المخزن الافتراضي
        "page_title": "إضافة فاتورة مشتريات" + (f" - {selected_supplier.name}" if selected_supplier else ""),
        "page_subtitle": "إضافة فاتورة مشتريات جديدة إلى النظام",
        "page_icon": "fas fa-plus-circle",
        "header_buttons": [
            {
                "url": reverse("supplier:supplier_detail", kwargs={"pk": selected_supplier.pk}) if selected_supplier else reverse("purchase:purchase_list"),
                "icon": "fa-arrow-right",
                "text": "العودة لتفاصيل المورد" if selected_supplier else "العودة للقائمة",
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
                "title": "المشتريات",
                "url": reverse("purchase:purchase_list"),
                "icon": "fas fa-shopping-bag",
            },
        ] + ([{
            "title": selected_supplier.name,
            "url": reverse("supplier:supplier_detail", kwargs={"pk": selected_supplier.pk}),
            "icon": "fas fa-truck",
        }] if selected_supplier else []) + [
            {"title": "إضافة فاتورة", "active": True},
        ],
    }

    return render(request, "purchase/purchase_form.html", context)




# تم حذف purchase_payment_list - غير مستخدم (لا يوجد URL مربوط)




@login_required
def purchase_detail(request, pk):
    """
    عرض تفاصيل فاتورة المشتريات
    """
    purchase = get_object_or_404(Purchase, pk=pk)
    # الحصول على المدفوعات مرتبة حسب تاريخ الإنشاء من الأحدث إلى الأقدم
    payments = purchase.payments.all().order_by("-created_at")

    # فحص إذا كان يجب عرض SweetAlert للترحيل
    show_post_alert = request.session.pop("show_post_alert", None)

    context = {
        "purchase": purchase,
        "payments": payments,  # تمرير المدفوعات المرتبة للقالب
        "title": "تفاصيل فاتورة المشتريات",
        "page_title": f"فاتورة مشتريات - {purchase.number}",
        "page_subtitle": "عرض تفاصيل فاتورة المشتريات وإدارتها",
        "page_icon": "fas fa-file-invoice",
        "show_post_alert": show_post_alert,  # إضافة معلومات SweetAlert
        "header_buttons": [
            {
                "url": reverse("purchase:purchase_print", kwargs={"pk": purchase.pk}),
                "icon": "fa-print",
                "text": "طباعة",
                "class": "btn-info",
            },
        ] + ([{
            "url": reverse("purchase:purchase_add_payment", kwargs={"pk": purchase.pk}),
            "icon": "fa-money-bill",
            "text": "إضافة دفعة",
            "class": "btn-success",
        }] if purchase.payment_status != 'paid' else []) + [
            {
                "url": "#",
                "icon": "fa-ellipsis-v",
                "text": "",
                "class": "btn-outline-secondary",
                "toggle": "modal",
                "target": "#actionsModal",
            },
        ],
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
                "title": purchase.supplier.name,
                "url": reverse("supplier:supplier_detail", args=[purchase.supplier.pk]),
                "icon": "fas fa-truck",
            },
            {"title": f"فاتورة {purchase.number}", "active": True},
        ],
    }
    return render(request, "purchase/purchase_detail.html", context)


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
                        if not product_ids[i]:  # تخطي البنود الفارغة
                            continue

                        product = get_object_or_404(Product, id=product_ids[i])
                        quantity = int(quantities[i])
                        unit_price = Decimal(unit_prices[i])
                        discount = Decimal(discounts[i] if discounts[i] else "0")

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
                        # حفظ الكمية الجديدة في القاموس
                        new_items[product.id] = quantity

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

                    # معالجة المنتجات المضافة أو التي تغيرت كميتها
                    for product_id, new_quantity in new_items.items():
                        original_quantity = original_items.get(product_id, 0)
                        quantity_diff = new_quantity - original_quantity

                        if quantity_diff != 0:  # فقط إذا كان هناك تغيير في الكمية
                            product = Product.objects.get(id=product_id)

                            # الحصول على المخزون الحالي
                            stock, created = Stock.objects.get_or_create(
                                product=product,
                                warehouse=updated_purchase.warehouse,
                                defaults={"quantity": 0},
                            )

                            # تحديث المخزون يدوياً حسب اتجاه التغيير
                            if (
                                quantity_diff > 0
                            ):  # إذا زادت الكمية، نضيف الزيادة للمخزون
                                stock.quantity += quantity_diff

                                # إنشاء حركة مخزون للإضافة
                                StockMovement.objects.create(
                                    product=product,
                                    warehouse=updated_purchase.warehouse,
                                    movement_type="in",
                                    quantity=quantity_diff,
                                    reference_number=f"{main_reference}-EDIT-IN-{timezone.now().strftime('%Y%m%d%H%M%S')}",
                                    document_type="purchase",
                                    document_number=updated_purchase.number,
                                    notes=f"زيادة كمية منتج في تعديل فاتورة مشتريات رقم {updated_purchase.number}",
                                    created_by=request.user,
                                )
                            else:  # إذا قلت الكمية، نخصم الفرق من المخزون
                                stock.quantity -= abs(quantity_diff)
                                if stock.quantity < 0:
                                    stock.quantity = 0

                                # إنشاء حركة مخزون للخصم
                                StockMovement.objects.create(
                                    product=product,
                                    warehouse=updated_purchase.warehouse,
                                    movement_type="out",
                                    quantity=abs(quantity_diff),
                                    reference_number=f"{main_reference}-EDIT-OUT-{timezone.now().strftime('%Y%m%d%H%M%S')}",
                                    document_type="purchase",
                                    document_number=updated_purchase.number,
                                    notes=f"نقص كمية منتج في تعديل فاتورة مشتريات رقم {updated_purchase.number}",
                                    created_by=request.user,
                                )

                            stock.save()

                    # معالجة المنتجات المحذوفة (المنتجات الموجودة في البنود القديمة وليست في البنود الجديدة)
                    for product_id, original_quantity in original_items.items():
                        if (
                            product_id not in new_items
                        ):  # إذا كان المنتج موجود سابقًا وتم حذفه
                            product = Product.objects.get(id=product_id)

                            # الحصول على المخزون الحالي
                            stock, created = Stock.objects.get_or_create(
                                product=product,
                                warehouse=updated_purchase.warehouse,
                                defaults={"quantity": 0},
                            )

                            # خصم الكمية المحذوفة من المخزون
                            stock.quantity -= original_quantity
                            if stock.quantity < 0:
                                stock.quantity = 0
                            stock.save()

                            # إنشاء حركة مخزون للخصم
                            StockMovement.objects.create(
                                product=product,
                                warehouse=updated_purchase.warehouse,
                                movement_type="out",
                                quantity=original_quantity,
                                reference_number=f"{main_reference}-EDIT-DELETE-{timezone.now().strftime('%Y%m%d%H%M%S')}",
                                document_type="purchase",
                                document_number=updated_purchase.number,
                                notes=f"حذف منتج من فاتورة مشتريات رقم {updated_purchase.number}",
                                created_by=request.user,
                            )

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
        form = PurchaseUpdateForm(instance=purchase)

    # جلب البيانات المطلوبة للقوائم المنسدلة
    suppliers = Supplier.objects.filter(is_active=True).order_by("name")
    warehouses = Warehouse.objects.filter(is_active=True).order_by("name")
    products = Product.objects.filter(is_active=True).order_by("name")

    context = {
        "form": form,
        "purchase": purchase,
        "products": products,
        "suppliers": suppliers,  # إضافة قائمة الموردين للقالب
        "warehouses": warehouses,  # إضافة قائمة المخازن للقالب
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
            
            # ✅ التحقق من المخزون المتاح قبل الحذف
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
                # ✅ تم إزالة إنشاء حركات return_out لتجنب الازدواجية
                # signal handle_deleted_purchase_item سيتولى إنشاء الحركات المعاكسة

                # إلغاء ترحيل وحذف القيد المحاسبي المرتبط بالفاتورة إذا وُجد
                journal_entry_info = ""
                if purchase.journal_entry:
                    journal_entry = purchase.journal_entry
                    journal_entry_number = journal_entry.number
                    journal_entry_status = journal_entry.status
                    
                    import logging
                    logger = logging.getLogger(__name__)
                    
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


@login_required
def purchase_print(request, pk):
    """
    طباعة فاتورة المشتريات
    """
    purchase = get_object_or_404(Purchase, pk=pk)
    today = timezone.now().date()
    year = timezone.now().year

    context = {
        "purchase": purchase,
        "title": f"طباعة فاتورة المشتريات - {purchase.number}",
        "today": today,
        "year": year,
    }

    return render(request, "purchase/purchase_print.html", context)


@login_required
def payment_detail(request, pk):
    """
    عرض تفاصيل دفعة المشتريات
    """
    payment = get_object_or_404(PurchasePayment, pk=pk)
    purchase = payment.purchase

    # معلومات إضافية للدفعة
    financial_info = {
        "has_journal_entry": bool(payment.financial_transaction),
        "journal_entry": payment.financial_transaction,
        "sync_status": payment.financial_status,
        "sync_error": payment.financial_error,
        "can_edit": payment.can_edit,
        "can_delete": payment.can_delete,
        "is_synced": payment.is_financially_synced,
    }

    context = {
        "payment": payment,
        "purchase": purchase,
        "invoice": purchase,  # للتوافق مع القوالب المشتركة
        "financial_info": financial_info,
        "page_title": f"دفعة رقم #{payment.id}",
        "page_subtitle": f"فاتورة {purchase.number} | {purchase.supplier.name}",
        "page_icon": "fas fa-money-bill-wave",
        "header_buttons": [
            {
                "url": reverse("purchase:purchase_detail", kwargs={"pk": purchase.pk}),
                "icon": "fa-arrow-left",
                "text": "العودة للفاتورة",
                "class": "btn-outline-secondary",
            },
        ],
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
                "title": purchase.supplier.name,
                "url": reverse("supplier:supplier_detail", args=[purchase.supplier.pk]),
                "icon": "fas fa-truck",
            },
            {
                "title": f"فاتورة {purchase.number}",
                "url": reverse("purchase:purchase_detail", kwargs={"pk": purchase.pk}),
                "icon": "fas fa-file-invoice",
            },
            {
                "title": f"دفعة #{payment.id}",
                "active": True,
                "icon": "fas fa-money-bill-wave",
            },
        ],
    }

    return render(request, "purchase/payment_detail.html", context)


@login_required
def add_payment(request, pk):
    """
    إضافة دفعة لفاتورة الشراء - محدث بالتكامل المالي الشامل
    """
    purchase = get_object_or_404(Purchase, pk=pk)

    if request.method == "POST":
        form = PurchasePaymentForm(request.POST, purchase=purchase)
        if form.is_valid():
            try:
                with transaction.atomic():
                    # حفظ الدفعة أولاً
                    payment = form.save(commit=False)
                    payment.purchase = purchase
                    payment.created_by = request.user

                    # تأكد من أن المبلغ لا يتجاوز المبلغ المستحق
                    if payment.amount > purchase.amount_due:
                        messages.warning(
                            request, _("تم تقليل المبلغ إلى القيمة المستحقة المتبقية")
                        )
                        payment.amount = purchase.amount_due

                    # حفظ الدفعة كمسودة (بدون ربط مالي)
                    payment.status = "draft"
                    payment.save()

                    # ملاحظة: الربط المالي سيحدث عند الترحيل فقط
                    # لم يعد يتم الربط التلقائي عند الإنشاء

                    # تحديث حالة فاتورة الشراء
                    purchase.refresh_from_db()
                    if purchase.amount_due <= 0:
                        purchase.payment_status = "paid"
                    elif purchase.amount_paid > 0:
                        purchase.payment_status = "partially_paid"
                    purchase.save()

                    messages.success(request, _("تم تسجيل الدفعة بنجاح"))
                    return redirect("purchase:purchase_detail", pk=purchase.pk)

            except Exception as e:
                logger.error(f"خطأ في حفظ دفعة المشتريات: {str(e)}")
                messages.error(request, f"حدث خطأ أثناء حفظ الدفعة: {str(e)}")
        else:
            # عرض أخطاء النموذج
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"خطأ في الحقل {field}: {error}")
    else:
        # تعبئة قيمة افتراضية للمبلغ (المبلغ المستحق)
        initial_data = {
            "amount": purchase.amount_due,
            "payment_date": datetime.now().date(),
        }
        form = PurchasePaymentForm(initial=initial_data, purchase=purchase)

    context = {
        "invoice": purchase,  # استخدام invoice بدلاً من purchase للنموذج المشترك
        "form": form,
        "is_purchase": True,  # تحديد أن هذا نموذج دفع للمشتريات
        "page_title": f"إضافة دفعة لفاتورة المشتريات {purchase.number}",
        "title": f"إضافة دفعة لفاتورة المشتريات {purchase.number}",
        "page_icon": "fas fa-money-bill-wave",
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
            {
                "title": purchase.number,
                "url": reverse("purchase:purchase_detail", kwargs={"pk": purchase.pk}),
            },
            {"title": "إضافة دفعة", "active": True},
        ],
    }

    return render(request, "purchase/purchase_payment_form.html", context)


@login_required
def purchase_return(request, pk):
    """
    إرجاع فاتورة المشتريات
    """
    purchase = get_object_or_404(Purchase, pk=pk)
    items = purchase.items.all()

    # الحصول على الكميات المرتجعة سابقاً لكل عنصر
    previously_returned_quantities = {}
    for item in items:
        returned_items = PurchaseReturnItem.objects.filter(
            purchase_item=item, purchase_return__status__in=["draft", "confirmed"]
        )
        previously_returned_quantities[item.id] = sum(
            returned_item.quantity for returned_item in returned_items
        )

    if request.method == "POST":
        try:
            # استيراد StockMovement محلياً لتجنب مشاكل الاستيراد الدائري
            from product.models import StockMovement
            
            with transaction.atomic():
                # إنشاء مرتجع المشتريات
                return_data = {
                    "date": request.POST.get("date") or timezone.now().date(),
                    "warehouse": purchase.warehouse.id,  # استخدام نفس مخزن الفاتورة
                    "notes": request.POST.get("notes", ""),
                }

                return_form = PurchaseReturnForm(return_data)
                if return_form.is_valid():
                    purchase_return = return_form.save(commit=False)
                    purchase_return.purchase = purchase
                    purchase_return.created_by = request.user
                    purchase_return.warehouse = (
                        purchase.warehouse
                    )  # استخدام نفس مخزن الفاتورة

                    # تعيين قيم افتراضية للحقول المطلوبة
                    purchase_return.subtotal = 0
                    purchase_return.discount = 0
                    purchase_return.tax = 0
                    purchase_return.total = 0

                    # تحديد رقم المرتجع
                    if not purchase_return.number:
                        from django.utils.crypto import get_random_string

                        purchase_return.number = f"RET-{get_random_string(6).upper()}"

                    purchase_return.save()

                    # إضافة بنود المرتجع
                    item_ids = request.POST.getlist("item_id")
                    return_quantities = request.POST.getlist("return_quantity")
                    return_reasons = request.POST.getlist("return_reason")

                    valid_items = False  # التحقق من وجود منتجات مرتجعة
                    subtotal = 0
                    for i in range(len(item_ids)):
                        if (
                            not item_ids[i]
                            or not return_quantities[i]
                            or int(return_quantities[i]) <= 0
                        ):
                            continue  # تجاهل البنود الفارغة أو الصفرية

                        try:
                            purchase_item = get_object_or_404(
                                PurchaseItem, id=item_ids[i]
                            )
                            return_quantity = int(float(return_quantities[i]))
                            previously_returned = previously_returned_quantities.get(
                                purchase_item.id, 0
                            )
                            available_quantity = (
                                purchase_item.quantity - previously_returned
                            )

                            return_reason = (
                                return_reasons[i]
                                if i < len(return_reasons) and return_reasons[i]
                                else "إرجاع بضاعة"
                            )

                            # التأكد من أن الكمية المرتجعة لا تتجاوز الكمية المتبقية
                            if return_quantity > available_quantity:
                                messages.warning(
                                    request,
                                    f"تم تعديل الكمية المرتجعة للمنتج {purchase_item.product.name} إلى {available_quantity} (الكمية المتبقية المتاحة للإرجاع)",
                                )
                                return_quantity = available_quantity

                            # تجاهل العناصر التي ليس لديها كمية متاحة للإرجاع
                            if return_quantity <= 0:
                                continue

                            # إنشاء بند المرتجع
                            return_item = PurchaseReturnItem(
                                purchase_return=purchase_return,
                                purchase_item=purchase_item,
                                product=purchase_item.product,
                                quantity=return_quantity,
                                unit_price=purchase_item.unit_price,
                                discount=0,  # تعيين قيمة افتراضية
                                total=(
                                    return_quantity * purchase_item.unit_price
                                ),  # حساب الإجمالي
                                reason=return_reason,
                            )
                            return_item.save()

                            valid_items = True  # تم إنشاء بند واحد على الأقل بنجاح

                            # تحديث المجموع
                            subtotal += return_item.total

                            # إنشاء حركة مخزون صادر (مرتجع مشتريات)
                            StockMovement.objects.create(
                                product=purchase_item.product,
                                warehouse=purchase_return.warehouse,
                                movement_type="return_out",
                                quantity=return_quantity,
                                reference_number=f"RETURN-{purchase_return.number}-ITEM{return_item.id}",
                                document_type="purchase_return",
                                document_number=purchase_return.number,
                                notes=f"مرتجع مشتريات - {return_reason}",
                                created_by=request.user,
                            )
                        except Exception as e:
                            logger.error(f"Error processing return item: {str(e)}")
                            continue

                    if not valid_items:
                        # إذا لم يتم إضافة أي بنود صالحة، قم بإلغاء العملية
                        messages.error(
                            request, "يرجى تحديد كمية مرتجعة واحدة على الأقل"
                        )
                        raise Exception("لم يتم تحديد أي منتجات للإرجاع")

                    # تحديث المرتجع
                    purchase_return.subtotal = subtotal
                    purchase_return.tax = 0  # إزالة الضريبة
                    purchase_return.total = (
                        subtotal  # الإجمالي يساوي المجموع الفرعي بدون ضريبة
                    )
                    purchase_return.save()

                    messages.success(request, "تم إنشاء مرتجع المشتريات بنجاح")
                    return redirect("purchase:purchase_detail", pk=purchase.pk)
                else:
                    for field, errors in return_form.errors.items():
                        for error in errors:
                            messages.error(request, f"خطأ في حقل {field}: {error}")
        except Exception as e:
            messages.error(request, f"حدث خطأ أثناء إنشاء مرتجع المشتريات: {str(e)}")
            logger.error(f"Error creating purchase return: {str(e)}")

    # حساب الكميات المتبقية للعرض
    available_quantities = {}
    for item in items:
        available_quantities[item.id] = item.quantity - previously_returned_quantities.get(item.id, 0)
    
    context = {
        "purchase": purchase,
        "items": items,
        "page_title": f"مرتجع مشتريات",
        "page_subtitle": f"فاتورة {purchase.number} | {purchase.supplier.name}",
        "page_icon": "fas fa-undo-alt",
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
            {"title": "مرتجع مشتريات", "active": True},
        ],
        "previously_returned_quantities": previously_returned_quantities,
        "has_returns": any(previously_returned_quantities.values()),
    }
    return render(request, "purchase/purchase_return.html", context)

@login_required
def purchase_return_list(request):
    """
    عرض قائمة مرتجعات المشتريات
    """
    returns = (
        PurchaseReturn.objects.all()
        .select_related("purchase", "purchase__supplier")
        .order_by("-date", "-id")
    )

    # تعريف أعمدة جدول مرتجعات المشتريات
    return_headers = [
        {
            "key": "id",
            "label": "#",
            "sortable": True,
            "class": "text-center",
            "width": "50px",
        },
        {
            "key": "purchase.number",
            "label": "رقم الفاتورة",
            "sortable": True,
            "class": "text-center",
            "width": "120px",
        },
        {
            "key": "purchase.supplier.name",
            "label": "المورد",
            "sortable": True,
            "class": "text-start",
        },
        {
            "key": "date",
            "label": "تاريخ المرتجع",
            "sortable": True,
            "class": "text-center",
            "format": "date",
            "width": "120px",
        },
        {
            "key": "total_amount",
            "label": "إجمالي المرتجع",
            "sortable": True,
            "class": "text-center",
            "format": "currency",
            "width": "120px",
        },
        {
            "key": "status",
            "label": "الحالة",
            "sortable": True,
            "class": "text-center",
            "template": "components/cells/return_status.html",
            "width": "100px",
        },
    ]

    # أزرار الإجراءات
    return_actions = [
        {
            "url": "purchase:purchase_return_detail",
            "icon": "fa-eye",
            "label": "عرض",
            "class": "action-view",
        },
    ]

    context = {
        "returns": returns,
        "return_headers": return_headers,
        "return_actions": return_actions,
        "primary_key": "id",
        "page_title": "مرتجعات المشتريات",
        "page_subtitle": "إدارة ومتابعة جميع مرتجعات المشتريات",
        "page_icon": "fas fa-undo-alt",
        "header_buttons": [
            {
                "url": reverse("purchase:purchase_list"),
                "icon": "fa-shopping-cart",
                "text": "المشتريات",
                "class": "btn-outline-primary",
            },
        ],
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "المشتريات",
                "url": reverse("purchase:purchase_list"),
                "icon": "fas fa-truck",
            },
            {"title": "مرتجعات المشتريات", "active": True},
        ],
    }

    return render(request, "purchase/purchase_return_list.html", context)


@login_required
def purchase_return_detail(request, pk):
    """
    عرض تفاصيل مرتجع المشتريات
    """
    purchase_return = get_object_or_404(PurchaseReturn, pk=pk)

    context = {
        "purchase_return": purchase_return,
        "page_title": f"مرتجع رقم {purchase_return.number}",
        "page_subtitle": f"فاتورة {purchase_return.purchase.number} | {purchase_return.purchase.supplier.name}",
        "page_icon": "fas fa-undo-alt",
        "header_buttons": [
            {
                "url": reverse("purchase:purchase_return_list"),
                "icon": "fa-list",
                "text": "العودة للقائمة",
                "class": "btn-outline-secondary",
            },
        ] + ([
            {
                "url": reverse("purchase:purchase_return_confirm", kwargs={"pk": purchase_return.pk}),
                "icon": "fa-check",
                "text": "تأكيد المرتجع",
                "class": "btn-success",
                "onclick": "return confirm('هل أنت متأكد من تأكيد هذا المرتجع؟')",
            },
            {
                "url": reverse("purchase:purchase_return_cancel", kwargs={"pk": purchase_return.pk}),
                "icon": "fa-times",
                "text": "إلغاء المرتجع",
                "class": "btn-danger",
                "onclick": "return confirm('هل أنت متأكد من إلغاء هذا المرتجع؟')",
            },
        ] if purchase_return.status == 'draft' else []),
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
                "title": "مرتجعات المشتريات",
                "url": reverse("purchase:purchase_return_list"),
                "icon": "fas fa-undo-alt",
            },
            {"title": purchase_return.number, "active": True},
        ],
    }

    return render(request, "purchase/purchase_return_detail.html", context)


@login_required
def purchase_return_confirm(request, pk):
    """
    تأكيد مرتجع المشتريات وتغيير حالته من مسودة إلى مؤكد
    """
    purchase_return = get_object_or_404(PurchaseReturn, pk=pk)

    # التأكد من أن المرتجع في حالة مسودة
    if purchase_return.status != "draft":
        messages.error(request, "لا يمكن تأكيد مرتجع تم تأكيده أو إلغاؤه من قبل")
        return redirect("purchase:purchase_return_detail", pk=purchase_return.pk)

    try:
        with transaction.atomic():
            # تحديث حالة المرتجع إلى مؤكد
            purchase_return.status = "confirmed"
            purchase_return.save()

            # يمكن هنا إضافة أي إجراءات إضافية مثل تحديث حسابات المورد
            # أو إنشاء قيود محاسبية أو إرسال إشعارات للموردين المعنيين

            messages.success(request, "تم تأكيد مرتجع المشتريات بنجاح")
    except Exception as e:
        logger.error(f"Error confirming purchase return: {str(e)}")
        messages.error(request, f"حدث خطأ أثناء تأكيد المرتجع: {str(e)}")

    return redirect("purchase:purchase_return_detail", pk=purchase_return.pk)


@login_required
def purchase_return_cancel(request, pk):
    """
    إلغاء مرتجع المشتريات وتغيير حالته إلى ملغي
    """
    purchase_return = get_object_or_404(PurchaseReturn, pk=pk)

    # التأكد من أن المرتجع في حالة مسودة
    if purchase_return.status != "draft":
        messages.error(request, "لا يمكن إلغاء مرتجع تم تأكيده أو إلغاؤه من قبل")
        return redirect("purchase:purchase_return_detail", pk=purchase_return.pk)

    try:
        with transaction.atomic():
            # تحديث حالة المرتجع إلى ملغي
            purchase_return.status = "cancelled"
            purchase_return.save()

            # يمكن هنا إضافة أي إجراءات إضافية مثل عكس حركات المخزون المرتبطة بالمرتجع

            messages.success(request, "تم إلغاء مرتجع المشتريات بنجاح")
    except Exception as e:
        logger.error(f"Error cancelling purchase return: {str(e)}")
        messages.error(request, f"حدث خطأ أثناء إلغاء المرتجع: {str(e)}")

    return redirect("purchase:purchase_return_detail", pk=purchase_return.pk)


@login_required
def post_payment(request, payment_id):
    """
    ترحيل دفعة مشتريات - إنشاء القيود المحاسبية وحركات الخزن
    """
    payment = get_object_or_404(PurchasePayment, pk=payment_id)

    # التحقق من أن الدفعة مسودة
    if payment.status != "draft":
        messages.error(request, "لا يمكن ترحيل دفعة مرحّلة مسبقاً")
        return redirect("purchase:purchase_detail", pk=payment.purchase.pk)

    try:
        with transaction.atomic():
            # استخدام خدمة التكامل المالي
            from financial.services.payment_integration_service import (
                payment_integration_service,
            )

            integration_result = payment_integration_service.process_payment(
                payment=payment, payment_type="purchase", user=request.user
            )

            if integration_result["success"]:
                # تحديث حالة الدفعة
                payment.status = "posted"
                payment.posted_at = timezone.now()
                payment.posted_by = request.user
                payment.save(update_fields=["status", "posted_at", "posted_by"])

                messages.success(
                    request,
                    f'تم ترحيل الدفعة بنجاح - القيد: {integration_result.get("journal_entry_number")}',
                )
            else:
                messages.error(
                    request, f'فشل الترحيل: {integration_result.get("message")}'
                )

    except Exception as e:
        logger.error(f"خطأ في ترحيل الدفعة {payment_id}: {str(e)}")
        messages.error(request, f"حدث خطأ أثناء الترحيل: {str(e)}")

    return redirect("purchase:purchase_detail", pk=payment.purchase.pk)


@login_required
def unpost_payment(request, payment_id):
    """
    إلغاء ترحيل دفعة مشتريات - إنشاء قيد عكسي وحذف حركة الخزن
    """
    payment = get_object_or_404(PurchasePayment, pk=payment_id)

    # التحقق من أن الدفعة مرحّلة
    if payment.status != "posted":
        messages.error(request, "لا يمكن إلغاء ترحيل دفعة غير مرحّلة")
        return redirect("purchase:purchase_detail", pk=payment.purchase.pk)

    try:
        with transaction.atomic():
            # إنشاء قيد عكسي للقيد المحاسبي
            if payment.financial_transaction:
                try:
                    reversal_entry = payment.financial_transaction.reverse(
                        user=request.user,
                        reason=f"إلغاء ترحيل دفعة مشتريات رقم {payment.id}",
                    )
                    logger.info(f"تم إنشاء قيد عكسي: {reversal_entry.number}")
                except Exception as e:
                    logger.warning(f"فشل إنشاء القيد العكسي: {str(e)}")
                    # في حالة فشل القيد العكسي، نحاول الحذف المباشر
                    payment.financial_transaction.status = "draft"
                    payment.financial_transaction.save()
                    payment.financial_transaction.delete()

            # حذف حركة الخزن (إذا وجدت)
            # البحث عن حركة الخزن المرتبطة بهذه الدفعة
            try:
                from financial.models.cash_movement import CashMovement

                cash_movements = CashMovement.objects.filter(
                    notes__icontains=f"PURCH_PAY_{payment.id}"
                ).filter(status__in=["approved", "executed"])

                for movement in cash_movements:
                    movement.status = "draft"
                    movement.save()
                    movement.delete()
                    logger.info(f"تم حذف حركة الخزن: {movement.id}")
            except Exception as e:
                logger.warning(f"فشل في حذف حركة الخزن: {str(e)}")

            # تحديث حالة الدفعة
            payment.status = "draft"
            payment.posted_at = None
            payment.posted_by = None
            payment.financial_transaction = None
            payment.financial_status = "pending"
            payment.save()

            messages.success(request, "تم إلغاء ترحيل الدفعة بنجاح")

    except Exception as e:
        logger.error(f"خطأ في إلغاء ترحيل الدفعة {payment_id}: {str(e)}")
        messages.error(request, f"حدث خطأ أثناء إلغاء الترحيل: {str(e)}")

    return redirect("purchase:purchase_detail", pk=payment.purchase.pk)


@login_required
def edit_payment(request, payment_id):
    """
    تعديل دفعة مشتريات - نظام مبسط وفعال
    """
    payment = get_object_or_404(PurchasePayment, pk=payment_id)

    # استيراد خدمة التعديل
    try:
        from financial.services.payment_edit_service import PaymentEditService
    except ImportError:
        messages.error(request, "خدمة تعديل الدفعات غير متاحة")
        return redirect("purchase:purchase_detail", pk=payment.purchase.pk)

    # فحص الصلاحيات
    permissions = PaymentEditService.get_edit_permissions(request.user, payment)
    if not permissions["can_edit"]:
        messages.error(request, "ليس لديك صلاحية تعديل هذه الدفعة")
        return redirect("purchase:purchase_detail", pk=payment.purchase.pk)

    if request.method == "POST":
        form = PurchasePaymentEditForm(
            request.POST, instance=payment, purchase=payment.purchase
        )
        if form.is_valid():
            try:
                # تحضير بيانات التعديل
                new_data = {
                    "amount": form.cleaned_data["amount"],
                    "payment_date": form.cleaned_data["payment_date"],
                    "payment_method": form.cleaned_data["payment_method"],
                    "financial_account": form.cleaned_data["financial_account"],
                    "reference_number": form.cleaned_data.get("reference_number", ""),
                    "notes": form.cleaned_data.get("notes", ""),
                }

                # تنفيذ التعديل عبر الخدمة
                result = PaymentEditService.edit_payment(
                    payment=payment,
                    payment_type="purchase",
                    new_data=new_data,
                    user=request.user,
                )

                if result["success"]:
                    messages.success(request, result["message"])
                    # إضافة معلومات لعرض SweetAlert إذا كانت الدفعة مسودة
                    if payment.status == "draft":
                        # إضافة معلومات لعرض SweetAlert
                        request.session["show_post_alert"] = {
                            "payment_id": payment.id,
                            "payment_type": "purchase",
                        }
                    return redirect("purchase:purchase_detail", pk=payment.purchase.pk)
                else:
                    messages.error(request, result["message"])

            except Exception as e:
                logger.error(f"خطأ في تعديل الدفعة {payment_id}: {str(e)}")
                messages.error(request, f"حدث خطأ أثناء تعديل الدفعة: {str(e)}")
        else:
            # عرض أخطاء النموذج
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"خطأ في الحقل {field}: {error}")
    else:
        form = PurchasePaymentEditForm(instance=payment, purchase=payment.purchase)

    context = {
        "form": form,
        "payment": payment,
        "purchase": payment.purchase,
        "permissions": permissions,
        "page_title": f"تعديل الدفعة #{payment.id}",
        "page_subtitle": f"فاتورة {payment.purchase.number} | {payment.purchase.supplier.name}",
        "page_icon": "fas fa-edit",
        "header_buttons": [
            {
                "url": reverse("purchase:purchase_detail", kwargs={"pk": payment.purchase.pk}),
                "icon": "fa-arrow-left",
                "text": "العودة للفاتورة",
                "class": "btn-outline-secondary",
            },
        ],
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
                "title": payment.purchase.supplier.name,
                "url": reverse("supplier:supplier_detail", args=[payment.purchase.supplier.pk]),
                "icon": "fas fa-truck",
            },
            {
                "title": f"فاتورة {payment.purchase.number}",
                "url": reverse("purchase:purchase_detail", kwargs={"pk": payment.purchase.pk}),
                "icon": "fas fa-file-invoice",
            },
            {
                "title": f"تعديل دفعة #{payment.id}",
                "active": True,
            },
        ],
    }

    return render(request, "purchase/payment_edit.html", context)


@login_required
def unpost_payment_only(request, payment_id):
    """
    إلغاء ترحيل الدفعة فقط (بدون تعديل)
    """
    payment = get_object_or_404(PurchasePayment, pk=payment_id)

    # استيراد خدمة التعديل
    try:
        from financial.services.payment_edit_service import PaymentEditService
    except ImportError:
        messages.error(request, "خدمة تعديل الدفعات غير متاحة")
        return redirect("purchase:purchase_detail", pk=payment.purchase.pk)

    # فحص الصلاحيات
    if not PaymentEditService.can_unpost_payment(request.user, payment):
        messages.error(request, "ليس لديك صلاحية إلغاء ترحيل الدفعات")
        return redirect("purchase:purchase_detail", pk=payment.purchase.pk)

    if request.method == "POST":
        reason = request.POST.get("reason", "")

        try:
            result = PaymentEditService.unpost_payment(
                payment=payment,
                payment_type="purchase",
                user=request.user,
                reason=reason,
            )

            if result["success"]:
                messages.success(request, result["message"])
            else:
                messages.error(request, result["message"])

        except Exception as e:
            logger.error(f"خطأ في إلغاء ترحيل الدفعة {payment_id}: {str(e)}")
            messages.error(request, f"حدث خطأ أثناء إلغاء الترحيل: {str(e)}")

    return redirect("purchase:purchase_detail", pk=payment.purchase.pk)


@login_required
def delete_payment(request, payment_id):
    """
    حذف دفعة مشتريات - يُسمح بالحذف فقط للدفعات غير المرحلة
    """
    payment = get_object_or_404(PurchasePayment, pk=payment_id)
    purchase = payment.purchase
    
    # التحقق من إمكانية الحذف
    if not payment.can_delete:
        messages.error(request, "لا يمكن حذف الدفعة المرحلة. يجب إلغاء الترحيل أولاً.")
        return redirect("purchase:purchase_detail", pk=purchase.pk)
    
    if request.method == "POST":
        try:
            # تسجيل العملية في سجل التدقيق قبل الحذف
            if hasattr(payment, 'log_payment_action'):
                payment.log_payment_action(
                    action="delete",
                    user=request.user,
                    description=f"حذف دفعة مشتريات - المبلغ: {payment.amount} - التاريخ: {payment.payment_date}",
                    reason=request.POST.get("reason", "حذف الدفعة"),
                    old_values={
                        "amount": float(payment.amount),
                        "payment_date": payment.payment_date.isoformat(),
                        "payment_method": payment.payment_method,
                        "reference_number": payment.reference_number,
                        "notes": payment.notes,
                        "status": payment.status,
                    }
                )
            
            # حذف الدفعة
            payment.delete()
            
            messages.success(request, "تم حذف الدفعة بنجاح")
            
        except Exception as e:
            logger.error(f"خطأ في حذف الدفعة {payment_id}: {str(e)}")
            messages.error(request, f"حدث خطأ أثناء حذف الدفعة: {str(e)}")
    
    return redirect("purchase:purchase_detail", pk=purchase.pk)
