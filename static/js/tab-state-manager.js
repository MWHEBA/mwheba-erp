/**
 * Tab State Manager
 * إدارة حالة التابات والنماذج والتفاعلات
 */

class TabStateManager {
    constructor() {
        this.formStates = new Map();
        this.scrollPositions = new Map();
        this.expandedSections = new Map();
        this.userInteractions = new Map();
        this.autoSaveInterval = null;
        this.debounceTimers = new Map();
        
        this.init();
    }

    init() {
        this.bindFormEvents();
        this.bindScrollEvents();
        this.bindExpandCollapseEvents();
        this.bindVisualFeedbackEvents();
        this.setupAutoSave();
        this.restoreAllStates();
    }

    bindFormEvents() {
        // Form input events with debouncing
        document.addEventListener('input', (e) => {
            if (this.isTabFormElement(e.target)) {
                this.debounceFormSave(e.target);
                this.showFormChangeIndicator(e.target);
            }
        });

        // Form change events (for select, radio, checkbox)
        document.addEventListener('change', (e) => {
            if (this.isTabFormElement(e.target)) {
                this.saveFormElementState(e.target);
                this.showFormChangeIndicator(e.target);
            }
        });

        // Form focus events
        document.addEventListener('focus', (e) => {
            if (this.isTabFormElement(e.target)) {
                this.trackUserInteraction(e.target, 'focus');
                this.highlightFormSection(e.target);
            }
        }, true);

        // Form blur events
        document.addEventListener('blur', (e) => {
            if (this.isTabFormElement(e.target)) {
                this.validateFormElement(e.target);
                this.removeFormSectionHighlight(e.target);
            }
        }, true);

        // Form submission prevention for unsaved changes
        document.addEventListener('beforeunload', (e) => {
            if (this.hasUnsavedChanges()) {
                e.preventDefault();
                e.returnValue = 'لديك تغييرات غير محفوظة. هل تريد المغادرة؟';
                return e.returnValue;
            }
        });
    }

    bindScrollEvents() {
        // Track scroll positions for each tab
        document.querySelectorAll('.tab-pane').forEach(tabPane => {
            tabPane.addEventListener('scroll', (e) => {
                this.debounceScrollSave(tabPane);
            });
        });
    }

    bindExpandCollapseEvents() {
        // Track expanded/collapsed sections
        document.addEventListener('shown.bs.collapse', (e) => {
            this.saveExpandedState(e.target, true);
        });

        document.addEventListener('hidden.bs.collapse', (e) => {
            this.saveExpandedState(e.target, false);
        });

        // Track accordion states
        document.addEventListener('shown.bs.accordion', (e) => {
            this.saveAccordionState(e.target);
        });
    }

    bindVisualFeedbackEvents() {
        // Add visual feedback for user interactions
        document.addEventListener('click', (e) => {
            if (e.target && e.target.matches && e.target.matches('.btn, .nav-link, .card-header')) {
                this.addClickFeedback(e.target);
            }
        });

        // Hover effects for interactive elements
        document.addEventListener('mouseenter', (e) => {
            if (e.target && e.target.matches && e.target.matches('.clickable, .interactive')) {
                this.addHoverFeedback(e.target);
            }
        });

        document.addEventListener('mouseleave', (e) => {
            if (e.target && e.target.matches && e.target.matches('.clickable, .interactive')) {
                this.removeHoverFeedback(e.target);
            }
        });
    }

    setupAutoSave() {
        // Auto-save form states every 30 seconds
        this.autoSaveInterval = setInterval(() => {
            this.saveAllFormStates();
        }, 30000);
    }

    isTabFormElement(element) {
        return element && element.matches && 
               element.matches('.tab-pane input, .tab-pane textarea, .tab-pane select') &&
               !element.matches('[data-no-save]');
    }

    debounceFormSave(element) {
        const key = this.getElementKey(element);
        
        // Clear existing timer
        if (this.debounceTimers.has(key)) {
            clearTimeout(this.debounceTimers.get(key));
        }
        
        // Set new timer
        const timer = setTimeout(() => {
            this.saveFormElementState(element);
            this.debounceTimers.delete(key);
        }, 500);
        
        this.debounceTimers.set(key, timer);
    }

    debounceScrollSave(tabPane) {
        const key = `scroll_${tabPane.id}`;
        
        if (this.debounceTimers.has(key)) {
            clearTimeout(this.debounceTimers.get(key));
        }
        
        const timer = setTimeout(() => {
            this.saveScrollPosition(tabPane);
            this.debounceTimers.delete(key);
        }, 200);
        
        this.debounceTimers.set(key, timer);
    }

    saveFormElementState(element) {
        const tabId = this.getTabId(element);
        const elementKey = this.getElementKey(element);
        
        if (!tabId) return;
        
        let tabFormState = this.formStates.get(tabId) || {};
        
        const elementState = {
            value: element.value,
            type: element.type,
            checked: element.checked,
            selectedIndex: element.selectedIndex,
            timestamp: Date.now()
        };
        
        tabFormState[elementKey] = elementState;
        this.formStates.set(tabId, tabFormState);
        
        // Save to sessionStorage
        this.persistFormState(tabId, tabFormState);
        
        // Mark as changed
        this.markElementAsChanged(element);
    }

    saveAllFormStates() {
        document.querySelectorAll('.tab-pane').forEach(tabPane => {
            const tabId = '#' + tabPane.id;
            const formElements = tabPane.querySelectorAll('input, textarea, select');
            
            formElements.forEach(element => {
                if (this.isTabFormElement(element)) {
                    this.saveFormElementState(element);
                }
            });
        });
    }

    restoreFormState(tabId) {
        // Try to get from memory first
        let formState = this.formStates.get(tabId);
        
        // If not in memory, try sessionStorage
        if (!formState) {
            formState = this.loadFormStateFromStorage(tabId);
            if (formState) {
                this.formStates.set(tabId, formState);
            }
        }
        
        if (!formState) return;
        
        const tabPane = document.querySelector(tabId);
        if (!tabPane) return;
        
        Object.entries(formState).forEach(([elementKey, elementState]) => {
            const element = this.findElementByKey(tabPane, elementKey);
            if (element) {
                this.restoreElementState(element, elementState);
            }
        });
    }

    restoreElementState(element, state) {
        try {
            if (state.type === 'checkbox' || state.type === 'radio') {
                element.checked = state.checked;
            } else if (element.tagName === 'SELECT') {
                element.value = state.value;
                if (state.selectedIndex !== undefined) {
                    element.selectedIndex = state.selectedIndex;
                }
            } else {
                element.value = state.value;
            }
            
            // Mark as restored (not changed)
            this.markElementAsRestored(element);
            
            // Trigger change event for dependent elements
            element.dispatchEvent(new Event('change', { bubbles: true }));
        } catch (error) {
            console.warn('Error restoring element state:', error);
        }
    }

    saveScrollPosition(tabPane) {
        const tabId = '#' + tabPane.id;
        const scrollData = {
            scrollTop: tabPane.scrollTop,
            scrollLeft: tabPane.scrollLeft,
            timestamp: Date.now()
        };
        
        this.scrollPositions.set(tabId, scrollData);
        sessionStorage.setItem(`scroll_${tabId}`, JSON.stringify(scrollData));
    }

    restoreScrollPosition(tabId) {
        let scrollData = this.scrollPositions.get(tabId);
        
        if (!scrollData) {
            const saved = sessionStorage.getItem(`scroll_${tabId}`);
            if (saved) {
                try {
                    scrollData = JSON.parse(saved);
                    this.scrollPositions.set(tabId, scrollData);
                } catch (error) {
                    console.warn('Error parsing saved scroll position:', error);
                    return;
                }
            }
        }
        
        if (!scrollData) return;
        
        const tabPane = document.querySelector(tabId);
        if (tabPane) {
            // Restore scroll position with smooth animation
            tabPane.scrollTo({
                top: scrollData.scrollTop,
                left: scrollData.scrollLeft,
                behavior: 'smooth'
            });
        }
    }

    saveExpandedState(element, isExpanded) {
        const tabId = this.getTabId(element);
        const elementId = element.id;
        
        if (!tabId || !elementId) return;
        
        let expandedState = this.expandedSections.get(tabId) || {};
        expandedState[elementId] = {
            expanded: isExpanded,
            timestamp: Date.now()
        };
        
        this.expandedSections.set(tabId, expandedState);
        sessionStorage.setItem(`expanded_${tabId}`, JSON.stringify(expandedState));
    }

    restoreExpandedStates(tabId) {
        let expandedState = this.expandedSections.get(tabId);
        
        if (!expandedState) {
            const saved = sessionStorage.getItem(`expanded_${tabId}`);
            if (saved) {
                try {
                    expandedState = JSON.parse(saved);
                    this.expandedSections.set(tabId, expandedState);
                } catch (error) {
                    console.warn('Error parsing saved expanded state:', error);
                    return;
                }
            }
        }
        
        if (!expandedState) return;
        
        Object.entries(expandedState).forEach(([elementId, state]) => {
            const element = document.getElementById(elementId);
            if (element) {
                if (state.expanded) {
                    // Show collapsed element
                    const collapse = new bootstrap.Collapse(element, { show: true });
                } else {
                    // Ensure element is hidden
                    element.classList.remove('show');
                }
            }
        });
    }

    showFormChangeIndicator(element) {
        // Add visual indicator for changed form elements
        element.classList.add('form-changed');
        
        // Add indicator to parent form group
        const formGroup = element.closest('.form-group, .mb-3, .row');
        if (formGroup) {
            formGroup.classList.add('has-changes');
        }
        
        // Add indicator to tab
        const tabId = this.getTabId(element);
        if (tabId) {
            this.addTabChangeIndicator(tabId);
        }
    }

    addTabChangeIndicator(tabId) {
        const tabButton = document.querySelector(`button[data-bs-target="${tabId}"]`);
        if (tabButton) {
            let indicator = tabButton.querySelector('.change-indicator');
            if (!indicator) {
                indicator = document.createElement('span');
                indicator.className = 'change-indicator';
                indicator.innerHTML = '<i class="fas fa-circle text-warning"></i>';
                indicator.style.fontSize = '0.5rem';
                indicator.style.marginLeft = '0.25rem';
                tabButton.appendChild(indicator);
            }
        }
    }

    removeTabChangeIndicator(tabId) {
        const tabButton = document.querySelector(`button[data-bs-target="${tabId}"]`);
        if (tabButton) {
            const indicator = tabButton.querySelector('.change-indicator');
            if (indicator) {
                indicator.remove();
            }
        }
    }

    markElementAsChanged(element) {
        element.dataset.changed = 'true';
        element.dataset.changeTime = Date.now().toString();
    }

    markElementAsRestored(element) {
        element.dataset.changed = 'false';
        delete element.dataset.changeTime;
        element.classList.remove('form-changed');
        
        const formGroup = element.closest('.form-group, .mb-3, .row');
        if (formGroup) {
            formGroup.classList.remove('has-changes');
        }
    }

    highlightFormSection(element) {
        const section = element.closest('.tab-section, .card, .form-section');
        if (section) {
            section.classList.add('section-focused');
        }
    }

    removeFormSectionHighlight(element) {
        const section = element.closest('.tab-section, .card, .form-section');
        if (section) {
            section.classList.remove('section-focused');
        }
    }

    validateFormElement(element) {
        // Basic validation feedback
        if (element.required && !element.value.trim()) {
            element.classList.add('is-invalid');
            this.showValidationMessage(element, 'هذا الحقل مطلوب');
        } else {
            element.classList.remove('is-invalid');
            this.hideValidationMessage(element);
        }
    }

    showValidationMessage(element, message) {
        let feedback = element.parentNode.querySelector('.invalid-feedback');
        if (!feedback) {
            feedback = document.createElement('div');
            feedback.className = 'invalid-feedback';
            element.parentNode.appendChild(feedback);
        }
        feedback.textContent = message;
    }

    hideValidationMessage(element) {
        const feedback = element.parentNode.querySelector('.invalid-feedback');
        if (feedback) {
            feedback.remove();
        }
    }

    addClickFeedback(element) {
        element.classList.add('clicked');
        setTimeout(() => {
            element.classList.remove('clicked');
        }, 150);
    }

    addHoverFeedback(element) {
        element.classList.add('hovered');
    }

    removeHoverFeedback(element) {
        element.classList.remove('hovered');
    }

    trackUserInteraction(element, type) {
        const tabId = this.getTabId(element);
        if (!tabId) return;
        
        let interactions = this.userInteractions.get(tabId) || [];
        interactions.push({
            element: this.getElementKey(element),
            type: type,
            timestamp: Date.now()
        });
        
        // Keep only last 50 interactions
        if (interactions.length > 50) {
            interactions = interactions.slice(-50);
        }
        
        this.userInteractions.set(tabId, interactions);
    }

    hasUnsavedChanges() {
        const changedElements = document.querySelectorAll('[data-changed="true"]');
        return changedElements.length > 0;
    }

    getChangedElementsCount(tabId = null) {
        let selector = '[data-changed="true"]';
        if (tabId) {
            const tabPane = document.querySelector(tabId);
            if (tabPane) {
                return tabPane.querySelectorAll(selector).length;
            }
        }
        return document.querySelectorAll(selector).length;
    }

    clearTabChanges(tabId) {
        const tabPane = document.querySelector(tabId);
        if (!tabPane) return;
        
        const changedElements = tabPane.querySelectorAll('[data-changed="true"]');
        changedElements.forEach(element => {
            this.markElementAsRestored(element);
        });
        
        this.removeTabChangeIndicator(tabId);
    }

    restoreAllStates() {
        // Restore states for all tabs
        document.querySelectorAll('.tab-pane').forEach(tabPane => {
            const tabId = '#' + tabPane.id;
            this.restoreFormState(tabId);
            this.restoreScrollPosition(tabId);
            this.restoreExpandedStates(tabId);
        });
    }

    persistFormState(tabId, formState) {
        try {
            sessionStorage.setItem(`formState_${tabId}`, JSON.stringify(formState));
        } catch (error) {
            console.warn('Error saving form state to sessionStorage:', error);
        }
    }

    loadFormStateFromStorage(tabId) {
        try {
            const saved = sessionStorage.getItem(`formState_${tabId}`);
            return saved ? JSON.parse(saved) : null;
        } catch (error) {
            console.warn('Error loading form state from sessionStorage:', error);
            return null;
        }
    }

    // Utility methods
    getTabId(element) {
        const tabPane = element.closest('.tab-pane');
        return tabPane ? '#' + tabPane.id : null;
    }

    getElementKey(element) {
        return element.name || element.id || `${element.tagName}_${Array.from(element.parentNode.children).indexOf(element)}`;
    }

    findElementByKey(container, key) {
        return container.querySelector(`[name="${key}"], #${key}`) ||
               Array.from(container.querySelectorAll('input, textarea, select')).find(el => 
                   this.getElementKey(el) === key
               );
    }

    // Public API
    saveCurrentTabState() {
        const activeTab = document.querySelector('.tab-pane.active');
        if (activeTab) {
            const tabId = '#' + activeTab.id;
            this.saveScrollPosition(activeTab);
            
            const formElements = activeTab.querySelectorAll('input, textarea, select');
            formElements.forEach(element => {
                if (this.isTabFormElement(element)) {
                    this.saveFormElementState(element);
                }
            });
        }
    }

    restoreTabState(tabId) {
        this.restoreFormState(tabId);
        this.restoreScrollPosition(tabId);
        this.restoreExpandedStates(tabId);
    }

    clearAllStates() {
        this.formStates.clear();
        this.scrollPositions.clear();
        this.expandedSections.clear();
        this.userInteractions.clear();
        
        // Clear sessionStorage
        Object.keys(sessionStorage).forEach(key => {
            if (key.startsWith('formState_') || 
                key.startsWith('scroll_') || 
                key.startsWith('expanded_')) {
                sessionStorage.removeItem(key);
            }
        });
    }

    destroy() {
        if (this.autoSaveInterval) {
            clearInterval(this.autoSaveInterval);
        }
        
        this.debounceTimers.forEach(timer => clearTimeout(timer));
        this.debounceTimers.clear();
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    if (document.querySelector('.profile-tabs')) {
        window.tabStateManager = new TabStateManager();
        
        // Listen for tab changes to restore state
        document.addEventListener('tabActivated', function(event) {
            const { tabId } = event.detail;
            if (window.tabStateManager) {
                setTimeout(() => {
                    window.tabStateManager.restoreTabState(tabId);
                }, 100);
            }
        });
        
        // Listen for tab deactivation to save state
        document.addEventListener('tabDeactivated', function(event) {
            const { tabId } = event.detail;
            if (window.tabStateManager) {
                window.tabStateManager.saveCurrentTabState();
            }
        });
    }
});

// Handle page unload
window.addEventListener('beforeunload', function() {
    if (window.tabStateManager) {
        window.tabStateManager.saveCurrentTabState();
        window.tabStateManager.destroy();
    }
});

// Export for use in other modules
window.TabStateManager = TabStateManager;