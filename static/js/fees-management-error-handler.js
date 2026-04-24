/**
 * Fees Management Error Handler
 * معالج أخطاء مكون إدارة الرسوم
 */

(function() {
    'use strict';

    // معالج أخطاء مكون إدارة الرسوم
    class FeesManagementErrorHandler {
        constructor() {
            this.init();
        }

        init() {
            this.setupErrorHandling();
            this.setupSafeElementAccess();
        }

        /**
         * إعداد معالجة الأخطاء
         */
        setupErrorHandling() {
            // معالجة أخطاء innerHTML في مكون الرسوم
            const originalInnerHTML = Object.getOwnPropertyDescriptor(Element.prototype, 'innerHTML');
            
            Object.defineProperty(Element.prototype, 'innerHTML', {
                get: originalInnerHTML.get,
                set: function(value) {
                    try {
                        return originalInnerHTML.set.call(this, value);
                    } catch (error) {
                        console.warn('Safe innerHTML set failed for fees component:', error);
                        return false;
                    }
                }
            });
        }

        /**
         * إعداد الوصول الآمن للعناصر
         */
        setupSafeElementAccess() {
            // دالة آمنة للحصول على العنصر
            window.safeGetElementForFees = function(selector, context = document) {
                try {
                    const element = context.querySelector(selector);
                    if (!element) {
                        console.warn(`Fees component element not found: ${selector}`);
                    }
                    return element;
                } catch (error) {
                    console.error('Error accessing fees element:', selector, error);
                    return null;
                }
            };

            // دالة آمنة لتعديل innerHTML
            window.safeSetInnerHTMLForFees = function(element, html) {
                if (!element) {
                    console.warn('Cannot set innerHTML: fees element is null');
                    return false;
                }

                try {
                    element.innerHTML = html || '';
                    return true;
                } catch (error) {
                    console.warn('Safe innerHTML set failed for fees element:', error);
                    return false;
                }
            };

            // دالة آمنة لتعديل textContent
            window.safeSetTextContentForFees = function(element, text) {
                if (!element) {
                    console.warn('Cannot set textContent: fees element is null');
                    return false;
                }

                try {
                    element.textContent = text || '';
                    return true;
                } catch (error) {
                    console.warn('Safe textContent set failed for fees element:', error);
                    return false;
                }
            };
        }

        /**
         * معالجة أخطاء AJAX في مكون الرسوم
         */
        static handleAjaxError(error, context = 'fees operation') {
            console.error(`Fees management AJAX error in ${context}:`, error);
            
            let message = 'حدث خطأ غير متوقع';
            
            if (error.name === 'TypeError' && error.message.includes('fetch')) {
                message = 'تحقق من اتصال الإنترنت';
            } else if (error.message.includes('404')) {
                message = 'الخدمة المطلوبة غير متاحة';
            } else if (error.message.includes('500')) {
                message = 'خطأ في الخادم، يرجى المحاولة لاحقاً';
            }

            // إظهار رسالة خطأ للمستخدم
            if (typeof showAlert === 'function') {
                showAlert(message, 'danger');
            } else {
                alert(`خطأ: ${message}`);
            }
        }

        /**
         * معالجة أخطاء النماذج
         */
        static handleFormError(form, error) {
            console.error('Fees form error:', error);
            
            // إعادة تفعيل زر الإرسال
            const submitBtn = form.querySelector('button[type="submit"]');
            if (submitBtn) {
                submitBtn.disabled = false;
                
                // استعادة النص الأصلي إذا كان متوفراً
                const originalText = submitBtn.getAttribute('data-original-text');
                if (originalText) {
                    submitBtn.innerHTML = originalText;
                } else {
                    submitBtn.innerHTML = submitBtn.innerHTML.replace(
                        /<i class="fas fa-spinner[^>]*><\/i>\s*/,
                        ''
                    );
                }
            }

            // إظهار رسالة خطأ
            this.handleAjaxError(error, 'form submission');
        }

        /**
         * تحسين أداء النماذج
         */
        static enhanceFormSubmission(form) {
            if (!form) return;

            form.addEventListener('submit', function(e) {
                let submitBtn = this.querySelector('button[type="submit"]');
                
                // البحث عن الزر خارج النموذج إذا لم يوجد داخله
                if (!submitBtn) {
                    const formId = this.id;
                    if (formId) {
                        submitBtn = document.querySelector(`button[type="submit"][form="${formId}"]`);
                    }
                }
                
                // البحث في modal-footer إذا كان النموذج داخل modal
                if (!submitBtn) {
                    const modal = this.closest('.modal');
                    if (modal) {
                        submitBtn = modal.querySelector('.modal-footer button[type="submit"]');
                    }
                }
                
                if (submitBtn) {
                    // حفظ النص الأصلي
                    submitBtn.setAttribute('data-original-text', submitBtn.innerHTML);
                }
            });
        }
    }

    // دوال مساعدة عامة لمكون الرسوم
    window.FeesManagementUtils = {
        /**
         * العثور على زر الإرسال بأمان
         */
        safeFindSubmitButton: function(form) {
            if (!form) return null;

            // البحث داخل النموذج أولاً
            let submitBtn = form.querySelector('button[type="submit"]');
            
            // البحث خارج النموذج باستخدام form attribute
            if (!submitBtn && form.id) {
                submitBtn = document.querySelector(`button[type="submit"][form="${form.id}"]`);
            }
            
            // البحث في modal-footer إذا كان النموذج داخل modal
            if (!submitBtn) {
                const modal = form.closest('.modal');
                if (modal) {
                    submitBtn = modal.querySelector('.modal-footer button[type="submit"]');
                }
            }
            
            // البحث في أي مكان في الصفحة كحل أخير
            if (!submitBtn) {
                const allSubmitButtons = document.querySelectorAll('button[type="submit"]');
                for (const btn of allSubmitButtons) {
                    if (btn.form === form || btn.getAttribute('form') === form.id) {
                        submitBtn = btn;
                        break;
                    }
                }
            }
            
            return submitBtn;
        },

        /**
         * تحديث عنصر بأمان
         */
        safeUpdateElement: function(selector, content, isHTML = false) {
            const element = document.querySelector(selector);
            if (!element) {
                console.warn(`Element not found for update: ${selector}`);
                return false;
            }

            try {
                if (isHTML) {
                    element.innerHTML = content || '';
                } else {
                    element.textContent = content || '';
                }
                return true;
            } catch (error) {
                console.warn(`Failed to update element ${selector}:`, error);
                return false;
            }
        },

        /**
         * إظهار/إخفاء عنصر بأمان
         */
        safeToggleElement: function(selector, show = true) {
            const element = document.querySelector(selector);
            if (!element) {
                console.warn(`Element not found for toggle: ${selector}`);
                return false;
            }

            try {
                element.style.display = show ? 'block' : 'none';
                return true;
            } catch (error) {
                console.warn(`Failed to toggle element ${selector}:`, error);
                return false;
            }
        },

        /**
         * تحديث قائمة منسدلة بأمان
         */
        safeUpdateSelect: function(selector, options, placeholder = 'اختر...') {
            const select = document.querySelector(selector);
            if (!select) {
                console.warn(`Select element not found: ${selector}`);
                return false;
            }

            try {
                // مسح الخيارات الحالية
                select.innerHTML = `<option value="">${placeholder}</option>`;

                // إضافة الخيارات الجديدة
                if (Array.isArray(options)) {
                    options.forEach(option => {
                        if (option && (option.value !== undefined || option.text)) {
                            const optionElement = document.createElement('option');
                            optionElement.value = option.value || '';
                            optionElement.textContent = option.text || option.label || '';
                            if (option.title) {
                                optionElement.title = option.title;
                            }
                            select.appendChild(optionElement);
                        }
                    });
                }

                return true;
            } catch (error) {
                console.warn(`Failed to update select ${selector}:`, error);
                return false;
            }
        },

        /**
         * معالجة استجابة AJAX بأمان
         */
        safeHandleAjaxResponse: function(response, successCallback, errorCallback) {
            try {
                if (response && response.success) {
                    if (typeof successCallback === 'function') {
                        successCallback(response);
                    }
                } else {
                    const errorMessage = response?.message || 'حدث خطأ غير معروف';
                    if (typeof errorCallback === 'function') {
                        errorCallback(errorMessage);
                    } else {
                        FeesManagementErrorHandler.handleAjaxError(
                            new Error(errorMessage), 
                            'AJAX response'
                        );
                    }
                }
            } catch (error) {
                console.error('Error handling AJAX response:', error);
                if (typeof errorCallback === 'function') {
                    errorCallback('خطأ في معالجة الاستجابة');
                }
            }
        }
    };

    // تهيئة معالج الأخطاء عند تحميل DOM
    document.addEventListener('DOMContentLoaded', function() {
        window.feesManagementErrorHandler = new FeesManagementErrorHandler();
        
        // تحسين جميع النماذج في الصفحة
        document.querySelectorAll('form').forEach(form => {
            FeesManagementErrorHandler.enhanceFormSubmission(form);
        });
    });

    // تصدير الكلاس للاستخدام العام
    window.FeesManagementErrorHandler = FeesManagementErrorHandler;

})();