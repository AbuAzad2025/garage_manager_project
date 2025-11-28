// 🔥 Checks Module - External JS File v5.0
(function() {
    'use strict';
    
    const IS_OWNER = Boolean(typeof window !== 'undefined' && (window.CHECKS_IS_OWNER === true || window.CHECKS_IS_OWNER === 'true'));
    
    function htmlEscape(value) {
        if (value === null || typeof value === 'undefined') {
            return '';
        }
        return String(value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }
    
    window.checkFilters = {
        direction: 'all',
        status: 'all',
        source: 'all',
    };
    
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

    function detectActualStatusFromNotes(notes) {
        try {
            const text = String(notes || '');
            const lines = text.split(/\n+/).map(function(s){ return s.trim(); }).filter(function(s){ return s.length > 0; });
            for (let i = lines.length - 1; i >= 0; i--) {
                const ln = lines[i];
                const idx = ln.indexOf('حالة الشيك:');
                if (idx === -1) continue;
                const label = ln.substring(idx + 'حالة الشيك:'.length).trim();
                if (label.indexOf('مسحوب') !== -1 || label.indexOf('تم الصرف') !== -1) return 'CASHED';
                if (label.indexOf('مرتجع') !== -1) return 'RETURNED';
                if (label.indexOf('ملغي') !== -1) return 'CANCELLED';
                if (label.indexOf('أعيد') !== -1 || label.indexOf('معاد') !== -1) return 'RESUBMITTED';
                if (label.indexOf('معلق') !== -1) return 'PENDING';
                if (label.indexOf('مرفوض') !== -1) return 'BOUNCED';
                if (label.indexOf('مؤرشف') !== -1) return 'CANCELLED';
            }
        } catch(e) {}
        return null;
    }

    if (typeof window.showNotification !== 'function') {
        window.showNotification = function(message, type = 'info') {
            const normalizedType = (type || 'info').toLowerCase();
            if (window.toastr && typeof window.toastr[normalizedType === 'danger' ? 'error' : normalizedType] === 'function') {
                const toastType = normalizedType === 'danger' ? 'error' : normalizedType;
                window.toastr[toastType](message);
            } else {
                console[(normalizedType === 'danger' || normalizedType === 'error') ? 'error' : 'log'](message);
                if (normalizedType === 'danger' || normalizedType === 'error') {
                    alert(message);
                }
            }
        };
    }

    // جلب وتصنيف الشيكات
    let checksLoadErrorShown = false;
    window.loadAndCategorizeChecks = function() {
        $.ajax({
            url: '/checks/api/checks',
            method: 'GET',
            data: window.checkFilters,
            dataType: 'json',
            xhrFields: {
                withCredentials: true
            },
            success: function(response) {
                    checksLoadErrorShown = false; // إعادة تعيين عند النجاح
                    const checks = response.checks;
                    try { window.checksByToken = {}; } catch(e) {}
                    if (Array.isArray(checks)) {
                        checks.forEach(function(c){
                            const t = c.token || c.id;
                            if (t) { window.checksByToken[t] = c; }
                        });
                    }
                    
                    // تصنيف
                    const categorized = {
                        pending: [],
                        overdue: [],
                        cashed: [],
                        returned: [],
                        bounced: [],
                        cancelled: [],
                        settled: [],
                        legal: [],
                        all: checks
                    };
                    
                    checks.forEach(function(check) {
                        const status = (check.status || '').toUpperCase();
                        const daysUntilDue = check.days_until_due || 0;
                        const isOverdue = daysUntilDue < 0;
                        
                    const notes = (check.notes || '');
                    const isSettled = check.is_settled || notes.indexOf('[settled=true]'.toLowerCase()) !== -1;
                    const isLegal = check.is_legal || notes.indexOf('دائرة قانونية') !== -1;
                    let actualStatus = status;
                    const detected = detectActualStatusFromNotes(notes);
                    if (detected) {
                        actualStatus = detected;
                    }
                    if (actualStatus === 'RESUBMITTED') {
                        actualStatus = 'PENDING';
                    }
                        
                        if (isLegal) {
                            categorized.legal.push(check);
                        } else if (isSettled) {
                            categorized.settled.push(check);
                        } else if (isOverdue && (actualStatus === 'PENDING' || actualStatus === 'DUE_SOON' || actualStatus === 'RESUBMITTED')) {
                            categorized.overdue.push(check);
                        } else if (actualStatus === 'CASHED') {
                            categorized.cashed.push(check);
                        } else if (actualStatus === 'RETURNED' || actualStatus === 'BOUNCED') {
                            categorized.returned.push(check);
                        } else if (actualStatus === 'CANCELLED') {
                            categorized.cancelled.push(check);
                        } else if (actualStatus === 'PENDING' || actualStatus === 'DUE_SOON' || actualStatus === 'RESUBMITTED') {
                            categorized.pending.push(check);
                        } else {
                            categorized.pending.push(check);
                        }
                    });

                    $('#badge-pending').text(categorized.pending.length);
                    $('#badge-overdue').text(categorized.overdue.length);
                    $('#badge-cashed').text(categorized.cashed.length);
                    $('#badge-returned').text(categorized.returned.length);
                    $('#badge-cancelled').text(categorized.cancelled.length);
                    $('#badge-settled').text(categorized.settled.length);
                    $('#badge-legal').text(categorized.legal.length);
                    $('#badge-all').text(checks.length);
                    
                    // 🚨 تحديث تحذير الشيكات المتأخرة
                    // ✅ سيتم استخدام الإحصائيات من الباكند في loadStatistics()
                    if (categorized.overdue.length > 0) {
                        $('#overdue-count-alert').text(categorized.overdue.length);
                        // المبلغ سيتم ملؤه من loadStatistics()
                        $('#overdue-alert').fadeIn(500);
                        
                        // تمييز بارز لتبويب المتأخرة
                        $('a[href="#tab-overdue"]').addClass('blink-red');
                    } else {
                        $('#overdue-alert').fadeOut(300);
                        $('a[href="#tab-overdue"]').removeClass('blink-red');
                    }
                    
                    // ملء الجداول
                    
                    fillTable('pending', categorized.pending);
                    fillTable('overdue', categorized.overdue);
                    fillTable('cashed', categorized.cashed);
                    fillTable('returned', categorized.returned);
                    fillTable('cancelled', categorized.cancelled);
                    fillTable('settled', categorized.settled);
                    fillTable('legal', categorized.legal);
                    fillTable('all', checks);
                    
                    // 🔥 فرض إظهار .tab-content والجداول (الحل النهائي!)
                    setTimeout(function() {

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

                    }, 250);
                    
                    // تحديث الإحصائيات
                    updateStats(categorized);
                    const lastRefreshEl = document.getElementById('checks-last-refresh');
                    if (lastRefreshEl) {
                        const now = new Date();
                        lastRefreshEl.textContent = now.toLocaleString('ar-EG');
                    }
            },
            error: function(xhr, status, error) {
                // فقط عرض الرسالة مرة واحدة وليس لكل محاولة
                if (!checksLoadErrorShown && xhr.status !== 0) {
                    checksLoadErrorShown = true;
                    console.error('فشل جلب الشيكات:', status, error);
                    showNotification('فشل جلب الشيكات', 'danger');
                }
            }
        });
    };

    // ملء جدول - استخدام insertAdjacentHTML لضمان العرض
    window.fillTable = function(tableId, checks) {
        const tbody = document.querySelector('#table-' + tableId + ' tbody');
        
        if (!tbody) {

            return;
        }

        if (checks.length === 0) {
            tbody.innerHTML = '<tr><td colspan="10" class="text-center"><div class="empty-state"><i class="fas fa-inbox"></i><p>لا توجد شيكات</p></div></td></tr>';
            return;
        }
        
        // تنظيف الجدول
        tbody.innerHTML = '';
        
        let allRows = '';
        checks.forEach(function(check, index) {
            const token = check.token || check.id;
            const viewId = check.id || token;
            const entityTypeCode = (check.entity_type_code || '').toString();
            const entityId = typeof check.entity_id === 'undefined' ? '' : check.entity_id;
            const checkNumber = check.check_number || '';
            const amountValue = check.amount || 0;
            const currencyValue = check.currency || 'ILS';
            const dueDateValue = (check.check_due_date || '').split('T')[0] || '';
            const bankValue = check.check_bank || '';
            const notes = (check.notes || '');
            const isSettled = notes.indexOf('[settled=true]'.toLowerCase()) !== -1;
            const canSettle = IS_OWNER && Boolean(entityTypeCode && entityId);
            // تحديد لون الصف
            let rowClass = '';
            if ((check.status || '').toUpperCase() === 'OVERDUE') rowClass = 'row-overdue';
            else if ((check.status || '').toUpperCase() === 'CASHED') rowClass = 'row-cashed';
            else if ((check.status || '').toUpperCase() === 'PENDING') rowClass = 'row-pending';
            else if ((check.status || '').toUpperCase() === 'RESUBMITTED') rowClass = 'row-pending';
            var nlow = (check.notes || '').toLowerCase();
            if (nlow.indexOf('[return_reason=bank]') !== -1) {
                rowClass = (rowClass ? rowClass + ' ' : '') + 'row-bank-return';
            }
            
            // بناء الأزرار حسب حالة الشيك
            let actionButtons = '<button class="btn btn-sm btn-info" onclick="viewCheckDetails(\'' + (viewId || '') + '\')" title="عرض"><i class="fas fa-eye"></i></button> ';
            
            const status = (check.status || '').toUpperCase();
            let actualStatus = status;
            const detectedForButtons = detectActualStatusFromNotes(notes);
            if (detectedForButtons) {
                actualStatus = detectedForButtons;
            }
            if (actualStatus === 'RESUBMITTED') {
                actualStatus = 'PENDING';
            }
            
            if (!isSettled && (actualStatus === 'PENDING' || actualStatus === 'OVERDUE' || actualStatus === 'DUE_SOON')) {
                // شيكات معلقة (بما فيها المُعادة للبنك): سحب | إرجاع | إلغاء
                actionButtons += '<button class="btn btn-sm btn-success" onclick="markAsCashed(\'' + token + '\')" title="سحب"><i class="fas fa-check"></i></button> ';
                actionButtons += '<button class="btn btn-sm btn-warning" onclick="markAsReturned(\'' + token + '\')" title="إرجاع"><i class="fas fa-undo"></i></button> ';
                actionButtons += '<button class="btn btn-sm btn-secondary" onclick="markAsCancelled(\'' + token + '\')" title="إلغاء"><i class="fas fa-ban"></i></button>';
            } else if (!isSettled && (actualStatus === 'RETURNED' || actualStatus === 'BOUNCED')) {
                // شيكات مرتجعة: إعادة للبنك | إلغاء
                actionButtons += '<button class="btn btn-sm btn-primary" onclick="resubmitCheck(\'' + token + '\')" title="إعادة للبنك"><i class="fas fa-sync"></i></button> ';
                actionButtons += '<button class="btn btn-sm btn-secondary" onclick="markAsCancelled(\'' + token + '\')" title="إلغاء"><i class="fas fa-ban"></i></button>';
                if (canSettle) {
                    const settlementAttrs = [
                        'data-token="' + token + '"',
                        'data-entity-type="' + entityTypeCode + '"',
                        'data-entity-id="' + entityId + '"',
                        'data-check-number="' + checkNumber.replace(/"/g, '&quot;') + '"',
                        'data-amount="' + amountValue + '"',
                        'data-currency="' + currencyValue + '"'
                    ].join(' ');
                    actionButtons += '<button class="btn btn-sm btn-outline-success" ' + settlementAttrs + ' onclick="openCheckSettlement(this)" title="تسوية مالية"><i class="fas fa-handshake"></i></button> ';
                }
                if (IS_OWNER) {
                    actionButtons += '<button class="btn btn-sm btn-outline-danger" onclick="markAsLegal(\'' + token + '\')" title="دائرة قانونية"><i class="fas fa-gavel"></i></button>';
                }
            } else if (actualStatus === 'CASHED') {
                // شيكات مسحوبة: أرشفة فقط
                actionButtons += '<button class="btn btn-sm btn-dark" onclick="archiveCheck(\'' + token + '\')" title="أرشفة"><i class="fas fa-archive"></i></button>';
            } else if (actualStatus === 'CANCELLED') {
                // شيكات ملغاة: استعادة فقط
                actionButtons += '<button class="btn btn-sm btn-success" onclick="restoreCheck(\'' + token + '\')" title="استعادة"><i class="fas fa-redo"></i></button>';
            }
            
            if (isSettled) {
                actionButtons = '<span class="badge badge-secondary">مسوّى</span> <button class="btn btn-sm btn-info" onclick="viewCheckDetails(\'' + (viewId || '') + '\')" title="عرض"><i class="fas fa-eye"></i></button> ';
                if (IS_OWNER) {
                    actionButtons += '<button class="btn btn-sm btn-warning" onclick="unsettleCheck(\'' + token + '\')" title="إلغاء التسوية"><i class="fas fa-undo"></i></button> ';
                }
            }
            
            if (IS_OWNER) {
                const editAttrs = [
                    'data-token="' + token + '"',
                    'data-entity-type="' + htmlEscape(entityTypeCode) + '"',
                    'data-entity-id="' + htmlEscape(entityId) + '"',
                    'data-check-number="' + htmlEscape(checkNumber) + '"',
                    'data-amount="' + htmlEscape(amountValue) + '"',
                    'data-currency="' + htmlEscape(currencyValue) + '"',
                    'data-due-date="' + htmlEscape(dueDateValue) + '"',
                    'data-bank="' + htmlEscape(bankValue) + '"'
                ].join(' ');
                actionButtons += '<button class="btn btn-sm btn-outline-primary" ' + editAttrs + ' onclick="openCheckEditor(this)" title="تعديل الشيك"><i class="fas fa-edit"></i></button> ';
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
                
                var issueRate = parseFloat(check.fx_rate_issue) || 0;
                fxRateDisplay = '<small>' + (isNaN(issueRate) ? '0.0000' : issueRate.toFixed(4)) + ' ' + fxIcon + '</small>';
                
                if (check.status === 'CASHED' && check.fx_rate_cash && check.fx_rate_cash !== check.fx_rate_issue) {
                    var cashIcon = '';
                    if (check.fx_rate_cash_source === 'online') cashIcon = '🌐';
                    else if (check.fx_rate_cash_source === 'manual') cashIcon = '✍️';
                    else cashIcon = '⚙️';
                    
                    var cashRate = parseFloat(check.fx_rate_cash) || 0;
                    fxRateDisplay += '<br><small class="text-success"><strong>صرف: ' + (isNaN(cashRate) ? '0.0000' : cashRate.toFixed(4)) + ' ' + cashIcon + '</strong></small>';
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
                (function(){
                    var reasonBadge = '';
                    var n = (check.notes || '').toLowerCase();
                    if (n.indexOf('[return_reason=bank]') !== -1) {
                        reasonBadge = ' <span class="badge badge-danger">مرتجع بنك</span>';
                    } else if (n.indexOf('[return_reason=payment_refund]') !== -1) {
                        reasonBadge = ' <span class="badge badge-info">إرجاع دفعة</span>';
                    }
                    return '<td><span class="badge badge-' + (check.badge_color || 'info') + '">' + (check.status_ar || check.status || '-') + '</span>' + reasonBadge + '</td>';
                })() +
                '<td><span class="badge badge-secondary">' + (check.source || '-') + '</span></td>' +
                '<td>' + actionButtons + '</td>' +
                '</tr>';
        });
        
        // استخدام insertAdjacentHTML لضمان العرض حتى في التبويبات المخفية
        tbody.insertAdjacentHTML('beforeend', allRows);

    };
    
    window.updateStats = function(categorized) {

        const calcTotalByCurrency = function(arr) {
            const totals = {};
            arr.forEach(function(c) {
                const curr = (c.currency || 'ILS').toUpperCase();
                if (!totals[curr]) totals[curr] = 0;
                const amt = parseFloat(c.amount) || 0;
                if (!isNaN(amt)) totals[curr] += amt;
            });
            return totals;
        };
        
        const formatTotals = function(totals) {
            const keys = Object.keys(totals);
            if (keys.length === 0) return '0.00 ₪';
            if (keys.length === 1) {
                const curr = keys[0];
                return formatCurrency(totals[curr]) + ' ' + curr;
            }
            return keys.map(c => formatCurrency(totals[c]) + ' ' + c).join(' + ');
        };
        
        const pendingTotals = calcTotalByCurrency(categorized.pending);
        const cashedTotals = calcTotalByCurrency(categorized.cashed);
        
        $('#stat-pending-count').text(categorized.pending.length);
        $('#stat-pending-amount').html(formatTotals(pendingTotals));
        
        $('#stat-cashed-count').text(categorized.cashed.length);
        $('#stat-cashed-amount').html(formatTotals(cashedTotals));
        
        const returnedTotal = (categorized.returned ? categorized.returned.length : 0) + (categorized.bounced ? categorized.bounced.length : 0);
        const returnedTotals = calcTotalByCurrency((categorized.returned || []).concat(categorized.bounced || []));
        $('#stat-returned-count').text(returnedTotal);
        $('#stat-returned-amount').html(formatTotals(returnedTotals));
        
        // ✅ سيتم ملؤها من loadStatistics() من الباكند
        // $('#stat-overdue-count').text(categorized.overdue.length);
        // $('#stat-overdue-amount').text(formatCurrency(calcTotal(categorized.overdue)) + ' ₪');

    };
    
    // ✅ تحميل الإحصائيات من الباكند
    window.loadStatistics = function() {
        $.get('/checks/api/statistics', function(response) {
            if (response.success && response.statistics) {
                const stats = response.statistics;
                
                // تحديث المبلغ المتأخر في التحذير
                if (stats.incoming && stats.incoming.overdue_amount) {
                    $('#overdue-amount-alert').text(formatCurrency(stats.incoming.overdue_amount) + ' ₪');
                }
                
                // تحديث الإحصائيات العامة
                if (stats.incoming) {
                    $('#stat-overdue-count').text(stats.incoming.overdue_count || 0);
                    $('#stat-overdue-amount').text(formatCurrency(stats.incoming.overdue_amount || 0) + ' ₪');
                }
            }
        }).fail(function() {
            // تجاهل الأخطاء بصمت - لا حاجة لإزعاج المستخدم
            console.debug('فشل جلب الإحصائيات (غير حرج)');
        });
    };
    
    // تحميل التنبيهات
    window.loadAlerts = function() {
        $.get('/checks/api/alerts', function(response) {
            if (response.success) {
                // معالجة التنبيهات
            }
        }).fail(function() {
            // تجاهل الأخطاء بصمت - لا حاجة لإزعاج المستخدم
            console.debug('فشل جلب التنبيهات (غير حرج)');
        });
    };
    
    // تحديث الكل
    window.refreshAll = function() {
        loadAndCategorizeChecks();
        loadStatistics();
        loadAlerts();
    };

    window.openFirstIncompleteCheck = function() {
        if (!IS_OWNER) {
            Swal.fire('تنبيه', 'هذا الإجراء متاح للمالك فقط.', 'warning');
            return;
        }
        $.get('/checks/api/first-incomplete', function(response) {
            if (!response || !response.success) {
                Swal.fire('خطأ', 'فشل جلب الشيك الناقص.', 'error');
                return;
            }
            if (!response.token) {
                Swal.fire('ممتاز', 'لا يوجد أي شيك ناقص بيانات أساسية.', 'success');
                return;
            }
            const token = response.token;
            $.get('/checks/api/checks', function(allResponse) {
                if (!allResponse || !allResponse.success || !Array.isArray(allResponse.checks)) {
                    Swal.fire('خطأ', 'فشل جلب قائمة الشيكات الكاملة.', 'error');
                    return;
                }
                const check = allResponse.checks.find(function(c) { return c.token === token; });
                if (!check) {
                    Swal.fire('خطأ', 'لم يتم العثور على الشيك المطلوب في القائمة.', 'error');
                    return;
                }
                const btn = document.createElement('button');
                btn.setAttribute('data-token', check.token || check.id);
                btn.setAttribute('data-entity-type', (check.entity_type_code || '').toString());
                if (typeof check.entity_id !== 'undefined' && check.entity_id !== null) {
                    btn.setAttribute('data-entity-id', String(check.entity_id));
                } else {
                    btn.setAttribute('data-entity-id', '');
                }
                btn.setAttribute('data-check-number', check.check_number || '');
                btn.setAttribute('data-amount', String(check.amount || 0));
                btn.setAttribute('data-currency', check.currency || 'ILS');
                btn.setAttribute('data-due-date', (check.check_due_date || '').split('T')[0] || '');
                btn.setAttribute('data-bank', check.check_bank || '');
                openCheckEditor(btn);
            }).fail(function() {
                Swal.fire('خطأ', 'تعذر تحميل الشيكات.', 'error');
            });
        }).fail(function() {
            Swal.fire('خطأ', 'تعذر الاتصال بخدمة جلب الشيك الناقص.', 'error');
        });
    };

    function initCheckFilters() {
        const directionButtons = document.querySelectorAll('[data-filter-direction]');
        directionButtons.forEach(function(btn) {
            btn.addEventListener('click', function() {
                const value = btn.getAttribute('data-filter-direction') || 'all';
                const current = window.checkFilters.direction;
                let nextValue = value;
                if (current === value && value !== 'all') {
                    nextValue = 'all';
                }
                window.checkFilters.direction = nextValue;
                directionButtons.forEach(function(b) {
                    const val = b.getAttribute('data-filter-direction') || 'all';
                    b.classList.toggle('active', val === nextValue);
                });
                loadAndCategorizeChecks();
            });
        });

        const sourceButtons = document.querySelectorAll('[data-filter-source]');
        sourceButtons.forEach(function(btn) {
            btn.addEventListener('click', function() {
                const value = btn.getAttribute('data-filter-source') || 'all';
                const current = window.checkFilters.source;
                let nextValue = value;
                if (current === value && value !== 'all') {
                    nextValue = 'all';
                }
                window.checkFilters.source = nextValue;
                sourceButtons.forEach(function(b) {
                    const val = b.getAttribute('data-filter-source') || 'all';
                    b.classList.toggle('active', val === nextValue);
                });
                loadAndCategorizeChecks();
            });
        });

        const statusSelect = document.getElementById('filter-status');
        if (statusSelect) {
            statusSelect.addEventListener('change', function() {
                window.checkFilters.status = statusSelect.value || 'all';
                loadAndCategorizeChecks();
            });
        }
    }
    
    // عرض تفاصيل الشيك
    window.viewCheckDetails = function(checkId) {

        // استدعاء API للحصول على التفاصيل
        $.get('/checks/api/checks', function(response) {
            if (response.success && response.checks) {
                const check = response.checks.find(c => c.id == checkId || c.token === checkId || c.id == 'split-' + checkId || c.id == 'expense-' + checkId);
                
                if (check) {
                    const tokenReference = check.token || check.id;
                    const ledgerLines = [];
                    if (check.is_incoming) {
                        ledgerLines.push('تسجيل الشيك يزيد حساب الشيكات تحت التحصيل ويخفض ذمة العميل.');
                        ledgerLines.push('عند صرف الشيك تنتقل القيمة من الشيكات تحت التحصيل إلى البنك ويتم إقفال دين العميل.');
                        ledgerLines.push('إذا عاد الشيك يتم إعادة الدين على العميل وتُفتح متابعة تحصيل جديدة.');
                    } else {
                        ledgerLines.push('إصدار الشيك يسجل التزاماً على المورد أو المصروف في حساب الشيكات تحت الدفع.');
                        ledgerLines.push('عند صرف الشيك يتم تخفيض حساب الشيكات تحت الدفع وسحب المبلغ من البنك.');
                        ledgerLines.push('إذا أُلغي أو أُعيد الشيك يعود الالتزام على المورد ويُعاد ترتيب الرصيد.');
                    }
                    const statusMap = {
                        'PENDING': 'تابع مع البنك قبل موعد الاستحقاق بثلاثة أيام للتأكد من توفر الرصيد.',
                        'OVERDUE': 'يجب التواصل فوراً مع الجهة المعنية وتحديث الحالة لتفادي تضارب الأرصدة.',
                        'DUE_SOON': 'اقترب موعد الاستحقاق، حضّر الإيداع أو أكد استلام المبلغ نقداً.',
                        'CASHED': 'تم صرف الشيك، احتفظ بإثبات البنك وأغلق أي متابعات مفتوحة.',
                        'RETURNED': 'سجل مطالبة على الجهة وحدث رصيدها حتى تتم إعادة التقديم.',
                        'BOUNCED': 'يفضل تدوين سبب الرفض من البنك وإعادة جدولة السداد.',
                        'RESUBMITTED': 'الشيك قيد المتابعة في البنك، راجع حالة الرصيد خلال 48 ساعة.',
                        'CANCELLED': 'لا يؤثر على الرصيد الحالي ويمكن أرشفته نهائياً.',
                    };
                    const statusHint = statusMap[(check.status || '').toUpperCase()] || '';
                    const ledgerHtml = ledgerLines.length ? `
                        <h5 class="text-danger mb-2 mt-4"><i class="fas fa-balance-scale"></i> الأثر المحاسبي</h5>
                        <div class="alert alert-light border text-right" style="white-space: normal;">
                            <ul class="pl-3 mb-0">
                                ${ledgerLines.map(function(line) { return '<li>' + line + '</li>'; }).join('')}
                            </ul>
                        </div>
                    ` : '';
                    const guidanceHtml = statusHint ? `
                        <div class="alert alert-secondary text-right" style="white-space: normal;">
                            <strong>التوصية الحالية:</strong> ${statusHint}
                        </div>
                    ` : '';

                    // بناء HTML للتفاصيل الكاملة
                    let detailsHtml = `
                        <div class="text-right" dir="rtl" style="max-height: 600px; overflow-y: auto;">
                            <h5 class="text-primary mb-3"><i class="fas fa-money-check-alt"></i> معلومات الشيك الأساسية</h5>
                            <table class="table table-bordered table-sm">
                                <tr><th width="40%">رقم الشيك:</th><td><strong>${check.check_number || '-'}</strong></td></tr>
                                <tr><th>البنك:</th><td><i class="fas fa-university text-primary"></i> ${check.check_bank || '-'}</td></tr>
                                <tr><th>المبلغ:</th><td><strong class="text-success" style="font-size: 1.2em;">${formatCurrency(check.amount || 0)} ${check.currency || 'ILS'}</strong></td></tr>
                                ${check.currency && check.currency != 'ILS' ? '<tr><th>العملة:</th><td><span class="badge badge-secondary">' + check.currency + '</span></td></tr>' : ''}
                                ${check.currency && check.currency != 'ILS' && check.fx_rate_issue ? (function() { var rate = parseFloat(check.fx_rate_issue) || 0; var amt = (check.amount || 0) * (rate || 1); return '<tr class="bg-light"><th>💱 سعر الصرف (إصدار):</th><td><strong>' + (isNaN(rate) ? '0.0000' : rate.toFixed(4)) + '</strong> ' + (check.fx_rate_issue_source === 'online' ? '🌐' : check.fx_rate_issue_source === 'manual' ? '✍️' : '⚙️') + ' <small class="text-muted">(' + (check.fx_rate_issue_timestamp || '-') + ')</small><br><small class="text-info">المبلغ بالشيكل: ' + formatCurrency(amt) + ' ₪</small></td></tr>'; })() : ''}
                                ${check.currency && check.currency != 'ILS' && check.status === 'CASHED' && check.fx_rate_cash ? (function() { var rate = parseFloat(check.fx_rate_cash) || 0; var amt = (check.amount || 0) * (rate || 1); return '<tr class="bg-success text-white"><th>💰 سعر الصرف (صرف):</th><td><strong>' + (isNaN(rate) ? '0.0000' : rate.toFixed(4)) + '</strong> ' + (check.fx_rate_cash_source === 'online' ? '🌐' : check.fx_rate_cash_source === 'manual' ? '✍️' : '⚙️') + ' <small>(' + (check.fx_rate_cash_timestamp || '-') + ')</small><br><small>المبلغ الفعلي: <strong>' + formatCurrency(amt) + ' ₪</strong></small></td></tr>'; })() : ''}
                                ${check.currency && check.currency != 'ILS' && check.fx_rate_issue && check.fx_rate_cash && check.fx_rate_cash !== check.fx_rate_issue ? '<tr class="bg-warning"><th>📊 فرق سعر الصرف:</th><td><strong>' + formatCurrency((check.amount || 0) * (check.fx_rate_cash - check.fx_rate_issue)) + ' ₪</strong> ' + ((check.fx_rate_cash > check.fx_rate_issue) ? '<span class="badge badge-success">ربح ✓</span>' : '<span class="badge badge-danger">خسارة ✗</span>') + '</td></tr>' : ''}
                                <tr><th>تاريخ الاستحقاق:</th><td>${check.due_date_formatted || check.check_due_date || '-'}</td></tr>
                                ${check.days_until_due ? '<tr><th>الأيام المتبقية:</th><td><span class="badge badge-' + (check.days_until_due < 0 ? 'danger' : check.days_until_due <= 7 ? 'warning' : 'info') + '">' + check.days_until_due + ' يوم</span></td></tr>' : ''}
                                <tr><th>رمز المتابعة:</th><td><code>${tokenReference || '-'}</code></td></tr>
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
                            ${ledgerHtml}
                            ${guidanceHtml}
                            
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
    window.markAsCashed = function(checkToken) {
        updateCheckStatus(checkToken, 'CASHED', 'تم السحب');
    };
    
    // تحديث حالة الشيك إلى مرتجع
    window.markAsReturned = function(checkToken) {
        updateCheckStatus(checkToken, 'RETURNED', 'تم إرجاع الشيك من البنك', { return_reason: 'BANK' });
    };
    
    // تحديث حالة الشيك إلى ملغي
    window.markAsCancelled = function(checkToken) {
        updateCheckStatus(checkToken, 'CANCELLED', 'تم إلغاء الشيك');
    };
    
    // إعادة تقديم الشيك للبنك (للشيكات المرتجعة)
    window.resubmitCheck = function(checkToken) {
        updateCheckStatus(checkToken, 'RESUBMITTED', 'تم إعادة تقديم الشيك للبنك', { return_reason: 'BANK' });
    };
    
    // أرشفة الشيك
    window.archiveCheck = function(checkToken) {
        updateCheckStatus(checkToken, 'CANCELLED', 'تم إلغاء الشيك (أرشفة)');
    };

    window.restoreCheck = function(checkToken) {
        updateCheckStatus(checkToken, 'PENDING', 'تم استعادة الشيك للحالة المعلقة');
    };

    window.openCheckEditor = function(buttonEl) {
        if (!IS_OWNER) {
            Swal.fire('تنبيه', 'هذا الإجراء متاح للمالك فقط.', 'warning');
            return;
        }
        const el = buttonEl;
        const token = el.getAttribute('data-token');
        const entityType = (el.getAttribute('data-entity-type') || '').toUpperCase();
        const entityId = el.getAttribute('data-entity-id') || '';
        const dueDate = el.getAttribute('data-due-date') || '';
        const amount = el.getAttribute('data-amount') || '';
        const currency = el.getAttribute('data-currency') || 'ILS';
        const bank = el.getAttribute('data-bank') || '';
        const checkNumber = el.getAttribute('data-check-number') || token;

        $.ajax({
            url: '/checks/api/get-details/' + token,
            method: 'GET',
            xhrFields: { withCredentials: true }
        }).then(function(response) {
            if (!response.success) {
                throw new Error(response.message || 'فشل جلب البيانات');
            }
            const resubmitCount = response.resubmit_allowed_count || 1;
            const legalReturnCount = response.legal_return_allowed_count || 1;

            const selectOptions = [
                { value: '', label: '-- بدون تغيير --' },
                { value: 'CUSTOMER', label: 'عميل' },
                { value: 'SUPPLIER', label: 'مورد' },
                { value: 'PARTNER', label: 'شريك' },
            ].map(opt => `<option value="${opt.value}" ${opt.value === entityType ? 'selected' : ''}>${opt.label}</option>`).join('');

            const html = `
                <div class="text-right" dir="rtl">
                    <label class="d-block font-weight-bold mb-1">نوع الجهة</label>
                    <select id="check-edit-entity-type" class="swal2-input" style="width:100%;">${selectOptions}</select>
                    <label class="d-block font-weight-bold mt-3 mb-1">معرّف الجهة</label>
                    <input type="number" id="check-edit-entity-id" class="swal2-input" placeholder="ID" value="${htmlEscape(entityId)}">
                    <label class="d-block font-weight-bold mt-3 mb-1">تاريخ الاستحقاق</label>
                    <input type="date" id="check-edit-due-date" class="swal2-input" value="${htmlEscape(dueDate)}">
                    <label class="d-block font-weight-bold mt-3 mb-1">المبلغ</label>
                    <input type="number" step="0.01" id="check-edit-amount" class="swal2-input" value="${htmlEscape(amount)}">
                    <label class="d-block font-weight-bold mt-3 mb-1">العملة</label>
                    <input type="text" id="check-edit-currency" class="swal2-input" value="${htmlEscape(currency)}">
                    <label class="d-block font-weight-bold mt-3 mb-1">البنك</label>
                    <input type="text" id="check-edit-bank" class="swal2-input" value="${htmlEscape(bank)}">
                    <hr style="margin: 15px 0;">
                    <label class="d-block font-weight-bold mt-3 mb-1">عدد مرات السماح بإعادة الإرسال للبنك</label>
                    <input type="number" min="1" id="check-edit-resubmit-count" class="swal2-input" value="${resubmitCount}" placeholder="الافتراضي: 1">
                    <small class="text-muted d-block mt-1">زيادة هذا العدد يسمح بإعادة إرسال الشيك للبنك أكثر من مرة</small>
                    <label class="d-block font-weight-bold mt-3 mb-1">عدد مرات السماح بالرجوع من الحالة القانونية</label>
                    <input type="number" min="1" id="check-edit-legal-return-count" class="swal2-input" value="${legalReturnCount}" placeholder="الافتراضي: 1">
                    <small class="text-muted d-block mt-1">زيادة هذا العدد يسمح بإرجاع الشيك من الحالة القانونية أكثر من مرة</small>
                </div>
            `;

            Swal.fire({
                title: `تعديل الشيك ${htmlEscape(checkNumber)}`,
                html: html,
                focusConfirm: false,
                showCancelButton: true,
                confirmButtonText: 'حفظ',
                cancelButtonText: 'إلغاء',
                preConfirm: () => {
                    const selectedType = document.getElementById('check-edit-entity-type').value;
                    const selectedId = (document.getElementById('check-edit-entity-id').value || '').trim();
                    const dueDateVal = document.getElementById('check-edit-due-date').value;
                    const amountVal = document.getElementById('check-edit-amount').value;
                    const currencyVal = (document.getElementById('check-edit-currency').value || 'ILS').toUpperCase();
                    const bankVal = document.getElementById('check-edit-bank').value;
                    const resubmitCount = document.getElementById('check-edit-resubmit-count').value;
                    const legalReturnCount = document.getElementById('check-edit-legal-return-count').value;

                    const amountNum = parseFloat(amountVal) || 0;
                    if (!amountVal || isNaN(amountNum) || amountNum <= 0) {
                        Swal.showValidationMessage('يرجى إدخال مبلغ صحيح أكبر من صفر.');
                        return false;
                    }
                    if (selectedType && !selectedId) {
                        Swal.showValidationMessage('يرجى إدخال معرف الجهة عند اختيار نوع جهة.');
                        return false;
                    }
                    const result = {
                        entity_type: selectedType,
                        entity_id: selectedId || null,
                        due_date: dueDateVal || null,
                        amount: amountVal,
                        currency: currencyVal || 'ILS',
                        bank: bankVal
                    };
                    if (resubmitCount) {
                        const count = parseInt(resubmitCount);
                        if (!isNaN(count) && count >= 1) {
                            result.resubmit_allowed_count = count;
                        }
                    }
                    if (legalReturnCount) {
                        const count = parseInt(legalReturnCount);
                        if (!isNaN(count) && count >= 1) {
                            result.legal_return_allowed_count = count;
                        }
                    }
                    return result;
                }
            }).then((result) => {
                if (!result.isConfirmed || !token) {
                    return;
                }
                $.ajax({
                    url: '/checks/api/update-details/' + token,
                    method: 'POST',
                    contentType: 'application/json',
                    xhrFields: { withCredentials: true },
                    data: JSON.stringify(result.value)
                }).then(response => {
                    if (!response.success) {
                        throw new Error(response.message || 'فشل التحديث');
                    }
                    Swal.fire({
                        title: 'تم الحفظ',
                        text: 'تم تعديل بيانات الشيك بنجاح.',
                        icon: 'success',
                        timer: 2000
                    });
                    setTimeout(() => loadAndCategorizeChecks(), 600);
                }).catch(error => {
                    const msg = error.responseJSON?.message || error.message || 'حدث خطأ غير متوقع';
                    Swal.fire('خطأ', msg, 'error');
                });
            });
        }).catch(error => {
            const msg = error.responseJSON?.message || error.message || 'حدث خطأ غير متوقع';
            Swal.fire('خطأ', msg, 'error');
        });
    };

    window.openCheckSettlement = function(buttonEl) {
        if (!IS_OWNER) {
            Swal.fire('تنبيه', 'هذا الإجراء متاح للمالك فقط.', 'warning');
            return;
        }
        const el = buttonEl;
        const token = el.getAttribute('data-token');
        const entityType = (el.getAttribute('data-entity-type') || '').toUpperCase();
        const entityId = el.getAttribute('data-entity-id');
        const checkNumber = el.getAttribute('data-check-number') || token;
        const amount = el.getAttribute('data-amount') || '';
        const currency = el.getAttribute('data-currency') || 'ILS';
        if (!token) {
            Swal.fire('تنبيه', 'لا يمكن تحديد هذا الشيك.', 'warning');
            return;
        }
        if (!entityType || !entityId) {
            Swal.fire('تنبيه', 'لا يمكن فتح تسوية مالية لهذا الشيك لأن الجهة غير معروفة.', 'warning');
            return;
        }
        Swal.fire({
            title: 'تسوية الشيك',
            text: 'سيتم فتح نموذج الدفع لتسجيل التسوية. سيتم تعليم الشيك كمسوّى بعد إكمال الدفعة وحفظها.',
            icon: 'info',
            showCancelButton: true,
            confirmButtonText: 'فتح نموذج الدفع',
            cancelButtonText: 'إلغاء'
        }).then((result) => {
            if (!result.isConfirmed) {
                return;
            }
            const params = new URLSearchParams({
                entity_type: entityType,
                entity_id: entityId,
                amount: amount,
                currency: currency,
                notes: `تسوية شيك مرتجع رقم ${checkNumber}`,
                reference: `CHK-SETTLE-${checkNumber}`,
                check_token: token
            });
            window.location.href = '/payments/create?' + params.toString();
        });
    };

    window.unsettleCheck = function(checkToken) {
        if (!IS_OWNER) {
            Swal.fire('تنبيه', 'هذا الإجراء متاح للمالك فقط.', 'warning');
            return;
        }
        Swal.fire({
            title: 'إلغاء التسوية',
            text: 'سيتم إلغاء تسوية الشيك وإرجاعه لحالته السابقة. إذا تم إنشاء قيود محاسبية، سيتم عكسها.',
            icon: 'warning',
            showCancelButton: true,
            confirmButtonText: 'نعم، إلغاء التسوية',
            cancelButtonText: 'إلغاء',
            showLoaderOnConfirm: true,
            preConfirm: () => {
                return $.ajax({
                    url: '/checks/api/unsettle/' + checkToken,
                    method: 'POST',
                    contentType: 'application/json',
                    xhrFields: { withCredentials: true },
                    data: JSON.stringify({})
                }).then(response => {
                    if (!response.success) {
                        throw new Error(response.message || 'فشل إلغاء التسوية');
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
                    icon: 'success',
                    title: 'تم إلغاء التسوية',
                    text: 'تم إلغاء تسوية الشيك بنجاح وإرجاعه لحالته السابقة.',
                    timer: 2000,
                    showConfirmButton: false
                }).then(() => {
                    loadAndCategorizeChecks();
                });
            }
        });
    };

    window.markAsLegal = function(checkToken) {
        if (!IS_OWNER) {
            Swal.fire('تنبيه', 'هذا الإجراء متاح للمالك فقط.', 'warning');
            return;
        }
        Swal.fire({
            title: 'تحويل للدائرة القانونية',
            text: 'سيتم تحويل الشيك للدائرة القانونية ولن يكون متاحاً لأي إجراء لاحق.',
            icon: 'warning',
            showCancelButton: true,
            confirmButtonText: 'نعم، تحويل قانوني',
            cancelButtonText: 'إلغاء',
            showLoaderOnConfirm: true,
            preConfirm: () => {
                return $.ajax({
                    url: '/checks/api/update-status/' + checkToken,
                    method: 'POST',
                    contentType: 'application/json',
                    xhrFields: {
                        withCredentials: true
                    },
                    data: JSON.stringify({
                        status: 'CANCELLED',
                        notes: 'تم تحويل الشيك للدائرة القانونية'
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
                const response = result.value || {};
                let successHtml = 'تم تحويل الشيك للدائرة القانونية.';
                if (response.balance !== undefined && response.balance !== null) {
                    successHtml += `<br>الرصيد الحالي: ${formatCurrency(response.balance)} ₪`;
                }
                Swal.fire({
                    title: 'تم!',
                    html: successHtml,
                    icon: 'success',
                    timer: 2200
                });
                setTimeout(() => loadAndCategorizeChecks(), 500);
            }
        });
    };
    
    // دالة مشتركة لتحديث حالة الشيك
    function updateCheckStatus(checkToken, newStatus, message, extra) {
        const statusInfo = {
            'CASHED': {
                title: 'تأكيد السحب',
                text: 'تم صرف الشيك من البنك؟',
                icon: 'question',
                confirmText: 'نعم، تم السحب',
                successText: 'تم تحديث حالة الشيك إلى "مسحوب".'
            },
            'RETURNED': {
                title: 'تأكيد الإرجاع',
                text: 'هل تم إرجاع الشيك من البنك؟',
                icon: 'warning',
                confirmText: 'نعم، تم الإرجاع',
                successText: 'تم تحديث حالة الشيك إلى "مرتجع".'
            },
            'CANCELLED': {
                title: 'تأكيد الإلغاء',
                text: 'هل تريد إلغاء هذا الشيك؟',
                icon: 'warning',
                confirmText: 'نعم، إلغاء',
                successText: 'تم تحديث حالة الشيك إلى "ملغي".'
            },
            'RESUBMITTED': {
                title: 'إعادة تقديم للبنك',
                text: 'سيتم وضع الشيك في حالة انتظار جديدة.',
                icon: 'info',
                confirmText: 'تأكيد',
                successText: 'تم إعادة تقديم الشيك للبنك.'
            },
            'PENDING': {
                title: 'استعادة الشيك',
                text: 'سيعود الشيك لقائمة الشيكات المعلقة.',
                icon: 'info',
                confirmText: 'استعادة',
                successText: 'تم استعادة الشيك للحالة المعلقة.'
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
                    url: '/checks/api/update-status/' + checkToken,
                    method: 'POST',
                    contentType: 'application/json',
                    xhrFields: {
                        withCredentials: true
                    },
                    data: JSON.stringify(Object.assign({
                        status: newStatus,
                        notes: message
                    }, extra || {}))
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
                const response = result.value || {};
                let msg = response.message || info.successText || '';
                const local = (window.checksByToken && window.checksByToken[checkToken]) ? window.checksByToken[checkToken] : null;
                const amt = (typeof response.amount !== 'undefined' && response.amount !== null) ? response.amount : (local ? (local.amount || 0) : null);
                const cur = (response.currency || (local ? (local.currency || 'ILS') : 'ILS')) || 'ILS';
                const dir = (response.direction || (local && local.is_incoming ? 'IN' : 'OUT')) || null;
                const entName = local ? (local.entity_name || null) : null;
                const entType = (response.entity_type || '').toString().toLowerCase();
                const entId = response.entity_id || null;
                let details = '';
                if (amt !== null) {
                    const isILS = String(cur || 'ILS').toUpperCase() === 'ILS';
                    const currencyDisplay = isILS ? '₪' : String(cur).toUpperCase();
                    details += `<br>المبلغ: <strong>${formatCurrency(parseFloat(amt) || 0)} ${currencyDisplay}</strong>`;
                }
                if (dir) {
                    const dirAr = (String(dir).toUpperCase() === 'IN') ? 'وارد' : 'صادر';
                    details += ` <span class="badge badge-${String(dir).toUpperCase() === 'IN' ? 'success' : 'danger'}">${dirAr}</span>`;
                }
                if (entName || entType || entId) {
                    const typeAr = (function(t){
                        if (t === 'customer') return 'عميل';
                        if (t === 'supplier') return 'مورد';
                        if (t === 'partner') return 'شريك';
                        return '';
                    })(entType);
                    const entDisp = entName ? entName : (typeAr ? `${typeAr} #${entId || ''}` : (entId ? `#${entId}` : ''));
                    if (entDisp) details += `<br>الجهة المرتبطة: <strong>${entDisp}</strong>`;
                }
                if (response.balance !== undefined && response.balance !== null) {
                    details += `<br>الرصيد بعد التحديث: ${formatCurrency(response.balance)} ₪`;
                }
                Swal.fire({
                    title: 'تم!',
                    html: `${msg}${details}`,
                    icon: 'success',
                    timer: 2200
                }).then(() => {
                    const nextList = (response.next_list || '').toString();
                    if (nextList) {
                        if (typeof window.switchToTab === 'function') {
                            window.switchToTab(nextList);
                        }
                    }
                });
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
    window.switchToTab = function(listKey) {
        if (!listKey) return;
        var key = String(listKey).toLowerCase();
        var selector = '#tab-' + key;
        $('.nav-link[data-toggle="pill"]').removeClass('active');
        $('.nav-link[href="' + selector + '"]').addClass('active');
        $('.tab-pane').removeClass('active show');
        $(selector).addClass('active show');
        window.scrollTo({ top: 0, behavior: 'smooth' });
    };
    
    // عند تحميل الصفحة
    $(document).ready(function() {
        initCheckFilters();
        // تحميل فوري
        setTimeout(function() {
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
})();
