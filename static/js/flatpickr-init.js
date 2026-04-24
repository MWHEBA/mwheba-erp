/**
 * Flatpickr Initialization for Corporate ERP
 * تهيئة تلقائية لجميع حقول التاريخ في النظام
 */

(function() {
    'use strict';

    // الإعدادات الافتراضية العربية مع أرقام إنجليزية
    const defaultConfig = {
        locale: {
            ...flatpickr.l10ns.ar,
            weekdays: {
                shorthand: ['أحد', 'اثنين', 'ثلاثاء', 'أربعاء', 'خميس', 'جمعة', 'سبت'],
                longhand: ['الأحد', 'الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت']
            },
            // إزالة تحويل الأرقام للعربية
            amPM: ['ص', 'م'],
            rangeSeparator: ' إلى ',
            scrollTitle: 'قم بالتمرير للزيادة',
            toggleTitle: 'اضغط للتبديل',
            firstDayOfWeek: 6  // السبت أول يوم
        },
        dateFormat: "Y-m-d",
        altInput: true,
        altFormat: "d/m/Y",
        allowInput: true,
        disableMobile: true,  // على الموبايل: استخدام native date picker
        position: "auto right",
        // تعطيل تحويل الأرقام للعربية
        formatDate: function(date, format) {
            return flatpickr.formatDate(date, format);
        },
        onReady: function(selectedDates, dateStr, instance) {
            // التحقق من وجود calendarContainer
            if (!instance.calendarContainer) return;
            
            // إضافة class للـ RTL
            instance.calendarContainer.classList.add('flatpickr-rtl');
            
            // إضافة زر "اليوم"
            addTodayButton(instance);
        }
    };

    /**
     * إضافة زر "اليوم"
     */
    function addTodayButton(instance) {
        if (!instance.calendarContainer) return;
        
        const todayBtn = document.createElement('button');
        todayBtn.type = 'button';
        todayBtn.className = 'btn-today';
        todayBtn.innerHTML = 'اليوم <i class="fas fa-calendar-day ms-1"></i>';
        todayBtn.onclick = function() {
            instance.setDate(new Date(), true);
            instance.close();
        };
        instance.calendarContainer.appendChild(todayBtn);
    }

    /**
     * تهيئة تلقائية لجميع حقول التاريخ
     */
    function initializeDatePickers() {
        
        // 1. حقول التاريخ العادية (النظام الجديد)
        const datePickers = document.querySelectorAll('input[data-date-picker]');
        datePickers.forEach(function(input) {
            if (input._flatpickr) return; // تجنب التهيئة المكررة
            
            const customConfig = {};
            
            // قراءة الإعدادات من data attributes
            if (input.dataset.dateConfig) {
                try {
                    Object.assign(customConfig, JSON.parse(input.dataset.dateConfig));
                } catch (e) {
                    console.error('خطأ في تحليل date-config:', e);
                }
            }
            
            // إعدادات خاصة بالحقل
            if (input.dataset.minDate) customConfig.minDate = input.dataset.minDate;
            if (input.dataset.maxDate) customConfig.maxDate = input.dataset.maxDate;
            if (input.dataset.allowClear) customConfig.allowClear = true;
            
            flatpickr(input, { ...defaultConfig, ...customConfig });
        });

        // 2. حقول التاريخ والوقت
        document.querySelectorAll('input[data-datetime-picker]').forEach(function(input) {
            if (input._flatpickr) return;
            
            const customConfig = {
                enableTime: true,
                time_24hr: true,
                altFormat: "d/m/Y - H:i"
            };
            
            if (input.dataset.dateConfig) {
                try {
                    Object.assign(customConfig, JSON.parse(input.dataset.dateConfig));
                } catch (e) {
                    console.error('خطأ في تحليل date-config:', e);
                }
            }
            
            flatpickr(input, { ...defaultConfig, ...customConfig });
        });

        // 3. حقول نطاق التاريخ (من - إلى)
        document.querySelectorAll('input[data-date-range]').forEach(function(input) {
            if (input._flatpickr) return;
            
            const customConfig = {
                mode: "range"
            };
            
            if (input.dataset.dateConfig) {
                try {
                    Object.assign(customConfig, JSON.parse(input.dataset.dateConfig));
                } catch (e) {
                    console.error('خطأ في تحليل date-config:', e);
                }
            }
            
            flatpickr(input, { ...defaultConfig, ...customConfig });
        });

        // 4. حقول اختيار الشهر (Month Picker)
        document.querySelectorAll('input[data-month-picker]').forEach(function(input) {
            if (input._flatpickr) return;
            
            const monthConfig = {
                ...defaultConfig,
                dateFormat: "Y-m",
                altFormat: "F Y",  // عرض "يناير 2025"
                plugins: [
                    new monthSelectPlugin({
                        shorthand: true,
                        dateFormat: "Y-m",
                        altFormat: "F Y"
                    })
                ],
                onReady: function(selectedDates, dateStr, instance) {
                    // التحقق من وجود calendarContainer
                    if (!instance.calendarContainer) return;
                    
                    instance.calendarContainer.classList.add('flatpickr-rtl');
                    instance.calendarContainer.classList.add('flatpickr-monthSelect');
                    addCurrentMonthButton(instance);
                }
            };
            
            if (input.dataset.dateConfig) {
                try {
                    Object.assign(monthConfig, JSON.parse(input.dataset.dateConfig));
                } catch (e) {
                    console.error('خطأ في تحليل date-config:', e);
                }
            }
            
            flatpickr(input, monthConfig);
        });

        // 5. حقول التاريخ القديمة (class="datepicker") - للتوافق مع النظام القديم
        const oldDatePickers = document.querySelectorAll('input.datepicker:not([data-date-picker]):not([data-datetime-picker]):not([data-date-range]):not([data-month-picker])');
        oldDatePickers.forEach(function(input) {
            if (input._flatpickr) return; // تجنب التهيئة المكررة
            
            const customConfig = {
                wrap: false  // عدم استخدام wrap mode
            };
            
            // قراءة الإعدادات من data attributes القديمة
            if (input.dataset.format) {
                // تحويل التنسيق القديم للجديد
                let format = input.dataset.format;
                format = format.replace(/YYYY/g, 'Y').replace(/MM/g, 'm').replace(/DD/g, 'd').replace(/HH/g, 'H').replace(/mm/g, 'i');
                customConfig.dateFormat = format;
                
                // إذا كان التنسيق يحتوي على وقت
                if (format.includes('H') || format.includes('i')) {
                    customConfig.enableTime = true;
                    customConfig.time_24hr = true;
                    customConfig.altFormat = "d/m/Y - H:i";
                } else {
                    customConfig.altFormat = "d/m/Y";
                }
            }
            
            if (input.dataset.minDate) customConfig.minDate = input.dataset.minDate;
            if (input.dataset.maxDate) customConfig.maxDate = input.dataset.maxDate;
            
            flatpickr(input, { ...defaultConfig, ...customConfig });
        });

        // 6. استبدال حقول type="date" و type="datetime-local" من Django widgets
        const nativeDateInputs = document.querySelectorAll('input[type="date"]:not(.flatpickr-input), input[type="datetime-local"]:not(.flatpickr-input)');
        
        if (nativeDateInputs.length > 0) {
            nativeDateInputs.forEach(function(input, index) {
            });
        }
        
        nativeDateInputs.forEach(function(input) {
            if (input._flatpickr || input.classList.contains('flatpickr-input')) {
                return; // تجنب التهيئة المكررة
            }
            
            const customConfig = {};
            const originalType = input.type;
            
            // إذا كان datetime-local
            if (originalType === 'datetime-local') {
                customConfig.enableTime = true;
                customConfig.time_24hr = true;
                customConfig.altFormat = "d/m/Y - H:i";
                customConfig.dateFormat = "Y-m-d H:i";
            }
            
            // تغيير type لمنع datepicker الأصلي من المتصفح
            input.type = 'text';
            
            // إضافة علامة لمنع إعادة التحويل
            input.dataset.flatpickrInitialized = 'true';
            input.setAttribute('data-original-type', originalType);
            
            const identifier = input.id || input.name || `حقل رقم ${Array.from(nativeDateInputs).indexOf(input) + 1}`;
            
            const instance = flatpickr(input, { ...defaultConfig, ...customConfig });
            
            // حماية من إعادة تغيير type
            Object.defineProperty(input, 'type', {
                get: function() { return 'text'; },
                set: function(value) {
                    console.warn('⚠️ محاولة تغيير type - تم منعها للحقل:', identifier);
                    // لا نفعل شيء - نمنع التغيير
                }
            });
        });
        
    }

    /**
     * إضافة زر "الشهر الحالي"
     */
    function addCurrentMonthButton(instance) {
        if (!instance.calendarContainer) return;
        
        const currentMonthBtn = document.createElement('button');
        currentMonthBtn.type = 'button';
        currentMonthBtn.className = 'btn-today';
        currentMonthBtn.innerHTML = 'الشهر الحالي <i class="fas fa-calendar-alt ms-1"></i>';
        currentMonthBtn.onclick = function() {
            const now = new Date();
            instance.setDate(new Date(now.getFullYear(), now.getMonth(), 1), true);
            instance.close();
        };
        instance.calendarContainer.appendChild(currentMonthBtn);
    }

    /**
     * API عامة للاستخدام اليدوي
     */
    window.MWHEBADatePicker = {
        // إنشاء date picker يدوياً
        init: function(selector, customConfig = {}) {
            return flatpickr(selector, { ...defaultConfig, ...customConfig });
        },

        // الإعدادات الافتراضية
        getDefaultConfig: function() {
            return { ...defaultConfig };
        },

        // إعادة تهيئة جميع الحقول
        reinitialize: function() {
            initializeDatePickers();
        }
    };

    // علامة لمنع التهيئة المتعددة
    let isInitialized = false;
    
    // دالة wrapper للتهيئة مع حماية من التكرار
    function safeInitialize() {
        if (isInitialized) {
            return;
        }
        isInitialized = true;
        initializeDatePickers();
        
        // السماح بإعادة التهيئة بعد 500ms (للمحتوى الديناميكي)
        setTimeout(() => { isInitialized = false; }, 500);
    }

    // تهيئة تلقائية عند تحميل الصفحة
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', safeInitialize);
    } else {
        safeInitialize();
    }

    // إعادة التهيئة عند تحميل محتوى ديناميكي (AJAX)
    document.addEventListener('contentLoaded', function() {
        // تأخير بسيط للسماح للمحتوى بالتحميل الكامل
        setTimeout(initializeDatePickers, 100);
    });

    // مراقبة محاولات إعادة تحويل الحقول لـ type="date"
    const observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            if (mutation.type === 'attributes' && mutation.attributeName === 'type') {
                const input = mutation.target;
                if (input.dataset.flatpickrInitialized === 'true' && input.type !== 'text') {
                    console.warn('🚫 محاولة إعادة تحويل الحقل - تم منعها:', input.id || input.name, 'من', input.type, 'إلى text');
                    console.trace('Stack trace للمحاولة:');
                    input.type = 'text';
                    // إعادة تهيئة Flatpickr إذا تم تدميره
                    if (!input._flatpickr) {
                        const originalType = input.getAttribute('data-original-type');
                        const customConfig = {};
                        if (originalType === 'datetime-local') {
                            customConfig.enableTime = true;
                            customConfig.time_24hr = true;
                            customConfig.altFormat = "d/m/Y - H:i";
                            customConfig.dateFormat = "Y-m-d H:i";
                        }
                        flatpickr(input, { ...defaultConfig, ...customConfig });
                    }
                }
            }
        });
    });

    // مراقبة جميع حقول الإدخال في الصفحة
    setTimeout(function() {
        document.querySelectorAll('input[data-flatpickr-initialized="true"]').forEach(function(input) {
            observer.observe(input, {
                attributes: true,
                attributeFilter: ['type']
            });
        });
    }, 1000);

    // منع jQuery datepicker من الشغل على حقول Flatpickr
    if (typeof jQuery !== 'undefined' && jQuery.fn.datepicker) {
        const originalDatepicker = jQuery.fn.datepicker;
        jQuery.fn.datepicker = function() {
            // فحص إذا كان الحقل مهيأ بـ Flatpickr
            const hasFlatpickr = this.filter(function() {
                return this._flatpickr || this.dataset.flatpickrInitialized === 'true';
            }).length > 0;
            
            if (hasFlatpickr) {
                console.warn('🚫 محاولة تهيئة jQuery datepicker على حقل Flatpickr - تم منعها');
                return this; // إرجاع jQuery object بدون تهيئة
            }
            
            // السماح بالتهيئة للحقول الأخرى
            return originalDatepicker.apply(this, arguments);
        };
    }

})();
