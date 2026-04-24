/**
 * Products Error Handler
 * معالج أخطاء صفحة المنتجات
 */

(function() {
    'use strict';

    // معالج أخطاء خاص بصفحة المنتجات
    function handleProductsErrors() {
        // معالجة أخطاء أزرار التسليم
        document.addEventListener('click', function(e) {
            const deliverBtn = e.target.closest('.deliver-single-btn');
            if (deliverBtn) {
                try {
                    // التحقق من وجود البيانات المطلوبة
                    const requestId = deliverBtn.dataset.requestId;
                    const productName = deliverBtn.dataset.productName;
                    
                    if (!requestId) {
                        console.error('Request ID not found on deliver button');
                        showAlert('خطأ: لا يمكن العثور على معرف الطلب', 'danger');
                        return;
                    }
                    
                    if (!productName) {
                        console.error('Product name not found on deliver button');
                        showAlert('خطأ: لا يمكن العثور على اسم المنتج', 'danger');
                        return;
                    }
                    
                    // التحقق من وجود دالة التسليم
                    if (typeof deliverSingleProduct === 'function') {
                        deliverSingleProduct(requestId, productName);
                    } else {
                        console.error('deliverSingleProduct function not found');
                        showAlert('خطأ: وظيفة التسليم غير متوفرة', 'danger');
                    }
                } catch (error) {
                    console.error('Error in deliver button click handler:', error);
                    showAlert('حدث خطأ في معالجة طلب التسليم', 'danger');
                }
            }
        });

        // معالجة أخطاء تحديد المنتجات
        document.addEventListener('change', function(e) {
            if (e.target.id === 'product_id') {
                try {
                    // التحقق من وجود دالة تحديث السعر
                    if (typeof updateTotalPrice === 'function') {
                        updateTotalPrice();
                    } else {
                        console.warn('updateTotalPrice function not found');
                    }
                } catch (error) {
                    console.error('Error in product selection:', error);
                    // لا نعرض تنبيه للمستخدم هنا لأنه قد يكون مزعج
                }
            }
        });

        // معالجة أخطاء النماذج
        document.addEventListener('submit', function(e) {
            const form = e.target;
            
            if (form.id === 'additional-product-form') {
                try {
                    // التحقق من البيانات المطلوبة
                    const productSelect = form.querySelector('#product_id');
                    const quantityInput = form.querySelector('#quantity');
                    
                    if (!productSelect || !productSelect.value) {
                        e.preventDefault();
                        showAlert('يرجى اختيار منتج', 'warning');
                        return;
                    }
                    
                    if (!quantityInput || !quantityInput.value || quantityInput.value <= 0) {
                        e.preventDefault();
                        showAlert('يرجى إدخال كمية صحيحة', 'warning');
                        return;
                    }
                    
                    // التحقق من المخزون
                    const selectedOption = productSelect.options[productSelect.selectedIndex];
                    if (selectedOption) {
                        const stock = parseInt(selectedOption.dataset.stock || 0);
                        const quantity = parseInt(quantityInput.value);
                        
                        if (quantity > stock) {
                            e.preventDefault();
                            showAlert(`الكمية المطلوبة (${quantity}) أكبر من المخزون المتاح (${stock})`, 'warning');
                            return;
                        }
                    }
                } catch (error) {
                    console.error('Error in form validation:', error);
                    e.preventDefault();
                    showAlert('حدث خطأ في التحقق من البيانات', 'danger');
                }
            }
        });
    }

    // دالة مساعدة لعرض التنبيهات
    function showAlert(message, type = 'info', duration = 5000) {
        try {
            // استخدام toastr إذا كان متاحاً
            if (typeof toastr !== 'undefined') {
                if (type === 'success') toastr.success(message);
                else if (type === 'error' || type === 'danger') toastr.error(message);
                else if (type === 'warning') toastr.warning(message);
                else toastr.info(message);
                return;
            }
            
            // البحث عن مكان لعرض التنبيه
            let alertsContainer = document.querySelector('.alerts-container');
            if (!alertsContainer) {
                alertsContainer = document.querySelector('.container-fluid');
            }
            if (!alertsContainer) {
                alertsContainer = document.body;
            }
            
            if (alertsContainer) {
                const alertDiv = document.createElement('div');
                alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
                alertDiv.setAttribute('role', 'alert');
                
                const iconMap = {
                    'success': 'check-circle',
                    'danger': 'exclamation-circle',
                    'warning': 'exclamation-triangle',
                    'info': 'info-circle'
                };
                
                const icon = iconMap[type] || 'info-circle';
                
                alertDiv.innerHTML = `
                    <i class="fas fa-${icon} me-2" aria-hidden="true"></i>
                    ${message}
                    <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="إغلاق التنبيه"></button>
                `;
                
                alertsContainer.insertBefore(alertDiv, alertsContainer.firstChild);
                
                // إخفاء تلقائي بعد المدة المحددة
                if (duration > 0) {
                    setTimeout(() => {
                        if (alertDiv.parentNode) {
                            alertDiv.remove();
                        }
                    }, duration);
                }
            } else {
                // fallback إلى console إذا لم نجد مكان لعرض التنبيه
                console.warn('Alert container not found, message:', message);
            }
        } catch (error) {
            console.error('Error showing alert:', error);
            console.warn('Alert message:', message);
        }
    }

    // تصدير الدالة للاستخدام العام
    window.showAlert = showAlert;

    // تهيئة معالج الأخطاء عند تحميل الصفحة
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', handleProductsErrors);
    } else {
        handleProductsErrors();
    }

})();
