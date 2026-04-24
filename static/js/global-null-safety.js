/**
 * Global Null Safety for DOM Operations
 * حماية شاملة من أخطاء null في عمليات DOM - نسخة محسنة
 */

(function() {
    'use strict';

    // تعديل console.error لتصفية أخطاء style المتكررة فقط
    const originalConsoleError = console.error;
    let styleErrorCount = 0;
    const MAX_STYLE_ERRORS = 3;

    console.error = function(...args) {
        const message = args.join(' ');
        
        // تصفية أخطاء style المتكررة فقط
        if (message.includes("Cannot read properties of null (reading 'style')") ||
            message.includes("Cannot read property 'style' of null")) {
            
            styleErrorCount++;
            
            if (styleErrorCount <= MAX_STYLE_ERRORS) {
                console.warn(`Style access error #${styleErrorCount} (suppressing after ${MAX_STYLE_ERRORS}):`, ...args);
            }
            
            // عدم إظهار الخطأ بعد الحد الأقصى
            if (styleErrorCount > MAX_STYLE_ERRORS) {
                return;
            }
        } else {
            // إظهار الأخطاء الأخرى بشكل طبيعي
            originalConsoleError.apply(console, args);
        }
    };

    // إعادة تعيين عداد أخطاء style كل دقيقة
    setInterval(() => {
        styleErrorCount = 0;
    }, 60000);

    // دالة مساعدة للوصول الآمن للعناصر
    window.safeQuery = function(selector, context = document) {
        try {
            const element = context.querySelector(selector);
            return element;
        } catch (error) {
            console.warn('safeQuery failed:', selector, error.message);
            return null;
        }
    };

    // دالة مساعدة للوصول الآمن لعدة عناصر
    window.safeQueryAll = function(selector, context = document) {
        try {
            const elements = context.querySelectorAll(selector);
            return Array.from(elements);
        } catch (error) {
            console.warn('safeQueryAll failed:', selector, error.message);
            return [];
        }
    };

    // دالة مساعدة للوصول الآمن بالـ ID
    window.safeGetById = function(id, context = document) {
        try {
            const element = context.getElementById(id);
            return element;
        } catch (error) {
            console.warn('safeGetById failed:', id, error.message);
            return null;
        }
    };

    // دالة مساعدة لتعديل الأنماط بأمان
    window.safeSetStyle = function(selector, property, value, context = document) {
        const element = window.safeQuery(selector, context);
        if (element && element.style) {
            try {
                element.style[property] = value;
                return true;
            } catch (error) {
                console.warn('safeSetStyle failed:', selector, property, value, error.message);
                return false;
            }
        }
        return false;
    };

    // دالة مساعدة لإضافة event listeners بأمان
    window.safeAddEventListener = function(selector, event, handler, context = document) {
        const element = window.safeQuery(selector, context);
        if (element && typeof element.addEventListener === 'function') {
            try {
                element.addEventListener(event, handler);
                return true;
            } catch (error) {
                console.warn('safeAddEventListener failed:', selector, event, error.message);
                return false;
            }
        }
        return false;
    };

    // دالة مساعدة للتحقق من وجود العنصر
    window.elementExists = function(selector, context = document) {
        try {
            return context.querySelector(selector) !== null;
        } catch (error) {
            console.warn('elementExists check failed:', selector, error.message);
            return false;
        }
    };

    // دالة مساعدة لإنشاء عناصر بأمان
    window.safeCreateElement = function(tagName, attributes = {}, styles = {}) {
        try {
            const element = document.createElement(tagName);
            
            // إضافة الخصائص
            Object.keys(attributes).forEach(key => {
                try {
                    element.setAttribute(key, attributes[key]);
                } catch (error) {
                    console.warn('Failed to set attribute:', key, error.message);
                }
            });
            
            // إضافة الأنماط
            Object.keys(styles).forEach(key => {
                try {
                    element.style[key] = styles[key];
                } catch (error) {
                    console.warn('Failed to set style:', key, error.message);
                }
            });
            
            return element;
        } catch (error) {
            console.warn('safeCreateElement failed:', tagName, error.message);
            return null;
        }
    };

    // دالة مساعدة لإضافة عنصر بأمان
    window.safeAppendChild = function(parent, child) {
        try {
            if (parent && child && typeof parent.appendChild === 'function') {
                parent.appendChild(child);
                return true;
            }
            return false;
        } catch (error) {
            console.warn('safeAppendChild failed:', error.message);
            return false;
        }
    };

    // تصدير الدوال للاستخدام العام
    window.GlobalNullSafety = {
        safeQuery: window.safeQuery,
        safeQueryAll: window.safeQueryAll,
        safeGetById: window.safeGetById,
        safeSetStyle: window.safeSetStyle,
        safeAddEventListener: window.safeAddEventListener,
        elementExists: window.elementExists,
        safeCreateElement: window.safeCreateElement,
        safeAppendChild: window.safeAppendChild
    };

})();