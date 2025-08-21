/**
 * Content renderer with markdown support
 */
class ContentRenderer {
    static renderMarkdown(markdown, targetElement) {
        if (typeof markdown === 'string' && markdown.trim()) {
            try {
                if (typeof marked !== 'undefined' && marked.parse) {
                    console.log('ContentRenderer: About to render markdown, length:', markdown.length);
                    console.log('ContentRenderer: First 200 chars:', markdown.substring(0, 200));
                    
                    // Check for code blocks in the markdown
                    const codeBlockMatches = markdown.match(/```[\s\S]*?```/g);
                    if (codeBlockMatches) {
                        console.log('ContentRenderer: Found', codeBlockMatches.length, 'code blocks');
                        console.log('ContentRenderer: First code block:', codeBlockMatches[0].substring(0, 100));
                    }
                    
                    // Configure marked options for better code block handling
                    if (typeof marked.setOptions === 'function') {
                        marked.setOptions({
                            breaks: true,
                            gfm: true,
                            sanitize: false
                        });
                    }
                    
                    const renderedHTML = marked.parse(markdown);
                    console.log('ContentRenderer: Rendered HTML length:', renderedHTML.length);
                    console.log('ContentRenderer: First 200 chars of HTML:', renderedHTML.substring(0, 200));
                    
                    // Clear target element completely before setting new content
                    targetElement.innerHTML = '';
                    targetElement.innerHTML = renderedHTML;
                    targetElement.classList.remove('empty');
                    console.log('ContentRenderer: Successfully rendered markdown');
                } else {
                    console.warn('ContentRenderer: marked library not available, showing raw markdown');
                    targetElement.innerHTML = '<pre>' + markdown + '</pre>';
                    targetElement.classList.remove('empty');
                }
            } catch (error) {
                console.error('ContentRenderer: Error rendering markdown:', error);
                console.log('ContentRenderer: Error occurred with markdown:', markdown.substring(0, 500));
                targetElement.innerHTML = '<div class="alert alert-warning">Error rendering content. Showing raw markdown:</div><pre>' + markdown + '</pre>';
                targetElement.classList.remove('empty');
            }
        } else {
            targetElement.innerHTML = '<p class="text-muted"><em>Content will appear here...</em></p>';
            targetElement.classList.add('empty');
            console.warn("Invalid content for Markdown rendering:", markdown);
        }
    }
    
    static clearContent(targetElement) {
        targetElement.innerHTML = '<p class="text-muted"><em>Content will appear here...</em></p>';
        targetElement.classList.add('empty');
        targetElement.dataset.rawMarkdown = '';
    }
}

// Make ContentRenderer available globally
window.ContentRenderer = ContentRenderer;
