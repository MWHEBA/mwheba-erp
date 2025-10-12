/**
 * تصفية الموردين بناءً على نوع الطلب
 */

// دالة تحديث موردي الطباعة بناءً على نوع الطلب
function updatePrintingSuppliers() {
    const orderTypeSelect = document.getElementById('id_order_type');
    const supplierSelect = document.getElementById('id_supplier');
    
    if (!orderTypeSelect || !supplierSelect) {
        return;
    }
    
    const orderType = orderTypeSelect.value;
        
    // إنشاء URL للـ API
    let apiUrl = '/pricing/api/printing-suppliers/';
    if (orderType) {
        apiUrl += `?order_type=${encodeURIComponent(orderType)}`;
    }
        
    // تعطيل القائمة أثناء التحميل
    supplierSelect.disabled = true;
    supplierSelect.innerHTML = '<option value="">-- جاري التحميل... --</option>';
    
    // استدعاء API
    fetch(apiUrl)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            supplierSelect.disabled = false;
            
            let html = '<option value="">-- اختر المطبعة --</option>';
            
            if (data.success && data.suppliers && data.suppliers.length > 0) {
                data.suppliers.forEach(supplier => {
                    html += `<option value="${supplier.id}">${supplier.name}</option>`;
                });
                
            } else {
                html = '<option value="">-- لا توجد مطابع متاحة --</option>';
            }
            
            supplierSelect.innerHTML = html;
            
            // مسح اختيار الماكينة عند تغيير المورد
            const pressSelector = document.getElementById('press_selector');
            if (pressSelector) {
                pressSelector.innerHTML = '<option value="">-- اختر ماكينة الطباعة --</option>';
            }
        })
        .catch(error => {
            console.error('خطأ في تحميل موردي الطباعة:', error);
            supplierSelect.disabled = false;
            
            // في حالة الخطأ، الاحتفاظ بالموردين الموجودين
            if (supplierSelect.options.length <= 1) {
                supplierSelect.innerHTML = '<option value="">-- خطأ في التحميل --</option>';
            }
        });
}

// دالة تحديث موردي الزنكات CTP
function updateCtpSuppliers() {
    const ctpSupplierSelect = document.getElementById('id_ctp_supplier');
    
    if (!ctpSupplierSelect) {
        return;
    }
    
    
    // تعطيل القائمة أثناء التحميل
    ctpSupplierSelect.disabled = true;
    ctpSupplierSelect.innerHTML = '<option value="">-- جاري التحميل... --</option>';
    
    // استدعاء API
    fetch('/pricing/api/ctp-suppliers/')
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            ctpSupplierSelect.disabled = false;
            
            let html = '<option value="">-- اختر المورد --</option>';
            
            if (data.success && data.suppliers && data.suppliers.length > 0) {
                data.suppliers.forEach(supplier => {
                    html += `<option value="${supplier.id}">${supplier.name}</option>`;
                });
                
            } else {
                html = '<option value="">-- لا توجد موردين متاحين --</option>';
            }
            
            ctpSupplierSelect.innerHTML = html;
        })
        .catch(error => {
            console.error('خطأ في تحميل موردي الزنكات:', error);
            ctpSupplierSelect.disabled = false;
            
            // في حالة الخطأ، الاحتفاظ بالموردين الموجودين
            if (ctpSupplierSelect.options.length <= 1) {
                ctpSupplierSelect.innerHTML = '<option value="">-- خطأ في التحميل --</option>';
            }
        });
}

// ربط الأحداث عند تحميل الصفحة
document.addEventListener('DOMContentLoaded', function() {
    const orderTypeSelect = document.getElementById('id_order_type');
    
    // معالج تغيير نوع الطلب فقط (الموردين الآن صحيحين من البداية)
    if (orderTypeSelect) {
        orderTypeSelect.addEventListener('change', function() {
            updatePrintingSuppliers();
        });
    }
    
});
