/**
 * Enhanced Data Table Manager
 * إدارة الجداول المحسنة مع DataTables
 */

class EnhancedDataTable {
    constructor(tableId, options = {}) {
        this.tableId = tableId;
        this.table = null;
        this.options = {
            // الإعدادات الافتراضية
            ordering: true,
            searching: true,
            paging: true,
            info: true,
            responsive: true,
            language: {
                url: '//cdn.datatables.net/plug-ins/1.13.7/i18n/ar.json'
            },
            columnDefs: [
                { targets: 'no-sort', orderable: false },
                { targets: '_all', className: 'text-center' }
            ],
            pageLength: 25,
            lengthMenu: [[10, 25, 50, 100], [10, 25, 50, 100]],
            dom: 'rt<"d-flex justify-content-between align-items-center mt-3"<"table-info"i><"table-pagination"p>>',
            ...options
        };
        
        this.init();
    }
    
    init() {
        if (!$.fn.DataTable) {
            console.error('DataTables library not found');
            return;
        }
        
        try {
            // تهيئة DataTable
            this.table = $(`#${this.tableId}`).DataTable(this.options);
            
            // ربط أدوات التحكم المخصصة
            this.bindCustomControls();
            
            // تفعيل النقر على الصفوف إذا كان مطلوباً
            if (this.options.clickableRows) {
                this.enableRowClicks();
            }
            
            // تفعيل أزرار التصدير
            this.enableExportButtons();
            
            console.log(`Enhanced DataTable initialized for #${this.tableId}`);
            
        } catch (error) {
            console.error(`Error initializing DataTable for #${this.tableId}:`, error);
        }
    }
    
    bindCustomControls() {
        const tableId = this.tableId;
        
        // ربط مربع البحث المخصص
        $(`.table-search[data-table="${tableId}"]`).on('keyup', (e) => {
            this.table.search(e.target.value).draw();
        });
        
        // ربط قائمة عدد العناصر المخصصة
        $(`.table-length[data-table="${tableId}"]`).on('change', (e) => {
            this.table.page.len(parseInt(e.target.value)).draw();
        });
    }
    
    enableRowClicks() {
        if (!this.options.rowClickUrl) return;
        
        $(`#${this.tableId} tbody`).on('click', 'tr', (e) => {
            // تجاهل النقر على أزرار الإجراءات
            if ($(e.target).closest('.col-actions').length > 0) return;
            
            // تجاهل الصفوف الفارغة
            if ($(e.currentTarget).hasClass('empty-row')) return;
            
            // الحصول على ID
            const itemId = $(e.currentTarget).data('id');
            if (itemId) {
                const url = this.options.rowClickUrl.replace('0', itemId);
                window.location.href = url;
            }
        });
        
        // إضافة مؤشر اليد
        $(`#${this.tableId} tbody tr:not(.empty-row)`).css('cursor', 'pointer');
    }
    
    enableExportButtons() {
        // تصدير CSV
        $(`.btn-export-table[data-table="${this.tableId}"]`).on('click', (e) => {
            const filename = $(e.currentTarget).data('filename') || 'table_data.csv';
            this.exportToCSV(filename);
        });
        
        // تصدير Excel
        $(`.btn-export-excel[data-table="${this.tableId}"]`).on('click', (e) => {
            const filename = $(e.currentTarget).data('filename') || 'table_data.xlsx';
            this.exportToExcel(filename);
        });
    }
    
    exportToCSV(filename) {
        if (!this.table) return;
        
        try {
            // الحصول على البيانات المرئية فقط
            const data = this.table.rows({ search: 'applied' }).data().toArray();
            const headers = this.table.columns().header().toArray().map(th => $(th).text().trim());
            
            // إزالة عمود الإجراءات
            const filteredHeaders = headers.filter(header => header !== 'إجراءات');
            
            // تحويل البيانات إلى CSV
            let csvContent = '\uFEFF'; // BOM for UTF-8
            csvContent += filteredHeaders.join(',') + '\n';
            
            this.table.rows({ search: 'applied' }).every(function() {
                const rowData = [];
                const row = $(this.node());
                
                row.find('td:not(.col-actions)').each(function() {
                    let cellText = $(this).text().trim();
                    // تنظيف النص من الأحرف الخاصة
                    cellText = cellText.replace(/"/g, '""');
                    rowData.push(`"${cellText}"`);
                });
                
                csvContent += rowData.join(',') + '\n';
            });
            
            // تحميل الملف
            const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
            const link = document.createElement('a');
            link.href = URL.createObjectURL(blob);
            link.download = filename;
            link.click();
            
        } catch (error) {
            console.error('Error exporting to CSV:', error);
            alert('حدث خطأ أثناء تصدير البيانات');
        }
    }
    
    exportToExcel(filename) {
        if (!this.table || !window.XLSX) {
            console.warn('XLSX library not found - استخدام CSV بدلاً من ذلك');
            this.exportToCSV(filename.replace('.xlsx', '.csv'));
            return;
        }
        
        try {
            // إنشاء workbook جديد
            const wb = XLSX.utils.book_new();
            
            // الحصول على البيانات
            const headers = this.table.columns().header().toArray()
                .map(th => $(th).text().trim())
                .filter(header => header !== 'إجراءات');
            
            const data = [headers];
            
            this.table.rows({ search: 'applied' }).every(function() {
                const rowData = [];
                const row = $(this.node());
                
                row.find('td:not(.col-actions)').each(function() {
                    rowData.push($(this).text().trim());
                });
                
                data.push(rowData);
            });
            
            // إنشاء worksheet
            const ws = XLSX.utils.aoa_to_sheet(data);
            
            // إضافة worksheet إلى workbook
            XLSX.utils.book_append_sheet(wb, ws, 'البيانات');
            
            // تحميل الملف
            XLSX.writeFile(wb, filename);
            
        } catch (error) {
            console.error('Error exporting to Excel:', error);
            alert('حدث خطأ أثناء تصدير البيانات');
        }
    }
    
    // دوال مساعدة
    refresh() {
        if (this.table) {
            this.table.ajax.reload();
        }
    }
    
    destroy() {
        if (this.table) {
            this.table.destroy();
            this.table = null;
        }
    }
    
    search(term) {
        if (this.table) {
            this.table.search(term).draw();
        }
    }
    
    // دالة مساعدة لتهيئة جدول بسيط
    static initSimpleTable(tableId, options = {}) {
        return new EnhancedDataTable(tableId, {
            ordering: true,
            searching: false, // سنستخدم البحث المخصص
            paging: false,    // سنستخدم التحكم المخصص
            info: false,      // سنستخدم المعلومات المخصصة
            ...options
        });
    }
}

// تصدير للاستخدام العام
window.EnhancedDataTable = EnhancedDataTable;

// دالة مساعدة للتهيئة السريعة
window.initEnhancedTable = function(tableId, options = {}) {
    return new EnhancedDataTable(tableId, options);
};
