/**
 * ========================================
 * Unified Search and Filter JavaScript
 * مكونات JavaScript للبحث والفلترة الموحدة
 * ========================================
 * 
 * مكتبة JavaScript شاملة لنظام البحث والفلترة المتقدمة
 * تتضمن البحث الذكي، الفلاتر المتعددة، والاقتراحات التفاعلية
 * 
 * المكونات:
 * 1. Advanced Search (البحث المتقدم)
 * 2. Smart Filter System (نظام الفلترة الذكي)
 * 3. Search Suggestions (اقتراحات البحث)
 * 4. Filter Tags Manager (مدير علامات الفلترة)
 * 5. Quick Filters (الفلاتر السريعة)
 * 6. Search Results Manager (مدير نتائج البحث)
 * 7. Filter Panels (لوحات الفلترة)
 * 8. Search Analytics (تحليلات البحث)
 * ========================================
 */

(function(window, document) {
    'use strict';

    // Namespace for search and filter components
    window.UnifiedSearchFilter = window.UnifiedSearchFilter || {};

    /**
     * ========================================
     * 1. ADVANCED SEARCH (البحث المتقدم)
     * ========================================
     */

    class AdvancedSearch {
        constructor(element, options = {}) {
            this.element = element;
            this.options = {
                minLength: 2,
                delay: 300,
                placeholder: 'البحث...',
                showSuggestions: true,
                maxSuggestions: 10,
                searchFields: [],
                operators: ['يحتوي على', 'يساوي', 'يبدأ بـ', 'ينتهي بـ', 'أكبر من', 'أصغر من'],
                ...options
            };
            
            this.searchTimeout = null;
            this.isExpanded = false;
            this.searchFields = [];
            this.suggestions = [];
            this.currentQuery = '';
            
            this.init();
        }

        init() {
            this.setupSearchBox();
            this.setupAdvancedPanel();
            this.setupEventListeners();
            this.setupKeyboardNavigation();
        }
        setupSearchBox() {
            const searchBox = this.element.querySelector('.unified-search-box');
            if (!searchBox) return;

            const input = searchBox.querySelector('.unified-search-input');
            if (input && !input.placeholder) {
                input.placeholder = this.options.placeholder;
            }

            // Add loading indicator
            if (!searchBox.querySelector('.unified-search-loading')) {
                const loading = document.createElement('div');
                loading.className = 'unified-search-loading';
                loading.innerHTML = '<i class="fas fa-spinner"></i>';
                loading.style.display = 'none';
                searchBox.appendChild(loading);
            }

            // Add clear button functionality
            const clearButton = searchBox.querySelector('.unified-search-clear');
            if (clearButton) {
                clearButton.addEventListener('click', () => this.clearSearch());
            }
        }

        setupAdvancedPanel() {
            const advancedPanel = this.element.querySelector('.unified-advanced-search');
            if (!advancedPanel) return;

            const toggleButton = advancedPanel.querySelector('.unified-advanced-search-toggle');
            if (toggleButton) {
                toggleButton.addEventListener('click', () => this.toggleAdvancedSearch());
            }

            // Initialize with one search field
            this.addSearchField();
        }

        setupEventListeners() {
            const input = this.element.querySelector('.unified-search-input');
            if (!input) return;

            input.addEventListener('input', (e) => {
                this.handleSearchInput(e.target.value);
            });

            input.addEventListener('keydown', (e) => {
                this.handleKeyDown(e);
            });

            input.addEventListener('focus', () => {
                this.showSuggestions();
            });

            input.addEventListener('blur', () => {
                // Delay hiding suggestions to allow clicking
                setTimeout(() => this.hideSuggestions(), 200);
            });
        }

        setupKeyboardNavigation() {
            document.addEventListener('keydown', (e) => {
                if (e.key === 'Escape') {
                    this.hideSuggestions();
                    this.collapseAdvancedSearch();
                }
            });
        }

        handleSearchInput(query) {
            this.currentQuery = query;
            const searchBox = this.element.querySelector('.unified-search-box');
            
            if (query.trim()) {
                searchBox.classList.add('has-value');
            } else {
                searchBox.classList.remove('has-value');
            }

            clearTimeout(this.searchTimeout);

            if (query.length < this.options.minLength) {
                this.hideSuggestions();
                this.triggerEvent('searchClear');
                return;
            }

            this.showLoading(true);

            this.searchTimeout = setTimeout(() => {
                this.performSearch(query);
            }, this.options.delay);
        }

        handleKeyDown(e) {
            const suggestions = this.element.querySelector('.unified-search-suggestions');
            if (!suggestions || !suggestions.classList.contains('show')) return;

            const highlighted = suggestions.querySelector('.unified-search-suggestion.highlighted');
            const allSuggestions = suggestions.querySelectorAll('.unified-search-suggestion');

            switch (e.key) {
                case 'ArrowDown':
                    e.preventDefault();
                    this.highlightNextSuggestion(highlighted, allSuggestions);
                    break;
                case 'ArrowUp':
                    e.preventDefault();
                    this.highlightPreviousSuggestion(highlighted, allSuggestions);
                    break;
                case 'Enter':
                    e.preventDefault();
                    if (highlighted) {
                        this.selectSuggestion(highlighted);
                    } else {
                        this.performSearch(this.currentQuery);
                    }
                    break;
            }
        }

        performSearch(query) {
            this.showLoading(false);
            
            const searchData = {
                query: query.trim(),
                fields: this.getAdvancedSearchFields(),
                timestamp: new Date().toISOString()
            };

            this.triggerEvent('search', searchData);
            
            if (this.options.showSuggestions) {
                this.updateSuggestions(query);
            }
        }

        getAdvancedSearchFields() {
            const fields = [];
            const fieldRows = this.element.querySelectorAll('.unified-search-field-row');
            
            fieldRows.forEach(row => {
                const fieldSelect = row.querySelector('.unified-search-field-select select');
                const operatorSelect = row.querySelector('.unified-search-field-operator select');
                const valueInput = row.querySelector('.unified-search-field-value input');
                
                if (fieldSelect && operatorSelect && valueInput && valueInput.value.trim()) {
                    fields.push({
                        field: fieldSelect.value,
                        operator: operatorSelect.value,
                        value: valueInput.value.trim()
                    });
                }
            });
            
            return fields;
        }
        toggleAdvancedSearch() {
            const advancedPanel = this.element.querySelector('.unified-advanced-search');
            if (!advancedPanel) return;

            this.isExpanded = !this.isExpanded;
            
            if (this.isExpanded) {
                advancedPanel.classList.add('expanded');
            } else {
                advancedPanel.classList.remove('expanded');
            }

            this.triggerEvent('advancedToggle', { expanded: this.isExpanded });
        }

        collapseAdvancedSearch() {
            const advancedPanel = this.element.querySelector('.unified-advanced-search');
            if (advancedPanel) {
                advancedPanel.classList.remove('expanded');
                this.isExpanded = false;
            }
        }

        addSearchField() {
            const fieldsContainer = this.element.querySelector('.unified-search-field-group');
            if (!fieldsContainer) return;

            const fieldRow = document.createElement('div');
            fieldRow.className = 'unified-search-field-row';
            
            fieldRow.innerHTML = `
                <div class="unified-search-field-select">
                    <select class="unified-filter-control">
                        <option value="">اختر الحقل</option>
                        ${this.options.searchFields.map(field => 
                            `<option value="${field.value}">${field.label}</option>`
                        ).join('')}
                    </select>
                </div>
                <div class="unified-search-field-operator">
                    <select class="unified-filter-control">
                        ${this.options.operators.map(op => 
                            `<option value="${op}">${op}</option>`
                        ).join('')}
                    </select>
                </div>
                <div class="unified-search-field-value">
                    <input type="text" class="unified-filter-control" placeholder="القيمة">
                </div>
                <div class="unified-search-field-actions">
                    <button type="button" class="unified-search-field-add" onclick="this.closest('.unified-search-container')._advancedSearch.addSearchField()">
                        <i class="fas fa-plus"></i>
                    </button>
                    <button type="button" class="unified-search-field-remove" onclick="this.closest('.unified-search-field-row').remove()">
                        <i class="fas fa-minus"></i>
                    </button>
                </div>
            `;

            fieldsContainer.appendChild(fieldRow);
        }

        showSuggestions() {
            if (!this.options.showSuggestions || !this.currentQuery) return;
            
            const suggestions = this.element.querySelector('.unified-search-suggestions');
            if (suggestions && this.suggestions.length > 0) {
                suggestions.classList.add('show');
            }
        }

        hideSuggestions() {
            const suggestions = this.element.querySelector('.unified-search-suggestions');
            if (suggestions) {
                suggestions.classList.remove('show');
            }
        }

        updateSuggestions(query) {
            // This would typically fetch suggestions from server
            // For now, we'll use mock data
            this.suggestions = this.generateMockSuggestions(query);
            this.renderSuggestions();
        }

        generateMockSuggestions(query) {
            const mockSuggestions = [
                { text: 'العملاء', type: 'category', icon: 'fa-users' },
                { text: 'الموظفين', type: 'category', icon: 'fa-user-tie' },
                { text: 'الرسوم والمدفوعات', type: 'category', icon: 'fa-money-bill' },
                { text: 'الأقسام والوحدات', type: 'category', icon: 'fa-building' },
                { text: 'التقارير المالية', type: 'category', icon: 'fa-chart-bar' }
            ];

            return mockSuggestions
                .filter(s => s.text.includes(query))
                .slice(0, this.options.maxSuggestions);
        }

        renderSuggestions() {
            let suggestionsContainer = this.element.querySelector('.unified-search-suggestions');
            
            if (!suggestionsContainer) {
                suggestionsContainer = document.createElement('div');
                suggestionsContainer.className = 'unified-search-suggestions';
                this.element.querySelector('.unified-search-container').appendChild(suggestionsContainer);
            }

            if (this.suggestions.length === 0) {
                suggestionsContainer.innerHTML = '';
                suggestionsContainer.classList.remove('show');
                return;
            }

            suggestionsContainer.innerHTML = `
                <div class="unified-search-suggestions-header">اقتراحات البحث</div>
                ${this.suggestions.map(suggestion => `
                    <div class="unified-search-suggestion" data-suggestion="${suggestion.text}">
                        <div class="unified-search-suggestion-icon">
                            <i class="fas ${suggestion.icon}"></i>
                        </div>
                        <div class="unified-search-suggestion-content">
                            <div class="unified-search-suggestion-text">${this.highlightQuery(suggestion.text)}</div>
                            <div class="unified-search-suggestion-meta">${suggestion.type}</div>
                        </div>
                    </div>
                `).join('')}
            `;

            // Add click handlers
            suggestionsContainer.querySelectorAll('.unified-search-suggestion').forEach(suggestion => {
                suggestion.addEventListener('click', () => this.selectSuggestion(suggestion));
            });

            suggestionsContainer.classList.add('show');
        }

        highlightQuery(text) {
            if (!this.currentQuery) return text;
            
            const regex = new RegExp(`(${this.currentQuery})`, 'gi');
            return text.replace(regex, '<span class="highlight">$1</span>');
        }

        selectSuggestion(suggestionElement) {
            const suggestionText = suggestionElement.dataset.suggestion;
            const input = this.element.querySelector('.unified-search-input');
            
            if (input) {
                input.value = suggestionText;
                this.currentQuery = suggestionText;
            }

            this.hideSuggestions();
            this.performSearch(suggestionText);
        }

        highlightNextSuggestion(current, all) {
            if (current) {
                current.classList.remove('highlighted');
                const next = current.nextElementSibling;
                if (next && next.classList.contains('unified-search-suggestion')) {
                    next.classList.add('highlighted');
                } else if (all.length > 0) {
                    all[0].classList.add('highlighted');
                }
            } else if (all.length > 0) {
                all[0].classList.add('highlighted');
            }
        }

        highlightPreviousSuggestion(current, all) {
            if (current) {
                current.classList.remove('highlighted');
                const prev = current.previousElementSibling;
                if (prev && prev.classList.contains('unified-search-suggestion')) {
                    prev.classList.add('highlighted');
                } else if (all.length > 0) {
                    all[all.length - 1].classList.add('highlighted');
                }
            } else if (all.length > 0) {
                all[all.length - 1].classList.add('highlighted');
            }
        }

        showLoading(show) {
            const loading = this.element.querySelector('.unified-search-loading');
            const icon = this.element.querySelector('.unified-search-icon');
            
            if (loading && icon) {
                if (show) {
                    loading.style.display = 'block';
                    icon.style.display = 'none';
                } else {
                    loading.style.display = 'none';
                    icon.style.display = 'block';
                }
            }
        }

        clearSearch() {
            const input = this.element.querySelector('.unified-search-input');
            const searchBox = this.element.querySelector('.unified-search-box');
            
            if (input) {
                input.value = '';
                this.currentQuery = '';
            }
            
            if (searchBox) {
                searchBox.classList.remove('has-value');
            }

            this.hideSuggestions();
            this.triggerEvent('searchClear');
        }

        triggerEvent(eventName, data = {}) {
            const event = new CustomEvent(`unified:search:${eventName}`, {
                detail: { ...data, searchInstance: this },
                bubbles: true
            });
            this.element.dispatchEvent(event);
        }
    }
    /**
     * ========================================
     * 2. SMART FILTER SYSTEM (نظام الفلترة الذكي)
     * ========================================
     */

    class SmartFilterSystem {
        constructor(element, options = {}) {
            this.element = element;
            this.options = {
                autoApply: true,
                showActiveCount: true,
                allowMultiSelect: true,
                saveFilters: true,
                ...options
            };
            
            this.activeFilters = new Map();
            this.filterPanels = new Map();
            this.filterHistory = [];
            
            this.init();
        }

        init() {
            this.setupFilterPanels();
            this.setupEventListeners();
            this.loadSavedFilters();
        }

        setupFilterPanels() {
            const panels = this.element.querySelectorAll('.unified-filter-panel');
            
            panels.forEach(panel => {
                const panelId = panel.dataset.filterId || panel.id;
                if (panelId) {
                    this.filterPanels.set(panelId, new FilterPanel(panel, {
                        onFilterChange: (filterId, values) => this.updateFilter(filterId, values),
                        allowMultiSelect: this.options.allowMultiSelect
                    }));
                }
            });
        }

        setupEventListeners() {
            // Filter actions
            const applyButton = this.element.querySelector('.unified-filter-actions .unified-btn-primary');
            if (applyButton) {
                applyButton.addEventListener('click', () => this.applyFilters());
            }

            const clearButton = this.element.querySelector('.unified-filter-actions .unified-btn-ghost');
            if (clearButton) {
                clearButton.addEventListener('click', () => this.clearAllFilters());
            }

            // Quick filters
            const quickFilters = this.element.querySelectorAll('.unified-quick-filter');
            quickFilters.forEach(filter => {
                filter.addEventListener('click', (e) => {
                    e.preventDefault();
                    this.toggleQuickFilter(filter);
                });
            });
        }

        updateFilter(filterId, values) {
            if (values && values.length > 0) {
                this.activeFilters.set(filterId, values);
            } else {
                this.activeFilters.delete(filterId);
            }

            this.updateActiveFiltersDisplay();
            
            if (this.options.autoApply) {
                this.applyFilters();
            }
        }

        toggleQuickFilter(filterElement) {
            const filterId = filterElement.dataset.filter;
            const filterValue = filterElement.dataset.value;
            
            if (!filterId || !filterValue) return;

            filterElement.classList.toggle('active');
            
            if (filterElement.classList.contains('active')) {
                this.activeFilters.set(filterId, [filterValue]);
            } else {
                this.activeFilters.delete(filterId);
            }

            this.updateActiveFiltersDisplay();
            
            if (this.options.autoApply) {
                this.applyFilters();
            }
        }

        updateActiveFiltersDisplay() {
            const activeFiltersContainer = this.element.querySelector('.unified-active-filters');
            if (!activeFiltersContainer) return;

            // Clear existing tags
            const existingTags = activeFiltersContainer.querySelectorAll('.unified-filter-tag');
            existingTags.forEach(tag => tag.remove());

            // Add new tags
            this.activeFilters.forEach((values, filterId) => {
                values.forEach(value => {
                    const tag = this.createFilterTag(filterId, value);
                    activeFiltersContainer.appendChild(tag);
                });
            });

            // Update clear all button visibility
            const clearAllButton = activeFiltersContainer.querySelector('.unified-clear-all-filters');
            if (clearAllButton) {
                clearAllButton.style.display = this.activeFilters.size > 0 ? 'inline-block' : 'none';
            }

            // Update filter counts
            if (this.options.showActiveCount) {
                this.updateFilterCounts();
            }
        }

        createFilterTag(filterId, value) {
            const tag = document.createElement('div');
            tag.className = 'unified-filter-tag';
            tag.innerHTML = `
                <span class="unified-filter-tag-text">${filterId}: ${value}</span>
                <button class="unified-filter-tag-remove" data-filter="${filterId}" data-value="${value}">
                    <i class="fas fa-times"></i>
                </button>
            `;

            const removeButton = tag.querySelector('.unified-filter-tag-remove');
            removeButton.addEventListener('click', () => {
                this.removeFilterValue(filterId, value);
            });

            return tag;
        }

        removeFilterValue(filterId, value) {
            const currentValues = this.activeFilters.get(filterId) || [];
            const updatedValues = currentValues.filter(v => v !== value);
            
            if (updatedValues.length > 0) {
                this.activeFilters.set(filterId, updatedValues);
            } else {
                this.activeFilters.delete(filterId);
            }

            // Update corresponding filter panel
            const panel = this.filterPanels.get(filterId);
            if (panel) {
                panel.updateSelection(updatedValues);
            }

            this.updateActiveFiltersDisplay();
            
            if (this.options.autoApply) {
                this.applyFilters();
            }
        }

        updateFilterCounts() {
            this.filterPanels.forEach((panel, filterId) => {
                const count = this.activeFilters.get(filterId)?.length || 0;
                panel.updateCount(count);
            });
        }

        applyFilters() {
            const filterData = {};
            this.activeFilters.forEach((values, filterId) => {
                filterData[filterId] = values;
            });

            this.addToHistory(filterData);
            
            if (this.options.saveFilters) {
                this.saveFilters(filterData);
            }

            this.triggerEvent('filtersApply', { filters: filterData });
        }

        clearAllFilters() {
            this.activeFilters.clear();
            
            // Clear all filter panels
            this.filterPanels.forEach(panel => {
                panel.clearSelection();
            });

            // Clear quick filters
            const quickFilters = this.element.querySelectorAll('.unified-quick-filter.active');
            quickFilters.forEach(filter => filter.classList.remove('active'));

            this.updateActiveFiltersDisplay();
            
            if (this.options.autoApply) {
                this.applyFilters();
            }

            this.triggerEvent('filtersClear');
        }

        addToHistory(filterData) {
            this.filterHistory.unshift({
                filters: { ...filterData },
                timestamp: new Date().toISOString()
            });

            // Keep only last 10 filter states
            if (this.filterHistory.length > 10) {
                this.filterHistory = this.filterHistory.slice(0, 10);
            }
        }

        saveFilters(filterData) {
            if (!this.isStorageAvailable()) return;
            
            try {
                localStorage.setItem('unified-filters', JSON.stringify(filterData));
            } catch (e) {
                console.warn('Could not save filters to localStorage:', e);
            }
        }

        isStorageAvailable() {
            try {
                const test = '__storage_test__';
                localStorage.setItem(test, test);
                localStorage.removeItem(test);
                return true;
            } catch (e) {
                return false;
            }
        }

        loadSavedFilters() {
            if (!this.options.saveFilters || !this.isStorageAvailable()) return;

            try {
                const saved = localStorage.getItem('unified-filters');
                if (saved) {
                    const filterData = JSON.parse(saved);
                    Object.keys(filterData).forEach(filterId => {
                        this.activeFilters.set(filterId, filterData[filterId]);
                    });
                    this.updateActiveFiltersDisplay();
                }
            } catch (e) {
                console.warn('Could not load saved filters:', e);
            }
        }

        getActiveFilters() {
            const result = {};
            this.activeFilters.forEach((values, filterId) => {
                result[filterId] = [...values];
            });
            return result;
        }

        setFilters(filterData) {
            this.activeFilters.clear();
            
            Object.keys(filterData).forEach(filterId => {
                if (filterData[filterId] && filterData[filterId].length > 0) {
                    this.activeFilters.set(filterId, filterData[filterId]);
                }
            });

            // Update filter panels
            this.filterPanels.forEach((panel, filterId) => {
                const values = filterData[filterId] || [];
                panel.updateSelection(values);
            });

            this.updateActiveFiltersDisplay();
        }

        triggerEvent(eventName, data = {}) {
            const event = new CustomEvent(`unified:filter:${eventName}`, {
                detail: { ...data, filterInstance: this },
                bubbles: true
            });
            this.element.dispatchEvent(event);
        }
    }
    /**
     * ========================================
     * 3. FILTER PANEL (لوحة الفلترة)
     * ========================================
     */

    class FilterPanel {
        constructor(element, options = {}) {
            this.element = element;
            this.options = {
                allowMultiSelect: true,
                searchable: false,
                maxHeight: 300,
                onFilterChange: null,
                ...options
            };
            
            this.selectedValues = new Set();
            this.allOptions = [];
            this.filteredOptions = [];
            
            this.init();
        }

        init() {
            this.loadOptions();
            this.setupEventListeners();
            this.setupSearch();
        }

        loadOptions() {
            const options = this.element.querySelectorAll('.unified-filter-option');
            
            options.forEach(option => {
                const input = option.querySelector('input');
                const label = option.querySelector('.unified-filter-option-label');
                
                if (input && label) {
                    this.allOptions.push({
                        value: input.value,
                        label: label.textContent.trim(),
                        element: option,
                        input: input
                    });
                }
            });
            
            this.filteredOptions = [...this.allOptions];
        }

        setupEventListeners() {
            this.allOptions.forEach(option => {
                option.input.addEventListener('change', (e) => {
                    this.handleOptionChange(option.value, e.target.checked);
                });
            });

            // Panel toggle
            const header = this.element.querySelector('.unified-filter-panel-header');
            if (header) {
                header.addEventListener('click', () => this.togglePanel());
            }
        }

        setupSearch() {
            if (!this.options.searchable) return;

            const searchInput = this.element.querySelector('.filter-panel-search');
            if (searchInput) {
                searchInput.addEventListener('input', (e) => {
                    this.filterOptions(e.target.value);
                });
            }
        }

        handleOptionChange(value, checked) {
            if (checked) {
                if (this.options.allowMultiSelect) {
                    this.selectedValues.add(value);
                } else {
                    this.selectedValues.clear();
                    this.selectedValues.add(value);
                    // Uncheck other options
                    this.allOptions.forEach(opt => {
                        if (opt.value !== value) {
                            opt.input.checked = false;
                        }
                    });
                }
            } else {
                this.selectedValues.delete(value);
            }

            this.updateCount();
            
            if (this.options.onFilterChange) {
                this.options.onFilterChange(
                    this.element.dataset.filterId || this.element.id,
                    Array.from(this.selectedValues)
                );
            }
        }

        filterOptions(searchTerm) {
            const term = searchTerm.toLowerCase();
            
            this.allOptions.forEach(option => {
                const matches = option.label.toLowerCase().includes(term);
                option.element.style.display = matches ? 'flex' : 'none';
            });
        }

        updateSelection(values) {
            this.selectedValues.clear();
            
            values.forEach(value => {
                this.selectedValues.add(value);
            });

            // Update checkboxes
            this.allOptions.forEach(option => {
                option.input.checked = this.selectedValues.has(option.value);
            });

            this.updateCount();
        }

        clearSelection() {
            this.selectedValues.clear();
            
            this.allOptions.forEach(option => {
                option.input.checked = false;
            });

            this.updateCount();
        }

        updateCount(customCount = null) {
            const countElement = this.element.querySelector('.unified-filter-panel-count');
            if (countElement) {
                const count = customCount !== null ? customCount : this.selectedValues.size;
                countElement.textContent = count;
                countElement.style.display = count > 0 ? 'inline-block' : 'none';
            }
        }

        togglePanel() {
            const body = this.element.querySelector('.unified-filter-panel-body');
            if (body) {
                const isVisible = body.style.display !== 'none';
                body.style.display = isVisible ? 'none' : 'block';
            }
        }

        getSelectedValues() {
            return Array.from(this.selectedValues);
        }
    }

    /**
     * ========================================
     * 4. SEARCH RESULTS MANAGER (مدير نتائج البحث)
     * ========================================
     */

    class SearchResultsManager {
        constructor(element, options = {}) {
            this.element = element;
            this.options = {
                itemsPerPage: 10,
                showPagination: true,
                showSorting: true,
                sortOptions: [
                    { value: 'relevance', label: 'الأكثر صلة' },
                    { value: 'date_desc', label: 'الأحدث أولاً' },
                    { value: 'date_asc', label: 'الأقدم أولاً' },
                    { value: 'name_asc', label: 'الاسم (أ-ي)' },
                    { value: 'name_desc', label: 'الاسم (ي-أ)' }
                ],
                ...options
            };
            
            this.results = [];
            this.filteredResults = [];
            this.currentPage = 1;
            this.currentSort = 'relevance';
            this.totalResults = 0;
            
            this.init();
        }

        init() {
            this.setupSorting();
            this.setupPagination();
        }

        setupSorting() {
            if (!this.options.showSorting) return;

            const sortSelect = this.element.querySelector('.unified-search-results-sort select');
            if (sortSelect) {
                // Populate sort options
                sortSelect.innerHTML = this.options.sortOptions
                    .map(option => `<option value="${option.value}">${option.label}</option>`)
                    .join('');

                sortSelect.addEventListener('change', (e) => {
                    this.sortResults(e.target.value);
                });
            }
        }

        setupPagination() {
            // Pagination will be set up when results are rendered
        }

        displayResults(results, query = '') {
            this.results = results || [];
            this.filteredResults = [...this.results];
            this.totalResults = this.results.length;
            this.currentPage = 1;
            
            this.updateResultsInfo();
            this.renderResults(query);
            this.renderPagination();
        }

        renderResults(query = '') {
            const resultsBody = this.element.querySelector('.unified-search-results-body');
            if (!resultsBody) return;

            if (this.filteredResults.length === 0) {
                this.renderEmptyState(resultsBody);
                return;
            }

            const startIndex = (this.currentPage - 1) * this.options.itemsPerPage;
            const endIndex = startIndex + this.options.itemsPerPage;
            const pageResults = this.filteredResults.slice(startIndex, endIndex);

            resultsBody.innerHTML = pageResults
                .map(result => this.renderResultItem(result, query))
                .join('');

            // Add click handlers
            resultsBody.querySelectorAll('.unified-search-result-item').forEach(item => {
                item.addEventListener('click', (e) => {
                    const resultId = item.dataset.resultId;
                    const result = this.results.find(r => r.id === resultId);
                    if (result) {
                        this.triggerEvent('resultClick', { result, element: item });
                    }
                });
            });
        }

        renderResultItem(result, query = '') {
            const highlightedTitle = this.highlightText(result.title || '', query);
            const highlightedDescription = this.highlightText(result.description || '', query);
            
            const tags = result.tags ? result.tags.map(tag => 
                `<span class="unified-search-result-tag">${tag}</span>`
            ).join('') : '';

            return `
                <div class="unified-search-result-item" data-result-id="${result.id}">
                    <div class="unified-search-result-header">
                        <h4 class="unified-search-result-title">${highlightedTitle}</h4>
                        <div class="unified-search-result-meta">
                            ${result.date ? `<span><i class="fas fa-calendar"></i> ${new Date(result.date).toLocaleDateString('en-GB')}</span>` : ''}
                            ${result.type ? `<span><i class="fas fa-tag"></i> ${result.type}</span>` : ''}
                        </div>
                    </div>
                    ${result.description ? `<p class="unified-search-result-description">${highlightedDescription}</p>` : ''}
                    ${tags ? `<div class="unified-search-result-tags">${tags}</div>` : ''}
                </div>
            `;
        }

        renderEmptyState(container) {
            container.innerHTML = `
                <div class="unified-search-results-empty">
                    <i class="fas fa-search icon"></i>
                    <h4>لا توجد نتائج</h4>
                    <p>لم يتم العثور على أي نتائج تطابق معايير البحث الخاصة بك</p>
                </div>
            `;
        }

        highlightText(text, query) {
            if (!query || !text) return text;
            
            const regex = new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
            return text.replace(regex, '<span class="highlight">$1</span>');
        }

        sortResults(sortBy) {
            this.currentSort = sortBy;
            
            this.filteredResults.sort((a, b) => {
                switch (sortBy) {
                    case 'date_desc':
                        return new Date(b.date || 0) - new Date(a.date || 0);
                    case 'date_asc':
                        return new Date(a.date || 0) - new Date(b.date || 0);
                    case 'name_asc':
                        return (a.title || '').localeCompare(b.title || '', 'ar');
                    case 'name_desc':
                        return (b.title || '').localeCompare(a.title || '', 'ar');
                    case 'relevance':
                    default:
                        return (b.relevance || 0) - (a.relevance || 0);
                }
            });

            this.currentPage = 1;
            this.renderResults();
            this.renderPagination();
        }

        renderPagination() {
            if (!this.options.showPagination) return;

            const paginationContainer = this.element.querySelector('.unified-search-results-pagination');
            if (!paginationContainer) return;

            const totalPages = Math.ceil(this.filteredResults.length / this.options.itemsPerPage);
            
            if (totalPages <= 1) {
                paginationContainer.innerHTML = '';
                return;
            }

            let paginationHTML = '<div class="unified-pagination">';
            
            // Previous button
            paginationHTML += `
                <button class="unified-pagination-item ${this.currentPage === 1 ? 'disabled' : ''}" 
                        ${this.currentPage > 1 ? `onclick="this.closest('.unified-search-results')._searchResults.goToPage(${this.currentPage - 1})"` : ''}>
                    <i class="fas fa-chevron-right"></i>
                </button>
            `;
            
            // Page numbers
            for (let i = 1; i <= totalPages; i++) {
                if (i === 1 || i === totalPages || (i >= this.currentPage - 2 && i <= this.currentPage + 2)) {
                    paginationHTML += `
                        <button class="unified-pagination-item ${i === this.currentPage ? 'active' : ''}" 
                                onclick="this.closest('.unified-search-results')._searchResults.goToPage(${i})">
                            ${i}
                        </button>
                    `;
                } else if (i === this.currentPage - 3 || i === this.currentPage + 3) {
                    paginationHTML += '<span class="unified-pagination-item disabled">...</span>';
                }
            }
            
            // Next button
            paginationHTML += `
                <button class="unified-pagination-item ${this.currentPage === totalPages ? 'disabled' : ''}" 
                        ${this.currentPage < totalPages ? `onclick="this.closest('.unified-search-results')._searchResults.goToPage(${this.currentPage + 1})"` : ''}>
                    <i class="fas fa-chevron-left"></i>
                </button>
            `;
            
            paginationHTML += '</div>';
            paginationContainer.innerHTML = paginationHTML;
        }

        goToPage(page) {
            const totalPages = Math.ceil(this.filteredResults.length / this.options.itemsPerPage);
            
            if (page < 1 || page > totalPages) return;
            
            this.currentPage = page;
            this.renderResults();
            this.renderPagination();
            this.updateResultsInfo();
        }

        updateResultsInfo() {
            const infoElement = this.element.querySelector('.unified-search-results-info');
            if (!infoElement) return;

            const start = (this.currentPage - 1) * this.options.itemsPerPage + 1;
            const end = Math.min(this.currentPage * this.options.itemsPerPage, this.filteredResults.length);
            
            infoElement.innerHTML = `
                عرض <span class="unified-search-results-count">${start}</span> إلى 
                <span class="unified-search-results-count">${end}</span> من 
                <span class="unified-search-results-count">${this.filteredResults.length}</span> نتيجة
            `;
        }

        triggerEvent(eventName, data = {}) {
            const event = new CustomEvent(`unified:searchResults:${eventName}`, {
                detail: { ...data, resultsInstance: this },
                bubbles: true
            });
            this.element.dispatchEvent(event);
        }
    }
    /**
     * ========================================
     * 5. SEARCH ANALYTICS (تحليلات البحث)
     * ========================================
     */

    class SearchAnalytics {
        constructor(options = {}) {
            this.options = {
                trackSearches: true,
                trackFilters: true,
                trackResults: true,
                maxHistorySize: 1000,
                ...options
            };
            
            this.searchHistory = [];
            this.filterHistory = [];
            this.popularSearches = new Map();
            this.popularFilters = new Map();
            
            this.init();
        }

        init() {
            this.loadFromStorage();
        }

        isStorageAvailable() {
            try {
                const test = '__storage_test__';
                localStorage.setItem(test, test);
                localStorage.removeItem(test);
                return true;
            } catch (e) {
                return false;
            }
        }

        trackSearch(query, resultsCount = 0) {
            if (!this.options.trackSearches) return;

            const searchData = {
                query: query.trim(),
                timestamp: new Date().toISOString(),
                resultsCount,
                id: Date.now()
            };

            this.searchHistory.unshift(searchData);
            
            // Update popular searches
            const count = this.popularSearches.get(query) || 0;
            this.popularSearches.set(query, count + 1);

            this.trimHistory();
            this.saveToStorage();
        }

        trackFilter(filterId, values) {
            if (!this.options.trackFilters) return;

            const filterData = {
                filterId,
                values: [...values],
                timestamp: new Date().toISOString(),
                id: Date.now()
            };

            this.filterHistory.unshift(filterData);
            
            // Update popular filters
            const filterKey = `${filterId}:${values.join(',')}`;
            const count = this.popularFilters.get(filterKey) || 0;
            this.popularFilters.set(filterKey, count + 1);

            this.trimHistory();
            this.saveToStorage();
        }

        getPopularSearches(limit = 10) {
            return Array.from(this.popularSearches.entries())
                .sort((a, b) => b[1] - a[1])
                .slice(0, limit)
                .map(([query, count]) => ({ query, count }));
        }

        getRecentSearches(limit = 10) {
            return this.searchHistory.slice(0, limit);
        }

        getSearchStats() {
            const totalSearches = this.searchHistory.length;
            const uniqueSearches = new Set(this.searchHistory.map(s => s.query)).size;
            const avgResultsCount = totalSearches > 0 
                ? this.searchHistory.reduce((sum, s) => sum + s.resultsCount, 0) / totalSearches 
                : 0;

            return {
                totalSearches,
                uniqueSearches,
                avgResultsCount: Math.round(avgResultsCount * 100) / 100
            };
        }

        clearHistory() {
            this.searchHistory = [];
            this.filterHistory = [];
            this.popularSearches.clear();
            this.popularFilters.clear();
            this.saveToStorage();
        }

        trimHistory() {
            if (this.searchHistory.length > this.options.maxHistorySize) {
                this.searchHistory = this.searchHistory.slice(0, this.options.maxHistorySize);
            }
            
            if (this.filterHistory.length > this.options.maxHistorySize) {
                this.filterHistory = this.filterHistory.slice(0, this.options.maxHistorySize);
            }
        }

        saveToStorage() {
            if (!this.isStorageAvailable()) return;
            
            try {
                const data = {
                    searchHistory: this.searchHistory,
                    filterHistory: this.filterHistory,
                    popularSearches: Array.from(this.popularSearches.entries()),
                    popularFilters: Array.from(this.popularFilters.entries())
                };
                localStorage.setItem('unified-search-analytics', JSON.stringify(data));
            } catch (e) {
                console.warn('Could not save search analytics:', e);
            }
        }

        loadFromStorage() {
            if (!this.isStorageAvailable()) return;
            try {
                const data = localStorage.getItem('unified-search-analytics');
                if (data) {
                    const parsed = JSON.parse(data);
                    this.searchHistory = parsed.searchHistory || [];
                    this.filterHistory = parsed.filterHistory || [];
                    this.popularSearches = new Map(parsed.popularSearches || []);
                    this.popularFilters = new Map(parsed.popularFilters || []);
                }
            } catch (e) {
                console.warn('Could not load search analytics:', e);
            }
        }
    }

    /**
     * ========================================
     * 6. UTILITY FUNCTIONS (وظائف مساعدة)
     * ========================================
     */

    const SearchFilterUtils = {
        // Debounce function for search input
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

        // Highlight search terms in text
        highlightSearchTerms(text, terms) {
            if (!terms || !text) return text;
            
            const termArray = Array.isArray(terms) ? terms : [terms];
            let result = text;
            
            termArray.forEach(term => {
                if (term.trim()) {
                    const regex = new RegExp(`(${term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
                    result = result.replace(regex, '<span class="highlight">$1</span>');
                }
            });
            
            return result;
        },

        // Parse search query for advanced features
        parseSearchQuery(query) {
            const result = {
                terms: [],
                phrases: [],
                excludes: [],
                fields: {}
            };

            // Extract quoted phrases
            const phraseRegex = /"([^"]+)"/g;
            let match;
            while ((match = phraseRegex.exec(query)) !== null) {
                result.phrases.push(match[1]);
                query = query.replace(match[0], '');
            }

            // Extract field searches (field:value)
            const fieldRegex = /(\w+):(\S+)/g;
            while ((match = fieldRegex.exec(query)) !== null) {
                result.fields[match[1]] = match[2];
                query = query.replace(match[0], '');
            }

            // Extract exclusions (-term)
            const excludeRegex = /-(\S+)/g;
            while ((match = excludeRegex.exec(query)) !== null) {
                result.excludes.push(match[1]);
                query = query.replace(match[0], '');
            }

            // Remaining terms
            result.terms = query.trim().split(/\s+/).filter(term => term.length > 0);

            return result;
        },

        // Generate search suggestions based on history
        generateSuggestions(query, history, limit = 5) {
            if (!query || query.length < 2) return [];

            const suggestions = history
                .filter(item => item.query && item.query.toLowerCase().includes(query.toLowerCase()))
                .sort((a, b) => b.timestamp.localeCompare(a.timestamp))
                .slice(0, limit)
                .map(item => ({
                    text: item.query,
                    type: 'history',
                    icon: 'fa-history'
                }));

            return suggestions;
        },

        // Export search/filter data
        exportData(data, filename = 'search-data.json') {
            const blob = new Blob([JSON.stringify(data, null, 2)], { 
                type: 'application/json' 
            });
            
            const link = document.createElement('a');
            link.href = URL.createObjectURL(blob);
            link.download = filename;
            link.click();
            
            URL.revokeObjectURL(link.href);
        },

        // Validate filter values
        validateFilterValue(value, type) {
            switch (type) {
                case 'number':
                    return !isNaN(parseFloat(value));
                case 'date':
                    return !isNaN(Date.parse(value));
                case 'email':
                    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
                case 'text':
                default:
                    return value && value.trim().length > 0;
            }
        }
    };

    /**
     * ========================================
     * 7. AUTO-INITIALIZATION (التهيئة التلقائية)
     * ========================================
     */

    function autoInitSearchFilter() {
        // Initialize advanced search components
        document.querySelectorAll('.unified-search-container').forEach(container => {
            if (!container._advancedSearch) {
                const options = container.dataset.searchOptions ? 
                    JSON.parse(container.dataset.searchOptions) : {};
                container._advancedSearch = new AdvancedSearch(container, options);
            }
        });

        // Initialize filter systems
        document.querySelectorAll('.unified-filter-container').forEach(container => {
            if (!container._smartFilter) {
                const options = container.dataset.filterOptions ? 
                    JSON.parse(container.dataset.filterOptions) : {};
                container._smartFilter = new SmartFilterSystem(container, options);
            }
        });

        // Initialize search results
        document.querySelectorAll('.unified-search-results').forEach(results => {
            if (!results._searchResults) {
                const options = results.dataset.resultsOptions ? 
                    JSON.parse(results.dataset.resultsOptions) : {};
                results._searchResults = new SearchResultsManager(results, options);
            }
        });
    }

    /**
     * ========================================
     * EXPORT TO GLOBAL NAMESPACE
     * ========================================
     */

    // Create global analytics instance
    const globalAnalytics = new SearchAnalytics();

    window.UnifiedSearchFilter = {
        AdvancedSearch,
        SmartFilterSystem,
        FilterPanel,
        SearchResultsManager,
        SearchAnalytics,
        Utils: SearchFilterUtils,
        Analytics: globalAnalytics,
        autoInit: autoInitSearchFilter
    };

    // Auto-initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', autoInitSearchFilter);
    } else {
        autoInitSearchFilter();
    }

    // Re-initialize when new content is added
    const observer = new MutationObserver((mutations) => {
        let shouldReinit = false;
        
        mutations.forEach((mutation) => {
            if (mutation.type === 'childList') {
                mutation.addedNodes.forEach((node) => {
                    if (node.nodeType === Node.ELEMENT_NODE) {
                        if (node.classList && (
                            node.classList.contains('unified-search-container') ||
                            node.classList.contains('unified-filter-container') ||
                            node.classList.contains('unified-search-results')
                        )) {
                            shouldReinit = true;
                        }
                    }
                });
            }
        });
        
        if (shouldReinit) {
            setTimeout(autoInitSearchFilter, 100);
        }
    });

    observer.observe(document.body, {
        childList: true,
        subtree: true
    });

})(window, document);