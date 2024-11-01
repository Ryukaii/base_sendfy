// Carregar campanhas e integrações existentes
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
        
        // Preencher dropdown de integrações
        const integrationSelect = document.getElementById('integrationId');
        integrationSelect.innerHTML = `<option value="">Selecione uma Integração</option>` + 
            integrations.map(integration => 
                `<option value="${integration.id}">${integration.name}</option>`
            ).join('');
        
        // Exibir campanhas
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
                                <strong>Integração:</strong> ${integration ? integration.name : 'Desconhecida'}<br>
                                <strong>Tipo de Evento:</strong> ${campaign.event_type}<br>
                                <strong>Modelo de Mensagem:</strong><br>
                                <code>${campaign.message_template}</code>
                            </p>
                            <p class="card-text"><small class="text-muted">Criada em: ${campaign.created_at}</small></p>
                        </div>
                        <div>
                            <button class="btn btn-primary mb-2" onclick="editCampaign('${campaign.id}')">Editar</button>
                            <button class="btn btn-danger" onclick="deleteCampaign('${campaign.id}')">Excluir</button>
                        </div>
                    </div>
                </div>
            `;
            list.appendChild(div);
        });
    } catch (error) {
        console.error('Erro ao carregar dados:', error);
        alert('Erro ao carregar campanhas e integrações. Por favor, tente novamente.');
    }
}

// Manipular criação/atualização de campanha
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
        delete formData.integration_id;
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
            alert(campaignId ? 'Campanha atualizada com sucesso!' : 'Campanha criada com sucesso!');
            resetForm();
            loadCampaigns();
        } else {
            const data = await response.json();
            alert(`Erro ao ${campaignId ? 'atualizar' : 'criar'} campanha: ${data.error}`);
        }
    } catch (error) {
        console.error('Erro ao salvar campanha:', error);
        alert(`Erro ao ${campaignId ? 'atualizar' : 'criar'} campanha. Por favor, tente novamente.`);
    }
});

// Resetar formulário para modo de criação
function resetForm() {
    const form = document.getElementById('campaignForm');
    form.reset();
    delete form.dataset.campaignId;
    document.getElementById('integrationId').disabled = false;
    document.querySelector('button[type="submit"]').textContent = 'Criar Campanha';
}

// Carregar dados da campanha para edição
async function editCampaign(campaignId) {
    try {
        const response = await fetch('/api/campaigns');
        const campaigns = await response.json();
        const campaign = campaigns.find(c => c.id === campaignId);
        
        if (!campaign) {
            alert('Campanha não encontrada');
            return;
        }
        
        const form = document.getElementById('campaignForm');
        form.dataset.campaignId = campaignId;
        
        document.getElementById('campaignName').value = campaign.name;
        document.getElementById('integrationId').value = campaign.integration_id;
        document.getElementById('integrationId').disabled = true;
        document.getElementById('eventType').value = campaign.event_type;
        document.getElementById('messageTemplate').value = campaign.message_template;
        
        document.querySelector('button[type="submit"]').textContent = 'Atualizar Campanha';
        
        form.scrollIntoView({ behavior: 'smooth' });
    } catch (error) {
        console.error('Erro ao carregar campanha para edição:', error);
        alert('Erro ao carregar dados da campanha. Por favor, tente novamente.');
    }
}

// Excluir campanha
async function deleteCampaign(campaignId) {
    if (!confirm('Tem certeza que deseja excluir esta campanha?')) {
        return;
    }
    
    try {
        const response = await fetch(`/api/campaigns/${campaignId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            alert('Campanha excluída com sucesso!');
            resetForm();
            loadCampaigns();
        } else {
            const data = await response.json();
            alert(`Erro ao excluir campanha: ${data.error}`);
        }
    } catch (error) {
        console.error('Erro ao excluir campanha:', error);
        alert('Erro ao excluir campanha. Por favor, tente novamente.');
    }
}

// Carregar dados quando a página carregar
document.addEventListener('DOMContentLoaded', () => {
    loadCampaigns();
    
    // Adicionar manipulador do botão cancelar
    const cancelButton = document.createElement('button');
    cancelButton.type = 'button';
    cancelButton.className = 'btn btn-secondary ms-2';
    cancelButton.textContent = 'Cancelar';
    cancelButton.onclick = resetForm;
    
    const submitButton = document.querySelector('button[type="submit"]');
    submitButton.parentNode.insertBefore(cancelButton, submitButton.nextSibling);
});
