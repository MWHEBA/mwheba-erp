/**
 * ========================================
 * Unified UI Components JavaScript Library
 * مكتبة JavaScript للمكونات الموحدة
 * ========================================
 * 
 * مكتبة شاملة لإدارة المكونات الموحدة في نظام إدارة الشركة
 * تتضمن جميع الوظائف والتفاعلات للمكونات الموحدة
 * 
 * المكونات:
 * 1. Form Components (مكونات النماذج)
 * 2. Table Components (مكونات الجداول)
 * 3. Modal Components (مكونات النوافذ المنبثقة)
 * 4. Tab Components (مكونات التبويبات)
 * 5. Validation Components (مكونات التحقق)
 * 6. Search Components (مكونات البحث)
 * 7. Filter Components (مكونات التصفية)
 * 8. Utility Functions (وظائف مساعدة)
 * ========================================
 */

(function(window, document) {
    'use strict';

    // Namespace for unified components
    window.UnifiedComponents = window.UnifiedComponents || {};

    /**
     * ========================================
     * 1. FORM COMPONENTS (مكونات النماذج)
     * ========================================
     */

    class UnifiedForm {
        constructor(element, options = {}) {
            this.element = element;
            this.options = {
                validateOnSubmit: true,
                validateOnBlur: true,
                showSuccessMessages: true,
                autoFocus: true,
                ...options
            };
            
            this.validators = new Map();
            this.init();
        }

        init() {
            this.setupValidation();
            this.setupAutoFocus();
            this.setupFormSubmission();
            this.setupFieldInteractions();
        }

        setupValidation() {
            if (!this.options.validateOnSubmit && !this.options.validateOnBlur) return;

            const fields = this.element.querySelectorAll('.unified-form-control');
            
            fields.forEach(field => {
                if (this.options.validateOnBlur) {
                    field.addEventListener('blur', (e) => this.validateField(e.target));
                }
                
                field.addEventListener('input', (e) => this.clearFieldError(e.target));
            });

            if (this.options.validateOnSubmit) {
                this.element.addEventListener('submit', (e) => this.handleSubmit(e));
            }
        }

        setupAutoFocus() {
            if (!this.options.autoFocus) return;
            
            const firstField = this.element.querySelector('.unified-form-control:not([disabled])');
            if (firstField) {
                setTimeout(() => firstField.focus(), 100);
            }
        }

        setupFormSubmission() {
            const submitButtons = this.element.querySelectorAll('[type="submit"]');
            submitButtons.forEach(button => {
                button.addEventListener('click', (e) => {
                    if (button.dataset.loading !== 'true') {
                        this.setButtonLoading(button, true);
                    }
                });
            });
        }

        setupFieldInteractions() {
            // Setup input groups
            const inputGroups = this.element.querySelectorAll('.unified-input-group');
            inputGroups.forEach(group => {
                const input = group.querySelector('.unified-form-control');
                if (input) {
                    input.addEventListener('focus', () => group.classList.add('focused'));
                    input.addEventListener('blur', () => group.classList.remove('focused'));
                }
            });

            // Setup switches
            const switches = this.element.querySelectorAll('.unified-switch input');
            switches.forEach(switchInput => {
                switchInput.addEventListener('change', (e) => {
                    this.triggerEvent('switchChange', {
                        element: e.target,
                        checked: e.target.checked
                    });
                });
            });
        }

        validateField(field) {
            const fieldName = field.name || field.id;
            const validator = this.validators.get(fieldName);
            
            if (validator) {
                const result = validator(field.value, field);
                this.displayFieldValidation(field, result);
                return result.isValid;
            }

            // Default validation
            const result = this.defaultValidation(field);
            this.displayFieldValidation(field, result);
            return result.isValid;
        }

        defaultValidation(field) {
            const value = field.value.trim();
            const isRequired = field.hasAttribute('required');
            
            if (isRequired && !value) {
                return {
                    isValid: false,
                    message: 'هذا الحقل مطلوب'
                };
            }

            // Email validation
            if (field.type === 'email' && value) {
                const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
                if (!emailRegex.test(value)) {
                    return {
                        isValid: false,
                        message: 'يرجى إدخال بريد إلكتروني صحيح'
                    };
                }
            }

            // Number validation
            if (field.type === 'number' && value) {
                const min = field.getAttribute('min');
                const max = field.getAttribute('max');
                const numValue = parseFloat(value);
                
                if (min && numValue < parseFloat(min)) {
                    return {
                        isValid: false,
                        message: `القيمة يجب أن تكون أكبر من أو تساوي ${min}`
                    };
                }
                
                if (max && numValue > parseFloat(max)) {
                    return {
                        isValid: false,
                        message: `القيمة يجب أن تكون أصغر من أو تساوي ${max}`
                    };
                }
            }

            return { isValid: true };
        }

        displayFieldValidation(field, result) {
            this.clearFieldError(field);
            
            if (result.isValid) {
                field.classList.remove('is-invalid');
                if (this.options.showSuccessMessages && field.value.trim()) {
                    field.classList.add('is-valid');
                }
            } else {
                field.classList.add('is-invalid');
                field.classList.remove('is-valid');
                this.showFieldError(field, result.message);
            }
        }

        showFieldError(field, message) {
            const errorElement = document.createElement('div');
            errorElement.className = 'unified-form-error';
            errorElement.innerHTML = `<i class="fas fa-exclamation-circle icon"></i>${message}`;
            
            field.parentNode.appendChild(errorElement);
        }

        clearFieldError(field) {
            const existingError = field.parentNode.querySelector('.unified-form-error');
            if (existingError) {
                existingError.remove();
            }
            field.classList.remove('is-invalid', 'is-valid');
        }

        handleSubmit(e) {
            const isValid = this.validateForm();
            
            if (!isValid) {
                e.preventDefault();
                this.focusFirstInvalidField();
                return false;
            }

            this.triggerEvent('formSubmit', { form: this.element });
            return true;
        }

        validateForm() {
            const fields = this.element.querySelectorAll('.unified-form-control');
            let isValid = true;
            
            fields.forEach(field => {
                if (!this.validateField(field)) {
                    isValid = false;
                }
            });
            
            return isValid;
        }

        focusFirstInvalidField() {
            const firstInvalid = this.element.querySelector('.unified-form-control.is-invalid');
            if (firstInvalid) {
                firstInvalid.focus();
                firstInvalid.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        }

        setButtonLoading(button, loading) {
            if (loading) {
                button.dataset.originalText = button.innerHTML;
                button.innerHTML = '<span class="unified-spinner unified-spinner-sm"></span> جاري المعالجة...';
                button.disabled = true;
                button.dataset.loading = 'true';
            } else {
                button.innerHTML = button.dataset.originalText || button.innerHTML;
                button.disabled = false;
                button.dataset.loading = 'false';
            }
        }

        addValidator(fieldName, validator) {
            this.validators.set(fieldName, validator);
        }

        triggerEvent(eventName, data) {
            const event = new CustomEvent(`unified:${eventName}`, {
                detail: data,
                bubbles: true
            });
            this.element.dispatchEvent(event);
        }
    }

    /**
     * ========================================
     * 2. TABLE COMPONENTS (مكونات الجداول)
     * ========================================
     */

    class UnifiedTable {
        constructor(element, options = {}) {
            this.element = element;
            this.options = {
                sortable: true,
                selectable: false,
                searchable: true,
                paginated: true,
                pageSize: 10,
                ...options
            };
            
            this.data = [];
            this.filteredData = [];
            this.currentPage = 1;
            this.sortColumn = null;
            this.sortDirection = 'asc';
            this.selectedRows = new Set();
            
            this.init();
        }

        init() {
            this.setupSorting();
            this.setupSelection();
            this.setupSearch();
            this.setupPagination();
            this.loadData();
        }

        setupSorting() {
            if (!this.options.sortable) return;
            
            const headers = this.element.querySelectorAll('th.sortable');
            headers.forEach(header => {
                header.addEventListener('click', () => {
                    const column = header.dataset.column;
                    this.sort(column);
                });
            });
        }

        setupSelection() {
            if (!this.options.selectable) return;
            
            // Add select all checkbox
            const headerRow = this.element.querySelector('thead tr');
            if (headerRow) {
                const selectAllCell = document.createElement('th');
                selectAllCell.innerHTML = '<input type="checkbox" class="select-all">';
                headerRow.insertBefore(selectAllCell, headerRow.firstChild);
                
                const selectAllCheckbox = selectAllCell.querySelector('.select-all');
                selectAllCheckbox.addEventListener('change', (e) => {
                    this.selectAll(e.target.checked);
                });
            }
            
            // Add individual checkboxes
            this.updateSelectionCheckboxes();
        }

        setupSearch() {
            if (!this.options.searchable) return;
            
            const searchInput = document.querySelector(`[data-table="${this.element.id}"] .table-search`);
            if (searchInput) {
                searchInput.addEventListener('input', (e) => {
                    this.search(e.target.value);
                });
            }
        }

        setupPagination() {
            if (!this.options.paginated) return;
            
            const pageSizeSelect = document.querySelector(`[data-table="${this.element.id}"] .table-length`);
            if (pageSizeSelect) {
                pageSizeSelect.addEventListener('change', (e) => {
                    this.options.pageSize = parseInt(e.target.value);
                    this.currentPage = 1;
                    this.render();
                });
            }
        }

        loadData() {
            // Extract data from existing table rows
            const rows = this.element.querySelectorAll('tbody tr');
            this.data = Array.from(rows).map((row, index) => {
                const cells = row.querySelectorAll('td');
                const rowData = { _index: index, _element: row };
                
                cells.forEach((cell, cellIndex) => {
                    const header = this.element.querySelector(`th:nth-child(${cellIndex + 1})`);
                    const column = header ? (header.dataset.column || `col_${cellIndex}`) : `col_${cellIndex}`;
                    rowData[column] = cell.textContent.trim();
                });
                
                return rowData;
            });
            
            this.filteredData = [...this.data];
            this.render();
        }

        sort(column) {
            if (this.sortColumn === column) {
                this.sortDirection = this.sortDirection === 'asc' ? 'desc' : 'asc';
            } else {
                this.sortColumn = column;
                this.sortDirection = 'asc';
            }
            
            this.filteredData.sort((a, b) => {
                let aVal = a[column] || '';
                let bVal = b[column] || '';
                
                // Try to parse as numbers
                const aNum = parseFloat(aVal);
                const bNum = parseFloat(bVal);
                
                if (!isNaN(aNum) && !isNaN(bNum)) {
                    aVal = aNum;
                    bVal = bNum;
                }
                
                if (aVal < bVal) return this.sortDirection === 'asc' ? -1 : 1;
                if (aVal > bVal) return this.sortDirection === 'asc' ? 1 : -1;
                return 0;
            });
            
            this.updateSortHeaders();
            this.render();
        }

        updateSortHeaders() {
            const headers = this.element.querySelectorAll('th.sortable');
            headers.forEach(header => {
                header.classList.remove('asc', 'desc');
                if (header.dataset.column === this.sortColumn) {
                    header.classList.add(this.sortDirection);
                }
            });
        }

        search(query) {
            if (!query.trim()) {
                this.filteredData = [...this.data];
            } else {
                const searchTerm = query.toLowerCase();
                this.filteredData = this.data.filter(row => {
                    return Object.values(row).some(value => 
                        String(value).toLowerCase().includes(searchTerm)
                    );
                });
            }
            
            this.currentPage = 1;
            this.render();
        }

        selectAll(checked) {
            if (checked) {
                this.getCurrentPageData().forEach(row => {
                    this.selectedRows.add(row._index);
                });
            } else {
                this.selectedRows.clear();
            }
            
            this.updateSelectionCheckboxes();
            this.triggerEvent('selectionChange', {
                selectedRows: Array.from(this.selectedRows)
            });
        }

        selectRow(index, checked) {
            if (checked) {
                this.selectedRows.add(index);
            } else {
                this.selectedRows.delete(index);
            }
            
            this.updateSelectionCheckboxes();
            this.triggerEvent('selectionChange', {
                selectedRows: Array.from(this.selectedRows)
            });
        }

        updateSelectionCheckboxes() {
            if (!this.options.selectable) return;
            
            const selectAllCheckbox = this.element.querySelector('.select-all');
            const currentPageData = this.getCurrentPageData();
            const selectedInPage = currentPageData.filter(row => this.selectedRows.has(row._index));
            
            if (selectAllCheckbox) {
                selectAllCheckbox.checked = selectedInPage.length === currentPageData.length && currentPageData.length > 0;
                selectAllCheckbox.indeterminate = selectedInPage.length > 0 && selectedInPage.length < currentPageData.length;
            }
            
            // Update individual checkboxes
            const rowCheckboxes = this.element.querySelectorAll('tbody .row-select');
            rowCheckboxes.forEach(checkbox => {
                const index = parseInt(checkbox.dataset.index);
                checkbox.checked = this.selectedRows.has(index);
            });
        }

        getCurrentPageData() {
            if (!this.options.paginated) return this.filteredData;
            
            const start = (this.currentPage - 1) * this.options.pageSize;
            const end = start + this.options.pageSize;
            return this.filteredData.slice(start, end);
        }

        render() {
            const tbody = this.element.querySelector('tbody');
            if (!tbody) return;
            
            const currentData = this.getCurrentPageData();
            
            // Clear existing rows
            tbody.innerHTML = '';
            
            if (currentData.length === 0) {
                this.renderEmptyState(tbody);
                return;
            }
            
            // Render rows
            currentData.forEach(rowData => {
                const originalRow = rowData._element;
                const newRow = originalRow.cloneNode(true);
                
                if (this.options.selectable) {
                    const selectCell = document.createElement('td');
                    selectCell.innerHTML = `<input type="checkbox" class="row-select" data-index="${rowData._index}">`;
                    newRow.insertBefore(selectCell, newRow.firstChild);
                    
                    const checkbox = selectCell.querySelector('.row-select');
                    checkbox.addEventListener('change', (e) => {
                        this.selectRow(rowData._index, e.target.checked);
                    });
                }
                
                tbody.appendChild(newRow);
            });
            
            this.updatePagination();
            this.updateTableInfo();
            this.updateSelectionCheckboxes();
        }

        renderEmptyState(tbody) {
            const colCount = this.element.querySelectorAll('thead th').length;
            const emptyRow = document.createElement('tr');
            emptyRow.innerHTML = `
                <td colspan="${colCount}" class="unified-table-empty">
                    <i class="fas fa-inbox icon"></i>
                    <h4>لا توجد بيانات</h4>
                    <p>لم يتم العثور على أي سجلات تطابق معايير البحث</p>
                </td>
            `;
            tbody.appendChild(emptyRow);
        }

        updatePagination() {
            if (!this.options.paginated) return;
            
            const totalPages = Math.ceil(this.filteredData.length / this.options.pageSize);
            const paginationContainer = document.querySelector(`[data-table="${this.element.id}"] .unified-table-pagination`);
            
            if (paginationContainer && totalPages > 1) {
                paginationContainer.innerHTML = this.generatePaginationHTML(totalPages);
                this.setupPaginationEvents(paginationContainer);
            }
        }

        generatePaginationHTML(totalPages) {
            let html = '<div class="unified-pagination">';
            
            // Previous button
            html += `<a href="#" class="unified-pagination-item ${this.currentPage === 1 ? 'disabled' : ''}" data-page="${this.currentPage - 1}">
                <i class="fas fa-chevron-right"></i>
            </a>`;
            
            // Page numbers
            for (let i = 1; i <= totalPages; i++) {
                if (i === 1 || i === totalPages || (i >= this.currentPage - 2 && i <= this.currentPage + 2)) {
                    html += `<a href="#" class="unified-pagination-item ${i === this.currentPage ? 'active' : ''}" data-page="${i}">${i}</a>`;
                } else if (i === this.currentPage - 3 || i === this.currentPage + 3) {
                    html += '<span class="unified-pagination-item disabled">...</span>';
                }
            }
            
            // Next button
            html += `<a href="#" class="unified-pagination-item ${this.currentPage === totalPages ? 'disabled' : ''}" data-page="${this.currentPage + 1}">
                <i class="fas fa-chevron-left"></i>
            </a>`;
            
            html += '</div>';
            return html;
        }

        setupPaginationEvents(container) {
            const links = container.querySelectorAll('.unified-pagination-item:not(.disabled)');
            links.forEach(link => {
                link.addEventListener('click', (e) => {
                    e.preventDefault();
                    const page = parseInt(e.target.closest('.unified-pagination-item').dataset.page);
                    if (page && page !== this.currentPage) {
                        this.currentPage = page;
                        this.render();
                    }
                });
            });
        }

        updateTableInfo() {
            const infoContainer = document.querySelector(`[data-table="${this.element.id}"] .unified-table-info`);
            if (infoContainer) {
                const start = (this.currentPage - 1) * this.options.pageSize + 1;
                const end = Math.min(this.currentPage * this.options.pageSize, this.filteredData.length);
                const total = this.filteredData.length;
                
                infoContainer.textContent = `عرض ${start} إلى ${end} من ${total} سجل`;
            }
        }

        triggerEvent(eventName, data) {
            const event = new CustomEvent(`unified:table:${eventName}`, {
                detail: data,
                bubbles: true
            });
            this.element.dispatchEvent(event);
        }
    }

    /**
     * ========================================
     * 3. MODAL COMPONENTS (مكونات النوافذ المنبثقة)
     * ========================================
     */

    class UnifiedModal {
        constructor(element, options = {}) {
            this.element = element;
            this.options = {
                backdrop: true,
                keyboard: true,
                focus: true,
                ...options
            };
            
            this.isOpen = false;
            this.init();
        }

        init() {
            this.setupEventListeners();
            this.setupKeyboardNavigation();
        }

        setupEventListeners() {
            // Close button
            const closeButton = this.element.querySelector('.unified-modal-close');
            if (closeButton) {
                closeButton.addEventListener('click', () => this.hide());
            }
            
            // Backdrop click
            if (this.options.backdrop) {
                this.element.addEventListener('click', (e) => {
                    if (e.target === this.element) {
                        this.hide();
                    }
                });
            }
        }

        setupKeyboardNavigation() {
            if (!this.options.keyboard) return;
            
            document.addEventListener('keydown', (e) => {
                if (this.isOpen && e.key === 'Escape') {
                    this.hide();
                }
            });
        }

        show() {
            if (this.isOpen) return;
            
            this.isOpen = true;
            this.element.classList.add('show');
            document.body.style.overflow = 'hidden';
            
            if (this.options.focus) {
                this.focusFirstElement();
            }
            
            this.triggerEvent('show');
        }

        hide() {
            if (!this.isOpen) return;
            
            this.isOpen = false;
            this.element.classList.remove('show');
            document.body.style.overflow = '';
            
            this.triggerEvent('hide');
        }

        toggle() {
            if (this.isOpen) {
                this.hide();
            } else {
                this.show();
            }
        }

        focusFirstElement() {
            const focusableElements = this.element.querySelectorAll(
                'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
            );
            
            if (focusableElements.length > 0) {
                focusableElements[0].focus();
            }
        }

        triggerEvent(eventName) {
            const event = new CustomEvent(`unified:modal:${eventName}`, {
                detail: { modal: this },
                bubbles: true
            });
            this.element.dispatchEvent(event);
        }
    }

    /**
     * ========================================
     * 4. TAB COMPONENTS (مكونات التبويبات)
     * ========================================
     */

    class UnifiedTabs {
        constructor(element, options = {}) {
            this.element = element;
            this.options = {
                defaultTab: 0,
                ...options
            };
            
            this.tabs = [];
            this.panes = [];
            this.activeTab = null;
            
            this.init();
        }

        init() {
            this.tabs = Array.from(this.element.querySelectorAll('.unified-tabs-link'));
            this.panes = Array.from(this.element.querySelectorAll('.unified-tabs-pane'));
            
            this.setupEventListeners();
            this.showTab(this.options.defaultTab);
        }

        setupEventListeners() {
            this.tabs.forEach((tab, index) => {
                tab.addEventListener('click', (e) => {
                    e.preventDefault();
                    this.showTab(index);
                });
            });
        }

        showTab(index) {
            if (index < 0 || index >= this.tabs.length) return;
            
            // Hide all tabs and panes
            this.tabs.forEach(tab => tab.classList.remove('active'));
            this.panes.forEach(pane => pane.classList.remove('active'));
            
            // Show selected tab and pane
            this.tabs[index].classList.add('active');
            if (this.panes[index]) {
                this.panes[index].classList.add('active');
            }
            
            this.activeTab = index;
            this.triggerEvent('tabChange', { activeTab: index });
        }

        getActiveTab() {
            return this.activeTab;
        }

        triggerEvent(eventName, data) {
            const event = new CustomEvent(`unified:tabs:${eventName}`, {
                detail: data,
                bubbles: true
            });
            this.element.dispatchEvent(event);
        }
    }

    /**
     * ========================================
     * 5. SEARCH COMPONENTS (مكونات البحث)
     * ========================================
     */

    class UnifiedSearch {
        constructor(element, options = {}) {
            this.element = element;
            this.options = {
                minLength: 2,
                delay: 300,
                placeholder: 'البحث...',
                ...options
            };
            
            this.searchTimeout = null;
            this.init();
        }

        init() {
            this.setupSearchInput();
            this.setupEventListeners();
        }

        setupSearchInput() {
            if (!this.element.querySelector('.search-icon')) {
                const icon = document.createElement('i');
                icon.className = 'fas fa-search search-icon';
                this.element.appendChild(icon);
            }
            
            const input = this.element.querySelector('input');
            if (input && !input.placeholder) {
                input.placeholder = this.options.placeholder;
            }
        }

        setupEventListeners() {
            const input = this.element.querySelector('input');
            if (!input) return;
            
            input.addEventListener('input', (e) => {
                this.handleSearch(e.target.value);
            });
            
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    this.performSearch(e.target.value);
                }
            });
        }

        handleSearch(query) {
            clearTimeout(this.searchTimeout);
            
            if (query.length < this.options.minLength) {
                this.triggerEvent('searchClear');
                return;
            }
            
            this.searchTimeout = setTimeout(() => {
                this.performSearch(query);
            }, this.options.delay);
        }

        performSearch(query) {
            this.triggerEvent('search', { query });
        }

        clear() {
            const input = this.element.querySelector('input');
            if (input) {
                input.value = '';
                this.triggerEvent('searchClear');
            }
        }

        triggerEvent(eventName, data = {}) {
            const event = new CustomEvent(`unified:search:${eventName}`, {
                detail: data,
                bubbles: true
            });
            this.element.dispatchEvent(event);
        }
    }

    /**
     * ========================================
     * 6. FILTER COMPONENTS (مكونات التصفية)
     * ========================================
     */

    class UnifiedFilter {
        constructor(element, options = {}) {
            this.element = element;
            this.options = {
                autoApply: true,
                ...options
            };
            
            this.filters = new Map();
            this.init();
        }

        init() {
            this.setupFilterControls();
            this.setupEventListeners();
        }

        setupFilterControls() {
            const filterInputs = this.element.querySelectorAll('select, input[type="text"], input[type="date"]');
            filterInputs.forEach(input => {
                const filterName = input.name || input.id;
                if (filterName) {
                    this.filters.set(filterName, input.value);
                }
            });
        }

        setupEventListeners() {
            const filterInputs = this.element.querySelectorAll('select, input[type="text"], input[type="date"]');
            
            filterInputs.forEach(input => {
                const eventType = input.tagName === 'SELECT' ? 'change' : 'input';
                
                input.addEventListener(eventType, (e) => {
                    const filterName = e.target.name || e.target.id;
                    this.updateFilter(filterName, e.target.value);
                });
            });
            
            // Apply button
            const applyButton = this.element.querySelector('.filter-apply');
            if (applyButton) {
                applyButton.addEventListener('click', () => {
                    this.applyFilters();
                });
            }
            
            // Clear button
            const clearButton = this.element.querySelector('.filter-clear');
            if (clearButton) {
                clearButton.addEventListener('click', () => {
                    this.clearFilters();
                });
            }
        }

        updateFilter(name, value) {
            this.filters.set(name, value);
            
            if (this.options.autoApply) {
                this.applyFilters();
            }
        }

        applyFilters() {
            const activeFilters = {};
            
            this.filters.forEach((value, name) => {
                if (value && value.trim()) {
                    activeFilters[name] = value;
                }
            });
            
            this.triggerEvent('filtersApply', { filters: activeFilters });
        }

        clearFilters() {
            const filterInputs = this.element.querySelectorAll('select, input[type="text"], input[type="date"]');
            
            filterInputs.forEach(input => {
                if (input.tagName === 'SELECT') {
                    input.selectedIndex = 0;
                } else {
                    input.value = '';
                }
                
                const filterName = input.name || input.id;
                this.filters.set(filterName, '');
            });
            
            this.triggerEvent('filtersClear');
            
            if (this.options.autoApply) {
                this.applyFilters();
            }
        }

        getFilters() {
            const activeFilters = {};
            this.filters.forEach((value, name) => {
                if (value && value.trim()) {
                    activeFilters[name] = value;
                }
            });
            return activeFilters;
        }

        triggerEvent(eventName, data = {}) {
            const event = new CustomEvent(`unified:filter:${eventName}`, {
                detail: data,
                bubbles: true
            });
            this.element.dispatchEvent(event);
        }
    }

    /**
     * ========================================
     * 7. UTILITY FUNCTIONS (وظائف مساعدة)
     * ========================================
     */

    const Utils = {
        // Format numbers
        formatNumber(number, decimals = 2) {
            return new Intl.NumberFormat('en-US', {
                minimumFractionDigits: decimals,
                maximumFractionDigits: decimals
            }).format(number);
        },

        // Format currency
        formatCurrency(amount, currency = 'EGP') {
            // استخدام الأرقام الإنجليزية مع الاحتفاظ بالعملة العربية
            const formattedNumber = new Intl.NumberFormat('en-US', {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2
            }).format(amount);
            
            // إضافة رمز العملة العربي يدوياً
            const currencySymbol = currency === 'EGP' ? 'ج.م' : currency;
            return `${formattedNumber} ${currencySymbol}`;
        },

        // Format dates
        formatDate(date, format = 'short') {
            const options = {
                short: { year: 'numeric', month: '2-digit', day: '2-digit' },
                long: { year: 'numeric', month: 'long', day: 'numeric' },
                time: { hour: '2-digit', minute: '2-digit' }
            };

            // استخدام الأرقام الإنجليزية مع الاحتفاظ بأسماء الأشهر العربية للتنسيق الطويل
            const locale = format === 'long' ? 'ar-EG' : 'en-GB';
            return new Intl.DateTimeFormat(locale, options[format] || options.short).format(new Date(date));
        },

        // Debounce function
        debounce(func, wait) {
            let timeout;
            return function executedFunction(...args) {
                const later = () => {
                    clearTimeout(timeout);
                    func(...args);
                };
                clearTimeout(timeout);
                timeout = setTimeout(later, wait);
            };
        },

        // Show toast notification
        showToast(message, type = 'info', duration = 3000) {
            // Create toast element
            const toast = document.createElement('div');
            toast.className = `unified-alert ${type}`;
            toast.innerHTML = `
                <div class="unified-alert-icon">
                    <i class="fas fa-${this.getToastIcon(type)}"></i>
                </div>
                <div class="unified-alert-content">
                    <div class="unified-alert-message">${message}</div>
                </div>
                <button class="unified-alert-close">
                    <i class="fas fa-times"></i>
                </button>
            `;

            // Add to page
            document.body.appendChild(toast);

            // Position toast
            toast.style.position = 'fixed';
            toast.style.top = '20px';
            toast.style.right = '20px';
            toast.style.zIndex = '9999';
            toast.style.minWidth = '300px';
            toast.style.maxWidth = '500px';

            // Setup close button
            const closeButton = toast.querySelector('.unified-alert-close');
            closeButton.addEventListener('click', () => {
                this.removeToast(toast);
            });

            // Auto remove
            if (duration > 0) {
                setTimeout(() => {
                    this.removeToast(toast);
                }, duration);
            }

            return toast;
        },

        getToastIcon(type) {
            const icons = {
                success: 'check-circle',
                warning: 'exclamation-triangle',
                danger: 'exclamation-circle',
                info: 'info-circle'
            };
            return icons[type] || icons.info;
        },

        removeToast(toast) {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(100%)';
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.parentNode.removeChild(toast);
                }
            }, 300);
        },

        // Copy to clipboard
        async copyToClipboard(text) {
            try {
                await navigator.clipboard.writeText(text);
                this.showToast('تم النسخ بنجاح', 'success');
                return true;
            } catch (err) {
                this.showToast('فشل في النسخ', 'danger');
                return false;
            }
        },

        // Validate form data
        validateFormData(data, rules) {
            const errors = {};

            Object.keys(rules).forEach(field => {
                const rule = rules[field];
                const value = data[field];

                if (rule.required && (!value || !value.toString().trim())) {
                    errors[field] = 'هذا الحقل مطلوب';
                    return;
                }

                if (value && rule.minLength && value.toString().length < rule.minLength) {
                    errors[field] = `يجب أن يكون الحد الأدنى ${rule.minLength} أحرف`;
                    return;
                }

                if (value && rule.maxLength && value.toString().length > rule.maxLength) {
                    errors[field] = `يجب أن يكون الحد الأقصى ${rule.maxLength} أحرف`;
                    return;
                }

                if (value && rule.pattern && !rule.pattern.test(value)) {
                    errors[field] = rule.message || 'تنسيق غير صحيح';
                    return;
                }
            });

            return {
                isValid: Object.keys(errors).length === 0,
                errors
            };
        }
    };

    /**
     * ========================================
     * 8. AUTO-INITIALIZATION (التهيئة التلقائية)
     * ========================================
     */

    function autoInit() {
        // Initialize forms
        document.querySelectorAll('.unified-form').forEach(form => {
            if (!form._unifiedForm) {
                form._unifiedForm = new UnifiedForm(form);
            }
        });

        // Initialize tables
        document.querySelectorAll('.unified-table-container').forEach(container => {
            const table = container.querySelector('.unified-table');
            if (table && !table._unifiedTable) {
                table._unifiedTable = new UnifiedTable(table);
            }
        });

        // Initialize modals
        document.querySelectorAll('.unified-modal-overlay').forEach(modal => {
            if (!modal._unifiedModal) {
                modal._unifiedModal = new UnifiedModal(modal);
            }
        });

        // Initialize tabs
        document.querySelectorAll('.unified-tabs').forEach(tabs => {
            if (!tabs._unifiedTabs) {
                tabs._unifiedTabs = new UnifiedTabs(tabs);
            }
        });

        // Initialize search components
        document.querySelectorAll('.unified-search-input').forEach(search => {
            if (!search._unifiedSearch) {
                search._unifiedSearch = new UnifiedSearch(search);
            }
        });

        // Initialize filter components
        document.querySelectorAll('.unified-filter').forEach(filter => {
            if (!filter._unifiedFilter) {
                filter._unifiedFilter = new UnifiedFilter(filter);
            }
        });
    }

    // Export to global namespace
    window.UnifiedComponents = {
        Form: UnifiedForm,
        Table: UnifiedTable,
        Modal: UnifiedModal,
        Tabs: UnifiedTabs,
        Search: UnifiedSearch,
        Filter: UnifiedFilter,
        Utils: Utils,
        autoInit: autoInit
    };

    // Auto-initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', autoInit);
    } else {
        autoInit();
    }

    // Re-initialize when new content is added
    const observer = new MutationObserver((mutations) => {
        let shouldReinit = false;
        
        mutations.forEach((mutation) => {
            if (mutation.type === 'childList') {
                mutation.addedNodes.forEach((node) => {
                    if (node.nodeType === Node.ELEMENT_NODE) {
                        if (node.classList && (
                            node.classList.contains('unified-form') ||
                            node.classList.contains('unified-table-container') ||
                            node.classList.contains('unified-modal-overlay') ||
                            node.classList.contains('unified-tabs') ||
                            node.classList.contains('unified-search-input') ||
                            node.classList.contains('unified-filter')
                        )) {
                            shouldReinit = true;
                        }
                    }
                });
            }
        });
        
        if (shouldReinit) {
            setTimeout(autoInit, 100);
        }
    });

    observer.observe(document.body, {
        childList: true,
        subtree: true
    });

})(window, document);