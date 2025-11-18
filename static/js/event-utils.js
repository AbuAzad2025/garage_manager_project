(function(window) {
  'use strict';

  function delegate(parent, eventType, selector, handler) {
    const listener = function(event) {
      const target = event.target.closest(selector);
      if (target && parent.contains(target)) {
        handler.call(target, event);
      }
    };
    parent.addEventListener(eventType, listener);
    return function removeDelegation() {
      parent.removeEventListener(eventType, listener);
    };
  }

  class ListenerManager {
    constructor() {
      this.listeners = new WeakMap();
    }
    
    add(element, eventType, handler, options = {}) {
      if (!element) return;
      element.addEventListener(eventType, handler, options);
      if (!this.listeners.has(element)) {
        this.listeners.set(element, []);
      }
      this.listeners.get(element).push({ eventType, handler, options });
    }
    
    removeAll(element) {
      if (!element || !this.listeners.has(element)) return;
      const listeners = this.listeners.get(element);
      listeners.forEach(({ eventType, handler }) => {
        element.removeEventListener(eventType, handler);
      });
      this.listeners.delete(element);
    }
    
    remove(element, eventType, handler) {
      if (!element) return;
      element.removeEventListener(eventType, handler);
      if (this.listeners.has(element)) {
        const listeners = this.listeners.get(element);
        const index = listeners.findIndex(l => l.eventType === eventType && l.handler === handler);
        if (index !== -1) listeners.splice(index, 1);
      }
    }
  }
  
  const listenerManager = new ListenerManager();

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

  class EventEmitter {
    constructor() {
      this.events = {};
    }
    
    on(eventName, handler) {
      if (!this.events[eventName]) this.events[eventName] = [];
      this.events[eventName].push(handler);
      return () => this.off(eventName, handler);
    }
    
    off(eventName, handler) {
      if (!this.events[eventName]) return;
      const index = this.events[eventName].indexOf(handler);
      if (index !== -1) this.events[eventName].splice(index, 1);
    }
    
    emit(eventName, data) {
      if (!this.events[eventName]) return;
      this.events[eventName].forEach(handler => {
        try { handler(data); } catch (error) {}
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
  
  const eventBus = new EventEmitter();

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
        setTimeout(() => { isSubmitting = false; }, 1000);
      }
    };
    form.addEventListener('submit', submitHandler);
    return function removeFormSubmitHandler() {
      form.removeEventListener('submit', submitHandler);
    };
  }
  
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

  function onClickOutside(element, handler) {
    if (!element) return;
    const listener = function(event) {
      if (!element.contains(event.target)) handler(event);
    };
    document.addEventListener('click', listener);
    return function removeClickOutsideListener() {
      document.removeEventListener('click', listener);
    };
  }

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

  function onScroll(handler, options = {}) {
    const { throttleTime = 100, passive = true } = options;
    const throttledHandler = throttle(handler, throttleTime);
    document.addEventListener('scroll', throttledHandler, { passive });
    return function removeScrollListener() {
      document.removeEventListener('scroll', throttledHandler);
    };
  }

  function onSwipe(element, handler, options = {}) {
    if (!element) return;
    const { threshold = 50, timeout = 300 } = options;
    let touchStartX = 0, touchStartY = 0, touchStartTime = 0;
    
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

  window.EventUtils = {
    delegate,
    listenerManager,
    debounce,
    throttle,
    once,
    onClickOutside,
    onScroll,
    onSwipe,
    handleFormSubmit,
    watchFormChanges,
    addKeyboardShortcut,
    eventBus,
    EventEmitter
  };
  
  window.$events = window.EventUtils;

})(window);

