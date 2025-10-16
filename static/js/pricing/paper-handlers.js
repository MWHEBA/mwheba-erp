/**
 * paper-handlers.js - دالات معالجة الورق
 */

// تعريف كائن عام للمشروع إذا لم يكن موجودًا
window.PricingSystem = window.PricingSystem || {};

// تعريف وحدة معالجة الورق
PricingSystem.Paper = {
    /**
     * بيانات أنواع الورق والأوزان
     */
    paperTypeWeights: {},

    /**
     * تهيئة معالج الورق
     */
    init: function() {
        // محاولة استخراج البيانات من عنصر مخفي في النموذج
        const paperTypeWeightsElement = document.getElementById('paper_type_weights_data');
        if (paperTypeWeightsElement) {
            try {
                this.paperTypeWeights = JSON.parse(paperTypeWeightsElement.textContent);
            } catch (e) {
                console.error('خطأ في تحليل بيانات أوزان الورق:', e);
            }
        }

        // إعداد معالجات الأحداث
        this.setupEventHandlers();
        
        // تسجيل معالجات الأحداث مع ناقل الأحداث إذا كان متاحًا
        if (PricingSystem.EventBus) {
            this.registerEventHandlers();
        }
    },
    
    /**
     * تسجيل معالجات الأحداث مع ناقل الأحداث
     */
    registerEventHandlers: function() {
        // الاستماع لتغييرات نوع الورق
        PricingSystem.EventBus.on('field:id_paper_type:changed', (data) => {
            this.updatePaperWeightOptions();
            this.updatePaperOrigins();
        });
        
        // الاستماع لتغييرات مورد الورق
        PricingSystem.EventBus.on('field:id_paper_supplier:changed', (data) => {
            this.updatePaperSheetTypes();
            this.updatePaperOrigins();
        });
        
        // الاستماع لتغييرات مقاس الورق
        PricingSystem.EventBus.on('field:id_paper_sheet_type:changed', (data) => {
            this.updatePaperOrigins();
        });
        
        // الاستماع لتغييرات جرام الورق
        PricingSystem.EventBus.on('field:id_paper_weight:changed', (data) => {
            this.updatePaperOrigins();
        });
        
        // الاستماع لتغييرات بلد المنشأ
        PricingSystem.EventBus.on('field:id_paper_origin:changed', (data) => {
            if (typeof PricingSystem.API !== 'undefined' && typeof PricingSystem.API.updatePaperPrice === 'function') {
                PricingSystem.API.updatePaperPrice();
            } else {
                this.updatePaperPrice();
            }
        });
        
        // الاستماع لتغييرات سعر الورق
        PricingSystem.EventBus.on('field:id_paper_price:changed', (data) => {
            this.updateTotalPaperCost();
        });
        
        // الاستماع لتغييرات كمية الورق
        PricingSystem.EventBus.on('field:id_paper_quantity:changed', (data) => {
            this.updateTotalPaperCost();
        });
        
        // الاستماع لتغييرات عدد أفرخ الورق
        PricingSystem.EventBus.on('field:id_paper_sheets_count:changed', (data) => {
            // تحديث كمية الورق بنفس قيمة عدد الأفرخ
            const paperQuantityInput = document.getElementById('id_paper_quantity');
            if (paperQuantityInput) {
                paperQuantityInput.value = data.value;
                PricingSystem.EventBus.fieldChanged('id_paper_quantity', data.value, false);
            }
        });
        
        // الاستماع لتغييرات الكمية أو عدد المونتاج
        PricingSystem.EventBus.on('field:id_quantity:changed', (data) => {
            this.calculatePaperSheetsDirectly();
        });
        
        PricingSystem.EventBus.on('field:id_montage_count:changed', (data) => {
            this.calculatePaperSheetsDirectly();
        });
        
        // الاستماع لتحديثات الحقول المتعلقة بالورق
        PricingSystem.EventBus.on('fields:updated', (data) => {
            const paperRelatedFields = [
                'id_paper_type', 'id_paper_weight', 'id_paper_supplier',
                'id_paper_sheet_type', 'id_paper_origin', 'id_quantity',
                'id_montage_count', 'id_paper_sheets_count', 'id_paper_quantity'
            ];
            
            const shouldUpdatePaperCost = data.changedFields.some(field => 
                paperRelatedFields.includes(field)
            );
            
            if (shouldUpdatePaperCost) {
                this.updateTotalPaperCost();
            }
        });
    },

    /**
     * إعداد معالجات الأحداث للورق
     */
    setupEventHandlers: function() {
        // الحصول على عناصر النموذج المتعلقة بالورق
        const paperTypeSelect = document.getElementById('id_paper_type');
        const paperWeightSelect = document.getElementById('id_paper_weight');
        const paperSupplierSelect = document.getElementById('id_paper_supplier');
        const paperSheetTypeSelect = document.getElementById('id_paper_sheet_type');
        const paperQuantityInput = document.getElementById('id_paper_quantity');
        const paperPriceInput = document.getElementById('id_paper_price');
        const quantityInput = document.getElementById('id_quantity');
        const montageCountInput = document.getElementById('id_montage_count');
        const paperOriginSelect = document.getElementById('id_paper_origin');
        const paperSheetsCountInput = document.getElementById('id_paper_sheets_count');
        
        // حفظ العناصر في كائن عام للوصول إليها من دوال أخرى
        PricingSystem.elements = {
            paperTypeSelect: paperTypeSelect,
            paperWeightSelect: paperWeightSelect,
            paperSupplierSelect: paperSupplierSelect,
            paperSheetTypeSelect: paperSheetTypeSelect,
            paperQuantityInput: paperQuantityInput,
            paperPriceInput: paperPriceInput,
            quantityInput: quantityInput,
            montageCountInput: montageCountInput,
            paperOriginSelect: paperOriginSelect,
            paperSheetsCountInput: paperSheetsCountInput
        };
        
        // إذا كان نظام ناقل الأحداث متاحًا، فلا داعي لإضافة مستمعات أحداث تقليدية
        if (PricingSystem.EventBus) {
            return;
        }
        
        // دالة مساعدة لتحديث سعر الورق وإجمالي التكلفة
        const updatePriceAndTotal = () => {
            if (typeof PricingSystem.API !== 'undefined' && typeof PricingSystem.API.updatePaperPrice === 'function') {
                PricingSystem.API.updatePaperPrice();
            } else {
                this.updatePaperPrice();
            }
        };
        
        // إضافة مستمع حدث لتغيير نوع الورق
        if (paperTypeSelect) {
            paperTypeSelect.addEventListener('change', () => {
                this.updatePaperWeightOptions();
                updatePriceAndTotal();
            });
        }
        
        // إضافة مستمع حدث لتغيير مورد الورق
        if (paperSupplierSelect) {
            paperSupplierSelect.addEventListener('change', () => {
                this.updatePaperSheetTypes();
                updatePriceAndTotal();
            });
        }
        
        // إضافة مستمع حدث لتغيير مقاس الورق
        if (paperSheetTypeSelect) {
            paperSheetTypeSelect.addEventListener('change', () => {
                // تحديث قائمة بلد المنشأ عند تغيير مقاس الورق
                this.updatePaperOrigins();
                updatePriceAndTotal();
            });
        }
        
        // إضافة مستمع حدث لتغيير جرام الورق
        if (paperWeightSelect) {
            paperWeightSelect.addEventListener('change', () => {
                // تحديث قائمة بلد المنشأ عند تغيير جرام الورق
                this.updatePaperOrigins();
                updatePriceAndTotal();
            });
        }
        
        // إضافة مستمع حدث لتغيير بلد المنشأ
        if (paperOriginSelect) {
            paperOriginSelect.addEventListener('change', updatePriceAndTotal);
        }
        
        // إضافة مستمع حدث لتغيير سعر الورق أو كميته
        if (paperPriceInput) {
            paperPriceInput.addEventListener('change', this.updateTotalPaperCost.bind(this));
            paperPriceInput.addEventListener('input', this.updateTotalPaperCost.bind(this));
        }
        
        if (paperQuantityInput) {
            paperQuantityInput.addEventListener('change', this.updateTotalPaperCost.bind(this));
            paperQuantityInput.addEventListener('input', this.updateTotalPaperCost.bind(this));
        }
        
        // إضافة مستمع حدث للتغيير اليدوي لعدد أفرخ الورق
        if (paperSheetsCountInput) {
            paperSheetsCountInput.addEventListener('change', () => {
                // تحديث كمية الورق بنفس قيمة عدد الأفرخ
                if (paperQuantityInput) {
                    paperQuantityInput.value = paperSheetsCountInput.value;
                }
                // استخدام API لتحديث سعر الورق وإجمالي التكلفة
                if (typeof PricingSystem.API !== 'undefined' && typeof PricingSystem.API.updatePaperPrice === 'function') {
                    PricingSystem.API.updatePaperPrice();
                } else {
                    this.updateTotalPaperCost();
                }
            });
            paperSheetsCountInput.addEventListener('input', () => {
                // تحديث كمية الورق بنفس قيمة عدد الأفرخ
                if (paperQuantityInput) {
                    paperQuantityInput.value = paperSheetsCountInput.value;
                }
                // استخدام API لتحديث سعر الورق وإجمالي التكلفة
                if (typeof PricingSystem.API !== 'undefined' && typeof PricingSystem.API.updatePaperPrice === 'function') {
                    PricingSystem.API.updatePaperPrice();
                } else {
                    this.updateTotalPaperCost();
                }
            });
        }
        
        // إضافة مستمع حدث لتغيير الكمية أو عدد المونتاج لحساب عدد أفرخ الورق
        if (quantityInput) {
            quantityInput.addEventListener('change', this.calculatePaperSheetsDirectly.bind(this));
            quantityInput.addEventListener('input', this.calculatePaperSheetsDirectly.bind(this));
        }
        
        if (montageCountInput) {
            montageCountInput.addEventListener('change', this.calculatePaperSheetsDirectly.bind(this));
            montageCountInput.addEventListener('input', this.calculatePaperSheetsDirectly.bind(this));
        }
    },

    /**
     * دالة لتحديث قائمة جرام الورق حسب نوع الورق المختار
     */
    updatePaperWeightOptions: function() {
        const paperTypeSelect = document.getElementById('id_paper_type');
        const paperWeightSelect = document.getElementById('id_paper_weight');
        const selectedType = paperTypeSelect.value;
        
        // امسح الاختيارات القديمة
        paperWeightSelect.innerHTML = '<option value="">-- اختر الجرام --</option>';
        
        if (this.paperTypeWeights[selectedType]) {
            // ترتيب الأوزان تصاعديًا
            const sortedWeights = [...this.paperTypeWeights[selectedType]].sort((a, b) => a - b);
            
            sortedWeights.forEach(function(weight) {
                const option = document.createElement('option');
                option.value = weight;
                option.text = weight + ' جم';
                paperWeightSelect.appendChild(option);
            });
        }
        
        // تحديث سعر الورق بعد تغيير نوع الورق
        if (typeof PricingSystem.API !== 'undefined' && typeof PricingSystem.API.updatePaperPrice === 'function') {
            PricingSystem.API.updatePaperPrice();
        }
    },
    
    /**
     * دالة لتهيئة قائمة أنواع الورق عند تحميل الصفحة
     */
    initializePaperTypeOptions: function() {
        // لا نحتاج إلى تعديل قائمة أنواع الورق هنا بعد الآن
        // لأننا قمنا بتجميعها بالفعل في الخلفية (backend)
        // ولكن يمكننا إضافة أي منطق إضافي هنا إذا لزم الأمر
        
        // التحقق من وجود قيمة محفوظة في الجلسة وتعيينها
        const sessionDataElement = document.getElementById('session_data');
        if (sessionDataElement) {
            try {
                const sessionData = JSON.parse(sessionDataElement.textContent);
                const savedPaperType = sessionData['paper_type'];
                
                if (savedPaperType) {
                    const paperTypeSelect = document.getElementById('id_paper_type');
                    if (paperTypeSelect) {
                        paperTypeSelect.value = savedPaperType;
                        // تشغيل حدث التغيير لتحديث قائمة الأوزان
                        const event = new Event('change');
                        paperTypeSelect.dispatchEvent(event);
                    }
                }
            } catch (e) {
                console.error('خطأ في تحليل بيانات الجلسة:', e);
            }
        }
    },
    
    /**
     * دالة لتحديث قائمة جرام الورق حسب مورد الورق المختار
     */
    updatePaperWeightBySupplier: function() {
        const elements = PricingSystem.elements;
        const paperSupplierSelect = elements.paperSupplierSelect;
        const paperWeightSelect = elements.paperWeightSelect;
        const selectedSupplierId = paperSupplierSelect.value;
        
        // امسح الاختيارات القديمة
        paperWeightSelect.innerHTML = '<option value="">-- اختر الجرام --</option>';
        
        if (!selectedSupplierId) {
            return; // إذا لم يتم اختيار مورد، لا تفعل شيء
        }
        
        // استدعاء API للحصول على الأوزان المتاحة عند المورد
        fetch(`/pricing/api/paper-weights/?supplier_id=${selectedSupplierId}`)
            .then(response => response.json())
            .then(data => {
                if (data.success && data.weights) {
                    // استخدام Set للتأكد من عدم تكرار الأوزان
                    const uniqueWeights = new Set();
                    
                    // إضافة جميع الأوزان إلى المجموعة الفريدة
                    data.weights.forEach(function(weight) {
                        if (weight.gsm) {
                            uniqueWeights.add(parseInt(weight.gsm));
                        }
                    });
                    
                    // ترتيب الأوزان تصاعديًا
                    const sortedWeights = Array.from(uniqueWeights).sort((a, b) => a - b);
                    
                    // إنشاء خيارات للقائمة المنسدلة من الأوزان الفريدة المرتبة
                    sortedWeights.forEach(function(gsm) {
                        const option = document.createElement('option');
                        option.value = gsm;
                        option.text = gsm + ' جم';
                        paperWeightSelect.appendChild(option);
                    });
                }
            })
            .catch(error => console.error('Error fetching paper weights:', error));
            
        // تحديث سعر الورق بعد تغيير المورد
        PricingSystem.API.updatePaperPrice();
    },
    
    /**
     * دالة لتحديث قائمة مقاسات الورق حسب مورد الورق ونوع الورق المختار
     */
    updatePaperSheetTypes: function() {
        const elements = PricingSystem.elements;
        const paperTypeSelect = elements.paperTypeSelect;
        const paperSupplierSelect = elements.paperSupplierSelect;
        const paperSheetTypeSelect = elements.paperSheetTypeSelect;
        
        if (!paperTypeSelect || !paperSupplierSelect || !paperSheetTypeSelect) return;
        
        const selectedType = paperTypeSelect.value;
        const selectedSupplierId = paperSupplierSelect.value;
        
        // امسح الاختيارات القديمة مع الاحتفاظ بخيار الافتراضي
        paperSheetTypeSelect.innerHTML = '<option value="">-- اختر مقاس الفرخ --</option>';
        
        if (!selectedType || !selectedSupplierId) {
            return; // إذا لم يتم اختيار نوع ورق أو مورد، لا تفعل شيء
        }
        
        // استدعاء API للحصول على مقاسات الورق المتاحة عند المورد لنوع الورق المحدد
        fetch(`/pricing/api/paper-sheet-types/?supplier_id=${selectedSupplierId}&paper_type_id=${selectedType}`)
            .then(response => response.json())
            .then(data => {
                if (data.success && data.sheet_types) {
                    // استخدام Set للتأكد من عدم تكرار المقاسات
                    const uniqueSheetTypes = new Set();
                    const displayNames = {};
                    const addedValues = new Set(); // مجموعة إضافية لتتبع القيم المضافة بالفعل
                    
                    // إضافة جميع المقاسات إلى المجموعة الفريدة
                    data.sheet_types.forEach(function(item) {
                        if (item.sheet_type) {
                            uniqueSheetTypes.add(item.sheet_type);
                            displayNames[item.sheet_type] = item.display_name;
                        }
                    });
                    
                    // إنشاء خيارات للقائمة المنسدلة من المقاسات الفريدة
                    if (uniqueSheetTypes.size > 0) {
                        uniqueSheetTypes.forEach(function(sheetType) {
                            // التحقق مرة أخرى من عدم إضافة القيمة من قبل
                            if (!addedValues.has(sheetType)) {
                            const option = document.createElement('option');
                            option.value = sheetType;
                                option.text = displayNames[sheetType] || sheetType;
                            paperSheetTypeSelect.appendChild(option);
                                addedValues.add(sheetType); // تسجيل القيمة كمضافة
                            }
                        });
                        
                        // تحديد أول خيار افتراضيًا
                        if (paperSheetTypeSelect.options.length > 1) {
                            paperSheetTypeSelect.selectedIndex = 1;
                            // تشغيل حدث التغيير لتحديث الحقول التالية
                            const event = new Event('change');
                            paperSheetTypeSelect.dispatchEvent(event);
                        }
                    } else {
                        // إضافة الخيارات الافتراضية إذا لم يتم العثور على مقاسات
                        // التأكد من عدم وجود تكرار في الخيارات الافتراضية
                        if (!addedValues.has('full')) {
                        const fullOption = document.createElement('option');
                        fullOption.value = 'full';
                        fullOption.text = 'فرخ كامل 70*100';
                        paperSheetTypeSelect.appendChild(fullOption);
                            addedValues.add('full');
                        }
                        
                        if (!addedValues.has('half')) {
                        const halfOption = document.createElement('option');
                        halfOption.value = 'half';
                        halfOption.text = 'فرخ جاير';
                        paperSheetTypeSelect.appendChild(halfOption);
                            addedValues.add('half');
                        }
                    }
                    
                    // تنقية إضافية - إزالة أي خيارات مكررة
                    const existingOptions = new Set();
                    Array.from(paperSheetTypeSelect.options).forEach((option, index) => {
                        if (index > 0) { // تجاوز الخيار الافتراضي الأول
                            if (existingOptions.has(option.value)) {
                                // إذا كانت القيمة موجودة بالفعل، قم بإزالة الخيار
                                paperSheetTypeSelect.removeChild(option);
                            } else {
                                existingOptions.add(option.value);
                            }
                        }
                    });
                }
            })
            .catch(error => console.error('Error fetching paper sheet types:', error));
            
        // تحديث سعر الورق بعد تغيير مقاس الورق
        PricingSystem.API.updatePaperPrice();
        
        // تحديث قائمة أوزان الورق حسب نوع الورق المحدد
        // هذا يضمن أن قائمة الأوزان لا تختفي عند اختيار المورد
        this.updatePaperWeightOptions();
    },
    
    /**
     * دالة لتحديث قائمة منشأ الورق حسب المعايير المختارة
     */
    updatePaperOrigins: function() {
        const paperTypeSelect = document.getElementById('id_paper_type');
        const paperSupplierSelect = document.getElementById('id_paper_supplier');
        const paperSheetTypeSelect = document.getElementById('id_paper_sheet_type');
        const paperWeightSelect = document.getElementById('id_paper_weight');
        const paperOriginSelect = document.getElementById('id_paper_origin');
        
        if (!paperTypeSelect || !paperSupplierSelect || !paperSheetTypeSelect || 
            !paperWeightSelect || !paperOriginSelect) return;
            
        // التحقق من وجود نوع الورق أولاً
        if (!paperTypeSelect.value) {
            console.log('لم يتم اختيار نوع الورق - تخطي تحديث منشأ الورق');
            paperOriginSelect.innerHTML = '<option value="">---------</option>';
            return;
        }
        
        const selectedType = paperTypeSelect.value;
        const selectedSupplierId = paperSupplierSelect.value;
        const selectedSheetType = paperSheetTypeSelect.value;
        const selectedWeight = paperWeightSelect.value;
        
        // إعادة تعيين قائمة بلاد المنشأ
        paperOriginSelect.innerHTML = '<option value="">---------</option>';
        
        if (!selectedType || !selectedSupplierId || !selectedSheetType || !selectedWeight) {
            return; // إذا لم تكتمل البيانات المطلوبة، لا تفعل شيء
        }
        
        // استدعاء API للحصول على بلاد المنشأ المتاحة
        fetch(`/pricing/api/paper-origins/?supplier_id=${selectedSupplierId}&paper_type_id=${selectedType}&sheet_type=${selectedSheetType}&gsm=${selectedWeight}`)
            .then(response => response.json())
            .then(data => {
                if (data.success && data.origins && data.origins.length > 0) {
                    // استخدام Set للتأكد من عدم تكرار بلاد المنشأ
                    const uniqueOrigins = new Set();
                    const displayNames = {};
                    const addedValues = new Set(); // مجموعة إضافية لتتبع القيم المضافة بالفعل
                    
                    // إضافة جميع بلاد المنشأ إلى المجموعة الفريدة
                    data.origins.forEach(function(origin) {
                        if (origin.country_of_origin) {
                            uniqueOrigins.add(origin.country_of_origin);
                            displayNames[origin.country_of_origin] = origin.country_of_origin;
                        }
                    });
                    
                    // إنشاء خيارات للقائمة المنسدلة من بلاد المنشأ الفريدة
                    uniqueOrigins.forEach(function(country) {
                        // التحقق مرة أخرى من عدم إضافة القيمة من قبل
                        if (!addedValues.has(country)) {
                            const option = document.createElement('option');
                            option.value = country;
                            option.textContent = displayNames[country] || country;
                            paperOriginSelect.appendChild(option);
                            addedValues.add(country); // تسجيل القيمة كمضافة
                        }
                    });
                    
                    // تنقية إضافية - إزالة أي خيارات مكررة
                    const existingOptions = new Set();
                    Array.from(paperOriginSelect.options).forEach((option, index) => {
                        if (index > 0) { // تجاوز الخيار الافتراضي الأول
                            if (existingOptions.has(option.value)) {
                                // إذا كانت القيمة موجودة بالفعل، قم بإزالة الخيار
                                paperOriginSelect.removeChild(option);
                            } else {
                                existingOptions.add(option.value);
                            }
                        }
                    });
                    
                    // تحديد الخيار الأول تلقائيًا
                    if (paperOriginSelect.options.length > 1) {
                        paperOriginSelect.selectedIndex = 1;
                        
                        // تحديث سعر الورق بعد تعيين بلد المنشأ
                        PricingSystem.Paper.updatePaperPrice();
                    } else {
                        console.warn('لم يتم العثور على بلاد منشأ للمعايير المحددة');
                    }
                } else {
                    console.warn('لم يتم العثور على بلاد منشأ:', data.error || 'لا توجد بيانات متاحة للمعايير المحددة');
                }
            })
            .catch(error => {
                console.error('خطأ في جلب بلاد المنشأ:', error);
            });
    },
    
    /**
     * دالة لتحديث قائمة موردي الورق
     */
    updatePaperSupplierOptions: function() {
        const paperSupplierSelect = document.getElementById('id_paper_supplier');
        if (!paperSupplierSelect) return;
        
        // إضافة مؤشر تحميل
        paperSupplierSelect.innerHTML = '<option value="">جاري التحميل...</option>';
        paperSupplierSelect.disabled = true;
        
        // استدعاء API للحصول على موردي الورق
        fetch('/pricing/api/paper-suppliers/')
            .then(response => response.json())
            .then(data => {
                // إعادة ضبط قائمة الموردين
                paperSupplierSelect.innerHTML = '<option value="">-- اختر المورد --</option>';
                paperSupplierSelect.disabled = false;
                
                if (data.success && data.suppliers) {
                    // إضافة الموردين إلى القائمة
                    data.suppliers.forEach(supplier => {
                        const option = document.createElement('option');
                        option.value = supplier.id;
                        option.text = supplier.name;
                        paperSupplierSelect.appendChild(option);
                    });
                    
                    // التحقق من وجود قيمة محفوظة في الجلسة وتعيينها
                    const sessionDataElement = document.getElementById('session_data');
                    if (sessionDataElement) {
                        try {
                            const sessionData = JSON.parse(sessionDataElement.textContent);
                            const savedValue = sessionData['paper_supplier'];
                            
                            if (savedValue) {
                                // تأكد من وجود الخيار في القائمة
                                const optionExists = Array.from(paperSupplierSelect.options).some(option => option.value === savedValue);
                                
                                if (optionExists) {
                                    paperSupplierSelect.value = savedValue;
                                    
                                    // إطلاق حدث change لتحديث القوائم المرتبطة
                                    const event = new Event('change', { bubbles: true });
                                    paperSupplierSelect.dispatchEvent(event);
                                }
                            }
                        } catch (e) {
                            console.error('خطأ في تحميل بيانات الجلسة لمورد الورق:', e);
                        }
                    }
                }
            })
            .catch(error => {
                console.error('خطأ في استدعاء API لموردي الورق:', error);
                // إعادة تمكين القائمة
                paperSupplierSelect.disabled = false;
                // إعادة ضبط قائمة الموردين مع رسالة خطأ
                paperSupplierSelect.innerHTML = '<option value="">-- خطأ في تحميل الموردين --</option>';
            });
    },
    
    /**
     * دالة لتحديث إجمالي تكلفة الورق
     */
    updateTotalPaperCost: function() {
        // التحقق من وجود نوع الورق قبل المتابعة
        const paperTypeSelect = document.getElementById('id_paper_type');
        if (!paperTypeSelect || !paperTypeSelect.value) {
            console.log('لم يتم اختيار نوع الورق - تخطي حساب تكلفة الورق');
            // مسح قيم التكلفة
            const paperTotalCostInput = document.getElementById('id_paper_total_cost');
            const paperCostSummaryInput = document.getElementById('id_material_cost');
            if (paperTotalCostInput) paperTotalCostInput.value = '0.00';
            if (paperCostSummaryInput) paperCostSummaryInput.value = '0.00';
            return;
        }
        
        const paperSheetsCountInput = document.getElementById('id_paper_sheets_count');
        const paperPriceInput = document.getElementById('id_paper_price');
        const paperTotalCostInput = document.getElementById('id_paper_total_cost');
        const paperCostSummaryInput = document.getElementById('id_material_cost');
        
        // التحقق من وجود العناصر المطلوبة
        // إذا لم تكن موجودة، يتم تسجيل رسالة أكثر تفصيلاً وإنهاء الدالة
        const missingElements = [];
        if (!paperSheetsCountInput) missingElements.push('id_paper_sheets_count');
        if (!paperPriceInput) missingElements.push('id_paper_price');
        if (!paperTotalCostInput) missingElements.push('id_paper_total_cost');
        if (!paperCostSummaryInput) missingElements.push('id_material_cost');
        
        if (missingElements.length > 0) {
            // تسجيل رسالة أكثر تفصيلاً
            console.log('بعض حقول تكلفة الورق غير موجودة:', missingElements.join(', '));
            // الاستمرار في تنفيذ العمليات على العناصر المتوفرة
        }
        
        // حساب التكلفة الإجمالية للعناصر المتوفرة
        const quantity = paperSheetsCountInput ? (parseFloat(paperSheetsCountInput.value) || 0) : 0;
        const price = paperPriceInput ? (parseFloat(paperPriceInput.value) || 0) : 0;
        
        // حساب التكلفة الإجمالية
        const totalCost = quantity * price;
        
        // تحديث حقل التكلفة الإجمالية إذا كان موجوداً
        if (paperTotalCostInput) {
            paperTotalCostInput.value = totalCost.toFixed(2);
        }
        
        // تحديث حقل تكلفة الورق في قسم التسعير إذا كان موجوداً
        if (paperCostSummaryInput) {
            paperCostSummaryInput.value = totalCost.toFixed(2);
        }
        
        // تحديث إجمالي التكلفة
        if (typeof PricingSystem.Pricing !== 'undefined' && typeof PricingSystem.Pricing.calculateCost === 'function') {
            PricingSystem.Pricing.calculateCost();
        }
    },
    
    /**
     * حساب عدد أفرخ الورق المطلوبة بناءً على الكمية وعدد المونتاج
     */
    calculatePaperSheetsDirectly: function() {
        // التحقق من وجود نوع الورق قبل المتابعة
        const paperTypeSelect = document.getElementById('id_paper_type');
        if (!paperTypeSelect || !paperTypeSelect.value) {
            console.log('لم يتم اختيار نوع الورق - تخطي حساب عدد الأفرخ');
            return;
        }
        
        // الحصول على العناصر المطلوبة
        const elements = {
            quantityInput: document.getElementById('id_quantity'),
            paperSheetsCountInput: document.getElementById('id_paper_sheets_count'),
            paperSheetsInfoElement: document.getElementById('paper-sheets-info'),
            montageInfoInput: document.getElementById('id_montage_info'),
            paperQuantityInput: document.getElementById('id_paper_quantity')
        };
        
        // التحقق من وجود العناصر المطلوبة
        const { 
            quantityInput, 
            paperSheetsCountInput, 
            paperSheetsInfoElement, 
            montageInfoInput,
            paperQuantityInput
        } = elements;
        
        // التحقق من وجود العناصر الأساسية
        const missingElements = [];
        if (!quantityInput) missingElements.push('id_quantity');
        if (!paperSheetsCountInput) missingElements.push('id_paper_sheets_count');
        if (!montageInfoInput) missingElements.push('id_montage_info');
        
        if (missingElements.length > 0) {
            console.log('بعض حقول حساب أفرخ الورق غير موجودة:', missingElements.join(', '));
            return; // لا يمكن إكمال الحساب بدون العناصر الأساسية
        }
        
        // التحقق من وجود قيم للحقول المطلوبة
        if (!quantityInput.value || !montageInfoInput.value) {
            if (paperSheetsCountInput) paperSheetsCountInput.value = '';
            if (paperSheetsInfoElement) {
                paperSheetsInfoElement.textContent = 'يجب تحديد الكمية والمونتاج أولاً';
            }
            return;
        }
        
        // استخراج معلومات المونتاج باستخدام تعبير منتظم
        const quantity = parseInt(quantityInput.value);
        const montageInfo = montageInfoInput.value.trim();
        const montageMatch = montageInfo.match(/(\d+)\s*\/\s*(\S+)/);
        
        // القيم الافتراضية
        let montageCount = 1;
        let sheetType = 1; // 1 = كامل، 2 = نصف، 4 = ربع، 8 = ثمن
        
        if (montageMatch) {
            // استخراج عدد المونتاج
            montageCount = parseInt(montageMatch[1]) || 1;
            
            // استخراج نوع الفرخ من النص
            const sheetTypeText = montageMatch[2].trim().toLowerCase();
            sheetType = sheetTypeText.includes('ثمن') ? 8 : 
                        sheetTypeText.includes('ربع') ? 4 : 
                        sheetTypeText.includes('نصف') ? 2 : 1;
        }
        
        // حساب عدد الأفرخ المطلوبة
        const sheetsCount = Math.ceil(quantity / (montageCount * sheetType));
        
        // تحديث حقل عدد الأفرخ والمعلومات
        if (paperSheetsCountInput) {
            paperSheetsCountInput.value = sheetsCount;
        }
        
        if (paperSheetsInfoElement) {
            paperSheetsInfoElement.textContent = `${quantity} نسخة ÷ (${montageCount} × ${sheetType}) = ${sheetsCount} فرخ`;
        }
        
        // تحديث قيمة id_paper_quantity بنفس قيمة id_paper_sheets_count مباشرة
        if (paperQuantityInput) {
            paperQuantityInput.value = sheetsCount;
        }
        
        // التحقق من توفر جميع معاملات الورق قبل تحديث السعر
        const paperSupplierSelect = document.getElementById('id_paper_supplier');
        const paperSheetTypeSelect = document.getElementById('id_paper_sheet_type');
        const paperWeightSelect = document.getElementById('id_paper_weight');
        
        const hasAllPaperParams = paperSupplierSelect && paperSupplierSelect.value &&
                                 paperSheetTypeSelect && paperSheetTypeSelect.value &&
                                 paperWeightSelect && paperWeightSelect.value;
        
        if (hasAllPaperParams) {
            // استخدام API لتحديث سعر الورق وإجمالي التكلفة
            if (typeof PricingSystem.API !== 'undefined' && typeof PricingSystem.API.updatePaperPrice === 'function') {
                PricingSystem.API.updatePaperPrice();
            } else {
                this.updateTotalPaperCost();
            }
        } else {
            console.log('بعض معاملات الورق مفقودة - تخطي تحديث السعر');
            // فقط تحديث إجمالي التكلفة بدون سعر الورق
            this.updateTotalPaperCost();
        }
    },
    
    /**
     * دالة لحساب عدد أفرخ الورق المطلوبة للمحتوى الداخلي
     */
    calculateInternalPaperSheets: function() {
        const elements = {
            quantityInput: document.getElementById('id_quantity'),
            internalPageCountInput: document.getElementById('id_internal_page_count'),
            internalMontageCountInput: document.getElementById('id_internal_montage_count'),
            internalPaperSheetsCountInput: document.getElementById('id_internal_paper_sheets_count'),
            internalPaperSheetsInfoElement: document.getElementById('internal-paper-sheets-info'),
            internalPaperQuantityInput: document.getElementById('id_internal_paper_quantity'),
            internalPaperPriceInput: document.getElementById('id_internal_paper_price'),
            internalPaperTotalCostInput: document.getElementById('id_internal_paper_total_cost'),
            internalPaperCostSummaryInput: document.getElementById('id_material_cost')
        };
        
        const {
            quantityInput,
            internalPageCountInput,
            internalMontageCountInput,
            internalPaperSheetsCountInput,
            internalPaperSheetsInfoElement,
            internalPaperQuantityInput,
            internalPaperPriceInput,
            internalPaperTotalCostInput,
            internalPaperCostSummaryInput
        } = elements;
        
        // التحقق من وجود العناصر الأساسية
        const missingElements = [];
        if (!quantityInput) missingElements.push('id_quantity');
        if (!internalPageCountInput) missingElements.push('id_internal_page_count');
        if (!internalMontageCountInput) missingElements.push('id_internal_montage_count');
        if (!internalPaperSheetsCountInput) missingElements.push('id_internal_paper_sheets_count');
        
        if (missingElements.length > 0) {
            console.log('بعض حقول حساب أفرخ الورق الداخلية غير موجودة:', missingElements.join(', '));
            return; // لا يمكن إكمال الحساب بدون العناصر الأساسية
        }
        
        const quantity = parseInt(quantityInput.value) || 0;
        const pageCount = parseInt(internalPageCountInput.value) || 0;
        const montageCount = parseInt(internalMontageCountInput.value) || 1;
        
        // الحصول على نوع الفرخ من معلومات المونتاج
        const montageInfoInput = document.getElementById('id_internal_montage_info');
        let sheetType = 1; // 1 = كامل، 2 = نصف، 4 = ربع، 8 = ثمن
        
        if (montageInfoInput && montageInfoInput.value) {
            const montageInfo = montageInfoInput.value;
            if (montageInfo.includes('نصف فرخ')) {
                sheetType = 2;
            } else if (montageInfo.includes('ربع فرخ')) {
                sheetType = 4;
            } else if (montageInfo.includes('ثمن فرخ')) {
                sheetType = 8;
            }
        }
        
        // حساب عدد الأفرخ المطلوبة للمحتوى الداخلي
        // عدد النسخ × عدد الصفحات ÷ (عدد المونتاج × نوع الفرخ × 2 (وجهين))
        const sheetsCount = Math.ceil((quantity * pageCount) / (montageCount * sheetType * 2));
        
        // تحديث حقل عدد الأفرخ
        internalPaperSheetsCountInput.value = sheetsCount;
        
        // تحديث عنصر المعلومات
        if (internalPaperSheetsInfoElement) {
            internalPaperSheetsInfoElement.textContent = `(${quantity} نسخة × ${pageCount} صفحة) ÷ (${montageCount} × ${sheetType} × 2) = ${sheetsCount} فرخ`;
        }
        
        // تحديث قيمة id_internal_paper_quantity بنفس قيمة id_internal_paper_sheets_count مباشرة
        if (internalPaperQuantityInput) {
            internalPaperQuantityInput.value = sheetsCount;
        }
        
        // حساب وتحديث التكلفة الإجمالية مباشرة
        if (internalPaperPriceInput && internalPaperTotalCostInput) {
            const price = parseFloat(internalPaperPriceInput.value) || 0;
            const totalCost = sheetsCount * price;
            
            internalPaperTotalCostInput.value = totalCost.toFixed(2);
            
            // تحديث حقل تكلفة الورق في قسم التسعير
            if (internalPaperCostSummaryInput) {
                internalPaperCostSummaryInput.value = totalCost.toFixed(2);
            }
            
            // تحديث إجمالي التكلفة
            if (typeof PricingSystem.Pricing !== 'undefined' && typeof PricingSystem.Pricing.calculateCost === 'function') {
                PricingSystem.Pricing.calculateCost();
            }
        }
    },
    
    /**
     * دالة لتحديث إجمالي تكلفة الورق الداخلي
     */
    updateInternalTotalPaperCost: function() {
        const paperQuantityInput = document.getElementById('id_internal_paper_quantity');
        const paperPriceInput = document.getElementById('id_internal_paper_price');
        const paperTotalCostInput = document.getElementById('id_internal_paper_total_cost');
        const paperCostSummaryInput = document.getElementById('id_material_cost');
        
        // التحقق من وجود العناصر المطلوبة
        const missingElements = [];
        if (!paperQuantityInput) missingElements.push('id_internal_paper_quantity');
        if (!paperPriceInput) missingElements.push('id_internal_paper_price');
        if (!paperTotalCostInput) missingElements.push('id_internal_paper_total_cost');
        if (!paperCostSummaryInput) missingElements.push('id_material_cost');
        
        if (missingElements.length > 0) {
            console.log('بعض حقول تكلفة الورق الداخلي غير موجودة:', missingElements.join(', '));
            return; // لا يمكن إكمال الحساب بدون العناصر الأساسية
        }
        
        const quantity = parseFloat(paperQuantityInput.value) || 0;
        const price = parseFloat(paperPriceInput.value) || 0;
        
        // حساب التكلفة الإجمالية
        const totalCost = quantity * price;
        
        // تحديث حقل التكلفة الإجمالية
        paperTotalCostInput.value = totalCost.toFixed(2);
        
        // تحديث حقل تكلفة الورق في قسم التسعير
        paperCostSummaryInput.value = totalCost.toFixed(2);
        
        // تحديث إجمالي التكلفة
        if (typeof PricingSystem.Pricing !== 'undefined' && typeof PricingSystem.Pricing.calculateCost === 'function') {
            PricingSystem.Pricing.calculateCost();
        }
    },
    
    /**
     * تحديث سعر الورق بناءً على المعلومات المحددة
     */
    updatePaperPrice: function() {
        // هذه الدالة تعتمد على وجود دالة updatePaperPrice في كائن API
        // لذلك سنتحقق من وجودها قبل استدعائها
        if (typeof PricingSystem.API !== 'undefined' && typeof PricingSystem.API.updatePaperPrice === 'function') {
            PricingSystem.API.updatePaperPrice();
        } else {
            console.error('دالة updatePaperPrice غير متوفرة في كائن API');
        }
    },
    
    // ... باقي الكود بدون تغيير
}; 