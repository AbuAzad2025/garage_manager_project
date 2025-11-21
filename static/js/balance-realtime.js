(function() {
    if (typeof io === 'undefined') return;
    
    const socket = io();
    
    socket.on('balance_updated', function(data) {
        const entityType = data.entity_type;
        const entityId = data.entity_id;
        const newBalance = Number(data.balance) || 0;
        
        const balanceElements = document.querySelectorAll(`[data-balance-${entityType}="${entityId}"]`);
        balanceElements.forEach(balanceElement => {
            if (balanceElement) {
                const formatted = new Intl.NumberFormat('ar-EG', {
                    style: 'currency',
                    currency: 'ILS',
                    minimumFractionDigits: 2
                }).format(newBalance);
                
                balanceElement.textContent = formatted;
                
                balanceElement.classList.remove('bg-danger', 'bg-success', 'bg-secondary', 'text-danger', 'text-success', 'text-secondary');
                if (newBalance > 0) {
                    balanceElement.classList.add('text-success');
                    if (balanceElement.classList.contains('bg-')) {
                        balanceElement.classList.add('bg-success');
                    }
                } else if (newBalance < 0) {
                    balanceElement.classList.add('text-danger');
                    if (balanceElement.classList.contains('bg-')) {
                        balanceElement.classList.add('bg-danger');
                    }
                } else {
                    balanceElement.classList.add('text-secondary');
                    if (balanceElement.classList.contains('bg-')) {
                        balanceElement.classList.add('bg-secondary');
                    }
                }
                
                balanceElement.classList.add('animate__animated', 'animate__pulse');
                setTimeout(() => {
                    balanceElement.classList.remove('animate__animated', 'animate__pulse');
                }, 1000);
            }
        });
    });
    
    socket.on('balances_summary_updated', function(data) {
        if (data.suppliers) {
            updateSummaryCard('suppliers', data.suppliers);
        }
        if (data.partners) {
            updateSummaryCard('partners', data.partners);
        }
        if (data.customers) {
            updateSummaryCard('customers', data.customers);
        }
    });
    
    function updateSummaryCard(entityType, summaryData) {
        const card = document.getElementById(`${entityType}-summary`);
        if (!card) return;
        
        if (summaryData.total_balance !== undefined) {
            const balanceEl = card.querySelector('.total-balance');
            if (balanceEl) {
                const balance = Number(summaryData.total_balance) || 0;
                balanceEl.textContent = balance.toFixed(2) + ' ₪';
            }
        }
        
        if (summaryData.count !== undefined) {
            const countEl = card.querySelector('.entity-count');
            if (countEl) {
                countEl.textContent = Number(summaryData.count) || 0;
            }
        }
    }
})();

