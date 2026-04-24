/**
 * Batch Voucher Form Management
 * إدارة نموذج الأذون الجماعية
 */

const BatchVoucherForm = {
    /**
     * تهيئة النموذج
     */
    init: function() {
        this.bindEvents();
        this.updateTotals();
        this.loadProductCosts();
        this.initFormSubmit();
        this.updateProductOptions(); // تحديث خيارات المنتجات عند التحميل
    },
    
    /**
     * ربط الأحداث
     */
    bindEvents: function() {
        const self = this;
        
        // إضافة صف جديد
        $('#add-row').on('click', function() {
            self.addRow();
        });
        
        // حذف صف
        $(document).on('click', '.delete-row', function() {
            self.deleteRow($(this));
        });
        
        // تحديث التكلفة عند اختيار المنتج
        $(document).on('change', '.product-select', function() {
            // select2 بيطلق change تلقائياً
            self.loadProductCost($(this));
            self.loadProductStock($(this));
            self.updateProductOptions();
        });
        
        // التحقق من الكمية عند التغيير
        $(document).on('input change', '.quantity-input', function() {
            self.validateQuantity($(this));
            self.updateRowTotal($(this).closest('.formset-row'));
            self.updateTotals();
        });
    },
    
    /**
     * تحديث خيارات المنتجات (إخفاء المنتجات المستخدمة)
     */
    updateProductOptions: function() {
        // جمع المنتجات المختارة
        const selectedProducts = [];
        $('.formset-row').not('.to-delete').each(function() {
            const productId = $(this).find('.product-select').val();
            if (productId) {
                selectedProducts.push(productId);
            }
        });
        
        // تحديث كل قائمة منتجات
        $('.formset-row').not('.to-delete').each(function() {
            const currentSelect = $(this).find('.product-select');
            const currentValue = currentSelect.val();
            
            // إخفاء المنتجات المستخدمة في صفوف أخرى
            currentSelect.find('option').each(function() {
                const optionValue = $(this).val();
                if (optionValue && optionValue !== currentValue && selectedProducts.includes(optionValue)) {
                    $(this).hide();
                } else {
                    $(this).show();
                }
            });
        });
    },
    
    /**
     * تهيئة حالة التحميل عند إرسال النموذج
     */
    initFormSubmit: function() {
        $('form').on('submit', function(e) {
            // تنظيف الصفوف الفاضية قبل الإرسال
            BatchVoucherForm.cleanEmptyRows();
            
            // Validate form first
            if (!BatchVoucherForm.validateForm()) {
                e.preventDefault();
                return false;
            }
            
            const submitBtn = $(this).find('button[type="submit"]');
            
            // Disable button
            submitBtn.prop('disabled', true);
            
            // Show loading
            const originalText = submitBtn.html();
            submitBtn.data('original-text', originalText);
            submitBtn.html('<i class="fas fa-spinner fa-spin me-2"></i>جاري الحفظ...');
            
            // Re-enable after 10 seconds as fallback
            setTimeout(function() {
                submitBtn.prop('disabled', false);
                submitBtn.html(originalText);
            }, 10000);
        });
    },
    
    /**
     * تنظيف الصفوف الفاضية
     */
    cleanEmptyRows: function() {
        console.log('=== Cleaning Empty Rows ===');
        $('.formset-row').each(function() {
            const row = $(this);
            const productId = row.find('.product-select').val();
            const quantity = parseFloat(row.find('.quantity-input').val()) || 0;
            const unitCost = parseFloat(row.find('.unit-cost-input').val()) || 0;
            const deleteCheckbox = row.find('input[name$="-DELETE"]');
            
            console.log('Row:', {
                product: productId,
                quantity: quantity,
                unitCost: unitCost,
                hasDeleteCheckbox: deleteCheckbox.length > 0
            });
            
            // لو الصف فاضي تماماً، علّمه للحذف
            if (!productId && quantity === 0 && unitCost === 0 && deleteCheckbox.length) {
                console.log('Marking row for deletion');
                deleteCheckbox.prop('checked', true);
                row.addClass('to-delete');
            }
        });
        console.log('=== Cleaning Complete ===');
    },
    
    /**
     * التحقق من صحة النموذج
     */
    validateForm: function() {
        console.log('=== Validating Form ===');
        let isValid = true;
        let errors = [];
        
        // التحقق من نوع الإذن
        const voucherType = $('#id_voucher_type').val();
        if (!voucherType) {
            errors.push('يرجى اختيار نوع الإذن');
            isValid = false;
        }
        
        // التحقق من المخزن
        const warehouse = $('#id_warehouse').val();
        if (!warehouse) {
            errors.push('يرجى اختيار المخزن');
            isValid = false;
        }
        
        // التحقق من المخزن الهدف (للتحويل)
        if (voucherType === 'transfer') {
            const targetWarehouse = $('#id_target_warehouse').val();
            if (!targetWarehouse) {
                errors.push('يرجى اختيار المخزن الهدف');
                isValid = false;
            } else if (warehouse === targetWarehouse) {
                errors.push('لا يمكن التحويل من وإلى نفس المخزن');
                isValid = false;
            }
        }
        
        // التحقق من الغرض (للاستلام/الصرف)
        if (voucherType !== 'transfer') {
            const purposeType = $('#id_purpose_type').val();
            if (!purposeType) {
                errors.push('يرجى اختيار الغرض');
                isValid = false;
            }
        }
        
        // التحقق من وجود منتجات صالحة
        let validRowsCount = 0;
        let rowErrors = [];
        
        $('.formset-row').each(function(index) {
            const row = $(this);
            const productId = row.find('.product-select').val();
            const quantity = parseFloat(row.find('.quantity-input').val()) || 0;
            const unitCost = parseFloat(row.find('.unit-cost-input').val()) || 0;
            const isMarkedForDeletion = row.find('input[name$="-DELETE"]').prop('checked');
            
            console.log(`Row ${index + 1}:`, {
                product: productId,
                quantity: quantity,
                unitCost: unitCost,
                markedForDeletion: isMarkedForDeletion
            });
            
            // تجاهل الصفوف المعلّمة للحذف
            if (isMarkedForDeletion) {
                console.log(`Row ${index + 1}: Skipped (marked for deletion)`);
                return; // skip
            }
            
            // لو في منتج، تحقق من البيانات
            if (productId) {
                validRowsCount++;
                console.log(`Row ${index + 1}: Valid product found`);
                
                if (quantity <= 0) {
                    rowErrors.push(`الصف ${index + 1}: الكمية يجب أن تكون أكبر من صفر`);
                    isValid = false;
                }
                if (unitCost < 0) {
                    rowErrors.push(`الصف ${index + 1}: التكلفة لا يمكن أن تكون سالبة`);
                    isValid = false;
                }
            } else if (quantity > 0 || unitCost > 0) {
                // لو في كمية أو تكلفة بس مافيش منتج
                rowErrors.push(`الصف ${index + 1}: يرجى اختيار المنتج`);
                isValid = false;
            }
        });
        
        console.log(`Valid rows count: ${validRowsCount}`);
        
        if (validRowsCount === 0) {
            errors.push('يرجى إضافة منتج واحد على الأقل');
            isValid = false;
        }
        
        errors = errors.concat(rowErrors);
        
        // عرض الأخطاء
        if (!isValid) {
            console.log('Validation failed:', errors);
            let errorMessage = '<div class="text-start"><ul class="mb-0">';
            errors.forEach(function(error) {
                errorMessage += '<li>' + error + '</li>';
            });
            errorMessage += '</ul></div>';
            
            Swal.fire({
                title: 'يرجى تصحيح الأخطاء',
                html: errorMessage,
                icon: 'error',
                confirmButtonText: 'حسناً'
            });
        } else {
            console.log('Validation passed!');
        }
        
        console.log('=== Validation Complete ===');
        return isValid;
    },
    
    /**
     * إضافة صف جديد
     */
    addRow: function() {
        const container = $('#formset-container');
        const totalForms = $('#id_items-TOTAL_FORMS');
        const formIdx = parseInt(totalForms.val());
        
        // نسخ أول صف مش محذوف
        const templateRow = container.find('.formset-row').not('.to-delete').first();
        
        if (!templateRow.length) {
            toastr.error('خطأ في إضافة صف جديد');
            return;
        }
        
        // destroy select2 على الصف الأصلي قبل الـ clone عشان نحصل على select نظيف
        const $origSelect = templateRow.find('.product-select');
        if ($origSelect.hasClass('select2-hidden-accessible')) {
            $origSelect.select2('destroy');
        }
        
        let newRow = templateRow.clone();
        
        // إعادة تهيئة select2 على الصف الأصلي
        if (typeof ProductSelect2 !== 'undefined') {
            ProductSelect2.initRow(templateRow);
        }
        
        // تحديث الـ indices
        newRow.html(newRow.html().replace(/-\d+-/g, `-${formIdx}-`));
        newRow.attr('data-form-index', formIdx);
        
        // مسح القيم - إزالة أي select2 artifacts من الـ clone
        newRow.find('.select2-container').remove();
        newRow.find('select.product-select')
            .removeClass('select2-hidden-accessible')
            .removeAttr('data-select2-id')
            .val('');
        newRow.find('input[type="number"], input[type="text"]').val('');
        newRow.find('.item-total').val('0.00');
        newRow.find('input[name$="-DELETE"]').prop('checked', false).val('');
        newRow.find('input[name$="-id"]').val('');
        newRow.removeClass('to-delete').show();
        
        // إضافة الصف
        container.append(newRow);
        
        // تهيئة select2 على الصف الجديد
        if (typeof ProductSelect2 !== 'undefined') {
            ProductSelect2.initRow(newRow);
        }
        
        // تحديث عدد النماذج
        totalForms.val(formIdx + 1);
        
        this.updateTotals();
        this.updateProductOptions(); // تحديث خيارات المنتجات بعد الإضافة
    },
    
    /**
     * حذف صف
     */
    deleteRow: function(button) {
        const row = button.closest('.formset-row');
        const container = $('#formset-container');
        
        // لو في أكثر من صف واحد
        if (container.find('.formset-row').not('.to-delete').length > 1) {
            const deleteCheckbox = row.find('input[name$="-DELETE"]');
            
            if (deleteCheckbox.length && deleteCheckbox.val()) {
                // إذا كان الصف موجود في قاعدة البيانات، علّمه للحذف
                deleteCheckbox.prop('checked', true);
                row.addClass('to-delete').hide();
            } else {
                // إذا كان صف جديد، احذفه مباشرة
                row.remove();
            }
            
            this.updateTotals();
            this.updateProductOptions(); // تحديث خيارات المنتجات بعد الحذف
        } else {
            toastr.warning('يجب الاحتفاظ بصف واحد على الأقل');
        }
    },
    
    /**
     * تحميل تكلفة المنتج
     */
    loadProductCost: function(select) {
        const productId = select.val();
        if (!productId) return;
        
        const row = select.closest('.formset-row');
        const unitCostInput = row.find('.unit-cost-input');
        
        $.ajax({
            url: '/products/api/product-cost/',
            data: { product_id: productId },
            success: function(data) {
                unitCostInput.val(data.unit_cost.toFixed(2));
                BatchVoucherForm.updateRowTotal(row);
                BatchVoucherForm.updateTotals();
            },
            error: function() {
                console.error('فشل تحميل تكلفة المنتج');
            }
        });
    },
    
    /**
     * تحميل الكمية المتاحة للمنتج في المخزن المصدر
     * يعمل فقط في أذون الصرف والتحويل
     */
    loadProductStock: function(select) {
        const productId = select.val();
        const row = select.closest('.formset-row');
        const stockInfo = row.find('.stock-info');
        const quantityInput = row.find('.quantity-input');

        // مسح المعلومات القديمة
        stockInfo.text('');
        quantityInput.removeAttr('data-max-stock');

        if (!productId) return;

        const voucherType = $('#id_voucher_type').val();
        // الكمية المتاحة مهمة فقط في الصادر والتحويل
        if (voucherType !== 'issue' && voucherType !== 'transfer') return;

        const warehouseId = $('#id_warehouse').val();
        if (!warehouseId) return;

        $.ajax({
            url: '/products/api/product-warehouses/',
            data: { product_id: productId },
            success: function(data) {
                const wh = data.warehouses.find(w => String(w.id) === String(warehouseId));
                const available = wh ? wh.quantity : 0;
                const unit = data.unit || 'وحدة';

                quantityInput.attr('data-max-stock', available);

                if (available > 0) {
                    stockInfo.html(`<i class="fas fa-box me-1"></i>متاح: <strong>${available}</strong> ${unit}`);
                    stockInfo.removeClass('text-danger').addClass('text-muted');
                } else {
                    stockInfo.html(`<i class="fas fa-exclamation-triangle me-1"></i>لا يوجد مخزون في هذا المخزن`);
                    stockInfo.removeClass('text-muted').addClass('text-danger');
                }
            }
        });
    },

    /**
     * التحقق من أن الكمية لا تتجاوز المتاح
     */
    validateQuantity: function(input) {
        const voucherType = $('#id_voucher_type').val();
        if (voucherType !== 'issue' && voucherType !== 'transfer') return;

        const maxStock = parseFloat(input.attr('data-max-stock'));
        if (isNaN(maxStock)) return;

        const entered = parseFloat(input.val()) || 0;

        if (entered > maxStock) {
            input.val(maxStock);
            toastr.warning(`الكمية المتاحة في المخزن هي ${maxStock} فقط`);
        }
    },

    /**
     * تحميل تكاليف جميع المنتجات عند تحميل الصفحة
     */
    loadProductCosts: function() {
        const self = this;
        $('.formset-row').each(function() {
            const row = $(this);
            const productSelect = row.find('.product-select');
            if (productSelect.val()) {
                self.updateRowTotal(row);
            }
        });
    },
    
    /**
     * تحديث إجمالي الصف
     */
    updateRowTotal: function(row) {
        const quantity = parseFloat(row.find('.quantity-input').val()) || 0;
        const unitCost = parseFloat(row.find('.unit-cost-input').val()) || 0;
        const total = quantity * unitCost;
        
        row.find('.item-total').val(total.toFixed(2));
    },
    
    /**
     * تحديث الإجماليات
     */
    updateTotals: function() {
        let totalItems = 0;
        let totalQuantity = 0;
        let totalValue = 0;
        
        $('.formset-row').not('.to-delete').each(function() {
            const row = $(this);
            const productSelect = row.find('.product-select');
            const quantity = parseFloat(row.find('.quantity-input').val()) || 0;
            const itemTotal = parseFloat(row.find('.item-total').val()) || 0;
            
            if (productSelect.val() && quantity > 0) {
                totalItems++;
                totalQuantity += quantity;
                totalValue += itemTotal;
            }
        });
        
        // Get currency symbol from data attribute or default
        const currencySymbol = $('#total-value').data('currency') || 'ج.م';
        
        $('#total-items').text(this.formatNumber(totalItems));
        $('#total-quantity').text(this.formatNumber(totalQuantity));
        $('#total-value').text(this.formatNumber(totalValue) + ' ' + currencySymbol);
    },
    
    /**
     * تنسيق الأرقام
     */
    formatNumber: function(value) {
        const num = parseFloat(value);
        if (isNaN(num)) return '0';
        
        // إزالة الأصفار غير الضرورية
        if (num % 1 === 0) {
            return num.toLocaleString('en-US');
        }
        
        return num.toLocaleString('en-US', {
            minimumFractionDigits: 0,
            maximumFractionDigits: 2
        });
    }
};


/**
 * اعتماد الإذن الجماعي
 */
function approveBatchVoucher(voucherId) {
    Swal.fire({
        title: '⚠️ تأكيد اعتماد الإذن',
        html: `
            <p class="text-start">هل أنت متأكد من اعتماد هذا الإذن؟</p>
            <div class="text-start mt-3">
                <p><strong>سيتم تنفيذ الإجراءات التالية:</strong></p>
                <ul>
                    <li>إنشاء حركات المخزون لجميع المنتجات</li>
                    <li>إنشاء القيد المحاسبي الموحد</li>
                    <li>لا يمكن التراجع عن هذا الإجراء</li>
                </ul>
            </div>
        `,
        icon: 'warning',
        showCancelButton: true,
        confirmButtonColor: '#28a745',
        cancelButtonColor: '#6c757d',
        confirmButtonText: '<i class="fas fa-check me-2"></i>نعم، اعتمد الإذن',
        cancelButtonText: '<i class="fas fa-times me-2"></i>إلغاء',
        customClass: {
            confirmButton: 'btn btn-success',
            cancelButton: 'btn btn-secondary'
        },
        buttonsStyling: false
    }).then((result) => {
        if (result.isConfirmed) {
            // Get button element
            const btn = event.target.closest('button');
            if (btn) {
                // Show loading
                btn.disabled = true;
                const originalText = btn.innerHTML;
                btn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>جاري الاعتماد...';
            }
            
            // Create and submit form
            const form = document.createElement('form');
            form.method = 'POST';
            form.action = `/products/batch-vouchers/${voucherId}/approve/`;
            
            const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]');
            if (csrfToken) {
                const csrfInput = document.createElement('input');
                csrfInput.type = 'hidden';
                csrfInput.name = 'csrfmiddlewaretoken';
                csrfInput.value = csrfToken.value;
                form.appendChild(csrfInput);
            }
            
            document.body.appendChild(form);
            form.submit();
        }
    });
}

/**
 * حذف الإذن الجماعي
 */
function deleteBatchVoucher(voucherId) {
    Swal.fire({
        title: '⚠️ تحذير: حذف الإذن',
        html: `
            <p class="text-start">هل أنت متأكد من حذف هذا الإذن؟</p>
            <div class="text-start mt-3">
                <p><strong>سيتم حذف:</strong></p>
                <ul>
                    <li>الإذن بالكامل</li>
                    <li>جميع المنتجات المرتبطة به</li>
                </ul>
                <p class="text-danger mt-2"><strong>⚠️ لا يمكن التراجع عن هذا الإجراء</strong></p>
            </div>
        `,
        icon: 'error',
        showCancelButton: true,
        confirmButtonColor: '#dc3545',
        cancelButtonColor: '#6c757d',
        confirmButtonText: '<i class="fas fa-trash me-2"></i>نعم، احذف الإذن',
        cancelButtonText: '<i class="fas fa-times me-2"></i>إلغاء',
        customClass: {
            confirmButton: 'btn btn-danger',
            cancelButton: 'btn btn-secondary'
        },
        buttonsStyling: false
    }).then((result) => {
        if (result.isConfirmed) {
            // Get button element
            const btn = event.target.closest('button');
            if (btn) {
                // Show loading
                btn.disabled = true;
                const originalText = btn.innerHTML;
                btn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>جاري الحذف...';
            }
            
            // Create and submit form
            const form = document.createElement('form');
            form.method = 'POST';
            form.action = `/products/batch-vouchers/${voucherId}/delete/`;
            
            const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]');
            if (csrfToken) {
                const csrfInput = document.createElement('input');
                csrfInput.type = 'hidden';
                csrfInput.name = 'csrfmiddlewaretoken';
                csrfInput.value = csrfToken.value;
                form.appendChild(csrfInput);
            }
            
            document.body.appendChild(form);
            form.submit();
        }
    });
}
