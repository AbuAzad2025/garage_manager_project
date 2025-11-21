window.FXUtils = {
    formatFxRate: function(rate, source, decimals = 4) {
        if (!rate || rate <= 0) return '<span class="text-muted">-</span>';
        
        const rateNum = parseFloat(rate) || 0;
        if (isNaN(rateNum)) return '<span class="text-muted">-</span>';
        const formattedRate = rateNum.toFixed(decimals);
        let icon = '';
        
        if (source) {
            switch (source.toLowerCase()) {
                case 'online':
                    icon = '🌐';
                    break;
                case 'manual':
                    icon = '✍️';
                    break;
                case 'default':
                    icon = '⚙️';
                    break;
                default:
                    icon = '💱';
            }
        }
        
        return `<small class="text-muted">${formattedRate} ${icon}</small>`;
    },

    formatCurrencyBadge: function(currency) {
        const curr = currency || 'ILS';
        return `<span class="badge badge-secondary">${curr}</span>`;
    },

    convertAmount: function(amount, rate, fromCurrency, toCurrency = 'ILS') {
        if (!amount || !rate || fromCurrency === toCurrency) return amount;
        return parseFloat(amount) * parseFloat(rate);
    },

    formatConvertedAmount: function(amount, currency, rate, targetCurrency = 'ILS', targetSymbol = '₪') {
        if (!amount) return '0.00';
        
        if (currency === targetCurrency || !rate) {
            const amtNum = parseFloat(amount) || 0;
            return `${isNaN(amtNum) ? '0.00' : amtNum.toFixed(2)} ${targetSymbol}`;
        }
        
        const converted = this.convertAmount(amount, rate, currency, targetCurrency);
        const convertedNum = parseFloat(converted) || 0;
        return `${isNaN(convertedNum) ? '0.00' : convertedNum.toFixed(2)} ${targetSymbol}`;
    },

    createFxRateColumn: function(fxRateField = 'fx_rate_used', currencyField = 'currency', fxSourceField = 'fx_rate_source') {
        return {
            data: null,
            className: 'text-center',
            orderable: false,
            searchable: false,
            render: function(data, type, row) {
                const rate = row[fxRateField];
                const currency = row[currencyField];
                const source = row[fxSourceField];
                
                if (rate && currency && currency !== 'ILS') {
                    return FXUtils.formatFxRate(rate, source);
                }
                return '<span class="text-muted">-</span>';
            }
        };
    },

    createCurrencyColumn: function(currencyField = 'currency') {
        return {
            data: currencyField,
            className: 'text-center',
            render: function(currency) {
                return FXUtils.formatCurrencyBadge(currency);
            }
        };
    },

    enhanceAmountDisplay: function(amountText, rate, currency, source) {
        if (!rate || currency === 'ILS') return amountText;
        
        const fxInfo = this.formatFxRate(rate, source);
        return `${amountText}<br><small class="text-muted">${fxInfo}</small>`;
    }
};

// Make it available globally
window.FX = window.FXUtils;
