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
});
