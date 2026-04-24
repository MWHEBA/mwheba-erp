/**
 * Error Prevention Utility
 * أداة منع الأخطاء الشاملة
 * 
 * يجب تحميل هذا الملف قبل أي JavaScript آخر
 */

(function() {
    'use strict';

    // منع جميع أخطاء localStorage و sessionStorage
    const createSilentStorage = () => ({
        getItem: () => null,
        setItem: () => {},
        removeItem: () => {},
        clear: () => {},
        key: () => null,
        length: 0
    });

    // استبدال storage APIs بنسخ صامتة
    try {
        Object.defineProperty(window, 'localStorage', {
            value: createSilentStorage(),
            writable: false,
            configurable: false
        });
        Object.defineProperty(window, 'sessionStorage', {
            value: createSilentStorage(),
            writable: false,
            configurable: false
        });
    } catch (e) {
        // تجاهل أي أخطاء في التهيئة
    }

    // منع أخطاء console في البيئات المقيدة
    if (typeof console === 'undefined') {
        window.console = {
            log: () => {},
            warn: () => {},
            error: () => {},
            info: () => {},
            debug: () => {}
        };
    }

    // منع أخطاء Promise rejection غير المعالجة
    window.addEventListener('unhandledrejection', function(event) {
        // تجاهل أخطاء storage و notifications بصمت
        if (event.reason && typeof event.reason === 'object') {
            const message = event.reason.message || '';
            if (message.includes('storage') || 
                message.includes('localStorage') || 
                message.includes('sessionStorage') ||
                message.includes('notifications') ||
                message.includes('500')) {
                event.preventDefault();
                return;
            }
        }
    });

})();