/**
 * ملف JavaScript الخاص بإدارة المخزون في التطبيق
 */

document.addEventListener('DOMContentLoaded', function() {

    /**
     * تهيئة جدول DataTable لعرض المخزون (بدون أزرار تصدير)
     */
    function initInventoryTable() {
        const table = document.querySelector('#inventory-table');
        if (table) {
            initDataTableArabic(table, {
                pageLength: 25,
                responsive: true,
                searching: false, // إزالة خانة البحث
                dom: 'rtip' // إزالة أزرار التصدير والبحث
            });
        }
    }

    /**
     * تهيئة جدول DataTable لعرض حركات المخزون
     */
    function initMovementsTable() {
        const table = document.querySelector('#movements-table');
        if (table) {
            initDataTableArabic(table, {
                order: [[1, 'desc']] // ترتيب حسب تاريخ الحركة (تنازلي)
            });
        }
    }

    /**
     * تهيئة جدول DataTable لعرض المخازن
     */
    function initWarehousesTable() {
        const table = document.querySelector('#warehouses-table');
        if (table) {
            initDataTableArabic(table);
        }
        
        // إرسال نموذج التصفية عند تغيير حالة المخزن
        document.querySelectorAll('input[name="status"]').forEach(radio => {
            radio.addEventListener('change', function() {
                document.getElementById('filter-form')?.submit();
            });
        });
    }

    /**
     * تهيئة حقول Select2 للاختيارات
     */
    function initSelectFields() {
        $('select.select2-field').each(function() {
            const field = $(this);
            field.select2({
                theme: 'bootstrap-5',
                placeholder: field.data('placeholder') || 'اختر...',
                allowClear: true,
                dir: 'rtl',
                language: 'ar'
            });
        });
    }

    /**
     * إضافة حركة مخزون (إضافة/سحب/تعديل)
     * @param {HTMLFormElement} form نموذج حركة المخزون
     * @param {string} url مسار API لإضافة الحركة
     * @param {Function} callback دالة يتم استدعاؤها بعد نجاح العملية
     */
    function addStockMovement(form, url, callback) {
        if (!form) {
            showAlert('لم يتم العثور على النموذج', 'danger');
            return;
        }

        const formData = new FormData(form);
        
        // تحقق من صحة البيانات
        const product = formData.get('product_id');
        const quantity = formData.get('quantity');
        const movementType = formData.get('movement_type');
        const warehouse = formData.get('warehouse_id');
        
        if (!product || !quantity || !movementType || !warehouse) {
            showAlert('يرجى ملء جميع الحقول المطلوبة', 'danger');
            return;
        }
        
        // التحقق من أن الكمية رقم موجب
        if (isNaN(quantity) || parseInt(quantity) <= 0) {
            showAlert('يجب أن تكون الكمية رقمًا موجبًا', 'danger');
            return;
        }
        
        // عند التحويل، يجب تحديد المخزن المستلم
        if (movementType === 'transfer' && !formData.get('destination_warehouse')) {
            showAlert('يرجى تحديد المخزن المستلم للتحويل', 'danger');
            return;
        }

        // التحقق من أن المخزن المصدر والمخزن المستلم ليسا نفس المخزن
        if (movementType === 'transfer' && formData.get('warehouse_id') === formData.get('destination_warehouse')) {
            showAlert('لا يمكن التحويل إلى نفس المخزن المصدر', 'danger');
            return;
        }
        
        // إظهار مؤشر تحميل
        const saveBtn = document.querySelector('#save-movement-btn');
        let originalText = '';
        
        if (saveBtn) {
            originalText = saveBtn.innerHTML;
            saveBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> جاري الحفظ...';
            saveBtn.disabled = true;
        }
        
        // التحقق من وجود رمز CSRF
        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
        if (!csrfToken) {
            console.error('CSRF token not found');
            showAlert('خطأ في الأمان: رمز CSRF غير موجود', 'danger');
            
            // إعادة زر الحفظ إلى حالته الأصلية
            if (saveBtn) {
                saveBtn.innerHTML = originalText;
                saveBtn.disabled = false;
            }
            return;
        }
        
        // إرسال الطلب
        fetch(url, {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrfToken
            },
            body: formData
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`خطأ في الطلب! الحالة: ${response.status} - ${response.statusText}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.success) {
                showAlert(data.message || 'تم تنفيذ العملية بنجاح', 'success');
                
                // استدعاء دالة رد الاتصال إذا كانت موجودة
                if (typeof callback === 'function') {
                    callback(data);
                }
                
                // إعادة تعيين النموذج
                form.reset();
                
                // إعادة تحميل الصفحة بعد فترة قصيرة
                setTimeout(() => {
                    window.location.reload();
                }, 1500);
            } else {
                showAlert(data.error || 'حدث خطأ أثناء تنفيذ العملية', 'danger');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showAlert('حدث خطأ في الاتصال بالخادم: ' + error.message, 'danger');
        })
        .finally(() => {
            // إعادة زر الحفظ إلى حالته الأصلية
            if (saveBtn) {
                saveBtn.innerHTML = originalText;
                saveBtn.disabled = false;
            }
        });
    }

    /**
     * عرض رسالة تنبيه
     * @param {string} message نص الرسالة
     * @param {string} type نوع التنبيه (success, danger, warning, info)
     */
    function showAlert(message, type = 'info') {
        const alertContainer = document.querySelector('#alert-container');
        if (!alertContainer) {
            // إنشاء حاوية للتنبيهات إذا لم تكن موجودة
            const container = document.createElement('div');
            container.id = 'alert-container';
            container.style.position = 'fixed';
            container.style.top = '20px';
            container.style.right = '20px';
            container.style.zIndex = '9999';
            document.body.appendChild(container);
        }
        
        const alertElement = document.createElement('div');
        alertElement.className = `alert alert-${type} alert-dismissible fade show`;
        alertElement.role = 'alert';
        alertElement.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        `;
        
        document.querySelector('#alert-container').appendChild(alertElement);
        
        // إزالة التنبيه بعد 5 ثوانٍ
        setTimeout(() => {
            alertElement.classList.remove('show');
            setTimeout(() => {
                alertElement.remove();
            }, 150);
        }, 5000);
    }

    /**
     * عرض تنبيه للمخزون المنخفض
     * @param {Array} lowStockItems عناصر المخزون المنخفض
     */
    function showLowStockAlert(lowStockItems) {
        if (lowStockItems && lowStockItems.length > 0) {
            const message = `
                <h6>تنبيه: مخزون منخفض</h6>
                <p>يوجد ${lowStockItems.length} منتج بمخزون منخفض.</p>
                <a href="/product/low-stock/" class="btn btn-sm btn-warning">عرض التفاصيل</a>
            `;
            showAlert(message, 'warning');
        }
    }

    /**
     * استيراد بيانات المخزون من ملف
     * @param {File} file ملف البيانات (CSV/Excel)
     */
    function importInventory(file) {
        if (!file) {
            showAlert('الرجاء اختيار ملف صالح', 'danger');
            return;
        }
        
        const formData = new FormData();
        formData.append('file', file);
        formData.append('csrfmiddlewaretoken', document.querySelector('[name=csrfmiddlewaretoken]')?.value || '');
        
        // إظهار مؤشر تحميل
        showAlert('جاري استيراد البيانات...', 'info');
        
        fetch('/product/api/import-inventory/', {
            method: 'POST',
            body: formData
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! Status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.success) {
                showAlert(`تم استيراد ${data.imported_count} سجل بنجاح`, 'success');
                setTimeout(() => {
                    window.location.reload();
                }, 2000);
            } else {
                showAlert(data.error || 'حدث خطأ أثناء استيراد البيانات', 'danger');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showAlert('حدث خطأ في الاتصال بالخادم: ' + error.message, 'danger');
        });
    }

    /**
     * إنشاء مؤشر المخزون
     * @param {number} current المخزون الحالي
     * @param {number} min الحد الأدنى للمخزون
     * @param {number} max الحد الأقصى للمخزون
     * @param {HTMLElement} container عنصر HTML لعرض المؤشر
     */
    function createStockIndicator(current, min, max, container) {
        if (!container) return;
        
        // تحديد لون وحالة المؤشر
        let color, percentage;
        
        if (current <= 0) {
            color = 'bg-danger';
            percentage = 0;
        } else if (current < min) {
            color = 'bg-warning';
            percentage = (current / min) * 100;
        } else if (current > max) {
            color = 'bg-info';
            percentage = 100;
        } else {
            color = 'bg-success';
            percentage = (current / max) * 100;
        }
        
        // إنشاء عنصر المؤشر
        container.innerHTML = `
            <div class="stock-level">
                <div class="progress-bar ${color}" style="width: ${percentage}%"></div>
            </div>
        `;
    }

    // تهيئة العناصر عند تحميل الصفحة
    initInventoryTable();
    initMovementsTable();
    initWarehousesTable();
    initSelectFields();
    
    // الاستماع لأحداث النقر على أزرار حركات المخزون
    document.addEventListener('click', function(event) {
        // زر حفظ حركة مخزون
        if (event.target.matches('#save-movement-btn') || event.target.closest('#save-movement-btn')) {
            const form = document.querySelector('#stock-movement-form');
            addStockMovement(form, '/product/api/stock-movements/add/', function() {
                // إعادة تحميل الصفحة بعد نجاح الإضافة
                location.reload();
            });
        }
        
        // زر تصدير البيانات CSV
        if (event.target.matches('#export-csv') || event.target.closest('#export-csv')) {
            const currentUrl = window.location.search;
            window.location.href = "/product/api/stock-movements/export/?format=csv" + 
                (currentUrl ? currentUrl.replace('?', '&') : '');
        }
        
        // زر تصدير البيانات PDF
        if (event.target.matches('#export-pdf') || event.target.closest('#export-pdf')) {
            const currentUrl = window.location.search;
            window.location.href = "/product/api/stock-movements/export/?format=pdf" + 
                (currentUrl ? currentUrl.replace('?', '&') : '');
        }
        
        // زر طباعة التقرير
        if (event.target.matches('#print-report') || event.target.closest('#print-report')) {
            window.print();
        }
        
        // زر استيراد المخزون
        if (event.target.matches('#import-inventory-btn') || event.target.closest('#import-inventory-btn')) {
            document.querySelector('#import-file')?.click();
        }
    });
    
    // الاستماع لتغيير ملف الاستيراد
    const importFileInput = document.querySelector('#import-file');
    if (importFileInput) {
        importFileInput.addEventListener('change', function() {
            if (this.files.length > 0) {
                importInventory(this.files[0]);
            }
        });
    }
    
    // تحديث مؤشرات المخزون
    document.querySelectorAll('[data-stock-indicator]').forEach(container => {
        const current = parseInt(container.dataset.current) || 0;
        const min = parseInt(container.dataset.min) || 0;
        const max = parseInt(container.dataset.max) || 100;
        createStockIndicator(current, min, max, container);
    });
    
    // إظهار تنبيه المخزون المنخفض
    const lowStockItems = window.lowStockItems || [];
    showLowStockAlert(lowStockItems);
}); 