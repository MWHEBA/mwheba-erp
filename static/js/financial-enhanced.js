/**
 * JavaScript محسن للواجهات المالية
 * يوفر وظائف محسنة للجداول والبحث والتحميل التدريجي
 */

class FinancialEnhanced {
    constructor() {
        this.init();
    }

    init() {
        this.initializeTables();
        this.initializeSearch();
        this.initializeFilters();
        this.initializeLazyLoading();
        this.initializeTooltips();
        this.initializeModals();
    }

    /**
     * تهيئة الجداول المحسنة
     */
    initializeTables() {
        // تهيئة جداول DataTables مع الإعدادات المحسنة
        if (typeof $.fn.DataTable !== 'undefined') {
            $('.financial-table').each((index, table) => {
                const $table = $(table);
                const tableId = $table.attr('id') || `financial-table-${index}`;
                
                // إعدادات DataTable المحسنة
                const options = {
                    responsive: true,
                    processing: true,
                    pageLength: 25,
                    lengthMenu: [[10, 25, 50, 100, -1], [10, 25, 50, 100, "الكل"]],
                    order: [[0, 'desc']], // ترتيب افتراضي حسب التاريخ
                    language: {
                        "search": "البحث:",
                        "lengthMenu": "عرض _MENU_ عنصر",
                        "info": "عرض _START_ إلى _END_ من _TOTAL_ عنصر",
                        "infoEmpty": "لا توجد عناصر للعرض",
                        "infoFiltered": "(مفلتر من _MAX_ عنصر إجمالي)",
                        "emptyTable": "لا توجد بيانات متاحة في الجدول",
                        "zeroRecords": "لم يتم العثور على نتائج مطابقة",
                        "paginate": {
                            "first": "الأول",
                            "last": "الأخير",
                            "next": "التالي",
                            "previous": "السابق"
                        }
                    },
                    dom: '<"row"<"col-sm-12 col-md-6"l><"col-sm-12 col-md-6"f>>' +
                         '<"row"<"col-sm-12"tr>>' +
                         '<"row"<"col-sm-12 col-md-5"i><"col-sm-12 col-md-7"p>>',
                    columnDefs: [
                        {
                            targets: -1, // آخر عمود (الإجراءات)
                            orderable: false,
                            searchable: false,
                            className: 'text-center'
                        }
                    ]
                };

                // تطبيق الإعدادات
                $table.DataTable(options);
            });
        }

        // تهيئة الجداول الهرمية (دليل الحسابات)
        this.initializeTreeTables();
    }

    /**
     * تهيئة الجداول الهرمية
     */
    initializeTreeTables() {
        // وظائف التوسيع والطي للحسابات
        $(document).on('click', '.expand-btn', function(e) {
            e.preventDefault();
            const accountId = $(this).data('account-id');
            if (accountId) {
                window.toggleAccountChildren(accountId);
            }
        });

        // توسيع الكل
        $('#expandAllBtn').on('click', function() {
            $('.expand-btn i.fa-chevron-left').each(function() {
                const btn = $(this).closest('.expand-btn');
                btn.trigger('click');
            });
        });

        // طي الكل
        $('#collapseAllBtn').on('click', function() {
            $('.expand-btn i.fa-chevron-down').each(function() {
                $(this).removeClass('fa-chevron-down').addClass('fa-chevron-left');
                $(this).css('color', '#6c757d');
            });
            
            $('.account-row[data-level]:not([data-level="0"])').removeClass('visible');
        });
    }

    /**
     * تهيئة البحث المحسن
     */
    initializeSearch() {
        // البحث الفوري
        let searchTimeout;
        $('.enhanced-search').on('input', function() {
            const $input = $(this);
            const form = $input.closest('form');
            
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                if ($input.val().length >= 2 || $input.val().length === 0) {
                    form.submit();
                }
            }, 500);
        });

        // البحث المتقدم
        $('.advanced-search-toggle').on('click', function() {
            const target = $(this).data('target');
            $(target).slideToggle();
            
            const icon = $(this).find('i');
            icon.toggleClass('fa-chevron-down fa-chevron-up');
        });

        // مسح البحث
        $('.clear-search').on('click', function() {
            const form = $(this).closest('form');
            form.find('input[type="text"], input[type="search"]').val('');
            form.find('select').prop('selectedIndex', 0);
            form.submit();
        });
    }

    /**
     * تهيئة الفلاتر المحسنة
     */
    initializeFilters() {
        // فلاتر تلقائية عند التغيير
        $('.auto-filter').on('change', function() {
            $(this).closest('form').submit();
        });

        // فلاتر التاريخ
        if (typeof flatpickr !== 'undefined') {
            flatpickr('[data-date-picker]', {
                dateFormat: 'Y-m-d',
                locale: 'ar',
                allowInput: true,
                clickOpens: true
            });
        }

        // فلاتر متعددة الاختيار
        if (typeof $ !== 'undefined' && $.fn.select2) {
            $('.multi-select').select2({
                placeholder: 'اختر...',
                allowClear: true,
                dir: 'rtl'
            });
        }
    }

    /**
     * تهيئة التحميل التدريجي
     */
    initializeLazyLoading() {
        // تحميل البيانات عند التمرير
        let isLoading = false;
        
        $(window).on('scroll', () => {
            if (isLoading) return;
            
            const scrollTop = $(window).scrollTop();
            const windowHeight = $(window).height();
            const documentHeight = $(document).height();
            
            // إذا وصل المستخدم إلى 80% من الصفحة
            if (scrollTop + windowHeight >= documentHeight * 0.8) {
                this.loadMoreData();
            }
        });
    }

    /**
     * تحميل المزيد من البيانات
     */
    loadMoreData() {
        const nextPageUrl = $('.pagination .page-item:last-child .page-link').attr('href');
        
        if (nextPageUrl && !nextPageUrl.includes('#')) {
            isLoading = true;
            
            // إظهار مؤشر التحميل
            this.showLoadingIndicator();
            
            $.get(nextPageUrl)
                .done((data) => {
                    // استخراج البيانات الجديدة وإضافتها
                    const newRows = $(data).find('tbody tr');
                    $('tbody').append(newRows);
                    
                    // تحديث رابط الصفحة التالية
                    const newNextUrl = $(data).find('.pagination .page-item:last-child .page-link').attr('href');
                    $('.pagination .page-item:last-child .page-link').attr('href', newNextUrl || '#');
                })
                .fail(() => {
                    this.showError('حدث خطأ في تحميل البيانات');
                })
                .always(() => {
                    isLoading = false;
                    this.hideLoadingIndicator();
                });
        }
    }

    /**
     * تهيئة التلميحات
     */
    initializeTooltips() {
        // تهيئة Bootstrap tooltips
        if (typeof bootstrap !== 'undefined') {
            const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
            tooltipTriggerList.map(function (tooltipTriggerEl) {
                return new bootstrap.Tooltip(tooltipTriggerEl);
            });
        }

        // تلميحات مخصصة للأرصدة
        $('.balance-tooltip').hover(
            function() {
                const balance = $(this).data('balance');
                const lastUpdate = $(this).data('last-update');
                
                $(this).attr('title', `الرصيد: ${balance} - آخر تحديث: ${lastUpdate}`);
            }
        );
    }

    /**
     * تهيئة النوافذ المنبثقة
     */
    initializeModals() {
        // تأكيد الحذف
        $('.delete-confirm').on('click', function(e) {
            e.preventDefault();
            
            const url = $(this).attr('href');
            const itemName = $(this).data('item-name') || 'هذا العنصر';
            
            if (confirm(`هل أنت متأكد من حذف ${itemName}؟`)) {
                window.location.href = url;
            }
        });

        // نافذة تفاصيل سريعة
        $('.quick-view').on('click', function(e) {
            e.preventDefault();
            
            const url = $(this).data('url');
            if (url) {
                this.loadQuickView(url);
            }
        });
    }

    /**
     * تحميل العرض السريع
     */
    loadQuickView(url) {
        const modal = $('#quickViewModal');
        if (modal.length === 0) {
            // إنشاء النافذة المنبثقة إذا لم تكن موجودة
            this.createQuickViewModal();
        }

        modal.find('.modal-body').html('<div class="text-center"><i class="fas fa-spinner fa-spin"></i> جاري التحميل...</div>');
        modal.modal('show');

        $.get(url)
            .done((data) => {
                modal.find('.modal-body').html(data);
            })
            .fail(() => {
                modal.find('.modal-body').html('<div class="alert alert-danger">حدث خطأ في تحميل البيانات</div>');
            });
    }

    /**
     * إنشاء نافذة العرض السريع
     */
    createQuickViewModal() {
        const modalHtml = `
            <div class="modal fade" id="quickViewModal" tabindex="-1">
                <div class="modal-dialog modal-lg">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">عرض سريع</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <!-- المحتوى سيتم تحميله هنا -->
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">إغلاق</button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        $('body').append(modalHtml);
    }

    /**
     * إظهار مؤشر التحميل
     */
    showLoadingIndicator() {
        if ($('#loadingIndicator').length === 0) {
            const indicator = `
                <div id="loadingIndicator" class="text-center py-3">
                    <i class="fas fa-spinner fa-spin me-2"></i>
                    جاري تحميل المزيد من البيانات...
                </div>
            `;
            $('tbody').after(indicator);
        }
    }

    /**
     * إخفاء مؤشر التحميل
     */
    hideLoadingIndicator() {
        $('#loadingIndicator').remove();
    }

    /**
     * إظهار رسالة خطأ
     */
    showError(message) {
        const alert = `
            <div class="alert alert-danger alert-dismissible fade show" role="alert">
                <i class="fas fa-exclamation-triangle me-2"></i>
                ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `;
        
        $('.container-fluid').prepend(alert);
        
        // إزالة التنبيه تلقائياً بعد 5 ثوان
        setTimeout(() => {
            $('.alert').fadeOut();
        }, 5000);
    }

    /**
     * تحديث الإحصائيات في الوقت الفعلي
     */
    updateStats() {
        $.get('/financial/api/stats/')
            .done((data) => {
                // تحديث البطاقات الإحصائية
                $('.stats-card-value').each(function() {
                    const cardType = $(this).closest('.stats-card').data('type');
                    if (data[cardType]) {
                        $(this).text(data[cardType]);
                    }
                });
            })
            .fail(() => {
                console.warn('فشل في تحديث الإحصائيات');
            });
    }

    /**
     * تصدير البيانات
     */
    exportData(format = 'excel') {
        const currentUrl = new URL(window.location);
        currentUrl.searchParams.set('export', format);
        
        // إنشاء رابط تحميل مخفي
        const link = document.createElement('a');
        link.href = currentUrl.toString();
        link.download = `financial_data_${new Date().toISOString().split('T')[0]}.${format}`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    }

    /**
     * طباعة التقرير
     */
    printReport() {
        // إخفاء العناصر غير المطلوبة للطباعة
        $('.no-print').hide();
        
        // تطبيق أنماط الطباعة
        $('body').addClass('print-mode');
        
        window.print();
        
        // استعادة العرض العادي
        $('.no-print').show();
        $('body').removeClass('print-mode');
    }
}

// تهيئة الكلاس عند تحميل الصفحة
$(document).ready(function() {
    window.FinancialEnhanced = new FinancialEnhanced();
});

// وظائف مساعدة عامة
window.toggleAccountChildren = function(accountId) {
    const parentRow = document.querySelector(`tr[data-account-id="${accountId}"]`);
    const icon = document.getElementById(`icon-${accountId}`);
    
    if (!parentRow || !icon) return;
    
    const parentLevel = parseInt(parentRow.dataset.level);
    
    // العثور على جميع الصفوف الفرعية المباشرة
    let nextRow = parentRow.nextElementSibling;
    const directChildRows = [];
    
    while (nextRow && nextRow.dataset.level && parseInt(nextRow.dataset.level) > parentLevel) {
        const currentLevel = parseInt(nextRow.dataset.level);
        
        // إضافة الأطفال المباشرين فقط (المستوى التالي مباشرة)
        if (currentLevel === parentLevel + 1) {
            directChildRows.push(nextRow);
        }
        
        nextRow = nextRow.nextElementSibling;
    }
    
    // تبديل حالة العرض
    const isExpanded = icon.classList.contains('fa-chevron-down');
    
    if (isExpanded) {
        // طي: إخفاء جميع الأطفال والأحفاد
        hideAllDescendants(parentRow, parentLevel);
        icon.classList.remove('fa-chevron-down');
        icon.classList.add('fa-chevron-left');
        icon.style.color = '#6c757d';
    } else {
        // توسع: إظهار الأطفال المباشرين فقط
        directChildRows.forEach(row => {
            row.classList.add('visible');
        });
        icon.classList.remove('fa-chevron-left');
        icon.classList.add('fa-chevron-down');
        icon.style.color = '#007bff';
    }
};

// دالة لإخفاء جميع الأحفاد
function hideAllDescendants(parentRow, parentLevel) {
    let nextRow = parentRow.nextElementSibling;
    
    while (nextRow && nextRow.dataset.level && parseInt(nextRow.dataset.level) > parentLevel) {
        nextRow.classList.remove('visible');
        
        // إذا كان هذا الصف موسعاً، اطويه أيضاً
        const rowAccountId = nextRow.dataset.accountId;
        const rowIcon = document.getElementById(`icon-${rowAccountId}`);
        if (rowIcon && rowIcon.classList.contains('fa-chevron-down')) {
            rowIcon.classList.remove('fa-chevron-down');
            rowIcon.classList.add('fa-chevron-left');
            rowIcon.style.color = '#6c757d';
        }
        
        nextRow = nextRow.nextElementSibling;
    }
}

// تصدير الوظائف للاستخدام العام
window.FinancialUtils = {
    exportData: (format) => window.FinancialEnhanced.exportData(format),
    printReport: () => window.FinancialEnhanced.printReport(),
    updateStats: () => window.FinancialEnhanced.updateStats()
};