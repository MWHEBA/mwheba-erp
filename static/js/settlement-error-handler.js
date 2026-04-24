/**
 * Settlement Error Handler
 * معالج أخطاء نظام التسوية المالية
 */

(function() {
    'use strict';

    // معالج الأخطاء العام للتسوية المالية
    class SettlementErrorHandler {
        constructor() {
            this.init();
        }

        init() {
            this.setupGlobalErrorHandling();
            this.setupDOMErrorHandling();
            this.setupAjaxErrorHandling();
        }

        /**
         * إعداد معالجة الأخطاء العامة
         */
        setupGlobalErrorHandling() {
            window.addEventListener('error', (event) => {
                // تجاهل أخطاء معينة غير مهمة
                if (this.shouldIgnoreError(event.error)) {
                    event.preventDefault();
                    return;
                }

                // معالجة أخطاء innerHTML
                if (event.error && event.error.message && 
                    event.error.message.includes("Cannot read properties of null (reading 'innerHTML')")) {
                    console.warn('Settlement DOM Error (handled):', event.error.message);
                    this.handleDOMError(event);
                    event.preventDefault();
                    return;
                }

                // تسجيل الأخطاء الأخرى
                console.error('Settlement Error:', event.error);
            });

            // معالجة الأخطاء غير المعالجة في Promise
            window.addEventListener('unhandledrejection', (event) => {
                console.error('Settlement Promise Rejection:', event.reason);
                
                // منع إظهار الخطأ في Console إذا كان خطأ شبكة بسيط
                if (this.isNetworkError(event.reason)) {
                    event.preventDefault();
                }
            });
        }

        /**
         * إعداد معالجة أخطاء DOM
         */
        setupDOMErrorHandling() {
            // إضافة معالج للتحقق من وجود العناصر قبل الوصول إليها
            const originalQuerySelector = document.querySelector;
            const originalGetElementById = document.getElementById;

            document.querySelector = function(selector) {
                try {
                    return originalQuerySelector.call(this, selector);
                } catch (error) {
                    console.warn('Settlement DOM Query Error:', selector, error);
                    return null;
                }
            };

            document.getElementById = function(id) {
                try {
                    return originalGetElementById.call(this, id);
                } catch (error) {
                    console.warn('Settlement DOM GetById Error:', id, error);
                    return null;
                }
            };
        }

        /**
         * إعداد معالجة أخطاء AJAX
         */
        setupAjaxErrorHandling() {
            // معالجة أخطاء jQuery AJAX إذا كان متوفراً
            if (typeof $ !== 'undefined') {
                $(document).ajaxError((event, xhr, settings, error) => {
                    // تجاهل أخطاء الإلغاء
                    if (xhr.statusText === 'abort') {
                        return;
                    }

                    console.error('Settlement AJAX Error:', {
                        url: settings.url,
                        status: xhr.status,
                        error: error
                    });

                    // إظهار رسالة خطأ للمستخدم
                    this.showUserFriendlyError(xhr.status, error);
                });
            }
        }

        /**
         * التحقق من ما إذا كان يجب تجاهل الخطأ
         */
        shouldIgnoreError(error) {
            if (!error || !error.message) return false;

            const ignoredErrors = [
                'Script error',
                'Non-Error promise rejection captured',
                'ResizeObserver loop limit exceeded',
                'already been declared'
            ];

            return ignoredErrors.some(ignored => 
                error.message.includes(ignored)
            );
        }

        /**
         * معالجة أخطاء DOM
         */
        handleDOMError(event) {
            // محاولة إعادة تهيئة المكونات المفقودة
            setTimeout(() => {
                this.reinitializeSettlementComponents();
            }, 100);
        }

        /**
         * التحقق من ما إذا كان الخطأ خطأ شبكة
         */
        isNetworkError(error) {
            if (!error) return false;
            
            const networkErrors = [
                'NetworkError',
                'Failed to fetch',
                'ERR_NETWORK',
                'ERR_INTERNET_DISCONNECTED'
            ];

            return networkErrors.some(netError => 
                error.toString().includes(netError)
            );
        }

        /**
         * إظهار رسالة خطأ مفهومة للمستخدم
         */
        showUserFriendlyError(status, error) {
            let message = 'حدث خطأ غير متوقع';

            switch (status) {
                case 0:
                    message = 'تحقق من اتصال الإنترنت';
                    break;
                case 400:
                    message = 'البيانات المرسلة غير صحيحة';
                    break;
                case 401:
                    message = 'انتهت صلاحية الجلسة، يرجى تسجيل الدخول مرة أخرى';
                    break;
                case 403:
                    message = 'ليس لديك صلاحية لتنفيذ هذا الإجراء';
                    break;
                case 404:
                    message = 'الصفحة أو البيانات المطلوبة غير موجودة';
                    break;
                case 500:
                    message = 'خطأ في الخادم، يرجى المحاولة لاحقاً';
                    break;
                case 503:
                    message = 'الخدمة غير متاحة مؤقتاً';
                    break;
            }

            // إظهار الرسالة باستخدام settlementUI إذا كان متوفراً
            if (typeof toastr !== 'undefined') {
                if (typeof toastr !== 'undefined') { toastr.error(message, 'خطأ'); };
            } else {
                // استخدام alert كبديل
                alert(`خطأ: ${message}`);
            }
        }

        /**
         * إعادة تهيئة مكونات التسوية
         */
        reinitializeSettlementComponents() {
            try {
                // إعادة تهيئة settlementUI إذا لم يكن موجوداً
                if (!window.settlementUI && window.FinancialSettlementUI) {
                    if (document.querySelector('.settlement-form, [data-page="settlement"]')) {
                        window.settlementUI = new window.FinancialSettlementUI();
                    }
                }

                // إعادة تهيئة Select2 إذا كان متوفراً
                if (typeof $ !== 'undefined' && $.fn.select2) {
                    $('select:not(.select2-hidden-accessible)').each(function() {
                        if ($(this).hasClass('select')) {
                            $(this).select2({
                                placeholder: $(this).attr('placeholder') || 'اختر...',
                                allowClear: true,
                                width: '100%'
                            });
                        }
                    });
                }

                // إعادة تهيئة tooltips
                if (typeof $ !== 'undefined' && $.fn.tooltip) {
                    $('[data-bs-toggle="tooltip"]').tooltip();
                }

            } catch (error) {
                console.warn('Error during component reinitialization:', error);
            }
        }

        /**
         * دالة مساعدة للتحقق من وجود عنصر قبل الوصول إليه
         */
        static safeGetElement(selector, context = document) {
            try {
                const element = context.querySelector(selector);
                return element;
            } catch (error) {
                console.warn('Safe element access failed:', selector, error);
                return null;
            }
        }

        /**
         * دالة مساعدة لتعديل innerHTML بأمان
         */
        static safeSetInnerHTML(element, html) {
            if (!element) {
                console.warn('Cannot set innerHTML: element is null');
                return false;
            }

            try {
                element.innerHTML = html;
                return true;
            } catch (error) {
                console.warn('Safe innerHTML set failed:', error);
                return false;
            }
        }
    }

    // تهيئة معالج الأخطاء عند تحميل DOM
    document.addEventListener('DOMContentLoaded', function() {
        window.settlementErrorHandler = new SettlementErrorHandler();
        
        // تصدير الدوال المساعدة للاستخدام العام
        window.safeGetElement = SettlementErrorHandler.safeGetElement;
        window.safeSetInnerHTML = SettlementErrorHandler.safeSetInnerHTML;
    });

    // تصدير الكلاس للاستخدام العام
    window.SettlementErrorHandler = SettlementErrorHandler;

})();