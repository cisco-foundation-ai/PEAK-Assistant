document.addEventListener('DOMContentLoaded', function() {
    const clearSessionSidebarBtn = document.getElementById('clear-session-sidebar-btn');
    if (clearSessionSidebarBtn) {
        clearSessionSidebarBtn.addEventListener('click', async function() {
            if (confirm('Are you sure you want to clear all session data? This will reset the application state.')) {
                try {
                    // Clear client-side storage
                    sessionStorage.clear();
                    localStorage.clear();

                    // Clear server-side session
                    const response = await fetch('/api/clear-session', { method: 'POST' });
                    if (!response.ok) {
                        const errorData = await response.json().catch(() => ({}));
                        throw new Error(errorData.error || 'Failed to clear server session.');
                    }

                    // Now that server and client are clear, inform the user and redirect.
                    alert('Session cleared. The application will now restart.');
                    window.location.href = '/';
                } catch (error) {
                    console.error('Error clearing session:', error);
                    alert('Could not fully clear the session. Please try again. Error: ' + error.message);
                }
            }
        });
    }

    // Function to ensure Hunt Planning button is always active
    function ensureHuntPlanningButtonActive() {
        const huntPlanningBtn = document.getElementById('hunt-planning-btn');
        
        if (huntPlanningBtn) {
            // Always enable and style the button as active
            huntPlanningBtn.classList.remove('disabled', 'btn-secondary');
            huntPlanningBtn.classList.add('btn-success');
            huntPlanningBtn.removeAttribute('aria-disabled');
            huntPlanningBtn.title = 'Generate Hunt Plan';
        }
    }

    // Initial setup when the DOM is loaded
    ensureHuntPlanningButtonActive();

    // Listen for session state changes and ensure button stays active
    document.addEventListener('sessionStateChanged', function() {
        console.log('Session state changed, ensuring hunt plan button stays active...');
        ensureHuntPlanningButtonActive();
    });
});
