"""
🔒 CSP Configuration
إعدادات Content Security Policy المتقدمة
"""

from django.conf import settings

# إعدادات CSP الأساسية
CSP_CONFIG = {
    # المصادر الموثوقة للـ Scripts
    'SCRIPT_SRC': [
        "'self'",
        "'unsafe-inline'",  # مطلوب للـ inline scripts
        "'unsafe-eval'",    # مطلوب لبعض المكتبات
        "https://cdn.jsdelivr.net",
        "https://cdnjs.cloudflare.com",
        "https://code.jquery.com",
        "https://cdn.datatables.net",
        "https://static.cloudflareinsights.com",  # Cloudflare Analytics
    ],
    
    # المصادر الموثوقة للـ Styles
    'STYLE_SRC': [
        "'self'",
        "'unsafe-inline'",  # مطلوب للـ inline styles
        "https://cdn.jsdelivr.net",
        "https://cdnjs.cloudflare.com",
        "https://fonts.googleapis.com",
        "https://cdn.datatables.net",
    ],
    
    # المصادر الموثوقة للخطوط
    'FONT_SRC': [
        "'self'",
        "https://fonts.gstatic.com",
        "https://cdn.jsdelivr.net",
        "https://cdnjs.cloudflare.com",
        "data:",
    ],
    
    # المصادر الموثوقة للصور
    'IMG_SRC': [
        "'self'",
        "data:",
        "blob:",
        "https:",  # السماح بجميع الصور HTTPS
    ],
    
    # المصادر الموثوقة للاتصالات
    'CONNECT_SRC': [
        "'self'",
        "https://cdn.jsdelivr.net",
        "https://cdnjs.cloudflare.com",
        "https://cloudflareinsights.com",  # Cloudflare Analytics
    ],
    
    # المصادر الموثوقة للوسائط
    'MEDIA_SRC': [
        "'self'",
    ],
    
    # إعدادات أخرى
    'OBJECT_SRC': ["'none'"],
    'BASE_URI': ["'self'"],
    'FORM_ACTION': ["'self'"],
    'FRAME_ANCESTORS': ["'none'"],
    'FRAME_SRC': ["'none'"],
    'WORKER_SRC': ["'self'"],
    'MANIFEST_SRC': ["'self'"],
    'DEFAULT_SRC': ["'self'"],
}

# إعدادات خاصة بالبيئة
if settings.DEBUG:
    # في وضع التطوير، كن أكثر تساهلاً
    if "'unsafe-eval'" not in CSP_CONFIG['SCRIPT_SRC']:
        CSP_CONFIG['SCRIPT_SRC'].append("'unsafe-eval'")
    
    CSP_CONFIG['CONNECT_SRC'].extend([
        "localhost:*",
        "127.0.0.1:*",
        "ws://localhost:*",
        "ws://127.0.0.1:*",
    ])
else:
    # في الإنتاج، كن أكثر صرامة
    CSP_CONFIG['UPGRADE_INSECURE_REQUESTS'] = True


def build_csp_policy(nonce=None):
    """
    بناء CSP policy كاملة
    """
    directives = []
    
    for directive, sources in CSP_CONFIG.items():
        if directive == 'UPGRADE_INSECURE_REQUESTS':
            if sources:
                directives.append('upgrade-insecure-requests')
            continue
            
        # تحويل اسم التوجيه
        directive_name = directive.lower().replace('_', '-')
        
        # لا نضيف nonce مع unsafe-inline لأنه يعطل unsafe-inline
        # نستخدم إما nonce أو unsafe-inline، ليس كلاهما
        sources_copy = sources.copy()
        
        # بناء التوجيه
        directive_value = f"{directive_name} {' '.join(sources_copy)}"
        directives.append(directive_value)
    
    # إضافة تقرير الانتهاكات في الإنتاج
    if not settings.DEBUG:
        directives.append("report-uri /api/csp-report/")
    
    return '; '.join(directives)


def get_trusted_domains():
    """
    الحصول على قائمة المصادر الموثوقة
    """
    domains = set()
    
    for sources in CSP_CONFIG.values():
        if isinstance(sources, list):
            for source in sources:
                if source.startswith('https://'):
                    domains.add(source)
    
    return sorted(list(domains))


def add_trusted_domain(domain, directives=None):
    """
    إضافة مصدر موثوق جديد
    
    Args:
        domain (str): المصدر الجديد (مثل https://example.com)
        directives (list): قائمة التوجيهات (افتراضي: script-src, style-src)
    """
    if directives is None:
        directives = ['SCRIPT_SRC', 'STYLE_SRC']
    
    for directive in directives:
        if directive in CSP_CONFIG:
            if domain not in CSP_CONFIG[directive]:
                CSP_CONFIG[directive].append(domain)


def remove_trusted_domain(domain, directives=None):
    """
    إزالة مصدر موثوق
    
    Args:
        domain (str): المصدر المراد إزالته
        directives (list): قائمة التوجيهات (افتراضي: جميع التوجيهات)
    """
    if directives is None:
        directives = CSP_CONFIG.keys()
    
    for directive in directives:
        if directive in CSP_CONFIG and isinstance(CSP_CONFIG[directive], list):
            if domain in CSP_CONFIG[directive]:
                CSP_CONFIG[directive].remove(domain)


def validate_csp_config():
    """
    التحقق من صحة إعدادات CSP
    """
    errors = []
    
    # التحقق من وجود التوجيهات الأساسية
    required_directives = ['SCRIPT_SRC', 'STYLE_SRC', 'DEFAULT_SRC']
    for directive in required_directives:
        if directive not in CSP_CONFIG:
            errors.append(f"Missing required directive: {directive}")
    
    # التحقق من صحة المصادر
    for directive, sources in CSP_CONFIG.items():
        if isinstance(sources, list):
            for source in sources:
                if isinstance(source, str):
                    # التحقق من صحة المصادر
                    if source.startswith('http://') and not settings.DEBUG:
                        errors.append(f"HTTP source in production: {source} in {directive}")
    
    return errors


# تحديث إعدادات CSP بناءً على إعدادات Django
def update_csp_from_settings():
    """
    تحديث إعدادات CSP من إعدادات Django
    """
    # لا نضيف STATIC_URL و MEDIA_URL مباشرة لأنها مسارات نسبية
    # 'self' يغطي جميع الملفات المحلية بما في ذلك static و media
    pass


# تهيئة إعدادات CSP
update_csp_from_settings()

# التحقق من صحة الإعدادات
csp_errors = validate_csp_config()
if csp_errors and settings.DEBUG:
    import warnings
    for error in csp_errors:
        warnings.warn(f"CSP Configuration Warning: {error}")