/**
 * montage-handlers.js - دالات معالجة المونتاج
 */

// تعريف كائن عام للمشروع إذا لم يكن موجودًا
window.PricingSystem = window.PricingSystem || {};

// تعريف وحدة معالجة المونتاج
PricingSystem.Montage = {
    /**
     * إعداد معالجات المونتاج
     */
    setupMontageHandlers: function() {
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
        const coverFields = ['id_paper_size', 'id_press', 'id_custom_size_width', 'id_custom_size_height'];
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
                'id_paper_size', 'id_press', 'id_custom_size_width', 'id_custom_size_height',
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
            if (PricingSystem.Paper && typeof PricingSystem.Paper.calculatePaperSheetsDirectly === 'function') {
                PricingSystem.Paper.calculatePaperSheetsDirectly();
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
        // إعداد معالجات أحداث التصميم لحساب المونتاج
        const paperSizeSelect = document.getElementById('id_paper_size');
        const customSizeWidthInput = document.getElementById('id_custom_size_width');
        const customSizeHeightInput = document.getElementById('id_custom_size_height');
        const pressSelect = document.getElementById('id_press');
        const montageInfoField = document.getElementById('id_montage_info');
        
        if (paperSizeSelect && pressSelect && montageInfoField) {
            // عند تغيير مقاس الورق أو ماكينة الطباعة، قم بتحديث معلومات المونتاج
            const updateMontageOnChange = () => {
                this.updateMontageInfo(montageInfoField);
            };
            
            paperSizeSelect.addEventListener('change', updateMontageOnChange);
            pressSelect.addEventListener('change', updateMontageOnChange);
            
            // إذا كان هناك مقاس مخصص، أضف مستمعات الأحداث له أيضًا
            if (customSizeWidthInput && customSizeHeightInput) {
                customSizeWidthInput.addEventListener('change', updateMontageOnChange);
                customSizeHeightInput.addEventListener('change', updateMontageOnChange);
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
        if (!montageInfoField) {
            console.warn('حقل معلومات المونتاج غير موجود');
            return;
        }
        
        if (isInternal) {
            this.updateInternalMontageInfo(montageInfoField);
            return;
        }
        
        const pressSelect = document.getElementById('id_press');
        const paperSizeSelect = document.getElementById('id_paper_size');
        const customSizeWidthInput = document.getElementById('id_custom_size_width');
        const customSizeHeightInput = document.getElementById('id_custom_size_height');
        
        if (!pressSelect) {
            console.warn('حقل ماكينة الطباعة غير موجود');
            montageInfoField.value = 'يرجى اختيار ماكينة الطباعة';
            return;
        }
        
        if (!paperSizeSelect) {
            console.warn('حقل مقاس الورق غير موجود');
            montageInfoField.value = 'يرجى اختيار مقاس الورق';
            return;
        }
        
        const pressId = pressSelect.value;
        if (!pressId) {
            montageInfoField.value = 'يجب اختيار ماكينة الطباعة أولاً';
            return;
        }
        
        // الحصول على مقاس التصميم من مقاس الورق أو المقاس المخصص
        let designWidth, designHeight;
        
        // التحقق مما إذا كان المقاس المخصص محدد
        if (paperSizeSelect.value === 'custom' && customSizeWidthInput && customSizeHeightInput) {
            designWidth = parseFloat(customSizeWidthInput.value);
            designHeight = parseFloat(customSizeHeightInput.value);
        } else {
            // الحصول على أبعاد مقاس الورق المحدد من API
            this.getPaperSizeDimensions(paperSizeSelect.value)
                .then(dimensions => {
                    if (!dimensions || !dimensions.width || !dimensions.height) {
                        montageInfoField.value = 'لا يمكن الحصول على أبعاد مقاس الورق';
                        return;
                    }
                    
                    designWidth = dimensions.width;
                    designHeight = dimensions.height;
                    
                    // بعد الحصول على أبعاد الورق، نستمر في حساب المونتاج
                    this.calculateMontageWithPressAndDesign(pressId, designWidth, designHeight, montageInfoField);
                })
                .catch(error => {
                    console.error('خطأ في الحصول على أبعاد مقاس الورق:', error);
                    montageInfoField.value = 'حدث خطأ أثناء حساب المونتاج';
                });
            return;
        }
        
        if (!designWidth || !designHeight) {
            montageInfoField.value = 'يرجى إدخال أبعاد التصميم';
            return;
        }
        
        // استمرار حساب المونتاج بعد الحصول على أبعاد التصميم
        this.calculateMontageWithPressAndDesign(pressId, designWidth, designHeight, montageInfoField);
    },
    
    /**
     * دالة مساعدة لحساب المونتاج بعد الحصول على أبعاد الماكينة والتصميم
     */
    calculateMontageWithPressAndDesign: function(pressId, designWidth, designHeight, montageInfoField) {
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
                    
                    // تحديث كمية الورق المطلوبة
                    if (typeof PricingSystem.Paper !== 'undefined' && typeof PricingSystem.Paper.calculatePaperSheetsDirectly === 'function') {
                        PricingSystem.Paper.calculatePaperSheetsDirectly();
                    }
                } else {
                    console.warn('حقل عدد المونتاج غير موجود');
                }
            })
            .catch(error => {
                console.error('خطأ في الحصول على مقاس ماكينة الطباعة:', error);
                montageInfoField.value = 'حدث خطأ أثناء حساب المونتاج';
            });
    },
    
    /**
     * دالة للحصول على أبعاد مقاس الورق
     * @param {number} paperSizeId - معرف مقاس الورق
     * @returns {Promise} وعد يحتوي على أبعاد الورق
     */
    getPaperSizeDimensions: function(paperSizeId) {
        return new Promise((resolve, reject) => {
            // القيم الافتراضية في حالة عدم نجاح الاستدعاء
            const defaultDimensions = { width: 21, height: 29.7 }; // A4 افتراضي
            
            // إذا لم يتم تمرير معرف مقاس الورق، أرجع القيم الافتراضية
            if (!paperSizeId) {
                resolve(defaultDimensions);
                return;
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
            
            // استدعاء API للحصول على أبعاد مقاس الورق
            fetch(`/pricing/api/paper-size-dimensions/?paper_size_id=${paperSizeId}`)
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`فشل الطلب بكود الحالة: ${response.status}`);
                    }
                    return response.json();
                })
                .then(data => {
                    if (data.success) {
                        const dimensions = {
                            width: parseFloat(data.width),
                            height: parseFloat(data.height)
                        };
                        window.paperSizeDimensionsCache[paperSizeId] = dimensions;
                        resolve(dimensions);
                    } else {
                        console.error('خطأ من الخادم:', data.error || 'خطأ غير معروف');
                        resolve(defaultDimensions);
                    }
                })
                .catch(error => {
                    console.error('خطأ في الحصول على أبعاد مقاس الورق:', error);
                    resolve(defaultDimensions);
                });
        });
    },
    
    /**
     * دالة للحصول على مقاس ماكينة الطباعة
     * @param {number} pressId - معرف ماكينة الطباعة
     * @returns {Promise} وعد يحتوي على مقاس الماكينة
     */
    getPressSize: function(pressId) {
        return new Promise((resolve, reject) => {
            // القيم الافتراضية في حالة عدم نجاح الاستدعاء
            const defaultPressSize = { width: 70, height: 100 }; // مقاس افتراضي للماكينة
            
            if (!pressId) {
                console.warn('لم يتم تمرير معرف ماكينة الطباعة');
                reject(new Error('معرف ماكينة الطباعة غير محدد'));
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
                    if (data.success) {
                        resolve({
                            width: parseFloat(data.width),
                            height: parseFloat(data.height)
                        });
                    } else {
                        console.warn('خطأ في الحصول على مقاس الماكينة من API:', data.error || 'خطأ غير معروف');
                        // استخدام القيم الافتراضية في حالة الخطأ
                        resolve(defaultPressSize);
                    }
                })
                .catch(error => {
                    console.error('خطأ في استدعاء API لمقاس الماكينة:', error);
                    // استخدام القيم الافتراضية في حالة الخطأ
                    resolve(defaultPressSize);
                });
        });
    },
    
    /**
     * دالة لحساب المونتاج
     * @param {Object} pressSize - مقاس ماكينة الطباعة
     * @param {Object} designSize - مقاس التصميم
     * @returns {Object} نتيجة حساب المونتاج
     */
    calculateMontage: function(pressSize, designSize) {
        // الحصول على مقاس ماكينة الطباعة ومقاس التصميم
        const pressWidth = pressSize.width;
        const pressHeight = pressSize.height;
        const designWidth = designSize.width;
        const designHeight = designSize.height;
        
        // حساب عدد التصاميم التي يمكن وضعها في العرض والطول
        const widthCount = Math.floor(pressWidth / designWidth);
        const heightCount = Math.floor(pressHeight / designHeight);
        
        // حساب عدد التصاميم التي يمكن وضعها في العرض والطول بعد تدوير التصميم
        const rotatedWidthCount = Math.floor(pressWidth / designHeight);
        const rotatedHeightCount = Math.floor(pressHeight / designWidth);
        
        // حساب إجمالي عدد التصاميم في كل حالة
        const normalCount = widthCount * heightCount;
        const rotatedCount = rotatedWidthCount * rotatedHeightCount;
        
        // اختيار الحالة التي تعطي أكبر عدد من التصاميم
        let montageCount, message, sheetType;
        if (normalCount >= rotatedCount) {
            montageCount = normalCount;
            message = `${widthCount} × ${heightCount} = ${montageCount} / فرخ كامل`;
            sheetType = 'فرخ كامل';
        } else {
            montageCount = rotatedCount;
            message = `${rotatedWidthCount} × ${rotatedHeightCount} = ${montageCount} / فرخ كامل (مع تدوير التصميم)`;
            sheetType = 'فرخ كامل';
        }
        
        // التحقق مما إذا كان يمكن استخدام نصف فرخ
        if (montageCount <= 1) {
            // حساب المونتاج لنصف فرخ
            const halfPressWidth = pressWidth / 2;
            const halfWidthCount = Math.floor(halfPressWidth / designWidth);
            const halfHeightCount = heightCount;
            const halfCount = halfWidthCount * halfHeightCount;
            
            const halfRotatedWidthCount = Math.floor(halfPressWidth / designHeight);
            const halfRotatedHeightCount = rotatedHeightCount;
            const halfRotatedCount = halfRotatedWidthCount * halfRotatedHeightCount;
            
            if (halfCount >= montageCount || halfRotatedCount >= montageCount) {
                if (halfCount >= halfRotatedCount) {
                    montageCount = halfCount;
                    message = `${halfWidthCount} × ${halfHeightCount} = ${montageCount} / نصف فرخ`;
                    sheetType = 'نصف فرخ';
                } else {
                    montageCount = halfRotatedCount;
                    message = `${halfRotatedWidthCount} × ${halfRotatedHeightCount} = ${montageCount} / نصف فرخ (مع تدوير التصميم)`;
                    sheetType = 'نصف فرخ';
                }
            }
        }
        
        // التحقق مما إذا كان يمكن استخدام ربع فرخ
        if (montageCount <= 1) {
            // حساب المونتاج لربع فرخ
            const quarterPressWidth = pressWidth / 2;
            const quarterPressHeight = pressHeight / 2;
            const quarterWidthCount = Math.floor(quarterPressWidth / designWidth);
            const quarterHeightCount = Math.floor(quarterPressHeight / designHeight);
            const quarterCount = quarterWidthCount * quarterHeightCount;
            
            const quarterRotatedWidthCount = Math.floor(quarterPressWidth / designHeight);
            const quarterRotatedHeightCount = Math.floor(quarterPressHeight / designWidth);
            const quarterRotatedCount = quarterRotatedWidthCount * quarterRotatedHeightCount;
            
            if (quarterCount >= montageCount || quarterRotatedCount >= montageCount) {
                if (quarterCount >= quarterRotatedCount) {
                    montageCount = quarterCount;
                    message = `${quarterWidthCount} × ${quarterHeightCount} = ${montageCount} / ربع فرخ`;
                    sheetType = 'ربع فرخ';
                } else {
                    montageCount = quarterRotatedCount;
                    message = `${quarterRotatedWidthCount} × ${quarterRotatedHeightCount} = ${montageCount} / ربع فرخ (مع تدوير التصميم)`;
                    sheetType = 'ربع فرخ';
                }
            }
        }
        
        return {
            count: montageCount,
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
    }
}; 