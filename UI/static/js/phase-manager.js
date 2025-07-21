/**
 * Standardized Phase Manager for consistent workflow handling
 */
class PhaseManager {
    constructor(phaseId, config = {}) {
        this.phaseId = phaseId;
        this.config = {
            apiEndpoint: config.apiEndpoint,
            contentContainer: config.contentContainer,
            downloadContainer: config.downloadContainer,
            prerequisites: config.prerequisites || [],
            sessionStorageKey: config.sessionStorageKey,
            globalContentVar: config.globalContentVar,
            ...config
        };
        
        this.apiClient = new APIClient();
        this.setupEventListeners();
        this.loadInitialData();
        this.checkPrerequisites();
    }
    
    setupEventListeners() {
        // Override in subclasses
    }
    
    async loadInitialData() {
        console.log(`[${this.phaseId}] 1. Starting loadInitialData.`);
        const stored = sessionStorage.getItem(this.config.sessionStorageKey);
        console.log(`[${this.phaseId}] 2. Checked sessionStorage for key '${this.config.sessionStorageKey}'. Found content length: ${stored ? stored.length : 'null'}`);

        let finalContent = '';
        if (stored && stored.trim()) {
            console.log(`[${this.phaseId}] 3a. Found data in sessionStorage.`);
            finalContent = stored;
        } else {
            console.log(`[${this.phaseId}] 3b. No data in sessionStorage. Falling back to server.`);
            try {
                const sessionData = await this.apiClient.getSessionData();
                const serverContent = sessionData[this.config.sessionStorageKey];
                if (serverContent && serverContent.trim()) {
                    console.log(`[${this.phaseId}] 6a. Found data on server.`);
                    finalContent = serverContent;
                    sessionStorage.setItem(this.config.sessionStorageKey, finalContent);
                } else {
                    console.log(`[${this.phaseId}] 6b. No data found on server for this key.`);
                }
            } catch (error) {
                console.warn(`[${this.phaseId}] Error loading initial data from server:`, error);
            }
        }

        this.displayContent(finalContent);

        // The return value indicates if content was loaded, so the caller can decide whether to setup the download button.
        return finalContent && finalContent.trim().length > 0;
    }
    
    displayContent(content) {
        const contentElement = document.getElementById(this.config.contentContainer);
        const downloadContainer = document.getElementById(this.config.downloadContainer);
        
        if (content && content.trim()) {
            if (this.config.globalContentVar) {
                window[this.config.globalContentVar] = content;
            }
            contentElement.dataset.rawMarkdown = content;
            ContentRenderer.renderMarkdown(content, contentElement);
            
            if (downloadContainer) {
                downloadContainer.style.display = 'flex';
            }
        } else {
            ContentRenderer.clearContent(contentElement);
            if (downloadContainer) {
                downloadContainer.style.display = 'none';
            }
        }
    }
    
    clearContent() {
        const contentElement = document.getElementById(this.config.contentContainer);
        const downloadContainer = document.getElementById(this.config.downloadContainer);
        
        ContentRenderer.clearContent(contentElement);
        if (downloadContainer) {
            downloadContainer.style.display = 'none';
        }
        
        if (this.config.sessionStorageKey) {
            sessionStorage.removeItem(this.config.sessionStorageKey);
        }
        
        if (this.config.globalContentVar) {
            window[this.config.globalContentVar] = '';
        }
    }
    
    async generateContent(requestBody = {}) {
        if (!this.config.apiEndpoint) {
            throw new Error('API endpoint not configured');
        }
        
        this.clearContent();
        UIFeedback.hideError();
        UIFeedback.show('loading', this.config.loadingMessage || 'Generating content...');
        
        try {
            const response = await this.apiClient.callWithRetry(this.config.apiEndpoint, requestBody);
            if (response.success) {
                const content = response[this.config.responseContentKey] || response.content;
                this.displayContent(content);
                
                if (this.config.sessionStorageKey) {
                    sessionStorage.setItem(this.config.sessionStorageKey, content);
                }
                
                if (this.onContentGenerated) {
                    this.onContentGenerated(response);
                }
                return response;
            } else {
                throw new Error(response.error || 'Generation failed');
            }
        } catch (error) {
            UIFeedback.show('error', 'Error generating content: ' + error.message);
            throw error;
        } finally {
            UIFeedback.hideLoading();
        }
    }
    
    onContentGenerated(response) {
        // Override in subclasses for custom post-generation logic
    }
    
    async checkPrerequisites() {
        if (!this.config.prerequisites || this.config.prerequisites.length === 0) {
            return { valid: true, missing: [] };
        }
        
        const sessionData = await this.apiClient.getSessionData();
        const missing = [];
        
        for (const prereq of this.config.prerequisites) {
            if (!sessionData[prereq.key] || !sessionData[prereq.key].trim()) {
                missing.push(prereq);
            }
        }
        
        return { valid: missing.length === 0, missing };
    }
}

// Make PhaseManager available globally
window.PhaseManager = PhaseManager;
