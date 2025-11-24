document.addEventListener('DOMContentLoaded', function() {
    const trainingStatusInterval = 3000;
    let trainingPollInterval = null;
    let currentJobId = null;

    function showTrainingAlert(message, type = 'info') {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
        alertDiv.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
        alertDiv.innerHTML = `
            <strong>${type === 'success' ? '✅' : type === 'warning' ? '⚠️' : type === 'info' ? 'ℹ️' : '❌'}</strong> ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        document.body.appendChild(alertDiv);
        
        setTimeout(() => {
            if (alertDiv.parentNode) {
                alertDiv.remove();
            }
        }, 5000);
    }

    function updateTrainingProgress(jobId) {
        if (!jobId) return;
        
        fetch(`/ai/training/status/${jobId}`)
            .then(response => response.json())
            .then(data => {
                if (data.success && data.job) {
                    const job = data.job;
                    updateProgressUI(job);
                    
                    if (job.status === 'completed' || job.status === 'failed') {
                        stopPolling();
                        if (job.status === 'completed') {
                            showTrainingAlert('✅ تم إكمال التدريب بنجاح!', 'success');
                        } else {
                            showTrainingAlert(`❌ فشل التدريب: ${job.error || 'خطأ غير معروف'}`, 'danger');
                        }
                    }
                }
            })
            .catch(error => {
                console.error('Error fetching training status:', error);
            });
    }

    function updateProgressUI(job) {
        const progressBars = document.querySelectorAll(`[data-job-id="${job.job_id}"]`);
        progressBars.forEach(bar => {
            const progressBar = bar.querySelector('.training-progress-bar');
            const progressText = bar.querySelector('.training-progress-text');
            const statusBadge = bar.querySelector('.training-status-badge');
            
            if (progressBar) {
                progressBar.style.width = `${job.progress}%`;
                progressBar.setAttribute('aria-valuenow', job.progress);
            }
            
            if (progressText) {
                progressText.textContent = `${job.progress}% - ${getStatusText(job.status)}`;
            }
            
            if (statusBadge) {
                statusBadge.className = `badge training-status-badge bg-${getStatusColor(job.status)}`;
                statusBadge.textContent = getStatusText(job.status);
            }
        });
        
        const trainingLogs = document.getElementById('training-logs');
        if (trainingLogs && job.logs) {
            const logEntry = document.createElement('div');
            logEntry.className = 'log-entry';
            logEntry.innerHTML = `
                <small class="text-muted">${new Date().toLocaleTimeString('ar-SA')}</small>
                <span class="ms-2">${getStatusText(job.status)} - ${job.progress}%</span>
            `;
            trainingLogs.appendChild(logEntry);
            trainingLogs.scrollTop = trainingLogs.scrollHeight;
        }
    }

    function getStatusText(status) {
        const statusMap = {
            'running': 'قيد التنفيذ...',
            'analyzing': 'جارٍ التحليل...',
            'completed': 'مكتمل',
            'failed': 'فشل',
            'pending': 'في الانتظار'
        };
        return statusMap[status] || status;
    }

    function getStatusColor(status) {
        const colorMap = {
            'running': 'primary',
            'analyzing': 'info',
            'completed': 'success',
            'failed': 'danger',
            'pending': 'secondary'
        };
        return colorMap[status] || 'secondary';
    }

    function startPolling(jobId) {
        if (trainingPollInterval) {
            clearInterval(trainingPollInterval);
        }
        
        currentJobId = jobId;
        updateTrainingProgress(jobId);
        
        trainingPollInterval = setInterval(() => {
            updateTrainingProgress(jobId);
        }, trainingStatusInterval);
    }

    function stopPolling() {
        if (trainingPollInterval) {
            clearInterval(trainingPollInterval);
            trainingPollInterval = null;
        }
        currentJobId = null;
    }

    window.startTrainingProgress = function(jobId) {
        startPolling(jobId);
        showTrainingAlert('🚀 بدء التدريب... سيتم تحديث التقدم تلقائياً', 'info');
    };

    window.stopTrainingProgress = function() {
        stopPolling();
    };

    if (window.currentTrainingJobId) {
        startPolling(window.currentTrainingJobId);
    }
});

