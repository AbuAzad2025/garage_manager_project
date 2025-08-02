/* ألوان الحالات */
.badge-pending { background-color: #6c757d; }
.badge-diagnosis { background-color: #17a2b8; }
.badge-in_progress { background-color: #0dcaf0; }
.badge-completed { background-color: #198754; }
.badge-cancelled { background-color: #dc3545; }
.badge-on_hold { background-color: #ffc107; }

/* تحسين جداول التفاصيل */
.table-sm th, .table-sm td {
    padding: 0.35rem;
}

/* تحسينات الطباعة للإيصال */
@media print {
    .btn, .breadcrumb, .page-header, .actions {
        display: none !important;
    }
    body {
        font-size: 14px;
        color: #000;
    }
}
