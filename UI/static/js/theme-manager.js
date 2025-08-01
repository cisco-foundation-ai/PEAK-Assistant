/**
 * Theme Manager - Handles dark/light mode switching
 */

class ThemeManager {
    constructor() {
        this.themeKey = 'peak-assistant-theme';
        this.init();
    }

    init() {
        // Set initial theme based on stored preference or system preference
        this.setInitialTheme();
        
        // Set up event listeners
        this.setupEventListeners();
        
        // Update UI to reflect current theme
        this.updateThemeUI();
    }

    setInitialTheme() {
        const storedTheme = localStorage.getItem(this.themeKey);
        
        if (storedTheme) {
            // Use stored preference
            this.setTheme(storedTheme);
        } else {
            // Use system preference
            const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
            this.setTheme(prefersDark ? 'dark' : 'light');
        }
    }

    setTheme(theme) {
        const html = document.documentElement;
        
        // Always set explicit data-theme attribute for manual selection
        html.setAttribute('data-theme', theme);
        console.log('Theme set to:', theme, 'data-theme attribute:', html.getAttribute('data-theme')); // Debug log
        
        // Store preference
        localStorage.setItem(this.themeKey, theme);
        
        // Update UI
        this.updateThemeUI();
    }

    toggleTheme() {
        const currentTheme = this.getCurrentTheme();
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        console.log('Toggling theme from', currentTheme, 'to', newTheme); // Debug log
        this.setTheme(newTheme);
    }

    getCurrentTheme() {
        const html = document.documentElement;
        return html.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
    }

    updateThemeUI() {
        const themeToggle = document.getElementById('theme-toggle');
        const themeText = document.getElementById('theme-text');
        const logo = document.querySelector('.sidebar-logo');
        const currentTheme = this.getCurrentTheme();
        
        // Update toggle switch state
        if (themeToggle) {
            themeToggle.checked = (currentTheme === 'dark');
        }
        
        // Label always says "Dark Mode" - no need to update text
        
        // Update logo based on theme
        if (logo) {
            if (currentTheme === 'dark') {
                logo.src = logo.src.replace('peak-logo.png', 'peak-logo-dark.png');
            } else {
                logo.src = logo.src.replace('peak-logo-dark.png', 'peak-logo.png');
            }
            console.log('Logo updated for', currentTheme, 'theme:', logo.src); // Debug log
        }
    }

    setupEventListeners() {
        // Theme toggle switch
        const themeToggle = document.getElementById('theme-toggle');
        console.log('Theme toggle element found:', themeToggle); // Debug log
        
        if (themeToggle) {
            themeToggle.addEventListener('change', (e) => {
                console.log('Theme toggle changed!', 'Checked:', e.target.checked); // Debug log
                const newTheme = e.target.checked ? 'dark' : 'light';
                console.log('Setting theme to:', newTheme); // Debug log
                this.setTheme(newTheme);
            });
            console.log('Theme toggle event listener added'); // Debug log
        } else {
            console.warn('Theme toggle switch not found!');
        }

        // Listen for system theme changes
        const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
        mediaQuery.addEventListener('change', (e) => {
            // Only auto-update if user hasn't set a manual preference
            const storedTheme = localStorage.getItem(this.themeKey);
            if (!storedTheme) {
                this.setTheme(e.matches ? 'dark' : 'light');
            }
        });
    }

    // Public method to get current theme for other scripts
    getTheme() {
        return this.getCurrentTheme();
    }

    // Public method to set theme programmatically
    setThemeManually(theme) {
        if (theme === 'dark' || theme === 'light') {
            this.setTheme(theme);
        }
    }
}

// Initialize theme manager when DOM is loaded
function initializeThemeManager() {
    console.log('Initializing theme manager...'); // Debug log
    window.themeManager = new ThemeManager();
    console.log('Theme manager initialized'); // Debug log
}

// Try multiple initialization methods to ensure it works
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeThemeManager);
} else {
    // DOM is already loaded
    initializeThemeManager();
}

// Also try with a small delay as fallback
setTimeout(() => {
    if (!window.themeManager) {
        console.log('Fallback theme manager initialization');
        initializeThemeManager();
    }
}, 100);

// Export for module usage
export default ThemeManager;
