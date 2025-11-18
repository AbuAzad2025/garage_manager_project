/**
 * ═══════════════════════════════════════════════════════════════════
 * ⌨️ اختصارات لوحة المفاتيح للوحدة السرية
 * ═══════════════════════════════════════════════════════════════════
 * 
 * Keyboard Shortcuts for Security Module
 */

(function() {
  'use strict';
  
  // ═══ قائمة الاختصارات ═══
  const shortcuts = {
    // المراكز الرئيسية
    'D': {
      url: '/security/database-manager',
      name: 'Database Manager',
      icon: '🗄️',
      description: 'مركز قاعدة البيانات'
    },
    'A': {
      url: '/security/ai-hub',
      name: 'AI Hub',
      icon: '🤖',
      description: 'مركز الذكاء الاصطناعي'
    },
    'S': {
      url: '/security/security-center',
      name: 'Security Center',
      icon: '🛡️',
      description: 'مركز الأمان والمراقبة'
    },
    'U': {
      url: '/security/users-center',
      name: 'Users Center',
      icon: '👥',
      description: 'مركز المستخدمين'
    },
    'T': {
      url: '/security/tools-center',
      name: 'Tools Center',
      icon: '🔧',
      description: 'مركز الأدوات والتكامل'
    },
    'R': {
      url: '/security/reports-center',
      name: 'Reports Center',
      icon: '📊',
      description: 'مركز التقارير'
    },
    'G': {
      url: '/security/settings-center',
      name: 'Settings Center',
      icon: '⚙️',
      description: 'مركز الإعدادات'
    },
    'L': {
      url: '/security/ledger-control/',
      name: 'Ledger Control',
      icon: '📒',
      description: 'دفتر الأستاذ'
    },
    
    // أدوات سريعة
    'H': {
      url: '/security/help',
      name: 'Help',
      icon: '❓',
      description: 'مركز المساعدة'
    },
    'E': {
      url: '/security/emergency-tools',
      name: 'Emergency Tools',
      icon: '🚨',
      description: 'أدوات الطوارئ'
    },
    'C': {
      url: '/security/user-control',
      name: 'User Control',
      icon: '👤',
      description: 'التحكم بالمستخدمين'
    },
    'I': {
      url: '/security/integrations',
      name: 'Integrations',
      icon: '🔌',
      description: 'التكاملات'
    },
    'M': {
      url: '/security/system-map',
      name: 'System Map',
      icon: '🗺️',
      description: 'خريطة النظام'
    },
    
    // الصفحة الرئيسية
    '0': {
      url: '/security/',
      name: 'Security Home',
      icon: '🏠',
      description: 'الصفحة الرئيسية'
    }
  };
  
  // ═══ معالج الاختصارات ═══
  document.addEventListener('keydown', function(e) {
    // التحقق من Ctrl+Shift
    if (e.ctrlKey && e.shiftKey) {
      const key = e.key.toUpperCase();
      
      // إظهار قائمة الاختصارات
      if (key === '?') {
        e.preventDefault();
        showShortcutsModal();
        return;
      }
      
      // التنقل للمراكز
      if (shortcuts[key]) {
        e.preventDefault();
        
        // عرض إشعار سريع
        showNavigationToast(shortcuts[key]);
        
        // التنقل بعد 300ms
        setTimeout(() => {
          window.location.href = shortcuts[key].url;
        }, 300);
      }
    }
  });
  
  /**
   * عرض إشعار سريع عند التنقل
   */
  function showNavigationToast(shortcut) {
    const toast = document.createElement('div');
    toast.className = 'keyboard-shortcut-toast';
    toast.innerHTML = `
      <div style="
        position: fixed;
        top: 20px;
        left: 50%;
        transform: translateX(-50%);
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 15px 25px;
        border-radius: 10px;
        box-shadow: 0 10px 30px rgba(0,0,0,0.3);
        z-index: 99999;
        font-size: 1.1rem;
        font-weight: bold;
        animation: slideDown 0.3s ease;
      ">
        ${shortcut.icon} ${shortcut.name}
        <br><small style="opacity: 0.8;">${shortcut.description}</small>
      </div>
    `;
    
    // إضافة animation
    if (!document.getElementById('shortcutAnimations')) {
      const style = document.createElement('style');
      style.id = 'shortcutAnimations';
      style.textContent = `
        @keyframes slideDown {
          from {
            opacity: 0;
            transform: translateX(-50%) translateY(-20px);
          }
          to {
            opacity: 1;
            transform: translateX(-50%) translateY(0);
          }
        }
      `;
      document.head.appendChild(style);
    }
    
    document.body.appendChild(toast);
    
    // إزالة بعد 500ms
    setTimeout(() => {
      toast.remove();
    }, 500);
  }
  
  /**
   * إظهار نافذة الاختصارات
   */
  window.showShortcutsModal = function() {
    // إزالة النافذة القديمة إن وجدت
    const oldModal = document.getElementById('shortcutsModal');
    if (oldModal) {
      oldModal.remove();
      return; // toggle
    }
    
    // إنشاء النافذة
    const modal = document.createElement('div');
    modal.id = 'shortcutsModal';
    modal.innerHTML = `
      <div style="
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0,0,0,0.7);
        z-index: 99998;
        display: flex;
        align-items: center;
        justify-content: center;
        animation: fadeIn 0.3s ease;
      " onclick="this.parentElement.remove()">
        <div style="
          background: white;
          border-radius: 15px;
          padding: 30px;
          max-width: 700px;
          max-height: 80vh;
          overflow-y: auto;
          box-shadow: 0 20px 60px rgba(0,0,0,0.5);
          animation: scaleIn 0.3s ease;
        " onclick="event.stopPropagation()">
          
          <div style="text-align: center; margin-bottom: 25px;">
            <h3 style="color: #667eea; margin: 0;">
              <i class="fas fa-keyboard"></i> اختصارات لوحة المفاتيح
            </h3>
            <p style="color: #666; margin-top: 10px;">
              اضغط <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>المفتاح</kbd> للتنقل السريع
            </p>
          </div>
          
          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px;">
            ${Object.entries(shortcuts).map(([key, data]) => `
              <div style="
                padding: 12px;
                border: 2px solid #e9ecef;
                border-radius: 8px;
                background: #f8f9fa;
                transition: all 0.2s;
                cursor: pointer;
              " onmouseover="this.style.borderColor='#667eea'; this.style.background='#fff'"
                 onmouseout="this.style.borderColor='#e9ecef'; this.style.background='#f8f9fa'"
                 onclick="window.location.href='${data.url}'">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                  <div>
                    <div style="font-size: 1.3rem; margin-bottom: 5px;">
                      ${data.icon}
                      <span style="
                        background: #667eea;
                        color: white;
                        padding: 3px 8px;
                        border-radius: 5px;
                        font-family: monospace;
                        font-size: 0.9rem;
                        margin-left: 8px;
                      ">${key}</span>
                    </div>
                    <div style="font-weight: bold; color: #333;">
                      ${data.name}
                    </div>
                    <div style="font-size: 0.85rem; color: #666;">
                      ${data.description}
                    </div>
                  </div>
                </div>
              </div>
            `).join('')}
          </div>
          
          <div style="margin-top: 25px; padding: 15px; background: #e7f3ff; border-radius: 8px;">
            <h6 style="margin: 0 0 10px 0; color: #0066cc;">
              <i class="fas fa-lightbulb"></i> نصائح:
            </h6>
            <ul style="margin: 0; padding-right: 20px; font-size: 0.9rem; color: #333;">
              <li><kbd>Ctrl</kbd>+<kbd>K</kbd> = فتح البحث السريع</li>
              <li><kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>?</kbd> = إظهار هذه النافذة</li>
              <li><kbd>Esc</kbd> = إغلاق النوافذ</li>
              <li>اضغط على أي مربع للتنقل مباشرة</li>
            </ul>
          </div>
          
          <div style="text-align: center; margin-top: 20px;">
            <button onclick="this.closest('#shortcutsModal').remove()" 
                    class="btn btn-primary">
              <i class="fas fa-times"></i> إغلاق
            </button>
          </div>
          
        </div>
      </div>
    `;
    
    // إضافة animations
    if (!document.getElementById('modalAnimations')) {
      const style = document.createElement('style');
      style.id = 'modalAnimations';
      style.textContent = `
        @keyframes fadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }
        @keyframes scaleIn {
          from {
            opacity: 0;
            transform: scale(0.9);
          }
          to {
            opacity: 1;
            transform: scale(1);
          }
        }
        kbd {
          background: #333;
          color: white;
          padding: 2px 6px;
          border-radius: 3px;
          font-family: monospace;
          font-size: 0.9rem;
          box-shadow: 0 2px 4px rgba(0,0,0,0.2);
        }
      `;
      document.head.appendChild(style);
    }
    
    document.body.appendChild(modal);
    
    // إغلاق بزر Esc
    const escHandler = function(e) {
      if (e.key === 'Escape') {
        modal.remove();
        document.removeEventListener('keydown', escHandler);
      }
    };
    document.addEventListener('keydown', escHandler);
  };
  
  /**
   * زر عائم لإظهار الاختصارات
   */
  function addShortcutsButton() {
    // إضافة الزر فقط في صفحات الوحدة السرية
    if (!window.location.pathname.startsWith('/security')) return;
    
    const button = document.createElement('button');
    button.innerHTML = '<i class="fas fa-keyboard"></i>';
    button.title = 'اختصارات لوحة المفاتيح (Ctrl+Shift+?)';
    button.className = 'shortcuts-float-btn';
    button.onclick = showShortcutsModal;
    
    // Styles
    const style = document.createElement('style');
    style.textContent = `
      .shortcuts-float-btn {
        position: fixed;
        bottom: 20px;
        left: 20px;
        width: 50px;
        height: 50px;
        border-radius: 50%;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
        cursor: pointer;
        z-index: 9999;
        transition: all 0.3s ease;
        font-size: 1.2rem;
      }
      
      .shortcuts-float-btn:hover {
        transform: scale(1.1) translateY(-3px);
        box-shadow: 0 6px 20px rgba(102, 126, 234, 0.6);
      }
      
      .shortcuts-float-btn:active {
        transform: scale(0.95);
      }
      
      /* إخفاء على الموبايل */
      @media (max-width: 768px) {
        .shortcuts-float-btn {
          width: 45px;
          height: 45px;
          bottom: 15px;
          left: 15px;
          font-size: 1rem;
        }
      }
    `;
    document.head.appendChild(style);
    
    document.body.appendChild(button);
  }
  
  document.addEventListener('DOMContentLoaded', function() {
    addShortcutsButton();
  });
  
})();

