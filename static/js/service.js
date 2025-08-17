// File: static/js/service.js
$(document).ready(function () {
  // ===================== DataTable وعمليات عامة =====================
  const $table = $('#servicesTable');
  if ($table.length) {
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
      const ids = $('.row-select:checked').map(function () { return this.value; }).get();
      if (!ids.length) return Swal.fire('تنبيه', 'لم يتم تحديد أي طلب', 'warning');
      Swal.fire({
        icon: 'warning', title: 'تأكيد الحذف الجماعي',
        text: `سيتم حذف ${ids.length} طلب (غير قابل للتراجع)`,
        showCancelButton: true, confirmButtonText: 'نعم، احذف'
      }).then((res) => {
        if (!res.isConfirmed) return;
        Swal.fire('تم', 'هذه واجهة فقط، أضف راوت الحذف الجماعي لاحقًا.', 'success');
      });
    });
    $('#exportCsv').on('click', () => { window.location.href = '/service/export/csv'; });
    $('#exportPdf').on('click', () => { window.location.href = '/service/export/pdf'; });
  }

  $(document).on('click', '.btn-delete', function (e) {
    e.preventDefault();
    const $form = $(this).closest('form');
    if (!$form.length) return;
    Swal.fire({
      icon: 'warning', title: 'تأكيد الحذف', text: 'سيتم حذف السجل نهائيًا',
      showCancelButton: true, confirmButtonText: 'احذف'
    }).then((r) => { if (r.isConfirmed) $form.trigger('submit'); });
  });

  $('#printReceiptBtn, #previewReceiptBtn').on('click', function () {
    const url = $(this).data('url');
    if (url) window.open(url, '_blank');
  });

  // ===================== Helpers: Select2 AJAX =====================
  function initSelect2Ajax($el, url) {
    $el.select2({
      width: '100%',
      ajax: {
        url: url,
        dataType: 'json',
        delay: 250,
        data: function (params) { return { q: params.term || '', limit: 20 }; },
        processResults: function (data) {
          // يدعم Array مباشرة أو {results:[...]}
          const arr = Array.isArray(data) ? data : (data.results || []);
          return { results: arr };
        }
      },
      minimumInputLength: 0,
      allowClear: true,
      placeholder: 'اختر...'
    });
  }

  // ===================== جلب السعر والمتاح وتعبئتهما =====================
  function fetchAndFillUnitPrice($scope) {
    const $part   = $scope.find('select[name="part_id"]');
    const $price  = $scope.find('input[name="unit_price"]');
    const infoTpl = $part.attr('data-product-info'); // مثل: /api/products/0/info
    const pid     = $part.val();
    if (!infoTpl || !pid || !$price.length) return;

    // تمرير warehouse_id اختياريًا لعرض المتاح من هذا المخزن
    const $wh = $scope.find('select[name="warehouse_id"]');
    const wid = $wh.val() ? `?warehouse_id=${encodeURIComponent($wh.val())}` : '';
    const url = infoTpl.replace(/0$/, String(pid)) + wid;

    fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(r => r.ok ? r.json() : null)
      .then(js => {
        if (!js) return;

        // تعبئة سعر الوحدة (مع إبقاءه قابل للتعديل)
        if (js.price != null && !isNaN(parseFloat(js.price))) {
          const prev = parseFloat($price.val());
          // إن كان الحقل فارغًا أو 0، عبّئه من السعر الافتراضي
          if (isNaN(prev) || prev === 0) {
            $price.val(parseFloat(js.price).toFixed(2));
          }
        }

        // إظهار المتاح بجانب حقل الكمية
        if (js.available != null) {
          const $qtyCol = $scope.find('div.col-md-2:has(input[name="quantity"])').first();
          let $hint = $qtyCol.find('.avail-hint');
          if (!$hint.length) {
            $hint = $('<div/>', { class: 'form-text text-muted mt-1 avail-hint' }).appendTo($qtyCol);
          }
          $hint.text(`المتاح في المخزن: ${js.available}`);
        }
      })
      .catch(() => {});
  }

  // ===================== ربط المستودع بالمنتجات + تعبئة السعر =====================
  function bindWarehouseProductCascade($scope) {
    const $wh = $scope.find('select[name="warehouse_id"]');
    const $pr = $scope.find('select[name="part_id"]');

    const whEndpoint = $wh.attr('data-endpoint'); // /api/search_warehouses
    const prEndpointTemplate = $pr.attr('data-endpoint-by-warehouse'); // /api/warehouses/0/products

    // تفعيل Select2 للمستودعات
    if (whEndpoint && $wh.hasClass('select2')) {
      initSelect2Ajax($wh, whEndpoint);
    }

    // تهيئة المنتجات بحسب المستودع
    function initProductsForWarehouse(wid) {
      if (!prEndpointTemplate) return;
      const url = prEndpointTemplate.replace(/0$/, String(wid));
      // إعادة تهيئة Select2 للقطع
      $pr.val(null).trigger('change');
      if ($pr.data('select2')) $pr.select2('destroy');
      initSelect2Ajax($pr, url);
    }

    // إن كان المستودع محددًا مسبقًا (مثلاً عند إعادة تحميل الصفحة)
    if ($pr.hasClass('select2') && $wh.val()) {
      initProductsForWarehouse($wh.val());
    }

    // عند تغيير المستودع: أعد تهيئة قائمة القطع
    $wh.on('change', function () {
      const wid = $(this).val();
      if (wid) initProductsForWarehouse(wid);
    });

    // عند اختيار/تغيير القطعة: اجلب السعر واملأه (ويبقى قابل للتعديل)
    $pr.on('select2:select change', function(){
      fetchAndFillUnitPrice($scope);
    });
  }

  // ===================== تفعيل Select2 عام للعناصر ذات data-endpoint =====================
  if ($('.select2').length) {
    $('.select2').each(function(){
      const $el = $(this);
      const ep = $el.attr('data-endpoint');
      if (ep) initSelect2Ajax($el, ep);
    });
  }

  // ===================== نموذج إضافة قطعة للصيانة =====================
  const $formPart = $('#form-add-part');
  if ($formPart.length) {
    bindWarehouseProductCascade($formPart);
    // إن كانت هناك قيمة محددة مسبقًا، حاول تعبئة السعر مباشرة
    fetchAndFillUnitPrice($formPart);
  }

  // ===================== صفوف ديناميكية (لو عندك أزرار إضافة سطور متعددة اختيارياً) =====================
  $('#addPartBtn, #add-part').on('click', function () {
    const tpl = `
      <div class="row g-2 align-items-end mb-2 part-line">
        <div class="col-md-3">
          <label class="form-label d-block">المستودع</label>
          <select class="form-select select2" name="warehouse_id" data-endpoint="/api/search_warehouses"></select>
        </div>
        <div class="col-md-3">
          <label class="form-label d-block">القطعة</label>
          <select class="form-select select2" name="part_id"
                  data-endpoint-by-warehouse="/api/warehouses/0/products"
                  data-product-info="/api/products/0/info"></select>
        </div>
        <div class="col-md-2">
          <label class="form-label">الكمية</label>
          <input type="number" min="1" class="form-control" name="quantity" value="1">
        </div>
        <div class="col-md-2">
          <label class="form-label">سعر الوحدة</label>
          <input type="number" step="0.01" min="0" class="form-control" name="unit_price">
        </div>
        <div class="col-auto">
          <label class="form-label d-block">&nbsp;</label>
          <button type="button" class="btn btn-outline-danger remove-part">&times;</button>
        </div>
      </div>`;
    $('#parts-list').append(tpl);
    const $row = $('#parts-list .part-line').last();

    // تفعيل select2 العام
    $row.find('.select2').each(function(){
      const $el = $(this);
      const ep = $el.attr('data-endpoint');
      if (ep) initSelect2Ajax($el, ep);
    });

    // ربط كاسكاد المخزن/القطعة + تعبئة السعر عند الاختيار
    bindWarehouseProductCascade($row);
  });

  $(document).on('click', '.remove-part', function () {
    $(this).closest('.part-line').remove();
  });

  // ===================== المهام =====================
  $('#addTaskBtn, #add-task').on('click', function () {
    const tpl = `
      <div class="row g-2 align-items-end mb-2 task-line">
        <div class="col-md-6"><input type="text" class="form-control" name="description" placeholder="الوصف"></div>
        <div class="col-md-2"><input type="number" min="1" class="form-control" name="quantity" value="1"></div>
        <div class="col-md-2"><input type="number" step="0.01" class="form-control" name="unit_price"></div>
        <div class="col-md-2"><input type="number" step="0.01" class="form-control" name="discount" placeholder="خصم %"></div>
        <div class="col-md-2"><input type="number" step="0.01" class="form-control" name="tax_rate" placeholder="ضريبة %"></div>
        <div class="col-auto"><button type="button" class="btn btn-outline-danger remove-task">&times;</button></div>
      </div>`;
    $('#tasks-list').append(tpl);
  });

  $(document).on('click', '.remove-task', function () {
    $(this).closest('.task-line').remove();
  });
});
