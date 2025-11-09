"""
صلاحيات مخصصة للنظام المالي
"""
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from financial.models.journal_entry import JournalEntry


def create_custom_permissions():
    """
    إنشاء صلاحيات مخصصة للنظام المالي
    """
    # صلاحيات القيود المحاسبية
    journal_entry_ct = ContentType.objects.get_for_model(JournalEntry)

    # صلاحية حذف القيود المرحلة (للمدير فقط)
    Permission.objects.get_or_create(
        codename="force_delete_posted_entry",
        name="يمكن حذف القيود المرحلة",
        content_type=journal_entry_ct,
    )

    # صلاحيات تعديل الدفعات
    Permission.objects.get_or_create(
        codename="can_edit_posted_payments",
        name="يمكن تعديل الدفعات المرحّلة",
        content_type=journal_entry_ct,
    )

    Permission.objects.get_or_create(
        codename="can_unpost_payments",
        name="يمكن إلغاء ترحيل الدفعات",
        content_type=journal_entry_ct,
    )


def check_user_can_delete_entry(user, entry):
    """
    التحقق من صلاحية المستخدم لحذف قيد محاسبي
    """
    # المسودات يمكن لأي شخص لديه صلاحية الحذف العادية حذفها
    if entry.status == "draft":
        return user.has_perm("financial.delete_journalentry")

    # القيود المرحلة تحتاج صلاحية خاصة
    if entry.status == "posted":
        return user.has_perm("financial.force_delete_posted_entry")

    # القيود الملغاة لا يمكن حذفها
    return False
