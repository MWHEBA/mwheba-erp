/**
 * تحسينات JavaScript لقسم المنتجات
 */

// متغيرات عامة
let unpaidProductsCount = 0;
let totalProductsCount = 0;

// تهيئة التحسينات عند تحميل الصفحة
document.addEventListener('DOMContentLoaded', function() {
    initializeProductsEnhancements();
});

function initializeProductsEnhancements() {
    try {
        // حساب عدد المنتجات غير المدفوعة
        countUnpaidProducts();
        
        // تحسين عرض الإشعارات
        enhanceNotifications();
        
        // تحسين أزرار الدفع
        enhancePaymentButtons();
        
        // تحسين checkbox تحديد الكل
        enhanceSelectAllCheckbox();
        
        // إضافة tooltips
        initializeTooltips();
        
    } catch (error) {
        // تسجيل صامت للأخطاء غير الحرجة
        if (error.message && !error.message.includes('storage')) {
            console.error('❌ خطأ في تهيئة تحسينات المنتجات:', error);
        }
    }
}

function countUnpaidProducts() {
    const disabledCheckboxes = document.querySelectorAll('.pending-request-checkbox[disabled]');
    const allCheckboxes = document.querySelectorAll('.pending-request-checkbox');
    
    unpaidProductsCount = disabledCheckboxes.length;
    totalProductsCount = allCheckboxes.length;
    
}

function enhanceNotifications() {
    try {
        if (unpaidProductsCount > 0) {
        }
    } catch (error) {
        console.error('❌ خطأ في تحسين الإشعارات:', error);
    }
}

function enhancePaymentButtons() {
    try {
        // إضافة تأثيرات hover للأزرار
        const paymentButtons = document.querySelectorAll('.btn-table-payment');
        
        if (paymentButtons.length === 0) {
            return;
        }
        
        paymentButtons.forEach(button => {
            // إضافة loading state عند النقر
            button.addEventListener('click', function() {
                const originalContent = this.innerHTML;
                this.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
                this.disabled = true;
                
                // إعادة تفعيل الزر بعد ثانيتين (في حالة عدم انتقال الصفحة)
                setTimeout(() => {
                    this.innerHTML = originalContent;
                    this.disabled = false;
                }, 2000);
            });
            
            // إضافة معلومات إضافية في tooltip
            const title = button.getAttribute('title');
            if (title && !title.includes('المبلغ:')) {
                // محاولة استخراج المبلغ من الصف
                const row = button.closest('tr');
                if (row) {
                    const amountCell = row.querySelector('td:nth-child(4)'); // عمود المبلغ
                    if (amountCell) {
                        const amount = amountCell.textContent.trim();
                        button.setAttribute('title', `${title} - المبلغ: ${amount}`);
                    }
                }
            }
        });
        
    } catch (error) {
        console.error('❌ خطأ في تحسين أزرار الدفع:', error);
    }
}

function enhanceSelectAllCheckbox() {
    try {
        const selectAllCheckbox = document.getElementById('select-all-pending');
        const selectAllLabel = document.querySelector('label[for="select-all-pending"]');
        
        if (!selectAllCheckbox || !selectAllLabel) {
            return;
        }
        
        // تحديث النص ليعكس الوضع الحقيقي
        const enabledCount = document.querySelectorAll('.pending-request-checkbox:not([disabled])').length;
        
        if (enabledCount === 0) {
            selectAllCheckbox.disabled = true;
            selectAllCheckbox.title = 'لا توجد منتجات قابلة للتحديد - جميع المنتجات غير مدفوعة';
            selectAllLabel.innerHTML = `<strong>تحديد الكل (0 من ${totalProductsCount} قابل للتحديد)</strong>`;
            selectAllLabel.style.opacity = '0.6';
        } else if (enabledCount < totalProductsCount) {
            selectAllLabel.innerHTML = `<strong>تحديد الكل (${enabledCount} من ${totalProductsCount} قابل للتحديد)</strong>`;
            
            // إضافة أيقونة تحذير
            if (!selectAllLabel.querySelector('.warning-icon')) {
                const warningIcon = document.createElement('i');
                warningIcon.className = 'fas fa-exclamation-triangle warning-icon ms-2';
                warningIcon.style.color = '#ffc107';
                warningIcon.title = `${unpaidProductsCount} منتج غير مدفوع`;
                selectAllLabel.appendChild(warningIcon);
            }
        }
        
    } catch (error) {
        console.error('❌ خطأ في تحسين checkbox تحديد الكل:', error);
    }
}

function initializeTooltips() {
    try {
        // تهيئة Bootstrap tooltips إذا كان متوفراً
        if (typeof bootstrap !== 'undefined' && bootstrap.Tooltip) {
            const tooltipTriggerList = [].slice.call(document.querySelectorAll('[title]'));
            tooltipTriggerList.forEach(function (tooltipTriggerEl) {
                new bootstrap.Tooltip(tooltipTriggerEl, {
                    placement: 'top',
                    trigger: 'hover'
                });
            });
        }
    } catch (error) {
        // تسجيل صامت
    }
}

// دالة لإظهار رسائل تفاعلية محسنة
function showEnhancedAlert(message, type = 'info', duration = 5000) {
    try {
        // إنشاء container للرسائل إذا لم يكن موجوداً
        let alertContainer = document.getElementById('enhanced-alerts-container');
        if (!alertContainer) {
            alertContainer = document.createElement('div');
            alertContainer.id = 'enhanced-alerts-container';
            alertContainer.style.cssText = `
                position: fixed;
                top: 20px;
                right: 20px;
                z-index: 9999;
                max-width: 400px;
            `;
            document.body.appendChild(alertContainer);
        }
        
        // إنشاء الرسالة
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show shadow-lg`;
        alertDiv.style.cssText = `
            margin-bottom: 10px;
            border-radius: 8px;
            border: none;
            animation: slideInRight 0.3s ease-out;
        `;
        
        const iconMap = {
            'success': 'check-circle',
            'danger': 'exclamation-circle',
            'warning': 'exclamation-triangle',
            'info': 'info-circle'
        };
        
        alertDiv.innerHTML = `
            <i class="fas fa-${iconMap[type] || 'info-circle'} me-2"></i>
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        alertContainer.appendChild(alertDiv);
        
        // إزالة تلقائية
        if (duration > 0) {
            setTimeout(() => {
                if (alertDiv.parentNode) {
                    alertDiv.style.animation = 'slideOutRight 0.3s ease-in';
                    setTimeout(() => alertDiv.remove(), 300);
                }
            }, duration);
        }
    } catch (error) {
        console.error('❌ خطأ في إظهار الرسالة المحسنة:', error);
        // fallback للرسالة العادية
        alert(message);
    }
}

// CSS animations
const style = document.createElement('style');
style.textContent = `
    @keyframes slideInRight {
        from {
            transform: translateX(100%);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
    
    @keyframes slideOutRight {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(100%);
            opacity: 0;
        }
    }
    
    .warning-icon {
        animation: pulse 2s infinite;
    }
    
    @keyframes pulse {
        0% { opacity: 1; }
        50% { opacity: 0.5; }
        100% { opacity: 1; }
    }
`;
document.head.appendChild(style);

// تصدير الدوال للاستخدام العام
window.ProductsEnhancements = {
    showEnhancedAlert,
    countUnpaidProducts,
    enhanceNotifications
};