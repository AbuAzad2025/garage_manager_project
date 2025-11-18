(function() {
  'use strict';

  const UXEnhancements = {
    init() {
      this.initTooltips();
      this.initToasts();
      this.initQuickActionsFAB();
      this.initPasswordStrength();
      this.initLoadingStates();
      this.initMobileNav();
    },

    initTooltips() {
      if (typeof $ !== 'undefined' && $.fn.tooltip) {
        $('[data-toggle="tooltip"], [title]').tooltip();
      }
    },

    showToast(message, type = 'info', duration = 0) {
      return;
    },

    initToasts() {
      window.showToast = this.showToast.bind(this);
    },

    initQuickActionsFAB() {
      const fabHTML = `
        <div class="quick-actions-fab">
          <button class="fab-trigger" onclick="UXEnhancements.toggleFAB()">
            <i class="fas fa-plus"></i>
          </button>
          <div class="fab-menu" id="fabMenu">
            ${this.getFABMenuItems()}
          </div>
        </div>
      `;

      if (!document.querySelector('.quick-actions-fab')) {
        document.body.insertAdjacentHTML('beforeend', fabHTML);
      }
    },

    getFABMenuItems() {
      const items = [];
      
      // دائماً أظهر كل الخيارات
      items.push('<a href="/customers/create"><i class="fas fa-user-plus"></i> عميل جديد</a>');
      items.push('<a href="/sales/new"><i class="fas fa-shopping-cart"></i> فاتورة جديدة</a>');
      items.push('<a href="/service/new"><i class="fas fa-wrench"></i> طلب صيانة</a>');
      
      return items.join('');
    },

    toggleFAB() {
      const menu = document.getElementById('fabMenu');
      if (menu) {
        menu.classList.toggle('active');
      }
    },

    initPasswordStrength() {
      const passwordInputs = document.querySelectorAll('input[type="password"][name="password"]');
      
      passwordInputs.forEach(input => {
        if (input.closest('form[action*="login"]')) return;
        
        const strengthDiv = document.createElement('div');
        strengthDiv.className = 'password-strength';
        strengthDiv.innerHTML = '<div class="strength-bar weak"></div><small class="text-muted">ضعيف</small>';
        
        input.parentElement.appendChild(strengthDiv);
        
        input.addEventListener('input', (e) => {
          const password = e.target.value;
          const strength = this.calculatePasswordStrength(password);
          const bar = strengthDiv.querySelector('.strength-bar');
          const text = strengthDiv.querySelector('small');
          
          bar.className = `strength-bar ${strength.class}`;
          text.textContent = strength.text;
          text.className = `text-${strength.color}`;
        });
      });
    },

    calculatePasswordStrength(password) {
      let score = 0;
      
      if (password.length >= 8) score += 1;
      if (password.length >= 12) score += 1;
      if (/[a-z]/.test(password)) score += 1;
      if (/[A-Z]/.test(password)) score += 1;
      if (/[0-9]/.test(password)) score += 1;
      if (/[^a-zA-Z0-9]/.test(password)) score += 1;
      
      if (score <= 2) {
        return { class: 'weak', text: 'ضعيف', color: 'danger' };
      } else if (score <= 4) {
        return { class: 'medium', text: 'متوسط', color: 'warning' };
      } else {
        return { class: 'strong', text: 'قوي', color: 'success' };
      }
    },

    initLoadingStates() {
      document.querySelectorAll('form').forEach(form => {
        form.addEventListener('submit', function(e) {
          const submitBtn = this.querySelector('button[type="submit"]');
          if (submitBtn && !submitBtn.classList.contains('no-loading')) {
            submitBtn.classList.add('loading');
            
            if (!submitBtn.querySelector('.btn-spinner')) {
              const spinner = document.createElement('span');
              spinner.className = 'btn-spinner';
              spinner.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
              submitBtn.appendChild(spinner);
            }
          }
        });
      });
    },

    initMobileNav() {
      if (window.innerWidth <= 768 && !document.querySelector('.mobile-bottom-nav')) {
        const navHTML = `
          <nav class="mobile-bottom-nav">
            <a href="/" ${window.location.pathname === '/' ? 'class="active"' : ''}>
              <i class="fas fa-home"></i>
              <span>الرئيسية</span>
            </a>
            <a href="/customers/" ${window.location.pathname.includes('/customers') ? 'class="active"' : ''}>
              <i class="fas fa-users"></i>
              <span>العملاء</span>
            </a>
            <a href="/sales/" ${window.location.pathname.includes('/sales') ? 'class="active"' : ''}>
              <i class="fas fa-shopping-cart"></i>
              <span>المبيعات</span>
            </a>
            <a href="/service/list" ${window.location.pathname.includes('/service') ? 'class="active"' : ''}>
              <i class="fas fa-wrench"></i>
              <span>الصيانة</span>
            </a>
          </nav>
        `;
        
        document.body.insertAdjacentHTML('beforeend', navHTML);
      }
    },

    showLoading() {
      if (!document.querySelector('.loading-overlay')) {
        const overlay = document.createElement('div');
        overlay.className = 'loading-overlay';
        overlay.innerHTML = '<div class="loading-spinner"></div>';
        document.body.appendChild(overlay);
      }
    },

    hideLoading() {
      const overlay = document.querySelector('.loading-overlay');
      if (overlay) {
        overlay.remove();
      }
    }
  };

  window.UXEnhancements = UXEnhancements;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => UXEnhancements.init());
  } else {
    UXEnhancements.init();
  }

  window.showToast = UXEnhancements.showToast.bind(UXEnhancements);
  window.showLoading = UXEnhancements.showLoading.bind(UXEnhancements);
  window.hideLoading = UXEnhancements.hideLoading.bind(UXEnhancements);

})();

