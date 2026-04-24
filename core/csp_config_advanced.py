"""
🔒 CSP Configuration Advanced
إعدادات CSP متقدمة مع دعم نهج مختلط للأمان
"""

from django.conf import settings

# Module-level cache - built once per process restart, not per request
_csp_policy_cache = {}


def get_csp_config_for_environment():
    """
    الحصول على إعدادات CSP حسب البيئة
    """
    
    # إعدادات أساسية مشتركة
    base_config = {
        'FONT_SRC': [
            "'self'",
            "https://fonts.gstatic.com",
            "https://cdn.jsdelivr.net",
            "https://cdnjs.cloudflare.com",
            "data:",
        ],
        
        'IMG_SRC': [
            "'self'",
            "data:",
            "blob:",
            "https:",
        ],
        
        'CONNECT_SRC': [
            "'self'",
            "https://cdn.jsdelivr.net",
            "https://cdnjs.cloudflare.com",
            "https://cloudflareinsights.com",  # Cloudflare Analytics
        ],
        
        'MEDIA_SRC': ["'self'"],
        'OBJECT_SRC': ["'none'"],
        'BASE_URI': ["'self'"],
        'FORM_ACTION': ["'self'"],
        'FRAME_ANCESTORS': ["'none'"],
        'FRAME_SRC': ["'none'"],
        'WORKER_SRC': ["'self'"],
        'MANIFEST_SRC': ["'self'"],
        'DEFAULT_SRC': ["'self'"],
    }
    
    if settings.DEBUG:
        # في التطوير: استخدم unsafe-inline للسهولة
        development_config = {
            'SCRIPT_SRC': [
                "'self'",
                "'unsafe-inline'",
                "'unsafe-eval'",
                "https://cdn.jsdelivr.net",
                "https://cdnjs.cloudflare.com",
                "https://code.jquery.com",
                "https://cdn.datatables.net",
                "localhost:*",
                "127.0.0.1:*",
            ],
            
            'STYLE_SRC': [
                "'self'",
                "'unsafe-inline'",
                "https://cdn.jsdelivr.net",
                "https://cdnjs.cloudflare.com",
                "https://fonts.googleapis.com",
                "https://cdn.datatables.net",
            ],
            
            'CONNECT_SRC': [
                "'self'",
                "https://cdn.jsdelivr.net",
                "https://cdnjs.cloudflare.com",
                "localhost:*",
                "127.0.0.1:*",
                "ws://localhost:*",
                "ws://127.0.0.1:*",
            ],
        }
        
    else:
        # في الإنتاج: استخدم nonce للأمان
        production_config = {
            'SCRIPT_SRC': [
                "'self'",
                "'unsafe-inline'",  # مطلوب للـ inline scripts في الـ templates
                "https://cdn.jsdelivr.net",
                "https://cdnjs.cloudflare.com",
                "https://code.jquery.com",
                "https://cdn.datatables.net",
                "https://static.cloudflareinsights.com",  # Cloudflare Analytics beacon
            ],
            
            'STYLE_SRC': [
                "'self'",
                "'unsafe-inline'",
                "https://cdn.jsdelivr.net",
                "https://cdnjs.cloudflare.com",
                "https://fonts.googleapis.com",
                "https://cdn.datatables.net",
            ],
            
            'UPGRADE_INSECURE_REQUESTS': True,
        }
        
        base_config.update(production_config)
        return base_config
    
    base_config.update(development_config)
    return base_config


def build_csp_policy_advanced(nonce=None):
    """
    بناء CSP policy متقدمة حسب البيئة.
    بدون nonce: يُكاش على مستوى الـ module (مرة واحدة per process).
    مع nonce: يُبنى في كل request (مطلوب للأمان).
    """
    # لو في nonce، لازم نبني من جديد في كل request
    if nonce:
        return _build_policy(nonce)

    # بدون nonce: استخدم الـ cache
    cache_key = 'production' if not settings.DEBUG else 'development'
    if cache_key not in _csp_policy_cache:
        _csp_policy_cache[cache_key] = _build_policy(None)
    return _csp_policy_cache[cache_key]


def clear_csp_cache():
    """مسح الـ CSP cache - استخدم بعد تغيير الإعدادات"""
    _csp_policy_cache.clear()


def _build_policy(nonce=None):
    """البناء الفعلي للـ CSP policy"""
    config = get_csp_config_for_environment()
    directives = []

    for directive, sources in config.items():
        if directive == 'UPGRADE_INSECURE_REQUESTS':
            if sources:
                directives.append('upgrade-insecure-requests')
            continue

        directive_name = directive.lower().replace('_', '-')

        if not settings.DEBUG and nonce and directive in ['SCRIPT_SRC', 'STYLE_SRC']:
            sources = sources.copy()
            sources.insert(1, f"'nonce-{nonce}'")

        directive_value = f"{directive_name} {' '.join(sources)}"
        directives.append(directive_value)

    if not settings.DEBUG:
        directives.append("report-uri /api/csp-report/")

    return '; '.join(directives)


def should_use_nonce():
    """
    تحديد ما إذا كان يجب استخدام nonce
    """
    return not settings.DEBUG  # استخدم nonce فقط في الإنتاج