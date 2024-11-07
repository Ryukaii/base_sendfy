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
    
    toastDiv.addEventListener('hidden.bs.toast', () => {
        toastDiv.remove();
    });
}

async function loadCampaigns() {
    const list = document.getElementById('campaignsList');
    list.innerHTML = `
        <div class="text-center py-4">
            <div class="spinner-border text-primary" role="status">
                <span class="visually-hidden">Carregando...</span>
            </div>
            <p class="mt-2">Carregando campanhas...</p>
        </div>
    `;
    
    try {
        const [campaignsResponse, integrationsResponse] = await Promise.all([
            fetch('/api/campaigns'),
            fetch('/api/integrations')
        ]);
        
        const campaigns = await campaignsResponse.json();
        const integrations = await integrationsResponse.json();
        
        // Update integration select even if empty
        const integrationSelect = document.getElementById('integrationId');
        integrationSelect.innerHTML = '<option value="">Selecione uma Integração</option>';
        if (integrations && Array.isArray(integrations)) {
            integrations.forEach(integration => {
                integrationSelect.innerHTML += `
                    <option value="${integration.id}">${integration.name}</option>
                `;
            });
        }
        
        list.innerHTML = '';
        
        // Handle empty campaigns list
        if (!campaigns || !Array.isArray(campaigns) || campaigns.length === 0) {
            list.innerHTML = `
                <div class="alert alert-info" role="alert">
                    <i class="fas fa-info-circle me-2"></i>
                    Nenhuma campanha encontrada. Crie sua primeira campanha usando o formulário acima.
                </div>
            `;
            return;
        }
        
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
                                <strong>Mensagens:</strong><br>
                            </p>
                            <div class="messages-list">
                                ${campaign.messages.map((msg, idx) => `
                                    <div class="message-item mb-2 p-2 border rounded">
                                        <div class="d-flex justify-content-between">
                                            <strong>Mensagem #${idx + 1}</strong>
                                            <span class="badge ${msg.enabled ? 'bg-success' : 'bg-secondary'}">
                                                ${msg.enabled ? 'Ativo' : 'Inativo'}
                                            </span>
                                        </div>
                                        <div class="text-muted small">
                                            Atraso: ${msg.delay.amount} ${msg.delay.unit}
                                        </div>
                                        <code class="d-block p-2 bg-dark rounded mt-2">${msg.template}</code>
                                    </div>
                                `).join('')}
                            </div>
                            <p class="card-text mt-2"><small class="text-muted">Criada em: ${campaign.created_at}</small></p>
                        </div>
                        <div class="d-flex flex-column gap-2">
                            <button class="btn btn-sm btn-danger" onclick="deleteCampaign('${campaign.id}')">
                                <i class="fas fa-trash me-1"></i>
                                Excluir
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
                    <i class="fas fa-sync-alt me-1"></i>
                    Tentar novamente
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
    
    const messages = [];
    for (let i = 1; i <= 4; i++) {
        messages.push({
            enabled: document.getElementById(`messageEnabled${i}`).checked,
            template: document.getElementById(`messageTemplate${i}`).value,
            delay: {
                amount: parseInt(document.getElementById(`delayAmount${i}`).value) || 0,
                unit: document.getElementById(`delayUnit${i}`).value
            }
        });
    }
    
    const formData = {
        name: document.getElementById('campaignName').value,
        integration_id: document.getElementById('integrationId').value,
        event_type: document.getElementById('eventType').value,
        messages: messages
    };
    
    try {
        const response = await fetch('/api/campaigns', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(formData)
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || 'Erro ao salvar campanha');
        }
        
        showToast('success', 'Campanha criada com sucesso!');
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
    
    // Reset all message fields
    for (let i = 1; i <= 4; i++) {
        document.getElementById(`messageEnabled${i}`).checked = true;
        document.getElementById(`delayAmount${i}`).value = '0';
        document.getElementById(`delayUnit${i}`).value = 'minutes';
        document.getElementById(`messageTemplate${i}`).value = '';
    }
}

function insertVariable(variable, targetId) {
    const textarea = document.getElementById(targetId);
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const text = textarea.value;
    textarea.value = text.substring(0, start) + variable + text.substring(end);
    textarea.focus();
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
        
        showToast('success', 'Campanha excluída com sucesso!');
    } catch (error) {
        console.error('Erro ao excluir campanha:', error);
        campaignCard.innerHTML = originalContent;
        showToast('error', error.message);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    loadCampaigns();
});
