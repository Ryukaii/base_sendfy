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
                    <h5 class="card-title">${integration.name}</h5>
                    <p class="card-text">Webhook URL: ${window.location.origin}${integration.webhook_url}</p>
                    <p class="card-text"><small class="text-muted">Created: ${integration.created_at}</small></p>
                </div>
            `;
            list.appendChild(div);
        });
    } catch (error) {
        console.error('Error loading integrations:', error);
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
            alert('Error creating integration');
        }
    } catch (error) {
        alert('Error creating integration: ' + error.message);
    }
});

// Load integrations when page loads
document.addEventListener('DOMContentLoaded', loadIntegrations);
