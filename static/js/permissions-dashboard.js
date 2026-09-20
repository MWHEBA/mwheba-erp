/**
 * Enterprise Permissions Dashboard JavaScript
 * MWHEBA ERP - RBAC Phase 8 Standardized Engine
 * Flat UI Styling | Root CSS Variables | Toastr 3100ms | Auto-Prerequisite Resolver
 */

class PermissionsDashboard {
    constructor() {
        this.currentTab = 'overview';
        this.csrfToken = $('[name=csrfmiddlewaretoken]').val() || this.getCookie('csrftoken');
        this.availablePermissions = null;
        this.dependencyMap = null;
        this.isBatchOperation = false;
    }

    getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    init() {
        if (!this.csrfToken) {
            this.csrfToken = $('[name=csrfmiddlewaretoken]').val() || this.getCookie('csrftoken');
        }
        this.bindEvents();
        this.initializeTooltips();
        this.preloadPermissions();
    }

    notify(message, type = 'info', title = '') {
        if (typeof window.showNotification === 'function') {
            window.showNotification(message, type, title);
        } else if (typeof window.showToastr === 'function') {
            window.showToastr(message, type);
        } else if (typeof toastr !== 'undefined') {
            toastr[type === 'danger' ? 'error' : type](message, title);
        } else {
            alert(message);
        }
    }

    bindEvents() {
        // Tab switching
        $('button[data-bs-toggle="tab"]').on('shown.bs.tab', (e) => {
            const target = $(e.target).attr('data-bs-target');
            this.currentTab = target.replace('#', '');
            const url = new URL(window.location);
            url.searchParams.set('tab', this.currentTab);
            window.history.replaceState({}, '', url);
        });

        // Search & Filter
        this.initializeSearchAndFilters();

        // Modal Events
        this.initializeModalEvents();

        // Live Permission Search & Scoped Selectors inside Modals
        this.setupLiveSearch();
    }

    initializeSearchAndFilters() {
        // Search in Users Tab
        $('#userSearch').on('input', this.debounce(() => {
            const search = $('#userSearch').val();
            const url = new URL(window.location);
            if (search) {
                url.searchParams.set('search', search);
            } else {
                url.searchParams.delete('search');
            }
            url.searchParams.set('tab', 'users');
            window.location.href = url.toString();
        }, 500));

        // Filter by Role
        $('#userRoleFilter').on('change', function () {
            const roleId = $(this).val();
            const url = new URL(window.location);
            if (roleId) {
                url.searchParams.set('role', roleId);
            } else {
                url.searchParams.delete('role');
            }
            url.searchParams.set('tab', 'users');
            window.location.href = url.toString();
        });

        // Filter by Permissions
        $('#userPermissionsFilter').on('change', function () {
            const val = $(this).val();
            const url = new URL(window.location);
            if (val) {
                url.searchParams.set('has_permissions', val);
            } else {
                url.searchParams.delete('has_permissions');
            }
            url.searchParams.set('tab', 'users');
            window.location.href = url.toString();
        });

        // Filter by Days in Monitoring Tab
        $('input[name="daysFilter"]').on('change', function () {
            const days = $(this).val();
            const url = new URL(window.location);
            url.searchParams.set('days', days);
            url.searchParams.set('tab', 'monitoring');
            window.location.href = url.toString();
        });
    }

    initializeModalEvents() {
        // Create Role Modal
        $('#createRoleModal').on('show.bs.modal', (e) => {
            if (!window.userCanManageRoles) {
                e.preventDefault();
                this.notify('ليس لديك صلاحية لإنشاء الأدوار. يتطلب صلاحيات المدير.', 'warning');
                return false;
            }
        });

        $('#createRoleModal').on('shown.bs.modal', () => {
            this.renderPermissionsCheckboxes('#createRoleModal .permissions-container');
        });

        $('#createRoleModal').on('hidden.bs.modal', () => {
            $('#createRoleForm')[0].reset();
            $('#createRoleModal .permissions-container').html(`
                <div class="text-center py-4">
                    <div class="spinner-border spinner-border-sm text-primary me-2"></div>
                    جاري تحميل الصلاحيات...
                </div>
            `);
        });

        $('#createRoleForm').on('submit', (e) => {
            e.preventDefault();
            this.createRole();
        });

        // Edit Role Modal
        $('#editRoleForm').on('submit', (e) => {
            e.preventDefault();
            this.updateRole();
        });

        // Edit User Custom Permissions Form
        $('#editUserPermissionsForm').on('submit', (e) => {
            e.preventDefault();
            this.saveUserPermissions();
        });

        // Action Buttons for Roles
        $(document).on('click', '.edit-role-btn', (e) => {
            const roleId = $(e.currentTarget).data('role-id');
            if (!window.userCanManageRoles) {
                this.notify('ليس لديك صلاحية لتعديل الأدوار. يتطلب صلاحيات المدير.', 'warning');
                return;
            }
            this.editRole(roleId);
        });

        $(document).on('click', '.delete-role-btn', (e) => {
            const roleId = $(e.currentTarget).data('role-id');
            const roleName = $(e.currentTarget).data('role-name');
            if (!window.userCanManageRoles) {
                this.notify('ليس لديك صلاحية لحذف الأدوار. يتطلب صلاحيات المدير.', 'warning');
                return;
            }
            this.deleteRole(roleId, roleName);
        });

        // Assign Role to User
        $(document).on('click', '.assign-role-btn', (e) => {
            const btn = $(e.currentTarget);
            const userId = btn.data('user-id');
            const userName = btn.data('user-name');
            const currentRole = btn.data('current-role');
            let secondaryRoles = btn.data('secondary-roles') || [];
            if (typeof secondaryRoles === 'string') {
                try { secondaryRoles = JSON.parse(secondaryRoles); } catch (err) { secondaryRoles = []; }
            }
            this.showAssignRoleModal(userId, userName, currentRole, secondaryRoles);
        });

        $('#assignRoleForm').on('submit', (e) => {
            e.preventDefault();
            this.assignRole();
        });

        // Edit User Custom Permissions Button
        $(document).on('click', '.edit-user-perms-btn', (e) => {
            const btn = $(e.currentTarget);
            const userId = btn.data('user-id');
            const userName = btn.data('user-name');
            this.showEditUserPermissionsModal(userId, userName);
        });

        $('#saveUserPermsBtn').on('click', (e) => {
            e.preventDefault();
            this.saveUserPermissions();
        });

        // Login as user (Impersonation)
        $(document).on('click', '.login-as-user-btn', (e) => {
            const btn = $(e.currentTarget);
            const userId = btn.data('user-id');
            const userName = btn.data('user-name');
            this.loginAsUser(userId, userName);
        });

        // Select2 RTL inside Modals (Rule #8)
        if ($.fn.select2) {
            $('#assignRoleSelect').select2({
                theme: 'bootstrap-5',
                dir: 'rtl',
                dropdownParent: $('#assignRoleModal'),
                width: '100%'
            });
            $('#assignSecondaryRolesSelect').select2({
                theme: 'bootstrap-5',
                dir: 'rtl',
                dropdownParent: $('#assignRoleModal'),
                width: '100%'
            });
            $('#roleParent').select2({
                theme: 'bootstrap-5',
                dir: 'rtl',
                dropdownParent: $('#createRoleModal'),
                width: '100%'
            });
            $('#editRoleParent').select2({
                theme: 'bootstrap-5',
                dir: 'rtl',
                dropdownParent: $('#editRoleModal'),
                width: '100%'
            });
            $('#compareRole1, #compareRole2').select2({
                theme: 'bootstrap-5',
                dir: 'rtl',
                dropdownParent: $('#compareRolesModal'),
                width: '100%'
            });
        }

        // Compare & Export Roles Toolbar Handlers
        $('#compareRolesBtn').on('click', () => {
            $('#compareRolesModal').modal('show');
        });

        $('#executeRoleCompareBtn').on('click', () => {
            this.executeRoleCompare();
        });

        $('#exportRolesBtn').on('click', () => {
            this.exportRoles();
        });
    }

    loginAsUser(userId, userName) {
        if (!confirm(`هل أنت متأكد من تسجيل الدخول بهوية "${userName}"؟\nستتمكن من تصفح النظام بالصلاحيات الممنوحة له فقط.`)) {
            return;
        }

        $.ajax({
            url: `/users/${userId}/login-as/`,
            type: 'POST',
            headers: {
                'X-CSRFToken': this.getCsrfToken()
            },
            success: (response) => {
                if (response.success) {
                    if (window.showNotification) {
                        window.showNotification(response.message || 'تم تسجيل الدخول بنجاح', 'success');
                    }
                    setTimeout(() => {
                        window.location.href = response.redirect_url || '/';
                    }, 1000);
                } else {
                    if (window.showNotification) {
                        window.showNotification(response.message || 'حدث خطأ أثناء محاولة تسجيل الدخول', 'error');
                    } else {
                        alert(response.message || 'حدث خطأ');
                    }
                }
            },
            error: (xhr) => {
                const msg = xhr.responseJSON ? xhr.responseJSON.message : 'فشل طلب تسجيل الدخول';
                if (window.showNotification) {
                    window.showNotification(msg, 'error');
                } else {
                    alert(msg);
                }
            }
        });
    }

    initializeTooltips() {
        try {
            const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
            tooltipTriggerList.forEach((el) => {
                new bootstrap.Tooltip(el, {
                    trigger: 'hover focus',
                    placement: 'top'
                });
            });
        } catch (e) {
            // Ignore tooltip errors
        }
    }

    async preloadPermissions() {
        if (!this.availablePermissions) {
            try {
                const res = await fetch('/users/permissions/available-permissions/');
                const data = await res.json();
                if (data.success) {
                    this.availablePermissions = data.permissions;
                    this.dependencyMap = data.dependencies || {};
                }
            } catch (err) {
                console.error('Failed to preload permissions:', err);
            }
        }
    }

    async renderPermissionsCheckboxes(containerSelector, selectedPermIds = [], options = {}) {
        const $container = $(containerSelector);
        $container.html(`
            <div class="text-center py-4">
                <div class="spinner-border spinner-border-sm text-primary me-2"></div>
                جاري تحميل وتجهيز مصفوفة الصلاحيات...
            </div>
        `);

        if (!this.availablePermissions) {
            await this.preloadPermissions();
        }

        if (!this.availablePermissions) {
            $container.html('<div class="alert alert-danger p-3 m-3">فشل في تحميل الصلاحيات. يرجى إعادة المحاولة.</div>');
            return;
        }

        const isUserMode = !!options.isUserMode;
        const rolePermSet = new Set((options.rolePermIds || []).map(Number));
        const revokedSet = new Set((options.revokedPermIds || []).map(Number));
        const selectedSet = new Set(selectedPermIds.map(Number));
        const cleanSelector = containerSelector.replace(/[^a-zA-Z0-9]/g, '');

        let html = '<div class="p-3">';

        for (const [catKey, catData] of Object.entries(this.availablePermissions)) {
            if (!catData.permissions || catData.permissions.length === 0) continue;

            html += `
                <div class="card border mb-3 shadow-none bg-white rounded-2">
                    <div class="card-header bg-light py-2 px-3 d-flex justify-content-between align-items-center">
                        <div class="fw-bold text-dark">
                            <i class="${catData.icon} me-2 text-primary"></i>${catData.name}
                            <span class="badge bg-secondary ms-2">${catData.permissions.length}</span>
                        </div>
                        <div class="btn-group btn-group-sm">
                            <button type="button" class="btn btn-outline-secondary btn-sm py-0 px-2 select-cat-btn" data-cat="${catKey}">تحديد الكل</button>
                            <button type="button" class="btn btn-outline-secondary btn-sm py-0 px-2 deselect-cat-btn" data-cat="${catKey}">إلغاء</button>
                        </div>
                    </div>
                    <div class="card-body p-3">
                        <div class="row g-2">
            `;

            for (const perm of catData.permissions) {
                const fullQualified = `${perm.app_label}.${perm.codename}`;
                const permId = Number(perm.id);
                const isInherited = isUserMode && rolePermSet.has(permId);
                const isRevoked = isUserMode && revokedSet.has(permId);
                const isCustomChecked = selectedSet.has(permId);

                if (isInherited) {
                    // Inherited from role: locked with option to revoke
                    html += `
                        <div class="col-md-6 col-lg-4">
                            <div class="permission-item p-2 border rounded-1 ${isRevoked ? 'bg-danger-subtle border-danger' : 'bg-light'}">
                                <div class="d-flex justify-content-between align-items-start">
                                    <div class="me-2 flex-grow-1">
                                        <span class="perm-title fw-semibold d-block text-dark small ${isRevoked ? 'text-decoration-line-through text-muted' : ''}">${perm.name}</span>
                                        <span class="perm-code text-muted font-monospace" style="font-size: 0.75rem;">${perm.codename}</span>
                                        <div class="mt-1">
                                            <span class="badge bg-light text-secondary border"><i class="fas fa-lock me-1"></i>موروثة من الدور</span>
                                        </div>
                                    </div>
                                    <div class="form-check form-switch ms-1">
                                        <input class="form-check-input revoked-checkbox" type="checkbox" 
                                               value="${perm.id}" 
                                               id="rev_${cleanSelector}_${perm.id}"
                                               data-category="${catKey}"
                                               data-codename="${perm.codename}"
                                               ${isRevoked ? 'checked' : ''}
                                               title="حجب هذه الصلاحية للمستخدم">
                                        <label class="form-check-label text-danger small fw-bold" for="rev_${cleanSelector}_${perm.id}" style="font-size: 0.75rem;">
                                            حجب
                                        </label>
                                    </div>
                                </div>
                            </div>
                        </div>
                    `;
                } else {
                    html += `
                        <div class="col-md-6 col-lg-4">
                            <div class="form-check permission-item p-2 border rounded-1 bg-light">
                                <input class="form-check-input perm-checkbox" type="checkbox" 
                                       value="${perm.id}" 
                                       id="perm_${cleanSelector}_${perm.id}"
                                       data-category="${catKey}"
                                       data-codename="${perm.codename}"
                                       data-qualified="${fullQualified}"
                                       ${isCustomChecked ? 'checked' : ''}>
                                <label class="form-check-label w-100 cursor-pointer user-select-none" 
                                       for="perm_${cleanSelector}_${perm.id}">
                                    <span class="perm-title fw-semibold d-block text-dark small">${perm.name}</span>
                                    <span class="perm-code text-muted font-monospace" style="font-size: 0.75rem;">${perm.codename}</span>
                                    <span class="prereq-badge-container"></span>
                                </label>
                            </div>
                        </div>
                    `;
                }
            }

            html += `
                        </div>
                    </div>
                </div>
            `;
        }

        html += '</div>';
        $container.html(html);

        // Bind Checkbox events & Auto-prerequisite resolver
        this.bindCheckboxPrerequisites($container);
        this.bindRevokedCheckboxEvents($container);
    }

    bindCheckboxPrerequisites($container) {
        const self = this;

        // Select/Deselect by Category with batch flag
        $container.find('.select-cat-btn').on('click', function () {
            const cat = $(this).data('cat');
            self.isBatchOperation = true;
            $container.find(`.perm-checkbox[data-category="${cat}"]`).prop('checked', true).trigger('change');
            self.isBatchOperation = false;
        });

        $container.find('.deselect-cat-btn').on('click', function () {
            const cat = $(this).data('cat');
            self.isBatchOperation = true;
            $container.find(`.perm-checkbox[data-category="${cat}"]`).prop('checked', false).trigger('change');
            self.isBatchOperation = false;
        });

        // Auto-select prerequisites when checked & Cascade uncheck when unchecked
        $container.find('.perm-checkbox').on('change.depEngine', function () {
            const $cb = $(this);
            const isChecked = $cb.is(':checked');
            const qualified = $cb.data('qualified');
            const codename = $cb.data('codename');

            if (isChecked && self.dependencyMap) {
                // Find prerequisites (either by full qualified or by codename)
                const deps = self.dependencyMap[qualified] || self.dependencyMap[codename] || [];
                deps.forEach((depName) => {
                    const depClean = depName.includes('.') ? depName.split('.')[1] : depName;
                    const $depCb = $container.find(`.perm-checkbox[data-qualified="${depName}"], .perm-checkbox[data-codename="${depClean}"]`);
                    if ($depCb.length && !$depCb.is(':checked')) {
                        $depCb.prop('checked', true);
                        const $badgeContainer = $depCb.closest('.form-check').find('.prereq-badge-container');
                        if (!$badgeContainer.find('.prereq-badge').length) {
                            $badgeContainer.html('<span class="badge bg-light text-primary border prereq-badge mt-1" style="font-size: 0.7rem;"><i class="fas fa-link me-1"></i>متطلب تلقائي</span>');
                        }
                    }
                });
            } else if (!isChecked && self.dependencyMap && !self.isBatchOperation) {
                // Descending Cascade Uncheck:
                // If a prerequisite permission is unchecked, uncheck any permissions that depend on it
                const targetKey1 = qualified;
                const targetKey2 = codename;
                const uncheckDependents = [];

                for (const [permKey, depsList] of Object.entries(self.dependencyMap)) {
                    if (Array.isArray(depsList) && (depsList.includes(targetKey1) || depsList.includes(targetKey2))) {
                        const permClean = permKey.includes('.') ? permKey.split('.')[1] : permKey;
                        const $depCb = $container.find(`.perm-checkbox[data-qualified="${permKey}"], .perm-checkbox[data-codename="${permClean}"]`);
                        if ($depCb.length && $depCb.is(':checked')) {
                            $depCb.prop('checked', false);
                            $depCb.closest('.form-check').find('.prereq-badge-container').empty();
                            const title = $depCb.closest('.form-check').find('.perm-title').text().trim() || permClean;
                            uncheckDependents.push(title);
                        }
                    }
                }

                if (uncheckDependents.length > 0) {
                    const currentTitle = $cb.closest('.form-check').find('.perm-title').text().trim() || codename;
                    self.notify(`تم إلغاء تحديد (${uncheckDependents.length}) صلاحية تابعة لعدم توفر متطلبها الأساسي (${currentTitle}).`, 'info');
                }
            }
        });
    }

    bindRevokedCheckboxEvents($container) {
        $container.find('.revoked-checkbox').on('change', function () {
            const isRevoked = $(this).is(':checked');
            const $item = $(this).closest('.permission-item');
            const $title = $item.find('.perm-title');
            if (isRevoked) {
                $item.addClass('bg-danger-subtle border-danger').removeClass('bg-light');
                $title.addClass('text-decoration-line-through text-muted');
            } else {
                $item.removeClass('bg-danger-subtle border-danger').addClass('bg-light');
                $title.removeClass('text-decoration-line-through text-muted');
            }
        });
    }

    setupLiveSearch() {
        $(document).on('input', '.perm-search-input', function () {
            const query = $(this).val().trim().toLowerCase();
            const $modal = $(this).closest('.modal');
            const $clearBtn = $modal.find('.clear-perm-search-btn');
            if (query) {
                $clearBtn.show();
            } else {
                $clearBtn.hide();
            }

            $modal.find('.permissions-container .card').each(function () {
                let catHasVisible = false;
                $(this).find('.permission-item').each(function () {
                    const title = $(this).find('.perm-title').text().toLowerCase();
                    const code = $(this).find('.perm-code').text().toLowerCase();
                    const matches = !query || title.includes(query) || code.includes(query);
                    $(this).closest('.col-md-6, .col-lg-4, [class*="col-"]').toggle(matches);
                    if (matches) catHasVisible = true;
                });
                $(this).toggle(catHasVisible);
            });
        });

        $(document).on('click', '.clear-perm-search-btn', function () {
            const $modal = $(this).closest('.modal');
            $modal.find('.perm-search-input').val('').trigger('input');
        });
    }

    // Pre-flight consistency check before submission
    preflightValidatePermissions(containerSelector) {
        if (!this.dependencyMap) return true;
        const $container = $(containerSelector);
        const checkedQualified = new Set();
        $container.find('.perm-checkbox:checked').each(function () {
            checkedQualified.add($(this).data('qualified'));
            checkedQualified.add($(this).data('codename'));
        });

        let autoResolvedCount = 0;
        for (const perm of checkedQualified) {
            const deps = this.dependencyMap[perm] || [];
            deps.forEach((dep) => {
                const depClean = dep.includes('.') ? dep.split('.')[1] : dep;
                if (!checkedQualified.has(dep) && !checkedQualified.has(depClean)) {
                    const $missingCb = $container.find(`.perm-checkbox[data-qualified="${dep}"], .perm-checkbox[data-codename="${depClean}"]`);
                    if ($missingCb.length) {
                        $missingCb.prop('checked', true);
                        autoResolvedCount++;
                    }
                }
            });
        }

        if (autoResolvedCount > 0) {
            this.notify(`تم ضم ${autoResolvedCount} صلاحية قراءة تمهيدية تلقائياً لضمان اتساق الدور.`, 'info');
        }
        return true;
    }

    async createRole() {
        const form = $('#createRoleForm');
        const name = form.find('#roleName').val().trim();
        const displayName = form.find('#roleDisplayName').val().trim();
        const description = form.find('#roleDescription').val().trim();
        const parentRoleId = form.find('#roleParent').val();

        if (!name || !displayName) {
            this.notify('اسم الدور والاسم المعروض مطلوبان.', 'warning');
            return;
        }

        this.preflightValidatePermissions('#createRoleModal .permissions-container');

        const selectedPermissions = [];
        $('#createRoleModal .perm-checkbox:checked').each(function () {
            selectedPermissions.push(parseInt($(this).val()));
        });

        const btn = form.find('button[type="submit"]');
        btn.prop('disabled', true).html('<i class="fas fa-spinner fa-spin me-1"></i>جاري الحفظ...');

        try {
            const res = await fetch('/users/permissions/roles/create/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.csrfToken
                },
                body: JSON.stringify({
                    name: name,
                    display_name: displayName,
                    description: description,
                    parent_role_id: parentRoleId ? parseInt(parentRoleId) : null,
                    permissions: selectedPermissions
                })
            });
            const data = await res.json();

            if (data.success) {
                this.notify(data.message, 'success');
                $('#createRoleModal').modal('hide');
                // Standard Rule #10: 3100ms before reload preserving roles tab
                setTimeout(() => {
                    const url = new URL(window.location);
                    url.searchParams.set('tab', 'roles');
                    window.location.href = url.toString();
                }, 3100);
            } else {
                this.notify(data.message || 'فشل إنشاء الدور', 'danger');
                btn.prop('disabled', false).html('<i class="fas fa-save me-1"></i>إنشاء الدور');
            }
        } catch (err) {
            this.notify('حدث خطأ في الشبكة أثناء إنشاء الدور', 'danger');
            btn.prop('disabled', false).html('<i class="fas fa-save me-1"></i>إنشاء الدور');
        }
    }

    async editRole(roleId) {
        const modal = $('#editRoleModal');
        modal.modal('show');
        modal.find('.permissions-container').html(`
            <div class="text-center py-4">
                <div class="spinner-border spinner-border-sm text-primary me-2"></div>
                جاري تحميل بيانات الدور...
            </div>
        `);

        try {
            const res = await fetch(`/users/permissions/roles/${roleId}/edit/`);
            const data = await res.json();

            if (data.success) {
                const role = data.role;
                modal.find('#editRoleId').val(role.id);
                modal.find('#editRoleName').val(role.name);
                modal.find('#editRoleDisplayName').val(role.display_name);
                modal.find('#editRoleDescription').val(role.description);
                modal.find('#editRoleActive').prop('checked', role.is_active);

                // Populate parent role and disable self to prevent cycle
                modal.find('#editRoleParent option').prop('disabled', false);
                modal.find(`#editRoleParent option[value="${role.id}"]`).prop('disabled', true);
                modal.find('#editRoleParent').val(role.parent_role_id || '').trigger('change');

                await this.renderPermissionsCheckboxes('#editRoleModal .permissions-container', role.permissions);
            } else {
                this.notify('فشل تحميل بيانات الدور', 'danger');
                modal.modal('hide');
            }
        } catch (err) {
            this.notify('حدث خطأ أثناء تحميل بيانات الدور', 'danger');
            modal.modal('hide');
        }
    }

    async updateRole() {
        const form = $('#editRoleForm');
        const roleId = form.find('#editRoleId').val();
        const displayName = form.find('#editRoleDisplayName').val().trim();
        const description = form.find('#editRoleDescription').val().trim();
        const isActive = form.find('#editRoleActive').is(':checked');
        const parentRoleId = form.find('#editRoleParent').val();

        this.preflightValidatePermissions('#editRoleModal .permissions-container');

        const selectedPermissions = [];
        $('#editRoleModal .perm-checkbox:checked').each(function () {
            selectedPermissions.push(parseInt($(this).val()));
        });

        const btn = form.find('button[type="submit"]');
        btn.prop('disabled', true).html('<i class="fas fa-spinner fa-spin me-1"></i>جاري التحديث...');

        try {
            const res = await fetch(`/users/permissions/roles/${roleId}/edit/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.csrfToken
                },
                body: JSON.stringify({
                    display_name: displayName,
                    description: description,
                    is_active: isActive,
                    parent_role_id: parentRoleId ? parseInt(parentRoleId) : null,
                    permissions: selectedPermissions
                })
            });
            const data = await res.json();

            if (data.success) {
                this.notify(data.message, 'success');
                $('#editRoleModal').modal('hide');
                // Rule #10: 3100ms before reload preserving roles tab
                setTimeout(() => {
                    const url = new URL(window.location);
                    url.searchParams.set('tab', 'roles');
                    window.location.href = url.toString();
                }, 3100);
            } else {
                this.notify(data.message || 'فشل تحديث الدور', 'danger');
                btn.prop('disabled', false).html('<i class="fas fa-save me-1"></i>حفظ التغييرات');
            }
        } catch (err) {
            this.notify('حدث خطأ في الاتصال أثناء تحديث الدور', 'danger');
            btn.prop('disabled', false).html('<i class="fas fa-save me-1"></i>حفظ التغييرات');
        }
    }

    deleteRole(roleId, roleName) {
        if (!confirm(`هل أنت متأكد من رغبتك في حذف الدور "${roleName}"؟`)) {
            return;
        }

        fetch(`/users/permissions/roles/${roleId}/delete/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.csrfToken
            }
        })
            .then((res) => res.json())
            .then((data) => {
                if (data.success) {
                    this.notify(data.message, 'success');
                    setTimeout(() => {
                        const url = new URL(window.location);
                        url.searchParams.set('tab', 'roles');
                        window.location.href = url.toString();
                    }, 3100);
                } else {
                    this.notify(data.message || 'فشل حذف الدور', 'danger');
                }
            })
            .catch(() => {
                this.notify('حدث خطأ أثناء محاولة حذف الدور', 'danger');
            });
    }

    showAssignRoleModal(userId, userName, currentRole, secondaryRoles = []) {
        $('#assignUserId').val(userId);
        $('#assignUserName').text(userName);
        $('#assignRoleSelect').val(currentRole || '').trigger('change');
        $('#assignSecondaryRolesSelect').val(secondaryRoles || []).trigger('change');
        $('#assignRoleModal').modal('show');
    }

    async assignRole() {
        const userId = $('#assignUserId').val();
        const roleId = $('#assignRoleSelect').val();
        const secondaryRoleIds = $('#assignSecondaryRolesSelect').val() || [];
        const btn = $('#assignRoleBtn');

        btn.prop('disabled', true).find('.btn-text').addClass('d-none');
        btn.find('.btn-loading').removeClass('d-none');

        try {
            const res = await fetch(`/users/permissions/users/${userId}/assign-role/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.csrfToken
                },
                body: JSON.stringify({
                    role_id: roleId ? parseInt(roleId) : null,
                    secondary_role_ids: secondaryRoleIds.map(Number)
                })
            });
            const data = await res.json();

            if (data.success) {
                this.notify(data.message, 'success');
                $('#assignRoleModal').modal('hide');
                setTimeout(() => {
                    const url = new URL(window.location);
                    url.searchParams.set('tab', 'users');
                    window.location.href = url.toString();
                }, 3100);
            } else {
                this.notify(data.message || 'فشل تعيين الدور للمستخدم', 'danger');
                btn.prop('disabled', false).find('.btn-text').removeClass('d-none');
                btn.find('.btn-loading').addClass('d-none');
            }
        } catch (err) {
            this.notify('حدث خطأ أثناء تعيين الدور', 'danger');
            btn.prop('disabled', false).find('.btn-text').removeClass('d-none');
            btn.find('.btn-loading').addClass('d-none');
        }
    }

    async showEditUserPermissionsModal(userId, userName) {
        const modal = $('#editUserPermissionsModal');
        modal.find('#editUserPermsUserId').val(userId);
        modal.find('#editUserPermsName').text(userName);
        modal.find('.perm-search-input').val('');
        modal.find('.clear-perm-search-btn').hide();
        modal.modal('show');

        modal.find('.permissions-container').html(`
            <div class="text-center py-4">
                <div class="spinner-border spinner-border-sm text-primary me-2"></div>
                جاري تحميل صلاحيات المستخدم...
            </div>
        `);

        try {
            const res = await fetch(`/users/permissions/users/${userId}/permissions/`);
            const data = await res.json();
            if (data.success) {
                const customPermIds = (data.custom_permissions || []).map((p) => p.id);
                const rolePermIds = (data.role_permissions || []).map((p) => p.id);
                const revokedPermIds = (data.revoked_permissions || []).map((p) => p.id);
                await this.renderPermissionsCheckboxes(
                    '#editUserPermissionsModal .permissions-container', 
                    customPermIds,
                    { isUserMode: true, rolePermIds: rolePermIds, revokedPermIds: revokedPermIds }
                );
            } else {
                this.notify(data.message || 'فشل تحميل صلاحيات المستخدم', 'danger');
                modal.modal('hide');
            }
        } catch (err) {
            this.notify('حدث خطأ أثناء تحميل صلاحيات المستخدم', 'danger');
            modal.modal('hide');
        }
    }

    async saveUserPermissions() {
        const modal = $('#editUserPermissionsModal');
        const userId = modal.find('#editUserPermsUserId').val();
        if (!userId) return;

        this.preflightValidatePermissions('#editUserPermissionsModal .permissions-container');

        const selectedPermissions = [];
        $('#editUserPermissionsModal .perm-checkbox:checked').each(function () {
            selectedPermissions.push(parseInt($(this).val()));
        });

        const revokedPermissions = [];
        $('#editUserPermissionsModal .revoked-checkbox:checked').each(function () {
            revokedPermissions.push(parseInt($(this).val()));
        });

        const btn = $('#saveUserPermsBtn');
        btn.prop('disabled', true).html('<i class="fas fa-spinner fa-spin me-1"></i>جاري الحفظ...');

        try {
            const res = await fetch(`/users/permissions/users/${userId}/update-custom-permissions/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.csrfToken
                },
                body: JSON.stringify({
                    permission_ids: selectedPermissions,
                    revoked_permission_ids: revokedPermissions
                })
            });
            const data = await res.json();

            if (data.success) {
                this.notify(data.message, 'success');
                modal.modal('hide');
                setTimeout(() => {
                    window.location.reload();
                }, 3100);
            } else {
                this.notify(data.message || 'فشل تحديث صلاحيات المستخدم', 'danger');
                btn.prop('disabled', false).html('<i class="fas fa-save me-2"></i>حفظ التغييرات');
            }
        } catch (err) {
            this.notify('حدث خطأ في الاتصال أثناء تحديث الصلاحيات', 'danger');
            btn.prop('disabled', false).html('<i class="fas fa-save me-2"></i>حفظ التغييرات');
        }
    }

    async executeRoleCompare() {
        const role1Id = $('#compareRole1').val();
        const role2Id = $('#compareRole2').val();

        if (!role1Id || !role2Id) {
            this.notify('يرجى تحديد الدورين لإجراء المقارنة.', 'warning');
            return;
        }

        if (role1Id === role2Id) {
            this.notify('يرجى اختيار دورين مختلفين للمقارنة.', 'warning');
            return;
        }

        const $btn = $('#executeRoleCompareBtn');
        const $loading = $('#roleCompareLoading');
        const $results = $('#roleCompareResults');
        const $empty = $('#roleCompareEmpty');

        $btn.prop('disabled', true).html('<i class="fas fa-spinner fa-spin me-1"></i>جاري...');
        $loading.show();
        $results.hide();
        $empty.hide();

        try {
            const res = await fetch(`/users/permissions/compare-roles/?role1_id=${encodeURIComponent(role1Id)}&role2_id=${encodeURIComponent(role2Id)}`, {
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'Accept': 'application/json'
                }
            });
            const data = await res.json();

            if (data.success && data.comparison) {
                const comp = data.comparison;
                
                // Update KPI Cards
                $('#statCommonCount').text(comp.comparison.common_count);
                $('#statRole1OnlyCount').text(comp.comparison.role1_only_count);
                $('#statRole2OnlyCount').text(comp.comparison.role2_only_count);
                $('#statSimilarity').text(`${comp.comparison.similarity_percentage}%`);

                $('#statRole1Label').text(`خاص بـ ${comp.role1.name}`);
                $('#statRole2Label').text(`خاص بـ ${comp.role2.name}`);
                $('#role1OnlyHeader').html(`<i class="fas fa-user-tag me-1"></i>خاص بـ ${comp.role1.name} فقط (${comp.comparison.role1_only_count})`);
                $('#role2OnlyHeader').html(`<i class="fas fa-user-tag me-1"></i>خاص بـ ${comp.role2.name} فقط (${comp.comparison.role2_only_count})`);

                // Helper to render app-grouped dictionary
                const renderGroupedPerms = (groupedMap, colorClass = 'text-primary') => {
                    if (!groupedMap || Object.keys(groupedMap).length === 0) {
                        return '<div class="text-muted text-center py-4 small">لا توجد صلاحيات في هذه الفئة</div>';
                    }
                    let out = '';
                    for (const [appLabel, permsList] of Object.entries(groupedMap)) {
                        out += `<div class="mb-3">
                            <div class="fw-bold small text-secondary border-bottom pb-1 mb-2">
                                <i class="fas fa-folder-open me-1 text-muted"></i>${appLabel.toUpperCase()}
                            </div>
                            <ul class="list-unstyled mb-0">`;
                        permsList.forEach(p => {
                            out += `<li class="small py-1 border-bottom border-light">
                                <i class="fas fa-check-circle ${colorClass} me-1 small"></i>
                                <span class="fw-semibold text-dark">${p.name}</span>
                                <div class="text-muted font-monospace" style="font-size: 0.7rem; padding-right: 18px;">${p.codename}</div>
                            </li>`;
                        });
                        out += `</ul></div>`;
                    }
                    return out;
                };

                $('#role1OnlyList').html(renderGroupedPerms(comp.permissions.role1_only, 'text-primary'));
                $('#commonPermsList').html(renderGroupedPerms(comp.permissions.common, 'text-success'));
                $('#role2OnlyList').html(renderGroupedPerms(comp.permissions.role2_only, 'text-warning'));

                $results.show();
            } else {
                this.notify(data.message || 'فشلت عملية مقارنة الأدوار', 'danger');
                $empty.show();
            }
        } catch (err) {
            this.notify('حدث خطأ في الاتصال أثناء مقارنة الأدوار.', 'danger');
            $empty.show();
        } finally {
            $btn.prop('disabled', false).html('<i class="fas fa-sync-alt me-1"></i>مقارنة');
            $loading.hide();
        }
    }

    async exportRoles() {
        const $btn = $('#exportRolesBtn');
        const origHtml = $btn.html();
        $btn.prop('disabled', true).html('<i class="fas fa-spinner fa-spin me-1"></i>جاري التصدير...');

        try {
            const res = await fetch('/users/permissions/export-roles/', {
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'Accept': 'application/json'
                }
            });
            const data = await res.json();

            if (data.success && data.export_data) {
                const jsonStr = JSON.stringify(data.export_data, null, 2);
                const blob = new Blob([jsonStr], { type: 'application/json' });
                const url = URL.createObjectURL(blob);
                const filename = data.filename || `roles_export_${Date.now()}.json`;

                const a = document.createElement('a');
                a.href = url;
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);

                this.notify('تم تصدير ملف إعدادات وتكوين الأدوار بنجاح.', 'success');
            } else {
                this.notify(data.message || 'فشل تصدير إعدادات الأدوار', 'danger');
            }
        } catch (err) {
            this.notify('حدث خطأ في الاتصال أثناء تصدير الأدوار.', 'danger');
        } finally {
            $btn.prop('disabled', false).html(origHtml);
        }
    }

    debounce(func, wait) {
        let timeout;
        return function (...args) {
            clearTimeout(timeout);
            timeout = setTimeout(() => func.apply(this, args), wait);
        };
    }
}

// Scoped modal helpers (fallback + class-based scoping)
$(document).on('click', '.select-all-modal-btn', function () {
    const $modal = $(this).closest('.modal');
    $modal.find('.permissions-container .perm-checkbox:not(:disabled)').prop('checked', true).trigger('change');
});

$(document).on('click', '.clear-all-modal-btn', function () {
    const $modal = $(this).closest('.modal');
    $modal.find('.permissions-container .perm-checkbox:not(:disabled)').prop('checked', false).trigger('change');
});

window.selectAllPermissions = function () {
    $('.modal.show .permissions-container .perm-checkbox:not(:disabled)').prop('checked', true).trigger('change');
};

window.clearAllPermissions = function () {
    $('.modal.show .permissions-container .perm-checkbox:not(:disabled)').prop('checked', false).trigger('change');
};