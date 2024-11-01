// Carregar campanhas e integrações existentes
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
        
        // Preencher dropdown de integrações
        const integrationSelect = document.getElementById('integrationId');
        integrationSelect.innerHTML = `<option value="">Selecione uma Integração</option>` + 
            integrationsResponse.map(integration => 
                `<option value="${integration.id}">${integration.name}</option>`
            ).join('');
        
        // Exibir campanhas
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
            
            const messagesHtml = campaign.messages.map((msg, index) => `
                <div class="card mb-2 bg-dark">
                    <div class="card-body">
                        <div class="d-flex justify-content-between align-items-center mb-2">
                            <h6 class="mb-0">Mensagem #${index + 1}</h6>
                            <span class="badge ${msg.is_active ? 'bg-success' : 'bg-danger'}">
                                ${msg.is_active ? 'Ativo' : 'Inativo'}
                            </span>
                        </div>
                        <p class="mb-2"><strong>Atraso:</strong> ${msg.delay_minutes} minutos</p>
                        <p class="mb-0"><strong>Mensagem:</strong></p>
                        <code class="d-block p-2 bg-dark rounded mt-2">${msg.template}</code>
                    </div>
                </div>
            `).join('');
            
            div.innerHTML = `
                <div class="card-body">
                    <div class="d-flex justify-content-between align-items-start">
                        <div>
                            <h5 class="card-title">${campaign.name}</h5>
                            <p class="card-text">
                                <strong>Integração:</strong> ${integration ? integration.name : 'Desconhecida'}<br>
                                <strong>Tipo de Evento:</strong> ${campaign.event_type}<br>
                                <strong>Mensagens:</strong>
                                <div class="mt-3">
                                    ${messagesHtml}
                                </div>
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

// Add message to form
function addMessageToForm(template = '', delay = 0, isActive = true) {
    const container = document.getElementById('messagesContainer');
    const messageTemplate = document.getElementById('messageTemplate');
    const messageElement = messageTemplate.content.cloneNode(true);
    
    const messageCount = container.children.length + 1;
    messageElement.querySelector('.message-number').textContent = messageCount;
    messageElement.querySelector('.message-template').value = template;
    messageElement.querySelector('.message-delay').value = delay;
    messageElement.querySelector('.message-active').checked = isActive;
    
    // Set up remove button
    messageElement.querySelector('.remove-message').addEventListener('click', function(e) {
        const card = e.target.closest('.message-card');
        card.remove();
        // Update message numbers
        container.querySelectorAll('.message-number').forEach((span, index) => {
            span.textContent = index + 1;
        });
    });
    
    container.appendChild(messageElement);
}

// Add message button handler
document.getElementById('addMessageBtn').addEventListener('click', () => {
    addMessageToForm();
});

// Get messages data from form
function getMessagesFromForm() {
    const messages = [];
    document.querySelectorAll('.message-card').forEach((card, index) => {
        messages.push({
            id: `msg${index + 1}`,
            template: card.querySelector('.message-template').value,
            delay_minutes: parseInt(card.querySelector('.message-delay').value) || 0,
            is_active: card.querySelector('.message-active').checked
        });
    });
    return messages;
}

// Manipular criação/atualização de campanha
document.getElementById('campaignForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const submitButton = e.target.querySelector('button[type="submit"]');
    const originalText = submitButton.innerHTML;
    submitButton.disabled = true;
    submitButton.innerHTML = `
        <span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>
        Salvando...
    `;
    
    const formData = {
        name: document.getElementById('campaignName').value,
        integration_id: document.getElementById('integrationId').value,
        event_type: document.getElementById('eventType').value,
        messages: getMessagesFromForm()
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
        
        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.error || 'Erro ao salvar campanha');
        }
        
        const toastDiv = document.createElement('div');
        toastDiv.className = 'position-fixed bottom-0 end-0 p-3';
        toastDiv.style.zIndex = '5';
        toastDiv.innerHTML = `
            <div class="toast align-items-center text-bg-success border-0" role="alert">
                <div class="d-flex">
                    <div class="toast-body">
                        <i class="fas fa-check-circle me-2"></i>
                        Campanha ${campaignId ? 'atualizada' : 'criada'} com sucesso!
                    </div>
                    <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
                </div>
            </div>
        `;
        document.body.appendChild(toastDiv);
        const toast = new bootstrap.Toast(toastDiv.querySelector('.toast'));
        toast.show();
        
        resetForm();
        loadCampaigns();
    } catch (error) {
        console.error('Erro ao salvar campanha:', error);
        const errorDiv = document.createElement('div');
        errorDiv.className = 'alert alert-danger mt-3';
        errorDiv.innerHTML = `
            <i class="fas fa-exclamation-circle me-2"></i>
            ${error.message}
        `;
        e.target.appendChild(errorDiv);
        setTimeout(() => errorDiv.remove(), 5000);
    } finally {
        submitButton.disabled = false;
        submitButton.innerHTML = originalText;
    }
});

// Resetar formulário para modo de criação
function resetForm() {
    const form = document.getElementById('campaignForm');
    form.reset();
    delete form.dataset.campaignId;
    document.getElementById('integrationId').disabled = false;
    document.querySelector('button[type="submit"]').textContent = 'Criar Campanha';
    document.getElementById('messagesContainer').innerHTML = '';
    addMessageToForm(); // Add one empty message by default
    
    // Remover mensagens de erro existentes
    const errorDivs = form.querySelectorAll('.alert-danger');
    errorDivs.forEach(div => div.remove());
}

// Carregar dados da campanha para edição
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
        
        // Clear and add messages
        document.getElementById('messagesContainer').innerHTML = '';
        campaign.messages.forEach(msg => {
            addMessageToForm(msg.template, msg.delay_minutes, msg.is_active);
        });
        
        document.querySelector('button[type="submit"]').innerHTML = `
            <i class="fas fa-save me-1"></i>
            Atualizar Campanha
        `;
        
        form.scrollIntoView({ behavior: 'smooth' });
    } catch (error) {
        console.error('Erro ao carregar campanha para edição:', error);
        alert(`Erro ao carregar dados da campanha: ${error.message}`);
    }
}

// Excluir campanha
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
        alert(`Erro ao excluir campanha: ${error.message}`);
    }
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', () => {
    loadCampaigns();
    addMessageToForm(); // Add one empty message by default
    
    // Adicionar manipulador do botão cancelar
    const cancelButton = document.createElement('button');
    cancelButton.type = 'button';
    cancelButton.className = 'btn btn-secondary ms-2';
    cancelButton.innerHTML = '<i class="fas fa-times me-1"></i> Cancelar';
    cancelButton.onclick = resetForm;
    
    const submitButton = document.querySelector('button[type="submit"]');
    submitButton.innerHTML = '<i class="fas fa-plus me-1"></i> Criar Campanha';
    submitButton.parentNode.insertBefore(cancelButton, submitButton.nextSibling);
});
