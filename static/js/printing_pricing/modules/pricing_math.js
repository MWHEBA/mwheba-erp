/**
 * MWHEBA ERP - Printing Pricing Calculation Engine
 * Module: PricingMath (Pure Calculation & Imposition Mathematics)
 * Version: 2.1.8
 * Responsibilities: Pure mathematical computations, geometric imposition, 
 * physical spine calculation, sheet waste rates, tirage, markup. (Zero DOM coupling)
 */

window.PricingMath = {
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
   * تسوية ومطابقة النصوص العربية وإزالة الهمزات والتشكيل والتاء المربوطة
   */
  normalizeArabic(text) {
    if (!text) return '';
    return String(text)
      .trim()
      .replace(/[إأآا]/g, 'ا')
      .replace(/ة/g, 'ه')
      .replace(/ى/g, 'ي')
      .replace(/[\u064B-\u065F]/g, '');
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
  calcPullsAndTirage(grossSheets, sidesMultiplier = 1, sidesMode = 'single') {
    if (sidesMode === 'work_sheet') {
      const pulls = Math.ceil(grossSheets * 2);
      const tiragesFront = grossSheets > 0 ? Math.max(1, Math.ceil(grossSheets / 1000)) : 0;
      const tiragesBack = grossSheets > 0 ? Math.max(1, Math.ceil(grossSheets / 1000)) : 0;
      return {
        pulls: pulls,
        tirages: tiragesFront + tiragesBack,
        tiragesFront: tiragesFront,
        tiragesBack: tiragesBack
      };
    }
    const pulls = Math.ceil(grossSheets * sidesMultiplier);
    const tirages = pulls > 0 ? Math.max(1, Math.ceil(pulls / 1000)) : 0;
    return {
      pulls: pulls,
      tirages: tirages,
      tiragesFront: tirages,
      tiragesBack: 0
    };
  },

  /**
   * حساب السعر النهائي المحاسبي بهامش الربح وفق نموذج التكلفة الإضافية (Markup)
   * مع حماية الهامش وتقريبه للأعلى (Math.ceil) للمطابقة التامة مع الباك إند
   */
  calcFinalPrice(totalCost, profitMargin) {
    // تحديد الهامش بين 0% و 500% كحد أقصى آمن
    const safeMargin = Math.min(5.0, Math.max(0, profitMargin));
    const rawPrice = totalCost * (1 + safeMargin);
    // جبر الإجمالي النهائي دائمًا للأعلى لمطابقة الباك إند
    return Math.ceil(rawPrice);
  }
};

// تصدير الكائن للنطاق العام
var PricingMath = window.PricingMath;
