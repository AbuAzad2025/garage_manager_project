(function() {
  'use strict';

  const STORAGE_KEY = 'security_favorites';
  const RECENT_KEY = 'security_recent_pages';
  
  window.SecurityFavorites = {
    favorites: [],
    recentPages: [],
    
    init: function() {
      this.loadFavorites();
      this.loadRecentPages();
      this.addCurrentPage();
      this.renderFavoriteButton();
      this.renderWidgets();
      
      console.log('✅ Favorites & Recent Pages System Ready');
    },
    
    loadFavorites: function() {
      try {
        this.favorites = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
      } catch (e) {
        this.favorites = [];
      }
    },
    
    loadRecentPages: function() {
      try {
        this.recentPages = JSON.parse(localStorage.getItem(RECENT_KEY) || '[]');
      } catch (e) {
        this.recentPages = [];
      }
    },
    
    saveFavorites: function() {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(this.favorites));
    },
    
    saveRecentPages: function() {
      localStorage.setItem(RECENT_KEY, JSON.stringify(this.recentPages));
    },
    
    addCurrentPage: function() {
      const currentPage = {
        url: window.location.pathname + window.location.search,
        title: document.title.split(' - ')[0] || document.title,
        icon: this.getPageIcon(),
        timestamp: new Date().toISOString()
      };
      
      this.recentPages = this.recentPages.filter(p => p.url !== currentPage.url);
      this.recentPages.unshift(currentPage);
      this.recentPages = this.recentPages.slice(0, 10);
      
      this.saveRecentPages();
    },
    
    getPageIcon: function() {
      const iconMap = {
        '/security/': 'fa-shield-alt',
        'database': 'fa-database',
        'ai': 'fa-robot',
        'security_center': 'fa-lock',
        'users': 'fa-users',
        'settings': 'fa-cog',
        'reports': 'fa-chart-bar',
        'tools': 'fa-toolbox',
        'ledger': 'fa-book',
        'emergency': 'fa-exclamation-triangle'
      };
      
      const path = window.location.pathname.toLowerCase();
      for (const [key, icon] of Object.entries(iconMap)) {
        if (path.includes(key)) return icon;
      }
      
      return 'fa-file';
    },
    
    isFavorite: function(url = window.location.pathname + window.location.search) {
      return this.favorites.some(f => f.url === url);
    },
    
    toggleFavorite: function(url = null) {
      if (!url) {
        url = window.location.pathname + window.location.search;
      }
      
      if (this.isFavorite(url)) {
        this.removeFavorite(url);
      } else {
        this.addFavorite(url);
      }
    },
    
    addFavorite: function(url = null) {
      const page = {
        url: url || (window.location.pathname + window.location.search),
        title: document.title.split(' - ')[0] || document.title,
        icon: this.getPageIcon(),
        timestamp: new Date().toISOString()
      };
      
      if (!this.isFavorite(page.url)) {
        this.favorites.unshift(page);
        this.saveFavorites();
        this.renderFavoriteButton();
        this.renderWidgets();
        
        if (window.toast) {
          window.toast.success('تمت إضافة الصفحة للمفضلة ⭐');
        }
      }
    },
    
    removeFavorite: function(url) {
      this.favorites = this.favorites.filter(f => f.url !== url);
      this.saveFavorites();
      this.renderFavoriteButton();
      this.renderWidgets();
      
      if (window.toast) {
        window.toast.info('تمت إزالة الصفحة من المفضلة');
      }
    },
    
    renderFavoriteButton: function() {
      const existingBtn = document.getElementById('favorite-btn');
      if (existingBtn) existingBtn.remove();
      
      const actionsDiv = document.querySelector('.security-page-header .d-flex > div:last-child');
      if (!actionsDiv) return;
      
      const isFav = this.isFavorite();
      const btn = document.createElement('button');
      btn.id = 'favorite-btn';
      btn.className = `btn btn-sm ${isFav ? 'btn-warning' : 'btn-outline-warning'}`;
      btn.innerHTML = `<i class="fas fa-star"></i> ${isFav ? 'مفضلة' : 'إضافة للمفضلة'}`;
      btn.onclick = () => this.toggleFavorite();
      
      actionsDiv.insertBefore(btn, actionsDiv.firstChild);
    },
    
    renderWidgets: function() {
      if (window.location.pathname === '/security/' || window.location.pathname === '/security') {
        this.renderDashboardWidgets();
      }
    },
    
    renderDashboardWidgets: function() {
      const container = document.querySelector('.security-content .container-fluid');
      if (!container) return;
      
      let widgetsContainer = document.getElementById('favorites-widgets');
      if (!widgetsContainer) {
        widgetsContainer = document.createElement('div');
        widgetsContainer.id = 'favorites-widgets';
        widgetsContainer.className = 'row g-3 mb-4';
        
        const firstCard = container.querySelector('.card');
        if (firstCard) {
          firstCard.parentNode.insertBefore(widgetsContainer, firstCard.nextSibling);
        }
      }
      
      widgetsContainer.innerHTML = '';
      
      if (this.favorites.length > 0) {
        const favCard = this.createFavoritesCard();
        widgetsContainer.appendChild(favCard);
      }
      
      if (this.recentPages.length > 0) {
        const recentCard = this.createRecentPagesCard();
        widgetsContainer.appendChild(recentCard);
      }
    },
    
    createFavoritesCard: function() {
      const col = document.createElement('div');
      col.className = 'col-lg-6';
      
      col.innerHTML = `
        <div class="card border-0 shadow-sm">
          <div class="card-header bg-warning text-dark">
            <div class="d-flex justify-content-between align-items-center">
              <h6 class="mb-0"><i class="fas fa-star"></i> المفضلة (${this.favorites.length})</h6>
              ${this.favorites.length > 0 ? '<button class="btn btn-sm btn-outline-dark" onclick="SecurityFavorites.clearFavorites()"><i class="fas fa-trash"></i></button>' : ''}
            </div>
          </div>
          <div class="card-body p-2" style="max-height: 300px; overflow-y: auto;">
            ${this.favorites.slice(0, 5).map(fav => `
              <div class="d-flex justify-content-between align-items-center p-2 border-bottom hover-bg">
                <a href="${fav.url}" class="text-decoration-none flex-grow-1">
                  <i class="fas ${fav.icon} text-warning mr-2"></i>
                  <strong>${fav.title}</strong>
                </a>
                <button class="btn btn-sm btn-link text-danger" onclick="SecurityFavorites.removeFavorite('${fav.url}')">
                  <i class="fas fa-times"></i>
                </button>
              </div>
            `).join('')}
            ${this.favorites.length > 5 ? `<small class="text-muted d-block p-2">و ${this.favorites.length - 5} أخرى...</small>` : ''}
          </div>
        </div>
      `;
      
      return col;
    },
    
    createRecentPagesCard: function() {
      const col = document.createElement('div');
      col.className = 'col-lg-6';
      
      col.innerHTML = `
        <div class="card border-0 shadow-sm">
          <div class="card-header bg-info text-white">
            <div class="d-flex justify-content-between align-items-center">
              <h6 class="mb-0"><i class="fas fa-history"></i> آخر الصفحات (${this.recentPages.length})</h6>
              ${this.recentPages.length > 0 ? '<button class="btn btn-sm btn-outline-light" onclick="SecurityFavorites.clearRecentPages()"><i class="fas fa-trash"></i></button>' : ''}
            </div>
          </div>
          <div class="card-body p-2" style="max-height: 300px; overflow-y: auto;">
            ${this.recentPages.slice(0, 5).map((page, index) => `
              <div class="d-flex justify-content-between align-items-center p-2 border-bottom hover-bg">
                <a href="${page.url}" class="text-decoration-none flex-grow-1">
                  <i class="fas ${page.icon} text-info mr-2"></i>
                  <strong>${page.title}</strong>
                  <br><small class="text-muted">${this.formatTime(page.timestamp)}</small>
                </a>
                ${index > 0 ? `<button class="btn btn-sm btn-link text-warning" onclick="SecurityFavorites.addFavorite('${page.url}')"><i class="fas fa-star"></i></button>` : ''}
              </div>
            `).join('')}
          </div>
        </div>
      `;
      
      return col;
    },
    
    formatTime: function(timestamp) {
      const date = new Date(timestamp);
      const now = new Date();
      const diff = now - date;
      const minutes = Math.floor(diff / 60000);
      const hours = Math.floor(diff / 3600000);
      const days = Math.floor(diff / 86400000);
      
      if (minutes < 1) return 'الآن';
      if (minutes < 60) return `منذ ${minutes} دقيقة`;
      if (hours < 24) return `منذ ${hours} ساعة`;
      return `منذ ${days} يوم`;
    },
    
    clearFavorites: function() {
      if (confirm('هل تريد مسح جميع المفضلة؟')) {
        this.favorites = [];
        this.saveFavorites();
        this.renderWidgets();
        
        if (window.toast) {
          window.toast.info('تم مسح جميع المفضلة');
        }
      }
    },
    
    clearRecentPages: function() {
      if (confirm('هل تريد مسح السجل؟')) {
        this.recentPages = [];
        this.saveRecentPages();
        this.renderWidgets();
        
        if (window.toast) {
          window.toast.info('تم مسح السجل');
        }
      }
    }
  };

  const style = document.createElement('style');
  style.textContent = `
    .hover-bg:hover {
      background: #f8f9fa;
      transition: background 0.2s ease;
    }
  `;
  document.head.appendChild(style);

  document.addEventListener('DOMContentLoaded', function() {
    SecurityFavorites.init();
  });
  
})();

