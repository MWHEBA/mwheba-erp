# -*- coding: utf-8 -*-
"""
إعدادات نظام المنتجات المجمعة
Bundle Products System Configuration

إعدادات قابلة للتخصيص لبيئات النشر المختلفة
"""

import os
from typing import Dict, Any

# إعدادات الأداء
BUNDLE_PERFORMANCE_SETTINGS = {
    # الحد الأقصى لوقت حساب المخزون (بالثواني)
    'MAX_STOCK_CALCULATION_TIME': 2.0,
    
    # الحد الأقصى لوقت معالجة المبيعات (بالثواني)
    'MAX_SALES_PROCESSING_TIME': 3.0,
    
    # عدد المنتجات المجمعة المسموح بمعالجتها في المرة الواحدة
    'MAX_BUNDLES_PER_BATCH': 1000,
    
    # تفعيل التخزين المؤقت للمخزون
    'ENABLE_STOCK_CACHING': True,
    
    # مدة التخزين المؤقت (بالثواني)
    'STOCK_CACHE_TIMEOUT': 300,  # 5 دقائق
    
    # تفعيل حساب المخزون المتوازي
    'ENABLE_PARALLEL_CALCULATION': False,
}

# إعدادات التنبيهات
BUNDLE_ALERT_SETTINGS = {
    # تفعيل تنبيهات المخزون المنخفض
    'ENABLE_LOW_STOCK_ALERTS': True,
    
    # حد المخزون المنخفض
    'LOW_STOCK_THRESHOLD': 10,
    
    # تفعيل تنبيهات نفاد المخزون
    'ENABLE_OUT_OF_STOCK_ALERTS': True,
    
    # تفعيل تنبيهات الأداء
    'ENABLE_PERFORMANCE_ALERTS': True,
    
    # حد تنبيه الأداء (بالثواني)
    'PERFORMANCE_ALERT_THRESHOLD': 5.0,
}

# إعدادات السجلات
BUNDLE_LOGGING_SETTINGS = {
    # مستوى السجلات
    'LOG_LEVEL': 'INFO',
    
    # تفعيل سجلات الأداء
    'ENABLE_PERFORMANCE_LOGGING': True,
    
    # تفعيل سجلات المعاملات
    'ENABLE_TRANSACTION_LOGGING': True,
    
    # تفعيل سجلات الأخطاء المفصلة
    'ENABLE_DETAILED_ERROR_LOGGING': True,
    
    # مدة الاحتفاظ بالسجلات (بالأيام)
    'LOG_RETENTION_DAYS': 30,
}

# إعدادات الأمان
BUNDLE_SECURITY_SETTINGS = {
    # تفعيل تسجيل العمليات الحساسة
    'ENABLE_AUDIT_LOGGING': True,
    
    # تفعيل التحقق من الصلاحيات المتقدم
    'ENABLE_ADVANCED_PERMISSIONS': True,
    
    # تفعيل حماية CSRF للعمليات الحساسة
    'ENABLE_CSRF_PROTECTION': True,
    
    # الحد الأقصى لحجم المعاملة الواحدة
    'MAX_TRANSACTION_SIZE': 1000,
}

# إعدادات التكامل
BUNDLE_INTEGRATION_SETTINGS = {
    # تفعيل التكامل مع النظام المالي
    'ENABLE_FINANCIAL_INTEGRATION': True,
    
    # تفعيل التكامل مع نظام الطلبات
    'ENABLE_ORDER_INTEGRATION': True,
    
    # تفعيل التكامل مع نظام المخزون
    'ENABLE_INVENTORY_INTEGRATION': True,
    
    # تفعيل التكامل مع نظام التقارير
    'ENABLE_REPORTING_INTEGRATION': True,
}

# إعدادات قاعدة البيانات
BUNDLE_DATABASE_SETTINGS = {
    # تفعيل الفهارس المتقدمة
    'ENABLE_ADVANCED_INDEXES': True,
    
    # تفعيل تحسين الاستعلامات
    'ENABLE_QUERY_OPTIMIZATION': True,
    
    # حجم دفعة المعالجة
    'BATCH_SIZE': 100,
    
    # تفعيل المعاملات الذرية
    'ENABLE_ATOMIC_TRANSACTIONS': True,
}


class BundleSystemConfig:
    """فئة إدارة إعدادات نظام المنتجات المجمعة"""
    
    def __init__(self, environment: str = 'production'):
        self.environment = environment
        self.settings = self._load_settings()
    
    def _load_settings(self) -> Dict[str, Any]:
        """تحميل الإعدادات حسب البيئة"""
        base_settings = {
            'PERFORMANCE': BUNDLE_PERFORMANCE_SETTINGS.copy(),
            'ALERTS': BUNDLE_ALERT_SETTINGS.copy(),
            'LOGGING': BUNDLE_LOGGING_SETTINGS.copy(),
            'SECURITY': BUNDLE_SECURITY_SETTINGS.copy(),
            'INTEGRATION': BUNDLE_INTEGRATION_SETTINGS.copy(),
            'DATABASE': BUNDLE_DATABASE_SETTINGS.copy(),
        }
        
        # تخصيص الإعدادات حسب البيئة
        if self.environment == 'development':
            base_settings['LOGGING']['LOG_LEVEL'] = 'DEBUG'
            base_settings['PERFORMANCE']['ENABLE_STOCK_CACHING'] = False
            base_settings['SECURITY']['ENABLE_ADVANCED_PERMISSIONS'] = False
            
        elif self.environment == 'testing':
            base_settings['LOGGING']['LOG_LEVEL'] = 'WARNING'
            base_settings['ALERTS']['ENABLE_LOW_STOCK_ALERTS'] = False
            base_settings['PERFORMANCE']['STOCK_CACHE_TIMEOUT'] = 60
            
        elif self.environment == 'staging':
            base_settings['LOGGING']['LOG_LEVEL'] = 'INFO'
            base_settings['PERFORMANCE']['ENABLE_PARALLEL_CALCULATION'] = True
            
        elif self.environment == 'production':
            base_settings['LOGGING']['LOG_LEVEL'] = 'WARNING'
            base_settings['PERFORMANCE']['ENABLE_PARALLEL_CALCULATION'] = True
            base_settings['SECURITY']['ENABLE_ADVANCED_PERMISSIONS'] = True
        
        # تطبيق إعدادات متغيرات البيئة
        self._apply_environment_variables(base_settings)
        
        return base_settings
    
    def _apply_environment_variables(self, settings: Dict[str, Any]):
        """تطبيق إعدادات متغيرات البيئة"""
        env_mappings = {
            'BUNDLE_MAX_STOCK_CALC_TIME': ('PERFORMANCE', 'MAX_STOCK_CALCULATION_TIME', float),
            'BUNDLE_MAX_SALES_PROC_TIME': ('PERFORMANCE', 'MAX_SALES_PROCESSING_TIME', float),
            'BUNDLE_ENABLE_CACHING': ('PERFORMANCE', 'ENABLE_STOCK_CACHING', bool),
            'BUNDLE_CACHE_TIMEOUT': ('PERFORMANCE', 'STOCK_CACHE_TIMEOUT', int),
            'BUNDLE_LOW_STOCK_THRESHOLD': ('ALERTS', 'LOW_STOCK_THRESHOLD', int),
            'BUNDLE_LOG_LEVEL': ('LOGGING', 'LOG_LEVEL', str),
            'BUNDLE_LOG_RETENTION_DAYS': ('LOGGING', 'LOG_RETENTION_DAYS', int),
            'BUNDLE_MAX_TRANSACTION_SIZE': ('SECURITY', 'MAX_TRANSACTION_SIZE', int),
            'BUNDLE_BATCH_SIZE': ('DATABASE', 'BATCH_SIZE', int),
        }
        
        for env_var, (category, key, type_func) in env_mappings.items():
            value = os.getenv(env_var)
            if value is not None:
                try:
                    if type_func == bool:
                        settings[category][key] = value.lower() in ('true', '1', 'yes', 'on')
                    else:
                        settings[category][key] = type_func(value)
                except (ValueError, TypeError):
                    print(f"تحذير: قيمة غير صحيحة لمتغير البيئة {env_var}: {value}")
    
    def get(self, category: str, key: str, default=None):
        """الحصول على قيمة إعداد محدد"""
        return self.settings.get(category, {}).get(key, default)
    
    def get_all(self, category: str) -> Dict[str, Any]:
        """الحصول على جميع إعدادات فئة معينة"""
        return self.settings.get(category, {})
    
    def update(self, category: str, key: str, value: Any):
        """تحديث قيمة إعداد"""
        if category not in self.settings:
            self.settings[category] = {}
        self.settings[category][key] = value
    
    def validate_settings(self) -> Dict[str, list]:
        """التحقق من صحة الإعدادات"""
        errors = {}
        
        # التحقق من إعدادات الأداء
        perf = self.settings['PERFORMANCE']
        if perf['MAX_STOCK_CALCULATION_TIME'] <= 0:
            errors.setdefault('PERFORMANCE', []).append('MAX_STOCK_CALCULATION_TIME يجب أن يكون أكبر من صفر')
        
        if perf['MAX_SALES_PROCESSING_TIME'] <= 0:
            errors.setdefault('PERFORMANCE', []).append('MAX_SALES_PROCESSING_TIME يجب أن يكون أكبر من صفر')
        
        if perf['STOCK_CACHE_TIMEOUT'] < 60:
            errors.setdefault('PERFORMANCE', []).append('STOCK_CACHE_TIMEOUT يجب أن يكون 60 ثانية على الأقل')
        
        # التحقق من إعدادات التنبيهات
        alerts = self.settings['ALERTS']
        if alerts['LOW_STOCK_THRESHOLD'] < 0:
            errors.setdefault('ALERTS', []).append('LOW_STOCK_THRESHOLD يجب أن يكون صفر أو أكبر')
        
        # التحقق من إعدادات السجلات
        logging_settings = self.settings['LOGGING']
        valid_log_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if logging_settings['LOG_LEVEL'] not in valid_log_levels:
            errors.setdefault('LOGGING', []).append(f'LOG_LEVEL يجب أن يكون أحد: {valid_log_levels}')
        
        if logging_settings['LOG_RETENTION_DAYS'] < 1:
            errors.setdefault('LOGGING', []).append('LOG_RETENTION_DAYS يجب أن يكون يوم واحد على الأقل')
        
        return errors
    
    def export_config(self) -> str:
        """تصدير الإعدادات كنص"""
        lines = [f"# إعدادات نظام المنتجات المجمعة - البيئة: {self.environment}"]
        lines.append(f"# تم الإنشاء في: {os.popen('date').read().strip()}")
        lines.append("")
        
        for category, settings in self.settings.items():
            lines.append(f"[{category}]")
            for key, value in settings.items():
                lines.append(f"{key} = {value}")
            lines.append("")
        
        return "\n".join(lines)


# إنشاء مثيل الإعدادات الافتراضي
def get_bundle_config(environment: str = None) -> BundleSystemConfig:
    """الحصول على إعدادات نظام المنتجات المجمعة"""
    if environment is None:
        environment = os.getenv('DJANGO_ENV', 'production')
    
    return BundleSystemConfig(environment)


# إعدادات سريعة للاستخدام المباشر
def get_performance_settings() -> Dict[str, Any]:
    """الحصول على إعدادات الأداء"""
    config = get_bundle_config()
    return config.get_all('PERFORMANCE')


def get_alert_settings() -> Dict[str, Any]:
    """الحصول على إعدادات التنبيهات"""
    config = get_bundle_config()
    return config.get_all('ALERTS')


def get_logging_settings() -> Dict[str, Any]:
    """الحصول على إعدادات السجلات"""
    config = get_bundle_config()
    return config.get_all('LOGGING')


# مثال على الاستخدام
if __name__ == '__main__':
    # إنشاء إعدادات للبيئات المختلفة
    environments = ['development', 'testing', 'staging', 'production']
    
    for env in environments:
        config = BundleSystemConfig(env)
        
        # التحقق من صحة الإعدادات
        errors = config.validate_settings()
        if errors:
            print(f"أخطاء في إعدادات {env}:")
            for category, error_list in errors.items():
                for error in error_list:
                    print(f"  {category}: {error}")
        else:
            print(f"✓ إعدادات {env} صحيحة")
        
        # تصدير الإعدادات
        config_text = config.export_config()
        with open(f"config/bundle_config_{env}.conf", 'w', encoding='utf-8') as f:
            f.write(config_text)
        
        print(f"تم تصدير إعدادات {env} إلى bundle_config_{env}.conf")
    
    print("تم إنشاء جميع ملفات الإعدادات بنجاح!")