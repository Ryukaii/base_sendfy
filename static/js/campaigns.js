function showToast(type, message) {
    const toastDiv = document.createElement('div');
    toastDiv.className = 'position-fixed bottom-0 end-0 p-3';
    toastDiv.style.zIndex = '5';
    toastDiv.innerHTML = `
        <div class="toast align-items-center text-white bg-${type === 'success' ? 'success' : 'danger'} border-0" role="alert">
            <div class="d-flex">
                <div class="toast-body">
                    <i class="fas fa-${type === 'success' ? 'check' : 'exclamation'}-circle me-2"></i>
                    ${message}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        </div>
    `;
    document.body.appendChild(toastDiv);
    const toast = new bootstrap.Toast(toastDiv.querySelector('.toast'), {
        delay: 3000
    });
    toast.show();
    
    // Remove toast element after it's hidden
    toastDiv.addEventListener('hidden.bs.toast', () => {
        toastDiv.remove();
    });
}

async function loadCampaigns() {
    const loadingDiv = document.createElement('div');
    loadingDiv.className = 'text-center py-4';
    loadingDiv.innerHTML = `
        <div class="spinner-border text-primary" role="status">
            <span class="visually-hidden">Carregando...</span>
        </div>
        <p class="mt-2">Carregando campanhas...</p>
    `;
    
    const list = document.getElementById('campaignsList');
    list.innerHTML = '';
    list.appendChild(loadingDiv);
    
    try {
        const [campaignsResponse, integrationsResponse] = await Promise.all([
            fetch('/api/campaigns').then(res => {
                if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
                return res.json();
            }),
            fetch('/api/integrations').then(res => {
                if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
                return res.json();
            })
        ]);
        
        const integrationSelect = document.getElementById('integrationId');
        integrationSelect.innerHTML = `<option value="">Selecione uma Integração</option>` + 
            integrationsResponse.map(integration => 
                `<option value="${integration.id}">${integration.name}</option>`
            ).join('');
        
        list.innerHTML = '';
        
        if (campaignsResponse.length === 0) {
            list.innerHTML = `
                <div class="alert alert-info" role="alert">
                    <i class="fas fa-info-circle me-2"></i>
                    Nenhuma campanha encontrada. Crie sua primeira campanha usando o formulário acima.
                </div>
            `;
            return;
        }
        
        campaignsResponse.forEach(campaign => {
            const integration = integrationsResponse.find(i => i.id === campaign.integration_id);
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
                                <code class="d-block p-2 bg-dark rounded mt-2">${campaign.message_template}</code>
                            </p>
                            <p class="card-text"><small class="text-muted">Criada em: ${campaign.created_at}</small></p>
                        </div>
                        <div class="d-flex flex-column gap-2">
                            <button class="btn btn-sm btn-primary" onclick="editCampaign('${campaign.id}')">
                                <i class="fas fa-edit me-1"></i> Editar
                            </button>
                            <button class="btn btn-sm btn-danger" onclick="deleteCampaign('${campaign.id}')">
                                <i class="fas fa-trash me-1"></i> Excluir
                            </button>
                        </div>
                    </div>
                </div>
            `;
            list.appendChild(div);
        });
    } catch (error) {
        console.error('Erro ao carregar dados:', error);
        list.innerHTML = `
            <div class="alert alert-danger" role="alert">
                <i class="fas fa-exclamation-circle me-2"></i>
                Erro ao carregar campanhas e integrações: ${error.message}
                <button class="btn btn-outline-danger btn-sm ms-3" onclick="loadCampaigns()">
                    <i class="fas fa-sync-alt me-1"></i> Tentar novamente
                </button>
            </div>
        `;
    }
}

document.getElementById('campaignForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const submitButton = e.target.querySelector('button[type="submit"]');
    const originalText = submitButton.innerHTML;
    submitButton.disabled = true;
    
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
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || 'Erro ao salvar campanha');
        }
        
        showToast('success', `Campanha ${campaignId ? 'atualizada' : 'criada'} com sucesso!`);
        resetForm();
        loadCampaigns();
    } catch (error) {
        console.error('Erro ao salvar campanha:', error);
        showToast('error', error.message);
    } finally {
        submitButton.disabled = false;
        submitButton.innerHTML = originalText;
    }
});

function resetForm() {
    const form = document.getElementById('campaignForm');
    form.reset();
    delete form.dataset.campaignId;
    document.getElementById('integrationId').disabled = false;
    document.querySelector('button[type="submit"]').innerHTML = '<i class="fas fa-plus me-1"></i> Criar Campanha';
    
    const errorDivs = form.querySelectorAll('.alert-danger');
    errorDivs.forEach(div => div.remove());
}

async function editCampaign(campaignId) {
    try {
        const response = await fetch('/api/campaigns');
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        
        const campaigns = await response.json();
        const campaign = campaigns.find(c => c.id === campaignId);
        
        if (!campaign) {
            throw new Error('Campanha não encontrada');
        }
        
        const form = document.getElementById('campaignForm');
        form.dataset.campaignId = campaignId;
        
        document.getElementById('campaignName').value = campaign.name;
        document.getElementById('integrationId').value = campaign.integration_id;
        document.getElementById('integrationId').disabled = true;
        document.getElementById('eventType').value = campaign.event_type;
        document.getElementById('messageTemplate').value = campaign.message_template;
        
        document.querySelector('button[type="submit"]').innerHTML = `
            <i class="fas fa-save me-1"></i>
            Atualizar Campanha
        `;
        
        form.scrollIntoView({ behavior: 'smooth' });
    } catch (error) {
        console.error('Erro ao carregar campanha para edição:', error);
        showToast('error', `Erro ao carregar dados da campanha: ${error.message}`);
    }
}

async function deleteCampaign(campaignId) {
    if (!confirm('Tem certeza que deseja excluir esta campanha?')) {
        return;
    }
    
    const campaignCard = document.querySelector(`[onclick="deleteCampaign('${campaignId}')"]`).closest('.card');
    const originalContent = campaignCard.innerHTML;
    
    campaignCard.innerHTML = `
        <div class="card-body text-center">
            <div class="spinner-border text-danger" role="status">
                <span class="visually-hidden">Excluindo...</span>
            </div>
            <p class="mt-2">Excluindo campanha...</p>
        </div>
    `;
    
    try {
        const response = await fetch(`/api/campaigns/${campaignId}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.error || 'Erro ao excluir campanha');
        }
        
        campaignCard.style.transition = 'all 0.3s ease-out';
        campaignCard.style.opacity = '0';
        campaignCard.style.transform = 'translateX(100%)';
        
        setTimeout(() => {
            campaignCard.remove();
            resetForm();
            loadCampaigns();
        }, 300);
    } catch (error) {
        console.error('Erro ao excluir campanha:', error);
        campaignCard.innerHTML = originalContent;
        showToast('error', `Erro ao excluir campanha: ${error.message}`);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    loadCampaigns();
    
    const cancelButton = document.createElement('button');
    cancelButton.type = 'button';
    cancelButton.className = 'btn btn-secondary ms-2';
    cancelButton.innerHTML = '<i class="fas fa-times me-1"></i> Cancelar';
    cancelButton.onclick = resetForm;
    
    const submitButton = document.querySelector('button[type="submit"]');
    submitButton.innerHTML = '<i class="fas fa-plus me-1"></i> Criar Campanha';
    submitButton.parentNode.insertBefore(cancelButton, submitButton.nextSibling);
});
