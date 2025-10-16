from django import template
from decimal import Decimal

register = template.Library()


@register.filter
def remove_trailing_zeros(value):
    """
    إزالة الأصفار الزائدة من الأرقام العشرية
    مثال: 7.00 -> 7, 7.50 -> 7.5, 7.25 -> 7.25
    """
    if value is None:
        return ""

    try:
        # التعامل مع Decimal بشكل مباشر
        if isinstance(value, Decimal):
            # استخدام normalize لإزالة الأصفار الزائدة
            normalized = value.normalize()
            # تحويل إلى string وإزالة الأصفار إذا لزم الأمر
            result = str(normalized)
            # التأكد من عدم وجود تدوين علمي
            if "E" in result.upper():
                # تحويل إلى float ثم إلى string
                result = f"{float(normalized):g}"
            return result
        
        # التعامل مع float
        elif isinstance(value, float):
            return f"{value:g}"
        
        # التعامل مع int
        elif isinstance(value, int):
            return str(value)
        
        # التعامل مع string
        else:
            try:
                decimal_value = Decimal(str(value))
                normalized = decimal_value.normalize()
                result = str(normalized)
                if "E" in result.upper():
                    result = f"{float(normalized):g}"
                return result
            except:
                return str(value)
    
    except Exception:
        return str(value) if value is not None else ""


@register.filter
def format_phone(value):
    """تنسيق رقم الهاتف"""
    if not value:
        return "لا يوجد"
    
    # إزالة المسافات والرموز الإضافية
    phone = str(value).strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    
    # إذا كان الرقم يبدأ بـ +20، قم بإزالته
    if phone.startswith("+20"):
        phone = phone[3:]
    elif phone.startswith("20"):
        phone = phone[2:]
    
    # إذا كان الرقم يبدأ بـ 0، قم بإزالته
    if phone.startswith("0"):
        phone = phone[1:]
    
    # تنسيق الرقم
    if len(phone) == 10:
        return f"{phone[:3]} {phone[3:6]} {phone[6:]}"
    elif len(phone) == 11:
        return f"{phone[:4]} {phone[4:7]} {phone[7:]}"
    else:
        return value


@register.simple_tag
def get_coating_type_name(coating_type_id):
    """جلب اسم نوع التغطية من ID"""
    try:
        from pricing.models import CoatingType
        coating_type = CoatingType.objects.get(id=coating_type_id)
        return coating_type.name
    except (CoatingType.DoesNotExist, ValueError, TypeError):
        return None


@register.filter
def format_dimension(value):
    """
    تنسيق الأبعاد بإزالة الأصفار الزائدة
    """
    return remove_trailing_zeros(value)
