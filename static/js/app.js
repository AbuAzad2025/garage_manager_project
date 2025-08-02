$(document).ready(function() {
  // 1. DataTables on tables with class 'datatable'
  $('.datatable').each(function() {
    $(this).DataTable({
      dom: 'Bfrtip',
      buttons: [
        { extend: 'excelHtml5', text: '<i class="fas fa-file-excel"></i> Excel' },
        { extend: 'print', text: '<i class="fas fa-print"></i> طباعة' }
      ],
      pageLength: 10,
      responsive: true,
      language: { url: '/static/datatables/Arabic.json' }
    });
  });

  // 2. Bootstrap Datepicker on inputs with class 'datepicker'
  $('.datepicker').each(function() {
    $(this).datepicker({
      format: 'yyyy-mm-dd',
      autoclose: true,
      language: 'ar'
    });
  });

  // 3. Select2 on selects with class 'select2'
  $('.select2').select2({
    width: '100%',
    placeholder: 'اختر...',
    language: 'ar'
  });

  // 4. Confirmation dialogs for forms with data-confirm attribute
  $('form[data-confirm]').on('submit', function(e) {
    var msg = $(this).data('confirm');
    if (!confirm(msg)) {
      e.preventDefault();
    }
  });

  // 5. Button loading state for buttons with class 'btn-loading'
  $('.btn-loading').on('click', function() {
    var $btn = $(this);
    var originalText = $btn.html();
    $btn.prop('disabled', true)
        .html('<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> جاري المعالجة...');
    // Optional: if form submission fails, you could restore text
    // setTimeout(function() { $btn.prop('disabled', false).html(originalText); }, 10000);
  });
});
