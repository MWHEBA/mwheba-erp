/**
 * MWHEBA ERP - Printing Pricing: Commercial Sheet-Fed Production Line Subsystem
 * Module: pricing_sheet_printing.js
 * Version: 2.3.0
 *
 * Responsibilities:
 * 1. Paper & Substrates Engineering: sheet sizes, grain (LG/SG), piece cutting imposition,
 *    pack capacities, weight (GSM), origins, merchants, and converted sheet pricing.
 * 2. Offset Presses: machine models, bed sizes (50x70, 70x100), tirage rates, floor setup.
 * 3. CTP Plates: front/back plate counts, archived plates, plate options, and plate unit prices.
 * 4. Digital Sheet Printing: digital click charges, sheet passes, and color modes (4/4, 4/0).
 * 5. Production Line Macros: quick copy cover-to-inner and preferred supplier auto-selection.
 */

class PricingSheetPrintingSubsystem {
  constructor(controller) {
    this.controller = controller;
    this.api = controller?.api || (window.PricingApiClient ? new window.PricingApiClient(controller?.config) : null);
    this.isPaperCascadeUpdating = false;
    this.isManualSheetsActive = false;
    this.manualGrossSheets = null;
    this.isSyncingOrigin = false;
    this.currentPieceName = '';
  }

  get isUserInteracting() {
    return this.controller ? this.controller.isUserInteracting : true;
  }
  set isUserInteracting(val) {
    if (this.controller) this.controller.isUserInteracting = val;
  }

  get config() {
    return this.controller ? this.controller.config : {};
  }

  debouncedRecalculate() {
    if (this.controller && typeof this.controller.debouncedRecalculate === 'function') {
      this.controller.debouncedRecalculate();
    }
  }

  recalculate() {
    if (this.controller && typeof this.controller.recalculate === 'function') {
      this.controller.recalculate();
    }
  }

  updateSupplierDependentSections() {
    if (this.controller && typeof this.controller.updateSupplierDependentSections === 'function') {
      this.controller.updateSupplierDependentSections();
    }
  }

  showNotification(msg, type) {
    if (this.controller && typeof this.controller.showNotification === 'function') {
      this.controller.showNotification(msg, type);
    }
  }

  renderPriceStalenessBadge(...args) {
    if (this.controller && typeof this.controller.renderPriceStalenessBadge === 'function') {
      this.controller.renderPriceStalenessBadge(...args);
    }
  }

  renderManualPriceBadge(...args) {
    if (this.controller && typeof this.controller.renderManualPriceBadge === 'function') {
      this.controller.renderManualPriceBadge(...args);
    }
  }

  clearPriceStalenessBadge(...args) {
    if (this.controller && typeof this.controller.clearPriceStalenessBadge === 'function') {
      this.controller.clearPriceStalenessBadge(...args);
    }
  }

  getCleanPieceName() {
    return this.controller && typeof this.controller.getCleanPieceName === 'function'
      ? this.controller.getCleanPieceName()
      : '';
  }

  formatMoney(amount, forceDecimals = false) {
    if (this.controller && typeof this.controller.formatMoney === 'function') {
      return this.controller.formatMoney(amount, forceDecimals);
    }
    const currency = this.config.currencySymbol || '';
    const num = Number(amount || 0);
    const formatted = num.toLocaleString('en-US', {
      minimumFractionDigits: forceDecimals ? 2 : 0,
      maximumFractionDigits: 2
    });
    return currency ? `${formatted}\u00A0${currency}` : formatted;
  }

  formatNumber(amount, forceDecimals = false) {
    if (this.controller && typeof this.controller.formatNumber === 'function') {
      return this.controller.formatNumber(amount, forceDecimals);
    }
    const num = Number(amount || 0);
    return num.toLocaleString('en-US', {
      minimumFractionDigits: forceDecimals ? 2 : 0,
      maximumFractionDigits: 2
    });
  }

  renderPressOptionsHtml(presses, selectedIdx = 0) {
    if (!presses || !presses.length) return '';
    let optionsHtml = '';
    presses.forEach((p, idx) => {
      const isSel = idx === selectedIdx ? 'selected' : '';
      const bedSize = p.bed_size || '';
      const stdBed = p.standard_bed_size || bedSize;
      optionsHtml += `<option value="${p.id}" data-bed="${bedSize}" data-std-bed="${stdBed}" data-rate="${p.price_per_1000 || 0}" data-floor="${p.setup_cost || 0}" data-service-id="${p.service_id}" data-set-price="${p.set_price || 0}" data-set-included-tirages="${p.set_included_tirages || 1}" data-price-date="${p.price_updated_at || ''}" data-price-age="${p.price_age_days !== undefined ? p.price_age_days : ''}" data-staleness="${p.price_staleness_status || 'fresh'}" data-valid-until="${p.price_valid_until || ''}" ${isSel}>${p.name}</option>`;
    });
    return optionsHtml;
  }

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

    if (coverPrintingType === 'offset' && offsetSides === 'work_sheet') {
      backColors = PricingMath.parseSafeNumber(backColorsInput?.value, 4);
      spotBack = PricingMath.parseSafeNumber(spotBackInput?.value, 0);
      const expectedBack = backColors + spotBack;
      if (plateBackInput) {
        plateBackInput.disabled = false;
        if (!plateBackInput.dataset.manual || parseInt(plateBackInput.value, 10) === 0) {
          plateBackInput.value = expectedBack;
        }
      }
    } else {
      if (plateBackInput) {
        plateBackInput.value = 0;
        plateBackInput.disabled = true;
        delete plateBackInput.dataset.manual;
        $(plateBackInput).removeClass('border-primary');
      }
    }

    const calculatedFront = frontColors + spotFront;
    if (plateFrontInput && !plateFrontInput.dataset.manual) {
      plateFrontInput.value = calculatedFront;
    }

    const curFront = PricingMath.parseSafeNumber(plateFrontInput?.value, calculatedFront);
    const curBack = (coverPrintingType === 'offset' && offsetSides === 'work_sheet')
      ? PricingMath.parseSafeNumber(plateBackInput?.value, (backColors + spotBack))
      : 0;
    const totalPlates = curFront + curBack;

    if (plateTotalInput) {
      plateTotalInput.value = totalPlates;
    }

    const actualPlates = totalPlates;
    const unitPrice = PricingMath.parseSafeNumber(platePriceInput?.value, 0);
    const setPrice = PricingMath.parseSafeNumber(platePriceInput?.dataset?.setPrice || $(platePriceInput).attr('data-set-price'), 0);

    let totalCost = 0;
    if (!isArchived && actualPlates > 0) {
      if (setPrice > 0 && unitPrice > 0) {
        const fullSets = Math.floor(actualPlates / 4);
        const remPlates = actualPlates % 4;
        const costUnit = actualPlates * unitPrice;
        const costSetRem = (fullSets * setPrice) + (remPlates * unitPrice);
        const costNextSet = (fullSets + (remPlates > 0 ? 1 : 0)) * setPrice;
        totalCost = Math.min(costUnit, costSetRem, costNextSet);
      } else if (setPrice > 0) {
        const totalSets = Math.ceil(actualPlates / 4);
        totalCost = totalSets * setPrice;
      } else {
        totalCost = actualPlates * unitPrice;
      }
    }

    if (coverPrintingType !== 'offset') {
      totalCost = 0;
    }

    const platesTotalInput = document.getElementById('id_plates_total');
    if (platesTotalInput) platesTotalInput.value = actualPlates;

    const workTurnAlert = document.getElementById('work_turn_advisor_alert');
    if (workTurnAlert) {
      if (coverPrintingType === 'offset' && (offsetSides === 'work_turn' || offsetSides === 'work_and_turn')) {
        workTurnAlert.classList.remove('d-none');
      } else {
        workTurnAlert.classList.add('d-none');
      }
    }

    const ctpSetBadge = document.getElementById('cover_ctp_set_badge');
    if (ctpSetBadge) {
      if (!isArchived && setPrice > 0 && actualPlates >= 4 && coverPrintingType === 'offset') {
        ctpSetBadge.classList.remove('d-none');
      } else {
        ctpSetBadge.classList.add('d-none');
      }
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
    const selectEl = document.getElementById('id_order_type') || document.getElementById('id_job_anatomy_type') || document.getElementById('id_product_type');
    const type = selectEl?.options?.[selectEl.selectedIndex]?.dataset?.archetype || selectEl?.dataset?.archetype || selectEl?.value || 'flyer';
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
    const unitPrice = PricingMath.parseSafeNumber(innerPriceInput?.value, 0);
    const setPrice = PricingMath.parseSafeNumber(innerPriceInput?.dataset?.setPrice || $(innerPriceInput).attr('data-set-price'), 0);

    let totalCost = 0;
    if (!isArchived && actualInnerPlates > 0) {
      if (setPrice > 0 && unitPrice > 0) {
        const fullSets = Math.floor(actualInnerPlates / 4);
        const remPlates = actualInnerPlates % 4;
        const costUnit = actualInnerPlates * unitPrice;
        const costSetRem = (fullSets * setPrice) + (remPlates * unitPrice);
        const costNextSet = (fullSets + (remPlates > 0 ? 1 : 0)) * setPrice;
        totalCost = Math.min(costUnit, costSetRem, costNextSet);
      } else if (setPrice > 0) {
        const totalSets = Math.ceil(actualInnerPlates / 4);
        totalCost = totalSets * setPrice;
      } else {
        totalCost = actualInnerPlates * unitPrice;
      }
    }

    if (innerPrintingType !== 'offset') {
      actualInnerPlates = 0;
      if (innerTotalInput) innerTotalInput.value = 0;
      totalCost = 0;
    }

    const innerCtpSetBadge = document.getElementById('inner_ctp_set_badge');
    if (innerCtpSetBadge) {
      if (!isArchived && setPrice > 0 && actualInnerPlates >= 4 && innerPrintingType === 'offset') {
        innerCtpSetBadge.classList.remove('d-none');
      } else {
        innerCtpSetBadge.classList.add('d-none');
      }
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

    // استيقاظ فوري ولحظي متزامن عند أي تفاعل أو اختيار للموردين (Instant Gating Wakeup)
    $(document).on('change select2:select select2:clear',
      '#id_paper_supplier, #id_cover_offset_supplier, #id_cover_ctp_supplier, #id_cover_digital_supplier, #id_inner_paper_supplier, #id_inner_offset_supplier, #id_inner_ctp_supplier, #id_inner_digital_supplier, input[name="paper_source"], #id_is_plates_archived, #id_is_inner_plates_archived',
      function () {
        self.updateSupplierDependentSections();
      }
    );

    // 1. مطبعة أوفست الغلاف — تحميل ماكينات ومواصفات المورد الفعلي
    $(document).on('change select2:select', '#id_cover_offset_supplier', function () {
      const supplierId = this.value;
      const machineSelect = $('#id_cover_press_machine');
      const pressRateInput = $('#id_press_rate');

      // تنشيط القسم فورياً وبشكل متزامن بمجرد اختيار المورد
      self.updateSupplierDependentSections();

      if (!supplierId) {
        machineSelect.html('<option value="">-- اختر مطبعة الأوفست أولاً --</option>');
        pressRateInput.val('');
        pressRateInput.removeAttr('data-baseline-price data-supplier-id data-service-id');
        $('#id_cover_press_service_id').val('');
        delete pressRateInput[0]?.dataset?.manual;
        pressRateInput.removeClass('border-primary');
        self.clearPriceStalenessBadge($('#press_rate_staleness_badge'), null);
        self.updateSupplierDependentSections();
        self.debouncedRecalculate();
      } else {
        delete pressRateInput[0]?.dataset?.manual;
        pressRateInput.removeClass('border-primary');
        $.getJSON(`${self.config.urls.pressesApi}?supplier_id=${supplierId}&order_type=offset`, function (data) {
          if (data && data.success && data.presses && data.presses.length > 0) {
            const currentBed = $('#id_press_bed_size').val();
            let selectedIdx = 0;
            if (currentBed) {
              const matchIdx = data.presses.findIndex(p => (p.standard_bed_size === currentBed || p.bed_size === currentBed));
              if (matchIdx !== -1) selectedIdx = matchIdx;
            }

            machineSelect.html(self.renderPressOptionsHtml(data.presses, selectedIdx));
            const chosen = data.presses[selectedIdx];
            const chosenRate = chosen.price_per_1000 || '';
            pressRateInput.val(chosenRate);
            pressRateInput.attr('data-baseline-price', chosenRate);
            pressRateInput.attr('data-supplier-id', supplierId);
            pressRateInput.attr('data-service-id', chosen.service_id || '');
            $('#id_cover_press_service_id').val(chosen.service_id || '');
            self.renderPriceStalenessBadge(
              chosen.price_updated_at,
              chosen.price_age_days,
              chosen.price_staleness_status,
              chosen.price_valid_until,
              $('#press_rate_staleness_badge'),
              null
            );
            const targetBed = chosen.standard_bed_size || chosen.bed_size;
            if (targetBed) $('#id_press_bed_size').val(targetBed).trigger('change');
          } else {
            machineSelect.html('<option value="">-- لا توجد ماكينات مسجلة لهذا المورد --</option>');
            pressRateInput.val('');
            pressRateInput.removeAttr('data-baseline-price data-supplier-id data-service-id');
            $('#id_cover_press_service_id').val('');
            self.clearPriceStalenessBadge($('#press_rate_staleness_badge'), null);
          }
          self.updateSupplierDependentSections();
          self.debouncedRecalculate();
        }).fail(() => {
          machineSelect.html('<option value="">-- فشل جلب ماكينات المورد --</option>');
          pressRateInput.val('');
          pressRateInput.removeAttr('data-baseline-price data-supplier-id data-service-id');
          $('#id_cover_press_service_id').val('');
          self.clearPriceStalenessBadge($('#press_rate_staleness_badge'), null);
          self.updateSupplierDependentSections();
          self.debouncedRecalculate();
        });
      }
    });

    // تغيير ماكينة أوفست الغلاف (المزامنة الدقيقة لسعر التراج ومقاس السرير المعتمد للمورد)
    $(document).on('change', '#id_cover_press_machine', function () {
      if (self.isSyncingFields) return;
      const selectedOpt = $(this).find('option:selected');
      const optRate = selectedOpt.data('rate');
      const optBed = selectedOpt.data('std-bed') || selectedOpt.data('bed');
      const svcId = selectedOpt.data('service-id');
      const pressRateInput = $('#id_press_rate');
      delete pressRateInput[0]?.dataset?.manual;
      pressRateInput.removeClass('border-primary');
      if (svcId) {
        $('#id_cover_press_service_id').val(svcId);
        pressRateInput.attr('data-service-id', svcId);
      }
      if (optRate !== undefined) {
        pressRateInput.val(optRate);
        pressRateInput.attr('data-baseline-price', optRate);
      }
      pressRateInput.attr('data-supplier-id', $('#id_cover_offset_supplier').val() || '');

      self.renderPriceStalenessBadge(
        selectedOpt.data('price-date'),
        selectedOpt.data('price-age'),
        selectedOpt.data('staleness'),
        selectedOpt.data('valid-until'),
        $('#press_rate_staleness_badge'),
        null
      );

      self.isSyncingFields = true;
      if (optBed && $('#id_press_bed_size').val() !== optBed) {
        const matchingPlate = $('#id_press_bed_size').find(`option[value="${optBed}"], option[data-bed="${optBed}"]`);
        if (matchingPlate.length) {
          $('#id_press_bed_size').val(matchingPlate.val()).trigger('change');
        }
      }
      self.isSyncingFields = false;
      self.updateSupplierDependentSections();
      self.debouncedRecalculate(50);
    });

    // 2. مكتب فصل زنكات الغلاف CTP — السعر يتحدد فقط من مواصفات زنك المورد للمقاس المطلوب
    $(document).on('change select2:select', '#id_cover_ctp_supplier', function () {
      const supplierId = this.value;
      const bedSize = $('#id_press_bed_size').val() || $('#id_press_bed_size option:selected').data('bed') || '';
      const platePriceInput = $('#id_plate_price');

      // تنشيط القسم فورياً وبشكل متزامن بمجرد اختيار المورد
      self.updateSupplierDependentSections();

      if (supplierId) {
        delete platePriceInput[0]?.dataset?.manual;
        platePriceInput.removeClass('border-primary');
        $.getJSON(`${self.config.urls.pressesApi}?supplier_id=${supplierId}&order_type=ctp`, function (data) {
          if (data && data.success && data.presses && data.presses.length > 0) {
            let matched = data.presses.find(p => (p.standard_bed_size === bedSize || p.bed_size === bedSize));
            if (matched) {
              const matchedRate = matched.price_per_1000 || '';
              platePriceInput.val(matchedRate);
              platePriceInput.attr('data-baseline-price', matchedRate);
              platePriceInput.attr('data-supplier-id', supplierId);
              platePriceInput.attr('data-service-id', matched.service_id || '');
              platePriceInput.attr('data-set-price', matched.set_price || 0);
              $('#id_cover_ctp_service_id').val(matched.service_id || '');
              self.renderPriceStalenessBadge(
                matched.price_updated_at,
                matched.price_age_days,
                matched.price_staleness_status,
                matched.price_valid_until,
                $('#plate_price_staleness_badge'),
                null
              );
            } else {
              platePriceInput.val('').removeAttr('data-set-price data-baseline-price data-supplier-id data-service-id');
              $('#id_cover_ctp_service_id').val('');
              self.clearPriceStalenessBadge($('#plate_price_staleness_badge'), null);
            }
          } else {
            platePriceInput.val('').removeAttr('data-set-price data-baseline-price data-supplier-id data-service-id');
            $('#id_cover_ctp_service_id').val('');
            self.clearPriceStalenessBadge($('#plate_price_staleness_badge'), null);
          }
          self.updateCoverPlatesUI();
          self.updateSupplierDependentSections();
          self.debouncedRecalculate();
        }).fail(() => {
          platePriceInput.val('').removeAttr('data-set-price data-baseline-price data-supplier-id data-service-id');
          $('#id_cover_ctp_service_id').val('');
          self.clearPriceStalenessBadge($('#plate_price_staleness_badge'), null);
          self.updateCoverPlatesUI();
          self.updateSupplierDependentSections();
          self.debouncedRecalculate();
        });
      } else {
        platePriceInput.val('').removeAttr('data-set-price data-baseline-price data-supplier-id data-service-id');
        $('#id_cover_ctp_service_id').val('');
        delete platePriceInput[0]?.dataset?.manual;
        platePriceInput.removeClass('border-primary');
        self.clearPriceStalenessBadge($('#plate_price_staleness_badge'), null);
        self.updateCoverPlatesUI();
        self.updateSupplierDependentSections();
        self.debouncedRecalculate();
      }
    });

    // 3. مركز ديجيتال الغلاف — جلب ماكينات المورد الحقيقية وتحديث السعر حسب مواصفات الماكينة ونمط الألوان
    $(document).on('change select2:select', '#id_cover_digital_supplier', function () {
      const supplierId = this.value;
      const machineSelect = $('#id_cover_digital_machine');
      const clickPriceInput = $('#id_digital_sheet_price');

      // تنشيط القسم فورياً وبشكل متزامن بمجرد اختيار المورد
      self.updateSupplierDependentSections();

      if (!supplierId) {
        machineSelect.html('<option value="">-- اختر مركز الديجيتال أولاً --</option>');
        clickPriceInput.val('');
        clickPriceInput.removeAttr('data-baseline-price data-supplier-id data-service-id');
        $('#id_cover_digital_service_id').val('');
        delete clickPriceInput[0]?.dataset?.manual;
        clickPriceInput.removeClass('border-primary');
        self.clearPriceStalenessBadge($('#digital_price_staleness_badge'), null);
        self.updateSupplierDependentSections();
        self.debouncedRecalculate();
      } else {
        delete clickPriceInput[0]?.dataset?.manual;
        clickPriceInput.removeClass('border-primary');
        $.getJSON(`${self.config.urls.pressesApi}?supplier_id=${supplierId}&order_type=digital`, function (data) {
          if (data && data.success && data.presses && data.presses.length > 0) {
            let optionsHtml = '';
            data.presses.forEach((p, idx) => {
              const isSel = idx === 0 ? 'selected' : '';
              const colorP = p.price_per_page_color || p.price_per_1000 || 0;
              const bwP = p.price_per_page_bw || 0;
              optionsHtml += `<option value="${p.id}" data-price-color="${colorP}" data-price-bw="${bwP}" data-service-id="${p.service_id}" data-price-date="${p.price_updated_at || ''}" data-price-age="${p.price_age_days !== undefined ? p.price_age_days : ''}" data-staleness="${p.price_staleness_status || 'fresh'}" data-valid-until="${p.price_valid_until || ''}" ${isSel}>${p.name} (${self.formatMoney(colorP)})</option>`;
            });
            machineSelect.html(optionsHtml);
            const first = data.presses[0];
            const colorMode = $('#id_digital_color_mode').val() || '4_0';
            const isColor = colorMode.includes('4');
            const unitPrice = isColor ? (first.price_per_page_color || first.price_per_1000) : (first.price_per_page_bw || 0);
            clickPriceInput.val(unitPrice || '');
            clickPriceInput.attr('data-baseline-price', unitPrice || '');
            clickPriceInput.attr('data-supplier-id', supplierId);
            clickPriceInput.attr('data-service-id', first.service_id || '');
            $('#id_cover_digital_service_id').val(first.service_id || '');
            self.renderPriceStalenessBadge(
              first.price_updated_at,
              first.price_age_days,
              first.price_staleness_status,
              first.price_valid_until,
              $('#digital_price_staleness_badge'),
              null
            );
          } else {
            machineSelect.html('<option value="">-- لا توجد ماكينات ديجيتال مسجلة لهذا المورد --</option>');
            clickPriceInput.val('');
            clickPriceInput.removeAttr('data-baseline-price data-supplier-id data-service-id');
            $('#id_cover_digital_service_id').val('');
            self.clearPriceStalenessBadge($('#digital_price_staleness_badge'), null);
          }
          self.updateSupplierDependentSections();
          self.debouncedRecalculate();
        }).fail(() => {
          machineSelect.html('<option value="">-- فشل جلب ماكينات المورد --</option>');
          clickPriceInput.val('');
          clickPriceInput.removeAttr('data-baseline-price data-supplier-id data-service-id');
          $('#id_cover_digital_service_id').val('');
          self.clearPriceStalenessBadge($('#digital_price_staleness_badge'), null);
          self.updateSupplierDependentSections();
          self.debouncedRecalculate();
        });
      }
    });

    // تغيير ماكينة ديجيتال الغلاف أو نمط الألوان (تحديث السعر المعتمد لطبعة الشيت لحظياً)
    $(document).on('change', '#id_cover_digital_machine, #id_digital_color_mode', function () {
      const selectedOpt = $('#id_cover_digital_machine').find('option:selected');
      if (selectedOpt.length && selectedOpt.val()) {
        const colorMode = $('#id_digital_color_mode').val() || '4_0';
        const isColor = colorMode.includes('4');
        const priceColor = parseFloat(selectedOpt.data('price-color')) || 0;
        const priceBw = parseFloat(selectedOpt.data('price-bw')) || 0;
        const svcId = selectedOpt.data('service-id');
        const clickPriceInput = $('#id_digital_sheet_price');
        delete clickPriceInput[0]?.dataset?.manual;
        clickPriceInput.removeClass('border-primary');
        if (svcId) {
          $('#id_cover_digital_service_id').val(svcId);
          clickPriceInput.attr('data-service-id', svcId);
        }
        const unitP = isColor ? (priceColor || '') : (priceBw || '');
        clickPriceInput.val(unitP);
        clickPriceInput.attr('data-baseline-price', unitP);
        clickPriceInput.attr('data-supplier-id', $('#id_cover_digital_supplier').val() || '');
        self.renderPriceStalenessBadge(
          selectedOpt.data('price-date'),
          selectedOpt.data('price-age'),
          selectedOpt.data('staleness'),
          selectedOpt.data('valid-until'),
          $('#digital_price_staleness_badge'),
          null
        );
        self.updateSupplierDependentSections();
        self.debouncedRecalculate();
      }
    });

    // 4. مطبعة أوفست الداخلي — تحميل ماكينات ومواصفات المورد الفعلي
    $(document).on('change select2:select', '#id_inner_offset_supplier', function () {
      const supplierId = this.value;
      const machineSelect = $('#id_inner_press_machine');
      const pressRateInput = $('#id_inner_press_rate');

      // تنشيط القسم فورياً وبشكل متزامن بمجرد اختيار المورد
      self.updateSupplierDependentSections();

      if (!supplierId) {
        machineSelect.html('<option value="">-- اختر مطبعة الأوفست أولاً --</option>');
        pressRateInput.val('');
        pressRateInput.removeAttr('data-baseline-price data-supplier-id data-service-id');
        $('#id_inner_press_service_id').val('');
        delete pressRateInput[0]?.dataset?.manual;
        pressRateInput.removeClass('border-primary');
        self.clearPriceStalenessBadge($('#inner_press_rate_staleness_badge'), null);
        self.updateSupplierDependentSections();
        self.debouncedRecalculate();
      } else {
        delete pressRateInput[0]?.dataset?.manual;
        pressRateInput.removeClass('border-primary');
        $.getJSON(`${self.config.urls.pressesApi}?supplier_id=${supplierId}&order_type=offset`, function (data) {
          if (data && data.success && data.presses && data.presses.length > 0) {
            const currentBed = $('#id_inner_press_bed_size').val();
            let selectedIdx = 0;
            if (currentBed) {
              const matchIdx = data.presses.findIndex(p => (p.standard_bed_size === currentBed || p.bed_size === currentBed));
              if (matchIdx !== -1) selectedIdx = matchIdx;
            }

            machineSelect.html(self.renderPressOptionsHtml(data.presses, selectedIdx));
            const chosen = data.presses[selectedIdx];
            const chosenRate = chosen.price_per_1000 || '';
            pressRateInput.val(chosenRate);
            pressRateInput.attr('data-baseline-price', chosenRate);
            pressRateInput.attr('data-supplier-id', supplierId);
            pressRateInput.attr('data-service-id', chosen.service_id || '');
            $('#id_inner_press_service_id').val(chosen.service_id || '');
            self.renderPriceStalenessBadge(
              chosen.price_updated_at,
              chosen.price_age_days,
              chosen.price_staleness_status,
              chosen.price_valid_until,
              $('#inner_press_rate_staleness_badge'),
              null
            );
            const targetBed = chosen.standard_bed_size || chosen.bed_size;
            if (targetBed) $('#id_inner_press_bed_size').val(targetBed).trigger('change');
          } else {
            machineSelect.html('<option value="">-- لا توجد ماكينات مسجلة لهذا المورد --</option>');
            pressRateInput.val('');
            pressRateInput.removeAttr('data-baseline-price data-supplier-id data-service-id');
            $('#id_inner_press_service_id').val('');
            self.clearPriceStalenessBadge($('#inner_press_rate_staleness_badge'), null);
          }
          self.updateSupplierDependentSections();
          self.debouncedRecalculate();
        }).fail(() => {
          machineSelect.html('<option value="">-- فشل جلب ماكينات المورد --</option>');
          pressRateInput.val('');
          pressRateInput.removeAttr('data-baseline-price data-supplier-id data-service-id');
          $('#id_inner_press_service_id').val('');
          self.clearPriceStalenessBadge($('#inner_press_rate_staleness_badge'), null);
          self.updateSupplierDependentSections();
          self.debouncedRecalculate();
        });
      }
    });

    $(document).on('change', '#id_inner_press_machine', function () {
      const selectedOpt = $(this).find('option:selected');
      const optRate = selectedOpt.data('rate');
      const optBed = selectedOpt.data('std-bed') || selectedOpt.data('bed');
      const svcId = selectedOpt.data('service-id');
      const pressRateInput = $('#id_inner_press_rate');
      delete pressRateInput[0]?.dataset?.manual;
      pressRateInput.removeClass('border-primary');
      if (svcId) {
        $('#id_inner_press_service_id').val(svcId);
        pressRateInput.attr('data-service-id', svcId);
      }
      if (optRate !== undefined) {
        pressRateInput.val(optRate);
        pressRateInput.attr('data-baseline-price', optRate);
      }
      pressRateInput.attr('data-supplier-id', $('#id_inner_offset_supplier').val() || '');

      self.renderPriceStalenessBadge(
        selectedOpt.data('price-date'),
        selectedOpt.data('price-age'),
        selectedOpt.data('staleness'),
        selectedOpt.data('valid-until'),
        $('#inner_press_rate_staleness_badge'),
        null
      );

      if (optBed && $('#id_inner_press_bed_size').val() !== optBed) {
        const matchingPlate = $('#id_inner_press_bed_size').find(`option[value="${optBed}"], option[data-bed="${optBed}"]`);
        if (matchingPlate.length) {
          $('#id_inner_press_bed_size').val(matchingPlate.val()).trigger('change');
        }
      }
      self.updateSupplierDependentSections();
      self.debouncedRecalculate();
    });

    // 5. مكتب فصل زنكات الداخلي CTP
    $(document).on('change select2:select', '#id_inner_ctp_supplier', function () {
      const supplierId = this.value;
      const bedSize = $('#id_inner_press_bed_size').val() || $('#id_inner_press_bed_size option:selected').data('bed') || '';
      const platePriceInput = $('#id_inner_plate_price');

      // تنشيط القسم فورياً وبشكل متزامن بمجرد اختيار المورد
      self.updateSupplierDependentSections();

      if (supplierId) {
        delete platePriceInput[0]?.dataset?.manual;
        platePriceInput.removeClass('border-primary');
        $.getJSON(`${self.config.urls.pressesApi}?supplier_id=${supplierId}&order_type=ctp`, function (data) {
          if (data && data.success && data.presses && data.presses.length > 0) {
            let matched = data.presses.find(p => (p.standard_bed_size === bedSize || p.bed_size === bedSize));
            if (matched) {
              const matchedRate = matched.price_per_1000 || '';
              platePriceInput.val(matchedRate);
              platePriceInput.attr('data-baseline-price', matchedRate);
              platePriceInput.attr('data-supplier-id', supplierId);
              platePriceInput.attr('data-service-id', matched.service_id || '');
              platePriceInput.attr('data-set-price', matched.set_price || 0);
              $('#id_inner_ctp_service_id').val(matched.service_id || '');
              self.renderPriceStalenessBadge(
                matched.price_updated_at,
                matched.price_age_days,
                matched.price_staleness_status,
                matched.price_valid_until,
                $('#inner_plate_price_staleness_badge'),
                null
              );
            } else {
              platePriceInput.val('').removeAttr('data-set-price data-baseline-price data-supplier-id data-service-id');
              $('#id_inner_ctp_service_id').val('');
              self.clearPriceStalenessBadge($('#inner_plate_price_staleness_badge'), null);
            }
          } else {
            platePriceInput.val('').removeAttr('data-set-price data-baseline-price data-supplier-id data-service-id');
            $('#id_inner_ctp_service_id').val('');
            self.clearPriceStalenessBadge($('#inner_plate_price_staleness_badge'), null);
          }
          self.updateInnerPlatesUI();
          self.updateSupplierDependentSections();
          self.debouncedRecalculate();
        }).fail(() => {
          platePriceInput.val('').removeAttr('data-set-price data-baseline-price data-supplier-id data-service-id');
          $('#id_inner_ctp_service_id').val('');
          self.clearPriceStalenessBadge($('#inner_plate_price_staleness_badge'), null);
          self.updateInnerPlatesUI();
          self.updateSupplierDependentSections();
          self.debouncedRecalculate();
        });
      } else {
        platePriceInput.val('').removeAttr('data-set-price data-baseline-price data-supplier-id data-service-id');
        $('#id_inner_ctp_service_id').val('');
        delete platePriceInput[0]?.dataset?.manual;
        platePriceInput.removeClass('border-primary');
        self.clearPriceStalenessBadge($('#inner_plate_price_staleness_badge'), null);
        self.updateInnerPlatesUI();
        self.updateSupplierDependentSections();
        self.debouncedRecalculate();
      }
    });

    // 6. مركز ديجيتال الداخلي — جلب ماكينات المورد وتحديث أسعار طبعات الألوان والأسود بناءً على ماكينة المورد
    $(document).on('change select2:select', '#id_inner_digital_supplier', function () {
      const supplierId = this.value;
      const machineSelect = $('#id_inner_digital_machine');
      const colorPriceInput = $('#id_digital_inner_color_price');
      const bwPriceInput = $('#id_digital_inner_bw_price');

      // تنشيط القسم فورياً وبشكل متزامن بمجرد اختيار المورد
      self.updateSupplierDependentSections();

      if (!supplierId) {
        machineSelect.html('<option value="">-- اختر مركز الديجيتال أولاً --</option>');
        colorPriceInput.val('');
        bwPriceInput.val('');
        colorPriceInput.removeAttr('data-baseline-price data-supplier-id data-service-id');
        bwPriceInput.removeAttr('data-baseline-price data-supplier-id data-service-id');
        $('#id_inner_digital_service_id').val('');
        delete colorPriceInput[0]?.dataset?.manual;
        delete bwPriceInput[0]?.dataset?.manual;
        colorPriceInput.removeClass('border-primary');
        bwPriceInput.removeClass('border-primary');
        self.updateSupplierDependentSections();
        self.debouncedRecalculate();
      } else {
        delete colorPriceInput[0]?.dataset?.manual;
        delete bwPriceInput[0]?.dataset?.manual;
        colorPriceInput.removeClass('border-primary');
        bwPriceInput.removeClass('border-primary');
        $.getJSON(`${self.config.urls.pressesApi}?supplier_id=${supplierId}&order_type=digital`, function (data) {
          if (data && data.success && data.presses && data.presses.length > 0) {
            let optionsHtml = '';
            data.presses.forEach((p, idx) => {
              const isSel = idx === 0 ? 'selected' : '';
              const colorP = p.price_per_page_color || p.price_per_1000 || 0;
              const bwP = p.price_per_page_bw || 0;
              optionsHtml += `<option value="${p.id}" data-price-color="${colorP}" data-price-bw="${bwP}" data-service-id="${p.service_id}" ${isSel}>${p.name}</option>`;
            });
            machineSelect.html(optionsHtml);
            const first = data.presses[0];
            const colorPrice = first.price_per_page_color || first.price_per_1000 || '';
            const bwPrice = first.price_per_page_bw || '';
            colorPriceInput.val(colorPrice);
            colorPriceInput.attr('data-baseline-price', colorPrice);
            colorPriceInput.attr('data-supplier-id', supplierId);
            colorPriceInput.attr('data-service-id', first.service_id || '');

            bwPriceInput.val(bwPrice);
            bwPriceInput.attr('data-baseline-price', bwPrice);
            bwPriceInput.attr('data-supplier-id', supplierId);
            bwPriceInput.attr('data-service-id', first.service_id || '');
            $('#id_inner_digital_service_id').val(first.service_id || '');
          } else {
            machineSelect.html('<option value="">-- لا توجد ماكينات ديجيتال مسجلة لهذا المورد --</option>');
            colorPriceInput.val('');
            bwPriceInput.val('');
            colorPriceInput.removeAttr('data-baseline-price data-supplier-id data-service-id');
            bwPriceInput.removeAttr('data-baseline-price data-supplier-id data-service-id');
            $('#id_inner_digital_service_id').val('');
          }
          self.updateSupplierDependentSections();
          self.debouncedRecalculate();
        }).fail(() => {
          machineSelect.html('<option value="">-- فشل جلب ماكينات المورد --</option>');
          colorPriceInput.val('');
          bwPriceInput.val('');
          colorPriceInput.removeAttr('data-baseline-price data-supplier-id data-service-id');
          bwPriceInput.removeAttr('data-baseline-price data-supplier-id data-service-id');
          $('#id_inner_digital_service_id').val('');
          self.updateSupplierDependentSections();
          self.debouncedRecalculate();
        });
      }
    });

    $(document).on('change', '#id_inner_digital_machine', function () {
      const selectedOpt = $(this).find('option:selected');
      if (selectedOpt.length && selectedOpt.val()) {
        const priceColor = parseFloat(selectedOpt.data('price-color')) || 0;
        const priceBw = parseFloat(selectedOpt.data('price-bw')) || 0;
        const svcId = selectedOpt.data('service-id');
        const colorInput = $('#id_digital_inner_color_price');
        const bwInput = $('#id_digital_inner_bw_price');
        delete colorInput[0]?.dataset?.manual;
        delete bwInput[0]?.dataset?.manual;
        colorInput.removeClass('border-primary');
        bwInput.removeClass('border-primary');
        if (svcId) {
          $('#id_inner_digital_service_id').val(svcId);
          colorInput.attr('data-service-id', svcId);
          bwInput.attr('data-service-id', svcId);
        }
        colorInput.val(priceColor || '');
        colorInput.attr('data-baseline-price', priceColor || '');
        colorInput.attr('data-supplier-id', $('#id_inner_digital_supplier').val() || '');

        bwInput.val(priceBw || '');
        bwInput.attr('data-baseline-price', priceBw || '');
        bwInput.attr('data-supplier-id', $('#id_inner_digital_supplier').val() || '');

        self.updateSupplierDependentSections();
        self.debouncedRecalculate();
      }
    });

    // مزامنة زنكات الغلاف والداخلي عند تغيير مقاس سرير الماكينة
    $(document).on('change', '#id_press_bed_size', function () {
      if ($('#id_cover_ctp_supplier').val()) {
        $('#id_cover_ctp_supplier').trigger('change');
      } else {
        self.updateCoverPlatesUI();
      }
    });

    $(document).on('change', '#id_inner_press_bed_size', function () {
      if ($('#id_inner_ctp_supplier').val()) {
        $('#id_inner_ctp_supplier').trigger('change');
      } else {
        self.updateInnerPlatesUI();
      }
    });

    // مزامنة حالة زنكات الغلاف والداخلي عند تبديل حالة الحفظ بالأرشيف
    $(document).on('change', '#id_is_plates_archived, #id_plates_option', function () {
      self.updateCoverPlatesUI();
      self.updateSupplierDependentSections();
      self.debouncedRecalculate();
    });

    $(document).on('change', '#id_is_inner_plates_archived, #id_inner_plates_option', function () {
      self.updateInnerPlatesUI();
      self.updateSupplierDependentSections();
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

    // نسخ شارات صلاحية وحداثة السعر لماكينة الطباعة والزنكات
    const $covPressBadge = $('#press_rate_staleness_badge');
    const $inPressBadge = $('#inner_press_rate_staleness_badge');
    if ($covPressBadge.length && !$covPressBadge.hasClass('d-none')) {
      $inPressBadge.attr('class', $covPressBadge.attr('class')).attr('title', $covPressBadge.attr('title')).html($covPressBadge.html());
    }

    const $covPlateBadge = $('#plate_price_staleness_badge');
    const $inPlateBadge = $('#inner_plate_price_staleness_badge');
    if ($covPlateBadge.length && !$covPlateBadge.hasClass('d-none')) {
      $inPlateBadge.attr('class', $covPlateBadge.attr('class')).attr('title', $covPlateBadge.attr('title')).html($covPlateBadge.html());
    }

    this.debouncedRecalculate();
    this.showNotification('تم نسخ مطبعة ومقاس وإعدادات الغلاف إلى صفحات الداخلي بنجاح', 'success');
  }

  /**
   * التطبيق السريع لكافة الموردين المعتمدين المتوافقين بنقرة واحدة
   */
  applyPreferredSuppliers() {
    // 1. مطبعة الأوفست المعتمدة
    const $offset = $('#id_cover_offset_supplier');
    const $optOffset = $offset.find('option[data-preferred="true"]').first();
    if ($optOffset.length && $offset.val() !== $optOffset.val()) {
      $offset.val($optOffset.val()).trigger('change');
    }

    // 2. مكتب فصل زنكات CTP المعتمد
    const $ctp = $('#id_cover_ctp_supplier');
    const $optCtp = $ctp.find('option[data-preferred="true"]').first();
    if ($optCtp.length && $ctp.val() !== $optCtp.val()) {
      $ctp.val($optCtp.val()).trigger('change');
    }

    // 3. تاجر الورق المعتمد
    const $paper = $('#id_paper_supplier');
    const $optPaper = $paper.find('option[data-preferred="true"]').first();
    if ($optPaper.length && $paper.val() !== $optPaper.val()) {
      $paper.val($optPaper.val()).trigger('change');
    }

    // 4. مركز الديجيتال المعتمد
    const $digital = $('#id_cover_digital_supplier');
    const $optDig = $digital.find('option[data-preferred="true"]').first();
    if ($optDig.length && $digital.val() !== $optDig.val()) {
      $digital.val($optDig.val()).trigger('change');
    }

    // موردو الداخلي
    const $inOffset = $('#id_inner_offset_supplier');
    const $optInOffset = $inOffset.find('option[data-preferred="true"]').first();
    if ($optInOffset.length && $inOffset.val() !== $optInOffset.val()) {
      $inOffset.val($optInOffset.val()).trigger('change');
    }

    const $inCtp = $('#id_inner_ctp_supplier');
    const $optInCtp = $inCtp.find('option[data-preferred="true"]').first();
    if ($optInCtp.length && $inCtp.val() !== $optInCtp.val()) {
      $inCtp.val($optInCtp.val()).trigger('change');
    }

    const $inPaper = $('#id_inner_paper_supplier');
    const $optInPaper = $inPaper.find('option[data-preferred="true"]').first();
    if ($optInPaper.length && $inPaper.val() !== $optInPaper.val()) {
      $inPaper.val($optInPaper.val()).trigger('change');
    }

    const $inDig = $('#id_inner_digital_supplier');
    const $optInDig = $inDig.find('option[data-preferred="true"]').first();
    if ($optInDig.length && $inDig.val() !== $optInDig.val()) {
      $inDig.val($optInDig.val()).trigger('change');
    }

    this.showNotification('تم تطبيق حزمة الموردين المعتمدين وجاري جلب أسعار مواصفات أمر الطباعة', 'success');
    this.debouncedRecalculate();
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
        priceInput.prop('readonly', true).val('0.00').addClass('bg-light text-muted');
        $('#paper_price_mode_label').text('خامة توريد العميل');
        self.showNotification(`تم تحديد خامة توريد العميل: سيتم احتساب تكلفة الورق كـ 0.00 ${self.config.currencySymbol} كشغل مصنعية مع استمرار حساب الأفرخ لإذن الاستلام`, 'info');
      } else {
        priceInput.prop('readonly', false).removeClass('bg-light text-muted');
        $('#paper_price_mode_label').text('سعر الفرخ');
        if ($('#id_paper_supplier').val()) {
          self.fetchLivePaperPrice();
        }
      }
      self.updateSupplierDependentSections();
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

    $(document).on('change', '#id_piece_size', function () {
      if (self.isSyncingFields) return;
      self.isManualMontage = false; // تصفير التعديل اليدوي لاحتساب السقف الجديد لمقاس القطع المختار
      const selected = $(this).find('option:selected');
      const cuts = PricingMath.parseSafeNumber(selected.data('cuts'), 0);
      const machineSelect = $('#id_cover_press_machine');
      const plateSelect = $('#id_press_bed_size');

      self.isSyncingFields = true;
      const pW = PricingMath.parseSafeNumber(selected.data('width'), 0);
      const pH = PricingMath.parseSafeNumber(selected.data('height'), 0);
      if (pW && pH && plateSelect.length) {
        const pieceMin = Math.min(pW, pH);
        const pieceMax = Math.max(pW, pH);

        let bestPlateVal = null;
        let minAreaDiff = Infinity;

        plateSelect.find('option').each(function () {
          const $opt = $(this);
          const optVal = $opt.val();
          if (!optVal) return;
          const optText = $opt.text();
          const match = optText.match(/(\d+(?:\.\d+)?)\s*[×xX*]\s*(\d+(?:\.\d+)?)/);
          if (match) {
            const bW = parseFloat(match[1]);
            const bH = parseFloat(match[2]);
            const bedMin = Math.min(bW, bH);
            const bedMax = Math.max(bW, bH);
            if (bedMin >= pieceMin - 1.0 && bedMax >= pieceMax - 1.0) {
              const diff = (bedMin * bedMax) - (pieceMin * pieceMax);
              if (diff >= 0 && diff < minAreaDiff) {
                minAreaDiff = diff;
                bestPlateVal = optVal;
              }
            }
          }
        });

        if (bestPlateVal && plateSelect.val() !== bestPlateVal) {
          plateSelect.val(bestPlateVal).trigger('change.select2');
        }
      }
      self.isSyncingFields = false;

      self.currentPieceName = self.getCleanPieceName();
      self.debouncedRecalculate(50);
    });



    // 6. منظومة تدفق كارت الورق الذكية المتتالية (Smart Cascading Without Circular Loop)
    $(document).on('change', '#id_paper_type', function (e) {
      if (self.isPaperCascadeUpdating) return;
      self.handlePaperTypeChange(true);
    });

    $(document).on('change select2:select', '#id_paper_supplier', function (e) {
      self.updateSupplierDependentSections();
      if (self.isPaperCascadeUpdating) return;
      self.handlePaperSupplierChange(true, true);
    });

    $(document).on('change', '#id_sheet_size', function (e) {
      if (self.isPaperCascadeUpdating) return;
      self.handleSheetSizeChange(true);
    });

    $(document).on('change', '#id_paper_weight', function (e) {
      if (self.isPaperCascadeUpdating) return;
      self.handlePaperWeightChange(true);
    });

    $(document).on('change', '#id_paper_origin', function () {
      if (self.isPaperCascadeUpdating || self.isSyncingOrigin) return;
      self.fetchLivePaperPrice();
      self.debouncedRecalculate(50);
    });

    // تبديل وضع عدد الأفرخ (يدوي / تلقائي) - الحقل السابع
    $(document).on('click', '#btn_toggle_manual_sheets', function () {
      self.toggleManualGrossSheets();
    });

    $(document).on('input', '#id_manual_gross_sheets', function () {
      self.manualGrossSheets = PricingMath.parseSafeNumber($(this).val(), 0);
      self.debouncedRecalculate(250);
    });

    // تحديث سعة رزمة الداخلي وموردي خامة الداخلي عند تغيير ورق أو جراماج الداخلي
    $(document).on('change', '#id_inner_paper_type', function () {
      self.updateResolvedInnerPackCapacity(false, 'type');
      if (this.value) {
        self.updateSuppliersForPaperType(this.value, '#id_inner_paper_supplier', true);
      }
      self.fetchLivePaperPrice({}, true);
      self.debouncedRecalculate(50);
    });

    $(document).on('change', '#id_inner_paper_weight', function () {
      self.updateResolvedInnerPackCapacity(false, 'weight');
      self.fetchLivePaperPrice({}, true);
      self.debouncedRecalculate(50);
    });

    $(document).on('change select2:select', '#id_inner_paper_supplier', function () {
      if (!this.value && !$('#id_inner_sheet_price')[0]?.dataset?.manual) {
        $('#id_inner_sheet_price').val('0.00');
        $('#id_inner_sheet_price').removeAttr('data-baseline-price data-supplier-id data-service-id');
      }
      if (self.config.urls && self.config.urls.paperTypesApi) {
        self.updatePaperTypesForSupplier(this.value, '#id_inner_paper_type');
      }
      self.fetchLivePaperPrice({}, true);
      self.updateSupplierDependentSections();
      self.debouncedRecalculate(50);
    });

    $(document).on('change', '#id_inner_sheet_size', function () {
      self.fetchLivePaperPrice({}, true);
      self.debouncedRecalculate(50);
    });

    // 7. نسخ خامة ومورد ومقاس الغلاف إلى الداخلي
    $(document).on('click', '#btn_copy_cover_paper_to_inner', function () {
      const coverSup = $('#id_paper_supplier').val();
      const coverType = $('#id_paper_type').val();
      const coverSheetSize = $('#id_sheet_size').val();
      const coverWeight = $('#id_paper_weight').val();
      const coverPrice = $('#id_paper_sheet_price').val();
      const coverBaseline = $('#id_paper_sheet_price').attr('data-baseline-price');
      const coverServiceId = $('#id_paper_sheet_price').attr('data-service-id');

      if (coverSup) $('#id_inner_paper_supplier').val(coverSup).trigger('change');
      if (coverType) $('#id_inner_paper_type').val(coverType).trigger('change');
      if (coverSheetSize) $('#id_inner_sheet_size').val(coverSheetSize).trigger('change');
      if (coverWeight) $('#id_inner_paper_weight').val(coverWeight).trigger('change');
      if (coverPrice) {
        const $inPaper = $('#id_inner_sheet_price');
        $inPaper.val(coverPrice);
        if (coverBaseline) $inPaper.attr('data-baseline-price', coverBaseline);
        if (coverSup) $inPaper.attr('data-supplier-id', coverSup);
        if (coverServiceId) $inPaper.attr('data-service-id', coverServiceId);
      }

      // نسخ شارة تاريخ وحالة سعر الورق إلى ورق الداخلي
      const $covBadge = $('#paper_price_staleness_badge');
      const $covDate = $('#paper_price_date_display');
      const $inBadge = $('#inner_paper_price_staleness_badge');
      const $inDate = $('#inner_paper_price_date_display');
      if ($covBadge.length && !$covBadge.hasClass('d-none')) {
        $inBadge.attr('class', $covBadge.attr('class')).attr('title', $covBadge.attr('title')).html($covBadge.html());
        if ($covDate.length && !$covDate.hasClass('d-none')) {
          $inDate.attr('class', $covDate.attr('class')).html($covDate.html());
        }
      }

      self.recalculate();
      self.showNotification('تم نسخ خامة ومقاس ومورد الغلاف إلى كارت الداخلي بنجاح', 'success');
    });

    // مراقبة التعديل اليدوي لحقول الأسعار للاستيقاظ من الخمول فوراً وعرض شارة السعر المخصص
    $(document).on('input change', '#id_paper_sheet_price, #id_press_rate, #id_plate_price, #id_digital_sheet_price, #id_inner_sheet_price, #id_inner_press_rate, #id_inner_plate_price, #id_digital_inner_color_price, #id_digital_inner_bw_price', function () {
      const val = parseFloat($(this).val()) || 0;
      const inputId = this.id;
      let badgeSel = null;
      let dateSel = null;
      if (inputId === 'id_paper_sheet_price') { badgeSel = '#paper_price_staleness_badge'; dateSel = '#paper_price_date_display'; }
      else if (inputId === 'id_press_rate') { badgeSel = '#press_rate_staleness_badge'; }
      else if (inputId === 'id_plate_price') { badgeSel = '#plate_price_staleness_badge'; }
      else if (inputId === 'id_digital_sheet_price') { badgeSel = '#digital_price_staleness_badge'; }
      else if (inputId === 'id_inner_sheet_price') { badgeSel = '#inner_paper_price_staleness_badge'; dateSel = '#inner_paper_price_date_display'; }
      else if (inputId === 'id_inner_press_rate') { badgeSel = '#inner_press_rate_staleness_badge'; }
      else if (inputId === 'id_inner_plate_price') { badgeSel = '#inner_plate_price_staleness_badge'; }

      if (val > 0) {
        this.dataset.manual = 'true';
        $(this).addClass('border-primary');
        if (badgeSel) self.renderManualPriceBadge($(badgeSel), dateSel ? $(dateSel) : null);
      } else {
        delete this.dataset.manual;
        $(this).removeClass('border-primary');
        if (badgeSel) self.clearPriceStalenessBadge($(badgeSel), dateSel ? $(dateSel) : null);
      }
      self.updateSupplierDependentSections();
      self.debouncedRecalculate();
    });
  }

  /**
   * دالة مساعدة لتحديث خيارات Select2 بأمان دون تدمير الـ DOM وتجنب الحلقات الدائرية
   */
  syncSelect2Options($select, options, selectedValue) {
    if (!$select || !$select.length) return;
    const currentVal = (selectedValue !== undefined && selectedValue !== null) ? selectedValue : $select.val();
    $select.empty();
    options.forEach(opt => {
      const isSel = (String(opt.value) === String(currentVal));
      const newOpt = new Option(opt.text, opt.value, isSel, isSel);
      if (opt.data) {
        Object.entries(opt.data).forEach(([k, v]) => $(newOpt).attr(`data-${k}`, v));
      }
      $select.append(newOpt);
    });
    $select.trigger('change.select2');
  }

  /**
   * تحديث قائمة خامات الورق لتقتصر على ما يوفره المورد المختار حصراً
   */
  updatePaperTypesForSupplier(supplierId, targetSelectId = '#id_paper_type') {
    const self = this;
    const $select = $(targetSelectId);
    if (!$select.length || !this.api) return;
    const currentVal = $select.val();

    this.api.getPaperTypes(supplierId)
      .then(data => {
        if (!data || !data.success || !data.paper_types) return;
        const types = data.paper_types;
        if (types.length === 0) return;

        const opts = self.api.formatPaperTypeOptions(types);

        const exists = types.some(t => String(t.id) === String(currentVal));
        const targetVal = exists ? currentVal : types[0].id;

        self.isPaperCascadeUpdating = true;
        self.syncSelect2Options($select, opts, targetVal);
        self.isPaperCascadeUpdating = false;

        if (!exists && targetSelectId === '#id_paper_type') {
          self.updateResolvedPackCapacity(false, 'type');
          self.debouncedRecalculate(50);
        } else if (!exists && targetSelectId === '#id_inner_paper_type') {
          self.updateResolvedInnerPackCapacity(false, 'type');
          self.debouncedRecalculate(50);
        }
      })
      .catch(err => console.warn('Error fetching paper types for supplier:', err));
  }

  /**
   * تحديث قائمة موردي الورق لتقتصر حصراً على الموردين الذين يوفرون نوع الورق المختار
   */
  updateSuppliersForPaperType(paperTypeId, targetSelectId = '#id_paper_supplier', userDriven = false) {
    const self = this;
    const $select = $(targetSelectId);
    if (!$select.length || !this.api) return;
    const currentVal = $select.val();

    if (!paperTypeId) {
      if (targetSelectId === '#id_paper_supplier') self.resetPaperCascade();
      return;
    }

    this.api.getPaperSuppliers(paperTypeId)
      .then(data => {
        if (!data || !data.success) return;
        const suppliers = data.suppliers || [];
        const opts = self.api.formatSupplierOptions(suppliers);

        // الاحتفاظ بالمورد المختار إن كان ضمن موفري الخامة، وإلا اختيار أول مورد (أو المفضل)
        const retainsCurrent = suppliers.some(s => String(s.id) === String(currentVal));
        let targetSup = '';
        if (retainsCurrent) {
          targetSup = currentVal;
        } else if (suppliers.length > 0) {
          const pref = suppliers.find(s => s.is_preferred);
          targetSup = pref ? pref.id : suppliers[0].id;
        }

        self.isPaperCascadeUpdating = true;
        self.syncSelect2Options($select, opts, targetSup);
        self.isPaperCascadeUpdating = false;

        if (targetSelectId === '#id_paper_supplier') {
          if (targetSup) {
            self.handlePaperSupplierChange(userDriven, false);
          } else {
            self.resetPaperCascade();
          }
        }
      })
      .catch(err => {
        console.warn('Error fetching paper suppliers:', err);
      });
  }

  /**
   * الحقل 1: معالجة تغيير نوع الورق وجلب الموردين المتاح لديهم هذه الخامة حصراً
   */
  handlePaperTypeChange(userDriven = false) {
    if (this.isPaperCascadeUpdating) return;
    const paperTypeId = $('#id_paper_type').val();

    if (!paperTypeId) {
      this.resetPaperCascade();
      return;
    }

    this.updateSuppliersForPaperType(paperTypeId, '#id_paper_supplier', userDriven);
    this.updateResolvedPackCapacity(false, 'type');
    this.debouncedRecalculate();
  }

  /**
   * الحقل 2: معالجة اختيار مورد الورق وجلب مقاسات الفرخ المتوفرة لديه
   */
  handlePaperSupplierChange(userDriven = false, isSupplierDirectChange = false) {
    this.updateSupplierDependentSections();
    if (this.isPaperCascadeUpdating) return;
    const self = this;
    const supplierId = $('#id_paper_supplier').val();
    const paperTypeId = $('#id_paper_type').val();
    const paperSource = $('input[name="paper_source"]:checked').val() || 'purchase';

    // إذا تم اختيار المورد مباشرة من قبل المستخدم، نقوم بتحديث خامات الورق المتاحة لديه
    if (isSupplierDirectChange && this.config.urls && this.config.urls.paperTypesApi) {
      this.updatePaperTypesForSupplier(supplierId, '#id_paper_type');
    }

    // فحص أمر الشراء اليتيم (Orphaned PO Guard)
    if (paperSource === 'purchase' && !supplierId) {
      $('#paper_supplier_note').html('<span class="text-warning"><i class="fas fa-exclamation-circle me-1"></i>تنبيه: يلزم تحديد المورد لتوليد أمر الشراء (PO) آلياً</span>');
    } else {
      $('#paper_supplier_note').text('ترشيح التجار الموفرين للخامة المحددة أولاً');
    }

    if (!supplierId && paperSource === 'purchase') {
      const $sheetSelect = $('#id_sheet_size');
      const $weightSelect = $('#id_paper_weight');
      const $originSelect = $('#id_paper_origin');
      self.isPaperCascadeUpdating = true;
      self.syncSelect2Options($sheetSelect, [{ value: '', text: '-- يلزم ملء المورد والورق أولاً --' }], '');
      self.syncSelect2Options($weightSelect, [{ value: '', text: '-- يلزم ملء المورد والورق أولاً --' }], '');
      self.syncSelect2Options($originSelect, [{ value: '', text: '-- يتحدد تلقائياً حسب خامة المورد --' }], '');
      self.isPaperCascadeUpdating = false;
      $('#id_paper_sheet_price').val('0.00');
      delete $('#id_paper_sheet_price')[0]?.dataset?.manual;
      $('#id_paper_sheet_price').removeClass('border-primary');
      $('#paper_origin_note').text('يتزامن تلقائياً مع بلد منشأ خامة المورد');
      self.updateSupplierDependentSections();
      self.recalculate();
      return;
    }

    // جلب مقاسات الفرخ بناءً على المورد والورق
    if (this.api) {
      this.api.getSheetSizes(supplierId, paperTypeId, paperSource)
        .then(data => {
          if (!data || !data.success) return;
          const sheetTypes = data.sheet_types || [];
          const $sheetSelect = $('#id_sheet_size');
          const currentSheetVal = $sheetSelect.val();

          if (sheetTypes.length === 0) {
            self.isPaperCascadeUpdating = true;
            self.syncSelect2Options($sheetSelect, [{ value: '', text: '-- لا توجد مقاسات مسجلة لهذا المورد --' }], '');
            self.isPaperCascadeUpdating = false;
            return;
          }

          const opts = self.api.formatSheetSizeOptions(sheetTypes);

          const retainsCurrent = sheetTypes.some(st => (st.sheet_size === currentSheetVal || st.sheet_type === currentSheetVal));
          const targetSheet = retainsCurrent ? currentSheetVal : (sheetTypes[0].sheet_size || sheetTypes[0].sheet_type);

          self.isPaperCascadeUpdating = true;
          self.syncSelect2Options($sheetSelect, opts, targetSheet);
          self.isPaperCascadeUpdating = false;

          if (targetSheet) {
            self.handleSheetSizeChange(userDriven);
          }
        })
        .catch(err => {
          if (err.name !== 'AbortError') console.warn('Error fetching sheet sizes:', err);
        });
    }

    this.updateSupplierDependentSections();
    this.debouncedRecalculate();
  }

  /**
   * تهيئة القائمة الأم لمقاسات القطع من الـ DOM
   */
  initPieceSizesMasterList() {
    if (this.masterPieceSizes && this.masterPieceSizes.length > 0) return;
    const $pieceSelect = $('#id_piece_size');
    if (!$pieceSelect.length) return;
    this.masterPieceSizes = [];
    $pieceSelect.find('option').each((idx, el) => {
      const $el = $(el);
      const val = $el.val();
      if (!val || val === 'auto') return;
      this.masterPieceSizes.push({
        value: val,
        text: $el.text().trim(),
        name: $el.data('name') || '',
        cuts: parseInt($el.data('cuts')) || 1,
        width: parseFloat($el.data('width')) || 0,
        height: parseFloat($el.data('height')) || 0,
        paperType: String($el.data('paper-type') || ''),
        paperWidth: parseFloat($el.data('paper-width')) || 0,
        paperHeight: parseFloat($el.data('paper-height')) || 0,
        isDefault: $el.data('is-default') === true || $el.data('is-default') === 'true' || $el.attr('data-is-default') === 'true',
        sortOrder: parseInt($el.data('sort-order')) || 0
      });
    });
  }

  /**
   * فلترة وتحديث خيارات مقاس القطع لتناسب حصراً مقاس الفرخ المختار
   * مع تطبيق شجرة الاختيار الذكي المتزن (Smart Best-Fit Hierarchy)
   */
  /**
   * فلترة وتحديث خيارات مقاس القطع لتناسب حصراً مقاس الفرخ المختار
   * ديناميكي 100% استناداً إلى المقاس الافتراضي (is_default) المخصص للفرخ في قاعدة البيانات
   */
  updatePieceSizesForSheet(sheetSize, sheetSizeId, sheetW, sheetH) {
    const self = this;
    const $pieceSelect = $('#id_piece_size');
    if (!$pieceSelect.length) return;

    this.initPieceSizesMasterList();

    const currentPieceVal = $pieceSelect.val();
    const sheetIdStr = String(sheetSizeId || '');
    let sW = parseFloat(sheetW) || 0;
    let sH = parseFloat(sheetH) || 0;
    if (!sW || !sH) {
      const match = String(sheetSize).match(/(\d+(?:\.\d+)?)\s*[×xX*]\s*(\d+(?:\.\d+)?)/);
      if (match) {
        sW = parseFloat(match[1]);
        sH = parseFloat(match[2]);
      }
    }
    const minSW = (sW > 0 && sH > 0) ? Math.min(sW, sH) : 0;
    const maxSW = (sW > 0 && sH > 0) ? Math.max(sW, sH) : 0;

    let matched = [];
    if (this.masterPieceSizes && this.masterPieceSizes.length > 0) {
      matched = this.masterPieceSizes.filter(item => {
        // إذا كان مقاس شيت عام
        if (!item.paperType && !item.paperWidth && !item.paperHeight) return true;
        // تطابق بالـ ID المباشر لمقاس الفرخ الخام
        if (sheetIdStr && item.paperType === sheetIdStr) return true;
        // تطابق بالأبعاد الهندسية المتبادلة
        if (minSW > 0 && maxSW > 0 && item.paperWidth > 0 && item.paperHeight > 0) {
          const itemMin = Math.min(item.paperWidth, item.paperHeight);
          const itemMax = Math.max(item.paperWidth, item.paperHeight);
          if (Math.abs(itemMin - minSW) < 1.0 && Math.abs(itemMax - maxSW) < 1.0) return true;
        }
        return false;
      });
    }

    // ترتيب العناصر ديناميكياً بحيث يتصدر المقاس الافتراضي (is_default) ثم الترتيب (sort_order)
    matched.sort((a, b) => {
      if (a.isDefault && !b.isDefault) return -1;
      if (!a.isDefault && b.isDefault) return 1;
      return (a.sortOrder || 0) - (b.sortOrder || 0);
    });

    const opts = [];
    matched.forEach(item => {
      opts.push({
        value: item.value,
        text: item.text,
        data: {
          name: item.name,
          cuts: item.cuts,
          width: item.width,
          height: item.height,
          'paper-type': item.paperType,
          'paper-width': item.paperWidth,
          'paper-height': item.paperHeight,
          'is-default': item.isDefault ? 'true' : 'false'
        }
      });
    });

    // الاختيار الديناميكي النقي 100%:
    // 1. الاحتفاظ باختيار المسعر إن كان صالحاً ضمن مقاسات الفرخ
    // 2. اختيار المقاس الافتراضي (is_default) المحدد لهذا الفرخ في قاعدة البيانات
    // 3. أول مقاس متاح وفق الترتيب (sort_order) كصمام أمان
    let targetPiece = '';
    const retainsCurrent = currentPieceVal && currentPieceVal !== 'auto' && matched.some(m => String(m.value) === String(currentPieceVal));

    if (retainsCurrent) {
      targetPiece = currentPieceVal;
    } else {
      const defaultItem = matched.find(m => m.isDefault);
      targetPiece = defaultItem ? defaultItem.value : (matched[0]?.value || '');
    }

    self.syncSelect2Options($pieceSelect, opts, targetPiece);

    // التحقق من توافر API مقاسات الشيت لجلب أي مقاسات مضافة حديثاً في قاعدة البيانات
    if (this.api) {
      this.api.getPieceSizes(sheetSize, sheetSizeId)
        .then(data => {
          if (data && data.success && data.piece_sizes && data.piece_sizes.length > 0) {
            const apiOpts = [];
            data.piece_sizes.forEach(ps => {
              apiOpts.push({
                value: ps.id,
                text: ps.display_name,
                data: {
                  name: ps.name,
                  cuts: ps.pieces_per_sheet || 1,
                  width: ps.width,
                  height: ps.height,
                  'paper-type': ps.paper_type_id || '',
                  'is-default': ps.is_default ? 'true' : 'false'
                }
              });
            });

            const currentVal = $pieceSelect.val();
            const stillValid = currentVal && currentVal !== 'auto' && data.piece_sizes.some(p => String(p.id) === String(currentVal));
            let nextTarget = '';

            if (stillValid) {
              nextTarget = currentVal;
            } else {
              const def = data.piece_sizes.find(p => p.is_default);
              nextTarget = def ? def.id : (data.piece_sizes[0]?.id || '');
            }
            self.syncSelect2Options($pieceSelect, apiOpts, nextTarget);
          }
        })
        .catch(e => { /* fallback to matched client list */ });
    }
  }

  /**
   * الحقل 3: معالجة مقاس الفرخ وجلب الأوزان المتاحة واقتراح مقاس القطع
   */
  handleSheetSizeChange(userDriven = false) {
    if (this.isPaperCascadeUpdating) return;
    const self = this;
    const supplierId = $('#id_paper_supplier').val();
    const paperTypeId = $('#id_paper_type').val();
    const sheetSize = $('#id_sheet_size').val();
    const sheetOpt = $('#id_sheet_size option:selected');
    const sheetSizeId = sheetOpt.data('id') || sheetOpt.attr('data-id') || '';
    const sheetW = sheetOpt.data('width') || sheetOpt.attr('data-width') || '';
    const sheetH = sheetOpt.data('height') || sheetOpt.attr('data-height') || '';

    // تحديث مقاسات القطع المتماشية مع مقاس الفرخ
    this.updatePieceSizesForSheet(sheetSize, sheetSizeId, sheetW, sheetH);

    // تحديث المعاينة الهندسية وتفصيل الفرخ لحظياً فور تغيير الاختيار
    if (this.controller && this.controller.updateImpositionPreview) {
      this.controller.updateImpositionPreview();
    }

    // احترام اختيار المسعر اليدوي لمقاس القطع وعدم الفرض الإجباري للنصوص
    const pressMachine = $('#id_cover_press_machine').val();
    const $pieceSelect = $('#id_piece_size');

    // جلب الأوزان المتاحة حسب الخامة والمورد ومقاس الفرخ
    if (this.api) {
      this.api.getPaperWeights(supplierId, sheetSize, paperTypeId)
        .then(data => {
          if (!data || !data.success) return;
          const weights = data.weights || [];
          if (weights.length > 0) {
            const $weightSelect = $('#id_paper_weight');
            const currentWeightVal = $weightSelect.val();

            const opts = self.api.formatWeightOptions(weights);

            const retainsCurrent = weights.some(w => String(w.value || w.gsm) === String(currentWeightVal));
            const targetWeight = retainsCurrent ? currentWeightVal : (weights[0].value || weights[0].gsm);

            self.isPaperCascadeUpdating = true;
            self.syncSelect2Options($weightSelect, opts, targetWeight);
            self.isPaperCascadeUpdating = false;

            if (targetWeight) {
              self.handlePaperWeightChange(userDriven);
            }
          }
        })
        .catch(err => {
          if (err.name !== 'AbortError') console.warn('Error fetching paper weights:', err);
        });
    }

    this.debouncedRecalculate();
  }

  /**
   * الحقل 4: معالجة جرام الورق وجلب بلاد المنشأ المتاحة فعلياً
   */
  handlePaperWeightChange(userDriven = false) {
    if (this.isPaperCascadeUpdating) return;
    this.updateResolvedPackCapacity(false, 'weight');
    this.fetchAvailablePaperOrigins(userDriven);
    this.debouncedRecalculate();
  }

  /**
   * الحقل 6: جلب بلاد المنشأ المتاحة فقط بناءً على كافة متغيرات الورق
   * (المورد، نوع الورق، مقاس الفرخ، الجراماج)
   */
  fetchAvailablePaperOrigins(userDriven = false) {
    const self = this;
    const supplierId = $('#id_paper_supplier').val();
    const paperTypeId = $('#id_paper_type').val();
    const sheetSize = $('#id_sheet_size').val();
    const weight = $('#id_paper_weight').val();
    const paperSource = $('input[name="paper_source"]:checked').val() || 'purchase';
    const $originSelect = $('#id_paper_origin');
    if (!$originSelect.length) return;

    const currentOrigin = $originSelect.val();

    if (!this.api) {
      this.fetchLivePaperPrice();
      return;
    }

    const requestedSupplierId = supplierId;
    const requestedPaperTypeId = paperTypeId;
    const requestedSheetSize = sheetSize;
    const requestedWeight = weight;

    const paramsObj = {
      supplier_id: supplierId,
      paper_type_id: paperTypeId,
      sheet_size: sheetSize,
      weight: weight,
      paper_source: paperSource
    };

    this.api.getPaperOrigins(paramsObj)
      .then(data => {
        // حماية سباق الردود المتأخرة (Race Condition Guard)
        if ($('#id_paper_supplier').val() !== requestedSupplierId ||
          $('#id_paper_type').val() !== requestedPaperTypeId ||
          $('#id_sheet_size').val() !== requestedSheetSize ||
          $('#id_paper_weight').val() !== requestedWeight) {
          return;
        }

        if (!data || !data.success) {
          self.fetchLivePaperPrice();
          return;
        }

        const origins = data.origins || [];
        const $note = $('#paper_origin_note');

        if (origins.length > 0) {
          const opts = self.api.formatOriginOptions(origins);

          // إذا توفر منشأ يطابق المختار حالياً يُحتفظ به، وإلا يُختار أول منشأ متاح آلياً
          const retainsCurrent = origins.some(o => (o.value || o.name) === currentOrigin);
          const targetOrigin = retainsCurrent ? currentOrigin : (origins[0].value || origins[0].name);

          self.isSyncingOrigin = true;
          self.syncSelect2Options($originSelect, opts, targetOrigin);
          self.isSyncingOrigin = false;
        } else {
          // لا تتوفر أي مناشئ مسجلة لهذه المواصفة لدى التاجر
          self.isSyncingOrigin = true;
          self.syncSelect2Options($originSelect, [{ value: '', text: '-- لا يتوفر منشأ مسجل لهذه المواصفة --' }], '');
          self.isSyncingOrigin = false;

          if ($note.length) {
            $note.html('<span class="text-danger"><i class="fas fa-times-circle me-1"></i>لا يتوفر منشأ مسجل لدى التاجر لهذه المواصفة</span>');
          }

          // تصفير سعر الفرخ لعدم احتساب سعر وهمي
          $('#id_paper_sheet_price').val('0.00');
          self.recalculate();
          return;
        }

        // استدعاء السعر المباشر بالمنشأ المتاح المستقر
        self.fetchLivePaperPrice();
      })
      .catch(err => {
        if (err.name !== 'AbortError') {
          console.warn('Error fetching paper origins:', err);
          self.fetchLivePaperPrice();
        }
      });
  }

  /**
   * استعلام السعر المباشر ومزامنة بلد المنشأ آلياً (دعم الغلاف والداخلي)
   */
  fetchLivePaperPrice(options = {}, isInner = false) {
    const self = this;
    const prefix = isInner ? 'inner_' : '';
    const supplierId = isInner
      ? ($('#id_inner_paper_supplier').val() || $('#id_paper_supplier').val())
      : $('#id_paper_supplier').val();
    const paperTypeId = $(`#id_${prefix}paper_type`).val();
    const sheetSize = $(`#id_${prefix}sheet_size`).val();
    const weight = $(`#id_${prefix}paper_weight`).val();
    const origin = isInner ? '' : $('#id_paper_origin').val();
    const paperSource = $('input[name="paper_source"]:checked').val() || 'purchase';
    const $paperInput = $(`#id_${prefix}paper_sheet_price`);
    const $badge = $(`#${prefix}paper_price_staleness_badge`);
    const $date = $(`#${prefix}paper_price_date_display`);

    if (paperSource === 'customer_supplied') {
      $paperInput.val('0.00');
      $paperInput.attr('data-baseline-price', '0.00');
      this.clearPriceStalenessBadge($badge, $date);
      this.updateSupplierDependentSections();
      this.recalculate();
      return;
    }

    if (!supplierId || !paperTypeId || !sheetSize || !weight) return;

    if (this.api) {
      const paramsObj = {
        supplier_id: supplierId,
        paper_type_id: paperTypeId,
        sheet_size: sheetSize,
        weight: weight,
        origin: origin || ''
      };

      this.api.getLivePaperPrice(paramsObj)
        .then(data => {
          const sheetPrice = parseFloat(data.price) || 0.0;
          const formattedPrice = sheetPrice.toFixed(2);

          // الحفاظ على السعر المحفوظ إذا طُلب صراحة ووجد سعر حالي صالح
          if (!options.preserveSavedPrice || !$paperInput.val() || parseFloat($paperInput.val()) === 0) {
            $paperInput.val(formattedPrice);
          }
          $paperInput.attr('data-baseline-price', formattedPrice);
          $paperInput.attr('data-service-id', data.service_id || '');
          $paperInput.attr('data-supplier-id', supplierId);
          $paperInput.attr('data-formula', data.pricing_formula || '');
          const ptName = $(`#id_${prefix}paper_type option:selected`).text().trim() || 'ورق';
          $paperInput.attr('data-item-label', `${ptName} (${sheetSize} - ${weight} جم)`);
          $paperInput.attr('data-unit-label', 'فرخ');

          // عرض تاريخ السعر والإنذار اللوني (Fresh / Expiring Soon / Stale)
          self.renderPriceStalenessBadge(
            data.price_updated_at,
            data.price_age_days,
            data.price_staleness_status,
            data.price_valid_until,
            $badge,
            $date
          );

          // مزامنة بلد المنشأ تلقائياً مع خامة المورد المسجلة للغلاف فقط
          if (!isInner && data.origin) {
            const $originSelect = $('#id_paper_origin');
            let matchedOrigin = null;
            $originSelect.find('option').each(function () {
              if ($(this).val().toLowerCase().includes(data.origin.toLowerCase()) || $(this).text().includes(data.origin)) {
                matchedOrigin = $(this).val();
              }
            });
            if (matchedOrigin && matchedOrigin !== $originSelect.val()) {
              self.isSyncingOrigin = true;
              $originSelect.val(matchedOrigin).trigger('change.select2');
              self.isSyncingOrigin = false;
            }
          }

          self.updateSupplierDependentSections();
          self.recalculate();
        })
        .catch(err => {
          if (err.name !== 'AbortError') console.warn('Error fetching paper price:', err);
        });
    }
  }

  /**
   * تبديل وضع حساب عدد الأفرخ (يدوي / تلقائي) - الحقل 7
   */
  toggleManualGrossSheets() {
    this.isManualSheetsActive = !this.isManualSheetsActive;
    const $boxAuto = $('#box_auto_sheets_display');
    const $boxManual = $('#box_manual_sheets_input');
    const $toggleBtnText = $('#toggle_manual_sheets_text');

    if (this.isManualSheetsActive) {
      $boxAuto.addClass('d-none');
      $boxManual.removeClass('d-none');
      $toggleBtnText.text('حساب تلقائي');
      const curGross = parseInt($('#display_cover_gross_sheets').text()) || 0;
      $('#id_manual_gross_sheets').val(curGross).focus();
      this.manualGrossSheets = curGross;
    } else {
      $boxManual.addClass('d-none');
      $boxAuto.removeClass('d-none');
      $toggleBtnText.text('تعديل يدوي');
      this.manualGrossSheets = null;
    }
    this.recalculate();
  }

  /**
   * تفريغ وإعادة تصفير كارت الورق عند مسح نوع الخامة أو المورد
   */
  resetPaperCascade() {
    this.clearPriceStalenessBadge($('#paper_price_staleness_badge'), $('#paper_price_date_display'));
    $('#id_paper_sheet_price').val('0.00');
    $('#display_cover_gross_sheets').text('0 فرخ');
    $('#display_cover_reams_breakdown').text('0 رزمة');
    $('#display_cover_net_sheets').text('0');
    $('#display_cover_waste_sheets').text('0');
    $('#display_cover_weight_kg').text('0.0 كجم');
    $('#cover_paper_cost_display').text(this.formatMoney(0));
    const $originSelect = $('#id_paper_origin');
    if ($originSelect.length) {
      this.isSyncingOrigin = true;
      this.syncSelect2Options($originSelect, [{ value: '', text: '-- يتحدد تلقائياً حسب خامة المورد --' }], '');
      this.isSyncingOrigin = false;
    }
    $('#paper_origin_note').text('يتزامن تلقائياً مع بلد منشأ خامة المورد');
    this.recalculate();
  }

  /**
   * استنتاج وحسم سعة الرزمة المعتمدة ديناميكياً من الإعدادات
   */
  updateResolvedPackCapacity(isInitial = false, source = null) {
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
    if (source === 'weight') {
      // عند التغيير المباشر لجراماج الورق، الأولوية لسعة رزمة الجراماج
      resolvedCapacity = weightPack > 0 ? weightPack : (overridePack > 0 ? overridePack : 250);
    } else if (source === 'type') {
      // عند تغيير نوع الخامة، إذا كانت الخامة استثنائية (مثل ستيكر أو دوبلكس) تُعتمد سعتها، وإلا سعة الجراماج
      resolvedCapacity = overridePack > 0 ? overridePack : (weightPack > 0 ? weightPack : 250);
    } else {
      // التهيئة الافتراضية العامة
      if (weightPack > 0) {
        resolvedCapacity = weightPack;
      } else if (overridePack > 0) {
        resolvedCapacity = overridePack;
      }
    }

    hiddenInput.val(resolvedCapacity);
    $('#val_sheets_per_pack').text(resolvedCapacity);
    $('#pack_addon_sheets').text(resolvedCapacity);
    this.updateConvertedSheetPrice();
  }

  /**
   * استنتاج وحسم سعة رزم ورق الداخلي ديناميكياً
   */
  updateResolvedInnerPackCapacity(isInitial = false, source = null) {
    const hiddenInput = $('#id_inner_sheets_per_pack');
    if (!hiddenInput.length) return;

    const paperTypeOpt = $('#id_inner_paper_type option:selected');
    const paperWeightOpt = $('#id_inner_paper_weight option:selected');

    const overridePack = PricingMath.parseSafeNumber(paperTypeOpt.data('override-pack'), 0);
    const weightPack = PricingMath.parseSafeNumber(paperWeightOpt.data('sheets-per-pack'), 0);

    let resolvedCapacity = 500;
    if (source === 'weight') {
      resolvedCapacity = weightPack > 0 ? weightPack : (overridePack > 0 ? overridePack : 500);
    } else if (source === 'type') {
      resolvedCapacity = overridePack > 0 ? overridePack : (weightPack > 0 ? weightPack : 500);
    } else {
      if (weightPack > 0) {
        resolvedCapacity = weightPack;
      } else if (overridePack > 0) {
        resolvedCapacity = overridePack;
      }
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
      converted = parseFloat($('#id_paper_sheet_price').val()) || 0;
    }

    display.data('converted-price', converted);
    display.text(`${converted.toFixed(2)} ${this.config.currencySymbol}`);
  }

  /**
   * النسخ السريع الآمن من الغلاف للداخلي
   */
  copyCoverPaperToInner() {
    const coverPaperSupp = $('#id_paper_supplier').val();
    const coverPaperType = $('#id_paper_type').val();
    const coverPaperWeight = $('#id_paper_weight').val();
    const coverSheetPrice = $('#id_paper_sheet_price').val();

    if (coverPaperSupp) $('#id_inner_paper_supplier').val(coverPaperSupp).trigger('change');
    if (coverPaperType) $('#id_inner_paper_type').val(coverPaperType).trigger('change');
    if (coverPaperWeight) $('#id_inner_paper_weight').val(coverPaperWeight).trigger('change');
    if (coverSheetPrice) $('#id_inner_sheet_price').val(coverSheetPrice);

    // نسخ شارة تاريخ وحالة سعر الورق إلى ورق الداخلي
    const $covBadge = $('#paper_price_staleness_badge');
    const $covDate = $('#paper_price_date_display');
    const $inBadge = $('#inner_paper_price_staleness_badge');
    const $inDate = $('#inner_paper_price_date_display');
    if ($covBadge.length && !$covBadge.hasClass('d-none')) {
      $inBadge.attr('class', $covBadge.attr('class')).attr('title', $covBadge.attr('title')).html($covBadge.html());
      if ($covDate.length && !$covDate.hasClass('d-none')) {
        $inDate.attr('class', $covDate.attr('class')).html($covDate.html());
      }
    }

    this.debouncedRecalculate();
    this.showNotification('تم نسخ خامة ومورد وسعر ورق الغلاف إلى ورق الداخلي بنجاح', 'success');
  }

}

// Global Export
if (typeof window !== 'undefined') {
  window.PricingSheetPrintingSubsystem = PricingSheetPrintingSubsystem;
}
