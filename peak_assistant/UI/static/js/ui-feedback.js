/**
 * Centralized UI feedback management
 */
class UIFeedback {
    static show(type, message, detail = null, duration = null) {
        switch (type) {
            case 'loading':
                this.showLoading(message);
                break;
            case 'success':
                this.showSuccess(message, duration);
                break;
            case 'error':
                this.showError(message, detail);
                break;
        }
    }
    
    static showLoading(message = "Processing...") {
        document.getElementById('loading-message').textContent = message;
        document.getElementById('loading-indicator').style.display = 'flex';
    }
    
    static hideLoading() {
        document.getElementById('loading-indicator').style.display = 'none';
    }
    
    static showError(message, detail = null) {
        const errorToastEl = document.getElementById('error-toast');
        const toast = new bootstrap.Toast(errorToastEl);
        document.getElementById('error-message-text').textContent = message;

        const detailsBtn = document.getElementById('show-error-details');
        const detailsContent = document.getElementById('error-details-content');

        if (detail) {
            detailsContent.textContent = typeof detail === 'object' ? JSON.stringify(detail, null, 2) : detail;
            detailsBtn.style.display = 'inline';
            detailsContent.style.display = 'none'; 
        } else {
            detailsBtn.style.display = 'none';
            detailsContent.style.display = 'none';
        }
        toast.show();
    }
    
    static hideError() {
        const errorToastEl = document.getElementById('error-toast');
        const toast = bootstrap.Toast.getInstance(errorToastEl);
        if (toast) {
            toast.hide();
        }
        document.getElementById('error-details-content').style.display = 'none';
        document.getElementById('show-error-details').style.display = 'none';
    }

    static showSuccess(message, duration = 5000) {
        const successToastEl = document.getElementById('success-toast-container');
        // Ensure delay is always a valid number, default to 5000ms if invalid
        const delay = (typeof duration === 'number' && duration > 0) ? duration : 5000;
        const toast = bootstrap.Toast.getOrCreateInstance(successToastEl, { delay: delay });
        document.getElementById('success-toast-body').textContent = message;
        toast.show();
    }
}

// Make UIFeedback available globally
window.UIFeedback = UIFeedback;
