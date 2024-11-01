// Load existing campaigns and integrations
async function loadCampaigns() {
    try {
        const [campaignsResponse, integrationsResponse] = await Promise.all([
            fetch('/api/campaigns'),
            fetch('/api/integrations')
        ]);
        
        const [campaigns, integrations] = await Promise.all([
            campaignsResponse.json(),
            integrationsResponse.json()
        ]);
        
        // Populate integrations dropdown
        const integrationSelect = document.getElementById('integrationId');
        integrationSelect.innerHTML = integrations.map(integration => 
            `<option value="${integration.id}">${integration.name}</option>`
        ).join('');
        
        // Display campaigns
        const list = document.getElementById('campaignsList');
        list.innerHTML = '';
        
        campaigns.forEach(campaign => {
            const div = document.createElement('div');
            div.className = 'card mb-3';
            div.innerHTML = `
                <div class="card-body">
                    <h5 class="card-title">${campaign.name}</h5>
                    <p class="card-text">Event Type: ${campaign.event_type}</p>
                    <p class="card-text">Message Template: ${campaign.message_template}</p>
                    <p class="card-text"><small class="text-muted">Created: ${campaign.created_at}</small></p>
                </div>
            `;
            list.appendChild(div);
        });
    } catch (error) {
        console.error('Error loading data:', error);
    }
}

// Handle campaign creation
document.getElementById('campaignForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const formData = {
        name: document.getElementById('campaignName').value,
        integration_id: document.getElementById('integrationId').value,
        event_type: document.getElementById('eventType').value,
        message_template: document.getElementById('messageTemplate').value
    };
    
    try {
        const response = await fetch('/api/campaigns', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(formData)
        });
        
        if (response.ok) {
            alert('Campaign created successfully!');
            e.target.reset();
            loadCampaigns();
        } else {
            alert('Error creating campaign');
        }
    } catch (error) {
        alert('Error creating campaign: ' + error.message);
    }
});

// Load data when page loads
document.addEventListener('DOMContentLoaded', loadCampaigns);
