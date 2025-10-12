/**
 * finishing-handlers.js - دالات معالجة خدمات ما بعد الطباعة
 * 
 * تم تحديث هذا الملف لمنع أخطاء "Cannot read properties of null (reading 'options')"
 * من خلال التحقق من وجود عناصر القائمة المنسدلة وخياراتها قبل محاولة الوصول إليها.
 * تم إضافة فحوصات في جميع المواضع التي تستخدم .options[element.selectedIndex].
 */

// تعريف كائن عام للمشروع إذا لم يكن موجودًا
window.PricingSystem = window.PricingSystem || {};

// تعريف وحدة معالجة خدمات ما بعد الطباعة
PricingSystem.Finishing = {
    /**
     * تهيئة خدمات ما بعد الطباعة
     */
    setupFinishingServices: function() {
        // تهيئة خدمة التغطية
        this.setupCoatingService();
        // تهيئة خدمة التقطيع
        this.setupCuttingService();
        // تهيئة خدمة التجليد
        this.setupBindingService();
        // تهيئة خدمة الطي
        this.setupFoldingService();
        // تهيئة خدمة التخريم
        this.setupPunchingService();
        // تهيئة خدمة التطبيق
        this.setupLaminationService();
        // تهيئة خدمة الـ Die Cut
        this.setupDieCutService();
        // تهيئة خدمة الـ Spot UV
        this.setupSpotUvService();
        // تهيئة الخدمات الإضافية
        this.setupAdditionalServices();
        
        // استخدام الدالة الموحدة لإعداد الخدمات
        this.setupUnifiedFinishingServices();
        
        // إصلاح مشكلة مربعات الاختيار
        this.fixFinishingCheckboxes();
        
        // تسجيل معالجات الأحداث مع ناقل الأحداث إذا كان متاحًا
        if (PricingSystem.EventBus) {
            this.registerEventHandlers();
        }
    },
    
    /**
     * إعداد معالجات الأحداث
     */
    setupEventHandlers: function() {
        // تسجيل معالجات الأحداث مع ناقل الأحداث إذا كان متاحًا
        if (PricingSystem.EventBus) {
            this.registerEventHandlers();
        } else {
            // إعداد معالجات الأحداث التقليدية
            this.setupFinishingServices();
        }
    },
    
    /**
     * تسجيل معالجات الأحداث مع ناقل الأحداث
     */
    registerEventHandlers: function() {
        // تسجيل معالجات لمربعات اختيار خدمات ما بعد الطباعة
        const finishingCheckboxes = [
            'id_coating_enabled', 'id_cutting_enabled', 'id_binding_enabled',
            'id_folding_enabled', 'id_punching_enabled', 'id_lamination_enabled',
            'id_die_cut_enabled', 'id_spot_uv_enabled', 'coating_service_checkbox',
            'folding_service', 'die_cut_service', 'spot_uv_service'
        ];
        
        // إضافة مستمعات لتغييرات مربعات الاختيار
        finishingCheckboxes.forEach(checkboxId => {
            PricingSystem.EventBus.on(`field:${checkboxId}:changed`, (data) => {
                // تحديث عرض قسم التفاصيل المرتبط بمربع الاختيار
                const detailsId = this.getDetailsElementId(checkboxId);
                if (detailsId) {
                    const detailsElement = document.getElementById(detailsId);
                    if (detailsElement) {
                        detailsElement.style.display = data.value ? 'block' : 'none';
                    }
                }
                
                // إعادة حساب التكلفة الإجمالية لخدمات ما بعد الطباعة
                this.calculateTotalFinishingCost();
            });
        });
        
        // الاستماع لتغييرات موردي الخدمات
        const supplierFields = [
            'id_coating_supplier', 'id_cutting_supplier', 'id_binding_supplier',
            'id_folding_supplier', 'id_punching_supplier', 'id_lamination_supplier',
            'id_die_cut_supplier', 'id_spot_uv_supplier'
        ];
        
        supplierFields.forEach(fieldId => {
            PricingSystem.EventBus.on(`field:${fieldId}:changed`, (data) => {
                // استخراج نوع الخدمة من معرف الحقل
                const serviceType = fieldId.replace('id_', '').replace('_supplier', '');
                // تحديث سعر الخدمة
                if (typeof PricingSystem.API !== 'undefined' && typeof PricingSystem.API.updateServicePrice === 'function') {
                    PricingSystem.API.updateServicePrice(serviceType, data.value);
                }
            });
        });
        
        // الاستماع لتغييرات أنواع الخدمات
        const typeFields = [
            'id_coating_type', 'id_binding_type', 'id_folding_type',
            'id_punching_type', 'id_lamination_type'
        ];
        
        typeFields.forEach(fieldId => {
            PricingSystem.EventBus.on(`field:${fieldId}:changed`, (data) => {
                // استخراج نوع الخدمة من معرف الحقل
                const serviceType = fieldId.replace('id_', '').replace('_type', '');
                // الحصول على حقل المورد المرتبط
                const supplierFieldId = `id_${serviceType}_supplier`;
                const supplierField = document.getElementById(supplierFieldId);
                
                if (supplierField && supplierField.value) {
                    // تحديث سعر الخدمة
                    if (typeof PricingSystem.API !== 'undefined' && typeof PricingSystem.API.updateServicePrice === 'function') {
                        PricingSystem.API.updateServicePrice(serviceType, supplierField.value);
                    }
                }
            });
        });
        
        // الاستماع لتغييرات أسعار وكميات الخدمات
        const priceFields = [
            'id_coating_price', 'id_cutting_price', 'id_binding_price',
            'id_folding_price', 'id_punching_price', 'id_lamination_price',
            'id_die_cut_price', 'id_spot_uv_price'
        ];
        
        const quantityFields = [
            'id_coating_quantity', 'id_cutting_quantity', 'id_binding_quantity',
            'id_folding_quantity', 'id_punching_quantity', 'id_lamination_quantity',
            'id_die_cut_quantity', 'id_spot_uv_quantity'
        ];
        
        // إضافة مستمعات لتغييرات الأسعار والكميات
        [...priceFields, ...quantityFields].forEach(fieldId => {
            PricingSystem.EventBus.on(`field:${fieldId}:changed`, (data) => {
                // استخراج نوع الخدمة من معرف الحقل
                const serviceType = fieldId.replace('id_', '').replace('_price', '').replace('_quantity', '');
                // حساب تكلفة الخدمة
                this.calculateServiceCost(serviceType);
            });
        });
        
        // الاستماع لتغييرات الكمية وعدد الأفرخ لتحديث تكلفة التغطية
        PricingSystem.EventBus.on('field:id_quantity:changed', (data) => {
            // تحديث عدد أفرخ الورق أولاً
            if (PricingSystem.Paper && typeof PricingSystem.Paper.calculatePaperSheetsDirectly === 'function') {
                PricingSystem.Paper.calculatePaperSheetsDirectly();
            }
            
            // تحديث تكلفة التغطية بناءً على عدد الأفرخ الجديد
            this.updateCoatingTotalBasedOnSheets();
        });
        
        // الاستماع لتغييرات عدد أفرخ الورق لتحديث تكلفة التغطية
        PricingSystem.EventBus.on('field:id_paper_sheets_count:changed', (data) => {
            this.updateCoatingTotalBasedOnSheets();
        });
        
        // الاستماع لتغييرات الكمية وعدد الأفرخ للمحتوى الداخلي
        PricingSystem.EventBus.on('field:id_internal_paper_sheets_count:changed', (data) => {
            this.updateInternalCoatingTotalBasedOnSheets();
        });
        
        // الاستماع لتحديثات الحقول المتعلقة بالتغطية
        PricingSystem.EventBus.on('fields:updated', (data) => {
            const coatingRelatedFields = [
                'id_quantity', 'id_paper_sheets_count', 'coating_service_select',
                'coating_sides', 'coating_price'
            ];
            
            const shouldUpdateCoating = data.changedFields.some(field => 
                coatingRelatedFields.includes(field)
            );
            
            if (shouldUpdateCoating) {
                this.updateCoatingTotalBasedOnSheets();
            }
        });
    },
    
    /**
     * الحصول على معرف عنصر التفاصيل المرتبط بمربع اختيار
     * @param {string} checkboxId - معرف مربع الاختيار
     * @returns {string|null} - معرف عنصر التفاصيل أو null إذا لم يتم العثور عليه
     */
    getDetailsElementId: function(checkboxId) {
        const mapping = {
            'id_coating_enabled': 'coating_section',
            'id_cutting_enabled': 'cutting_section',
            'id_binding_enabled': 'binding_section',
            'id_folding_enabled': 'folding_section',
            'id_punching_enabled': 'punching_section',
            'id_lamination_enabled': 'lamination_section',
            'id_die_cut_enabled': 'die_cut_section',
            'id_spot_uv_enabled': 'spot_uv_section',
            'coating_service_checkbox': 'coating_service_details',
            'folding_service': 'folding_service_details',
            'die_cut_service': 'die_cut_service_details',
            'spot_uv_service': 'spot_uv_service_details'
        };
        
        return mapping[checkboxId] || null;
    },
    
    /**
     * حساب تكلفة خدمة معينة
     * @param {string} serviceType - نوع الخدمة (coating, cutting, binding, etc.)
     */
    calculateServiceCost: function(serviceType) {
        const priceInput = document.getElementById(`id_${serviceType}_price`);
        const quantityInput = document.getElementById(`id_${serviceType}_quantity`);
        const totalCostInput = document.getElementById(`id_${serviceType}_total_cost`);
        
        if (priceInput && quantityInput && totalCostInput) {
            const price = parseFloat(priceInput.value) || 0;
            const quantity = parseInt(quantityInput.value) || 0;
            const totalCost = price * quantity;
            totalCostInput.value = totalCost.toFixed(2);
            
            // إعادة حساب التكلفة الإجمالية لخدمات ما بعد الطباعة
            this.calculateTotalFinishingCost();
        }
    },
    
    /**
     * إصلاح مشكلة مربعات الاختيار في خدمات ما بعد الطباعة
     */
    fixFinishingCheckboxes: function() {
        // تعريف مربعات الاختيار وعناصر التفاصيل المقابلة لها
        const checkboxMappings = [
            { checkbox: 'coating_service_checkbox', details: 'coating_service_details' },
            { checkbox: 'folding_service', details: 'folding_service_details' },
            { checkbox: 'die_cut_service', details: 'die_cut_service_details' },
            { checkbox: 'spot_uv_service', details: 'spot_uv_service_details' }
        ];
        
        // إضافة مستمعي الأحداث لكل مربع اختيار
        checkboxMappings.forEach(mapping => {
            const checkbox = document.getElementById(mapping.checkbox);
            const detailsElement = document.getElementById(mapping.details);
            
            if (checkbox && detailsElement) {
                // إذا كان نظام ناقل الأحداث متاحًا، فلا داعي لإضافة مستمعات أحداث تقليدية
                if (PricingSystem.EventBus) {
                    // تطبيق الحالة الأولية فقط
                    detailsElement.style.display = checkbox.checked ? 'block' : 'none';
                    return;
                }
                
                // إضافة مستمع حدث click لمعالجة النقر المباشر
                checkbox.addEventListener('click', function() {
                    detailsElement.style.display = this.checked ? 'block' : 'none';
                });
                
                // إضافة مستمع حدث change لمعالجة التغييرات الأخرى
                checkbox.addEventListener('change', function() {
                    detailsElement.style.display = this.checked ? 'block' : 'none';
                    
                    // تحديث إجمالي تكلفة خدمات مابعد الطباعة
                    PricingSystem.Finishing.calculateTotalFinishingCost();
                });
                
                // تطبيق الحالة الأولية
                detailsElement.style.display = checkbox.checked ? 'block' : 'none';
            }
        });
        
        // إضافة مستمع أحداث لجميع مربعات الاختيار بشكل عام
        if (!PricingSystem.EventBus) {
            const allCheckboxes = document.querySelectorAll('.finishing-service-checkbox');
            allCheckboxes.forEach(checkbox => {
                checkbox.addEventListener('change', function() {
                    console.log('تم تغيير حالة مربع اختيار:', this.id, 'الحالة الجديدة:', this.checked);
                });
            });
        }
    },
    
    /**
     * تهيئة خدمة التغطية
     */
    setupCoatingService: function() {
        const coatingCheckbox = document.getElementById('id_coating_enabled');
        const coatingSection = document.getElementById('coating_section');
        const coatingSupplierSelect = document.getElementById('id_coating_supplier');
        const coatingTypeSelect = document.getElementById('id_coating_type');
        const coatingPriceInput = document.getElementById('id_coating_price');
        const coatingQuantityInput = document.getElementById('id_coating_quantity');
        const coatingTotalCostInput = document.getElementById('id_coating_total_cost');
        
        if (!coatingCheckbox || !coatingSection) {
            return;
        }
        
        // إظهار أو إخفاء قسم التغطية بناءً على حالة مربع الاختيار
        coatingCheckbox.addEventListener('change', function() {
            coatingSection.style.display = this.checked ? 'block' : 'none';
            // إعادة حساب التكلفة الإجمالية لخدمات ما بعد الطباعة
            PricingSystem.Finishing.calculateTotalFinishingCost();
        });
        
        // تحميل موردي خدمة التغطية
        if (coatingSupplierSelect) {
            PricingSystem.API.loadSuppliers('id_coating_supplier', 'coating');
            
            // عند اختيار مورد، قم بتحديث سعر الخدمة
            coatingSupplierSelect.addEventListener('change', function() {
                PricingSystem.API.updateServicePrice('coating', this.value);
            });
        }
        
        // عند تغيير نوع التغطية، قم بتحديث السعر
        if (coatingTypeSelect) {
            coatingTypeSelect.addEventListener('change', function() {
                if (coatingSupplierSelect && coatingSupplierSelect.value) {
                    PricingSystem.API.updateServicePrice('coating', coatingSupplierSelect.value);
                }
            });
        }
        
        // عند تغيير السعر أو الكمية، قم بإعادة حساب التكلفة الإجمالية
        if (coatingPriceInput && coatingQuantityInput && coatingTotalCostInput) {
            const calculateCoatingCost = function() {
                const price = parseFloat(coatingPriceInput.value) || 0;
                const quantity = parseInt(coatingQuantityInput.value) || 0;
                const totalCost = price * quantity;
                coatingTotalCostInput.value = totalCost.toFixed(2);
                // إعادة حساب التكلفة الإجمالية لخدمات ما بعد الطباعة
                PricingSystem.Finishing.calculateTotalFinishingCost();
            };
            
            coatingPriceInput.addEventListener('change', calculateCoatingCost);
            coatingPriceInput.addEventListener('input', calculateCoatingCost);
            coatingQuantityInput.addEventListener('change', calculateCoatingCost);
            coatingQuantityInput.addEventListener('input', calculateCoatingCost);
        }
        
        // تعيين حالة مربع الاختيار الأولية
        if (coatingSection) {
            coatingSection.style.display = coatingCheckbox.checked ? 'block' : 'none';
        }
    },
    
    /**
     * تهيئة خدمة التقطيع
     */
    setupCuttingService: function() {
        const cuttingCheckbox = document.getElementById('id_cutting_enabled');
        const cuttingSection = document.getElementById('cutting_section');
        const cuttingSupplierSelect = document.getElementById('id_cutting_supplier');
        const cuttingPriceInput = document.getElementById('id_cutting_price');
        const cuttingQuantityInput = document.getElementById('id_cutting_quantity');
        const cuttingTotalCostInput = document.getElementById('id_cutting_total_cost');
        
        if (!cuttingCheckbox || !cuttingSection) {
            return;
        }
        
        // إظهار أو إخفاء قسم التقطيع بناءً على حالة مربع الاختيار
        cuttingCheckbox.addEventListener('change', function() {
            cuttingSection.style.display = this.checked ? 'block' : 'none';
            // إعادة حساب التكلفة الإجمالية لخدمات ما بعد الطباعة
            PricingSystem.Finishing.calculateTotalFinishingCost();
        });
        
        // تحميل موردي خدمة التقطيع
        if (cuttingSupplierSelect) {
            PricingSystem.API.loadSuppliers('id_cutting_supplier', 'cutting');
            
            // عند اختيار مورد، قم بتحديث سعر الخدمة
            cuttingSupplierSelect.addEventListener('change', function() {
                PricingSystem.API.updateServicePrice('cutting', this.value);
            });
        }
        
        // عند تغيير السعر أو الكمية، قم بإعادة حساب التكلفة الإجمالية
        if (cuttingPriceInput && cuttingQuantityInput && cuttingTotalCostInput) {
            const calculateCuttingCost = function() {
                const price = parseFloat(cuttingPriceInput.value) || 0;
                const quantity = parseInt(cuttingQuantityInput.value) || 0;
                const totalCost = price * quantity;
                cuttingTotalCostInput.value = totalCost.toFixed(2);
                // إعادة حساب التكلفة الإجمالية لخدمات ما بعد الطباعة
                PricingSystem.Finishing.calculateTotalFinishingCost();
            };
            
            cuttingPriceInput.addEventListener('change', calculateCuttingCost);
            cuttingPriceInput.addEventListener('input', calculateCuttingCost);
            cuttingQuantityInput.addEventListener('change', calculateCuttingCost);
            cuttingQuantityInput.addEventListener('input', calculateCuttingCost);
        }
        
        // تعيين حالة مربع الاختيار الأولية
        if (cuttingSection) {
            cuttingSection.style.display = cuttingCheckbox.checked ? 'block' : 'none';
        }
    },
    
    /**
     * تهيئة خدمة التجليد
     */
    setupBindingService: function() {
        const bindingCheckbox = document.getElementById('id_binding_enabled');
        const bindingSection = document.getElementById('binding_section');
        const bindingSupplierSelect = document.getElementById('id_binding_supplier');
        const bindingTypeSelect = document.getElementById('id_binding_type');
        const bindingPriceInput = document.getElementById('id_binding_price');
        const bindingQuantityInput = document.getElementById('id_binding_quantity');
        const bindingTotalCostInput = document.getElementById('id_binding_total_cost');
        
        if (!bindingCheckbox || !bindingSection) {
            return;
        }
        
        // إظهار أو إخفاء قسم التجليد بناءً على حالة مربع الاختيار
        bindingCheckbox.addEventListener('change', function() {
            bindingSection.style.display = this.checked ? 'block' : 'none';
            // إعادة حساب التكلفة الإجمالية لخدمات ما بعد الطباعة
            PricingSystem.Finishing.calculateTotalFinishingCost();
        });
        
        // تحميل موردي خدمة التجليد
        if (bindingSupplierSelect) {
            PricingSystem.API.loadSuppliers('id_binding_supplier', 'binding');
            
            // عند اختيار مورد، قم بتحديث سعر الخدمة
            bindingSupplierSelect.addEventListener('change', function() {
                PricingSystem.API.updateServicePrice('binding', this.value);
            });
        }
        
        // عند تغيير نوع التجليد، قم بتحديث السعر
        if (bindingTypeSelect) {
            bindingTypeSelect.addEventListener('change', function() {
                if (bindingSupplierSelect && bindingSupplierSelect.value) {
                    PricingSystem.API.updateServicePrice('binding', bindingSupplierSelect.value);
                }
            });
        }
        
        // عند تغيير السعر أو الكمية، قم بإعادة حساب التكلفة الإجمالية
        if (bindingPriceInput && bindingQuantityInput && bindingTotalCostInput) {
            const calculateBindingCost = function() {
                const price = parseFloat(bindingPriceInput.value) || 0;
                const quantity = parseInt(bindingQuantityInput.value) || 0;
                const totalCost = price * quantity;
                bindingTotalCostInput.value = totalCost.toFixed(2);
                // إعادة حساب التكلفة الإجمالية لخدمات ما بعد الطباعة
                PricingSystem.Finishing.calculateTotalFinishingCost();
            };
            
            bindingPriceInput.addEventListener('change', calculateBindingCost);
            bindingPriceInput.addEventListener('input', calculateBindingCost);
            bindingQuantityInput.addEventListener('change', calculateBindingCost);
            bindingQuantityInput.addEventListener('input', calculateBindingCost);
        }
        
        // تعيين حالة مربع الاختيار الأولية
        if (bindingSection) {
            bindingSection.style.display = bindingCheckbox.checked ? 'block' : 'none';
        }
    },
    
    /**
     * تهيئة خدمات إضافية أخرى (الطي، التخريم، التطبيق)
     */
    setupAdditionalServices: function() {
        // قائمة الخدمات الإضافية
        const additionalServices = ['folding', 'punching', 'lamination'];
        
        additionalServices.forEach(service => {
            const checkbox = document.getElementById(`id_${service}_enabled`);
            const section = document.getElementById(`${service}_section`);
            const supplierSelect = document.getElementById(`id_${service}_supplier`);
            const priceInput = document.getElementById(`id_${service}_price`);
            const quantityInput = document.getElementById(`id_${service}_quantity`);
            const totalCostInput = document.getElementById(`id_${service}_total_cost`);
            
            if (!checkbox || !section) {
                return;
            }
            
            // إظهار أو إخفاء قسم الخدمة بناءً على حالة مربع الاختيار
            checkbox.addEventListener('change', function() {
                section.style.display = this.checked ? 'block' : 'none';
                // إعادة حساب التكلفة الإجمالية لخدمات ما بعد الطباعة
                PricingSystem.Finishing.calculateTotalFinishingCost();
            });
            
            // تحميل موردي الخدمة
            if (supplierSelect) {
                PricingSystem.API.loadSuppliers(`id_${service}_supplier`, service);
                
                // عند اختيار مورد، قم بتحديث سعر الخدمة
                supplierSelect.addEventListener('change', function() {
                    PricingSystem.API.updateServicePrice(service, this.value);
                });
            }
            
            // عند تغيير السعر أو الكمية، قم بإعادة حساب التكلفة الإجمالية
            if (priceInput && quantityInput && totalCostInput) {
                const calculateServiceCost = function() {
                    const price = parseFloat(priceInput.value) || 0;
                    const quantity = parseInt(quantityInput.value) || 0;
                    const totalCost = price * quantity;
                    totalCostInput.value = totalCost.toFixed(2);
                    // إعادة حساب التكلفة الإجمالية لخدمات ما بعد الطباعة
                    PricingSystem.Finishing.calculateTotalFinishingCost();
                };
                
                priceInput.addEventListener('change', calculateServiceCost);
                priceInput.addEventListener('input', calculateServiceCost);
                quantityInput.addEventListener('change', calculateServiceCost);
                quantityInput.addEventListener('input', calculateServiceCost);
            }
            
            // تعيين حالة مربع الاختيار الأولية
            if (section) {
                section.style.display = checkbox.checked ? 'block' : 'none';
            }
        });
    },
    
    /**
     * تهيئة خدمة الطي
     */
    setupFoldingService: function() {
        // تم تنفيذها من خلال setupAdditionalServices
    },
    
    /**
     * تهيئة خدمة التخريم
     */
    setupPunchingService: function() {
        // تم تنفيذها من خلال setupAdditionalServices
    },
    
    /**
     * تهيئة خدمة التطبيق
     */
    setupLaminationService: function() {
        // تم تنفيذها من خلال setupAdditionalServices
    },
    
    /**
     * تهيئة خدمة Die Cut
     */
    setupDieCutService: function() {
        const dieCutCheckbox = document.getElementById('id_die_cut_enabled');
        const dieCutSection = document.getElementById('die_cut_section');
        const dieCutSupplierSelect = document.getElementById('id_die_cut_supplier');
        const dieCutServiceSelect = document.getElementById('id_die_cut_service_select');
        const dieCutPriceInput = document.getElementById('id_die_cut_price');
        
        if (!dieCutCheckbox || !dieCutSection) {
            return;
        }
        
        // إظهار أو إخفاء قسم Die Cut بناءً على حالة مربع الاختيار
        dieCutCheckbox.addEventListener('change', function() {
            dieCutSection.style.display = this.checked ? 'block' : 'none';
            // إعادة حساب التكلفة الإجمالية لخدمات ما بعد الطباعة
            PricingSystem.Finishing.calculateTotalFinishingCost();
        });
        
        // تحميل موردي خدمة Die Cut
        if (dieCutSupplierSelect) {
            PricingSystem.API.loadSuppliers('id_die_cut_supplier', 'die_cut');
            
            // عند اختيار مورد، قم بتحميل خدمات Die Cut المتاحة
            dieCutSupplierSelect.addEventListener('change', function() {
                const supplierId = this.value;
                
                // مسح خيارات خدمات Die Cut الحالية
                dieCutServiceSelect.innerHTML = '<option value="">-- اختر نوع الخدمة --</option>';
                dieCutPriceInput.value = '';
                
                if (!supplierId) return;
                
                // استدعاء API للحصول على خدمات المورد المحدد
                fetch(`/pricing/api/die-cut-services/?supplier_id=${supplierId}`)
                    .then(response => response.json())
                    .then(data => {
                        if (data.success && data.services) {
                            // إضافة الخدمات إلى القائمة المنسدلة
                            data.services.forEach(service => {
                                const option = document.createElement('option');
                                option.value = service.id;
                                option.text = service.name;
                                option.dataset.price = service.unit_price;
                                dieCutServiceSelect.appendChild(option);
                            });
                        }
                    })
                    .catch(error => console.error('Error fetching die cut services:', error));
            });
        }
        
        // إضافة مستمع أحداث لتغيير خدمة Die Cut
        if (dieCutServiceSelect) {
            dieCutServiceSelect.addEventListener('change', function() {
                let selectedOption = null;
                if (this.selectedIndex >= 0) {
                    selectedOption = this.options[this.selectedIndex];
                }
                if (selectedOption && selectedOption.dataset.price) {
                    dieCutPriceInput.value = selectedOption.dataset.price;
                    // إعادة حساب التكلفة الإجمالية لخدمات ما بعد الطباعة
                    PricingSystem.Finishing.calculateTotalFinishingCost();
                } else {
                    dieCutPriceInput.value = '';
                }
            });
        }
        
        // تعيين حالة مربع الاختيار الأولية
        if (dieCutSection) {
            dieCutSection.style.display = dieCutCheckbox.checked ? 'block' : 'none';
        }
    },
    
    /**
     * تهيئة خدمة Spot UV
     */
    setupSpotUvService: function() {
        const spotUvCheckbox = document.getElementById('id_spot_uv_enabled');
        const spotUvSection = document.getElementById('spot_uv_section');
        const spotUvSupplierSelect = document.getElementById('id_spot_uv_supplier');
        const spotUvServiceSelect = document.getElementById('id_spot_uv_service_select');
        const spotUvPriceInput = document.getElementById('id_spot_uv_price');
        const spotUvAreaInput = document.getElementById('id_spot_uv_area');
        
        if (!spotUvCheckbox || !spotUvSection) {
            return;
        }
        
        // إظهار أو إخفاء قسم Spot UV بناءً على حالة مربع الاختيار
        spotUvCheckbox.addEventListener('change', function() {
            spotUvSection.style.display = this.checked ? 'block' : 'none';
            // إعادة حساب التكلفة الإجمالية لخدمات ما بعد الطباعة
            PricingSystem.Finishing.calculateTotalFinishingCost();
        });
        
        // تحميل موردي خدمة Spot UV
        if (spotUvSupplierSelect) {
            PricingSystem.API.loadSuppliers('id_spot_uv_supplier', 'spot_uv');
            
            // عند اختيار مورد، قم بتحميل خدمات Spot UV المتاحة
            spotUvSupplierSelect.addEventListener('change', function() {
                const supplierId = this.value;
                
                // مسح خيارات خدمات Spot UV الحالية
                spotUvServiceSelect.innerHTML = '<option value="">-- اختر نوع الخدمة --</option>';
                spotUvPriceInput.value = '';
                
                if (!supplierId) return;
                
                // استدعاء API للحصول على خدمات المورد المحدد
                fetch(`/pricing/api/spot-uv-services/?supplier_id=${supplierId}`)
                    .then(response => response.json())
                    .then(data => {
                        if (data.success && data.services) {
                            // إضافة الخدمات إلى القائمة المنسدلة
                            data.services.forEach(service => {
                                const option = document.createElement('option');
                                option.value = service.id;
                                option.text = service.name;
                                option.dataset.price = service.unit_price;
                                spotUvServiceSelect.appendChild(option);
                            });
                        }
                    })
                    .catch(error => console.error('Error fetching spot UV services:', error));
            });
        }
        
        // دالة لتحديث سعر Spot UV بناءً على المساحة
        const updateSpotUvPrice = function() {
            let selectedOption = null;
            if (spotUvServiceSelect && spotUvServiceSelect.selectedIndex >= 0) {
                selectedOption = spotUvServiceSelect.options[spotUvServiceSelect.selectedIndex];
            }
            if (selectedOption && selectedOption.dataset.price) {
                const basePrice = parseFloat(selectedOption.dataset.price);
                const area = parseFloat(spotUvAreaInput.value) || 1;
                
                // ضرب السعر الأساسي في المساحة
                const finalPrice = basePrice * area;
                spotUvPriceInput.value = finalPrice.toFixed(2);
                
                // تحديث إجمالي تكلفة خدمات ما بعد الطباعة
                PricingSystem.Finishing.calculateTotalFinishingCost();
            } else {
                spotUvPriceInput.value = '';
            }
        };
        
        // إضافة مستمع أحداث لتغيير خدمة Spot UV
        if (spotUvServiceSelect) {
            spotUvServiceSelect.addEventListener('change', updateSpotUvPrice);
        }
        
        // إضافة مستمع أحداث لتغيير مساحة Spot UV
        if (spotUvAreaInput) {
            spotUvAreaInput.addEventListener('change', updateSpotUvPrice);
            spotUvAreaInput.addEventListener('input', updateSpotUvPrice);
        }
        
        // تعيين حالة مربع الاختيار الأولية
        if (spotUvSection) {
            spotUvSection.style.display = spotUvCheckbox.checked ? 'block' : 'none';
        }
    },
    
    /**
     * حساب إجمالي تكلفة خدمات ما بعد الطباعة
     */
    calculateTotalFinishingCost: function() {
        let totalCost = 0;
        
        // التحقق من كل خدمة وإضافة تكلفتها إذا كانت مختارة
        const finishingServices = [
            { name: 'coating', enabled: 'id_coating_enabled', total: 'id_coating_total_cost' },
            { name: 'cutting', enabled: 'id_cutting_enabled', total: 'id_cutting_total_cost' },
            { name: 'binding', enabled: 'id_binding_enabled', total: 'id_binding_total_cost' },
            { name: 'folding', enabled: 'id_folding_enabled', total: 'id_folding_total_cost' },
            { name: 'punching', enabled: 'id_punching_enabled', total: 'id_punching_total_cost' },
            { name: 'lamination', enabled: 'id_lamination_enabled', total: 'id_lamination_total_cost' },
            { name: 'die_cut', enabled: 'id_die_cut_enabled', total: 'id_die_cut_total_cost' },
            { name: 'spot_uv', enabled: 'id_spot_uv_enabled', total: 'id_spot_uv_total_cost' }
        ];
        
        finishingServices.forEach(service => {
            const enabledCheckbox = document.getElementById(service.enabled);
            const totalCostInput = document.getElementById(service.total);
            
            if (enabledCheckbox && enabledCheckbox.checked && totalCostInput && totalCostInput.value) {
                totalCost += parseFloat(totalCostInput.value) || 0;
            }
        });
        
        // تحديث حقل إجمالي تكلفة خدمات ما بعد الطباعة
        const totalFinishingCostInput = document.getElementById('id_finishing_cost_summary');
        if (totalFinishingCostInput) {
            totalFinishingCostInput.value = totalCost.toFixed(2);
        }
        
        // تحديث حقل تكلفة خدمات ما بعد الطباعة في النموذج الرئيسي
        const finishingCostInput = document.getElementById('id_finishing_cost');
        if (finishingCostInput) {
            finishingCostInput.value = totalCost.toFixed(2);
        }
        
        // تحديث إجمالي التكلفة
        if (typeof PricingSystem.Pricing !== 'undefined' && typeof PricingSystem.Pricing.calculateCost === 'function') {
            PricingSystem.Pricing.calculateCost();
        }
    },
    
    /**
     * دالة موحدة لإعداد خدمات ما بعد الطباعة
     */
    setupUnifiedFinishingServices: function() {
        // تكوين الخدمات المختلفة
        const serviceConfig = {
            coating: {
                supplierSelector: 'coating_supplier',
                serviceSelector: 'coating_service_select',
                priceSelector: 'coating_price',
                apiUrl: '/pricing/api/coating-services/',
                updatePrice: function(selectedOption) {
                    const coatingPriceInput = document.getElementById('coating_price');
                    const coatingSidesSelect = document.getElementById('coating_sides');
                    
                    if (!selectedOption && coatingServiceSelect) {
                        const coatingServiceSelect = document.getElementById('coating_service_select');
                        if (coatingServiceSelect && coatingServiceSelect.selectedIndex >= 0) {
                            selectedOption = coatingServiceSelect.options[coatingServiceSelect.selectedIndex];
                        }
                    }
                    
                    if (selectedOption && selectedOption.dataset.price) {
                        const basePrice = parseFloat(selectedOption.dataset.price);
                        const sides = parseInt(coatingSidesSelect.value) || 1;
                        
                        // مضاعفة السعر إذا كان وجهين
                        const finalPrice = basePrice * sides;
                        coatingPriceInput.value = finalPrice.toFixed(2);
                        
                        // حساب الإجمالي بناءً على عدد الأفرخ وليس الكمية
                        const sheetsCount = parseInt(document.getElementById('id_paper_sheets_count')?.value) || 0;
                        const coatingTotalInput = document.getElementById('coating_total');
                        if (coatingTotalInput) {
                            // حساب الإجمالي: السعر × عدد الأفرخ
                            const totalCost = finalPrice * sheetsCount;
                            coatingTotalInput.value = totalCost.toFixed(2);
                        }
                        
                        // تحديث إجمالي تكلفة خدمات مابعد الطباعة
                        PricingSystem.Finishing.calculateTotalFinishingCost();
                    } else {
                        coatingPriceInput.value = '';
                        // إعادة تعيين حقل الإجمالي
                        const coatingTotalInput = document.getElementById('coating_total');
                        if (coatingTotalInput) {
                            coatingTotalInput.value = '';
                        }
                    }
                },
                extraSetup: function() {
                    const coatingSidesSelect = document.getElementById('coating_sides');
                    const coatingServiceSelect = document.getElementById('coating_service_select');
                    
                    if (coatingSidesSelect) {
                        coatingSidesSelect.addEventListener('change', function() {
                            if (coatingServiceSelect && coatingServiceSelect.selectedIndex >= 0) {
                                const selectedOption = coatingServiceSelect.options[coatingServiceSelect.selectedIndex];
                                serviceConfig.coating.updatePrice(selectedOption);
                            }
                        });
                    }
                    
                    // إضافة مستمع حدث لعدد الأفرخ لتحديث الإجمالي عند تغيير عدد الأفرخ
                    const paperSheetsCountInput = document.getElementById('id_paper_sheets_count');
                    if (paperSheetsCountInput) {
                        paperSheetsCountInput.addEventListener('change', function() {
                            if (coatingServiceSelect && coatingServiceSelect.selectedIndex >= 0) {
                                const selectedOption = coatingServiceSelect.options[coatingServiceSelect.selectedIndex];
                                serviceConfig.coating.updatePrice(selectedOption);
                            }
                        });
                        paperSheetsCountInput.addEventListener('input', function() {
                            if (coatingServiceSelect && coatingServiceSelect.selectedIndex >= 0) {
                                const selectedOption = coatingServiceSelect.options[coatingServiceSelect.selectedIndex];
                                serviceConfig.coating.updatePrice(selectedOption);
                            }
                        });
                    }
                }
            },
            folding: {
                supplierSelector: 'folding_supplier',
                serviceSelector: 'folding_service_select',
                priceSelector: 'folding_price',
                apiUrl: '/pricing/api/folding-services/',
                updatePrice: function() {
                    const foldingServiceSelect = document.getElementById('folding_service_select');
                    const foldingPriceInput = document.getElementById('folding_price');
                    const foldingCountInput = document.getElementById('folding_count');
                    
                    let selectedOption = null;
                    if (foldingServiceSelect && foldingServiceSelect.selectedIndex >= 0) {
                        selectedOption = foldingServiceSelect.options[foldingServiceSelect.selectedIndex];
                    }
                    
                    if (selectedOption && selectedOption.dataset.price) {
                        const basePrice = parseFloat(selectedOption.dataset.price);
                        const count = parseInt(foldingCountInput.value) || 1;
                        
                        // ضرب السعر الأساسي في عدد الريجات
                        const finalPrice = basePrice * count;
                        foldingPriceInput.value = finalPrice.toFixed(2);
                        
                        // تحديث إجمالي تكلفة خدمات مابعد الطباعة
                        PricingSystem.Finishing.calculateTotalFinishingCost();
                    } else {
                        foldingPriceInput.value = '';
                    }
                },
                extraSetup: function() {
                    const foldingCountInput = document.getElementById('folding_count');
                    
                    if (foldingCountInput) {
                        foldingCountInput.addEventListener('change', serviceConfig.folding.updatePrice);
                        foldingCountInput.addEventListener('input', serviceConfig.folding.updatePrice);
                    }
                }
            },
            die_cut: {
                supplierSelector: 'die_cut_supplier',
                serviceSelector: 'die_cut_service_select',
                priceSelector: 'die_cut_price',
                apiUrl: '/pricing/api/die-cut-services/',
                updatePrice: function(selectedOption) {
                    const dieCutPriceInput = document.getElementById('die_cut_price');
                    
                    if (selectedOption && selectedOption.dataset.price) {
                        dieCutPriceInput.value = selectedOption.dataset.price;
                        PricingSystem.Finishing.calculateTotalFinishingCost();
                    } else {
                        dieCutPriceInput.value = '';
                    }
                }
            },
            spot_uv: {
                supplierSelector: 'spot_uv_supplier',
                serviceSelector: 'spot_uv_service_select',
                priceSelector: 'spot_uv_price',
                apiUrl: '/pricing/api/spot-uv-services/',
                updatePrice: function() {
                    const spotUvServiceSelect = document.getElementById('spot_uv_service_select');
                    const spotUvPriceInput = document.getElementById('spot_uv_price');
                    const spotUvAreaInput = document.getElementById('spot_uv_area');
                    
                    let selectedOption = null;
                    if (spotUvServiceSelect && spotUvServiceSelect.selectedIndex >= 0) {
                        selectedOption = spotUvServiceSelect.options[spotUvServiceSelect.selectedIndex];
                    }
                    
                    if (selectedOption && selectedOption.dataset.price) {
                        const basePrice = parseFloat(selectedOption.dataset.price);
                        const area = parseFloat(spotUvAreaInput.value) || 1;
                        
                        // ضرب السعر الأساسي في المساحة
                        const finalPrice = basePrice * area;
                        spotUvPriceInput.value = finalPrice.toFixed(2);
                        
                        // تحديث إجمالي تكلفة خدمات مابعد الطباعة
                        PricingSystem.Finishing.calculateTotalFinishingCost();
                    } else {
                        spotUvPriceInput.value = '';
                    }
                },
                extraSetup: function() {
                    const spotUvAreaInput = document.getElementById('spot_uv_area');
                    
                    if (spotUvAreaInput) {
                        spotUvAreaInput.addEventListener('change', serviceConfig.spot_uv.updatePrice);
                        spotUvAreaInput.addEventListener('input', serviceConfig.spot_uv.updatePrice);
                    }
                }
            }
        };
        
        // تطبيق التكوين على كل خدمة
        Object.keys(serviceConfig).forEach(serviceType => {
            this.setupFinishingService(serviceType, serviceConfig[serviceType]);
        });
    },
    
    /**
     * دالة موحدة لإعداد خدمة ما بعد الطباعة
     * @param {string} serviceType - نوع الخدمة
     * @param {object} config - تكوين الخدمة
     */
    setupFinishingService: function(serviceType, config) {
        if (!config) return;
        
        const supplierSelect = document.getElementById(config.supplierSelector);
        const serviceSelect = document.getElementById(config.serviceSelector);
        const priceInput = document.getElementById(config.priceSelector);
        
        if (supplierSelect) {
            supplierSelect.addEventListener('change', function() {
                const supplierId = this.value;
                
                // مسح خيارات الخدمات الحالية
                serviceSelect.innerHTML = '<option value="">-- اختر نوع الخدمة --</option>';
                priceInput.value = '';
                
                if (!supplierId) return;
                
                // استدعاء API للحصول على خدمات المورد المحدد
                fetch(`${config.apiUrl}?supplier_id=${supplierId}`)
                    .then(response => response.json())
                    .then(data => {
                        if (data.success && data.services) {
                            // إضافة الخدمات إلى القائمة المنسدلة
                            data.services.forEach(service => {
                                const option = document.createElement('option');
                                option.value = service.id;
                                option.text = service.name;
                                option.dataset.price = service.unit_price;
                                serviceSelect.appendChild(option);
                            });
                        }
                    })
                    .catch(error => console.error(`Error fetching ${serviceType} services:`, error));
            });
        }
        
        // إضافة مستمع أحداث لتغيير الخدمة
        if (serviceSelect) {
            serviceSelect.addEventListener('change', function() {
                let selectedOption = null;
                if (this.selectedIndex >= 0) {
                    selectedOption = this.options[this.selectedIndex];
                }
                if (config.updatePrice) {
                    config.updatePrice(selectedOption);
                }
            });
        }
        
        // إعداد إضافي خاص بكل خدمة
        if (config.extraSetup) {
            config.extraSetup();
        }
    },
    
    /**
     * تحديث تكلفة التغطية بناءً على عدد أفرخ الورق للغلاف
     */
    updateCoatingTotalBasedOnSheets: function() {
        // التحقق من تفعيل خدمة التغطية
        const coatingEnabled = document.getElementById('id_coating_enabled');
        if (!coatingEnabled || !coatingEnabled.checked) {
            return;
        }
        
        // الحصول على عدد أفرخ الورق
        const paperSheetsCount = document.getElementById('id_paper_sheets_count');
        if (!paperSheetsCount) {
            return;
        }
        
        // الحصول على سعر التغطية
        const coatingPrice = document.getElementById('id_coating_price');
        if (!coatingPrice) {
            return;
        }
        
        // الحصول على عدد جوانب التغطية (وجه/وجهين)
        const coatingSides = document.getElementById('coating_sides');
        let sidesMultiplier = 1;
        
        if (coatingSides && coatingSides.options && coatingSides.selectedIndex >= 0) {
            const selectedValue = coatingSides.options[coatingSides.selectedIndex].value;
            sidesMultiplier = selectedValue === 'both_sides' ? 2 : 1;
        }
        
        // حساب إجمالي تكلفة التغطية
        const sheetsCount = parseFloat(paperSheetsCount.value) || 0;
        const price = parseFloat(coatingPrice.value) || 0;
        const total = sheetsCount * price * sidesMultiplier;
        
        // تحديث حقل إجمالي تكلفة التغطية
        const coatingTotal = document.getElementById('coating_total');
        if (coatingTotal) {
            coatingTotal.value = total.toFixed(2);
            
            // إطلاق حدث تغيير لتحديث التكلفة الإجمالية
            if (PricingSystem.EventBus) {
                PricingSystem.EventBus.fieldChanged('coating_total', coatingTotal.value, true, true);
            }
            
            // تحديث التكلفة الإجمالية لخدمات ما بعد الطباعة
            this.calculateTotalFinishingCost();
        }
        
        console.log(`تم تحديث تكلفة التغطية: ${total.toFixed(2)} بناءً على ${sheetsCount} فرخ × ${price} × ${sidesMultiplier} جانب`);
    },
    
    /**
     * تحديث تكلفة التغطية بناءً على عدد أفرخ الورق للمحتوى الداخلي
     */
    updateInternalCoatingTotalBasedOnSheets: function() {
        // التحقق من تفعيل خدمة التغطية للمحتوى الداخلي
        const internalCoatingEnabled = document.getElementById('id_internal_coating_enabled');
        if (!internalCoatingEnabled || !internalCoatingEnabled.checked) {
            return;
        }
        
        // الحصول على عدد أفرخ الورق للمحتوى الداخلي
        const internalPaperSheetsCount = document.getElementById('id_internal_paper_sheets_count');
        if (!internalPaperSheetsCount) {
            return;
        }
        
        // الحصول على سعر التغطية للمحتوى الداخلي
        const internalCoatingPrice = document.getElementById('id_internal_coating_price');
        if (!internalCoatingPrice) {
            return;
        }
        
        // الحصول على عدد جوانب التغطية (وجه/وجهين)
        const internalCoatingSides = document.getElementById('internal_coating_sides');
        let sidesMultiplier = 1;
        
        if (internalCoatingSides && internalCoatingSides.options && internalCoatingSides.selectedIndex >= 0) {
            const selectedValue = internalCoatingSides.options[internalCoatingSides.selectedIndex].value;
            sidesMultiplier = selectedValue === 'both_sides' ? 2 : 1;
        }
        
        // حساب إجمالي تكلفة التغطية للمحتوى الداخلي
        const sheetsCount = parseFloat(internalPaperSheetsCount.value) || 0;
        const price = parseFloat(internalCoatingPrice.value) || 0;
        const total = sheetsCount * price * sidesMultiplier;
        
        // تحديث حقل إجمالي تكلفة التغطية للمحتوى الداخلي
        const internalCoatingTotal = document.getElementById('internal_coating_total');
        if (internalCoatingTotal) {
            internalCoatingTotal.value = total.toFixed(2);
            
            // إطلاق حدث تغيير لتحديث التكلفة الإجمالية
            if (PricingSystem.EventBus) {
                PricingSystem.EventBus.fieldChanged('internal_coating_total', internalCoatingTotal.value, true, true);
            }
            
            // تحديث التكلفة الإجمالية لخدمات ما بعد الطباعة
            this.calculateTotalFinishingCost();
        }
        
        console.log(`تم تحديث تكلفة التغطية للمحتوى الداخلي: ${total.toFixed(2)} بناءً على ${sheetsCount} فرخ × ${price} × ${sidesMultiplier} جانب`);
    }
}; 