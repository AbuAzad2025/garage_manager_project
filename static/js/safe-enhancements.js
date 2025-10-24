/**
 * ═══════════════════════════════════════════════════════════════════
 * ✨ Safe Enhancements - تحسينات آمنة لا تؤثر على الوظائف الموجودة
 * ═══════════════════════════════════════════════════════════════════
 * 
 * هذا الملف يضيف تحسينات تدريجية دون التأثير على الكود الموجود
 */

(function() {
  'use strict';
  
  // التأكد من تحميل الـ utilities أولاً
  if (!window.EventUtils || !window.PerfUtils) {
    // Utilities not loaded yet - safe enhancements will be limited
    return;
  }
  
  const { delegate, debounce, throttle } = window.EventUtils;
  const { requestCache } = window.PerfUtils;

  // ═══════════════════════════════════════════════════════════════════
  // 1. تحسين أداء البحث في الجداول
  // ═══════════════════════════════════════════════════════════════════
  
  function enhanceTableSearch() {
    const searchInputs = document.querySelectorAll('input[type="search"], input[placeholder*="بحث"]');
    
    searchInputs.forEach(input => {
      // استخدام debounce لتقليل عدد العمليات
      const originalHandler = input.oninput;
      
      if (originalHandler) {
        input.oninput = null;
        const debouncedHandler = debounce((e) => originalHandler.call(input, e), 300);
        input.addEventListener('input', debouncedHandler);
      }
    });
  }

  // ═══════════════════════════════════════════════════════════════════
  // 2. تحسين التمرير في الجداول الطويلة
  // ═══════════════════════════════════════════════════════════════════
  
  function enhanceTableScrolling() {
    const tables = document.querySelectorAll('.table-responsive');
    
    tables.forEach(container => {
      // إضافة مؤشر للتمرير
      const scrollIndicator = document.createElement('div');
      scrollIndicator.className = 'scroll-indicator';
      scrollIndicator.style.cssText = `
        position: sticky;
        top: 0;
        height: 3px;
        background: linear-gradient(90deg, #667eea 0%, transparent 100%);
        transform-origin: left;
        transform: scaleX(0);
        transition: transform 0.1s ease;
        z-index: 10;
      `;
      
      container.insertBefore(scrollIndicator, container.firstChild);
      
      // تحديث المؤشر عند التمرير
      const table = container.querySelector('table');
      if (table) {
        container.addEventListener('scroll', throttle(() => {
          const scrollLeft = container.scrollLeft;
          const scrollWidth = container.scrollWidth - container.clientWidth;
          const scrollPercent = scrollWidth > 0 ? scrollLeft / scrollWidth : 0;
          scrollIndicator.style.transform = `scaleX(${scrollPercent})`;
        }, 50), { passive: true });
      }
    });
  }

  // ═══════════════════════════════════════════════════════════════════
  // 3. تحسين النماذج - Auto-save Draft
  // ═══════════════════════════════════════════════════════════════════
  
  function enableAutoSaveDraft() {
    const forms = document.querySelectorAll('form[data-autosave="true"]');
    
    forms.forEach(form => {
      const formId = form.id || form.action;
      const storageKey = `draft_${formId}`;
      
      // استرجاع المسودة المحفوظة
      const savedDraft = localStorage.getItem(storageKey);
      if (savedDraft) {
        try {
          const data = JSON.parse(savedDraft);
          Object.keys(data).forEach(name => {
            const field = form.elements[name];
            if (field && !field.value) {
              field.value = data[name];
            }
          });
          // Draft restored successfully
        } catch (e) {
          // Error restoring draft - continue normally
        }
      }
      
      // حفظ تلقائي
      const saveHandler = debounce(() => {
        const formData = new FormData(form);
        const data = {};
        for (let [key, value] of formData.entries()) {
          if (key !== 'csrf_token') {
            data[key] = value;
          }
        }
        localStorage.setItem(storageKey, JSON.stringify(data));
        // Draft auto-saved to localStorage
      }, 2000);
      
      form.addEventListener('input', saveHandler);
      
      // حذف المسودة عند الإرسال الناجح
      form.addEventListener('submit', () => {
        setTimeout(() => {
          localStorage.removeItem(storageKey);
        }, 1000);
      });
    });
  }

  // ═══════════════════════════════════════════════════════════════════
  // 4. تحسين Modal Handling
  // ═══════════════════════════════════════════════════════════════════
  
  function enhanceModals() {
    // إغلاق Modal بـ Escape
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        const openModal = document.querySelector('.modal.show');
        if (openModal) {
          const closeBtn = openModal.querySelector('.close, [data-dismiss="modal"]');
          if (closeBtn) closeBtn.click();
        }
      }
    });
    
    // منع scroll في background عند فتح modal
    const modals = document.querySelectorAll('.modal');
    modals.forEach(modal => {
      modal.addEventListener('show.bs.modal', () => {
        document.body.style.overflow = 'hidden';
      });
      
      modal.addEventListener('hidden.bs.modal', () => {
        document.body.style.overflow = '';
      });
    });
  }

  // ═══════════════════════════════════════════════════════════════════
  // 5. تحسين Tooltips
  // ═══════════════════════════════════════════════════════════════════
  
  function enhanceTooltips() {
    // إضافة tooltips تلقائية لأي عنصر له title
    const elements = document.querySelectorAll('[title]:not([data-toggle="tooltip"])');
    
    elements.forEach(el => {
      if (el.title && typeof $ !== 'undefined' && $.fn.tooltip) {
        $(el).tooltip({
          trigger: 'hover',
          placement: 'auto',
          boundary: 'window'
        });
      }
    });
  }

  // ═══════════════════════════════════════════════════════════════════
  // 6. تحسين النسخ إلى الحافظة
  // ═══════════════════════════════════════════════════════════════════
  
  function enableCopyToClipboard() {
    // إضافة وظيفة نسخ لأي عنصر له data-copy
    delegate(document, 'click', '[data-copy]', async function(e) {
      e.preventDefault();
      const textToCopy = this.dataset.copy || this.textContent;
      
      try {
        await navigator.clipboard.writeText(textToCopy);
        
        // تغيير مؤقت للإشارة للنجاح
        const originalText = this.textContent;
        const originalIcon = this.innerHTML;
        
        if (this.querySelector('i')) {
          this.innerHTML = '<i class="fas fa-check text-success"></i> تم النسخ';
        } else {
          this.textContent = '✅ تم النسخ';
        }
        
        setTimeout(() => {
          if (this.querySelector('i')) {
            this.innerHTML = originalIcon;
          } else {
            this.textContent = originalText;
          }
        }, 2000);
      } catch (err) {
        // Copy failed - show user-friendly message
        alert('فشل النسخ إلى الحافظة');
      }
    });
  }

  // ═══════════════════════════════════════════════════════════════════
  // 7. تحسين Print Handling
  // ═══════════════════════════════════════════════════════════════════
  
  function enhancePrintHandling() {
    // إضافة معالجة أفضل للطباعة
    window.addEventListener('beforeprint', () => {
      // Preparing for print
      document.body.classList.add('is-printing');
    });
    
    window.addEventListener('afterprint', () => {
      // Print finished
      document.body.classList.remove('is-printing');
    });
  }

  // ═══════════════════════════════════════════════════════════════════
  // 8. تحسين Form Validation
  // ═══════════════════════════════════════════════════════════════════
  
  function enhanceFormValidation() {
    const forms = document.querySelectorAll('form[novalidate]');
    
    forms.forEach(form => {
      form.addEventListener('submit', function(e) {
        if (!this.checkValidity()) {
          e.preventDefault();
          e.stopPropagation();
          
          // إضافة class للتمييز
          this.classList.add('was-validated');
          
          // التركيز على أول حقل خاطئ
          const firstInvalid = this.querySelector(':invalid');
          if (firstInvalid) {
            firstInvalid.focus();
            firstInvalid.scrollIntoView({ behavior: 'smooth', block: 'center' });
          }
        }
      });
    });
  }

  // ═══════════════════════════════════════════════════════════════════
  // 9. تحسين Back to Top Button
  // ═══════════════════════════════════════════════════════════════════
  
  function addBackToTopButton() {
    // إنشاء زر العودة للأعلى (فقط إذا لم يكن موجوداً)
    if (document.getElementById('back-to-top')) return;
    
    const btn = document.createElement('button');
    btn.id = 'back-to-top';
    btn.innerHTML = '<i class="fas fa-arrow-up"></i>';
    btn.title = 'العودة للأعلى';
    btn.style.cssText = `
      position: fixed;
      bottom: 20px;
      left: 20px;
      width: 50px;
      height: 50px;
      border-radius: 50%;
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: white;
      border: none;
      box-shadow: 0 4px 12px rgba(0,0,0,0.2);
      cursor: pointer;
      display: none;
      z-index: 1000;
      transition: all 0.3s ease;
      font-size: 18px;
    `;
    
    document.body.appendChild(btn);
    
    // إظهار/إخفاء الزر
    window.addEventListener('scroll', throttle(() => {
      if (window.pageYOffset > 300) {
        btn.style.display = 'block';
      } else {
        btn.style.display = 'none';
      }
    }, 100), { passive: true });
    
    // العودة للأعلى
    btn.addEventListener('click', () => {
      window.scrollTo({
        top: 0,
        behavior: 'smooth'
      });
    });
    
    // تأثير hover
    btn.addEventListener('mouseenter', () => {
      btn.style.transform = 'scale(1.1)';
    });
    
    btn.addEventListener('mouseleave', () => {
      btn.style.transform = 'scale(1)';
    });
  }

  // ═══════════════════════════════════════════════════════════════════
  // 10. تحسين Loading States
  // ═══════════════════════════════════════════════════════════════════
  
  function enhanceLoadingStates() {
    // إضافة loading state تلقائي للأزرار عند الإرسال
    const forms = document.querySelectorAll('form');
    
    forms.forEach(form => {
      form.addEventListener('submit', function(e) {
        const submitBtn = this.querySelector('button[type="submit"], input[type="submit"]');
        
        if (submitBtn && !submitBtn.dataset.noLoading) {
          submitBtn.disabled = true;
          
          const originalContent = submitBtn.innerHTML;
          submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> جاري الحفظ...';
          
          // استعادة بعد 10 ثواني (safety)
          setTimeout(() => {
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalContent;
          }, 10000);
        }
      });
    });
  }

  // ═══════════════════════════════════════════════════════════════════
  // 11. تحسين Dropdown Menus
  // ═══════════════════════════════════════════════════════════════════
  
  function enhanceDropdowns() {
    // إغلاق dropdown عند النقر خارجه
    const dropdowns = document.querySelectorAll('.dropdown-toggle');
    
    dropdowns.forEach(dropdown => {
      const menu = dropdown.nextElementSibling;
      
      if (menu && menu.classList.contains('dropdown-menu')) {
        document.addEventListener('click', (e) => {
          if (!dropdown.contains(e.target) && !menu.contains(e.target)) {
            menu.classList.remove('show');
          }
        });
      }
    });
  }

  // ═══════════════════════════════════════════════════════════════════
  // 12. تحسين Keyboard Navigation
  // ═══════════════════════════════════════════════════════════════════
  
  function enhanceKeyboardNavigation() {
    // Ctrl+S للحفظ السريع
    document.addEventListener('keydown', (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        const activeForm = document.querySelector('form:not([data-no-shortcut])');
        if (activeForm) {
          e.preventDefault();
          const submitBtn = activeForm.querySelector('button[type="submit"]');
          if (submitBtn) {
            submitBtn.click();
            // Quick save with Ctrl+S
          }
        }
      }
      
      // Escape لإلغاء
      if (e.key === 'Escape') {
        const cancelBtn = document.querySelector('a[href*="cancel"], .btn-secondary:not([data-dismiss])');
        if (cancelBtn && !document.querySelector('.modal.show')) {
          // Cancel with Escape (only if no modal is open)
        }
      }
    });
  }

  // ═══════════════════════════════════════════════════════════════════
  // 13. تحسين Table Row Highlighting
  // ═══════════════════════════════════════════════════════════════════
  
  function enhanceTableRowHighlight() {
    const tables = document.querySelectorAll('.table tbody');
    
    tables.forEach(tbody => {
      delegate(tbody, 'mouseenter', 'tr', function() {
        this.style.backgroundColor = 'rgba(102, 126, 234, 0.1)';
      });
      
      delegate(tbody, 'mouseleave', 'tr', function() {
        this.style.backgroundColor = '';
      });
    });
  }

  // ═══════════════════════════════════════════════════════════════════
  // 14. تحسين AJAX Error Handling
  // ═══════════════════════════════════════════════════════════════════
  
  function setupGlobalErrorHandler() {
    // معالج عام للأخطاء في AJAX requests
    window.addEventListener('unhandledrejection', (event) => {
      // Unhandled promise rejection detected
      
      // يمكن إضافة إشعار للمستخدم
      if (event.reason && event.reason.message) {
        const message = event.reason.message;
        if (message.includes('fetch') || message.includes('network')) {
          // Network connection issue detected
        }
      }
    });
  }

  // ═══════════════════════════════════════════════════════════════════
  // 15. تحسين Number Input Formatting
  // ═══════════════════════════════════════════════════════════════════
  
  function enhanceNumberInputs() {
    const numberInputs = document.querySelectorAll('input[type="number"]');
    
    numberInputs.forEach(input => {
      // منع الأرقام السالبة إذا كان min=0
      if (input.min === '0') {
        input.addEventListener('keydown', (e) => {
          if (e.key === '-') {
            e.preventDefault();
          }
        });
      }
      
      // تحديد النص عند التركيز
      input.addEventListener('focus', function() {
        this.select();
      });
    });
  }

  // ═══════════════════════════════════════════════════════════════════
  // 16. تحسين Date Inputs
  // ═══════════════════════════════════════════════════════════════════
  
  function enhanceDateInputs() {
    const dateInputs = document.querySelectorAll('input[type="date"], input[type="datetime-local"]');
    
    dateInputs.forEach(input => {
      // إضافة أيقونة تقويم
      if (!input.classList.contains('has-icon')) {
        input.classList.add('has-icon');
        const wrapper = document.createElement('div');
        wrapper.style.position = 'relative';
        wrapper.style.display = 'inline-block';
        wrapper.style.width = '100%';
        
        input.parentNode.insertBefore(wrapper, input);
        wrapper.appendChild(input);
        
        const icon = document.createElement('i');
        icon.className = 'fas fa-calendar-alt';
        icon.style.cssText = `
          position: absolute;
          left: 10px;
          top: 50%;
          transform: translateY(-50%);
          pointer-events: none;
          color: #6c757d;
        `;
        
        wrapper.appendChild(icon);
        input.style.paddingLeft = '35px';
      }
    });
  }

  // ═══════════════════════════════════════════════════════════════════
  // 17. تحسين Select Elements
  // ═══════════════════════════════════════════════════════════════════
  
  function enhanceSelects() {
    const selects = document.querySelectorAll('select:not(.select2-hidden-accessible)');
    
    selects.forEach(select => {
      // إضافة تأثير عند التغيير
      select.addEventListener('change', function() {
        this.classList.add('just-changed');
        setTimeout(() => {
          this.classList.remove('just-changed');
        }, 300);
      });
    });
  }

  // ═══════════════════════════════════════════════════════════════════
  // 18. Auto-resize Textarea
  // ═══════════════════════════════════════════════════════════════════
  
  function autoResizeTextareas() {
    const textareas = document.querySelectorAll('textarea[data-autoresize="true"]');
    
    textareas.forEach(textarea => {
      const resize = () => {
        textarea.style.height = 'auto';
        textarea.style.height = textarea.scrollHeight + 'px';
      };
      
      textarea.addEventListener('input', resize);
      resize(); // تطبيق فوري
    });
  }

  // ═══════════════════════════════════════════════════════════════════
  // 19. تحسين Focus Management
  // ═══════════════════════════════════════════════════════════════════
  
  function enhanceFocusManagement() {
    // التركيز التلقائي على أول حقل في النماذج
    const forms = document.querySelectorAll('form[data-autofocus="true"]');
    
    forms.forEach(form => {
      const firstInput = form.querySelector('input:not([type="hidden"]), select, textarea');
      if (firstInput && !firstInput.value) {
        setTimeout(() => firstInput.focus(), 100);
      }
    });
  }

  // ═══════════════════════════════════════════════════════════════════
  // 20. تحسين Animation Performance
  // ═══════════════════════════════════════════════════════════════════
  
  function optimizeAnimations() {
    // تقليل الحركات إذا طلب المستخدم ذلك
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    
    if (prefersReducedMotion) {
      document.documentElement.style.setProperty('--transition-fast', '0s');
      document.documentElement.style.setProperty('--transition-normal', '0s');
      document.documentElement.style.setProperty('--transition-slow', '0s');
      // Reduced motion for accessibility
    }
  }

  // ═══════════════════════════════════════════════════════════════════
  // Initialize All Enhancements - تفعيل جميع التحسينات
  // ═══════════════════════════════════════════════════════════════════
  
  function initAllEnhancements() {
    try {
      enhanceTableSearch();
      enhanceTableScrolling();
      enableAutoSaveDraft();
      enhanceModals();
      enhanceTooltips();
      enableCopyToClipboard();
      enhancePrintHandling();
      enhanceFormValidation();
      enhanceTableRowHighlight();
      setupGlobalErrorHandler();
      enhanceNumberInputs();
      enhanceDateInputs();
      enhanceSelects();
      autoResizeTextareas();
      enhanceFocusManagement();
      enhanceDropdowns();
      optimizeAnimations();
      addBackToTopButton();
      
      // All safe enhancements activated successfully
    } catch (error) {
      // Error activating enhancements - system continues normally
    }
  }

  // ═══════════════════════════════════════════════════════════════════
  // Auto-init when DOM is ready
  // ═══════════════════════════════════════════════════════════════════
  
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAllEnhancements);
  } else {
    initAllEnhancements();
  }
  
  // Re-init on AJAX page updates (if needed)
  window.reinitEnhancements = initAllEnhancements;
  
  // Export للاستخدام الخارجي
  window.SafeEnhancements = {
    init: initAllEnhancements,
    enhanceTableSearch,
    enhanceTableScrolling,
    enableAutoSaveDraft,
    enhanceModals,
    enhanceTooltips,
    enableCopyToClipboard,
    enhancePrintHandling,
    enhanceFormValidation,
    enhanceTableRowHighlight,
    enhanceNumberInputs,
    enhanceDateInputs,
    enhanceSelects,
    autoResizeTextareas,
    enhanceFocusManagement,
    enhanceDropdowns,
    optimizeAnimations,
    addBackToTopButton
  };

})();

