/**
 * auth.js
 * 
 * Manages MCP server authentication and connection status.
 * Provides a comprehensive interface for managing server connections.
 */

/**
 * Loads and displays all MCP servers with their authentication status.
 * Creates a clean list interface with Connect/Disconnect buttons.
 */
export async function loadServerStatus() {
    try {
        const response = await fetch('/oauth/servers/status');
        if (!response.ok) {
            console.error('Failed to fetch server status:', response.statusText);
            showError('Failed to load server status');
            return;
        }

        const data = await response.json();
        displayServerList(data);
        updateStatusSummary(data);
    } catch (error) {
        console.error('Error loading server status:', error);
        showError('Error loading server status');
    }
}

/**
 * Displays the list of MCP servers with their authentication status.
 */
function displayServerList(data) {
    const serverList = document.getElementById('mcp-server-list');
    if (!serverList) {
        console.error('MCP server list element not found in the DOM.');
        return;
    }

    if (!data.servers || data.servers.length === 0) {
        serverList.innerHTML = `
            <div class="text-center text-muted py-2">
                <small>No MCP servers configured</small>
            </div>
        `;
        return;
    }

    serverList.innerHTML = ''; // Clear previous content
    
    data.servers.forEach(server => {
        const serverButton = document.createElement('button');
        serverButton.className = 'btn text-start w-100 mb-1 p-2';
        serverButton.style.fontSize = '0.85rem';
        serverButton.title = server.description; // Tooltip with description
        
        // Determine button styling based on server state
        if (!server.requires_auth) {
            // No authentication required - muted green styling (ready but inactive)
            serverButton.className += ' btn-outline-success';
            serverButton.style.opacity = '0.6'; // Make it more subtle
            serverButton.innerHTML = `
                <div class="d-flex align-items-center">
                    <i class="bi bi-check-circle text-success me-2"></i>
                    <span class="flex-grow-1">${server.name}</span>
                    <small class="text-success">Ready</small>
                </div>
            `;
            serverButton.disabled = true; // No action needed
        } else if (server.is_authenticated) {
            // Connected - show as success with disconnect action
            serverButton.className += ' btn-outline-success';
            serverButton.innerHTML = `
                <div class="d-flex align-items-center">
                    <i class="bi bi-check-circle-fill text-success me-2"></i>
                    <span class="flex-grow-1">${server.name}</span>
                    <small class="text-muted">Connected</small>
                </div>
            `;
            serverButton.onclick = () => {
                if (confirm(`Disconnect from ${server.name}?`)) {
                    disconnectServer(server.name);
                }
            };
        } else {
            // Not connected - show as warning (yellow) to match status summary
            serverButton.className += ' btn-outline-warning';
            serverButton.innerHTML = `
                <div class="d-flex align-items-center">
                    <i class="bi bi-exclamation-circle text-warning me-2"></i>
                    <span class="flex-grow-1">${server.name}</span>
                    <small class="text-warning">Click to connect</small>
                </div>
            `;
            serverButton.onclick = () => window.location.href = server.auth_url;
        }
        
        serverList.appendChild(serverButton);
    });
}

/**
 * Updates the status summary display.
 */
function updateStatusSummary(data) {
    const summary = document.getElementById('server-status-summary');
    if (!summary) return;
    
    const connected = data.authenticated_count || 0;
    const needingAuth = data.needing_auth_count || 0;
    const totalRequiringAuth = connected + needingAuth; // Only count servers that require auth
    
    if (totalRequiringAuth > 0) {
        summary.textContent = `${connected}/${totalRequiringAuth} connected`;
        summary.className = needingAuth > 0 ? 'text-warning' : 'text-success';
    } else {
        // No servers require authentication
        summary.textContent = '';
    }
}

/**
 * Disconnects from a specific MCP server.
 */
async function disconnectServer(serverName) {
    try {
        const response = await fetch(`/oauth/disconnect/${serverName}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        const result = await response.json();
        
        if (response.ok && result.success) {
            // Show success message briefly
            showSuccess(`Disconnected from ${serverName}`);
            // Refresh the server list
            await loadServerStatus();
        } else {
            showError(result.error || 'Failed to disconnect from server');
        }
    } catch (error) {
        console.error('Error disconnecting server:', error);
        showError('Error disconnecting from server');
    }
}

/**
 * Shows an error message to the user.
 */
function showError(message) {
    // You can integrate with existing error display system
    console.error('Server management error:', message);
}

/**
 * Shows a success message to the user.
 */
function showSuccess(message) {
    // You can integrate with existing success display system
    console.log('Server management success:', message);
}

/**
 * Legacy function for backward compatibility.
 * Redirects to the new server status loading.
 */
export async function checkAuthStatus() {
    await loadServerStatus();
}

/**
 * Legacy function for backward compatibility.
 */
export function showAuthBanner() {
    loadServerStatus();
}
