function initPrint() {
    document.querySelectorAll('.btn-print').forEach(function(btn) {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            printReport(this.getAttribute('data-target') || 'body');
        });
    });
}

function printReport(targetSelector = 'body') {
    const printContent = document.querySelector(targetSelector);
    
    if (!printContent) {
        console.error('Print target not found:', targetSelector);
        return;
    }

    const originalContents = document.body.innerHTML;
    const printableContent = printContent.innerHTML;

    const printHeader = generatePrintHeader();
    const printInfo = generatePrintInfo();
    const printFooter = generatePrintFooter();

    const fullContent = `
        <div class="print-container">
            ${printHeader}
            ${printInfo}
            ${printableContent}
            ${printFooter}
        </div>
    `;

    document.body.innerHTML = fullContent;
    
    window.print();
    
    document.body.innerHTML = originalContents;
    
    initPrint();
    
    location.reload();
}

function generatePrintHeader() {
    const title = document.title || 'تقرير';
    const currentPage = document.querySelector('h1')?.textContent || 'تقرير النظام';
    
    return `
        <div class="print-header">
            <img src="/static/img/azad_logo.png" alt="Logo" class="company-logo" style="max-height: 60px;">
            <h1>AZAD Garage Manager</h1>
            <h2>${currentPage}</h2>
            <div class="subtitle">المهندس الفلسطيني للمعدات الثقيلة</div>
        </div>
    `;
}

function generatePrintInfo() {
    const now = new Date();
    const dateStr = now.toLocaleDateString('ar-EG', { 
        year: 'numeric', 
        month: 'long', 
        day: 'numeric' 
    });
    const timeStr = now.toLocaleTimeString('ar-EG');
    
    const currentUser = document.querySelector('[data-username]')?.getAttribute('data-username') || 'غير معروف';
    
    return `
        <div class="print-info">
            <div class="print-info-section">
                <div class="print-info-row">
                    <span class="print-info-label">📅 التاريخ:</span>
                    <span>${dateStr}</span>
                </div>
                <div class="print-info-row">
                    <span class="print-info-label">⏰ الوقت:</span>
                    <span>${timeStr}</span>
                </div>
            </div>
            <div class="print-info-section">
                <div class="print-info-row">
                    <span class="print-info-label">👤 المستخدم:</span>
                    <span>${currentUser}</span>
                </div>
                <div class="print-info-row">
                    <span class="print-info-label">📄 رقم التقرير:</span>
                    <span>RPT-${Date.now()}</span>
                </div>
            </div>
        </div>
    `;
}

function generatePrintFooter() {
    const now = new Date();
    const dateStr = now.toLocaleDateString('ar-EG');
    const timeStr = now.toLocaleTimeString('ar-EG');
    
    return `
        <div class="print-footer">
            <p>
                AZAD Garage Manager © 2025 | 
                تاريخ الطباعة: ${dateStr} ${timeStr} |
                رام الله - فلسطين
            </p>
        </div>
    `;
}

function printTable(tableId) {
    const table = document.getElementById(tableId);
    
    if (!table) {
        console.error('Table not found:', tableId);
        return;
    }

    const clone = table.cloneNode(true);
    
    clone.querySelectorAll('.no-print, .action-column, .btn').forEach(el => el.remove());
    
    const printWindow = window.open('', '_blank');
    
    printWindow.document.write(`
        <!DOCTYPE html>
        <html dir="rtl" lang="ar">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>${document.title}</title>
            <link rel="stylesheet" href="/static/css/print.css">
            <link rel="stylesheet" href="/static/adminlte/dist/css/adminlte.min.css">
            <style>
                body {
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    padding: 20px;
                    direction: rtl;
                }
                table {
                    width: 100%;
                    border-collapse: collapse;
                    margin: 20px 0;
                }
                th, td {
                    border: 1px solid #000;
                    padding: 8px;
                    text-align: right;
                }
                th {
                    background: #e9ecef;
                    font-weight: bold;
                }
            </style>
        </head>
        <body>
            ${generatePrintHeader()}
            ${generatePrintInfo()}
            ${clone.outerHTML}
            ${generatePrintFooter()}
        </body>
        </html>
    `);
    
    printWindow.document.close();
    
    printWindow.onload = function() {
        printWindow.print();
        printWindow.close();
    };
}

function exportToCSV(tableId, filename = 'report.csv') {
    const table = document.getElementById(tableId);
    
    if (!table) {
        console.error('Table not found:', tableId);
        return;
    }

    const rows = Array.from(table.querySelectorAll('tr'));
    const csvContent = rows.map(row => {
        const cells = Array.from(row.querySelectorAll('th, td'));
        return cells
            .filter(cell => !cell.classList.contains('no-print') && !cell.classList.contains('action-column'))
            .map(cell => {
                let text = cell.textContent.trim();
                text = text.replace(/"/g, '""');
                return `"${text}"`;
            })
            .join(',');
    }).join('\n');

    const BOM = '\uFEFF';
    const blob = new Blob([BOM + csvContent], { type: 'text/csv;charset=utf-8;' });
    
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    link.click();
    
    URL.revokeObjectURL(link.href);
}

function exportToExcel(tableId, filename = 'report.xlsx') {
    const table = document.getElementById(tableId);
    
    if (!table) {
        console.error('Table not found:', tableId);
        return;
    }

    const clone = table.cloneNode(true);
    clone.querySelectorAll('.no-print, .action-column, .btn').forEach(el => el.remove());

    const html = clone.outerHTML;
    const url = 'data:application/vnd.ms-excel,' + encodeURIComponent(html);
    
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.click();
}

function printWithSummary(targetSelector, summaryData) {
    const printContent = document.querySelector(targetSelector);
    
    if (!printContent) {
        console.error('Print target not found:', targetSelector);
        return;
    }

    const originalContents = document.body.innerHTML;
    const printableContent = printContent.innerHTML;

    const printHeader = generatePrintHeader();
    const printInfo = generatePrintInfo();
    const printSummary = generatePrintSummary(summaryData);
    const printFooter = generatePrintFooter();

    const fullContent = `
        <div class="print-container">
            ${printHeader}
            ${printInfo}
            ${printSummary}
            ${printableContent}
            ${printFooter}
        </div>
    `;

    document.body.innerHTML = fullContent;
    
    window.print();
    
    document.body.innerHTML = originalContents;
    
    initPrint();
    
    location.reload();
}

function generatePrintSummary(data) {
    if (!data || Object.keys(data).length === 0) {
        return '';
    }

    const rows = Object.entries(data).map(([label, value]) => `
        <div class="print-summary-row">
            <div class="print-summary-label">${label}</div>
            <div class="print-summary-value">${value}</div>
        </div>
    `).join('');

    return `
        <div class="print-summary">
            <h4 style="margin: 0 0 10px 0; text-align: center;">ملخص التقرير</h4>
            ${rows}
        </div>
    `;
}

document.addEventListener('DOMContentLoaded', function() {
    initPrint();
});

window.printReport = printReport;
window.printTable = printTable;
window.exportToCSV = exportToCSV;
window.exportToExcel = exportToExcel;
window.printWithSummary = printWithSummary;

