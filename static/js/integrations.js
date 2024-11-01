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
        alert('Error loading integrations. Please try again.');
    }
}

// Copy webhook URL to clipboard
async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
        alert('Webhook URL copied to clipboard!');
    } catch (err) {
        console.error('Failed to copy text: ', err);
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
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ name })
        });
        
        if (response.ok) {
            alert('Integration created successfully!');
            e.target.reset();
            loadIntegrations();
        } else {
            const data = await response.json();
            alert(`Error creating integration: ${data.error}`);
        }
    } catch (error) {
        console.error('Error creating integration:', error);
        alert('Error creating integration. Please try again.');
    }
});

// Delete integration
async function deleteIntegration(integrationId) {
    if (!confirm('Are you sure you want to delete this integration? This will also delete all associated campaigns.')) {
        return;
    }
    
    try {
        const response = await fetch(`/api/integrations/${integrationId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            alert('Integration deleted successfully!');
            loadIntegrations();
        } else {
            const data = await response.json();
            alert(`Error deleting integration: ${data.error}`);
        }
    } catch (error) {
        console.error('Error deleting integration:', error);
        alert('Error deleting integration. Please try again.');
    }
}

// Load integrations when page loads
document.addEventListener('DOMContentLoaded', loadIntegrations);
