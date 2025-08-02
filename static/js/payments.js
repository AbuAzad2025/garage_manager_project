و// static/js/payments.js
document.addEventListener('DOMContentLoaded', function() {
    // عناصر الفلترة
    const filterElements = [
        '#filterEntity', '#filterStatus', '#filterDirection', 
        '#filterMethod', '#startDate', '#endDate'
    ];
    
    // إضافة مستمعات الأحداث
    filterElements.forEach(selector => {
        document.querySelector(selector)?.addEventListener('change', function() {
            loadPayments(1); // إعادة التحميل من الصفحة الأولى
        });
    });
    
    // تحميل الدفعات مع الترحيل
    function loadPayments(page = 1) {
        const params = new URLSearchParams({
            entity_type: document.querySelector('#filterEntity').value,
            status: document.querySelector('#filterStatus').value,
            direction: document.querySelector('#filterDirection').value,
            method: document.querySelector('#filterMethod').value,
            start_date: document.querySelector('#startDate').value,
            end_date: document.querySelector('#endDate').value,
            page: page
        });
        
        fetch(`/payments/?${params.toString()}`, {
            headers: {"Accept": "application/json"}
        })
        .then(response => response.json())
        .then(data => {
            renderPaymentsTable(data.payments);
            renderPagination(data.total_pages, data.current_page);
        });
    }
    
    // عرض الدفعات في الجدول
    function renderPaymentsTable(payments) {
        const tbody = document.querySelector('#paymentsTable tbody');
        tbody.innerHTML = '';
        
        payments.forEach(p => {
            const row = document.createElement('tr');
            
            // تنسيق الدفعات الجزئية
            const splitsHtml = p.splits.map(s => `
                <div class="split-info">
                    <span class="badge bg-secondary">${s.method}: ${s.amount} ${p.currency}</span>
                </div>
            `).join('');
            
            row.innerHTML = `
                <td>${p.payment_date.split('T')[0]}</td>
                <td>${p.total_amount} ${p.currency}</td>
                <td>${p.method}</td>
                <td>
                    <span class="badge ${p.direction === 'IN' ? 'bg-success' : 'bg-danger'}">
                        ${p.direction === 'IN' ? 'وارد' : 'صادر'}
                    </span>
                </td>
                <td>
                    <span class="badge 
                        ${p.status === 'COMPLETED' ? 'bg-success' : 
                          p.status === 'PENDING' ? 'bg-warning' : 
                          p.status === 'FAILED' ? 'bg-danger' : 'bg-secondary'}">
                        ${p.status}
                    </span>
                </td>
                <td>${p.entity_type}</td>
                <td>
                    <div class="splits-container">${splitsHtml}</div>
                </td>
                <td>
                    <a href="/payments/${p.id}" class="btn btn-info btn-sm">عرض</a>
                    <a href="/payments/${p.id}/edit" class="btn btn-warning btn-sm">تعديل</a>
                </td>
            `;
            
            tbody.appendChild(row);
        });
    }
    
    // عرض الترحيل
    function renderPagination(totalPages, currentPage) {
        const pagination = document.querySelector('#pagination');
        pagination.innerHTML = '';
        
        // زر الصفحة السابقة
        const prevLi = document.createElement('li');
        prevLi.className = `page-item ${currentPage === 1 ? 'disabled' : ''}`;
        prevLi.innerHTML = `<a class="page-link" href="#" data-page="${currentPage - 1}">السابق</a>`;
        pagination.appendChild(prevLi);
        
        // أرقام الصفحات
        for (let i = 1; i <= totalPages; i++) {
            const li = document.createElement('li');
            li.className = `page-item ${i === currentPage ? 'active' : ''}`;
            li.innerHTML = `<a class="page-link" href="#" data-page="${i}">${i}</a>`;
            pagination.appendChild(li);
        }
        
        // زر الصفحة التالية
        const nextLi = document.createElement('li');
        nextLi.className = `page-item ${currentPage === totalPages ? 'disabled' : ''}`;
        nextLi.innerHTML = `<a class="page-link" href="#" data-page="${currentPage + 1}">التالي</a>`;
        pagination.appendChild(nextLi);
        
        // إضافة مستمعات الأحداث لأرقام الصفحات
        pagination.querySelectorAll('.page-link').forEach(link => {
            link.addEventListener('click', function(e) {
                e.preventDefault();
                loadPayments(parseInt(this.dataset.page));
            });
        });
    }
    
    // التحميل الأولي
    loadPayments();
});