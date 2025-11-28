/**
 * ═══════════════════════════════════════════════════════════════════
 * 🚀 Security Module - Mega Enhancements
 * ═══════════════════════════════════════════════════════════════════
 * 
 * يحتوي على جميع التحسينات المتبقية:
 * - Tab Memory
 * - Favorites/Bookmarks
 * - Quick Actions Menu (Ctrl+Space)
 * - Notification Center
 * - Settings Search
 * - وأكثر...
 */

(function() {
  'use strict';
  
  // ═══════════════════════════════════════════════════════════════════
  // 📌 Tab Memory - حفظ التبويب الأخير
  // ═══════════════════════════════════════════════════════════════════
  
  function initTabMemory() {
    const TAB_MEMORY_KEY = 'security_tab_memory';
    
    // حفظ التبويب الحالي
    const currentPath = window.location.pathname;
    const currentTab = new URLSearchParams(window.location.search).get('tab');
    
    if (currentPath.startsWith('/security/') && currentTab) {
      const memory = JSON.parse(localStorage.getItem(TAB_MEMORY_KEY) || '{}');
      memory[currentPath] = currentTab;
      localStorage.setItem(TAB_MEMORY_KEY, JSON.stringify(memory));
    }
    
    // استعادة التبويب عند العودة
    document.querySelectorAll('a[href*="/security/"]').forEach(link => {
      const url = new URL(link.href, window.location.origin);
      const path = url.pathname;
      const memory = JSON.parse(localStorage.getItem(TAB_MEMORY_KEY) || '{}');
      
      if (memory[path] && !url.searchParams.has('tab')) {
        url.searchParams.set('tab', memory[path]);
        link.href = url.toString();
      }
    });
  }
  
  // ═══════════════════════════════════════════════════════════════════
  // ⭐ Favorites/Bookmarks
  // ═══════════════════════════════════════════════════════════════════
  
  function initFavorites() {
    const FAVORITES_KEY = 'security_favorites';
    
    // إضافة زر المفضلة في كل صفحة
    if (window.location.pathname.startsWith('/security/')) {
      addFavoriteButton();
    }
    
    // إضافة قائمة المفضلة في الصفحة الرئيسية
    if (window.location.pathname === '/security/' || window.location.pathname === '/security') {
      showFavoritesWidget();
    }
  }
  
  function addFavoriteButton() {
    const nav = document.querySelector('.mb-3.d-flex');
    if (!nav) return;
    
    const currentPage = {
      url: window.location.pathname + window.location.search,
      title: document.title,
      timestamp: new Date().toISOString()
    };
    
    const favorites = JSON.parse(localStorage.getItem('security_favorites') || '[]');
    const isFavorite = favorites.some(f => f.url === currentPage.url);
    
    const btn = document.createElement('button');
    btn.className = `btn btn-sm ${isFavorite ? 'btn-warning' : 'btn-outline-warning'}`;
    btn.innerHTML = `<i class="fas fa-star"></i> ${isFavorite ? 'مفضل' : 'إضافة للمفضلة'}`;
    btn.onclick = () => toggleFavorite(currentPage, btn);
    
    nav.querySelector('div').appendChild(btn);
  }
  
  function toggleFavorite(page, btn) {
    let favorites = JSON.parse(localStorage.getItem('security_favorites') || '[]');
    const index = favorites.findIndex(f => f.url === page.url);
    
    if (index >= 0) {
      favorites.splice(index, 1);
      btn.className = 'btn btn-sm btn-outline-warning';
      btn.innerHTML = '<i class="fas fa-star"></i> إضافة للمفضلة';
    } else {
      favorites.push(page);
      btn.className = 'btn btn-sm btn-warning';
      btn.innerHTML = '<i class="fas fa-star"></i> مفضل';
    }
    
    localStorage.setItem('security_favorites', JSON.stringify(favorites));
  }
  
  function showFavoritesWidget() {
    const favorites = JSON.parse(localStorage.getItem('security_favorites') || '[]');
    if (favorites.length === 0) return;
    
    const widget = document.createElement('div');
    widget.className = 'card border-warning mb-4';
    widget.innerHTML = `
      <div class="card-header bg-warning text-dark">
        <h6 class="mb-0"><i class="fas fa-star"></i> المفضلة (${favorites.length})</h6>
      </div>
      <div class="card-body">
        <div class="list-group">
          ${favorites.slice(0, 5).map(fav => `
            <a href="${fav.url}" class="list-group-item list-group-item-action">
              <div class="d-flex justify-content-between">
                <span><i class="fas fa-bookmark text-warning"></i> ${fav.title.replace(' - وحدة الأمان المتقدمة', '')}</span>
                <small class="text-muted">${new Date(fav.timestamp).toLocaleDateString('ar-EG')}</small>
              </div>
            </a>
          `).join('')}
        </div>
        ${favorites.length > 5 ? `<small class="text-muted d-block mt-2">... و ${favorites.length - 5} أخرى</small>` : ''}
      </div>
    `;
    
    // إضافة في أول container-fluid
    const container = document.querySelector('.container-fluid');
    const firstAlert = container.querySelector('.alert');
    container.insertBefore(widget, firstAlert);
  }
  
  // ═══════════════════════════════════════════════════════════════════
  // ⚡ Quick Actions Menu (Ctrl+Space)
  // ═══════════════════════════════════════════════════════════════════
  
  function initQuickActions() {
    document.addEventListener('keydown', function(e) {
      if (e.ctrlKey && e.key === ' ') {
        e.preventDefault();
        showQuickActionsMenu();
      }
    });
  }
  
  function showQuickActionsMenu() {
    // قائمة الإجراءات السريعة
    const actions = [
      {icon: '🗄️', name: 'Database Manager', url: '/security/database-manager', shortcut: 'Ctrl+Shift+D'},
      {icon: '🤖', name: 'AI Hub', url: '/security/ai-hub', shortcut: 'Ctrl+Shift+A'},
      {icon: '🛡️', name: 'Security Center', url: '/security/security-center', shortcut: 'Ctrl+Shift+S'},
      {icon: '👥', name: 'Users Center', url: '/security/users-center', shortcut: 'Ctrl+Shift+U'},
      {icon: '🔧', name: 'Tools Center', url: '/security/tools-center', shortcut: 'Ctrl+Shift+T'},
      {icon: '📊', name: 'Reports Center', url: '/security/reports-center', shortcut: 'Ctrl+Shift+R'},
      {icon: '⚙️', name: 'Settings Center', url: '/security/settings-center', shortcut: 'Ctrl+Shift+G'},
      {icon: '📒', name: 'Ledger Control', url: '/security/ledger-control/', shortcut: 'Ctrl+Shift+L'},
      {icon: '🔌', name: 'Integrations', url: '/security/integrations', shortcut: 'Ctrl+Shift+I'},
      {icon: '🚨', name: 'Emergency Tools', url: '/security/emergency-tools', shortcut: 'Ctrl+Shift+E'},
      {icon: '❓', name: 'Help', url: '/security/help', shortcut: 'Ctrl+Shift+H'},
      {icon: '🗺️', name: 'Sitemap', url: '/security/sitemap', shortcut: ''},
    ];
    
    const modal = document.createElement('div');
    modal.className = 'quick-actions-modal';
    modal.innerHTML = `
      <div style="
        position: fixed;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        background: white;
        border-radius: 15px;
        padding: 25px;
        max-width: 600px;
        width: 90%;
        box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        z-index: 99999;
      ">
        <div class="text-center mb-3">
          <h4><i class="fas fa-bolt text-warning"></i> إجراءات سريعة</h4>
          <input type="text" id="quickActionsSearch" class="form-control mt-2" 
                 placeholder="🔍 ابحث عن إجراء..." autofocus>
        </div>
        
        <div id="quickActionsList" style="max-height: 400px; overflow-y: auto;">
          ${actions.map((action, index) => `
            <div class="quick-action-item p-2 rounded mb-1" style="cursor: pointer; transition: all 0.2s;"
                 data-name="${action.name.toLowerCase()}"
                 data-index="${index}"
                 onmouseover="this.style.background='#f0f0f0'"
                 onmouseout="this.style.background=''"
                 onclick="window.location.href='${action.url}'; this.closest('.quick-actions-modal').remove();">
              <div class="d-flex justify-content-between align-items-center">
                <div>
                  <span style="font-size: 1.5rem;">${action.icon}</span>
                  <strong class="ms-2">${action.name}</strong>
                </div>
                ${action.shortcut ? `<kbd style="font-size: 0.75rem;">${action.shortcut}</kbd>` : ''}
              </div>
            </div>
          `).join('')}
        </div>
        
        <div class="text-center mt-3">
          <small class="text-muted">
            <kbd>↑↓</kbd> التنقل | <kbd>Enter</kbd> اختيار | <kbd>Esc</kbd> إغلاق
          </small>
        </div>
      </div>
    `;
    
    modal.style.cssText = `
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: rgba(0,0,0,0.5);
      z-index: 99998;
    `;
    
    modal.onclick = (e) => {
      if (e.target === modal) modal.remove();
    };
    
    document.body.appendChild(modal);
    
    // البحث في الإجراءات
    const searchInput = document.getElementById('quickActionsSearch');
    searchInput.addEventListener('input', function() {
      const query = this.value.toLowerCase();
      document.querySelectorAll('.quick-action-item').forEach(item => {
        const name = item.dataset.name;
        item.style.display = name.includes(query) ? '' : 'none';
      });
    });
    
    // التنقل بالأسهم
    let selectedIndex = 0;
    document.addEventListener('keydown', function handler(e) {
      const items = Array.from(document.querySelectorAll('.quick-action-item:not([style*="display: none"])'));
      
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        selectedIndex = Math.min(selectedIndex + 1, items.length - 1);
        highlightItem(items, selectedIndex);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        selectedIndex = Math.max(selectedIndex - 1, 0);
        highlightItem(items, selectedIndex);
      } else if (e.key === 'Enter') {
        e.preventDefault();
        items[selectedIndex]?.click();
      } else if (e.key === 'Escape') {
        modal.remove();
        document.removeEventListener('keydown', handler);
      }
    });
    
    function highlightItem(items, index) {
      items.forEach((item, i) => {
        item.style.background = i === index ? '#667eea' : '';
        item.style.color = i === index ? 'white' : '';
      });
    }
  }
  
  // ═══════════════════════════════════════════════════════════════════
  // 🔔 Notification Center موحد
  // ═══════════════════════════════════════════════════════════════════
  
  function initNotificationCenter() {
    addNotificationBell();
  }
  
  function addNotificationBell() {
    const nav = document.querySelector('.mb-3.d-flex');
    if (!nav) return;
    
    const notifications = getNotifications();
    const unreadCount = notifications.filter(n => !n.read).length;
    
    const bell = document.createElement('button');
    bell.className = 'btn btn-sm btn-outline-primary position-relative';
    bell.innerHTML = `
      <i class="fas fa-bell"></i>
      ${unreadCount > 0 ? `<span class="position-absolute top-0 start-100 translate-middle badge rounded-pill bg-danger">${unreadCount}</span>` : ''}
    `;
    bell.onclick = showNotificationCenter;
    
    nav.querySelector('div').appendChild(bell);
  }
  
  function getNotifications() {
    // محاكاة - في الإنتاج تُجلب من API
    return JSON.parse(localStorage.getItem('security_notifications') || '[]');
  }
  
  function showNotificationCenter() {
    const notifications = getNotifications();
    
    const modal = document.createElement('div');
    modal.className = 'notification-center-modal';
    modal.innerHTML = `
      <div style="
        position: fixed;
        top: 70px;
        left: 50%;
        transform: translateX(-50%);
        background: white;
        border-radius: 10px;
        padding: 20px;
        max-width: 500px;
        width: 90%;
        max-height: 500px;
        overflow-y: auto;
        box-shadow: 0 10px 40px rgba(0,0,0,0.3);
        z-index: 99999;
      ">
        <div class="d-flex justify-content-between align-items-center mb-3">
          <h5 class="mb-0"><i class="fas fa-bell"></i> الإشعارات</h5>
          <div>
            <button class="btn btn-sm btn-outline-secondary me-2" onclick="markAllAsRead()">
              <i class="fas fa-check"></i> تحديد الكل كمقروء
            </button>
            <button class="close" onclick="this.closest('.notification-center-modal').remove()"><span aria-hidden="true">&times;</span></button>
          </div>
        </div>
        
        ${notifications.length === 0 ? `
          <div class="alert alert-info text-center">
            <i class="fas fa-inbox"></i><br>
            لا توجد إشعارات
          </div>
        ` : notifications.map(notif => `
          <div class="alert alert-${notif.type || 'info'} ${notif.read ? 'opacity-50' : ''} mb-2">
            <div class="d-flex justify-content-between">
              <div>
                <strong>${notif.title}</strong>
                <br><small>${notif.message}</small>
                <br><small class="text-muted">${new Date(notif.timestamp).toLocaleString('ar-EG')}</small>
              </div>
              ${!notif.read ? '<span class="badge bg-primary">جديد</span>' : ''}
            </div>
          </div>
        `).join('')}
      </div>
    `;
    
    modal.style.cssText = `
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: rgba(0,0,0,0.3);
      z-index: 99998;
    `;
    
    modal.onclick = (e) => {
      if (e.target === modal) modal.remove();
    };
    
    document.body.appendChild(modal);
  }
  
  window.markAllAsRead = function() {
    let notifications = getNotifications();
    notifications.forEach(n => n.read = true);
    localStorage.setItem('security_notifications', JSON.stringify(notifications));
    document.querySelector('.notification-center-modal')?.remove();
    location.reload();
  };
  
  // ═══════════════════════════════════════════════════════════════════
  // 🔍 Settings Search
  // ═══════════════════════════════════════════════════════════════════
  
  function initSettingsSearch() {
    // إذا كنا في Settings Center
    if (!window.location.pathname.includes('settings-center')) return;
    
    // إضافة شريط بحث
    const container = document.querySelector('.container-fluid');
    if (!container) return;
    
    const searchBox = document.createElement('div');
    searchBox.className = 'mb-3';
    searchBox.innerHTML = `
      <div class="input-group">
        <span class="input-group-text bg-primary text-white">
          <i class="fas fa-search"></i>
        </span>
        <input type="text" id="settingsSearch" class="form-control" 
               placeholder="🔍 ابحث في الإعدادات...">
      </div>
    `;
    
    const firstCard = container.querySelector('.card');
    if (firstCard) {
      firstCard.parentNode.insertBefore(searchBox, firstCard);
    }
    
    document.getElementById('settingsSearch')?.addEventListener('input', function() {
      const query = this.value.toLowerCase();
      document.querySelectorAll('.form-group, .card').forEach(item => {
        const text = item.textContent.toLowerCase();
        item.style.display = text.includes(query) || !query ? '' : 'none';
      });
    });
  }
  
  // ═══════════════════════════════════════════════════════════════════
  // 🎯 Recent Pages
  // ═══════════════════════════════════════════════════════════════════
  
  function trackRecentPages() {
    const RECENT_KEY = 'security_recent_pages';
    const currentPage = {
      url: window.location.pathname + window.location.search,
      title: document.title,
      timestamp: new Date().toISOString()
    };
    
    let recent = JSON.parse(localStorage.getItem(RECENT_KEY) || '[]');
    
    // إزالة إذا موجود
    recent = recent.filter(p => p.url !== currentPage.url);
    
    // إضافة في الأول
    recent.unshift(currentPage);
    
    // الاحتفاظ بآخر 10 صفحات
    recent = recent.slice(0, 10);
    
    localStorage.setItem(RECENT_KEY, JSON.stringify(recent));
  }
  
  // ═══════════════════════════════════════════════════════════════════
  // 📊 Enhanced Data Tables
  // ═══════════════════════════════════════════════════════════════════
  
  function enhanceDataTables() {
    const path = (window.location && window.location.pathname) ? window.location.pathname : '';
    const isCustomerStatement = /\/customers\/\d+\/account_statement/.test(path);
    if (isCustomerStatement) {
      document.querySelectorAll('.table-export-btn').forEach(btn => btn.remove());
    }
    
    document.querySelectorAll('table.table').forEach(table => {
      const attrNoExport = (table.getAttribute('data-no-export') === 'true');
      const classNoExport = table.classList.contains('no-export');
      const skipExport = attrNoExport || classNoExport || isCustomerStatement;
      if (!skipExport && !table.querySelector('.table-export-btn')) {
        addTableExportButton(table);
      }
      
      if (!table.querySelector('.column-visibility')) {
        addColumnVisibility(table);
      }
    });
  }
  
  function addTableExportButton(table) {
    const wrapper = table.parentElement;
    if (!wrapper) return;
    const skipExport = (table.getAttribute('data-no-export') === 'true') || table.classList.contains('no-export');
    if (skipExport) return;
    
    const btn = document.createElement('button');
    btn.className = 'btn btn-sm btn-outline-success table-export-btn mb-2';
    btn.classList.add('no-print');
    btn.innerHTML = '<i class="fas fa-file-excel"></i> Export CSV';
    btn.onclick = () => exportTableToCSV(table);
    
    wrapper.insertBefore(btn, table);
  }
  
  function exportTableToCSV(table) {
    let csv = [];
    const rows = table.querySelectorAll('tr');
    
    rows.forEach(row => {
      const cols = row.querySelectorAll('td, th');
      const rowData = Array.from(cols).map(col => {
        return '"' + col.textContent.trim().replace(/"/g, '""') + '"';
      });
      csv.push(rowData.join(','));
    });
    
    const csvContent = csv.join('\n');
    const blob = new Blob(['\ufeff' + csvContent], {type: 'text/csv;charset=utf-8;'});
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `export_${new Date().toISOString().split('T')[0]}.csv`;
    link.click();
  }
  
  function addColumnVisibility(table) {
    // يمكن إضافة لاحقاً
  }
  
  // ═══════════════════════════════════════════════════════════════════
  // 🎨 UI Enhancements
  // ═══════════════════════════════════════════════════════════════════
  
  function initUIEnhancements() {
    // Loading states
    addLoadingStates();
    
    // Copy to clipboard buttons
    addCopyButtons();
    
    // Collapse/Expand all
    addCollapseButtons();
  }
  
  function addLoadingStates() {
    document.querySelectorAll('form').forEach(form => {
      form.addEventListener('submit', function() {
        const submitBtn = this.querySelector('button[type="submit"]');
        if (submitBtn && !submitBtn.dataset.noLoading) {
          submitBtn.disabled = true;
          submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> جاري المعالجة...';
        }
      });
    });
  }
  
  function addCopyButtons() {
    document.querySelectorAll('pre, code').forEach(element => {
      if (element.textContent.trim().length > 20) {
        const btn = document.createElement('button');
        btn.className = 'btn btn-sm btn-outline-secondary position-absolute top-0 end-0 m-1';
        btn.innerHTML = '<i class="fas fa-copy"></i>';
        btn.onclick = () => {
          navigator.clipboard.writeText(element.textContent);
          btn.innerHTML = '<i class="fas fa-check text-success"></i>';
          setTimeout(() => btn.innerHTML = '<i class="fas fa-copy"></i>', 2000);
        };
        
        element.style.position = 'relative';
        element.appendChild(btn);
      }
    });
  }
  
  function addCollapseButtons() {
    // يمكن إضافة لاحقاً للأقسام الكبيرة
  }
  
  // ═══════════════════════════════════════════════════════════════════
  // 🚀 التهيئة الشاملة
  // ═══════════════════════════════════════════════════════════════════
  
  document.addEventListener('DOMContentLoaded', function() {
    // تفعيل جميع الميزات
    initTabMemory();
    initFavorites();
    initQuickActions();
    initNotificationCenter();
    initSettingsSearch();
    trackRecentPages();
    enhanceDataTables();
    initUIEnhancements();
  });
  
})();

