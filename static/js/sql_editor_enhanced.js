/**
 * ═══════════════════════════════════════════════════════════════════
 * 🔍 SQL Editor محسّن - Enhanced SQL Editor
 * ═══════════════════════════════════════════════════════════════════
 * 
 * Features:
 * - Syntax Highlighting
 * - Autocomplete
 * - Query History
 * - Saved Queries
 * - Query Formatter
 * - Keyboard Shortcuts
 */

(function() {
  'use strict';
  
  const SQL_HISTORY_KEY = 'sql_query_history';
  const SAVED_QUERIES_KEY = 'saved_sql_queries';
  
  /**
   * تهيئة SQL Editor
   */
  function initSQLEditor() {
    const textarea = document.querySelector('textarea[name="sql_query"]');
    if (!textarea) return;
    
    // إضافة features للـ textarea
    enhanceTextarea(textarea);
    
    // إضافة Query History
    addQueryHistory(textarea);
    
    // إضافة Saved Queries
    addSavedQueries(textarea);
    
    // إضافة Query Formatter
    addQueryFormatter(textarea);
    
    addAutocomplete(textarea);
    addKeyboardShortcuts(textarea);
  }
  
  /**
   * تحسين Textarea
   */
  function enhanceTextarea(textarea) {
    // إضافة line numbers
    textarea.style.lineHeight = '1.5';
    textarea.style.fontSize = '14px';
    textarea.style.tabSize = '4';
    
    // منع tab من الخروج من الحقل
    textarea.addEventListener('keydown', function(e) {
      if (e.key === 'Tab') {
        e.preventDefault();
        const start = this.selectionStart;
        const end = this.selectionEnd;
        const value = this.value;
        
        // إدراج tab
        this.value = value.substring(0, start) + '    ' + value.substring(end);
        this.selectionStart = this.selectionEnd = start + 4;
      }
    });
    
    // Syntax highlighting (بسيط)
    applySyntaxHighlighting(textarea);
  }
  
  /**
   * Syntax Highlighting بسيط
   */
  function applySyntaxHighlighting(textarea) {
    // إنشاء div للعرض
    const wrapper = document.createElement('div');
    wrapper.className = 'sql-editor-wrapper';
    wrapper.style.position = 'relative';
    
    const highlighted = document.createElement('div');
    highlighted.className = 'sql-highlighted';
    highlighted.style.cssText = `
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      padding: 10px;
      font-family: 'Courier New', monospace;
      font-size: 14px;
      line-height: 1.5;
      white-space: pre-wrap;
      word-wrap: break-word;
      pointer-events: none;
      color: transparent;
      overflow: hidden;
    `;
    
    textarea.parentNode.insertBefore(wrapper, textarea);
    wrapper.appendChild(highlighted);
    wrapper.appendChild(textarea);
    
    textarea.style.position = 'relative';
    textarea.style.background = 'transparent';
    textarea.style.caretColor = '#000';
    
    // تحديث highlighting عند الكتابة
    function updateHighlight() {
      const sql = textarea.value;
      highlighted.innerHTML = highlightSQL(sql);
      highlighted.scrollTop = textarea.scrollTop;
    }
    
    textarea.addEventListener('input', updateHighlight);
    textarea.addEventListener('scroll', () => {
      highlighted.scrollTop = textarea.scrollTop;
    });
    
    updateHighlight();
  }
  
  /**
   * Highlight SQL syntax
   */
  function highlightSQL(sql) {
    if (!sql) return '';
    
    // كلمات SQL الأساسية
    const keywords = /\b(SELECT|FROM|WHERE|JOIN|LEFT|RIGHT|INNER|OUTER|ON|AND|OR|NOT|IN|LIKE|ORDER BY|GROUP BY|HAVING|LIMIT|OFFSET|INSERT|INTO|VALUES|UPDATE|SET|DELETE|CREATE|TABLE|INDEX|DROP|ALTER|AS|DISTINCT|COUNT|SUM|AVG|MAX|MIN)\b/gi;
    
    // الأرقام
    const numbers = /\b(\d+)\b/g;
    
    // النصوص
    const strings = /'([^']*)'/g;
    
    // التعليقات
    const comments = /--[^\n]*/g;
    
    let highlighted = sql;
    
    // Highlight keywords
    highlighted = highlighted.replace(keywords, '<span style="color: #0000ff; font-weight: bold;">$&</span>');
    
    // Highlight numbers
    highlighted = highlighted.replace(numbers, '<span style="color: #098658;">$&</span>');
    
    // Highlight strings
    highlighted = highlighted.replace(strings, '<span style="color: #a31515;">$&</span>');
    
    // Highlight comments
    highlighted = highlighted.replace(comments, '<span style="color: #008000; font-style: italic;">$&</span>');
    
    return highlighted;
  }
  
  /**
   * Query History
   */
  function addQueryHistory(textarea) {
    // حفظ الاستعلام عند التنفيذ
    const form = textarea.closest('form');
    if (form) {
      form.addEventListener('submit', function() {
        const query = textarea.value.trim();
        if (query) {
          saveToHistory(query);
        }
      });
    }
    
    // إضافة زر History
    const historyBtn = document.createElement('button');
    historyBtn.type = 'button';
    historyBtn.className = 'btn btn-outline-info btn-sm me-2';
    historyBtn.innerHTML = '<i class="fas fa-history"></i> السجل';
    historyBtn.onclick = () => showHistoryModal(textarea);
    
    const submitBtn = form.querySelector('button[type="submit"]');
    submitBtn.parentNode.insertBefore(historyBtn, submitBtn);
  }
  
  /**
   * حفظ في History
   */
  function saveToHistory(query) {
    let history = JSON.parse(localStorage.getItem(SQL_HISTORY_KEY) || '[]');
    
    // إضافة مع timestamp
    history.unshift({
      query: query,
      timestamp: new Date().toISOString(),
      id: Date.now()
    });
    
    // الاحتفاظ بآخر 50 استعلام
    history = history.slice(0, 50);
    
    localStorage.setItem(SQL_HISTORY_KEY, JSON.stringify(history));
  }
  
  /**
   * عرض History Modal
   */
  function showHistoryModal(textarea) {
    const history = JSON.parse(localStorage.getItem(SQL_HISTORY_KEY) || '[]');
    
    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.innerHTML = `
      <div class="modal-dialog modal-lg" style="
        position: fixed;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        background: white;
        border-radius: 10px;
        padding: 20px;
        max-height: 80vh;
        overflow-y: auto;
        box-shadow: 0 10px 40px rgba(0,0,0,0.3);
        z-index: 99999;
        width: 90%;
        max-width: 800px;
      ">
        <div class="modal-header border-bottom pb-3">
          <h5 class="modal-title">
            <i class="fas fa-history"></i> سجل الاستعلامات
            <span class="badge bg-primary">${history.length}</span>
          </h5>
          <button type="button" class="close" onclick="this.closest('.modal-overlay').remove()"><span aria-hidden="true">&times;</span></button>
        </div>
        <div class="modal-body mt-3">
          ${history.length === 0 ? '<div class="alert alert-info">لا يوجد سجل حتى الآن</div>' : ''}
          ${history.map((item, index) => `
            <div class="card mb-2 history-item" style="cursor: pointer;" 
                 onclick='document.querySelector("textarea[name=\\'sql_query\\']").value = \`${item.query.replace(/`/g, '\\`')}\`; this.closest(".modal-overlay").remove();'>
              <div class="card-body p-2">
                <div class="d-flex justify-content-between align-items-start">
                  <div class="flex-grow-1">
                    <small class="text-muted">
                      <i class="fas fa-clock"></i> ${new Date(item.timestamp).toLocaleString('ar-EG')}
                    </small>
                    <pre class="mb-0 mt-1" style="font-size: 12px; background: #f8f9fa; padding: 8px; border-radius: 4px; overflow-x: auto;">${item.query}</pre>
                  </div>
                  <button class="btn btn-sm btn-outline-danger ms-2" 
                          onclick="event.stopPropagation(); deleteHistoryItem(${item.id}); this.closest('.history-item').remove();">
                    <i class="fas fa-trash"></i>
                  </button>
                </div>
              </div>
            </div>
          `).join('')}
        </div>
        <div class="modal-footer border-top pt-3">
          <button class="btn btn-danger btn-sm" onclick="clearAllHistory(); this.closest('.modal-overlay').remove();">
            <i class="fas fa-trash"></i> مسح الكل
          </button>
          <button class="btn btn-secondary" onclick="this.closest('.modal-overlay').remove();">
            إغلاق
          </button>
        </div>
      </div>
    `;
    
    // Overlay
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
  }
  
  /**
   * حذف من History
   */
  window.deleteHistoryItem = function(id) {
    let history = JSON.parse(localStorage.getItem(SQL_HISTORY_KEY) || '[]');
    history = history.filter(item => item.id !== id);
    localStorage.setItem(SQL_HISTORY_KEY, JSON.stringify(history));
  };
  
  /**
   * مسح كل History
   */
  window.clearAllHistory = function() {
    if (confirm('هل تريد مسح جميع السجل؟')) {
      localStorage.removeItem(SQL_HISTORY_KEY);
    }
  };
  
  /**
   * Saved Queries
   */
  function addSavedQueries(textarea) {
    const form = textarea.closest('form');
    
    // زر Save Query
    const saveBtn = document.createElement('button');
    saveBtn.type = 'button';
    saveBtn.className = 'btn btn-outline-success btn-sm me-2';
    saveBtn.innerHTML = '<i class="fas fa-save"></i> حفظ';
    saveBtn.onclick = () => saveQueryModal(textarea);
    
    // زر Load Query
    const loadBtn = document.createElement('button');
    loadBtn.type = 'button';
    loadBtn.className = 'btn btn-outline-primary btn-sm me-2';
    loadBtn.innerHTML = '<i class="fas fa-folder-open"></i> المحفوظة';
    loadBtn.onclick = () => showSavedQueriesModal(textarea);
    
    const submitBtn = form.querySelector('button[type="submit"]');
    submitBtn.parentNode.insertBefore(saveBtn, submitBtn);
    submitBtn.parentNode.insertBefore(loadBtn, submitBtn);
  }
  
  /**
   * حفظ استعلام
   */
  function saveQueryModal(textarea) {
    const query = textarea.value.trim();
    if (!query) {
      alert('لا يوجد استعلام لحفظه');
      return;
    }
    
    const name = prompt('أدخل اسماً للاستعلام:');
    if (!name) return;
    
    let saved = JSON.parse(localStorage.getItem(SAVED_QUERIES_KEY) || '[]');
    
    saved.push({
      id: Date.now(),
      name: name,
      query: query,
      created: new Date().toISOString()
    });
    
    localStorage.setItem(SAVED_QUERIES_KEY, JSON.stringify(saved));
    alert(`✅ تم حفظ الاستعلام: ${name}`);
  }
  
  /**
   * عرض Saved Queries
   */
  function showSavedQueriesModal(textarea) {
    const saved = JSON.parse(localStorage.getItem(SAVED_QUERIES_KEY) || '[]');
    
    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.innerHTML = `
      <div class="modal-dialog modal-lg" style="
        position: fixed;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        background: white;
        border-radius: 10px;
        padding: 20px;
        max-height: 80vh;
        overflow-y: auto;
        box-shadow: 0 10px 40px rgba(0,0,0,0.3);
        z-index: 99999;
        width: 90%;
        max-width: 800px;
      ">
        <div class="modal-header border-bottom pb-3">
          <h5 class="modal-title">
            <i class="fas fa-folder-open"></i> الاستعلامات المحفوظة
            <span class="badge bg-success">${saved.length}</span>
          </h5>
          <button type="button" class="close" onclick="this.closest('.modal-overlay').remove()"><span aria-hidden="true">&times;</span></button>
        </div>
        <div class="modal-body mt-3">
          ${saved.length === 0 ? '<div class="alert alert-info">لا توجد استعلامات محفوظة</div>' : ''}
          ${saved.map(item => `
            <div class="card mb-2 saved-query-item">
              <div class="card-body p-2">
                <div class="d-flex justify-content-between align-items-start">
                  <div class="flex-grow-1">
                    <strong><i class="fas fa-bookmark text-success"></i> ${item.name}</strong>
                    <br><small class="text-muted">
                      <i class="fas fa-clock"></i> ${new Date(item.created).toLocaleString('ar-EG')}
                    </small>
                    <pre class="mb-0 mt-2" style="font-size: 12px; background: #f8f9fa; padding: 8px; border-radius: 4px; max-height: 100px; overflow-y: auto;">${item.query}</pre>
                  </div>
                  <div class="btn-group-vertical ms-2">
                    <button class="btn btn-sm btn-primary" 
                            onclick='document.querySelector("textarea[name=\\'sql_query\\']").value = \`${item.query.replace(/`/g, '\\`')}\`; this.closest(".modal-overlay").remove();'>
                      <i class="fas fa-upload"></i> تحميل
                    </button>
                    <button class="btn btn-sm btn-danger" 
                            onclick="deleteSavedQuery(${item.id}); this.closest('.saved-query-item').remove();">
                      <i class="fas fa-trash"></i> حذف
                    </button>
                  </div>
                </div>
              </div>
            </div>
          `).join('')}
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
  }
  
  /**
   * حذف استعلام محفوظ
   */
  window.deleteSavedQuery = function(id) {
    let saved = JSON.parse(localStorage.getItem(SAVED_QUERIES_KEY) || '[]');
    saved = saved.filter(item => item.id !== id);
    localStorage.setItem(SAVED_QUERIES_KEY, JSON.stringify(saved));
  };
  
  /**
   * Query Formatter
   */
  function addQueryFormatter(textarea) {
    const form = textarea.closest('form');
    
    const formatBtn = document.createElement('button');
    formatBtn.type = 'button';
    formatBtn.className = 'btn btn-outline-secondary btn-sm me-2';
    formatBtn.innerHTML = '<i class="fas fa-align-left"></i> تنسيق';
    formatBtn.onclick = () => {
      textarea.value = formatSQL(textarea.value);
    };
    
    const submitBtn = form.querySelector('button[type="submit"]');
    submitBtn.parentNode.insertBefore(formatBtn, submitBtn);
  }
  
  /**
   * تنسيق SQL
   */
  function formatSQL(sql) {
    if (!sql) return '';
    
    let formatted = sql.trim();
    
    // تنسيق بسيط
    formatted = formatted.replace(/\bSELECT\b/gi, '\nSELECT\n  ');
    formatted = formatted.replace(/\bFROM\b/gi, '\nFROM\n  ');
    formatted = formatted.replace(/\bWHERE\b/gi, '\nWHERE\n  ');
    formatted = formatted.replace(/\bJOIN\b/gi, '\nJOIN\n  ');
    formatted = formatted.replace(/\bON\b/gi, '\n  ON ');
    formatted = formatted.replace(/\bAND\b/gi, '\n  AND ');
    formatted = formatted.replace(/\bOR\b/gi, '\n  OR ');
    formatted = formatted.replace(/\bORDER BY\b/gi, '\nORDER BY\n  ');
    formatted = formatted.replace(/\bGROUP BY\b/gi, '\nGROUP BY\n  ');
    formatted = formatted.replace(/\bLIMIT\b/gi, '\nLIMIT ');
    
    // إزالة الأسطر الفارغة المتكررة
    formatted = formatted.replace(/\n\n+/g, '\n\n');
    
    return formatted.trim();
  }
  
  /**
   * Autocomplete بسيط
   */
  function addAutocomplete(textarea) {
    const suggestions = [
      'SELECT * FROM ',
      'SELECT id, name FROM ',
      'WHERE id = ',
      'ORDER BY id DESC',
      'LIMIT 10',
      'COUNT(*)',
      'GROUP BY ',
      'INNER JOIN ',
      'LEFT JOIN ',
      'INSERT INTO ',
      'UPDATE ',
      'DELETE FROM ',
      'CREATE TABLE ',
      'DROP TABLE ',
      'ALTER TABLE '
    ];
    
    let suggestionBox = null;
    
    textarea.addEventListener('input', function(e) {
      const value = this.value;
      const cursorPos = this.selectionStart;
      const textBeforeCursor = value.substring(0, cursorPos);
      const lastWord = textBeforeCursor.split(/\s/).pop().toUpperCase();
      
      if (lastWord.length >= 2) {
        const matches = suggestions.filter(s => s.toUpperCase().includes(lastWord));
        
        if (matches.length > 0) {
          showSuggestions(matches, textarea);
        } else {
          hideSuggestions();
        }
      } else {
        hideSuggestions();
      }
    });
    
    function showSuggestions(matches, textarea) {
      hideSuggestions();
      
      suggestionBox = document.createElement('div');
      suggestionBox.className = 'sql-suggestions';
      suggestionBox.style.cssText = `
        position: absolute;
        background: white;
        border: 1px solid #ccc;
        border-radius: 4px;
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        max-height: 200px;
        overflow-y: auto;
        z-index: 1000;
        min-width: 200px;
      `;
      
      matches.forEach(suggestion => {
        const div = document.createElement('div');
        div.textContent = suggestion;
        div.style.cssText = `
          padding: 8px 12px;
          cursor: pointer;
          font-family: 'Courier New', monospace;
          font-size: 13px;
        `;
        
        div.onmouseover = () => div.style.background = '#667eea';
        div.onmouseout = () => div.style.background = '';
        
        div.onclick = () => {
          const value = textarea.value;
          const cursorPos = textarea.selectionStart;
          const textBeforeCursor = value.substring(0, cursorPos);
          const words = textBeforeCursor.split(/\s/);
          words.pop();
          const newText = words.join(' ') + (words.length > 0 ? ' ' : '') + suggestion;
          textarea.value = newText + value.substring(cursorPos);
          textarea.selectionStart = textarea.selectionEnd = newText.length;
          hideSuggestions();
          textarea.focus();
        };
        
        suggestionBox.appendChild(div);
      });
      
      const rect = textarea.getBoundingClientRect();
      suggestionBox.style.top = (rect.bottom + window.scrollY) + 'px';
      suggestionBox.style.left = rect.left + 'px';
      
      document.body.appendChild(suggestionBox);
    }
    
    function hideSuggestions() {
      if (suggestionBox) {
        suggestionBox.remove();
        suggestionBox = null;
      }
    }
    
    // إخفاء عند النقر خارجاً
    document.addEventListener('click', function(e) {
      if (e.target !== textarea && !suggestionBox?.contains(e.target)) {
        hideSuggestions();
      }
    });
  }
  
  /**
   * Keyboard Shortcuts
   */
  function addKeyboardShortcuts(textarea) {
    textarea.addEventListener('keydown', function(e) {
      // Ctrl+Enter = تنفيذ
      if (e.ctrlKey && e.key === 'Enter') {
        e.preventDefault();
        const form = this.closest('form');
        if (form) form.submit();
      }
      
      // Ctrl+/ = تعليق
      if (e.ctrlKey && e.key === '/') {
        e.preventDefault();
        const start = this.selectionStart;
        const end = this.selectionEnd;
        const value = this.value;
        const selectedText = value.substring(start, end);
        
        const commented = '-- ' + selectedText.split('\n').join('\n-- ');
        this.value = value.substring(0, start) + commented + value.substring(end);
        this.selectionStart = start;
        this.selectionEnd = start + commented.length;
      }
      
      // Ctrl+D = تنسيق
      if (e.ctrlKey && e.key === 'd') {
        e.preventDefault();
        this.value = formatSQL(this.value);
      }
    });
    
    // إضافة مساعدة
    const helpText = document.createElement('small');
    helpText.className = 'text-muted d-block mt-2';
    helpText.innerHTML = `
      <i class="fas fa-keyboard"></i> اختصارات:
      <kbd>Ctrl+Enter</kbd> تنفيذ |
      <kbd>Ctrl+D</kbd> تنسيق |
      <kbd>Ctrl+/</kbd> تعليق |
      <kbd>Tab</kbd> مسافة
    `;
    
    textarea.parentNode.appendChild(helpText);
  }
  
  // التهيئة عند تحميل الصفحة
  document.addEventListener('DOMContentLoaded', initSQLEditor);
  
})();

