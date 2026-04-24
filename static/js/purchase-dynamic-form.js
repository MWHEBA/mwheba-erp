/**
 * Purchase Dynamic Form Handler
 * Handles dynamic product/service filtering based on supplier type
 */

(function() {
    'use strict';

    // Configuration
    const CONFIG = {
        supplierSelectId: '#id_supplier',
        warehouseFieldId: '#warehouse-field',
        productSelectClass: '.product-select',
        apiEndpoint: '/purchases/api/supplier-type/',
    };

    // State
    let currentSupplierType = null;
    let availableProducts = [];

    /**
     * Initialize the dynamic form
     */
    function init() {
        
        const supplierSelect = $(CONFIG.supplierSelectId);
        
        if (supplierSelect.length === 0) {
            console.warn('?? Supplier select not found');
            return;
        }
        

        // Attach event listener
        supplierSelect.on('change', handleSupplierChange);

        // Trigger on page load if supplier is pre-selected
        if (supplierSelect.val()) {
            handleSupplierChange();
        }
    }

    /**
     * Handle supplier selection change
     */
    function handleSupplierChange() {
        const supplierId = $(CONFIG.supplierSelectId).val();
        
        
        if (!supplierId) {
            resetForm();
            return;
        }

        // Fetch supplier type and products
        fetchSupplierData(supplierId);
    }

    /**
     * Fetch supplier data from API
     */
    function fetchSupplierData(supplierId) {
        const url = `${CONFIG.apiEndpoint}${supplierId}/`;

        $.ajax({
            url: url,
            method: 'GET',
            dataType: 'json',
            success: function(response) {
                if (response.success) {
                    handleSupplierDataSuccess(response);
                } else {
                    console.error('API returned error:', response.message);
                    showNotification('error', response.message || 'حدث خطأ في جلب بيانات المورد');
                }
            },
            error: function(xhr, status, error) {
                console.error('API request failed:', error);
                showNotification('error', 'خطأ في الاتصال بالخادم');
            }
        });
    }

    /**
     * Handle successful supplier data fetch
     */
    function handleSupplierDataSuccess(data) {
        
        currentSupplierType = data.supplier_type_code;
        availableProducts = data.products;

        // Update warehouse field visibility
        updateWarehouseField(data.requires_warehouse);

        // Update product dropdowns
        updateProductDropdowns(data.products, data.is_service_provider);

        // Update UI labels
        updateUILabels(data.is_service_provider);
        
        // Update financial category based on supplier type
        updateFinancialCategory(data.financial_categories || [], data.is_service_provider);
        
    }

    /**
     * Update warehouse field visibility
     */
    function updateWarehouseField(required) {
        
        const warehouseField = $(CONFIG.warehouseFieldId);
        const warehouseSelect = warehouseField.find('select');
        const requiredStar = warehouseField.find('.warehouse-required');

        if (required) {
            warehouseField.show();
            warehouseSelect.prop('required', true);
            requiredStar.show();
        } else {
            warehouseField.hide();
            warehouseSelect.prop('required', false);
            warehouseSelect.val('').trigger('change');
            requiredStar.hide();
            
            // If using select2, clear it properly
            if (warehouseSelect.hasClass('select2-hidden-accessible')) {
                warehouseSelect.select2('val', '');
            }
        }
    }

    /**
     * Update product dropdown options
     */
    function updateProductDropdowns(products, isService) {
        const productSelects = $(CONFIG.productSelectClass);

        if (productSelects.length === 0) {
            console.warn('No product select elements found');
            return;
        }

        // Build options HTML
        let optionsHtml = '<option value="">اختر...</option>';
        products.forEach(function(product) {
            const price = product.cost_price || product.selling_price || 0;
            optionsHtml += `<option value="${product.id}" data-price="${price}">${product.name} (${product.sku})</option>`;
        });

        // Update all product selects
        productSelects.each(function() {
            const $select = $(this);
            const currentValue = $select.val();
            
            // Destroy select2 if initialized
            if ($select.hasClass('select2-hidden-accessible')) {
                $select.select2('destroy');
            }
            
            // Update options
            $select.html(optionsHtml);
            
            // Restore previous selection if still valid
            if (currentValue && products.some(p => p.id == currentValue)) {
                $select.val(currentValue);
            }
            
            // Re-initialize select2
            $select.select2({
                placeholder: isService ? "اختر الخدمة" : "اختر المنتج",
                width: '100%',
                dir: 'rtl'
            });
        });
    }

    /**
     * Update UI labels based on supplier type
     */
    function updateUILabels(isService) {
        
        const itemType = isService ? 'الخدمة' : 'المنتج';
        
        // Update page title
        const pageTitle = $('.header-title');
        if (pageTitle.length) {
            const titleText = isService ? 'إضافة فاتورة خدمات جديدة' : 'إضافة فاتورة مشتريات جديدة';
            pageTitle.text(titleText);
        }
        
        // Update section title (بيانات الفاتورة)
        const sectionTitle = $('#supplier-section-title');
        if (sectionTitle.length) {
            sectionTitle.text(isService ? 'الخدمات' : 'بيانات الفاتورة');
        }
        
        // Update section titles
        const itemsTitle = $('#items-title');
        const addBtnText = $('#add-btn-text');
        const itemsIcon = $('#items-icon');
        const productHeaders = $('.product-header');
        
        if (itemsTitle.length) {
            itemsTitle.text(`بنود ${itemType}`);
        }
        
        if (addBtnText.length) {
            addBtnText.text(`إضافة ${itemType}`);
        }
        
        // Update table headers
        if (productHeaders.length) {
            productHeaders.text(itemType);
        }
        
        // Update icons
        const icon = isService ? 'fas fa-concierge-bell' : 'fas fa-boxes';
        if (itemsIcon.length) {
            itemsIcon.attr('class', `${icon} me-2`);
        }
    }

    /**
     * Update financial category based on supplier type
     * - Auto mode: shows badge with auto-selected category, hidden input carries the value
     * - Manual mode: shows full dropdown (toggled by user)
     */
    function updateFinancialCategory(categories, isService) {
        const categorySelect = $('#id_financial_category');
        const autoValueInput = $('#financial_category_auto_value');
        const autoBadgeText = $('#auto-category-text');

        // Build new options for the manual dropdown
        let optionsHtml = '<option value="">اختر التصنيف المالي</option>';
        if (categories && categories.length > 0) {
            categories.forEach(function(cat) {
                optionsHtml += `<option value="${cat.value}">${cat.label}</option>`;
            });
        }

        if (categorySelect.length) {
            if (categorySelect.hasClass('select2-hidden-accessible')) {
                categorySelect.select2('destroy');
            }

            // في وضع النسخ: احفظ القيمة الحالية قبل مسح الـ options
            const preservedValue = (window._disableCategorySuggestion && window._duplicateData)
                ? window._duplicateData.financialCategoryId
                : null;

            categorySelect.html(optionsHtml);

            if (preservedValue) {
                // أعد تحديد التصنيف الأصلي
                categorySelect.val(preservedValue);
            } else if (categories && categories.length >= 1) {
                categorySelect.val(categories[0].value);
            }

            categorySelect.select2({
                placeholder: 'اختر التصنيف المالي',
                width: '100%',
                allowClear: true
            });
        }

        // Update auto badge and hidden value - فقط لو مش في وضع النسخ
        if (!window._disableCategorySuggestion) {
            if (categories && categories.length >= 1) {
                const autoCategory = categories[0];
                const cleanLabel = autoCategory.label.replace(/^[📁↳\s]+/, '').trim();
                autoBadgeText.text(cleanLabel);
                autoValueInput.val(autoCategory.value);
            } else {
                autoBadgeText.text('سيتم تحديده تلقائياً');
                autoValueInput.val('');
            }
        }
    }

    /**
     * Reset form to default state
     */
    function resetForm() {
        currentSupplierType = null;
        availableProducts = [];

        // Show warehouse field
        updateWarehouseField(true);

        // Clear product dropdowns
        const productSelects = $(CONFIG.productSelectClass);
        productSelects.each(function() {
            const $select = $(this);
            
            // Destroy select2 if initialized
            if ($select.hasClass('select2-hidden-accessible')) {
                $select.select2('destroy');
            }
            
            $select.html('<option value="">اختر المورد أولاً...</option>');
            
            // Re-initialize select2
            $select.select2({
                placeholder: "اختر المورد أولاً",
                width: '100%',
                dir: 'rtl'
            });
        });

        // Reset labels
        const pageTitle = $('.header-title');
        if (pageTitle.length) {
            pageTitle.text('إضافة فاتورة مشتريات جديدة');
        }
        
        const sectionTitle = $('#supplier-section-title');
        if (sectionTitle.length) {
            sectionTitle.text('بيانات الفاتورة');
        }
        
        $('#items-title').text('بنود المشتريات');
        $('#add-btn-text').text('إضافة بند');
        $('#items-icon').attr('class', 'fas fa-boxes me-2');

        // Reset financial category to show all options
        const categorySelect = $('#id_financial_category');
        if (categorySelect.length) {
            if (categorySelect.hasClass('select2-hidden-accessible')) {
                categorySelect.select2('destroy');
            }
            categorySelect.val('').trigger('change');
            categorySelect.select2({
                placeholder: 'اختر التصنيف المالي',
                width: '100%',
                allowClear: true
            });
        }
        // Reset auto badge
        $('#auto-category-text').text('سيتم تحديده تلقائياً');
        $('#financial_category_auto_value').val('');
    }

    /**
     * Show notification message
     */
    function showNotification(message, type = 'info') {
        if (typeof toastr !== 'undefined') {
            if (type === 'success') toastr.success(message);
            else if (type === 'error' || type === 'danger') toastr.error(message);
            else if (type === 'warning') toastr.warning(message);
            else toastr.info(message);
        } else {
            // Fallback to alert
            alert(message);
        }
    }

    /**
     * Get current supplier type
     */
    function getCurrentSupplierType() {
        return currentSupplierType;
    }

    /**
     * Get available products
     */
    function getAvailableProducts() {
        return availableProducts;
    }

    // Initialize on document ready
    $(document).ready(function() {
        init();
    });

    // Expose public API
    window.PurchaseDynamicForm = {
        getCurrentSupplierType: getCurrentSupplierType,
        getAvailableProducts: getAvailableProducts,
        refresh: handleSupplierChange
    };

})();


