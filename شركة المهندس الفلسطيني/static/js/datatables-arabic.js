// Arabic DataTables Translation (Inline)
(function() {
    if (window.jQuery && $.fn && $.fn.dataTable) {
        $.extend(true, $.fn.dataTable.defaults, {
            language: {
                "emptyTable": "لا توجد بيانات متاحة",
                "info": "عرض _START_ إلى _END_ من أصل _TOTAL_ سجل",
                "infoEmpty": "عرض 0 إلى 0 من أصل 0 سجل",
                "infoFiltered": "(مفلتر من إجمالي _MAX_ سجل)",
                "lengthMenu": "عرض _MENU_ سجل",
                "loadingRecords": "جاري التحميل...",
                "processing": "جاري المعالجة...",
                "search": "بحث:",
                "zeroRecords": "لم يتم العثور على نتائج",
                "paginate": {
                    "first": "الأول",
                    "last": "الأخير",
                    "next": "التالي",
                    "previous": "السابق"
                },
                "aria": {
                    "sortAscending": ": ترتيب تصاعدي",
                    "sortDescending": ": ترتيب تنازلي"
                },
                "thousands": ",",
                "decimal": ".",
                "searchPlaceholder": "ابحث هنا..."
            }
        });
    }
})();
