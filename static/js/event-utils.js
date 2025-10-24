/**
 * ═══════════════════════════════════════════════════════════════════
 * 🎧 Event Utilities - أدوات مساعدة للـ Event Listeners
 * ═══════════════════════════════════════════════════════════════════
 * 
 * هذا الملف يوفر utilities آمنة ومحسّنة للتعامل مع Events
 * لا يؤثر على الكود الموجود - فقط يضيف وظائف جديدة
 */

(function(window) {
  'use strict';

  // ═══════════════════════════════════════════════════════════════════
  // 1. Event Delegation - تفويض الأحداث
  // ═══════════════════════════════════════════════════════════════════
  
  /**
   * Event Delegation - بدلاً من إضافة listener لكل عنصر
   * @param {Element} parent - العنصر الأب
   * @param {string} eventType - نوع الحدث (click, submit, etc)
   * @param {string} selector - CSS selector للعناصر الهدف
   * @param {Function} handler - الوظيفة المراد تنفيذها
   * @returns {Function} cleanup function
   */
  function delegate(parent, eventType, selector, handler) {
    const listener = function(event) {
      // البحث عن العنصر المطابق
      const target = event.target.closest(selector);
      if (target && parent.contains(target)) {
        handler.call(target, event);
      }
    };
    
    parent.addEventListener(eventType, listener);
    
    // إرجاع cleanup function
    return function removeDelegation() {
      parent.removeEventListener(eventType, listener);
    };
  }

  // ═══════════════════════════════════════════════════════════════════
  // 2. Listener Manager - إدارة Event Listeners
  // ═══════════════════════════════════════════════════════════════════
  
  class ListenerManager {
    constructor() {
      this.listeners = new WeakMap();
    }
    
    /**
     * إضافة listener مع تتبع تلقائي
     */
    add(element, eventType, handler, options = {}) {
      if (!element) return;
      
      element.addEventListener(eventType, handler, options);
      
      // تخزين للـ cleanup لاحقاً
      if (!this.listeners.has(element)) {
        this.listeners.set(element, []);
      }
      
      this.listeners.get(element).push({
        eventType,
        handler,
        options
      });
    }
    
    /**
     * إزالة جميع listeners من عنصر
     */
    removeAll(element) {
      if (!element || !this.listeners.has(element)) return;
      
      const listeners = this.listeners.get(element);
      listeners.forEach(({ eventType, handler }) => {
        element.removeEventListener(eventType, handler);
      });
      
      this.listeners.delete(element);
    }
    
    /**
     * إزالة listener محدد
     */
    remove(element, eventType, handler) {
      if (!element) return;
      
      element.removeEventListener(eventType, handler);
      
      if (this.listeners.has(element)) {
        const listeners = this.listeners.get(element);
        const index = listeners.findIndex(
          l => l.eventType === eventType && l.handler === handler
        );
        if (index !== -1) {
          listeners.splice(index, 1);
        }
      }
    }
  }
  
  // Instance عامة
  const listenerManager = new ListenerManager();

  // ═══════════════════════════════════════════════════════════════════
  // 3. Debounce & Throttle - تحسين الأداء
  // ═══════════════════════════════════════════════════════════════════
  
  /**
   * Debounce - تأخير تنفيذ الوظيفة حتى يتوقف المستخدم عن الإدخال
   */
  function debounce(func, wait = 300) {
    let timeout;
    return function executedFunction(...args) {
      const later = () => {
        clearTimeout(timeout);
        func(...args);
      };
      clearTimeout(timeout);
      timeout = setTimeout(later, wait);
    };
  }
  
  /**
   * Throttle - تحديد عدد مرات تنفيذ الوظيفة في فترة زمنية
   */
  function throttle(func, limit = 100) {
    let inThrottle;
    return function(...args) {
      if (!inThrottle) {
        func.apply(this, args);
        inThrottle = true;
        setTimeout(() => inThrottle = false, limit);
      }
    };
  }

  // ═══════════════════════════════════════════════════════════════════
  // 4. Once Listener - تنفيذ مرة واحدة فقط
  // ═══════════════════════════════════════════════════════════════════
  
  /**
   * إضافة listener يعمل مرة واحدة فقط
   */
  function once(element, eventType, handler) {
    const wrappedHandler = function(event) {
      handler.call(this, event);
      element.removeEventListener(eventType, wrappedHandler);
    };
    
    element.addEventListener(eventType, wrappedHandler);
    
    return function removeOnceListener() {
      element.removeEventListener(eventType, wrappedHandler);
    };
  }

  // ═══════════════════════════════════════════════════════════════════
  // 5. Safe Event Emitter - نظام أحداث مخصص
  // ═══════════════════════════════════════════════════════════════════
  
  class EventEmitter {
    constructor() {
      this.events = {};
    }
    
    on(eventName, handler) {
      if (!this.events[eventName]) {
        this.events[eventName] = [];
      }
      this.events[eventName].push(handler);
      
      // إرجاع cleanup function
      return () => this.off(eventName, handler);
    }
    
    off(eventName, handler) {
      if (!this.events[eventName]) return;
      
      const index = this.events[eventName].indexOf(handler);
      if (index !== -1) {
        this.events[eventName].splice(index, 1);
      }
    }
    
    emit(eventName, data) {
      if (!this.events[eventName]) return;
      
      this.events[eventName].forEach(handler => {
        try {
          handler(data);
        } catch (error) {
          console.error(`Error in event handler for ${eventName}:`, error);
        }
      });
    }
    
    once(eventName, handler) {
      const wrappedHandler = (data) => {
        handler(data);
        this.off(eventName, wrappedHandler);
      };
      this.on(eventName, wrappedHandler);
    }
  }
  
  // Global event bus
  const eventBus = new EventEmitter();

  // ═══════════════════════════════════════════════════════════════════
  // 6. Form Utilities - أدوات النماذج
  // ═══════════════════════════════════════════════════════════════════
  
  /**
   * معالجة إرسال النموذج مع منع التكرار
   */
  function handleFormSubmit(form, handler) {
    if (!form) return;
    
    let isSubmitting = false;
    
    const submitHandler = async function(event) {
      if (isSubmitting) {
        event.preventDefault();
        return;
      }
      
      isSubmitting = true;
      
      try {
        await handler.call(form, event);
      } finally {
        setTimeout(() => {
          isSubmitting = false;
        }, 1000);
      }
    };
    
    form.addEventListener('submit', submitHandler);
    
    return function removeFormSubmitHandler() {
      form.removeEventListener('submit', submitHandler);
    };
  }
  
  /**
   * تتبع تغييرات النموذج
   */
  function watchFormChanges(form, callback) {
    if (!form) return;
    
    const handler = debounce(() => {
      const formData = new FormData(form);
      const data = Object.fromEntries(formData);
      callback(data);
    }, 300);
    
    form.addEventListener('input', handler);
    form.addEventListener('change', handler);
    
    return function stopWatchingForm() {
      form.removeEventListener('input', handler);
      form.removeEventListener('change', handler);
    };
  }

  // ═══════════════════════════════════════════════════════════════════
  // 7. Click Outside - الكشف عن النقر خارج العنصر
  // ═══════════════════════════════════════════════════════════════════
  
  /**
   * تنفيذ وظيفة عند النقر خارج عنصر معين
   */
  function onClickOutside(element, handler) {
    if (!element) return;
    
    const listener = function(event) {
      if (!element.contains(event.target)) {
        handler(event);
      }
    };
    
    document.addEventListener('click', listener);
    
    return function removeClickOutsideListener() {
      document.removeEventListener('click', listener);
    };
  }

  // ═══════════════════════════════════════════════════════════════════
  // 8. Keyboard Shortcuts - اختصارات لوحة المفاتيح
  // ═══════════════════════════════════════════════════════════════════
  
  /**
   * إضافة اختصار لوحة مفاتيح
   */
  function addKeyboardShortcut(keys, handler, options = {}) {
    const { ctrl = false, alt = false, shift = false } = options;
    
    const listener = function(event) {
      const keyMatch = keys.toLowerCase() === event.key.toLowerCase();
      const ctrlMatch = ctrl === (event.ctrlKey || event.metaKey);
      const altMatch = alt === event.altKey;
      const shiftMatch = shift === event.shiftKey;
      
      if (keyMatch && ctrlMatch && altMatch && shiftMatch) {
        event.preventDefault();
        handler(event);
      }
    };
    
    document.addEventListener('keydown', listener);
    
    return function removeKeyboardShortcut() {
      document.removeEventListener('keydown', listener);
    };
  }

  // ═══════════════════════════════════════════════════════════════════
  // 9. Scroll Management - إدارة التمرير
  // ═══════════════════════════════════════════════════════════════════
  
  /**
   * معالجة التمرير مع throttle تلقائي
   */
  function onScroll(handler, options = {}) {
    const { throttleTime = 100, passive = true } = options;
    const throttledHandler = throttle(handler, throttleTime);
    
    document.addEventListener('scroll', throttledHandler, { passive });
    
    return function removeScrollListener() {
      document.removeEventListener('scroll', throttledHandler);
    };
  }

  // ═══════════════════════════════════════════════════════════════════
  // 10. Touch Gestures - إيماءات اللمس
  // ═══════════════════════════════════════════════════════════════════
  
  /**
   * اكتشاف Swipe gesture
   */
  function onSwipe(element, handler, options = {}) {
    if (!element) return;
    
    const { threshold = 50, timeout = 300 } = options;
    let touchStartX = 0;
    let touchStartY = 0;
    let touchStartTime = 0;
    
    const touchStart = (e) => {
      touchStartX = e.touches[0].clientX;
      touchStartY = e.touches[0].clientY;
      touchStartTime = Date.now();
    };
    
    const touchEnd = (e) => {
      const touchEndX = e.changedTouches[0].clientX;
      const touchEndY = e.changedTouches[0].clientY;
      const touchEndTime = Date.now();
      
      const deltaX = touchEndX - touchStartX;
      const deltaY = touchEndY - touchStartY;
      const deltaTime = touchEndTime - touchStartTime;
      
      if (deltaTime > timeout) return;
      
      if (Math.abs(deltaX) > Math.abs(deltaY) && Math.abs(deltaX) > threshold) {
        const direction = deltaX > 0 ? 'right' : 'left';
        handler({ direction, deltaX, deltaY });
      } else if (Math.abs(deltaY) > threshold) {
        const direction = deltaY > 0 ? 'down' : 'up';
        handler({ direction, deltaX, deltaY });
      }
    };
    
    element.addEventListener('touchstart', touchStart, { passive: true });
    element.addEventListener('touchend', touchEnd, { passive: true });
    
    return function removeSwipeListener() {
      element.removeEventListener('touchstart', touchStart);
      element.removeEventListener('touchend', touchEnd);
    };
  }

  // ═══════════════════════════════════════════════════════════════════
  // Export to window - إتاحة الوظائف عالمياً
  // ═══════════════════════════════════════════════════════════════════
  
  window.EventUtils = {
    // Core utilities
    delegate,
    listenerManager,
    
    // Performance utilities
    debounce,
    throttle,
    
    // Specialized listeners
    once,
    onClickOutside,
    onScroll,
    onSwipe,
    
    // Form utilities
    handleFormSubmit,
    watchFormChanges,
    
    // Keyboard
    addKeyboardShortcut,
    
    // Event bus
    eventBus,
    EventEmitter
  };
  
  // Shorter alias
  window.$events = window.EventUtils;

})(window);

