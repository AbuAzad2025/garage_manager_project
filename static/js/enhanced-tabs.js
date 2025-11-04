(function() {
  'use strict';

  window.EnhancedTabs = {
    activeTabKey: 'enhanced_tabs_memory',
    
    init: function() {
      this.enhanceAllTabs();
      this.addTabMemory();
      this.addTabAnimations();
      this.addTabShortcuts();
      this.addTabCounter();
      
      console.log('✅ Enhanced Tabs System Ready');
    },
    
    enhanceAllTabs: function() {
      const tabContainers = document.querySelectorAll('.nav-tabs');
      
      tabContainers.forEach(container => {
        container.classList.add('enhanced-tabs');
        
        const tabs = container.querySelectorAll('.nav-link');
        tabs.forEach((tab, index) => {
          this.enhanceTab(tab, index);
        });
        
        this.addTabIndicator(container);
      });
    },
    
    enhanceTab: function(tab, index) {
      const icon = tab.querySelector('i');
      if (!icon && !tab.dataset.noIcon) {
        const defaultIcon = this.getDefaultIcon(tab.textContent);
        tab.innerHTML = `<i class="fas ${defaultIcon}"></i> ${tab.innerHTML}`;
      }
      
      tab.dataset.tabIndex = index;
      
      if (!tab.dataset.noShortcut && index < 9) {
        const shortcutBadge = document.createElement('span');
        shortcutBadge.className = 'tab-shortcut-badge';
        shortcutBadge.textContent = `Alt+${index + 1}`;
        shortcutBadge.style.cssText = `
          font-size: 9px;
          opacity: 0.5;
          margin-right: 5px;
          padding: 2px 4px;
          background: rgba(255,255,255,0.1);
          border-radius: 3px;
        `;
        tab.appendChild(shortcutBadge);
      }
      
      tab.addEventListener('click', (e) => {
        this.onTabClick(tab, e);
      });
    },
    
    getDefaultIcon: function(text) {
      const iconMap = {
        'تصفح': 'fa-search',
        'browse': 'fa-search',
        'تحرير': 'fa-edit',
        'edit': 'fa-edit',
        'sql': 'fa-database',
        'python': 'fa-code',
        'فهارس': 'fa-bolt',
        'indexes': 'fa-bolt',
        'صيانة': 'fa-wrench',
        'maintenance': 'fa-wrench',
        'logs': 'fa-file-alt',
        'سجلات': 'fa-file-alt',
        'backup': 'fa-save',
        'نسخ': 'fa-save',
        'restore': 'fa-upload',
        'استعادة': 'fa-upload',
        'import': 'fa-download',
        'استيراد': 'fa-download',
        'export': 'fa-upload',
        'تصدير': 'fa-upload',
        'schema': 'fa-sitemap',
        'بنية': 'fa-sitemap',
        'users': 'fa-users',
        'مستخدمين': 'fa-users',
        'settings': 'fa-cog',
        'إعدادات': 'fa-cog',
        'reports': 'fa-chart-bar',
        'تقارير': 'fa-chart-bar',
        'dashboard': 'fa-tachometer-alt',
        'لوحة': 'fa-tachometer-alt'
      };
      
      const textLower = text.toLowerCase().trim();
      for (const [key, icon] of Object.entries(iconMap)) {
        if (textLower.includes(key)) return icon;
      }
      
      return 'fa-circle';
    },
    
    addTabIndicator: function(container) {
      const indicator = document.createElement('div');
      indicator.className = 'tab-indicator';
      indicator.style.cssText = `
        position: absolute;
        bottom: 0;
        height: 3px;
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        border-radius: 3px 3px 0 0;
        z-index: 10;
      `;
      
      container.style.position = 'relative';
      container.appendChild(indicator);
      
      this.updateIndicator(container);
    },
    
    updateIndicator: function(container) {
      const indicator = container.querySelector('.tab-indicator');
      const activeTab = container.querySelector('.nav-link.active');
      
      if (indicator && activeTab) {
        const rect = activeTab.getBoundingClientRect();
        const containerRect = container.getBoundingClientRect();
        
        indicator.style.left = (rect.left - containerRect.left) + 'px';
        indicator.style.width = rect.width + 'px';
      }
    },
    
    onTabClick: function(tab, event) {
      const container = tab.closest('.nav-tabs');
      this.updateIndicator(container);
      
      const pageUrl = window.location.pathname;
      const tabHref = tab.getAttribute('href');
      
      if (tabHref && tabHref.includes('?tab=')) {
        const tabName = new URL(tabHref, window.location.origin).searchParams.get('tab');
        this.saveTabMemory(pageUrl, tabName);
      }
      
      this.addClickAnimation(tab);
    },
    
    addTabMemory: function() {
      const pageUrl = window.location.pathname;
      const savedTab = this.getTabMemory(pageUrl);
      
      if (savedTab) {
        const tabLink = document.querySelector(`.nav-link[href*="tab=${savedTab}"]`);
        if (tabLink && !tabLink.classList.contains('active')) {
          console.log('📌 استعادة آخر تاب:', savedTab);
        }
      }
    },
    
    saveTabMemory: function(page, tab) {
      try {
        const memory = JSON.parse(localStorage.getItem(this.activeTabKey) || '{}');
        memory[page] = tab;
        localStorage.setItem(this.activeTabKey, JSON.stringify(memory));
      } catch (e) {
        console.warn('⚠️ فشل حفظ التاب:', e);
      }
    },
    
    getTabMemory: function(page) {
      try {
        const memory = JSON.parse(localStorage.getItem(this.activeTabKey) || '{}');
        return memory[page];
      } catch (e) {
        return null;
      }
    },
    
    addTabAnimations: function() {
      const style = document.createElement('style');
      style.textContent = `
        .enhanced-tabs {
          background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
          padding: 0;
          border-radius: 10px 10px 0 0;
          box-shadow: 0 2px 8px rgba(0,0,0,0.1);
          margin-bottom: 0 !important;
        }
        
        .enhanced-tabs .nav-link {
          border: none !important;
          padding: 15px 25px;
          font-weight: 500;
          color: #495057;
          transition: all 0.3s ease;
          position: relative;
          border-radius: 0;
          background: transparent;
        }
        
        .enhanced-tabs .nav-link:hover {
          background: rgba(255,255,255,0.5);
          color: #667eea;
          transform: translateY(-2px);
        }
        
        .enhanced-tabs .nav-link.active {
          background: white !important;
          color: #667eea !important;
          font-weight: 600;
          box-shadow: 0 -3px 10px rgba(102, 126, 234, 0.2);
        }
        
        .enhanced-tabs .nav-link i {
          margin-left: 8px;
          transition: transform 0.3s ease;
        }
        
        .enhanced-tabs .nav-link:hover i {
          transform: scale(1.2) rotate(5deg);
        }
        
        .enhanced-tabs .nav-link.active i {
          color: #764ba2;
        }
        
        .tab-click-ripple {
          position: absolute;
          border-radius: 50%;
          background: rgba(102, 126, 234, 0.3);
          transform: scale(0);
          animation: ripple 0.6s ease-out;
          pointer-events: none;
        }
        
        @keyframes ripple {
          to {
            transform: scale(4);
            opacity: 0;
          }
        }
        
        .tab-content {
          background: white;
          border-radius: 0 0 10px 10px;
          box-shadow: 0 2px 15px rgba(0,0,0,0.1);
          padding: 25px;
        }
        
        .tab-pane {
          animation: fadeInTab 0.4s ease;
        }
        
        @keyframes fadeInTab {
          from {
            opacity: 0;
            transform: translateY(10px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
        
        .tab-counter {
          background: #667eea;
          color: white;
          padding: 2px 6px;
          border-radius: 10px;
          font-size: 11px;
          margin-right: 5px;
          font-weight: 600;
        }
        
        @media (max-width: 768px) {
          .enhanced-tabs .nav-link {
            padding: 12px 15px;
            font-size: 13px;
          }
          
          .tab-shortcut-badge {
            display: none !important;
          }
        }
      `;
      document.head.appendChild(style);
    },
    
    addClickAnimation: function(tab) {
      const ripple = document.createElement('span');
      ripple.className = 'tab-click-ripple';
      
      const rect = tab.getBoundingClientRect();
      const size = Math.max(rect.width, rect.height);
      
      ripple.style.width = ripple.style.height = size + 'px';
      ripple.style.left = '50%';
      ripple.style.top = '50%';
      ripple.style.marginLeft = -(size / 2) + 'px';
      ripple.style.marginTop = -(size / 2) + 'px';
      
      tab.style.position = 'relative';
      tab.style.overflow = 'hidden';
      tab.appendChild(ripple);
      
      setTimeout(() => ripple.remove(), 600);
    },
    
    addTabShortcuts: function() {
      document.addEventListener('keydown', (e) => {
        if (e.altKey && e.key >= '1' && e.key <= '9') {
          e.preventDefault();
          const index = parseInt(e.key) - 1;
          const tab = document.querySelector(`.nav-link[data-tab-index="${index}"]`);
          
          if (tab) {
            tab.click();
            
            if (window.toast) {
              const tabName = tab.textContent.trim().split('\n')[0];
              window.toast.info(`تم الانتقال إلى: ${tabName}`);
            }
          }
        }
        
        if (e.ctrlKey && e.key === 'ArrowRight') {
          e.preventDefault();
          this.switchToNextTab();
        }
        
        if (e.ctrlKey && e.key === 'ArrowLeft') {
          e.preventDefault();
          this.switchToPreviousTab();
        }
      });
    },
    
    switchToNextTab: function() {
      const activeTab = document.querySelector('.nav-link.active');
      if (!activeTab) return;
      
      const allTabs = Array.from(document.querySelectorAll('.nav-link'));
      const currentIndex = allTabs.indexOf(activeTab);
      const nextIndex = (currentIndex + 1) % allTabs.length;
      
      allTabs[nextIndex]?.click();
    },
    
    switchToPreviousTab: function() {
      const activeTab = document.querySelector('.nav-link.active');
      if (!activeTab) return;
      
      const allTabs = Array.from(document.querySelectorAll('.nav-link'));
      const currentIndex = allTabs.indexOf(activeTab);
      const prevIndex = currentIndex - 1 < 0 ? allTabs.length - 1 : currentIndex - 1;
      
      allTabs[prevIndex]?.click();
    },
    
    addTabCounter: function() {
      document.querySelectorAll('.nav-link').forEach(tab => {
        const href = tab.getAttribute('href');
        if (!href || href.startsWith('#')) return;
        
        const tabId = href.split('tab=')[1];
        if (!tabId) return;
        
        const countElement = document.querySelector(`[data-tab-count="${tabId}"]`);
        if (countElement) {
          const count = countElement.textContent || countElement.dataset.count;
          if (count && parseInt(count) > 0) {
            const badge = document.createElement('span');
            badge.className = 'tab-counter';
            badge.textContent = count;
            tab.appendChild(badge);
          }
        }
      });
    }
  };

  document.addEventListener('DOMContentLoaded', function() {
    EnhancedTabs.init();
    
    window.addEventListener('resize', function() {
      document.querySelectorAll('.nav-tabs').forEach(container => {
        EnhancedTabs.updateIndicator(container);
      });
    });
    
    const observer = new MutationObserver(function(mutations) {
      mutations.forEach(function(mutation) {
        if (mutation.target.classList && mutation.target.classList.contains('nav-link')) {
          const container = mutation.target.closest('.nav-tabs');
          if (container) {
            EnhancedTabs.updateIndicator(container);
          }
        }
      });
    });
    
    document.querySelectorAll('.nav-tabs').forEach(container => {
      observer.observe(container, {
        attributes: true,
        attributeFilter: ['class'],
        subtree: true
      });
    });
  });

  console.log('✅ Enhanced Tabs Module Loaded');
  
})();

