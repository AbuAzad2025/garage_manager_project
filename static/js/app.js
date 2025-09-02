(function ($) {
  "use strict";
  if (typeof $ === "undefined") return;

  $(function () {
    initAll(document);
    try {
      let t = null, pending = false;
      const observer = new MutationObserver(function (mutations) {
        if (pending) return;
        pending = true;
        clearTimeout(t);
        t = setTimeout(function () {
          pending = false;
          initAll(document);
        }, 60);
      });
      observer.observe(document.body, { childList: true, subtree: true });
    } catch (e) {}
  });

  $(document).on("shown.bs.modal", function (e) {
    const root = e.target || document;
    initAll(root);
  });

  function initAll(root) {
    initDataTables(root);
    initDatepickers(root);
    initSelect2Basic(root);
    initAjaxSelects(root);
    initConfirmForms(root);
    initBtnLoading(root);
  }

  function initDataTables(root) {
    if (!$.fn.DataTable) return;
    $(root).find(".datatable").each(function () {
      const $tbl = $(this);
      if ($tbl.data("dt-initialized")) return;
      $tbl.data("dt-initialized", 1);

      const hasButtons = $.fn.dataTable && $.fn.dataTable.Buttons;
      const pageLen = Number($tbl.data("page-length") || 10);
      let order = [];
      const orderAttr = ($tbl.data("order") || "").toString().trim();
      if (orderAttr) {
        const m = orderAttr.match(/^(\d+)\s*,\s*(asc|desc)$/i);
        if (m) order = [[Number(m[1]), m[2].toLowerCase()]];
      }
      const noSortIdx = [];
      $tbl.find("thead th").each(function (i) {
        if ($(this).hasClass("dt-nosort")) noSortIdx.push(i);
      });

      const opts = {
        dom: hasButtons ? "Bfrtip" : "frtip",
        buttons: hasButtons ? [
          { extend: "excelHtml5", text: '<i class="fas fa-file-excel"></i> Excel' },
          { extend: "print", text: '<i class="fas fa-print"></i> طباعة' }
        ] : [],
        pageLength: pageLen,
        responsive: true,
        autoWidth: false,
        language: { url: "/static/datatables/Arabic.json" }
      };
      if (order.length) opts.order = order;
      if (noSortIdx.length) opts.columnDefs = [{ orderable: false, targets: noSortIdx }];

      $tbl.DataTable(opts);
    });
  }

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

  function initSelect2Basic(root) {
    if (!$.fn.select2) return;
    $(root).find("select.select2").each(function () {
      const $el = $(this);
      if ($el.hasClass("ajax-select")) return;
      if ($el.data("s2-initialized")) return;
      $el.data("s2-initialized", 1);
      const parent = $el.closest(".modal");
      $el.select2({
        dir: "rtl",
        width: "100%",
        language: "ar",
        placeholder: $el.attr("placeholder") || "اختر...",
        allowClear: String($el.data("allow-clear") || "").toLowerCase() === "true" || $el.data("allowClear") === 1,
        dropdownParent: parent.length ? parent : $(document.body)
      });
    });
  }

  function initAjaxSelects(root) {
    if (!$.fn.select2) return;
    $(root).find("select.ajax-select").each(function () {
      const $el = $(this);
      if ($el.data("s2-initialized")) return;

      const url = $el.data("url") || $el.data("endpoint");
      if (!url) return;

      const parent = $el.closest(".modal");
      const delay = Number($el.data("delay") || 250);
      const limit = Number($el.data("limit") || 20);
      const minLen = Number($el.data("min-length") || 0);

      $el.select2({
        dir: "rtl",
        width: "100%",
        language: "ar",
        placeholder: $el.attr("placeholder") || "اختر...",
        allowClear: String($el.data("allow-clear") || "").toLowerCase() === "true" || $el.data("allowClear") === 1,
        minimumInputLength: minLen,
        dropdownParent: parent.length ? parent : $(document.body),
        ajax: {
          url: url,
          dataType: "json",
          delay: delay,
          transport: function (params, success, failure) {
            return $.ajax(params).then(success).catch(failure);
          },
          data: function (params) {
            return { q: params.term || "", limit: limit };
          },
          processResults: function (data) {
            const arr = Array.isArray(data) ? data : (data.results || data.data || []);
            return {
              results: arr.map(function (x) {
                return { id: x.id, text: x.text || x.name || String(x.id) };
              })
            };
          },
          cache: true
        }
      });

      const val = $el.val();
      const txt = $el.data("initial-text");
      if (val && !$el.find('option[value="' + val + '"]').length && txt) {
        const opt = new Option(txt, String(val), true, true);
        $el.append(opt).trigger("change");
      }

      $el.data("s2-initialized", 1);
    });
  }

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

  function initBtnLoading(root) {
    $(root).find(".btn-loading").each(function () {
      const $btn = $(this);
      if ($btn.data("loading-bound")) return;
      $btn.data("loading-bound", 1);
      $btn.on("click", function () {
        if ($btn.prop("disabled")) return;
        const original = $btn.html();
        $btn.data("original-html", original);
        $btn.attr("aria-busy", "true");
        $btn.prop("disabled", true).html('<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> جاري المعالجة...');
        setTimeout(function () {
          if ($btn.closest("form").length === 0) {
            $btn.prop("disabled", false).attr("aria-busy", "false").html(original);
          }
        }, 10000);
      });
    });
  }
})(jQuery);
