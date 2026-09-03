/**
 * محرك إدارة العمليات لإعدادات تسعير الطباعة (Unified Settings CRUD Engine)
 * يتوافق مع معايير AGENTS.md (البند 8 والبند 10)
 */

window.SettingsCRUD = (function () {
    'use strict';

    // مساعدة للحصول على CSRF Token
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    const csrftoken = getCookie('csrftoken') || (document.querySelector('[name=csrfmiddlewaretoken]') ? document.querySelector('[name=csrfmiddlewaretoken]').value : '');

    // إشعار موحد
    function notify(message, type = 'info', title = '') {
        if (typeof window.showNotification === 'function') {
            window.showNotification(message, type, title);
        } else if (typeof toastr !== 'undefined' && toastr[type]) {
            toastr[type](message, title);
        } else {
            console.log(`[${type.toUpperCase()}] ${message}`);
        }
    }

    // فتح مودال الإضافة
    function openCreateModal(url, modalId = '#formModal') {
        const modalEl = document.querySelector(modalId);
        if (!modalEl) return;
        const modalBody = modalEl.querySelector('.modal-body') || modalEl;
        
        // إظهار حالة التحميل
        modalBody.innerHTML = `
            <div class="text-center py-5">
                <div class="spinner-border text-primary" role="status">
                    <span class="visually-hidden">جاري التحميل...</span>
                </div>
                <div class="mt-2 text-muted">جاري تحميل النموذج...</div>
            </div>
        `;
        
        const bsModal = bootstrap.Modal.getOrCreateInstance(modalEl);
        bsModal.show();

        fetch(url, {
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
        .then(response => response.text())
        .then(html => {
            const modalContent = modalEl.querySelector('.modal-content');
            if (modalContent) {
                modalContent.innerHTML = html;
                initModalPlugins(modalEl);
            }
        })
        .catch(err => {
            notify('حدث خطأ أثناء تحميل النموذج', 'error');
            bsModal.hide();
        });
    }

    // فتح مودال التعديل
    function openEditModal(url, modalId = '#formModal') {
        openCreateModal(url, modalId);
    }

    // فتح مودال الحذف
    function openDeleteModal(url, itemName, modalId = '#deleteModal') {
        const modalEl = document.querySelector(modalId);
        if (!modalEl) return;
        
        const nameEl = modalEl.querySelector('#deleteItemName') || modalEl.querySelector('.delete-item-name');
        if (nameEl) {
            nameEl.textContent = itemName;
        }

        const formEl = modalEl.querySelector('form');
        if (formEl) {
            formEl.action = url;
            formEl.onsubmit = function (e) {
                e.preventDefault();
                submitDelete(url, formEl, modalEl);
            };
        }

        const bsModal = bootstrap.Modal.getOrCreateInstance(modalEl);
        bsModal.show();
    }

    // إرسال الحذف
    function submitDelete(url, formEl, modalEl) {
        const submitBtn = formEl.querySelector('button[type="submit"]') || formEl.querySelector('.btn-danger');
        const origText = submitBtn ? submitBtn.innerHTML : '';
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> جاري الحذف...';
        }

        fetch(url, {
            method: 'POST',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': csrftoken
            }
        })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                const bsModal = bootstrap.Modal.getInstance(modalEl);
                if (bsModal) bsModal.hide();
                notify(data.message || 'تم الحذف بنجاح', 'success');
                // الالتزام بالبند 10: تأخير 3100ms
                setTimeout(() => {
                    window.location.reload();
                }, 3100);
            } else {
                notify(data.message || 'تعذر الحذف، قد يكون العنصر مرتبطاً ببيانات أخرى', 'error');
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = origText;
                }
            }
        })
        .catch(err => {
            notify('حدث خطأ في الاتصال بالخادم', 'error');
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.innerHTML = origText;
            }
        });
    }

    // إرسال النموذج (Submit Form)
    function submitForm(formEl, modalId = '#formModal') {
        if (!formEl) return false;
        
        const modalEl = document.querySelector(modalId);
        const submitBtn = formEl.querySelector('button[type="submit"]') || (modalEl ? modalEl.querySelector('.btn-save') : null);
        const origText = submitBtn ? submitBtn.innerHTML : '';

        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> جاري الحفظ...';
        }

        const formData = new FormData(formEl);

        fetch(formEl.action, {
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
            }
            return response.text().then(html => ({ success: false, html: html }));
        })
        .then(data => {
            if (data.success) {
                if (modalEl) {
                    const bsModal = bootstrap.Modal.getInstance(modalEl);
                    if (bsModal) bsModal.hide();
                }
                notify(data.message || 'تم الحفظ بنجاح', 'success');
                // الالتزام بالبند 10: تأخير 3100ms لاكتمال حركة Toastr
                setTimeout(() => {
                    window.location.reload();
                }, 3100);
            } else {
                if (data.html && modalEl) {
                    const modalContent = modalEl.querySelector('.modal-content');
                    if (modalContent) {
                        modalContent.innerHTML = data.html;
                        initModalPlugins(modalEl);
                    }
                }
                notify(data.message || 'يرجى مراجعة وتصحيح الأخطاء في النموذج', 'error');
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = origText;
                }
            }
        })
        .catch(err => {
            notify('حدث خطأ أثناء حفظ البيانات', 'error');
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.innerHTML = origText;
            }
        });

        return false;
    }

    // تهيئة الـ Plugins داخل المودال (Select2 وغيرها)
    function initModalPlugins(modalEl) {
        if (!modalEl) return;
        
        // Select2 inside modal with dropdownParent per Rule 8
        if (typeof $ !== 'undefined' && $.fn.select2) {
            $(modalEl).find('.select2-modal').each(function () {
                $(this).select2({
                    theme: 'bootstrap-5',
                    dir: 'rtl',
                    language: 'ar',
                    dropdownParent: $(modalEl)
                });
            });
        }
    }

    return {
        openCreateModal,
        openEditModal,
        openDeleteModal,
        submitForm,
        submitDelete,
        initModalPlugins,
        notify
    };
})();
