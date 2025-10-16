/**
 * core.js - الدالات الأساسية والتهيئة
 */

// تعريف كائن عام للمشروع
window.PricingSystem = window.PricingSystem || {};

// تهيئة المتغيرات العامة
PricingSystem.init = function() {
    // بيانات أنواع الورق والأوزان
    this.paperTypeWeights = {};
    
    // عناصر النموذج الرئيسية
    this.elements = {
        // المورد وماكينة الطباعة
        supplierSelect: document.getElementById('id_supplier'),
        pressSelect: document.getElementById('id_press'),
        pressPriceInput: document.getElementById('id_press_price_per_1000'),
        pressRunsInput: document.getElementById('id_press_runs'),
        pressTransportationInput: document.getElementById('id_press_transportation'),
        pressTotalCostInput: document.getElementById('id_press_total_cost'),
        
        // الورق
        paperTypeSelect: document.getElementById('id_paper_type'),
        paperWeightSelect: document.getElementById('id_paper_weight'),
        paperSupplierSelect: document.getElementById('id_paper_supplier'),
        paperSheetTypeSelect: document.getElementById('id_paper_sheet_type'),
        
        // الطباعة
        printSidesSelect: document.getElementById('id_print_sides'),
        colorsDesignInput: document.getElementById('id_colors_design'),
        colorsFrontInput: document.getElementById('id_colors_front'),
        colorsBackInput: document.getElementById('id_colors_back'),
        
        // المونتاج
        montageInfoField: document.getElementById('id_montage_info'),
        
        // الكمية
        quantityInput: document.getElementById('id_quantity'),
        
        // التصميم
        designPriceInput: document.getElementById('id_design_price'),
        internalDesignPriceInput: document.getElementById('id_internal_design_price'),
        designPriceSummary: document.getElementById('id_design_price_summary'),
        
        // النموذج
        pricingForm: document.getElementById('pricing-form'),
        
        // المحتوى الداخلي
        hasInternalContent: document.getElementById('id_has_internal_content'),
        internalFields: document.getElementById('internal-fields'),
        internalContentSection: document.getElementById('internal-content-section'),
        step3Element: document.getElementById('step-3'),
        section3Element: document.getElementById('section-3'),
        section2HeaderElement: document.querySelector('#section-2 .section-header h4'),
        step2Element: document.getElementById('step-2'),
        
        // المحتوى الداخلي - عناصر إضافية
        internalPrintSidesSelect: document.getElementById('id_internal_print_sides'),
        internalColorsDesignInput: document.getElementById('id_internal_colors_design'),
        internalColorsFrontInput: document.getElementById('id_internal_colors_front'),
        internalColorsBackInput: document.getElementById('id_internal_colors_back'),
        internalPressRunsInput: document.getElementById('id_internal_press_runs'),
        internalPressPriceInput: document.getElementById('id_internal_press_price_per_1000'),
        internalPressTransportationInput: document.getElementById('id_internal_press_transportation'),
        internalPressTotalCostInput: document.getElementById('id_internal_press_total_cost'),
        internalPageCountInput: document.getElementById('id_internal_page_count')
    };
    
    // محاولة استخراج بيانات أنواع الورق من عنصر مخفي في النموذج
    const paperTypeWeightsElement = document.getElementById('paper_type_weights_data');
    if (paperTypeWeightsElement) {
        try {
            this.paperTypeWeights = JSON.parse(paperTypeWeightsElement.textContent);
        } catch (e) {
            console.error('خطأ في تحليل بيانات أوزان الورق:', e);
        }
    }
    
    // تهيئة وحدة معالجة الورق
    if (typeof this.Paper !== 'undefined' && typeof this.Paper.init === 'function') {
        this.Paper.init();
    }
    
    // تهيئة وحدة معالجة الطباعة
    if (typeof this.Print !== 'undefined' && typeof this.Print.init === 'function') {
        this.Print.init();
    }
    
    // تهيئة وحدة التسعير
    if (typeof this.Pricing !== 'undefined' && typeof this.Pricing.init === 'function') {
        this.Pricing.init();
    }
    
    // إعداد معالجات الأحداث الخاصة بالمورد وماكينة الطباعة
    this.setupSupplierPressHandlers();
    
    // إعداد وظيفة المحتوى الداخلي
    this.setupInternalContentHandlers();
    
    // تحميل بيانات الجلسة
    if (typeof this.Session !== 'undefined' && typeof this.Session.loadSessionData === 'function') {
        this.Session.loadSessionData();
    }
    
    // تهيئة خدمات ما بعد الطباعة
    if (typeof this.Finishing !== 'undefined' && typeof this.Finishing.setupFinishingServices === 'function') {
        this.Finishing.setupFinishingServices();
    }
    
    // تهيئة زنكات CTP
    if (typeof this.CTP !== 'undefined' && typeof this.CTP.setupCtpHandlers === 'function') {
        this.CTP.setupCtpHandlers();
    }
    
    // تهيئة معالجات المونتاج
    if (typeof this.Montage !== 'undefined' && typeof this.Montage.setupMontageHandlers === 'function') {
        this.Montage.setupMontageHandlers();
    }
    
    // تسجيل معالجات الأحداث العامة مع ناقل الأحداث إذا كان متاحًا
    if (PricingSystem.EventBus) {
        this.registerGlobalEventHandlers();
    }
};

/**
 * تسجيل معالجات الأحداث العامة مع ناقل الأحداث
 */
PricingSystem.registerGlobalEventHandlers = function() {
    // الاستماع لتغييرات المحتوى الداخلي
    PricingSystem.EventBus.on('internal-content:changed', (data) => {
        // تجنب تحديث الأقسام مرة أخرى لمنع الحلقة اللانهائية
        // نستخدم فقط البيانات التي تم تمريرها في الحدث
        this.updateSectionsVisibility(data.hasInternal);
    });
    
    // الاستماع لتغييرات القسم
    PricingSystem.EventBus.on('section:changed', (data) => {
        // تحديث التكلفة الإجمالية عند الانتقال إلى قسم التسعير
        if (data.to === 'section-4') {
            PricingSystem.EventBus.emit('pricing:update', { 
                sectionChange: true,
                toSection: data.to
            });
        }
    });
    
    // الاستماع لتحميل النموذج
    PricingSystem.EventBus.on('form:loaded', (data) => {
        // تحديث حالة المحتوى الداخلي
        const hasInternalContent = this.elements.hasInternalContent;
        if (hasInternalContent) {
            this.updateSectionsBasedOnInternalContent(hasInternalContent.checked);
        }
    });
};

/**
 * إعداد معالجات الأحداث للمحتوى الداخلي
 */
PricingSystem.setupInternalContentHandlers = function() {
    const elements = this.elements;
    
    // التحقق من وجود عنصر المحتوى الداخلي
    if (elements.hasInternalContent) {
        // إضافة مستمع حدث لتغيير حالة المحتوى الداخلي
        elements.hasInternalContent.addEventListener('change', function() {
            const isChecked = this.checked;
            
            // تحديث الواجهة
            PricingSystem.updateSectionsBasedOnInternalContent(isChecked);
            
            // إطلاق حدث تغيير المحتوى الداخلي عبر ناقل الأحداث
            if (PricingSystem.EventBus) {
                PricingSystem.EventBus.fieldChanged('id_has_internal_content', isChecked, true);
            }
        });
        
        // تحديث الواجهة عند التحميل
        this.updateSectionsBasedOnInternalContent(elements.hasInternalContent.checked);
    } else {
        // تجاهل الأخطاء إذا كان العنصر غير موجود في هذه الصفحة
        // هذه الوظيفة قد تكون غير مطلوبة في بعض الصفحات
        return;
    }
};

/**
 * تحديث الأقسام بناءً على حالة المحتوى الداخلي
 * @param {boolean} hasInternal - هل يحتوي على محتوى داخلي
 */
PricingSystem.updateSectionsBasedOnInternalContent = function(hasInternal) {
    // تحديث العناصر المرئية
    this.updateSectionsVisibility(hasInternal);
    
    // إطلاق حدث تغيير المحتوى الداخلي عبر ناقل الأحداث
    if (PricingSystem.EventBus) {
        // استخدام علامة skipRecursion لمنع الحلقة اللانهائية
        PricingSystem.EventBus.emit('internal-content:changed', { 
            hasInternal: hasInternal,
            skipRecursion: true 
        });
    }
};

/**
 * تحديث رؤية الأقسام بناءً على حالة المحتوى الداخلي
 * هذه الدالة تتعامل فقط مع تحديث العناصر المرئية دون إطلاق أحداث
 * @param {boolean} hasInternal - هل يحتوي على محتوى داخلي
 */
PricingSystem.updateSectionsVisibility = function(hasInternal) {
    const elements = this.elements;
    
    // إظهار/إخفاء حقول المحتوى الداخلي في القسم الأول
    if (elements.internalFields) {
        elements.internalFields.style.display = hasInternal ? 'block' : 'none';
    }
    
    if (elements.internalContentSection) {
        elements.internalContentSection.style.display = hasInternal ? 'block' : 'none';
    }
    
    // إظهار/إخفاء خطوة المحتوى الداخلي
    if (elements.step3Element) {
        elements.step3Element.style.display = hasInternal ? 'block' : 'none';
    }
    
    if (elements.section3Element) {
        elements.section3Element.style.display = hasInternal ? 'block' : 'none';
    }
    
    // تغيير عنوان القسم الثاني
    if (elements.section2HeaderElement) {
        if (hasInternal) {
            // عند تفعيل المحتوى الداخلي
            elements.section2HeaderElement.innerHTML = '🖨️ تفاصيل الغلاف';
        } else {
            // عند إلغاء تفعيل المحتوى الداخلي
            elements.section2HeaderElement.innerHTML = '🖨️ تفاصيل الطباعة';
        }
    }
    
    if (elements.step2Element) {
        if (hasInternal) {
            elements.step2Element.textContent = 'تفاصيل الغلاف';
        } else {
            elements.step2Element.textContent = 'تفاصيل الطباعة';
        }
    }
};

/**
 * إعداد معالجات الأحداث للمورد وماكينة الطباعة
 */
PricingSystem.setupSupplierPressHandlers = function() {
    const elements = this.elements;
    
    // معالجات أحداث المورد وماكينة الطباعة
    if (elements.supplierSelect && elements.pressSelect) {
        
        // التحقق مما إذا كان هناك قيمة محددة بالفعل للمورد
        if (elements.supplierSelect.value) {
            // استخدام دالة loadPressesDirectly إذا كانت موجودة، وإلا استخدام API.loadPresses
            if (typeof window.loadPressesDirectly === 'function') {
                window.loadPressesDirectly(elements.supplierSelect.value);
            } else {
                setTimeout(() => {
                    this.API.loadPresses(elements.supplierSelect.value, elements.pressSelect, elements.pressPriceInput);
                }, 500);
            }
        }
        
        // إضافة معالج حدث لتغيير المورد
        elements.supplierSelect.addEventListener('change', (event) => {            
            // استخدام دالة loadPressesDirectly إذا كانت موجودة، وإلا استخدام API.loadPresses
            if (typeof window.loadPressesDirectly === 'function') {
                window.loadPressesDirectly(event.target.value);
            } else {
                this.API.loadPresses(event.target.value, elements.pressSelect, elements.pressPriceInput);
            }
            
            // إطلاق حدث تغيير المورد عبر ناقل الأحداث
            if (PricingSystem.EventBus) {
                PricingSystem.EventBus.fieldChanged('id_supplier', event.target.value, true);
            }
        });
        
        // إضافة معالج حدث لتغيير ماكينة الطباعة
        elements.pressSelect.addEventListener('change', function() {
            
            // استخدام دالة updatePressInfo إذا كانت موجودة، وإلا استخدام الكود المباشر
            if (typeof window.updatePressInfo === 'function') {
                window.updatePressInfo(this);
            } else {
                if (this.value) {
                    // التحقق من وجود سعر في البيانات المخزنة في القائمة
                    const selectedOption = this.options[this.selectedIndex];
                    if (selectedOption && selectedOption.dataset.price) {
                        elements.pressPriceInput.value = selectedOption.dataset.price;
                        
                        // إطلاق حدث تغيير سعر الماكينة عبر ناقل الأحداث
                        if (PricingSystem.EventBus) {
                            PricingSystem.EventBus.fieldChanged('id_press_price_per_1000', selectedOption.dataset.price);
                        } else {
                            // استخدام الطريقة القديمة إذا لم يكن ناقل الأحداث متاحًا
                            setTimeout(() => PricingSystem.Print.calculatePressCost(), 100);
                        }
                    } else {
                        // إذا لم يتم العثور على السعر في البيانات المخزنة، استدعاء API
                        PricingSystem.API.fetchPressPrice(this.value, elements.pressPriceInput);
                    }
                    
                    // تحديث معلومات المونتاج عند اختيار ماكينة طباعة
                    PricingSystem.Montage.updateMontageInfo(elements.montageInfoField);
                    
                    // حساب عدد التراجات تلقائيًا
                    if (PricingSystem.EventBus) {
                        // سيتم التعامل مع هذا من خلال ناقل الأحداث
                        PricingSystem.EventBus.fieldChanged('id_press', this.value, true);
                    } else {
                        // استخدام الطريقة القديمة إذا لم يكن ناقل الأحداث متاحًا
                        PricingSystem.Print.calculatePressRuns();
                    }
                } else {
                    elements.pressPriceInput.value = '';
                    
                    // إطلاق حدث تغيير سعر الماكينة عبر ناقل الأحداث
                    if (PricingSystem.EventBus) {
                        PricingSystem.EventBus.fieldChanged('id_press_price_per_1000', '');
                    }
                }
            }
        });
    }
    
    // معالجات أحداث المورد وماكينة الطباعة للمحتوى الداخلي
    const internalSupplierSelect = document.getElementById('id_internal_supplier');
    const internalPressSelect = document.getElementById('id_internal_press');
    
    if (internalSupplierSelect && internalPressSelect && elements.internalPressPriceInput) {
        // التحقق مما إذا كان هناك قيمة محددة بالفعل للمورد الداخلي
        if (internalSupplierSelect.value) {
            setTimeout(() => {
                this.API.loadPresses(internalSupplierSelect.value, internalPressSelect, elements.internalPressPriceInput);
            }, 500);
        }
        
        // إضافة معالج حدث لتغيير المورد الداخلي
        internalSupplierSelect.addEventListener('change', (event) => {            
            this.API.loadPresses(event.target.value, internalPressSelect, elements.internalPressPriceInput);
            
            // إطلاق حدث تغيير المورد الداخلي عبر ناقل الأحداث
            if (PricingSystem.EventBus) {
                PricingSystem.EventBus.fieldChanged('id_internal_supplier', event.target.value, true);
            }
        });
        
        // إضافة معالج حدث لتغيير ماكينة الطباعة الداخلية
        internalPressSelect.addEventListener('change', function() {
            if (this.value) {
                // التحقق من وجود سعر في البيانات المخزنة في القائمة
                const selectedOption = this.options[this.selectedIndex];
                if (selectedOption && selectedOption.dataset.price) {
                    elements.internalPressPriceInput.value = selectedOption.dataset.price;
                    
                    // إطلاق حدث تغيير سعر الماكينة الداخلية عبر ناقل الأحداث
                    if (PricingSystem.EventBus) {
                        PricingSystem.EventBus.fieldChanged('id_internal_press_price_per_1000', selectedOption.dataset.price);
                    } else {
                        // استخدام الطريقة القديمة إذا لم يكن ناقل الأحداث متاحًا
                        setTimeout(() => PricingSystem.Print.calculateInternalPressCost(), 100);
                    }
                } else {
                    // إذا لم يتم العثور على السعر في البيانات المخزنة، استدعاء API
                    PricingSystem.API.fetchPressPrice(this.value, elements.internalPressPriceInput);
                }
                
                // حساب عدد التراجات الداخلية تلقائيًا
                if (PricingSystem.EventBus) {
                    // سيتم التعامل مع هذا من خلال ناقل الأحداث
                    PricingSystem.EventBus.fieldChanged('id_internal_press', this.value, true);
                } else {
                    // استخدام الطريقة القديمة إذا لم يكن ناقل الأحداث متاحًا
                    PricingSystem.Print.calculateInternalPressRuns();
                }
            } else {
                elements.internalPressPriceInput.value = '';
                
                // إطلاق حدث تغيير سعر الماكينة الداخلية عبر ناقل الأحداث
                if (PricingSystem.EventBus) {
                    PricingSystem.EventBus.fieldChanged('id_internal_press_price_per_1000', '');
                }
            }
        });
    }
};

// تنفيذ التهيئة عند اكتمال تحميل الصفحة
document.addEventListener('DOMContentLoaded', function() {
    // تم نقل PricingSystem.init() إلى main.js لتجنب التكرار
    
    // إطلاق حدث تحميل النموذج عبر ناقل الأحداث
    if (PricingSystem.EventBus) {
        PricingSystem.EventBus.emit('form:loaded', { timestamp: Date.now() });
    }
}); 