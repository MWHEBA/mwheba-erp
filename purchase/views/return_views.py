"""
Purchase Return Views
عرض وإدارة مرتجعات المشتريات
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from django.urls import reverse
from decimal import Decimal
import logging

from purchase.models import Purchase, PurchaseItem, PurchaseReturn, PurchaseReturnItem
from purchase.forms import PurchaseReturnForm

logger = logging.getLogger(__name__)


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

                            # إنشاء حركة مخزون صادر (مرتجع مشتريات) عبر MovementService
                            from governance.services.movement_service import MovementService
                            movement_service = MovementService()
                            
                            movement_service.process_movement(
                                product_id=purchase_item.product.id,
                                quantity_change=return_quantity,
                                movement_type='out',
                                source_reference=f"PURCHASE_RETURN:{purchase_return.number}",
                                idempotency_key=f"SM:purchase_return:{purchase_return.id}:item:{return_item.id}",
                                user=request.user,
                                warehouse_id=purchase_return.warehouse.id,
                                document_number=purchase_return.number,
                                notes=f"مرتجع مشتريات - {return_reason}"
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
        "header_buttons": ([] if purchase_return.status != 'draft' else [
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
        ]),
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
