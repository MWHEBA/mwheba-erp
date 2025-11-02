"""
دوال مساعدة لإرسال الإيميلات في نظام MWHEBA ERP
"""
from django.core.mail import EmailMessage, EmailMultiAlternatives, get_connection
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags
import logging

logger = logging.getLogger(__name__)


def get_email_settings_from_db():
    """
    قراءة إعدادات الإيميل من قاعدة البيانات
    
    Returns:
        dict: إعدادات الإيميل أو None
    """
    try:
        from core.models import SystemSetting
        
        email_settings = {}
        settings_keys = [
            'email_host',
            'email_port',
            'email_username',
            'email_password',
            'email_encryption',
            'email_from'
        ]
        
        for key in settings_keys:
            setting = SystemSetting.objects.filter(key=key, is_active=True).first()
            if setting:
                # تحويل القيم حسب النوع
                if key == 'email_port':
                    email_settings[key] = int(setting.value) if setting.value else 587
                else:
                    email_settings[key] = setting.value
        
        # التحقق من وجود الإعدادات الأساسية
        if email_settings.get('email_host'):
            return email_settings
        
        return None
    except Exception as e:
        logger.warning(f"فشل قراءة إعدادات الإيميل من قاعدة البيانات: {e}")
        return None


def get_email_connection():
    """
    إنشاء اتصال إيميل باستخدام الإعدادات من قاعدة البيانات أو settings.py
    
    Returns:
        EmailBackend connection
    """
    # محاولة قراءة من قاعدة البيانات أولاً
    db_settings = get_email_settings_from_db()
    
    if db_settings:
        encryption = db_settings.get('email_encryption', 'tls')
        use_tls = encryption == 'tls'
        use_ssl = encryption == 'ssl'
        
        logger.info(f"استخدام إعدادات الإيميل من قاعدة البيانات: {db_settings.get('email_host')}:{db_settings.get('email_port')} ({encryption.upper()})")
        
        connection = get_connection(
            backend=settings.EMAIL_BACKEND,
            host=db_settings.get('email_host'),
            port=db_settings.get('email_port', 587),
            username=db_settings.get('email_username'),
            password=db_settings.get('email_password'),
            use_tls=use_tls,
            use_ssl=use_ssl,
            fail_silently=False,
        )
        
        # اختبار الاتصال
        try:
            connection.open()
            logger.info("✅ تم الاتصال بخادم SMTP بنجاح")
            connection.close()
        except Exception as e:
            logger.error(f"❌ فشل الاتصال بخادم SMTP: {str(e)}")
            raise
        
        return connection
    
    # استخدام الإعدادات من settings.py
    logger.info("استخدام إعدادات الإيميل من settings.py")
    return get_connection()


def send_email(
    subject,
    message,
    recipient_list,
    from_email=None,
    html_message=None,
    attachments=None,
    fail_silently=False,
):
    """
    إرسال إيميل بسيط أو HTML
    
    Args:
        subject: عنوان الإيميل
        message: محتوى الإيميل النصي
        recipient_list: قائمة المستقبلين
        from_email: إيميل المرسل (اختياري)
        html_message: محتوى HTML (اختياري)
        attachments: قائمة المرفقات (اختياري)
        fail_silently: إخفاء الأخطاء (افتراضي: False)
    
    Returns:
        bool: True إذا تم الإرسال بنجاح
    """
    try:
        # محاولة قراءة إعدادات الإيميل من قاعدة البيانات
        db_settings = get_email_settings_from_db()
        
        # تحديد from_email
        if db_settings and db_settings.get('email_from'):
            from_email = from_email or db_settings.get('email_from')
        else:
            from_email = from_email or settings.DEFAULT_FROM_EMAIL
        
        # التحقق من الإعدادات الأساسية
        if not from_email:
            error_msg = "DEFAULT_FROM_EMAIL غير محدد في إعدادات الإيميل"
            logger.error(error_msg)
            if not fail_silently:
                raise ValueError(error_msg)
            return False
        
        # إنشاء اتصال الإيميل
        connection = get_email_connection()
        
        if html_message:
            # إرسال إيميل HTML
            email = EmailMultiAlternatives(
                subject=subject,
                body=message,
                from_email=from_email,
                to=recipient_list,
                connection=connection,
            )
            email.attach_alternative(html_message, "text/html")
        else:
            # إرسال إيميل نصي
            email = EmailMessage(
                subject=subject,
                body=message,
                from_email=from_email,
                to=recipient_list,
                connection=connection,
            )
        
        # إضافة المرفقات إن وجدت
        if attachments:
            for attachment in attachments:
                if isinstance(attachment, dict):
                    email.attach(
                        attachment.get('filename'),
                        attachment.get('content'),
                        attachment.get('mimetype')
                    )
                else:
                    email.attach_file(attachment)
        
        # محاولة الإرسال والحصول على عدد الرسائل المرسلة
        sent_count = email.send(fail_silently=fail_silently)
        
        if sent_count > 0:
            logger.info(f"تم إرسال إيميل بنجاح إلى: {', '.join(recipient_list)}")
            return True
        else:
            logger.warning(f"فشل إرسال الإيميل إلى: {', '.join(recipient_list)}")
            return False
        
    except Exception as e:
        logger.error(f"خطأ في إرسال الإيميل: {str(e)}")
        if not fail_silently:
            raise
        return False


def send_template_email(
    subject,
    template_name,
    context,
    recipient_list,
    from_email=None,
    attachments=None,
    fail_silently=False,
):
    """
    إرسال إيميل باستخدام قالب HTML
    
    Args:
        subject: عنوان الإيميل
        template_name: اسم القالب (مثل: 'emails/invoice.html')
        context: البيانات المطلوبة للقالب
        recipient_list: قائمة المستقبلين
        from_email: إيميل المرسل (اختياري)
        attachments: قائمة المرفقات (اختياري)
        fail_silently: إخفاء الأخطاء (افتراضي: False)
    
    Returns:
        bool: True إذا تم الإرسال بنجاح
    """
    try:
        # تحميل القالب HTML
        html_message = render_to_string(template_name, context)
        # إنشاء نسخة نصية من HTML
        plain_message = strip_tags(html_message)
        
        return send_email(
            subject=subject,
            message=plain_message,
            recipient_list=recipient_list,
            from_email=from_email,
            html_message=html_message,
            attachments=attachments,
            fail_silently=fail_silently,
        )
        
    except Exception as e:
        logger.error(f"خطأ في إرسال إيميل القالب: {str(e)}")
        if not fail_silently:
            raise
        return False


def send_notification_email(user, subject, message, html_message=None):
    """
    إرسال إيميل إشعار لمستخدم معين
    
    Args:
        user: كائن المستخدم
        subject: عنوان الإيميل
        message: محتوى الإيميل
        html_message: محتوى HTML (اختياري)
    
    Returns:
        bool: True إذا تم الإرسال بنجاح
    """
    if not user.email:
        logger.warning(f"المستخدم {user.username} ليس لديه إيميل")
        return False
    
    return send_email(
        subject=subject,
        message=message,
        recipient_list=[user.email],
        html_message=html_message,
        fail_silently=True,
    )


def send_invoice_email(invoice, recipient_email=None):
    """
    إرسال فاتورة بالإيميل
    
    Args:
        invoice: كائن الفاتورة
        recipient_email: إيميل المستقبل (اختياري، يستخدم إيميل العميل افتراضياً)
    
    Returns:
        bool: True إذا تم الإرسال بنجاح
    """
    try:
        recipient = recipient_email or invoice.customer.email
        
        if not recipient:
            logger.warning(f"العميل {invoice.customer.name} ليس لديه إيميل")
            return False
        
        context = {
            'invoice': invoice,
            'customer': invoice.customer,
            'company': settings.COMPANY_NAME if hasattr(settings, 'COMPANY_NAME') else 'MWHEBA',
        }
        
        return send_template_email(
            subject=f'فاتورة رقم {invoice.invoice_number}',
            template_name='emails/invoice.html',
            context=context,
            recipient_list=[recipient],
            fail_silently=True,
        )
        
    except Exception as e:
        logger.error(f"خطأ في إرسال فاتورة بالإيميل: {str(e)}")
        return False


def send_payment_confirmation_email(payment):
    """
    إرسال تأكيد دفع بالإيميل
    
    Args:
        payment: كائن الدفع
    
    Returns:
        bool: True إذا تم الإرسال بنجاح
    """
    try:
        if not payment.customer.email:
            logger.warning(f"العميل {payment.customer.name} ليس لديه إيميل")
            return False
        
        context = {
            'payment': payment,
            'customer': payment.customer,
            'company': settings.COMPANY_NAME if hasattr(settings, 'COMPANY_NAME') else 'MWHEBA',
        }
        
        return send_template_email(
            subject=f'تأكيد دفع - مبلغ {payment.amount} جنيه',
            template_name='emails/payment_confirmation.html',
            context=context,
            recipient_list=[payment.customer.email],
            fail_silently=True,
        )
        
    except Exception as e:
        logger.error(f"خطأ في إرسال تأكيد دفع بالإيميل: {str(e)}")
        return False
