/**
 * api-services.js - دالات التعامل مع API
 */

// تعريف كائن عام للمشروع إذا لم يكن موجودًا
window.PricingSystem = window.PricingSystem || {};

// تعريف وحدة خدمات API
PricingSystem.API = {
    
    // URLs الجديدة للـ APIs
    baseUrl: '/pricing/api/v2/',
    
    // دالة مساعدة لإرسال طلبات POST
    async postRequest(url, data) {
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
            },
            body: JSON.stringify(data)
        });
        return response.json();
    },
    
    // دالة مساعدة لإرسال طلبات GET
    async getRequest(url) {
        const response = await fetch(url);
        return response.json();
    },
    
    /**
     * حساب التكلفة الإجمالية للطلب
     */
    async calculateTotalCost(orderData) {
        try {
            const result = await this.postRequest(this.baseUrl + 'calculate-cost/', orderData);
            return result;
        } catch (error) {
            console.error('خطأ في حساب التكلفة:', error);
            return { success: false, error: error.message };
        }
    },
    
    /**
     * جلب سعر الورق من المورد
     */
    async getPaperPrice(supplierId, paperTypeId, paperSizeId, weight = 80, origin = 'local') {
        try {
            const url = `${this.baseUrl}paper-price/?supplier_id=${supplierId}&paper_type_id=${paperTypeId}&paper_size_id=${paperSizeId}&weight=${weight}&origin=${origin}`;
            const result = await this.getRequest(url);
            return result;
        } catch (error) {
            console.error('خطأ في جلب سعر الورق:', error);
            return { success: false, error: error.message };
        }
    },
    
    /**
     * جلب سعر الزنكات من المورد
     */
    async getPlatePrice(supplierId, plateSizeId) {
        try {
            const url = `${this.baseUrl}plate-price/?supplier_id=${supplierId}&plate_size_id=${plateSizeId}`;
            const result = await this.getRequest(url);
            return result;
        } catch (error) {
            console.error('خطأ في جلب سعر الزنك:', error);
            return { success: false, error: error.message };
        }
    },
    
    /**
     * جلب سعر الطباعة الرقمية
     */
    async getDigitalPrintingPrice(supplierId, paperSizeId, colorType = 'color') {
        try {
            const url = `${this.baseUrl}digital-printing-price/?supplier_id=${supplierId}&paper_size_id=${paperSizeId}&color_type=${colorType}`;
            const result = await this.getRequest(url);
            return result;
        } catch (error) {
            console.error('خطأ في جلب سعر الطباعة الرقمية:', error);
            return { success: false, error: error.message };
        }
    },
    
    /**
     * حساب تكلفة خدمات التشطيب
     */
    async calculateFinishingCost(finishingServices, quantity) {
        try {
            const data = {
                finishing_services: finishingServices,
                quantity: quantity
            };
            const result = await this.postRequest(this.baseUrl + 'finishing-cost/', data);
            return result;
        } catch (error) {
            console.error('خطأ في حساب تكلفة التشطيب:', error);
            return { success: false, error: error.message };
        }
    },
    
    /**
     * جلب أنواع الورق النشطة
     */
    async getPaperTypes() {
        try {
            const result = await this.getRequest(this.baseUrl + 'paper-types/');
            return result;
        } catch (error) {
            console.error('خطأ في جلب أنواع الورق:', error);
            return { success: false, error: error.message };
        }
    },
    
    /**
     * جلب مقاسات الورق النشطة
     */
    async getPaperSizes() {
        try {
            const result = await this.getRequest(this.baseUrl + 'paper-sizes/');
            return result;
        } catch (error) {
            console.error('خطأ في جلب مقاسات الورق:', error);
            return { success: false, error: error.message };
        }
    },
    
    /**
     * جلب الموردين النشطين
     */
    async getSuppliers() {
        try {
            const result = await this.getRequest(this.baseUrl + 'suppliers/');
            return result;
        } catch (error) {
            console.error('خطأ في جلب الموردين:', error);
            return { success: false, error: error.message };
        }
    },
    
    /**
     * جلب ملخص طلب التسعير
     */
    async getOrderSummary(orderId) {
        try {
            const result = await this.getRequest(this.baseUrl + `order-summary/${orderId}/`);
            return result;
        } catch (error) {
            console.error('خطأ في جلب ملخص الطلب:', error);
            return { success: false, error: error.message };
        }
    },
    /**
     * تحميل ماكينات الطباعة المتاحة لمورد محدد
     * @param {string} supplierId - معرف المورد
     * @param {HTMLSelectElement} pressSelect - عنصر قائمة ماكينات الطباعة
     * @param {HTMLInputElement} pressPriceInput - عنصر حقل سعر الماكينة
     */
    loadPresses: function(supplierId, pressSelect, pressPriceInput) {
        
        if (!supplierId || !pressSelect) {
            console.error('معرف المورد أو عنصر قائمة الماكينات غير موجود');
            return;
        }
                
        // تعطيل القائمة أثناء التحميل
        pressSelect.disabled = true;
        
        // مسح الخيارات الحالية
        pressSelect.innerHTML = '<option value="">-- جاري تحميل الماكينات... --</option>';
        
        // مسح سعر الماكينة
        if (pressPriceInput) {
            pressPriceInput.value = '';
            
            // إطلاق حدث تغيير سعر الماكينة عبر ناقل الأحداث
            if (PricingSystem.EventBus) {
                PricingSystem.EventBus.fieldChanged('id_press_price_per_1000', '');
            }
        }
        
        // استدعاء API للحصول على ماكينات الطباعة المتاحة
        const apiUrl = `/pricing/api/presses/?supplier_id=${supplierId}`;
        
        // استخدام الدالة الجديدة
        this.getRequest(apiUrl)
            .then(data => {
                // إعادة تمكين القائمة
                pressSelect.disabled = false;
                
                // إعادة ضبط قائمة الماكينات
                pressSelect.innerHTML = '<option value="">-- اختر ماكينة الطباعة --</option>';
                                
                // التحقق من وجود البيانات والمصفوفة presses
                if (data && data.success && data.presses && Array.isArray(data.presses)) {                    
                    // إضافة ماكينات الطباعة إلى القائمة
                    data.presses.forEach(press => {
                        if (!press || typeof press !== 'object') {
                            console.warn('تم تخطي ماكينة غير صالحة:', press);
                            return;
                        }
                        
                        const option = document.createElement('option');
                        option.value = press.id;
                        option.text = press.name || `ماكينة ${press.id}`;
                        
                        // التحقق من وجود سعر الماكينة (price_per_1000 أو unit_price)
                        if (press.price_per_1000 !== undefined) {
                            option.dataset.price = press.price_per_1000;
                        } else if (press.unit_price !== undefined) {
                            option.dataset.price = press.unit_price;
                        } else {
                            console.warn(`لم يتم العثور على سعر للماكينة: ${press.name}`);
                        }
                        
                        // التحقق من وجود أبعاد الماكينة (width/height)
                        if (press.width !== undefined) {
                            option.dataset.width = press.width;
                        }
                        if (press.height !== undefined) {
                            option.dataset.height = press.height;
                        }
                        
                        pressSelect.appendChild(option);
                    });
                    
                    // تحديث حالة القائمة
                    if (pressSelect.options.length > 1) {
                    } else {
                        console.warn('لم يتم إضافة أي ماكينات إلى القائمة');
                    }
                } else {
                    console.warn('لم يتم العثور على ماكينات طباعة للمورد المحدد');
                    if (data && data.error) {
                        console.error('رسالة الخطأ من الخادم:', data.error);
                    }
                }
                
                // إطلاق حدث تغيير قائمة الماكينات عبر ناقل الأحداث
                if (PricingSystem.EventBus) {
                    PricingSystem.EventBus.emit('presses:loaded', {
                        supplierId: supplierId,
                        success: data && data.success ? true : false
                    });
                }
            })
            .catch(error => {
                console.error('خطأ في استدعاء API لماكينات الطباعة:', error);
                // إعادة تمكين القائمة
                pressSelect.disabled = false;
                // إعادة ضبط قائمة الماكينات مع رسالة خطأ
                pressSelect.innerHTML = '<option value="">-- خطأ في تحميل الماكينات --</option>';
                
                // إطلاق حدث خطأ عبر ناقل الأحداث
                if (PricingSystem.EventBus) {
                    PricingSystem.EventBus.emit('api:error', {
                        type: 'presses',
                        supplierId: supplierId,
                        error: error.message
                    });
                }
            });
    },
    
    /**
     * الحصول على سعر ماكينة الطباعة
     * @param {string} pressId - معرف ماكينة الطباعة
     * @param {HTMLInputElement} pressPriceInput - عنصر حقل سعر الماكينة
     */
    fetchPressPrice: function(pressId, pressPriceInput) {
        if (!pressId || !pressPriceInput) {
            console.warn('معرف الماكينة أو عنصر حقل السعر غير موجود');
            return;
        }
        
        
        // محاولة الحصول على السعر من البيانات المخزنة في القائمة
        const option = document.querySelector(`option[value="${pressId}"]`);
        if (option && option.dataset.price) {
            const price = option.dataset.price;
            pressPriceInput.value = price;
            
            // إطلاق حدث تغيير سعر الماكينة عبر ناقل الأحداث
            if (PricingSystem.EventBus) {
                PricingSystem.EventBus.fieldChanged('id_press_price_per_1000', price);
            } else {
                // تحديث إجمالي تكلفة الطباعة
                if (typeof PricingSystem.Print !== 'undefined' && typeof PricingSystem.Print.calculatePressCost === 'function') {
                    setTimeout(function() {
                        PricingSystem.Print.calculatePressCost();
                    }, 100);
                }
            }
            return;
        }
                
        // استدعاء API للحصول على سعر الماكينة
        fetch(`/pricing/api/press-price/?press_id=${pressId}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`فشل الطلب بكود الحالة: ${response.status}`);
                }
                return response.text().then(text => {
                    try {
                        return JSON.parse(text);
                    } catch (error) {
                        console.error('خطأ في تحليل استجابة JSON:', error);
                        console.error('نص الاستجابة:', text);
                        throw new Error('خطأ في تحليل استجابة الخادم');
                    }
                });
            })
            .then(data => {
                
                if (data.success) {
                    // تحديث سعر الماكينة - التحقق من وجود price أو price_per_1000 أو unit_price
                    let price = null;
                    if (data.price_per_1000 !== undefined) {
                        price = data.price_per_1000;
                    } else if (data.price !== undefined) {
                        price = data.price;
                    } else if (data.unit_price !== undefined) {
                        price = data.unit_price;
                    }
                    
                    if (price !== null) {
                        pressPriceInput.value = price;
                        
                        // إطلاق حدث تغيير سعر الماكينة عبر ناقل الأحداث
                        if (PricingSystem.EventBus) {
                            PricingSystem.EventBus.fieldChanged('id_press_price_per_1000', price);
                        } else {
                            // تحديث إجمالي تكلفة الطباعة
                            if (typeof PricingSystem.Print !== 'undefined' && typeof PricingSystem.Print.calculatePressCost === 'function') {
                                setTimeout(function() {
                                    PricingSystem.Print.calculatePressCost();
                                }, 100);
                            }
                        }
                    } else {
                        console.warn('لم يتم العثور على سعر للماكينة في استجابة API');
                    }
                } else {
                    console.error('خطأ في استجابة API:', data.error || 'سبب غير معروف');
                }
            })
            .catch(error => {
                console.error('خطأ في استدعاء API لسعر الماكينة:', error);
                
                // إطلاق حدث خطأ عبر ناقل الأحداث
                if (PricingSystem.EventBus) {
                    PricingSystem.EventBus.emit('api:error', {
                        type: 'press-price',
                        pressId: pressId,
                        error: error.message
                    });
                }
            });
    },
    
    /**
     * تحميل موردي الورق
     * @param {HTMLSelectElement} paperSupplierSelect - عنصر قائمة موردي الورق
     */
    loadPaperSuppliers: function(paperSupplierSelect) {
        if (!paperSupplierSelect) {
            return;
        }
        
        // تعطيل القائمة أثناء التحميل
        paperSupplierSelect.disabled = true;
        
        // مسح الخيارات الحالية
        paperSupplierSelect.innerHTML = '<option value="">-- اختر مورد الورق --</option>';
        
        // استدعاء API للحصول على موردي الورق
        fetch('/pricing/api/paper-suppliers/')
            .then(response => {
                if (!response.ok) {
                    throw new Error(`فشل الطلب بكود الحالة: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                // إعادة تمكين القائمة
                paperSupplierSelect.disabled = false;
                
                if (data.success && data.suppliers) {
                    // إضافة موردي الورق إلى القائمة
                    data.suppliers.forEach(supplier => {
                        const option = document.createElement('option');
                        option.value = supplier.id;
                        option.text = supplier.name;
                        paperSupplierSelect.appendChild(option);
                    });
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
     * تحميل أوزان الورق المتاحة لمورد ونوع ورق محددين
     * @param {string} supplierId - معرف المورد
     * @param {string} paperTypeId - معرف نوع الورق
     * @param {HTMLSelectElement} paperWeightSelect - عنصر قائمة أوزان الورق
     */
    loadPaperWeights: function(supplierId, paperTypeId, paperWeightSelect) {
        if (!supplierId || !paperTypeId || !paperWeightSelect) {
            return;
        }
        
        // تعطيل القائمة أثناء التحميل
        paperWeightSelect.disabled = true;
        
        // مسح الخيارات الحالية
        paperWeightSelect.innerHTML = '<option value="">-- اختر جرام الورق --</option>';
        
        // استدعاء API للحصول على أوزان الورق المتاحة
        fetch(`/pricing/api/paper-weights/?supplier_id=${supplierId}&paper_type_id=${paperTypeId}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`فشل الطلب بكود الحالة: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                // إعادة تمكين القائمة
                paperWeightSelect.disabled = false;
                
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
            .catch(error => {
                console.error('خطأ في استدعاء API لأوزان الورق:', error);
                // إعادة تمكين القائمة
                paperWeightSelect.disabled = false;
                // إعادة ضبط قائمة الأوزان مع رسالة خطأ
                paperWeightSelect.innerHTML = '<option value="">-- خطأ في تحميل أوزان الورق --</option>';
            });
    },
    
    /**
     * تحميل مقاسات الورق المتاحة لمورد ونوع ورق محددين
     * @param {string} supplierId - معرف المورد
     * @param {string} paperTypeId - معرف نوع الورق
     * @param {HTMLSelectElement} paperSheetTypeSelect - عنصر قائمة مقاسات الورق
     */
    loadPaperSheetTypes: function(supplierId, paperTypeId, paperSheetTypeSelect) {
        if (!supplierId || !paperTypeId || !paperSheetTypeSelect) {
            return;
        }
        
        // تعطيل القائمة أثناء التحميل
        paperSheetTypeSelect.disabled = true;
        
        // مسح الخيارات الحالية
        paperSheetTypeSelect.innerHTML = '<option value="">-- اختر مقاس الفرخ --</option>';
        
        // استدعاء API للحصول على مقاسات الورق المتاحة
        fetch(`/pricing/api/paper-sheet-types/?supplier_id=${supplierId}&paper_type_id=${paperTypeId}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`فشل الطلب بكود الحالة: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                // إعادة تمكين القائمة
                paperSheetTypeSelect.disabled = false;
                
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
            .catch(error => {
                console.error('خطأ في استدعاء API لمقاسات الورق:', error);
                // إعادة تمكين القائمة
                paperSheetTypeSelect.disabled = false;
                // إعادة ضبط قائمة المقاسات مع رسالة خطأ
                paperSheetTypeSelect.innerHTML = '<option value="">-- خطأ في تحميل مقاسات الورق --</option>';
            });
    },
    
    /**
     * تحميل منشأ الورق المتاح لمورد ونوع ورق وجرام ومقاس محددين
     * @param {string} supplierId - معرف المورد
     * @param {string} paperTypeId - معرف نوع الورق
     * @param {string} gsm - جرام الورق
     * @param {string} sheetTypeId - معرف مقاس الورق
     * @param {HTMLSelectElement} paperOriginSelect - عنصر قائمة منشأ الورق
     */
    loadPaperOrigins: function(supplierId, paperTypeId, gsm, sheetTypeId, paperOriginSelect) {
        if (!supplierId || !paperTypeId || !gsm || !sheetTypeId || !paperOriginSelect) {
            return;
        }
        
        // تعطيل القائمة أثناء التحميل
        paperOriginSelect.disabled = true;
        
        // مسح الخيارات الحالية
        paperOriginSelect.innerHTML = '<option value="">-- اختر منشأ الورق --</option>';
        
        // استدعاء API للحصول على منشأ الورق المتاح
        fetch(`/pricing/api/paper-origins/?supplier_id=${supplierId}&paper_type_id=${paperTypeId}&gsm=${gsm}&sheet_type_id=${sheetTypeId}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`فشل الطلب بكود الحالة: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                // إعادة تمكين القائمة
                paperOriginSelect.disabled = false;
                
                if (data.success && data.origins) {
                    // استخدام Map للتأكد من عدم تكرار المنشأ
                    const uniqueOrigins = new Map();
                    
                    // إضافة جميع المنشأ إلى المجموعة الفريدة
                    data.origins.forEach(function(item) {
                        if (item.origin) {
                            uniqueOrigins.set(item.origin_id, item.origin);
                        }
                    });
                    
                    // إنشاء خيارات للقائمة المنسدلة من المنشأ الفريد
                    if (uniqueOrigins.size > 0) {
                        uniqueOrigins.forEach(function(origin, originId) {
                            const option = document.createElement('option');
                            option.value = originId;
                            option.text = origin;
                            paperOriginSelect.appendChild(option);
                        });
                    }
                }
            })
            .catch(error => {
                console.error('خطأ في استدعاء API لمنشأ الورق:', error);
                // إعادة تمكين القائمة
                paperOriginSelect.disabled = false;
                // إعادة ضبط قائمة المنشأ مع رسالة خطأ
                paperOriginSelect.innerHTML = '<option value="">-- خطأ في تحميل منشأ الورق --</option>';
            });
    },
    
    /**
     * تحديث سعر الورق بناءً على المعايير المحددة
     */
    updatePaperPrice: function() {
        const paperTypeSelect = document.getElementById('id_paper_type');
        const paperSupplierSelect = document.getElementById('id_paper_supplier');
        const paperSheetTypeSelect = document.getElementById('id_paper_sheet_type');
        const paperWeightSelect = document.getElementById('id_paper_weight');
        const paperOriginSelect = document.getElementById('id_paper_origin');
        const paperPriceInput = document.getElementById('id_paper_price');
        const paperSheetsCountInput = document.getElementById('id_paper_sheets_count');
        const paperTotalCostInput = document.getElementById('id_paper_total_cost');
        
        if (!paperTypeSelect || !paperSupplierSelect || !paperSheetTypeSelect || 
            !paperWeightSelect || !paperPriceInput) {
            return;
        }
        
        const selectedType = paperTypeSelect.value;
        const selectedSupplierId = paperSupplierSelect.value;
        const selectedSheetType = paperSheetTypeSelect.value;
        const selectedWeight = paperWeightSelect.value;
        const selectedOrigin = paperOriginSelect ? paperOriginSelect.value : '';
        
        // إذا لم تكتمل البيانات المطلوبة، لا تفعل شيء
        if (!selectedType || !selectedSupplierId || !selectedSheetType || !selectedWeight) {
            paperPriceInput.value = '';
            if (paperTotalCostInput) paperTotalCostInput.value = '';
            return;
        }
        
        // استدعاء API للحصول على سعر الورق
        const url = `/pricing/api/paper-price/?supplier_id=${selectedSupplierId}&paper_type_id=${selectedType}&sheet_type=${selectedSheetType}&gsm=${selectedWeight}${selectedOrigin ? '&origin=' + selectedOrigin : ''}`;
        
        fetch(url)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`فشل الطلب بكود الحالة: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                if (data.success && data.price !== undefined) {
                    // تحديث سعر الورق
                    paperPriceInput.value = data.price;
                    
                    // حساب التكلفة الإجمالية إذا كانت الكمية متاحة
                    if (paperSheetsCountInput && paperTotalCostInput) {
                        const quantity = parseInt(paperSheetsCountInput.value) || 0;
                        const price = parseFloat(data.price) || 0;
                        const totalCost = price * quantity;
                        paperTotalCostInput.value = totalCost.toFixed(2);
                    }
                    
                    // تحديث إجمالي تكلفة الورق
                    if (typeof PricingSystem.Paper !== 'undefined' && typeof PricingSystem.Paper.updateTotalPaperCost === 'function') {
                        PricingSystem.Paper.updateTotalPaperCost();
                    }
                } else {
                    paperPriceInput.value = '';
                    if (paperTotalCostInput) paperTotalCostInput.value = '';
                    console.warn('لم يتم العثور على سعر للورق المحدد:', data.error || 'سبب غير معروف');
                }
            })
            .catch(error => {
                console.error('خطأ في استدعاء API لسعر الورق:', error);
                paperPriceInput.value = '';
                if (paperTotalCostInput) paperTotalCostInput.value = '';
            });
    },
    
    /**
     * تحميل موردي خدمة معينة
     * @param {string} selectId - معرف عنصر القائمة المنسدلة
     * @param {string} serviceType - نوع الخدمة
     */
    loadSuppliers: function(selectId, serviceType) {
        const supplierSelect = document.getElementById(selectId);
        if (!supplierSelect) return;
        
        // مسح الخيارات الحالية
        supplierSelect.innerHTML = '<option value="">-- اختر المورد --</option>';
        
        // استدعاء API للحصول على الموردين المتاحين لنوع الخدمة
        fetch(`/pricing/api/suppliers-by-service/?service_type=${serviceType}`)
            .then(response => response.json())
            .then(data => {
                if (data.success && data.suppliers) {
                    data.suppliers.forEach(supplier => {
                        const option = document.createElement('option');
                        option.value = supplier.id;
                        option.text = supplier.name;
                        option.dataset.price = supplier.price;
                        supplierSelect.appendChild(option);
                    });
                } else {
                    // إذا لم تنجح عملية الجلب، استخدم بيانات افتراضية
                    const suppliers = [
                        { id: 1, name: 'مورد 1' },
                        { id: 2, name: 'مورد 2' },
                        { id: 3, name: 'مورد 3' }
                    ];
                    
                    suppliers.forEach(supplier => {
                        const option = document.createElement('option');
                        option.value = supplier.id;
                        option.text = supplier.name;
                        supplierSelect.appendChild(option);
                    });
                }
            })
            .catch(error => {
                console.error('Error fetching suppliers:', error);
                // استخدام بيانات افتراضية في حالة الخطأ
                const suppliers = [
                    { id: 1, name: 'مورد 1' },
                    { id: 2, name: 'مورد 2' },
                    { id: 3, name: 'مورد 3' }
                ];
                
                suppliers.forEach(supplier => {
                    const option = document.createElement('option');
                    option.value = supplier.id;
                    option.text = supplier.name;
                    supplierSelect.appendChild(option);
                });
            });
    },
    
    /**
     * تحديث سعر الخدمة بناءً على المورد المختار
     * @param {string} serviceType - نوع الخدمة
     * @param {string} supplierId - معرف المورد
     */
    updateServicePrice: function(serviceType, supplierId) {
        if (!supplierId) return;
        
        const supplierSelect = document.getElementById(`id_${serviceType}_supplier`);
        const priceInput = document.getElementById(`id_${serviceType}_price`);
        
        if (!supplierSelect || !priceInput) return;
        
        // البحث عن الخيار المحدد للحصول على السعر
        const selectedOption = supplierSelect.querySelector(`option[value="${supplierId}"]`);
        if (selectedOption && selectedOption.dataset.price) {
            priceInput.value = selectedOption.dataset.price;
            
            // تحديث إجمالي تكلفة خدمات ما بعد الطباعة
            if (typeof PricingSystem.Finishing !== 'undefined' && typeof PricingSystem.Finishing.calculateTotalFinishingCost === 'function') {
                PricingSystem.Finishing.calculateTotalFinishingCost();
            }
        } else {
            // إذا لم يكن هناك سعر محدد، استخدم الأسعار الافتراضية
            const prices = {
                'coating': { '1': 100, '2': 120, '3': 90 },
                'folding': { '1': 50, '2': 60, '3': 45 },
                'die_cut': { '1': 200, '2': 220, '3': 180 },
                'spot_uv': { '1': 150, '2': 170, '3': 140 }
            };
            
            if (prices[serviceType] && prices[serviceType][supplierId]) {
                priceInput.value = prices[serviceType][supplierId];
                
                // تحديث إجمالي تكلفة خدمات ما بعد الطباعة
                if (typeof PricingSystem.Finishing !== 'undefined' && typeof PricingSystem.Finishing.calculateTotalFinishingCost === 'function') {
                    PricingSystem.Finishing.calculateTotalFinishingCost();
                }
            }
        }
    }
}; 