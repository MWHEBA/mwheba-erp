/**
 * DataTables Error Handler
 * معالج أخطاء جداول البيانات
 */

(function() {
    'use strict';

    // معالج أخطاء DataTables
    function handleDataTablesErrors() {
        // التحقق من وجود jQuery و DataTables
        if (typeof $ === 'undefined') {
            console.warn('jQuery not loaded, DataTables error handler disabled');
            return;
        }

        // معالج أخطاء DataTables العام
        $(document).on('error.dt', function(e, settings, techNote, message) {
            console.warn('DataTables error:', message);
            
            // تجاهل أخطاء DataTables الشائعة
            const ignoredErrors = [
                'Cannot reinitialise DataTable',
                'Requested unknown parameter',
                'Invalid JSON response'
            ];
            
            if (ignoredErrors.some(error => message.includes(error))) {
                console.warn('DataTables error ignored:', message);
                e.preventDefault();
                return;
            }
        });

        // دالة آمنة لتهيئة DataTables
        window.safeInitDataTable = function(tableId, options = {}) {
            try {
                const tableElement = document.getElementById(tableId);
                if (!tableElement) {
                    console.warn(`Table with ID "${tableId}" not found`);
                    return null;
                }

                const $table = $(tableElement);
                
                // التحقق من أن DataTables متوفر
                if (!$.fn.DataTable) {
                    console.warn('DataTables not loaded');
                    return null;
                }

                // التحقق من أن الجدول لم يتم تهيئته مسبقاً
                if ($.fn.DataTable.isDataTable(tableElement)) {
                    $table.DataTable().destroy();
                }

                // تهيئة الجدول مع معالجة الأخطاء
                const defaultOptions = {
                    responsive: true,
                    language: {
                        url: '/static/js/ar.json',
                        emptyTable: 'لا توجد بيانات متاحة',
                        info: 'عرض _START_ إلى _END_ من _TOTAL_ عنصر',
                        infoEmpty: 'عرض 0 إلى 0 من 0 عنصر',
                        infoFiltered: '(مفلتر من _MAX_ عنصر)',
                        lengthMenu: 'عرض _MENU_ عنصر',
                        loadingRecords: 'جاري التحميل...',
                        processing: 'جاري المعالجة...',
                        search: 'البحث:',
                        zeroRecords: 'لم يتم العثور على نتائج',
                        paginate: {
                            first: 'الأول',
                            last: 'الأخير',
                            next: 'التالي',
                            previous: 'السابق'
                        }
                    },
                    dom: '<"row"<"col-sm-12 col-md-6"l><"col-sm-12 col-md-6"f>>' +
                         '<"row"<"col-sm-12"tr>>' +
                         '<"row"<"col-sm-12 col-md-5"i><"col-sm-12 col-md-7"p>>',
                    pageLength: 25,
                    lengthMenu: [[10, 25, 50, 100, -1], [10, 25, 50, 100, 'الكل']],
                    order: [],
                    columnDefs: [
                        { targets: 'no-sort', orderable: false }
                    ]
                };

                const finalOptions = $.extend(true, {}, defaultOptions, options);
                
                const dataTable = $table.DataTable(finalOptions);
                
                return dataTable;
                
            } catch (error) {
                console.error(`Error initializing DataTable "${tableId}":`, error);
                return null;
            }
        };

        // دالة آمنة لتدمير DataTables
        window.safeDestroyDataTable = function(tableId) {
            try {
                const tableElement = document.getElementById(tableId);
                if (!tableElement) {
                    return false;
                }

                const $table = $(tableElement);
                
                if ($.fn.DataTable && $.fn.DataTable.isDataTable(tableElement)) {
                    $table.DataTable().destroy();
                    return true;
                }
                
                return false;
            } catch (error) {
                console.error(`Error destroying DataTable "${tableId}":`, error);
                return false;
            }
        };

        // دالة آمنة لإعادة تحميل بيانات DataTables
        window.safeReloadDataTable = function(tableId) {
            try {
                const tableElement = document.getElementById(tableId);
                if (!tableElement) {
                    return false;
                }

                const $table = $(tableElement);
                
                if ($.fn.DataTable && $.fn.DataTable.isDataTable(tableElement)) {
                    $table.DataTable().ajax.reload();
                    return true;
                }
                
                return false;
            } catch (error) {
                console.error(`Error reloading DataTable "${tableId}":`, error);
                return false;
            }
        };
    }

    // تهيئة معالج أخطاء DataTables
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            // انتظار تحميل jQuery
            function waitForJQuery() {
                if (typeof $ !== 'undefined') {
                    handleDataTablesErrors();
                } else {
                    setTimeout(waitForJQuery, 100);
                }
            }
            waitForJQuery();
        });
    } else {
        if (typeof $ !== 'undefined') {
            handleDataTablesErrors();
        } else {
            // انتظار تحميل jQuery
            function waitForJQuery() {
                if (typeof $ !== 'undefined') {
                    handleDataTablesErrors();
                } else {
                    setTimeout(waitForJQuery, 100);
                }
            }
            waitForJQuery();
        }
    }


})();