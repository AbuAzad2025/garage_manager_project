/**
 * FX Utils - JavaScript utilities for displaying exchange rates
 * Utility functions to display FX rates consistently across all templates
 */

window.FXUtils = {
    /**
     * Format FX rate display with source icon
     * @param {number} rate - The exchange rate
     * @param {string} source - The source of the rate (online, manual, default)
     * @param {number} decimals - Number of decimal places (default: 4)
     * @returns {string} Formatted FX rate with icon
     */
    formatFxRate: function(rate, source, decimals = 4) {
        if (!rate || rate <= 0) return '<span class="text-muted">-</span>';
        
        const formattedRate = parseFloat(rate).toFixed(decimals);
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

    /**
     * Format currency badge
     * @param {string} currency - Currency code
     * @returns {string} Formatted currency badge
     */
    formatCurrencyBadge: function(currency) {
        const curr = currency || 'ILS';
        return `<span class="badge badge-secondary">${curr}</span>`;
    },

    /**
     * Calculate converted amount
     * @param {number} amount - Original amount
     * @param {number} rate - Exchange rate
     * @param {string} fromCurrency - Source currency
     * @param {string} toCurrency - Target currency (default: ILS)
     * @returns {number} Converted amount
     */
    convertAmount: function(amount, rate, fromCurrency, toCurrency = 'ILS') {
        if (!amount || !rate || fromCurrency === toCurrency) return amount;
        return parseFloat(amount) * parseFloat(rate);
    },

    /**
     * Format converted amount display
     * @param {number} amount - Original amount
     * @param {string} currency - Original currency
     * @param {number} rate - Exchange rate
     * @param {string} targetCurrency - Target currency (default: ILS)
     * @param {string} targetSymbol - Target currency symbol (default: ₪)
     * @returns {string} Formatted converted amount
     */
    formatConvertedAmount: function(amount, currency, rate, targetCurrency = 'ILS', targetSymbol = '₪') {
        if (!amount) return '0.00';
        
        if (currency === targetCurrency || !rate) {
            return `${parseFloat(amount).toFixed(2)} ${targetSymbol}`;
        }
        
        const converted = this.convertAmount(amount, rate, currency, targetCurrency);
        return `${converted.toFixed(2)} ${targetSymbol}`;
    },

    /**
     * Create FX rate column for DataTables
     * @param {string} fxRateField - Field name for FX rate (default: 'fx_rate_used')
     * @param {string} currencyField - Field name for currency (default: 'currency')
     * @param {string} fxSourceField - Field name for FX source (default: 'fx_rate_source')
     * @returns {object} DataTables column configuration
     */
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

    /**
     * Create currency column for DataTables
     * @param {string} currencyField - Field name for currency (default: 'currency')
     * @returns {object} DataTables column configuration
     */
    createCurrencyColumn: function(currencyField = 'currency') {
        return {
            data: currencyField,
            className: 'text-center',
            render: function(currency) {
                return FXUtils.formatCurrencyBadge(currency);
            }
        };
    },

    /**
     * Add FX info to existing amount display
     * @param {string} amountText - Current amount text
     * @param {number} rate - Exchange rate
     * @param {string} currency - Original currency
     * @param {string} source - FX source
     * @returns {string} Enhanced amount display with FX info
     */
    enhanceAmountDisplay: function(amountText, rate, currency, source) {
        if (!rate || currency === 'ILS') return amountText;
        
        const fxInfo = this.formatFxRate(rate, source);
        return `${amountText}<br><small class="text-muted">${fxInfo}</small>`;
    }
};

// Make it available globally
window.FX = window.FXUtils;
