/**
 * نظام إدارة الأدوار والصلاحيات
 * MWHEBA ERP - User Roles Management
 */

// دالة عامة لعرض الرسائل
function showMessage(message, type = 'success') {
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
    alertDiv.role = 'alert';
    alertDiv.innerHTML = `
        <i class="fas fa-${type === 'success' ? 'check-circle' : 'exclamation-circle'} me-2"></i>
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    const container = document.querySelector('.container-fluid');
    container.insertBefore(alertDiv, container.firstChild);
    
    // إزالة الرسالة بعد 5 ثوان
    setTimeout(() => {
        alertDiv.remove();
    }, 5000);
}

// دالة لتحديث عداد الصلاحيات المحددة
function updatePermissionCount() {
    const checkedCount = document.querySelectorAll('.permission-checkbox:checked:not(:disabled)').length;
    const totalCount = document.querySelectorAll('.permission-checkbox:not(:disabled)').length;
    
    const countElement = document.getElementById('permissionCount');
    if (countElement) {
        countElement.textContent = `${checkedCount} من ${totalCount}`;
    }
}

// دالة للتحقق من صحة النموذج
function validateRoleForm() {
    const name = document.querySelector('input[name="name"]');
    const displayName = document.querySelector('input[name="display_name"]');
    
    if (!name || !name.value.trim()) {
        showMessage('يرجى إدخال اسم الدور', 'danger');
        name.focus();
        return false;
    }
    
    if (!displayName || !displayName.value.trim()) {
        showMessage('يرجى إدخال الاسم المعروض', 'danger');
        displayName.focus();
        return false;
    }
    
    // التحقق من أن الاسم بالإنجليزية فقط
    const namePattern = /^[a-z_]+$/;
    if (!namePattern.test(name.value)) {
        showMessage('اسم الدور يجب أن يكون بالإنجليزية الصغيرة فقط (a-z و _)', 'danger');
        name.focus();
        return false;
    }
    
    return true;
}

// دالة لتصدير الصلاحيات المحددة
function exportSelectedPermissions() {
    const selected = [];
    document.querySelectorAll('.permission-checkbox:checked').forEach(cb => {
        const label = cb.nextElementSibling;
        const permName = label.querySelector('.permission-name').textContent;
        const permCode = label.querySelector('.text-muted').textContent;
        selected.push({ name: permName, code: permCode });
    });
    
    const dataStr = JSON.stringify(selected, null, 2);
    const dataBlob = new Blob([dataStr], { type: 'application/json' });
    const url = URL.createObjectURL(dataBlob);
    
    const link = document.createElement('a');
    link.href = url;
    link.download = 'permissions.json';
    link.click();
    
    URL.revokeObjectURL(url);
    showMessage('تم تصدير الصلاحيات بنجاح', 'success');
}

// دالة لنسخ دور
function copyRole(roleId) {
    if (confirm('هل تريد نسخ هذا الدور؟')) {
        // يمكن إضافة منطق النسخ هنا
        showMessage('جاري نسخ الدور...', 'info');
    }
}

// دالة لطباعة الصلاحيات
function printPermissions() {
    window.print();
}

// دالة للتحقق من التغييرات غير المحفوظة
function checkUnsavedChanges() {
    const form = document.getElementById('roleForm');
    if (!form) return false;
    
    let hasChanges = false;
    const formData = new FormData(form);
    
    // يمكن إضافة منطق للتحقق من التغييرات هنا
    
    return hasChanges;
}

// تحذير عند مغادرة الصفحة مع تغييرات غير محفوظة
window.addEventListener('beforeunload', function(e) {
    if (checkUnsavedChanges()) {
        e.preventDefault();
        e.returnValue = 'لديك تغييرات غير محفوظة. هل تريد المغادرة؟';
        return e.returnValue;
    }
});

// دالة لتحميل الصلاحيات بشكل ديناميكي (AJAX)
async function loadPermissions(appLabel) {
    try {
        const response = await fetch(`/users/api/permissions/?app=${appLabel}`);
        const data = await response.json();
        
        if (data.success) {
            // تحديث الصلاحيات في الواجهة
            updatePermissionsUI(data.permissions);
        }
    } catch (error) {
        console.error('خطأ في تحميل الصلاحيات:', error);
        showMessage('حدث خطأ في تحميل الصلاحيات', 'danger');
    }
}

// دالة لتحديث واجهة الصلاحيات
function updatePermissionsUI(permissions) {
    // يمكن إضافة منطق لتحديث الواجهة هنا
}

// دالة لفلترة الصلاحيات حسب النوع
function filterPermissionsByType(type) {
    const types = {
        'view': 'view_',
        'add': 'add_',
        'change': 'change_',
        'delete': 'delete_'
    };
    
    const prefix = types[type];
    if (!prefix) return;
    
    document.querySelectorAll('.permission-item').forEach(item => {
        const codename = item.querySelector('.text-muted').textContent;
        item.style.display = codename.startsWith(prefix) ? '' : 'none';
    });
}

// دالة لإعادة تعيين الفلاتر
function resetFilters() {
    document.querySelectorAll('.permission-item').forEach(item => {
        item.style.display = '';
    });
    document.getElementById('permissionSearch').value = '';
}

// إضافة shortcuts للوحة المفاتيح
document.addEventListener('keydown', function(e) {
    // Ctrl+S للحفظ
    if (e.ctrlKey && e.key === 's') {
        e.preventDefault();
        const form = document.getElementById('roleForm');
        if (form) {
            if (validateRoleForm()) {
                form.submit();
            }
        }
    }
    
    // Ctrl+F للبحث
    if (e.ctrlKey && e.key === 'f') {
        e.preventDefault();
        const searchInput = document.getElementById('permissionSearch');
        if (searchInput) {
            searchInput.focus();
        }
    }
    
    // Escape لإلغاء
    if (e.key === 'Escape') {
        const searchInput = document.getElementById('permissionSearch');
        if (searchInput && searchInput.value) {
            searchInput.value = '';
            resetFilters();
        }
    }
});

// تهيئة عند تحميل الصفحة
document.addEventListener('DOMContentLoaded', function() {
    console.log('نظام إدارة الأدوار جاهز');
    
    // إضافة مستمعات الأحداث
    const form = document.getElementById('roleForm');
    if (form) {
        form.addEventListener('submit', function(e) {
            if (!validateRoleForm()) {
                e.preventDefault();
            }
        });
    }
    
    // تحديث عداد الصلاحيات عند التغيير
    document.querySelectorAll('.permission-checkbox').forEach(cb => {
        cb.addEventListener('change', updatePermissionCount);
    });
    
    // تهيئة العداد
    updatePermissionCount();
});

// تصدير الدوال للاستخدام العام
window.RolesManager = {
    showMessage,
    updatePermissionCount,
    validateRoleForm,
    exportSelectedPermissions,
    copyRole,
    printPermissions,
    filterPermissionsByType,
    resetFilters
};
