$(function () {
  // DataTables
  $('#transfersTable').DataTable({
    language: { url: "//cdn.datatables.net/plug-ins/1.10.25/i18n/Arabic.json" },
    responsive: true,
    autoWidth: false
  });

  // Select2
  $('.select2').select2({ theme: 'bootstrap4', width: '100%' });

  // Datepicker
  $('.datepicker').datepicker({
    format: 'yyyy-mm-dd',
    autoclose: true,
    todayHighlight: true
  });
});
