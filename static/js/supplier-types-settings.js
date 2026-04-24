// Supplier Types Settings JavaScript

// دالة للحصول على CSRF token
function getCsrfToken() {
    const csrfInput = document.querySelector('[name=csrfmiddlewaretoken]');
    return csrfInput ? csrfInput.value : null;
}

// تهيئة الصفحة
document.addEventListener('DOMContentLoaded', function() {
    // إعداد السحب والإفلات لإعادة الترتيب
    const sortableElement = document.getElementById('sortableTypes');
    if (sortableElement && typeof Sortable !== 'undefined') {
        new Sortable(sortableElement, {
            handle: '.sortable-handle',
            animation: 150,
            onEnd: function(evt) {
                window.reorderTypes();
            }
        });
    }
});

// تنفيذ JavaScript الخاص بالمودال
function executeModalScripts() {
    // البحث عن script tags في المودال وتنفيذها
    const scripts = document.querySelectorAll('#modalContent script');
    scripts.forEach(script => {
        if (script.innerHTML) {
            try {
                eval(script.innerHTML);
            } catch (error) {
                console.error('❌ خطأ في تنفيذ script:', error);
            }
        }
    });
    
    // تحقق من نوع المودال وتنفيذ JavaScript المناسب
    if (document.querySelector('#modalContent #deleteForm')) {
        initializeDeleteModal();
    } else if (document.querySelector('#modalContent #supplierTypeForm')) {
        initializeModalPreview();
    }
}

// تهيئة معاينة المودال
function initializeModalPreview() {
    const modalContent = document.getElementById('modalContent');
    if (!modalContent) {
        console.error('❌ لم يتم العثور على modalContent');
        return;
    }
        
    // الحصول على عناصر النموذج
    const iconField = document.querySelector('#modalContent select[name="icon"]');
    const colorField = document.querySelector('#modalContent input[name="color"]');
    const nameField = document.querySelector('#modalContent input[name="name"]');
    
    // فحص الأزرار
    const iconButtons = document.querySelectorAll('#modalContent .icon-btn');
    const colorButtons = document.querySelectorAll('#modalContent .color-btn');
    
    if (!iconField) {
        return;
    }
    
    // دالة تحديث المعاينة
    function updateModalPreview() {
        const icon = iconField?.value || 'fas fa-truck';
        const color = colorField?.value || '#007bff';
        const name = nameField?.value || 'اسم النوع';
                
        // تحديث جميع عناصر المعاينة
        const previewElements = [
            '#modalContent #selectedIconPreview i',
            '#modalContent #previewIconClass',
            '#modalContent #previewIconClassLarge',
            '#modalContent #previewBadge i'
        ];
        
        previewElements.forEach(selector => {
            const element = document.querySelector(selector);
            if (element) {
                element.className = icon;
            }
        });
        
        // تحديث الألوان
        const colorElements = [
            '#modalContent #previewIconSmall',
            '#modalContent #previewIconLarge',
            '#modalContent #previewBadge',
            '#modalContent #colorPreview'
        ];
        
        colorElements.forEach(selector => {
            const element = document.querySelector(selector);
            if (element) {
                element.style.backgroundColor = color;
            }
        });
        
        // تحديث النصوص
        const textElements = {
            '#modalContent #previewName': name,
            '#modalContent #previewNameLarge': name,
            '#modalContent #previewBadge span': name
        };
        
        Object.entries(textElements).forEach(([selector, text]) => {
            const element = document.querySelector(selector);
            if (element) {
                element.textContent = text;
            }
        });
    }
    
    // إضافة event listeners
    if (iconField) {
        iconField.addEventListener('change', updateModalPreview);
        iconField.addEventListener('input', updateModalPreview);
    }
    
    if (colorField) {
        colorField.addEventListener('change', updateModalPreview);
        colorField.addEventListener('input', updateModalPreview);
    }
    
    if (nameField) {
        nameField.addEventListener('input', updateModalPreview);
    }
    
    // إضافة event listeners للأزرار
    if (iconButtons.length > 0) {
        iconButtons.forEach(btn => {
            btn.addEventListener('click', function(e) {
                e.preventDefault();
                const icon = this.dataset.icon;
                
                if (iconField) {
                    iconField.value = icon;
                    iconButtons.forEach(b => b.classList.remove('selected'));
                    this.classList.add('selected');
                    updateModalPreview();
                }
            });
        });
    }
    
    if (colorButtons.length > 0) {
        colorButtons.forEach(btn => {
            btn.addEventListener('click', function(e) {
                e.preventDefault();
                const color = this.dataset.color;
                
                if (colorField) {
                    colorField.value = color;
                    colorButtons.forEach(b => b.classList.remove('selected'));
                    this.classList.add('selected');
                    updateModalPreview();
                }
            });
        });
    }
    
    // تحديث أولي
    setTimeout(() => {
        updateModalPreview();
        
        if (iconField && iconField.value) {
            const selectedIconBtn = document.querySelector(`#modalContent .icon-btn[data-icon="${iconField.value}"]`);
            if (selectedIconBtn) {
                selectedIconBtn.classList.add('selected');
            }
        }
        
        if (colorField && colorField.value) {
            const selectedColorBtn = document.querySelector(`#modalContent .color-btn[data-color="${colorField.value}"]`);
            if (selectedColorBtn) {
                selectedColorBtn.classList.add('selected');
            }
        }
    }, 100);
}

// تهيئة مودال الحذف
function initializeDeleteModal() {
    const form = document.querySelector('#modalContent #deleteForm');
    const confirmCheckbox = document.querySelector('#modalContent input[name="confirm_delete"]') || 
                           document.querySelector('#modalContent #id_confirm_delete');
    const deleteBtn = document.querySelector('#modalContent #deleteBtn');
    
    if (!confirmCheckbox || !deleteBtn) {
        console.error('❌ لم يتم العثور على عناصر مودال الحذف');
        return;
    }
    
    // تفعيل/إلغاء تفعيل زر الحذف
    confirmCheckbox.addEventListener('change', function() {
        deleteBtn.disabled = !this.checked;
        
        if (this.checked) {
            deleteBtn.classList.remove('btn-outline-danger');
            deleteBtn.classList.add('btn-danger');
        } else {
            deleteBtn.classList.remove('btn-danger');
            deleteBtn.classList.add('btn-outline-danger');
        }
    });
    
    // إرسال النموذج
    if (form) {
        form.addEventListener('submit', function(e) {
            e.preventDefault();
            
            if (!confirmCheckbox.checked) {
                window.showAlert('يرجى تأكيد رغبتك في الحذف', 'warning');
                return;
            }
            
            if (!confirm('هل أنت متأكد تماماً من حذف هذا النوع؟ هذا الإجراء لا يمكن التراجع عنه!')) {
                return;
            }
            
            submitDeleteForm();
        });
    }
    
    function submitDeleteForm() {
        const originalText = deleteBtn.innerHTML;
        deleteBtn.disabled = true;
        deleteBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> جاري الحذف...';
        
        const formData = new FormData(form);
        
        fetch(form.action, {
            method: 'POST',
            body: formData,
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(response => {
            const contentType = response.headers.get('content-type');
            if (contentType && contentType.includes('application/json')) {
                return response.json();
            } else {
                return response.text().then(text => {
                    throw new Error('الخادم أرجع HTML بدلاً من JSON');
                });
            }
        })
        .then(data => {
            if (data.success) {
                window.showAlert(data.message, 'success');
                const modal = bootstrap.Modal.getInstance(document.getElementById('typeModal'));
                modal.hide();
                setTimeout(() => window.location.reload(), 1000);
            } else {
                window.showAlert(data.message || 'حدث خطأ أثناء الحذف', 'danger');
            }
        })
        .catch(error => {
            console.error('❌ خطأ في الاتصال:', error);
            window.showAlert('حدث خطأ في الاتصال', 'danger');
        })
        .finally(() => {
            deleteBtn.disabled = false;
            deleteBtn.innerHTML = originalText;
        });
    }
}

// فتح مودال الإنشاء
window.openCreateModal = function() {
    fetch('/supplier/settings/types/create/', {
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
    })
    .then(response => response.text())
    .then(html => {
        document.getElementById('modalContent').innerHTML = html;
        // تنفيذ الـ scripts المضمنة في المحتوى
        document.querySelectorAll('#modalContent script').forEach(oldScript => {
            const newScript = document.createElement('script');
            newScript.textContent = oldScript.textContent;
            document.head.appendChild(newScript);
            document.head.removeChild(newScript);
        });
        new bootstrap.Modal(document.getElementById('typeModal')).show();
    })
    .catch(err => { if (typeof toastr !== 'undefined') toastr.error('حدث خطأ في تحميل النموذج'); });
};

// تعديل نوع
window.editType = function(id) {
    fetch(`/supplier/settings/types/${id}/edit/`, {
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
    })
    .then(response => response.text())
    .then(html => {
        document.getElementById('modalContent').innerHTML = html;
        document.querySelectorAll('#modalContent script').forEach(oldScript => {
            const newScript = document.createElement('script');
            newScript.textContent = oldScript.textContent;
            document.head.appendChild(newScript);
            document.head.removeChild(newScript);
        });
        new bootstrap.Modal(document.getElementById('typeModal')).show();
    })
    .catch(err => { if (typeof toastr !== 'undefined') toastr.error('حدث خطأ في تحميل النموذج'); });
};

// حذف نوع
window.deleteType = function(id) {
    fetch(`/supplier/settings/types/${id}/delete/`, {
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
    })
    .then(response => response.text())
    .then(html => {
        document.getElementById('modalContent').innerHTML = html;
        document.querySelectorAll('#modalContent script').forEach(oldScript => {
            const newScript = document.createElement('script');
            newScript.textContent = oldScript.textContent;
            document.head.appendChild(newScript);
            document.head.removeChild(newScript);
        });
        new bootstrap.Modal(document.getElementById('typeModal')).show();
    })
    .catch(err => { if (typeof toastr !== 'undefined') toastr.error('حدث خطأ في تحميل النموذج'); });
};



// تبديل الحالة
window.toggleStatus = function(id, isActive) {
    const csrfToken = getCsrfToken();
    if (!csrfToken) {
        window.showAlert('خطأ في الأمان - يرجى إعادة تحميل الصفحة', 'danger');
        return;
    }
    
    fetch(`/supplier/settings/types/${id}/toggle-status/`, {
        method: 'POST',
        headers: {
            'X-Requested-With': 'XMLHttpRequest',
            'X-CSRFToken': csrfToken
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            window.showAlert(data.message, 'success');
        } else {
            window.showAlert(data.message, 'danger');
            event.target.checked = !isActive;
        }
    });
};

// إعادة ترتيب الأنواع
window.reorderTypes = function() {
    const rows = document.querySelectorAll('#sortableTypes tr');
    const typeIds = Array.from(rows).map(row => row.dataset.id);
    
    const csrfToken = getCsrfToken();
    if (!csrfToken) {
        window.showAlert('خطأ في الأمان - يرجى إعادة تحميل الصفحة', 'danger');
        return;
    }
    
    fetch('/supplier/settings/types/reorder/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken
        },
        body: JSON.stringify({
            type_ids: typeIds
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            window.showAlert(data.message, 'success');
        } else {
            window.showAlert(data.message, 'danger');
        }
    });
};

// مزامنة مع النظام القديم
window.syncWithOldSystem = function() {
    if (!confirm('هل تريد مزامنة أنواع الموردين مع النظام القديم؟')) {
        return;
    }
    
    const csrfToken = getCsrfToken();
    if (!csrfToken) {
        window.showAlert('خطأ في الأمان - يرجى إعادة تحميل الصفحة', 'danger');
        return;
    }
    
    fetch('/supplier/settings/types/sync/', {
        method: 'POST',
        headers: {
            'X-Requested-With': 'XMLHttpRequest',
            'X-CSRFToken': csrfToken
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            window.showAlert(data.message, 'success');
            setTimeout(() => location.reload(), 1000);
        } else {
            window.showAlert(data.message, 'danger');
        }
    });
};

// عرض تنبيه
window.showAlert = function(message, type) {
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
    alertDiv.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    document.body.appendChild(alertDiv);
    
    setTimeout(() => {
        if (alertDiv.parentNode) {
            alertDiv.remove();
        }
    }, 5000);
};
