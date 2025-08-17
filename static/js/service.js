$(document).ready(function () {
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

  function initSelect2Ajax($el, url) {
    $el.select2({
      width: '100%',
      ajax: {
        url: url,
        dataType: 'json',
        delay: 250,
        data: function (params) { return { q: params.term || '', limit: 20 }; },
        processResults: function (data) {
          return { results: data };
        }
      },
      minimumInputLength: 0
    });
  }

  function bindWarehouseProductCascade($scope) {
    const $wh = $scope.find('select[name="warehouse_id"]');
    const $pr = $scope.find('select[name="part_id"]');
    const whEndpoint = $wh.attr('data-endpoint');
    const prEndpointTemplate = $pr.attr('data-endpoint-by-warehouse');
    if (whEndpoint && $wh.hasClass('select2')) {
      initSelect2Ajax($wh, whEndpoint);
    }
    function initProductsForWarehouse(wid) {
      if (!prEndpointTemplate) return;
      const url = prEndpointTemplate.replace(/0$/, String(wid));
      $pr.val(null).trigger('change');
      $pr.select2('destroy');
      initSelect2Ajax($pr, url);
    }
    if ($pr.hasClass('select2') && $wh.val()) {
      initProductsForWarehouse($wh.val());
    }
    $wh.on('change', function () {
      const wid = $(this).val();
      if (wid) initProductsForWarehouse(wid);
    });
  }

  if ($('.select2').length) {
    $('.select2').each(function(){
      const $el = $(this);
      const ep = $el.attr('data-endpoint');
      if (ep) initSelect2Ajax($el, ep);
    });
  }

  const $formPart = $('#form-add-part');
  if ($formPart.length) {
    bindWarehouseProductCascade($formPart);
  }

  $('#addPartBtn, #add-part').on('click', function () {
    const tpl = `
      <div class="row g-2 align-items-end mb-2 part-line">
        <div class="col-md-4"><select class="form-select select2" name="part_id" data-endpoint-by-warehouse=""></select></div>
        <div class="col-md-3"><select class="form-select select2" name="warehouse_id" data-endpoint=""></select></div>
        <div class="col-md-2"><input type="number" min="1" class="form-control" name="quantity" value="1"></div>
        <div class="col-md-2"><input type="number" step="0.01" class="form-control" name="unit_price"></div>
        <div class="col-auto"><button type="button" class="btn btn-outline-danger remove-part">&times;</button></div>
      </div>`;
    $('#parts-list').append(tpl);
    const $row = $('#parts-list .part-line').last();
    $row.find('.select2').each(function(){
      const $el = $(this);
      const ep = $el.attr('data-endpoint');
      if (ep) initSelect2Ajax($el, ep);
    });
    bindWarehouseProductCascade($row);
  });

  $(document).on('click', '.remove-part', function () {
    $(this).closest('.part-line').remove();
  });

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
