/**
 * Unified download manager
 */
class DownloadManager {
    static setupDownloadButton(targetContentId, baseFilename, containerId) {
        const contentElement = document.getElementById(targetContentId);
        const hasContent = contentElement && contentElement.dataset.rawMarkdown && contentElement.dataset.rawMarkdown.trim();

        const container = document.getElementById(containerId);
        if (!container) {
            console.error('Download button container not found:', containerId);
            return;
        }

        if (!hasContent) {
            container.innerHTML = ''; // Ensure the container is empty if there's no content
            return;
        }

        container.innerHTML = `
            <div class="btn-group">
                <button type="button" class="btn btn-outline-secondary dropdown-toggle" data-bs-toggle="dropdown" aria-expanded="false">
                    <i class="bi bi-download me-1"></i> Download
                </button>
                <ul class="dropdown-menu">
                    <li><a class="dropdown-item" href="#" data-format="markdown">
                        <i class="bi bi-file-earmark-text me-2"></i>Download Markdown (.md)
                    </a></li>
                    <li><a class="dropdown-item" href="#" data-format="pdf">
                        <i class="bi bi-file-earmark-pdf me-2"></i>Download PDF (.pdf)
                    </a></li>
                </ul>
            </div>
        `;

        container.querySelectorAll('.dropdown-item').forEach(item => {
            item.addEventListener('click', (e) => {
                e.preventDefault();
                this.handleDownload(targetContentId, baseFilename, item.dataset.format);
            });
        });
    }
    
    static async handleDownload(targetContentId, baseFilename, format) {
        const contentElement = document.getElementById(targetContentId);
        let contentToDownload = '';

        if (contentElement) {
            contentToDownload = contentElement.dataset.rawMarkdown || contentElement.innerText || contentElement.value;
        } else {
            // Fallback for global content variables
            contentToDownload = this.getGlobalContent(targetContentId);
        }
        
        if (!contentToDownload) {
            UIFeedback.show('error', `No content available to download as ${format.toUpperCase()}. Please generate content first.`);
            return;
        }

        const filename = `${baseFilename}.${format === 'markdown' ? 'md' : 'pdf'}`;
        const apiUrl = format === 'markdown' ? '/api/download/markdown' : '/api/download/pdf';

        try {
            const response = await fetch(apiUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content: contentToDownload, filename: filename })
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Download failed');
            }
            
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            a.remove();
        } catch (error) {
            UIFeedback.show('error', 'Download error: ' + error.message, error.detail || error);
        }
    }
    
    static getGlobalContent(targetContentId) {
        // Map target content IDs to global variables
        const contentMap = {
            'plan-content': 'currentPlanMarkdown',
            'report-content': 'currentReportMarkdown',
            'current-hypo-content': 'currentHypothesisMarkdown',
            'refined-hypo-content': 'currentRefinedHypothesisMarkdown',
            'able-table-content': 'currentAbleTableMarkdown',
            'data-sources-content': 'currentDataSourcesMarkdown'
        };
        
        const globalVar = contentMap[targetContentId];
        return globalVar && window[globalVar] ? window[globalVar] : '';
    }
}

// Make DownloadManager available globally
window.DownloadManager = DownloadManager;
