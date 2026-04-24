/**
 * Select2 Error Handler
 * معالج أخطاء Select2
 */

(function() {
    'use strict';

    // دالة آمنة لتهيئة Select2
    window.safeInitSelect2 = function(selector, options = {}) {
        try {
            // التحقق من وجود jQuery و Select2
            if (typeof $ === 'undefined') {
                console.warn('jQuery not loaded, cannot initialize Select2');
                return null;
            }

            if (!$.fn.select2) {
                console.warn('Select2 not loaded, cannot initialize');
                return null;
            }

            const $element = $(selector);
            if (!$element.length) {
                console.warn(`Select2: Element "${selector}" not found`);
                return null;
            }

            // التحقق من أن Select2 لم يتم تهيئته مسبقاً
            if ($element.hasClass('select2-hidden-accessible')) {
                $element.select2('destroy');
            }

            // الإعدادات الافتراضية
            const defaultOptions = {
                theme: 'bootstrap-5',
                dir: 'rtl',
                language: 'ar',
                allowClear: true,
                placeholder: 'اختر...',
                width: '100%',
                dropdownAutoWidth: true,
                escapeMarkup: function(markup) {
                    return markup;
                }
            };

            // دمج الإعدادات
            const finalOptions = $.extend(true, {}, defaultOptions, options);

            // تهيئة Select2
            const select2Instance = $element.select2(finalOptions);

            return select2Instance;

        } catch (error) {
            console.error(`Error initializing Select2 for "${selector}":`, error);
            
            // عرض رسالة للمستخدم
            if (typeof window.showAlert === 'function') {
                window.showAlert('حدث خطأ في تهيئة قائمة الاختيار', 'warning', 3000);
            }
            
            return null;
        }
    };

    // دالة آمنة لتدمير Select2
    window.safeDestroySelect2 = function(selector) {
        try {
            if (typeof $ === 'undefined' || !$.fn.select2) {
                return false;
            }

            const $element = $(selector);
            if (!$element.length) {
                return false;
            }

            if ($element.hasClass('select2-hidden-accessible')) {
                $element.select2('destroy');
                return true;
            }

            return false;
        } catch (error) {
            console.error(`Error destroying Select2 for "${selector}":`, error);
            return false;
        }
    };

    // دالة آمنة لتحديث خيارات Select2
    window.safeUpdateSelect2Options = function(selector, newOptions) {
        try {
            if (typeof $ === 'undefined' || !$.fn.select2) {
                return false;
            }

            const $element = $(selector);
            if (!$element.length) {
                return false;
            }

            // إضافة الخيارات الجديدة
            $element.empty();
            if (newOptions && Array.isArray(newOptions)) {
                newOptions.forEach(option => {
                    const optionElement = new Option(option.text, option.id, false, false);
                    if (option.data) {
                        $(optionElement).data(option.data);
                    }
                    $element.append(optionElement);
                });
            }

            // تحديث Select2
            if ($element.hasClass('select2-hidden-accessible')) {
                $element.trigger('change');
            }

            return true;

        } catch (error) {
            console.error(`Error updating Select2 options for "${selector}":`, error);
            return false;
        }
    };

    // دالة آمنة لتعيين قيمة Select2
    window.safeSetSelect2Value = function(selector, value) {
        try {
            if (typeof $ === 'undefined' || !$.fn.select2) {
                return false;
            }

            const $element = $(selector);
            if (!$element.length) {
                return false;
            }

            $element.val(value);
            
            if ($element.hasClass('select2-hidden-accessible')) {
                $element.trigger('change');
            }

            return true;

        } catch (error) {
            console.error(`Error setting Select2 value for "${selector}":`, error);
            return false;
        }
    };

    // معالج أخطاء Select2 العام
    function handleSelect2Errors() {
        if (typeof $ === 'undefined') {
            return;
        }

        // معالج أخطاء Select2
        $(document).on('select2:error', function(e) {
            console.warn('Select2 error:', e.params);
            
            if (typeof window.showAlert === 'function') {
                window.showAlert('حدث خطأ في قائمة الاختيار', 'warning', 3000);
            }
        });

        // معالج أخطاء AJAX في Select2
        $(document).on('select2:select', function(e) {
            try {
                const data = e.params.data;
            } catch (error) {
                console.error('Error in Select2 selection handler:', error);
            }
        });

        // معالج إغلاق Select2
        $(document).on('select2:close', function(e) {
            try {
                // إزالة أي dropdown مفتوح
                $('.select2-dropdown').remove();
            } catch (error) {
                console.error('Error in Select2 close handler:', error);
            }
        });
    }

    // تهيئة معالج أخطاء Select2
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            // انتظار تحميل jQuery
            function waitForJQuery() {
                if (typeof $ !== 'undefined') {
                    handleSelect2Errors();
                } else {
                    setTimeout(waitForJQuery, 100);
                }
            }
            waitForJQuery();
        });
    } else {
        if (typeof $ !== 'undefined') {
            handleSelect2Errors();
        } else {
            // انتظار تحميل jQuery
            function waitForJQuery() {
                if (typeof $ !== 'undefined') {
                    handleSelect2Errors();
                } else {
                    setTimeout(waitForJQuery, 100);
                }
            }
            waitForJQuery();
        }
    }


})();