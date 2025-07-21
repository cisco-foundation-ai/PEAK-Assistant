/* ==========================================================================
   MODERN UI ARCHITECTURE - Core Components and API Client
   ========================================================================== */

/**
 * Centralized API Client for all backend communication
 */
class APIClient {
    constructor() {
        this.baseURL = '';
        this.defaultRetryCount = 3;
        this.defaultTimeout = 300000; // 5 minutes
    }
    
    getRetryCount() {
        const stored = localStorage.getItem('retryCount') || localStorage.getItem('retry-count-page');
        return stored ? parseInt(stored, 10) || this.defaultRetryCount : this.defaultRetryCount;
    }
    
    getVerboseMode() {
        return localStorage.getItem('verboseMode') === 'true' || 
               localStorage.getItem('debug-mode-page') === 'true';
    }
    
    async delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
    
    async callWithRetry(endpoint, data = {}, options = {}) {
        const retryCount = options.retryCount || this.getRetryCount();
        const verboseMode = options.verboseMode !== undefined ? options.verboseMode : this.getVerboseMode();
        
        const requestData = {
            ...data,
            retry_count: retryCount,
            verbose_mode: verboseMode
        };
        
        for (let attempt = 1; attempt <= retryCount; attempt++) {
            try {
                const response = await fetch(endpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(requestData)
                });
                
                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({}));
                    throw new Error(errorData.error || `HTTP ${response.status}`);
                }
                
                const result = await response.json();
                document.dispatchEvent(new CustomEvent('sessionStateChanged'));
                return result;
            } catch (error) {
                if (attempt === retryCount) {
                    throw error;
                }
                await this.delay(1000 * attempt); // Exponential backoff
            }
        }
    }

    async uploadFile(endpoint, formData) {
        try {
            const response = await fetch(endpoint, {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.error || `HTTP ${response.status}`);
            }

            const result = await response.json();
            document.dispatchEvent(new CustomEvent('sessionStateChanged'));
            return result;
        } catch (error) {
            console.error('Upload failed:', error);
            throw error;
        }
    }
}

// Create global API client instance
window.apiClient = new APIClient();
