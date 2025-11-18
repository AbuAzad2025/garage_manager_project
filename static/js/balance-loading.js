(function() {
    const style = document.createElement('style');
    style.textContent = `
        .balance-loading {
            position: relative;
            opacity: 0.6;
        }
        .balance-loading::after {
            content: "";
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            width: 16px;
            height: 16px;
            border: 2px solid #f3f3f3;
            border-top: 2px solid #3498db;
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }
        @keyframes spin {
            0% { transform: translate(-50%, -50%) rotate(0deg); }
            100% { transform: translate(-50%, -50%) rotate(360deg); }
        }
        .balance-loaded {
            animation: fadeIn 0.3s ease-in;
        }
        @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
        }
    `;
    document.head.appendChild(style);
    
    window.showBalanceLoading = function(element) {
        if (element) {
            element.classList.add('balance-loading');
        }
    };
    
    window.hideBalanceLoading = function(element) {
        if (element) {
            element.classList.remove('balance-loading');
            element.classList.add('balance-loaded');
            setTimeout(() => {
                element.classList.remove('balance-loaded');
            }, 300);
        }
    };
    
    window.loadBalanceAsync = async function(entityType, entityId, targetElement) {
        showBalanceLoading(targetElement);
        
        try {
            const response = await fetch(`/api/balances/${entityType}/${entityId}`);
            const data = await response.json();
            
            if (data.success && targetElement) {
                const balance = data.balance || 0;
                const formatted = new Intl.NumberFormat('ar-EG', {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2
                }).format(Math.abs(balance));
                
                targetElement.textContent = formatted + ' ₪';
                
                targetElement.classList.remove('bg-danger', 'bg-success', 'bg-secondary');
                if (balance > 0) {
                    targetElement.classList.add('bg-success');
                } else if (balance < 0) {
                    targetElement.classList.add('bg-danger');
                } else {
                    targetElement.classList.add('bg-secondary');
                }
            }
        } catch (error) {
            if (targetElement) {
                targetElement.textContent = 'خطأ';
                targetElement.classList.add('bg-warning');
            }
        } finally {
            hideBalanceLoading(targetElement);
        }
    };
})();

