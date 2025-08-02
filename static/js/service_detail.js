$(document).ready(function () {
    // ✅ تأكيد حذف
    $('.btn-delete').on('click', function (e) {
        if (!confirm('تأكيد حذف هذا العنصر؟')) e.preventDefault();
    });

    // ✅ طباعة الإيصال
    $('#printReceiptBtn').on('click', function () {
        window.open($(this).data('url'), '_blank');
    });

    // ✅ معاينة سند القبض (لو أضفت الزر)
    $('#previewReceiptBtn').on('click', function () {
        window.open($(this).data('url'), '_blank');
    });
});
