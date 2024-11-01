// Load existing integrations
async function loadIntegrations() {
    try {
        const response = await fetch('/api/integrations');
        const integrations = await response.json();
        
        const list = document.getElementById('integrationsList');
        list.innerHTML = '';
        
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
        alert('Failed to load integrations. Please try again.');
    }
}

// Copy webhook URL to clipboard
async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
        alert('Webhook URL copied to clipboard!');
    } catch (err) {
        console.error('Failed to copy text: ', err);
        alert('Failed to copy webhook URL');
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
            alert('Integration created successfully!');
            e.target.reset();
            loadIntegrations();
        } else {
            throw new Error(data.error || 'Failed to create integration');
        }
    } catch (error) {
        console.error('Error creating integration:', error);
        alert(error.message || 'Failed to create integration. Please try again.');
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
        alert(error.message || 'Failed to delete integration. Please try again.');
    }
}

// Load integrations when page loads
document.addEventListener('DOMContentLoaded', loadIntegrations);
