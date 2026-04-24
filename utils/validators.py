from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
import re
import os


def validate_phone_number(value):
    """
    التحقق من صحة رقم الهاتف
    يقبل الأرقام المصرية بصيغ مختلفة
    """
    if not value:
        raise ValidationError(_("رقم الهاتف مطلوب"))

    # التأكد من أن رقم الهاتف يحتوي على أرقام فقط مع السماح بعلامة + في البداية
    pattern = r"^(\+|00)?[0-9]+$"
    if not re.match(pattern, value):
        raise ValidationError(_("رقم هاتف غير صالح. يجب أن يحتوي على أرقام فقط"))

    # التحقق من الطول المناسب لرقم الهاتف المصري
    clean_number = value
    
    # إزالة رمز الدولة إذا وجد
    if clean_number.startswith(("+20", "0020")):
        clean_number = re.sub(r"^(\+20|0020)", "", clean_number)
    
    # إزالة الصفر البادئ إذا وجد
    if clean_number.startswith("0"):
        clean_number = clean_number[1:]

    # التحقق من الطول النهائي (يجب أن يكون 10 أرقام بالضبط بعد التنظيف)
    if len(clean_number) != 10:
        raise ValidationError(_("رقم هاتف غير صالح"))
    
    # التحقق من أن الرقم يبدأ بكود صحيح للشبكات المصرية
    if not clean_number.startswith(("10", "11", "12", "15")):
        raise ValidationError(_("رقم هاتف غير صالح"))


def validate_national_id(value, birth_date=None, gender=None, raise_exception=True):
    """
    التحقق الشامل من صحة الرقم القومي المصري
    
    بنية الرقم القومي المصري (14 رقم):
    - الرقم 1: القرن (2 للقرن 20، 3 للقرن 21)
    - الأرقام 2-3: السنة (00-99)
    - الأرقام 4-5: الشهر (01-12)
    - الأرقام 6-7: اليوم (01-31)
    - الأرقام 8-9: كود المحافظة (01-35 أو 85-89 للأكواد الإدارية/الاستثنائية)
    - الأرقام 10-13: الرقم التسلسلي (فردي للذكور، زوجي للإناث)
    - الرقم 14: رقم التحقق
    
    ملاحظة: الأكواد 85-89 تُستخدم للحالات الإدارية/الاستثنائية مثل:
    - استخراج البطاقة من السجل المدني المركزي
    - تعديل بيانات جوهرية وإصدار رقم جديد
    - بدل فاقد/تالف، تسجيل متأخر
    - تسجيل لمصريين مولودين/مقيدين عبر جهات خارجية
    
    Args:
        value: الرقم القومي
        birth_date: تاريخ الميلاد للتحقق من التطابق (اختياري)
        gender: الجنس للتحقق من التطابق (اختياري) - 'male' أو 'female'
        raise_exception: رفع استثناء عند الخطأ أو إرجاع dict مع التفاصيل
    
    Returns:
        dict: معلومات مستخرجة من الرقم القومي إذا كان raise_exception=False
        None: إذا كان raise_exception=True والرقم صحيح
    
    Raises:
        ValidationError: إذا كان الرقم غير صحيح وكان raise_exception=True
    """
    from datetime import date
    
    # 1. التحقق الأساسي
    if not value:
        if raise_exception:
            raise ValidationError(_("الرقم القومي مطلوب"))
        return {'valid': False, 'error': 'الرقم القومي مطلوب'}
    
    # إزالة المسافات
    value = str(value).strip().replace(' ', '')
    
    if not value.isdigit():
        if raise_exception:
            raise ValidationError(_("الرقم القومي يجب أن يحتوي على أرقام فقط"))
        return {'valid': False, 'error': 'الرقم القومي يجب أن يحتوي على أرقام فقط'}
    
    if len(value) != 14:
        if raise_exception:
            raise ValidationError(_("الرقم القومي يجب أن يكون 14 رقم بالضبط"))
        return {'valid': False, 'error': 'الرقم القومي يجب أن يكون 14 رقم بالضبط'}
    
    # 2. التحقق من القرن
    century = int(value[0])
    if century not in [2, 3]:
        if raise_exception:
            raise ValidationError(_("الرقم القومي غير صحيح: القرن يجب أن يكون 2 أو 3"))
        return {'valid': False, 'error': 'الرقم القومي غير صحيح: القرن يجب أن يكون 2 أو 3'}
    
    # 3. استخراج التاريخ والتحقق منه
    year = int(value[1:3])
    month = int(value[3:5])
    day = int(value[5:7])
    
    # التحقق من الشهر
    if month < 1 or month > 12:
        if raise_exception:
            raise ValidationError(_("الرقم القومي غير صحيح: الشهر ({}) غير صحيح").format(month))
        return {'valid': False, 'error': f'الرقم القومي غير صحيح: الشهر ({month}) غير صحيح'}
    
    # التحقق من اليوم
    if day < 1 or day > 31:
        if raise_exception:
            raise ValidationError(_("الرقم القومي غير صحيح: اليوم ({}) غير صحيح").format(day))
        return {'valid': False, 'error': f'الرقم القومي غير صحيح: اليوم ({day}) غير صحيح'}
    
    # التحقق من صحة التاريخ
    full_year = (1900 if century == 2 else 2000) + year
    try:
        birth_date_from_id = date(full_year, month, day)
    except ValueError:
        if raise_exception:
            raise ValidationError(_("الرقم القومي غير صحيح: التاريخ ({}/{}/{}) غير صحيح").format(day, month, full_year))
        return {'valid': False, 'error': f'الرقم القومي غير صحيح: التاريخ ({day}/{month}/{full_year}) غير صحيح'}
    
    # 4. التحقق من كود المحافظة (01-35 أو الأكواد الإدارية/الاستثنائية 85-89)
    governorate_code = int(value[7:9])
    valid_codes = (
        (governorate_code >= 1 and governorate_code <= 35) or  # المحافظات التقليدية
        (governorate_code >= 85 and governorate_code <= 89)    # الأكواد الإدارية/الاستثنائية
    )
    
    if not valid_codes:
        if raise_exception:
            raise ValidationError(_("الرقم القومي غير صحيح: كود المحافظة ({}) غير صحيح").format(governorate_code))
        return {'valid': False, 'error': f'الرقم القومي غير صحيح: كود المحافظة ({governorate_code}) غير صحيح'}
    
    # 5. استخراج الجنس من الرقم التسلسلي
    serial = int(value[9:13])
    gender_from_id = 'male' if serial % 2 == 1 else 'female'
    
    # 6. التحقق من التطابق مع البيانات المدخلة
    if birth_date:
        if birth_date != birth_date_from_id:
            if raise_exception:
                raise ValidationError(
                    _("تاريخ الميلاد ({}) لا يتطابق مع الرقم القومي ({})").format(
                        birth_date, birth_date_from_id
                    )
                )
            return {
                'valid': False, 
                'error': f'تاريخ الميلاد ({birth_date}) لا يتطابق مع الرقم القومي ({birth_date_from_id})'
            }
    
    if gender:
        if gender != gender_from_id:
            gender_ar = 'ذكر' if gender == 'male' else 'أنثى'
            gender_id_ar = 'ذكر' if gender_from_id == 'male' else 'أنثى'
            if raise_exception:
                raise ValidationError(
                    _("الجنس ({}) لا يتطابق مع الرقم القومي ({})").format(
                        gender_ar, gender_id_ar
                    )
                )
            return {
                'valid': False,
                'error': f'الجنس ({gender_ar}) لا يتطابق مع الرقم القومي ({gender_id_ar})'
            }
    
    # 7. إرجاع المعلومات المستخرجة
    result = {
        'valid': True,
        'birth_date': birth_date_from_id,
        'gender': gender_from_id,
        'governorate_code': governorate_code,
        'century': century,
        'serial': serial,
        'age': (date.today() - birth_date_from_id).days // 365
    }
    
    if not raise_exception:
        return result
    
    # إذا كان raise_exception=True ولم يحدث خطأ، لا نرجع شيء (للتوافق مع Django validators)
    return None


def extract_info_from_national_id(national_id):
    """
    استخراج المعلومات من الرقم القومي المصري بدون رفع استثناءات
    
    Args:
        national_id: الرقم القومي
    
    Returns:
        dict: معلومات مستخرجة أو None إذا كان الرقم غير صحيح
    """
    result = validate_national_id(national_id, raise_exception=False)
    
    if not result or not result.get('valid'):
        return None
    
    # خريطة المحافظات (تشمل المحافظات التقليدية والأكواد الإدارية/الاستثنائية)
    governorates = {
        1: 'القاهرة', 2: 'الإسكندرية', 3: 'بورسعيد', 4: 'السويس',
        11: 'دمياط', 12: 'الدقهلية', 13: 'الشرقية', 14: 'القليوبية',
        15: 'كفر الشيخ', 16: 'الغربية', 17: 'المنوفية', 18: 'البحيرة',
        19: 'الإسماعيلية', 21: 'الجيزة', 22: 'بني سويف', 23: 'الفيوم',
        24: 'المنيا', 25: 'أسيوط', 26: 'سوهاج', 27: 'قنا',
        28: 'أسوان', 29: 'الأقصر', 31: 'البحر الأحمر', 32: 'الوادي الجديد',
        33: 'مطروح', 34: 'شمال سيناء', 35: 'جنوب سيناء',
        # الأكواد الإدارية/الاستثنائية
        85: 'إداري/استثنائي', 86: 'إداري/استثنائي', 87: 'إداري/استثنائي',
        88: 'إداري/استثنائي', 89: 'إداري/استثنائي'
    }
    
    result['governorate_name'] = governorates.get(result['governorate_code'], 'غير معروف')
    result['gender_ar'] = 'ذكر' if result['gender'] == 'male' else 'أنثى'
    
    return result


def validate_positive_number(value):
    """
    التحقق من أن القيمة هي رقم موجب
    """
    try:
        # التحويل إلى رقم إذا كان نصًا
        if isinstance(value, str):
            value = float(value)

        if value <= 0:
            raise ValidationError(_("يجب أن تكون القيمة رقم موجب"))
    except (ValueError, TypeError):
        raise ValidationError(_("الرجاء إدخال رقم صالح"))


def validate_file_extension(value):
    """
    التحقق من امتداد الملف
    """
    ext = os.path.splitext(value)[1]  # الحصول على امتداد الملف
    valid_extensions = [
        ".pdf",
        ".doc",
        ".docx",
        ".xlsx",
        ".xls",
        ".txt",
        ".csv",
        ".zip",
        ".rar",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".pptx",
        ".ppt",
    ]

    if not ext.lower() in valid_extensions:
        raise ValidationError(
            _(
                "امتداد الملف غير مسموح به. الامتدادات المسموحة هي: {0}".format(
                    ", ".join(valid_extensions)
                )
            )
        )


def validate_image_extension(value):
    """
    التحقق من امتداد الصورة
    """
    ext = os.path.splitext(value)[1]  # الحصول على امتداد الملف
    valid_extensions = [".png", ".jpg", ".jpeg", ".gif", ".svg"]

    if not ext.lower() in valid_extensions:
        raise ValidationError(
            _(
                "امتداد الصورة غير مسموح به. الامتدادات المسموحة هي: {0}".format(
                    ", ".join(valid_extensions)
                )
            )
        )


def validate_arabic_text(value):
    """
    التحقق من أن النص عربي - استخدام الـ validator الآمن
    """
    from core.secure_validators import validate_arabic_text_secure

    validate_arabic_text_secure(value)


def validate_english_text(value):
    """
    التحقق من أن النص إنجليزي - استخدام الـ validator الآمن
    """
    from core.secure_validators import validate_english_text_secure

    validate_english_text_secure(value)


def validate_alphanumeric(value):
    """
    التحقق من أن النص يحتوي على أحرف وأرقام فقط
    """
    pattern = re.compile(r"^[a-zA-Z0-9_]*$")

    if not pattern.match(value):
        raise ValidationError(
            _("الرجاء إدخال أحرف وأرقام فقط (بدون مسافات أو رموز خاصة)")
        )


def validate_percentage(value):
    """
    التحقق من أن القيمة هي نسبة مئوية صالحة (0-100)
    """
    try:
        # التحويل إلى رقم إذا كان نصًا
        if isinstance(value, str):
            value = float(value)

        if value < 0 or value > 100:
            raise ValidationError(_("الرجاء إدخال نسبة مئوية صالحة (0-100)"))
    except (ValueError, TypeError):
        raise ValidationError(_("الرجاء إدخال رقم صالح"))
