/**
 * ctp-handlers.js - دالات معالجة ألواح الطباعة
 */

// تعريف كائن عام للمشروع إذا لم يكن موجودًا
window.PricingSystem = window.PricingSystem || {};

// تعريف وحدة معالجة ألواح الطباعة
PricingSystem.CTP = {
    /**
     * دالة لحساب عدد ألواح الطباعة المطلوبة
     */
    calculatePlatesCount: function() {
        const elements = PricingSystem.elements;
        const printSidesSelect = elements.printSidesSelect;
        const colorsFrontInput = elements.colorsFrontInput;
        const colorsBackInput = elements.colorsBackInput;
        const colorsDesignInput = elements.colorsDesignInput;
        const platesCountInput = document.getElementById('id_plates_count');
        
        if (!printSidesSelect || !platesCountInput) {
            return;
        }
        
        // الحصول على نص الخيار المحدد لمعرفة عدد الأوجه
        const selectedOption = printSidesSelect.options[printSidesSelect.selectedIndex];
        const optionText = selectedOption ? selectedOption.text : '';
        
        // تحديد نوع الطباعة بناءً على النص المعروض
        const isDoubleSided = optionText.includes('وجهين') || optionText.includes('طرفين');
        
        // حساب عدد الألواح بناءً على عدد الألوان
        let platesCount = 0;
        
        if (isDoubleSided && colorsFrontInput && colorsBackInput) {
            // وجهين: عدد الألواح = عدد ألوان الوجه الأمامي + عدد ألوان الوجه الخلفي
            const frontColors = parseInt(colorsFrontInput.value) || 0;
            const backColors = parseInt(colorsBackInput.value) || 0;
            platesCount = frontColors + backColors;
        } else if (colorsDesignInput) {
            // وجه واحد: عدد الألواح = عدد ألوان التصميم
            platesCount = parseInt(colorsDesignInput.value) || 0;
        }
        
        // تحديث حقل عدد الألواح
        platesCountInput.value = platesCount;
        
        // حساب تكلفة الألواح بعد تحديث العدد
        this.calculatePlatesTotalCost();
    },
    
    /**
     * دالة لحساب التكلفة الإجمالية لألواح الطباعة
     */
    calculatePlatesTotalCost: function() {
        const platesCountInput = document.getElementById('id_plates_count');
        const platePriceInput = document.getElementById('id_plate_price');
        const platesTotalCostInput = document.getElementById('id_plates_total_cost');
        const platesCostSummaryInput = document.getElementById('id_plates_cost_summary');
        
        if (!platesCountInput || !platePriceInput || !platesTotalCostInput || !platesCostSummaryInput) {
            return;
        }
        
        const count = parseInt(platesCountInput.value) || 0;
        const price = parseFloat(platePriceInput.value) || 0;
        
        // حساب التكلفة الإجمالية
        const totalCost = count * price;
        
        // تحديث حقل التكلفة الإجمالية
        platesTotalCostInput.value = totalCost.toFixed(2);
        
        // تحديث حقل تكلفة الألواح في قسم التسعير
        platesCostSummaryInput.value = totalCost.toFixed(2);
        
        // تحديث إجمالي التكلفة
        if (typeof PricingSystem.Pricing !== 'undefined' && typeof PricingSystem.Pricing.calculateCost === 'function') {
            PricingSystem.Pricing.calculateCost();
        }
    },
    
    /**
     * تحديث سعر الزنك للغلاف
     */
    updatePlatePrice: function() {
        const ctpSupplierSelect = document.getElementById('id_ctp_supplier');
        const ctpPlateSizeSelect = document.getElementById('id_ctp_plate_size');
        const ctpPlatePriceInput = document.getElementById('id_ctp_plate_price');
        
        if (!ctpSupplierSelect || !ctpPlateSizeSelect || !ctpPlatePriceInput) {
            return;
        }
        
        const supplierId = ctpSupplierSelect.value;
        const plateSizeId = ctpPlateSizeSelect.value;
        
        // التحقق من وجود المورد ومقاس الزنك
        if (!supplierId || !plateSizeId) {
            return;
        }
        
        // محاولة الحصول على السعر من البيانات المخزنة في القائمة
        const selectedOption = ctpPlateSizeSelect.options[ctpPlateSizeSelect.selectedIndex];
        if (selectedOption && selectedOption.dataset.price) {
            ctpPlatePriceInput.value = selectedOption.dataset.price;
            // تحديث التكلفة الإجمالية
            this.calculateCTPCost();
            return;
        }
        
        // استدعاء API للحصول على سعر الزنك
        fetch(`/pricing/api/plate-price/?supplier_id=${supplierId}&plate_size_id=${plateSizeId}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`فشل الطلب بكود الحالة: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                if (data.success) {
                    // تحديث سعر الزنك
                    ctpPlatePriceInput.value = data.price || '';
                    // تحديث التكلفة الإجمالية
                    this.calculateCTPCost();
                }
            })
            .catch(error => {
                console.error('خطأ في استدعاء API لسعر الزنك:', error);
            });
    },
    
    /**
     * تهيئة معالجات أحداث الزنكات
     */
    setupCtpHandlers: function() {
        // تهيئة معالجات أحداث الزنكات للغلاف
        this.setupCoverCTPHandlers();
        
        // تهيئة معالجات أحداث الزنكات للمحتوى الداخلي
        this.setupInternalCTPHandlers();
        
        // تسجيل معالجات الأحداث مع ناقل الأحداث إذا كان متاحًا
        if (PricingSystem.EventBus) {
            this.registerEventHandlers();
        }
    },
    
    /**
     * تسجيل معالجات الأحداث مع ناقل الأحداث
     */
    registerEventHandlers: function() {
        // الاستماع لتغييرات مورد الزنكات للغلاف
        PricingSystem.EventBus.on('field:id_ctp_supplier:changed', (data) => {
            const ctpSupplierSelect = document.getElementById('id_ctp_supplier');
            const ctpPlateSizeSelect = document.getElementById('id_ctp_plate_size');
            const ctpPlatePriceInput = document.getElementById('id_ctp_plate_price');
            
            // إذا تم إعادة تعيين المورد (اختيار قيمة فارغة)، نقوم بمسح قائمة مقاسات الزنك وحقول السعر
            if (!ctpSupplierSelect.value) {
                ctpPlateSizeSelect.innerHTML = '<option value="">-- اختر مقاس الزنك --</option>';
                ctpPlateSizeSelect.disabled = true;
                ctpPlatePriceInput.value = '';
                this.calculateCTPCost();
                return;
            }
            
            // تحميل مقاسات الزنكات للمورد المختار
            this.loadPlateSizes(ctpSupplierSelect.value, ctpPlateSizeSelect);
            this.updatePlatePrice();
        });
        
        // الاستماع لتغييرات مقاس الزنك للغلاف
        PricingSystem.EventBus.on('field:id_ctp_plate_size:changed', (data) => {
            // إظهار/إخفاء حقول المقاس المخصص - تم إلغاء هذه الميزة
            const ctpCustomSizeFields = document.getElementById('ctp-custom-size-fields');
            if (ctpCustomSizeFields) {
                ctpCustomSizeFields.style.display = 'none'; // إخفاء حقول المقاس المخصص دائمًا
            }
            
            this.updatePlatePrice();
        });
        
        // الاستماع لتغييرات حقول تكلفة الزنكات للغلاف
        const ctpCostFields = ['id_ctp_plates_count', 'id_ctp_plate_price', 'id_ctp_transportation'];
        ctpCostFields.forEach(fieldId => {
            PricingSystem.EventBus.on(`field:${fieldId}:changed`, (data) => {
                this.calculateCTPCost();
            });
        });
        
        // الاستماع لتغييرات مورد الزنكات للمحتوى الداخلي
        PricingSystem.EventBus.on('field:id_internal_ctp_supplier:changed', (data) => {
            const internalCtpSupplierSelect = document.getElementById('id_internal_ctp_supplier');
            const internalCtpPlateSizeSelect = document.getElementById('id_internal_ctp_plate_size');
            const internalCtpPlatePriceInput = document.getElementById('id_internal_ctp_plate_price');
            
            // إذا تم إعادة تعيين المورد (اختيار قيمة فارغة)، نقوم بمسح قائمة مقاسات الزنك وحقول السعر
            if (!internalCtpSupplierSelect.value) {
                internalCtpPlateSizeSelect.innerHTML = '<option value="">-- اختر مقاس الزنك --</option>';
                internalCtpPlateSizeSelect.disabled = true;
                internalCtpPlatePriceInput.value = '';
                this.calculateInternalCTPCost();
                return;
            }
            
            // تحميل مقاسات الزنكات للمورد المختار
            this.loadPlateSizes(internalCtpSupplierSelect.value, internalCtpPlateSizeSelect);
            this.updateInternalPlatePrice();
        });
        
        // الاستماع لتغييرات مقاس الزنك للمحتوى الداخلي
        PricingSystem.EventBus.on('field:id_internal_ctp_plate_size:changed', (data) => {
            // إظهار/إخفاء حقول المقاس المخصص - تم إلغاء هذه الميزة
            const internalCtpCustomSizeFields = document.getElementById('internal-ctp-custom-size-fields');
            if (internalCtpCustomSizeFields) {
                internalCtpCustomSizeFields.style.display = 'none'; // إخفاء حقول المقاس المخصص دائمًا
            }
            
            this.updateInternalPlatePrice();
        });
        
        // الاستماع لتغييرات حقول تكلفة الزنكات للمحتوى الداخلي
        const internalCtpCostFields = ['id_internal_ctp_plates_count', 'id_internal_ctp_plate_price', 'id_internal_ctp_transportation'];
        internalCtpCostFields.forEach(fieldId => {
            PricingSystem.EventBus.on(`field:${fieldId}:changed`, (data) => {
                this.calculateInternalCTPCost();
            });
        });
        
        // الاستماع لتغييرات أوجه الطباعة وعدد الألوان للغلاف
        PricingSystem.EventBus.on('field:id_print_sides:changed', (data) => {
            this.calculatePlatesCount();
        });
        
        const colorFields = ['id_colors_design', 'id_colors_front', 'id_colors_back'];
        colorFields.forEach(fieldId => {
            PricingSystem.EventBus.on(`field:${fieldId}:changed`, (data) => {
                this.calculatePlatesCount();
            });
        });
        
        // الاستماع لتغييرات أوجه الطباعة وعدد الألوان للمحتوى الداخلي
        PricingSystem.EventBus.on('field:id_internal_print_sides:changed', (data) => {
            this.calculateInternalPlatesCount();
        });
        
        const internalColorFields = ['id_internal_colors_design', 'id_internal_colors_front', 'id_internal_colors_back'];
        internalColorFields.forEach(fieldId => {
            PricingSystem.EventBus.on(`field:${fieldId}:changed`, (data) => {
                this.calculateInternalPlatesCount();
            });
        });
        
        // الاستماع لتحديثات الحقول المتعلقة بالزنكات
        PricingSystem.EventBus.on('fields:updated', (data) => {
            const ctpRelatedFields = [
                'id_print_sides', 'id_colors_design', 'id_colors_front', 'id_colors_back',
                'id_ctp_supplier', 'id_ctp_plate_size', 'id_ctp_plates_count', 'id_ctp_plate_price',
                'id_ctp_transportation'
            ];
            
            const shouldUpdateCtp = data.changedFields.some(field => 
                ctpRelatedFields.includes(field)
            );
            
            if (shouldUpdateCtp) {
                this.calculatePlatesCount();
                this.calculateCTPCost();
            }
            
            const internalCtpRelatedFields = [
                'id_internal_print_sides', 'id_internal_colors_design', 'id_internal_colors_front',
                'id_internal_colors_back', 'id_internal_ctp_supplier', 'id_internal_ctp_plate_size',
                'id_internal_ctp_plates_count', 'id_internal_ctp_plate_price', 'id_internal_ctp_transportation'
            ];
            
            const shouldUpdateInternalCtp = data.changedFields.some(field => 
                internalCtpRelatedFields.includes(field)
            );
            
            if (shouldUpdateInternalCtp) {
                this.calculateInternalPlatesCount();
                this.calculateInternalCTPCost();
            }
        });
    },
    
    /**
     * تهيئة معالجات أحداث الزنكات للغلاف
     */
    setupCoverCTPHandlers: function() {
        // الحصول على عناصر الزنكات
        const ctpSupplierSelect = document.getElementById('id_ctp_supplier');
        const ctpPlateSizeSelect = document.getElementById('id_ctp_plate_size');
        const ctpPlatesCountInput = document.getElementById('id_ctp_plates_count');
        const ctpPlatePriceInput = document.getElementById('id_ctp_plate_price');
        const ctpTransportationInput = document.getElementById('id_ctp_transportation');
        const ctpTotalCostInput = document.getElementById('id_ctp_total_cost');
        const ctpCustomSizeFields = document.getElementById('ctp-custom-size-fields');
        
        // التحقق من وجود العناصر
        if (!ctpSupplierSelect || !ctpPlateSizeSelect || !ctpPlatesCountInput || !ctpPlatePriceInput || !ctpTransportationInput || !ctpTotalCostInput) {
            return;
        }
        
        // إذا كان نظام ناقل الأحداث متاحًا، فلا داعي لإضافة مستمعات أحداث تقليدية
        if (PricingSystem.EventBus) {
            return;
        }
        
        // إضافة معالج حدث لتغيير مورد الزنكات
        ctpSupplierSelect.addEventListener('change', () => {
            // إذا تم إعادة تعيين المورد (اختيار قيمة فارغة)، نقوم بمسح قائمة مقاسات الزنك وحقول السعر
            if (!ctpSupplierSelect.value) {
                ctpPlateSizeSelect.innerHTML = '<option value="">-- اختر مقاس الزنك --</option>';
                ctpPlateSizeSelect.disabled = true;
                ctpPlatePriceInput.value = '';
                this.calculateCTPCost();
                return;
            }
            
            // تحميل مقاسات الزنكات للمورد المختار
            this.loadPlateSizes(ctpSupplierSelect.value, ctpPlateSizeSelect);
            this.updatePlatePrice();
        });
        
        // إضافة معالج حدث لتغيير مقاس الزنك
        ctpPlateSizeSelect.addEventListener('change', () => {
            // إظهار/إخفاء حقول المقاس المخصص - تم إلغاء هذه الميزة
            if (ctpCustomSizeFields) {
                ctpCustomSizeFields.style.display = 'none'; // إخفاء حقول المقاس المخصص دائمًا
            }
            
            this.updatePlatePrice();
        });
        
        // إضافة معالجات أحداث لحساب التكلفة الإجمالية
        ctpPlatesCountInput.addEventListener('change', this.calculateCTPCost.bind(this));
        ctpPlatesCountInput.addEventListener('input', this.calculateCTPCost.bind(this));
        ctpPlatePriceInput.addEventListener('change', this.calculateCTPCost.bind(this));
        ctpPlatePriceInput.addEventListener('input', this.calculateCTPCost.bind(this));
        ctpTransportationInput.addEventListener('change', this.calculateCTPCost.bind(this));
        ctpTransportationInput.addEventListener('input', this.calculateCTPCost.bind(this));
        
        // حساب عدد الزنكات عند تغيير عدد الألوان أو أوجه الطباعة
        const printSidesSelect = document.getElementById('id_print_sides');
        const colorsDesignInput = document.getElementById('id_colors_design');
        const colorsFrontInput = document.getElementById('id_colors_front');
        const colorsBackInput = document.getElementById('id_colors_back');
        
        if (printSidesSelect) {
            printSidesSelect.addEventListener('change', this.calculatePlatesCount.bind(this));
        }
        
        if (colorsDesignInput) {
            colorsDesignInput.addEventListener('change', this.calculatePlatesCount.bind(this));
            colorsDesignInput.addEventListener('input', this.calculatePlatesCount.bind(this));
        }
        
        if (colorsFrontInput) {
            colorsFrontInput.addEventListener('change', this.calculatePlatesCount.bind(this));
            colorsFrontInput.addEventListener('input', this.calculatePlatesCount.bind(this));
        }
        
        if (colorsBackInput) {
            colorsBackInput.addEventListener('change', this.calculatePlatesCount.bind(this));
            colorsBackInput.addEventListener('input', this.calculatePlatesCount.bind(this));
        }
    },
    
    /**
     * تهيئة معالجات أحداث الزنكات للمحتوى الداخلي
     */
    setupInternalCTPHandlers: function() {
        // الحصول على عناصر الزنكات للمحتوى الداخلي
        const internalCtpSupplierSelect = document.getElementById('id_internal_ctp_supplier');
        const internalCtpPlateSizeSelect = document.getElementById('id_internal_ctp_plate_size');
        const internalCtpPlatesCountInput = document.getElementById('id_internal_ctp_plates_count');
        const internalCtpPlatePriceInput = document.getElementById('id_internal_ctp_plate_price');
        const internalCtpTransportationInput = document.getElementById('id_internal_ctp_transportation');
        const internalCtpTotalCostInput = document.getElementById('id_internal_ctp_total_cost');
        const internalCtpCustomSizeFields = document.getElementById('internal-ctp-custom-size-fields');
        
        // التحقق من وجود العناصر
        if (!internalCtpSupplierSelect || !internalCtpPlateSizeSelect || !internalCtpPlatesCountInput || !internalCtpPlatePriceInput || !internalCtpTransportationInput || !internalCtpTotalCostInput) {
            return;
        }
        
        // إضافة معالج حدث لتغيير مورد الزنكات
        internalCtpSupplierSelect.addEventListener('change', () => {
            // إذا تم إعادة تعيين المورد (اختيار قيمة فارغة)، نقوم بمسح قائمة مقاسات الزنك وحقول السعر
            if (!internalCtpSupplierSelect.value) {
                internalCtpPlateSizeSelect.innerHTML = '<option value="">-- اختر مقاس الزنك --</option>';
                internalCtpPlateSizeSelect.disabled = true;
                internalCtpPlatePriceInput.value = '';
                this.calculateInternalCTPCost();
                return;
            }
            
            // تحميل مقاسات الزنكات للمورد المختار
            this.loadPlateSizes(internalCtpSupplierSelect.value, internalCtpPlateSizeSelect);
            this.updateInternalPlatePrice();
        });
        
        // إضافة معالج حدث لتغيير مقاس الزنك
        internalCtpPlateSizeSelect.addEventListener('change', () => {
            // إظهار/إخفاء حقول المقاس المخصص - تم إلغاء هذه الميزة
            if (internalCtpCustomSizeFields) {
                internalCtpCustomSizeFields.style.display = 'none'; // إخفاء حقول المقاس المخصص دائمًا
            }
            
            this.updateInternalPlatePrice();
        });
        
        // إضافة معالجات أحداث لحساب التكلفة الإجمالية
        internalCtpPlatesCountInput.addEventListener('change', this.calculateInternalCTPCost.bind(this));
        internalCtpPlatesCountInput.addEventListener('input', this.calculateInternalCTPCost.bind(this));
        internalCtpPlatePriceInput.addEventListener('change', this.calculateInternalCTPCost.bind(this));
        internalCtpPlatePriceInput.addEventListener('input', this.calculateInternalCTPCost.bind(this));
        internalCtpTransportationInput.addEventListener('change', this.calculateInternalCTPCost.bind(this));
        internalCtpTransportationInput.addEventListener('input', this.calculateInternalCTPCost.bind(this));
        
        // حساب عدد الزنكات عند تغيير عدد الألوان أو أوجه الطباعة
        const internalPrintSidesSelect = document.getElementById('id_internal_print_sides');
        const internalColorsDesignInput = document.getElementById('id_internal_colors_design');
        const internalColorsFrontInput = document.getElementById('id_internal_colors_front');
        const internalColorsBackInput = document.getElementById('id_internal_colors_back');
        
        if (internalPrintSidesSelect) {
            internalPrintSidesSelect.addEventListener('change', this.calculateInternalPlatesCount.bind(this));
        }
        
        if (internalColorsDesignInput) {
            internalColorsDesignInput.addEventListener('change', this.calculateInternalPlatesCount.bind(this));
            internalColorsDesignInput.addEventListener('input', this.calculateInternalPlatesCount.bind(this));
        }
        
        if (internalColorsFrontInput) {
            internalColorsFrontInput.addEventListener('change', this.calculateInternalPlatesCount.bind(this));
            internalColorsFrontInput.addEventListener('input', this.calculateInternalPlatesCount.bind(this));
        }
        
        if (internalColorsBackInput) {
            internalColorsBackInput.addEventListener('change', this.calculateInternalPlatesCount.bind(this));
            internalColorsBackInput.addEventListener('input', this.calculateInternalPlatesCount.bind(this));
        }
    },
    
    /**
     * تحميل مقاسات الزنكات المتاحة لمورد محدد
     * @param {string} supplierId - معرف المورد
     * @param {HTMLSelectElement} plateSizeSelect - عنصر قائمة مقاسات الزنكات
     */
    loadPlateSizes: function(supplierId, plateSizeSelect) {
        if (!plateSizeSelect) {
            return;
        }
        
        // تعطيل القائمة أثناء التحميل
        plateSizeSelect.disabled = true;
        
        // مسح الخيارات الحالية
        plateSizeSelect.innerHTML = '<option value="">-- اختر المقاس --</option>';
        
        // التحقق من وجود معرف المورد
        if (!supplierId) {
            // إذا لم يتم اختيار مورد، نعيد تفعيل القائمة ونتوقف
            plateSizeSelect.disabled = false;
            return;
        }
        
        // استدعاء API للحصول على مقاسات الزنكات المتاحة
        fetch(`/pricing/api/plate-sizes/?supplier_id=${supplierId}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`فشل الطلب بكود الحالة: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                // إعادة تمكين القائمة
                plateSizeSelect.disabled = false;
                
                if (data.success && data.plate_sizes && data.plate_sizes.length > 0) {
                    // إضافة مقاسات الزنكات إلى القائمة
                    data.plate_sizes.forEach((plateSize, index) => {
                        const option = document.createElement('option');
                        option.value = plateSize.id;
                        
                        // استخدام اسم الخدمة إذا كان متاحًا أو مقاس الزنك كاحتياطي
                        if (plateSize.service_name) {
                            option.text = plateSize.service_name;
                        } else {
                            // استخدام الاسم فقط بدلاً من النص الكامل كخطة احتياطية
                            option.text = plateSize.name.split('(')[0].trim();
                        }
                        
                        option.dataset.price = plateSize.price;
                        plateSizeSelect.appendChild(option);
                    });
                    
                    // تحديد أول خيار بشكل تلقائي إذا كان هناك خيارات متاحة
                    if (plateSizeSelect.options.length > 1) {
                        plateSizeSelect.selectedIndex = 1; // اختيار الخيار الأول بعد "-- اختر المقاس --"
                        
                        // تفعيل حدث التغيير لتحديث السعر وباقي الحقول
                        // استخدام dispatchEvent لضمان تنفيذ معالجات الأحداث المرتبطة
                        plateSizeSelect.dispatchEvent(new Event('change'));
                    }
                }
            })
            .catch(error => {
                console.error('خطأ في استدعاء API لمقاسات الزنكات:', error);
                // إعادة تمكين القائمة
                plateSizeSelect.disabled = false;
            });
    },
    
    /**
     * تحديث سعر الزنك للمحتوى الداخلي
     */
    updateInternalPlatePrice: function() {
        const internalCtpSupplierSelect = document.getElementById('id_internal_ctp_supplier');
        const internalCtpPlateSizeSelect = document.getElementById('id_internal_ctp_plate_size');
        const internalCtpPlatePriceInput = document.getElementById('id_internal_ctp_plate_price');
        
        if (!internalCtpSupplierSelect || !internalCtpPlateSizeSelect || !internalCtpPlatePriceInput) {
            return;
        }
        
        const supplierId = internalCtpSupplierSelect.value;
        const plateSizeId = internalCtpPlateSizeSelect.value;
        
        // التحقق من وجود المورد ومقاس الزنك
        if (!supplierId || !plateSizeId) {
            return;
        }
        
        // محاولة الحصول على السعر من البيانات المخزنة في القائمة
        const selectedOption = internalCtpPlateSizeSelect.options[internalCtpPlateSizeSelect.selectedIndex];
        if (selectedOption && selectedOption.dataset.price) {
            internalCtpPlatePriceInput.value = selectedOption.dataset.price;
            // تحديث التكلفة الإجمالية
            this.calculateInternalCTPCost();
            return;
        }
        
        // استدعاء API للحصول على سعر الزنك
        fetch(`/pricing/api/plate-price/?supplier_id=${supplierId}&plate_size_id=${plateSizeId}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`فشل الطلب بكود الحالة: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                if (data.success) {
                    // تحديث سعر الزنك
                    internalCtpPlatePriceInput.value = data.price || '';
                    // تحديث التكلفة الإجمالية
                    this.calculateInternalCTPCost();
                }
            })
            .catch(error => {
                console.error('خطأ في استدعاء API لسعر الزنك:', error);
            });
    },
    
    /**
     * حساب عدد الزنكات للغلاف
     */
    calculatePlatesCount: function() {
        const printSidesSelect = document.getElementById('id_print_sides');
        const colorsDesignInput = document.getElementById('id_colors_design');
        const colorsFrontInput = document.getElementById('id_colors_front');
        const colorsBackInput = document.getElementById('id_colors_back');
        const ctpPlatesCountInput = document.getElementById('id_ctp_plates_count');
        
        if (!printSidesSelect || !ctpPlatesCountInput) {
            return;
        }
        
        const printSides = printSidesSelect.value;
        let totalPlates = 0;
        
        // حساب عدد الزنكات حسب أوجه الطباعة وعدد الألوان
        if (printSides === '1' || printSides === '3') {
            // وجه واحد أو وجهين متطابقين
            if (colorsDesignInput && colorsDesignInput.value) {
                totalPlates = parseInt(colorsDesignInput.value) || 0;
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
            
            totalPlates = frontColors + backColors;
        }
        
        // تحديث حقل عدد الزنكات
        ctpPlatesCountInput.value = totalPlates;
        
        // تحديث التكلفة الإجمالية
        this.calculateCTPCost();
    },
    
    /**
     * حساب عدد الزنكات للمحتوى الداخلي
     */
    calculateInternalPlatesCount: function() {
        const internalPrintSidesSelect = document.getElementById('id_internal_print_sides');
        const internalColorsDesignInput = document.getElementById('id_internal_colors_design');
        const internalColorsFrontInput = document.getElementById('id_internal_colors_front');
        const internalColorsBackInput = document.getElementById('id_internal_colors_back');
        const internalCtpPlatesCountInput = document.getElementById('id_internal_ctp_plates_count');
        
        if (!internalPrintSidesSelect || !internalCtpPlatesCountInput) {
            return;
        }
        
        const printSides = internalPrintSidesSelect.value;
        let totalPlates = 0;
        
        // حساب عدد الزنكات حسب أوجه الطباعة وعدد الألوان
        if (printSides === '1' || printSides === '3') {
            // وجه واحد أو وجهين متطابقين
            if (internalColorsDesignInput && internalColorsDesignInput.value) {
                totalPlates = parseInt(internalColorsDesignInput.value) || 0;
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
            
            totalPlates = frontColors + backColors;
        }
        
        // تحديث حقل عدد الزنكات
        internalCtpPlatesCountInput.value = totalPlates;
        
        // تحديث التكلفة الإجمالية
        this.calculateInternalCTPCost();
    },
    
    /**
     * حساب التكلفة الإجمالية للزنكات للغلاف
     */
    calculateCTPCost: function() {
        const ctpPlatesCountInput = document.getElementById('id_ctp_plates_count');
        const ctpPlatePriceInput = document.getElementById('id_ctp_plate_price');
        const ctpTransportationInput = document.getElementById('id_ctp_transportation');
        const ctpTotalCostInput = document.getElementById('id_ctp_total_cost');
        const platesCostSummaryInput = document.getElementById('id_plates_cost_summary');
        
        if (!ctpPlatesCountInput || !ctpPlatePriceInput || !ctpTransportationInput || !ctpTotalCostInput) {
            return;
        }
        
        const platesCount = parseInt(ctpPlatesCountInput.value) || 0;
        const platePrice = parseFloat(ctpPlatePriceInput.value) || 0;
        const transportation = parseFloat(ctpTransportationInput.value) || 0;
        
        // حساب التكلفة الإجمالية
        const totalCost = (platesCount * platePrice) + transportation;
        
        // تحديث حقل التكلفة الإجمالية
        ctpTotalCostInput.value = totalCost.toFixed(2);
        
        // تحديث حقل تكلفة الزنكات في قسم التسعير
        if (platesCostSummaryInput) {
            platesCostSummaryInput.value = totalCost.toFixed(2);
        }
        
        // تحديث إجمالي التكلفة
        if (typeof PricingSystem.Pricing !== 'undefined' && typeof PricingSystem.Pricing.calculateCost === 'function') {
            PricingSystem.Pricing.calculateCost();
        }
    },
    
    /**
     * حساب التكلفة الإجمالية للزنكات للمحتوى الداخلي
     */
    calculateInternalCTPCost: function() {
        const internalCtpPlatesCountInput = document.getElementById('id_internal_ctp_plates_count');
        const internalCtpPlatePriceInput = document.getElementById('id_internal_ctp_plate_price');
        const internalCtpTransportationInput = document.getElementById('id_internal_ctp_transportation');
        const internalCtpTotalCostInput = document.getElementById('id_internal_ctp_total_cost');
        const internalPlatesCostSummaryInput = document.getElementById('id_internal_plates_cost_summary');
        
        if (!internalCtpPlatesCountInput || !internalCtpPlatePriceInput || !internalCtpTransportationInput || !internalCtpTotalCostInput) {
            return;
        }
        
        const platesCount = parseInt(internalCtpPlatesCountInput.value) || 0;
        const platePrice = parseFloat(internalCtpPlatePriceInput.value) || 0;
        const transportation = parseFloat(internalCtpTransportationInput.value) || 0;
        
        // حساب التكلفة الإجمالية
        const totalCost = (platesCount * platePrice) + transportation;
        
        // تحديث حقل التكلفة الإجمالية
        internalCtpTotalCostInput.value = totalCost.toFixed(2);
        
        // تحديث حقل تكلفة الزنكات في قسم التسعير
        if (internalPlatesCostSummaryInput) {
            internalPlatesCostSummaryInput.value = totalCost.toFixed(2);
        }
        
        // تحديث إجمالي التكلفة
        if (typeof PricingSystem.Pricing !== 'undefined' && typeof PricingSystem.Pricing.calculateCost === 'function') {
            PricingSystem.Pricing.calculateCost();
        }
    },
    
    /**
     * تهيئة حقول الزنكات عند تحميل الصفحة
     */
    init: function() {
        // تحميل مقاسات الزنكات الأولية للغلاف
        const ctpPlateSizeSelect = document.getElementById('id_ctp_plate_size');
        if (ctpPlateSizeSelect && ctpPlateSizeSelect.options.length <= 1) {
            // إذا كان الحقل فارغ، حمل جميع المقاسات المتاحة
            this.loadPlateSizes('', ctpPlateSizeSelect);
        }
        
        // تحميل مقاسات الزنكات الأولية للمحتوى الداخلي
        const internalCtpPlateSizeSelect = document.getElementById('id_internal_ctp_plate_size');
        if (internalCtpPlateSizeSelect && internalCtpPlateSizeSelect.options.length <= 1) {
            // إذا كان الحقل فارغ، حمل جميع المقاسات المتاحة
            this.loadPlateSizes('', internalCtpPlateSizeSelect);
        }
    },
    
    /**
     * إعداد معالجات الأحداث للزنكات
     */
    setupEventHandlers: function() {
        // معالج تغيير مورد الزنكات للغلاف
        const ctpSupplierSelect = document.getElementById('id_ctp_supplier');
        if (ctpSupplierSelect) {
            ctpSupplierSelect.addEventListener('change', () => {
                const ctpPlateSizeSelect = document.getElementById('id_ctp_plate_size');
                if (ctpPlateSizeSelect) {
                    // تحميل مقاسات الزنكات للمورد المختار
                    this.loadPlateSizes(ctpSupplierSelect.value, ctpPlateSizeSelect);
                }
            });
        }
        
        // معالج تغيير مقاس الزنك للغلاف
        const ctpPlateSizeSelect = document.getElementById('id_ctp_plate_size');
        if (ctpPlateSizeSelect) {
            ctpPlateSizeSelect.addEventListener('change', () => {
                this.updatePlatePrice();
            });
        }
        
        // معالج تغيير مورد الزنكات للمحتوى الداخلي
        const internalCtpSupplierSelect = document.getElementById('id_internal_ctp_supplier');
        if (internalCtpSupplierSelect) {
            internalCtpSupplierSelect.addEventListener('change', () => {
                const internalCtpPlateSizeSelect = document.getElementById('id_internal_ctp_plate_size');
                if (internalCtpPlateSizeSelect) {
                    // تحميل مقاسات الزنكات للمورد المختار
                    this.loadPlateSizes(internalCtpSupplierSelect.value, internalCtpPlateSizeSelect);
                }
            });
        }
        
        // معالج تغيير مقاس الزنك للمحتوى الداخلي
        const internalCtpPlateSizeSelect = document.getElementById('id_internal_ctp_plate_size');
        if (internalCtpPlateSizeSelect) {
            internalCtpPlateSizeSelect.addEventListener('change', () => {
                this.updateInternalPlatePrice();
            });
        }
    }
};