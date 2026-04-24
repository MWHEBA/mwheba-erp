/**
 * ملف اختبار لتحسينات المنتجات
 */

// اختبار وجود الدوال المطلوبة
document.addEventListener('DOMContentLoaded', function() {
    
    // اختبار وجود الدوال
    const requiredFunctions = [
        'initializeProductsEnhancements',
        'countUnpaidProducts', 
        'enhanceNotifications',
        'showUnpaidProductsNotification',
        'enhancePaymentButtons',
        'enhanceSelectAllCheckbox',
        'initializeTooltips',
        'showEnhancedAlert'
    ];
    
    let allFunctionsExist = true;
    
    requiredFunctions.forEach(funcName => {
        if (typeof window[funcName] === 'function' || typeof eval(funcName) === 'function') {
        } else {
            console.error(`❌ ${funcName} غير موجودة`);
            allFunctionsExist = false;
        }
    });
    
    // اختبار العناصر المطلوبة
    setTimeout(() => {
        const elements = {
            'select-all-pending': document.getElementById('select-all-pending'),
            'pending-request-checkbox': document.querySelectorAll('.pending-request-checkbox'),
            'btn-table-payment': document.querySelectorAll('.btn-table-payment'),
            'bg-light.rounded': document.querySelector('.bg-light.rounded')
        };
        
        Object.keys(elements).forEach(key => {
            const element = elements[key];
            if (element && (element.length > 0 || element.nodeType)) {
            } else {
            }
        });
        
        // اختبار المتغيرات العامة
        if (typeof unpaidProductsCount !== 'undefined') {
        }
        
        if (typeof totalProductsCount !== 'undefined') {
        }
        
    }, 1000);
});

// اختبار دالة الإشعارات
function testEnhancedAlert() {
    if (typeof showEnhancedAlert === 'function') {
        showEnhancedAlert('اختبار الإشعارات يعمل بنجاح!', 'success', 3000);
        return true;
    } else if (typeof window.ProductsEnhancements?.showEnhancedAlert === 'function') {
        window.ProductsEnhancements.showEnhancedAlert('اختبار الإشعارات يعمل بنجاح!', 'success', 3000);
        return true;
    }
    console.error('❌ دالة showEnhancedAlert غير متوفرة');
    return false;
}

// إضافة الدالة للنافذة العامة للاختبار اليدوي
window.testProductsEnhancements = testEnhancedAlert;