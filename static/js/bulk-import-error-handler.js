/**
 * معالج أخطاء خاص بصفحة الاستيراد المجمع
 * Bulk Import Error Handler
 */

(function() {
    'use strict';
    
    // معالج أخطاء عام لمنع أخطاء الوصول للعناصر المفقودة
    window.addEventListener('error', function(event) {
        if (event.error && event.error.message) {
            const errorMessage = event.error.message;
            
            // معالجة أخطاء الوصول لخاصية style
            if (errorMessage.includes("Cannot read properties of null (reading 'style')")) {
                console.warn('BulkImportErrorHandler: تم منع خطأ الوصول لخاصية style لعنصر null');
                event.preventDefault();
                return true;
            }
            
            // معالجة أخطاء الوصول لخصائص أخرى
            if (errorMessage.includes("Cannot read properties of null") || 
                errorMessage.includes("Cannot read property") ||
                errorMessage.includes("is null")) {
                console.warn('BulkImportErrorHandler: تم منع خطأ الوصول لعنصر null:', errorMessage);
                event.preventDefault();
                return true;
            }
            
            // معالجة أخطاء jQuery
            if (errorMessage.includes("$ is not defined") || 
                errorMessage.includes("jQuery is not defined")) {
                console.error('BulkImportErrorHandler: jQuery غير محمل بشكل صحيح');
                return true;
            }
        }
        
        return false;
    });
    
    // معالج أخطاء غير المعالجة في Promise
    window.addEventListener('unhandledrejection', function(event) {
        console.warn('BulkImportErrorHandler: Promise rejection غير معالج:', event.reason);
        
        // منع ظهور الخطأ في الكونسول إذا كان متعلق بـ DOM
        if (event.reason && event.reason.message && 
            (event.reason.message.includes('null') || 
             event.reason.message.includes('undefined'))) {
            event.preventDefault();
        }
    });
    
    // دالة مساعدة للتحقق من وجود العنصر قبل الوصول إليه
    window.safeElementAccess = function(selector, callback, fallback) {
        try {
            const element = $(selector);
            if (element && element.length > 0 && callback) {
                return callback(element);
            } else if (fallback) {
                return fallback();
            }
        } catch (error) {
            console.warn(`BulkImportErrorHandler: خطأ في الوصول للعنصر ${selector}:`, error);
            if (fallback) {
                return fallback();
            }
        }
        return null;
    };
    
    // دالة مساعدة للتحقق من وجود دالة قبل استدعائها
    window.safeFunctionCall = function(func, args, context) {
        try {
            if (typeof func === 'function') {
                return func.apply(context || window, args || []);
            } else {
                console.warn('BulkImportErrorHandler: الدالة المطلوبة غير موجودة:', func);
            }
        } catch (error) {
            console.warn('BulkImportErrorHandler: خطأ في استدعاء الدالة:', error);
        }
        return null;
    };
    
    // دالة مساعدة للتحقق من وجود كائن قبل الوصول لخصائصه
    window.safeObjectAccess = function(obj, property, defaultValue) {
        try {
            if (obj && typeof obj === 'object' && property in obj) {
                return obj[property];
            }
        } catch (error) {
            console.warn('BulkImportErrorHandler: خطأ في الوصول لخاصية الكائن:', error);
        }
        return defaultValue || null;
    };
    
    // معالج خاص لأخطاء Bootstrap
    document.addEventListener('DOMContentLoaded', function() {
        // التحقق من وجود Bootstrap
        if (typeof bootstrap === 'undefined') {
            console.warn('BulkImportErrorHandler: Bootstrap غير محمل بشكل صحيح');
        }
        
        // معالج أخطاء الـ modals
        $(document).on('show.bs.modal', function(e) {
            try {
                const modal = e.target;
                if (!modal) {
                    console.warn('BulkImportErrorHandler: محاولة فتح modal غير موجود');
                    e.preventDefault();
                }
            } catch (error) {
                console.warn('BulkImportErrorHandler: خطأ في فتح modal:', error);
                e.preventDefault();
            }
        });
        
        // معالج أخطاء الـ collapse
        $(document).on('show.bs.collapse hide.bs.collapse', function(e) {
            try {
                const target = e.target;
                if (!target) {
                    console.warn('BulkImportErrorHandler: محاولة تبديل collapse غير موجود');
                    e.preventDefault();
                }
            } catch (error) {
                console.warn('BulkImportErrorHandler: خطأ في تبديل collapse:', error);
                e.preventDefault();
            }
        });
    });
    
})();