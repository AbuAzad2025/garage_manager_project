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

      const hasButtons = $.fn.dataTable?.Buttons;
      const pageLen = +$tbl.data("page-length") || 10;
      const orderAttr = String($tbl.data("order") || "").trim();
      const order = orderAttr.match(/^(\d+)\s*,\s*(asc|desc)$/i)
        ? [[+RegExp.$1, RegExp.$2.toLowerCase()]]
        : [];

      const noSortIdx = $tbl.find("thead th.dt-nosort").map((i, el) => i).get();

      $tbl.DataTable({
        dom: hasButtons ? "Bfrtip" : "frtip",
        buttons: hasButtons ? [
          { extend: "excelHtml5", text: '<i class="fas fa-file-excel"></i> Excel' },
          { extend: "print", text: '<i class="fas fa-print"></i> طباعة' }
        ] : [],
        pageLength: pageLen,
        responsive: true,
        autoWidth: false,
        language: { url: "/static/datatables/Arabic.json" },
        order,
        columnDefs: noSortIdx.length ? [{ orderable: false, targets: noSortIdx }] : []
      });
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
})(jQuery);
