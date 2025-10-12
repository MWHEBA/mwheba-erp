# حزمة الأدوات المساعدة 
default_app_config = 'utils.apps.UtilsConfig'

def create_breadcrumb_item(title, url='', icon=None, active=False):
    """
    دالة مساعدة لإنشاء عنصر في شريط التنقل التسلسلي
    
    المعلمات:
    - title: عنوان العنصر (مطلوب)
    - url: رابط العنصر (اختياري، فارغ للعنصر النشط)
    - icon: أيقونة من Font Awesome (اختياري)
    - active: هل العنصر نشط (اختياري، افتراضي False)
    
    مثال الاستخدام:
    ```
    context['breadcrumb_items'] = [
        create_breadcrumb_item('الرئيسية', reverse('core:dashboard'), 'fas fa-home'),
        create_breadcrumb_item('المنتجات', reverse('product:list'), 'fas fa-boxes'),
        create_breadcrumb_item('إضافة منتج', active=True)
    ]
    ```
    """
    return {
        'title': title,
        'url': url,
        'icon': icon,
        'active': active
    } 