/**
 * Flatpickr Initialization for MWHEBA ERP
 * تهيئة تلقائية لجميع حقول التاريخ في النظام
 */

(function() {
    'use strict';

    // الإعدادات الافتراضية العربية
    const defaultConfig = {
        locale: {
            ...flatpickr.l10ns.ar,
            weekdays: {
                shorthand: ['أحد', 'اثنين', 'ثلاثاء', 'أربعاء', 'خميس', 'جمعة', 'سبت'],
                longhand: ['الأحد', 'الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت']
            },
            firstDayOfWeek: 6  // السبت أول يوم
        },
        dateFormat: "Y-m-d",
        altInput: true,
        altFormat: "d/m/Y",
        allowInput: true,
        position: "auto right",
        onReady: function(selectedDates, dateStr, instance) {
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
        // 1. حقول التاريخ العادية
        document.querySelectorAll('input[data-date-picker]').forEach(function(input) {
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
    }

    /**
     * إضافة زر "الشهر الحالي"
     */
    function addCurrentMonthButton(instance) {
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

    // تهيئة تلقائية عند تحميل الصفحة
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initializeDatePickers);
    } else {
        initializeDatePickers();
    }

    // إعادة التهيئة عند تحميل محتوى ديناميكي (AJAX)
    document.addEventListener('contentLoaded', initializeDatePickers);

})();
