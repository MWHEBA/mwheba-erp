/**
 * نظام إدارة الجداول الموحد - نسخة نظيفة
 * @version 2.0.0
 */


// التحقق من وجود المكتبات المطلوبة
function checkRequiredLibraries() {
    const libraries = {
        'jQuery': typeof $ !== 'undefined',
        'DataTables': typeof $.fn.DataTable !== 'undefined',
        'DataTables Buttons': typeof $.fn.dataTable !== 'undefined' && typeof $.fn.dataTable.Buttons !== 'undefined',
        'XLSX': typeof XLSX !== 'undefined' // اختياري للتصدير
    };
    
    let allLoaded = true;
    for (const [name, loaded] of Object.entries(libraries)) {
        if (!loaded) {
            console.warn(`مكتبة ${name} غير متوفرة`);
            if (name === 'jQuery' || name === 'DataTables') {
                allLoaded = false;
            }
        }
    }
    
    return allLoaded;
}

// تهيئة جدول واحد
function initializeTable(tableId, options = {}) {
    // التحقق من وجود المكتبات الأساسية
    if (!checkRequiredLibraries()) {
        console.error('المكتبات الأساسية غير متوفرة');
        return;
    }
    
    const table = document.getElementById(tableId);
    if (!table) {
        console.warn(`الجدول ${tableId} غير موجود`);
        return;
    }
    
    // تجاهل الجداول التي فشلت سابقاً
    if (table.classList.contains('table-failed')) {
        console.info(`تجاهل الجدول ${tableId} - فشل في التهيئة سابقاً`);
        return;
    }
    
    // تجاهل الجداول المُهيأة بالفعل والتي تعمل بشكل صحيح
    if (table.classList.contains('table-initialized') && $.fn.DataTable.isDataTable(table)) {
        console.info(`تجاهل الجدول ${tableId} - مُهيأ بالفعل`);
        return;
    }
    
    // التحقق من وجود بيانات في الجدول
    const tbody = table.querySelector('tbody');
    const rows = tbody ? tbody.querySelectorAll('tr') : [];
    
    // فحص إضافي للجداول الفاضية
    if (rows.length === 0) {
        console.info(`تجاهل الجدول ${tableId} - لا يحتوي على صفوف`);
        return;
    }
    
    // فحص الجداول التي تحتوي على رسالة "لا توجد بيانات" فقط
    if (rows.length === 1) {
        const firstRowText = rows[0].textContent.trim();
        if (firstRowText.includes('لا توجد') || firstRowText.includes('No data') || firstRowText === '') {
            console.info(`تجاهل الجدول ${tableId} - يحتوي على رسالة فارغة أو "لا توجد بيانات"`);
            return;
        }
    }
    
    // التحقق من تطابق عدد الأعمدة
    if (!validateTableStructure(tableId)) {
        console.warn(`بنية الجدول ${tableId} غير صحيحة`);
        return;
    }
    
    // التحقق من وجود مربع بحث خارجي
    const hasExternalSearch = document.querySelector(`.table-search[data-table="${tableId}"]`) !== null;
    
    // التحقق من تعطيل الترتيب
    const disableOrdering = table.getAttribute('data-disable-ordering') === 'true';
    
    // إعدادات DataTables الافتراضية
    const defaultOptions = {
        responsive: true,
        pageLength: 25,
        lengthMenu: [[10, 25, 50, 100, -1], [10, 25, 50, 100, "الكل"]],
        language: {
            url: '/static/js/ar.json'
        },
        dom: '<"row"<"col-sm-12"tr>>' +
             '<"row"<"col-sm-12 col-md-5"i><"col-sm-12 col-md-7"p>>',
        searching: hasExternalSearch,  // تفعيل البحث إذا كان هناك مربع بحث خارجي
        lengthChange: false,  // تعطيل قائمة عدد العناصر التلقائية
        ordering: !disableOrdering,  // تعطيل الترتيب إذا كان محدد
        order: [],  // بدون ترتيب افتراضي - استخدام ترتيب البيانات الأصلي
        columnDefs: disableOrdering ? [
            { targets: '_all', className: 'text-center', orderable: false }
        ] : [
            { targets: '_all', className: 'text-center' }
        ]
    };
    
    // دمج الإعدادات
    const mergedOptions = Object.assign({}, defaultOptions, options);
    
    try {
        // التحقق من وجود العنصر في DOM
        if (!document.contains(table)) {
            console.warn(`الجدول ${tableId} غير موجود في DOM`);
            return;
        }
        
        // تحقق من وجود DataTable مسبقاً وقم بتدميره
        if ($.fn.DataTable.isDataTable(table)) {
            try {
                // محاولة الحصول على instance الموجود
                const existingTable = $.fn.DataTable.Api(table);
                if (existingTable && typeof existingTable.destroy === 'function') {
                    existingTable.destroy(true); // true لإزالة DOM elements
                }
            } catch (destroyError) {
                console.warn(`تحذير: مشكلة في تدمير الجدول ${tableId}:`, destroyError);
                
                // تنظيف شامل يدوياً
                try {
                    // إزالة جميع البيانات المرتبطة بـ DataTables
                    $(table).removeData();
                    $(table).removeClass('dataTable');
                    
                    // إزالة الـ wrapper إذا كان موجود
                    const wrapper = $(table).closest('.dataTables_wrapper');
                    if (wrapper.length > 0) {
                        $(table).unwrap();
                    }
                    
                    // إزالة أي عناصر DataTables إضافية
                    $(table).find('.dataTables_empty').remove();
                    
                } catch (cleanupError) {
                    console.error(`فشل في تنظيف الجدول ${tableId}:`, cleanupError);
                    // كحل أخير، تجاهل هذا الجدول
                    return;
                }
            }
        }
        
        const dataTable = $(table).DataTable(mergedOptions);
        setupExternalControls(tableId, dataTable);
        
        // إضافة علامة نجاح التهيئة
        table.classList.add('table-initialized');
        
    } catch (error) {
        console.error(`خطأ في تهيئة الجدول ${tableId}:`, error);
        
        // محاولة إصلاح مشكلة الأعمدة وإعادة المحاولة
        if (error.message && error.message.includes('_DT_CellIndex')) {
            try {
                fixColumnCount(tableId);
                // تحقق من وجود DataTable مسبقاً وقم بتدميره
                if ($.fn.DataTable.isDataTable(table)) {
                    try {
                        const existingTable = $(table).DataTable();
                        if (existingTable && existingTable.destroy) {
                            existingTable.destroy();
                        }
                    } catch (destroyError) {
                        console.warn(`تحذير: مشكلة في تدمير الجدول ${tableId} (المحاولة الثانية):`, destroyError);
                        $(table).removeData();
                        $(table).removeClass('dataTable');
                    }
                }
                const dataTable = $(table).DataTable(mergedOptions);
                setupExternalControls(tableId, dataTable);
                
                // إضافة علامة نجاح التهيئة
                table.classList.add('table-initialized');
                console.info(`تم إصلاح وتهيئة الجدول ${tableId} بنجاح`);
            } catch (secondError) {
                console.error(`فشل في إصلاح الجدول ${tableId}:`, secondError);
                table.classList.add('table-failed');
            }
        }
    }
}

// التحقق من بنية الجدول
function validateTableStructure(tableId) {
    const table = document.getElementById(tableId);
    if (!table) return false;
    
    try {
        const headColumns = table.querySelectorAll('thead th').length;
        const bodyRows = table.querySelectorAll('tbody tr');
        
        if (headColumns === 0) {
            console.warn(`الجدول ${tableId} لا يحتوي على رأس`);
            return false;
        }
        
        // التحقق من تطابق عدد الأعمدة في كل صف (تجاهل الصفوف الفارغة)
        for (let row of bodyRows) {
            // تجاهل الصفوف الفارغة التي تحتوي على colspan
            if (row.getAttribute('data-empty') === 'true') {
                continue;
            }
            
            const rowColumns = row.querySelectorAll('td').length;
            if (rowColumns !== headColumns) {
                console.warn(`عدم تطابق الأعمدة في الجدول ${tableId}: رأس=${headColumns}, صف=${rowColumns}`);
                return false;
            }
        }
        
        return true;
        
    } catch (error) {
        console.error(`خطأ في التحقق من بنية الجدول ${tableId}:`, error);
        return false;
    }
}

// ملاحظة: تم إزالة دوال hideTableControls و showTableControls 
// لأن الجداول الفارغة لا تظهر أصلاً في النظام الجديد

// ربط عناصر التحكم الخارجية
function setupExternalControls(tableId, dataTable) {
    // ربط البحث الخارجي
    const searchInput = document.querySelector(`.table-search[data-table="${tableId}"]`);
    if (searchInput) {
        searchInput.addEventListener('keyup', function() {
            dataTable.search(this.value).draw();
        });
    } else {
        console.warn(`⚠️ لم يتم العثور على مربع البحث للجدول ${tableId}`);
    }
    
    // ربط تحكم عدد العناصر
    const lengthSelect = document.querySelector(`.table-length[data-table="${tableId}"]`);
    if (lengthSelect) {
        lengthSelect.addEventListener('change', function() {
            dataTable.page.len(parseInt(this.value)).draw();
        });
    }
}

// إصلاح عدد الأعمدة
function fixColumnCount(tableId) {
    const table = document.getElementById(tableId);
    if (!table) return;
    
    const headColumns = table.querySelectorAll('thead th').length;
    const bodyRows = table.querySelectorAll('tbody tr');
    
    bodyRows.forEach(row => {
        if (row.getAttribute('data-empty') === 'true') return;
        
        const cells = row.querySelectorAll('td');
        const currentColumns = cells.length;
        
        if (currentColumns < headColumns) {
            // إضافة خلايا فارغة
            for (let i = currentColumns; i < headColumns; i++) {
                const newCell = document.createElement('td');
                newCell.textContent = '-';
                newCell.className = 'text-center';
                row.appendChild(newCell);
            }
        } else if (currentColumns > headColumns) {
            // إزالة الخلايا الزائدة
            for (let i = currentColumns - 1; i >= headColumns; i--) {
                if (cells[i]) {
                    cells[i].remove();
                }
            }
        }
    });
}

// تصدير CSV
function exportToCSV(tableId, filename = 'export.csv') {
    const table = document.getElementById(tableId);
    if (!table) return;
    
    const rows = table.querySelectorAll('tr');
    let csv = [];
    
    rows.forEach(row => {
        const cells = row.querySelectorAll('th, td');
        const rowData = [];
        
        cells.forEach(cell => {
            // تجاهل عمود الإجراءات
            if (!cell.classList.contains('col-actions')) {
                let text = cell.textContent.trim();
                // إزالة الفواصل والاقتباسات
                text = text.replace(/"/g, '""');
                rowData.push(`"${text}"`);
            }
        });
        
        if (rowData.length > 0) {
            csv.push(rowData.join(','));
        }
    });
    
    // إضافة BOM للعربية
    const csvContent = "\uFEFF" + csv.join('\n');
    
    // تنزيل الملف
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    link.setAttribute('href', url);
    link.setAttribute('download', filename);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

// تصدير Excel
function exportToExcel(tableId, filename = 'export.xlsx') {
    if (typeof XLSX === 'undefined') {
        console.warn('مكتبة XLSX غير متوفرة - استخدام تصدير CSV بدلاً من ذلك');
        exportToCSV(tableId, filename.replace('.xlsx', '.csv'));
        return;
    }
    
    const table = document.getElementById(tableId);
    if (!table) return;
    
    // إنشاء نسخة من الجدول بدون عمود الإجراءات
    const tableClone = table.cloneNode(true);
    const actionColumns = tableClone.querySelectorAll('.col-actions');
    actionColumns.forEach(col => col.remove());
    
    // تحويل إلى Excel
    const wb = XLSX.utils.table_to_book(tableClone, {sheet: "البيانات"});
    XLSX.writeFile(wb, filename);
}

// إعادة تعيين حالة جميع الجداول (للاستخدام عند الحاجة)
function resetAllTables() {
    const tables = document.querySelectorAll('table[id]');
    tables.forEach(table => {
        table.classList.remove('table-failed', 'table-initialized');
        
        // تنظيف DataTables إذا كان موجود
        if ($.fn.DataTable.isDataTable(table)) {
            try {
                $(table).DataTable().destroy();
            } catch (e) {
                // تجاهل الأخطاء
            }
        }
    });
    console.info('تم إعادة تعيين حالة جميع الجداول');
}

// تهيئة جميع الجداول في الصفحة
function initializeAllTables() {
    const tables = document.querySelectorAll('table[id]');
    
    tables.forEach(table => {
        const tableId = table.id;
        if (tableId && !table.classList.contains('no-datatables')) {
            // تجاهل الجداول التي فشلت أو تم تهيئتها بالفعل
            if (table.classList.contains('table-failed') || table.classList.contains('table-initialized')) {
                return;
            }
            
            // فحص إضافي للجداول المشكوك فيها
            if (!document.contains(table)) {
                console.warn(`تجاهل الجدول ${tableId} - غير موجود في DOM`);
                return;
            }
            
            // فحص بنية الجدول
            const tbody = table.querySelector('tbody');
            if (!tbody) {
                console.warn(`تجاهل الجدول ${tableId} - لا يحتوي على tbody`);
                return;
            }
            
            // فحص وجود صفوف في الجدول
            const rows = tbody.querySelectorAll('tr');
            if (rows.length === 0) {
                console.info(`تجاهل الجدول ${tableId} - لا يحتوي على بيانات`);
                return;
            }
            
            // فحص خاص للجداول الفاضية أو التي تحتوي على رسالة "لا توجد بيانات"
            const firstRow = rows[0];
            if (rows.length === 1 && firstRow.textContent.includes('لا توجد')) {
                console.info(`تجاهل الجدول ${tableId} - يحتوي على رسالة "لا توجد بيانات"`);
                return;
            }
            
            try {
                initializeTable(tableId);
            } catch (error) {
                console.error(`فشل في تهيئة الجدول ${tableId}:`, error);
                table.classList.add('table-failed');
            }
        }
    });
}

// دالة للتوافق مع الكود القديم
function initGlobalTable(tableId, options = {}) {
    return initializeTable(tableId, options);
}

// دوال للتوافق مع أزرار التصدير
function exportTableToCSV(tableId, filename) {
    return exportToCSV(tableId, filename);
}

function exportTableToExcel(tableId, filename) {
    return exportToExcel(tableId, filename);
}

// تصدير الوظائف للاستخدام العام
window.GlobalTableManager = {
    initializeTable,
    initializeAllTables,
    resetAllTables,
    exportToCSV,
    exportToExcel,
    checkRequiredLibraries
};

// تصدير الدوال للنطاق العام للتوافق
window.initGlobalTable = initGlobalTable;
window.exportTableToCSV = exportTableToCSV;
window.exportTableToExcel = exportTableToExcel;

// ربط أزرار التصدير
document.addEventListener('DOMContentLoaded', function() {
    // ربط أزرار تصدير CSV
    document.addEventListener('click', function(e) {
        if (e.target.classList.contains('btn-export-table')) {
            const tableId = e.target.getAttribute('data-table');
            const filename = e.target.getAttribute('data-filename') || 'export.csv';
            exportToCSV(tableId, filename);
        }
        
        // ربط أزرار تصدير Excel
        if (e.target.classList.contains('btn-export-excel')) {
            const tableId = e.target.getAttribute('data-table');
            const filename = e.target.getAttribute('data-filename') || 'export.xlsx';
            exportToExcel(tableId, filename);
        }
    });
});
