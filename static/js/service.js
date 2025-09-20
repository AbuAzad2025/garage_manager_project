(function () {
  'use strict';

  function toNum(v) { var n = parseFloat(v); return isNaN(n) ? 0 : n; }
  function round2(v) { return (Math.round((toNum(v) + Number.EPSILON) * 100) / 100).toFixed(2); }

  function dtSafeInit() {
    var $table = $('#servicesTable');
    if (!$table.length) return;
    try {
      $table.DataTable({ language: { url: '//cdn.datatables.net/plug-ins/1.13.4/i18n/ar.json' }, pageLength: 25, order: [] });
    } catch (e) {}
    $('#selectAll').on('change', function () { $('.row-select').prop('checked', this.checked); });
    $('#bulkDelete').on('click', function () {
      var ids = $('.row-select:checked').map(function () { return this.value; }).get();
      if (!ids.length) return Swal.fire('تنبيه', 'لم يتم تحديد أي طلب', 'warning');
      Swal.fire({ icon: 'warning', title: 'تأكيد الحذف الجماعي', text: 'سيتم حذف ' + ids.length + ' طلب (غير قابل للتراجع)', showCancelButton: true, confirmButtonText: 'نعم، احذف' })
      .then(function (res) { if (!res.isConfirmed) return; Swal.fire('تم', 'هذه واجهة فقط، أضف راوت الحذف الجماعي لاحقًا.', 'success'); });
    });
    $('#exportCsv').on('click', function () { window.location.assign('/service/export/csv'); });
    $('#exportPdf').on('click', function () { window.location.assign('/service/export/pdf'); });
  }

  function smartPost(url) {
    if (!url) return;
    var token = $('input[name="csrf_token"]').first().val() || $('meta[name="csrf-token"]').attr('content') || '';
    var $f = $('<form>', { method: 'POST', action: url, style: 'display:none' });
    if (token) $f.append($('<input>', { type: 'hidden', name: 'csrf_token', value: token }));
    $(document.body).append($f); $f.trigger('submit');
  }

  function bindCommonActions() {
    $(document).on('click', '.btn-delete', function (e) {
      e.preventDefault();
      var $form = $(this).closest('form'); if (!$form.length) return;
      Swal.fire({ icon: 'warning', title: 'تأكيد الحذف', text: 'سيتم حذف السجل نهائيًا', showCancelButton: true, confirmButtonText: 'احذف' })
      .then(function (r) { if (r.isConfirmed) $form.trigger('submit'); });
    });
    $('#printReceiptBtn, #previewReceiptBtn').on('click', function () { var url = $(this).data('url'); if (url) window.open(url, '_blank'); });
    $(document).on('click', '.btn-service-start', function (e) {
      e.preventDefault(); var url = $(this).data('url') || $(this).attr('href');
      Swal.fire({ icon: 'question', title: 'بدء الصيانة؟', showCancelButton: true, confirmButtonText: 'ابدأ' })
      .then(function (r) { if (r.isConfirmed) smartPost(url); });
    });
    $(document).on('click', '.btn-service-complete', function (e) {
      e.preventDefault(); var url = $(this).data('url') || $(this).attr('href');
      Swal.fire({ icon: 'question', title: 'إكمال الصيانة؟', text: 'سيتم احتساب المدة الفعلية وإقفال الاستهلاك.', showCancelButton: true, confirmButtonText: 'أكمل' })
      .then(function (r) { if (r.isConfirmed) smartPost(url); });
    });
  }

  function initSelect2Ajax($el, url) {
    $el.select2({
      theme: 'bootstrap4', width: '100%',
      ajax: {
        url: url, dataType: 'json', delay: 250,
        data: function (p) { return { q: p.term || '', limit: 20 }; },
        processResults: function (data) {
          var arr = Array.isArray(data) ? data : (data.results || data.data || []);
          return { results: arr.map(function (x) { if (typeof x === 'object') { var txt = x.text || x.name || String(x.id); return Object.assign({}, x, { id: x.id, text: txt }); } return { id: x, text: String(x) }; }) };
        }
      },
      minimumInputLength: 0, allowClear: true,
      placeholder: $el.attr('data-placeholder') || 'اختر...'
    });
 // اطلب النتائج الفورية بمجرد فتح القائمة حتى لو term فاضي
 $el.on('select2:open', function () {
   var $search = $('.select2-container--open .select2-search__field');
   if ($search.length && !$search.val()) { $search.trigger('input'); }
 });

  }

  function updateAvailHint($scope, available) {
    var $qtyCol = $scope.find('div:has(input[name="quantity"])').first();
    var $hint = $qtyCol.find('.avail-hint');
    if (!$hint.length) $hint = $('<div/>', { class: 'form-text text-muted mt-1 avail-hint' }).appendTo($qtyCol);
    $hint.text('المتاح في المخزن: ' + (available == null ? '-' : available));
  }

  function recalcPriceFromDiscount($scope) {
    var $price = $scope.find('input[name="unit_price"]');
    var $disc  = $scope.find('input[name="discount"]');
    var base   = toNum($price.data('basePrice'));
    var d      = toNum($disc.val());
    if (base > 0) { var p = base * (1 - (d / 100)); $price.val(round2(p)); }
  }

  function recalcDiscountFromPrice($scope) {
    var $price = $scope.find('input[name="unit_price"]');
    var $disc  = $scope.find('input[name="discount"]');
    var base   = toNum($price.data('basePrice'));
    var p      = toNum($price.val());
    if (base > 0) { var d = ((base - p) / base) * 100; $disc.val(round2(d)); }
  }

  function setQueryParam(url, key, val) {
    var u = new URL(url, window.location.origin);
    if (val == null || val === '') u.searchParams.delete(key); else u.searchParams.set(key, val);
    return u.pathname + (u.search ? u.search : '');
  }

  function buildByWarehouseUrl(tpl, wid) {
    if (!tpl) return '';
    if (/[\?&]wid=/.test(tpl)) return tpl.replace(/wid=\d+/i, 'wid=' + String(wid || 0));
    if (/\/(0|\d+)(?=\/products(?:\/)?$)/.test(tpl)) return tpl.replace(/\/(0|\d+)(?=\/products(?:\/)?$)/, '/' + String(wid || 0));
    return setQueryParam(tpl, 'wid', String(wid || 0));
  }

  function buildProductInfoUrl(tpl, pid, wid) {
    if (!tpl) return '';
    var url = tpl;
    if (/[\?&]pid=/.test(url)) url = url.replace(/pid=\d+/i, 'pid=' + String(pid));
    else if (/\/(0|\d+)(?=\/info(?:\/)?$)/.test(url)) url = url.replace(/\/(0|\d+)(?=\/info(?:\/)?$)/, '/' + String(pid));
    else url = setQueryParam(url, 'pid', String(pid));
    if (wid) url = /[\?&]warehouse_id=/.test(url) ? url.replace(/warehouse_id=\d+/i, 'warehouse_id=' + String(wid)) : setQueryParam(url, 'warehouse_id', String(wid));
    return url;
  }

  function fetchAndFillUnitPrice($scope) {
    var $part  = $scope.find('select[name="part_id"]');
    var $price = $scope.find('input[name="unit_price"]');
    var infoTpl = $part.attr('data-product-info');
    var pid = $part.val(); if (!infoTpl || !pid || !$price.length) return;
    var $wh = $scope.find('select[name="warehouse_id"]'); var wid = $wh.val();
    var url = buildProductInfoUrl(infoTpl, pid, wid);

    fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (js) {
        if (!js) return;
        if (js.available != null) updateAvailHint($scope, js.available);
        if (js.price != null && !isNaN(parseFloat(js.price))) {
          var base = toNum(js.price);
          $price.data('basePrice', base);
          $price.val(round2(base));
          var $disc = $scope.find('input[name="discount"]');
          if ($disc.length) $disc.val('0.00');
        }
      })
      .catch(function () {});
  }

  function bindWarehouseProductCascade($scope) {
    if ($scope.data('cascade-bound')) return;
    var $wh = $scope.find('select[name="warehouse_id"]');
    var $pr = $scope.find('select[name="part_id"]');
    var whEndpoint = $wh.attr('data-endpoint');
    var prEndpointTemplate = $pr.attr('data-endpoint-by-warehouse');

    if (whEndpoint && $wh.hasClass('select2')) initSelect2Ajax($wh, whEndpoint);

    function initProductsForWarehouse(wid) {
      if (!prEndpointTemplate) return;
      var url = buildByWarehouseUrl(prEndpointTemplate, wid);
      if ($pr.data('select2')) $pr.select2('destroy');
      $pr.val(null).trigger('change');
      initSelect2Ajax($pr, url);
    }

    if ($pr.hasClass('select2') && $wh.val()) initProductsForWarehouse($wh.val());

    $wh.on('change', function () {
      var wid = $(this).val();
      initProductsForWarehouse(wid);
      if ($pr.val()) fetchAndFillUnitPrice($scope);
    });

    $pr.on('select2:select change', function () { fetchAndFillUnitPrice($scope); });

    $scope.data('cascade-bound', true);
  }

  function bootSelect2Auto() {
    $('.select2').each(function () {
      var $el = $(this);
      if ($el.data('bound')) return;
      var ep = $el.attr('data-endpoint');
      if (ep) initSelect2Ajax($el, ep);
      $el.data('bound', true);
    });
  }

  function bindServicePartForm() {
    var $formPart = $('#form-add-part'); if (!$formPart.length) return;
    var $disc = $formPart.find('input[name="discount"]');
    if ($disc.length) { $disc.attr('min', '-100'); $disc.attr('max', '100'); }
    bindWarehouseProductCascade($formPart);
    fetchAndFillUnitPrice($formPart);
    $formPart.on('input change', 'input[name="discount"]', function () { recalcPriceFromDiscount($formPart); });
    $formPart.on('input change', 'input[name="unit_price"]', function () { recalcDiscountFromPrice($formPart); });
  }

  function bindDynamicRows() {
    $('#addPartBtn, #add-part').on('click', function () {
      var tpl =
        '<div class="row g-2 align-items-end mb-2 part-line">' +
          '<div class="col-md-3">' +
            '<label class="form-label d-block">المستودع</label>' +
            '<select class="form-select select2" name="warehouse_id" data-endpoint="/api/search_warehouses"></select>' +
          '</div>' +
          '<div class="col-md-3">' +
            '<label class="form-label d-block">القطعة</label>' +
            '<select class="form-select select2" name="part_id" data-endpoint-by-warehouse="/api/warehouses/0/products" data-product-info="/api/products/0/info"></select>' +
          '</div>' +
          '<div class="col-md-2"><label class="form-label">الكمية</label><input type="number" min="1" class="form-control" name="quantity" value="1"></div>' +
          '<div class="col-md-2"><label class="form-label">سعر الوحدة</label><input type="number" step="0.01" min="0" class="form-control" name="unit_price"></div>' +
          '<div class="col-auto"><label class="form-label d-block">&nbsp;</label><button type="button" class="btn btn-outline-danger remove-part">&times;</button></div>' +
        '</div>';
      $('#parts-list').append(tpl);
      var $row = $('#parts-list .part-line').last();
      $row.find('.select2').each(function () { var $el = $(this); if ($el.data('bound')) return; var ep = $el.attr('data-endpoint'); if (ep) initSelect2Ajax($el, ep); $el.data('bound', true); });
      var $d = $row.find('input[name="discount"]'); if ($d.length) { $d.attr('min','-100').attr('max','100'); }
      bindWarehouseProductCascade($row);
      $row.on('input change', 'input[name="discount"]', function () { recalcPriceFromDiscount($row); });
      $row.on('input change', 'input[name="unit_price"]', function () { recalcDiscountFromPrice($row); });
    });

    $(document).on('click', '.remove-part', function () { $(this).closest('.part-line').remove(); });

    $('#addTaskBtn, #add-task').on('click', function () {
      var tpl =
        '<div class="row g-2 align-items-end mb-2 task-line">' +
          '<div class="col-md-6"><input type="text" class="form-control" name="description" placeholder="الوصف"></div>' +
          '<div class="col-md-2"><input type="number" min="1" class="form-control" name="quantity" value="1"></div>' +
          '<div class="col-md-2"><input type="number" step="0.01" class="form-control" name="unit_price"></div>' +
          '<div class="col-auto"><button type="button" class="btn btn-outline-danger remove-task">&times;</button></div>' +
        '</div>';
      $('#tasks-list').append(tpl);
    });

    $(document).on('click', '.remove-task', function () { $(this).closest('.task-line').remove(); });
  }

  $(document).ready(function () {
    dtSafeInit();
    bindCommonActions();
    bootSelect2Auto();
    bindServicePartForm();
    bindDynamicRows();
  });
})();
