/**
 * محمل نظام المدفوعات - Payment System Loader
 * يحمل جميع ملفات JavaScript المطلوبة لنظام المدفوعات بالترتيب الصحيح
 */

(function() {
    'use strict';

    // قائمة الملفات المطلوبة بالترتيب (مسارات نسبية)
    const requiredScripts = [
        'js/suppress-json-errors.js',
        'js/error-handler-config.js',
        'js/connection-monitor.js',
        'js/payment-error-recovery.js',
        'js/payment-processing.js',
        'js/payment_management.js',
    ];

    // قائمة ملفات CSS المطلوبة
    const requiredStyles = [
        'css/connection-status.css'
    ];

    let loadedScripts = 0;
    let loadedStyles = 0;
    let hasErrors = false;

    // الحصول على المسار الأساسي للملفات الثابتة
    function getStaticPath() {
        // البحث عن مسار static في الصفحة
        const scripts = document.querySelectorAll('script[src*="static"]');
        if (scripts.length > 0) {
            const src = scripts[0].src;
            const staticIndex = src.indexOf('/static/');
            if (staticIndex !== -1) {
                return src.substring(0, staticIndex + 8); // يتضمن /static/
            }
        }
        
        // المسار الافتراضي
        return '/static/';
    }

    const staticBasePath = getStaticPath();

    // دالة لتحميل ملف JavaScript
    function loadScript(src, callback) {
        const fullPath = staticBasePath + src;
        const script = document.createElement('script');
        script.src = fullPath;
        script.async = false; // تحميل متسلسل
        
        script.onload = function() {
            loadedScripts++;
            if (callback) callback(null);
        };
        
        script.onerror = function() {
            console.error(`❌ فشل في تحميل: ${src}`);
            hasErrors = true;
            loadedScripts++;
            if (callback) callback(new Error(`Failed to load ${src}`));
        };
        
        document.head.appendChild(script);
    }

    // دالة لتحميل ملف CSS
    function loadStyle(href) {
        const fullPath = staticBasePath + href;
        
        // تحقق من وجود الملف أولاً
        const existingLink = document.querySelector(`link[href="${fullPath}"]`);
        if (existingLink) {
            loadedStyles++;
            return;
        }

        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = fullPath;
        
        link.onload = function() {
            loadedStyles++;
        };
        
        link.onerror = function() {
            console.warn(`⚠️ فشل في تحميل CSS: ${href}`);
            loadedStyles++; // لا نعتبر CSS خطأ حرج
        };
        
        document.head.appendChild(link);
    }

    // دالة للتحقق من اكتمال التحميل
    function checkLoadingComplete() {
        if (loadedScripts >= requiredScripts.length && loadedStyles >= requiredStyles.length) {
            const message = hasErrors ? 
                'تم تحميل نظام المدفوعات مع بعض الأخطاء' : 
                'تم تحميل جميع ملفات نظام المدفوعات بنجاح';
                        
            // إرسال حدث اكتمال التحميل
            const event = new CustomEvent('paymentSystemLoaded', {
                detail: {
                    scriptsLoaded: loadedScripts,
                    stylesLoaded: loadedStyles,
                    hasErrors: hasErrors,
                    timestamp: new Date().toISOString()
                }
            });
            document.dispatchEvent(event);
            
            // تهيئة فورية للمكونات المتاحة
            initializeAvailableComponents();
        }
    }

    // تهيئة المكونات المتاحة
    function initializeAvailableComponents() {
        // تهيئة معالج الأخطاء
        if (typeof PaymentErrorHandler !== 'undefined' && !window.paymentErrorHandler) {
            try {
                window.paymentErrorHandler = new PaymentErrorHandler();
            } catch (error) {
                console.error('❌ خطأ في تهيئة معالج الأخطاء:', error);
            }
        }

        // تهيئة مراقب الاتصال
        if (typeof ConnectionMonitor !== 'undefined' && !window.connectionMonitor) {
            try {
                window.connectionMonitor = new ConnectionMonitor();
            } catch (error) {
                console.error('❌ خطأ في تهيئة مراقب الاتصال:', error);
            }
        }

        // تهيئة معالج المدفوعات
        if (typeof PaymentProcessor !== 'undefined' && !window.paymentProcessor) {
            try {
                if (document.querySelector('.payment-processing-component') || 
                    document.querySelector('.payment-processor')) {
                    window.paymentProcessor = new PaymentProcessor();
                }
            } catch (error) {
                console.error('❌ خطأ في تهيئة معالج المدفوعات:', error);
            }
        }

        // تهيئة معالج المدفوعات
    }

    // تحميل ملفات CSS أولاً
    requiredStyles.forEach(href => {
        loadStyle(href);
    });

    // تحميل ملفات JavaScript بالتسلسل
    function loadScriptsSequentially(index = 0) {
        if (index >= requiredScripts.length) {
            checkLoadingComplete();
            return;
        }

        loadScript(requiredScripts[index], (error) => {
            if (error) {
                console.warn(`تجاهل خطأ التحميل والمتابعة: ${error.message}`);
            }
            loadScriptsSequentially(index + 1);
        });
    }

    // بدء التحميل عند جاهزية DOM
    function startLoading() {
        loadScriptsSequentially();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', startLoading);
    } else {
        startLoading();
    }

    // مراقبة اكتمال تحميل CSS
    const styleCheckInterval = setInterval(() => {
        checkLoadingComplete();
        
        if (loadedStyles >= requiredStyles.length) {
            clearInterval(styleCheckInterval);
        }
    }, 100);

    // تنظيف بعد 30 ثانية (timeout)
    setTimeout(() => {
        clearInterval(styleCheckInterval);
        if (loadedScripts < requiredScripts.length || loadedStyles < requiredStyles.length) {
            console.warn('⏰ انتهت مهلة تحميل بعض ملفات نظام المدفوعات');
            // محاولة تهيئة ما هو متاح
            initializeAvailableComponents();
        }
    }, 30000);

})();

// إضافة مستمع لحدث اكتمال التحميل
document.addEventListener('paymentSystemLoaded', function(event) {
    
    // عرض حالة المكونات
    const components = [
        { name: 'معالج الأخطاء', obj: window.paymentErrorHandler },
        { name: 'مراقب الاتصال', obj: window.connectionMonitor },
        { name: 'معالج المدفوعات', obj: window.paymentProcessor },
    ];

    components.forEach(component => {
        const status = component.obj ? '✅ نشط' : '❌ غير متاح';
    });
});