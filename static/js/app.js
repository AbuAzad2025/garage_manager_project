(function ($, window, document) {
  "use strict";
  if (!$) return;

  const rawEventAdd = $.event && $.event.add;
  const rawEventRemove = $.event && $.event.remove;
  const registryStore = new WeakMap();
  let registryCount = 0;

  function normalizeTypes(types) {
    if (typeof types !== "string") {
      return [];
    }
    return types
      .split(/\s+/)
      .map(t => t && t.split(".")[0])
      .filter(Boolean);
  }

  function getEntries(element) {
    return registryStore.get(element) || [];
  }

  function remember(element, type, selector, handler) {
    if (!element || !type || !handler) return;
    const entries = getEntries(element);
    entries.push({ type, selector: selector || null, handler, guid: handler.guid });
    registryStore.set(element, entries);
    registryCount += 1;
  }

  function forget(element, predicate) {
    if (!element || !registryStore.has(element)) return;
    const entries = registryStore.get(element);
    if (!entries || !entries.length) {
      registryStore.delete(element);
      return;
    }
    const filtered = entries.filter(entry => !(predicate && predicate(entry)));
    registryCount -= entries.length - filtered.length;
    if (filtered.length) {
      registryStore.set(element, filtered);
    } else {
      registryStore.delete(element);
    }
  }

  function detachElement(element) {
    if (!element || !rawEventRemove) return;
    if (!registryStore.has(element)) return;
    const entries = registryStore.get(element) || [];
    entries.forEach(entry => {
      try {
        rawEventRemove.call($.event, element, entry.type, entry.handler, entry.selector || undefined);
      } catch (err) {
      }
    });
    registryStore.delete(element);
  }

  function detachTree(node) {
    if (!node) return;
    if (node.nodeType === 1 || node.nodeType === 9) {
      detachElement(node);
      if (node.querySelectorAll) {
        node.querySelectorAll("*").forEach(child => detachElement(child));
      }
    }
  }

  if (rawEventAdd && rawEventRemove) {
    $.event.add = function (elem, types, handler, data, selector) {
      if (!elem || !types || !handler) {
        return rawEventAdd.call(this, elem, types, handler, data, selector);
      }
      handler.guid = handler.guid || $.guid++;
      const normalizedTypes = normalizeTypes(types);
      if (normalizedTypes.length) {
        normalizedTypes.forEach(type => {
          const duplicates = getEntries(elem).filter(entry =>
            entry.type === type &&
            entry.selector === (selector || null) &&
            entry.guid === handler.guid
          );
          if (duplicates.length) {
            rawEventRemove.call(this, elem, type, handler, selector);
            forget(elem, entry =>
              entry.type === type &&
              entry.selector === (selector || null) &&
              entry.guid === handler.guid
            );
          }
        });
      }
      const result = rawEventAdd.call(this, elem, types, handler, data, selector);
      if (normalizedTypes.length) {
        normalizedTypes.forEach(type => remember(elem, type, selector, handler));
      }
      return result;
    };

    $.event.remove = function (elem, types, handler, selector, mappedTypes) {
      const result = rawEventRemove.call(this, elem, types, handler, selector, mappedTypes);
      if (!elem) return result;
      if (!types) {
        forget(elem);
        return result;
      }
      const normalizedTypes = normalizeTypes(types);
      if (normalizedTypes.length) {
        normalizedTypes.forEach(type => {
          forget(elem, entry =>
            entry.type === type &&
            (selector ? entry.selector === selector : true) &&
            (handler ? entry.guid === (handler.guid || handler.__guid) : true)
          );
        });
      } else {
        forget(elem);
      }
      return result;
    };
  }

  if (!window.EventRegistry) {
    window.EventRegistry = {
      detach(element) {
        detachTree(element);
      },
      activeCount() {
        return registryCount;
      }
    };
  }

  const registryObserver = new MutationObserver(mutations => {
    mutations.forEach(mutation => {
      mutation.removedNodes.forEach(node => detachTree(node));
    });
  });
  registryObserver.observe(document.documentElement || document.body, { childList: true, subtree: true });

  const dataTablesAssets = {
    css: [
      "/static/adminlte/plugins/datatables-bs4/css/dataTables.bootstrap4.min.css",
      "/static/adminlte/plugins/datatables-responsive/css/responsive.bootstrap4.min.css",
      "/static/adminlte/plugins/datatables-buttons/css/buttons.bootstrap4.min.css"
    ],
    js: [
      "/static/adminlte/plugins/datatables/jquery.dataTables.min.js",
      "/static/adminlte/plugins/datatables-bs4/js/dataTables.bootstrap4.min.js",
      "/static/adminlte/plugins/datatables-responsive/js/dataTables.responsive.min.js",
      "/static/adminlte/plugins/datatables-responsive/js/responsive.bootstrap4.min.js",
      "/static/adminlte/plugins/datatables-buttons/js/dataTables.buttons.min.js",
      "/static/adminlte/plugins/datatables-buttons/js/buttons.bootstrap4.min.js",
      "/static/adminlte/plugins/jszip/jszip.min.js",
      "/static/adminlte/plugins/datatables-buttons/js/buttons.html5.min.js",
      "/static/adminlte/plugins/datatables-buttons/js/buttons.print.min.js"
    ]
  };
  let dataTablesPromise = null;

  function ensureDataTables() {
    if ($.fn.DataTable) return Promise.resolve();
    if (dataTablesPromise) return dataTablesPromise;
    const cssLoaders = dataTablesAssets.css.map(href => {
      if (window.PerfUtils && PerfUtils.loadCSS) return PerfUtils.loadCSS(href);
      return new Promise((resolve, reject) => {
        const link = document.createElement("link");
        link.rel = "stylesheet";
        link.href = href;
        link.onload = () => resolve(link);
        link.onerror = () => reject(new Error("Failed to load CSS: " + href));
        document.head.appendChild(link);
      });
    });
    const loadJsSequentially = dataTablesAssets.js.reduce((chain, src) => {
      return chain.then(() => {
        if (window.PerfUtils && PerfUtils.loadScript) {
          return PerfUtils.loadScript(src, { async: false });
        }
        return new Promise((resolve, reject) => {
          const script = document.createElement("script");
          script.src = src;
          script.async = false;
          script.onload = () => resolve(script);
          script.onerror = () => reject(new Error("Failed to load script: " + src));
          document.head.appendChild(script);
        });
      });
    }, Promise.resolve());
    dataTablesPromise = Promise.all(cssLoaders).then(() => loadJsSequentially).then(() => {
      if (!$.fn.DataTable) throw new Error("DataTables failed to load");
      $(document).trigger("datatables:ready");
    }).catch(() => {
      dataTablesPromise = null;
    });
    return dataTablesPromise || Promise.resolve();
  }

  $(function () {
    const observer = new MutationObserver(() => {
      if (window._mutationPending) return;
      window._mutationPending = true;
      setTimeout(() => {
        window._mutationPending = false;
        initAll(document);
      }, 60);
    });
    observer.observe(document.body, { childList: true, subtree: true });

    $(document).on("shown.bs.modal", e => initAll(e.target || document));

    initAll(document);
    
    // Enhanced performance optimizations
    initPerformanceOptimizations();
  });

  function initAll(root) {
    initDataTables(root);
    initDatepickers(root);
    initSelect2Basic(root);
    initPerformanceOptimizations(root);
    initAjaxSelects(root);
    initConfirmForms(root);
    initBtnLoading(root);
  }

  function initDataTables(root) {
    const tables = $(root).find(".datatable");
    if (!tables.length) return;
    if (!$.fn.DataTable) {
      ensureDataTables().then(() => initDataTables(root));
      return;
    }
    tables.each(function () {
      const $tbl = $(this);
      // تخطي الجداول المحددة بـ data-dt-skip
      if ($tbl.data("dt-skip") || $tbl.attr("data-dt-skip")) return;
      if ($tbl.data("dt-initialized")) return;
      $tbl.data("dt-initialized", 1);

      const hasButtons = $.fn.dataTable?.Buttons;
      const pageLen = +$tbl.data("page-length") || 10;
      const orderAttr = String($tbl.data("order") || "").trim();
      const order = orderAttr.match(/^(\d+)\s*,\s*(asc|desc)$/i)
        ? [[+RegExp.$1, RegExp.$2.toLowerCase()]]
        : [];

      const noSortIdx = $tbl.find("thead th.dt-nosort").map((i, el) => i).get();

      // تحقق من وجود thead و tbody صحيحين
      if (!$tbl.find('thead').length || !$tbl.find('tbody').length) {
        return;
      }

      // تحقق من وجود بيانات فعلية (تجاهل صفوف colspan)
      const dataRows = $tbl.find('tbody tr').not(':has(td[colspan])');
      if (dataRows.length === 0) {
        return; // لا نهيئ DataTables للجداول الفارغة
      }

      // تحقق من تطابق عدد الأعمدة في صف البيانات الأول
      const headerCols = $tbl.find('thead tr:first th, thead tr:first td').length;
      const bodyCols = dataRows.first().find('td').length;
      
      if (headerCols !== bodyCols) {

        return;
      }

      try {
        $tbl.DataTable({
          dom: hasButtons ? "Bfrtip" : "frtip",
          buttons: hasButtons ? [
            { extend: "excelHtml5", text: '<i class="fas fa-file-excel"></i> Excel' },
            { extend: "print", text: '<i class="fas fa-print"></i> طباعة' }
          ] : [],
          pageLength: pageLen,
          responsive: true,
          autoWidth: false,
          language: { 
            url: "/static/datatables/Arabic.json",
            // fallback في حالة فشل تحميل الملف
            emptyTable: "لا توجد بيانات متاحة",
            info: "عرض _START_ إلى _END_ من أصل _TOTAL_ سجل",
            infoEmpty: "عرض 0 إلى 0 من أصل 0 سجل",
            infoFiltered: "(مفلتر من إجمالي _MAX_ سجل)",
            lengthMenu: "عرض _MENU_ سجل",
            loadingRecords: "جاري التحميل...",
            processing: "جاري المعالجة...",
            search: "بحث:",
            zeroRecords: "لم يتم العثور على نتائج",
            paginate: {
              first: "الأول",
              last: "الأخير", 
              next: "التالي",
              previous: "السابق"
            }
          },
          order,
          columnDefs: noSortIdx.length ? [{ orderable: false, targets: noSortIdx }] : []
        });
      } catch (e) {

      }
    });
  }

  function initDatepickers(root) {
    if (!$.fn.datepicker) return;
    $(root).find(".datepicker").each(function () {
      const $el = $(this);
      if ($el.data("dp-initialized")) return;
      $el.data("dp-initialized", 1).datepicker({
        format: "yyyy-mm-dd",
        autoclose: true,
        language: "ar",
        orientation: "auto right",
        todayHighlight: true
      });
    });
  }

  function initSelect2Basic(root) {
    if (!$.fn.select2) return;
    $(root).find("select.select2:not(.ajax-select)").each(function () {
      const $el = $(this);
      if ($el.data("s2-initialized")) return;
      $el.data("s2-initialized", 1);
      const parent = $el.closest(".modal");
      $el.select2({
        dir: "rtl",
        width: "100%",
        language: "ar",
        placeholder: $el.attr("placeholder") || "اختر...",
        allowClear: String($el.data("allow-clear") || "").toLowerCase() === "true" || $el.data("allowClear") == 1,
        dropdownParent: parent.length ? parent : $(document.body)
      });
    });
  }

  function initAjaxSelects(root) {
    if (!$.fn.select2) return;
    $(root).find("select.ajax-select").each(function () {
      const $el = $(this);
      if ($el.data("s2-initialized")) return;
      $el.data("s2-initialized", 1);

      const url = $el.data("url") || $el.data("endpoint");
      if (!url) return;

      const parent = $el.closest(".modal");
      const delay = +$el.data("delay") || 250;
      const limit = +$el.data("limit") || 20;
      const minLen = +$el.data("min-length") || 0;

      $el.select2({
        dir: "rtl",
        width: "100%",
        language: "ar",
        placeholder: $el.attr("placeholder") || "اختر...",
        allowClear: String($el.data("allow-clear") || "").toLowerCase() === "true" || $el.data("allowClear") == 1,
        minimumInputLength: minLen,
        dropdownParent: parent.length ? parent : $(document.body),
        ajax: {
          url,
          dataType: "json",
          delay,
          cache: true,
          data: params => ({ q: params.term || "", limit }),
          processResults: data => ({
            results: (Array.isArray(data) ? data : (data.results || data.data || [])).map(x => ({
              id: x.id,
              text: x.text || x.name || String(x.id)
            }))
          })
        }
      });

      const val = $el.val();
      const txt = $el.data("initial-text");
      if (val && txt && !$el.find('option[value="' + val + '"]').length) {
        $el.append(new Option(txt, val, true, true)).trigger("change");
      }
    });
  }

  function initConfirmForms(root) {
    $(root).find("form[data-confirm]").each(function () {
      const $form = $(this);
      if ($form.data("confirm-bound")) return;
      $form.data("confirm-bound", 1).on("submit", function (e) {
        const msg = $form.data("confirm");
        if (msg && !confirm(msg)) {
          e.preventDefault();
          e.stopImmediatePropagation();
        }
      });
    });
  }

  function initBtnLoading(root) {
    $(root).find(".btn-loading").each(function () {
      const $btn = $(this);
      if ($btn.data("loading-bound")) return;
      $btn.data("loading-bound", 1).on("click", function () {
        if ($btn.prop("disabled")) return;
        const original = $btn.html();
        $btn.data("original-html", original).prop("disabled", true).attr("aria-busy", "true")
          .html('<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> جاري المعالجة...');
        setTimeout(() => {
          if (!$btn.closest("form").length) {
            $btn.prop("disabled", false).attr("aria-busy", "false").html(original);
          }
        }, 10000);
      });
    });
  }

  // Enhanced performance optimizations
  function initPerformanceOptimizations(root) {
    // Lazy loading for images
    if ('IntersectionObserver' in window) {
      const imageObserver = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            const img = entry.target;
            img.src = img.dataset.src;
            img.classList.remove('lazy');
            imageObserver.unobserve(img);
          }
        });
      });

      $(root).find('img[data-src]').each(function() {
        imageObserver.observe(this);
      });
    }

    // Debounced search
    let searchTimeout;
    $(root).find('[data-search]').on('input', function() {
      clearTimeout(searchTimeout);
      const $this = $(this);
      searchTimeout = setTimeout(() => {
        performSearch($this.val(), $this.data('search'));
      }, 300);
    });

    // Auto-save forms
    $(root).find('[data-autosave]').on('input change', debounce(function() {
      saveFormData($(this).closest('form'));
    }, 1000));
  }

  function performSearch(query, target) {
    if (query.length < 2) return;
    
    const $container = $(`[data-search-target="${target}"]`);
    $container.html('<div class="text-center"><div class="spinner-border"></div></div>');
    
    $.get(`/api/search/${target}`, { q: query })
      .done(data => {
        $container.html(data.html || 'لا توجد نتائج');
      })
      .fail(() => {
        $container.html('<div class="alert alert-danger">خطأ في البحث</div>');
      });
  }

  function saveFormData($form) {
    const formData = $form.serialize();
    localStorage.setItem(`form_${$form.attr('id')}`, formData);
  }

  function initNotifications() {
    if (!$('#notification-container').length) {
      $('body').append('<div id="notification-container" class="position-fixed" style="top: 20px; right: 20px; z-index: 9999;"></div>');
    }
  }

  function showNotification(message, type = 'info') {
    // Disabled: notifications can cause performance issues
    return;
  }

  function debounce(func, wait) {
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

  // نظام الإشعارات الفورية
  let socketNotificationsInitialized = false;
  function initSocketNotifications() {
    if (socketNotificationsInitialized) return;
    socketNotificationsInitialized = true;
    
    if (typeof io === 'undefined') {

      return;
    }

    const socket = io();
    
    // إشعارات المستخدم
    socket.on('notification', function(data) {
      showNotification(data.title, data.message, data.type);
    });
    
    // إشعارات عامة
    socket.on('broadcast_notification', function(data) {
      showNotification(data.title, data.message, data.type);
    });
    
    // تنبيهات النظام
    socket.on('system_alert', function(data) {
      showSystemAlert(data.message, data.severity);
    });
    
    // اتصال المستخدم بالغرفة
    socket.emit('join_user_room');
  }

  function showNotification(title, message, type = 'info') {
    // Disabled: notifications can cause performance issues
    return;
  }

  function showSystemAlert(message, severity = 'warning') {
    // Disabled: notifications can cause performance issues
    return;
  }
})(jQuery, window, document);
