// File: static/js/service.js
(function () {
  'use strict';

  function dtSafeInit() {
    var $table = $('#servicesTable');
    if (!$table.length) return;
    try {
      $table.DataTable({
        language: { url: '//cdn.datatables.net/plug-ins/1.13.4/i18n/ar.json' },
        pageLength: 25,
        order: []
      });
    } catch (e) {}
    $('#selectAll').on('change', function () {
      $('.row-select').prop('checked', this.checked);
    });
    $('#bulkDelete').on('click', function () {
      var ids = $('.row-select:checked').map(function () { return this.value; }).get();
      if (!ids.length) return Swal.fire('تنبيه', 'لم يتم تحديد أي طلب', 'warning');
      Swal.fire({
        icon: 'warning', title: 'تأكيد الحذف الجماعي',
        text: 'سيتم حذف ' + ids.length + ' طلب (غير قابل للتراجع)',
        showCancelButton: true, confirmButtonText: 'نعم، احذف'
      }).then(function (res) {
        if (!res.isConfirmed) return;
        Swal.fire('تم', 'هذه واجهة فقط، أضف راوت الحذف الجماعي لاحقًا.', 'success');
      });
    });
    $('#exportCsv').on('click', function () { window.location.assign('/service/export/csv'); });
    $('#exportPdf').on('click', function () { window.location.assign('/service/export/pdf'); });
  }

  function smartPost(url) {
    if (!url) return;
    var token = $('input[name="csrf_token"]').first().val() || $('meta[name="csrf-token"]').attr('content') || '';
    var $f = $('<form>', { method: 'POST', action: url, style: 'display:none' });
    if (token) $f.append($('<input>', { type: 'hidden', name: 'csrf_token', value: token }));
    $(document.body).append($f);
    $f.trigger('submit');
  }

  function bindCommonActions() {
    $(document).on('click', '.btn-delete', function (e) {
      e.preventDefault();
      var $form = $(this).closest('form');
      if (!$form.length) return;
      Swal.fire({
        icon: 'warning', title: 'تأكيد الحذف', text: 'سيتم حذف السجل نهائيًا',
        showCancelButton: true, confirmButtonText: 'احذف'
      }).then(function (r) { if (r.isConfirmed) $form.trigger('submit'); });
    });

    $('#printReceiptBtn, #previewReceiptBtn').on('click', function () {
      var url = $(this).data('url');
      if (url) window.open(url, '_blank');
    });

    $(document).on('click', '.btn-service-start', function (e) {
      e.preventDefault();
      var url = $(this).data('url') || $(this).attr('href');
      Swal.fire({
        icon: 'question', title: 'بدء الصيانة؟',
        showCancelButton: true, confirmButtonText: 'ابدأ'
      }).then(function (r) { if (r.isConfirmed) smartPost(url); });
    });

    $(document).on('click', '.btn-service-complete', function (e) {
      e.preventDefault();
      var url = $(this).data('url') || $(this).attr('href');
      Swal.fire({
        icon: 'question', title: 'إكمال الصيانة؟',
        text: 'سيتم احتساب المدة الفعلية وإقفال الاستهلاك.',
        showCancelButton: true, confirmButtonText: 'أكمل'
      }).then(function (r) { if (r.isConfirmed) smartPost(url); });
    });
  }

  function initSelect2Ajax($el, url) {
    $el.select2({
      width: '100%',
      ajax: {
        url: url,
        dataType: 'json',
        delay: 250,
        data: function (params) { return { q: params.term || '', limit: 20 }; },
        processResults: function (data) {
          var arr = Array.isArray(data) ? data : (data.results || data.data || []);
          return { results: arr.map(function (x) {
            return typeof x === 'object' ? x : { id: x, text: String(x) };
          }) };
        }
      },
      minimumInputLength: 0,
      allowClear: true,
      placeholder: 'اختر...'
    });
  }

  function fetchAndFillUnitPrice($scope) {
    var $part   = $scope.find('select[name="part_id"]');
    var $price  = $scope.find('input[name="unit_price"]');
    var infoTpl = $part.attr('data-product-info');
    var pid     = $part.val();
    if (!infoTpl || !pid || !$price.length) return;

    var $wh = $scope.find('select[name="warehouse_id"]');
    var wid = $wh.val() ? ('?warehouse_id=' + encodeURIComponent($wh.val())) : '';
    var url = infoTpl.replace(/0$/, String(pid)) + wid;

    fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (js) {
        if (!js) return;
        if (js.price != null && !isNaN(parseFloat(js.price))) {
          var prev = parseFloat($price.val());
          if (isNaN(prev) || prev === 0) $price.val(parseFloat(js.price).toFixed(2));
        }
        if (js.available != null) {
          var $qtyCol = $scope.find('div:has(input[name="quantity"])').first();
          var $hint = $qtyCol.find('.avail-hint');
          if (!$hint.length) $hint = $('<div/>', { class: 'form-text text-muted mt-1 avail-hint' }).appendTo($qtyCol);
          $hint.text('المتاح في المخزن: ' + js.available);
        }
      })
      .catch(function () {});
  }

  function bindWarehouseProductCascade($scope) {
    var $wh = $scope.find('select[name="warehouse_id"]');
    var $pr = $scope.find('select[name="part_id"]');

    var whEndpoint = $wh.attr('data-endpoint');
    var prEndpointTemplate = $pr.attr('data-endpoint-by-warehouse');

    if (whEndpoint && $wh.hasClass('select2')) initSelect2Ajax($wh, whEndpoint);

    function initProductsForWarehouse(wid) {
      if (!prEndpointTemplate) return;
      var url = prEndpointTemplate.replace(/0$/, String(wid));
      if ($pr.data('select2')) $pr.select2('destroy');
      $pr.val(null).trigger('change');
      initSelect2Ajax($pr, url);
    }

    if ($pr.hasClass('select2') && $wh.val()) initProductsForWarehouse($wh.val());

    $wh.on('change', function () {
      var wid = $(this).val();
      if (wid) {
        initProductsForWarehouse(wid);
        if ($pr.val()) fetchAndFillUnitPrice($scope);
      }
    });

    $pr.on('select2:select change', function () { fetchAndFillUnitPrice($scope); });
  }

  function bootSelect2Auto() {
    $('.select2').each(function () {
      var $el = $(this);
      var ep = $el.attr('data-endpoint');
      if (ep) initSelect2Ajax($el, ep);
    });
  }

  function bindServicePartForm() {
    var $formPart = $('#form-add-part');
    if (!$formPart.length) return;
    bindWarehouseProductCascade($formPart);
    fetchAndFillUnitPrice($formPart);
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
          '<div class="col-md-2">' +
            '<label class="form-label">الكمية</label>' +
            '<input type="number" min="1" class="form-control" name="quantity" value="1">' +
          '</div>' +
          '<div class="col-md-2">' +
            '<label class="form-label">سعر الوحدة</label>' +
            '<input type="number" step="0.01" min="0" class="form-control" name="unit_price">' +
          '</div>' +
          '<div class="col-auto">' +
            '<label class="form-label d-block">&nbsp;</label>' +
            '<button type="button" class="btn btn-outline-danger remove-part">&times;</button>' +
          '</div>' +
        '</div>';
      $('#parts-list').append(tpl);
      var $row = $('#parts-list .part-line').last();
      $row.find('.select2').each(function () {
        var $el = $(this);
        var ep = $el.attr('data-endpoint');
        if (ep) initSelect2Ajax($el, ep);
      });
      bindWarehouseProductCascade($row);
    });

    $(document).on('click', '.remove-part', function () {
      $(this).closest('.part-line').remove();
    });

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

    $(document).on('click', '.remove-task', function () {
      $(this).closest('.task-line').remove();
    });
  }

  $(document).ready(function () {
    dtSafeInit();
    bindCommonActions();
    bootSelect2Auto();
    bindServicePartForm();
    bindDynamicRows();
  });
})();
