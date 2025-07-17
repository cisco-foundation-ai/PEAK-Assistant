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

    // Function to check prerequisites for Hunt Planning button and style it
    async function checkHuntPlanningPrerequisites() {
        const huntPlanningBtn = document.getElementById('hunt-planning-btn');
        if (!huntPlanningBtn) return;

        try {
            const response = await fetch('/api/prerequisite-check');
            const data = await response.json();

            if (data.all_met) {
                huntPlanningBtn.classList.remove('disabled', 'btn-secondary');
                huntPlanningBtn.classList.add('btn-success');
                huntPlanningBtn.removeAttribute('aria-disabled');
                huntPlanningBtn.title = 'Proceed to Hunt Planning';
            } else {
                huntPlanningBtn.classList.add('disabled', 'btn-secondary');
                huntPlanningBtn.classList.remove('btn-success');
                huntPlanningBtn.setAttribute('aria-disabled', 'true');
                huntPlanningBtn.title = `Complete these phases first: ${data.missing.join(', ')}`;
            }
        } catch (error) {
            console.error('Error checking hunt planning prerequisites:', error);
            huntPlanningBtn.classList.add('disabled', 'btn-secondary');
            huntPlanningBtn.classList.remove('btn-success');
            huntPlanningBtn.title = 'Error checking prerequisites.';
        }
    }

    // Initial check when the DOM is loaded
    checkHuntPlanningPrerequisites();

    // Listen for session state changes and re-run the check
    document.addEventListener('sessionStateChanged', function() {
        console.log('Session state changed, re-checking hunt plan prerequisites...');
        checkHuntPlanningPrerequisites();
    });
});
