/**
 * auth.js
 * 
 * Manages OAuth authentication state for MCP servers.
 * Checks which servers require user login and updates the UI accordingly.
 */

/**
 * Checks the authentication status of all configured MCP servers.
 * If any servers require user authentication, it displays a banner.
 */
export async function checkAuthStatus() {
    try {
        const response = await fetch('/oauth/servers/needing-auth');
        if (!response.ok) {
            console.error('Failed to fetch auth status:', response.statusText);
            return;
        }

        const data = await response.json();
        const serversNeedingAuth = data.servers_needing_auth || [];

        const authBanner = document.getElementById('auth-banner');
        const authServerList = document.getElementById('auth-server-list');

        if (!authBanner || !authServerList) {
            console.error('Required auth banner elements not found in the DOM.');
            return;
        }

        if (serversNeedingAuth.length > 0) {
            authServerList.innerHTML = ''; // Clear previous list
            serversNeedingAuth.forEach(server => {
                const serverItem = document.createElement('div');
                serverItem.className = 'auth-server-item';

                const serverInfo = document.createElement('span');
                serverInfo.textContent = `Login required for ${server.name} (${server.description || 'No description'}).`;
                
                const loginButton = document.createElement('a');
                loginButton.href = server.auth_url;
                loginButton.className = 'btn btn-primary btn-sm ms-2';
                loginButton.textContent = 'Login';

                serverItem.appendChild(serverInfo);
                serverItem.appendChild(loginButton);
                authServerList.appendChild(serverItem);
            });
            authBanner.style.display = 'block';
        } else {
            authBanner.style.display = 'none';
        }
    } catch (error) {
        console.error('Error checking auth status:', error);
    }
}

/**
 * Shows the authentication banner with a generic message.
 * This can be called when an API call fails due to auth issues.
 */
export function showAuthBanner() {
    const authBanner = document.getElementById('auth-banner');
    if (authBanner) {
        authBanner.style.display = 'block';
        // Optionally, you could update the text to be more generic
        // document.getElementById('auth-server-list').innerHTML = 'An action failed due to missing authentication. Please log in.';
    }
    // Re-run the check to get specific server login links
    checkAuthStatus();
}
