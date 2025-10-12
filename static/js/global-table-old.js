/**
 * نظام إدارة الجداول الموحد
 */

// التحقق من وجود المكتبات المطلوبة
function checkRequiredLibraries() {
    const libraries = {
        'jQuery': typeof $ !== 'undefined',
        'DataTables': typeof $.fn.DataTable !== 'undefined',
        'DataTables Buttons': typeof $.fn.dataTable !== 'undefined' && typeof $.fn.dataTable.Buttons !== 'undefined',
        'XLSX': typeof XLSX !== 'undefined'
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
        console.error('المكتبات الأساسية غير متوفرة - تم إلغاء تهيئة الجدول');
        return;
    }
    
    const table = document.getElementById(tableId);
    if (!table) {
        console.warn(`الجدول ${tableId} غير موجود`);
        return;
    }
    
    // التحقق من وجود بيانات في الجدول
    const tbody = table.querySelector('tbody');
    const rows = tbody ? tbody.querySelectorAll('tr') : [];
    
    // التحقق من الجداول الفارغة (صف واحد مع data-empty="true")
    if (rows.length === 0 || (rows.length === 1 && rows[0].getAttribute('data-empty') === 'true')) {
        hideTableControls(tableId);
        return;
    }
    
    // التحقق من تطابق عدد الأعمدة
    if (!validateTableStructure(tableId)) {
        console.warn(`بنية الجدول ${tableId} غير صحيحة`);
        return;
    }
    
    // إعدادات DataTables الافتراضية
    const defaultOptions = {
        responsive: true,
        pageLength: 25,
        lengthMenu: [[10, 25, 50, 100, -1], [10, 25, 50, 100, "الكل"]],
        language: {
            url: '/static/js/ar.json'
        },
        dom: '<"row"<"col-sm-12 col-md-6"l><"col-sm-12 col-md-6"f>>' +
             '<"row"<"col-sm-12"tr>>' +
             '<"row"<"col-sm-12 col-md-5"i><"col-sm-12 col-md-7"p>>',
        order: [[0, 'desc']],
        columnDefs: [
            { targets: '_all', className: 'text-center' }
        ]
    };
    
    // دمج الإعدادات
    const mergedOptions = Object.assign({}, defaultOptions, options);
    
    try {
        const dataTable = $(table).DataTable(mergedOptions);
        
        // ربط عناصر التحكم الخارجية
        setupExternalControls(tableId, dataTable);
        
    } catch (error) {
        console.error(`خطأ في تهيئة الجدول ${tableId}:`, error);
        
        // محاولة إصلاح مشكلة الأعمدة وإعادة المحاولة
        if (error.message && error.message.includes('_DT_CellIndex')) {
            try {
                fixColumnCount(tableId);
                const dataTable = $(table).DataTable(mergedOptions);
                setupExternalControls(tableId, dataTable);
            } catch (secondError) {
                console.error(`فشل في إصلاح الجدول ${tableId}:`, secondError);
                // تراجع للجدول العادي
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

// إخفاء عناصر التحكم للجداول الفارغة
function hideTableControls(tableId) {
    const table = document.getElementById(tableId);
    if (!table) return;
    
    // إخفاء أزرار التصدير
    const exportButtons = document.querySelectorAll(`[data-table="${tableId}"]`);
    exportButtons.forEach(btn => {
        btn.style.display = 'none';
    });
    
    // إخفاء عناصر التحكم (البحث وعدد العناصر)
    const tableControls = document.querySelector('.table-controls');
    if (tableControls) {
        tableControls.style.display = 'none';
    }
    
    // إضافة class للجدول الفارغ
    table.classList.add('table-empty');
}

// ربط عناصر التحكم الخارجية
function setupExternalControls(tableId, dataTable) {
    // ربط البحث الخارجي
    const searchInput = document.querySelector(`.table-search[data-table="${tableId}"]`);
    if (searchInput) {
        searchInput.addEventListener('keyup', function() {
            dataTable.search(this.value).draw();
        });
    }
    
    // ربط تغيير عدد العناصر
    const lengthSelect = document.querySelector(`.table-length[data-table="${tableId}"]`);
    if (lengthSelect) {
        lengthSelect.addEventListener('change', function() {
            dataTable.page.len(parseInt(this.value)).draw();
        });
    }
}

// إعداد أزرار التصدير
function setupExportButtons(tableId, dataTable) {
    // زر تصدير CSV
    const csvButton = document.querySelector(`.btn-export-table[data-table="${tableId}"]`);
    if (csvButton) {
        csvButton.addEventListener('click', function() {
            exportToCSV(tableId, this.dataset.filename || 'export');
        });
    }
    
    // زر تصدير Excel
    const excelButton = document.querySelector(`.btn-export-excel[data-table="${tableId}"]`);
    if (excelButton) {
        excelButton.addEventListener('click', function() {
            exportToExcel(tableId, this.dataset.filename || 'export');
        });
    }
}

// تصدير إلى CSV
function exportToCSV(tableId, filename) {
    try {
        const table = document.getElementById(tableId);
        if (!table) return;
        
        let csv = '\uFEFF'; // BOM for UTF-8
        
        // إضافة الرأس
        const headers = table.querySelectorAll('thead th');
        const headerRow = Array.from(headers)
            .filter(th => !th.classList.contains('col-actions'))
            .map(th => `"${th.textContent.trim()}"`)
            .join(',');
        csv += headerRow + '\n';
        
        // إضافة البيانات
        const rows = table.querySelectorAll('tbody tr');
        rows.forEach(row => {
            const cells = row.querySelectorAll('td');
            const rowData = Array.from(cells)
                .filter((td, index) => !headers[index]?.classList.contains('col-actions'))
                .map(td => `"${td.textContent.trim()}"`)
                .join(',');
            csv += rowData + '\n';
        });
        
        // تحميل الملف
        const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = `${filename}.csv`;
        link.click();
        
        console.log(`تم تصدير ${tableId} إلى CSV بنجاح`);
        
    } catch (error) {
        console.error(`خطأ في تصدير CSV للجدول ${tableId}:`, error);
    }
}

// تصدير إلى Excel
function exportToExcel(tableId, filename) {
    if (typeof XLSX === 'undefined') {
        console.warn('مكتبة XLSX غير متوفرة - لا يمكن التصدير إلى Excel');
        return;
    }
    
    try {
        const table = document.getElementById(tableId);
        if (!table) return;
        
        // إنشاء workbook
        const wb = XLSX.utils.book_new();
        
        // تحويل الجدول إلى worksheet
        const ws = XLSX.utils.table_to_sheet(table);
        
        // إضافة worksheet إلى workbook
        XLSX.utils.book_append_sheet(wb, ws, 'البيانات');
        
        // تحميل الملف
        XLSX.writeFile(wb, `${filename}.xlsx`);
        
        console.log(`تم تصدير ${tableId} إلى Excel بنجاح`);
        
    } catch (error) {
        console.error(`خطأ في تصدير Excel للجدول ${tableId}:`, error);
    }
}

// معالجة أخطاء الجداول
function handleTableError(tableId, error) {
    const table = document.getElementById(tableId);
    if (!table) return;
    
    console.log(`معالجة خطأ الجدول ${tableId}:`, error.message);
    
    // إضافة class للإشارة إلى فشل DataTables
    table.classList.add('datatables-failed');
    
    // إخفاء عناصر التحكم في حالة الفشل
    const tableControls = document.querySelector('.table-controls');
    if (tableControls) {
        tableControls.style.display = 'none';
    }
    
    // محاولة إصلاح مشكلة _DT_CellIndex
    if (error.message && error.message.includes('_DT_CellIndex')) {
        console.log(`محاولة إصلاح مشكلة _DT_CellIndex للجدول ${tableId}`);
        
        // إزالة جميع خصائص DataTables
        const $table = $(table);
        if ($table.hasClass('dataTable')) {
            $table.DataTable().destroy();
        }
        
        // إعادة المحاولة بإعدادات مبسطة
        setTimeout(() => {
            try {
                const simpleOptions = {
                    paging: false,
                    searching: false,
                    ordering: false,
                    info: false
                };
                
                const dataTable = $table.DataTable(simpleOptions);
                table.dataTable = dataTable;
                
                console.log(`تم إصلاح الجدول ${tableId} بإعدادات مبسطة`);
                
            } catch (retryError) {
                console.error(`فشل في إصلاح الجدول ${tableId}:`, retryError);
            }
        }, 100);
    }
}

// تهيئة جميع الجداول في الصفحة
function initializeAllTables() {
    // البحث عن جميع الجداول في الصفحة
    const tables = document.querySelectorAll('table[id][data-datatable]');
    
    tables.forEach(table => {
        const tableId = table.id;
        if (tableId && !table.classList.contains('no-datatables')) {
        }
    });
}

// تهيئة تلقائية عند تحميل الصفحة - معطلة لتجنب التكرار
// document.addEventListener('DOMContentLoaded', function() {
//     console.log('تهيئة نظام الجداول الموحد');
//     
//     // انتظار قصير للتأكد من تحميل جميع المكتبات
//     setTimeout(() => {
//         initializeAllTables();
//     }, 100);
// });

// تصدير الوظائف للاستخدام العام
window.GlobalTableManager = {
    initializeTable,
    initializeAllTables,
    exportToCSV,
    exportToExcel,
    checkRequiredLibraries
};
