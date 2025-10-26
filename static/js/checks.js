// 🔥 Checks Module - External JS File v5.0
(function() {
    'use strict';
    
    console.clear();
    console.log('%c🔥 CHECKS MODULE v5.0 LOADED (External File)!', 'background: #667eea; color: white; padding: 5px 10px; border-radius: 3px; font-weight: bold;');
    console.log('✅ jQuery:', typeof jQuery !== 'undefined' ? 'موجود ✓' : 'غير موجود ✗');
    console.log('✅ $:', typeof $ !== 'undefined' ? 'موجود ✓' : 'غير موجود ✗');
    
    // دوال مساعدة
    window.formatCurrency = function(number) {
        return new Intl.NumberFormat('en-US', {
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
            xhrFields: {
                withCredentials: true
            },
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
                        cancelled: [],
                        archived: []
                    };
                    
                    checks.forEach(function(check) {
                        const status = (check.status || '').toUpperCase();
                        
                        // فحص الملاحظات لاكتشاف التغييرات
                        const notes = (check.notes || '').toLowerCase();
                        let actualStatus = status;
                        
                        // إذا كان في الملاحظات حالة جديدة، استخدمها
                        if (notes.includes('حالة الشيك: مسحوب') || notes.includes('حالة الشيك: تم الصرف')) {
                            actualStatus = 'CASHED';
                        } else if (notes.includes('حالة الشيك: مرتجع')) {
                            actualStatus = 'RETURNED';
                        } else if (notes.includes('حالة الشيك: ملغي')) {
                            actualStatus = 'CANCELLED';
                        } else if (notes.includes('حالة الشيك: أعيد للبنك') || notes.includes('حالة الشيك: معلق')) {
                            actualStatus = 'PENDING';
                        } else if (notes.includes('حالة الشيك: مؤرشف')) {
                            actualStatus = 'ARCHIVED';
                        }
                        
                        if (actualStatus === 'PENDING' || actualStatus === 'DUE_SOON' || actualStatus === 'RESUBMITTED') {
                            categorized.pending.push(check);
                        } else if (actualStatus === 'OVERDUE') {
                            categorized.overdue.push(check);
                        } else if (actualStatus === 'CASHED') {
                            categorized.cashed.push(check);
                        } else if (actualStatus === 'RETURNED' || actualStatus === 'BOUNCED') {
                            categorized.returned.push(check);
                        } else if (actualStatus === 'CANCELLED') {
                            // الملغاة في تبويب خاص
                            categorized.cancelled.push(check);
                        } else if (actualStatus === 'ARCHIVED') {
                            categorized.archived.push(check);
                        }
                    });
                    
                    console.log('📊 التصنيف:', {
                        pending: categorized.pending.length,
                        overdue: categorized.overdue.length,
                        cashed: categorized.cashed.length,
                        returned: categorized.returned.length,
                        cancelled: categorized.cancelled.length,
                        archived: categorized.archived.length
                    });
                    
                    // تحديث العدادات
                    $('#badge-pending').text(categorized.pending.length);
                    $('#badge-overdue').text(categorized.overdue.length);
                    $('#badge-cashed').text(categorized.cashed.length);
                    $('#badge-returned').text(categorized.returned.length);
                    $('#badge-cancelled').text(categorized.cancelled.length);
                    $('#badge-archived').text(categorized.archived.length);
                    $('#badge-all').text(checks.length);
                    
                    // 🚨 تحديث تحذير الشيكات المتأخرة
                    if (categorized.overdue.length > 0) {
                        const overdueTotal = categorized.overdue.reduce((sum, c) => sum + (parseFloat(c.amount) || 0), 0);
                        $('#overdue-count-alert').text(categorized.overdue.length);
                        $('#overdue-amount-alert').text(formatCurrency(overdueTotal) + ' ₪');
                        $('#overdue-alert').fadeIn(500);
                        
                        // تمييز بارز لتبويب المتأخرة
                        $('a[href="#tab-overdue"]').addClass('blink-red');
                        
                        console.log('%c🚨 يوجد ' + categorized.overdue.length + ' شيك متأخر!', 'background: red; color: white; padding: 5px 10px; font-weight: bold; font-size: 14px;');
                    } else {
                        $('#overdue-alert').fadeOut(300);
                        $('a[href="#tab-overdue"]').removeClass('blink-red');
                    }
                    
                    // ملء الجداول
                    console.log('%c📋 ملء الجداول...', 'color: purple; font-weight: bold;');
                    
                    fillTable('pending', categorized.pending);
                    fillTable('overdue', categorized.overdue);
                    fillTable('cashed', categorized.cashed);
                    fillTable('returned', categorized.returned);
                    fillTable('cancelled', categorized.cancelled);
                    fillTable('archived', categorized.archived);
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
            
            // بناء الأزرار حسب حالة الشيك
            let actionButtons = '<button class="btn btn-sm btn-info" onclick="viewCheckDetails(\'' + (check.id || '') + '\')" title="عرض"><i class="fas fa-eye"></i></button> ';
            
            const status = (check.status || '').toUpperCase();
            
            // أزرار حسب الحالة (مع فحص الملاحظات)
            const notes = (check.notes || '').toLowerCase();
            let actualStatus = status;
            
            // الكشف عن الحالة الفعلية من الملاحظات
            if (notes.includes('حالة الشيك: مسحوب')) actualStatus = 'CASHED';
            else if (notes.includes('حالة الشيك: مرتجع')) actualStatus = 'RETURNED';
            else if (notes.includes('حالة الشيك: ملغي')) actualStatus = 'CANCELLED';
            else if (notes.includes('حالة الشيك: أعيد للبنك')) actualStatus = 'RESUBMITTED';
            else if (notes.includes('حالة الشيك: مؤرشف')) actualStatus = 'ARCHIVED';
            
            if (actualStatus === 'PENDING' || actualStatus === 'OVERDUE' || actualStatus === 'DUE_SOON' || actualStatus === 'RESUBMITTED') {
                // شيكات معلقة (بما فيها المُعادة للبنك): سحب | إرجاع | إلغاء
                actionButtons += '<button class="btn btn-sm btn-success" onclick="markAsCashed(\'' + (check.id || '') + '\')" title="سحب"><i class="fas fa-check"></i></button> ';
                actionButtons += '<button class="btn btn-sm btn-warning" onclick="markAsReturned(\'' + (check.id || '') + '\')" title="إرجاع"><i class="fas fa-undo"></i></button> ';
                actionButtons += '<button class="btn btn-sm btn-secondary" onclick="markAsCancelled(\'' + (check.id || '') + '\')" title="إلغاء/إتلاف"><i class="fas fa-ban"></i></button>';
            } else if (actualStatus === 'RETURNED' || actualStatus === 'BOUNCED') {
                // شيكات مرتجعة: إعادة للبنك | إلغاء
                actionButtons += '<button class="btn btn-sm btn-primary" onclick="resubmitCheck(\'' + (check.id || '') + '\')" title="إعادة للبنك"><i class="fas fa-sync"></i></button> ';
                actionButtons += '<button class="btn btn-sm btn-secondary" onclick="markAsCancelled(\'' + (check.id || '') + '\')" title="إلغاء/إتلاف"><i class="fas fa-ban"></i></button>';
            } else if (actualStatus === 'CASHED') {
                // شيكات مسحوبة: أرشفة فقط
                actionButtons += '<button class="btn btn-sm btn-dark" onclick="archiveCheck(\'' + (check.id || '') + '\')" title="أرشفة"><i class="fas fa-archive"></i></button>';
            } else if (actualStatus === 'CANCELLED') {
                // شيكات ملغاة: أرشفة أو استعادة
                actionButtons += '<button class="btn btn-sm btn-success" onclick="restoreCheck(\'' + (check.id || '') + '\')" title="استعادة"><i class="fas fa-redo"></i></button> ';
                actionButtons += '<button class="btn btn-sm btn-dark" onclick="archiveCheck(\'' + (check.id || '') + '\')" title="أرشفة"><i class="fas fa-archive"></i></button>';
            } else if (actualStatus === 'ARCHIVED') {
                // شيكات مؤرشفة: استعادة فقط
                actionButtons += '<button class="btn btn-sm btn-success" onclick="restoreCheck(\'' + (check.id || '') + '\')" title="استعادة"><i class="fas fa-redo"></i></button>';
            }
            
            // عرض العملة وسعر الصرف
            var currencyBadge = '<span class="badge badge-secondary">' + (check.currency || 'ILS') + '</span>';
            var fxRateDisplay = '-';
            
            // سعر الصرف وقت الإصدار (إذا كانت العملة مختلفة)
            if (check.currency && check.currency !== 'ILS' && check.fx_rate_issue) {
                var fxIcon = '';
                if (check.fx_rate_issue_source === 'online') fxIcon = '🌐';
                else if (check.fx_rate_issue_source === 'manual') fxIcon = '✍️';
                else fxIcon = '⚙️';
                
                fxRateDisplay = '<small>' + parseFloat(check.fx_rate_issue).toFixed(4) + ' ' + fxIcon + '</small>';
                
                // إذا تم صرف الشيك وهناك سعر صرف مختلف
                if (check.status === 'CASHED' && check.fx_rate_cash && check.fx_rate_cash !== check.fx_rate_issue) {
                    var cashIcon = '';
                    if (check.fx_rate_cash_source === 'online') cashIcon = '🌐';
                    else if (check.fx_rate_cash_source === 'manual') cashIcon = '✍️';
                    else cashIcon = '⚙️';
                    
                    fxRateDisplay += '<br><small class="text-success"><strong>صرف: ' + parseFloat(check.fx_rate_cash).toFixed(4) + ' ' + cashIcon + '</strong></small>';
                }
            }
            
            allRows += '<tr class="' + rowClass + '">' +
                '<td>' + (index + 1) + '</td>' +
                '<td><strong>' + (check.check_number || '-') + '</strong></td>' +
                '<td><strong>' + formatCurrency(check.amount || 0) + '</strong></td>' +
                '<td class="text-center">' + currencyBadge + '</td>' +
                '<td class="text-center">' + fxRateDisplay + '</td>' +
                '<td>' + (check.check_bank || '-') + '</td>' +
                '<td>' + (check.entity_name || '-') + '</td>' +
                '<td>' + (check.due_date_formatted || check.check_due_date || '-') + '</td>' +
                '<td>' + (check.is_incoming ? '<span class="badge badge-success"><i class="fas fa-arrow-down"></i> وارد</span>' : '<span class="badge badge-danger"><i class="fas fa-arrow-up"></i> صادر</span>') + '</td>' +
                '<td><span class="badge badge-' + (check.badge_color || 'info') + '">' + (check.status_ar || check.status || '-') + '</span></td>' +
                '<td><span class="badge badge-secondary">' + (check.source || '-') + '</span></td>' +
                '<td>' + actionButtons + '</td>' +
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
        
        // استدعاء API للحصول على التفاصيل
        $.get('/checks/api/checks', function(response) {
            if (response.success && response.checks) {
                const check = response.checks.find(c => c.id == checkId || c.id == 'split-' + checkId || c.id == 'expense-' + checkId);
                
                if (check) {
                    // بناء HTML للتفاصيل الكاملة
                    let detailsHtml = `
                        <div class="text-right" dir="rtl" style="max-height: 600px; overflow-y: auto;">
                            <h5 class="text-primary mb-3"><i class="fas fa-money-check-alt"></i> معلومات الشيك الأساسية</h5>
                            <table class="table table-bordered table-sm">
                                <tr><th width="40%">رقم الشيك:</th><td><strong>${check.check_number || '-'}</strong></td></tr>
                                <tr><th>البنك:</th><td><i class="fas fa-university text-primary"></i> ${check.check_bank || '-'}</td></tr>
                                <tr><th>المبلغ:</th><td><strong class="text-success" style="font-size: 1.2em;">${formatCurrency(check.amount || 0)} ${check.currency || 'ILS'}</strong></td></tr>
                                ${check.currency && check.currency != 'ILS' ? '<tr><th>العملة:</th><td><span class="badge badge-secondary">' + check.currency + '</span></td></tr>' : ''}
                                ${check.currency && check.currency != 'ILS' && check.fx_rate_issue ? '<tr class="bg-light"><th>💱 سعر الصرف (إصدار):</th><td><strong>' + parseFloat(check.fx_rate_issue).toFixed(4) + '</strong> ' + (check.fx_rate_issue_source === 'online' ? '🌐' : check.fx_rate_issue_source === 'manual' ? '✍️' : '⚙️') + ' <small class="text-muted">(' + (check.fx_rate_issue_timestamp || '-') + ')</small><br><small class="text-info">المبلغ بالشيكل: ' + formatCurrency((check.amount || 0) * (check.fx_rate_issue || 1)) + ' ₪</small></td></tr>' : ''}
                                ${check.currency && check.currency != 'ILS' && check.status === 'CASHED' && check.fx_rate_cash ? '<tr class="bg-success text-white"><th>💰 سعر الصرف (صرف):</th><td><strong>' + parseFloat(check.fx_rate_cash).toFixed(4) + '</strong> ' + (check.fx_rate_cash_source === 'online' ? '🌐' : check.fx_rate_cash_source === 'manual' ? '✍️' : '⚙️') + ' <small>(' + (check.fx_rate_cash_timestamp || '-') + ')</small><br><small>المبلغ الفعلي: <strong>' + formatCurrency((check.amount || 0) * (check.fx_rate_cash || 1)) + ' ₪</strong></small></td></tr>' : ''}
                                ${check.currency && check.currency != 'ILS' && check.fx_rate_issue && check.fx_rate_cash && check.fx_rate_cash !== check.fx_rate_issue ? '<tr class="bg-warning"><th>📊 فرق سعر الصرف:</th><td><strong>' + formatCurrency((check.amount || 0) * (check.fx_rate_cash - check.fx_rate_issue)) + ' ₪</strong> ' + ((check.fx_rate_cash > check.fx_rate_issue) ? '<span class="badge badge-success">ربح ✓</span>' : '<span class="badge badge-danger">خسارة ✗</span>') + '</td></tr>' : ''}
                                <tr><th>تاريخ الاستحقاق:</th><td>${check.due_date_formatted || check.check_due_date || '-'}</td></tr>
                                ${check.days_until_due ? '<tr><th>الأيام المتبقية:</th><td><span class="badge badge-' + (check.days_until_due < 0 ? 'danger' : check.days_until_due <= 7 ? 'warning' : 'info') + '">' + check.days_until_due + ' يوم</span></td></tr>' : ''}
                            </table>
                            
                            <h5 class="text-info mb-3 mt-4"><i class="fas fa-users"></i> الأطراف</h5>
                            <table class="table table-bordered table-sm">
                                <tr><th width="40%">الجهة:</th><td><strong>${check.entity_name || '-'}</strong> <span class="badge badge-secondary">${check.entity_type || '-'}</span></td></tr>
                                <tr><th>نوع الجهة:</th><td>${check.entity_type || '-'}</td></tr>
                                ${check.drawer_name ? '<tr><th>الساحب:</th><td>' + check.drawer_name + '</td></tr>' : ''}
                                ${check.payee_name ? '<tr><th>المستفيد:</th><td>' + check.payee_name + '</td></tr>' : ''}
                                <tr><th>الاتجاه:</th><td>${check.is_incoming ? '<span class="badge badge-success"><i class="fas fa-arrow-down"></i> شيك وارد (نستلمه)</span>' : '<span class="badge badge-danger"><i class="fas fa-arrow-up"></i> شيك صادر (ندفعه)</span>'}</td></tr>
                            </table>
                            
                            <h5 class="text-warning mb-3 mt-4"><i class="fas fa-info-circle"></i> الحالة والمصدر</h5>
                            <table class="table table-bordered table-sm">
                                <tr><th width="40%">الحالة:</th><td><span class="badge badge-${check.badge_color || 'info'}" style="font-size: 1.1em;">${check.status_ar || check.status || '-'}</span></td></tr>
                                <tr><th>المصدر:</th><td><span class="badge badge-primary">${check.source || '-'}</span></td></tr>
                                ${check.source_badge ? '<tr><th>نوع المصدر:</th><td><span class="badge badge-' + check.source_badge + '">' + check.source + '</span></td></tr>' : ''}
                                ${check.receipt_number ? '<tr><th>رقم الإيصال:</th><td><code>' + check.receipt_number + '</code></td></tr>' : ''}
                                ${check.reference ? '<tr><th>الرقم المرجعي:</th><td><code>' + check.reference + '</code></td></tr>' : ''}
                            </table>
                            
                            ${check.description || check.purpose || check.reason ? `
                            <h5 class="text-success mb-3 mt-4"><i class="fas fa-file-alt"></i> السبب/البيان</h5>
                            <div class="alert alert-info text-right">
                                <strong>${check.description || check.purpose || check.reason || '-'}</strong>
                            </div>
                            ` : ''}
                            
                            ${check.notes ? `
                            <h5 class="text-secondary mb-3 mt-4"><i class="fas fa-sticky-note"></i> ملاحظات</h5>
                            <div class="alert alert-warning text-right" style="white-space: pre-line; max-height: 150px; overflow-y: auto;">
                                ${check.notes}
                            </div>
                            ` : ''}
                            
                            ${check.created_at ? `
                            <h5 class="text-muted mb-3 mt-4"><i class="fas fa-history"></i> معلومات التدقيق</h5>
                            <table class="table table-bordered table-sm">
                                <tr><th width="40%">تاريخ الإنشاء:</th><td>${check.created_at || '-'}</td></tr>
                                ${check.created_by ? '<tr><th>أنشئ بواسطة:</th><td>' + check.created_by + '</td></tr>' : ''}
                            </table>
                            ` : ''}
                        </div>
                    `;
                    
                    Swal.fire({
                        title: '<i class="fas fa-money-check-alt text-primary"></i> تفاصيل الشيك الكاملة',
                        html: detailsHtml,
                        width: 800,
                        showCloseButton: true,
                        confirmButtonText: '<i class="fas fa-times"></i> إغلاق',
                        customClass: {
                            popup: 'swal-rtl'
                        }
                    });
                } else {
                    Swal.fire('خطأ', 'لم يتم العثور على الشيك', 'error');
                }
            }
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
            confirmButtonText: 'نعم، سحب',
            cancelButtonText: 'إلغاء',
            showLoaderOnConfirm: true,
            preConfirm: () => {
                return $.ajax({
                    url: '/checks/api/update-status/' + checkId,
                    method: 'POST',
                    contentType: 'application/json',
                    xhrFields: {
                        withCredentials: true
                    },
                    data: JSON.stringify({
                        status: 'CASHED',
                        notes: 'تم السحب'
                    })
                }).then(response => {
                    if (!response.success) {
                        throw new Error(response.message || 'فشل التحديث');
                    }
                    return response;
                }).catch(error => {
                    Swal.showValidationMessage('خطأ: ' + error.message);
                });
            },
            allowOutsideClick: () => !Swal.isLoading()
        }).then((result) => {
            if (result.isConfirmed) {
                Swal.fire({
                    title: 'تم!',
                    text: 'تم تحديث حالة الشيك إلى "مسحوب"',
                    icon: 'success',
                    timer: 2000
                });
                // إعادة تحميل البيانات
                loadAndCategorizeChecks();
            }
        });
    };
    
    // تحديث حالة الشيك إلى مرتجع
    window.markAsReturned = function(checkId) {
        console.log('↩️ تحديث الشيك إلى مرتجع:', checkId);
        updateCheckStatus(checkId, 'RETURNED', 'تم إرجاع الشيك من البنك');
    };
    
    // تحديث حالة الشيك إلى ملغي
    window.markAsCancelled = function(checkId) {
        console.log('⛔ تحديث الشيك إلى ملغي:', checkId);
        updateCheckStatus(checkId, 'CANCELLED', 'تم إلغاء الشيك');
    };
    
    // إعادة تقديم الشيك للبنك (للشيكات المرتجعة)
    window.resubmitCheck = function(checkId) {
        console.log('🔁 إعادة تقديم الشيك للبنك:', checkId);
        updateCheckStatus(checkId, 'RESUBMITTED', 'تم إعادة تقديم الشيك للبنك');
    };
    
    // أرشفة الشيك
    window.archiveCheck = function(checkId) {
        console.log('📦 أرشفة الشيك:', checkId);
        updateCheckStatus(checkId, 'ARCHIVED', 'تم أرشفة الشيك');
    };
    
    // استعادة الشيك من الأرشيف
    window.restoreCheck = function(checkId) {
        console.log('♻️ استعادة الشيك:', checkId);
        updateCheckStatus(checkId, 'PENDING', 'تم استعادة الشيك من الأرشيف');
    };
    
    // دالة مشتركة لتحديث حالة الشيك
    function updateCheckStatus(checkId, newStatus, message) {
        const statusInfo = {
            'CASHED': {
                title: '✅ تأكيد سحب الشيك', 
                text: 'هل تم صرف هذا الشيك من البنك فعلاً؟\n\nسيتم تسجيل قيد محاسبي تلقائي:\n• مدين: البنك\n• دائن: شيكات تحت التحصيل', 
                icon: 'question', 
                confirmText: '✅ نعم، تم السحب', 
                successText: 'تم تحديث حالة الشيك إلى "مسحوب" بنجاح!\n\nتم تسجيل القيد المحاسبي في دفتر الأستاذ.'
            },
            'RETURNED': {
                title: '⚠️ تأكيد إرجاع الشيك', 
                text: 'هل تم إرجاع هذا الشيك من البنك؟\n\nسيتم تسجيل قيد محاسبي عكسي:\n• مدين: العملاء/الموردين\n• دائن: شيكات تحت التحصيل/الدفع', 
                icon: 'warning', 
                confirmText: '🔄 نعم، تم الإرجاع', 
                successText: 'تم تحديث حالة الشيك إلى "مرتجع" بنجاح!\n\nتم تسجيل القيد العكسي في دفتر الأستاذ.'
            },
            'CANCELLED': {
                title: '⛔ تأكيد إلغاء/إتلاف الشيك', 
                text: 'هل تريد إلغاء أو إتلاف هذا الشيك نهائياً؟\n\nسيتم:\n• عكس القيد المحاسبي\n• إرجاع الدين للجهة\n• نقل الشيك لتبويب "ملغاة/تالفة"', 
                icon: 'warning', 
                confirmText: '⛔ نعم، إلغاء/إتلاف', 
                successText: 'تم إلغاء الشيك بنجاح!\n\nتم عكس القيد المحاسبي وإرجاع الدين.'
            },
            'RESUBMITTED': {
                title: '🔁 إعادة تقديم الشيك للبنك', 
                text: 'هل تريد إعادة تقديم هذا الشيك للبنك مرة أخرى؟\n\nسيعود الشيك إلى حالة "معلق".', 
                icon: 'info', 
                confirmText: '🔁 نعم، إعادة تقديم', 
                successText: 'تم إعادة الشيك للبنك بنجاح!\n\nأصبح الشيك في حالة "معلق" الآن.'
            },
            'ARCHIVED': {
                title: '📦 أرشفة الشيك', 
                text: 'هل تريد نقل هذا الشيك إلى الأرشيف؟\n\nيمكنك استعادته لاحقاً.', 
                icon: 'info', 
                confirmText: '📦 نعم، أرشفة', 
                successText: 'تم أرشفة الشيك بنجاح!'
            },
            'PENDING': {
                title: '♻️ استعادة الشيك', 
                text: 'هل تريد استعادة هذا الشيك من الأرشيف؟\n\nسيعود إلى حالة "معلق".', 
                icon: 'info', 
                confirmText: '♻️ نعم، استعادة', 
                successText: 'تم استعادة الشيك من الأرشيف بنجاح!'
            }
        };
        
        const info = statusInfo[newStatus] || {title: 'تحديث', text: 'هل تريد تحديث الحالة؟', icon: 'question', confirmText: 'نعم', successText: 'تم التحديث'};
        
        Swal.fire({
            title: info.title,
            text: info.text,
            icon: info.icon,
            showCancelButton: true,
            confirmButtonText: info.confirmText,
            cancelButtonText: 'إلغاء',
            showLoaderOnConfirm: true,
            preConfirm: () => {
                return $.ajax({
                    url: '/checks/api/update-status/' + checkId,
                    method: 'POST',
                    contentType: 'application/json',
                    xhrFields: {
                        withCredentials: true
                    },
                    data: JSON.stringify({
                        status: newStatus,
                        notes: message
                    })
                }).then(response => {
                    if (!response.success) {
                        throw new Error(response.message || 'فشل التحديث');
                    }
                    return response;
                }).catch(error => {
                    Swal.showValidationMessage('خطأ: ' + (error.responseJSON?.message || error.message || 'حدث خطأ غير متوقع'));
                });
            },
            allowOutsideClick: () => !Swal.isLoading()
        }).then((result) => {
            if (result.isConfirmed) {
                Swal.fire({
                    title: 'تم!',
                    text: info.successText,
                    icon: 'success',
                    timer: 2000
                });
                // إعادة تحميل البيانات
                setTimeout(() => loadAndCategorizeChecks(), 500);
            }
        });
    }
    
    // 🚨 عرض تبويب الشيكات المتأخرة
    window.showOverdueTab = function() {
        $('.nav-link[data-toggle="pill"]').removeClass('active');
        $('.nav-link[href="#tab-overdue"]').addClass('active');
        $('.tab-pane').removeClass('active show');
        $('#tab-overdue').addClass('active show');
        
        // scroll للأعلى
        window.scrollTo({ top: 0, behavior: 'smooth' });
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
