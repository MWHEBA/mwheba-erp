/**
 * Safe Element Access Utilities
 * أدوات الوصول الآمن للعناصر
 */

(function() {
    'use strict';

    // دالة الوصول الآمن للعناصر
    function safeGetElement(selector, context = document) {
        try {
            const element = typeof selector === 'string' 
                ? context.querySelector(selector)
                : selector;
            
            return element || null;
        } catch (error) {
            console.warn(`Safe element access failed for selector: ${selector}`, error);
            return null;
        }
    }

    // دالة الوصول الآمن لعدة عناصر
    function safeGetElements(selector, context = document) {
        try {
            const elements = typeof selector === 'string' 
                ? context.querySelectorAll(selector)
                : selector;
            
            return Array.from(elements || []);
        } catch (error) {
            console.warn(`Safe elements access failed for selector: ${selector}`, error);
            return [];
        }
    }

    // دالة التحقق من وجود العنصر وتنفيذ عملية آمنة
    function safeElementOperation(selector, operation, context = document) {
        const element = safeGetElement(selector, context);
        if (element && typeof operation === 'function') {
            try {
                return operation(element);
            } catch (error) {
                console.warn(`Safe operation failed for element:`, element, error);
                return null;
            }
        }
        return null;
    }

    // دالة تعديل الأنماط بشكل آمن
    function safeSetStyle(selector, property, value, context = document) {
        return safeElementOperation(selector, (element) => {
            if (element.style) {
                element.style[property] = value;
                return true;
            }
            return false;
        }, context);
    }

    // دالة إضافة مستمع الأحداث بشكل آمن
    function safeAddEventListener(selector, event, handler, context = document) {
        return safeElementOperation(selector, (element) => {
            element.addEventListener(event, handler);
            return true;
        }, context);
    }

    // دالة تعديل المحتوى بشكل آمن
    function safeSetContent(selector, content, context = document) {
        return safeElementOperation(selector, (element) => {
            if (typeof content === 'string') {
                element.textContent = content;
            } else {
                element.innerHTML = content;
            }
            return true;
        }, context);
    }

    // دالة تعديل القيم بشكل آمن
    function safeSetValue(selector, value, context = document) {
        return safeElementOperation(selector, (element) => {
            if ('value' in element) {
                element.value = value;
                return true;
            }
            return false;
        }, context);
    }

    // دالة التحقق من وجود العنصر
    function elementExists(selector, context = document) {
        return safeGetElement(selector, context) !== null;
    }

    // دالة انتظار ظهور العنصر
    function waitForElement(selector, timeout = 5000, context = document) {
        return new Promise((resolve, reject) => {
            const element = safeGetElement(selector, context);
            if (element) {
                resolve(element);
                return;
            }

            const observer = new MutationObserver((mutations, obs) => {
                const element = safeGetElement(selector, context);
                if (element) {
                    obs.disconnect();
                    resolve(element);
                }
            });

            observer.observe(context, {
                childList: true,
                subtree: true
            });

            setTimeout(() => {
                observer.disconnect();
                reject(new Error(`Element ${selector} not found within ${timeout}ms`));
            }, timeout);
        });
    }

    // تصدير الدوال للاستخدام العام
    window.SafeDOM = {
        get: safeGetElement,
        getAll: safeGetElements,
        operation: safeElementOperation,
        setStyle: safeSetStyle,
        addEventListener: safeAddEventListener,
        setContent: safeSetContent,
        setValue: safeSetValue,
        exists: elementExists,
        waitFor: waitForElement
    };

    // اختصارات مفيدة
    window.$ = window.$ || safeGetElement;
    window.$$ = window.$$ || safeGetElements;

})();