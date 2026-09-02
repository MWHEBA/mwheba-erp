/**
 * MWHEBA ERP - Printing Pricing Master Engine (Enterprise ES6 Architecture)
 * Two-Tier Decoupled Pricing Engine: Pure Math Logic + Resilient UI Controller
 * Version: 2.1.8
 */

// ============================================================================
// 1. طبقة الحسابات الرياضية الصرفة (Pure Math Functions)
// ============================================================================
const PricingMath = {
  /**
   * تحويل وتطهير الأرقام العربية المشرقية والفواصل
   */
  parseSafeNumber(val, fallback = 0) {
    if (val === undefined || val === null || val === '') return fallback;
    if (typeof val === 'number') return isNaN(val) ? fallback : val;
    let s = String(val).trim();
    // تحويل الأرقام العربية ٠-٩ إلى 0-9
    s = s.replace(/[٠-٩]/g, d => '٠١٢٣٤٥٦٧٨٩'.indexOf(d));
    // تحويل الفواصل العربية والإنجليزية
    s = s.replace(/,/g, '.');
    const parsed = parseFloat(s);
    return isNaN(parsed) ? fallback : parsed;
  },

  /**
   * حساب استغلال الفرخ والمونتاج الهندسي مع خصم 2.0 سم (بنسة الماكينة 1.5 سم + طهارة المقص 0.5 سم)
   * وصمام أمان عند تجاوز مقاس المطبوع لمساحة الفرخ
   */
  calcImposition(sheetW, sheetH, openW, openH) {
    // خصم 1.5 سم للبنسة و 0.5 سم لطهارة المقص
    const netW = Math.max(0, sheetW - 2.0);
    const netH = Math.max(0, sheetH - 2.0);
    const safeW = Math.max(0.1, openW);
    const safeH = Math.max(0.1, openH);

    // الوضع الطبيعي
    const cutsNormalW = Math.floor(netW / safeW);
    const cutsNormalH = Math.floor(netH / safeH);
    const normalTotal = cutsNormalW * cutsNormalH;

    // وضع التدوير 90 درجة
    const cutsRotW = Math.floor(netW / safeH);
    const cutsRotH = Math.floor(netH / safeW);
    const rotTotal = cutsRotW * cutsRotH;

    const bestCuts = Math.max(normalTotal, rotTotal);
    const isOverflow = bestCuts <= 0;
    const isRotated = rotTotal > normalTotal;

    return {
      cutsPerSheet: isOverflow ? 0 : bestCuts,
      cutsW: isOverflow ? 0 : (isRotated ? cutsRotW : cutsNormalW),
      cutsH: isOverflow ? 0 : (isRotated ? cutsRotH : cutsNormalH),
      isRotated: isRotated,
      isOverflow: isOverflow
    };
  },

  /**
   * حساب الفروخ الصافية والفاقد وتجهيز الماكينة مع معالجة التصفير عند التجاوز
   */
  calcGrossSheets(qty, cutsPerSheet, wasteRate, minMakeReady = 20) {
    if (cutsPerSheet <= 0) {
      return {
        netSheets: 0,
        grossSheets: 0,
        wasteSheets: 0
      };
    }
    const safeCuts = Math.max(1, cutsPerSheet);
    const netSheets = Math.ceil(qty / safeCuts);
    let gross = Math.ceil(netSheets * (1 + wasteRate));
    if (gross - netSheets < minMakeReady) {
      gross = netSheets + minMakeReady;
    }
    return {
      netSheets: netSheets,
      grossSheets: gross,
      wasteSheets: gross - netSheets
    };
  },

  /**
   * حساب سماكة الكعب الفيزيائي بالمليمتر
   */
  calcSpineMm(pages, paperWeight, bindingType, isHardcover = false) {
    if (bindingType === 'staple' || bindingType === 'wire_o') {
      return 0.0;
    }
    const sheets = Math.ceil(pages / 2);
    let rawSpine = sheets * (paperWeight / 1000) * 1.15;
    if (isHardcover) {
      rawSpine += 4.0; // 4mm شاسيه كرتون وتجليد فاخر
    }
    return Math.round(rawSpine * 10) / 10;
  },

  /**
   * حساب الملازم
   */
  calcSignatures(pages, w, h) {
    const sigCapacity = (w <= 15.5 && h <= 22.0) ? 32 : 16;
    const totalSignatures = Math.max(1, Math.ceil(pages / sigCapacity));
    return {
      signaturesCount: totalSignatures,
      sigCapacity: sigCapacity
    };
  },

  /**
   * حساب السحبات وعدد التراج (ألف سحبة)
   */
  calcPullsAndTirage(grossSheets, sidesMultiplier = 1) {
    const pulls = Math.ceil(grossSheets * sidesMultiplier);
    const tirages = Math.max(1, Math.ceil(pulls / 1000));
    return {
      pulls: pulls,
      tirages: tirages
    };
  },

  /**
   * حساب السعر النهائي المحاسبي بهامش الربح مع حماية القسمة على صفر
   */
  calcFinalPrice(totalCost, profitMargin) {
    // حماية القسمة على صفر (حد أقصى 99%)
    const safeMargin = Math.min(0.99, Math.max(0, profitMargin));
    const rawPrice = totalCost / (1 - safeMargin);
    // جبر الإجمالي النهائي دائمًا للأعلى
    return Math.ceil(rawPrice);
  },

  /**
   * حساب الشرائح الكمية الصافية
   */
  calcPricingTiers(totalCost, qty, profitMargin, isDigital = false, fixedSetup = 335) {
    const safeQty = Math.max(1, qty);
    const safeMargin = Math.min(0.99, Math.max(0, profitMargin));
    
    const tier1Qty = safeQty;
    const tier2Qty = Math.round(safeQty * 2.5);
    const tier3Qty = Math.round(safeQty * 5);

    let t1Total, t2Total, t3Total;
    if (isDigital) {
      const unitVarCost = totalCost / safeQty;
      t1Total = Math.ceil((unitVarCost * tier1Qty) / (1 - safeMargin));
      t2Total = Math.ceil(((unitVarCost * 0.90) * tier2Qty) / (1 - safeMargin));
      t3Total = Math.ceil(((unitVarCost * 0.85) * tier3Qty) / (1 - safeMargin));
    } else {
      const variablePerUnit = Math.max(0, (totalCost - fixedSetup) / safeQty);
      t1Total = Math.ceil((fixedSetup + (variablePerUnit * tier1Qty)) / (1 - safeMargin));
      t2Total = Math.ceil((fixedSetup + (variablePerUnit * tier2Qty)) / (1 - safeMargin));
      t3Total = Math.ceil((fixedSetup + (variablePerUnit * tier3Qty)) / (1 - safeMargin));
    }

    return {
      t1: { qty: tier1Qty, total: t1Total, unit: t1Total / tier1Qty },
      t2: { qty: tier2Qty, total: t2Total, unit: t2Total / tier2Qty },
      t3: { qty: tier3Qty, total: t3Total, unit: t3Total / tier3Qty }
    };
  }
};

// ============================================================================
// 2. كتالوج القوالب السريعة (Presets Catalog)
// ============================================================================
const PRESETS_DATA = {
  business_card: {
    type: 'flyer', title: 'كروت شخصية', qty: 1000,
    size_keyword: 'كارت', orientation: 'landscape',
    w: 9, h: 5, paper: 'couche', weight: '350', sheet: '70x100',
    front_c: 4, back_c: 4, plates: 4, lam: 'matte_2_sides', finishing: 'spot_uv', die: 'straight_cut',
    inner_pages: 0, inner_paper: 'couche', inner_weight: '135', binding: 'none'
  },
  flyer_a5: {
    type: 'flyer', title: 'فلاير A5', qty: 5000,
    size_keyword: 'A5', orientation: 'portrait', is_closed: false, open_dir: 'right',
    w: 14.8, h: 21, paper: 'couche', weight: '150', sheet: '70x100',
    front_c: 4, back_c: 4, plates: 4, lam: 'none', finishing: 'none', die: 'straight_cut',
    inner_pages: 0, inner_paper: 'couche', inner_weight: '135', binding: 'none'
  },
  brochure_trifold: {
    type: 'flyer', title: 'بروشور 3 بوابة', qty: 2500,
    size_keyword: 'بروشور', orientation: 'portrait', is_closed: true, open_dir: 'right',
    w: 21, h: 29.7, paper: 'couche', weight: '170', sheet: '70x100',
    front_c: 4, back_c: 4, plates: 4, lam: 'matte_2_sides', finishing: 'none', die: 'creasing_2',
    inner_pages: 0, inner_paper: 'couche', inner_weight: '135', binding: 'none'
  },
  folder_pocket: {
    type: 'folder', title: 'فولدر', qty: 1000,
    size_keyword: 'فولدر', orientation: 'portrait', is_closed: true, open_dir: 'right',
    w: 22, h: 31, paper: 'couche', weight: '350', sheet: '70x100',
    front_c: 4, back_c: 0, plates: 4, lam: 'matte_1_side', finishing: 'spot_uv', die: 'die_cut_custom',
    inner_pages: 4, inner_paper: 'couche', inner_weight: '350', binding: 'none'
  },
  catalog_64p: {
    type: 'catalog', title: 'كتالوج', qty: 1000,
    size_keyword: 'A4', orientation: 'portrait', is_closed: true, open_dir: 'right',
    w: 21, h: 29.7, paper: 'couche', weight: '300', sheet: '70x100',
    front_c: 4, back_c: 4, plates: 4, lam: 'matte_1_side', finishing: 'none', die: 'straight_cut',
    inner_pages: 32, inner_paper: 'couche', inner_weight: '135', binding: 'staple'
  },
  ncr_invoice: {
    type: 'invoice', title: 'دفاتر مكربن', qty: 50,
    size_keyword: 'A4', orientation: 'portrait', is_closed: false, open_dir: 'top',
    w: 21, h: 29.7, paper: 'woodfree', weight: '80', sheet: '70x100',
    front_c: 1, back_c: 0, plates: 1, lam: 'none', finishing: 'none', die: 'straight_cut',
    inner_pages: 50, inner_paper: 'woodfree', inner_weight: '80', binding: 'staple'
  },
  giveaways_pen_mug: {
    type: 'giveaways', title: 'هدايا دعائية و UV', qty: 100,
    size_keyword: 'custom', orientation: 'portrait', is_closed: false, open_dir: 'right',
    w: 10, h: 10, paper: 'couche', weight: '300', sheet: '70x100',
    front_c: 4, back_c: 0, plates: 0, lam: 'none', finishing: 'none', die: 'straight_cut',
    inner_pages: 0, inner_paper: 'couche', inner_weight: '300', binding: 'none'
  }
};

// ============================================================================
// 3. كلاس التحكم بالواجهة والأحداث (UI & Event Orchestrator)
// ============================================================================
class OrderFormUIController {
  constructor(config = {}) {
    this.config = Object.assign({
      currencySymbol: 'ج.م',
      urls: {
        pressesApi: '/api/printing/presses/',
        paperStocksApi: '/api/printing/paper-stocks/'
      },
      i18n: {
        pulls: 'سحبة',
        tirage: 'تراج',
        archivedPlates: 'زنكات موجودة مسبقاً',
        newPlates: 'زنكات جديدة',
        piece: 'قطعة',
        sheet: 'شيت',
        sqm: 'م²',
        signature: 'ملزمة',
        signaturesEq: 'يعادل',
        step2Cover: 'تفاصيل الغلاف الخارجي',
        step2Print: 'تفاصيل الطباعة',
        step2Folder: 'تفاصيل الفولدر والعلبة',
        step2Invoice: 'تفاصيل غلاف الدفاتر',
        step2Giveaways: 'تفاصيل الهدايا الدعائية',
        step3Inner: 'تفاصيل الداخلي والتجليد'
      }
    }, config);

    this.debounceTimer = null;
    this.isDirty = false;
    this.currentTrimSuggestion = null;
  }

  /**
   * تهيئة المنظومة
   */
  init() {
    this.initDefaultDate();
    this.initSelect2();
    this.bindDelegatedEvents();
    this.bindSupplierWatchers();
    this.bindPaperCardWatchers();
    this.bindKeyboardShortcuts();
    this.bindLifecycleGuards();
    
    // تشغيل الحالة الأولية
    const anatomySelect = document.getElementById('id_order_type') || document.getElementById('id_job_anatomy_type');
    if (anatomySelect) {
      const initOpt = anatomySelect.options[anatomySelect.selectedIndex];
      const initArchetype = initOpt?.dataset?.archetype || anatomySelect.value || 'flyer';
      this.handleAnatomySwitch(initArchetype);
    }
    this.applySelectedProductSize();
    this.updatePrintingTypeUI();
    this.updateResolvedPackCapacity(true);
    this.updateResolvedInnerPackCapacity(true);
    this.recalculate();
  }

  /**
   * التنسيق المالي مع مسافة BiDi غير قابلة للكسر
   */
  formatMoney(amount, forceDecimals = false) {
    if (amount === undefined || amount === null || isNaN(amount)) {
      return `0\u00A0${this.config.currencySymbol}`;
    }
    const num = Number(amount);
    const hasDecimals = (num % 1 !== 0) || forceDecimals;
    const formatted = num.toLocaleString('en-US', {
      minimumFractionDigits: hasDecimals ? 2 : 0,
      maximumFractionDigits: 2
    });
    return `${formatted}\u00A0${this.config.currencySymbol}`;
  }

  /**
   * تاريخ اليوم الافتراضي
   */
  initDefaultDate() {
    const orderDateInput = document.getElementById('id_order_date');
    if (orderDateInput && !orderDateInput.value) {
      orderDateInput.value = new Date().toISOString().split('T')[0];
    }
  }

  /**
   * تهيئة Select2
   */
  initSelect2() {
    if (typeof $.fn !== 'undefined' && typeof $.fn.select2 !== 'undefined') {
      $('.select2-filter').select2({
        width: '100%',
        dir: 'rtl',
        language: 'ar'
      });

      // إعادة تهيئة القوائم عند فتح الأكورديون
      $(document).on('shown.bs.collapse', '.collapse', function () {
        $(this).find('.select2-filter').each(function () {
          if ($(this).data('select2')) {
            $(this).select2('destroy');
          }
          $(this).select2({ width: '100%', dir: 'rtl', language: 'ar' });
        });
      });
    }
  }

  /**
   * ربط كافة الأحداث عبر Document-Level Event Delegation
   */
  bindDelegatedEvents() {
    const self = this;

    // 1. مراقبة تغيير نوع المطبوع
    $(document).on('change select2:select', '#id_order_type, #id_job_anatomy_type', function () {
      const selectEl = this;
      const archetype = selectEl.options[selectEl.selectedIndex]?.dataset?.archetype || selectEl.value;
      self.handleAnatomySwitch(archetype);
      self.debouncedRecalculate();
    });

    // 2. مراقبة مقاس المطبوع
    $(document).on('change select2:select', '#id_product_size', function () {
      self.applySelectedProductSize();
      self.debouncedRecalculate();
    });

    // 3. مراقبة العميل وتصنيف B2B
    $(document).on('change select2:select', '#id_customer', function () {
      const selected = this.options[this.selectedIndex];
      const badge = document.getElementById('customer_badge_info');
      const phone = document.getElementById('cust_phone_text');
      const tierBadge = document.getElementById('cust_tier_badge');

      if (selected && selected.value) {
        if (badge) badge.classList.remove('d-none');
        if (phone) phone.textContent = selected.dataset.phone || '';
        if (tierBadge) {
          const isB2b = selected.dataset.isB2b === 'true';
          tierBadge.textContent = isB2b ? 'وكالة / تاجر (B2B)' : 'عميل مباشر';
          tierBadge.className = isB2b
            ? 'badge bg-primary-subtle text-primary border border-primary-subtle me-1'
            : 'badge bg-light text-dark border me-1';
        }
      } else {
        if (badge) badge.classList.add('d-none');
      }
      self.debouncedRecalculate();
    });

    // 4. أزرار القوالب السريعة
    $(document).on('click', '.preset-btn', function () {
      const presetKey = this.dataset.preset;
      self.applyPreset(presetKey);
    });

    // 5. اتجاه الطباعة والمقاس المقفول وجهة الفتح
    $(document).on('change', 'input[name="print_orientation"]', function () {
      const sizeSelect = document.getElementById('id_product_size');
      const widthInput = document.getElementById('id_width');
      const heightInput = document.getElementById('id_height');

      if (sizeSelect && sizeSelect.value !== 'custom') {
        self.applySelectedProductSize();
      } else {
        if (widthInput && heightInput) {
          const oldW = widthInput.value;
          const oldH = heightInput.value;
          widthInput.value = oldH;
          heightInput.value = oldW;
        }
        self.updateOpenDimensionsDisplay();
        self.debouncedRecalculate();
      }
    });

    $(document).on('change', '#id_is_closed_size', function () {
      this.dataset.manual = '1';
      self.updateOpenDimensionsDisplay();
      self.debouncedRecalculate();
    });

    $(document).on('change', 'input[name="open_direction"]', function () {
      self.updateOpenDimensionsDisplay();
      self.debouncedRecalculate();
    });

    // 6. مدخلات الأبعاد المخصصة والكشف التلقائي عن الاتجاه
    $(document).on('input', '#id_width, #id_height, #id_custom_size_width, #id_custom_size_height', function () {
      const widthEl = document.getElementById('id_width');
      const heightEl = document.getElementById('id_height');
      const sizeSelect = document.getElementById('id_product_size');

      if (sizeSelect && sizeSelect.value === 'custom') {
        const w = PricingMath.parseSafeNumber(widthEl?.value);
        const h = PricingMath.parseSafeNumber(heightEl?.value);
        if (w > 0 && h > 0) {
          if (w > h) {
            const landRadio = document.getElementById('orient_landscape');
            if (landRadio && !landRadio.checked) landRadio.checked = true;
          } else if (h > w) {
            const portRadio = document.getElementById('orient_portrait');
            if (portRadio && !portRadio.checked) portRadio.checked = true;
          }
        }
      }
      self.updateOpenDimensionsDisplay();
      self.debouncedRecalculate();
    });

    // 7. مراقبة تغيير تقنيات الطباعة والأوجه والألوان
    $(document).on('change input', '#id_cover_printing_type, #id_inner_printing_type, #id_print_sides_mode_offset, #id_print_sides_mode_standard, #id_inner_print_sides_mode, #id_inner_color_mode, #id_inner_colors_single, #id_inner_spot_colors_single, #id_inner_spot_colors, #id_colors_front, #id_colors_back, #id_spot_colors_front, #id_spot_colors_back, #id_screen_colors_count, #id_digital_color_mode, #id_has_white_ink, #id_banner_sqm_price, #id_paper_type, #id_paper_weight, #id_inner_paper_type, #id_inner_paper_weight, #id_binding_type, #id_pages_count, #id_digital_inner_color_pages, #id_digital_inner_bw_pages, #id_color_signatures_count, #id_bw_signatures_count, #id_ncr_sets_count, #id_ncr_book_capacity, #id_ncr_serial_start, #id_lamination, #id_finishing, #id_die_cutting, #id_extra_cost, #id_quantity, #id_profit_margin, #id_giveaway_item_cost, #id_press_bed_size, #id_inner_press_bed_size', function () {
      self.isDirty = true;

      // المزامنة التبادلية للأوجه
      if (this.id === 'id_print_sides_mode_standard') {
        const offsetSel = document.getElementById('id_print_sides_mode_offset');
        if (offsetSel) offsetSel.value = this.value;
      } else if (this.id === 'id_print_sides_mode_offset') {
        const stdSel = document.getElementById('id_print_sides_mode_standard');
        if (stdSel) stdSel.value = this.value === 'work_sheet' ? 'double' : 'single';
      }

      // أسعار سلندر الزنك الافتراضية
      if (this.id === 'id_press_bed_size') {
        const bed = this.value;
        const platePriceInput = document.getElementById('id_plate_price');
        const pressRateInput = document.getElementById('id_press_rate');
        if (bed === '35x50') {
          if (platePriceInput && !platePriceInput.dataset.manual) platePriceInput.value = 60;
          if (pressRateInput && !pressRateInput.dataset.manual) pressRateInput.value = 35;
        } else if (bed === '50x70') {
          if (platePriceInput && !platePriceInput.dataset.manual) platePriceInput.value = 85;
          if (pressRateInput && !pressRateInput.dataset.manual) pressRateInput.value = 45;
        } else if (bed === '70x100') {
          if (platePriceInput && !platePriceInput.dataset.manual) platePriceInput.value = 150;
          if (pressRateInput && !pressRateInput.dataset.manual) pressRateInput.value = 65;
        }
      }

      self.updatePrintingTypeUI();
      self.updateOpenDimensionsDisplay();
      self.debouncedRecalculate();
    });

    // 8. زنكات CTP
    $(document).on('change', '#id_is_plates_archived', function () {
      self.updateCoverPlatesUI();
      self.debouncedRecalculate();
    });

    $(document).on('change', '#id_is_inner_plates_archived', function () {
      self.updateInnerPlatesUI();
      self.debouncedRecalculate();
    });

    $(document).on('input', '#id_plate_count_front, #id_plate_count_back, #id_plate_count, #id_inner_plates_count_total, #id_plate_price, #id_inner_plate_price, #id_press_rate, #id_inner_press_rate', function () {
      this.dataset.manual = "true";
      self.debouncedRecalculate();
    });

    // 9. AJAX الموردين والماكينات
    this.bindSupplierWatchers();

    // 10. زر النسخ السريع من الغلاف للداخلي
    $(document).on('click', '#btn_copy_cover_press_to_inner', function () {
      self.copyCoverPressToInner();
    });

    // 11. زر نسخ الواتساب
    $(document).on('click', '#btn_copy_whatsapp, #btn_copy_quote_whatsapp', function (e) {
      e.preventDefault();
      self.generateWhatsAppQuote();
    });

    // 12. زر مستشار تقليل الهدر
    $(document).on('click', '#btn_apply_trim_suggestion', function (e) {
      e.preventDefault();
      if (self.currentTrimSuggestion && typeof self.currentTrimSuggestion.action === 'function') {
        self.currentTrimSuggestion.action();
        self.showNotification('تم تطبيق المقترح الذكي وتقليل الهدر بنجاح! 🚀', 'success');
      }
    });

    // 13. زر الحفظ كمسودة
    $(document).on('click', '#btn_save_draft', function (e) {
      e.preventDefault();
      const form = document.getElementById('order-form');
      if (form) {
        let statusInput = document.getElementById('id_status');
        if (!statusInput) {
          statusInput = document.createElement('input');
          statusInput.type = 'hidden';
          statusInput.name = 'status';
          statusInput.id = 'id_status';
          form.appendChild(statusInput);
        }
        statusInput.value = 'draft';
        self.isDirty = false;
        form.submit();
      }
    });

    // 14. التحقق قبل إرسال النموذج وتوسيع الأكورديونات المطوية
    const form = document.getElementById('order-form');
    if (form) {
      form.addEventListener('submit', function (e) {
        self.sanitizePayloadOnSubmit();

        if (!form.checkValidity()) {
          e.preventDefault();
          e.stopPropagation();
          self.validateAndUnfoldCollapsedSections(form);
        } else {
          self.isDirty = false;
          // منع النقر المزدوج
          const submitBtn = document.getElementById('btn_save_order');
          if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>جاري الحفظ والتسجيل...';
          }
        }
        form.classList.add('was-validated');
      });
    }
  }

  /**
   * استدعاء الحسابات مع Debounce 20ms لمنع تداخل الحلقات المتسلسلة
   */
  debouncedRecalculate() {
    clearTimeout(this.debounceTimer);
    this.debounceTimer = setTimeout(() => {
      requestAnimationFrame(() => {
        this.recalculate();
      });
    }, 20);
  }

  /**
   * التبديل بين نماذج المطبوعات وعناوين الخطوات
   */
  handleAnatomySwitch(type) {
    const cardStep3 = document.getElementById('card_step3_inner');
    const cardStep4 = document.getElementById('card_step4_giveaways');
    const innerBook = document.getElementById('inner_book_section');
    const innerFolder = document.getElementById('inner_folder_section');
    const innerNcr = document.getElementById('inner_ncr_section');
    const closedContainer = document.getElementById('closed_size_container');
    const closedSwitch = document.getElementById('id_is_closed_size');

    // التحكم في ظهور سويتش المقاس المقفول
    if (['catalog', 'book', 'magazine', 'book_catalog', 'folder', 'folder_packaging', 'box', 'brochure'].includes(type)) {
      if (closedContainer) closedContainer.classList.remove('d-none');
      if (closedSwitch && !closedSwitch.dataset.manual) {
        closedSwitch.checked = true;
      }
    } else {
      if (closedContainer) closedContainer.classList.add('d-none');
      if (closedSwitch && !closedSwitch.dataset.manual) {
        closedSwitch.checked = false;
      }
    }

    const step3Header = document.getElementById('step3_header_title');
    if (step3Header) step3Header.textContent = `3. ${this.config.i18n.step3Inner}`;

    const headerTitle = document.getElementById('step2_header_title');

    if (type === 'flyer' || type === 'single_sheet' || type === 'brochure' || type === 'business_card') {
      if (cardStep3) cardStep3.classList.add('d-none');
      if (cardStep4) cardStep4.classList.add('d-none');
      if (headerTitle) headerTitle.textContent = `2. ${this.config.i18n.step2Print}`;
    } else if (type === 'catalog' || type === 'book' || type === 'magazine' || type === 'book_catalog') {
      if (cardStep3) cardStep3.classList.remove('d-none');
      if (cardStep4) cardStep4.classList.add('d-none');
      if (innerBook) innerBook.classList.remove('d-none');
      if (innerFolder) innerFolder.classList.add('d-none');
      if (innerNcr) innerNcr.classList.add('d-none');
      if (headerTitle) headerTitle.textContent = `2. ${this.config.i18n.step2Cover}`;
    } else if (type === 'folder' || type === 'box' || type === 'folder_packaging') {
      if (cardStep3) cardStep3.classList.remove('d-none');
      if (cardStep4) cardStep4.classList.add('d-none');
      if (innerBook) innerBook.classList.add('d-none');
      if (innerFolder) innerFolder.classList.remove('d-none');
      if (innerNcr) innerNcr.classList.add('d-none');
      if (headerTitle) headerTitle.textContent = `2. ${this.config.i18n.step2Folder}`;
    } else if (type === 'invoice' || type === 'receipt' || type === 'ncr') {
      if (cardStep3) cardStep3.classList.remove('d-none');
      if (cardStep4) cardStep4.classList.add('d-none');
      if (innerBook) innerBook.classList.add('d-none');
      if (innerFolder) innerFolder.classList.add('d-none');
      if (innerNcr) innerNcr.classList.remove('d-none');
      if (headerTitle) headerTitle.textContent = `2. ${this.config.i18n.step2Invoice}`;

      const innerPrintSelect = document.getElementById('id_inner_printing_type');
      if (innerPrintSelect) {
        innerPrintSelect.value = 'offset';
        $(innerPrintSelect).trigger('change');
      }
    } else if (type === 'giveaways' || type === 'gift' || type === 'promo') {
      if (cardStep3) cardStep3.classList.add('d-none');
      if (cardStep4) cardStep4.classList.remove('d-none');
      if (headerTitle) headerTitle.textContent = `2. ${this.config.i18n.step2Giveaways}`;
    }

    this.updatePrintingTypeUI();
    this.updateOpenDimensionsDisplay();
  }

  /**
   * تطبيق القوالب السريعة
   */
  applyPreset(presetKey) {
    const p = PRESETS_DATA[presetKey];
    if (!p) return;

    // مزامنة نوع المطبوع
    const anatomySelect = document.getElementById('id_order_type') || document.getElementById('id_job_anatomy_type');
    if (anatomySelect) {
      let matchedVal = null;
      for (let i = 0; i < anatomySelect.options.length; i++) {
        if (anatomySelect.options[i].dataset.archetype === p.type) {
          matchedVal = anatomySelect.options[i].value;
          break;
        }
      }
      if (matchedVal) {
        $(anatomySelect).val(matchedVal).trigger('change');
      } else {
        $(anatomySelect).val(p.type).trigger('change');
      }
      this.handleAnatomySwitch(p.type);
    }

    // مزامنة اتجاه الطباعة
    if (p.orientation === 'landscape') {
      const landRadio = document.getElementById('orient_landscape');
      if (landRadio) landRadio.checked = true;
    } else {
      const portRadio = document.getElementById('orient_portrait');
      if (portRadio) portRadio.checked = true;
    }

    // مزامنة المقاس المقفول وجهة الفتح
    const closedSwitch = document.getElementById('id_is_closed_size');
    if (closedSwitch && p.is_closed !== undefined) {
      closedSwitch.checked = p.is_closed;
    }
    if (p.open_dir) {
      const dirRadio = document.querySelector(`input[name="open_direction"][value="${p.open_dir}"]`);
      if (dirRadio) dirRadio.checked = true;
    }

    // مزامنة مقاس المطبوع
    const sizeSelect = document.getElementById('id_product_size');
    if (sizeSelect) {
      let matchedSizeVal = 'custom';
      for (let i = 0; i < sizeSelect.options.length; i++) {
        if (p.size_keyword && p.size_keyword !== 'custom' && sizeSelect.options[i].text.includes(p.size_keyword)) {
          matchedSizeVal = sizeSelect.options[i].value;
          break;
        }
      }
      $(sizeSelect).val(matchedSizeVal).trigger('change');
    }

    if (document.getElementById('id_title') && !document.getElementById('id_title').value) {
      document.getElementById('id_title').value = p.title;
    }
    if (document.getElementById('id_quantity')) document.getElementById('id_quantity').value = p.qty;
    if (document.getElementById('id_paper_type')) $(document.getElementById('id_paper_type')).val(p.paper).trigger('change');
    if (document.getElementById('id_paper_weight')) document.getElementById('id_paper_weight').value = p.weight;
    if (document.getElementById('id_colors_front')) document.getElementById('id_colors_front').value = p.front_c;
    if (document.getElementById('id_colors_back')) document.getElementById('id_colors_back').value = p.back_c;
    if (document.getElementById('id_plate_count')) document.getElementById('id_plate_count').value = p.plates;
    if (document.getElementById('id_lamination')) $(document.getElementById('id_lamination')).val(p.lam).trigger('change');
    if (document.getElementById('id_finishing')) $(document.getElementById('id_finishing')).val(p.finishing).trigger('change');
    if (document.getElementById('id_die_cutting')) $(document.getElementById('id_die_cutting')).val(p.die).trigger('change');
    if (document.getElementById('id_pages_count')) document.getElementById('id_pages_count').value = p.inner_pages;
    if (document.getElementById('id_binding_type')) $(document.getElementById('id_binding_type')).val(p.binding).trigger('change');

    this.applySelectedProductSize();
    this.debouncedRecalculate();
  }

  /**
   * تطبيق مقاس المطبوع المختار والقفل الذكي
   */
  applySelectedProductSize() {
    const sizeSelect = document.getElementById('id_product_size');
    if (!sizeSelect) return;

    const widthInput = document.getElementById('id_width');
    const heightInput = document.getElementById('id_height');
    const selectedOpt = sizeSelect.options[sizeSelect.selectedIndex];
    const isCustom = !selectedOpt || selectedOpt.value === 'custom';
    const isLandscape = document.getElementById('orient_landscape')?.checked || false;

    if (isCustom) {
      if (widthInput) {
        widthInput.readOnly = false;
        widthInput.style.backgroundColor = 'var(--bg-card, #ffffff)';
        widthInput.style.cursor = 'text';
      }
      if (heightInput) {
        heightInput.readOnly = false;
        heightInput.style.backgroundColor = 'var(--bg-card, #ffffff)';
        heightInput.style.cursor = 'text';
      }
    } else {
      const rawW = PricingMath.parseSafeNumber(selectedOpt.dataset.width, 21);
      const rawH = PricingMath.parseSafeNumber(selectedOpt.dataset.height, 29.7);

      let finalW = isLandscape ? Math.max(rawW, rawH) : Math.min(rawW, rawH);
      let finalH = isLandscape ? Math.min(rawW, rawH) : Math.max(rawW, rawH);

      if (widthInput) {
        widthInput.value = finalW;
        widthInput.readOnly = true;
        widthInput.style.backgroundColor = 'var(--bg-light, #f8f9fa)';
        widthInput.style.cursor = 'not-allowed';
      }
      if (heightInput) {
        heightInput.value = finalH;
        heightInput.readOnly = true;
        heightInput.style.backgroundColor = 'var(--bg-light, #f8f9fa)';
        heightInput.style.cursor = 'not-allowed';
      }
    }
    this.updateOpenDimensionsDisplay();
  }

  /**
   * تحديث الأبعاد المفتوحة وعرض الكعب وحاسبة NCR
   */
  updateOpenDimensionsDisplay() {
    const isClosed = document.getElementById('id_is_closed_size')?.checked || false;
    const w = PricingMath.parseSafeNumber(document.getElementById('id_width')?.value, 21);
    const h = PricingMath.parseSafeNumber(document.getElementById('id_height')?.value, 29.7);
    const selectEl = document.getElementById('id_order_type') || document.getElementById('id_job_anatomy_type');
    const type = selectEl?.options[selectEl.selectedIndex]?.dataset?.archetype || selectEl?.value || 'flyer';
    const openDir = document.querySelector('input[name="open_direction"]:checked')?.value || 'right';

    // تغيير مسميات الحقول
    const labelW = document.getElementById('label_width');
    const labelH = document.getElementById('label_height');
    if (labelW) labelW.textContent = isClosed ? 'العرض المقفول (سم)' : 'العرض (سم)';
    if (labelH) labelH.textContent = isClosed ? 'الارتفاع المقفول (سم)' : 'الارتفاع (سم)';

    let multiplier = (type === 'brochure' || type === 'brochures') ? 3 : 2;
    let spineMm = 0;
    const bindingType = document.getElementById('id_binding_type')?.value || 'staple';
    const isHardcover = bindingType === 'hardcover';

    if (['catalog', 'book', 'magazine', 'book_catalog'].includes(type)) {
      const pages = PricingMath.parseSafeNumber(document.getElementById('id_pages_count')?.value, 32);
      const innerSides = document.getElementById('id_inner_print_sides_mode')?.value || 'work_sheet';
      const innerPaperWeight = PricingMath.parseSafeNumber(document.getElementById('id_inner_paper_weight')?.value, 135);

      const sigInfo = PricingMath.calcSignatures(pages, w, h);
      const sigHint = document.getElementById('signatures_count_hint');
      if (sigHint) {
        if (innerSides === 'single') {
          sigHint.textContent = `${pages} ورقة وجه واحد (بلوك)`;
        } else {
          sigHint.textContent = `${this.config.i18n.signaturesEq} ${sigInfo.signaturesCount} ${this.config.i18n.signature} (${sigInfo.sigCapacity} صفحة/ملزمة)`;
        }
      }

      spineMm = PricingMath.calcSpineMm(pages, innerPaperWeight, bindingType, isHardcover);
      const spineDisplay = document.getElementById('spine_thickness_display');
      if (spineDisplay) spineDisplay.textContent = `${spineMm.toFixed(1)} مم`;

      // صمامات الأمان للتجليد
      const warnBox = document.getElementById('binding_feasibility_warning');
      const warnText = document.getElementById('binding_warning_text');
      if (warnBox && warnText) {
        if (bindingType === 'staple' && pages % 4 !== 0) {
          warnBox.classList.remove('d-none');
          warnText.textContent = 'تنبيه: عدد الصفحات يجب أن يقبل القسمة على 4 في التجليد الدبوس لضمان طي الملازم.';
        } else if (bindingType === 'staple' && pages > 64 && innerPaperWeight >= 135) {
          warnBox.classList.remove('d-none');
          warnText.textContent = 'تنبيه: عدد الصفحات كبير للتجليد الدبوس، يُنصح باختيار غراء حراري PUR لمنع نفخ الكتالوج.';
        } else if (bindingType === 'perfect_binding' && spineMm < 3.0) {
          warnBox.classList.remove('d-none');
          warnText.textContent = 'تنبيه: سمك الكعب أقل من 3 مم، يُفضل اختيار دبوس فرنسي سرج لضمان تماسك الصفحات.';
        } else {
          warnBox.classList.add('d-none');
        }
      }
    }

    // حساب مقاس الغلاف المفتوح
    let openW = w;
    let openH = h;
    if (isClosed) {
      if (openDir === 'top') {
        openW = w;
        openH = (h * multiplier) + (spineMm / 10);
      } else {
        if (isHardcover) {
          openW = (w * 2) + (spineMm / 10) + 4.6;
          openH = h + 3.6;
        } else {
          openW = (w * multiplier) + (spineMm / 10);
          openH = h;
        }
      }
    }

    const openText = document.getElementById('open_dims_text');
    if (openText) {
      openText.textContent = `${openW.toFixed(1).replace(/\.0$/, '')} × ${openH.toFixed(1).replace(/\.0$/, '')} سم`;
    }

    // حساب نهاية ترقيم دفاتر NCR
    const ncrStart = PricingMath.parseSafeNumber(document.getElementById('id_ncr_serial_start')?.value, 1001);
    const ncrCap = PricingMath.parseSafeNumber(document.getElementById('id_ncr_book_capacity')?.value, 50);
    const orderQty = PricingMath.parseSafeNumber(document.getElementById('id_quantity')?.value, 1);
    const ncrEnd = ncrStart + (ncrCap * orderQty) - 1;
    const ncrEndDisplay = document.getElementById('ncr_serial_end_display');
    if (ncrEndDisplay) ncrEndDisplay.textContent = ncrEnd.toLocaleString('en-US');

    // تحذير مقاس شيت الديجيتال
    const digitalWarning = document.getElementById('digital_sheet_size_warning');
    const coverType = document.getElementById('id_cover_printing_type')?.value || 'offset';
    if (digitalWarning) {
      digitalWarning.classList.toggle('d-none', !(openW > 48.7 && coverType === 'digital'));
    }
  }

  /**
   * التوزيع الشبكي المتناسق والصمامات الذكية
   */
  updatePrintingTypeUI() {
    const coverType = document.getElementById('id_cover_printing_type')?.value || 'offset';
    const innerType = document.getElementById('id_inner_printing_type')?.value || 'offset';
    const offsetSides = document.getElementById('id_print_sides_mode_offset')?.value || 'single';
    const paperType = document.getElementById('id_paper_type')?.value || 'couche';
    const paperWeight = PricingMath.parseSafeNumber(document.getElementById('id_paper_weight')?.value, 300);
    const qty = PricingMath.parseSafeNumber(document.getElementById('id_quantity')?.value, 1000);

    const containerOffsetSides = document.getElementById('container_offset_sides');
    const containerStdSides = document.getElementById('container_standard_sides');
    if (containerOffsetSides) containerOffsetSides.classList.toggle('d-none', coverType !== 'offset');
    if (containerStdSides) containerStdSides.classList.toggle('d-none', coverType === 'offset' || coverType === 'none');

    // التوزيع الشبكي 3+3+3+3=12 vs 3+3+6=12
    const colCoverType = document.getElementById('col_cover_type_wrapper');
    const colSides = document.getElementById('col_print_sides_wrapper');
    const colFrontColors = document.getElementById('col_front_colors_wrapper');
    const colBackColors = document.getElementById('col_back_colors_or_sqm_wrapper');

    const contOffsetFront = document.getElementById('container_offset_front_colors');
    const contDigitalColor = document.getElementById('container_digital_color_mode');
    const contBannerColor = document.getElementById('container_banner_color_mode');
    const contScreenColor = document.getElementById('container_screen_colors');
    const contOffsetBack = document.getElementById('container_offset_back_colors');
    const contBannerSqm = document.getElementById('container_banner_sqm_input');

    const labelFront = document.getElementById('label_front_colors');
    const labelBack = document.getElementById('label_back_colors');

    if (coverType === 'none') {
      if (colCoverType) colCoverType.className = 'col-md-12';
      if (colSides) colSides.classList.add('d-none');
      if (colFrontColors) colFrontColors.classList.add('d-none');
      if (colBackColors) colBackColors.classList.add('d-none');
    } else if (coverType === 'digital_banner') {
      if (colCoverType) colCoverType.className = 'col-md-3';
      if (colSides) { colSides.className = 'col-md-3'; colSides.classList.remove('d-none'); }
      if (colFrontColors) { colFrontColors.className = 'col-md-3'; colFrontColors.classList.remove('d-none'); }
      if (colBackColors) { colBackColors.className = 'col-md-3'; colBackColors.classList.remove('d-none'); }

      if (contOffsetFront) contOffsetFront.classList.add('d-none');
      if (contDigitalColor) contDigitalColor.classList.add('d-none');
      if (contBannerColor) contBannerColor.classList.remove('d-none');
      if (contScreenColor) contScreenColor.classList.add('d-none');
      if (contOffsetBack) contOffsetBack.classList.add('d-none');
      if (contBannerSqm) contBannerSqm.classList.remove('d-none');
    } else if (coverType === 'offset') {
      if (offsetSides === 'work_sheet') {
        if (colCoverType) colCoverType.className = 'col-md-3';
        if (colSides) { colSides.className = 'col-md-3'; colSides.classList.remove('d-none'); }
        if (colFrontColors) { colFrontColors.className = 'col-md-3'; colFrontColors.classList.remove('d-none'); }
        if (colBackColors) { colBackColors.className = 'col-md-3'; colBackColors.classList.remove('d-none'); }

        if (contOffsetFront) contOffsetFront.classList.remove('d-none');
        if (contDigitalColor) contDigitalColor.classList.add('d-none');
        if (contBannerColor) contBannerColor.classList.add('d-none');
        if (contScreenColor) contScreenColor.classList.add('d-none');
        if (contOffsetBack) contOffsetBack.classList.remove('d-none');
        if (contBannerSqm) contBannerSqm.classList.add('d-none');

        if (labelFront) labelFront.textContent = 'ألوان الوجه';
        if (labelBack) labelBack.textContent = 'ألوان الظهر';
      } else {
        if (colCoverType) colCoverType.className = 'col-md-3';
        if (colSides) { colSides.className = 'col-md-3'; colSides.classList.remove('d-none'); }
        if (colFrontColors) { colFrontColors.className = 'col-md-6'; colFrontColors.classList.remove('d-none'); }
        if (colBackColors) colBackColors.classList.add('d-none');

        if (contOffsetFront) contOffsetFront.classList.remove('d-none');
        if (contDigitalColor) contDigitalColor.classList.add('d-none');
        if (contBannerColor) contBannerColor.classList.add('d-none');
        if (contScreenColor) contScreenColor.classList.add('d-none');
        if (contOffsetBack) contOffsetBack.classList.add('d-none');
        if (contBannerSqm) contBannerSqm.classList.add('d-none');

        if (labelFront) labelFront.textContent = 'ألوان التصميم';
      }
    } else {
      if (colCoverType) colCoverType.className = 'col-md-3';
      if (colSides) { colSides.className = 'col-md-3'; colSides.classList.remove('d-none'); }
      if (colFrontColors) { colFrontColors.className = 'col-md-6'; colFrontColors.classList.remove('d-none'); }
      if (colBackColors) colBackColors.classList.add('d-none');

      if (contOffsetFront) contOffsetFront.classList.add('d-none');
      if (contDigitalColor) contDigitalColor.classList.toggle('d-none', coverType !== 'digital');
      if (contBannerColor) contBannerColor.classList.add('d-none');
      if (contScreenColor) contScreenColor.classList.toggle('d-none', coverType !== 'screen');
      if (contOffsetBack) contOffsetBack.classList.add('d-none');
      if (contBannerSqm) contBannerSqm.classList.add('d-none');
    }

    // كروت تفاصيل الماكينات
    const coverOffsetFields = document.getElementById('cover_offset_fields');
    const coverDigitalFields = document.getElementById('cover_digital_fields');
    const coverBannerFields = document.getElementById('cover_banner_fields');
    const coverScreenFields = document.getElementById('cover_screen_fields');

    if (coverOffsetFields) coverOffsetFields.classList.toggle('d-none', coverType !== 'offset');
    if (coverDigitalFields) coverDigitalFields.classList.toggle('d-none', coverType !== 'digital');
    if (coverBannerFields) coverBannerFields.classList.toggle('d-none', coverType !== 'digital_banner');
    if (coverScreenFields) coverScreenFields.classList.toggle('d-none', coverType !== 'screen');

    // الصمامات الذكية الأربعة
    const isSticker = paperType === 'sticker' || paperType === 'vinyl_adhesive';
    const stickerBadge = document.getElementById('sticker_guard_badge');
    if (stickerBadge) stickerBadge.classList.toggle('d-none', !isSticker);

    const isDuplex = paperType === 'duplex';
    const duplexWarning = document.getElementById('duplex_greyback_warning');
    if (duplexWarning) duplexWarning.classList.toggle('d-none', !isDuplex);

    const gsmWarning = document.getElementById('digital_gsm_warning');
    if (gsmWarning) gsmWarning.classList.toggle('d-none', !(coverType === 'digital' && paperWeight > 350));

    const microWarning = document.getElementById('micro_qty_offset_warning');
    if (microWarning) microWarning.classList.toggle('d-none', !(coverType === 'offset' && qty <= 300));

    // حقول الداخلي
    const innerSides = document.getElementById('id_inner_print_sides_mode')?.value || 'work_sheet';
    const contInnerOffset = document.getElementById('container_inner_color_mode_offset');
    const contInnerSingle = document.getElementById('container_inner_color_mode_single');
    const contInnerDigital = document.getElementById('container_inner_color_mode_digital');
    const innerOffsetFields = document.getElementById('inner_offset_fields');

    if (innerType === 'offset') {
      if (contInnerDigital) contInnerDigital.classList.add('d-none');
      if (innerSides === 'single') {
        if (contInnerSingle) contInnerSingle.classList.remove('d-none');
        if (contInnerOffset) contInnerOffset.classList.add('d-none');
        if (innerOffsetFields) innerOffsetFields.classList.add('d-none');
      } else {
        if (contInnerSingle) contInnerSingle.classList.add('d-none');
        if (contInnerOffset) contInnerOffset.classList.remove('d-none');
        const innerColorMode = document.getElementById('id_inner_color_mode')?.value || 'all_color';
        if (innerOffsetFields) innerOffsetFields.classList.toggle('d-none', innerColorMode !== 'mixed');
      }
    } else if (innerType === 'digital') {
      if (contInnerSingle) contInnerSingle.classList.add('d-none');
      if (contInnerOffset) contInnerOffset.classList.add('d-none');
      if (contInnerDigital) contInnerDigital.classList.remove('d-none');
      if (innerOffsetFields) innerOffsetFields.classList.add('d-none');
    }
  }

  /**
   * زنكات CTP للغلاف
   */
  updateCoverPlatesUI() {
    const coverPrintingType = document.getElementById('id_cover_printing_type')?.value || 'offset';
    const offsetSides = document.getElementById('id_print_sides_mode_offset')?.value || 'single';
    const archivedCheckbox = document.getElementById('id_is_plates_archived');
    const isArchived = archivedCheckbox ? archivedCheckbox.checked : (document.getElementById('id_plates_option')?.value === 'archived');
    
    const platesOptionInput = document.getElementById('id_plates_option');
    if (platesOptionInput) platesOptionInput.value = isArchived ? 'archived' : 'new';

    const frontColorsInput = document.getElementById('id_colors_front');
    const spotFrontInput = document.getElementById('id_spot_colors_front');
    const backColorsInput = document.getElementById('id_colors_back');
    const spotBackInput = document.getElementById('id_spot_colors_back');

    let frontColors = PricingMath.parseSafeNumber(frontColorsInput?.value, 4);
    let spotFront = PricingMath.parseSafeNumber(spotFrontInput?.value, 0);
    let backColors = 0;
    let spotBack = 0;

    const plateFrontInput = document.getElementById('id_plate_count_front');
    const plateBackInput = document.getElementById('id_plate_count_back');
    const plateTotalInput = document.getElementById('id_plate_count');
    const platePriceInput = document.getElementById('id_plate_price');
    const ctpCostDisplay = document.getElementById('cover_ctp_cost_display');
    const ctpBadge = document.getElementById('cover_ctp_summary_badge');

    if (offsetSides === 'work_sheet') {
      backColors = PricingMath.parseSafeNumber(backColorsInput?.value, 4);
      spotBack = PricingMath.parseSafeNumber(spotBackInput?.value, 0);
      if (plateBackInput) {
        plateBackInput.disabled = false;
        if (!plateBackInput.dataset.manual) plateBackInput.value = (backColors + spotBack);
      }
    } else {
      if (plateBackInput) {
        plateBackInput.value = 0;
        plateBackInput.disabled = true;
      }
    }

    const calculatedFront = frontColors + spotFront;
    if (plateFrontInput && !plateFrontInput.dataset.manual) {
      plateFrontInput.value = calculatedFront;
    }

    const curFront = PricingMath.parseSafeNumber(plateFrontInput?.value, calculatedFront);
    const curBack = PricingMath.parseSafeNumber(plateBackInput?.value, (offsetSides === 'work_sheet' ? (backColors + spotBack) : 0));
    const totalPlates = curFront + curBack;

    if (plateTotalInput && !plateTotalInput.dataset.manual) {
      plateTotalInput.value = totalPlates;
    }

    const actualPlates = PricingMath.parseSafeNumber(plateTotalInput?.value, totalPlates);
    const unitPrice = PricingMath.parseSafeNumber(platePriceInput?.value, 85);
    let totalCost = isArchived ? 0 : (actualPlates * unitPrice);

    if (coverPrintingType !== 'offset') {
      totalCost = 0;
    }

    if (ctpCostDisplay) ctpCostDisplay.textContent = this.formatMoney(totalCost);
    if (ctpBadge) {
      ctpBadge.textContent = isArchived ? `${this.config.i18n.archivedPlates} (0 ${this.config.currencySymbol})` : this.config.i18n.newPlates;
      ctpBadge.className = isArchived
        ? 'badge bg-secondary-subtle text-secondary border border-secondary-subtle px-2 py-1'
        : 'badge bg-primary-subtle text-primary border border-primary-subtle px-2 py-1';
    }

    return { totalPlates: actualPlates, totalCost: totalCost, isArchived: isArchived };
  }

  /**
   * زنكات CTP للداخلي
   */
  updateInnerPlatesUI() {
    const selectEl = document.getElementById('id_order_type') || document.getElementById('id_job_anatomy_type');
    const type = selectEl?.options[selectEl.selectedIndex]?.dataset?.archetype || selectEl?.value || 'flyer';
    const innerPrintingType = document.getElementById('id_inner_printing_type')?.value || 'offset';
    const innerSides = document.getElementById('id_inner_print_sides_mode')?.value || 'work_sheet';
    const innerArchivedCheckbox = document.getElementById('id_is_inner_plates_archived');
    const isArchived = innerArchivedCheckbox ? innerArchivedCheckbox.checked : (document.getElementById('id_inner_plates_option')?.value === 'archived');

    const innerPlatesOptionInput = document.getElementById('id_inner_plates_option');
    if (innerPlatesOptionInput) innerPlatesOptionInput.value = isArchived ? 'archived' : 'new';

    const spotColors = PricingMath.parseSafeNumber(document.getElementById('id_inner_spot_colors')?.value, 0);
    const innerPriceInput = document.getElementById('id_inner_plate_price');
    const innerTotalInput = document.getElementById('id_inner_plates_count_total');
    const innerCostDisplay = document.getElementById('inner_ctp_cost_display');
    const innerBadge = document.getElementById('inner_ctp_summary_badge');

    const w = PricingMath.parseSafeNumber(document.getElementById('id_width')?.value, 21);
    const h = PricingMath.parseSafeNumber(document.getElementById('id_height')?.value, 29.7);
    const pages = PricingMath.parseSafeNumber(document.getElementById('id_pages_count')?.value, 32);
    const totalSignatures = PricingMath.calcSignatures(pages, w, h).signaturesCount;

    let innerPlates = 0;
    if (['catalog', 'book', 'magazine', 'book_catalog'].includes(type)) {
      if (innerPrintingType === 'offset') {
        if (innerSides === 'single') {
          const singleColors = PricingMath.parseSafeNumber(document.getElementById('id_inner_colors_single')?.value, 4);
          innerPlates = singleColors + spotColors;
        } else {
          const innerColorMode = document.getElementById('id_inner_color_mode')?.value || 'all_color';
          let colorSigs = totalSignatures;
          let bwSigs = 0;
          if (innerColorMode === 'all_bw') {
            colorSigs = 0;
            bwSigs = totalSignatures;
          } else if (innerColorMode === 'mixed') {
            colorSigs = PricingMath.parseSafeNumber(document.getElementById('id_color_signatures_count')?.value, 0);
            bwSigs = PricingMath.parseSafeNumber(document.getElementById('id_bw_signatures_count')?.value, 0);
          }
          innerPlates = (colorSigs * 8) + (bwSigs * 2) + (spotColors * totalSignatures);
        }
      }
    } else if (type === 'invoice' || type === 'receipt' || type === 'ncr') {
      innerPlates = 2; // زنكة للأصل + زنكة للصور
    }

    if (innerTotalInput && !innerTotalInput.dataset.manual) {
      innerTotalInput.value = innerPlates;
    }

    const actualInnerPlates = PricingMath.parseSafeNumber(innerTotalInput?.value, innerPlates);
    const unitPrice = PricingMath.parseSafeNumber(innerPriceInput?.value, 85);
    let totalCost = isArchived ? 0 : (actualInnerPlates * unitPrice);

    if (innerPrintingType !== 'offset') {
      totalCost = 0;
    }

    if (innerCostDisplay) innerCostDisplay.textContent = this.formatMoney(totalCost);
    if (innerBadge) {
      innerBadge.textContent = isArchived ? `${this.config.i18n.archivedPlates} (0 ${this.config.currencySymbol})` : this.config.i18n.newPlates;
      innerBadge.className = isArchived
        ? 'badge bg-secondary-subtle text-secondary border border-secondary-subtle px-2 py-1'
        : 'badge bg-primary-subtle text-primary border border-primary-subtle px-2 py-1';
    }

    return { totalPlates: actualInnerPlates, totalCost: totalCost, isArchived: isArchived };
  }

  /**
   * ربط مراقبي الموردين والماكينات عبر AJAX مع الـ Fallbacks
   */
  bindSupplierWatchers() {
    const self = this;

    // مطبعة أوفست الغلاف
    $(document).on('change select2:select', '#id_cover_offset_supplier', function () {
      const supplierId = this.value;
      const machineSelect = $('#id_cover_press_machine');
      const pressRateInput = $('#id_press_rate');

      if (!supplierId) {
        machineSelect.html(`
          <option value="50x70" data-bed="50x70" data-rate="45" data-floor="200" selected>نصف فرخ 50×70 سم</option>
          <option value="70x100" data-bed="70x100" data-rate="65" data-floor="350">فرخ كامل 70×100 سم</option>
          <option value="35x50" data-bed="35x50" data-rate="35" data-floor="150">ربع فرخ 35×50 سم</option>
        `);
        pressRateInput.val(45);
        $('#id_press_bed_size').val('50x70').trigger('change');
        self.debouncedRecalculate();
      } else {
        $.getJSON(`${self.config.urls.pressesApi}?supplier_id=${supplierId}&order_type=offset`, function (data) {
          if (data && data.success && data.presses && data.presses.length > 0) {
            let optionsHtml = '';
            data.presses.forEach((p, idx) => {
              const isSel = idx === 0 ? 'selected' : '';
              const bedSize = p.bed_size || '50x70';
              optionsHtml += `<option value="${p.id}" data-bed="${bedSize}" data-rate="${p.price_per_1000}" data-floor="${p.setup_cost}" data-service-id="${p.service_id}" ${isSel}>${p.name}</option>`;
            });
            machineSelect.html(optionsHtml);
            const first = data.presses[0];
            pressRateInput.val(first.price_per_1000);
            $('#id_press_bed_size').val(first.bed_size || '50x70').trigger('change');
          }
          self.debouncedRecalculate();
        }).fail(() => {
          self.debouncedRecalculate();
        });
      }
    });

    // تغيير ماكينة أوفست الغلاف
    $(document).on('change', '#id_cover_press_machine', function () {
      const selectedOpt = $(this).find('option:selected');
      const optRate = selectedOpt.data('rate');
      const optBed = selectedOpt.data('bed');
      if (optRate !== undefined) $('#id_press_rate').val(optRate);
      if (optBed) $('#id_press_bed_size').val(optBed).trigger('change');
      self.debouncedRecalculate();
    });

    // مركز ديجيتال الغلاف
    $(document).on('change select2:select', '#id_cover_digital_supplier', function () {
      const supplierId = this.value;
      const machineSelect = $('#id_cover_digital_machine');
      const clickPriceInput = $('#id_digital_sheet_price');

      if (!supplierId) {
        machineSelect.html(`
          <option value="canon_c10000" data-price-color="2.50" data-price-bw="0.80" selected>Canon imagePRESS C10000</option>
          <option value="xerox_iridesse" data-price-color="3.00" data-price-bw="1.00">Xerox Iridesse Production Press</option>
          <option value="konica_accurio" data-price-color="2.25" data-price-bw="0.75">Konica Minolta AccurioPress</option>
        `);
        clickPriceInput.val(2.50);
        self.debouncedRecalculate();
      } else {
        $.getJSON(`${self.config.urls.pressesApi}?supplier_id=${supplierId}&order_type=digital`, function (data) {
          if (data && data.success && data.presses && data.presses.length > 0) {
            let optionsHtml = '';
            data.presses.forEach((p, idx) => {
              const isSel = idx === 0 ? 'selected' : '';
              optionsHtml += `<option value="${p.id}" data-price-color="${p.price_per_page_color}" data-price-bw="${p.price_per_page_bw}" data-service-id="${p.service_id}" ${isSel}>${p.name} (${self.formatMoney(p.price_per_page_color)})</option>`;
            });
            machineSelect.html(optionsHtml);
            const first = data.presses[0];
            clickPriceInput.val(first.price_per_page_color || 2.50);
          }
          self.debouncedRecalculate();
        }).fail(() => {
          self.debouncedRecalculate();
        });
      }
    });

    // مطبعة أوفست الداخلي
    $(document).on('change select2:select', '#id_inner_offset_supplier', function () {
      const supplierId = this.value;
      const machineSelect = $('#id_inner_press_machine');
      const pressRateInput = $('#id_inner_press_rate');

      if (!supplierId) {
        machineSelect.html(`
          <option value="50x70" data-bed="50x70" data-rate="45" data-floor="200" selected>نصف فرخ 50×70 سم</option>
          <option value="70x100" data-bed="70x100" data-rate="65" data-floor="350">فرخ كامل 70×100 سم</option>
          <option value="35x50" data-bed="35x50" data-rate="35" data-floor="150">ربع فرخ 35×50 سم</option>
        `);
        pressRateInput.val(45);
        $('#id_inner_press_bed_size').val('50x70').trigger('change');
        self.debouncedRecalculate();
      } else {
        $.getJSON(`${self.config.urls.pressesApi}?supplier_id=${supplierId}&order_type=offset`, function (data) {
          if (data && data.success && data.presses && data.presses.length > 0) {
            let optionsHtml = '';
            data.presses.forEach((p, idx) => {
              const isSel = idx === 0 ? 'selected' : '';
              const bedSize = p.bed_size || '50x70';
              optionsHtml += `<option value="${p.id}" data-bed="${bedSize}" data-rate="${p.price_per_1000}" data-floor="${p.setup_cost}" data-service-id="${p.service_id}" ${isSel}>${p.name}</option>`;
            });
            machineSelect.html(optionsHtml);
            const first = data.presses[0];
            pressRateInput.val(first.price_per_1000);
            $('#id_inner_press_bed_size').val(first.bed_size || '50x70').trigger('change');
          }
          self.debouncedRecalculate();
        }).fail(() => {
          self.debouncedRecalculate();
        });
      }
    });

    $(document).on('change', '#id_inner_press_machine', function () {
      const selectedOpt = $(this).find('option:selected');
      const optRate = selectedOpt.data('rate');
      const optBed = selectedOpt.data('bed');
      if (optRate !== undefined) $('#id_inner_press_rate').val(optRate);
      if (optBed) $('#id_inner_press_bed_size').val(optBed).trigger('change');
      self.debouncedRecalculate();
    });

    // سنترة خيارات القوائم المنسدلة عند فتح select2 للحقول المحددة بـ text-center
    $(document).on('select2:open', function (e) {
      if ($(e.target).hasClass('text-center')) {
        $('.select2-dropdown .select2-results__option').css({
          'text-align': 'center',
          'text-align-last': 'center'
        });
      }
    });
  }

  /**
   * ربط مراقبي كارت الورق المؤسسي ومحول الأسعار والمثلث الذهبي
   */
  bindPaperCardWatchers() {
    const self = this;

    // 1. اتجاه ألياف الورق (طولي LG / عرضي SG)
    $(document).on('click', '#btn_toggle_grain', function () {
      const current = $(this).attr('data-grain') || 'LG';
      const next = (current === 'LG') ? 'SG' : 'LG';
      $(this).attr('data-grain', next);
      $('#id_grain_direction').val(next);
      $('#grain_direction_label').text(next === 'LG' ? 'LG طولي' : 'SG عرضي');
      self.showNotification(`تم تبديل اتجاه ألياف الورق إلى: ${next === 'LG' ? 'طولي (Long Grain)' : 'عرضي (Short Grain)'}`, 'info');
    });

    // 2. مصدر الورق (شراء مباشر / من المخزن / توريد العميل)
    $(document).on('change', 'input[name="paper_source"]', function () {
      const source = this.value;
      const priceInput = $('#id_paper_sheet_price');
      if (source === 'customer_supplied') {
        priceInput.prop('disabled', true).addClass('bg-light text-muted');
        $('#paper_price_mode_label').text('خامة توريد العميل (0.00 ج)');
        self.showNotification('تم تحديد خامة توريد العميل: سيتم احتساب تكلفة الورق كـ 0.00 ج.م كشغل مصنعية مع استمرار حساب الأفرخ لإذن الاستلام', 'info');
      } else {
        priceInput.prop('disabled', false).removeClass('bg-light text-muted');
        $('#paper_price_mode_label').text('سعر شراء الفرخ');
      }
      self.debouncedRecalculate();
    });

    // 3. طريقة تسعير الورق ومحول الوحدات (بالفرخ / بالرزمة / بالطن)
    $(document).on('change', 'input[name="price_input_mode"]', function () {
      const mode = this.value;
      if (mode === 'sheet') {
        $('#input_wrapper_ream').addClass('d-none');
        $('#input_wrapper_ton').addClass('d-none');
      } else if (mode === 'ream') {
        $('#input_wrapper_ream').removeClass('d-none');
        $('#input_wrapper_ton').addClass('d-none');
      } else if (mode === 'ton') {
        $('#input_wrapper_ton').removeClass('d-none');
        $('#input_wrapper_ream').addClass('d-none');
      }
      self.updateConvertedSheetPrice();
    });

    // حساب السعر المحول لحظياً عند كتابة سعر الرزمة أو الطن بالعملة الوظيفية
    $(document).on('input', '#input_ream_price, #input_ton_price', function () {
      self.updateConvertedSheetPrice();
    });

    // تطبيق السعر المحول في حقل سعر الفرخ
    $(document).on('click', '#btn_apply_converted_price', function () {
      const converted = parseFloat($('#calc_converted_sheet_display').data('converted-price')) || 0;
      if (converted > 0) {
        $('#id_paper_sheet_price').val(converted.toFixed(2));
        $('#paper_unit_converter_collapse').collapse('hide');
        self.recalculate();
        self.showNotification(`تم تطبيق سعر الفرخ المحول: ${converted.toFixed(2)} ${self.config.currencySymbol}`, 'success');
      }
    });

    // 4. المثلث الذهبي الميكانيكي (المزامنة الثنائية بين تفصيل الفرخ والماكينة وزنك CTP)
    $(document).on('change', '#id_cover_press_machine', function () {
      const machineVal = $(this).val();
      const pieceSelect = $('#id_piece_size');
      if (machineVal === '50x70') {
        const opt = pieceSelect.find('option[data-cuts="2"]');
        if (opt.length) pieceSelect.val(opt.val()).trigger('change.select2');
      } else if (machineVal === '35x50') {
        const opt = pieceSelect.find('option[data-cuts="4"]');
        if (opt.length) pieceSelect.val(opt.val()).trigger('change.select2');
      } else if (machineVal === '70x100') {
        const opt = pieceSelect.find('option[data-cuts="1"]');
        if (opt.length) pieceSelect.val(opt.val()).trigger('change.select2');
      }
      self.debouncedRecalculate();
    });

    $(document).on('change', '#id_piece_size', function () {
      const selected = $(this).find('option:selected');
      const cuts = PricingMath.parseSafeNumber(selected.data('cuts'), 0);
      const machineSelect = $('#id_cover_press_machine');
      if (cuts === 2 && machineSelect.val() !== '50x70') {
        machineSelect.val('50x70').trigger('change.select2');
      } else if (cuts === 4 && machineSelect.val() !== '35x50') {
        machineSelect.val('35x50').trigger('change.select2');
      } else if (cuts === 1 && machineSelect.val() !== '70x100') {
        machineSelect.val('70x100').trigger('change.select2');
      }
      self.debouncedRecalculate();
    });

    // 5. سويتش تقريب الرزمة المقفولة
    $(document).on('change', '#id_ream_rounding_switch', function () {
      self.debouncedRecalculate();
    });

    // تحديث سعة الرزمة ديناميكياً عند تغيير نوع الورق أو الجراماج
    $(document).on('change', '#id_paper_type, #id_paper_weight', function () {
      self.updateResolvedPackCapacity(false);
      self.debouncedRecalculate();
    });

    // تحديث سعة رزمة الداخلي عند تغيير ورق أو جراماج الداخلي
    $(document).on('change', '#id_inner_paper_type, #id_inner_paper_weight', function () {
      self.updateResolvedInnerPackCapacity(false);
      self.debouncedRecalculate();
    });

    // صمام أمان الديجيتال: إطفاء سويتش التقريب تلقائياً في الطباعة الديجيتال
    $(document).on('change', '#id_cover_printing_type', function () {
      const pType = $(this).val();
      const reamSwitch = $('#id_ream_rounding_switch');
      if (pType === 'digital') {
        if (reamSwitch.is(':checked')) {
          reamSwitch.prop('checked', false);
          self.showNotification('تم إيقاف تقريب الرزم المقفولة تلقائياً لأن الطباعة ديجيتال لضمان عدالة التسعير', 'info');
        }
      } else if (pType === 'offset') {
        if (!reamSwitch.is(':checked')) {
          reamSwitch.prop('checked', true);
        }
      }
      self.debouncedRecalculate();
    });

    // 6. نسخ خامة ومورد الغلاف إلى الداخلي
    $(document).on('click', '#btn_copy_cover_paper_to_inner', function () {
      const coverSup = $('#id_paper_supplier').val();
      const coverType = $('#id_paper_type').val();
      const coverSheetSize = $('#id_sheet_size').val();
      const coverWeight = $('#id_paper_weight').val();
      const coverPrice = $('#id_paper_sheet_price').val();

      if (coverSup) $('#id_inner_paper_supplier').val(coverSup).trigger('change.select2');
      if (coverType) $('#id_inner_paper_type').val(coverType).trigger('change.select2');
      if (coverSheetSize) $('#id_inner_sheet_size').val(coverSheetSize).trigger('change.select2');
      if (coverWeight) $('#id_inner_paper_weight').val(coverWeight).trigger('change.select2');
      if (coverPrice) $('#id_inner_sheet_price').val(coverPrice);

      self.recalculate();
      self.showNotification('تم نسخ خامة ومقاس ومورد الغلاف إلى كارت الداخلي بنجاح', 'success');
    });

    // 7. زر اعتماد الشريحة الكمية في جدول الشرائح
    $(document).on('click', '.select-tier-btn', function () {
      const qty = $(this).data('qty');
      if (qty) {
        $('#id_quantity').val(qty);
        self.recalculate();
        self.showNotification(`تم اعتماد الكمية ${qty.toLocaleString()} قطعة بنجاح`, 'success');
      }
    });

    // 8. إعادة الحساب عند تغيير حقول كارت الورق
    $(document).on('change', '#id_paper_supplier, #id_paper_type, #id_sheet_size, #id_paper_weight, #id_paper_origin, #id_inner_paper_supplier, #id_inner_paper_type, #id_inner_sheet_size, #id_inner_paper_weight', function () {
      self.debouncedRecalculate();
    });
    $(document).on('input', '#id_paper_sheet_price, #id_inner_sheet_price', function () {
      self.debouncedRecalculate();
    });
  }

  /**
   * استنتاج وحسم سعة الرزمة المعتمدة ديناميكياً من الإعدادات
   */
  updateResolvedPackCapacity(isInitial = false) {
    const hiddenInput = $('#id_sheets_per_pack');
    const initialSavedVal = hiddenInput.data('initial');

    if (isInitial && initialSavedVal && PricingMath.parseSafeNumber(initialSavedVal, 0) > 0) {
      const savedCap = PricingMath.parseSafeNumber(initialSavedVal, 250);
      hiddenInput.val(savedCap);
      $('#val_sheets_per_pack').text(savedCap);
      $('#pack_addon_sheets').text(savedCap);
      this.updateConvertedSheetPrice();
      return;
    }

    const paperTypeOpt = $('#id_paper_type option:selected');
    const paperWeightOpt = $('#id_paper_weight option:selected');

    const overridePack = PricingMath.parseSafeNumber(paperTypeOpt.data('override-pack'), 0);
    const weightPack = PricingMath.parseSafeNumber(paperWeightOpt.data('sheets-per-pack'), 0);

    let resolvedCapacity = 250;
    if (overridePack > 0) {
      resolvedCapacity = overridePack;
    } else if (weightPack > 0) {
      resolvedCapacity = weightPack;
    }

    hiddenInput.val(resolvedCapacity);
    $('#val_sheets_per_pack').text(resolvedCapacity);
    $('#pack_addon_sheets').text(resolvedCapacity);
    this.updateConvertedSheetPrice();
  }

  /**
   * استنتاج وحسم سعة رزم ورق الداخلي ديناميكياً
   */
  updateResolvedInnerPackCapacity(isInitial = false) {
    const hiddenInput = $('#id_inner_sheets_per_pack');
    if (!hiddenInput.length) return;

    const paperTypeOpt = $('#id_inner_paper_type option:selected');
    const paperWeightOpt = $('#id_inner_paper_weight option:selected');

    const overridePack = PricingMath.parseSafeNumber(paperTypeOpt.data('override-pack'), 0);
    const weightPack = PricingMath.parseSafeNumber(paperWeightOpt.data('sheets-per-pack'), 0);

    let resolvedCapacity = 500;
    if (overridePack > 0) {
      resolvedCapacity = overridePack;
    } else if (weightPack > 0) {
      resolvedCapacity = weightPack;
    }

    hiddenInput.val(resolvedCapacity);
  }

  /**
   * حساب السعر المحول للفرخ من الرزمة أو الطن
   */
  updateConvertedSheetPrice() {
    const mode = $('input[name="price_input_mode"]:checked').val() || 'sheet';
    const display = $('#calc_converted_sheet_display');
    let converted = 0;

    if (mode === 'ream') {
      const reamPrice = parseFloat($('#input_ream_price').val()) || 0;
      const packCapacity = Math.max(1, PricingMath.parseSafeNumber($('#id_sheets_per_pack').val(), 250));
      converted = packCapacity > 0 ? (reamPrice / packCapacity) : 0;
    } else if (mode === 'ton') {
      const tonPrice = parseFloat($('#input_ton_price').val()) || 0;
      const sheetOpt = $('#id_sheet_size option:selected');
      const sw = PricingMath.parseSafeNumber(sheetOpt.data('width'), 100) / 100;
      const sh = PricingMath.parseSafeNumber(sheetOpt.data('height'), 70) / 100;
      const gsm = PricingMath.parseSafeNumber($('#id_paper_weight').val(), 300);
      const sheetWeightTon = (sw * sh * gsm) / 1000000;
      converted = tonPrice * sheetWeightTon;
    } else {
      converted = parseFloat($('#id_paper_sheet_price').val()) || 3.50;
    }

    display.data('converted-price', converted);
    display.text(`${converted.toFixed(2)} ${this.config.currencySymbol}`);
  }

  /**
   * النسخ السريع الآمن من الغلاف للداخلي
   */
  copyCoverPressToInner() {
    const coverSupplier = $('#id_cover_offset_supplier').val();
    const coverMachine = $('#id_cover_press_machine').val();
    const coverRate = $('#id_press_rate').val();
    const coverCtpSupp = $('#id_cover_ctp_supplier').val();
    const coverBed = $('#id_press_bed_size').val();
    const coverPlatePrice = $('#id_plate_price').val();

    if (coverSupplier) $('#id_inner_offset_supplier').val(coverSupplier).trigger('change');
    if (coverRate) $('#id_inner_press_rate').val(coverRate);
    if (coverCtpSupp) $('#id_inner_ctp_supplier').val(coverCtpSupp).trigger('change');
    if (coverBed) $('#id_inner_press_bed_size').val(coverBed);
    if (coverPlatePrice) $('#id_inner_plate_price').val(coverPlatePrice);

    this.debouncedRecalculate();
    this.showNotification('تم نسخ مطبعة ومقاس وإعدادات الغلاف إلى صفحات الداخلي بنجاح', 'success');
  }

  /**
   * المساعد الشامل لرسائل التنبيه والتوستر
   */
  showNotification(message, type = 'info') {
    if (typeof window.showNotification === 'function') {
      window.showNotification(message, type);
    } else if (typeof window.showToastr === 'function') {
      window.showToastr(message, type);
    } else if (typeof toastr !== 'undefined' && typeof toastr[type] === 'function') {
      toastr[type](message);
    } else {
      console.log(`[Notification ${type}]: ${message}`);
    }
  }

  /**
   * المحرك الحسابي الرئيسي الشامل (Master Recalculate Engine)
   */
  recalculate() {
    const qty = PricingMath.parseSafeNumber(document.getElementById('id_quantity')?.value, 1000);
    const selectEl = document.getElementById('id_order_type') || document.getElementById('id_job_anatomy_type');
    const type = selectEl?.options[selectEl.selectedIndex]?.dataset?.archetype || selectEl?.value || 'flyer';
    const openDir = document.querySelector('input[name="open_direction"]:checked')?.value || 'right';

    const isClosed = document.getElementById('id_is_closed_size')?.checked || false;
    const w = PricingMath.parseSafeNumber(document.getElementById('id_width')?.value, 21);
    const h = PricingMath.parseSafeNumber(document.getElementById('id_height')?.value, 29.7);

    let multiplier = (type === 'brochure' || type === 'brochures') ? 3 : 2;
    let spineMm = 0;
    const bindingType = document.getElementById('id_binding_type')?.value || 'staple';
    const isHardcover = bindingType === 'hardcover';
    const isWireO = bindingType === 'wire_o';
    const isPad = bindingType === 'pad_glue';
    const isStaple = bindingType === 'staple';

    const pages = PricingMath.parseSafeNumber(document.getElementById('id_pages_count')?.value, 32);
    const innerPaperType = document.getElementById('id_inner_paper_type')?.value || 'couche';
    const innerPaperWeight = PricingMath.parseSafeNumber(document.getElementById('id_inner_paper_weight')?.value, 135);
    const innerSides = document.getElementById('id_inner_print_sides_mode')?.value || 'work_sheet';
    const innerPrintingType = document.getElementById('id_inner_printing_type')?.value || 'offset';

    if (['catalog', 'book', 'magazine', 'book_catalog'].includes(type)) {
      spineMm = PricingMath.calcSpineMm(pages, innerPaperWeight, bindingType, isHardcover);
    }

    const spineDisplay = document.getElementById('spine_thickness_display');
    if (spineDisplay) spineDisplay.textContent = `${spineMm.toFixed(1)} مم`;

    // حساب المقاس المفتوح
    let openW = w;
    let openH = h;
    if (isClosed) {
      if (openDir === 'right' || openDir === 'left') {
        openW = (w * multiplier) + (spineMm / 10);
      } else {
        openH = (h * multiplier) + (spineMm / 10);
      }
    }

    // 1. حساب استهلاك الورق والمونتاج بديناميكية تامة
    const sheetOpt = $('#id_sheet_size option:selected');
    const sheetW = PricingMath.parseSafeNumber(sheetOpt.data('width'), 100.0);
    const sheetH = PricingMath.parseSafeNumber(sheetOpt.data('height'), 70.0);

    const imposition = PricingMath.calcImposition(sheetW, sheetH, openW, openH);

    // فحص صمام أمان تجاوز الأبعاد
    const overflowAlert = $('#dimension_overflow_alert');
    const submitBtn = $('#btn_submit_order');
    if (imposition.isOverflow) {
      overflowAlert.removeClass('d-none');
      $('#id_width, #id_height').addClass('is-invalid');
      if (submitBtn.length) submitBtn.prop('disabled', true);
    } else {
      overflowAlert.addClass('d-none');
      $('#id_width, #id_height').removeClass('is-invalid');
      if (submitBtn.length) submitBtn.prop('disabled', false);
    }

    const coverPrintingType = document.getElementById('id_cover_printing_type')?.value || 'offset';
    const offsetSides = document.getElementById('id_print_sides_mode_offset')?.value || 'single';
    const coverWasteRate = (coverPrintingType === 'digital') ? 0.03 : 0.08;
    const minMakeReady = (offsetSides === 'work_sheet') ? 40 : 20;

    const coverGrossCalc = PricingMath.calcGrossSheets(qty, imposition.cutsPerSheet, coverWasteRate, minMakeReady);
    
    // سويتش تقريب الرزمة المقفولة بحسب سعة الرزمة (100 إلى 500 فرخ)
    const isReamRounding = $('#id_ream_rounding_switch').is(':checked');
    const packCapacity = Math.max(1, PricingMath.parseSafeNumber($('#id_sheets_per_pack').val(), 250));
    let grossSheets = coverGrossCalc.grossSheets;
    let excessSheets = 0;
    if (isReamRounding && grossSheets > 0 && packCapacity > 0) {
      const roundedGross = Math.ceil(grossSheets / packCapacity) * packCapacity;
      excessSheets = roundedGross - grossSheets;
      grossSheets = roundedGross;
    }

    // قراءة معامل قطع تفصيل الفرخ للماكينة (PieceSize)
    const pieceOpt = $('#id_piece_size option:selected');
    let machineCuts = PricingMath.parseSafeNumber(pieceOpt.data('cuts'), 0);
    if (machineCuts <= 0) {
      const pressBed = $('#id_cover_press_machine').val();
      if (pressBed === '50x70') machineCuts = 2;
      else if (pressBed === '35x50') machineCuts = 4;
      else machineCuts = 1;
    }

    const paperType = document.getElementById('id_paper_type')?.value || 'couche';
    const paperTypeName = $('#id_paper_type option:selected').text() || 'كوشيه';
    const paperWeight = PricingMath.parseSafeNumber(document.getElementById('id_paper_weight')?.value, 300);

    // التحقق من خامة توريد العميل
    const isCustomerSupplied = $('input[name="paper_source"]:checked').val() === 'customer_supplied';
    const enteredPrice = PricingMath.parseSafeNumber($('#id_paper_sheet_price').val(), 3.50);
    const actualSheetPrice = isCustomerSupplied ? 0.00 : enteredPrice;
    const costCoverPaper = grossSheets * actualSheetPrice;

    // وزن الورق بالكيلوجرام
    const coverWeightKg = ((grossSheets * (sheetW / 100) * (sheetH / 100) * paperWeight) / 1000);

    // تحديث مؤشرات كارت الورق الحية
    const packsCount = packCapacity > 0 ? (grossSheets / packCapacity).toFixed(1) : 0;
    $('#display_cover_net_sheets').text(coverGrossCalc.netSheets.toLocaleString());
    $('#display_cover_waste_sheets').text(coverGrossCalc.wasteSheets.toLocaleString());
    $('#display_cover_gross_sheets').text(`${grossSheets.toLocaleString()} فرخ`);
    if (isCustomerSupplied) {
      $('#display_cover_reams_breakdown').text(`مطلوب من العميل: ${packsCount} رزمة (${packCapacity} فرخ)`);
    } else {
      $('#display_cover_reams_breakdown').text(`${packsCount} رزمة (${packCapacity} فرخ)`);
    }

    // إظهار فائض الرزمة المقفولة كرصيد للمخزن
    const excessBadge = $('#display_ream_excess_badge');
    if (excessSheets > 0 && isReamRounding) {
      excessBadge.text(`منها ${excessSheets.toLocaleString()} فرخ فائض رصيد للمخزن`).removeClass('d-none');
    } else {
      excessBadge.addClass('d-none');
    }

    $('#display_cover_weight_kg').text(`${coverWeightKg.toFixed(1)} كجم`);
    $('#cover_paper_cost_display').text(this.formatMoney(costCoverPaper));
    $('#badge_gross_sheets').text(grossSheets.toLocaleString());
    $('#badge_total_weight').text(coverWeightKg.toFixed(1));
    $('#badge_total_cost').text(this.formatMoney(costCoverPaper));
    $('#pieces_per_sheet_display').text(`${imposition.cutsPerSheet} قطع`);

    // صمامات الجودة الميدانية
    if (paperWeight > 170 && ['couche', 'كوشيه'].some(t => paperTypeName.toLowerCase().includes(t))) {
      $('#heavy_couche_creasing_alert').removeClass('d-none');
    } else {
      $('#heavy_couche_creasing_alert').addClass('d-none');
    }

    const coatingType = $('#id_lamination').val() || '';
    if (paperWeight < 200 && coatingType.includes('1_side')) {
      $('#single_lam_curl_warning').removeClass('d-none');
    } else {
      $('#single_lam_curl_warning').addClass('d-none');
    }

    let costInnerPaper = 0;
    let innerGrossSheets = 0;
    let innerWeightKg = 0;
    let totalSignatures = 1;

    if (['catalog', 'book', 'magazine', 'book_catalog'].includes(type)) {
      const sigInfo = PricingMath.calcSignatures(pages, w, h);
      totalSignatures = sigInfo.signaturesCount;
      const actualSheetsPerUnit = (innerSides === 'single') ? pages : Math.ceil(pages / 2);
      const innerLeafW = (innerSides === 'single') ? w : (w * 2);
      const innerLeafH = h;

      const innerSheetOpt = $('#id_inner_sheet_size option:selected');
      const innerSheetW = PricingMath.parseSafeNumber(innerSheetOpt.data('width'), 88.0);
      const innerSheetH = PricingMath.parseSafeNumber(innerSheetOpt.data('height'), 66.0);

      const innerImposition = PricingMath.calcImposition(innerSheetW, innerSheetH, innerLeafW, innerLeafH);
      const innerWasteRate = (innerPrintingType === 'digital') ? 0.03 : 0.08;
      const minInnerMakeReady = totalSignatures * 20;

      const innerGrossCalc = PricingMath.calcGrossSheets(qty * actualSheetsPerUnit, innerImposition.cutsPerSheet, innerWasteRate, minInnerMakeReady);
      innerGrossSheets = innerGrossCalc.grossSheets;

      const innerEnteredPrice = PricingMath.parseSafeNumber($('#id_inner_sheet_price').val(), 2.40);
      const innerSheetCost = isCustomerSupplied ? 0.00 : innerEnteredPrice;
      costInnerPaper += (innerGrossSheets * innerSheetCost);

      innerWeightKg = ((innerGrossSheets * (innerSheetW / 100) * (innerSheetH / 100) * innerPaperWeight) / 1000);

      if (isHardcover) {
        const cardboardSheets = Math.ceil(qty / 4) * 1.05;
        const endpaperSheets = Math.ceil(qty / 2) * 1.05;
        costInnerPaper += (cardboardSheets * 18.00) + (endpaperSheets * 1.80);
      }
      if (isPad) {
        const backingSheets = Math.ceil(qty / 8) * 1.05;
        costInnerPaper += (backingSheets * 8.00);
      }

      // تحديث مؤشرات كارت ورق الداخلي
      const innerPackCapacity = Math.max(1, PricingMath.parseSafeNumber($('#id_inner_sheets_per_pack').val(), 500));
      const innerPacksCount = (innerGrossSheets / innerPackCapacity).toFixed(1);
      $('#display_signatures_breakdown').text(`${totalSignatures} ملازم (${pages} صفحة)`);
      $('#display_inner_gross_sheets').text(`${innerGrossSheets.toLocaleString()} فرخ`);
      $('#display_inner_reams_breakdown').text(`${innerPacksCount} رزمة (${innerPackCapacity} فرخ)`);
      $('#display_inner_weight_kg').text(`${innerWeightKg.toFixed(1)} كجم`);
      $('#cost_inner_paper_display').text(this.formatMoney(costInnerPaper));
      $('#badge_inner_gross_sheets').text(innerGrossSheets.toLocaleString());
      $('#badge_inner_weight').text(innerWeightKg.toFixed(1));
      $('#badge_inner_cost').text(this.formatMoney(costInnerPaper));
    } else if (type === 'invoice' || type === 'receipt' || type === 'ncr') {
      const ncrSets = PricingMath.parseSafeNumber(document.getElementById('id_ncr_sets_count')?.value, 2);
      const ncrCap = PricingMath.parseSafeNumber(document.getElementById('id_ncr_book_capacity')?.value, 50);
      const totalSets = qty * ncrCap;
      const ncrCuts = Math.max(1, Math.floor(70 / w) * Math.floor(100 / h));
      const ncrReams = Math.ceil((totalSets * ncrSets) / (ncrCuts * 500)) * 1.05;
      const ncrReamPrice = isCustomerSupplied ? 0.00 : 450.00;
      costInnerPaper += (ncrReams * ncrReamPrice);
      const dividerSheets = Math.ceil(qty / 10) * 1.05;
      costInnerPaper += (dividerSheets * (isCustomerSupplied ? 0.00 : 12.00));
    }

    const costPaper = costCoverPaper + costInnerPaper;

    // تحديث أسطر مفتش التكاليف (Formula Inspector Modal)
    $('#insp_paper_desc').text(`${paperTypeName} ${paperWeight} جم (${sheetW}×${sheetH})`);
    $('#insp_paper_sheets').text(`${grossSheets.toLocaleString()} فرخ`);
    $('#insp_sheet_rate').text(`${actualSheetPrice.toFixed(2)} ${this.config.currencySymbol}`);
    $('#insp_paper_cost').text(this.formatMoney(costCoverPaper));

    if (innerGrossSheets > 0) {
      $('#insp_row_inner_paper').removeClass('d-none');
      const innerTypeTxt = $('#id_inner_paper_type option:selected').text() || 'داخلي';
      $('#insp_inner_paper_desc').text(`${innerTypeTxt} ${innerPaperWeight} جم`);
      $('#insp_inner_paper_sheets').text(`${innerGrossSheets.toLocaleString()} فرخ`);
      const innerPriceVal = isCustomerSupplied ? 0 : PricingMath.parseSafeNumber($('#id_inner_sheet_price').val(), 2.40);
      $('#insp_inner_sheet_rate').text(`${innerPriceVal.toFixed(2)} ${this.config.currencySymbol}`);
      $('#insp_inner_paper_cost').text(this.formatMoney(costInnerPaper));
    } else {
      $('#insp_row_inner_paper').addClass('d-none');
    }

    // 2. تكلفة الطباعة
    let costPrintingCover = 0;
    const coverPlatesResult = this.updateCoverPlatesUI();

    if (coverPrintingType === 'offset') {
      let backColors = 0;
      let spotBack = 0;
      if (offsetSides === 'work_sheet') {
        backColors = PricingMath.parseSafeNumber(document.getElementById('id_colors_back')?.value, 4);
        spotBack = PricingMath.parseSafeNumber(document.getElementById('id_spot_colors_back')?.value, 0);
      }
      const pressRate = PricingMath.parseSafeNumber(document.getElementById('id_press_rate')?.value, 45);
      const pullsMultiplier = (offsetSides === 'work_turn' || (offsetSides === 'work_sheet' && (backColors > 0 || spotBack > 0))) ? 2 : 1;
      const machinePulls = grossSheets * machineCuts;
      const pullsInfo = PricingMath.calcPullsAndTirage(machinePulls, pullsMultiplier);

      const pullsText = document.getElementById('press_pulls_count');
      if (pullsText) {
        pullsText.textContent = `${pullsInfo.pulls.toLocaleString()} ${this.config.i18n.pulls} (${pullsInfo.tirages} ${this.config.i18n.tirage})`;
      }
      $('#display_machine_pulls_count').text(`${pullsInfo.pulls.toLocaleString()} سحبة`);
      $('#display_machine_tirages').text(`(${pullsInfo.tirages} تراج)`);

      const pressCostDisplay = document.getElementById('cover_press_cost_display');
      const pressFloorBadge = document.getElementById('cover_press_floor_badge');
      const selectedMachineOpt = $('#id_cover_press_machine option:selected');
      const minPressFloor = PricingMath.parseSafeNumber(selectedMachineOpt.data('floor'), 200);

      if (pressFloorBadge) pressFloorBadge.textContent = `${minPressFloor.toFixed(2)} ${this.config.currencySymbol} فتحة`;
      const basePressCost = Math.max(minPressFloor, pullsInfo.tirages * pressRate);
      if (pressCostDisplay) pressCostDisplay.textContent = this.formatMoney(basePressCost);

      costPrintingCover = coverPlatesResult.totalCost + basePressCost;
    } else if (coverPrintingType === 'digital') {
      const clickPrice = PricingMath.parseSafeNumber(document.getElementById('id_digital_sheet_price')?.value, 2.50);
      const totalClicks = grossSheets;
      const clicksDisplay = document.getElementById('cover_digital_clicks_count');
      if (clicksDisplay) clicksDisplay.textContent = `${totalClicks.toLocaleString()} ${this.config.i18n.sheet}`;
      costPrintingCover = totalClicks * clickPrice;
      const digCostDisplay = document.getElementById('cover_digital_cost_display');
      if (digCostDisplay) digCostDisplay.textContent = this.formatMoney(costPrintingCover);
    } else if (coverPrintingType === 'digital_banner') {
      const bannerPricePerSqm = PricingMath.parseSafeNumber(document.getElementById('id_banner_sqm_price')?.value, 75);
      const hasWhiteInk = document.getElementById('id_has_white_ink')?.checked || false;
      const effectiveSqmPrice = bannerPricePerSqm + (hasWhiteInk ? 35 : 0);
      const singlePieceSqm = (openW * openH) / 10000;
      const totalSqm = Math.max(1, singlePieceSqm * qty);
      costPrintingCover = totalSqm * effectiveSqmPrice;
      const bannerSqmDisplay = document.getElementById('cover_banner_sqm_count');
      if (bannerSqmDisplay) bannerSqmDisplay.textContent = `${totalSqm.toFixed(2)} ${this.config.i18n.sqm}`;
      const bannerCostDisplay = document.getElementById('cover_banner_cost_display');
      if (bannerCostDisplay) bannerCostDisplay.textContent = this.formatMoney(costPrintingCover);
    } else if (coverPrintingType === 'screen') {
      const screenColors = PricingMath.parseSafeNumber(document.getElementById('id_screen_colors_count')?.value, 1);
      const screenSetupCost = screenColors * 120;
      const screenPrintCost = qty * screenColors * 1.50;
      costPrintingCover = screenSetupCost + screenPrintCost;
      const screenDisplay = document.getElementById('cover_screen_cost_display');
      if (screenDisplay) screenDisplay.textContent = this.formatMoney(costPrintingCover);
    }

    let costPrintingInner = 0;
    const innerPlatesResult = this.updateInnerPlatesUI();

    if (['catalog', 'book', 'magazine', 'book_catalog'].includes(type)) {
      if (innerPrintingType === 'offset') {
        const innerPressRate = PricingMath.parseSafeNumber(document.getElementById('id_inner_press_rate')?.value, 45);
        const innerPulls = grossSheets * totalSignatures * 2;
        const innerTirages = Math.max(1, Math.ceil(innerPulls / 1000));
        const innerPullsText = document.getElementById('inner_press_pulls_count');
        if (innerPullsText) {
          innerPullsText.textContent = `${innerPulls.toLocaleString()} ${this.config.i18n.pulls} (${innerTirages} ${this.config.i18n.tirage})`;
        }
        const innerPressCost = Math.max(250, innerTirages * innerPressRate);
        const innerPressCostDisplay = document.getElementById('inner_press_cost_display');
        if (innerPressCostDisplay) innerPressCostDisplay.textContent = this.formatMoney(innerPressCost);
        costPrintingInner = innerPlatesResult.totalCost + innerPressCost;
      } else if (innerPrintingType === 'digital') {
        const colorPages = PricingMath.parseSafeNumber(document.getElementById('id_digital_inner_color_pages')?.value, pages);
        const bwPages = PricingMath.parseSafeNumber(document.getElementById('id_digital_inner_bw_pages')?.value, 0);
        const colorClicks = (colorPages / 2) * qty;
        const bwClicks = (bwPages / 2) * qty;
        costPrintingInner = (colorClicks * 0.80) + (bwClicks * 0.25);
      }
    } else if (type === 'invoice' || type === 'receipt' || type === 'ncr') {
      costPrintingInner = innerPlatesResult.totalCost + Math.max(200, qty * 0.60);
    }

    const costPrinting = costPrintingCover + costPrintingInner;

    // 3. تكلفة السلوفان والتشطيب
    const lam = document.getElementById('id_lamination')?.value || 'none';
    let costFinishing = 0;
    if (lam !== 'none') {
      if (coverPrintingType === 'digital_banner') {
        const totalSqm = ((openW * openH) / 10000) * qty;
        costFinishing += Math.max(30, totalSqm * 15);
      } else {
        const lamRatePerSheet = lam.includes('2_sides') ? 0.90 : 0.50;
        costFinishing += Math.max(150, grossSheets * lamRatePerSheet);
      }
    }

    const finishVal = document.getElementById('id_finishing')?.value || 'none';
    if (finishVal !== 'none') {
      const dieSetup = (finishVal.includes('foil') || finishVal.includes('emboss')) ? 150 : 0;
      costFinishing += Math.max(200, qty * 0.40) + dieSetup;
    }

    // 4. تكلفة التجليد والتكسير
    let costInnerBinding = 0;
    const dieVal = document.getElementById('id_die_cutting')?.value || 'straight_cut';
    const costCoverDie = (dieVal.includes('die_cut') || dieVal === 'kiss_cut') ? 250 : 0;

    if (['catalog', 'book', 'magazine', 'book_catalog'].includes(type)) {
      if (isStaple) {
        costInnerBinding += Math.max(75, qty * 0.50);
      } else if (bindingType === 'perfect_binding') {
        costInnerBinding += Math.max(150, qty * 1.80);
      } else if (isHardcover) {
        costInnerBinding += Math.max(250, (qty * 4.50) + 150);
      } else if (isWireO) {
        costInnerBinding += Math.max(120, qty * 2.50);
      } else if (isPad) {
        costInnerBinding += Math.max(50, qty * 0.75);
      } else if (bindingType === 'sewing_binding') {
        const sewingCost = totalSignatures * 0.20 * qty;
        costInnerBinding += Math.max(200, (qty * 2.00) + sewingCost);
      }
    } else if (type === 'invoice' || type === 'receipt' || type === 'ncr') {
      const ncrCap = PricingMath.parseSafeNumber(document.getElementById('id_ncr_book_capacity')?.value, 50);
      const totalNums = qty * ncrCap;
      const numberingCost = Math.max(100, (totalNums / 1000) * 20.00);
      const padBindingCost = qty * 2.50;
      costInnerBinding += numberingCost + padBindingCost;
    } else if (type === 'folder' || type === 'box' || type === 'folder_packaging') {
      costInnerBinding += 350 + (qty * 0.60);
    }

    const costBinding = costCoverDie + costInnerBinding;

    // 5. اللوجستيات والهدايا
    const costLogistics = PricingMath.parseSafeNumber(document.getElementById('id_extra_cost')?.value || document.getElementById('id_estimated_shipping_cost')?.value, 0);
    const costGiveaways = (type === 'giveaways' || type === 'gift' || type === 'promo')
      ? PricingMath.parseSafeNumber(document.getElementById('id_giveaway_item_cost')?.value, 0)
      : 0;

    // تحديث نسبة فحص الهدايا 3%
    const giveawayBufferDisplay = document.getElementById('giveaway_buffer_qty_display');
    if (giveawayBufferDisplay) {
      giveawayBufferDisplay.textContent = `${Math.ceil(qty * 1.03).toLocaleString()} ${this.config.i18n.piece}`;
    }

    // حساب إجمالي تكلفة كل قسم على حدة لشارات الهيدر
    const step2Cost = costCoverPaper + costPrintingCover + costFinishing + costCoverDie;
    const step3Cost = costInnerPaper + costPrintingInner + costInnerBinding;
    const step4Cost = costGiveaways;
    const step5Cost = costLogistics;

    const badgeStep2 = document.getElementById('step2_cost_badge');
    if (badgeStep2) badgeStep2.textContent = this.formatMoney(step2Cost);

    const badgeStep3 = document.getElementById('step3_cost_badge');
    if (badgeStep3) badgeStep3.textContent = this.formatMoney(step3Cost);

    const badgeStep4 = document.getElementById('step4_cost_badge');
    if (badgeStep4) badgeStep4.textContent = this.formatMoney(step4Cost);

    const badgeStep5 = document.getElementById('step5_cost_badge');
    if (badgeStep5) badgeStep5.textContent = this.formatMoney(step5Cost);

    // الإجمالي النهائي وهامش الربح
    const totalCost = costPaper + costPrinting + costFinishing + costBinding + costLogistics + costGiveaways;
    const profitMarginInput = document.getElementById('id_profit_margin');
    const profitMargin = profitMarginInput ? (PricingMath.parseSafeNumber(profitMarginInput.value, 25) / 100) : 0.25;

    const grandTotal = PricingMath.calcFinalPrice(totalCost, profitMargin);
    const safeQty = Math.max(1, qty);
    const unitPrice = grandTotal / safeQty;

    // مزامنة الحقول المخفية للباك إند
    if (document.getElementById('id_material_cost')) document.getElementById('id_material_cost').value = costPaper.toFixed(2);
    if (document.getElementById('id_printing_cost')) document.getElementById('id_printing_cost').value = costPrinting.toFixed(2);
    if (document.getElementById('id_finishing_cost')) document.getElementById('id_finishing_cost').value = (costFinishing + costBinding).toFixed(2);
    if (document.getElementById('id_final_price')) document.getElementById('id_final_price').value = grandTotal.toFixed(2);
    if (document.getElementById('id_sale_price')) document.getElementById('id_sale_price').value = grandTotal.toFixed(2);

    // تحديث شاشات العرض بالشريط الجانبي
    const costPaperEl = document.getElementById('cost_paper_display');
    if (costPaperEl) costPaperEl.textContent = this.formatMoney(costPaper);
    const costPrintEl = document.getElementById('cost_printing_display');
    if (costPrintEl) costPrintEl.textContent = this.formatMoney(costPrinting);
    const costFinEl = document.getElementById('cost_finishing_display');
    if (costFinEl) costFinEl.textContent = this.formatMoney(costFinishing);
    const costBindEl = document.getElementById('cost_binding_display');
    if (costBindEl) costBindEl.textContent = this.formatMoney(costBinding);
    const costLogEl = document.getElementById('cost_logistics_display');
    if (costLogEl) costLogEl.textContent = this.formatMoney(costLogistics);
    const totalCostEl = document.getElementById('total_cost_display');
    if (totalCostEl) totalCostEl.textContent = this.formatMoney(totalCost);

    const unitPriceEl = document.getElementById('unit_price_display');
    if (unitPriceEl) unitPriceEl.textContent = this.formatMoney(unitPrice, true);
    const finalTotalEl = document.getElementById('final_total_display');
    if (finalTotalEl) finalTotalEl.textContent = this.formatMoney(grandTotal);

    // شريط ومؤشر هامش الربح والتلوين الذكي
    const marginPct = Math.round(profitMargin * 100);
    const marginDisplay = document.getElementById('margin_percentage_display');
    const marginBar = document.getElementById('margin_progress_bar');
    if (marginDisplay) marginDisplay.textContent = `${marginPct}%`;
    if (marginBar) {
      marginBar.style.width = `${Math.min(100, Math.max(0, marginPct))}%`;
      marginBar.className = marginPct < 15
        ? 'progress-bar bg-danger'
        : (marginPct < 25 ? 'progress-bar bg-primary' : 'progress-bar bg-success');
    }

    // تحديث البدائل اللحظية
    const altNoLam = document.getElementById('alt_no_lam_diff');
    if (altNoLam) altNoLam.textContent = `- ${this.formatMoney(costFinishing * 0.7)}`;
    const altLightPaper = document.getElementById('alt_lighter_paper_diff');
    if (altLightPaper) altLightPaper.textContent = `- ${this.formatMoney(costPaper * 0.25)}`;

    // تحديث جدول الشرائح الكمية بدعم المعرفات المزدوجة
    const isDigital = coverPrintingType === 'digital';
    const plates = PricingMath.parseSafeNumber(document.getElementById('id_plate_count')?.value, 0);
    const fixedSetup = (plates * 85) + 250;
    const tiers = PricingMath.calcPricingTiers(totalCost, safeQty, profitMargin, isDigital, fixedSetup);

    const setTierContent = (prefixA, prefixB, tierData) => {
      const qtyEl = document.getElementById(`${prefixA}_qty`) || document.getElementById(`${prefixB}_qty`);
      const unitEl = document.getElementById(`${prefixA}_unit`) || document.getElementById(`${prefixB}_unit`);
      const totalEl = document.getElementById(`${prefixA}_total`) || document.getElementById(`${prefixB}_total`);

      if (qtyEl) qtyEl.textContent = `${tierData.qty.toLocaleString()} ${this.config.i18n.piece}`;
      if (unitEl) unitEl.textContent = this.formatMoney(tierData.unit, true);
      if (totalEl) totalEl.textContent = this.formatMoney(tierData.total);
    };

    setTierContent('tier1', 'tier_1', tiers.t1);
    setTierContent('tier2', 'tier_2', tiers.t2);
    setTierContent('tier3', 'tier_3', tiers.t3);

    // مستشار تقليل الهدر
    this.updateTrimAdvisor(openW, openH);
  }

  /**
   * مستشار تقليل الهدر الذكي
   */
  updateTrimAdvisor(openW, openH) {
    const curImp = PricingMath.calcImposition(100.0, 70.0, openW, openH);
    const testW = openW - 0.5;
    const testH = openH - 0.5;
    const altImp = PricingMath.calcImposition(100.0, 70.0, testW, testH);

    const trimBanner = document.getElementById('trim_advisor_banner');
    const trimText = document.getElementById('trim_advisor_text');

    if (altImp.cutsPerSheet > curImp.cutsPerSheet && testW > 5 && testH > 5) {
      if (trimBanner) trimBanner.classList.remove('d-none');
      if (trimText) {
        trimText.textContent = `وفر في الورق: تقليل المقاس بمقدار 0.5 سم فقط يرفع عائد الفرخ من ${curImp.cutsPerSheet} إلى ${altImp.cutsPerSheet} قطعة!`;
      }
      this.currentTrimSuggestion = {
        action: () => {
          const widthInput = document.getElementById('id_width');
          const heightInput = document.getElementById('id_height');
          if (widthInput) widthInput.value = testW.toFixed(1);
          if (heightInput) heightInput.value = testH.toFixed(1);
          this.updateOpenDimensionsDisplay();
          this.debouncedRecalculate();
        }
      };
    } else {
      if (trimBanner) trimBanner.classList.add('d-none');
      this.currentTrimSuggestion = null;
    }
  }

  /**
   * توليد ونسخ رسالة عرض السعر للواتساب (Universal Clipboard)
   */
  generateWhatsAppQuote() {
    const title = document.getElementById('id_title')?.value || 'مطبوعات فاخرة';
    const qty = document.getElementById('id_quantity')?.value || '1000';
    const total = document.getElementById('final_total_display')?.textContent || `0.00 ${this.config.currencySymbol}`;
    const unit = document.getElementById('unit_price_display')?.textContent || `0.00 ${this.config.currencySymbol}`;
    const isClosed = document.getElementById('id_is_closed_size')?.checked || false;
    const openDimsText = document.getElementById('open_dims_text')?.textContent || '';
    const sizeSelect = document.getElementById('id_product_size');
    const sizeName = sizeSelect?.options[sizeSelect.selectedIndex]?.text || '';
    const widthVal = document.getElementById('id_width')?.value;
    const heightVal = document.getElementById('id_height')?.value;
    const orientRadio = document.querySelector('input[name="print_orientation"]:checked');
    const orientLabel = orientRadio?.value === 'landscape' ? 'عرضي' : 'طولي';
    const openDirRadio = document.querySelector('input[name="open_direction"]:checked');
    const openDirLabel = openDirRadio?.value === 'top' ? 'فتح من أعلى' : (openDirRadio?.value === 'left' ? 'فتح إنجليزي (يسار)' : 'فتح عربي (يمين)');

    let sizeText = sizeSelect?.value === 'custom'
      ? `مقاس مخصص (${widthVal}×${heightVal} سم)`
      : `${sizeName}`;

    if (isClosed) {
      sizeText += ` (مقفول) [مفتوح: ${openDimsText}] - ${orientLabel} (${openDirLabel})`;
    } else {
      sizeText += ` - ${orientLabel}`;
    }

    const coverType = document.getElementById('id_cover_printing_type')?.value || 'offset';
    let printMethodText = 'أوفست فاخر 4 ألوان';
    if (coverType === 'offset') {
      const sides = document.getElementById('id_print_sides_mode_offset')?.value || 'single';
      const sidesLabel = sides === 'work_turn' ? 'طبع وقلب' : (sides === 'work_sheet' ? 'وجهين' : 'وجه واحد');
      const frontC = parseInt(document.getElementById('id_colors_front')?.value || '4', 10);
      const spotF = parseInt(document.getElementById('id_spot_colors_front')?.value || '0', 10);

      if (sides === 'work_sheet') {
        const backC = parseInt(document.getElementById('id_colors_back')?.value || '4', 10);
        const spotB = parseInt(document.getElementById('id_spot_colors_back')?.value || '0', 10);
        const totalSpot = spotF + spotB;
        printMethodText = `أوفست وجهين (${frontC}+${backC})` + (totalSpot > 0 ? ` + ${totalSpot} لون مخصوص` : '');
      } else {
        printMethodText = `أوفست ${sidesLabel} (${frontC} لون)` + (spotF > 0 ? ` + ${spotF} لون مخصوص` : '');
      }
    } else if (coverType === 'digital') {
      const clickMode = document.getElementById('id_digital_color_mode')?.value || '4_0';
      const clickLabel = clickMode === '4_4' ? 'وجهين ألوان (4/4)' : (clickMode === '4_1' ? 'وجه ألوان + ظهر أسود (4/1)' : (clickMode === '1_0' ? 'وجه واحد أسود' : 'وجه واحد ألوان'));
      printMethodText = `ديجيتال ليزر عالي الدقة ${clickLabel}`;
    } else if (coverType === 'digital_banner') {
      printMethodText = 'طباعة خامات كبيرة بالمتر المربع';
    } else if (coverType === 'screen') {
      printMethodText = 'سلك سكرين شابلونات يدوية فاخرة';
    } else if (coverType === 'none') {
      printMethodText = 'بدون طباعة (خامة جاهزة سادة)';
    }

    const paper = document.getElementById('id_paper_type')?.options[document.getElementById('id_paper_type')?.selectedIndex]?.text || '';
    const weight = document.getElementById('id_paper_weight')?.value || '300';
    const lam = document.getElementById('id_lamination')?.options[document.getElementById('id_lamination')?.selectedIndex]?.text || '';

    const text = `🌟 *عرض سعر طباعة معتمد - MWHEBA ERP* 🌟\n\n` +
      `📋 *الصنف:* ${title}\n` +
      `📐 *المقاس:* ${sizeText}\n` +
      `🔢 *الكمية:* ${Number(qty).toLocaleString()} قطعة/نسخة\n` +
      `📄 *المواصفات:* ورق ${paper} ${weight} جم | ${lam}\n` +
      `💰 *سعر القطعة:* ${unit}\n` +
      `💵 *إجمالي السعر:* ${total}\n` +
      `📌 *ملاحظة:* الأسعار صافية غير شاملة ضريبة القيمة المضافة (14%).\n` +
      `⏳ *الصلاحية:* صالح لمدة 5 أيام من تاريخه.\n\n` +
      `_شكراً لتعاملكم معنا، يسعدنا تأكيد طلبكم!_`;

    this.copyToClipboard(text);
  }

  /**
   * نسخ للنص بالحافظة مع Fallback للشبكات الداخلية HTTP
   */
  copyToClipboard(text) {
    const self = this;
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(() => {
        self.showNotification('تم نسخ ملخص عرض السعر للواتساب بنجاح 📲', 'success');
      }).catch(() => {
        self.fallbackCopyText(text);
      });
    } else {
      this.fallbackCopyText(text);
    }
  }

  /**
   * Fallback للنسخ عبر textarea مؤقتة
   */
  fallbackCopyText(text) {
    const textArea = document.createElement('textarea');
    textArea.value = text;
    textArea.style.position = 'fixed';
    textArea.style.left = '-999999px';
    textArea.style.top = '-999999px';
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    try {
      document.execCommand('copy');
      this.showNotification('تم نسخ ملخص عرض السعر للواتساب بنجاح 📲', 'success');
    } catch (err) {
      this.showNotification('تعذر النسخ التلقائي، يرجى التحديد والنسخ يدوياً', 'warning');
    }
    document.body.removeChild(textArea);
  }

  /**
   * كشف الحقول غير الصالحة وتوسيع الأكورديون الحاضن لها
   */
  validateAndUnfoldCollapsedSections(form) {
    const firstInvalid = form.querySelector(':invalid');
    if (firstInvalid) {
      const collapsedParent = firstInvalid.closest('.collapse');
      if (collapsedParent && !collapsedParent.classList.contains('show')) {
        if (typeof bootstrap !== 'undefined' && bootstrap.Collapse) {
          const bsCollapse = new bootstrap.Collapse(collapsedParent, { toggle: true });
        } else {
          $(collapsedParent).collapse('show');
        }
      }
      setTimeout(() => {
        firstInvalid.focus();
        firstInvalid.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }, 200);
    }
  }

  /**
   * تنظيف وتطهير الحقول غير النشطة قبل الـ POST
   */
  sanitizePayloadOnSubmit() {
    const coverType = document.getElementById('id_cover_printing_type')?.value || 'offset';
    const offsetSides = document.getElementById('id_print_sides_mode_offset')?.value || 'single';

    if (coverType === 'offset') {
      if (offsetSides !== 'work_sheet') {
        const backC = document.getElementById('id_colors_back');
        if (backC) backC.value = '0';
        const backSpot = document.getElementById('id_spot_colors_back');
        if (backSpot) backSpot.value = '0';
      }
    } else if (coverType === 'none') {
      ['id_colors_front', 'id_colors_back', 'id_spot_colors_front', 'id_spot_colors_back'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = '0';
      });
    }
  }

  /**
   * اختصارات لوحة المفاتيح (Ctrl+S / Cmd+S)
   */
  bindKeyboardShortcuts() {
    const self = this;
    document.addEventListener('keydown', function (e) {
      if ((e.ctrlKey || e.metaKey) && (e.key === 's' || e.key === 'S')) {
        e.preventDefault();
        const form = document.getElementById('order-form');
        if (form) {
          const submitBtn = document.getElementById('btn_save_order');
          if (submitBtn) submitBtn.click();
        }
      }
    });
  }

  /**
   * دورة حياة المتصفح (BFCache Restore & Unsaved Changes Guard)
   */
  bindLifecycleGuards() {
    const self = this;

    // استعادة الحسابات من الـ BFCache عند الرجوع
    window.addEventListener('pageshow', function (event) {
      self.recalculate();
    });

    // تحذير الخروج بدون حفظ
    window.addEventListener('beforeunload', function (e) {
      if (self.isDirty) {
        e.preventDefault();
        e.returnValue = '';
      }
    });
  }
}

// تصدير الكائن للنطاق العام
window.PricingMath = PricingMath;
window.PRESETS_DATA = PRESETS_DATA;
window.OrderFormUIController = OrderFormUIController;
