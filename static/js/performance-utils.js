(function(window) {
  'use strict';

  function initLazyLoading() {
    if ('IntersectionObserver' in window) {
      const imageObserver = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            const img = entry.target;
            if (img.dataset.src) {
              img.src = img.dataset.src;
              img.removeAttribute('data-src');
            }
            if (img.dataset.srcset) {
              img.srcset = img.dataset.srcset;
              img.removeAttribute('data-srcset');
            }
            img.classList.add('loaded');
            observer.unobserve(img);
          }
        });
      }, { rootMargin: '50px 0px', threshold: 0.01 });
      
      document.querySelectorAll('img[data-src]').forEach(img => {
        imageObserver.observe(img);
      });
      return imageObserver;
    }
    
    document.querySelectorAll('img[data-src]').forEach(img => {
      if (img.dataset.src) {
        img.src = img.dataset.src;
        img.removeAttribute('data-src');
      }
    });
  }

  class VirtualScroller {
    constructor(container, options = {}) {
      this.container = container;
      this.rowHeight = options.rowHeight || 50;
      this.visibleRows = options.visibleRows || 20;
      this.data = options.data || [];
      this.renderRow = options.renderRow || (item => `<div>${item}</div>`);
      this.scrollTop = 0;
      this.init();
    }
    
    init() {
      this.container.style.height = `${this.rowHeight * this.visibleRows}px`;
      this.container.style.overflow = 'auto';
      this.container.style.position = 'relative';
      const wrapper = document.createElement('div');
      wrapper.style.height = `${this.rowHeight * this.data.length}px`;
      wrapper.style.position = 'relative';
      this.wrapper = wrapper;
      this.container.appendChild(wrapper);
      this.container.addEventListener('scroll', this.onScroll.bind(this), { passive: true });
      this.render();
    }
    
    onScroll() {
      this.scrollTop = this.container.scrollTop;
      this.render();
    }
    
    render() {
      const startIndex = Math.floor(this.scrollTop / this.rowHeight);
      const endIndex = Math.min(startIndex + this.visibleRows + 2, this.data.length);
      this.wrapper.innerHTML = '';
      for (let i = startIndex; i < endIndex; i++) {
        const row = document.createElement('div');
        row.style.position = 'absolute';
        row.style.top = `${i * this.rowHeight}px`;
        row.style.height = `${this.rowHeight}px`;
        row.innerHTML = this.renderRow(this.data[i], i);
        this.wrapper.appendChild(row);
      }
    }
  }

  function loadScript(src, options = {}) {
    return new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = src;
      script.async = options.async !== false;
      script.defer = options.defer || false;
      script.onload = () => resolve(script);
      script.onerror = () => reject(new Error(`Failed to load script: ${src}`));
      document.head.appendChild(script);
    });
  }
  
  function loadCSS(href) {
    return new Promise((resolve, reject) => {
      const link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = href;
      link.onload = () => resolve(link);
      link.onerror = () => reject(new Error(`Failed to load CSS: ${href}`));
      document.head.appendChild(link);
    });
  }

  class RequestCache {
    constructor(maxAge = 5 * 60 * 1000) {
      this.cache = new Map();
      this.maxAge = maxAge;
    }
    
    async fetch(url, options = {}) {
      const cacheKey = `${url}:${JSON.stringify(options)}`;
      if (this.cache.has(cacheKey)) {
        const cached = this.cache.get(cacheKey);
        if (Date.now() - cached.timestamp < this.maxAge) {
          return cached.data;
        }
        this.cache.delete(cacheKey);
      }
      const response = await fetch(url, options);
      const data = await response.json();
      this.cache.set(cacheKey, { data, timestamp: Date.now() });
      return data;
    }
    
    clear() {
      this.cache.clear();
    }
    
    invalidate(url) {
      const keys = Array.from(this.cache.keys());
      keys.forEach(key => {
        if (key.startsWith(url)) this.cache.delete(key);
      });
    }
  }
  
  const requestCache = new RequestCache();

  function nextFrame(callback) {
    return requestAnimationFrame(() => {
      requestAnimationFrame(callback);
    });
  }
  
  function batchUpdates(updates) {
    requestAnimationFrame(() => {
      updates.forEach(update => update());
    });
  }

  function whenVisible(element, callback, options = {}) {
    if (!element) return;
    if ('IntersectionObserver' in window) {
      const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            callback(entry.target);
            if (options.once) observer.unobserve(entry.target);
          }
        });
      }, {
        threshold: options.threshold || 0.1,
        rootMargin: options.rootMargin || '0px'
      });
      observer.observe(element);
      return function stopObservingVisibility() {
        observer.disconnect();
      };
    }
    callback(element);
  }

  function measurePerformance(name, func) {
    const start = performance.now();
    const result = func();
    const end = performance.now();
    return result;
  }
  
  async function measureAsync(name, func) {
    const start = performance.now();
    const result = await func();
    const end = performance.now();
    return result;
  }

  window.PerfUtils = {
    initLazyLoading,
    loadScript,
    loadCSS,
    VirtualScroller,
    requestCache,
    nextFrame,
    batchUpdates,
    whenVisible,
    measurePerformance,
    measureAsync
  };
  
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initLazyLoading);
  } else {
    initLazyLoading();
  }

})(window);

