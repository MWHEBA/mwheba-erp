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
        console.error('المكتبات الأساسية غير متوفرة');
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
    
    console.log(`الجدول ${tableId} يحتوي على ${rows.length} صف - تهيئة DataTables`);
    
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
            "decimal": "",
            "emptyTable": "لا توجد بيانات متاحة في الجدول",
            "info": "عرض _START_ إلى _END_ من إجمالي _TOTAL_ عنصر",
            "infoEmpty": "عرض 0 إلى 0 من إجمالي 0 عنصر",
            "infoFiltered": "(مفلتر من إجمالي _MAX_ عنصر)",
            "infoPostFix": "",
            "thousands": ",",
            "lengthMenu": "عرض _MENU_ عنصر",
            "loadingRecords": "جاري التحميل...",
            "processing": "جاري المعالجة...",
            "search": "بحث:",
            "zeroRecords": "لم يتم العثور على نتائج مطابقة",
            "paginate": {
                "first": "الأول",
                "last": "الأخير",
                "next": "التالي",
                "previous": "السابق"
            },
            "aria": {
                "sortAscending": ": تفعيل لترتيب العمود تصاعدياً",
                "sortDescending": ": تفعيل لترتيب العمود تنازلياً"
            }
        },
        dom: '<"row"<"col-sm-12"tr>>' +
             '<"row"<"col-sm-12 col-md-5"i><"col-sm-12 col-md-7"p>>',
        searching: false,  // تعطيل البحث التلقائي (نستخدم table-controls)
        lengthChange: false,  // تعطيل قائمة عدد العناصر التلقائية
        order: [[0, 'desc']],
        columnDefs: [
            { targets: '_all', className: 'text-center' }
        ]
    };
    
    // دمج الإعدادات
    const mergedOptions = Object.assign({}, defaultOptions, options);
    
    try {
        // تحقق من وجود DataTable مسبقاً وقم بتدميره
        if ($.fn.DataTable.isDataTable(table)) {
            $(table).DataTable().destroy();
        }
        
        const dataTable = $(table).DataTable(mergedOptions);
        setupExternalControls(tableId, dataTable);
        
    } catch (error) {
        console.error(`خطأ في تهيئة الجدول ${tableId}:`, error);
        
        // محاولة إصلاح مشكلة الأعمدة وإعادة المحاولة
        if (error.message && error.message.includes('_DT_CellIndex')) {
            try {
                fixColumnCount(tableId);
                // تحقق من وجود DataTable مسبقاً وقم بتدميره
                if ($.fn.DataTable.isDataTable(table)) {
                    $(table).DataTable().destroy();
                }
                const dataTable = $(table).DataTable(mergedOptions);
                setupExternalControls(tableId, dataTable);
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
        console.error('مكتبة XLSX غير متوفرة');
        alert('مكتبة التصدير غير متوفرة');
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

// تهيئة جميع الجداول في الصفحة
function initializeAllTables() {
    const tables = document.querySelectorAll('table[id]');
    
    tables.forEach(table => {
        const tableId = table.id;
        if (tableId && !table.classList.contains('no-datatables')) {
            initializeTable(tableId);
        }
    });
}

// تصدير الوظائف للاستخدام العام
window.GlobalTableManager = {
    initializeTable,
    initializeAllTables,
    exportToCSV,
    exportToExcel,
    checkRequiredLibraries
};

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
