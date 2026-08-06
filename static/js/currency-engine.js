/**
 * currency-engine.js - المكون الموحد للجافاسكريبت لحساب وتحديث مبالغ وسعر الصرف ديناميكياً
 * FIN-CORE-016: Strict Quotation Convention (1 Foreign = X Base) & Decimal Rounding Sync
 */

const CurrencyEngine = (function () {
  'use strict';

  let functionalCurrency = window.SYSTEM_FUNCTIONAL_CURRENCY || document.documentElement.getAttribute('data-functional-currency') || '';

  /**
   * تعيين العملة الوظيفية الحالية للنظام
   */
  function setFunctionalCurrency(code) {
    if (code) {
      functionalCurrency = code.toUpperCase();
    }
  }

  /**
   * تحويل المبلغ بين العملات بالمعادلة الموحدة: Functional Amount = Foreign Amount * Spot Rate
   */
  function calculateFunctionalAmount(foreignAmount, exchangeRate) {
    const amount = parseFloat(foreignAmount) || 0;
    const rate = parseFloat(exchangeRate) || 1;
    return (amount * rate).toFixed(2);
  }

  /**
   * تحويل سعر الكتالوج الأساسي بالعملة الوظيفية إلى العملة الأجنبية المستهدفة بالقسمة على سعر الصرف
   */
  function convertBaseToForeignPrice(baseCatalogPrice, exchangeRate) {
    const price = parseFloat(baseCatalogPrice) || 0;
    const rate = parseFloat(exchangeRate) || 1;
    if (rate <= 0) return price.toFixed(2);
    return (price / rate).toFixed(4);
  }

  /**
   * الربط التلقائي لعناصر الشاشة: حقل العملة + حقل سعر الصرف + حقول الإجمالي
   */
  function attachCurrencyControls(options) {
    const currencySelect = document.getElementById(options.currencySelectId);
    const rateInput = document.getElementById(options.rateInputId);
    const amountInput = document.getElementById(options.amountInputId);
    const resultSpan = document.getElementById(options.resultSpanId);

    if (!currencySelect || !rateInput) return;

    currencySelect.addEventListener('change', function () {
      const selectedCurrency = this.value;
      if (selectedCurrency === functionalCurrency) {
        rateInput.value = '1.000000';
        rateInput.readOnly = true;
      } else {
        rateInput.readOnly = false;
        // جلب أحدث سعر صرف من الـ API
        fetch(`/financial/api/exchange-rate/?from=${selectedCurrency}&to=${functionalCurrency}`)
          .then(res => res.json())
          .then(data => {
            if (data.rate) {
              rateInput.value = data.rate;
              if (amountInput && resultSpan) {
                resultSpan.textContent = calculateFunctionalAmount(amountInput.value, data.rate);
              }
            }
          })
          .catch(() => {});
      }
    });

    if (amountInput && rateInput && resultSpan) {
      const updateResult = function () {
        resultSpan.textContent = calculateFunctionalAmount(amountInput.value, rateInput.value);
      };
      amountInput.addEventListener('input', updateResult);
      rateInput.addEventListener('input', updateResult);
    }
  }

  return {
    setFunctionalCurrency: setFunctionalCurrency,
    calculateFunctionalAmount: calculateFunctionalAmount,
    convertBaseToForeignPrice: convertBaseToForeignPrice,
    attachCurrencyControls: attachCurrencyControls
  };
})();

// تصدير كـ Global Variable للاستخدام المباشر في جميع الشاشات
window.CurrencyEngine = CurrencyEngine;
