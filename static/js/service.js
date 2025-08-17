/* وحدة الصيانة — سكربت موحد */
$(document).ready(function () {
  // ========== قائمة الطلبات ==========
  const $table = $('#servicesTable');
  if ($table.length) {
    try {
      $table.DataTable({
        language: { url: '//cdn.datatables.net/plug-ins/1.13.4/i18n/ar.json' },
        pageLength: 25,
        order: []
      });
    } catch (e) { /* DataTables غير متوفر */ }

    // تحديد/إلغاء تحديد الكل
    $('#selectAll').on('change', function () {
      $('.row-select').prop('checked', this.checked);
    });

    // حذف جماعي (placeholder: أضف راوت عندك إن رغبت)
    $('#bulkDelete').on('click', function () {
      const ids = $('.row-select:checked').map(function () { return this.value; }).get();
      if (!ids.length) return Swal.fire('تنبيه', 'لم يتم تحديد أي طلب', 'warning');
      Swal.fire({
        icon: 'warning', title: 'تأكيد الحذف الجماعي', text: `سيتم حذف ${ids.length} طلب (غير قابل للتراجع)`,
        showCancelButton: true, confirmButtonText: 'نعم، احذف'
      }).then((res) => {
        if (!res.isConfirmed) return;
        // TODO: نفّذ طلب AJAX لراوت الحذف الجماعي إذا أضفته لاحقًا
        Swal.fire('تم', 'هذه واجهة فقط، أضف راوت الحذف الجماعي لاحقًا.', 'success');
      });
    });

    // تصدير CSV/PDF (روابط افتراضية — حدّدها إن وجدت)
    $('#exportCsv').on('click', () => { window.location.href = '/service/export/csv'; });
    $('#exportPdf').on('click', () => { window.location.href = '/service/export/pdf'; });
  }

  // تأكيد حذف مفرد (من صفحات القائمة/التفاصيل)
  $(document).on('click', '.btn-delete', function (e) {
    e.preventDefault();
    const $form = $(this).closest('form');
    if (!$form.length) return;
    Swal.fire({
      icon: 'warning', title: 'تأكيد الحذف', text: 'سيتم حذف السجل نهائيًا',
      showCancelButton: true, confirmButtonText: 'احذف'
    }).then((r) => { if (r.isConfirmed) $form.trigger('submit'); });
  });

  // ========== أزرار الطباعة/المعاينة (صفحة التفاصيل إن وجدت) ==========
  $('#printReceiptBtn, #previewReceiptBtn').on('click', function () {
    const url = $(this).data('url');
    if (url) window.open(url, '_blank');
  });

  // ========== صفحة إنشاء/تعديل: سطور ديناميكية ==========
  // سطر قطعة
  $('#addPartBtn, #add-part').on('click', function () {
    const tpl = `
      <div class="row g-2 align-items-end mb-2 part-line">
        <div class="col-md-4"><select class="form-select" name="part_id"></select></div>
        <div class="col-md-3"><select class="form-select" name="warehouse_id"></select></div>
        <div class="col-md-2"><input type="number" min="1" class="form-control" name="quantity"></div>
        <div class="col-md-2"><input type="number" step="0.01" class="form-control" name="unit_price"></div>
        <div class="col-auto"><button type="button" class="btn btn-outline-danger remove-part">&times;</button></div>
      </div>`;
    $('#parts-list').append(tpl);
  });
  $(document).on('click', '.remove-part', function () {
    $(this).closest('.part-line').remove();
  });

  // سطر مهمة
  $('#addTaskBtn, #add-task').on('click', function () {
    const tpl = `
      <div class="row g-2 align-items-end mb-2 task-line">
        <div class="col-md-6"><i
