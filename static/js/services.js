$(document).ready(function () {
    // ✅ تفعيل DataTable
    $('#servicesTable').DataTable({
        language: { url: '//cdn.datatables.net/plug-ins/1.13.4/i18n/ar.json' }
    });

    // ✅ تحديد الكل
    $('#selectAll').on('click', function () {
        $('.row-select').prop('checked', this.checked);
    });

    // ✅ حذف جماعي
    $('#bulkDelete').on('click', function () {
        let ids = $('.row-select:checked').map(function () { return this.value; }).get();
        if (!ids.length) return Swal.fire('تنبيه', 'لم يتم تحديد أي طلب', 'warning');
        Swal.fire('جاري الحذف...', '', 'info');
        // أرسل AJAX إذا كان هناك راوت
    });

    // ✅ تصدير CSV
    $('#exportCsv').on('click', () => {
        window.location.href = '/service/export/csv';
    });
});
