/**
 * تهيئة آمنة لـ DataTables
 * يمنع أخطاء _DT_CellIndex والأخطاء الشائعة الأخرى
 */

function safeDataTableInit(tableId, options = {}) {
    // الإعدادات الافتراضية
    const defaultOptions = {
        language: {
            url: '/static/js/datatables/ar.json'
        },
        pageLength: 25,
        responsive: true,
        order: [[0, 'asc']],
        columnDefs: []
    };
    
    // دمج الإعدادات
    const finalOptions = Object.assign({}, defaultOptions, options);
    
    return new Promise((resolve, reject) => {
        // انتظار قليل للتأكد من تحميل الجدول
        setTimeout(() => {
            try {
                const $table = $('#' + tableId);
                
                // فحص وجود الجدول
                if (!$table.length) {
                    console.warn('الجدول غير موجود:', tableId);
                    resolve(null);
                    return;
                }
                
                // فحص وجود البيانات
                const $tbody = $table.find('tbody');
                const $rows = $tbody.find('tr');
                
                if (!$rows.length) {
                    console.log('لا توجد صفوف في الجدول:', tableId);
                    resolve(null);
                    return;
                }
                
                // فحص الصف الأول للتأكد من عدم وجود colspan
                const $firstRow = $rows.first();
                const hasColspan = $firstRow.find('td[colspan]').length > 0;
                
                if (hasColspan) {
                    console.log('الجدول يحتوي على صف فارغ أو رسالة:', tableId);
                    resolve(null);
                    return;
                }
                
                // عد الأعمدة
                const headerColumns = $table.find('thead th').length;
                const firstRowColumns = $firstRow.find('td').length;
                
                if (headerColumns !== firstRowColumns) {
                    console.warn('عدد الأعمدة غير متطابق في الجدول:', tableId, 
                                'Header:', headerColumns, 'First Row:', firstRowColumns);
                    resolve(null);
                    return;
                }
                
                // فحص جميع الصفوف للتأكد من تطابق عدد الأعمدة
                let allRowsValid = true;
                $rows.each(function() {
                    const $row = $(this);
                    const rowColumns = $row.find('td').length;
                    if (rowColumns !== headerColumns && !$row.find('td[colspan]').length) {
                        console.warn('صف غير متطابق في الجدول:', tableId, 'Row columns:', rowColumns);
                        allRowsValid = false;
                        return false; // break
                    }
                });
                
                if (!allRowsValid) {
                    resolve(null);
                    return;
                }
                
                // تهيئة DataTable
                const dataTable = $table.DataTable(finalOptions);
                console.log('تم تهيئة DataTable بنجاح:', tableId);
                resolve(dataTable);
                
            } catch (error) {
                console.error('خطأ في تهيئة DataTable:', tableId, error);
                reject(error);
            }
        }, 150); // انتظار 150ms
    });
}

// دالة مساعدة لتحديد الأعمدة الرقمية
function getNumericColumns(columnCount, columnMap = {}) {
    const numericColumns = [];
    
    for (const [minColumns, columnIndex] of Object.entries(columnMap)) {
        if (columnCount >= parseInt(minColumns)) {
            numericColumns.push(columnIndex);
        }
    }
    
    return numericColumns;
}

// تصدير للاستخدام العام
window.safeDataTableInit = safeDataTableInit;
window.getNumericColumns = getNumericColumns;
