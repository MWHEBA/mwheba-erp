/**
 * إصلاح مؤقت لربط id_order_type مع تحميل المكابس
 */

// دالة محسنة لتحميل المكابس مع دعم order_type
function loadPressesWithOrderType(supplierId) {
    if (!supplierId) {
        return;
    }
    
    // الحصول على عناصر DOM
    var pressSelect = document.getElementById('press_selector');
    var orderTypeSelect = document.getElementById('id_order_type');
    var hiddenInput = document.getElementById('id_press');
    var pressPriceInput = document.getElementById('id_press_price_per_1000');
    
    if (!pressSelect) {
        return;
    }
    
    // الحصول على نوع الطلب
    var orderType = orderTypeSelect ? orderTypeSelect.value : '';
    
    // تعطيل القائمة أثناء التحميل
    pressSelect.disabled = true;
    pressSelect.innerHTML = '<option value="">-- جاري تحميل الماكينات... --</option>';
    
    // مسح القيم السابقة
    if (pressPriceInput) pressPriceInput.value = '';
    if (hiddenInput) hiddenInput.value = '';
    
    // بناء URL
    var apiUrl = "/pricing/api/presses/?supplier_id=" + supplierId;
    if (orderType) {
        apiUrl += "&order_type=" + encodeURIComponent(orderType);
    }
    
    console.log('تحميل المكابس:', { supplierId: supplierId, orderType: orderType, url: apiUrl });
    
    // استدعاء API
    fetch(apiUrl)
        .then(function(response) {
            if (!response.ok) {
                throw new Error("خطأ في استجابة الخادم: " + response.status);
            }
            return response.json();
        })
        .then(function(data) {
            pressSelect.disabled = false;
            
            var html = '<option value="">-- اختر ماكينة الطباعة --</option>';
            
            if (data && data.success && Array.isArray(data.presses) && data.presses.length > 0) {
                data.presses.forEach(function(press) {
                    if (press && press.id) {
                        var name = press.name || "ماكينة " + press.id;
                        var price = press.price_per_1000 || press.unit_price || '';
                        
                        html += '<option value="' + press.id + '" data-price="' + price + '">' + name + '</option>';
                    }
                });
                
                console.log('تم تحميل ' + data.presses.length + ' ماكينة');
            } else {
                html = '<option value="">-- لا توجد ماكينات متاحة --</option>';
                console.log('لا توجد مكابس متاحة');
            }
            
            pressSelect.innerHTML = html;
        })
        .catch(function(error) {
            console.error('خطأ في تحميل المكابس:', error);
            pressSelect.disabled = false;
            pressSelect.innerHTML = '<option value="">-- خطأ في تحميل الماكينات --</option>';
        });
}

// ربط الأحداث عند تحميل الصفحة
document.addEventListener('DOMContentLoaded', function() {
    var supplierSelect = document.getElementById('id_supplier');
    var orderTypeSelect = document.getElementById('id_order_type');
    
    // معالج تغيير المورد
    if (supplierSelect) {
        supplierSelect.addEventListener('change', function() {
            if (this.value) {
                loadPressesWithOrderType(this.value);
            } else {
                var pressSelect = document.getElementById('press_selector');
                if (pressSelect) {
                    pressSelect.innerHTML = '<option value="">-- اختر ماكينة الطباعة --</option>';
                }
            }
        });
    }
    
    // معالج تغيير نوع الطلب
    if (orderTypeSelect) {
        orderTypeSelect.addEventListener('change', function() {
            if (supplierSelect && supplierSelect.value) {
                loadPressesWithOrderType(supplierSelect.value);
            }
        });
    }
    
    // تحميل أولي إذا كان المورد محدد مسبقاً
    if (supplierSelect && supplierSelect.value) {
        setTimeout(function() {
            loadPressesWithOrderType(supplierSelect.value);
        }, 500);
    }
});

// إعادة تعريف الدالة العامة للتوافق مع الكود القديم
window.loadPressesDirectly = function(supplierId) {
    loadPressesWithOrderType(supplierId);
};
