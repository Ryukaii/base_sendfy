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
        integrationSelect.innerHTML = `<option value="">Select Integration</option>` + 
            integrations.map(integration => 
                `<option value="${integration.id}">${integration.name}</option>`
            ).join('');
        
        // Display campaigns
        const list = document.getElementById('campaignsList');
        list.innerHTML = '';
        
        campaigns.forEach(campaign => {
            const integration = integrations.find(i => i.id === campaign.integration_id);
            const div = document.createElement('div');
            div.className = 'card mb-3';
            div.innerHTML = `
                <div class="card-body">
                    <div class="d-flex justify-content-between align-items-start">
                        <div>
                            <h5 class="card-title">${campaign.name}</h5>
                            <p class="card-text">
                                <strong>Integration:</strong> ${integration ? integration.name : 'Unknown'}<br>
                                <strong>Event Type:</strong> ${campaign.event_type}<br>
                                <strong>Message Template:</strong><br>
                                <code>${campaign.message_template}</code>
                            </p>
                            <p class="card-text"><small class="text-muted">Created: ${campaign.created_at}</small></p>
                        </div>
                        <div>
                            <button class="btn btn-primary mb-2" onclick="editCampaign('${campaign.id}')">Edit</button>
                            <button class="btn btn-danger" onclick="deleteCampaign('${campaign.id}')">Delete</button>
                        </div>
                    </div>
                </div>
            `;
            list.appendChild(div);
        });
    } catch (error) {
        console.error('Error loading data:', error);
        alert('Error loading campaigns and integrations. Please try again.');
    }
}

// Handle campaign creation/update
document.getElementById('campaignForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const formData = {
        name: document.getElementById('campaignName').value,
        integration_id: document.getElementById('integrationId').value,
        event_type: document.getElementById('eventType').value,
        message_template: document.getElementById('messageTemplate').value
    };
    
    const campaignId = e.target.dataset.campaignId;
    let url = '/api/campaigns';
    let method = 'POST';
    
    if (campaignId) {
        url += `/${campaignId}`;
        method = 'PUT';
        delete formData.integration_id; // Don't update integration ID
    }
    
    try {
        const response = await fetch(url, {
            method: method,
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(formData)
        });
        
        if (response.ok) {
            alert(campaignId ? 'Campaign updated successfully!' : 'Campaign created successfully!');
            resetForm();
            loadCampaigns();
        } else {
            const data = await response.json();
            alert(`Error ${campaignId ? 'updating' : 'creating'} campaign: ${data.error}`);
        }
    } catch (error) {
        console.error('Error saving campaign:', error);
        alert(`Error ${campaignId ? 'updating' : 'creating'} campaign. Please try again.`);
    }
});

// Reset form to creation mode
function resetForm() {
    const form = document.getElementById('campaignForm');
    form.reset();
    delete form.dataset.campaignId;
    document.getElementById('integrationId').disabled = false;
    document.querySelector('button[type="submit"]').textContent = 'Create Campaign';
}

// Load campaign data for editing
async function editCampaign(campaignId) {
    try {
        const response = await fetch('/api/campaigns');
        const campaigns = await response.json();
        const campaign = campaigns.find(c => c.id === campaignId);
        
        if (!campaign) {
            alert('Campaign not found');
            return;
        }
        
        const form = document.getElementById('campaignForm');
        form.dataset.campaignId = campaignId;
        
        document.getElementById('campaignName').value = campaign.name;
        document.getElementById('integrationId').value = campaign.integration_id;
        document.getElementById('integrationId').disabled = true;
        document.getElementById('eventType').value = campaign.event_type;
        document.getElementById('messageTemplate').value = campaign.message_template;
        
        document.querySelector('button[type="submit"]').textContent = 'Update Campaign';
        
        // Scroll to form
        form.scrollIntoView({ behavior: 'smooth' });
    } catch (error) {
        console.error('Error loading campaign for edit:', error);
        alert('Error loading campaign data. Please try again.');
    }
}

// Delete campaign
async function deleteCampaign(campaignId) {
    if (!confirm('Are you sure you want to delete this campaign?')) {
        return;
    }
    
    try {
        const response = await fetch(`/api/campaigns/${campaignId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            alert('Campaign deleted successfully!');
            resetForm();
            loadCampaigns();
        } else {
            const data = await response.json();
            alert(`Error deleting campaign: ${data.error}`);
        }
    } catch (error) {
        console.error('Error deleting campaign:', error);
        alert('Error deleting campaign. Please try again.');
    }
}

// Load data when page loads
document.addEventListener('DOMContentLoaded', () => {
    loadCampaigns();
    
    // Add cancel button handler
    const cancelButton = document.createElement('button');
    cancelButton.type = 'button';
    cancelButton.className = 'btn btn-secondary ms-2';
    cancelButton.textContent = 'Cancel';
    cancelButton.onclick = resetForm;
    
    const submitButton = document.querySelector('button[type="submit"]');
    submitButton.parentNode.insertBefore(cancelButton, submitButton.nextSibling);
});
