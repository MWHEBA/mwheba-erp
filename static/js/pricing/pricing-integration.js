/**
 * pricing-integration.js - ربط Frontend مع Backend الجديد
 */

// تعريف كائن عام للمشروع إذا لم يكن موجودًا
window.PricingSystem = window.PricingSystem || {};

// تعريف وحدة التكامل
const PricingIntegration = {
    // متغير لتتبع حالة التحميل الأولي
    isInitialLoading: true,
    
    /**
     * تهيئة وحدة التكامل
     */
    init: function() {
        this.setupEventListeners();
        this.loadInitialData();
        
        // إنهاء حالة التحميل الأولي بعد ثانيتين
        setTimeout(() => {
            this.isInitialLoading = false;
        }, 2000);
    },
    
    /**
     * إعداد معالجات الأحداث
     */
    setupEventListeners: function() {
        // معالج تغيير نوع الطلب
        const orderTypeSelect = document.getElementById('id_order_type');
        if (orderTypeSelect) {
            orderTypeSelect.addEventListener('change', () => {
                this.handleOrderTypeChange();
            });
        }
        
        // معالج تغيير المورد
        const supplierSelect = document.getElementById('id_supplier');
        if (supplierSelect) {
            supplierSelect.addEventListener('change', () => {
                this.handleSupplierChange();
            });
        }
        
        // معالج تغيير نوع الورق
        const paperTypeSelect = document.getElementById('id_paper_type');
        if (paperTypeSelect) {
            paperTypeSelect.addEventListener('change', () => {
                this.handlePaperTypeChange();
            });
        }
        
        // معالج تغيير مقاس الورق
        const paperSizeSelect = document.getElementById('id_product_size');
        if (paperSizeSelect) {
            paperSizeSelect.addEventListener('change', () => {
                this.handlePaperSizeChange();
            });
        }
        
        // معالج تغيير وزن الورق
        const paperWeightSelect = document.getElementById('id_paper_weight');
        if (paperWeightSelect) {
            paperWeightSelect.addEventListener('change', () => {
                this.handlePaperWeightChange();
            });
        }
        
        // معالج تغيير الكمية
        const quantityInput = document.getElementById('id_quantity');
        if (quantityInput) {
            quantityInput.addEventListener('input', this.debounce(() => {
                this.calculateTotalCost();
            }, 500));
        }
        
        // زر حساب التكلفة
        const calculateButton = document.getElementById('calculate-cost-btn');
        if (calculateButton) {
            calculateButton.addEventListener('click', () => {
                this.calculateTotalCost(true); // عرض رسالة النجاح عند الضغط على الزر
            });
        }
    },
    
    /**
     * تحميل البيانات الأولية
     */
    async loadInitialData() {
        try {
            // تحميل أنواع الورق
            await this.loadPaperTypes();
            
            // تحميل مقاسات الورق
            await this.loadPaperSizes();
            
            // تحميل الموردين
            await this.loadSuppliers();
            
        } catch (error) {
            console.error('خطأ في تحميل البيانات الأولية:', error);
        }
    },
    
    /**
     * تحميل أنواع الورق
     */
    async loadPaperTypes() {
        try {
            const result = await PricingSystem.API.getPaperTypes();
            
            if (result.success) {
                const select = document.getElementById('id_paper_type');
                if (select) {
                    this.populateSelect(select, result.paper_types, 'id', 'name');
                }
            }
        } catch (error) {
            console.error('خطأ في تحميل أنواع الورق:', error);
        }
    },
    
    /**
     * تحميل مقاسات الورق
     */
    async loadPaperSizes() {
        try {
            const result = await PricingSystem.API.getPaperSizes();
            
            if (result.success) {
                const select = document.getElementById('id_product_size');
                if (select) {
                    this.populatePaperSizeSelect(select, result.paper_sizes);
                }
            }
        } catch (error) {
            console.error('خطأ في تحميل مقاسات الورق:', error);
        }
    },
    
    /**
     * تحميل الموردين
     */
    async loadSuppliers() {
        try {
            const result = await PricingSystem.API.getSuppliers();
            
            if (result.success) {
                const select = document.getElementById('id_supplier');
                if (select) {
                    this.populateSelect(select, result.suppliers, 'id', 'name');
                }
            }
        } catch (error) {
            console.error('خطأ في تحميل الموردين:', error);
        }
    },
    
    /**
     * ملء قائمة منسدلة بالبيانات
     */
    populateSelect: function(selectElement, data, valueField, textField) {
        // الاحتفاظ بالخيار الأول
        const firstOption = selectElement.querySelector('option:first-child');
        selectElement.innerHTML = '';
        
        if (firstOption) {
            selectElement.appendChild(firstOption);
        }
        
        // إضافة الخيارات الجديدة
        data.forEach(item => {
            const option = document.createElement('option');
            option.value = item[valueField];
            option.textContent = item[textField];
            selectElement.appendChild(option);
        });
    },
    
    /**
     * ملء قائمة مقاسات الورق مع الأبعاد
     */
    populatePaperSizeSelect: function(selectElement, paperSizes) {
        // الاحتفاظ بالخيار الأول
        const firstOption = selectElement.querySelector('option:first-child');
        selectElement.innerHTML = '';
        
        if (firstOption) {
            selectElement.appendChild(firstOption);
        }
        
        // إضافة الخيارات الجديدة مع الأبعاد
        paperSizes.forEach(size => {
            const option = document.createElement('option');
            option.value = size.id;
            // إزالة الأصفار الزائدة من الأبعاد
            const width = parseFloat(size.width).toString();
            const height = parseFloat(size.height).toString();
            option.textContent = `${size.name} (${width}×${height})`;
            selectElement.appendChild(option);
        });
        
        // إضافة خيار "مقاس مخصص" في النهاية
        const customOption = document.createElement('option');
        customOption.value = 'custom';
        customOption.textContent = 'مقاس مخصص';
        selectElement.appendChild(customOption);
    },
    
    /**
     * معالج تغيير نوع الطلب
     */
    handleOrderTypeChange: function() {
        this.calculateTotalCost();
    },
    
    /**
     * معالج تغيير المورد
     */
    async handleSupplierChange() {

        // تحديث أسعار الورق
        await this.updatePaperPrice();
        
        // إعادة حساب التكلفة
        this.calculateTotalCost();
    },
    
    /**
     * معالج تغيير نوع الورق
     */
    async handlePaperTypeChange() {

        // تحديث أسعار الورق
        await this.updatePaperPrice();
        
        // إعادة حساب التكلفة
        this.calculateTotalCost();
    },
    
    /**
     * معالج تغيير مقاس الورق
     */
    async handlePaperSizeChange() {
        
        // تحديث أسعار الورق
        await this.updatePaperPrice();
        
        // إعادة حساب التكلفة
        this.calculateTotalCost();
    },
    
    /**
     * معالج تغيير وزن الورق
     */
    async handlePaperWeightChange() {        
        // تحديث أسعار الورق
        await this.updatePaperPrice();
        
        // إعادة حساب التكلفة
        this.calculateTotalCost();
    },
    
    /**
     * تحديث سعر الورق
     */
    async updatePaperPrice() {
        try {
            const supplierElement = document.getElementById('id_supplier');
            const paperTypeElement = document.getElementById('id_paper_type');
            const paperSizeElement = document.getElementById('id_product_size');
            const paperWeightElement = document.getElementById('id_paper_weight');
            
            if (!supplierElement?.value || !paperTypeElement?.value || !paperSizeElement?.value) {
                return;
            }
            
            const result = await PricingSystem.API.getPaperPrice(
                supplierElement.value,
                paperTypeElement.value,
                paperSizeElement.value,
                paperWeightElement?.value || 80
            );
            
            if (result.success) {
                // تحديث حقل سعر الورق
                const paperPriceField = document.getElementById('id_paper_price');
                if (paperPriceField) {
                    paperPriceField.value = result.price_per_sheet.toFixed(4);
                }
                
                // عرض معلومات إضافية
                this.showPaperPriceInfo(result);
            }
        } catch (error) {
            console.error('خطأ في تحديث سعر الورق:', error);
        }
    },
    
    /**
     * عرض معلومات سعر الورق
     */
    showPaperPriceInfo: function(priceData) {
        const infoElement = document.getElementById('paper-price-info');
        if (infoElement) {
            infoElement.innerHTML = `
                <small class="text-muted">
                    <i class="fas fa-info-circle"></i>
                    سعر الورقة: ${priceData.price_per_sheet.toFixed(4)} ريال
                    | نوع الورقة: ${priceData.sheet_type}
                    | المنشأ: ${priceData.origin}
                </small>
            `;
        }
    },
    
    /**
     * حساب التكلفة الإجمالية
     * @param {boolean} showSuccessMessage - هل تريد عرض رسالة النجاح (افتراضي: false)
     */
    async calculateTotalCost(showSuccessMessage = false) {
        try {
            // تجنب الحسابات أثناء التحميل الأولي
            if (this.isInitialLoading) {
                return;
            }
            
            // جمع بيانات الطلب
            const orderData = this.collectOrderData();
            
            if (!orderData) {
                // لا تظهر تحذير إذا كانت البيانات غير مكتملة أثناء التحميل
                return;
            }
            
            // عرض مؤشر التحميل
            this.showLoadingIndicator(true);
            
            // استدعاء API الحساب
            const result = await PricingSystem.API.calculateTotalCost(orderData);
            
            if (result.success) {
                this.updateCostFields(result);
                // عرض رسالة النجاح فقط إذا طُلب ذلك صراحة
                if (showSuccessMessage) {
                    this.showSuccessMessage('تم حساب التكلفة بنجاح');
                }
            } else {
                this.showErrorMessage(result.error);
            }
        } catch (error) {
            console.error('خطأ في حساب التكلفة:', error);
            this.showErrorMessage('حدث خطأ أثناء حساب التكلفة');
        } finally {
            this.showLoadingIndicator(false);
        }
    },
    
    /**
     * جمع بيانات الطلب
     */
    collectOrderData: function() {
        try {
            const orderTypeElement = document.getElementById('id_order_type');
            const quantityElement = document.getElementById('id_quantity');
            const paperTypeElement = document.getElementById('id_paper_type');
            const paperSizeElement = document.getElementById('id_product_size');
            const paperWeightElement = document.getElementById('id_paper_weight');
            const supplierElement = document.getElementById('id_supplier');
            const colorsFrontElement = document.getElementById('id_colors_front');
            const colorsBackElement = document.getElementById('id_colors_back');
            
            // التحقق من وجود العناصر المطلوبة (فقط إذا كانت موجودة في الصفحة)
            if (!orderTypeElement || !quantityElement || !paperTypeElement || !paperSizeElement) {
                return null; // العناصر غير موجودة في الصفحة
            }
            
            // التحقق من وجود القيم الأساسية (مع تنظيف القيم)
            const orderTypeValue = orderTypeElement.value && orderTypeElement.value.trim();
            const quantityValue = quantityElement.value && quantityElement.value.trim();
            const paperTypeValueCheck = paperTypeElement.value && paperTypeElement.value.trim();
            const paperSizeValueCheck = paperSizeElement.value && paperSizeElement.value.trim();
            
            if (!orderTypeValue || !quantityValue || !paperTypeValueCheck || !paperSizeValueCheck) {
                return null; // البيانات غير مكتملة
            }
            
            // التحقق من صحة القيم قبل الإرسال
            const productSizeValue = paperSizeElement.value && paperSizeElement.value.trim() ? paperSizeElement.value.trim() : null;
            const paperTypeValue = paperTypeElement.value && paperTypeElement.value.trim() ? paperTypeElement.value.trim() : null;
            const supplierValue = supplierElement && supplierElement.value && supplierElement.value.trim() ? supplierElement.value.trim() : null;
            
            return {
                order_type: orderTypeElement.value,
                quantity: parseInt(quantityElement.value) || 0,
                paper_type: paperTypeValue,
                product_size: productSizeValue, // قيمة آمنة ومنظفة
                paper_weight: paperWeightElement ? parseInt(paperWeightElement.value) || 80 : 80,
                supplier: supplierValue,
                colors_front: colorsFrontElement ? parseInt(colorsFrontElement.value) || 4 : 4,
                colors_back: colorsBackElement ? parseInt(colorsBackElement.value) || 0 : 0
            };
        } catch (error) {
            console.error('خطأ في جمع بيانات الطلب:', error);
            return null;
        }
    },
    
    /**
     * تحديث حقول التكلفة
     */
    updateCostFields: function(result) {
        // تحديث حقول التكلفة
        this.updateFieldValue('id_material_cost', result.material_cost);
        this.updateFieldValue('id_printing_cost', result.printing_cost);
        this.updateFieldValue('id_plates_cost', result.plates_cost);
        this.updateFieldValue('id_finishing_cost', result.finishing_cost);
        this.updateFieldValue('id_total_cost', result.total_cost);
        this.updateFieldValue('id_sale_price', result.sale_price);
        
        // حساب سعر الوحدة
        const quantity = parseInt(document.getElementById('id_quantity')?.value) || 1;
        const unitPrice = result.sale_price / quantity;
        this.updateFieldValue('unit_price', unitPrice);
    },
    
    /**
     * تحديث قيمة حقل معين
     */
    updateFieldValue: function(fieldId, value) {
        const field = document.getElementById(fieldId);
        if (field) {
            field.value = parseFloat(value).toFixed(2);
            
            // إضافة تأثير بصري
            field.classList.add('updated');
            setTimeout(() => {
                field.classList.remove('updated');
            }, 1000);
        }
    },
    
    /**
     * عرض مؤشر التحميل
     */
    showLoadingIndicator: function(show) {
        const indicator = document.getElementById('loading-indicator');
        const calculateButton = document.getElementById('calculate-cost-btn');
        
        if (show) {
            if (indicator) indicator.style.display = 'block';
            if (calculateButton) {
                calculateButton.disabled = true;
                calculateButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> جاري الحساب...';
            }
        } else {
            if (indicator) indicator.style.display = 'none';
            if (calculateButton) {
                calculateButton.disabled = false;
                calculateButton.innerHTML = '<i class="fas fa-calculator"></i> احسب التكلفة';
            }
        }
    },
    
    /**
     * عرض رسالة نجاح
     */
    showSuccessMessage: function(message) {
        if (typeof Swal !== 'undefined') {
            Swal.fire({
                icon: 'success',
                title: 'نجح!',
                text: message,
                timer: 2000,
                showConfirmButton: false
            });
        } else {
            // عرض تنبيه بسيط
            this.showSimpleAlert(message, 'success');
        }
    },
    
    /**
     * عرض رسالة خطأ
     */
    showErrorMessage: function(message) {
        if (typeof Swal !== 'undefined') {
            Swal.fire({
                icon: 'error',
                title: 'خطأ!',
                text: message
            });
        } else {
            // عرض تنبيه بسيط
            this.showSimpleAlert(message, 'error');
        }
    },
    
    /**
     * عرض تنبيه بسيط
     */
    showSimpleAlert: function(message, type) {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type === 'success' ? 'success' : 'danger'} alert-dismissible fade show`;
        alertDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        // إضافة التنبيه في أعلى النموذج
        const form = document.querySelector('form');
        if (form) {
            form.insertBefore(alertDiv, form.firstChild);
            
            // إزالة التنبيه بعد 5 ثوان
            setTimeout(() => {
                alertDiv.remove();
            }, 5000);
        }
    },
    
    /**
     * دالة debounce لتأخير التنفيذ
     */
    debounce: function(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }
};

// ربط وحدة التكامل بـ PricingSystem
PricingSystem.Integration = PricingIntegration;

// تهيئة وحدة التكامل عند تحميل الصفحة
document.addEventListener('DOMContentLoaded', function() {
    // التأكد من وجود PricingSystem.API
    if (PricingSystem.API) {
        PricingIntegration.init();
    } else {
        console.error('PricingSystem.API غير متوفر');
    }
});
