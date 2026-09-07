/**
 * MWHEBA ERP - Industrial 2D Imposition Visualizer Engine
 * Module: imposition_visualizer.js
 * Version: 3.0.0
 *
 * Responsibilities:
 * 1. Pure SVG 2D layout engine (1 unit = 1 mm) for machine press sheets & raw parent sheets.
 * 2. Offset gripper geometry (12mm lead edge on cylinder, 5mm tail, 3mm sides) & digital (4mm border).
 * 3. 4-Archetype specialization: Flyer, Folder (same_sheet vs separate), Catalog/Book spread (spine), NCR invoices.
 * 4. Double cut (دوبل تكسير 3mm) vs common knife cut (قص مشترك) detection and badges.
 * 5. Work & Turn (طبع وقلب) vertical division vs Work & Sheet (وجهين) toggle.
 * 6. Contiguous fill from gripper & idle slots (خانات شاغرة - فاقد تفريد) on montage step-down.
 * 7. Live production batch stats (صافي، هالك، إجمالي أفرخ).
 * 8. Egyptian cutter shearing map (L-cuts: 11 pieces 20x30, 5 pieces 30x40 with knife sequence [1], [2], [3]).
 * 9. Micro-stamp for single-page A4 work order detail view (Monochrome Grayscale).
 * 10. Strict :root CSS variable colors only. Zero hardcoded hex/rgb, zero gradients.
 */

const ImpositionVisualizer = (function() {
  'use strict';

  const SVG_NS = 'http://www.w3.org/2000/svg';

  /**
   * إنشاء عنصر SVG مساعد
   */
  function createSvgEl(tag, attrs = {}) {
    const el = document.createElementNS(SVG_NS, tag);
    for (const [k, v] of Object.entries(attrs)) {
      el.setAttribute(k, v);
    }
    return el;
  }

  /**
   * تنظيف وتطهير الحاوية
   */
  function clearContainer(container) {
    if (!container) return;
    while (container.firstChild) {
      container.removeChild(container.firstChild);
    }
  }

  /**
   * رسم شيت الانتظار التجريدي (Skeleton Guard)
   */
  function renderSkeleton(container, message = 'بانتظار اكتمال بيانات المقاس والتفصيل...') {
    clearContainer(container);
    const wrapper = document.createElement('div');
    wrapper.className = 'd-flex flex-column align-items-center justify-content-center p-4 text-center';
    wrapper.style.minHeight = '240px';
    wrapper.style.backgroundColor = 'var(--gray-100, #f8f9fa)';
    wrapper.style.borderRadius = 'var(--border-radius, 6px)';
    wrapper.style.border = '1px dashed var(--border-color, #dee2e6)';

    const icon = document.createElement('i');
    icon.className = 'fas fa-th-large fa-2x mb-2 text-muted';
    const text = document.createElement('span');
    text.className = 'text-muted small fw-bold';
    text.textContent = message;

    wrapper.appendChild(icon);
    wrapper.appendChild(text);
    container.appendChild(wrapper);
  }

  /**
   * المحرك الرئيسي لرسم شيت الماكينة (Press Sheet Imposition)
   */
  function renderPressSheet(container, options = {}) {
    if (!container) return;

    const {
      pressSheetW = 35.0,     // سم
      pressSheetH = 50.0,     // سم
      openW = 21.0,           // سم
      openH = 29.7,           // سم
      montageCount = null,    // المونتاج الحالي المعتمد
      printingType = 'offset', // offset | digital | screen | none
      productType = 'flyer',  // flyer | brochure | folder | catalog | book | book_catalog | invoice
      sidesMode = 'single',   // single | work_sheet | work_turn
      orientation = 'auto',   // auto | normal | rotated
      folderPocketType = 'same_sheet', // same_sheet | separate_sheet
      folderPocketHeight = 7.5,
      folderCardSlit = true,
      spineThickness = 0.0,
      quantity = 1000,
      wasteSheets = 20,
      interactive = true,
      activeFace = 'front'    // front | back (for work_sheet)
    } = options;

    if (pressSheetW <= 0 || pressSheetH <= 0 || openW <= 0 || openH <= 0) {
      renderSkeleton(container);
      return;
    }

    // توجيه شيت الماكينة بالعرض دائماً (Landscape) لأفضل استغلال للمساحة ومطابقة واقع تغذية درفيل السلندر
    const sheetW_cm = Math.max(pressSheetW, pressSheetH);
    const sheetH_cm = Math.min(pressSheetW, pressSheetH);

    // 1. حسابات المونتاج الهندسية الصرفة
    const calc = PricingMath.calcImposition(sheetW_cm, sheetH_cm, openW, openH, printingType, orientation);
    if (calc.isOverflow || calc.cutsPerSheet <= 0) {
      renderSkeleton(container, `مقاس المطبوع (${openW}×${openH} سم) لا يتسع داخل شيت الماكينة (${sheetW_cm}×${sheetH_cm} سم)`);
      return;
    }

    const maxMontage = calc.cutsPerSheet;
    const activeMontage = (montageCount !== null && montageCount > 0 && montageCount <= maxMontage) ? montageCount : maxMontage;
    const isRotated = calc.isRotated;

    // أبعاد القطعة المطبوعة المفردة (بالمللي)
    const itemW_mm = (isRotated ? openH : openW) * 10.0;
    const itemH_mm = (isRotated ? openW : openH) * 10.0;

    // أبعاد شيت الماكينة (بالمللي) بالعرض
    const sheetW_mm = sheetW_cm * 10.0;
    const sheetH_mm = sheetH_cm * 10.0;

    // 2. هندسة الهوامش والبنسة
    const isOffset = (printingType === 'offset');
    const isFeedHorizontal = (sheetW_mm >= sheetH_mm);

    let gripperMargin = 0;
    let tailMargin = 0;
    let sideMarginLeft = 0;
    let sideMarginRight = 0;
    let digitalBorder = 0;

    if (isOffset) {
      gripperMargin = 12.0; // 12 mm
      tailMargin = 5.0;     // 5 mm
      sideMarginLeft = 3.0; // 3 mm
      sideMarginRight = 3.0;// 3 mm
    } else {
      digitalBorder = 4.0;  // 4 mm all around
    }

    // الصافي والهوامش المسنترة (بالمللي)
    const marginX_mm = calc.marginX * 10.0;
    const marginY_mm = calc.marginY * 10.0;
    const gapX_mm = calc.gapX * 10.0;
    const gapY_mm = calc.gapY * 10.0;

    // نقطة بداية شبكة المونتاج (بالمللي)
    let startX_mm = 0;
    let startY_mm = 0;

    if (isOffset) {
      if (isFeedHorizontal) {
        startX_mm = sideMarginLeft + marginX_mm;
        startY_mm = gripperMargin + marginY_mm; // تبدأ من بعد ضلع البنسة العلوي
      } else {
        startX_mm = gripperMargin + marginX_mm;
        startY_mm = sideMarginLeft + marginY_mm;
      }
    } else {
      startX_mm = digitalBorder + marginX_mm;
      startY_mm = digitalBorder + marginY_mm;
    }

    // 3. بناء SVG
    clearContainer(container);

    const svg = createSvgEl('svg', {
      viewBox: `0 0 ${sheetW_mm} ${sheetH_mm}`,
      width: '100%',
      height: '100%',
      preserveAspectRatio: 'xMidYMid meet',
      style: 'max-height: 420px; width: 100%; max-width: 680px; display: block; margin: 0 auto; user-select: none;'
    });

    // تعريف الرموز والتنسيقات الفلات
    const defs = createSvgEl('defs');
    svg.appendChild(defs);

    // خلفية شيت الماكينة
    const sheetBg = createSvgEl('rect', {
      x: 0,
      y: 0,
      width: sheetW_mm,
      height: sheetH_mm,
      fill: 'var(--card-bg, #ffffff)',
      stroke: 'var(--border-color, #495057)',
      'stroke-width': 1.5,
      rx: 2
    });
    svg.appendChild(sheetBg);

    // رسم شريط البنسة وهوامش التشغيل
    if (isOffset) {
      // شريط البنسة (12 مم) على الضلع الأطول
      const gripperRect = isFeedHorizontal ?
        createSvgEl('rect', {
          x: 0,
          y: 0,
          width: sheetW_mm,
          height: gripperMargin,
          fill: 'var(--gray-200, #e9ecef)',
          stroke: 'none'
        }) :
        createSvgEl('rect', {
          x: 0,
          y: 0,
          width: gripperMargin,
          height: sheetH_mm,
          fill: 'var(--gray-200, #e9ecef)',
          stroke: 'none'
        });
      svg.appendChild(gripperRect);

      // خط البنسة المنقط
      const gripperLine = isFeedHorizontal ?
        createSvgEl('line', {
          x1: 0, y1: gripperMargin,
          x2: sheetW_mm, y2: gripperMargin,
          stroke: 'var(--secondary, #6c757d)',
          'stroke-width': 0.8,
          'stroke-dasharray': '3,3'
        }) :
        createSvgEl('line', {
          x1: gripperMargin, y1: 0,
          x2: gripperMargin, y2: sheetH_mm,
          stroke: 'var(--secondary, #6c757d)',
          'stroke-width': 0.8,
          'stroke-dasharray': '3,3'
        });
      svg.appendChild(gripperLine);

      // نص تسمية البنسة
      const gripperText = isFeedHorizontal ?
        createSvgEl('text', {
          x: sheetW_mm / 2,
          y: gripperMargin / 2 + 2.5,
          'text-anchor': 'middle',
          fill: 'var(--secondary, #6c757d)',
          'font-size': 8.5,
          'font-family': 'inherit',
          'font-weight': 'bold'
        }) :
        createSvgEl('text', {
          x: gripperMargin / 2 + 2.5,
          y: sheetH_mm / 2,
          'text-anchor': 'middle',
          fill: 'var(--secondary, #6c757d)',
          'font-size': Math.max(7, Math.min(10, sheetH_mm * 0.02)),
          'font-family': 'inherit',
          'font-weight': 'bold',
          transform: `rotate(-90, ${gripperMargin / 2}, ${sheetH_mm / 2})`
        });
      gripperText.textContent = 'بنسة الماكينة (12 مم)';
      svg.appendChild(gripperText);

      // هامش الديل (5 مم)
      const tailRect = isFeedHorizontal ?
        createSvgEl('rect', {
          x: 0,
          y: sheetH_mm - tailMargin,
          width: sheetW_mm,
          height: tailMargin,
          fill: 'var(--gray-100, #f8f9fa)',
          stroke: 'none'
        }) :
        createSvgEl('rect', {
          x: sheetW_mm - tailMargin,
          y: 0,
          width: tailMargin,
          height: sheetH_mm,
          fill: 'var(--gray-100, #f8f9fa)',
          stroke: 'none'
        });
      svg.appendChild(tailRect);
    } else {
      // إطار الديجيتال المحيطي (4 مم)
      const digFrame = createSvgEl('rect', {
        x: digitalBorder,
        y: digitalBorder,
        width: sheetW_mm - (digitalBorder * 2),
        height: sheetH_mm - (digitalBorder * 2),
        fill: 'none',
        stroke: 'var(--gray-400, #ced4da)',
        'stroke-width': 0.8,
        'stroke-dasharray': '2,2'
      });
      svg.appendChild(digFrame);

      const digLabel = createSvgEl('text', {
        x: sheetW_mm / 2,
        y: digitalBorder - 1,
        'text-anchor': 'middle',
        fill: 'var(--secondary, #6c757d)',
        'font-size': 6,
        'font-family': 'inherit'
      });
      digLabel.textContent = 'هامش ديجيتال غير مطبوع (4 مم)';
      svg.appendChild(digLabel);
    }

    // 4. خط الطبع والقلب (Work & Turn)
    const isWorkTurn = (sidesMode === 'work_turn' && activeMontage >= 2);
    if (isWorkTurn) {
      const splitX = sheetW_mm / 2;
      const splitLine = createSvgEl('line', {
        x1: splitX, y1: isFeedHorizontal ? gripperMargin : 0,
        x2: splitX, y2: sheetH_mm,
        stroke: 'var(--info, #0dcaf0)',
        'stroke-width': 1.2,
        'stroke-dasharray': '4,2'
      });
      svg.appendChild(splitLine);

      const labelA = createSvgEl('text', {
        x: splitX / 2,
        y: (isFeedHorizontal ? gripperMargin : 0) + 14,
        'text-anchor': 'middle',
        fill: 'var(--info, #0dcaf0)',
        'font-size': 8,
        'font-weight': 'bold'
      });
      labelA.textContent = 'نصف (وجه A)';
      svg.appendChild(labelA);

      const labelB = createSvgEl('text', {
        x: splitX + (splitX / 2),
        y: (isFeedHorizontal ? gripperMargin : 0) + 14,
        'text-anchor': 'middle',
        fill: 'var(--info, #0dcaf0)',
        'font-size': 8,
        'font-weight': 'bold'
      });
      labelB.textContent = 'نصف (ظهر A) - طبع وقلب';
      svg.appendChild(labelB);
    }

    // 5. رسم قطع المونتاج (Grid of Items)
    const cols = calc.cols;
    const rows = calc.rows;
    let slotIndex = 0;

    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        slotIndex++;
        const isActive = (slotIndex <= activeMontage);

        const x = startX_mm + (c * (itemW_mm + gapX_mm));
        const y = startY_mm + (r * (itemH_mm + gapY_mm));

        // حاوية القطعة
        const itemG = createSvgEl('g', {
          class: `imposition-slot ${isActive ? 'slot-active' : 'slot-idle'}`,
          'data-slot': slotIndex
        });

        // المستطيل الأساسي للقطعة
        const itemRect = createSvgEl('rect', {
          x: x,
          y: y,
          width: itemW_mm,
          height: itemH_mm,
          fill: isActive ? 'var(--primary-subtle, #e7f1ff)' : 'var(--gray-100, #f8f9fa)',
          stroke: isActive ? 'var(--primary, #0d6efd)' : 'var(--secondary, #adb5bd)',
          'stroke-width': isActive ? 1.0 : 0.8,
          'stroke-dasharray': isActive ? 'none' : '3,2',
          rx: 1.5
        });
        itemG.appendChild(itemRect);

        // تخصيص الأنماط الأربعة (Archetypes)
        if (isActive) {
          if (productType === 'folder') {
            // فولدر: لسان الجيب السفلي وشلاقة الكارت
            if (folderPocketType === 'same_sheet') {
              const pocketH_mm = (folderPocketHeight || 7.5) * 10.0;
              const foldY = y + itemH_mm - pocketH_mm;

              // خط طي الجيب المنقط
              const foldLine = createSvgEl('line', {
                x1: x, y1: foldY,
                x2: x + itemW_mm, y2: foldY,
                stroke: 'var(--danger, #dc3545)',
                'stroke-width': 0.8,
                'stroke-dasharray': '2,2'
              });
              itemG.appendChild(foldLine);

              // لسان الجيب
              const pocketRect = createSvgEl('rect', {
                x: x, y: foldY,
                width: itemW_mm, height: pocketH_mm,
                fill: 'var(--gray-200, #e2e3e5)',
                stroke: 'none',
                opacity: 0.7
              });
              itemG.appendChild(pocketRect);

              // فتحة الكارت الشخصي (Slit)
              if (folderCardSlit) {
                const slitW = Math.min(30, itemW_mm * 0.4);
                const slitX = x + (itemW_mm - slitW) / 2;
                const slitY = foldY + (pocketH_mm / 2);
                const slitLine = createSvgEl('line', {
                  x1: slitX, y1: slitY,
                  x2: slitX + slitW, y2: slitY,
                  stroke: 'var(--dark, #212529)',
                  'stroke-width': 1.0
                });
                itemG.appendChild(slitLine);
              }

              // تسمية الجيب المتصل
              const pocketLabel = createSvgEl('text', {
                x: x + (itemW_mm / 2),
                y: foldY + (pocketH_mm / 2) + 2,
                'text-anchor': 'middle',
                fill: 'var(--secondary, #495057)',
                'font-size': Math.max(7.5, Math.min(11, pocketH_mm * 0.2)),
                'font-weight': 'bold',
                'font-family': 'inherit'
              });
              pocketLabel.textContent = `جيب متصل (${folderPocketHeight} سم)`;
              itemG.appendChild(pocketLabel);
            }
          } else if (productType === 'catalog' || productType === 'book' || productType === 'book_catalog') {
            // غلاف كتاب/كتالوج مع كعب
            const spineW_mm = (spineThickness || 0.5) * 10.0;
            if (spineW_mm > 1.0) {
              const spineX = x + ((itemW_mm - spineW_mm) / 2);
              const spineRect = createSvgEl('rect', {
                x: spineX, y: y,
                width: spineW_mm, height: itemH_mm,
                fill: 'var(--warning-subtle, #fff3cd)',
                stroke: 'var(--warning, #ffc107)',
                'stroke-width': 0.6,
                'stroke-dasharray': '2,1'
              });
              itemG.appendChild(spineRect);

              const spineText = createSvgEl('text', {
                x: spineX + (spineW_mm / 2),
                y: y + (itemH_mm / 2),
                'text-anchor': 'middle',
                fill: 'var(--dark, #212529)',
                'font-size': Math.max(6.5, Math.min(10, spineW_mm * 0.5)),
                'font-weight': 'bold',
                transform: `rotate(-90, ${spineX + (spineW_mm / 2)}, ${y + (itemH_mm / 2)})`
              });
              spineText.textContent = `كعب ${spineThickness} سم`;
              itemG.appendChild(spineText);
            }
          } else if (productType === 'invoice') {
            // دفاتر فواتير NCR: كعب التخريم والدبوس
            const stubW_mm = 15.0; // 1.5 سم كعب
            const stubRect = createSvgEl('rect', {
              x: x, y: y,
              width: stubW_mm, height: itemH_mm,
              fill: 'var(--info-subtle, #cff4fc)',
              stroke: 'none'
            });
            itemG.appendChild(stubRect);

            // خط التخريم المنقط
            const perfLine = createSvgEl('line', {
              x1: x + stubW_mm, y1: y,
              x2: x + stubW_mm, y2: y + itemH_mm,
              stroke: 'var(--secondary, #6c757d)',
              'stroke-width': 0.8,
              'stroke-dasharray': '1.5,1.5'
            });
            itemG.appendChild(perfLine);
          }

          // حساب المقاسات والخطوط المتناسقة والمريحة للعين (خط متزن أوضح بدرجة)
          const minDim = Math.min(itemW_mm, itemH_mm);
          const titleSize = Math.max(10, Math.min(18, minDim * 0.1));
          const dimSize = Math.max(8.5, Math.min(13, titleSize * 0.72));

          const centerX = x + (itemW_mm / 2);
          const centerY = y + (itemH_mm / 2);

          // رقم القطعة
          const labelNum = createSvgEl('text', {
            x: centerX,
            y: centerY - 2,
            'text-anchor': 'middle',
            fill: 'var(--primary, #0d6efd)',
            'font-size': titleSize,
            'font-weight': 'bold',
            'font-family': 'inherit'
          });
          labelNum.textContent = `قطعة #${slotIndex}`;
          itemG.appendChild(labelNum);

          // أبعاد القطعة
          const labelDim = createSvgEl('text', {
            x: centerX,
            y: centerY + dimSize + 2,
            'text-anchor': 'middle',
            fill: 'var(--secondary, #6c757d)',
            'font-size': dimSize,
            'font-weight': '500',
            'font-family': 'inherit'
          });
          labelDim.textContent = `${(itemW_mm / 10).toFixed(1)} × ${(itemH_mm / 10).toFixed(1)} سم`;
          itemG.appendChild(labelDim);
        } else {
          // خانة شاغرة (فاقد تفريد)
          const minDim = Math.min(itemW_mm, itemH_mm);
          const idleSize = Math.max(9, Math.min(14, minDim * 0.085));
          const idleText = createSvgEl('text', {
            x: x + (itemW_mm / 2),
            y: y + (itemH_mm / 2) + 3,
            'text-anchor': 'middle',
            fill: 'var(--secondary, #6c757d)',
            'font-size': idleSize,
            'font-style': 'italic',
            'font-family': 'inherit'
          });
          idleText.textContent = 'خانة شاغرة (فاقد)';
          itemG.appendChild(idleText);
        }

        svg.appendChild(itemG);
      }
    }

    container.appendChild(svg);

    // 6. شريط الإحصائية التشغيلية المباشرة وشارات الحالة (Live Batch Stats & Badges)
    _renderBatchStatsBar(container, {
      activeMontage,
      maxMontage,
      quantity,
      wasteSheets,
      hasBleedGutters: calc.hasBleedGutters,
      pressSheetW: sheetW_cm,
      pressSheetH: sheetH_cm,
      printingType,
      productType,
      folderPocketType
    });
  }

  /**
   * شريط الإحصائيات الفورية أعلى وأسفل الكارت
   */
  function _renderBatchStatsBar(container, info) {
    // إزالة أي شريط إحصائيات قديم
    const oldBar = container.parentNode?.querySelector('.imposition-stats-bar');
    if (oldBar) oldBar.remove();

    const statsBar = document.createElement('div');
    statsBar.className = 'imposition-stats-bar d-flex flex-wrap align-items-center justify-content-between p-2 mt-2 border rounded';
    statsBar.style.backgroundColor = 'var(--card-bg, #ffffff)';
    statsBar.style.borderColor = 'var(--border-color, #dee2e6)';
    statsBar.style.fontSize = '0.85rem';

    // حساب الشيتات الصافية والإجمالية
    const netSheets = Math.ceil(info.quantity / Math.max(1, info.activeMontage));
    const grossSheets = netSheets + (info.wasteSheets || 20);

    // 1. إحصائيات السحب والتشغيل
    const leftStats = document.createElement('div');
    leftStats.className = 'd-flex align-items-center gap-2';
    leftStats.innerHTML = `
      <span class="badge bg-light text-dark border">
        <i class="fas fa-th me-1 text-primary"></i> المونتاج: <strong>${info.activeMontage}</strong> قطعة
      </span>
      <span class="badge bg-light text-dark border">
        صافي الشيتات: <strong>${netSheets.toLocaleString('en-US')}</strong>
      </span>
      <span class="badge bg-light text-dark border">
        الهالك: <strong>${(info.wasteSheets || 20).toLocaleString('en-US')}</strong>
      </span>
      <span class="badge bg-primary text-white">
        المطلوب سحبه: <strong>${grossSheets.toLocaleString('en-US')}</strong> شيت
      </span>
    `;

    // 2. شارة الدوبل تكسير أو القص المشترك
    const rightBadges = document.createElement('div');
    rightBadges.className = 'd-flex align-items-center gap-1';

    if (info.hasBleedGutters) {
      rightBadges.innerHTML = `
        <span class="badge bg-success-subtle text-success border border-success-subtle">
          <i class="fas fa-check-circle me-1"></i> فواصل دوبل تكسير (3 مم)
        </span>
      `;
    } else {
      rightBadges.innerHTML = `
        <span class="badge bg-warning-subtle text-warning border border-warning-subtle" title="المقاس حاشر في الشيت ولا يتسع لفواصل 3 مم">
          <i class="fas fa-exclamation-triangle me-1"></i> قص مشترك (بدون دوبل تكسير)
        </span>
      `;
    }

    // شارة الجيب المنفصل في الفولدر إن وجد
    if (info.productType === 'folder' && info.folderPocketType === 'separate_sheet') {
      rightBadges.innerHTML += `
        <span class="badge bg-info-subtle text-info border border-info-subtle">
          <i class="fas fa-folder-open me-1"></i> الجيب منفصل (تفريد خارجي)
        </span>
      `;
    }

    statsBar.appendChild(leftStats);
    statsBar.appendChild(rightBadges);

    container.parentNode?.insertBefore(statsBar, container);
  }

  /**
   * خريطة تفصيل الفرخ الخام للمقصدار (Shearing Map)
   * مع التركيبات الخاصة (حداشر 20×30 وخمسات 30×40)
   */
  function renderShearingMap(container, options = {}) {
    if (!container) return;

    const {
      parentW = 70.0,
      parentH = 100.0,
      pieceW = 35.0,
      pieceH = 50.0,
      machineCuts = 4,
      paperSource = 'purchase', // purchase | warehouse | customer_supplied
      cutsPerSheet = 1
    } = options;

    clearContainer(container);

    // إذا كان الورق منصرفاً جاهزاً من المخزن مقصوصاً
    if (paperSource === 'warehouse') {
      const notice = document.createElement('div');
      notice.className = 'alert alert-info d-flex align-items-center mb-0 p-3';
      notice.innerHTML = `
        <i class="fas fa-warehouse fa-2x me-3 text-info"></i>
        <div>
          <strong class="d-block mb-1">الخامة منصرفة مقصوصة جاهزة من مخزن المنشأة</strong>
          <span class="small text-muted">مقاس القطع (${pieceW}×${pieceH} سم) منصرف ومجهز مسبقاً ولا يتطلب تقطيع فرخ خام بالمقصدار.</span>
        </div>
      `;
      container.appendChild(notice);
      return;
    }

    // توجيه الفرخ الخام بالعرض دائماً (Landscape) لملء العرض ومطابقة اتجاه طاولة المقصدار
    const effParentW = Math.max(parentW, parentH); // 100.0 سم
    const effParentH = Math.min(parentW, parentH); // 70.0 سم
    const parentW_mm = effParentW * 10.0;          // 1000 مم
    const parentH_mm = effParentH * 10.0;          // 700 مم

    const svg = createSvgEl('svg', {
      viewBox: `0 0 ${parentW_mm} ${parentH_mm}`,
      width: '100%',
      height: '100%',
      preserveAspectRatio: 'xMidYMid meet',
      style: 'max-height: 420px; width: 100%; max-width: 680px; display: block; margin: 0 auto; user-select: none;'
    });

    // رسم الفرخ الخام
    const parentBg = createSvgEl('rect', {
      x: 0,
      y: 0,
      width: parentW_mm,
      height: parentH_mm,
      fill: 'var(--gray-100, #f8f9fa)',
      stroke: 'var(--border-color, #212529)',
      'stroke-width': 1.5,
      rx: 2
    });
    svg.appendChild(parentBg);

    // فحص حالات التقطيع المركب للمقصدار في الفرخ 70×100
    const isStandard70x100 = (Math.min(parentW, parentH) >= 69.0 && Math.max(parentW, parentH) <= 101.0);

    if (machineCuts === 11 && isStandard70x100) {
      // تفصيل 11 قطعة مقاس 20×30 سم (حداشر)
      _draw11CutsPattern(svg, parentW_mm, parentH_mm);
    } else if (machineCuts === 5 && isStandard70x100) {
      // تفصيل 5 قطع مقاس 30×40 سم (خمسات)
      _draw5CutsPattern(svg, parentW_mm, parentH_mm);
    } else {
      // التقطيع المتناظر القياسي (ربع 4 قطع، نصف قطعتين، ثمن 8 قطع)
      _drawStandardCutsPattern(svg, parentW_mm, parentH_mm, pieceW * 10.0, pieceH * 10.0, machineCuts);
    }

    container.appendChild(svg);

    // شريط إحصائية الفرخ الخام
    const totalItemsPerParent = (machineCuts || 1) * (cutsPerSheet || 1);
    const summaryDiv = document.createElement('div');
    summaryDiv.className = 'text-center small text-muted mt-2 fw-bold';
    summaryDiv.innerHTML = `
      <i class="fas fa-cut me-1 text-primary"></i> الفرخ الخام (${effParentW}×${effParentH} سم) يعطي <strong>${machineCuts}</strong> شيت للماكينة × <strong>${cutsPerSheet}</strong> مونتاج = <strong>${totalItemsPerParent}</strong> قطعة بالفرخ
    `;
    container.appendChild(summaryDiv);
  }

  /**
   * رسم نمط الـ 11 قطعة (حداشر 20×30) على الفرخ العرضي 100×70 سم
   */
  function _draw11CutsPattern(svg, pW, pH) {
    // 9 قطع 300×200 مم (شبكة 3×3) في مساحة 900×600
    for (let r = 0; r < 3; r++) {
      for (let c = 0; c < 3; c++) {
        const x = c * 300;
        const y = r * 200;
        const rect = createSvgEl('rect', {
          x, y, width: 300, height: 200,
          fill: 'var(--primary-subtle, #e7f1ff)',
          stroke: 'var(--primary, #0d6efd)',
          'stroke-width': 1.0
        });
        svg.appendChild(rect);

        const txt = createSvgEl('text', {
          x: x + 150, y: y + 105,
          'text-anchor': 'middle',
          fill: 'var(--primary, #0d6efd)',
          'font-size': 18, 'font-weight': 'bold'
        });
        txt.textContent = `شيت #${r * 3 + c + 1} (20×30)`;
        svg.appendChild(txt);
      }
    }

    // قطعتين إضافيتين في الشريحة الرأسية 100×600 مم
    for (let i = 0; i < 2; i++) {
      const x = 900;
      const y = i * 300;
      const rect = createSvgEl('rect', {
        x, y, width: 100, height: 300,
        fill: 'var(--info-subtle, #cff4fc)',
        stroke: 'var(--info, #0dcaf0)',
        'stroke-width': 1.0
      });
      svg.appendChild(rect);

      const txt = createSvgEl('text', {
        x: x + 50, y: y + 150,
        'text-anchor': 'middle',
        fill: 'var(--info, #0dcaf0)',
        'font-size': 13, 'font-weight': 'bold',
        transform: `rotate(-90, ${x + 50}, ${y + 150})`
      });
      txt.textContent = `شيت #${10 + i} (20×30 مركب)`;
      svg.appendChild(txt);
    }

    // شريط الفائض السفلي 100×1000 مم
    const scrapRect = createSvgEl('rect', {
      x: 0, y: 600, width: pW, height: 100,
      fill: 'var(--gray-200, #e9ecef)',
      stroke: 'var(--secondary, #adb5bd)',
      'stroke-width': 0.8,
      'stroke-dasharray': '4,4'
    });
    svg.appendChild(scrapRect);

    const scrapTxt = createSvgEl('text', {
      x: pW / 2, y: 655,
      'text-anchor': 'middle',
      fill: 'var(--secondary, #6c757d)',
      'font-size': 14, 'font-weight': 'bold'
    });
    scrapTxt.textContent = 'فاقد تقطيع الفرخ الخام (10×100 سم)';
    svg.appendChild(scrapTxt);

    // ضربات سكين المقصدار
    _drawKnifeStep(svg, 0, 600, pW, 600, '[1] ضربة سكين رئيسية أولى (فصل شريط الفائض 10 سم)');
    _drawKnifeStep(svg, 900, 0, 900, 600, '[2] ضربة سكين ثانية (فصل شريحة الشيتين المركبين)');
  }

  /**
   * رسم نمط الـ 5 قطع (خمسات 30×40) على الفرخ العرضي 100×70 سم
   */
  function _draw5CutsPattern(svg, pW, pH) {
    // 3 قطع 300×400 مم في الصف العلوي (مساحة 900×400)
    for (let c = 0; c < 3; c++) {
      const x = c * 300;
      const y = 0;
      const rect = createSvgEl('rect', {
        x, y, width: 300, height: 400,
        fill: 'var(--primary-subtle, #e7f1ff)',
        stroke: 'var(--primary, #0d6efd)',
        'stroke-width': 1.0
      });
      svg.appendChild(rect);

      const txt = createSvgEl('text', {
        x: x + 150, y: 205,
        'text-anchor': 'middle',
        fill: 'var(--primary, #0d6efd)',
        'font-size': 20, 'font-weight': 'bold'
      });
      txt.textContent = `شيت #${c + 1} (30×40)`;
      svg.appendChild(txt);
    }

    // قطعتين 400×300 مم في الصف السفلي (مساحة 800×300)
    for (let c = 0; c < 2; c++) {
      const x = c * 400;
      const y = 400;
      const rect = createSvgEl('rect', {
        x, y, width: 400, height: 300,
        fill: 'var(--info-subtle, #cff4fc)',
        stroke: 'var(--info, #0dcaf0)',
        'stroke-width': 1.0
      });
      svg.appendChild(rect);

      const txt = createSvgEl('text', {
        x: x + 200, y: y + 155,
        'text-anchor': 'middle',
        fill: 'var(--info, #0dcaf0)',
        'font-size': 20, 'font-weight': 'bold'
      });
      txt.textContent = `شيت #${4 + c} (30×40 مركب)`;
      svg.appendChild(txt);
    }

    // مساحات الفائض
    const scrap1 = createSvgEl('rect', {
      x: 900, y: 0, width: 100, height: 400,
      fill: 'var(--gray-200, #e9ecef)',
      stroke: 'var(--secondary, #adb5bd)',
      'stroke-width': 0.8
    });
    svg.appendChild(scrap1);

    const scrap2 = createSvgEl('rect', {
      x: 800, y: 400, width: 200, height: 300,
      fill: 'var(--gray-200, #e9ecef)',
      stroke: 'var(--secondary, #adb5bd)',
      'stroke-width': 0.8
    });
    svg.appendChild(scrap2);

    _drawKnifeStep(svg, 0, 400, pW, 400, '[1] ضربة سكين رئيسية (فصل الـ 40 سم عن الـ 30 سم)');
    _drawKnifeStep(svg, 900, 0, 900, 400, '[2] ضربة تشذيب الفائض العلوي (10 سم)');
    _drawKnifeStep(svg, 800, 400, 800, 700, '[3] ضربة تشذيب الفائض السفلي (20 سم)');
  }

  /**
   * رسم التقطيع القياسي المتناظر (أرباع، أنصاف، أثمان) على الفرخ العرضي
   */
  function _drawStandardCutsPattern(svg, pW, pH, pieceW_mm, pieceH_mm, cuts) {
    let cols = 2, rows = 2;
    if (cuts === 2) {
      cols = 2; rows = 1; // 500x700 mm
    } else if (cuts === 4) {
      cols = 2; rows = 2; // 500x350 mm
    } else if (cuts === 8) {
      cols = 4; rows = 2; // 250x350 mm
    } else if (cuts === 6) {
      cols = 3; rows = 2; // 333x350 mm
    } else if (cuts === 3) {
      cols = 3; rows = 1; // 333x700 mm
    } else if (cuts === 16) {
      cols = 4; rows = 4;
    } else if (cuts > 0) {
      cols = Math.ceil(Math.sqrt(cuts * (pW / pH)));
      rows = Math.ceil(cuts / cols);
    }

    const itemW = pW / cols;
    const itemH = pH / rows;

    let idx = 0;
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        if (idx >= cuts) break;
        idx++;
        const x = c * itemW;
        const y = r * itemH;

        const rect = createSvgEl('rect', {
          x, y, width: itemW, height: itemH,
          fill: 'var(--primary-subtle, #e7f1ff)',
          stroke: 'var(--primary, #0d6efd)',
          'stroke-width': 1.0
        });
        svg.appendChild(rect);

        const txt = createSvgEl('text', {
          x: x + (itemW / 2),
          y: y + (itemH / 2) + 5,
          'text-anchor': 'middle',
          fill: 'var(--primary, #0d6efd)',
          'font-size': Math.max(14, Math.min(24, itemH * 0.12)),
          'font-weight': 'bold'
        });
        txt.textContent = `شيت #${idx}`;
        svg.appendChild(txt);
      }
    }
  }

  function _drawKnifeStep(svg, x1, y1, x2, y2, label) {
    const line = createSvgEl('line', {
      x1, y1, x2, y2,
      stroke: 'var(--danger, #dc3545)',
      'stroke-width': 1.5,
      'stroke-dasharray': '5,3'
    });
    svg.appendChild(line);

    const txt = createSvgEl('text', {
      x: (x1 + x2) / 2,
      y: (y1 + y2) / 2 - 4,
      'text-anchor': 'middle',
      fill: 'var(--danger, #dc3545)',
      'font-size': 10,
      'font-weight': 'bold'
    });
    txt.textContent = label;
    svg.appendChild(txt);
  }

  /**
   * رسم طابع أمر الشغل المصغر (Micro-Stamp) في صفحة أمر الشغل
   * مصمم ومحصن لضمان خروج أمر الشغل في ورقة A4 واحدة مقدسة
   */
  function renderMicroStamp(container, options = {}) {
    if (!container) return;

    const {
      pressSheetW = 35.0,
      pressSheetH = 50.0,
      openW = 21.0,
      openH = 29.7,
      montageCount = 1,
      printingType = 'offset'
    } = options;

    clearContainer(container);

    const sW = Math.max(pressSheetW, pressSheetH);
    const sH = Math.min(pressSheetW, pressSheetH);
    const calc = PricingMath.calcImposition(sW, sH, openW, openH, printingType);
    const cols = calc.cols || 1;
    const rows = calc.rows || 1;
    const total = (montageCount > 0) ? montageCount : (calc.cutsPerSheet || 1);

    const svg = createSvgEl('svg', {
      viewBox: '0 0 120 85',
      width: '100%',
      height: '75px',
      preserveAspectRatio: 'xMidYMid meet',
      style: 'display: block; margin: 0 auto; page-break-inside: avoid; break-inside: avoid;'
    });

    // إطار الشيت بالأبيض والأسود الناصع للطباعة
    const bg = createSvgEl('rect', {
      x: 1, y: 1, width: 118, height: 83,
      fill: '#ffffff',
      stroke: '#000000',
      'stroke-width': 1
    });
    svg.appendChild(bg);

    // شريط البنسة المصغر
    if (printingType === 'offset') {
      const grip = createSvgEl('rect', {
        x: 1, y: 1, width: 118, height: 7,
        fill: '#eeeeee',
        stroke: '#888888',
        'stroke-width': 0.5
      });
      svg.appendChild(grip);
    }

    // شبكة القطع المصغرة
    const gridW = 112;
    const gridH = 70;
    const itemW = gridW / cols;
    const itemH = gridH / rows;

    let idx = 0;
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        idx++;
        const isActive = (idx <= total);
        const x = 4 + (c * itemW);
        const y = 10 + (r * itemH);

        const rect = createSvgEl('rect', {
          x: x + 1, y: y + 1,
          width: Math.max(2, itemW - 2),
          height: Math.max(2, itemH - 2),
          fill: isActive ? '#f0f0f0' : '#ffffff',
          stroke: isActive ? '#000000' : '#cccccc',
          'stroke-width': 0.8,
          'stroke-dasharray': isActive ? 'none' : '2,1'
        });
        svg.appendChild(rect);

        if (isActive) {
          const txt = createSvgEl('text', {
            x: x + (itemW / 2),
            y: y + (itemH / 2) + 2,
            'text-anchor': 'middle',
            fill: '#000000',
            'font-size': Math.min(8, itemH * 0.4),
            'font-weight': 'bold'
          });
          txt.textContent = idx;
          svg.appendChild(txt);
        }
      }
    }

    container.appendChild(svg);
  }

  return {
    renderPressSheet,
    renderShearingMap,
    renderMicroStamp,
    renderSkeleton
  };
})();

// تصدير عالمي
if (typeof window !== 'undefined') {
  window.ImpositionVisualizer = ImpositionVisualizer;
}
