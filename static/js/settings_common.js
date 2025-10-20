/**
 * JavaScript مشترك لصفحات الإعدادات
 * يحتوي على دوال مشتركة لمعالجة المودالز والنماذج
 */

/**
 * فتح مودال الإنشاء
 * @param {string} createUrl - رابط صفحة الإنشاء
 */
function openCreateModal(createUrl) {
    fetch(createUrl)
        .then(response => response.text())
        .then(html => {
            document.getElementById('modalContent').innerHTML = html;
            new bootstrap.Modal(document.getElementById('formModal')).show();
        })
        .catch(error => {
            console.error('Error loading create modal:', error);
            alert('حدث خطأ أثناء تحميل نموذج الإضافة');
        });
}

/**
 * فتح مودال التعديل
 * @param {string} editUrl - رابط صفحة التعديل
 */
function openEditModal(editUrl) {
    fetch(editUrl)
        .then(response => response.text())
        .then(html => {
            document.getElementById('modalContent').innerHTML = html;
            new bootstrap.Modal(document.getElementById('formModal')).show();
        })
        .catch(error => {
            console.error('Error loading edit modal:', error);
            alert('حدث خطأ أثناء تحميل نموذج التعديل');
        });
}

/**
 * فتح مودال الحذف
 * @param {string} deleteUrl - رابط صفحة الحذف
 */
function openDeleteModal(deleteUrl) {
    fetch(deleteUrl)
        .then(response => response.text())
        .then(html => {
            document.getElementById('deleteModalContent').innerHTML = html;
            new bootstrap.Modal(document.getElementById('deleteModal')).show();
        })
        .catch(error => {
            console.error('Error loading delete modal:', error);
            alert('حدث خطأ أثناء تحميل نموذج الحذف');
        });
}

/**
 * إرسال نموذج عبر AJAX
 * @param {string} formId - معرف النموذج
 */
function submitForm(formId) {
    const form = document.getElementById(formId);
    if (!form) {
        console.error('Form not found:', formId);
        return;
    }

    const formData = new FormData(form);
    const submitBtn = form.querySelector('button[type="submit"], input[type="submit"]');
    const originalBtnText = submitBtn ? submitBtn.innerHTML : '';
    
    // تعطيل الزر وإظهار مؤشر التحميل
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> جاري المعالجة...';
    }
    
    fetch(form.action, {
        method: 'POST',
        body: formData,
        headers: {
            'X-Requested-With': 'XMLHttpRequest',
            'X-CSRFToken': formData.get('csrfmiddlewaretoken')
        }
    })
    .then(response => {
        // التحقق من نوع المحتوى
        const contentType = response.headers.get('content-type');
        if (contentType && contentType.includes('application/json')) {
            return response.json();
        } else {
            // إذا لم يكن JSON، فهناك خطأ في الخادم
            throw new Error('Server returned HTML instead of JSON. Check server logs for errors.');
        }
    })
    .then(data => {
        if (data.success) {
            // إغلاق المودال
            const modal = bootstrap.Modal.getInstance(document.querySelector('.modal.show'));
            if (modal) modal.hide();
            
            // عرض رسالة النجاح
            if (data.message) {
                showSuccessMessage(data.message);
            }
            
            // إعادة تحميل الصفحة بعد تأخير قصير
            setTimeout(() => {
                location.reload();
            }, 500);
        } else {
            // عرض الأخطاء
            if (data.errors) {
                showFormErrors(data.errors);
            } else {
                alert('حدث خطأ غير متوقع');
            }
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('حدث خطأ أثناء معالجة الطلب. يرجى المحاولة مرة أخرى.');
    })
    .finally(() => {
        // إعادة تفعيل الزر
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalBtnText;
        }
    });
}

/**
 * عرض رسالة نجاح
 * @param {string} message - نص الرسالة
 */
function showSuccessMessage(message) {
    // إنشاء عنصر التنبيه
    const alertDiv = document.createElement('div');
    alertDiv.className = 'alert alert-success alert-dismissible fade show position-fixed';
    alertDiv.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
    alertDiv.innerHTML = `
        <i class="fas fa-check-circle me-2"></i>
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    // إضافة التنبيه للصفحة
    document.body.appendChild(alertDiv);
    
    // إزالة التنبيه تلقائياً بعد 3 ثوانٍ
    setTimeout(() => {
        if (alertDiv.parentNode) {
            alertDiv.remove();
        }
    }, 3000);
}

/**
 * عرض أخطاء النموذج
 * @param {Object} errors - كائن الأخطاء
 */
function showFormErrors(errors) {
    // إزالة الأخطاء السابقة
    document.querySelectorAll('.invalid-feedback').forEach(el => el.remove());
    document.querySelectorAll('.is-invalid').forEach(el => el.classList.remove('is-invalid'));
    
    // عرض الأخطاء الجديدة
    for (const [fieldName, fieldErrors] of Object.entries(errors)) {
        const field = document.querySelector(`[name="${fieldName}"]`);
        if (field) {
            field.classList.add('is-invalid');
            
            // إنشاء عنصر عرض الخطأ
            const errorDiv = document.createElement('div');
            errorDiv.className = 'invalid-feedback';
            errorDiv.textContent = Array.isArray(fieldErrors) ? fieldErrors.join(', ') : fieldErrors;
            
            // إضافة الخطأ بعد الحقل
            field.parentNode.appendChild(errorDiv);
        }
    }
    
    // التركيز على أول حقل يحتوي على خطأ
    const firstErrorField = document.querySelector('.is-invalid');
    if (firstErrorField) {
        firstErrorField.focus();
    }
}

/**
 * تأكيد الحذف
 * @param {string} itemName - اسم العنصر المراد حذفه
 * @param {Function} deleteCallback - دالة الحذف
 */
function confirmDelete(itemName, deleteCallback) {
    if (confirm(`هل أنت متأكد من حذف "${itemName}"؟\n\nهذا الإجراء لا يمكن التراجع عنه.`)) {
        deleteCallback();
    }
}

// تهيئة الأحداث عند تحميل الصفحة
document.addEventListener('DOMContentLoaded', function() {
    // إضافة معالج للنماذج التي تحتوي على data-ajax="true"
    document.addEventListener('submit', function(e) {
        const form = e.target;
        if (form.dataset.ajax === 'true') {
            e.preventDefault();
            submitForm(form.id);
        }
    });
    
    // إضافة معالج لأزرار الحذف
    document.addEventListener('click', function(e) {
        if (e.target.matches('[data-action="delete"]')) {
            e.preventDefault();
            const deleteUrl = e.target.dataset.url;
            const itemName = e.target.dataset.name || 'هذا العنصر';
            
            confirmDelete(itemName, () => {
                openDeleteModal(deleteUrl);
            });
        }
    });
});
