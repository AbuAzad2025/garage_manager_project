(function ($) {
  "use strict";
  if (!$) return;

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
    
    // Initialize real-time notifications
    initSocketNotifications();
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
    if (!$.fn.DataTable) return;
    $(root).find(".datatable").each(function () {
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
        console.error('DataTable column mismatch:', $tbl.attr('id'), {
          header: headerCols,
          body: bodyCols
        });
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
        console.error('DataTable initialization failed:', e, $tbl);
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

    // Enhanced notifications
    initSocketNotifications();
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
    showNotification('تم حفظ البيانات تلقائياً', 'success');
  }

  function initNotifications() {
    if (!$('#notification-container').length) {
      $('body').append('<div id="notification-container" class="position-fixed" style="top: 20px; right: 20px; z-index: 9999;"></div>');
    }
  }

  function showNotification(message, type = 'info') {
    const $container = $('#notification-container');
    const $notification = $(`
      <div class="alert alert-${type} alert-dismissible fade show" style="min-width: 300px;">
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
      </div>
    `);
    
    $container.append($notification);
    
    setTimeout(() => {
      $notification.alert('close');
    }, 3000);
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
      console.warn('Socket.IO not loaded, notifications disabled');
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
    const alertClass = {
      'success': 'alert-success',
      'error': 'alert-danger',
      'warning': 'alert-warning',
      'info': 'alert-info'
    }[type] || 'alert-info';
    
    const icon = {
      'success': 'fas fa-check-circle',
      'error': 'fas fa-exclamation-circle',
      'warning': 'fas fa-exclamation-triangle',
      'info': 'fas fa-info-circle'
    }[type] || 'fas fa-info-circle';
    
    const $notification = $(`
      <div class="alert ${alertClass} alert-dismissible fade show notification-toast" role="alert">
        <i class="${icon} me-2"></i>
        <strong>${title}</strong><br>
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
      </div>
    `);
    
    // إضافة للصفحة
    let $container = $('#notification-container');
    if ($container.length === 0) {
      $container = $('<div id="notification-container" style="position: fixed; top: 20px; right: 20px; z-index: 9999; max-width: 350px;"></div>');
      $('body').append($container);
    }
    
    $container.append($notification);
    
    // إزالة تلقائية
    setTimeout(() => {
      $notification.alert('close');
    }, 5000);
  }

  function showSystemAlert(message, severity = 'warning') {
    const alertClass = {
      'critical': 'alert-danger',
      'warning': 'alert-warning',
      'info': 'alert-info'
    }[severity] || 'alert-warning';
    
    const icon = {
      'critical': 'fas fa-exclamation-triangle',
      'warning': 'fas fa-exclamation-triangle',
      'info': 'fas fa-info-circle'
    }[severity] || 'fas fa-exclamation-triangle';
    
    const $alert = $(`
      <div class="alert ${alertClass} alert-dismissible fade show system-alert" role="alert">
        <i class="${icon} me-2"></i>
        <strong>تنبيه النظام:</strong> ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
      </div>
    `);
    
    // إضافة للصفحة
    let $container = $('#system-alert-container');
    if ($container.length === 0) {
      $container = $('<div id="system-alert-container" style="position: fixed; top: 20px; left: 20px; z-index: 9999; max-width: 400px;"></div>');
      $('body').append($container);
    }
    
    $container.append($alert);
    
    // إزالة تلقائية
    setTimeout(() => {
      $alert.alert('close');
    }, 10000);
  }
})(jQuery);
