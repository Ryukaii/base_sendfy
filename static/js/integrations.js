// Load existing integrations
async function loadIntegrations() {
    try {
        const response = await fetch('/api/integrations');
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const integrations = await response.json();
        
        const list = document.getElementById('integrationsList');
        list.innerHTML = '';
        
        if (!Array.isArray(integrations)) {
            throw new Error('Invalid response format: expected an array');
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
                                <code>${window.location.origin}/webhook/${integration.id}</code>
                                <button class="btn btn-sm btn-outline-secondary ms-2" onclick="copyToClipboard('${window.location.origin}/webhook/${integration.id}')">
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
        console.error('Error loading integrations:', error.message || error);
        const list = document.getElementById('integrationsList');
        list.innerHTML = '<div class="alert alert-danger">Error loading integrations. Please refresh the page to try again.</div>';
    }
}

// Copy webhook URL to clipboard
async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
        alert('Webhook URL copied to clipboard!');
    } catch (err) {
        console.error('Failed to copy text:', err.message || err);
        // Fallback for older browsers
        const textArea = document.createElement('textarea');
        textArea.value = text;
        document.body.appendChild(textArea);
        textArea.select();
        try {
            document.execCommand('copy');
            alert('Webhook URL copied to clipboard!');
        } catch (err) {
            console.error('Fallback copying failed:', err.message || err);
            alert('Failed to copy URL. Please copy it manually.');
        }
        document.body.removeChild(textArea);
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
        
        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.error || 'Failed to create integration');
        }
        
        alert('Integration created successfully!');
        e.target.reset();
        loadIntegrations();
    } catch (error) {
        console.error('Error creating integration:', error.message || error);
        alert(`Error creating integration: ${error.message || 'Please try again'}`);
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
        
        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.error || 'Failed to delete integration');
        }
        
        alert('Integration deleted successfully!');
        loadIntegrations();
    } catch (error) {
        console.error('Error deleting integration:', error.message || error);
        alert(`Error deleting integration: ${error.message || 'Please try again'}`);
    }
}

// Load integrations when page loads
document.addEventListener('DOMContentLoaded', loadIntegrations);
