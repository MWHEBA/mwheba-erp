"""
Purchase Payment Views
عرض وإدارة دفعات المشتريات
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from django.urls import reverse
from django.http import JsonResponse
from datetime import datetime
import logging

from purchase.models import Purchase, PurchasePayment
from purchase.forms import PurchasePaymentForm, PurchasePaymentEditForm

logger = logging.getLogger(__name__)


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
        "header_buttons": [],
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
    from financial.exceptions import FinancialValidationError
    from financial.services.validation_service import FinancialValidationService
    
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

                    # التحقق من المعاملة المالية قبل الحفظ
                    # نستخدم supplier (المورد) كالكيان المالي
                    try:
                        validation_result = FinancialValidationService.validate_transaction(
                            entity=purchase.supplier,
                            transaction_date=payment.payment_date,
                            entity_type='supplier',
                            transaction_type='purchase_payment',
                            transaction_amount=float(payment.amount),
                            user=request.user,
                            module='purchase',
                            view_name='add_payment',
                            request=request,
                            raise_exception=True,
                            log_failures=True
                        )
                    except FinancialValidationError as e:
                        messages.error(request, str(e))
                        # إعادة عرض النموذج مع الخطأ
                        raise

                    # حفظ الدفعة أولاً
                    payment.status = "draft"
                    payment.save()

                    # إنشاء قيد محاسبي للدفعة وترحيلها باستخدام PurchaseService
                    from purchase.services.purchase_service import PurchaseService

                    try:
                        journal_entry = PurchaseService._create_payment_journal_entry(
                            payment=payment,
                            user=request.user,
                        )

                        if journal_entry:
                            # ربط القيد بالدفعة وتحديث الحالة إلى مرحلة
                            payment.financial_transaction = journal_entry
                            payment.financial_status = "synced"
                            payment.status = "posted"
                            payment.posted_at = timezone.now()
                            payment.posted_by = request.user
                            payment.save(
                                update_fields=[
                                    "financial_transaction",
                                    "financial_status",
                                    "status",
                                    "posted_at",
                                    "posted_by",
                                ]
                            )
                            logger.info(
                                f"✅ تم إنشاء دفعة وقيد محاسبي للفاتورة: {purchase.number}"
                            )
                        else:
                            logger.warning(
                                f"⚠️ تم إنشاء الدفعة لكن فشل إنشاء القيد المحاسبي للفاتورة: {purchase.number}"
                            )
                    except Exception as e:
                        logger.error(f"❌ خطأ في إنشاء القيد المحاسبي: {str(e)}")
                        raise

                    # تحديث حالة فاتورة الشراء
                    purchase.refresh_from_db()
                    if purchase.amount_due <= 0:
                        purchase.payment_status = "paid"
                    elif purchase.amount_paid > 0:
                        purchase.payment_status = "partially_paid"
                    purchase.save()

                    messages.success(request, _("تم تسجيل الدفعة وترحيلها بنجاح"))
                    return redirect("purchase:purchase_detail", pk=purchase.pk)

            except FinancialValidationError as e:
                # معالجة أخطاء التحقق المالي
                logger.warning(f"فشل التحقق المالي لدفعة المشتريات: {str(e)}")
                messages.error(request, str(e))
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
        "invoice": purchase,
        "form": form,
        "is_purchase": True,
        "title": f"إضافة دفعة لفاتورة المشتريات {purchase.number}",
        "page_subtitle": "إضافة دفعة جديدة لفاتورة المشتريات",
        "header_buttons": [],
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
def post_payment(request, payment_id):
    """
    ترحيل دفعة مشتريات - إنشاء القيود المحاسبية
    """
    payment = get_object_or_404(PurchasePayment, pk=payment_id)

    # التحقق من أن الدفعة مسودة
    if payment.status != "draft":
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': 'لا يمكن ترحيل دفعة مرحّلة مسبقاً'}, status=400)
        messages.error(request, "لا يمكن ترحيل دفعة مرحّلة مسبقاً")
        return redirect("purchase:purchase_detail", pk=payment.purchase.pk)

    try:
        with transaction.atomic():
            # استخدام PurchaseService للترحيل (Single Source of Truth)
            from purchase.services.purchase_service import PurchaseService

            journal_entry = PurchaseService._create_payment_journal_entry(
                payment=payment,
                user=request.user
            )

            if journal_entry:
                # تحديث حالة الدفعة
                # ملاحظة: القيد تم ربطه بالدفعة في الـ service، نحتاج فقط تحديث الحالة
                payment.refresh_from_db()  # تحديث البيانات من قاعدة البيانات
                payment.status = "posted"
                payment.posted_at = timezone.now()
                payment.posted_by = request.user
                payment.save(update_fields=["status", "posted_at", "posted_by"])
                
                # تحديث حالة الدفع للفاتورة
                payment.purchase.update_payment_status()

                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': True,
                        'message': f'تم ترحيل الدفعة بنجاح - القيد: {journal_entry.number}'
                    })
                
                messages.success(
                    request,
                    f'تم ترحيل الدفعة بنجاح - القيد: {journal_entry.number}',
                )
            else:
                error_msg = 'فشل إنشاء القيد المحاسبي - تحقق من الحسابات المحاسبية'
                logger.error(f"Journal entry is None for payment {payment_id}")
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': error_msg}, status=500)
                messages.error(request, error_msg)

    except Exception as e:
        logger.error(f"خطأ في ترحيل الدفعة {payment_id}: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        
        error_msg = f"خطأ: {str(e)}"
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': error_msg}, status=500)
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
        "header_buttons": [],
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
