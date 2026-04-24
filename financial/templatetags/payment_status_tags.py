"""
Template tags لعرض حالة الربط المالي للدفعات
"""
from django import template
from django.utils.safestring import mark_safe
from django.utils.html import format_html

register = template.Library()


@register.simple_tag
def payment_financial_status_badge(payment):
    """
    عرض badge لحالة الربط المالي للدفعة
    """
    if not payment:
        return ""

    status = payment.financial_status
    status_classes = {
        "pending": "badge-warning",
        "synced": "badge-success",
        "failed": "badge-danger",
        "manual": "badge-info",
    }

    status_texts = {
        "pending": "معلق",
        "synced": "مربوط",
        "failed": "فشل",
        "manual": "يدوي",
    }

    status_icons = {
        "pending": "fas fa-clock",
        "synced": "fas fa-check-circle",
        "failed": "fas fa-exclamation-triangle",
        "manual": "fas fa-hand-paper",
    }

    css_class = status_classes.get(status, "badge-secondary")
    text = status_texts.get(status, status)
    icon = status_icons.get(status, "fas fa-question")

    return format_html(
        '<span class="badge {} d-inline-flex align-items-center">'
        '<i class="{} me-1"></i>{}</span>',
        css_class,
        icon,
        text,
    )


@register.simple_tag
def payment_posting_status_badge(payment):
    """
    عرض badge لحالة الترحيل للدفعة
    """
    if not payment:
        return ""

    status = payment.status
    status_classes = {"draft": "badge-secondary", "posted": "badge-primary"}

    status_texts = {"draft": "مسودة", "posted": "مرحّلة"}

    status_icons = {"draft": "fas fa-edit", "posted": "fas fa-check"}

    css_class = status_classes.get(status, "badge-secondary")
    text = status_texts.get(status, status)
    icon = status_icons.get(status, "fas fa-question")

    return format_html(
        '<span class="badge {} d-inline-flex align-items-center">'
        '<i class="{} me-1"></i>{}</span>',
        css_class,
        icon,
        text,
    )


@register.simple_tag
def payment_status_summary(payment):
    """
    عرض ملخص شامل لحالة الدفعة
    """
    if not payment:
        return ""

    # حالة الترحيل
    posting_badge = payment_posting_status_badge(payment)

    # حالة الربط المالي
    financial_badge = payment_financial_status_badge(payment)

    # معلومات إضافية
    extra_info = []

    if payment.financial_transaction:
        extra_info.append(f"القيد: {payment.financial_transaction.number}")

    if payment.financial_error:
        extra_info.append(f"خطأ: {payment.financial_error[:50]}...")

    extra_text = " | ".join(extra_info) if extra_info else ""

    return format_html(
        '<div class="payment-status-summary">' "{} {} {}" "</div>",
        posting_badge,
        financial_badge,
        f'<small class="text-muted d-block mt-1">{extra_text}</small>'
        if extra_text
        else "",
    )


@register.simple_tag
def payment_actions_buttons(payment, user):
    """
    عرض أزرار العمليات المتاحة للدفعة
    """
    if not payment or not user:
        return ""

    buttons = []

    # زر التعديل
    if payment.can_edit:
        buttons.append(
            '<button class="btn btn-sm btn-outline-primary me-1" '
            'onclick="editPayment({})" title="تعديل الدفعة">'
            '<i class="fas fa-edit"></i></button>'.format(payment.id)
        )

    # زر إلغاء الترحيل
    if payment.can_unpost and user.has_perm("financial.can_unpost_payments"):
        buttons.append(
            '<button class="btn btn-sm btn-outline-warning me-1" '
            'onclick="unpostPayment({})" title="إلغاء الترحيل">'
            '<i class="fas fa-undo"></i></button>'.format(payment.id)
        )

    # زر عرض التاريخ
    buttons.append(
        '<button class="btn btn-sm btn-outline-info me-1" '
        'onclick="showPaymentHistory({})" title="تاريخ التغييرات">'
        '<i class="fas fa-history"></i></button>'.format(payment.id)
    )

    # زر الحذف
    if payment.can_delete:
        buttons.append(
            '<button class="btn btn-sm btn-outline-danger" '
            'onclick="deletePayment({})" title="حذف الدفعة">'
            '<i class="fas fa-trash"></i></button>'.format(payment.id)
        )

    return mark_safe("".join(buttons))


@register.simple_tag
def payment_financial_details(payment):
    """
    عرض تفاصيل الربط المالي للدفعة
    """
    if not payment:
        return ""

    details = []

    # الحساب المالي
    if payment.financial_account:
        details.append(f"الحساب: {payment.financial_account.name}")

    # القيد المحاسبي
    if payment.financial_transaction:
        details.append(f"القيد: {payment.financial_transaction.number}")
        if payment.financial_transaction.date:
            details.append(f"تاريخ القيد: {payment.financial_transaction.date}")

    # تاريخ الترحيل
    if payment.posted_at:
        details.append(f'رُحّل في: {payment.posted_at.strftime("%Y-%m-%d %H:%M")}')

    # المستخدم الذي رحّل
    if payment.posted_by:
        details.append(
            f"رحّله: {payment.posted_by.get_full_name() or payment.posted_by.username}"
        )

    if not details:
        return '<small class="text-muted">لا توجد تفاصيل مالية</small>'

    return format_html(
        '<div class="payment-financial-details">'
        '<small class="text-muted">{}</small>'
        "</div>",
        " | ".join(details),
    )


@register.inclusion_tag("financial/components/payment_status_card.html")
def payment_status_card(payment, user=None, show_actions=True):
    """
    عرض بطاقة شاملة لحالة الدفعة
    """
    return {
        "payment": payment,
        "user": user,
        "show_actions": show_actions,
        "can_edit": payment.can_edit if payment else False,
        "can_unpost": payment.can_unpost if payment else False,
        "can_delete": payment.can_delete if payment else False,
    }


@register.filter
def payment_status_color(status):
    """
    إرجاع لون CSS حسب حالة الدفعة
    """
    colors = {
        "draft": "secondary",
        "posted": "primary",
        "pending": "warning",
        "synced": "success",
        "failed": "danger",
        "manual": "info",
    }
    return colors.get(status, "secondary")


@register.filter
def payment_status_icon(status):
    """
    إرجاع أيقونة حسب حالة الدفعة
    """
    icons = {
        "draft": "fas fa-edit",
        "posted": "fas fa-check",
        "pending": "fas fa-clock",
        "synced": "fas fa-check-circle",
        "failed": "fas fa-exclamation-triangle",
        "manual": "fas fa-hand-paper",
    }
    return icons.get(status, "fas fa-question")
