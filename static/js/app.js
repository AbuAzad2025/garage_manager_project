// File: static/js/app.js
// Production-ready app boot (RTL + Select2 + DataTables + Datepicker + AJAX selects)
(function ($) {
  "use strict";
  if (typeof $ === "undefined") return;

  // =========================
  // Boot
  // =========================
  $(document).ready(function () {
    initAll(document);

    // مراقبة العناصر المُضافة ديناميكيًا (مودالات، partials...)
    try {
      const observer = new MutationObserver(function (mutations) {
        for (const m of mutations) {
          if (m.addedNodes && m.addedNodes.length) {
            initAll(document);
            break;
          }
        }
      });
      observer.observe(document.body, { childList: true, subtree: true });
    } catch (e) {
      // متصفحات قديمة — نتجاهل
    }
  });

  // إعادة تهيئة عند فتح مودال Bootstrap
  $(document).on("shown.bs.modal", function (e) {
    const root = e.target || document;
    initAll(root);
  });

  // =========================
  // Master init
  // =========================
  function initAll(root) {
    initDataTables(root);
    initDatepickers(root);
    initSelect2Basic(root);
    initAjaxSelects(root);
    initConfirmForms(root);
    initBtnLoading(root);
  }

  // =========================
  // 1) DataTables
  // =========================
  function initDataTables(root) {
    if (!$.fn.DataTable) return;
    $(root).find(".datatable").each(function () {
      const $tbl = $(this);
      if ($tbl.data("dt-initialized")) return;
      $tbl.data("dt-initialized", 1);

      $tbl.DataTable({
        dom: "Bfrtip",
        buttons: [
          { extend: "excelHtml5", text: '<i class="fas fa-file-excel"></i> Excel' },
          { extend: "print", text: '<i class="fas fa-print"></i> طباعة' }
        ],
        pageLength: 10,
        responsive: true,
        language: { url: "/static/datatables/Arabic.json" }
      });
    });
  }

  // =========================
  // 2) Datepicker (Bootstrap)
  // =========================
  function initDatepickers(root) {
    if (!$.fn.datepicker) return;
    $(root).find(".datepicker").each(function () {
      const $el = $(this);
      if ($el.data("dp-initialized")) return;
      $el.data("dp-initialized", 1);

      $el.datepicker({
        format: "yyyy-mm-dd",
        autoclose: true,
        language: "ar",
        orientation: "auto right",
        todayHighlight: true
      });
    });
  }

  // =========================
  // 3) Select2 (عادي)
  // =========================
  function initSelect2Basic(root) {
    if (!$.fn.select2) return;
    $(root).find("select.select2").each(function () {
      const $el = $(this);
      // لو هذا الحقل ajax-select، تتركه للدالة التالية
      if ($el.hasClass("ajax-select")) return;
      if ($el.data("s2-initialized")) return;
      $el.data("s2-initialized", 1);

      $el.select2({
        dir: "rtl",
        width: "100%",
        placeholder: $el.attr("placeholder") || "اختر...",
        language: "ar"
      });
    });
  }

  // =========================
  // 4) Select2 (AJAX) باستخدام data-url
  // =========================
  function initAjaxSelects(root) {
    if (!$.fn.select2) return;
    $(root).find("select.ajax-select").each(function () {
      const $el = $(this);
      if ($el.data("s2-initialized")) return;

      const url = $el.attr("data-url");
      if (!url) return; // يحتاج data-url مُحقّن من الفورم

      $el.select2({
        dir: "rtl",
        width: "100%",
        language: "ar",
        placeholder: $el.attr("placeholder") || "اختر...",
        ajax: {
          url: url,
          dataType: "json",
          delay: 250,
          data: function (params) {
            return {
              q: params.term || "",
              limit: 20
            };
          },
          processResults: function (data) {
            // يدعم صيغتين: Array أو {results:[...]}
            const arr = Array.isArray(data) ? data : (data.results || []);
            return {
              results: arr.map(function (x) {
                return { id: x.id, text: x.text };
              }),
              pagination: { more: false }
            };
          },
          cache: true
        }
      });

      $el.data("s2-initialized", 1);
    });
  }

  // =========================
  // 5) حوار تأكيد للنماذج
  // =========================
  function initConfirmForms(root) {
    $(root).find("form[data-confirm]").each(function () {
      const $form = $(this);
      if ($form.data("confirm-bound")) return;
      $form.data("confirm-bound", 1);

      $form.on("submit", function (e) {
        const msg = $form.data("confirm");
        if (!msg) return;
        if (!window.confirm(msg)) {
          e.preventDefault();
          e.stopImmediatePropagation();
        }
      });
    });
  }

  // =========================
  // 6) حالة تحميل الأزرار
  // =========================
  function initBtnLoading(root) {
    $(root).find(".btn-loading").each(function () {
      const $btn = $(this);
      if ($btn.data("loading-bound")) return;
      $btn.data("loading-bound", 1);

      $btn.on("click", function () {
        if ($btn.prop("disabled")) return;
        const original = $btn.html();
        $btn.data("original-html", original);
        $btn.prop("disabled", true).html(
          '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> جاري المعالجة...'
        );

        // لو تم إلغاء الإرسال أو فشل بشكل واضح، نعيد الزر (حماية إضافية)
        setTimeout(function () {
          if ($btn.closest("form").length === 0) {
            $btn.prop("disabled", false).html(original);
          }
        }, 10000);
      });
    });
  }

})(jQuery);
