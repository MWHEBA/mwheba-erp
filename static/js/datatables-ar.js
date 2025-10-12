/**
 * ملف تعريف اللغة العربية لـ DataTables
 */

// تعريف اللغة العربية كمتغير عالمي
const dataTablesArabicLanguage = {
    "sProcessing": "جارٍ التحميل...",
    "sLengthMenu": "أظهر _MENU_ مدخلات",
    "sZeroRecords": "لم يعثر على أية سجلات",
    "sInfo": "إظهار _START_ إلى _END_ من أصل _TOTAL_ مدخل",
    "sInfoEmpty": "يعرض 0 إلى 0 من أصل 0 سجل",
    "sInfoFiltered": "(منتقاة من مجموع _MAX_ مُدخل)",
    "sInfoPostFix": "",
    "sSearch": "ابحث:",
    "sUrl": "",
    "oPaginate": {
        "sFirst": "الأول",
        "sPrevious": "السابق",
        "sNext": "التالي",
        "sLast": "الأخير"
    }
};

// تعريف اللغة في كائن DataTables مباشرة (لدعم الإصدارات القديمة)
if (typeof $.fn.dataTable !== 'undefined') {
    $.extend(true, $.fn.dataTable.defaults, {
        language: dataTablesArabicLanguage
    });
}

// دالة مساعدة لتهيئة DataTables بتعريف اللغة العربية
function initDataTableArabic(selector, options = {}) {
    const defaultOptions = {
        language: dataTablesArabicLanguage,
        pageLength: 25,
        responsive: true,
        // إضافة تنسيق الأرقام افتراضيًا
        columnDefs: [
            {
                // تطبيق على أعمدة الأرقام
                targets: '_all',
                render: function(data, type, row) {
                    // استخدام تنسيق الأرقام فقط للعرض وليس للتصفية أو الفرز
                    if (type === 'display' && data !== null && !isNaN(data) && typeof formatNumber === 'function') {
                        return formatNumber(data);
                    }
                    return data;
                }
            }
        ]
    };
    
    // دمج الخيارات المخصصة مع الخيارات الافتراضية
    const mergedOptions = { ...defaultOptions, ...options };
    
    // إذا كان المستخدم قدم columnDefs خاصة به، فندمجها مع الافتراضي بدلاً من استبدالها
    if (options.columnDefs) {
        mergedOptions.columnDefs = [...defaultOptions.columnDefs, ...options.columnDefs];
    }
    
    // تهيئة الجدول
    return new DataTable(selector, mergedOptions);
} 