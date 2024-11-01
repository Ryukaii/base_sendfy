// Load existing integrations
async function loadIntegrations() {
    try {
        const response = await fetch('/api/integrations');
        const integrations = await response.json();
        
        if (!Array.isArray(integrations)) {
            console.error('Invalid integrations data:', integrations);
            throw new Error('Invalid integrations data received');
        }
        
        const list = document.getElementById('integrationsList');
        list.innerHTML = '';
        
        if (integrations.length === 0) {
            list.innerHTML = '<div class="alert alert-info">No integrations found. Create one to get started!</div>';
            return;
        }
        
        integrations.forEach(integration => {
            const div = document.createElement('div');
            div.className = 'card mb-3';
            div.innerHTML = `
                <div class="card-body">
                    <div class="d-flex justify-content-between align-items-start">
                        <div>
                            <h5 class="card-title">${integration.name}</h5>
                            <p class="card-text">
                                <strong>Webhook URL:</strong> 
                                <code>${window.location.origin}${integration.webhook_url}</code>
                                <button class="btn btn-sm btn-outline-secondary ms-2" onclick="copyToClipboard('${window.location.origin}${integration.webhook_url}')">
                                    Copy
                                </button>
                            </p>
                            <p class="card-text"><small class="text-muted">Created: ${integration.created_at}</small></p>
                        </div>
                        <button class="btn btn-danger" onclick="deleteIntegration('${integration.id}')">Delete</button>
                    </div>
                </div>
            `;
            list.appendChild(div);
        });
    } catch (error) {
        console.error('Error loading integrations:', error);
        const list = document.getElementById('integrationsList');
        list.innerHTML = '<div class="alert alert-danger">Failed to load integrations. Please try again.</div>';
    }
}

// Copy webhook URL to clipboard
async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
        showMessage('Success', 'Webhook URL copied to clipboard!', 'success');
    } catch (err) {
        console.error('Failed to copy text: ', err);
        showMessage('Error', 'Failed to copy webhook URL', 'danger');
    }
}

// Handle integration creation
document.getElementById('integrationForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const name = document.getElementById('integrationName').value;
    
    try {
        const response = await fetch('/api/integrations', {
            method: 'POST',
            headers: {
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ name })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showMessage('Success', 'Integration created successfully!', 'success');
            e.target.reset();
            loadIntegrations();
        } else {
            throw new Error(data.error || 'Failed to create integration');
        }
    } catch (error) {
        console.error('Error creating integration:', error);
        showMessage('Error', error.message || 'Failed to create integration. Please try again.', 'danger');
    }
});

// Delete integration
async function deleteIntegration(integrationId) {
    try {
        const response = await fetch(`/api/integrations/${integrationId}`, {
            method: 'DELETE',
            headers: {
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            }
        });
        
        // Try to parse response as JSON
        let data;
        try {
            data = await response.json();
        } catch (e) {
            console.error('Error parsing response:', e);
            throw new Error('Invalid server response');
        }
        
        if (response.ok) {
            // Refresh the page only after successful deletion
            window.location.reload();
        } else {
            throw new Error(data.error || 'Failed to delete integration');
        }
    } catch (error) {
        console.error('Error:', error);
        showMessage('Error', error.message || 'Failed to delete integration. Please try again.', 'danger');
    }
}

// Load integrations when page loads
document.addEventListener('DOMContentLoaded', loadIntegrations);
