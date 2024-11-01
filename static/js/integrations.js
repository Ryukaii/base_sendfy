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
            alert(`Failed to create integration: ${data.error}`);
        }
    } catch (error) {
        console.error('Error creating integration:', error);
        alert('Failed to create integration. Please try again.');
    }
});

// Delete integration
async function deleteIntegration(integrationId) {
    try {
        const response = await fetch(`/api/integrations/${integrationId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            const result = await response.json();
            location.reload(); // Reload page after successful deletion
        } else {
            const error = await response.json();
            console.error('Server error:', error);
            alert(error.error || 'Failed to delete integration');
        }
    } catch (error) {
        console.error('Network error:', error);
        alert('Network error. Please try again.');
    }
}

// Load integrations when page loads
document.addEventListener('DOMContentLoaded', loadIntegrations);
