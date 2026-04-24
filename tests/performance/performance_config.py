"""
إعدادات اختبارات الأداء
Performance Testing Configuration
"""
from dataclasses import dataclass
from typing import Dict, List, Any
import os


@dataclass
class PerformanceTestConfig:
    """إعدادات اختبارات الأداء"""
    
    # حدود الأداء العامة
    max_response_time_ms: float = 2000.0  # 2 ثانية
    max_memory_usage_mb: float = 512.0    # 512 MB
    max_cpu_usage_percent: float = 80.0   # 80%
    
    # حدود قاعدة البيانات
    max_database_queries: int = 50        # 50 استعلام
    max_database_time_ms: float = 1000.0  # 1 ثانية
    
    # إعدادات اختبار الحمولة
    concurrent_users: List[int] = None
    test_duration_seconds: int = 60
    ramp_up_time_seconds: int = 10
    
    # إعدادات التقارير
    reports_directory: str = "reports/performance"
    enable_detailed_logging: bool = True
    save_raw_data: bool = True
    
    def __post_init__(self):
        if self.concurrent_users is None:
            self.concurrent_users = [1, 5, 10, 25, 50]


# إعدادات مختلفة للبيئات المختلفة
DEVELOPMENT_CONFIG = PerformanceTestConfig(
    max_response_time_ms=3000.0,  # أكثر تساهلاً في التطوير
    max_memory_usage_mb=1024.0,
    max_cpu_usage_percent=90.0,
    concurrent_users=[1, 5, 10],
    test_duration_seconds=30
)

PRODUCTION_CONFIG = PerformanceTestConfig(
    max_response_time_ms=3000.0,  # 3 ثواني - واقعي لبيئة 1 كور
    max_memory_usage_mb=800.0,    # 800 MB من أصل 1GB (ترك مساحة للنظام)
    max_cpu_usage_percent=80.0,   # 80% كحد أقصى
    concurrent_users=[1, 3, 5, 8, 10],  # أعداد واقعية لـ 1 كور
    test_duration_seconds=120
)

CI_CONFIG = PerformanceTestConfig(
    max_response_time_ms=5000.0,  # أكثر تساهلاً في CI
    max_memory_usage_mb=512.0,
    max_cpu_usage_percent=95.0,
    concurrent_users=[1, 5],
    test_duration_seconds=15
)


def get_config() -> PerformanceTestConfig:
    """الحصول على الإعدادات المناسبة للبيئة الحالية"""
    environment = os.getenv('TESTING_ENVIRONMENT', 'development').lower()
    
    if environment == 'production':
        return PRODUCTION_CONFIG
    elif environment == 'ci':
        return CI_CONFIG
    else:
        return DEVELOPMENT_CONFIG


# إعدادات خاصة لبيئة الإنتاج المحدودة (1 كور، 1GB رام)
LOW_RESOURCE_PRODUCTION_CONFIG = PerformanceTestConfig(
    max_response_time_ms=4000.0,  # 4 ثواني - واقعي جداً لبيئة محدودة
    max_memory_usage_mb=700.0,    # 700 MB فقط (ترك 300MB للنظام)
    max_cpu_usage_percent=75.0,   # 75% كحد أقصى لتجنب التجمد
    max_database_queries=30,      # تقليل الاستعلامات
    max_database_time_ms=2000.0,  # ثانيتين للاستعلامات
    concurrent_users=[1, 2, 3, 5], # أعداد صغيرة جداً
    test_duration_seconds=90,
    reports_directory="reports/performance_low_resource"
)


def get_low_resource_config() -> PerformanceTestConfig:
    """إعدادات خاصة للبيئات محدودة الموارد"""
    return LOW_RESOURCE_PRODUCTION_CONFIG


# إعدادات العمليات الحرجة - معدلة لبيئة 1 كور و 1GB رام
CRITICAL_OPERATIONS_LIMITS = {
    'report_generation': {
        'max_response_time_ms': 8000.0,
        'max_database_queries': 80,
        'max_memory_mb': 400.0
    },
    'user_authentication': {
        'max_response_time_ms': 1000.0,
        'max_database_queries': 8,
        'max_memory_mb': 50.0
    },
    'dashboard_loading': {
        'max_response_time_ms': 3000.0,
        'max_database_queries': 40,
        'max_memory_mb': 128.0
    },
    'search_operations': {
        'max_response_time_ms': 1500.0,
        'max_database_queries': 25,
        'max_memory_mb': 96.0
    }
}


# سيناريوهات اختبار الحمولة
LOAD_TEST_SCENARIOS = {
    'light_load': {
        'users': 5,
        'duration': 60,
        'ramp_up': 10,
        'description': 'حمولة خفيفة - 5 مستخدمين'
    },
    'normal_load': {
        'users': 25,
        'duration': 120,
        'ramp_up': 30,
        'description': 'حمولة عادية - 25 مستخدم'
    },
    'peak_load': {
        'users': 50,
        'duration': 300,
        'ramp_up': 60,
        'description': 'حمولة الذروة - 50 مستخدم'
    },
    'stress_test': {
        'users': 100,
        'duration': 600,
        'ramp_up': 120,
        'description': 'اختبار الضغط - 100 مستخدم'
    }
}


# عمليات الاختبار الأساسية
BASIC_OPERATIONS = [
    {
        'name': 'login',
        'url': '/users/login/',
        'method': 'POST',
        'data': {'username': 'testuser', 'password': 'testpass'},
        'weight': 10
    },
    {
        'name': 'dashboard',
        'url': '/core/dashboard/',
        'method': 'GET',
        'weight': 20
    },
    {
        'name': 'financial_reports',
        'url': '/financial/reports/',
        'method': 'GET',
        'weight': 5
    }
]


# إعدادات المراقبة
MONITORING_CONFIG = {
    'sample_interval_seconds': 0.1,
    'memory_threshold_mb': 1024,
    'cpu_threshold_percent': 90,
    'response_time_threshold_ms': 5000,
    'enable_real_time_alerts': True,
    'alert_email': None  # يمكن إضافة بريد إلكتروني للتنبيهات
}


# إعدادات التقارير
REPORTING_CONFIG = {
    'generate_html_report': True,
    'generate_json_report': True,
    'generate_csv_report': True,
    'include_charts': True,
    'include_raw_data': False,  # لتوفير المساحة
    'compress_reports': True,
    'retention_days': 30  # الاحتفاظ بالتقارير لمدة 30 يوم
}


# إعدادات قاعدة البيانات للاختبار
DATABASE_TEST_CONFIG = {
    'use_in_memory_db': True,
    'enable_query_logging': True,
    'log_slow_queries': True,
    'slow_query_threshold_ms': 100,
    'max_connections': 10,
    'connection_timeout_seconds': 30
}

# سيناريوهات اختبار خاصة لبيئة الإنتاج المحدودة
LOW_RESOURCE_SCENARIOS = {
    'light_load': {
        'concurrent_users': 1,
        'duration_seconds': 30,
        'operations_per_user': 5,
        'description': 'حمولة خفيفة - مستخدم واحد'
    },
    'normal_load': {
        'concurrent_users': 3,
        'duration_seconds': 60,
        'operations_per_user': 10,
        'description': 'حمولة عادية - 3 مستخدمين'
    },
    'peak_load': {
        'concurrent_users': 5,
        'duration_seconds': 90,
        'operations_per_user': 8,
        'description': 'حمولة الذروة - 5 مستخدمين (الحد الأقصى)'
    },
    'stress_test': {
        'concurrent_users': 8,
        'duration_seconds': 30,
        'operations_per_user': 3,
        'description': 'اختبار الضغط - تجاوز الحد المتوقع'
    }
}

# نصائح التحسين لبيئة الإنتاج المحدودة
OPTIMIZATION_TIPS = {
    'memory': [
        "استخدم pagination للقوائم الطويلة",
        "قم بتنظيف الكائنات غير المستخدمة",
        "استخدم select_related و prefetch_related",
        "فعل ضغط الاستجابات (gzip)",
        "استخدم Redis للتخزين المؤقت"
    ],
    'cpu': [
        "استخدم الفهرسة المناسبة لقاعدة البيانات",
        "قلل من العمليات المعقدة في القوالب",
        "استخدم التخزين المؤقت للاستعلامات الثقيلة",
        "فعل ضغط الملفات الثابتة",
        "استخدم CDN للملفات الثابتة"
    ],
    'database': [
        "استخدم connection pooling",
        "قم بتحسين الاستعلامات البطيئة",
        "استخدم الفهارس المركبة",
        "فعل query caching",
        "قلل من عدد الاستعلامات per request"
    ]
}

def get_optimization_tips(resource_type: str) -> List[str]:
    """الحصول على نصائح التحسين لنوع مورد معين"""
    return OPTIMIZATION_TIPS.get(resource_type, [])

def assess_production_readiness(metrics: Dict[str, float]) -> Dict[str, Any]:
    """تقييم الجاهزية للإنتاج بناءً على المقاييس"""
    config = get_low_resource_config()
    
    assessment = {
        'ready': True,
        'warnings': [],
        'recommendations': [],
        'score': 100
    }
    
    # تقييم وقت الاستجابة
    if metrics.get('response_time_ms', 0) > config.max_response_time_ms * 0.8:
        assessment['warnings'].append(f"وقت الاستجابة مرتفع: {metrics['response_time_ms']:.1f}ms")
        assessment['score'] -= 20
        assessment['recommendations'].extend(get_optimization_tips('cpu'))
    
    # تقييم الذاكرة
    if metrics.get('memory_usage_mb', 0) > config.max_memory_usage_mb * 0.7:
        assessment['warnings'].append(f"استهلاك الذاكرة مرتفع: {metrics['memory_usage_mb']:.1f}MB")
        assessment['score'] -= 25
        assessment['recommendations'].extend(get_optimization_tips('memory'))
    
    # تقييم المعالج
    if metrics.get('cpu_usage_percent', 0) > config.max_cpu_usage_percent * 0.8:
        assessment['warnings'].append(f"استهلاك المعالج مرتفع: {metrics['cpu_usage_percent']:.1f}%")
        assessment['score'] -= 15
        assessment['recommendations'].extend(get_optimization_tips('cpu'))
    
    # تحديد الجاهزية النهائية
    if assessment['score'] < 60:
        assessment['ready'] = False
    
    return assessment