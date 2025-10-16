/**
 * event-bus.js - نظام مركزي لإدارة الأحداث وتحديث الحقول
 */

// تعريف كائن عام للمشروع إذا لم يكن موجودًا
window.PricingSystem = window.PricingSystem || {};

// تعريف وحدة ناقل الأحداث (Event Bus)
PricingSystem.EventBus = {
    // مستمعو الأحداث
    listeners: {},
    
    // مؤقت التأخير للتحديث المجمع
    debounceTimer: null,
    
    // قائمة الحقول التي تم تغييرها خلال دورة التحديث الحالية
    changedFields: new Set(),
    
    // قائمة الأحداث التي تم إطلاقها مؤخراً لمنع الحلقات اللانهائية
    recentEvents: {},
    
    // مدة التجاهل للأحداث المكررة (بالمللي ثانية)
    eventThrottleTime: 50,
    
    // تبعيات الحقول - تحدد أي الحقول تتأثر بتغيير حقل معين
    fieldDependencies: {},
    
    // قائمة الحقول التي يتم تحديثها حالياً لمنع التكرار
    updatingFields: new Set(),
    
    /**
     * تسجيل مستمع حدث
     * @param {string} event - اسم الحدث
     * @param {Function} callback - دالة رد الاستدعاء
     * @param {Object} context - سياق تنفيذ الدالة (this)
     * @returns {Object} كائن يمثل الاشتراك
     */
    on: function(event, callback, context) {
        if (!this.listeners[event]) {
            this.listeners[event] = [];
        }
        
        const listener = {
            callback: callback,
            context: context || window
        };
        
        this.listeners[event].push(listener);
        return listener;
    },
    
    /**
     * إلغاء تسجيل مستمع حدث
     * @param {string} event - اسم الحدث
     * @param {Function} callback - دالة رد الاستدعاء
     * @param {Object} context - سياق تنفيذ الدالة (this)
     */
    off: function(event, callback, context) {
        if (!this.listeners[event]) {
            return;
        }
        
        this.listeners[event] = this.listeners[event].filter(listener => {
            return callback !== listener.callback || context !== listener.context;
        });
    },
    
    /**
     * إطلاق حدث
     * @param {string} event - اسم الحدث
     * @param {Object} data - بيانات الحدث
     */
    emit: function(event, data) {
        if (!this.listeners[event]) {
            return;
        }
        
        // التحقق من الحلقات اللانهائية
        const now = Date.now();
        const eventKey = event + JSON.stringify(data || {});
        
        // تخطي الأحداث المكررة التي تم إطلاقها مؤخراً
        if (this.recentEvents[eventKey] && (now - this.recentEvents[eventKey] < this.eventThrottleTime)) {
            return;
        }
        
        // تسجيل الحدث في قائمة الأحداث الأخيرة
        this.recentEvents[eventKey] = now;
        
        // تنظيف قائمة الأحداث القديمة كل 5 ثواني
        if (!this._cleanupTimer) {
            this._cleanupTimer = setInterval(() => {
                const cutoff = Date.now() - 5000;
                for (const key in this.recentEvents) {
                    if (this.recentEvents[key] < cutoff) {
                        delete this.recentEvents[key];
                    }
                }
            }, 5000);
        }
        
        // التعامل مع أحداث خاصة
        if (event === 'internal-content:changed') {
            // إذا كان الحدث يحتوي على علامة skipRecursion، نتجاهل هذا الفحص
            if (data && data.skipRecursion) {
                delete data.skipRecursion; // إزالة العلامة قبل تمرير البيانات للمستمعين
            }
        }
        
        this.listeners[event].forEach(listener => {
            try {
                listener.callback.call(listener.context, data);
            } catch (error) {
                console.error(`خطأ في معالج الحدث ${event}:`, error);
            }
        });
    },
    
    /**
     * تسجيل تغيير في حقل وجدولة تحديث مجمع
     * @param {string} fieldId - معرف الحقل الذي تم تغييره
     * @param {*} value - القيمة الجديدة
     * @param {boolean} immediate - هل يجب التحديث فورًا بدون تأخير
     * @param {boolean} skipDependencies - تخطي تحديث الحقول التابعة
     */
    fieldChanged: function(fieldId, value, immediate, skipDependencies) {
        // إضافة الحقل إلى قائمة الحقول المتغيرة
        this.changedFields.add(fieldId);
        
        // إلغاء المؤقت السابق إذا كان موجودًا
        if (this.debounceTimer) {
            clearTimeout(this.debounceTimer);
        }
        
        // إطلاق حدث فوري للحقل المحدد
        this.emit(`field:${fieldId}:changed`, { fieldId, value });
        
        // تحديث الحقول التابعة إذا لم يتم تخطيها
        if (!skipDependencies) {
            this.updateDependentFields(fieldId, value);
        }
        
        // جدولة تحديث مجمع بعد فترة تأخير قصيرة
        const self = this;
        const delay = immediate ? 0 : 300; // تأخير أقصر للتحديثات الفورية
        
        this.debounceTimer = setTimeout(function() {
            // إنشاء نسخة من قائمة الحقول المتغيرة
            const changedFieldsList = Array.from(self.changedFields);
            
            // مسح قائمة الحقول المتغيرة
            self.changedFields.clear();
            
            // إطلاق حدث التحديث المجمع
            self.emit('fields:updated', {
                changedFields: changedFieldsList,
                timestamp: Date.now()
            });
            
            // إطلاق حدث لتحديث التكلفة الإجمالية
            self.emit('pricing:update', {
                changedFields: changedFieldsList,
                timestamp: Date.now()
            });
        }, delay);
    },
    
    /**
     * تحديث الحقول التابعة لحقل معين
     * @param {string} fieldId - معرف الحقل الأصلي
     * @param {*} value - قيمة الحقل الأصلي
     */
    updateDependentFields: function(fieldId, value) {
        // إذا كان الحقل قيد التحديث بالفعل، تخطي لمنع الحلقات اللانهائية
        if (this.updatingFields.has(fieldId)) {
            return;
        }
        
        // إضافة الحقل إلى قائمة الحقول قيد التحديث
        this.updatingFields.add(fieldId);
        
        // التحقق من وجود تبعيات للحقل
        if (this.fieldDependencies[fieldId]) {
            // الحصول على قائمة الحقول التابعة
            const dependencies = this.fieldDependencies[fieldId];
            
            // تحديث كل حقل تابع
            dependencies.forEach(dependency => {
                // الحصول على عنصر الحقل
                const element = document.getElementById(dependency.fieldId);
                if (!element) return;
                
                // تحديث قيمة الحقل إذا كانت هناك دالة تحديث
                if (dependency.updateFunction) {
                    try {
                        // استدعاء دالة التحديث مع قيمة الحقل الأصلي
                        const newValue = dependency.updateFunction(value, element);
                        
                        // تحديث قيمة الحقل إذا تم إرجاع قيمة
                        if (newValue !== undefined) {
                            if (element.type === 'checkbox') {
                                element.checked = Boolean(newValue);
                            } else {
                                element.value = newValue;
                            }
                        }
                        
                        // إطلاق حدث تغيير للحقل التابع
                        this.fieldChanged(dependency.fieldId, element.type === 'checkbox' ? element.checked : element.value, true, true);
                    } catch (error) {
                        console.error(`خطأ في تحديث الحقل التابع ${dependency.fieldId}:`, error);
                    }
                }
                
                // إطلاق حدث تغيير للحقل التابع إذا كان هناك تحديث مباشر
                if (dependency.directUpdate) {
                    // إطلاق حدث تغيير للحقل التابع
                    this.emit(`field:${dependency.fieldId}:changed`, { 
                        fieldId: dependency.fieldId, 
                        value: element.type === 'checkbox' ? element.checked : element.value,
                        parentField: fieldId,
                        parentValue: value
                    });
                }
            });
        }
        
        // إزالة الحقل من قائمة الحقول قيد التحديث
        this.updatingFields.delete(fieldId);
    },
    
    /**
     * إعداد تبعيات الحقول
     * @param {string} sourceFieldId - معرف الحقل المصدر
     * @param {Array} dependencies - قائمة الحقول التابعة
     */
    setupFieldDependencies: function(sourceFieldId, dependencies) {
        if (!this.fieldDependencies[sourceFieldId]) {
            this.fieldDependencies[sourceFieldId] = [];
        }
        
        // إضافة التبعيات الجديدة
        this.fieldDependencies[sourceFieldId] = [
            ...this.fieldDependencies[sourceFieldId],
            ...dependencies
        ];
    },
    
    /**
     * تهيئة مستمعي الأحداث لجميع حقول النموذج
     */
    setupFormListeners: function() {
        // الحصول على جميع حقول الإدخال في النموذج
        const form = document.getElementById('pricing-form');
        if (!form) {
            console.error('لم يتم العثور على نموذج التسعير');
            return;
        }
        
        // الحصول على جميع حقول الإدخال والاختيار والنص
        const inputs = form.querySelectorAll('input, select, textarea');
        
        // إضافة مستمعي الأحداث لكل حقل
        inputs.forEach(input => {
            const fieldId = input.id;
            if (!fieldId) {
                return; // تخطي الحقول بدون معرف
            }
            
            // تحديد نوع الحدث بناءً على نوع الحقل
            const eventType = (input.type === 'checkbox' || input.type === 'radio' || input.tagName.toLowerCase() === 'select') 
                ? 'change' 
                : 'input';
            
            // إضافة مستمع الحدث
            input.addEventListener(eventType, event => {
                const value = input.type === 'checkbox' ? input.checked : input.value;
                this.fieldChanged(fieldId, value);
            });
        });
        
    },
    
    /**
     * تهيئة التبعيات الأساسية في النظام
     */
    initDependencies: function() {
        // تبعيات حقل الكمية
        this.setupFieldDependencies('id_quantity', [
            { 
                fieldId: 'id_paper_sheets_count', 
                directUpdate: true 
            },
            { 
                fieldId: 'coating_total', 
                directUpdate: true 
            },
            {
                fieldId: 'id_coating_total_cost',
                directUpdate: true
            }
        ]);
        
        // تبعيات حقل عدد أفرخ الورق
        this.setupFieldDependencies('id_paper_sheets_count', [
            { 
                fieldId: 'id_paper_quantity', 
                updateFunction: (value) => value 
            },
            { 
                fieldId: 'coating_total', 
                directUpdate: true 
            }
        ]);
        
        // تبعيات حقل ماكينة الطباعة
        this.setupFieldDependencies('press_selector', [
            { 
                fieldId: 'id_press', 
                updateFunction: (value) => value 
            },
            { 
                fieldId: 'id_montage_info', 
                directUpdate: true 
            },
            { 
                fieldId: 'id_paper_sheets_count', 
                directUpdate: true 
            },
            {
                fieldId: 'coating_total',
                directUpdate: true
            }
        ]);
        
        // تبعيات حقل مقاس الورق
        this.setupFieldDependencies('id_product_size', [
            { 
                fieldId: 'id_montage_info', 
                directUpdate: true 
            },
            { 
                fieldId: 'id_paper_sheets_count', 
                directUpdate: true 
            },
            {
                fieldId: 'coating_total',
                directUpdate: true
            }
        ]);
        
    },
    
    /**
     * تسجيل المعالجات الرئيسية للتحديثات
     */
    registerCoreHandlers: function() {
        // مستمع لتحديث التكلفة الإجمالية
        this.on('pricing:update', function() {
            // تأكد من وجود وحدة التسعير قبل استدعاء الدالة
            if (PricingSystem.Pricing && typeof PricingSystem.Pricing.calculateCost === 'function') {
                PricingSystem.Pricing.calculateCost();
            }
        });
        
        // مستمع لتحديث تكلفة الطباعة
        this.on('fields:updated', function(data) {
            // تحديث تكلفة الطباعة إذا تغيرت الحقول ذات الصلة
            const printRelatedFields = [
                'id_quantity', 'id_press', 'id_press_price_per_1000', 
                'id_colors_front', 'id_colors_back', 'id_press_runs'
            ];
            
            const shouldUpdatePrintCost = data.changedFields.some(field => 
                printRelatedFields.includes(field)
            );
            
            if (shouldUpdatePrintCost && PricingSystem.Print && 
                typeof PricingSystem.Print.calculatePressCost === 'function') {
                PricingSystem.Print.calculatePressCost();
            }
            
            // تحديث تكلفة الورق إذا تغيرت الحقول ذات الصلة
            const paperRelatedFields = [
                'id_paper_type', 'id_paper_weight', 'id_paper_supplier',
                'id_paper_sheet_type', 'id_quantity'
            ];
            
            const shouldUpdatePaperCost = data.changedFields.some(field => 
                paperRelatedFields.includes(field)
            );
            
            if (shouldUpdatePaperCost && PricingSystem.Paper && 
                typeof PricingSystem.Paper.updateTotalPaperCost === 'function') {
                PricingSystem.Paper.updateTotalPaperCost();
            }
            
            // تحديث تكلفة التصميم إذا تغيرت الحقول ذات الصلة
            const designRelatedFields = [
                'id_design_price', 'id_internal_design_price'
            ];
            
            const shouldUpdateDesignCost = data.changedFields.some(field => 
                designRelatedFields.includes(field)
            );
            
            if (shouldUpdateDesignCost && PricingSystem.Pricing && 
                typeof PricingSystem.Pricing.updateDesignCost === 'function') {
                PricingSystem.Pricing.updateDesignCost();
            }
            
            // تحديث معلومات المونتاج إذا تغيرت ماكينة الطباعة
            if (data.changedFields.includes('id_press') && 
                PricingSystem.Montage && 
                typeof PricingSystem.Montage.updateMontageInfo === 'function') {
                const montageInfoField = document.getElementById('id_montage_info');
                if (montageInfoField) {
                    PricingSystem.Montage.updateMontageInfo(montageInfoField);
                }
            }
            
            // حساب عدد التراجات تلقائيًا إذا تغيرت الكمية
            if (data.changedFields.includes('id_quantity') && 
                PricingSystem.Print && 
                typeof PricingSystem.Print.calculatePressRuns === 'function') {
                PricingSystem.Print.calculatePressRuns();
            }
        });
    },
    
    /**
     * تهيئة نظام ناقل الأحداث
     */
    init: function() {
        this.registerCoreHandlers();
        this.initDependencies();
        this.setupFormListeners();
        
    }
}; 