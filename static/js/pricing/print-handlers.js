/**
 * print-handlers.js - دالات معالجة الطباعة
 */

// تعريف كائن عام للمشروع إذا لم يكن موجودًا
window.PricingSystem = window.PricingSystem || {};

// تعريف وحدة معالجة الطباعة
PricingSystem.Print = {
    /**
     * تهيئة معالجات أحداث الطباعة
     */
    init: function() {
        // تسجيل معالجات الأحداث مع ناقل الأحداث إذا كان متاحًا
        if (PricingSystem.EventBus) {
            this.registerEventHandlers();
        } else {
            // استخدام الطريقة التقليدية
            this.setupTraditionalEventHandlers();
        }
        
        // تهيئة حقول ألوان المحتوى الداخلي
        this.initInternalColorsFields();
    },
    
    /**
     * تسجيل معالجات الأحداث مع ناقل الأحداث
     */
    registerEventHandlers: function() {
        // الاستماع لتغييرات عدد أوجه الطباعة
        PricingSystem.EventBus.on('field:id_print_sides:changed', (data) => {
            const printSidesSelect = document.getElementById('id_print_sides');
            const singleSideColors = document.getElementById('single-side-colors');
            const doubleSideColors = document.getElementById('double-side-colors');
            
            if (printSidesSelect && singleSideColors && doubleSideColors) {
                this.updateColorsFields(printSidesSelect, singleSideColors, doubleSideColors);
            }
        });
        
        // الاستماع لتغييرات عدد أوجه الطباعة للمحتوى الداخلي
        PricingSystem.EventBus.on('field:id_internal_print_sides:changed', (data) => {
            const internalPrintSidesSelect = document.getElementById('id_internal_print_sides');
            const internalSingleSideColors = document.getElementById('internal-single-side-colors');
            const internalDoubleSideColors = document.getElementById('internal-double-side-colors');
            
            if (internalPrintSidesSelect && internalSingleSideColors && internalDoubleSideColors) {
                this.updateInternalColorsFields(internalPrintSidesSelect, internalSingleSideColors, internalDoubleSideColors);
            }
        });
        
        // الاستماع لتحديثات الحقول المتعلقة بالطباعة
        PricingSystem.EventBus.on('fields:updated', (data) => {
            const printRelatedFields = [
                'id_quantity', 'id_print_sides', 'id_colors_design', 
                'id_colors_front', 'id_colors_back'
            ];
            
            const shouldUpdatePressRuns = data.changedFields.some(field => 
                printRelatedFields.includes(field)
            );
            
            if (shouldUpdatePressRuns) {
                this.calculatePressRuns();
            }
            
            // تحديث تكلفة الطباعة إذا تغيرت الحقول ذات الصلة
            const pressCostFields = [
                'id_press_price_per_1000', 'id_press_runs', 'id_press_transportation'
            ];
            
            const shouldUpdatePressCost = data.changedFields.some(field => 
                pressCostFields.includes(field)
            );
            
            if (shouldUpdatePressCost) {
                this.calculatePressCost();
            }
            
            // تحديث حقول المحتوى الداخلي
            const internalPrintRelatedFields = [
                'id_quantity', 'id_internal_print_sides', 'id_internal_colors_design', 
                'id_internal_colors_front', 'id_internal_colors_back', 'id_internal_page_count'
            ];
            
            const shouldUpdateInternalPressRuns = data.changedFields.some(field => 
                internalPrintRelatedFields.includes(field)
            );
            
            if (shouldUpdateInternalPressRuns) {
                this.calculateInternalPressRuns();
            }
            
            // تحديث تكلفة طباعة المحتوى الداخلي إذا تغيرت الحقول ذات الصلة
            const internalPressCostFields = [
                'id_internal_press_price_per_1000', 'id_internal_press_runs', 
                'id_internal_press_transportation', 'id_internal_page_count'
            ];
            
            const shouldUpdateInternalPressCost = data.changedFields.some(field => 
                internalPressCostFields.includes(field)
            );
            
            if (shouldUpdateInternalPressCost) {
                this.calculateInternalPressCost();
            }
        });
        
        // الاستماع لتغيير حالة المحتوى الداخلي
        PricingSystem.EventBus.on('internal-content:changed', (data) => {
            if (data.hasInternal) {
                // تحديث حقول المحتوى الداخلي عند تفعيله
                setTimeout(() => {
                    this.calculateInternalPressRuns();
                    this.calculateInternalPressCost();
                }, 300);
            }
        });
    },
    
    /**
     * إعداد معالجات الأحداث التقليدية (بدون ناقل الأحداث)
     */
    setupTraditionalEventHandlers: function() {
        // إضافة معالج حدث لتغيير عدد أوجه الطباعة
        const printSidesSelect = document.getElementById('id_print_sides');
        const singleSideColors = document.getElementById('single-side-colors');
        const doubleSideColors = document.getElementById('double-side-colors');
        
        if (printSidesSelect && singleSideColors && doubleSideColors) {
            // تحديث حقول الألوان عند تحميل الصفحة
            this.updateColorsFields(printSidesSelect, singleSideColors, doubleSideColors);
            
            // إضافة معالج حدث لتغيير عدد أوجه الطباعة
            printSidesSelect.addEventListener('change', () => {
                this.updateColorsFields(printSidesSelect, singleSideColors, doubleSideColors);
                this.calculatePressRuns();
            });
            
            // تنفيذ تحديث أولي لحقول الألوان عند تحميل الصفحة
            setTimeout(() => {
                this.updateColorsFields(printSidesSelect, singleSideColors, doubleSideColors);
            }, 100);
        }
        
        // إضافة معالجات أحداث لتغيير عدد الألوان
        const colorsDesignInput = document.getElementById('id_colors_design');
        const colorsFrontInput = document.getElementById('id_colors_front');
        const colorsBackInput = document.getElementById('id_colors_back');
        
        if (colorsDesignInput) {
            colorsDesignInput.addEventListener('input', this.calculatePressRuns.bind(this));
            colorsDesignInput.addEventListener('change', this.calculatePressRuns.bind(this));
        }
        
        if (colorsFrontInput) {
            colorsFrontInput.addEventListener('input', this.calculatePressRuns.bind(this));
            colorsFrontInput.addEventListener('change', this.calculatePressRuns.bind(this));
        }
        
        if (colorsBackInput) {
            colorsBackInput.addEventListener('input', this.calculatePressRuns.bind(this));
            colorsBackInput.addEventListener('change', this.calculatePressRuns.bind(this));
        }
        
        // إضافة معالج حدث لتغيير الكمية
        const quantityInput = document.getElementById('id_quantity');
        if (quantityInput) {
            quantityInput.addEventListener('input', this.calculatePressRuns.bind(this));
            quantityInput.addEventListener('change', this.calculatePressRuns.bind(this));
        }
        
        // إضافة معالج حدث لتغيير سعر الطباعة
        const pressPriceInput = document.getElementById('id_press_price_per_1000');
        if (pressPriceInput) {
            pressPriceInput.addEventListener('input', this.calculatePressCost.bind(this));
            pressPriceInput.addEventListener('change', this.calculatePressCost.bind(this));
        }
        
        // إضافة معالج حدث لتغيير تكلفة الانتقالات
        const pressTransportationInput = document.getElementById('id_press_transportation');
        if (pressTransportationInput) {
            pressTransportationInput.addEventListener('input', this.calculatePressCost.bind(this));
            pressTransportationInput.addEventListener('change', this.calculatePressCost.bind(this));
        }
    },
    
    /**
     * حساب عدد التراجات
     */
    calculatePressRuns: function() {
        const quantityInput = document.getElementById('id_quantity');
        const printSidesSelect = document.getElementById('id_print_sides');
        const colorsDesignInput = document.getElementById('id_colors_design');
        const colorsFrontInput = document.getElementById('id_colors_front');
        const colorsBackInput = document.getElementById('id_colors_back');
        const pressRunsInput = document.getElementById('id_press_runs');
        
        if (!printSidesSelect || !pressRunsInput || !quantityInput) {
            return;
        }
        
        // تحويل الكمية إلى رقم صحيح
        const quantity = parseInt(quantityInput.value) || 0;
        
        // حساب عدد التراجات بناءً على الكمية (كل 1000 أو كسر الألف فوق 150)
        let runs = 0;
        
        // عدد الألوف الكاملة
        const fullThousands = Math.floor(quantity / 1000);
        // الكسر المتبقي
        const remainder = quantity % 1000;
        
        // إضافة عدد الألوف
        runs = fullThousands;
        
        // إذا كان الكسر أكبر من 150، نضيف تراج إضافي
        if (remainder > 150) {
            runs += 1;
        }
        
        // إذا كانت الكمية أقل من 150، لكن أكبر من 0، نحسب تراج واحد على الأقل
        if (quantity > 0 && runs === 0) {
            runs = 1;
        }
        
        // حساب عدد الألوان حسب أوجه الطباعة
        let totalColors = 0;
        const printSides = printSidesSelect.value;
        
        if (printSides === '1') {
            // وجه واحد
            if (colorsDesignInput && colorsDesignInput.value) {
                totalColors = parseInt(colorsDesignInput.value) || 0;
            }
        } else if (printSides === '2') {
            // وجهين مختلفين
            let frontColors = 0;
            let backColors = 0;
            
            if (colorsFrontInput && colorsFrontInput.value) {
                frontColors = parseInt(colorsFrontInput.value) || 0;
            }
            
            if (colorsBackInput && colorsBackInput.value) {
                backColors = parseInt(colorsBackInput.value) || 0;
            }
            
            totalColors = frontColors + backColors;
        } else if (printSides === '3') {
            // وجهين متطابقين
            if (colorsDesignInput && colorsDesignInput.value) {
                totalColors = parseInt(colorsDesignInput.value) * 2 || 0;
            }
        }
        
        // ضرب عدد التراجات في عدد الألوان
        runs = runs * Math.max(1, totalColors);
        
        // تحديث حقل عدد التراجات
        pressRunsInput.value = runs;
        
        // إطلاق حدث تغيير عدد التراجات عبر ناقل الأحداث
        if (PricingSystem.EventBus) {
            PricingSystem.EventBus.fieldChanged('id_press_runs', runs, true);
        } else {
            // تحديث تكلفة الطباعة
            PricingSystem.Print.calculatePressCost();
            
            // تحديث عدد الزنكات - التحقق من وجود الدالة قبل استدعائها
            if (typeof this.updateCtpPlatesCount === 'function') {
                this.updateCtpPlatesCount();
            } else if (typeof PricingSystem.CTP !== 'undefined' && typeof PricingSystem.CTP.calculatePlatesCount === 'function') {
                // استخدام دالة calculatePlatesCount من كائن PricingSystem.CTP إذا كانت متاحة
                PricingSystem.CTP.calculatePlatesCount();
            }
        }
    },
    
    /**
     * حساب تكلفة الطباعة
     */
    calculatePressCost: function() {
        const pressPriceInput = document.getElementById('id_press_price_per_1000');
        const pressRunsInput = document.getElementById('id_press_runs');
        const pressTransportationInput = document.getElementById('id_press_transportation');
        const pressTotalCostInput = document.getElementById('id_press_total_cost');
        
        if (!pressPriceInput || !pressRunsInput || !pressTotalCostInput) {
            return;
        }
        
        // تحويل القيم إلى أرقام
        const pressPrice = parseFloat(pressPriceInput.value) || 0;
        const pressRuns = parseInt(pressRunsInput.value) || 0;
        const pressTransportation = parseFloat(pressTransportationInput.value) || 0;
        
        // حساب التكلفة الإجمالية
        const totalCost = (pressPrice * pressRuns) + pressTransportation;
        
        // تحديث حقل التكلفة الإجمالية
        pressTotalCostInput.value = totalCost.toFixed(2);
        
        // إطلاق حدث تغيير تكلفة الطباعة عبر ناقل الأحداث
        if (PricingSystem.EventBus) {
            PricingSystem.EventBus.fieldChanged('id_press_total_cost', totalCost.toFixed(2), true);
        } else {
            // تحديث التكلفة الإجمالية
            if (typeof PricingSystem.Pricing !== 'undefined' && typeof PricingSystem.Pricing.calculateCost === 'function') {
                PricingSystem.Pricing.calculateCost();
            }
        }
    },
    
    /**
     * تهيئة حقول ألوان المحتوى الداخلي
     */
    initInternalColorsFields: function() {
        const internalPrintSidesSelect = document.getElementById('id_internal_print_sides');
        const internalSingleSideColors = document.getElementById('internal-single-side-colors');
        const internalDoubleSideColors = document.getElementById('internal-double-side-colors');
        
        if (internalPrintSidesSelect && internalSingleSideColors && internalDoubleSideColors) {
            // تحديث حقول الألوان عند تحميل الصفحة
            this.updateInternalColorsFields(internalPrintSidesSelect, internalSingleSideColors, internalDoubleSideColors);
            
            // إضافة معالج حدث لتغيير عدد أوجه الطباعة
            internalPrintSidesSelect.addEventListener('change', () => {
                this.updateInternalColorsFields(internalPrintSidesSelect, internalSingleSideColors, internalDoubleSideColors);
                this.calculateInternalPressRuns();
            });
            
            // تنفيذ تحديث أولي لحقول الألوان عند تحميل الصفحة
            setTimeout(() => {
                this.updateInternalColorsFields(internalPrintSidesSelect, internalSingleSideColors, internalDoubleSideColors);
            }, 100);
        }
    },
    
    /**
     * تحديث حقول ألوان المحتوى الداخلي بناءً على عدد أوجه الطباعة
     * @param {HTMLSelectElement} printSidesSelect - قائمة اختيار أوجه الطباعة
     * @param {HTMLElement} singleSideColors - حقل ألوان الوجه الواحد
     * @param {HTMLElement} doubleSideColors - حقل ألوان الوجهين
     */
    updateInternalColorsFields: function(printSidesSelect, singleSideColors, doubleSideColors) {
        if (!printSidesSelect || !singleSideColors || !doubleSideColors) {
            return;
        }
        
        const selectedValue = printSidesSelect.value;
        
        // تحديث حقول الألوان حسب عدد الأوجه
        // القيم: 1 = وجه واحد، 2 = وجهين، 3 = طبع وقلب
        if (selectedValue === '1' || selectedValue === '3') {
            // وجه واحد أو طبع وقلب (تصميم واحد)
            singleSideColors.style.display = 'block';
            doubleSideColors.style.display = 'none';
        } else if (selectedValue === '2') {
            // وجهين مختلفين
            singleSideColors.style.display = 'none';
            doubleSideColors.style.display = 'block';
        }
    },
    
    /**
     * تحديث حقول الألوان بناءً على عدد أوجه الطباعة
     * @param {HTMLSelectElement} printSidesSelect - قائمة اختيار أوجه الطباعة
     * @param {HTMLElement} singleSideColors - حقل ألوان الوجه الواحد
     * @param {HTMLElement} doubleSideColors - حقل ألوان الوجهين
     */
    updateColorsFields: function(printSidesSelect, singleSideColors, doubleSideColors) {
        if (!printSidesSelect || !singleSideColors || !doubleSideColors) {
            return;
        }
        
        const selectedValue = printSidesSelect.value;
        
        // تحديث حقول الألوان حسب عدد الأوجه
        // القيم: 1 = وجه واحد، 2 = وجهين، 3 = طبع وقلب
        if (selectedValue === '1' || selectedValue === '3') {
            // وجه واحد أو طبع وقلب (تصميم واحد)
            singleSideColors.style.display = 'block';
            doubleSideColors.style.display = 'none';
        } else if (selectedValue === '2') {
            // وجهين مختلفين
            singleSideColors.style.display = 'none';
            doubleSideColors.style.display = 'block';
        }
    },
    
    /**
     * حساب عدد التراجات للمحتوى الداخلي
     */
    calculateInternalPressRuns: function() {
        const quantityInput = document.getElementById('id_quantity');
        const internalPrintSidesSelect = document.getElementById('id_internal_print_sides');
        const internalColorsDesignInput = document.getElementById('id_internal_colors_design');
        const internalColorsFrontInput = document.getElementById('id_internal_colors_front');
        const internalColorsBackInput = document.getElementById('id_internal_colors_back');
        const internalPressRunsInput = document.getElementById('id_internal_press_runs');
        
        if (!internalPrintSidesSelect || !internalPressRunsInput || !quantityInput) {
            return;
        }
        
        // تحويل الكمية إلى رقم صحيح
        const quantity = parseInt(quantityInput.value) || 0;
        
        // حساب عدد التراجات بناءً على الكمية (كل 1000 أو كسر الألف فوق 150)
        let runs = 0;
        
        // عدد الألوف الكاملة
        const fullThousands = Math.floor(quantity / 1000);
        // الكسر المتبقي
        const remainder = quantity % 1000;
        
        // إضافة عدد الألوف
        runs = fullThousands;
        
        // إذا كان الكسر أكبر من 150، نضيف تراج إضافي
        if (remainder > 150) {
            runs += 1;
        }
        
        // إذا كانت الكمية أقل من 150، لكن أكبر من 0، نحسب تراج واحد على الأقل
        if (quantity > 0 && runs === 0) {
            runs = 1;
        }
        
        // حساب عدد الألوان حسب أوجه الطباعة
        let totalColors = 0;
        const printSides = internalPrintSidesSelect.value;
        
        if (printSides === '1') {
            // وجه واحد
            if (internalColorsDesignInput && internalColorsDesignInput.value) {
                totalColors = parseInt(internalColorsDesignInput.value) || 0;
            }
        } else if (printSides === '2') {
            // وجهين مختلفين
            let frontColors = 0;
            let backColors = 0;
            
            if (internalColorsFrontInput && internalColorsFrontInput.value) {
                frontColors = parseInt(internalColorsFrontInput.value) || 0;
            }
            
            if (internalColorsBackInput && internalColorsBackInput.value) {
                backColors = parseInt(internalColorsBackInput.value) || 0;
            }
            
            totalColors = frontColors + backColors;
        } else if (printSides === '3') {
            // وجهين متطابقين
            if (internalColorsDesignInput && internalColorsDesignInput.value) {
                totalColors = parseInt(internalColorsDesignInput.value) * 2 || 0;
            }
        }
        
        // ضرب عدد التراجات في عدد الألوان
        runs = runs * Math.max(1, totalColors);
        
        // تحديث حقل عدد التراجات
        internalPressRunsInput.value = runs;
        
        // تحديث تكلفة الطباعة
        PricingSystem.Print.calculateInternalPressCost();
    },
    
    /**
     * حساب تكلفة الطباعة للغلاف
     */
    calculatePressCost: function() {
        const quantityInput = document.getElementById('id_quantity');
        const pressPriceInput = document.getElementById('id_press_price_per_1000');
        const pressRunsInput = document.getElementById('id_press_runs');
        const pressTransportationInput = document.getElementById('id_press_transportation');
        const pressTotalCostInput = document.getElementById('id_press_total_cost');
        const pressCostSummaryInput = document.getElementById('id_press_cost_summary');
        
        if (!quantityInput || !pressPriceInput || !pressRunsInput || !pressTransportationInput || !pressTotalCostInput) {
            return;
        }
        
        // تأكد من تحويل القيم إلى أرقام بشكل صحيح
        let quantity = 0;
        try {
            quantity = parseInt(quantityInput.value.replace(/[^\d]/g, '')) || 0;
        } catch (e) {
            quantity = 0;
        }
        
        const pricePerThousand = parseFloat(pressPriceInput.value) || 0;
        const runs = parseInt(pressRunsInput.value) || 0;
        const transportation = parseFloat(pressTransportationInput.value) || 0;
        
        // حساب تكلفة الطباعة بناءً على عدد التراجات فقط
        // السعر × عدد مرات التراج + تكلفة الانتقالات
        const printCost = (pricePerThousand * runs) + transportation;
        
        // تحديث حقل التكلفة الإجمالية
        pressTotalCostInput.value = printCost.toFixed(2);
        
        // تحديث حقل تكلفة الطباعة في قسم التسعير
        if (pressCostSummaryInput) {
            pressCostSummaryInput.value = printCost.toFixed(2);
        }
        
        // تحديث إجمالي التكلفة
        if (typeof PricingSystem.Pricing !== 'undefined' && typeof PricingSystem.Pricing.calculateCost === 'function') {
            PricingSystem.Pricing.calculateCost();
        }
    },
    
    /**
     * حساب تكلفة الطباعة للمحتوى الداخلي
     */
    calculateInternalPressCost: function() {
        const quantityInput = document.getElementById('id_quantity');
        const internalPageCountInput = document.getElementById('id_internal_page_count');
        const internalPressPriceInput = document.getElementById('id_internal_press_price_per_1000');
        const internalPressRunsInput = document.getElementById('id_internal_press_runs');
        const internalPressTransportationInput = document.getElementById('id_internal_press_transportation');
        const internalPressTotalCostInput = document.getElementById('id_internal_press_total_cost');
        const internalPressCostSummaryInput = document.getElementById('id_internal_press_cost_summary');
        
        if (!quantityInput || !internalPageCountInput || !internalPressPriceInput || !internalPressRunsInput || !internalPressTransportationInput || !internalPressTotalCostInput) {
            return;
        }
        
        const quantity = parseInt(quantityInput.value) || 0;
        const pageCount = parseInt(internalPageCountInput.value) || 0;
        const pricePerThousand = parseFloat(internalPressPriceInput.value) || 0;
        const runs = parseInt(internalPressRunsInput.value) || 0;
        const transportation = parseFloat(internalPressTransportationInput.value) || 0;
        
        // حساب تكلفة الطباعة بناءً على عدد التراجات فقط
        // السعر × عدد الصفحات × عدد التراجات + تكلفة النقل
        const printCost = (pricePerThousand * pageCount * runs) + transportation;
        
        // تحديث حقل التكلفة الإجمالية
        internalPressTotalCostInput.value = printCost.toFixed(2);
        
        // تحديث حقل تكلفة الطباعة في قسم التسعير
        if (internalPressCostSummaryInput) {
            internalPressCostSummaryInput.value = printCost.toFixed(2);
        }
        
        // تحديث إجمالي التكلفة
        if (typeof PricingSystem.Pricing !== 'undefined' && typeof PricingSystem.Pricing.calculateCost === 'function') {
            PricingSystem.Pricing.calculateCost();
        }
    },

    /**
     * إعداد معالجات الأحداث للطباعة
     * هذه الدالة تضمن أن جميع معالجات الأحداث تستخدم الدالات الصحيحة من كائن PricingSystem.Print
     */
    setupPrintEventHandlers: function() {
        // عناصر النموذج
        const printSidesSelect = document.getElementById('id_print_sides');
        const colorsDesignInput = document.getElementById('id_colors_design');
        const colorsFrontInput = document.getElementById('id_colors_front');
        const colorsBackInput = document.getElementById('id_colors_back');
        const quantityInput = document.getElementById('id_quantity');
        const pressRunsInput = document.getElementById('id_press_runs');
        const pressPriceInput = document.getElementById('id_press_price_per_1000');
        const pressTransportationInput = document.getElementById('id_press_transportation');
        
        // إعادة تعريف الدالة العالمية calculatePressRuns لتستخدم PricingSystem.Print.calculatePressRuns
        // هذا لمعالجة حالة تحميل ملف pricing_form.js.bak الاحتياطي
        window.calculatePressRuns = function() {
            PricingSystem.Print.calculatePressRuns();
        };
        
        // إعادة تعريف الدالة العالمية calculatePressCost لتستخدم PricingSystem.Print.calculatePressCost
        window.calculatePressCost = function(isInternal) {
            if (isInternal) {
                PricingSystem.Print.calculateInternalPressCost();
            } else {
                PricingSystem.Print.calculatePressCost();
            }
        };
        
        // إضافة معالجات الأحداث
        if (quantityInput) {
            quantityInput.addEventListener('input', function() {
                PricingSystem.Print.calculatePressRuns();
                // إضافة استدعاء مباشر لدالة حساب تكلفة الطباعة عند تغيير الكمية
                PricingSystem.Print.calculatePressCost();
            });
            quantityInput.addEventListener('change', function() {
                PricingSystem.Print.calculatePressRuns();
                // إضافة استدعاء مباشر لدالة حساب تكلفة الطباعة عند تغيير الكمية
                PricingSystem.Print.calculatePressCost();
            });
        }
        
        if (printSidesSelect) {
            printSidesSelect.addEventListener('change', function() {
                // تحديث حقول الألوان
                PricingSystem.Print.updateColorsFields(this, 
                    document.getElementById('single-side-colors'), 
                    document.getElementById('double-side-colors'));
                // ثم إعادة حساب عدد التراجات
                PricingSystem.Print.calculatePressRuns();
            });
        }
        
        if (colorsDesignInput) {
            colorsDesignInput.addEventListener('input', function() {
                PricingSystem.Print.calculatePressRuns();
            });
            colorsDesignInput.addEventListener('change', function() {
                PricingSystem.Print.calculatePressRuns();
            });
        }
        
        if (colorsFrontInput) {
            colorsFrontInput.addEventListener('input', function() {
                PricingSystem.Print.calculatePressRuns();
            });
            colorsFrontInput.addEventListener('change', function() {
                PricingSystem.Print.calculatePressRuns();
            });
        }
        
        if (colorsBackInput) {
            colorsBackInput.addEventListener('input', function() {
                PricingSystem.Print.calculatePressRuns();
            });
            colorsBackInput.addEventListener('change', function() {
                PricingSystem.Print.calculatePressRuns();
            });
        }
        
        // نلاحظ أن معالجات الأحداث لـ pressRunsInput و pressPriceInput و pressTransportationInput
        // يتم تعريفها أيضًا في ملف press-handlers.js
        // لذلك نتحقق أولاً إذا كان PricingSystem.Press موجودًا لتجنب تكرار معالجات الأحداث
        if (pressRunsInput && (!window.PricingSystem.Press || !window.PricingSystem.Press.setupPressEventHandlers)) {
            pressRunsInput.addEventListener('change', function() {
                PricingSystem.Print.calculatePressCost();
            });
        }
        
        if (pressPriceInput && (!window.PricingSystem.Press || !window.PricingSystem.Press.setupPressEventHandlers)) {
            pressPriceInput.addEventListener('change', function() {
                PricingSystem.Print.calculatePressCost();
            });
            pressPriceInput.addEventListener('input', function() {
                PricingSystem.Print.calculatePressCost();
            });
        }
        
        if (pressTransportationInput && (!window.PricingSystem.Press || !window.PricingSystem.Press.setupPressEventHandlers)) {
            pressTransportationInput.addEventListener('change', function() {
                PricingSystem.Print.calculatePressCost();
            });
            pressTransportationInput.addEventListener('input', function() {
                PricingSystem.Print.calculatePressCost();
            });
        }
    }
};

// استدعاء دالة إعداد معالجات الأحداث
document.addEventListener('DOMContentLoaded', function() {
    PricingSystem.Print.setupPrintEventHandlers();
}); 