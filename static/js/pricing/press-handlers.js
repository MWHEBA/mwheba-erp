/**
 * press-handlers.js - دوال معالجة ماكينات الطباعة
 */

// تعريف كائن عام للمشروع إذا لم يكن موجودًا
window.PricingSystem = window.PricingSystem || {};
// تعريف وحدة معالجة ماكينات الطباعة
PricingSystem.Press = {
    /**
     * تهيئة معالجات أحداث ماكينات الطباعة
    setupEventHandlers: function() {
        // تسجيل معالجات الأحداث مع ناقل الأحداث إذا كان متاحًا
        if (PricingSystem.EventBus) {
            this.registerEventHandlers();
        }
        
        // استخدام الطريقة التقليدية أيضاً للتأكد
        this.setupTraditionalEventHandlers();
        // الاستماع لتغييرات ماكينة الطباعة
        PricingSystem.EventBus.on('field:press_selector:changed', (data) => {
            this.updatePressValue(data.value);
            
            // تأخير قصير لضمان تحديث قيمة id_press قبل التحديثات التالية
            setTimeout(() => {
                // تحديث معلومات المونتاج
                if (PricingSystem.Montage && typeof PricingSystem.Montage.updateMontageInfo === 'function') {
                    const montageInfoField = document.getElementById('id_montage_info');
                    if (montageInfoField) {
                        PricingSystem.Montage.updateMontageInfo(montageInfoField);
                    }
                }
                
                // تحديث عدد أفرخ الورق
                if (PricingSystem.Paper && typeof PricingSystem.Paper.calculatePaperSheetsDirectly === 'function') {
                    PricingSystem.Paper.calculatePaperSheetsDirectly();
                }
                
                // تحديث تكلفة التغطية
                if (PricingSystem.Finishing && typeof PricingSystem.Finishing.updateCoatingTotalBasedOnSheets === 'function') {
                    PricingSystem.Finishing.updateCoatingTotalBasedOnSheets();
                }
            }, 200);
        });
        
        // الاستماع لتغييرات سعر الطباعة وعدد التراجات
        const pressCostFields = ['id_press_price_per_1000', 'id_press_runs', 'id_press_transportation'];
        pressCostFields.forEach(fieldId => {
            PricingSystem.EventBus.on(`field:${fieldId}:changed`, (data) => {
                if (PricingSystem.Print && typeof PricingSystem.Print.calculatePressCost === 'function') {
                    PricingSystem.Print.calculatePressCost();
                } else {
                    this.calculatePressTotalCost();
                }
            });
        });
        
        // الاستماع لتغييرات مورد الطباعة للمحتوى الداخلي
        PricingSystem.EventBus.on('field:id_internal_supplier:changed', (data) => {
            if (data.value) {
                this.loadInternalPressesDirectly(data.value);
            }
        });
        
        // الاستماع لتغييرات ماكينة الطباعة للمحتوى الداخلي
        PricingSystem.EventBus.on('field:internal_press_selector:changed', (data) => {
            this.updateInternalPressValue(data.value);
        });
        
        // الاستماع لتغييرات سعر الطباعة وعدد التراجات للمحتوى الداخلي
        const internalPressCostFields = ['id_internal_press_price_per_1000', 'id_internal_press_runs', 'id_internal_press_transportation'];
        internalPressCostFields.forEach(fieldId => {
            PricingSystem.EventBus.on(`field:${fieldId}:changed`, (data) => {
                if (PricingSystem.Print && typeof PricingSystem.Print.calculateInternalPressCost === 'function') {
                    PricingSystem.Print.calculateInternalPressCost();
                } else {
                    this.calculateInternalPressTotalCost();
                }
            });
        });
        
        // الاستماع لتغييرات الكمية لتحديث عدد التراجات
        PricingSystem.EventBus.on('field:id_quantity:changed', (data) => {
            if (PricingSystem.Print && typeof PricingSystem.Print.calculatePressRuns === 'function') {
                PricingSystem.Print.calculatePressRuns();
            }
        });
        
        // الاستماع لتحديثات الحقول المتعلقة بالطباعة
        PricingSystem.EventBus.on('fields:updated', (data) => {
            const pressRelatedFields = [
                'id_supplier', 'id_press', 'press_selector', 
                'id_press_price_per_1000', 'id_press_runs', 'id_press_transportation'
            ];
            
            const shouldUpdatePress = data.changedFields.some(field => 
                pressRelatedFields.includes(field)
            );
            
            if (shouldUpdatePress && PricingSystem.Print && 
                typeof PricingSystem.Print.calculatePressCost === 'function') {
                PricingSystem.Print.calculatePressCost();
            }
            
            const internalPressRelatedFields = [
                'id_internal_supplier', 'id_internal_press', 'internal_press_selector',
                'id_internal_press_price_per_1000', 'id_internal_press_runs', 'id_internal_press_transportation'
            ];
            
            const shouldUpdateInternalPress = data.changedFields.some(field => 
                internalPressRelatedFields.includes(field)
            );
            
            if (shouldUpdateInternalPress && PricingSystem.Print && 
                typeof PricingSystem.Print.calculateInternalPressCost === 'function') {
                PricingSystem.Print.calculateInternalPressCost();
            }
        });
    },
    
    /**
     * إعداد معالجات الأحداث التقليدية (بدون ناقل الأحداث)
     */
    setupTraditionalEventHandlers: function() {
        // إعداد معالجات أحداث لمورد الطباعة وماكينة الطباعة
        const supplierSelect = document.getElementById('id_supplier');
        const pressSelector = document.getElementById('press_selector');
        
        if (supplierSelect) {
            supplierSelect.addEventListener('change', () => {
                if (supplierSelect.value) {
                    this.loadPressesDirectly(supplierSelect.value);
                }
            });
        }
        
        if (pressSelector) {
            pressSelector.addEventListener('change', () => {
                this.updatePressValue(pressSelector.value);
            });
        }
        
        // إعداد معالجات أحداث لحقول سعر الطباعة وعدد التراجات
        const pressPriceInput = document.getElementById('id_press_price_per_1000');
        const pressRunsInput = document.getElementById('id_press_runs');
        const pressTransportationInput = document.getElementById('id_press_transportation');
        
        if (pressPriceInput) {
            pressPriceInput.addEventListener('change', () => {
                if (PricingSystem.Print && typeof PricingSystem.Print.calculatePressCost === 'function') {
                    PricingSystem.Print.calculatePressCost();
                } else {
                    this.calculatePressTotalCost();
                }
            });
            
            pressPriceInput.addEventListener('input', () => {
                if (PricingSystem.Print && typeof PricingSystem.Print.calculatePressCost === 'function') {
                    PricingSystem.Print.calculatePressCost();
                } else {
                    this.calculatePressTotalCost();
                }
            });
        }
        
        if (pressRunsInput) {
            pressRunsInput.addEventListener('change', () => {
                if (PricingSystem.Print && typeof PricingSystem.Print.calculatePressCost === 'function') {
                    PricingSystem.Print.calculatePressCost();
                } else {
                    this.calculatePressTotalCost();
                }
            });
            
            pressRunsInput.addEventListener('input', () => {
                if (PricingSystem.Print && typeof PricingSystem.Print.calculatePressCost === 'function') {
                    PricingSystem.Print.calculatePressCost();
                } else {
                    this.calculatePressTotalCost();
                }
            });
        }
        
        if (pressTransportationInput) {
            pressTransportationInput.addEventListener('change', () => {
                if (PricingSystem.Print && typeof PricingSystem.Print.calculatePressCost === 'function') {
                    PricingSystem.Print.calculatePressCost();
                } else {
                    this.calculatePressTotalCost();
                }
            });
            
            pressTransportationInput.addEventListener('input', () => {
                if (PricingSystem.Print && typeof PricingSystem.Print.calculatePressCost === 'function') {
                    PricingSystem.Print.calculatePressCost();
                } else {
                    this.calculatePressTotalCost();
                }
            });
        }
        
        // إعداد معالجات أحداث لمورد الطباعة وماكينة الطباعة للمحتوى الداخلي
        const internalSupplierSelect = document.getElementById('id_internal_supplier');
        const internalPressSelector = document.getElementById('internal_press_selector');
        
        if (internalSupplierSelect) {
            internalSupplierSelect.addEventListener('change', () => {
                if (internalSupplierSelect.value) {
                    this.loadInternalPressesDirectly(internalSupplierSelect.value);
                }
            });
        }
        
        if (internalPressSelector) {
            internalPressSelector.addEventListener('change', () => {
                this.updateInternalPressValue(internalPressSelector.value);
            });
        }
    },
    
    /**
     * تحديث قيمة الماكينة في الحقل المخفي
     * @param {string|object} value - قيمة الماكينة أو عنصر DOM
     */
    updatePressValue: function(value) {
        var hiddenInput = document.getElementById('id_press');
        if (hiddenInput) {
            hiddenInput.value = value;
            
            if (typeof this.updatePressInfo === 'function') {
                this.updatePressInfo(value);
            }
        }
    },
    
    /**
     * تحديث معلومات الماكينة عند اختيارها
     * @param {string|object} pressValue - قيمة الماكينة أو عنصر DOM
     */
    updatePressInfo: function(pressValue) {
        // إذا كان المدخل هو عنصر DOM، استخراج القيمة منه
        if (typeof pressValue === 'object' && pressValue !== null) {
            if (pressValue.value !== undefined) {
                pressValue = pressValue.value;
            } else {
                return;
            }
        }
        
        var pressPriceInput = document.getElementById('id_press_price_per_1000');
        var montageInfoField = document.getElementById('id_montage_info');
        var pressSelector = document.getElementById('press_selector');
        
        if (pressValue) {
            // تحديث قيمة الحقل المخفي
            var hiddenInput = document.getElementById('id_press');
            if (hiddenInput) {
                hiddenInput.value = pressValue;
            }
            
            // التحقق من وجود سعر في البيانات المخزنة في القائمة
            var price = null;
            if (pressSelector && pressSelector.options) {
                for (var i = 0; i < pressSelector.options.length; i++) {
                    if (pressSelector.options[i].value === pressValue) {
                        price = pressSelector.options[i].getAttribute('data-price');
                        break;
                    }
                }
            }
            
            if (price && pressPriceInput) {
                pressPriceInput.value = price;
                
                // تحديث إجمالي تكلفة الطباعة - استخدام دالة PricingSystem.Print.calculatePressCost بدلاً من الدالة المحلية
                if (window.PricingSystem && PricingSystem.Print && typeof PricingSystem.Print.calculatePressCost === 'function') {
                    setTimeout(function() {
                        try {
                            PricingSystem.Print.calculatePressCost();
                        } catch (e) {
                            console.error('خطأ في استدعاء PricingSystem.Print.calculatePressCost:', e);
                        }
                    }, 100);
                } else {
                    // إذا لم تكن دالة calculatePressCost متاحة، نستخدم الدالة المحلية
                    console.warn('دالة PricingSystem.Print.calculatePressCost غير متاحة، استخدام PricingSystem.Press.calculatePressTotalCost بدلاً منها');
                    PricingSystem.Press.calculatePressTotalCost();
                }
            } else {
                // إذا لم يتم العثور على السعر في البيانات المخزنة، استدعاء API
                PricingSystem.Press.fetchPressPriceDirectly(pressValue, pressPriceInput);
            }
            
            // تحديث معلومات المونتاج
            if (window.PricingSystem && PricingSystem.Montage && typeof PricingSystem.Montage.updateMontageInfo === 'function' && montageInfoField) {
                try {
                    PricingSystem.Montage.updateMontageInfo(montageInfoField);
                } catch (e) {
                    console.error('خطأ في استدعاء PricingSystem.Montage.updateMontageInfo:', e);
                }
            }
            
            // حساب عدد التراجات تلقائيًا
            if (window.PricingSystem && PricingSystem.Print && typeof PricingSystem.Print.calculatePressRuns === 'function') {
                try {
                    PricingSystem.Print.calculatePressRuns();
                } catch (e) {
                    console.error('خطأ في استدعاء PricingSystem.Print.calculatePressRuns:', e);
                }
            }
        } else {
            // إعادة تعيين القيم عند إلغاء اختيار ماكينة
            if (pressPriceInput) {
                pressPriceInput.value = '';
            }
            if (montageInfoField) {
                montageInfoField.value = 'يجب اختيار ماكينة الطباعة أولاً';
            }
            
            // إعادة تعيين إجمالي التكلفة
            var pressTotalCostInput = document.getElementById('id_press_total_cost');
            if (pressTotalCostInput) {
                pressTotalCostInput.value = '';
            }
        }
    },
    
    /**
     * تحميل ماكينات الطباعة مباشرة
     * @param {string} supplierId - معرف المورد
     */
    loadPressesDirectly: function(supplierId) {
        if (!supplierId) {
            return;
        }
        
        // الحصول على عناصر DOM
        var pressSelect = document.getElementById('press_selector');
        var hiddenInput = document.getElementById('id_press');
        var pressPriceInput = document.getElementById('id_press_price_per_1000');
        
        // التأكد من وجود عنصر القائمة المنسدلة
        if (!pressSelect) {
            return;
        }
        
        // تعطيل القائمة أثناء التحميل
        pressSelect.disabled = true;
        
        // مسح الخيارات الحالية
        pressSelect.innerHTML = '<option value="">-- جاري تحميل الماكينات... --</option>';
        
        // مسح سعر الماكينة والقيمة المخفية
        if (pressPriceInput) {
            pressPriceInput.value = '';
        }
        if (hiddenInput) {
            hiddenInput.value = '';
        }
        
        // الحصول على نوع الطلب
        var orderTypeSelect = document.getElementById('id_order_type');
        var orderType = orderTypeSelect ? orderTypeSelect.value : '';
        
        // بناء URL مع المعاملات
        var apiUrl = "/pricing/api/presses/?supplier_id=" + supplierId;
        if (orderType) {
            apiUrl += "&order_type=" + encodeURIComponent(orderType);
        }
        
        // استدعاء API
        fetch(apiUrl)
            .then(function(response) {
                if (!response.ok) {
                    throw new Error("خطأ في استجابة الخادم: " + response.status);
                }
                return response.json();
            })
            .then(function(data) {
                // إعادة تمكين القائمة
                pressSelect.disabled = false;
                
                // إعداد HTML للخيارات
                var html = '<option value="">-- اختر ماكينة الطباعة --</option>';
                var addedCount = 0;
                
                if (data && data.success && Array.isArray(data.presses) && data.presses.length > 0) {
                    // إضافة خيارات الماكينات
                    data.presses.forEach(function(press) {
                        if (press && typeof press === 'object' && press.id) {
                            var name = press.name || "ماكينة " + press.id;
                            var price = '';
                            
                            if (press.price_per_1000 !== undefined) {
                                price = press.price_per_1000;
                            } else if (press.unit_price !== undefined) {
                                price = press.unit_price;
                            }
                            
                            html += '<option value="' + press.id + '" data-price="' + price + '">' + name + '</option>';
                            addedCount++;
                        }
                    });
                    
                    // تحديث القائمة
                    pressSelect.innerHTML = html;
                    
                    // اختيار الماكينة الأولى تلقائيًا إذا كان هناك ماكينة واحدة فقط
                    if (addedCount === 1 && pressSelect.options && pressSelect.options.length > 1) {
                        try {
                            // تعيين القيمة المحددة
                            pressSelect.selectedIndex = 1;
                            var selectedValue = pressSelect.options[1].value;
                            
                            // تحديث الحقل المخفي
                            if (hiddenInput) {
                                hiddenInput.value = selectedValue;
                            }
                            
                            // استدعاء دالة updatePressValue
                            PricingSystem.Press.updatePressValue(selectedValue);
                        } catch (e) {
                            console.error('خطأ أثناء تحديد الماكينة الأولى تلقائيًا:', e);
                        }
                    }
                } else {
                    // إذا لم يتم العثور على ماكينات
                    pressSelect.innerHTML = '<option value="">-- لا توجد ماكينات متاحة --</option>';
                }
            })
            .catch(function(error) {
                console.error('خطأ في تحميل ماكينات الطباعة:', error);
                pressSelect.disabled = false;
                pressSelect.innerHTML = '<option value="">-- خطأ في تحميل الماكينات --</option>';
            });
    },
    
    /**
     * جلب سعر الماكينة مباشرة
     * @param {string} pressId - معرف الماكينة
     * @param {HTMLInputElement} pressPriceInput - عنصر حقل سعر الماكينة
     */
    fetchPressPriceDirectly: function(pressId, pressPriceInput) {
        if (!pressId || !pressPriceInput) {
            return;
        }
        
        var xhr = new XMLHttpRequest();
        xhr.open('GET', "/pricing/api/press-price/?press_id=" + pressId, true);
        
        xhr.onreadystatechange = function() {
            if (xhr.readyState === 4 && xhr.status === 200) {
                try {
                    var data = JSON.parse(xhr.responseText);
                    
                    if (data && data.success) {
                        // تحديث سعر الماكينة
                        var price = null;
                        if (data.price_per_1000 !== undefined) {
                            price = data.price_per_1000;
                        } else if (data.price !== undefined) {
                            price = data.price;
                        } else if (data.unit_price !== undefined) {
                            price = data.unit_price;
                        }
                        
                        if (price !== null && pressPriceInput) {
                            pressPriceInput.value = price;
                            
                            // تحديث إجمالي تكلفة الطباعة - استخدام دالة PricingSystem.Print.calculatePressCost بدلاً من الدالة المحلية
                            if (window.PricingSystem && PricingSystem.Print && typeof PricingSystem.Print.calculatePressCost === 'function') {
                                setTimeout(function() {
                                    try {
                                        PricingSystem.Print.calculatePressCost();
                                    } catch (e) {
                                        console.error('خطأ في استدعاء PricingSystem.Print.calculatePressCost:', e);
                                    }
                                }, 100);
                            } else {
                                // إذا لم تكن دالة calculatePressCost متاحة، نستخدم الدالة المحلية
                                console.warn('دالة PricingSystem.Print.calculatePressCost غير متاحة، استخدام PricingSystem.Press.calculatePressTotalCost بدلاً منها');
                                PricingSystem.Press.calculatePressTotalCost();
                            }
                        }
                    }
                } catch (error) {
                    console.error('خطأ في تحليل استجابة API لسعر الماكينة:', error);
                }
            }
        };
        
        xhr.send();
    },
    
    /**
     * حساب إجمالي تكلفة الطباعة
     * هذه الدالة مخصصة للاستخدام الاحتياطي فقط، ويفضل استخدام PricingSystem.Print.calculatePressCost
     */
    calculatePressTotalCost: function() {
        var quantityInput = document.getElementById('id_quantity');
        var pricePerThousand = document.getElementById('id_press_price_per_1000');
        var pressRuns = document.getElementById('id_press_runs');
        var pressTransportation = document.getElementById('id_press_transportation');
        var pressTotalCost = document.getElementById('id_press_total_cost');
        
        if (quantityInput && pricePerThousand && pressRuns && pressTotalCost) {
            // تأكد من تحويل القيم إلى أرقام بشكل صحيح
            var quantity = 0;
            try {
                quantity = parseInt(quantityInput.value.replace(/[^\d]/g, '')) || 0;
            } catch (e) {
                console.error('خطأ في تحويل قيمة الكمية (احتياطي):', e);
                quantity = 0;
            }
            
            var price = parseFloat(pricePerThousand.value) || 0;
            var runs = parseFloat(pressRuns.value) || 0;
            var transportation = parseFloat(pressTransportation.value) || 0;
            
            // حساب تكلفة الطباعة وفقاً للصيغة الصحيحة من الملف الاحتياطي
            // السعر × الكمية ÷ 1000 × عدد مرات التراج + تكلفة الانتقالات
            var total = (price * quantity / 1000 * runs) + transportation;
            
            pressTotalCost.value = total.toFixed(2);
        }
    },
    
    /**
     * إعداد معالجات الأحداث لماكينات الطباعة
     */
    setupPressEventHandlers: function() {
        try {
            
            // إضافة معالج للنموذج للتأكد من أن id_press يحصل على القيمة الصحيحة
            var pricingForm = document.getElementById('pricing-form');
            if (pricingForm) {
                pricingForm.addEventListener('submit', function(event) {
                    var pressSelector = document.getElementById('press_selector');
                    var hiddenInput = document.getElementById('id_press');
                    
                    if (pressSelector && pressSelector.value && hiddenInput) {
                        // تعيين قيمة الحقل المخفي
                        hiddenInput.value = pressSelector.value;                        
                        // للتأكد من إرسال القيمة، إضافة حقل مخفي جديد
                        var extraHiddenInput = document.createElement('input');
                        extraHiddenInput.type = 'hidden';
                        extraHiddenInput.name = 'press_extra';
                        extraHiddenInput.value = pressSelector.value;
                        pricingForm.appendChild(extraHiddenInput);
                    }
                });
            }
            
            // إضافة مستمعات أحداث لحساب إجمالي تكلفة الطباعة
            // نستخدم PricingSystem.Print.calculatePressCost بدلاً من الدالة المحلية
            var pressRunsInput = document.getElementById('id_press_runs');
            var pressPriceInput = document.getElementById('id_press_price_per_1000');
            var pressTransportationInput = document.getElementById('id_press_transportation');
            
            if (pressRunsInput && window.PricingSystem && PricingSystem.Print) {
                pressRunsInput.addEventListener('input', PricingSystem.Print.calculatePressCost);
            }
            
            if (pressPriceInput && window.PricingSystem && PricingSystem.Print) {
                pressPriceInput.addEventListener('input', PricingSystem.Print.calculatePressCost);
            }
            
            if (pressTransportationInput && window.PricingSystem && PricingSystem.Print) {
                pressTransportationInput.addEventListener('input', PricingSystem.Print.calculatePressCost);
            }
            
            // تحميل الماكينات إذا كان المورد محددًا
            var supplierSelect = document.getElementById('id_supplier');
            if (supplierSelect && supplierSelect.value) {
                setTimeout(function() {
                    PricingSystem.Press.loadPressesDirectly(supplierSelect.value);
                }, 200);
            }
            
            // إعادة تعريف الدوال العالمية لدعم الشفرة القديمة
            window.updatePressValue = function(value) {
                PricingSystem.Press.updatePressValue(value);
            };
            
            window.updatePressInfo = function(pressValue) {
                PricingSystem.Press.updatePressInfo(pressValue);
            };
            
            window.loadPressesDirectly = function(supplierId) {
                PricingSystem.Press.loadPressesDirectly(supplierId);
            };
            
            window.fetchPressPriceDirectly = function(pressId, pressPriceInput) {
                PricingSystem.Press.fetchPressPriceDirectly(pressId, pressPriceInput);
            };
            
            // لا نقوم بإعادة تعريف calculatePressTotalCost لتجنب التعارض مع PricingSystem.Print.calculatePressCost
            // بدلاً من ذلك، نستخدم دائمًا PricingSystem.Print.calculatePressCost
            
        } catch (e) {
            console.error('خطأ في إعداد معالجات أحداث الماكينات:', e);
        }
    },
    
    /**
     * تهيئة حقول المكابس عند تحميل الصفحة
     */
    init: function() {
        // تحميل المكابس الأولية للغلاف
        const pressSelector = document.getElementById('press_selector');
        if (pressSelector && pressSelector.options.length <= 1) {
            // إذا كان الحقل فارغ، حمل جميع المكابس المتاحة
            this.loadPressesDirectly('');
        }
        
        // تحميل المكابس الأولية للمحتوى الداخلي
        const internalPressSelector = document.getElementById('internal_press_selector');
        if (internalPressSelector && internalPressSelector.options.length <= 1) {
            // إذا كان الحقل فارغ، حمل جميع المكابس المتاحة
            this.loadInternalPressesDirectly('');
        }
    }
};

// استدعاء دالة إعداد معالجات الأحداث
document.addEventListener('DOMContentLoaded', function() {
    PricingSystem.Press.setupPressEventHandlers();
    PricingSystem.Press.init();
});