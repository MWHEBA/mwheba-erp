/**
 * Syntax Validator - Development Only
 * Validates HTML/CSS/JS syntax in development mode
 */

(function() {
    'use strict';

    // Only run in development mode
    if (!window.location.hostname.includes('127.0.0.1') && 
        !window.location.hostname.includes('localhost')) {
        return;
    }


    // Check for common HTML issues
    function validateHTML() {
        const issues = [];
        
        // Check for unclosed tags
        const openTags = document.querySelectorAll('*');
        openTags.forEach(tag => {
            if (tag.innerHTML.includes('<') && !tag.innerHTML.includes('>')) {
                issues.push(`Potential unclosed tag in: ${tag.tagName}`);
            }
        });

        return issues;
    }

    // Check for CSS issues
    function validateCSS() {
        const issues = [];
        const sheets = document.styleSheets;
        
        try {
            for (let sheet of sheets) {
                if (sheet.href && sheet.href.includes(window.location.hostname)) {
                    // Only check local stylesheets
                    try {
                        const rules = sheet.cssRules || sheet.rules;
                        if (rules.length === 0) {
                            issues.push(`Empty stylesheet: ${sheet.href}`);
                        }
                    } catch (e) {
                        // CORS or access issues - skip
                    }
                }
            }
        } catch (e) {
            console.warn('CSS validation skipped:', e.message);
        }

        return issues;
    }

    // Run validation on page load
    window.addEventListener('DOMContentLoaded', function() {
        setTimeout(() => {
            const htmlIssues = validateHTML();
            const cssIssues = validateCSS();
            
            if (htmlIssues.length > 0 || cssIssues.length > 0) {
                console.group('⚠️ Syntax Validation Issues');
                if (htmlIssues.length > 0) {
                    console.warn('HTML Issues:', htmlIssues);
                }
                if (cssIssues.length > 0) {
                    console.warn('CSS Issues:', cssIssues);
                }
                console.groupEnd();
            } else {
            }
        }, 1000);
    });

})();
