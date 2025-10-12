// 🔥 Checks Module - External JS File v5.0
(function() {
    'use strict';
    
    console.clear();
    console.log('%c🔥 CHECKS MODULE v5.0 LOADED (External File)!', 'background: #667eea; color: white; padding: 5px 10px; border-radius: 3px; font-weight: bold;');
    console.log('✅ jQuery:', typeof jQuery !== 'undefined' ? 'موجود ✓' : 'غير موجود ✗');
    console.log('✅ $:', typeof $ !== 'undefined' ? 'موجود ✓' : 'غير موجود ✗');
    
    // دوال مساعدة
    window.formatCurrency = function(number) {
        return new Intl.NumberFormat('ar-EG', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        }).format(number);
    };

    window.formatDate = function(dateStr) {
        if (!dateStr) return '-';
        try {
            const date = new Date(dateStr);
            return date.toLocaleDateString('ar-EG');
        } catch {
            return dateStr;
        }
    };

    // جلب وتصنيف الشيكات
    window.loadAndCategorizeChecks = function() {
        console.log('%c🔄 جلب الشيكات...', 'color: #667eea; font-weight: bold;');
        
        $.ajax({
            url: '/checks/api/checks',
            method: 'GET',
            dataType: 'json',
            success: function(response) {
                console.log('%c✅ تم استلام الرد!', 'color: green; font-weight: bold;');
                console.log('Response:', response);
                
                if (response.success && response.checks) {
                    const checks = response.checks;
                    console.log('%c📊 عدد الشيكات: ' + checks.length, 'color: blue; font-weight: bold;');
                    
                    // تصنيف
                    const categorized = {
                        pending: [],
                        overdue: [],
                        cashed: [],
                        returned: [],
                        bounced: []
                    };
                    
                    checks.forEach(function(check) {
                        const status = (check.status || '').toUpperCase();
                        if (status === 'PENDING' || status === 'DUE_SOON') {
                            categorized.pending.push(check);
                        } else if (status === 'OVERDUE') {
                            categorized.overdue.push(check);
                        } else if (status === 'CASHED') {
                            categorized.cashed.push(check);
                        } else if (status === 'RETURNED') {
                            categorized.returned.push(check);
                        } else if (status === 'BOUNCED') {
                            categorized.bounced.push(check);
                        } else if (status === 'RESUBMITTED') {
                            categorized.pending.push(check);
                        }
                    });
                    
                    console.log('📊 التصنيف:', {
                        pending: categorized.pending.length,
                        overdue: categorized.overdue.length,
                        cashed: categorized.cashed.length,
                        returned: categorized.returned.length,
                        bounced: categorized.bounced.length
                    });
                    
                    // تحديث العدادات
                    $('#badge-pending').text(categorized.pending.length);
                    $('#badge-overdue').text(categorized.overdue.length);
                    $('#badge-cashed').text(categorized.cashed.length);
                    $('#badge-returned').text(categorized.returned.length);
                    $('#badge-bounced').text(categorized.bounced.length);
                    $('#badge-all').text(checks.length);
                    
                    // ملء الجداول
                    console.log('%c📋 ملء الجداول...', 'color: purple; font-weight: bold;');
                    
                    fillTable('pending', categorized.pending);
                    fillTable('overdue', categorized.overdue);
                    fillTable('cashed', categorized.cashed);
                    fillTable('returned', categorized.returned);
                    fillTable('bounced', categorized.bounced);
                    fillTable('all', checks);
                    
                    // 🔥 فرض إظهار .tab-content والجداول (الحل النهائي!)
                    setTimeout(function() {
                        console.log('🔥 فرض إظهار .tab-content والجداول...');
                        
                        // فرض إظهار جميع .tab-content بـ !important
                        document.querySelectorAll('.tab-content').forEach(function(el) {
                            el.style.setProperty('display', 'block', 'important');
                            el.style.setProperty('visibility', 'visible', 'important');
                            el.style.setProperty('opacity', '1', 'important');
                        });
                        
                        // فرض إظهار جميع الجداول (حتى في التبويبات المخفية)
                        document.querySelectorAll('.checks-table').forEach(function(table) {
                            table.style.setProperty('display', 'table', 'important');
                            table.style.setProperty('visibility', 'visible', 'important');
                        });
                        
                        console.log('✅ تم فرض إظهار .tab-content وجميع الجداول');
                        
                    }, 250);
                    
                    // تحديث الإحصائيات
                    updateStats(categorized);
                    
                    console.log('%c✅ تم عرض جميع الشيكات!', 'color: green; font-weight: bold; font-size: 14px;');
                } else {
                    console.error('❌ Response لا يحتوي على checks!');
                }
            },
            error: function(xhr, status, error) {
                console.error('%c❌ فشل جلب الشيكات!', 'color: red; font-weight: bold;');
                console.error('Status:', xhr.status, 'Error:', error);
            }
        });
    };

    // ملء جدول - استخدام insertAdjacentHTML لضمان العرض
    window.fillTable = function(tableId, checks) {
        const tbody = document.querySelector('#table-' + tableId + ' tbody');
        
        if (!tbody) {
            console.error('❌ الجدول غير موجود: table-' + tableId);
            return;
        }
        
        console.log('📋 ملء جدول ' + tableId + ' بـ ' + checks.length + ' شيك');
        
        if (checks.length === 0) {
            tbody.innerHTML = '<tr><td colspan="10" class="text-center"><div class="empty-state"><i class="fas fa-inbox"></i><p>لا توجد شيكات</p></div></td></tr>';
            return;
        }
        
        // تنظيف الجدول
        tbody.innerHTML = '';
        
        let allRows = '';
        checks.forEach(function(check, index) {
            // تحديد لون الصف
            let rowClass = '';
            if ((check.status || '').toUpperCase() === 'OVERDUE') rowClass = 'row-overdue';
            else if ((check.status || '').toUpperCase() === 'CASHED') rowClass = 'row-cashed';
            else if ((check.status || '').toUpperCase() === 'PENDING') rowClass = 'row-pending';
            
            allRows += '<tr class="' + rowClass + '">' +
                '<td>' + (index + 1) + '</td>' +
                '<td><strong>' + (check.check_number || '-') + '</strong></td>' +
                '<td><strong>' + formatCurrency(check.amount || 0) + ' ₪</strong></td>' +
                '<td>' + (check.check_bank || '-') + '</td>' +
                '<td>' + (check.entity_name || '-') + '</td>' +
                '<td>' + (check.due_date_formatted || check.check_due_date || '-') + '</td>' +
                '<td>' + (check.is_incoming ? '<span class="badge badge-success"><i class="fas fa-arrow-down"></i> وارد</span>' : '<span class="badge badge-danger"><i class="fas fa-arrow-up"></i> صادر</span>') + '</td>' +
                '<td><span class="badge badge-' + (check.badge_color || 'info') + '">' + (check.status_ar || check.status || '-') + '</span></td>' +
                '<td><span class="badge badge-secondary">' + (check.source || '-') + '</span></td>' +
                '<td>' +
                    '<button class="btn btn-sm btn-info" onclick="viewCheckDetails(\'' + (check.id || '') + '\')" title="عرض"><i class="fas fa-eye"></i></button> ' +
                    '<button class="btn btn-sm btn-success" onclick="markAsCashed(\'' + (check.id || '') + '\')" title="سحب"><i class="fas fa-check"></i></button> ' +
                    '<button class="btn btn-sm btn-warning" title="تعديل"><i class="fas fa-edit"></i></button>' +
                '</td>' +
                '</tr>';
        });
        
        // استخدام insertAdjacentHTML لضمان العرض حتى في التبويبات المخفية
        tbody.insertAdjacentHTML('beforeend', allRows);
        
        console.log('✅ تم إضافة ' + checks.length + ' صف لجدول ' + tableId + ' (عدد الصفوف الفعلي: ' + tbody.querySelectorAll('tr').length + ')');
    };
    
    // تحديث الإحصائيات
    window.updateStats = function(categorized) {
        console.log('📊 تحديث إحصائيات الكاردات...');
        
        const calcTotal = function(arr) {
            return arr.reduce(function(sum, c) { return sum + (parseFloat(c.amount) || 0); }, 0);
        };
        
        $('#stat-pending-count').text(categorized.pending.length);
        $('#stat-pending-amount').text(formatCurrency(calcTotal(categorized.pending)) + ' ₪');
        
        $('#stat-cashed-count').text(categorized.cashed.length);
        $('#stat-cashed-amount').text(formatCurrency(calcTotal(categorized.cashed)) + ' ₪');
        
        $('#stat-returned-count').text(categorized.returned.length + categorized.bounced.length);
        $('#stat-returned-amount').text(formatCurrency(calcTotal(categorized.returned) + calcTotal(categorized.bounced)) + ' ₪');
        
        $('#stat-overdue-count').text(categorized.overdue.length);
        $('#stat-overdue-amount').text(formatCurrency(calcTotal(categorized.overdue)) + ' ₪');
        
        console.log('✅ تم تحديث الإحصائيات!');
    };
    
    // تحميل الإحصائيات
    window.loadStatistics = function() {
        console.log('📊 جلب إحصائيات API...');
        $.get('/checks/api/statistics', function(response) {
            if (response.success) {
                console.log('✅ إحصائيات API:', response.statistics);
            }
        });
    };
    
    // تحميل التنبيهات
    window.loadAlerts = function() {
        console.log('📢 جلب التنبيهات...');
        $.get('/checks/api/alerts', function(response) {
            if (response.success) {
                console.log('✅ التنبيهات:', response.alerts ? response.alerts.length : 0);
            }
        });
    };
    
    // تحديث الكل
    window.refreshAll = function() {
        console.log('%c🔄 تحديث جميع البيانات...', 'color: orange; font-weight: bold;');
        loadAndCategorizeChecks();
        loadStatistics();
        loadAlerts();
    };
    
    // عرض تفاصيل الشيك
    window.viewCheckDetails = function(checkId) {
        console.log('👁️ عرض تفاصيل الشيك:', checkId);
        Swal.fire({
            title: 'تفاصيل الشيك',
            text: 'جاري تحميل التفاصيل...',
            icon: 'info'
        });
    };
    
    // تحديث حالة الشيك إلى مسحوب
    window.markAsCashed = function(checkId) {
        console.log('💰 تحديث الشيك إلى مسحوب:', checkId);
        Swal.fire({
            title: 'تأكيد السحب',
            text: 'هل تريد تحديث حالة الشيك إلى "مسحوب"؟',
            icon: 'question',
            showCancelButton: true,
            confirmButtonText: 'نعم',
            cancelButtonText: 'لا'
        });
    };
    
    // عند تحميل الصفحة
    $(document).ready(function() {
        console.log('%c🔥 صفحة الشيكات v5.0 جاهزة!', 'background: #28a745; color: white; padding: 5px 10px; border-radius: 3px; font-weight: bold;');
        
        // تحميل فوري
        setTimeout(function() {
            console.log('%c📊 بدء التحميل التلقائي...', 'color: #667eea; font-weight: bold; font-size: 12px;');
            loadAndCategorizeChecks();
            loadStatistics();
            loadAlerts();
        }, 300);
        
        // تحديث دوري
        setInterval(function() {
            loadAndCategorizeChecks();
            loadStatistics();
            loadAlerts();
        }, 60000);
    });
    
    console.log('%c✅ جميع الدوال محملة ومتاحة!', 'color: green; font-weight: bold;');
})();
