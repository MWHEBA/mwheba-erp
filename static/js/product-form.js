/**
 * Product Form Handler
 * Handles product/service form interactions and validations
 */

$(document).ready(function() {
    
    // Toggle stock fields based on service type
    function toggleStockFields() {
        const isServiceCheckbox = $('#id_is_service');
        const isServiceHidden = $('input[name="is_service"][type="hidden"]');
        
        let isService = false;
        if (isServiceCheckbox.length) {
            isService = isServiceCheckbox.is(':checked');
        } else if (isServiceHidden.length) {
            isService = isServiceHidden.val() === 'True';
        }
        
        const minStockField = $('#min-stock-field');
        const unitField = $('#unit-field');
        const costPriceField = $('#id_cost_price').closest('.col-md-4');
        const pricingTitle = $('#pricing-title');
        
        if (isService) {
            minStockField.slideUp(300);
            $('#id_min_stock').val(0).prop('required', false);
            
            unitField.find('label').html('وحدة القياس <small class="text-muted">(اختياري)</small>');
            $('#id_unit').prop('required', false);
            
            costPriceField.find('label').html('سعر التكلفة <small class="text-muted">(اختياري)</small>');
            $('#id_cost_price').prop('required', false);
            
            pricingTitle.html('<i class="fas fa-dollar-sign me-2"></i>الأسعار');
        } else {
            minStockField.slideDown(300);
            $('#id_min_stock').prop('required', false);
            
            unitField.find('label').html('وحدة القياس <span class="text-danger">*</span>');
            $('#id_unit').prop('required', true);
            
            costPriceField.find('label').html('سعر التكلفة <span class="text-danger">*</span>');
            $('#id_cost_price').prop('required', true);
            
            pricingTitle.html('<i class="fas fa-dollar-sign me-2"></i>الأسعار والمخزون');
        }
    }
    
    // Generate SKU automatically
    function generateSKU() {
        const categorySelect = $('#id_category');
        const skuField = $('#id_sku');
        
        if (categorySelect.val() && !skuField.val() && PRODUCT_FORM_CONFIG.generateSkuUrl) {
            $.ajax({
                url: PRODUCT_FORM_CONFIG.generateSkuUrl,
                type: 'POST',
                data: {
                    'category_id': categorySelect.val(),
                    'csrfmiddlewaretoken': $('input[name=csrfmiddlewaretoken]').val()
                },
                success: function(response) {
                    if (response.success) {
                        skuField.val(response.sku);
                        skuField.addClass('auto-generated');
                        skuField.animate({backgroundColor: '#d4edda'}, 300)
                               .delay(1000)
                               .animate({backgroundColor: '#fff'}, 300);
                    }
                },
                error: function() {
                    console.log('خطأ في توليد الكود');
                }
            });
        }
    }
    
    // Validate prices
    function validatePrices() {
        const costPrice = parseFloat($('#id_cost_price').val()) || 0;
        const sellingPrice = parseFloat($('#id_selling_price').val()) || 0;
        
        if (sellingPrice > 0 && costPrice > 0 && sellingPrice <= costPrice) {
            alert('سعر البيع يجب أن يكون أكبر من سعر التكلفة');
            return false;
        }
        
        return true;
    }
    
    // Initialize
    toggleStockFields();
    
    // Event handlers
    $('#id_is_service').change(toggleStockFields);
    
    $('#id_category').change(function() {
        const skuField = $('#id_sku');
        if (!skuField.val() || skuField.hasClass('auto-generated')) {
            skuField.val('').removeClass('auto-generated');
            generateSKU();
        }
    });
    
    $('#product-form').submit(function(e) {
        if (!validatePrices()) {
            e.preventDefault();
            return false;
        }
    });
    
    // Image management (only in edit mode)
    if (PRODUCT_FORM_CONFIG.isEditMode) {
        $('#add-image-btn').click(function() {
            $('#image-form')[0].reset();
            $('#imageModal').modal('show');
        });
        
        $('#save-image-btn').click(function() {
            const formData = new FormData($('#image-form')[0]);
            formData.append('product_id', PRODUCT_FORM_CONFIG.productId);
            
            $.ajax({
                url: PRODUCT_FORM_CONFIG.addImageUrl,
                type: 'POST',
                data: formData,
                processData: false,
                contentType: false,
                success: function(response) {
                    if (response.success) {
                        $('#imageModal').modal('hide');
                        location.reload();
                    } else {
                        alert(response.error);
                    }
                },
                error: function() {
                    alert('حدث خطأ أثناء رفع الصورة');
                }
            });
        });
        
        $('.delete-image').click(function(e) {
            e.preventDefault();
            const imageId = $(this).data('id');
            
            if (confirm('هل أنت متأكد من حذف هذه الصورة؟')) {
                $.ajax({
                    url: `/products/images/${imageId}/delete/`,
                    type: 'POST',
                    headers: {
                        'X-CSRFToken': $('input[name=csrfmiddlewaretoken]').val()
                    },
                    data: {
                        'csrfmiddlewaretoken': $('input[name=csrfmiddlewaretoken]').val()
                    },
                    success: function(response) {
                        if (response.success) {
                            alert(response.message || 'تم حذف الصورة بنجاح');
                            location.reload();
                        } else {
                            alert(response.error || 'حدث خطأ أثناء حذف الصورة');
                        }
                    },
                    error: function(xhr) {
                        console.error('Error details:', xhr.responseText);
                        alert('حدث خطأ أثناء حذف الصورة');
                    }
                });
            }
        });
    }
});
