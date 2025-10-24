/**
 * ملف JavaScript آمن للتفاعل مع نماذج التسعير
 * يحتوي على وظائف تحسين تجربة المستخدم في نماذج الموردين والعملاء
 * محدث لمنع ثغرات XSS
 */

$(document).ready(function() {
    
    // تهيئة Select2 للقوائم المنسدلة
    initializeSelect2();
    
    // تفعيل وظائف نموذج المورد
    initializeSupplierForm();
    
    // تفعيل وظائف نموذج العميل
    initializeCustomerForm();
    
    // تفعيل وظائف إدارة موردي الطلب
    initializeOrderSupplierForm();
    
    // تفعيل التأثيرات البصرية
    initializeVisualEffects();
});

/**
 * دالة مساعدة لإنشاء عناصر HTML بشكل آمن
 */
function createSafeAlert(alertClass, iconClass, strongText, contentText, badgeText = null) {
    const $alertDiv = $('<div></div>').addClass('alert py-2').addClass(alertClass);
    const $icon = $('<i></i>').addClass('fas me-2').addClass(iconClass);
    const $strong = $('<strong></strong>').text(strongText);
    const $content = $('<span></span>').text(contentText);
    
    $alertDiv.append($icon).append($strong).append($content);
    
    if (badgeText) {
        const $badge = $('<span></span>').addClass('badge bg-secondary ms-2').text(badgeText);
        $alertDiv.append(' ').append($badge);
    }
    
    return $alertDiv;
}

/**
 * تهيئة Select2 للقوائم المنسدلة
 */
function initializeSelect2() {
    $('.select2-search').select2({
        theme: 'bootstrap-5',
        dir: 'rtl',
        language: {
            noResults: function() {
                return "لا توجد نتائج";
            },
            searching: function() {
                return "جاري البحث...";
            },
            inputTooShort: function() {
                return "اكتب للبحث";
            },
            loadingMore: function() {
                return "جاري تحميل المزيد...";
            }
        },
        placeholder: function() {
            return $(this).data('placeholder');
        },
        allowClear: true,
        width: '100%'
    });
}

/**
 * تهيئة وظائف نموذج المورد
 */
function initializeSupplierForm() {
    // تحديث تقييم المورد بصرياً
    $('#supplier_rating').on('change', function() {
        const rating = $(this).val();
        
        // إضافة تأثير بصري للتقييم
        const ratingCard = $('#rating-display');
        if (ratingCard.length === 0) {
            $(this).after('<div id="rating-display" class="mt-2"></div>');
        }
        
        if (rating) {
            const stars = '⭐'.repeat(parseInt(rating));
            const ratingText = stars + ' (' + rating + '/5)';
            const $alert = createSafeAlert('alert-info', 'fa-star text-warning', 'التقييم المحدد: ', ratingText);
            $('#rating-display').empty().append($alert).fadeIn();
        } else {
            $('#rating-display').fadeOut();
        }
    });
    
    // حساب مدة التسليم التقديرية
    $('#delivery_time').on('input', function() {
        const days = parseInt($(this).val());
        const deliveryInfo = $('#delivery-info');
        
        if (deliveryInfo.length === 0) {
            $(this).after('<div id="delivery-info" class="mt-2"></div>');
        }
        
        if (days && days > 0) {
            let alertClass = 'alert-success';
            let icon = 'fa-check-circle';
            let message = 'سريع';
            
            if (days > 7) {
                alertClass = 'alert-warning';
                icon = 'fa-clock';
                message = 'متوسط';
            }
            if (days > 14) {
                alertClass = 'alert-danger';
                icon = 'fa-exclamation-triangle';
                message = 'بطيء';
            }
            
            const expectedDate = new Date();
            expectedDate.setDate(expectedDate.getDate() + days);
            const dateText = expectedDate.toLocaleDateString('ar-EG');
            
            const $alert = createSafeAlert(alertClass, icon, 'التسليم المتوقع: ', dateText, message);
            $('#delivery-info').empty().append($alert).fadeIn();
        } else {
            $('#delivery-info').fadeOut();
        }
    });
    
    // تحديث عداد الخدمات المحددة
    $('input[name="services[]"]').on('change', function() {
        updateServicesCount();
    });
    
    // إنشاء كود تلقائي للمورد الجديد
    if ($('#id_name').length && !$('#id_code').val()) {
        $('#id_name').on('blur', function() {
            generateSupplierCode();
        });
    }
}

/**
 * تهيئة وظائف نموذج العميل
 */
function initializeCustomerForm() {
    // تحديث معلومات نوع العميل
    $('#client_type').on('change', function() {
        const clientType = $(this).val();
        updateClientTypeInfo(clientType);
    });
    
    // حساب الخصم التلقائي
    $('#discount_rate').on('input', function() {
        const discountRate = parseFloat($(this).val()) || 0;
        updateDiscountInfo(discountRate);
    });
    
    // تحديث عداد الاهتمامات المحددة
    $('input[name="interests[]"]').on('change', function() {
        updateInterestsCount();
    });
    
    // تحديث معلومات شروط الدفع
    $('#payment_terms').on('change', function() {
        const paymentTerms = $(this).val();
        updatePaymentTermsInfo(paymentTerms);
    });
    
    // إنشاء كود تلقائي للعميل الجديد
    if ($('#id_name').length && !$('#id_code').val()) {
        $('#id_name').on('blur', function() {
            generateCustomerCode();
        });
    }
}

/**
 * تهيئة وظائف إدارة موردي الطلب
 */
function initializeOrderSupplierForm() {
    // تحديث قائمة موردي الورق عند تغيير نوع الورق
    $('#id_paper_type').on('change', function() {
        updatePaperSuppliers();
    });
    
    // تحديث معلومات الاتصال عند اختيار المورد
    $('#supplier').on('change', function() {
        const selectedOption = $(this).find('option:selected');
        const contactInfo = $('#contact-info');
        
        if (selectedOption.val()) {
            const phone = selectedOption.data('phone') || '';
            const email = selectedOption.data('email') || '';
            const contact = selectedOption.data('contact') || '';
            
            $('#contact_person').val(contact);
            $('#phone').val(phone);
            $('#email').val(email);
            
            contactInfo.slideDown();
        } else {
            contactInfo.slideUp();
        }
    });
    
    // حساب الفرق بين التكلفة والسعر المعروض
    $('#estimated_cost, #quoted_price').on('input', function() {
        calculateCostDifference();
    });
}

/**
 * تهيئة التأثيرات البصرية
 */
function initializeVisualEffects() {
    // تأثير hover للكروت
    $('.card').hover(
        function() {
            $(this).addClass('shadow-lg').css('transform', 'translateY(-2px)');
        },
        function() {
            $(this).removeClass('shadow-lg').css('transform', 'translateY(0)');
        }
    );
    
    // تأثير النقر على الأزرار
    $('.btn').on('click', function() {
        $(this).addClass('btn-clicked');
        setTimeout(() => {
            $(this).removeClass('btn-clicked');
        }, 150);
    });
    
    // تأثير التركيز على الحقول
    $('.form-control, .form-select').on('focus', function() {
        $(this).parent().addClass('field-focused');
    }).on('blur', function() {
        $(this).parent().removeClass('field-focused');
    });
}

/**
 * تحديث عداد الخدمات المحددة
 */
function updateServicesCount() {
    const selectedServices = $('input[name="services[]"]:checked').length;
    const servicesCounter = $('#services-counter');
    
    if (servicesCounter.length === 0) {
        $('.form-check-group').first().after('<div id="services-counter" class="mt-2"></div>');
    }
    
    if (selectedServices > 0) {
        const serviceText = 'تم تحديد ' + selectedServices + ' خدمة';
        const $alert = createSafeAlert('alert-info', 'fa-check-circle text-success', '', serviceText);
        $('#services-counter').empty().append($alert).fadeIn();
    } else {
        $('#services-counter').fadeOut();
    }
}

/**
 * تحديث معلومات نوع العميل
 */
function updateClientTypeInfo(clientType) {
    const clientTypeInfo = $('#client-type-info');
    
    if (clientTypeInfo.length === 0) {
        $('#client_type').after('<div id="client-type-info" class="mt-2"></div>');
    }
    
    const typeInfo = {
        'regular': { icon: 'fa-user', color: 'alert-primary', text: 'عميل عادي - خصومات قياسية' },
        'vip': { icon: 'fa-crown', color: 'alert-warning', text: 'عميل مميز - خصومات إضافية' },
        'corporate': { icon: 'fa-building', color: 'alert-success', text: 'شركة - أسعار خاصة' },
        'government': { icon: 'fa-university', color: 'alert-info', text: 'جهة حكومية - إجراءات خاصة' }
    };
    
    if (clientType && typeInfo[clientType]) {
        const info = typeInfo[clientType];
        const $alert = createSafeAlert(info.color, info.icon, '', info.text);
        $('#client-type-info').empty().append($alert).fadeIn();
    } else {
        $('#client-type-info').fadeOut();
    }
}

/**
 * تحديث معلومات الخصم
 */
function updateDiscountInfo(discountRate) {
    const discountInfo = $('#discount-info');
    
    if (discountInfo.length === 0) {
        $('#discount_rate').after('<div id="discount-info" class="mt-2"></div>');
    }
    
    if (discountRate > 0) {
        let alertClass = 'alert-info';
        let message = 'خصم قياسي';
        
        if (discountRate >= 10) {
            alertClass = 'alert-warning';
            message = 'خصم جيد';
        }
        if (discountRate >= 20) {
            alertClass = 'alert-success';
            message = 'خصم ممتاز';
        }
        if (discountRate >= 30) {
            alertClass = 'alert-danger';
            message = 'خصم عالي - يحتاج موافقة';
        }
        
        const discountText = message + ': خصم ' + discountRate + '%';
        const $alert = createSafeAlert(alertClass, 'fa-percentage', '', discountText);
        $('#discount-info').empty().append($alert).fadeIn();
    } else {
        $('#discount-info').fadeOut();
    }
}

/**
 * تحديث عداد الاهتمامات المحددة
 */
function updateInterestsCount() {
    const selectedInterests = $('input[name="interests[]"]:checked').length;
    const interestsCounter = $('#interests-counter');
    
    if (interestsCounter.length === 0) {
        $('input[name="interests[]"]').last().closest('.col-md-3').after('<div class="col-12"><div id="interests-counter" class="mt-2"></div></div>');
    }
    
    if (selectedInterests > 0) {
        const interestText = 'اهتمامات العميل: ' + selectedInterests + ' مجال محدد';
        const $alert = createSafeAlert('alert-success', 'fa-heart text-danger', '', interestText);
        $('#interests-counter').empty().append($alert).fadeIn();
    } else {
        $('#interests-counter').fadeOut();
    }
}

/**
 * حساب الفرق بين التكلفة والسعر المعروض
 */
function calculateCostDifference() {
    const estimated = parseFloat($('#estimated_cost').val()) || 0;
    const quoted = parseFloat($('#quoted_price').val()) || 0;
    const difference = quoted - estimated;
    
    const differenceInfo = $('#cost-difference');
    
    if (differenceInfo.length === 0) {
        $('#quoted_price').after('<div id="cost-difference" class="mt-2"></div>');
    }
    
    if (estimated > 0 && quoted > 0) {
        let alertClass = 'alert-info';
        let icon = 'fa-equals';
        let message = 'متساوي';
        
        if (difference > 0) {
            alertClass = 'alert-success';
            icon = 'fa-arrow-up';
            message = 'ربح: ' + difference.toFixed(2) + ' ' + (window.CURRENCY_SYMBOL || 'ج.م');
        } else if (difference < 0) {
            alertClass = 'alert-danger';
            icon = 'fa-arrow-down';
            message = 'خسارة: ' + Math.abs(difference).toFixed(2) + ' ' + (window.CURRENCY_SYMBOL || 'ج.م');
        }
        
        const diffText = 'الفرق: ' + message;
        const $alert = createSafeAlert(alertClass, icon, '', diffText);
        $('#cost-difference').empty().append($alert).fadeIn();
    } else {
        $('#cost-difference').fadeOut();
    }
}

/**
 * إنشاء كود تلقائي للمورد
 */
function generateSupplierCode() {
    const name = $('#id_name').val().trim();
    if (name && !$('#id_code').val()) {
        const code = 'SUP' + name.substring(0, 3).toUpperCase() + 
                    new Date().getFullYear().toString().substr(-2) + 
                    (Math.floor(Math.random() * 99) + 1).toString().padStart(2, '0');
        $('#id_code').val(code);
        
        // إظهار رسالة تأكيد
        showCodeGenerated('مورد', code);
    }
}

/**
 * إنشاء كود تلقائي للعميل
 */
function generateCustomerCode() {
    const name = $('#id_name').val().trim();
    if (name && !$('#id_code').val()) {
        const code = 'CUS' + name.substring(0, 3).toUpperCase() + 
                    new Date().getFullYear().toString().substr(-2) + 
                    (Math.floor(Math.random() * 99) + 1).toString().padStart(2, '0');
        $('#id_code').val(code);
        
        // إظهار رسالة تأكيد
        showCodeGenerated('عميل', code);
    }
}

/**
 * إظهار رسالة تأكيد إنشاء الكود
 */
function showCodeGenerated(type, code) {
    const codeInfo = $('#code-generated');
    
    if (codeInfo.length === 0) {
        $('#id_code').after('<div id="code-generated" class="mt-2"></div>');
    }
    
    const codeText = 'تم إنشاء كود ' + type + ' تلقائياً: ' + code;
    const $alert = createSafeAlert('alert-success', 'fa-magic', '', codeText);
    $('#code-generated').empty().append($alert).fadeIn().delay(3000).fadeOut();
}

/**
 * تحديث معلومات شروط الدفع
 */
function updatePaymentTermsInfo(paymentTerms) {
    const paymentInfo = $('#payment-terms-info');
    
    if (paymentInfo.length === 0) {
        $('#payment_terms').after('<div id="payment-terms-info" class="mt-2"></div>');
    }
    
    const termsInfo = {
        'cash': { icon: 'fa-money-bill-wave', color: 'alert-success', text: 'دفع نقدي فوري' },
        '30_days': { icon: 'fa-calendar-alt', color: 'alert-info', text: 'دفع خلال 30 يوم' },
        '60_days': { icon: 'fa-calendar-alt', color: 'alert-warning', text: 'دفع خلال 60 يوم' },
        '90_days': { icon: 'fa-calendar-alt', color: 'alert-danger', text: 'دفع خلال 90 يوم' },
        'custom': { icon: 'fa-cog', color: 'alert-secondary', text: 'شروط دفع مخصصة' }
    };
    
    if (paymentTerms && termsInfo[paymentTerms]) {
        const info = termsInfo[paymentTerms];
        const $alert = createSafeAlert(info.color, info.icon, '', info.text);
        $('#payment-terms-info').empty().append($alert).fadeIn();
    } else {
        $('#payment-terms-info').fadeOut();
    }
}

/**
 * تحديث قائمة موردي الورق بناءً على نوع الورق المختار
 */
function updatePaperSuppliers() {
    const paperTypeId = $('#id_paper_type').val();
    const paperSupplierSelect = $('#id_paper_supplier');
    
    if (!paperTypeId) {
        resetPaperSuppliers();
        return;
    }
    
    // عرض مؤشر التحميل
    paperSupplierSelect.html('<option value="">جاري التحميل...</option>');
    paperSupplierSelect.prop('disabled', true);
    
    // استدعاء API لجلب الموردين المناسبين
    $.ajax({
        url: '/printing-pricing/api/paper-suppliers/',
        method: 'GET',
        data: {
            paper_type_id: paperTypeId
        },
        success: function(response) {
            if (response.success) {
                paperSupplierSelect.html('<option value="">-- اختر مورد الورق --</option>');
                
                if (response.suppliers && response.suppliers.length > 0) {
                    $.each(response.suppliers, function(index, supplier) {
                        const $option = $('<option></option>')
                            .attr('value', supplier.id)
                            .text(supplier.name);
                        paperSupplierSelect.append($option);
                    });
                } else {
                    paperSupplierSelect.append('<option value="">لا توجد موردين متاحين لهذا النوع</option>');
                }
            } else {
                console.error('خطأ في جلب موردي الورق:', response.error);
                paperSupplierSelect.html('<option value="">خطأ في التحميل</option>');
            }
        },
        error: function(xhr, status, error) {
            console.error('خطأ في الاتصال:', error);
            paperSupplierSelect.html('<option value="">خطأ في الاتصال</option>');
        },
        complete: function() {
            paperSupplierSelect.prop('disabled', false);
        }
    });
}

/**
 * إعادة تعيين قائمة موردي الورق لعرض جميع الموردين النشطين
 */
function resetPaperSuppliers() {
    const paperSupplierSelect = $('#id_paper_supplier');
    
    $.ajax({
        url: '/printing-pricing/api/paper-suppliers/',
        method: 'GET',
        success: function(response) {
            if (response.success) {
                paperSupplierSelect.html('<option value="">-- اختر مورد الورق --</option>');
                
                if (response.suppliers && response.suppliers.length > 0) {
                    $.each(response.suppliers, function(index, supplier) {
                        const $option = $('<option></option>')
                            .attr('value', supplier.id)
                            .text(supplier.name);
                        paperSupplierSelect.append($option);
                    });
                }
            }
        },
        error: function(xhr, status, error) {
            console.error('خطأ في إعادة تحميل موردي الورق:', error);
        }
    });
}

// إضافة CSS للصفحة بشكل آمن
$(document).ready(function() {
    const customCSS = $('<style></style>').text(`
        .field-focused {
            transform: scale(1.02);
            transition: transform 0.2s ease;
        }
        .btn-clicked {
            transform: scale(0.95);
        }
    `);
    $('head').append(customCSS);
});
