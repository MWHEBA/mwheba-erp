/**
 * Permissions Dashboard JavaScript
 * Handles simplified permissions system with 42 custom permissions instead of 828
 */

class PermissionsDashboard {
    constructor() {
        this.currentTab = 'overview';
        this.matrixData = null;
        this.selectedUsers = [];
        this.csrfToken = $('[name=csrfmiddlewaretoken]').val();
    }

    init() {
        
        // Initialize CSRF token if not set
        if (!this.csrfToken) {
            this.csrfToken = $('[name=csrfmiddlewaretoken]').val();
        }
        
        this.bindEvents();
        this.initializeTooltips();
        this.loadInitialData();
        
        // Initialize safe storage fallback - no localStorage access attempts
        this.storageAvailable = false;
        
        // Always use fallback storage to prevent any localStorage errors
        this.storage = {
            getItem: () => null,
            setItem: () => {},
            removeItem: () => {},
            clear: () => {},
            key: () => null,
            length: 0
        };
    }

    bindEvents() {
        // Tab switching
        $('button[data-bs-toggle="tab"]').on('shown.bs.tab', (e) => {
            const target = $(e.target).attr('data-bs-target');
            this.currentTab = target.replace('#', '');
            
            // Update URL with current tab
            const url = new URL(window.location);
            url.searchParams.set('tab', this.currentTab);
            window.history.replaceState({}, '', url);
            
            // Handle tab-specific data loading
            this.handleTabSwitch(this.currentTab);
        });

        // Search functionality
        this.initializeSearch();
        
        // Filter functionality
        this.initializeFilters();
        
        // User selection
        this.initializeUserSelection();
        
        // Permission buttons
        this.initializePermissionButtons();
        
        // Modal events
        this.initializeModalEvents();
    }
    
    initializeModalEvents() {
        // تحميل الصلاحيات عند فتح مودال إنشاء الدور
        $('#createRoleModal').on('show.bs.modal', (e) => {
            // التحقق من صلاحيات المستخدم
            if (!window.userCanManageRoles) {
                e.preventDefault();
                showAlert('ليس لديك صلاحية لإنشاء الأدوار. يتطلب صلاحيات المدير.', 'warning');
                return false;
            }
        });
        
        $('#createRoleModal').on('shown.bs.modal', () => {
            this.renderPermissionsCheckboxes('#createRoleModal .permissions-container');
        });
        
        // تنظيف المودال عند إغلاقه
        $('#createRoleModal').on('hidden.bs.modal', () => {
            $('#createRoleForm')[0].reset();
            $('#createRoleModal .permissions-container').html(`
                <div class="text-center py-4">
                    <div class="spinner-border spinner-border-sm text-primary me-2"></div>
                    جاري تحميل الصلاحيات...
                </div>
            `);
        });
        
        // معالجة إرسال نموذج إنشاء الدور
        $('#createRoleForm').on('submit', (e) => {
            e.preventDefault();
            this.createRole();
        });
        
        // معالجة إرسال نموذج تعديل الدور
        $('#editRoleForm').on('submit', (e) => {
            e.preventDefault();
            this.updateRole();
        });
        
        // معالجة إرسال نموذج تعديل صلاحيات المستخدم
        $('#editUserPermissionsForm').on('submit', (e) => {
            e.preventDefault();
            this.saveUserPermissions();
        });
        
        // معالجة أزرار تعديل وحذف الأدوار
        $(document).on('click', '.edit-role-btn', (e) => {
            const roleId = $(e.currentTarget).data('role-id');
            if (!window.userCanManageRoles) {
                showAlert('ليس لديك صلاحية لتعديل الأدوار. يتطلب صلاحيات المدير.', 'warning');
                return;
            }
            this.editRole(roleId);
        });
        
        $(document).on('click', '.delete-role-btn', (e) => {
            const roleId = $(e.currentTarget).data('role-id');
            const roleName = $(e.currentTarget).data('role-name');
            if (!window.userCanManageRoles) {
                showAlert('ليس لديك صلاحية لحذف الأدوار. يتطلب صلاحيات المدير.', 'warning');
                return;
            }
            this.deleteRole(roleId, roleName);
        });
    }

    initializeTooltips() {
        // Initialize Bootstrap tooltips with safe configuration for Arabic text
        try {
            const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
            tooltipTriggerList.forEach(function (tooltipTriggerEl) {
                try {
                    // تنظيف النص العربي من data attributes قبل تهيئة tooltip
                    const title = tooltipTriggerEl.getAttribute('title') || tooltipTriggerEl.getAttribute('data-bs-original-title');
                    
                    // إنشاء tooltip مع إعدادات آمنة للنصوص العربية
                    new bootstrap.Tooltip(tooltipTriggerEl, {
                        sanitize: false,
                        html: false,
                        trigger: 'hover focus',
                        placement: 'top',
                        title: title, // تمرير النص مباشرة
                        customClass: 'arabic-tooltip', // فئة CSS مخصصة للنصوص العربية
                        // منع Bootstrap من محاولة parse النصوص العربية كـ JSON
                        template: '<div class="tooltip arabic-tooltip" role="tooltip"><div class="tooltip-arrow"></div><div class="tooltip-inner"></div></div>'
                    });
                } catch (tooltipError) {
                    // تسجيل صامت للأخطاء - لا نريد إزعاج المستخدم
                    // console.warn('تحذير في تهيئة tooltip:', tooltipError.message);
                }
            });
        } catch (error) {
            // تسجيل صامت للأخطاء العامة
            // console.warn('تحذير في تهيئة tooltips:', error.message);
        }
    }

    loadInitialData() {
        // Load data for current tab
        const urlParams = new URLSearchParams(window.location.search);
        const currentTab = urlParams.get('tab') || 'overview';
        
        // Load data based on current tab
        switch(currentTab) {
            case 'roles':
                // Data already loaded on page load, no need to reload
                break;
            case 'users':
                // Data already loaded on page load, no need to reload
                break;
            case 'monitoring':
                // Data already loaded on page load, no need to reload
                break;
            case 'matrix':
                this.loadPermissionsMatrix();
                break;
        }
    }

    handleTabSwitch(tabName) {
        // Simple tab switching - no complex data loading
        // All data is already loaded on page load
        
        // Only handle special cases that need dynamic loading
        if (tabName === 'matrix') {
            this.loadPermissionsMatrix();
        }
    }

    initializeSearch() {
        // Debounced search for roles
        let rolesSearchTimeout;
        $('#roleSearch').on('input', function() {
            const searchTerm = $(this).val();
            clearTimeout(rolesSearchTimeout);
            rolesSearchTimeout = setTimeout(() => {
                if (searchTerm.length > 2 || searchTerm.length === 0) {
                    window.location.href = updateUrlParameter(window.location.href, 'search', searchTerm);
                }
            }, 500);
        });

        // Debounced search for users
        let usersSearchTimeout;
        $('#userSearch').on('input', function() {
            const searchTerm = $(this).val();
            clearTimeout(usersSearchTimeout);
            usersSearchTimeout = setTimeout(() => {
                if (searchTerm.length > 2 || searchTerm.length === 0) {
                    window.location.href = updateUrlParameter(window.location.href, 'search', searchTerm);
                }
            }, 500);
        });

        // Matrix search
        $('#matrixSearch').on('input', (e) => {
            this.filterMatrixPermissions($(e.target).val());
        });
    }

    initializeFilters() {
        // Role filter for users
        $('#userRoleFilter').on('change', function() {
            const roleId = $(this).val();
            window.location.href = updateUrlParameter(window.location.href, 'role', roleId);
        });

        // Permissions filter for users
        $('#userPermissionsFilter').on('change', function() {
            const hasPermissions = $(this).val();
            window.location.href = updateUrlParameter(window.location.href, 'has_permissions', hasPermissions);
        });

        // Role status filter
        $('#roleStatusFilter').on('change', function() {
            const status = $(this).val();
            window.location.href = updateUrlParameter(window.location.href, 'status', status);
        });

        // Days filter for monitoring
        $(document).on('change', 'input[name="daysFilter"]', function() {
            const days = $(this).val();
            window.location.href = updateUrlParameter(window.location.href, 'days', days);
        });

        // Category filter for matrix
        $('#categoryFilter').on('change', (e) => {
            const selectedCategory = $(e.target).val();
            if (selectedCategory) {
                $(`button[data-bs-target="#matrix-${selectedCategory}"]`).tab('show');
            }
        });
    }

    initializeUserSelection() {
        // Select all users checkbox
        $('#selectAllUsers').on('change', function() {
            $('.user-checkbox').prop('checked', this.checked);
        });

        // Individual user checkboxes
        $(document).on('change', '.user-checkbox', function() {
            const totalCheckboxes = $('.user-checkbox').length;
            const checkedCheckboxes = $('.user-checkbox:checked').length;
            
            $('#selectAllUsers').prop('indeterminate', checkedCheckboxes > 0 && checkedCheckboxes < totalCheckboxes);
            $('#selectAllUsers').prop('checked', checkedCheckboxes === totalCheckboxes);
        });
    }

    initializePermissionButtons() {
        // Permission button clicks
        $(document).on('click', '.permission-btn', (e) => {
            const button = $(e.currentTarget);
            const userId = button.data('user-id');
            const userName = button.data('user-name');
            const userRole = button.data('user-role');
            const customPermissionsCount = button.data('custom-permissions-count');
            
            this.showUserPermissionsModal(userId, userName, userRole, customPermissionsCount);
        });

        // View permissions button
        $(document).on('click', '.view-permissions-btn', (e) => {
            const button = $(e.currentTarget);
            const userId = button.data('user-id');
            const userName = button.data('user-name');
            
            this.showUserPermissionsModal(userId, userName);
        });

        // Assign role button
        $(document).on('click', '.assign-role-btn', (e) => {
            const button = $(e.currentTarget);
            const userId = button.data('user-id');
            const userName = button.data('user-name');
            const currentRole = button.data('current-role');
            
            this.showAssignRoleModal(userId, userName, currentRole);
        });
        
        // Handle assign role form submission
        $(document).on('submit', '#assignRoleForm', (e) => {
            e.preventDefault();
            this.assignRole();
        });
        
        // Handle assign role button click (backup)
        $(document).on('click', '#assignRoleBtn', (e) => {
            e.preventDefault();
            this.assignRole();
        });
    }

    // Matrix functionality
    async loadPermissionsMatrix() {
        $('#matrixContainer').html(`
            <div class="text-center py-5">
                <div class="loading-spinner"></div>
                <p class="mt-3">جاري تحميل مصفوفة الصلاحيات المبسطة...</p>
            </div>
        `);

        try {
            const response = await fetch('/users/permissions/matrix/');
            const data = await response.json();

            if (data.success) {
                this.matrixData = data.matrix_data;
                this.renderPermissionsMatrix(data.matrix_data);
            } else {
                this.showMatrixError('خطأ في تحميل المصفوفة: ' + data.message);
            }
        } catch (error) {
            console.error('Error loading permissions matrix:', error);
            this.showMatrixError('فشل في تحميل مصفوفة الصلاحيات');
        }
    }

    renderPermissionsMatrix(matrixData) {
        // Update statistics
        if (matrixData.statistics) {
            $('#customPermCount').text(matrixData.statistics.total_custom_permissions);
            $('#djangoPermCount').text(matrixData.statistics.total_django_permissions);
            $('#reductionPercent').text(matrixData.statistics.reduction_percentage + '%');
            $('#categoriesCount').text(matrixData.statistics.categories_count);
        }

        let html = '<div class="simplified-permissions-matrix">';
        
        // Add controls
        html += this.renderMatrixControls();
        
        // Group permissions by category
        const permissionsByCategory = this.groupPermissionsByCategory(matrixData.permissions);
        
        // Create tabbed interface
        html += this.renderMatrixTabs(permissionsByCategory);
        html += this.renderMatrixTabContent(permissionsByCategory, matrixData.roles);
        
        html += '</div>';
        
        $('#matrixContainer').html(html);
        this.initializeMatrixFilters();
    }

    renderMatrixControls() {
        return `
            <div class="matrix-controls mb-4">
                <div class="row">
                    <div class="col-md-4">
                        <input type="text" class="form-control" id="matrixSearch" placeholder="البحث في الصلاحيات المخصصة...">
                    </div>
                    <div class="col-md-3">
                        <select class="form-select" id="categoryFilter">
                            <option value="">جميع الفئات</option>
                            <option value="customers_suppliers">العملاء والموردين</option>
                            <option value="inventory">المنتجات والمخزون</option>
                            <option value="financial">المالية والمحاسبة</option>
                            <option value="reports">التقارير</option>
                            <option value="system_admin">إدارة النظام</option>
                        </select>
                    </div>
                    <div class="col-md-5 text-end">
                        <div class="btn-group">
                            <button class="btn btn-outline-success btn-sm" onclick="expandAllCategories()">
                                <i class="fas fa-expand-alt"></i> توسيع الكل
                            </button>
                            <button class="btn btn-outline-secondary btn-sm" onclick="collapseAllCategories()">
                                <i class="fas fa-compress-alt"></i> طي الكل
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    groupPermissionsByCategory(permissions) {
        const permissionsByCategory = {};
        
        permissions.forEach(perm => {
            if (!permissionsByCategory[perm.category_key]) {
                permissionsByCategory[perm.category_key] = {
                    name: perm.category_name,
                    icon: perm.category_icon,
                    color: perm.category_color,
                    permissions: []
                };
            }
            permissionsByCategory[perm.category_key].permissions.push(perm);
        });
        
        return permissionsByCategory;
    }

    renderMatrixTabs(permissionsByCategory) {
        let html = '<ul class="nav nav-tabs matrix-tabs" id="matrixCategoryTabs">';
        let isFirst = true;
        
        Object.keys(permissionsByCategory).forEach(categoryKey => {
            const category = permissionsByCategory[categoryKey];
            html += `
                <li class="nav-item">
                    <button class="nav-link ${isFirst ? 'active' : ''}" data-bs-toggle="tab" 
                            data-bs-target="#matrix-${categoryKey}" type="button">
                        <i class="${category.icon} text-${category.color}"></i>
                        ${category.name}
                        <span class="badge bg-${category.color} ms-1">${category.permissions.length}</span>
                    </button>
                </li>
            `;
            isFirst = false;
        });
        
        html += '</ul>';
        return html;
    }

    renderMatrixTabContent(permissionsByCategory, roles) {
        let html = '<div class="tab-content matrix-tab-content">';
        let isFirst = true;
        
        Object.keys(permissionsByCategory).forEach(categoryKey => {
            const category = permissionsByCategory[categoryKey];
            html += `
                <div class="tab-pane fade ${isFirst ? 'show active' : ''}" id="matrix-${categoryKey}">
                    <div class="category-matrix mt-3">
                        <div class="table-responsive">
                            <table class="table table-sm matrix-table">
                                <thead class="table-${category.color}">
                                    <tr>
                                        <th class="permission-name-col">الصلاحية</th>
            `;
            
            // Add role headers
            roles.forEach(role => {
                html += `<th class="role-col text-center" title="${role.name}">
                    ${role.name}${role.is_system ? ' 🔒' : ''}
                </th>`;
            });
            
            html += '</tr></thead><tbody>';
            
            // Add permissions for this category
            category.permissions.forEach(perm => {
                html += `
                    <tr class="permission-row" data-permission-id="${perm.permission_id}" 
                        data-category="${categoryKey}" data-search-text="${perm.permission_name.toLowerCase()} ${perm.permission_codename.toLowerCase()}">
                        <td class="permission-name-col">
                            <div class="permission-info">
                                <strong>${perm.permission_name}</strong>
                                <br><small class="text-muted">${perm.permission_codename}</small>
                            </div>
                        </td>
                `;
                
                // Add role indicators
                roles.forEach(role => {
                    const hasPermission = perm.roles[role.id] && perm.roles[role.id].has_permission;
                    html += `
                        <td class="text-center role-col">
                            <span class="matrix-indicator ${hasPermission ? 'has-permission' : 'no-permission'}" 
                                  title="${hasPermission ? 'لديه الصلاحية' : 'ليس لديه الصلاحية'}"
                                  data-role-id="${role.id}" data-permission-id="${perm.permission_id}">
                                ${hasPermission ? '✓' : '✗'}
                            </span>
                        </td>
                    `;
                });
                
                html += '</tr>';
            });
            
            html += '</tbody></table></div></div></div>';
            isFirst = false;
        });
        
        html += '</div></div>';
        
        $('#matrixContainer').html(html);
        this.initializeMatrixFilters();
    }

    initializeMatrixFilters() {
        // Search functionality
        $('#matrixSearch').on('input', function() {
            const searchTerm = $(this).val().toLowerCase();
            $('.permission-row').each(function() {
                const searchText = $(this).data('search-text');
                if (searchText.includes(searchTerm)) {
                    $(this).show();
                } else {
                    $(this).hide();
                }
            });
        });
        
        // Category filter
        $('#categoryFilter').on('change', function() {
            const selectedCategory = $(this).val();
            if (selectedCategory) {
                $(`button[data-bs-target="#matrix-${selectedCategory}"]`).tab('show');
            }
        });
    }

    filterMatrixPermissions(searchTerm) {
        const term = searchTerm.toLowerCase();
        $('.permission-row').each(function() {
            const searchText = $(this).data('search-text') || '';
            if (searchText.includes(term)) {
                $(this).show();
            } else {
                $(this).hide();
            }
        });
    }

    showMatrixError(message) {
        $('#matrixContainer').html(`
            <div class="alert alert-danger">
                <i class="fas fa-exclamation-triangle me-2"></i>
                ${message}
            </div>
        `);
    }

    // Permissions loading and rendering
    async loadAvailablePermissions() {
        if (this.availablePermissions) {
            return this.availablePermissions;
        }

        try {
            const response = await fetch('/users/permissions/available-permissions/');
            
            // التحقق من حالة الاستجابة
            if (response.status === 403) {
                console.error('Access denied: Admin permissions required');
                this.showPermissionError('ليس لديك صلاحية للوصول لهذه البيانات. يتطلب صلاحيات المدير.');
                return null;
            }
            
            if (response.status === 302 || response.redirected) {
                console.error('User not authenticated or session expired');
                this.showPermissionError('انتهت جلسة العمل. يرجى تسجيل الدخول مرة أخرى.');
                return null;
            }
            
            if (!response.ok) {
                console.error('HTTP error:', response.status);
                this.showPermissionError('حدث خطأ في الخادم. يرجى المحاولة مرة أخرى.');
                return null;
            }
            
            const data = await response.json();
            
            if (data.success) {
                this.availablePermissions = data.permissions;
                this.permissionsInfo = data.stats;
                return this.availablePermissions;
            } else {
                console.error('Failed to load permissions:', data.message);
                this.showPermissionError(data.message || 'فشل في تحميل الصلاحيات');
                return null;
            }
        } catch (error) {
            console.error('Error loading permissions:', error);
            this.showPermissionError('حدث خطأ في الاتصال. يرجى التحقق من الاتصال بالإنترنت.');
            return null;
        }
    }
    
    showPermissionError(message) {
        // إظهار رسالة خطأ واضحة للمستخدم
        console.error('Permission Error:', message);
        
        // محاولة استخدام alert بسيط
        if (typeof $ !== 'undefined') {
            const alertHtml = `
                <div class="alert alert-danger alert-dismissible fade show" role="alert">
                    <i class="fas fa-exclamation-triangle me-2"></i>
                    ${message}
                    <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                </div>
            `;
            
            // البحث عن مكان لإدراج التنبيه
            let container = $('.permissions-content').first();
            if (container.length === 0) {
                container = $('.container-fluid').first();
            }
            if (container.length === 0) {
                container = $('body');
            }
            
            // إزالة التنبيهات السابقة
            container.find('.alert').remove();
            
            // إضافة التنبيه الجديد
            container.prepend(alertHtml);
        } else {
            // fallback إلى alert عادي
            alert(message);
        }
    }

    async renderPermissionsCheckboxes(container, selectedPermissions = []) {
        const $container = $(container);
        
        // إظهار مؤشر التحميل
        $container.html(`
            <div class="text-center py-4">
                <div class="spinner-border spinner-border-sm text-primary me-2"></div>
                جاري تحميل الصلاحيات المخصصة...
            </div>
        `);
        
        // تحميل الصلاحيات إذا لم تكن محملة
        const permissions = await this.loadAvailablePermissions();
        
        // التحقق من نجاح التحميل
        if (!permissions) {
            $container.html(`
                <div class="alert alert-warning">
                    <i class="fas fa-exclamation-triangle me-2"></i>
                    <strong>تعذر تحميل الصلاحيات</strong><br>
                    <small>قد تحتاج لصلاحيات إضافية أو إعادة تسجيل الدخول.</small>
                    <div class="mt-2">
                        <button type="button" class="btn btn-sm btn-outline-primary" onclick="window.location.reload()">
                            <i class="fas fa-refresh me-1"></i>إعادة تحميل الصفحة
                        </button>
                    </div>
                </div>
            `);
            return;
        }
        
        // عرض المحتوى
        this._renderPermissionsContent($container, selectedPermissions);
    }

    _renderPermissionsContent($container, selectedPermissions) {
        // التحقق من وجود الصلاحيات
        if (!this.availablePermissions || Object.keys(this.availablePermissions).length === 0) {
            $container.html(`
                <div class="alert alert-warning">
                    <i class="fas fa-exclamation-triangle me-2"></i>
                    <strong>لا توجد صلاحيات متاحة</strong><br>
                    <small>قد تحتاج لصلاحيات إضافية للوصول لهذه البيانات.</small>
                </div>
            `);
            return;
        }
        
        // Show info about custom permissions
        let html = '';
        if (this.permissionsInfo) {
            html += `
                <div class="alert alert-info mb-3">
                    <i class="fas fa-info-circle me-2"></i>
                    ${this.permissionsInfo.message}
                </div>
            `;
        }
        
        // Render categorized permissions
        Object.keys(this.availablePermissions).forEach(categoryKey => {
            const categoryData = this.availablePermissions[categoryKey];
            const categoryPermissions = categoryData.permissions || [];
            
            if (categoryPermissions.length === 0) return;
            
            html += `
                <div class="permission-group">
                    <div class="permission-group-header">
                        <div class="form-check">
                            <input type="checkbox" class="form-check-input category-checkbox" 
                                   data-category="${categoryKey}" id="category_${categoryKey}"
                                   onchange="toggleCategoryPermissions('${categoryKey}')">
                            <label class="form-check-label fw-bold" for="category_${categoryKey}">
                                <i class="${categoryData.icon} me-2"></i>
                                ${categoryData.name} (${categoryPermissions.length} صلاحية)
                            </label>
                        </div>
                        <small class="text-muted d-block mt-1">${categoryData.description}</small>
                    </div>
                    <div class="permission-list">
                        <div class="row">
            `;
            
            categoryPermissions.forEach(perm => {
                const isChecked = selectedPermissions.includes(perm.id);
                html += `
                    <div class="col-md-6 mb-2">
                        <div class="form-check">
                            <input class="form-check-input permission-checkbox" 
                                   type="checkbox" 
                                   value="${perm.id}" 
                                   id="perm_${perm.id}"
                                   data-category="${categoryKey}"
                                   ${isChecked ? 'checked' : ''}>
                            <label class="form-check-label" for="perm_${perm.id}">
                                <div class="permission-item">
                                    <div class="permission-name">${perm.name}</div>
                                    <div class="permission-codename text-muted">${perm.codename}</div>
                                </div>
                            </label>
                        </div>
                    </div>
                `;
            });
            
            html += `
                        </div>
                    </div>
                </div>
            `;
        });

        // التحقق من وجود الـ container
        if ($container.length === 0) {
            console.error('❌ Container not found:', container);
            return;
        }
        
        $container.html(html);
        
        // تحديث حالة checkboxes الفئات
        this.updateCategoryCheckboxes();
    }
    
    updateCategoryCheckboxes() {
        $('.category-checkbox').each(function() {
            const categoryKey = $(this).data('category');
            const categoryPermissions = $(`.permission-checkbox[data-category="${categoryKey}"]`);
            const checkedPermissions = categoryPermissions.filter(':checked');
            
            if (checkedPermissions.length === 0) {
                $(this).prop('checked', false).prop('indeterminate', false);
            } else if (checkedPermissions.length === categoryPermissions.length) {
                $(this).prop('checked', true).prop('indeterminate', false);
            } else {
                $(this).prop('checked', false).prop('indeterminate', true);
            }
        });
    }

    // Role Management Functions - تحسين إدارة الأدوار
    async createRole() {
        const $btn = $('#createRoleBtn');
        const $form = $('#createRoleForm');
        
        // التحقق من صحة النموذج
        if (!$form[0].checkValidity()) {
            $form[0].reportValidity();
            return;
        }
        
        // التحقق من تحميل الصلاحيات
        if (!this.availablePermissions) {
            showAlert('لم يتم تحميل الصلاحيات بعد. يرجى الانتظار أو إعادة تحميل الصفحة.', 'warning');
            return;
        }
        
        // تعطيل الزر وإظهار التحميل
        this.setButtonLoading($btn, true);
        
        const formData = {
            name: $('#roleName').val().trim(),
            display_name: $('#roleDisplayName').val().trim(),
            description: $('#roleDescription').val().trim(),
            is_active: $('#roleActive').is(':checked'),
            permissions: $('.permission-checkbox:checked').map(function() {
                return parseInt($(this).val());
            }).get()
        };

        try {
            const response = await fetch('/users/permissions/roles/create/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.csrfToken
                },
                body: JSON.stringify(formData)
            });

            // التحقق من حالة الاستجابة
            if (response.status === 403) {
                showAlert('ليس لديك صلاحية لإنشاء الأدوار. يتطلب صلاحيات المدير.', 'danger');
                return;
            }
            
            if (response.status === 302 || response.redirected) {
                showAlert('انتهت جلسة العمل. يرجى تسجيل الدخول مرة أخرى.', 'warning');
                setTimeout(() => window.location.reload(), 2000);
                return;
            }

            const data = await response.json();
            
            if (data.success) {
                showAlert(data.message, 'success');
                $('#createRoleModal').modal('hide');
                
                // إضافة الدور الجديد للقائمة بدلاً من إعادة تحميل الصفحة
                this.addRoleToList(data.role);
            } else {
                showAlert(data.message, 'danger');
            }
        } catch (error) {
            showAlert('حدث خطأ في إنشاء الدور. يرجى المحاولة مرة أخرى.', 'danger');
            console.error('Error creating role:', error);
        } finally {
            this.setButtonLoading($btn, false);
        }
    }
    
    addRoleToList(role) {
        const roleHtml = `
            <div class="role-card" data-role-id="${role.id}">
                <div class="role-header">
                    <div>
                        <h6 class="role-title">${role.display_name}</h6>
                        <span class="role-name">${role.name}</span>
                        <span class="badge bg-success ms-2">جديد</span>
                    </div>
                    <div class="btn-group btn-group-sm">
                        <button type="button" class="btn btn-outline-primary edit-role-btn" 
                                data-role-id="${role.id}">
                            <i class="fas fa-edit"></i>
                        </button>
                        <button type="button" class="btn btn-outline-danger delete-role-btn" 
                                data-role-id="${role.id}" data-role-name="${role.display_name}">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </div>
                
                <div class="role-stats">
                    <div class="role-stat">
                        <i class="fas fa-users text-primary"></i>
                        <span>0 مستخدم</span>
                    </div>
                    <div class="role-stat">
                        <i class="fas fa-key text-success"></i>
                        <span>${role.permissions_count || 0} صلاحية</span>
                    </div>
                    <div class="role-stat">
                        <i class="fas fa-calendar text-info"></i>
                        <span>الآن</span>
                    </div>
                </div>
                
                ${role.description ? `<p class="text-muted mb-0">${role.description}</p>` : ''}
            </div>
        `;
        
        // إضافة الدور في بداية القائمة
        $('#rolesList').prepend(roleHtml);
        
        // إزالة رسالة "لا توجد أدوار" إن وجدت
        $('#rolesList .text-center.py-5').remove();
        
        // تحديث الإحصائيات
        this.updateStatsAfterRoleCreation();
    }
    
    updateStatsAfterRoleCreation() {
        // تحديث عدد الأدوار في الإحصائيات
        const $totalRolesCard = $('.stat-card.success .stat-number');
        const currentCount = parseInt($totalRolesCard.text()) || 0;
        $totalRolesCard.text(currentCount + 1);
    }
    
    setButtonLoading($button, isLoading) {
        if (isLoading) {
            $button.prop('disabled', true);
            $button.find('.btn-text').addClass('d-none');
            $button.find('.btn-loading').removeClass('d-none');
        } else {
            $button.prop('disabled', false);
            $button.find('.btn-text').removeClass('d-none');
            $button.find('.btn-loading').addClass('d-none');
        }
    }

    async editRole(roleId) {
        try {
            // إظهار مؤشر التحميل
            $('#editRoleModal .modal-body').html(`
                <div class="text-center py-4">
                    <div class="spinner-border text-primary me-2"></div>
                    جاري تحميل بيانات الدور...
                </div>
            `);
            $('#editRoleModal').modal('show');
            
            const response = await fetch(`/users/permissions/roles/${roleId}/edit/`);
            const data = await response.json();
            
            if (data.success) {
                const role = data.role;
                
                // استعادة محتوى المودال
                $('#editRoleModal .modal-body').html(`
                    <div class="row">
                        <div class="col-md-6">
                            <div class="mb-3">
                                <label for="editRoleName" class="form-label">اسم الدور <span class="text-danger">*</span></label>
                                <input type="text" class="form-control" id="editRoleName" name="name" required readonly>
                                <div class="form-text">لا يمكن تغيير اسم الدور</div>
                            </div>
                        </div>
                        <div class="col-md-6">
                            <div class="mb-3">
                                <label for="editRoleDisplayName" class="form-label">الاسم المعروض <span class="text-danger">*</span></label>
                                <input type="text" class="form-control" id="editRoleDisplayName" name="display_name" required>
                            </div>
                        </div>
                    </div>
                    
                    <div class="mb-3">
                        <label for="editRoleDescription" class="form-label">الوصف</label>
                        <textarea class="form-control" id="editRoleDescription" name="description" rows="3"></textarea>
                    </div>
                    
                    <div class="mb-3">
                        <div class="form-check">
                            <input class="form-check-input" type="checkbox" id="editRoleIsActive" name="is_active">
                            <label class="form-check-label" for="editRoleIsActive">
                                دور نشط
                            </label>
                        </div>
                    </div>
                    
                    <hr>
                    
                    <div class="mb-3">
                        <div class="d-flex justify-content-between align-items-center mb-3">
                            <h6 class="mb-0">الصلاحيات</h6>
                            <div class="btn-group btn-group-sm">
                                <button type="button" class="btn btn-outline-primary" onclick="selectAllPermissions()">
                                    <i class="fas fa-check-double me-1"></i>تحديد الكل
                                </button>
                                <button type="button" class="btn btn-outline-secondary" onclick="clearAllPermissions()">
                                    <i class="fas fa-times me-1"></i>إلغاء الكل
                                </button>
                            </div>
                        </div>
                        <div class="permissions-container" style="max-height: 350px; overflow-y: auto; border: 1px solid var(--bs-border-color); border-radius: 8px;">
                            <div class="text-center py-4">
                                <div class="spinner-border spinner-border-sm text-primary me-2"></div>
                                جاري تحميل الصلاحيات...
                            </div>
                        </div>
                        <div class="mt-2">
                            <small class="text-muted">
                                <i class="fas fa-info-circle me-1"></i>
                                يمكنك النقر على اسم التطبيق لتحديد/إلغاء تحديد جميع صلاحياته
                            </small>
                        </div>
                    </div>
                `);
                
                // ملء البيانات
                $('#editRoleId').val(role.id);
                $('#editRoleName').val(role.name);
                $('#editRoleDisplayName').val(role.display_name);
                $('#editRoleDescription').val(role.description);
                $('#editRoleIsActive').prop('checked', role.is_active);
                
                // تحميل الصلاحيات
                this.renderPermissionsCheckboxes('#editRoleModal .permissions-container', role.permissions);
            } else {
                showAlert(data.message, 'danger');
                $('#editRoleModal').modal('hide');
            }
        } catch (error) {
            showAlert('حدث خطأ في تحميل بيانات الدور', 'danger');
            console.error('Error loading role:', error);
            $('#editRoleModal').modal('hide');
        }
    }

    async updateRole() {
        const $btn = $('#editRoleBtn');
        const $form = $('#editRoleForm');
        
        // التحقق من صحة النموذج
        if (!$form[0].checkValidity()) {
            $form[0].reportValidity();
            return;
        }
        
        // تعطيل الزر وإظهار التحميل
        this.setButtonLoading($btn, true);
        
        const roleId = $('#editRoleId').val();
        const formData = {
            display_name: $('#editRoleDisplayName').val().trim(),
            description: $('#editRoleDescription').val().trim(),
            is_active: $('#editRoleIsActive').is(':checked'),
            permissions: $('#editRoleModal .permission-checkbox:checked').map(function() {
                return parseInt($(this).val());
            }).get()
        };

        try {
            const response = await fetch(`/users/permissions/roles/${roleId}/edit/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.csrfToken
                },
                body: JSON.stringify(formData)
            });

            const data = await response.json();
            
            if (data.success) {
                showAlert(data.message, 'success');
                $('#editRoleModal').modal('hide');
                
                // تحديث الدور في القائمة
                this.updateRoleInList(roleId, formData);
            } else {
                showAlert(data.message, 'danger');
            }
        } catch (error) {
            showAlert('حدث خطأ في تحديث الدور', 'danger');
            console.error('Error updating role:', error);
        } finally {
            this.setButtonLoading($btn, false);
        }
    }
    
    updateRoleInList(roleId, updatedData) {
        const $roleCard = $(`.role-card[data-role-id="${roleId}"]`);
        if ($roleCard.length) {
            // تحديث الاسم المعروض
            $roleCard.find('.role-title').text(updatedData.display_name);
            
            // تحديث الوصف
            if (updatedData.description) {
                let $description = $roleCard.find('p.text-muted');
                if ($description.length) {
                    $description.text(updatedData.description);
                } else {
                    $roleCard.append(`<p class="text-muted mb-0">${updatedData.description}</p>`);
                }
            }
            
            // تحديث حالة النشاط
            const $inactiveBadge = $roleCard.find('.badge:contains("غير نشط")');
            if (!updatedData.is_active && !$inactiveBadge.length) {
                $roleCard.find('.role-name').after('<span class="badge bg-secondary ms-2">غير نشط</span>');
            } else if (updatedData.is_active && $inactiveBadge.length) {
                $inactiveBadge.remove();
            }
            
            // إضافة مؤشر التحديث
            $roleCard.find('.badge.bg-warning').remove();
            $roleCard.find('.role-name').after('<span class="badge bg-warning ms-2">محدث</span>');
            
            // إزالة مؤشر التحديث بعد 3 ثواني
            setTimeout(() => {
                $roleCard.find('.badge.bg-warning').fadeOut(() => {
                    $roleCard.find('.badge.bg-warning').remove();
                });
            }, 3000);
        }
    }

    deleteRole(roleId, roleName) {
        $('#deleteConfirmMessage').text(`سيتم حذف الدور "${roleName}" نهائياً`);
        $('#confirmDeleteBtn').off('click').on('click', () => this.confirmDeleteRole(roleId));
        $('#deleteConfirmModal').modal('show');
    }

    async confirmDeleteRole(roleId) {
        try {
            const response = await fetch(`/users/permissions/roles/${roleId}/delete/`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': this.csrfToken
                }
            });

            const data = await response.json();
            
            if (data.success) {
                showAlert(data.message, 'success');
                $('#deleteConfirmModal').modal('hide');
                setTimeout(() => window.location.reload(), 1000);
            } else {
                showAlert(data.message, 'danger');
            }
        } catch (error) {
            showAlert('حدث خطأ في حذف الدور', 'danger');
            console.error('Error deleting role:', error);
        }
    }

    // Show user permissions modal
    showUserPermissionsModal(userId, userName, userRole = null, customPermissionsCount = 0) {
        // Set modal title
        $('#userPermissionsModal .modal-title').text(`صلاحيات المستخدم: ${userName}`);
        
        // Call the existing viewUserPermissions function
        this.viewUserPermissions(userId);
    }

    // Show assign role modal
    showAssignRoleModal(userId, userName, currentRole = '') {
        // Set modal title and user info
        $('#assignRoleModal .modal-title').text(`تعيين دور للمستخدم: ${userName}`);
        $('#assignRoleModal #assignUserId').val(userId);
        $('#assignRoleModal #assignUserName').text(userName);
        
        // Set current role in dropdown
        if (currentRole) {
            $('#assignRoleModal #assignRoleSelect').val(currentRole);
        } else {
            $('#assignRoleModal #assignRoleSelect').val('');
        }
        
        // Show modal
        $('#assignRoleModal').modal('show');
    }

    // User Management Functions
    async viewUserPermissions(userId) {
        try {
            
            const response = await fetch(`/users/permissions/users/${userId}/permissions/`);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            
            if (data.success) {
                this.renderUserPermissions(data);
                $('#userPermissionsModal').modal('show');
            } else {
                console.error('Failed to load user permissions:', data.message);
                this.showPermissionError(data.message || 'فشل في تحميل صلاحيات المستخدم');
            }
        } catch (error) {
            console.error('Error loading user permissions:', error);
            this.showPermissionError('حدث خطأ في تحميل صلاحيات المستخدم');
        }
    }

    renderUserPermissions(data) {
        const user = data.user || {};
        const permissionsOverview = data.permissions_overview || {};
        const categories = data.categories || {};

        // التحقق من وجود البيانات الأساسية
        if (!user.id) {
            console.error('User data is missing or invalid:', data);
            $('#userPermissionsModal .modal-body').html(`
                <div class="alert alert-danger">
                    <i class="fas fa-exclamation-triangle me-2"></i>
                    خطأ في تحميل بيانات المستخدم
                </div>
            `);
            return;
        }

        let html = `
            <div class="row mb-4">
                <div class="col-md-6">
                    <h6>معلومات المستخدم</h6>
                    <div class="card">
                        <div class="card-body">
                            <h6 class="card-title">${user.full_name || user.username || 'غير محدد'}</h6>
                            <p class="card-text">
                                <strong>اسم المستخدم:</strong> ${user.username || 'غير محدد'}<br>
                                <strong>الدور:</strong> ${user.role_name || 'بدون دور'}<br>
                                <strong>مدير عام:</strong> ${user.is_superuser ? 'نعم' : 'لا'}<br>
                                <strong>نشط:</strong> ${user.is_active ? 'نعم' : 'لا'}
                            </p>
                        </div>
                    </div>
                </div>
                <div class="col-md-6">
                    <h6>ملخص الصلاحيات المخصصة</h6>
                    <div class="row">
                        <div class="col-6">
                            <div class="text-center p-3 bg-primary text-white rounded">
                                <h4>${permissionsOverview.total_custom_permissions}</h4>
                                <small>إجمالي الصلاحيات المخصصة</small>
                            </div>
                        </div>
                        <div class="col-6">
                            <div class="text-center p-3 bg-info text-white rounded">
                                <h4>${permissionsOverview.role_permissions_count}</h4>
                                <small>صلاحيات من الدور</small>
                            </div>
                        </div>
                    </div>
                    <div class="row mt-2">
                        <div class="col-12">
                            <div class="text-center p-2 bg-success text-white rounded">
                                <h6>${permissionsOverview.direct_permissions_count}</h6>
                                <small>صلاحيات مباشرة</small>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            
            <h6>الصلاحيات المخصصة حسب الفئة</h6>
            <div class="accordion" id="permissionsAccordion">
        `;

        Object.keys(categories).forEach((categoryKey, index) => {
            const category = categories[categoryKey];
            const totalPermissions = category.role_permissions.length + category.direct_permissions.length;
            
            if (totalPermissions === 0) return; // Skip empty categories
            
            html += `
                <div class="accordion-item">
                    <h2 class="accordion-header" id="heading${index}">
                        <button class="accordion-button ${index === 0 ? '' : 'collapsed'}" type="button" 
                                data-bs-toggle="collapse" data-bs-target="#collapse${index}">
                            <i class="${category.icon} me-2"></i>
                            ${category.name} 
                            <span class="badge bg-primary ms-2">${totalPermissions} صلاحية</span>
                        </button>
                    </h2>
                    <div id="collapse${index}" class="accordion-collapse collapse ${index === 0 ? 'show' : ''}" 
                         data-bs-parent="#permissionsAccordion">
                        <div class="accordion-body">
                            <div class="row">
                                <div class="col-md-6">
                                    <h6 class="text-success">
                                        <i class="fas fa-user-tag me-1"></i>
                                        صلاحيات من الدور (${category.role_permissions.length})
                                    </h6>
                                    ${category.role_permissions.length > 0 ? `
                                        <ul class="list-unstyled">
                                            ${category.role_permissions.map(perm => 
                                                `<li><i class="fas fa-check text-success me-2"></i>${perm.name}</li>`
                                            ).join('')}
                                        </ul>
                                    ` : '<p class="text-muted">لا توجد صلاحيات من الدور</p>'}
                                </div>
                                <div class="col-md-6">
                                    <h6 class="text-info">
                                        <i class="fas fa-user-plus me-1"></i>
                                        صلاحيات مباشرة (${category.direct_permissions.length})
                                    </h6>
                                    ${category.direct_permissions.length > 0 ? `
                                        <ul class="list-unstyled">
                                            ${category.direct_permissions.map(perm => 
                                                `<li><i class="fas fa-user-plus text-info me-2"></i>${perm.name}</li>`
                                            ).join('')}
                                        </ul>
                                    ` : '<p class="text-muted">لا توجد صلاحيات مباشرة</p>'}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        });

        html += '</div>';
        
        // Add edit permissions button if user has permission
        html += `
            <div class="mt-4 text-center">
                <button type="button" class="btn btn-primary" onclick="editUserPermissions(${user.id})">
                    <i class="fas fa-edit me-2"></i>تعديل الصلاحيات المخصصة
                </button>
            </div>
        `;
        
        $('#userPermissionsContent').html(html);
    }

    assignUserRole(userId) {
        // Get user info and populate modal
        const userRow = $(`.user-checkbox[value="${userId}"]`).closest('tr');
        const userName = userRow.find('td:nth-child(2) strong').text();
        const userEmail = userRow.find('td:nth-child(3)').text();
        const currentRole = userRow.find('td:nth-child(4) .badge').text();

        $('#assignUserId').val(userId);
        $('#assignUserInfo').html(`
            <strong>${userName}</strong><br>
            <small class="text-muted">${userEmail}</small><br>
            <span class="badge bg-info mt-1">الدور الحالي: ${currentRole}</span>
        `);

        $('#assignRoleModal').modal('show');
    }

    async assignRole() {
        const userId = $('#assignUserId').val();
        const roleId = $('#assignRoleSelect').val();

        if (!userId) {
            alert('خطأ: معرف المستخدم مفقود');
            return;
        }

        try {
            const response = await fetch(`/users/permissions/users/${userId}/assign-role/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.csrfToken
                },
                body: JSON.stringify({ role_id: roleId })
            });

            if (!response.ok) {
                alert(`خطأ HTTP: ${response.status} - ${response.statusText}`);
                return;
            }

            const data = await response.json();
            
            if (data.success) {
                // إظهار رسالة نجاح
                const alertHtml = `
                    <div class="alert alert-success alert-dismissible fade show" role="alert">
                        <i class="fas fa-check-circle me-2"></i>
                        ${data.message}
                        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                    </div>
                `;
                
                // البحث عن مكان لإدراج التنبيه
                let container = $('.permissions-content').first();
                if (container.length === 0) {
                    container = $('.container-fluid').first();
                }
                
                // إزالة التنبيهات السابقة وإضافة الجديد
                container.find('.alert').remove();
                container.prepend(alertHtml);
                
                $('#assignRoleModal').modal('hide');
                
                // تحديث الصفحة بعد ثانيتين
                setTimeout(() => {
                    window.location.reload();
                }, 2000);
                
            } else {
                alert('فشل في تعيين الدور: ' + data.message);
            }
        } catch (error) {
            alert('حدث خطأ في الشبكة: ' + error.message);
        }
    }

    async editUserPermissions(userId) {
        try {
            // Show loading state
            $('#editUserPermissionsModal .modal-body').html(`
                <div class="text-center py-4">
                    <div class="spinner-border text-primary me-2"></div>
                    جاري تحميل صلاحيات المستخدم...
                </div>
            `);
            $('#editUserPermissionsModal').modal('show');
            
            // Get user permissions for editing
            const response = await fetch(`/users/permissions/users/${userId}/permissions/`);
            const data = await response.json();
            
            if (data.success) {
                this.renderEditUserPermissions(data);
            } else {
                showAlert(data.message, 'danger');
                $('#editUserPermissionsModal').modal('hide');
            }
        } catch (error) {
            showAlert('حدث خطأ في تحميل صلاحيات المستخدم', 'danger');
            console.error('Error loading user permissions for edit:', error);
            $('#editUserPermissionsModal').modal('hide');
        }
    }

    renderEditUserPermissions(data) {
        const user = data.user;
        const categories = data.categories;
        const userDirectPermissions = data.permissions_overview.direct_permission_ids || [];

        let html = `
            <div class="mb-3">
                <h6>تعديل الصلاحيات المخصصة للمستخدم: ${user.full_name}</h6>
                <div class="alert alert-info">
                    <i class="fas fa-info-circle me-2"></i>
                    يمكنك إضافة أو إزالة الصلاحيات المخصصة للمستخدم. الصلاحيات من الدور لا يمكن تعديلها هنا.
                </div>
            </div>
            
            <div class="mb-3">
                <div class="d-flex justify-content-between align-items-center mb-3">
                    <h6 class="mb-0">الصلاحيات المخصصة المتاحة</h6>
                    <div class="btn-group btn-group-sm">
                        <button type="button" class="btn btn-outline-primary" onclick="selectAllUserPermissions()">
                            <i class="fas fa-check-double me-1"></i>تحديد الكل
                        </button>
                        <button type="button" class="btn btn-outline-secondary" onclick="clearAllUserPermissions()">
                            <i class="fas fa-times me-1"></i>إلغاء الكل
                        </button>
                    </div>
                </div>
                
                <div class="permissions-container" style="max-height: 400px; overflow-y: auto; border: 1px solid var(--bs-border-color); border-radius: 8px;">
        `;

        // Render categorized permissions for editing
        Object.keys(categories).forEach(categoryKey => {
            const categoryData = this.availablePermissions[categoryKey];
            const categoryPermissions = categoryData.permissions || [];
            
            if (categoryPermissions.length === 0) return;
            
            html += `
                <div class="permission-group">
                    <div class="permission-group-header">
                        <div class="form-check">
                            <input type="checkbox" class="form-check-input category-checkbox" 
                                   data-category="${categoryKey}" id="edit_category_${categoryKey}"
                                   onchange="toggleCategoryUserPermissions('${categoryKey}')">
                            <label class="form-check-label fw-bold" for="edit_category_${categoryKey}">
                                <i class="${categoryData.icon} me-2"></i>
                                ${categoryData.name} (${categoryPermissions.length} صلاحية)
                            </label>
                        </div>
                        <small class="text-muted d-block mt-1">${categoryData.description}</small>
                    </div>
                    <div class="permission-list">
                        <div class="row">
            `;
            
            categoryPermissions.forEach(perm => {
                const isChecked = userDirectPermissions.includes(perm.id);
                const isFromRole = categories[categoryKey] && 
                    categories[categoryKey].role_permissions.some(rolePerm => rolePerm.id === perm.id);
                
                html += `
                    <div class="col-md-6 mb-2">
                        <div class="form-check">
                            <input class="form-check-input user-permission-checkbox" 
                                   type="checkbox" 
                                   value="${perm.id}" 
                                   id="edit_perm_${perm.id}"
                                   data-category="${categoryKey}"
                                   ${isChecked ? 'checked' : ''}
                                   ${isFromRole ? 'disabled' : ''}>
                            <label class="form-check-label" for="edit_perm_${perm.id}">
                                <div class="permission-item">
                                    <div class="permission-name">
                                        ${perm.name}
                                        ${isFromRole ? '<span class="badge bg-success ms-1">من الدور</span>' : ''}
                                    </div>
                                    <div class="permission-codename text-muted">${perm.codename}</div>
                                </div>
                            </label>
                        </div>
                    </div>
                `;
            });
            
            html += `
                        </div>
                    </div>
                </div>
            `;
        });

        html += `
                </div>
            </div>
            
            <input type="hidden" id="editUserId" value="${user.id}">
        `;

        $('#editUserPermissionsModal .modal-body').html(html);
        
        // Update category checkboxes state
        this.updateUserPermissionCategoryCheckboxes();
    }

    updateUserPermissionCategoryCheckboxes() {
        $('.category-checkbox').each(function() {
            const categoryKey = $(this).data('category');
            const categoryPermissions = $(`.user-permission-checkbox[data-category="${categoryKey}"]:not(:disabled)`);
            const checkedPermissions = categoryPermissions.filter(':checked');
            
            if (checkedPermissions.length === 0) {
                $(this).prop('checked', false).prop('indeterminate', false);
            } else if (checkedPermissions.length === categoryPermissions.length) {
                $(this).prop('checked', true).prop('indeterminate', false);
            } else {
                $(this).prop('checked', false).prop('indeterminate', true);
            }
        });
    }

    async saveUserPermissions() {
        const userId = $('#editUserId').val();
        const selectedPermissions = $('.user-permission-checkbox:checked:not(:disabled)').map(function() {
            return parseInt($(this).val());
        }).get();

        try {
            const response = await fetch(`/users/permissions/users/${userId}/update-custom-permissions/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.csrfToken
                },
                body: JSON.stringify({
                    permission_ids: selectedPermissions
                })
            });

            const data = await response.json();
            
            if (data.success) {
                showAlert(data.message, 'success');
                $('#editUserPermissionsModal').modal('hide');
                
                // Update the user permissions count in the table
                const userRow = $(`.view-permissions-btn[data-user-id="${userId}"]`).closest('tr');
                const customPermsCount = data.custom_permissions_count || selectedPermissions.length;
                userRow.find('.custom-permissions-count').text(customPermsCount);
                
                // Update the tooltip
                const permissionsBtn = userRow.find('.view-permissions-btn');
                permissionsBtn.attr('title', `${customPermsCount} صلاحية مخصصة`);
                
            } else {
                showAlert(data.message, 'danger');
            }
        } catch (error) {
            showAlert('حدث خطأ في حفظ الصلاحيات', 'danger');
            console.error('Error saving user permissions:', error);
        }
    }

    // Bulk Operations
    toggleAllUsers(checkbox) {
        $('.user-checkbox').prop('checked', checkbox.checked);
        this.updateSelectedUsers();
    }

    updateSelectedUsers() {
        this.selectedUsers = $('.user-checkbox:checked').map(function() {
            return parseInt($(this).val());
        }).get();
    }

    bulkAssignRoles() {
        this.updateSelectedUsers();
        
        if (this.selectedUsers.length === 0) {
            showAlert('يرجى تحديد مستخدم واحد على الأقل', 'warning');
            return;
        }

        $('#selectedUsersInfo').html(`
            <div class="d-flex align-items-center">
                <i class="fas fa-users fa-2x text-primary me-3"></i>
                <div>
                    <strong>${this.selectedUsers.length} مستخدم محدد</strong>
                    <br><small class="text-muted">سيتم تعيين الدور لجميع المستخدمين المحددين</small>
                </div>
            </div>
        `);

        $('#bulkAssignModal').modal('show');
    }

    async performBulkAssign() {
        const roleId = $('#bulkRoleSelect').val();
        
        if (!roleId) {
            showAlert('يرجى اختيار الدور', 'warning');
            return;
        }

        try {
            const response = await fetch('/users/permissions/bulk-assign-roles/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.csrfToken
                },
                body: JSON.stringify({
                    user_ids: this.selectedUsers,
                    role_id: roleId
                })
            });

            const data = await response.json();
            
            if (data.success) {
                showAlert(data.message, 'success');
                $('#bulkAssignModal').modal('hide');
                setTimeout(() => window.location.reload(), 1000);
            } else {
                showAlert(data.message, 'danger');
            }
        } catch (error) {
            showAlert('حدث خطأ في التعيين الجماعي', 'danger');
            console.error('Error in bulk assign:', error);
        }
    }

    // Monitoring Functions - تحسين وظائف المراقبة
    updateMonitoringData(days) {
        const currentUrl = new URL(window.location);
        currentUrl.searchParams.set('tab', 'monitoring');
        currentUrl.searchParams.set('days', days);
        currentUrl.searchParams.delete('page');
        
        // تحديث الصفحة مع المعاملات الجديدة
        window.location.href = currentUrl.toString();
    }

    startMonitoringRefresh() {
        // Refresh monitoring data every 30 seconds if monitoring tab is active
        setInterval(() => {
            if ($('#monitoring-tab').hasClass('active')) {
                this.refreshMonitoringData();
            }
        }, 30000);
    }

    async refreshMonitoringData() {
        // Optional refresh for monitoring data
        // This is only called manually, not on tab switch
        try {
            this.showRefreshIndicator();
            // Just reload the page with monitoring tab
            window.location.href = updateUrlParameter(window.location.href, 'tab', 'monitoring');
        } catch (error) {
            console.error('Error refreshing monitoring data:', error);
        }
    }
    
    showRefreshIndicator() {
        const $indicator = $('<div class="refresh-indicator position-fixed top-0 end-0 m-3 alert alert-success alert-dismissible fade show" role="alert">' +
            '<i class="fas fa-sync-alt me-2"></i>تم تحديث بيانات المراقبة' +
            '<button type="button" class="btn-close" data-bs-dismiss="alert"></button>' +
            '</div>');
        
        $('body').append($indicator);
        
        // إزالة المؤشر تلقائياً بعد 3 ثواني
        setTimeout(() => {
            $indicator.fadeOut(() => $indicator.remove());
        }, 3000);
    }

    updateMonitoringDisplay(data) {
        // Update system health indicators
        if (data.system_health) {
            // تحديث مؤشرات صحة النظام
            this.updateSystemHealthDisplay(data.system_health);
        }
        
        // Update security alerts
        if (data.security_alerts && data.security_alerts.length > 0) {
            this.updateSecurityAlertsDisplay(data.security_alerts);
        }
        
        // Update usage statistics
        if (data.usage_statistics) {
            this.updateUsageStatisticsDisplay(data.usage_statistics);
        }
    }
    
    updateSystemHealthDisplay(healthData) {
        // تحديث عرض صحة النظام
        const healthItems = [
            { key: 'permissions_system', label: 'نظام الصلاحيات' },
            { key: 'governance_system', label: 'نظام الحوكمة' },
            { key: 'audit_logging', label: 'تسجيل العمليات' }
        ];
        
        healthItems.forEach(item => {
            const status = healthData[item.key] || 'unknown';
            const $statusElement = $(`.system-health [data-system="${item.key}"] .badge`);
            
            if ($statusElement.length) {
                $statusElement.removeClass('bg-success bg-warning bg-danger')
                    .addClass(status === 'healthy' ? 'bg-success' : 
                             status === 'warning' ? 'bg-warning' : 'bg-danger')
                    .text(status === 'healthy' ? 'يعمل' : 
                          status === 'warning' ? 'تحذير' : 'خطأ');
            }
        });
    }
    
    updateSecurityAlertsDisplay(alerts) {
        // تحديث عرض تنبيهات الأمان
        const $alertsContainer = $('.security-events .card-body');
        
        if (alerts.length === 0) {
            $alertsContainer.html(`
                <div class="text-center py-3">
                    <i class="fas fa-shield-check fa-2x text-success mb-2"></i>
                    <p class="text-muted mb-0">لا توجد أحداث أمان</p>
                    <small class="text-muted">النظام آمن</small>
                </div>
            `);
        } else {
            let alertsHtml = '';
            alerts.slice(0, 5).forEach(alert => {
                alertsHtml += `
                    <div class="d-flex align-items-start mb-3 pb-3 border-bottom">
                        <div class="flex-shrink-0 me-3">
                            <div class="bg-danger-subtle text-danger rounded-circle d-flex align-items-center justify-content-center" 
                                 style="width: 32px; height: 32px;">
                                <i class="fas fa-exclamation-triangle fa-sm"></i>
                            </div>
                        </div>
                        <div class="flex-grow-1">
                            <h6 class="mb-1 fs-6">${alert.operation}</h6>
                            <small class="text-muted">
                                ${alert.timestamp} مضت
                                ${alert.user ? '• ' + alert.user : ''}
                            </small>
                        </div>
                    </div>
                `;
            });
            $alertsContainer.html(alertsHtml);
        }
    }

    showErrorMessage(message) {
        // إزالة التنبيهات السابقة
        $('.alert.position-fixed').remove();
        
        // إنشاء تنبيه خطأ
        const alertHtml = `
            <div class="alert alert-danger alert-dismissible position-fixed" style="top: 20px; right: 20px; z-index: 9999; min-width: 300px;">
                <i class="fas fa-exclamation-triangle me-2"></i>
                ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `;
        
        $('body').append(alertHtml);
        
        // إزالة تلقائية بعد 5 ثواني
        setTimeout(() => {
            $('.alert.position-fixed').fadeOut(() => {
                $('.alert.position-fixed').remove();
            });
        }, 5000);
    }
}

// Global Functions (for onclick handlers)
window.editRole = function(roleId) {
    if (window.permissionsDashboard) {
        window.permissionsDashboard.editRole(roleId);
    }
};

window.deleteRole = function(roleId, roleName) {
    if (window.permissionsDashboard) {
        window.permissionsDashboard.deleteRole(roleId, roleName);
    }
};

window.createRole = function() {
    if (window.permissionsDashboard) {
        window.permissionsDashboard.createRole();
    }
};

window.updateRole = function() {
    if (window.permissionsDashboard) {
        window.permissionsDashboard.updateRole();
    }
};

window.viewUserPermissions = function(userId) {
    if (window.permissionsDashboard) {
        window.permissionsDashboard.viewUserPermissions(userId);
    }
};

window.assignUserRole = function(userId) {
    if (window.permissionsDashboard) {
        window.permissionsDashboard.assignUserRole(userId);
    }
};

window.assignRole = function() {
    if (window.permissionsDashboard) {
        window.permissionsDashboard.assignRole();
    }
};

window.bulkAssignRoles = function() {
    if (window.permissionsDashboard) {
        window.permissionsDashboard.bulkAssignRoles();
    }
};

window.performBulkAssign = function() {
    if (window.permissionsDashboard) {
        window.permissionsDashboard.performBulkAssign();
    }
};

window.toggleAllUsers = function(checkbox) {
    if (window.permissionsDashboard) {
        window.permissionsDashboard.toggleAllUsers(checkbox);
    }
};

window.editUserPermissions = function(userId) {
    if (window.permissionsDashboard) {
        window.permissionsDashboard.editUserPermissions(userId);
    }
};

window.saveUserPermissions = function() {
    if (window.permissionsDashboard) {
        window.permissionsDashboard.saveUserPermissions();
    }
};

window.toggleCategoryPermissions = function(categoryKey) {
    const categoryCheckbox = $(`.category-checkbox[data-category="${categoryKey}"]`);
    const permissionCheckboxes = $(`.permission-checkbox[data-category="${categoryKey}"]`);
    
    // تحديد حالة الـ checkbox الرئيسي
    const isChecked = categoryCheckbox.is(':checked');
    
    // تطبيق الحالة على جميع الصلاحيات
    permissionCheckboxes.prop('checked', isChecked);
    
    // تحديث حالة checkboxes الفئات الأخرى
    setTimeout(() => {
        const dashboard = window.permissionsDashboard;
        if (dashboard && dashboard.updateCategoryCheckboxes) {
            dashboard.updateCategoryCheckboxes();
        }
    }, 10);
};

window.toggleCategoryUserPermissions = function(categoryKey) {
    const categoryCheckbox = $(`.category-checkbox[data-category="${categoryKey}"]`);
    const permissionCheckboxes = $(`.user-permission-checkbox[data-category="${categoryKey}"]:not(:disabled)`);
    
    // تحديد حالة الـ checkbox الرئيسي
    const isChecked = categoryCheckbox.is(':checked');
    
    // تطبيق الحالة على جميع الصلاحيات غير المعطلة
    permissionCheckboxes.prop('checked', isChecked);
    
    // تحديث حالة checkboxes الفئات الأخرى
    setTimeout(() => {
        const dashboard = window.permissionsDashboard;
        if (dashboard && dashboard.updateUserPermissionCategoryCheckboxes) {
            dashboard.updateUserPermissionCategoryCheckboxes();
        }
    }, 10);
};

// إضافة مستمع للتغييرات في صلاحيات فردية
$(document).on('change', '.permission-checkbox', function() {
    const dashboard = window.permissionsDashboard;
    if (dashboard && dashboard.updateCategoryCheckboxes) {
        dashboard.updateCategoryCheckboxes();
    }
});

// إضافة مستمع للتغييرات في صلاحيات المستخدم
$(document).on('change', '.user-permission-checkbox', function() {
    const dashboard = window.permissionsDashboard;
    if (dashboard && dashboard.updateUserPermissionCategoryCheckboxes) {
        dashboard.updateUserPermissionCategoryCheckboxes();
    }
});

// Utility Functions
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// إضافة وظائف مساعدة للمودالات
window.selectAllPermissions = function() {
    $('.permission-checkbox').prop('checked', true);
    $('.category-checkbox').prop('checked', true).prop('indeterminate', false);
};

window.clearAllPermissions = function() {
    $('.permission-checkbox').prop('checked', false);
    $('.category-checkbox').prop('checked', false).prop('indeterminate', false);
};

window.selectAllUserPermissions = function() {
    $('.user-permission-checkbox:not(:disabled)').prop('checked', true);
    $('.category-checkbox').prop('checked', true).prop('indeterminate', false);
};

window.clearAllUserPermissions = function() {
    $('.user-permission-checkbox:not(:disabled)').prop('checked', false);
    $('.category-checkbox').prop('checked', false).prop('indeterminate', false);
};

// دوال إدارة الأدوار
window.createRole = function() {
    if (!window.userCanManageRoles) {
        showAlert('ليس لديك صلاحية لإنشاء الأدوار. يتطلب صلاحيات المدير.', 'warning');
        return;
    }
    
    if (window.permissionsDashboard) {
        window.permissionsDashboard.createRole();
    } else {
        showAlert('خطأ في النظام. يرجى إعادة تحميل الصفحة.', 'danger');
    }
};

window.editRole = function(roleId) {
    if (!window.userCanManageRoles) {
        showAlert('ليس لديك صلاحية لتعديل الأدوار. يتطلب صلاحيات المدير.', 'warning');
        return;
    }
    
    if (window.permissionsDashboard) {
        window.permissionsDashboard.editRole(roleId);
    } else {
        showAlert('خطأ في النظام. يرجى إعادة تحميل الصفحة.', 'danger');
    }
};

window.deleteRole = function(roleId, roleName) {
    if (!window.userCanManageRoles) {
        showAlert('ليس لديك صلاحية لحذف الأدوار. يتطلب صلاحيات المدير.', 'warning');
        return;
    }
    
    if (window.permissionsDashboard) {
        window.permissionsDashboard.deleteRole(roleId, roleName);
    } else {
        showAlert('خطأ في النظام. يرجى إعادة تحميل الصفحة.', 'danger');
    }
};

window.viewUserPermissions = function(userId) {
    if (!window.userCanViewPermissions) {
        showAlert('ليس لديك صلاحية لعرض صلاحيات المستخدمين.', 'warning');
        return;
    }
    
    if (window.permissionsDashboard) {
        window.permissionsDashboard.viewUserPermissions(userId);
    } else {
        showAlert('خطأ في النظام. يرجى إعادة تحميل الصفحة.', 'danger');
    }
};

window.editUserPermissions = function(userId) {
    if (!window.userCanManageRoles) {
        showAlert('ليس لديك صلاحية لتعديل صلاحيات المستخدمين. يتطلب صلاحيات المدير.', 'warning');
        return;
    }
    
    if (window.permissionsDashboard) {
        window.permissionsDashboard.editUserPermissions(userId);
    } else {
        showAlert('خطأ في النظام. يرجى إعادة تحميل الصفحة.', 'danger');
    }
};

window.toggleCategoryPermissions = function(categoryKey) {
    const $categoryCheckbox = $(`#category_${categoryKey}, #edit_category_${categoryKey}`);
    const $permissionCheckboxes = $(`.permission-checkbox[data-category="${categoryKey}"], .user-permission-checkbox[data-category="${categoryKey}"]:not(:disabled)`);
    
    if ($categoryCheckbox.is(':checked')) {
        $permissionCheckboxes.prop('checked', true);
    } else {
        $permissionCheckboxes.prop('checked', false);
    }
    
    // Update other category checkboxes
    if (window.permissionsDashboard) {
        window.permissionsDashboard.updateCategoryCheckboxes();
    }
};

window.selectAllPermissions = function() {
    $('.permission-checkbox').prop('checked', true);
    $('.category-checkbox').prop('checked', true).prop('indeterminate', false);
};

window.clearAllPermissions = function() {
    $('.permission-checkbox').prop('checked', false);
    $('.category-checkbox').prop('checked', false).prop('indeterminate', false);
};

window.toggleCategoryUserPermissions = function(categoryKey) {
    window.toggleCategoryPermissions(categoryKey);
    if (window.permissionsDashboard) {
        window.permissionsDashboard.updateUserPermissionCategoryCheckboxes();
    }
};

// دالة showAlert موحدة - تستخدم النظام الموحد للإشعارات
function showAlert(message, type = 'info') {
    if (typeof toastr !== 'undefined') {
        if (type === 'success') toastr.success(message);
        else if (type === 'error' || type === 'danger') toastr.error(message);
        else if (type === 'warning') toastr.warning(message);
        else toastr.info(message);
    }
}
    
    // البديل: استخدام toastr مباشرة
    if (typeof toastr !== 'undefined') {
        switch(type) {
            case 'success':
                toastr.success(message);
                break;
            case 'danger':
            case 'error':
                toastr.error(message);
                break;
            case 'warning':
                toastr.warning(message);
                break;
            case 'info':
            default:
                toastr.info(message);
                break;
        }
        return;
    }
    
    // البديل الأخير: alert عادي
    alert(message);
}

// تحسين وظيفة updateUrlParameter
function updateUrlParameter(url, param, paramVal) {
    let newAdditionalURL = "";
    let tempArray = url.split("?");
    let baseURL = tempArray[0];
    let additionalURL = tempArray[1];
    let temp = "";
    
    if (additionalURL) {
        tempArray = additionalURL.split("&");
        for (let i = 0; i < tempArray.length; i++) {
            if (tempArray[i].split('=')[0] != param) {
                newAdditionalURL += temp + tempArray[i];
                temp = "&";
            }
        }
    }
    
    if (paramVal) {
        let rows_txt = temp + "" + param + "=" + paramVal;
        return baseURL + "?" + newAdditionalURL + rows_txt;
    } else {
        return baseURL + "?" + newAdditionalURL;
    }
}

// Note: Dashboard initialization is handled in the template to avoid conflicts