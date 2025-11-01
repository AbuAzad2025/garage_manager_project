/**
 * ═══════════════════════════════════════════════════════════════════
 * 🌙 Dark Mode Toggle للوحدة السرية
 * ═══════════════════════════════════════════════════════════════════
 */

(function() {
  'use strict';
  
  const DARK_MODE_KEY = 'securityDarkMode';
  
  /**
   * تطبيق Dark Mode
   */
  function applyDarkMode(isDark) {
    const body = document.body;
    
    if (isDark) {
      body.classList.add('dark-mode');
    } else {
      body.classList.remove('dark-mode');
    }
    
    // حفظ التفضيل
    localStorage.setItem(DARK_MODE_KEY, isDark ? 'true' : 'false');
    
    // تحديث الأيقونة
    updateToggleIcon(isDark);
  }
  
  /**
   * تحديث أيقونة الزر
   */
  function updateToggleIcon(isDark) {
    const btn = document.getElementById('darkModeToggle');
    if (!btn) return;
    
    const icon = btn.querySelector('i');
    if (icon) {
      icon.className = isDark ? 'fas fa-sun' : 'fas fa-moon';
    }
    
    btn.title = isDark ? 'تفعيل الوضع النهاري' : 'تفعيل الوضع الليلي';
  }
  
  /**
   * التبديل بين الأوضاع
   */
  window.toggleDarkMode = function() {
    const isDark = !document.body.classList.contains('dark-mode');
    applyDarkMode(isDark);
    
    // Animation عند التبديل
    document.body.style.transition = 'background-color 0.5s ease';
    
    // رسالة توضيحية
    showDarkModeToast(isDark);
  };
  
  /**
   * إشعار عند التبديل
   */
  function showDarkModeToast(isDark) {
    const toast = document.createElement('div');
    toast.style.cssText = `
      position: fixed;
      top: 20px;
      left: 50%;
      transform: translateX(-50%);
      background: ${isDark ? '#0f3460' : '#fff'};
      color: ${isDark ? '#e0e0e0' : '#333'};
      padding: 12px 20px;
      border-radius: 8px;
      box-shadow: 0 4px 15px rgba(0,0,0,0.3);
      z-index: 99999;
      animation: slideDown 0.3s ease;
      font-weight: bold;
    `;
    
    toast.innerHTML = `
      <i class="fas fa-${isDark ? 'moon' : 'sun'}"></i>
      ${isDark ? '🌙 الوضع الليلي مفعّل' : '☀️ الوضع النهاري مفعّل'}
    `;
    
    document.body.appendChild(toast);
    
    setTimeout(() => {
      toast.style.animation = 'slideUp 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, 2000);
  }
  
  /**
   * إضافة زر Dark Mode
   */
  function addDarkModeButton() {
    // إضافة الزر فقط في صفحات الوحدة السرية
    if (!window.location.pathname.startsWith('/security')) return;
    
    const button = document.createElement('button');
    button.id = 'darkModeToggle';
    button.className = 'dark-mode-toggle';
    button.innerHTML = '<i class="fas fa-moon"></i>';
    button.onclick = toggleDarkMode;
    button.setAttribute('aria-label', 'تبديل الوضع الليلي');
    
    document.body.appendChild(button);
  }
  
  /**
   * تحميل التفضيل المحفوظ
   */
  function loadSavedPreference() {
    const saved = localStorage.getItem(DARK_MODE_KEY);
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    
    // استخدام التفضيل المحفوظ أو تفضيلات النظام
    const isDark = saved === 'true' || (saved === null && prefersDark);
    
    if (isDark) {
      applyDarkMode(true);
    }
  }
  
  /**
   * مراقبة تغيير تفضيلات النظام
   */
  function watchSystemPreference() {
    const darkModeQuery = window.matchMedia('(prefers-color-scheme: dark)');
    
    darkModeQuery.addEventListener('change', (e) => {
      // تطبيق فقط إذا لم يكن هناك تفضيل محفوظ
      if (localStorage.getItem(DARK_MODE_KEY) === null) {
        applyDarkMode(e.matches);
      }
    });
  }
  
  // ═══ التهيئة ═══
  document.addEventListener('DOMContentLoaded', function() {
    loadSavedPreference();
    addDarkModeButton();
    watchSystemPreference();
    
    console.log('✅ Dark Mode جاهز (زر عائم على اليسار)');
  });
  
  // تطبيق سريع قبل التحميل لتجنب flash
  loadSavedPreference();
  
})();

