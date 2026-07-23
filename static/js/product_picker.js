/**
 * Unified Product Picker & Fast Barcode Scanner Component Engine
 * MWHEBA ERP System
 */
(function(window, $) {
    'use strict';

    var ProductPicker = {
        options: {
            type: 'sale', // 'sale', 'purchase', or 'quotation'
            priceField: 'selling_price',
            currencySymbol: 'ج.م',
            getWarehouseId: function() { return $('#id_warehouse').val() || ''; },
            getInvoiceId: function() { return '0'; },
            onProductSelect: null // function($row, product, matchType) {}
        },
        _activePickerRow: null,
        _activeCategory: 'all',
        _activeType: 'all',
        _searchTerm: '',
        _lookupTimeout: null,
        _modalSearchTimeout: null,

        init: function(userOptions) {
            this.options = $.extend({}, this.options, userOptions);
            this.bindEvents();
            this.loadInitialStock();
        },

        bindEvents: function() {
            var self = this;

            // 1. فتح المودال عند النقر على زر اختيار المنتج
            $(document).off('click.productPicker', '.product-picker-btn').on('click.productPicker', '.product-picker-btn', function() {
                self._activePickerRow = $(this).closest('.item-row');
                self._activeCategory = 'all';
                self._activeType = 'all';
                self._searchTerm = '';

                $('#picker-search').val('');
                var typeRadioAll = document.getElementById('type-all');
                if (typeRadioAll) typeRadioAll.checked = true;

                $('#categoryTabs .nav-link').removeClass('active');
                $('#categoryTabs .nav-link[data-category="all"]').addClass('active');

                self.loadModalProducts();
                var modalEl = document.getElementById('productPickerModal');
                if (modalEl) {
                    var modal = bootstrap.Modal.getInstance(modalEl) || new bootstrap.Modal(modalEl);
                    modal.show();
                }
            });

            // 2. الفوكس التلقائي على حقل البحث عند اكتمال ظهور المودال
            $(document).off('shown.bs.modal.productPicker', '#productPickerModal').on('shown.bs.modal.productPicker', '#productPickerModal', function() {
                $('#picker-search').focus().select();
            });

            // 3. التبديل بين التصنيفات داخل المودال
            $(document).off('click.productPicker', '#categoryTabs .nav-link').on('click.productPicker', '#categoryTabs .nav-link', function(e) {
                e.preventDefault();
                $('#categoryTabs .nav-link').removeClass('active');
                $(this).addClass('active');
                self._activeCategory = $(this).data('category');
                self.loadModalProducts();
            });

            // 4. تغيير نوع البند (المنتجات / الخدمات) عبر أزرار الراديو
            $(document).off('change.productPicker', 'input[name="picker-type"]').on('change.productPicker', 'input[name="picker-type"]', function() {
                self._activeType = $(this).val();
                self._activeCategory = 'all';
                $('#categoryTabs .nav-link').removeClass('active');
                $('#categoryTabs .nav-link[data-category="all"]').addClass('active');
                self.loadModalProducts();
            });

            // 5. البحث الفوري داخل المودال
            $(document).off('input.productPicker', '#picker-search').on('input.productPicker', '#picker-search', function() {
                self._searchTerm = $(this).val().trim().toLowerCase();
                self.loadModalProducts();
            });

            // 6. اختيار منتج من شبكة الكروت في المودال
            $(document).off('click.productPicker', '.product-card').on('click.productPicker', '.product-card', function() {
                var $card = $(this);
                if (!self._activePickerRow) return;

                var product = {
                    id: $card.data('id'),
                    name: $card.data('name'),
                    code: $card.data('code') || '',
                    price: $card.data('price'),
                    stock: parseFloat($card.data('stock') || 0),
                    is_service: $card.data('is-service') === true || $card.data('is-service') === "true"
                };

                self.applyProductToRow(self._activePickerRow, product, 'modal');

                var modalEl = document.getElementById('productPickerModal');
                if (modalEl) {
                    var modal = bootstrap.Modal.getInstance(modalEl);
                    if (modal) modal.hide();
                }

                var $row = self._activePickerRow;
                self._activePickerRow = null;

                setTimeout(function() {
                    var $qtyInput = $row.find('.quantity');
                    if ($qtyInput.length) $qtyInput.focus().select();
                }, 300);
            });

            // 7. تغيير إعداد إظهار كافة المنتجات
            $(document).off('change.productPicker', '#show-all-products').on('change.productPicker', '#show-all-products', function() {
                if ($('#productPickerModal').hasClass('show')) {
                    self.loadModalProducts();
                }
            });

            // 8. البحث المباشر في حقل الباركود / الكود بجدول البنود
            $(document).off('input.productPicker', '.product-code-input').on('input.productPicker', '.product-code-input', function() {
                var $input = $(this);
                var query = $input.val().trim();
                var $row = $input.closest('.item-row');

                $input.removeClass('is-valid is-invalid');

                if (query === '') {
                    self.clearRowProductData($row);
                    return;
                }

                clearTimeout(self._lookupTimeout);
                self._lookupTimeout = setTimeout(function() {
                    self.performCodeLookup($row, $input, query);
                }, 300);
            });

            // 9. التحقق عند مغادرة حقل الباركود
            $(document).off('blur.productPicker', '.product-code-input').on('blur.productPicker', '.product-code-input', function() {
                var $input = $(this);
                var query = $input.val().trim();
                var $row = $input.closest('.item-row');

                if (query !== '' && !$input.hasClass('is-valid')) {
                    self.performCodeLookup($row, $input, query, true);
                }
            });

            // 10. تفريغ البنود عند تغيير المخزن
            $(document).off('change.productPicker', '#id_warehouse').on('change.productPicker', '#id_warehouse', function() {
                var firstRow = $('#items-container .item-row:first');
                $('#items-container .item-row:not(:first)').remove();
                self.clearRowProductData(firstRow);
                if (typeof window.calculateTotals === 'function') {
                    window.calculateTotals();
                }
            });
        },

        // تنفيذ طلب البحث المباشر بالكود / الباركود
        performCodeLookup: function($row, $input, query, isBlur) {
            var self = this;
            var warehouseId = self.options.getWarehouseId();
            var invoiceId = self.options.getInvoiceId();
            var lookupType = (self.options.type === 'purchase') ? 'purchase' : 'sale';

            $.ajax({
                url: '/products/api/invoice-product-lookup/',
                method: 'GET',
                data: {
                    q: query,
                    exact: 'true',
                    warehouse_id: warehouseId,
                    invoice_id: invoiceId,
                    type: lookupType
                },
                success: function(response) {
                    if (response.products && response.products.length > 0) {
                        var found = response.products[0];
                        var price = (self.options.priceField === 'cost_price') ? found.cost_price : found.selling_price;
                        var product = {
                            id: found.id,
                            name: found.name,
                            code: found.code || found.sku || query,
                            price: price,
                            stock: found.stock,
                            is_service: found.is_service === true || found.is_service === "true"
                        };

                        $input.removeClass('is-invalid').addClass('is-valid');
                        self.applyProductToRow($row, product, 'scan');

                        // التمرير والتنقل التلقائي عند مسح الباركود
                        var $isLastRow = $row.is('#items-container .item-row:last-child');
                        if ($isLastRow) {
                            var $addButton = $('#add-item');
                            if ($addButton.length) {
                                $addButton.trigger('click');
                                setTimeout(function() {
                                    var $newLastRow = $('#items-container .item-row:last-child');
                                    $newLastRow.find('.product-code-input').focus();
                                }, 150);
                            } else {
                                var $qtyInput = $row.find('.quantity');
                                if ($qtyInput.length) $qtyInput.focus().select();
                            }
                        } else {
                            var $qtyInput = $row.find('.quantity');
                            if ($qtyInput.length) $qtyInput.focus().select();
                        }
                    } else if (isBlur) {
                        $input.addClass('is-invalid');
                        if (typeof toastr !== 'undefined') {
                            toastr.warning('كود المنتج غير صحيح أو غير متوفر في هذا المخزن');
                        }
                    }
                }
            });
        },

        // تطبيق المنتج المختار على الصف
        applyProductToRow: function($row, product, matchType) {
            var self = this;
            $row.find('.product-picker-btn').html('<span class="selected-text">' + product.name + '</span><i class="fas fa-th-large text-muted small"></i>');
            $row.find('.product-code-input').val(product.code).removeClass('is-invalid').addClass('is-valid');
            
            var $idInput = $row.find('.product-id-input');
            $idInput.val(product.id)
                .attr('data-price', product.price)
                .attr('data-stock', product.stock)
                .attr('data-is-service', product.is_service);

            $row.find('.unit-price').val(product.price !== '' && product.price !== undefined ? (typeof smartFloat === 'function' ? smartFloat(product.price) : product.price) : '');

            if (product.is_service) {
                $row.find('.stock-info').html('<span class="text-success small"><i class="fas fa-tools"></i> خدمة</span>');
            } else {
                self.renderStockInfo($row, product.stock);
            }

            if (typeof self.options.onProductSelect === 'function') {
                self.options.onProductSelect($row, product, matchType);
            } else {
                if (typeof window.calculateRowTotal === 'function') {
                    window.calculateRowTotal($row);
                }
            }
        },

        // مسح بيانات الصف عند تفريغ البند
        clearRowProductData: function($row) {
            $row.find('.product-picker-btn').html('<span class="placeholder-text">اختر المنتج</span><i class="fas fa-th-large text-muted small"></i>');
            $row.find('.product-id-input').val('').removeAttr('data-price data-stock data-is-service');
            $row.find('.product-code-input').removeClass('is-valid is-invalid').val('');
            $row.find('.unit-price').val('');
            $row.find('.stock-info').html('');
            if (typeof window.calculateRowTotal === 'function') {
                window.calculateRowTotal($row);
            }
        },

        // تنظيف وحجم الصف عند إضافة بند جديد
        resetRow: function($row) {
            this.clearRowProductData($row);
            $row.find('.quantity').val('1');
            $row.find('.item-discount').val('0');
            $row.find('.item-total').val('0');
        },

        // تحميل أجهزة ومحتويات المودال
        loadModalProducts: function() {
            var self = this;
            var warehouseId = self.options.getWarehouseId();
            var invoiceId = self.options.getInvoiceId();
            var showAll = $('#show-all-products').is(':checked');

            clearTimeout(self._modalSearchTimeout);
            self._modalSearchTimeout = setTimeout(function() {
                var $grid = $('#products-grid');
                $grid.html('<div class="no-results text-center py-5 text-muted"><span class="spinner-border spinner-border-sm me-2"></span>جاري البحث...</div>');

                var lookupType = self._activeType;
                if (lookupType === 'all') {
                    lookupType = (self.options.type === 'purchase') ? 'purchase' : 'sale';
                }

                $.ajax({
                    url: '/products/api/invoice-product-lookup/',
                    method: 'GET',
                    data: {
                        q: self._searchTerm,
                        exact: 'false',
                        warehouse_id: warehouseId,
                        invoice_id: invoiceId,
                        type: lookupType,
                        show_all: showAll
                    },
                    success: function(response) {
                        var rawProducts = response.products || [];
                        self.updateCategoryTabs(rawProducts);

                        var products = rawProducts;
                        if (self._activeCategory !== 'all') {
                            products = products.filter(function(p) {
                                return String(p.category_id) === String(self._activeCategory);
                            });
                        }

                        $grid.empty();
                        if (products.length === 0) {
                            $grid.html('<div class="no-results text-center py-5 text-muted"><i class="fas fa-box-open fa-2x mb-2 d-block"></i>لا توجد نتائج</div>');
                            return;
                        }

                        products.forEach(function(p) {
                            var price = (self.options.priceField === 'cost_price') ? p.cost_price : p.selling_price;
                            var isService = p.is_service === true || p.is_service === "true" || p.is_service === "True" || p.is_service === 1;
                            var stockClass = (!isService && p.stock <= 0) ? 'out-of-stock' : '';
                            var stockLabel = '';

                            if (isService) {
                                stockLabel = '<span class="product-stock text-success"><i class="fas fa-tools"></i> خدمة</span>';
                            } else {
                                stockLabel = p.stock <= 0
                                    ? '<span class="product-stock low-stock">غير متوفر</span>'
                                    : (p.stock <= 5
                                        ? '<span class="product-stock low-stock">مخزون: ' + p.stock + '</span>'
                                        : '<span class="product-stock">مخزون: ' + p.stock + '</span>');
                            }

                            var displayPrice = typeof smartFloat === 'function' ? smartFloat(price) : price;
                            var $card = $('<div class="col-md-3 col-sm-4 col-6">' +
                                '<div class="product-card ' + stockClass + '" data-id="' + p.id + '" data-price="' + price + '" data-stock="' + p.stock + '" data-name="' + p.name + '" data-is-service="' + isService + '" data-code="' + (p.code || '') + '">' +
                                    '<div class="product-name">' + p.name + '</div>' +
                                    '<div class="product-footer">' +
                                        '<span class="product-price">' + displayPrice + ' ' + self.options.currencySymbol + '</span>' +
                                        stockLabel +
                                    '</div>' +
                                '</div>' +
                            '</div>');
                            $grid.append($card);
                        });
                    }
                });
            }, 300);
        },

        // تحديث إظهار وتفعيل التبويبات حسب نتائج المنتجات المتاحة
        updateCategoryTabs: function(products) {
            var self = this;
            var activeCatIds = {};
            (products || []).forEach(function(p) {
                if (p.category_id) {
                    activeCatIds[String(p.category_id)] = true;
                }
            });

            $('#categoryTabs .nav-link[data-category]').each(function() {
                var $tab = $(this);
                var catId = String($tab.data('category'));
                if (catId === 'all') {
                    $tab.parent().show();
                    return;
                }
                if (activeCatIds[catId]) {
                    $tab.parent().show();
                } else {
                    $tab.parent().hide();
                    if ($tab.hasClass('active')) {
                        $tab.removeClass('active');
                        $('#categoryTabs .nav-link[data-category="all"]').addClass('active');
                        self._activeCategory = 'all';
                    }
                }
            });
        },

        // طباعة حالة رصيد المخزون
        renderStockInfo: function($row, stock) {
            var $stockContainer = $row.find('.stock-info');
            if (stock <= 0) {
                $stockContainer.html('<span class="stock-warning">لا يوجد مخزون</span>');
            } else if (stock <= 5) {
                $stockContainer.html('<span class="stock-warning">المخزون المتاح: ' + stock + ' (منخفض)</span>');
            } else {
                $stockContainer.html('المخزون المتاح: ' + stock);
            }
        },

        // طلب تجمعي واحد لتحميل أرصدة المخزون للبنود القديمة عند فتح الصفحة
        loadInitialStock: function() {
            var self = this;
            var warehouseId = self.options.getWarehouseId();
            var invoiceId = self.options.getInvoiceId();
            var productIds = [];

            $('#items-container .product-id-input').each(function() {
                var val = $(this).val();
                if (val) productIds.push(val);
            });

            if (productIds.length === 0) return;

            var lookupType = (self.options.type === 'purchase') ? 'purchase' : 'sale';
            $.ajax({
                url: '/products/api/invoice-product-lookup/',
                method: 'GET',
                data: {
                    product_ids: productIds.join(','),
                    warehouse_id: warehouseId,
                    invoice_id: invoiceId,
                    type: lookupType
                },
                success: function(response) {
                    var products = response.products || [];
                    products.forEach(function(p) {
                        var $row = $('#items-container .product-id-input[value="' + p.id + '"]').closest('.item-row');
                        var price = (self.options.priceField === 'cost_price') ? p.cost_price : p.selling_price;
                        $row.find('.product-id-input')
                            .attr('data-price', price)
                            .attr('data-stock', p.stock)
                            .attr('data-is-service', p.is_service);
                        $row.find('.product-code-input').val(p.code);

                        if (p.is_service) {
                            $row.find('.stock-info').html('<span class="text-success small"><i class="fas fa-tools"></i> خدمة</span>');
                        } else {
                            self.renderStockInfo($row, p.stock);
                        }
                    });
                }
            });
        }
    };

    window.ProductPicker = ProductPicker;

})(window, jQuery);
