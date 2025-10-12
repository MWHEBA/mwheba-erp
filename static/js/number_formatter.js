/**
 * تنسيق الأرقام بالشكل المطلوب:
 * - علامة عشرية واحدة فقط إذا كانت هناك كسور
 * - بدون علامة عشرية إذا كان العدد صحيح
 * - فاصلة لكل ألف
 * 
 * @param {number|string} value القيمة المراد تنسيقها
 * @returns {string} القيمة بعد التنسيق
 */
function formatNumber(value) {
    if (value === null || value === undefined || value === '') {
        return '0';
    }
    
    // تحويل القيمة إلى رقم
    let number = parseFloat(value);
    if (isNaN(number)) {
        return value;
    }
    
    // تقريب القيمة إلى رقمين عشريين
    number = Math.round(number * 100) / 100;
    
    // إذا كانت القيمة عدد صحيح، نعرضها بدون علامة عشرية
    if (number === Math.floor(number)) {
        return number.toLocaleString('en-US');
    } else {
        // تنسيق الرقم بعلامة عشرية واحدة فقط
        return number.toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
    }
}

/**
 * تحويل السعر أو المبلغ المالي إلى نص منسق
 * 
 * @param {number|string} value القيمة المراد تنسيقها
 * @param {string} currency عملة التنسيق (افتراضي: ج.م)
 * @returns {string} القيمة المنسقة مع العملة
 */
function formatCurrency(value, currency = 'ج.م') {
    return formatNumber(value) + ' ' + currency;
}

// تصدير الدوال إذا كانت بيئة ES modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        formatNumber,
        formatCurrency
    };
} 