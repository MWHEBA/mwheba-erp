/**
 * SweetAlert للتأكيد على إلغاء الترحيل
 * يتم استخدامه في جميع أنحاء النظام
 */

// دالة عامة لإظهار تأكيد إلغاء الترحيل
function confirmUnpost(url, title = 'إلغاء الترحيل', text = 'هل أنت متأكد من إلغاء ترحيل هذا العنصر؟') {
    Swal.fire({
        title: title,
        text: text,
        icon: 'warning',
        showCancelButton: true,
        confirmButtonColor: '#f0ad4e',
        cancelButtonColor: '#6c757d',
        confirmButtonText: '<i class="fas fa-undo me-1"></i> نعم، إلغاء الترحيل',
        cancelButtonText: '<i class="fas fa-times me-1"></i> إلغاء',
        reverseButtons: true,
        customClass: {
            confirmButton: 'btn btn-warning ms-2',
            cancelButton: 'btn btn-secondary'
        },
        buttonsStyling: false,
        focusCancel: true
    }).then((result) => {
        if (result.isConfirmed) {
            // إظهار مؤشر التحميل
            Swal.fire({
                title: 'جاري إلغاء الترحيل...',
                text: 'يرجى الانتظار',
                icon: 'info',
                allowOutsideClick: false,
                allowEscapeKey: false,
                showConfirmButton: false,
                didOpen: () => {
                    Swal.showLoading();
                }
            });
            
            // الانتقال للرابط
            window.location.href = url;
        }
    });
}

// دالة خاصة لإلغاء ترحيل الدفعات
function confirmUnpostPayment(url) {
    confirmUnpost(
        url,
        'إلغاء ترحيل الدفعة',
        'سيتم حذف القيد المحاسبي المرتبط وتحديث الأرصدة. هل تريد المتابعة؟'
    );
}

// دالة خاصة لإلغاء ترحيل القيود المحاسبية
function confirmUnpostJournalEntry(url) {
    confirmUnpost(
        url,
        'إلغاء ترحيل القيد المحاسبي',
        'سيتم إلغاء تأثير هذا القيد على الأرصدة. هل تريد المتابعة؟'
    );
}

// دالة عامة لإظهار تأكيد الترحيل
function confirmPost(url, title = 'ترحيل العنصر', text = 'هل أنت متأكد من ترحيل هذا العنصر؟') {
    Swal.fire({
        title: title,
        text: text,
        icon: 'question',
        showCancelButton: true,
        confirmButtonColor: '#198754',
        cancelButtonColor: '#6c757d',
        confirmButtonText: '<i class="fas fa-check me-1"></i> نعم، ترحيل',
        cancelButtonText: '<i class="fas fa-times me-1"></i> إلغاء',
        reverseButtons: true,
        customClass: {
            confirmButton: 'btn btn-success ms-2',
            cancelButton: 'btn btn-secondary'
        },
        buttonsStyling: false,
        focusCancel: true
    }).then((result) => {
        if (result.isConfirmed) {
            // إظهار مؤشر التحميل
            Swal.fire({
                title: 'جاري الترحيل...',
                text: 'يرجى الانتظار',
                icon: 'info',
                allowOutsideClick: false,
                allowEscapeKey: false,
                showConfirmButton: false,
                didOpen: () => {
                    Swal.showLoading();
                }
            });
            
            // الانتقال للرابط
            window.location.href = url;
        }
    });
}

// دالة خاصة لترحيل الدفعات
function confirmPostPayment(url) {
    confirmPost(
        url,
        'ترحيل الدفعة',
        'سيتم إنشاء القيد المحاسبي وتحديث الأرصدة. هل تريد المتابعة؟'
    );
}

// دالة خاصة لترحيل القيود المحاسبية
function confirmPostJournalEntry(url) {
    confirmPost(
        url,
        'ترحيل القيد المحاسبي',
        'سيتم تطبيق تأثير هذا القيد على الأرصدة. هل تريد المتابعة؟'
    );
}

// تفعيل SweetAlert عند تحميل الصفحة
document.addEventListener('DOMContentLoaded', function() {
    initUnpostAlerts();
});

// دالة التهيئة الرئيسية
function initUnpostAlerts() {
    // معالجة أزرار ترحيل الدفعات
    document.querySelectorAll('a[href*="post_payment"]:not(.post-processed)').forEach(function(link) {
        link.classList.add('post-processed');
        link.addEventListener('click', function(e) {
            e.preventDefault();
            confirmPostPayment(this.href);
        });
    });
    
    // معالجة أزرار ترحيل القيود المحاسبية
    document.querySelectorAll('a[href*="journal"][href*="post"]:not(.post-processed), a[href*="post"][href*="journal"]:not(.post-processed)').forEach(function(link) {
        link.classList.add('post-processed');
        link.addEventListener('click', function(e) {
            e.preventDefault();
            confirmPostJournalEntry(this.href);
        });
    });
    
    // معالجة أي أزرار أخرى تحتوي على "post" في الرابط (ما عدا unpost)
    document.querySelectorAll('a[href*="/post"]:not([href*="unpost"]):not([href*="post_payment"]):not(.post-processed)').forEach(function(link) {
        if (!link.href.includes('post_payment') && !link.href.includes('journal') && !link.href.includes('unpost')) {
            link.classList.add('post-processed');
            link.addEventListener('click', function(e) {
                e.preventDefault();
                if (link.href.includes('journal')) {
                    confirmPostJournalEntry(this.href);
                } else {
                    confirmPost(this.href);
                }
            });
        }
    });
    
    // معالجة أزرار إلغاء ترحيل الدفعات
    document.querySelectorAll('a[href*="unpost_payment"]:not(.unpost-processed)').forEach(function(link) {
        link.classList.add('unpost-processed');
        link.addEventListener('click', function(e) {
            e.preventDefault();
            confirmUnpostPayment(this.href);
        });
    });
    
    // معالجة أزرار إلغاء ترحيل القيود المحاسبية
    document.querySelectorAll('a[href*="journal"][href*="unpost"]:not(.unpost-processed), a[href*="unpost"][href*="journal"]:not(.unpost-processed)').forEach(function(link) {
        link.classList.add('unpost-processed');
        link.addEventListener('click', function(e) {
            e.preventDefault();
            confirmUnpostJournalEntry(this.href);
        });
    });
    
    // معالجة أي أزرار أخرى تحتوي على "unpost" في الرابط
    document.querySelectorAll('a[href*="unpost"]:not([href*="unpost_payment"]):not(.unpost-processed)').forEach(function(link) {
        // تجاهل الروابط التي تم معالجتها بالفعل
        if (!link.href.includes('unpost_payment') && !link.href.includes('journal')) {
            link.classList.add('unpost-processed');
            link.addEventListener('click', function(e) {
                e.preventDefault();
                confirmUnpost(this.href);
            });
        }
    });
    
    // معالجة الأزرار التي تحتوي على class خاص للترحيل
    document.querySelectorAll('.btn-post:not(.post-processed), .post-btn:not(.post-processed)').forEach(function(btn) {
        btn.classList.add('post-processed');
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            const url = this.href || this.dataset.url;
            if (url) {
                if (url.includes('payment')) {
                    confirmPostPayment(url);
                } else if (url.includes('journal')) {
                    confirmPostJournalEntry(url);
                } else {
                    confirmPost(url);
                }
            }
        });
    });
    
    // معالجة الأزرار التي تحتوي على class خاص لإلغاء الترحيل
    document.querySelectorAll('.btn-unpost:not(.unpost-processed), .unpost-btn:not(.unpost-processed)').forEach(function(btn) {
        btn.classList.add('unpost-processed');
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            const url = this.href || this.dataset.url;
            if (url) {
                if (url.includes('payment')) {
                    confirmUnpostPayment(url);
                } else if (url.includes('journal')) {
                    confirmUnpostJournalEntry(url);
                } else {
                    confirmUnpost(url);
                }
            }
        });
    });
    
    // معالجة النماذج (forms) التي تحتوي على إلغاء الترحيل
    document.querySelectorAll('form[action*="unpost"]:not(.unpost-processed), form.unpost-form:not(.unpost-processed)').forEach(function(form) {
        form.classList.add('unpost-processed');
        form.addEventListener('submit', function(e) {
            e.preventDefault();
            
            const formData = new FormData(this);
            const reason = formData.get('reason') || '';
            
            let confirmText = 'هل أنت متأكد من إلغاء الترحيل؟';
            let confirmHtml = '';
            
            if (reason.trim()) {
                confirmHtml = `
                    <div class="text-start">
                        <p class="mb-2">${confirmText}</p>
                        <div class="alert alert-info mb-0">
                            <strong>السبب:</strong> ${reason}
                        </div>
                    </div>
                `;
            } else {
                confirmText += '<br><small class="text-muted">سيتم حذف القيد المحاسبي المرتبط وتحديث الأرصدة</small>';
            }
            
            Swal.fire({
                title: 'تأكيد إلغاء الترحيل',
                html: confirmHtml || confirmText,
                icon: 'warning',
                showCancelButton: true,
                confirmButtonColor: '#f0ad4e',
                cancelButtonColor: '#6c757d',
                confirmButtonText: '<i class="fas fa-undo me-1"></i> نعم، إلغاء الترحيل',
                cancelButtonText: '<i class="fas fa-times me-1"></i> إلغاء',
                reverseButtons: true,
                customClass: {
                    confirmButton: 'btn btn-warning me-2',
                    cancelButton: 'btn btn-secondary'
                },
                buttonsStyling: false,
                focusCancel: true
            }).then((result) => {
                if (result.isConfirmed) {
                    // إظهار مؤشر التحميل
                    Swal.fire({
                        title: 'جاري إلغاء الترحيل...',
                        text: 'يرجى الانتظار',
                        icon: 'info',
                        allowOutsideClick: false,
                        allowEscapeKey: false,
                        showConfirmButton: false,
                        didOpen: () => {
                            Swal.showLoading();
                        }
                    });
                    
                    // إرسال النموذج
                    this.submit();
                }
            });
        });
    });
}

// دالة لعرض SweetAlert عند حفظ الدفعة مع خيار الترحيل
function showPostAfterSaveAlert(saveUrl, postUrl, paymentType = 'الدفعة') {
    Swal.fire({
        title: `تم حفظ ${paymentType} بنجاح!`,
        text: `هل تريد ترحيل ${paymentType} الآن؟`,
        icon: 'success',
        showCancelButton: true,
        confirmButtonColor: '#198754',
        cancelButtonColor: '#6c757d',
        confirmButtonText: '<i class="fas fa-check me-1"></i> نعم، ترحيل الآن',
        cancelButtonText: '<i class="fas fa-times me-1"></i> لا، ابقها مسودة',
        reverseButtons: true,
        customClass: {
            confirmButton: 'btn btn-success ms-2',
            cancelButton: 'btn btn-secondary'
        },
        buttonsStyling: false,
        focusCancel: false
    }).then((result) => {
        if (result.isConfirmed) {
            // إظهار مؤشر التحميل
            Swal.fire({
                title: 'جاري الترحيل...',
                text: 'يرجى الانتظار',
                icon: 'info',
                allowOutsideClick: false,
                allowEscapeKey: false,
                showConfirmButton: false,
                didOpen: () => {
                    Swal.showLoading();
                }
            });
            
            // الانتقال لرابط الترحيل
            window.location.href = postUrl;
        } else {
            // العودة لصفحة التفاصيل أو البقاء في نفس الصفحة
            // يمكن تخصيص هذا حسب الحاجة
        }
    });
}

// دالة مساعدة لإضافة SweetAlert لعناصر جديدة (للمحتوى المحمل ديناميكياً)
function attachUnpostAlerts(container = document) {
    // معالجة أزرار ترحيل الدفعات
    container.querySelectorAll('a[href*="post_payment"]:not(.post-processed)').forEach(function(link) {
        link.classList.add('post-processed');
        link.addEventListener('click', function(e) {
            e.preventDefault();
            confirmPostPayment(this.href);
        });
    });
    
    // معالجة أزرار إلغاء ترحيل الدفعات
    container.querySelectorAll('a[href*="unpost_payment"]:not(.unpost-processed)').forEach(function(link) {
        link.classList.add('unpost-processed');
        link.addEventListener('click', function(e) {
            e.preventDefault();
            confirmUnpostPayment(this.href);
        });
    });
    
    container.querySelectorAll('a[href*="unpost"]:not([href*="unpost_payment"]):not(.unpost-processed)').forEach(function(link) {
        link.classList.add('unpost-processed');
        link.addEventListener('click', function(e) {
            e.preventDefault();
            if (link.href.includes('journal')) {
                confirmUnpostJournalEntry(this.href);
            } else {
                confirmUnpost(this.href);
            }
        });
    });
}
