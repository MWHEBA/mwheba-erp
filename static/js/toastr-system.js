/**
 * نظام Toastr العام للنظام
 * يمكن استخدامه في جميع وحدات النظام
 */

// إعدادات Toastr الافتراضية
if (typeof DEFAULT_TOASTR_OPTIONS === 'undefined') {
    var DEFAULT_TOASTR_OPTIONS = {
    closeButton: true,
    debug: false,
    newestOnTop: true,
    progressBar: true,
    positionClass: "toast-top-left",
    preventDuplicates: true,
    timeOut: 4000,
    extendedTimeOut: 1000,
    showDuration: 300,
    hideDuration: 1000,
    showEasing: "swing",
    hideEasing: "linear",
    showMethod: "fadeIn",
    hideMethod: "fadeOut",
    tapToDismiss: true,
    closeHtml: '<button type="button">&times;</button>',
    closeDuration: 300,
    rtl: true
    };
}

// إعدادات النظام المتقدم
if (typeof ADVANCED_TOASTR_OPTIONS === 'undefined') {
    var ADVANCED_TOASTR_OPTIONS = {
    ...DEFAULT_TOASTR_OPTIONS,
    timeOut: 5000,
    extendedTimeOut: 2000
    };
}

/**
 * تطبيق إعدادات Toastr
 */
if (typeof applyToastrOptions === 'undefined') {
    function applyToastrOptions(options = DEFAULT_TOASTR_OPTIONS) {
        if (typeof toastr !== 'undefined') {
            toastr.clear();
            toastr.options = { ...options };
            return true;
        }
        return false;
    }
}

/**
 * تهيئة إعدادات Toastr الأساسية
 */
window.initToastr = function() {
    if (applyToastrOptions()) {
        return true;
    }
    return false;
};

/**
 * نظام الإشعارات الموحد المحسن
 */
window.showNotification = function(message, type = 'info', title = null, customOptions = {}) {
    if (typeof toastr === 'undefined') {
        // fallback للمتصفحات القديمة
        const prefix = type === 'error' ? '❌' : type === 'success' ? '✅' : type === 'warning' ? '⚠️' : 'ℹ️';
        alert(`${prefix} ${title || type}: ${message}`);
        return false;
    }

    // إعدادات مخصصة حسب نوع الإشعار
    const typeConfig = {
        success: { timeOut: 3000, title: title || 'نجح' },
        error: { timeOut: 5000, title: title || 'خطأ' },
        warning: { timeOut: 4000, title: title || 'تحذير' },
        info: { timeOut: 4000, title: title || 'معلومات' }
    };

    const config = {
        ...DEFAULT_TOASTR_OPTIONS,
        ...typeConfig[type],
        ...customOptions
    };

    const toastrType = window.mapToToastrType(type);
    
    // تطبيق الإعدادات مؤقتاً
    const originalOptions = { ...toastr.options };
    toastr.options = { ...toastr.options, ...config };
    
    // عرض الإشعار
    const result = toastr[toastrType](message, config.title);
    
    // استعادة الإعدادات الأصلية
    toastr.options = originalOptions;
    
    return result;
};

/**
 * عرض رسالة toastr (للتوافق مع الكود القديم)
 */
window.showToastr = function(message, type = 'info', title = '') {
    return window.showNotification(message, type, title);
};

/**
 * تحويل أنواع الرسائل
 */
window.mapToToastrType = function(type) {
    const typeMap = {
        'success': 'success',
        'warning': 'warning',
        'danger': 'error',
        'error': 'error',
        'info': 'info'
    };
    return typeMap[type] || 'info';
};

/**
 * تحويل رسائل Django Messages إلى Toastr
 */
window.convertDjangoMessagesToToastr = function() {
    // البحث عن رسائل Django في الصفحة
    const djangoMessages = document.querySelectorAll('.messages .alert, .alert[role="alert"]');
    
    if (djangoMessages.length > 0 && typeof toastr !== 'undefined') {
        djangoMessages.forEach(alert => {
            window.convertSingleAlertToToastr(alert);
        });
        
    }
};

/**
 * تحويل جميع Bootstrap Alerts الموجودة إلى Toastr
 */
window.convertAllAlertsToToastr = function() {
    const alerts = document.querySelectorAll('.alert');
    
    alerts.forEach(alert => {
        window.convertSingleAlertToToastr(alert);
    });
};

/**
 * تحويل alert واحد إلى toastr
 */
window.convertSingleAlertToToastr = function(alert) {
    if (!alert || alert.dataset.converted === 'true') {
        return; // تجنب التحويل المكرر
    }
    
    // استخراج نوع الرسالة
    let type = 'info';
    if (alert.classList.contains('alert-success')) type = 'success';
    else if (alert.classList.contains('alert-warning')) type = 'warning';
    else if (alert.classList.contains('alert-danger')) type = 'error';
    else if (alert.classList.contains('alert-error')) type = 'error';
    else if (alert.classList.contains('alert-info')) type = 'info';
    
    // استخراج نص الرسالة (تنظيف من HTML)
    let messageText = alert.textContent || alert.innerText || '';
    messageText = messageText.trim();
    
    // إزالة نصوص الأزرار
    const buttons = alert.querySelectorAll('button, .btn-close');
    buttons.forEach(btn => {
        const btnText = btn.textContent || btn.innerText || '';
        if (btnText.trim()) {
            messageText = messageText.replace(btnText.trim(), '');
        }
    });
    
    messageText = messageText.trim();
    
    if (messageText && typeof toastr !== 'undefined') {
        // عرض الرسالة في toastr
        toastr[window.mapToToastrType(type)](messageText);
        
        // وضع علامة على أنه تم التحويل
        alert.dataset.converted = 'true';
        
        // إخفاء الـ alert الأصلي
        alert.style.display = 'none';
        alert.remove();
    }
};

/**
 * إعداد مراقب DOM لتحويل الـ alerts الجديدة
 */
window.setupAlertObserver = function() {
    const observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            mutation.addedNodes.forEach(function(node) {
                if (node.nodeType === 1) {
                    // تحويل الـ alert الجديد
                    if (node.classList && node.classList.contains('alert')) {
                        window.convertSingleAlertToToastr(node);
                    }
                    // البحث عن alerts داخل العنصر الجديد
                    const alerts = node.querySelectorAll && node.querySelectorAll('.alert');
                    if (alerts && alerts.length > 0) {
                        alerts.forEach(alert => window.convertSingleAlertToToastr(alert));
                    }
                }
            });
        });
    });
    
    observer.observe(document.body, {
        childList: true,
        subtree: true
    });
    
    return observer;
};

/**
 * تهيئة النظام المتقدم للتحويل الكامل
 */
window.initAdvancedToastrMode = function() {
    if (!applyToastrOptions(ADVANCED_TOASTR_OPTIONS)) {
        console.warn('⚠️ Toastr غير متوفر - لا يمكن تحويل الإشعارات');
        return false;
    }
        
    // تحويل رسائل Django فوراً
    setTimeout(() => window.convertAllAlertsToToastr(), 100);
    
    // إعداد مراقب DOM
    window.setupAlertObserver();
    
    return true;
};

/**
 * تهيئة تلقائية عند تحميل الصفحة
 */
document.addEventListener('DOMContentLoaded', function() {
    // انتظار تحميل toastr إذا كان موجوداً
    setTimeout(() => {
        if (window.initToastr()) {
            window.convertDjangoMessagesToToastr();
        }
    }, 100);
});

/**
 * دوال مختصرة للنظام الموحد
 */
window.showSuccess = function(message, title = 'نجح', options = {}) {
    return window.showNotification(message, 'success', title, options);
};

window.showError = function(message, title = 'خطأ', options = {}) {
    return window.showNotification(message, 'error', title, options);
};

window.showWarning = function(message, title = 'تحذير', options = {}) {
    return window.showNotification(message, 'warning', title, options);
};

window.showInfo = function(message, title = 'معلومات', options = {}) {
    return window.showNotification(message, 'info', title, options);
};

/**
 * إشعارات خاصة بنظام التسعير
 */
window.showPricingNotification = function(message, type = 'info', title = null) {
    const pricingOptions = {
        positionClass: 'toast-top-left',
        timeOut: type === 'success' ? 3000 : type === 'error' ? 5000 : 4000,
        extendedTimeOut: type === 'warning' ? 2000 : 1000
    };
    return window.showNotification(message, type, title, pricingOptions);
};

// ملاحظة: جميع الدوال مُصدرة بالفعل كـ window properties أعلاه
