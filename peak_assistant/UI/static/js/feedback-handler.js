document.addEventListener('DOMContentLoaded', () => {
    const feedbackInput = document.getElementById('feedback-input');
    const sendFeedbackBtn = document.getElementById('send-feedback-btn');

    if (feedbackInput && sendFeedbackBtn) {
        feedbackInput.addEventListener('keydown', (e) => {
            // If Enter is pressed without Shift, trigger the send button
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault(); // Prevents adding a newline
                sendFeedbackBtn.click();
            }
            // Shift+Enter will continue to allow newlines by default
        });
    }
});
