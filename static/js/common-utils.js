/**
 * ✅ دوال مشتركة للنظام بالكامل
 * تجنب التكرار - استخدم هذا الملف في جميع القوالب
 */

// ✅ Debounce - منع التنفيذ المتكرر
function debounce(fn, ms) {
    let timer;
    return function() {
        clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, arguments), ms);
    };
}

// ✅ تحويل النص لرقم (يدعم الأرقام العربية)
function toNumber(s) {
    s = String(s || '')
        .replace(/[٠-٩]/g, d => '٠١٢٣٤٥٦٧٨٩'.indexOf(d))
        .replace(/[٬،\s]/g, '')
        .replace(',', '.');
    const n = parseFloat(s);
    return isNaN(n) ? 0 : n;
}

// ✅ تنسيق المبلغ (2 decimal places)
function fmtAmount(v) { 
    const num = toNumber(v);
    return num.toLocaleString('en-US', { 
        minimumFractionDigits: 2, 
        maximumFractionDigits: 2 
    });
}

// ✅ تنسيق العملة
function formatCurrency(amount, currency = 'ILS') {
    const num = toNumber(amount);
    const formatted = num.toLocaleString('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
    return currency === 'ILS' ? formatted + ' ₪' : formatted + ' ' + currency;
}

// ✅ Badge للاتجاه
function badgeForDirection(dir) {
    const v = String(dir || '').toUpperCase();
    return (v === 'IN' || v === 'INCOMING') 
        ? '<span class="badge bg-success">وارد</span>' 
        : '<span class="badge bg-danger">صادر</span>';
}

// ✅ Badge للحالة
function badgeForStatus(st) {
    const statusMap = {
        'COMPLETED': {cls: 'bg-success', txt: 'مكتملة'},
        'PENDING': {cls: 'bg-warning text-dark', txt: 'قيد الانتظار'},
        'FAILED': {cls: 'bg-danger', txt: 'فاشلة'},
        'REFUNDED': {cls: 'bg-secondary', txt: 'مُرجعة'},
        'CANCELLED': {cls: 'bg-dark', txt: 'ملغية'}
    };
    const s = String(st || '');
    const status = statusMap[s] || {cls: 'bg-secondary', txt: s};
    return `<span class="badge ${status.cls}">${status.txt}</span>`;
}

// ✅ عرض رسالة تنبيه
function showAlert(type, message, duration = 5000) {
    const alertTypes = {
        'success': 'alert-success',
        'error': 'alert-danger',
        'danger': 'alert-danger',
        'warning': 'alert-warning',
        'info': 'alert-info'
    };
    
    const alertClass = alertTypes[type] || 'alert-info';
    const alertHtml = `
        <div class="alert ${alertClass} alert-dismissible fade show position-fixed" 
             style="top: 80px; left: 50%; transform: translateX(-50%); z-index: 9999; min-width: 300px; max-width: 600px;" 
             role="alert">
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `;
    
    const alertDiv = document.createElement('div');
    alertDiv.innerHTML = alertHtml;
    document.body.appendChild(alertDiv);
    
    if (duration > 0) {
        setTimeout(() => {
            alertDiv.querySelector('.alert')?.classList.remove('show');
            setTimeout(() => alertDiv.remove(), 150);
        }, duration);
    }
}

// ✅ تحميل البيانات مع Loading
function setLoading(selector, isLoading) {
    const el = typeof selector === 'string' ? document.querySelector(selector) : selector;
    if (!el) return;
    
    if (isLoading) {
        const colspan = el.tagName === 'TBODY' 
            ? el.closest('table')?.querySelectorAll('thead th').length || 5
            : 1;
        el.innerHTML = `<tr><td colspan="${colspan}" class="text-center text-muted py-4">
            <div class="spinner-border spinner-border-sm me-2"></div>جارِ التحميل…
        </td></tr>`;
    }
}

// ✅ تأكيد قبل الحذف
function confirmDelete(entityName, entityId) {
    return confirm(`هل أنت متأكد من حذف ${entityName} #${entityId}؟\n\nهذا الإجراء لا يمكن التراجع عنه!`);
}

// ✅ Export to CSV
function exportToCSV(data, filename) {
    const csv = data.map(row => 
        row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(',')
    ).join('\n');
    
    const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    const timestamp = new Date().toISOString().split('T')[0];
    
    a.href = url;
    a.download = `${filename}_${timestamp}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

// ✅ تحويل التاريخ للعرض
function formatDate(dateString) {
    if (!dateString) return '-';
    const date = new Date(dateString);
    if (isNaN(date)) return dateString;
    return date.toLocaleDateString('ar-SA', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit'
    });
}

// ✅ تحويل الوقت للعرض
function formatDateTime(dateString) {
    if (!dateString) return '-';
    const date = new Date(dateString);
    if (isNaN(date)) return dateString;
    return date.toLocaleString('ar-SA', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    });
}

// ✅ استخراج تسمية الجهة من كائن الدفعة
function deriveEntityLabel(p) {
    if (p.entity_display) return p.entity_display;
    
    const entityConfig = {
        customer_id: {icon: 'fas fa-user text-primary', label: 'عميل', badge: 'badge-primary'},
        supplier_id: {icon: 'fas fa-truck text-info', label: 'مورد', badge: 'badge-info'},
        partner_id: {icon: 'fas fa-handshake text-success', label: 'شريك', badge: 'badge-success'},
        sale_id: {icon: 'fas fa-shopping-cart text-warning', label: 'فاتورة مبيعات', badge: 'badge-warning'},
        service_id: {icon: 'fas fa-wrench text-danger', label: 'صيانة مركبة', badge: 'badge-danger'},
        expense_id: {icon: 'fas fa-receipt text-secondary', label: 'مصروف', badge: 'badge-secondary'},
        shipment_id: {icon: 'fas fa-shipping-fast text-primary', label: 'شحنة', badge: 'badge-primary'},
        preorder_id: {icon: 'fas fa-calendar-check text-info', label: 'طلب مسبق', badge: 'badge-info'},
        loan_settlement_id: {icon: 'fas fa-balance-scale text-warning', label: 'تسوية قرض', badge: 'badge-warning'},
        invoice_id: {icon: 'fas fa-file-invoice text-success', label: 'فاتورة', badge: 'badge-success'}
    };
    
    for (const [key, config] of Object.entries(entityConfig)) {
        if (p[key]) {
            const icon = `<i class="${config.icon}"></i>`;
            const label = `${config.label} #${p[key]}`;
            const badge = `<span class="badge ${config.badge}">${label}</span>`;
            const details = p.reference ? `<br><small class="text-muted">${p.reference}</small>` : '';
            return icon + ' ' + badge + details;
        }
    }
    
    return p.entity_type || '';
}

// ✅ تطبيع نوع الجهة
function normalizeEntity(val) {
    if (!val) return '';
    const enumMap = {
        customer: 'CUSTOMER', supplier: 'SUPPLIER', partner: 'PARTNER',
        sale: 'SALE', service: 'SERVICE', expense: 'EXPENSE',
        loan: 'LOAN', preorder: 'PREORDER', shipment: 'SHIPMENT'
    };
    const k = val.toString().toLowerCase();
    return enumMap[k] || val.toString().toUpperCase();
}

// ✅ تطبيع طريقة الدفع
function normalizeMethod(v) {
    v = String(v || '').trim();
    if (!v) return '';
    return v.replace(/\s+/g,'_').replace(/-/g,'_').toUpperCase();
}

// ✅ تطبيع الاتجاه
function normDir(v) {
    v = (v || '').toUpperCase();
    if (v === 'IN') return 'INCOMING';
    if (v === 'OUT') return 'OUTGOING';
    return v;
}

// ✅ التحقق من صحة التواريخ
function validDates(start, end) {
    if (!start || !end) return { start, end };
    const s = new Date(start), e = new Date(end);
    if (isNaN(s) || isNaN(e)) return { start, end };
    if (s.getTime() > e.getTime()) return { start: end, end: start };
    return { start, end };
}

