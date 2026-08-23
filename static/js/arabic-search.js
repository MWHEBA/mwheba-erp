/**
 * MWHEBA ERP - Unified Smart Arabic Search Frontend Engine
 * ========================================================
 * Provides intelligent Arabic string normalization and Select2/DataTable matchers.
 */

(function(window, $) {
    'use strict';

    const EASTERN_DIGITS_MAP = {
        '٠': '0', '١': '1', '٢': '2', '٣': '3', '٤': '4',
        '٥': '5', '٦': '6', '٧': '7', '٨': '8', '٩': '9'
    };

    const FOREIGN_CHARS_MAP = {
        'ڤ': 'ف', 'پ': 'ب', 'چ': 'ج', 'گ': 'ك', 'ک': 'ك', 'ی': 'ي'
    };

    const COMPOUND_PREFIXES = ['عبد', 'ابو', 'كفر', 'بور', 'راس', 'عين', 'بني', 'بيت', 'دير'];

    /**
     * Normalizes an Arabic string for robust fuzzy/token matching.
     */
    function normalizeArabic(text) {
        if (!text) return '';

        let s = String(text).toLowerCase();

        // 1. Convert Eastern digits to Western digits
        s = s.replace(/[٠-٩]/g, function(d) {
            return EASTERN_DIGITS_MAP[d] || d;
        });

        // 2. Map Persian / Loanword characters
        s = s.replace(/[ڤپچگکی]/g, function(c) {
            return FOREIGN_CHARS_MAP[c] || c;
        });

        // 3. Strip Tashkeel & Tatweel
        s = s.replace(/[\u064B-\u065F\u0670\u06D6-\u06ED\u0640]/g, '');

        // 4. Standardize Alif forms
        s = s.replace(/[أإآٱ]/g, 'ا');

        // 5. Standardize Ta Marbuta
        s = s.replace(/ة/g, 'ه');

        // 6. Standardize Alif Maqsura and Hamza on Nabrah
        s = s.replace(/[ىئ]/g, 'ي');

        // 7. Standardize Hamza on Waw
        s = s.replace(/ؤ/g, 'و');

        // 8. Remove isolated Hamza
        s = s.replace(/ء/g, '');

        // 9. Reduce repeated characters (> 2)
        s = s.replace(/(.)\1{2,}/g, '$1');

        // 10. Replace punctuations with space
        s = s.replace(/[\.,_\-\/\\()\[\]{}\"\':;?!+=*&^%$#@~`|<>،؛؟]/g, ' ');

        // 11. Normalize compound names (e.g. عبد الرحمن -> عبدالرحمن in tokens)
        for (let i = 0; i < COMPOUND_PREFIXES.length; i++) {
            const p = COMPOUND_PREFIXES[i];
            const regex = new RegExp('(^|\\s)' + p + '\\s+', 'g');
            s = s.replace(regex, '$1' + p);
        }

        // 12. Collapse whitespace
        return s.replace(/\s+/g, ' ').trim();
    }

    /**
     * Matches a single token against the normalized text.
     */
    function matchToken(token, text) {
        if (!token || !text) return false;

        // Direct substring match
        if (text.indexOf(token) !== -1) return true;

        // Match with/without "ال" prefix
        if (token.startsWith('ال') && token.length > 3) {
            const withoutAl = token.substring(2);
            if (text.indexOf(withoutAl) !== -1) return true;
        } else {
            const withAl = 'ال' + token;
            if (text.indexOf(withAl) !== -1) return true;
        }

        // Match with/without "و" prefix (conjunction)
        if (token.startsWith('و') && token.length > 4) {
            const withoutWaw = token.substring(1);
            if (text.indexOf(withoutWaw) !== -1) return true;
            if (withoutWaw.startsWith('ال') && withoutWaw.length > 3) {
                if (text.indexOf(withoutWaw.substring(2)) !== -1) return true;
            }
        }

        return false;
    }

    /**
     * Smart Select2 Matcher with Optgroup and Multi-Token support.
     */
    function arabicSelect2Matcher(params, data) {
        // If there are no search terms, return all of the data
        if (!params || !params.term || $.trim(params.term) === '') {
            return data;
        }

        // Do not display the item if there is no data object
        if (!data) {
            return null;
        }

        // Handle Optgroups recursively
        if (data.children && data.children.length > 0) {
            const matchGroup = $.extend(true, {}, data);
            matchGroup.children = [];

            for (let i = 0; i < data.children.length; i++) {
                const childMatch = arabicSelect2Matcher(params, data.children[i]);
                if (childMatch) {
                    matchGroup.children.push(childMatch);
                }
            }

            if (matchGroup.children.length > 0) {
                return matchGroup;
            }

            // Also check if the group label itself matches
            const normTerm = normalizeArabic(params.term);
            const normGroupText = normalizeArabic(data.text);
            if (normGroupText && normGroupText.indexOf(normTerm) !== -1) {
                return data;
            }

            return null;
        }

        // Leaf option matching
        const normTerm = normalizeArabic(params.term);
        const normText = normalizeArabic(data.text);

        if (!normTerm || !normText) {
            return null;
        }

        // Multi-Token Matching: Every token must match
        const tokens = normTerm.split(/\s+/).filter(Boolean);
        if (tokens.length === 0) return data;

        for (let j = 0; j < tokens.length; j++) {
            if (!matchToken(tokens[j], normText)) {
                return null;
            }
        }

        return data;
    }

    // Expose utilities on window object
    window.normalizeArabic = normalizeArabic;
    window.arabicSelect2Matcher = arabicSelect2Matcher;

    // Apply globally to Select2 defaults if jQuery and Select2 exist
    if (typeof $ !== 'undefined') {
        $(function() {
            if ($.fn && $.fn.select2) {
                $.fn.select2.defaults.set('matcher', arabicSelect2Matcher);
            }

            // DataTables custom Arabic search string type if DataTables is loaded
            if ($.fn && $.fn.dataTable && $.fn.dataTable.ext && $.fn.dataTable.ext.type) {
                $.fn.dataTable.ext.type.search.string = function(data) {
                    return !data ? '' : normalizeArabic(data);
                };
            }
        });
    }

})(window, typeof jQuery !== 'undefined' ? jQuery : undefined);
