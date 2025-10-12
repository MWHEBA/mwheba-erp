/**
 * session-handlers.js - دالات معالجة بيانات الجلسة
 */

// تعريف كائن عام للمشروع إذا لم يكن موجودًا
window.PricingSystem = window.PricingSystem || {};

// تعريف وحدة معالجة بيانات الجلسة
PricingSystem.Session = {
    /**
     * بيانات الجلسة
     */
    sessionData: {},
    
    /**
     * تحميل بيانات الجلسة من العنصر المخفي في النموذج
     */
    loadSessionData: function() {
        // التحقق من وجود عنصر يحتوي على بيانات الجلسة
        const sessionDataElement = document.getElementById('session_data');
        if (!sessionDataElement || !sessionDataElement.textContent) {
            return;
        }
        
        try {
            // استخراج البيانات من العنصر المخفي
            const sessionDataText = sessionDataElement.textContent.trim();
            if (!sessionDataText) {
                console.warn('بيانات الجلسة فارغة');
                return;
            }
            
            const sessionData = JSON.parse(sessionDataText);
            if (!sessionData || typeof sessionData !== 'object') {
                console.warn('بيانات الجلسة غير صالحة');
                return;
            }
            
            // معالجة خاصة لحقل المورد وماكينة الطباعة
            // يجب تحميل المورد أولاً ثم ماكينة الطباعة
            const supplierValue = sessionData['supplier'];
            const pressValue = sessionData['press'];
            
            // تحميل المورد أولاً إذا كان موجودًا
            if (supplierValue) {
                const supplierSelect = document.getElementById('id_supplier');
                if (supplierSelect) {
                    supplierSelect.value = supplierValue;
                    
                    // إطلاق حدث change لتحميل ماكينات الطباعة بعد تأخير قصير
                    // هذا يعطي وقتًا للصفحة للتهيئة بشكل كامل
                    setTimeout(() => {
                        const supplierEvent = new Event('change', { bubbles: true });
                        supplierSelect.dispatchEvent(supplierEvent);
                        
                        // تحميل ماكينة الطباعة بعد تحميل الماكينات المتاحة
                        if (pressValue) {
                            setTimeout(() => {
                                const pressSelect = document.getElementById('id_press') || document.getElementById('press_selector');
                                if (pressSelect) {
                                    pressSelect.value = pressValue;
                                    const pressEvent = new Event('change', { bubbles: true });
                                    pressSelect.dispatchEvent(pressEvent);
                                }
                            }, 500);
                        }
                    }, 300);
                }
            }
            
            // تعيين القيم للحقول المناسبة (باستثناء المورد وماكينة الطباعة التي تم معالجتها بالفعل)
            Object.keys(sessionData).forEach(key => {
                // تخطي المورد وماكينة الطباعة لأننا عالجناهما بالفعل
                if (key === 'supplier' || key === 'press') return;
                
                const value = sessionData[key];
                if (value === undefined || value === null) return;
                
                const element = document.getElementById(`id_${key}`);
                
                if (element) {
                    // تعيين القيمة حسب نوع العنصر
                    if (element.tagName === 'SELECT') {
                        element.value = value;
                        // إطلاق حدث change لتحديث أي حقول مرتبطة
                        const event = new Event('change', { bubbles: true });
                        element.dispatchEvent(event);
                    } else if (element.type === 'checkbox') {
                        element.checked = value === 'on' || value === 'true' || value === true;
                        // إطلاق حدث change لتحديث أي حقول مرتبطة
                        const event = new Event('change', { bubbles: true });
                        element.dispatchEvent(event);
                    } else {
                        element.value = value;
                    }
                }
                
                // معالجة خاصة لبعض الحقول التي لها أسماء مختلفة
                if (key === 'ctp_supplier' && value) {
                    const ctpSupplierElement = document.getElementById('id_ctp_supplier');
                    if (ctpSupplierElement) {
                        ctpSupplierElement.value = value;
                        // إطلاق حدث change لتحديث أي حقول مرتبطة
                        const event = new Event('change', { bubbles: true });
                        ctpSupplierElement.dispatchEvent(event);
                    }
                }
                
                if (key === 'ctp_plate_size' && value) {
                    const ctpPlateSizeElement = document.getElementById('id_ctp_plate_size');
                    if (ctpPlateSizeElement) {
                        ctpPlateSizeElement.value = value;
                        // إطلاق حدث change لتحديث أي حقول مرتبطة
                        const event = new Event('change', { bubbles: true });
                        ctpPlateSizeElement.dispatchEvent(event);
                    }
                }
            });
            
            // تحديث حقول إضافية بعد تعيين القيم - بعد تأخير قصير للتأكد من تحميل جميع البيانات
            setTimeout(() => {
                if (typeof PricingSystem.Print !== 'undefined' && typeof PricingSystem.Print.updateColorsFields === 'function') {
                    const printSidesSelect = document.getElementById('id_print_sides');
                    if (printSidesSelect) {
                        PricingSystem.Print.updateColorsFields(printSidesSelect, 
                            document.getElementById('single-side-colors'), 
                            document.getElementById('double-side-colors'));
                    }
                }
                
                if (typeof PricingSystem.Paper !== 'undefined' && typeof PricingSystem.Paper.calculatePaperSheetsDirectly === 'function') {
                    PricingSystem.Paper.calculatePaperSheetsDirectly();
                }
                
                if (typeof PricingSystem.CTP !== 'undefined' && typeof PricingSystem.CTP.calculateCtpCost === 'function') {
                    PricingSystem.CTP.calculateCtpCost(false);
                }
                
                if (typeof PricingSystem.Montage !== 'undefined' && typeof PricingSystem.Montage.updateMontageInfo === 'function') {
                    const montageInfoField = document.getElementById('id_montage_info');
                    if (montageInfoField) {
                        PricingSystem.Montage.updateMontageInfo(montageInfoField);
                    }
                }
            }, 800);
        } catch (e) {
            console.error('خطأ في تحميل بيانات الجلسة:', e);
        }
    },
    
    /**
     * حفظ بيانات النموذج في الجلسة تلقائيًا
     */
    saveFormData: function() {
        // تجميع بيانات النموذج
        const form = document.getElementById('pricing-form');
        if (!form) return;
        
        const formData = new FormData(form);
        
        // التأكد من عدم إرسال حقل regular_submit (هذا خاص بالإرسال العادي)
        formData.delete('regular_submit');
        
        // إضافة بيانات الزنكات
        const ctpSupplierSelect = document.getElementById('id_ctp_supplier');
        const ctpPlateSizeSelect = document.getElementById('id_ctp_plate_size');
        const ctpPlatesCount = document.getElementById('id_ctp_plates_count');
        const ctpPlatePrice = document.getElementById('id_ctp_plate_price');
        const ctpTransportation = document.getElementById('id_ctp_transportation');
        
        if (ctpSupplierSelect && ctpSupplierSelect.value) {
            formData.append('ctp_supplier', ctpSupplierSelect.value);
        }
        if (ctpPlateSizeSelect && ctpPlateSizeSelect.value) {
            formData.append('ctp_plate_size', ctpPlateSizeSelect.value);
        }
        if (ctpPlatesCount && ctpPlatesCount.value) {
            formData.append('ctp_plates_count', ctpPlatesCount.value);
        }
        if (ctpPlatePrice && ctpPlatePrice.value) {
            formData.append('ctp_plate_price', ctpPlatePrice.value);
        }
        if (ctpTransportation && ctpTransportation.value) {
            formData.append('ctp_transportation', ctpTransportation.value);
        }
        
        // إضافة بيانات نوع الطباعة وعدد الألوان
        const orderTypeSelect = document.getElementById('id_order_type');
        if (orderTypeSelect && orderTypeSelect.value) {
            formData.append('order_type', orderTypeSelect.value);
        }
        
        // حفظ عدد ألوان التصميم حسب نوع الطباعة (وجه واحد أو وجهين)
        const printSidesSelect = document.getElementById('id_print_sides');
        if (printSidesSelect && printSidesSelect.value) {
            formData.append('print_sides', printSidesSelect.value);
            
            if (printSidesSelect.value === '1' || printSidesSelect.value === '3') {
                const colorsDesign = document.getElementById('id_colors_design');
                if (colorsDesign && colorsDesign.value) {
                    formData.append('colors_design', colorsDesign.value);
                }
            } else if (printSidesSelect.value === '2') {
                const colorsFront = document.getElementById('id_colors_front');
                const colorsBack = document.getElementById('id_colors_back');
                if (colorsFront && colorsFront.value) {
                    formData.append('colors_front', colorsFront.value);
                }
                if (colorsBack && colorsBack.value) {
                    formData.append('colors_back', colorsBack.value);
                }
            }
        }
        
        // إضافة بيانات المطبعة وماكينة الطباعة
        const supplierSelect = document.getElementById('id_supplier');
        const pressSelect = document.getElementById('id_press');
        if (supplierSelect && supplierSelect.value) {
            formData.append('supplier', supplierSelect.value);
        }
        if (pressSelect && pressSelect.value) {
            formData.append('press', pressSelect.value);
        }
        
        // إضافة بيانات جرام الورق
        const paperWeightSelect = document.getElementById('id_paper_weight');
        if (paperWeightSelect && paperWeightSelect.value) {
            formData.append('paper_weight', paperWeightSelect.value);
        }
        
        // إضافة بيانات سعر التصميم
        const designPriceInput = document.getElementById('id_design_price');
        if (designPriceInput && designPriceInput.value) {
            formData.append('design_price', designPriceInput.value);
        }
        
        // إضافة جميع القوائم المنسدلة بشكل صريح
        const allSelects = form.querySelectorAll('select');
        allSelects.forEach(select => {
            if (select.name && select.value) {
                formData.append(select.name, select.value);
            }
        });
        
        // إضافة جميع حقول النص والأرقام بشكل صريح
        const allTextInputs = form.querySelectorAll('input[type="text"], input[type="number"], input[type="email"], input[type="tel"], input[type="date"], input[type="time"], textarea');
        allTextInputs.forEach(input => {
            if (input.name && input.value) {
                formData.append(input.name, input.value);
            }
        });
        
        // إضافة مربعات الاختيار بشكل صريح
        const allCheckboxes = form.querySelectorAll('input[type="checkbox"]');
        allCheckboxes.forEach(checkbox => {
            if (checkbox.name) {
                formData.append(checkbox.name, checkbox.checked ? 'on' : 'off');
            }
        });
        
        // الحصول على رمز CSRF
        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
        
        // إرسال البيانات باستخدام fetch API
        fetch(window.location.href, {
            method: 'POST',
            body: formData,
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': csrfToken
            }
        }).then(response => {
            // تم حفظ البيانات بنجاح
            console.log('تم حفظ بيانات النموذج في الجلسة بنجاح');
        }).catch(error => {
            // حدث خطأ أثناء الحفظ
            console.error('خطأ في حفظ البيانات:', error);
        });
    },
    
    /**
     * إعداد معالجات أحداث الجلسة
     */
    setupSessionEventHandlers: function() {
        const form = document.getElementById('pricing-form');
        if (!form) return;
        
        // الحصول على جميع الحقول في النموذج
        const formInputs = form.querySelectorAll('input, select, textarea');
        
        // تأخير حفظ البيانات لتجنب الطلبات المتكررة
        let saveTimeout;
        
        // إضافة مستمع أحداث لكل حقل
        formInputs.forEach(input => {
            // استثناء حقل CSRF وأزرار الإرسال
            if (input.name === 'csrfmiddlewaretoken' || input.type === 'submit' || input.type === 'button') {
                return;
            }
            
            // إضافة مستمع لحدث التغيير
            input.addEventListener('change', function() {
                // إلغاء المؤقت السابق إذا كان موجودًا
                if (saveTimeout) {
                    clearTimeout(saveTimeout);
                }
                
                // تعيين مؤقت جديد لتأخير الحفظ
                saveTimeout = setTimeout(function() {
                    PricingSystem.Session.saveFormData();
                }, 1000); // تأخير لمدة ثانية واحدة
            });
            
            // إضافة مستمع لحدث الإدخال (للحقول النصية والرقمية)
            if (input.type === 'text' || input.type === 'number' || input.tagName === 'TEXTAREA') {
                input.addEventListener('input', function() {
                    // إلغاء المؤقت السابق إذا كان موجودًا
                    if (saveTimeout) {
                        clearTimeout(saveTimeout);
                    }
                    
                    // تعيين مؤقت جديد لتأخير الحفظ
                    saveTimeout = setTimeout(function() {
                        PricingSystem.Session.saveFormData();
                    }, 1500); // تأخير لمدة 1.5 ثانية للإدخال
                });
            }
        });
        
        // حفظ البيانات عند مغادرة الصفحة
        window.addEventListener('beforeunload', function() {
            // إلغاء المؤقت السابق إذا كان موجودًا
            if (saveTimeout) {
                clearTimeout(saveTimeout);
            }
            
            // حفظ البيانات مباشرة
            PricingSystem.Session.saveFormData();
        });
    },
    
    /**
     * مسح بيانات الجلسة
     */
    clearSessionData: function() {
        // إرسال طلب لمسح بيانات الجلسة
        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
        
        fetch('/pricing/clear-session/', {
            method: 'POST',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': csrfToken,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ clear: true })
        }).then(response => {
            if (response.ok) {
                console.log('تم مسح بيانات الجلسة بنجاح');
            } else {
                throw new Error('فشل في مسح بيانات الجلسة');
            }
        }).catch(error => {
            console.error('خطأ في مسح بيانات الجلسة:', error);
        });
    }
}; 

// استدعاء دالة إعداد معالجات الأحداث
document.addEventListener('DOMContentLoaded', function() {
    PricingSystem.Session.setupSessionEventHandlers();
}); 