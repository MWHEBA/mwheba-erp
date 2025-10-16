/**
 * coating-dynamic.js - التحديث الديناميكي لخدمات التغطية
 */

// إضافة دالة إعداد التحديث الديناميكي لخدمات التغطية
if (typeof PricingSystem !== 'undefined' && PricingSystem.Finishing) {
    
    /**
     * إعداد التحديث الديناميكي لخدمات التغطية
     */
    PricingSystem.Finishing.setupDynamicCoatingServices = function() {
        const coatingSupplierSelect = document.getElementById('coating_supplier');
        const coatingServiceSelect = document.getElementById('coating_service_select');
        const coatingPriceInput = document.getElementById('coating_price');
        const coatingTotalInput = document.getElementById('coating_total');
        const coatingSidesSelect = document.getElementById('coating_sides');

        if (!coatingSupplierSelect || !coatingServiceSelect || !coatingPriceInput) {
            console.log('عناصر خدمة التغطية غير موجودة');
            return;
        }

        console.log('تم إعداد التحديث الديناميكي لخدمات التغطية');

        // عند تغيير المورد، جلب الخدمات المتاحة
        coatingSupplierSelect.addEventListener('change', function() {
            const supplierId = this.value;
            
            // مسح الخدمات الحالية
            coatingServiceSelect.innerHTML = '<option value="">-- اختر نوع التغطية --</option>';
            coatingPriceInput.value = '';
            if (coatingTotalInput) coatingTotalInput.value = '';

            if (!supplierId) return;

            console.log('جلب خدمات التغطية للمورد:', supplierId);

            // جلب خدمات التغطية للمورد المحدد
            fetch(`/pricing/api/coating-services-by-supplier/?supplier_id=${supplierId}`)
                .then(response => {
                    console.log('استجابة الخادم:', response.status);
                    return response.json();
                })
                .then(data => {
                    console.log('بيانات الاستجابة:', data);
                    if (data.success && data.services) {
                        console.log('تم جلب', data.services.length, 'خدمة تغطية');
                        data.services.forEach(service => {
                            const option = document.createElement('option');
                            option.value = service.id;
                            option.textContent = service.name;
                            option.dataset.price = service.price_per_unit;
                            option.dataset.calculationMethod = service.calculation_method;
                            option.dataset.finishingType = service.finishing_type;
                            coatingServiceSelect.appendChild(option);
                            console.log('تمت إضافة خدمة:', service.name);
                        });
                    } else {
                        console.error('فشل في جلب خدمات التغطية:', data.error || 'لا توجد خدمات');
                    }
                })
                .catch(error => {
                    console.error('خطأ في جلب خدمات التغطية:', error);
                });
        });

        // عند تغيير نوع الخدمة، جلب السعر وحساب الإجمالي
        coatingServiceSelect.addEventListener('change', function() {
            const serviceId = this.value;
            
            coatingPriceInput.value = '';
            if (coatingTotalInput) coatingTotalInput.value = '';

            if (!serviceId) return;

            console.log('جلب سعر خدمة التغطية:', serviceId);

            // جلب سعر الخدمة
            const quantity = PricingSystem.Finishing.getQuantityForCoating();
            
            fetch(`/pricing/api/coating-service-price/?service_id=${serviceId}&quantity=${quantity}`)
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        coatingPriceInput.value = data.price_per_unit;
                        console.log('تم تحديث سعر التغطية:', data.price_per_unit);
                        
                        // حساب الإجمالي
                        PricingSystem.Finishing.calculateCoatingTotal();
                    } else {
                        console.error('فشل في جلب سعر الخدمة:', data.error);
                    }
                })
                .catch(error => {
                    console.error('خطأ في جلب سعر الخدمة:', error);
                });
        });

        // عند تغيير عدد الأوجه، إعادة حساب الإجمالي
        if (coatingSidesSelect) {
            coatingSidesSelect.addEventListener('change', () => {
                PricingSystem.Finishing.calculateCoatingTotal();
            });
        }

        // عند تغيير السعر يدوياً، إعادة حساب الإجمالي
        coatingPriceInput.addEventListener('input', () => {
            PricingSystem.Finishing.calculateCoatingTotal();
        });
    };

    /**
     * حساب إجمالي تكلفة التغطية
     */
    PricingSystem.Finishing.calculateCoatingTotal = function() {
        const coatingPriceInput = document.getElementById('coating_price');
        const coatingTotalInput = document.getElementById('coating_total');
        const coatingSidesSelect = document.getElementById('coating_sides');
        
        if (!coatingPriceInput || !coatingTotalInput) return;

        const pricePerUnit = parseFloat(coatingPriceInput.value) || 0;
        const sides = parseInt(coatingSidesSelect?.value || 1);
        const quantity = this.getQuantityForCoating();
        
        // حساب الإجمالي (السعر × الكمية × عدد الأوجه)
        const total = pricePerUnit * quantity * sides;
        
        coatingTotalInput.value = total.toFixed(2);
        
        console.log(`تم حساب إجمالي التغطية: ${total.toFixed(2)} (${pricePerUnit} × ${quantity} × ${sides})`);
        
        // تحديث التكلفة الإجمالية لخدمات ما بعد الطباعة
        if (typeof this.calculateTotalFinishingCost === 'function') {
            this.calculateTotalFinishingCost();
        }
    };

    /**
     * الحصول على الكمية المناسبة لحساب تكلفة التغطية
     */
    PricingSystem.Finishing.getQuantityForCoating = function() {
        // محاولة الحصول على عدد أفرخ الورق أولاً
        const paperSheetsInput = document.getElementById('id_paper_sheets_count');
        if (paperSheetsInput && paperSheetsInput.value) {
            return parseInt(paperSheetsInput.value) || 1;
        }
        
        // إذا لم يتوفر، استخدم الكمية العامة
        const quantityInput = document.getElementById('id_quantity');
        if (quantityInput && quantityInput.value) {
            return parseInt(quantityInput.value) || 1;
        }
        
        // القيمة الافتراضية
        return 1;
    };
}

// تهيئة الخدمة عند تحميل الصفحة
document.addEventListener('DOMContentLoaded', function() {
    if (typeof PricingSystem !== 'undefined' && 
        PricingSystem.Finishing && 
        typeof PricingSystem.Finishing.setupDynamicCoatingServices === 'function') {
        
        // تأخير قصير للتأكد من تحميل جميع العناصر
        setTimeout(() => {
            PricingSystem.Finishing.setupDynamicCoatingServices();
        }, 500);
    }
});
