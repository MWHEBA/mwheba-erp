from django.utils.text import slugify
from django.utils import timezone
import random
import string
import re
import datetime
from decimal import Decimal

def arabic_slugify(text):
    """
    تحويل النص العربي إلى slug صالح للاستخدام في URLs
    
    المعلمات:
    text (str): النص المراد تحويله
    
    تُرجع: نص slug
    """
    # إذا كان النص خاليًا أو None، ارجع سلسلة فارغة
    if not text:
        return ''
    
    # استخدام وظيفة slugify الموجودة في Django للنص الإنجليزي
    slug = slugify(text)
    
    # إذا كان النص يحتوي على أحرف عربية،
    # slugify قد لا تتعامل معها بشكل جيد، لذا نقوم بمعالجتها يدويًا
    if not slug and any('\u0600' <= c <= '\u06FF' for c in text):
        # استبدال المسافات بشرطة
        slug = re.sub(r'\s+', '-', text.strip())
        # إزالة الأحرف الخاصة
        slug = re.sub(r'[^\w\s-]', '', slug)
        # تحويل الأحرف الكبيرة إلى صغيرة
        slug = slug.lower()
    
    return slug

def generate_random_code(length=8, digits_only=False, prefix=''):
    """
    توليد كود عشوائي
    
    المعلمات:
    length (int): طول الكود
    digits_only (bool): إذا كان True، فسيتكون الكود من أرقام فقط
    prefix (str): بادئة للكود
    
    تُرجع: الكود العشوائي
    """
    if digits_only:
        chars = string.digits
    else:
        chars = string.ascii_uppercase + string.digits
    
    # توليد الكود العشوائي
    code = ''.join(random.choice(chars) for _ in range(length))
    
    # إضافة البادئة إذا كانت موجودة
    if prefix:
        code = f"{prefix}{code}"
    
    return code

def format_currency(value, currency='', decimal_places=2):
    """
    تنسيق قيمة عملة
    
    المعلمات:
    value (float, int, Decimal): القيمة
    currency (str): رمز العملة
    decimal_places (int): عدد المنازل العشرية
    
    تُرجع: نص منسق للقيمة
    """
    if not isinstance(value, (int, float, Decimal)):
        try:
            value = float(value)
        except (ValueError, TypeError):
            return "0.00"
    
    # تنسيق القيمة بعدد المنازل العشرية المحدد
    if decimal_places > 0:
        formatter = "{:,.%df}" % decimal_places
        formatted = formatter.format(value)
    else:
        formatted = "{:,}".format(int(value))
    
    # إضافة رمز العملة إذا كان موجودًا
    if currency:
        if currency == '$' or currency == '€' or currency == '£':
            formatted = f"{currency}{formatted}"
        else:
            formatted = f"{formatted} {currency}"
    
    return formatted

def calculate_vat(amount, rate=15):
    """
    حساب ضريبة القيمة المضافة
    
    المعلمات:
    amount (float, int, Decimal): المبلغ
    rate (float): نسبة الضريبة (٪)
    
    تُرجع: قيمة الضريبة
    """
    if not isinstance(amount, (int, float, Decimal)):
        try:
            amount = float(amount)
        except (ValueError, TypeError):
            return 0
    
    return amount * (rate / 100)

def arabic_date_format(date, with_time=False, use_hijri=False):
    """
    تنسيق التاريخ بالعربية
    
    المعلمات:
    date (date, datetime): التاريخ
    with_time (bool): تضمين الوقت في التنسيق
    use_hijri (bool): استخدام التاريخ الهجري
    
    تُرجع: نص منسق للتاريخ
    """
    if not date:
        return ''
    
    # التحقق من نوع الكائن
    if isinstance(date, datetime.datetime):
        date_obj = date
    elif isinstance(date, datetime.date):
        date_obj = datetime.datetime.combine(date, datetime.time())
    else:
        return str(date)
    
    # أسماء الأشهر بالعربية
    arabic_months = [
        'يناير', 'فبراير', 'مارس', 'إبريل', 'مايو', 'يونيو',
        'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر'
    ]
    
    # تنسيق التاريخ بالعربية
    day = date_obj.day
    month = arabic_months[date_obj.month - 1]
    year = date_obj.year
    
    # إذا كان التاريخ الهجري مطلوبًا
    if use_hijri:
        # يمكن استخدام مكتبة خارجية لتحويل التاريخ إلى هجري
        # مثل hijri-converter، لكن هنا سنكتفي بإرجاع التاريخ الميلادي
        formatted_date = f"{day} {month} {year} م"
    else:
        formatted_date = f"{day} {month} {year}"
    
    # إضافة الوقت إذا كان مطلوبًا
    if with_time:
        time_str = date_obj.strftime("%H:%M")
        formatted_date = f"{formatted_date} {time_str}"
    
    return formatted_date

def get_current_fiscal_year():
    """
    الحصول على السنة المالية الحالية
    
    تُرجع: (تاريخ البداية، تاريخ النهاية)
    """
    today = timezone.now().date()
    fiscal_year_start_month = 1  # يناير
    
    # تحديد بداية السنة المالية
    if today.month < fiscal_year_start_month:
        start_year = today.year - 1
    else:
        start_year = today.year
    
    start_date = datetime.date(start_year, fiscal_year_start_month, 1)
    end_date = datetime.date(start_year + 1, fiscal_year_start_month, 1) - datetime.timedelta(days=1)
    
    return start_date, end_date

def arabic_text_to_html(text):
    """
    تحويل النص العربي إلى HTML مع مراعاة اتجاه النص
    
    المعلمات:
    text (str): النص العربي
    
    تُرجع: نص HTML
    """
    if not text:
        return ''
    
    # إضافة اتجاه النص من اليمين إلى اليسار
    html = f'<div dir="rtl">{text}</div>'
    
    # استبدال السطور الجديدة بـ <br>
    html = html.replace('\n', '<br>')
    
    return html

def validate_egyptian_phone(phone):
    """
    التحقق من صحة رقم الهاتف المصري
    
    المعلمات:
    phone (str): رقم الهاتف
    
    تُرجع: True إذا كان الرقم صحيحًا، False خلاف ذلك
    """
    if not phone:
        return False
    
    # إزالة الأحرف غير الرقمية
    phone = re.sub(r'\D', '', phone)
    
    # التحقق من طول الرقم وبدايته
    # أرقام المحمول المصرية تبدأ بـ 01 وتكون 11 رقمًا
    if len(phone) == 11 and phone.startswith('01'):
        return True
    
    return False

def is_arabic_text(text):
    """
    التحقق مما إذا كان النص يحتوي على أحرف عربية
    
    المعلمات:
    text (str): النص المراد فحصه
    
    تُرجع: True إذا كان النص يحتوي على أحرف عربية، False خلاف ذلك
    """
    if not text:
        return False
    
    # نطاق الأحرف العربية في Unicode
    arabic_pattern = re.compile(r'[\u0600-\u06FF]')
    
    return bool(arabic_pattern.search(text))

def calculate_age(birth_date):
    """
    حساب العمر بناءً على تاريخ الميلاد
    
    المعلمات:
    birth_date (date): تاريخ الميلاد
    
    تُرجع: العمر بالسنوات
    """
    if not birth_date:
        return 0
    
    today = timezone.now().date()
    
    # حساب العمر
    age = today.year - birth_date.year
    
    # تعديل العمر إذا لم يحن موعد عيد الميلاد بعد
    if (today.month, today.day) < (birth_date.month, birth_date.day):
        age -= 1
    
    return age 