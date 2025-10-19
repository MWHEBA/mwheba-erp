/**
 * montage-handlers.js - دالات معالجة المونتاج
 */

// تعريف كائن عام للمشروع إذا لم يكن موجودًا
window.PricingSystem = window.PricingSystem || {};

// تعريف وحدة معالجة المونتاج
PricingSystem.Montage = {
    // إنشاء instance من الحاسبة الجديدة
    calculator: null,
    
    /**
     * إعداد معالجات المونتاج الشاملة
     */
    setupMontageHandlers: function() {
        // إنشاء الحاسبة الجديدة إذا كانت متاحة
        if (typeof MontageCalculator !== 'undefined') {
            this.calculator = new MontageCalculator();
        }
        
        // تسجيل معالجات الأحداث مع ناقل الأحداث إذا كان متاحًا
        if (PricingSystem.EventBus) {
            this.registerEventHandlers();
        } else {
            // استخدام الطريقة التقليدية
            this.setupTraditionalEventHandlers();
        }
    },
    
    /**
     * تسجيل معالجات الأحداث مع ناقل الأحداث
     */
    registerEventHandlers: function() {
        // الاستماع لتغييرات مقاس الورق وماكينة الطباعة للغلاف
        const coverFields = ['id_product_size', 'id_press', 'id_custom_size_width', 'id_custom_size_height'];
        coverFields.forEach(fieldId => {
            PricingSystem.EventBus.on(`field:${fieldId}:changed`, (data) => {
                const montageInfoField = document.getElementById('id_montage_info');
                if (montageInfoField) {
                    this.updateMontageInfo(montageInfoField);
                }
            });
        });
        
        // الاستماع لتغييرات أبعاد التصميم وماكينة الطباعة للمحتوى الداخلي
        const internalFields = ['id_internal_design_width', 'id_internal_design_height', 'id_internal_press'];
        internalFields.forEach(fieldId => {
            PricingSystem.EventBus.on(`field:${fieldId}:changed`, (data) => {
                const internalMontageInfoField = document.getElementById('id_internal_montage_info');
                if (internalMontageInfoField) {
                    this.updateMontageInfo(internalMontageInfoField, true);
                }
            });
        });
        
        // الاستماع لتغييرات في قائمة الماكينات (press_selector)
        PricingSystem.EventBus.on(`field:press_selector:changed`, (data) => {
            const montageInfoField = document.getElementById('id_montage_info');
            if (montageInfoField) {
                // تأخير قصير لضمان تحديث قيمة id_press قبل حساب المونتاج
                setTimeout(() => {
                    this.updateMontageInfo(montageInfoField);
                }, 100);
            }
        });
        
        // الاستماع لتغييرات في قائمة الماكينات الداخلية (internal_press_selector)
        PricingSystem.EventBus.on(`field:internal_press_selector:changed`, (data) => {
            const internalMontageInfoField = document.getElementById('id_internal_montage_info');
            if (internalMontageInfoField) {
                // تأخير قصير لضمان تحديث قيمة id_internal_press قبل حساب المونتاج
                setTimeout(() => {
                    this.updateMontageInfo(internalMontageInfoField, true);
                }, 100);
            }
        });
        
        // الاستماع لتحديثات الحقول المتعلقة بالمونتاج
        PricingSystem.EventBus.on('fields:updated', (data) => {
            const montageRelatedFields = [
                'id_product_size', 'id_press', 'id_custom_size_width', 'id_custom_size_height',
                'press_selector'
            ];
            
            const shouldUpdateMontage = data.changedFields.some(field => 
                montageRelatedFields.includes(field)
            );
            
            if (shouldUpdateMontage) {
                const montageInfoField = document.getElementById('id_montage_info');
                if (montageInfoField) {
                    this.updateMontageInfo(montageInfoField);
                }
            }
            
            const internalMontageRelatedFields = [
                'id_internal_design_width', 'id_internal_design_height', 'id_internal_press',
                'internal_press_selector'
            ];
            
            const shouldUpdateInternalMontage = data.changedFields.some(field => 
                internalMontageRelatedFields.includes(field)
            );
            
            if (shouldUpdateInternalMontage) {
                const internalMontageInfoField = document.getElementById('id_internal_montage_info');
                if (internalMontageInfoField) {
                    this.updateMontageInfo(internalMontageInfoField, true);
                }
            }
        });
        
        // الاستماع لتغييرات عدد المونتاج لتحديث عدد أفرخ الورق
        PricingSystem.EventBus.on(`field:id_montage_count:changed`, (data) => {
            // التحقق من وجود نوع الورق قبل حساب كمية الورق
            const paperTypeSelect = document.getElementById('id_paper_type');
            if (paperTypeSelect && paperTypeSelect.value && 
                PricingSystem.Paper && typeof PricingSystem.Paper.calculatePaperSheetsDirectly === 'function') {
                PricingSystem.Paper.calculatePaperSheetsDirectly();
            } else {
                console.log('نوع الورق غير محدد - تخطي حساب كمية الورق من تغيير المونتاج');
            }
        });
        
        // الاستماع لتغييرات عدد المونتاج الداخلي لتحديث عدد أفرخ الورق الداخلي
        PricingSystem.EventBus.on(`field:id_internal_montage_count:changed`, (data) => {
            if (PricingSystem.Paper && typeof PricingSystem.Paper.calculateInternalPaperSheets === 'function') {
                PricingSystem.Paper.calculateInternalPaperSheets();
            }
        });
    },
    
    /**
     * إعداد معالجات الأحداث التقليدية (بدون ناقل الأحداث)
     */
    setupTraditionalEventHandlers: function() {
        console.log('إعداد معالجات الأحداث التقليدية...');
        
        // الحصول على القيم من النموذج
        const quantity = parseInt(document.getElementById('id_quantity')?.value) || 1000;
        const designWidth = parseFloat(document.getElementById('id_custom_size_width')?.value) || 0;
        const designHeight = parseFloat(document.getElementById('id_custom_size_height')?.value) || 0;
        
        const pressSelect = document.getElementById('id_press');
        const paperSizeSelect = document.getElementById('id_product_size');
        const customSizeWidthInput = document.getElementById('id_custom_size_width');
        const customSizeHeightInput = document.getElementById('id_custom_size_height');
        const montageInfoField = document.getElementById('id_montage_info');
        
        if (pressSelect && montageInfoField) {
            // عند تغيير مقاس الورق أو ماكينة الطباعة، قم بتحديث معلومات المونتاج
            const updateMontageOnChange = () => {
                console.log('تم تشغيل updateMontageOnChange');
                this.updateMontageInfo(montageInfoField);
            };
            
            if (paperSizeSelect) {
                paperSizeSelect.addEventListener('change', updateMontageOnChange);
            }
            pressSelect.addEventListener('change', updateMontageOnChange);
            
            // إذا كان هناك مقاس مخصص، أضف مستمعات الأحداث له أيضًا
            if (customSizeWidthInput && customSizeHeightInput) {
                customSizeWidthInput.addEventListener('change', updateMontageOnChange);
                customSizeHeightInput.addEventListener('change', updateMontageOnChange);
                customSizeWidthInput.addEventListener('input', updateMontageOnChange);
                customSizeHeightInput.addEventListener('input', updateMontageOnChange);
            }
            
            // إضافة معالجات لحقول أخرى قد تؤثر على المونتاج
            const designWidthInput = document.getElementById('id_design_width');
            const designHeightInput = document.getElementById('id_design_height');
            
            if (designWidthInput) {
                designWidthInput.addEventListener('change', updateMontageOnChange);
                designWidthInput.addEventListener('input', updateMontageOnChange);
            }
            
            if (designHeightInput) {
                designHeightInput.addEventListener('change', updateMontageOnChange);
                designHeightInput.addEventListener('input', updateMontageOnChange);
            }
            
            // معالج لـ press_selector إذا كان موجوداً
            const pressSelectorSelect = document.getElementById('press_selector');
            if (pressSelectorSelect) {
                pressSelectorSelect.addEventListener('change', () => {
                    setTimeout(() => {
                        updateMontageOnChange();
                    }, 100);
                });
            }
        }
        
        // إعداد معالجات أحداث التصميم الداخلي لحساب المونتاج
        const internalDesignWidthInput = document.getElementById('id_internal_design_width');
        const internalDesignHeightInput = document.getElementById('id_internal_design_height');
        const internalPressSelect = document.getElementById('id_internal_press');
        const internalMontageInfoField = document.getElementById('id_internal_montage_info');
        
        if (internalDesignWidthInput && internalDesignHeightInput && internalPressSelect && internalMontageInfoField) {
            // عند تغيير أبعاد التصميم الداخلي أو ماكينة الطباعة، قم بتحديث معلومات المونتاج
            const updateInternalMontageOnChange = () => {
                this.updateMontageInfo(internalMontageInfoField, true);
            };
            
            internalDesignWidthInput.addEventListener('change', updateInternalMontageOnChange);
            internalDesignHeightInput.addEventListener('change', updateInternalMontageOnChange);
            internalPressSelect.addEventListener('change', updateInternalMontageOnChange);
        }
    },
    
    /**
     * دالة لتحديث معلومات المونتاج
     * @param {HTMLInputElement} montageInfoField - حقل معلومات المونتاج
     * @param {boolean} isInternal - هل هو للمحتوى الداخلي
     */
    updateMontageInfo: function(montageInfoField, isInternal = false) {
        console.log('تم استدعاء updateMontageInfo، isInternal:', isInternal);
        
        if (!montageInfoField) {
            console.warn('حقل معلومات المونتاج غير موجود');
            return;
        }
        
        if (isInternal) {
            console.log('تحويل إلى updateInternalMontageInfo');
            this.updateInternalMontageInfo(montageInfoField);
            return;
        }
        
        console.log('بدء معالجة المونتاج الرئيسي...');
        
        const pressSelect = document.getElementById('id_press');
        let paperSizeSelect = document.getElementById('id_product_size');
        
        // البحث عن حقول مقاس الورق البديلة
        if (!paperSizeSelect) {
            const possiblePaperFields = [
                'id_paper_sheet_type',
                'id_paper_type', 
                'id_sheet_type',
                'paper_size',
                'paper_sheet_type',
                'sheet_type'
            ];
            
            console.log('البحث عن حقول مقاس الورق البديلة...');
            for (const fieldId of possiblePaperFields) {
                paperSizeSelect = document.getElementById(fieldId);
                if (paperSizeSelect) {
                    console.log('تم العثور على حقل مقاس الورق:', fieldId);
                    break;
                }
            }
        }
        
        let customSizeWidthInput = document.getElementById('id_custom_size_width');
        let customSizeHeightInput = document.getElementById('id_custom_size_height');
        
        // البحث عن حقول أبعاد التصميم البديلة
        if (!customSizeWidthInput || !customSizeHeightInput) {
            const possibleWidthFields = ['id_design_width', 'design_width', 'width'];
            const possibleHeightFields = ['id_design_height', 'design_height', 'height'];
            
            console.log('البحث عن حقول أبعاد التصميم البديلة...');
            
            if (!customSizeWidthInput) {
                for (const fieldId of possibleWidthFields) {
                    customSizeWidthInput = document.getElementById(fieldId);
                    if (customSizeWidthInput) {
                        console.log('تم العثور على حقل العرض:', fieldId);
                        break;
                    }
                }
            }
            
            if (!customSizeHeightInput) {
                for (const fieldId of possibleHeightFields) {
                    customSizeHeightInput = document.getElementById(fieldId);
                    if (customSizeHeightInput) {
                        console.log('تم العثور على حقل الارتفاع:', fieldId);
                        break;
                    }
                }
            }
        }
        
        if (!pressSelect) {
            console.warn('حقل ماكينة الطباعة غير موجود');
            montageInfoField.value = 'يرجى اختيار ماكينة الطباعة';
            return;
        }
        
        const pressId = pressSelect.value;
        
        if (!paperSizeSelect) {
            console.warn('حقل مقاس الورق غير موجود - محاولة استخدام أبعاد التصميم مباشرة');
            
            // محاولة استخدام أبعاد التصميم مباشرة
            if (customSizeWidthInput && customSizeHeightInput) {
                const designWidth = parseFloat(customSizeWidthInput.value);
                const designHeight = parseFloat(customSizeHeightInput.value);
                
                if (designWidth && designHeight && designWidth > 0 && designHeight > 0) {
                    console.log('استخدام أبعاد التصميم مباشرة:', designWidth, 'x', designHeight);
                    this.calculateMontageWithPressAndDesign(pressId, designWidth, designHeight, montageInfoField);
                    return;
                } else {
                    montageInfoField.value = 'يرجى إدخال أبعاد التصميم';
                    return;
                }
            } else {
                montageInfoField.value = 'حقول مقاس الورق وأبعاد التصميم غير متاحة';
                return;
            }
        }
        console.log('معرف الماكينة المحددة:', pressId);
        
        if (!pressId) {
            console.warn('لم يتم اختيار ماكينة طباعة');
            montageInfoField.value = 'يجب اختيار ماكينة الطباعة أولاً';
            return;
        }
        
        // الحصول على مقاس التصميم من مقاس الورق أو المقاس المخصص
        let designWidth, designHeight;
        
        // التحقق مما إذا كان المقاس المخصص محدد
        console.log('مقاس الورق المحدد:', paperSizeSelect ? paperSizeSelect.value : 'حقل مقاس الورق غير موجود');
        
        // أولاً: التحقق من اختيار المقاس المخصص
        if (paperSizeSelect && paperSizeSelect.value === 'custom' && 
            customSizeWidthInput && customSizeHeightInput && 
            customSizeWidthInput.value && customSizeHeightInput.value &&
            parseFloat(customSizeWidthInput.value) > 0 && parseFloat(customSizeHeightInput.value) > 0) {
            
            designWidth = parseFloat(customSizeWidthInput.value);
            designHeight = parseFloat(customSizeHeightInput.value);
            console.log('استخدام المقاس المخصص من الحقول - العرض:', designWidth, 'الارتفاع:', designHeight);
            this.calculateMontageWithPressAndDesign(pressId, designWidth, designHeight, montageInfoField);
            return;
            
        } else if (paperSizeSelect && paperSizeSelect.value && paperSizeSelect.value.trim() !== '') {
            console.log('استخدام مقاس ورق معياري، جاري الحصول على الأبعاد...');
            
            // استخدام مقاس الورق المحدد كمقاس التصميم (الحالة الافتراضية)
            console.log('معرف مقاس الورق المرسل للAPI:', paperSizeSelect.value);
            console.log('نص مقاس الورق المحدد:', paperSizeSelect.options[paperSizeSelect.selectedIndex]?.text);
            
            // التحقق من التضارب بين النص والقيمة
            const selectedText = paperSizeSelect.options[paperSizeSelect.selectedIndex]?.text || '';
            console.log('فحص التضارب - النص المحدد:', selectedText, 'القيمة المرسلة:', paperSizeSelect.value);
            
            // معالجة المقاسات الشائعة بناءً على النص المعروض
            if (selectedText.includes('A3')) {
                console.log('تم اكتشاف A3 - استخدام أبعاد A3 مباشرة (30×42)');
                designWidth = 30;
                designHeight = 42;
                this.calculateMontageWithPressAndDesign(pressId, designWidth, designHeight, montageInfoField);
                return;
            } else if (selectedText.includes('A4')) {
                console.log('تم اكتشاف A4 - استخدام أبعاد A4 مباشرة (21×30)');
                designWidth = 21;
                designHeight = 30;
                this.calculateMontageWithPressAndDesign(pressId, designWidth, designHeight, montageInfoField);
                return;
                } else if (selectedText.includes('A5')) {
                    console.log('تم اكتشاف A5 - استخدام أبعاد A5 مباشرة (15×21)');
                    designWidth = 15;
                    designHeight = 21;
                    this.calculateMontageWithPressAndDesign(pressId, designWidth, designHeight, montageInfoField);
                    return;
                } else if (selectedText.includes('A6')) {
                    console.log('تم اكتشاف A6 - استخدام أبعاد A6 مباشرة (10.5×15)');
                    designWidth = 10.5;
                    designHeight = 15;
                    this.calculateMontageWithPressAndDesign(pressId, designWidth, designHeight, montageInfoField);
                    return;
                } else if (selectedText.includes('بزنس كارد') || selectedText.includes('business card')) {
                    console.log('تم اكتشاف بزنس كارد - استخدام أبعاد البزنس كارد (5.5×9)');
                    designWidth = 5.5;
                    designHeight = 9;
                    this.calculateMontageWithPressAndDesign(pressId, designWidth, designHeight, montageInfoField);
                    return;
                } else if (selectedText.includes('فلاير') || selectedText.includes('flyer')) {
                    console.log('تم اكتشاف فلاير - استخدام أبعاد الفلاير الشائع (15×21)');
                    designWidth = 15;
                    designHeight = 21;
                    this.calculateMontageWithPressAndDesign(pressId, designWidth, designHeight, montageInfoField);
                    return;
                } else if (selectedText.includes('مخصص') || selectedText.includes('custom')) {
                    // التحقق من حقول المقاس المخصص
                    if (customSizeWidthInput && customSizeHeightInput && 
                        customSizeWidthInput.value && customSizeHeightInput.value &&
                        parseFloat(customSizeWidthInput.value) > 0 && parseFloat(customSizeHeightInput.value) > 0) {
                        
                        designWidth = parseFloat(customSizeWidthInput.value);
                        designHeight = parseFloat(customSizeHeightInput.value);
                        console.log('استخدام المقاس المخصص:', designWidth, 'x', designHeight);
                        this.calculateMontageWithPressAndDesign(pressId, designWidth, designHeight, montageInfoField);
                        return;
                    } else {
                        montageInfoField.value = 'يرجى إدخال أبعاد المقاس المخصص';
                        return;
                    }
                }
                
                this.getPaperSizeDimensions(paperSizeSelect.value)
                    .then(dimensions => {
                        console.log('استخدام مقاس الورق كمقاس التصميم:', dimensions);
                        console.log('تحقق: هل هذا A4؟', dimensions.name, dimensions.width, dimensions.height);
                        designWidth = dimensions.width;
                        designHeight = dimensions.height;
                        
                        // بعد الحصول على أبعاد الورق، نستمر في حساب المونتاج
                        this.calculateMontageWithPressAndDesign(pressId, designWidth, designHeight, montageInfoField);
                    })
                    .catch(error => {
                        console.error('خطأ في الحصول على أبعاد مقاس الورق:', error.message);
                        montageInfoField.value = error.message;
                    });
        } else {
            console.warn('مقاس الورق فارغ - محاولة استخدام أبعاد التصميم مباشرة');
            
            // محاولة استخدام أبعاد التصميم مباشرة
            if (customSizeWidthInput && customSizeHeightInput) {
                designWidth = parseFloat(customSizeWidthInput.value);
                designHeight = parseFloat(customSizeHeightInput.value);
                
                if (designWidth && designHeight && designWidth > 0 && designHeight > 0) {
                    console.log('استخدام أبعاد التصميم مباشرة (مقاس ورق فارغ):', designWidth, 'x', designHeight);
                    this.calculateMontageWithPressAndDesign(pressId, designWidth, designHeight, montageInfoField);
                    return;
                } else {
                    montageInfoField.value = 'يرجى إدخال أبعاد التصميم';
                    return;
                }
            } else {
                montageInfoField.value = 'يرجى اختيار مقاس الورق أو إدخال أبعاد التصميم';
                return;
            }
        }
    },
    
    /**
     * دالة مساعدة لحساب المونتاج بعد الحصول على أبعاد الماكينة والتصميم
     */
    calculateMontageWithPressAndDesign: function(pressId, designWidth, designHeight, montageInfoField) {
        console.log('بدء حساب المونتاج - معرف الماكينة:', pressId, 'أبعاد التصميم:', designWidth, 'x', designHeight);
        
        // الحصول على مقاس الورق المحدد
        const paperSizeSelect = document.getElementById('id_product_size');
        if (!paperSizeSelect || !paperSizeSelect.value) {
            montageInfoField.value = 'يرجى اختيار مقاس الورق أولاً';
            return;
        }
        
        // الحصول على مقاس الورق ومقاس الماكينة
        Promise.all([
            this.getPaperSizeDimensions(paperSizeSelect.value),
            this.getPressSize(pressId)
        ])
            .then(([paperSize, pressSize]) => {
                console.log('مقاس الورق المسترجع:', paperSize);
                console.log('مقاس الماكينة المسترجع:', pressSize);
                
                // معالجة خاصة للمقاس المخصص
                if (paperSizeSelect.value === 'custom') {
                    console.log('معالجة مقاس مخصص - أبعاد التصميم:', designWidth, 'x', designHeight);
                    
                    // للمقاس المخصص، نستخدم أبعاد التصميم مباشرة
                    const montageResult = this.calculateMontageForCustomSize(designWidth, designHeight, pressSize);
                    montageInfoField.value = montageResult;
                    return;
                }
                
                // تحديد مقاس الطباعة الفعلي بناءً على نوع الورق والماكينة (للمقاسات المعيارية فقط)
                let actualPrintSize;
                
                // التحقق من نوع الورق (جاير أم كامل)
                const isJayerPaper = paperSize.width === 70 && paperSize.height === 100; // فرخ جاير
                
                // تحديد مقاس الماكينة الفعلي
                if (isJayerPaper && pressSize.width === 35 && pressSize.height === 50) {
                    // ورق جاير + ماكينة ربع فرخ = ربع جاير (33×44)
                    actualPrintSize = {
                        width: 33,
                        height: 44
                    };
                    console.log('تم اكتشاف ورق جاير مع ماكينة ربع فرخ - استخدام ربع جاير (33×44)');
                } else if (isJayerPaper && pressSize.width === 50 && pressSize.height === 70) {
                    // ورق جاير + ماكينة نصف فرخ = نصف جاير (33×50)
                    actualPrintSize = {
                        width: 33,
                        height: 50
                    };
                    console.log('تم اكتشاف ورق جاير مع ماكينة نصف فرخ - استخدام نصف جاير (33×50)');
                } else {
                    // الحالة العادية: الأصغر بين الورق والماكينة
                    actualPrintSize = {
                        width: Math.min(paperSize.width, pressSize.width),
                        height: Math.min(paperSize.height, pressSize.height)
                    };
                }
                
                console.log('مقاس الطباعة الفعلي:', actualPrintSize);
                
                // حساب المونتاج بناءً على مقاس الطباعة الفعلي
                const designSize = { width: designWidth, height: designHeight };
                console.log('بدء حساب المونتاج بالبيانات:', { actualPrintSize, designSize });
                const montageResult = this.calculateMontage(actualPrintSize, designSize);
                console.log('نتيجة حساب المونتاج:', montageResult);
                
                // الحصول على نوع الماكينة المكتوب بين القوسين
                let pressSheetType = montageResult.sheetType; // القيمة الافتراضية
                
                // محاولة استخراج نوع الماكينة من اسم الماكينة المحددة
                const internalPressElement = document.getElementById('id_internal_press');
                const isInternalPress = internalPressElement && pressId === internalPressElement.value;
                
                // البحث عن عنصر الماكينة المحددة
                let pressSelect = null;
                
                if (isInternalPress) {
                    pressSelect = document.getElementById('id_internal_press');
                } else {
                    // محاولة العثور على عنصر press_selector أولاً
                    pressSelect = document.getElementById('press_selector');
                    // إذا لم يتم العثور عليه، نبحث عن id_press
                    if (!pressSelect) {
                        pressSelect = document.getElementById('id_press');
                    }
                }
                                
                if (pressSelect && pressSelect.selectedIndex >= 0) {
                    const selectedOption = pressSelect.options[pressSelect.selectedIndex];
                    if (selectedOption) {
                        const pressName = selectedOption.textContent || '';
                        
                        // محاولة استخراج النص بين قوسين
                        const match = pressName.match(/\(([^)]+)\)/);
                        if (match && match[1]) {
                            pressSheetType = match[1].trim();
                        }
                    }
                } else {
                    
                    // محاولة أخيرة للعثور على الماكينة من خلال البحث عن جميع قوائم الاختيار في الصفحة
                    const allSelects = document.querySelectorAll('select');
                    
                    for (const select of allSelects) {
                        
                        const option = select.querySelector(`option[value="${pressId}"]`);
                        if (option) {
                            const pressName = option.textContent || '';                            
                            // محاولة استخراج النص بين قوسين
                            const match = pressName.match(/\(([^)]+)\)/);
                            if (match && match[1]) {
                                pressSheetType = match[1].trim();
                                break;
                            }
                        }
                    }
                }
                
                // تنسيق رسالة المونتاج بالشكل الصحيح باستخدام نوع الماكينة المستخرج
                const formattedMessage = `${montageResult.count} / ${pressSheetType}`;                
                // تحديث حقل معلومات المونتاج
                montageInfoField.value = formattedMessage;
                
                // تحديث حقل عدد المونتاج
                const montageCountField = document.getElementById('id_montage_count');
                if (montageCountField) {
                    montageCountField.value = montageResult.count;
                    
                    // تحديث كمية الورق المطلوبة فقط إذا كان نوع الورق محدد
                    const paperTypeSelect = document.getElementById('id_paper_type');
                    if (paperTypeSelect && paperTypeSelect.value && 
                        typeof PricingSystem.Paper !== 'undefined' && 
                        typeof PricingSystem.Paper.calculatePaperSheetsDirectly === 'function') {
                        PricingSystem.Paper.calculatePaperSheetsDirectly();
                    } else {
                        console.log('نوع الورق غير محدد - تخطي حساب كمية الورق من المونتاج');
                    }
                } else {
                    console.warn('حقل عدد المونتاج غير موجود');
                }
            })
            .catch(error => {
                console.error('خطأ في الحصول على بيانات الطباعة:', error.message);
                montageInfoField.value = error.message;
            });
    },
    
    /**
     * دالة للحصول على أبعاد مقاس الورق
     * @param {number} paperSizeId - معرف مقاس الورق
     * @returns {Promise} وعد يحتوي على أبعاد الورق
     */
    getPaperSizeDimensions: function(paperSizeId) {
        return new Promise((resolve, reject) => {
            // التحقق من وجود معرف مقاس الورق
            if (!paperSizeId || paperSizeId === '' || paperSizeId === 'undefined' || paperSizeId === 'null') {
                reject(new Error('معرف مقاس الورق مطلوب - يرجى اختيار مقاس الورق من القائمة'));
                return;
            }
            
            // معالجة خاصة للمقاس المخصص
            if (paperSizeId === 'custom') {
                const widthInput = document.getElementById('id_custom_size_width');
                const heightInput = document.getElementById('id_custom_size_height');
                
                if (widthInput && heightInput && widthInput.value && heightInput.value) {
                    const width = parseFloat(widthInput.value);
                    const height = parseFloat(heightInput.value);
                    
                    if (width > 0 && height > 0) {
                        const dimensions = { width: width, height: height };
                        console.log('استخدام المقاس المخصص:', dimensions);
                        resolve(dimensions);
                        return;
                    } else {
                        reject(new Error('يرجى إدخال أبعاد صحيحة للمقاس المخصص'));
                        return;
                    }
                } else {
                    reject(new Error('يرجى إدخال العرض والارتفاع للمقاس المخصص'));
                    return;
                }
            }
            
            // مخزن للقيم المسترجعة من الخادم (لتجنب استدعاء API متكرر)
            if (!window.paperSizeDimensionsCache) {
                window.paperSizeDimensionsCache = {};
            }
            
            // إذا كانت البيانات موجودة في المخزن المؤقت، أعدها مباشرة
            if (window.paperSizeDimensionsCache[paperSizeId]) {
                resolve(window.paperSizeDimensionsCache[paperSizeId]);
                return;
            }
            
            // تحديد API المناسب بناءً على نوع المعرف
            let apiUrl;
            if (paperSizeId.match(/^\d+$/)) {
                // إذا كان رقم، استخدم API مقاسات الورق
                apiUrl = `/pricing/api/paper-size-dimensions/?paper_size_id=${paperSizeId}`;
            } else {
                // إذا كان نص (مثل full_70x100)، استخدم API تحويل مقاس الورق
                apiUrl = `/pricing/api/convert-sheet-type-to-dimensions/?sheet_type=${paperSizeId}`;
            }
            
            // استدعاء API للحصول على أبعاد مقاس الورق
            fetch(apiUrl)
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`فشل الطلب بكود الحالة: ${response.status}`);
                    }
                    return response.json();
                })
                .then(data => {
                    if (data.success && data.width && data.height) {
                        const dimensions = {
                            width: parseFloat(data.width),
                            height: parseFloat(data.height)
                        };
                        
                        // التحقق من صحة الأبعاد
                        if (dimensions.width > 0 && dimensions.height > 0) {
                            window.paperSizeDimensionsCache[paperSizeId] = dimensions;
                            resolve(dimensions);
                        } else {
                            reject(new Error(`أبعاد مقاس الورق غير صحيحة: ${dimensions.width}×${dimensions.height}`));
                        }
                    } else {
                        reject(new Error(`مقاس الورق ${paperSizeId} غير موجود في قاعدة البيانات - يرجى إضافته في إعدادات النظام`));
                    }
                })
                .catch(error => {
                    reject(new Error(`فشل في الاتصال بخادم البيانات: ${error.message}`));
                });
        });
    },
    
    /**
     * حساب المونتاج للمقاس المخصص
     */
    calculateMontageForCustomSize: function(designWidth, designHeight, pressSize) {
        console.log('حساب المونتاج للمقاس المخصص:', designWidth, 'x', designHeight, 'على ماكينة:', pressSize);
        
        // التحقق من أن أبعاد التصميم تدخل في الماكينة
        if (designWidth > pressSize.width || designHeight > pressSize.height) {
            return `التصميم (${designWidth}×${designHeight}) أكبر من مقاس الماكينة (${pressSize.width}×${pressSize.height})`;
        }
        
        // حساب عدد القطع في الاتجاه الأفقي والعمودي
        const piecesHorizontal = Math.floor(pressSize.width / designWidth);
        const piecesVertical = Math.floor(pressSize.height / designHeight);
        const totalPieces = piecesHorizontal * piecesVertical;
        
        if (totalPieces === 0) {
            return `لا يمكن طباعة التصميم بهذا المقاس على الماكينة المحددة`;
        }
        
        // حساب المساحة المستغلة
        const usedWidth = piecesHorizontal * designWidth;
        const usedHeight = piecesVertical * designHeight;
        const wasteWidth = pressSize.width - usedWidth;
        const wasteHeight = pressSize.height - usedHeight;
        
        // تحديد نوع الماكينة بناءً على مساحتها (مثل باقي المقاسات)
        const pressType = this.determinePressTypeFromSize(pressSize);
        
        // تنسيق النتيجة بنفس طريقة المقاسات المعيارية
        return `${totalPieces} / ${pressType}`;
    },
    
    /**
     * إعادة تعيين رسائل الخطأ المسجلة (فقط عند تغيير الماكينة)
     */
    resetErrorFlags: function() {
        // إعادة تعيين رسائل الخطأ المرتبطة بمعرفات الماكينات المحددة
        Object.keys(window).forEach(key => {
            if (key.startsWith('pressApiError_') || key.startsWith('pressFetchError_')) {
                delete window[key];
            }
        });
    },

    /**
     * دالة للحصول على مقاس ماكينة الطباعة
     * @param {number} pressId - معرف ماكينة الطباعة
     * @returns {Promise} وعد يحتوي على مقاس الماكينة
     */
    getPressSize: function(pressId) {
        return new Promise((resolve, reject) => {
            // التحقق من وجود معرف الماكينة
            if (!pressId || pressId === '' || pressId === 'undefined' || pressId === 'null') {
                reject(new Error('معرف الماكينة مطلوب - يرجى اختيار ماكينة الطباعة'));
                return;
            }
                        
            // محاولة الحصول على مقاس الماكينة من البيانات المخزنة في القائمة
            // البحث أولاً في قائمة الماكينات الداخلية
            const internalPressSelect = document.getElementById('id_internal_press');
            if (internalPressSelect) {
                const internalOption = internalPressSelect.querySelector(`option[value="${pressId}"]`);
                if (internalOption && internalOption.dataset.width && internalOption.dataset.height) {
                    resolve({
                        width: parseFloat(internalOption.dataset.width),
                        height: parseFloat(internalOption.dataset.height)
                    });
                    return;
                }
            }
            
            // البحث في قائمة press_selector
            const pressSelector = document.getElementById('press_selector');
            if (pressSelector) {
                const selectorOption = pressSelector.querySelector(`option[value="${pressId}"]`);
                if (selectorOption && selectorOption.dataset.width && selectorOption.dataset.height) {
                    resolve({
                        width: parseFloat(selectorOption.dataset.width),
                        height: parseFloat(selectorOption.dataset.height)
                    });
                    return;
                }
            }
            
            // البحث في قائمة الماكينات الرئيسية
            const pressSelect = document.getElementById('id_press');
            if (pressSelect) {
                const selectedOption = pressSelect.querySelector(`option[value="${pressId}"]`);
                if (selectedOption && selectedOption.dataset.width && selectedOption.dataset.height) {
                    resolve({
                        width: parseFloat(selectedOption.dataset.width),
                        height: parseFloat(selectedOption.dataset.height)
                    });
                    return;
                }
            }
            
            // البحث في جميع قوائم الاختيار في الصفحة
            const allSelects = document.querySelectorAll('select');
            
            for (const select of allSelects) {
                if (select.id === 'id_internal_press' || select.id === 'id_press' || select.id === 'press_selector') {
                    continue; // تم البحث فيهم بالفعل
                }
                
                const option = select.querySelector(`option[value="${pressId}"]`);
                if (option && option.dataset.width && option.dataset.height) {
                    resolve({
                        width: parseFloat(option.dataset.width),
                        height: parseFloat(option.dataset.height)
                    });
                    return;
                }
            }
            
            // إذا لم يتم العثور على المقاس في البيانات المخزنة، استدعاء API
            fetch(`/pricing/api/press-size/?press_id=${pressId}`)
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`فشل الطلب بكود الحالة: ${response.status}`);
                    }
                    return response.json();
                })
                .then(data => {
                    if (data.success && data.press_size && data.press_size.width && data.press_size.height) {
                        const pressSize = {
                            width: parseFloat(data.press_size.width),
                            height: parseFloat(data.press_size.height)
                        };
                        
                        // التحقق من صحة الأبعاد
                        if (pressSize.width > 0 && pressSize.height > 0) {
                            resolve(pressSize);
                        } else {
                            reject(new Error(`أبعاد الماكينة غير صحيحة: ${pressSize.width}×${pressSize.height}`));
                        }
                    } else {
                        reject(new Error(`الماكينة ID ${pressId} غير موجودة أو غير مكتملة البيانات - يرجى التحقق من إعدادات المورد`));
                    }
                })
                .catch(error => {
                    reject(new Error(`فشل في الاتصال بخادم البيانات: ${error.message}`));
                });
        });
    },
    
    /**
     * دالة لحساب المونتاج - كم تصميم يدخل في مساحة الطباعة
     * @param {Object} printSize - مقاس الطباعة الفعلي (الأصغر بين الورق والماكينة)
     * @param {Object} designSize - مقاس التصميم
     * @returns {Object} نتيجة حساب المونتاج
     */
    calculateMontage: function(printSize, designSize) {
        // حساب المونتاج = كم تصميم يدخل في مساحة الطباعة الفعلية
        console.log('حساب المونتاج - مقاس الطباعة:', printSize.width, 'x', printSize.height);
        console.log('حساب المونتاج - مقاس التصميم:', designSize.width, 'x', designSize.height);
        
        // الحصول على أبعاد الطباعة والتصميم
        const printWidth = printSize.width;
        const printHeight = printSize.height;
        const designWidth = designSize.width;
        const designHeight = designSize.height;
        
        // المعادلة الصحيحة حسب طلبك:
        
        // الحالة العادية (بدون تدوير)
        const عدد_بالعرض = Math.floor(printWidth / designWidth);
        const عدد_بالطول = Math.floor(printHeight / designHeight);
        const عدد_عادي = عدد_بالعرض * عدد_بالطول;
        
        // الحالة المدورة (مع تدوير التصميم 90 درجة)
        const عدد_مدور_بالعرض = Math.floor(printWidth / designHeight);
        const عدد_مدور_بالطول = Math.floor(printHeight / designWidth);
        const عدد_مدور = عدد_مدور_بالعرض * عدد_مدور_بالطول;
        
        // العدد النهائي = الأكبر(عدد_عادي, عدد_مدور)
        const العدد_النهائي = Math.max(عدد_عادي, عدد_مدور);
        
        console.log(`الحالة العادية: ${عدد_بالعرض} × ${عدد_بالطول} = ${عدد_عادي}`);
        console.log(`الحالة المدورة: ${عدد_مدور_بالعرض} × ${عدد_مدور_بالطول} = ${عدد_مدور}`);
        console.log(`العدد النهائي: ${العدد_النهائي}`);
        
        // تحديد نوع الورق بناءً على مقاس الطباعة الفعلي
        const actualSheetType = this.determinePaperTypeFromSize({ width: printWidth, height: printHeight });
        
        // تحديد الرسالة والحالة المستخدمة
        let message, sheetType;
        if (عدد_عادي >= عدد_مدور) {
            message = `${عدد_بالعرض} × ${عدد_بالطول} = ${العدد_النهائي} / ${actualSheetType}`;
            sheetType = actualSheetType;
        } else {
            message = `${عدد_مدور_بالعرض} × ${عدد_مدور_بالطول} = ${العدد_النهائي} / ${actualSheetType} (مع تدوير التصميم)`;
            sheetType = actualSheetType;
        }
        
        return {
            count: العدد_النهائي,
            message: message,
            sheetType: sheetType
        };
    },
    
    /**
     * دالة لتحديث معلومات مونتاج المحتوى الداخلي
     * @param {HTMLInputElement} montageInfoField - حقل معلومات المونتاج
     */
    updateInternalMontageInfo: function(montageInfoField) {
        const internalPressSelect = document.getElementById('id_internal_press');
        const internalDesignWidthInput = document.getElementById('id_internal_design_width');
        const internalDesignHeightInput = document.getElementById('id_internal_design_height');
        
        if (!internalPressSelect || !internalDesignWidthInput || !internalDesignHeightInput) {
            montageInfoField.value = 'يرجى إدخال أبعاد التصميم الداخلي واختيار ماكينة الطباعة';
            return;
        }
        
        const pressId = internalPressSelect.value;
        if (!pressId) {
            montageInfoField.value = 'يجب اختيار ماكينة الطباعة للمحتوى الداخلي أولاً';
            return;
        }
        
        const designWidth = parseFloat(internalDesignWidthInput.value);
        const designHeight = parseFloat(internalDesignHeightInput.value);
        
        if (!designWidth || !designHeight) {
            montageInfoField.value = 'يرجى إدخال أبعاد التصميم الداخلي';
            return;
        }
        
        // الحصول على مقاس ماكينة الطباعة
        this.getPressSize(pressId)
            .then(pressSize => {
                if (!pressSize || !pressSize.width || !pressSize.height) {
                    montageInfoField.value = 'لا يمكن الحصول على مقاس ماكينة الطباعة';
                    return;
                }
                
                // حساب المونتاج
                const designSize = { width: designWidth, height: designHeight };
                const montageResult = this.calculateMontage(pressSize, designSize);
                
                // الحصول على نوع الماكينة المكتوب بين القوسين
                let pressSheetType = montageResult.sheetType; // القيمة الافتراضية
                
                // محاولة استخراج نوع الماكينة من اسم الماكينة المحددة
                if (internalPressSelect && internalPressSelect.selectedIndex >= 0) {
                    const selectedOption = internalPressSelect.options[internalPressSelect.selectedIndex];
                    if (selectedOption) {
                        const pressName = selectedOption.textContent || '';
                        
                        // محاولة استخراج النص بين قوسين
                        const match = pressName.match(/\(([^)]+)\)/);
                        if (match && match[1]) {
                            pressSheetType = match[1].trim();
                        }
                    }
                }
                
                // تنسيق رسالة المونتاج بالشكل الصحيح باستخدام نوع الماكينة المستخرج
                const formattedMessage = `${montageResult.count} / ${pressSheetType}`;
                
                // تحديث حقل معلومات المونتاج
                montageInfoField.value = formattedMessage;
                
                // تحديث حقل عدد المونتاج
                const internalMontageCountField = document.getElementById('id_internal_montage_count');
                if (internalMontageCountField) {
                    internalMontageCountField.value = montageResult.count;
                }
                
                // تحديث كمية الورق المطلوبة للمحتوى الداخلي
                if (typeof PricingSystem.Paper !== 'undefined' && typeof PricingSystem.Paper.calculateInternalPaperSheets === 'function') {
                    PricingSystem.Paper.calculateInternalPaperSheets();
                }
            })
            .catch(error => {
                console.error('خطأ في الحصول على مقاس ماكينة الطباعة للمحتوى الداخلي:', error);
                montageInfoField.value = 'حدث خطأ أثناء حساب المونتاج';
            });
    },
    
    /**
     * تحديد نوع الماكينة بناءً على مقاسها (ديناميكي)
     */
    determinePressTypeFromSize: function(pressSize) {
        const area = pressSize.width * pressSize.height;
        
        // تصنيف ديناميكي بناءً على المساحة
        if (area <= 1750) {  // 35×50 = 1750
            return 'الربع';
        } else if (area <= 3500) {  // 50×70 = 3500
            return 'النصف';
        } else if (area <= 7000) {  // 70×100 = 7000
            return 'الفرخ';
        } else {
            return `مقاس كبير (${pressSize.width}×${pressSize.height})`;
        }
    },
    
    /**
     * البحث عن حقل مقاس الورق في النموذج
     */
    findPaperSizeField: function() {
        // البحث عن حقول مقاس الورق المختلفة
        const possibleFields = [
            'id_product_size',
            'id_paper_sheet_type', 
            'paper_size',
            'paper_sheet_type'
        ];
        
        for (const fieldId of possibleFields) {
            const field = document.getElementById(fieldId);
            if (field && field.value) {
                console.log('تم العثور على حقل مقاس الورق:', fieldId, 'القيمة:', field.value);
                return field;
            }
        }
        
        console.log('لم يتم العثور على حقل مقاس الورق');
        return null;
    },
    
    /**
     * تحديد نوع الورق بناءً على مقاسه (ديناميكي)
     */
    determinePaperTypeFromSize: function(paperSize) {
        const area = paperSize.width * paperSize.height;
        
        // تصنيف ديناميكي بناءً على المساحة
        if (area <= 625) {  // A4: 21×29.7 = 623
            return 'A4';
        } else if (area <= 1250) {  // A3: 29.7×42 = 1247
            return 'A3';
        } else if (area <= 1750) {  // ربع فرخ: 35×50 = 1750
            return 'ربع فرخ';
        } else if (area <= 3500) {  // نصف فرخ: 50×70 = 3500
            return 'نصف فرخ';
        } else if (area <= 7000) {  // فرخ كامل: 70×100 = 7000
            return 'فرخ كامل';
        } else {
            return `مقاس كبير (${paperSize.width}×${paperSize.height})`;
        }
    },
    
    /**
     * تحويل مقاس الماكينة إلى نوع مدعوم في النظام الجديد (ديناميكي)
     */
    mapPressSizeToType: function(pressSize) {
        const area = pressSize.width * pressSize.height;
        
        // تصنيف ديناميكي بناءً على المساحة
        if (area <= 1750) {  // 35×50 = 1750
            return 'quarter';
        } else if (area <= 3500) {  // 50×70 = 3500
            return 'half';
        } else {
            return 'full';
        }
    },
    
    /**
     * استخراج نوع الماكينة من النص بين القوسين
     */
    extractPressSheetType: function(pressId) {
        // البحث في جميع قوائم الاختيار
        const selectors = ['id_press', 'id_internal_press', 'press_selector', 'internal_press_selector'];
        
        for (const selectorId of selectors) {
            const select = document.getElementById(selectorId);
            if (select) {
                const option = select.querySelector(`option[value="${pressId}"]`);
                if (option) {
                    const pressName = option.textContent || '';
                    // محاولة استخراج النص بين قوسين
                    const match = pressName.match(/\(([^)]+)\)/);
                    if (match && match[1]) {
                        return match[1].trim();
                    }
                }
            }
        }
        
        // البحث في جميع قوائم الاختيار في الصفحة
        const allSelects = document.querySelectorAll('select');
        for (const select of allSelects) {
            const option = select.querySelector(`option[value="${pressId}"]`);
            if (option) {
                const pressName = option.textContent || '';
                const match = pressName.match(/\(([^)]+)\)/);
                if (match && match[1]) {
                    return match[1].trim();
                }
            }
        }
        
        return null;
    }
};

// تهيئة النظام عند تحميل الصفحة
document.addEventListener('DOMContentLoaded', function() {
    if (PricingSystem && PricingSystem.Montage) {
        PricingSystem.Montage.setupMontageHandlers();
    }
}); 