/**
 * Export Helpers - وظائف مساعدة للتصدير
 * ========================================
 */

/**
 * تصدير جدول HTML إلى ملف CSV
 * @param {string} filename - اسم الملف
 * @param {string} tableId - ID الجدول (افتراضي: report-table)
 */
function exportTableToCSV(filename = 'export.csv', tableId = 'report-table') {
    const table = document.getElementById(tableId) || document.querySelector('table');
    
    if (!table) {
        alert('لا يوجد جدول للتصدير');
        return;
    }
    
    const rows = table.querySelectorAll('tr');
    const csv = [];
    
    rows.forEach(row => {
        const cols = row.querySelectorAll('td, th');
        const rowData = [];
        
        cols.forEach(col => {
            let text = col.innerText || col.textContent || '';
            // تنظيف النص
            text = text.replace(/\s+/g, ' ').trim();
            // إضافة علامات اقتباس إذا كان النص يحتوي على فاصلة
            if (text.includes(',') || text.includes('"') || text.includes('\n')) {
                text = '"' + text.replace(/"/g, '""') + '"';
            }
            rowData.push(text);
        });
        
        csv.push(rowData.join(','));
    });
    
    // تحويل إلى blob وتحميل
    const csvContent = csv.join('\n');
    const BOM = '\uFEFF'; // UTF-8 BOM للعربي
    const blob = new Blob([BOM + csvContent], { type: 'text/csv;charset=utf-8;' });
    
    const link = document.createElement('a');
    if (link.download !== undefined) {
        const url = URL.createObjectURL(blob);
        link.setAttribute('href', url);
        link.setAttribute('download', filename);
        link.style.visibility = 'hidden';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        
        setTimeout(() => URL.revokeObjectURL(url), 100);
        if (typeof showToast === 'function') {
            showToast('✅ تم تصدير الملف بنجاح', 'success');
        }
    } else {
        alert('المتصفح لا يدعم التحميل التلقائي');
    }
}

function exportJSONToCSV(data, filename = 'export.csv', columns = null) {
    if (!data || data.length === 0) {
        alert('لا توجد بيانات للتصدير');
        return;
    }
    
    // تحديد الأعمدة
    const headers = columns || Object.keys(data[0]);
    
    // إنشاء CSV
    const csv = [];
    
    // الرأس
    csv.push(headers.join(','));
    
    // البيانات
    data.forEach(row => {
        const values = headers.map(header => {
            let value = row[header] || '';
            // تحويل إلى نص
            value = String(value);
            // إضافة علامات اقتباس
            if (value.includes(',') || value.includes('"')) {
                value = '"' + value.replace(/"/g, '""') + '"';
            }
            return value;
        });
        csv.push(values.join(','));
    });
    
    // تحميل
    const csvContent = csv.join('\n');
    const BOM = '\uFEFF';
    const blob = new Blob([BOM + csvContent], { type: 'text/csv;charset=utf-8;' });
    
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    link.setAttribute('href', url);
    link.setAttribute('download', filename);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    
    setTimeout(() => URL.revokeObjectURL(url), 100);
}



