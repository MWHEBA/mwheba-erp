/**
 * نظام إدارة الجداول الموحد - Unified Table Management System
 * Global Table Manager for consistent DataTables configuration across all modules
 * 
 * @version 2.1.0
 * @description Provides unified DataTables initialization with Arabic language support,
 *              error handling, and consistent configuration across the application
 * 
 * Requirements: 3.1, 3.6, 8.1, 8.2
 */

/**
 * Global Table Manager - Main interface for table initialization
 * Provides consistent DataTables configuration with Arabic language support
 */
if (typeof window.GlobalTableManager === 'undefined') {
    window.GlobalTableManager = (function() {
        'use strict';
    
    /**
     * Default DataTables configuration
     * Used as base configuration for all tables unless overridden
     */
    const defaultConfig = {
        responsive: true,
        pageLength: 20,
        lengthMenu: [[10, 25, 50, 100, -1], [10, 25, 50, 100, "الكل"]],
        order: [[0, 'asc']],
        language: {
            search: "البحث:",
            lengthMenu: "عرض _MENU_ عنصر",
            info: "عرض _START_ إلى _END_ من _TOTAL_ عنصر",
            infoEmpty: "لا توجد بيانات",
            infoFiltered: "(تصفية من _MAX_ إجمالي)",
            paginate: {
                first: "الأول",
                last: "الأخير",
                next: "التالي",
                previous: "السابق"
            },
            emptyTable: "لا توجد بيانات للعرض",
            zeroRecords: "لم يتم العثور على نتائج",
            processing: "جاري المعالجة...",
            loadingRecords: "جاري التحميل..."
        },
        dom: '<"row"<"col-sm-12"tr>>' +
             '<"row"<"col-sm-12 col-md-5"i><"col-sm-12 col-md-7"p>>',
        searching: true,
        lengthChange: false,
        ordering: true,
        columnDefs: [
            { targets: '_all', className: 'text-center' }
        ]
    };
    
    /**
     * Check if required libraries are loaded
     * @returns {boolean} True if all required libraries are available
     */
    function checkRequiredLibraries() {
        const libraries = {
            'jQuery': typeof $ !== 'undefined',
            'DataTables': typeof $.fn !== 'undefined' && typeof $.fn.DataTable !== 'undefined'
        };
        
        let allLoaded = true;
        for (const [name, loaded] of Object.entries(libraries)) {
            if (!loaded) {
                console.error(`GlobalTableManager: مكتبة ${name} غير متوفرة - Required library ${name} is not loaded`);
                allLoaded = false;
            }
        }
        
        return allLoaded;
    }

    /**
     * Initialize a DataTable with unified configuration
     * 
     * @param {string} tableId - The ID of the table element to initialize
     * @param {Object} options - Custom DataTables options to merge with defaults
     * @returns {Object|null} DataTable instance or null if initialization fails
     * 
     * @example
     * GlobalTableManager.initializeTable('data-table', {
     *     order: [[1, 'asc']],
     *     columnDefs: [
     *         { targets: 0, width: '5%', orderable: false },
     *         { targets: -1, orderable: false }
     *     ]
     * });
     */
    function initializeTable(tableId, options = {}) {
        // Check if required libraries are loaded
        if (!checkRequiredLibraries()) {
            console.error('GlobalTableManager: Cannot initialize table - required libraries not loaded');
            return null;
        }
        
        // Use safe DataTable initialization if available
        if (typeof window.safeInitDataTable === 'function') {
            return window.safeInitDataTable(tableId, Object.assign({}, defaultConfig, options));
        }
        
        // Get table element
        const table = document.getElementById(tableId);
        if (!table) {
            console.info(`GlobalTableManager: الجدول "${tableId}" غير موجود - قد يكون بسبب عدم وجود بيانات للعرض`);
            return null;
        }
        
        // Skip tables that previously failed initialization
        if (table.classList.contains('table-failed')) {
            console.info(`GlobalTableManager: Skipping table "${tableId}" - previously failed initialization`);
            return null;
        }
        
        // Skip tables already initialized
        if (table.classList.contains('table-initialized') && $.fn.DataTable.isDataTable(table)) {
            console.info(`GlobalTableManager: Table "${tableId}" already initialized`);
            return $.fn.DataTable.Api(table);
        }
        
        // Validate table has data
        const tbody = table.querySelector('tbody');
        const rows = tbody ? tbody.querySelectorAll('tr') : [];
        
        if (rows.length === 0) {
            console.info(`GlobalTableManager: Skipping table "${tableId}" - no data rows`);
            return null;
        }
        
        // Check for empty state message
        if (rows.length === 1) {
            const firstRowText = rows[0].textContent.trim();
            if (firstRowText.includes('لا توجد') || firstRowText.includes('No data') || firstRowText === '') {
                console.info(`GlobalTableManager: Skipping table "${tableId}" - contains empty state message`);
                return null;
            }
        }
        
        // Validate table structure
        if (!validateTableStructure(tableId)) {
            console.warn(`GlobalTableManager: Table "${tableId}" has invalid structure`);
            return null;
        }
        
        // Check for external search control
        const hasExternalSearch = document.querySelector(`.table-search[data-table="${tableId}"]`) !== null;
        
        // Check for ordering disable attribute
        const disableOrdering = table.getAttribute('data-disable-ordering') === 'true';
        
        // Build configuration
        const tableConfig = Object.assign({}, defaultConfig, {
            searching: hasExternalSearch || defaultConfig.searching,
            ordering: !disableOrdering && defaultConfig.ordering
        });
        
        // Apply ordering override if specified
        if (disableOrdering) {
            tableConfig.columnDefs = [
                { targets: '_all', className: 'text-center', orderable: false }
            ];
        }
        
        // Merge with custom options (custom options take precedence)
        const mergedOptions = Object.assign({}, tableConfig, options);
        
        try {
            // Destroy existing DataTable if present
            if ($.fn.DataTable.isDataTable(table)) {
                try {
                    const existingTable = $.fn.DataTable.Api(table);
                    if (existingTable && typeof existingTable.destroy === 'function') {
                        existingTable.destroy(true);
                    }
                } catch (destroyError) {
                    console.warn(`GlobalTableManager: Error destroying existing table "${tableId}":`, destroyError);
                    
                    // Manual cleanup
                    try {
                        $(table).removeData();
                        $(table).removeClass('dataTable');
                        
                        const wrapper = $(table).closest('.dataTables_wrapper');
                        if (wrapper.length > 0) {
                            $(table).unwrap();
                        }
                        
                        $(table).find('.dataTables_empty').remove();
                    } catch (cleanupError) {
                        console.error(`GlobalTableManager: Failed to cleanup table "${tableId}":`, cleanupError);
                        return null;
                    }
                }
            }
            
            // Initialize DataTable
            const dataTable = $(table).DataTable(mergedOptions);
            
            // Setup external controls
            setupExternalControls(tableId, dataTable);
            
            // Mark as successfully initialized
            table.classList.add('table-initialized');
            
            return dataTable;
            
        } catch (error) {
            console.error(`GlobalTableManager: Error initializing table "${tableId}":`, error);
            
            // Attempt to fix column count mismatch and retry
            if (error.message && error.message.includes('_DT_CellIndex')) {
                try {
                    console.info(`GlobalTableManager: Attempting to fix column count for table "${tableId}"`);
                    fixColumnCount(tableId);
                    
                    // Destroy any partial initialization
                    if ($.fn.DataTable.isDataTable(table)) {
                        try {
                            $(table).DataTable().destroy();
                        } catch (destroyError) {
                            $(table).removeData();
                            $(table).removeClass('dataTable');
                        }
                    }
                    
                    // Retry initialization
                    const dataTable = $(table).DataTable(mergedOptions);
                    setupExternalControls(tableId, dataTable);
                    table.classList.add('table-initialized');
                    
                    console.info(`GlobalTableManager: Successfully fixed and initialized table "${tableId}"`);
                    return dataTable;
                    
                } catch (secondError) {
                    console.error(`GlobalTableManager: Failed to fix table "${tableId}":`, secondError);
                    table.classList.add('table-failed');
                    return null;
                }
            }
            
            table.classList.add('table-failed');
            return null;
        }
    }

    /**
     * Validate table structure (header columns match body columns)
     * 
     * @param {string} tableId - The ID of the table to validate
     * @returns {boolean} True if table structure is valid
     */
    function validateTableStructure(tableId) {
        const table = document.getElementById(tableId);
        if (!table) return false;
        
        try {
            const headColumns = table.querySelectorAll('thead th').length;
            const bodyRows = table.querySelectorAll('tbody tr');
            
            if (headColumns === 0) {
                console.warn(`GlobalTableManager: Table "${tableId}" has no header columns`);
                return false;
            }
            
            // Check column count matches in each row (skip empty state rows)
            for (let row of bodyRows) {
                // Skip rows marked as empty state
                if (row.getAttribute('data-empty') === 'true') {
                    continue;
                }
                
                const rowColumns = row.querySelectorAll('td').length;
                if (rowColumns !== headColumns) {
                    console.warn(`GlobalTableManager: Column mismatch in table "${tableId}": header=${headColumns}, row=${rowColumns}`);
                    return false;
                }
            }
            
            return true;
            
        } catch (error) {
            console.error(`GlobalTableManager: Error validating table "${tableId}":`, error);
            return false;
        }
    }

    /**
     * Setup external controls (search, length selector) for a table
     * 
     * @param {string} tableId - The ID of the table
     * @param {Object} dataTable - The DataTable instance
     */
    function setupExternalControls(tableId, dataTable) {
        // Setup external search input
        const searchInput = document.querySelector(`.table-search[data-table="${tableId}"]`);
        if (searchInput) {
            searchInput.addEventListener('keyup', function() {
                dataTable.search(this.value).draw();
            });
        }
        
        // Setup external length selector
        const lengthSelect = document.querySelector(`.table-length[data-table="${tableId}"]`);
        if (lengthSelect) {
            lengthSelect.addEventListener('change', function() {
                dataTable.page.len(parseInt(this.value)).draw();
            });
        }
    }

    /**
     * Fix column count mismatches in table rows
     * 
     * @param {string} tableId - The ID of the table to fix
     */
    function fixColumnCount(tableId) {
        const table = document.getElementById(tableId);
        if (!table) return;
        
        const headColumns = table.querySelectorAll('thead th').length;
        const bodyRows = table.querySelectorAll('tbody tr');
        
        bodyRows.forEach(row => {
            if (row.getAttribute('data-empty') === 'true') return;
            
            const cells = row.querySelectorAll('td');
            const currentColumns = cells.length;
            
            if (currentColumns < headColumns) {
                // Add empty cells
                for (let i = currentColumns; i < headColumns; i++) {
                    const newCell = document.createElement('td');
                    newCell.textContent = '-';
                    newCell.className = 'text-center';
                    row.appendChild(newCell);
                }
            } else if (currentColumns > headColumns) {
                // Remove extra cells
                for (let i = currentColumns - 1; i >= headColumns; i--) {
                    if (cells[i]) {
                        cells[i].remove();
                    }
                }
            }
        });
    }

    /**
     * Initialize all tables on the page
     * Automatically finds and initializes all tables with IDs
     */
    function initializeAllTables() {
        const tables = document.querySelectorAll('table[id]');
        
        tables.forEach(table => {
            const tableId = table.id;
            
            // Skip tables marked to not use DataTables
            if (table.classList.contains('no-datatables')) {
                return;
            }
            
            // Skip tables that failed or are already initialized
            if (table.classList.contains('table-failed') || table.classList.contains('table-initialized')) {
                return;
            }
            
            // Validate table is in DOM
            if (!document.contains(table)) {
                console.warn(`GlobalTableManager: Skipping table "${tableId}" - not in DOM`);
                return;
            }
            
            // Validate table has tbody
            const tbody = table.querySelector('tbody');
            if (!tbody) {
                console.warn(`GlobalTableManager: Skipping table "${tableId}" - no tbody element`);
                return;
            }
            
            // Validate table has rows
            const rows = tbody.querySelectorAll('tr');
            if (rows.length === 0) {
                console.info(`GlobalTableManager: Skipping table "${tableId}" - no data rows`);
                return;
            }
            
            // Check for empty state message
            const firstRow = rows[0];
            if (rows.length === 1 && firstRow.textContent.includes('لا توجد')) {
                console.info(`GlobalTableManager: Skipping table "${tableId}" - empty state message`);
                return;
            }
            
            try {
                initializeTable(tableId);
            } catch (error) {
                console.error(`GlobalTableManager: Failed to initialize table "${tableId}":`, error);
                table.classList.add('table-failed');
            }
        });
    }
    
    /**
     * Reset all tables state (for debugging/development)
     * Removes initialization markers and destroys DataTables instances
     */
    function resetAllTables() {
        const tables = document.querySelectorAll('table[id]');
        tables.forEach(table => {
            table.classList.remove('table-failed', 'table-initialized');
            
            // Cleanup DataTables if present
            if ($.fn.DataTable.isDataTable(table)) {
                try {
                    $(table).DataTable().destroy();
                } catch (e) {
                    // Ignore errors during cleanup
                }
            }
        });
        console.info('GlobalTableManager: Reset all tables state');
    }
    
    /**
     * Export table data to CSV format
     * 
     * @param {string} tableId - The ID of the table to export
     * @param {string} filename - The filename for the exported file
     */
    function exportToCSV(tableId, filename = 'export.csv') {
        const table = document.getElementById(tableId);
        if (!table) {
            console.error(`GlobalTableManager: Cannot export - table "${tableId}" not found`);
            return;
        }
        
        const rows = table.querySelectorAll('tr');
        let csv = [];
        
        rows.forEach(row => {
            const cells = row.querySelectorAll('th, td');
            const rowData = [];
            
            cells.forEach(cell => {
                // Skip action columns
                if (!cell.classList.contains('col-actions')) {
                    let text = cell.textContent.trim();
                    // Escape quotes
                    text = text.replace(/"/g, '""');
                    rowData.push(`"${text}"`);
                }
            });
            
            if (rowData.length > 0) {
                csv.push(rowData.join(','));
            }
        });
        
        // Add BOM for Arabic support
        const csvContent = "\uFEFF" + csv.join('\n');
        
        // Download file
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        const url = URL.createObjectURL(blob);
        link.setAttribute('href', url);
        link.setAttribute('download', filename);
        link.style.visibility = 'hidden';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        
        console.info(`GlobalTableManager: Exported table "${tableId}" to CSV`);
    }
    
    /**
     * Export table data to Excel format
     * Requires XLSX library to be loaded
     * 
     * @param {string} tableId - The ID of the table to export
     * @param {string} filename - The filename for the exported file
     */
    function exportToExcel(tableId, filename = 'export.xlsx') {
        if (typeof XLSX === 'undefined') {
            console.warn('GlobalTableManager: XLSX library not available - falling back to CSV export');
            exportToCSV(tableId, filename.replace('.xlsx', '.csv'));
            return;
        }
        
        const table = document.getElementById(tableId);
        if (!table) {
            console.error(`GlobalTableManager: Cannot export - table "${tableId}" not found`);
            return;
        }
        
        // Clone table without action columns
        const tableClone = table.cloneNode(true);
        const actionColumns = tableClone.querySelectorAll('.col-actions');
        actionColumns.forEach(col => col.remove());
        
        // Convert to Excel
        const wb = XLSX.utils.table_to_book(tableClone, {sheet: "البيانات"});
        XLSX.writeFile(wb, filename);
        
        console.info(`GlobalTableManager: Exported table "${tableId}" to Excel`);
    }
    
        // Public API
        return {
            initializeTable: initializeTable,
            initializeAllTables: initializeAllTables,
            resetAllTables: resetAllTables,
            exportToCSV: exportToCSV,
            exportToExcel: exportToExcel,
            checkRequiredLibraries: checkRequiredLibraries,
            defaultConfig: defaultConfig
        };
        
    }()); // End of IIFE
} // End of if statement

// Backward compatibility - Legacy function names
// These are maintained for compatibility with existing code
if (typeof window.initGlobalTable === 'undefined') {
    window.initGlobalTable = function(tableId, options = {}) {
        // التحقق من وجود الجدول قبل المحاولة
        const table = document.getElementById(tableId);
        if (!table) {
            console.info(`initGlobalTable: الجدول "${tableId}" غير موجود في الصفحة - قد يكون بسبب عدم وجود بيانات`);
            return null;
        }
        return window.GlobalTableManager.initializeTable(tableId, options);
    };
}

if (typeof window.exportTableToCSV === 'undefined') {
    window.exportTableToCSV = function(tableId, filename) {
        return window.GlobalTableManager.exportToCSV(tableId, filename);
    };
}

if (typeof window.exportTableToExcel === 'undefined') {
    window.exportTableToExcel = function(tableId, filename) {
        return window.GlobalTableManager.exportToExcel(tableId, filename);
    };
}

/**
 * Setup export button event listeners
 * Automatically binds click events to export buttons
 */
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function() {
        setupExportButtons();
    });
} else {
    setupExportButtons();
}

function setupExportButtons() {
    // CSV export buttons
    document.addEventListener('click', function(e) {
        if (e.target.classList.contains('btn-export-table')) {
            const tableId = e.target.getAttribute('data-table');
            const filename = e.target.getAttribute('data-filename') || 'export.csv';
            window.GlobalTableManager.exportToCSV(tableId, filename);
        }
        
        // Excel export buttons
        if (e.target.classList.contains('btn-export-excel')) {
            const tableId = e.target.getAttribute('data-table');
            const filename = e.target.getAttribute('data-filename') || 'export.xlsx';
            window.GlobalTableManager.exportToExcel(tableId, filename);
        }
    });
}
