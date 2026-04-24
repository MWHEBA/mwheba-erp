/**
 * JSON Error Suppression Utility
 * أداة منع أخطاء JSON
 */

(function() {
    'use strict';

    // قائمة القيم المعروفة التي ليست JSON ولكن Bootstrap يحاول parse-ها
    const knownNonJsonValues = [
        'tab', 'pill', 'modal', 'collapse', 'dropdown', 'tooltip', 'popover',
        '#academic', '#financial', '#activities', '#services', '#enrolled-activities',
        'show', 'hide', 'toggle', 'fade', 'active', 'static',
        // النصوص العربية الشائعة في tooltips
        'عرض الصلاحيات', 'تعيين دور', 'تعديل المستخدم', 'حذف', 'تعديل', 'عرض',
        'إضافة', 'حفظ', 'إلغاء', 'تأكيد', 'بحث', 'فلترة', 'تصدير', 'طباعة',
        'عرض الصلاح', 'تعديل الصلاح', 'حذف الصلاح', 'إضافة صلاح', 'صلاحيات المستخدم'
    ];

    // حفظ المرجع الأصلي لـ JSON.parse
    const originalParse = JSON.parse;
    
    // Override JSON.parse globally قبل تحميل Bootstrap
    JSON.parse = function(text, reviver) {
        try {
            return originalParse.call(this, text, reviver);
        } catch (error) {
            // التحقق من القيم المعروفة التي ليست JSON
            const textStr = String(text).trim();
            
            // فحص النصوص العربية والقيم المعروفة
            if (knownNonJsonValues.includes(textStr) || 
                textStr.startsWith('#') || 
                textStr.startsWith('static') ||
                textStr.includes('/static/') ||
                /^[\u0600-\u06FF\s\u060C\u061B\u061F\u0640\u064B-\u065F\u0670\u06D6-\u06ED]+$/.test(textStr)) { // النصوص العربية مع علامات الترقيم
                // هذه قيم Bootstrap عادية أو نصوص عربية، إرجاع النص كما هو بصمت
                return textStr;
            }
            
            // للقيم الأخرى، تسجيل تحذير صامت فقط
            if (textStr.length > 0 && textStr !== 'undefined' && textStr !== 'null') {
                // تسجيل صامت جداً - لا يظهر في console
                // console.warn('JSON parsing warning:', error.message);
            }
            
            // إرجاع القيمة الأصلية إذا لم تكن JSON
            return textStr || null;
        }
    };

    // منع أخطاء localStorage بشكل كامل وصامت
    (function() {
        try {
            // إنشاء localStorage وهمي صامت دائماً
            const silentStorage = {
                getItem: function() { return null; },
                setItem: function() { },
                removeItem: function() { },
                clear: function() { },
                key: function() { return null; },
                length: 0
            };
            
            // استبدال localStorage بالنسخة الصامتة
            Object.defineProperty(window, 'localStorage', {
                value: silentStorage,
                writable: false,
                configurable: false
            });
            
            // منع أي محاولات للوصول لـ sessionStorage أيضاً
            Object.defineProperty(window, 'sessionStorage', {
                value: silentStorage,
                writable: false,
                configurable: false
            });
            
        } catch (e) {
            // تجاهل أي أخطاء في تهيئة storage
        }
    })();

    // منع أخطاء Bootstrap data attributes parsing
    const originalGetDataAttributes = function() {
        if (typeof bootstrap !== 'undefined' && bootstrap.Util && bootstrap.Util.getDataAttributes) {
            const originalMethod = bootstrap.Util.getDataAttributes;
            bootstrap.Util.getDataAttributes = function(element) {
                try {
                    return originalMethod.call(this, element);
                } catch (error) {
                    // إرجاع كائن فارغ بدلاً من رمي خطأ
                    return {};
                }
            };
        }
    };

    // تطبيق التحسين عند تحميل Bootstrap
    if (typeof bootstrap !== 'undefined') {
        originalGetDataAttributes();
    } else {
        // انتظار تحميل Bootstrap
        document.addEventListener('DOMContentLoaded', function() {
            setTimeout(originalGetDataAttributes, 100);
        });
    }

    // منع أخطاء Bootstrap tooltip/popover parsing
    const patchBootstrapComponents = function() {
        if (typeof bootstrap !== 'undefined') {
            // Patch Tooltip
            if (bootstrap.Tooltip) {
                const originalTooltipConstructor = bootstrap.Tooltip;
                bootstrap.Tooltip = function(element, config) {
                    try {
                        return new originalTooltipConstructor(element, config);
                    } catch (error) {
                        console.warn('Tooltip initialization warning:', error.message);
                        // إرجاع كائن وهمي لتجنب كسر الكود
                        return {
                            show: function() {},
                            hide: function() {},
                            dispose: function() {},
                            enable: function() {},
                            disable: function() {}
                        };
                    }
                };
                // نسخ الخصائص الثابتة
                Object.setPrototypeOf(bootstrap.Tooltip, originalTooltipConstructor);
                Object.assign(bootstrap.Tooltip, originalTooltipConstructor);
            }

            // Patch Popover
            if (bootstrap.Popover) {
                const originalPopoverConstructor = bootstrap.Popover;
                bootstrap.Popover = function(element, config) {
                    try {
                        return new originalPopoverConstructor(element, config);
                    } catch (error) {
                        console.warn('Popover initialization warning:', error.message);
                        // إرجاع كائن وهمي لتجنب كسر الكود
                        return {
                            show: function() {},
                            hide: function() {},
                            dispose: function() {},
                            enable: function() {},
                            disable: function() {}
                        };
                    }
                };
                // نسخ الخصائص الثابتة
                Object.setPrototypeOf(bootstrap.Popover, originalPopoverConstructor);
                Object.assign(bootstrap.Popover, originalPopoverConstructor);
            }
        }
    };

    // تطبيق التحسينات
    if (typeof bootstrap !== 'undefined') {
        patchBootstrapComponents();
    } else {
        document.addEventListener('DOMContentLoaded', function() {
            setTimeout(patchBootstrapComponents, 200);
        });
    }

    // منع أخطاء fetch JSON parsing
    const originalFetch = window.fetch;
    window.fetch = async function(...args) {
        try {
            const response = await originalFetch.apply(this, args);
            
            // إنشاء نسخة محسنة من json()
            const originalJson = response.json;
            response.json = async function() {
                try {
                    const text = await response.clone().text();
                    
                    // التحقق من نوع المحتوى
                    const contentType = response.headers.get('content-type');
                    if (!contentType || !contentType.includes('application/json')) {
                        console.warn('Response is not JSON:', contentType);
                        
                        // إذا كانت الاستجابة HTML، فهناك خطأ في الخادم
                        if (text.includes('<!DOCTYPE') || text.includes('<html')) {
                            throw new Error('Server returned HTML instead of JSON - possible server error');
                        }
                        
                        return { error: 'Invalid response format', content: text };
                    }
                    
                    return await originalJson.call(this);
                } catch (error) {
                    console.warn('Response JSON parsing warning:', error.message);
                    
                    // إرسال حدث خطأ مخصص
                    const errorEvent = new CustomEvent('paymentError', {
                        detail: { 
                            type: 'response_parsing_error', 
                            message: 'خطأ في تحليل استجابة الخادم',
                            originalError: error.message
                        }
                    });
                    document.dispatchEvent(errorEvent);
                    
                    return { error: 'Response parsing failed', details: error.message };
                }
            };
            
            return response;
        } catch (networkError) {
            // معالجة أخطاء الشبكة (مثل ERR_CONNECTION_REFUSED)
            if (networkError.message.includes('Failed to fetch') || 
                networkError.message.includes('ERR_CONNECTION_REFUSED')) {
                
                // تسجيل تحذير بدلاً من خطأ للطلبات غير الحرجة
                const url = args[0];
                if (typeof url === 'string' && (url.includes('/api/notifications/') || url.includes('/notifications/'))) {
                    // تسجيل صامت تماماً للإشعارات - لا نريد إزعاج console
                    // console.warn('تحذير: لا يمكن الوصول لخدمة الإشعارات، سيتم المحاولة لاحقاً');
                    
                    // إرجاع استجابة وهمية للإشعارات
                    return {
                        ok: false,
                        status: 503,
                        statusText: 'Service Unavailable',
                        json: async () => ({ success: false, message: 'الخدمة غير متاحة مؤقتاً', count: 0 }),
                        text: async () => '{"success": false, "message": "الخدمة غير متاحة مؤقتاً", "count": 0}'
                    };
                }
            }
            
            // إعادة رمي الخطأ للطلبات الأخرى
            throw networkError;
        }
    };

})();