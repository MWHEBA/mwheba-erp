/**
 * Error Cleanup Utilities
 * أدوات تنظيف الأخطاء المتكررة
 */

(function() {
    'use strict';

    // قائمة الأخطاء المتجاهلة
    const IGNORED_ERRORS = [
        'Cannot read properties of null (reading \'style\')',
        'Cannot read properties of undefined (reading \'style\')',
        'Cannot read property \'style\' of null',
        'Cannot read property \'style\' of undefined',
        'Failed to execute \'appendChild\' on \'Node\'',
        'Failed to execute \'insertBefore\' on \'Node\'',
        'Failed to execute \'getComputedStyle\' on \'Window\'',
        'parameter 1 is not of type \'Node\'',
        'parameter 1 is not of type \'Element\'',
        'الزر معطل حالياً',
        'Element not found',
        'querySelector returned null',
        'getElementById returned null'
    ];

    // عداد الأخطاء المتكررة
    const errorCounts = new Map();
    const MAX_SAME_ERROR = 3; // الحد الأقصى لنفس الخطأ

    // دالة التحقق من الأخطاء المتكررة
    function shouldSuppressError(errorMessage) {
        if (!errorMessage) return false;

        // التحقق من الأخطاء المتجاهلة
        const isIgnored = IGNORED_ERRORS.some(ignored => 
            errorMessage.includes(ignored)
        );

        if (isIgnored) {
            const count = errorCounts.get(errorMessage) || 0;
            errorCounts.set(errorMessage, count + 1);
            
            // إذا تكرر الخطأ أكثر من الحد المسموح، قم بكتمه
            if (count >= MAX_SAME_ERROR) {
                return true;
            }
        }

        return false;
    }

    // تنظيف عدادات الأخطاء كل دقيقة
    setInterval(() => {
        errorCounts.clear();
    }, 60000);

    // تعديل console.error لتصفية الأخطاء المتكررة
    const originalConsoleError = console.error;
    console.error = function(...args) {
        const errorMessage = args.join(' ');
        
        if (!shouldSuppressError(errorMessage)) {
            originalConsoleError.apply(console, args);
        }
    };

    // تعديل console.warn لتصفية التحذيرات المتكررة
    const originalConsoleWarn = console.warn;
    console.warn = function(...args) {
        const warnMessage = args.join(' ');
        
        if (!shouldSuppressError(warnMessage)) {
            originalConsoleWarn.apply(console, args);
        }
    };

    // دالة تنظيف الأخطاء من DOM
    function cleanupDOMErrors() {
        // إزالة event listeners التي تسبب أخطاء
        const problematicElements = document.querySelectorAll('[data-error-prone="true"]');
        problematicElements.forEach(element => {
            // إزالة جميع event listeners
            const newElement = element.cloneNode(true);
            element.parentNode.replaceChild(newElement, element);
        });
    }

    // دالة إصلاح العناصر المفقودة
    function fixMissingElements() {
        // إنشاء عناصر placeholder للعناصر المفقودة الشائعة
        const commonMissingElements = [
            { id: 'single-payment-section', tag: 'div', style: 'display: none;' },
            { id: 'multiple-payment-section', tag: 'div', style: 'display: none;' },
            { class: 'reference-section', tag: 'div', style: 'display: none;' },
            { class: 'form-progress-bar', tag: 'div', style: 'width: 0%;' }
        ];

        commonMissingElements.forEach(elementInfo => {
            let exists = false;
            
            try {
                if (elementInfo.id) {
                    exists = document.getElementById(elementInfo.id) !== null;
                } else if (elementInfo.class) {
                    exists = document.querySelector(`.${elementInfo.class}`) !== null;
                }

                if (!exists) {
                    // استخدام الدالة الآمنة لإنشاء العنصر
                    const element = window.safeCreateElement ? 
                        window.safeCreateElement(elementInfo.tag) : 
                        document.createElement(elementInfo.tag);
                    
                    if (element) {
                        if (elementInfo.id) {
                            element.id = elementInfo.id;
                        }
                        if (elementInfo.class) {
                            element.className = elementInfo.class;
                        }
                        if (elementInfo.style) {
                            element.setAttribute('style', elementInfo.style);
                        }
                        
                        // إضافة العنصر إلى body (مخفي)
                        element.style.display = 'none';
                        element.setAttribute('data-placeholder', 'true');
                        
                        // استخدام الدالة الآمنة لإضافة العنصر
                        if (window.safeAppendChild) {
                            window.safeAppendChild(document.body, element);
                        } else {
                            document.body.appendChild(element);
                        }
                        
                    }
                }
            } catch (error) {
                console.warn(`Error creating placeholder element ${elementInfo.id || elementInfo.class}:`, error.message);
            }
        });

        // إصلاح الأزرار المعطلة بإضافة رسائل توضيحية
        try {
            const disabledButtons = document.querySelectorAll('button[disabled]');
            disabledButtons.forEach(button => {
                // تجاهل الأزرار التي يجب أن تكون معطلة (مثل btn-locked)
                if (button.classList.contains('btn-locked') || button.classList.contains('quick-pay-btn')) {
                    if (!button.hasAttribute('data-disabled-reason')) {
                        button.setAttribute('data-disabled-reason', 'يجب سداد الرسوم أولاً');
                        button.style.cursor = 'not-allowed';
                        button.style.opacity = '0.6';
                        
                        // إضافة tooltip إذا لم يكن موجود
                        if (!button.hasAttribute('title')) {
                            button.setAttribute('title', 'يجب سداد الرسوم أولاً قبل استخدام هذا الزر');
                        }
                    }
                }
            });
        } catch (error) {
            console.warn('Error fixing disabled buttons:', error.message);
        }
    }

    // دالة تنظيف شاملة
    function performErrorCleanup() {
        try {
            cleanupDOMErrors();
            fixMissingElements();
        } catch (error) {
            console.warn('Error during cleanup:', error);
        }
    }

    // تشغيل التنظيف عند تحميل الصفحة
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', performErrorCleanup);
    } else {
        performErrorCleanup();
    }

    // تشغيل التنظيف كل 30 ثانية
    setInterval(performErrorCleanup, 30000);

    // تصدير الدوال للاستخدام العام
    window.ErrorCleanup = {
        cleanup: performErrorCleanup,
        fixMissingElements: fixMissingElements,
        shouldSuppressError: shouldSuppressError
    };

})();