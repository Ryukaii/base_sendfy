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
    if (!list) return;

    list.innerHTML = '';
    list.appendChild(loadingDiv);
    
    try {
        const [campaignsResponse, integrationsResponse] = await Promise.all([
            fetch(`${window.BASE_URL}/api/campaigns`).then(res => {
                if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
                return res.json();
            }),
            fetch(`${window.BASE_URL}/api/integrations`).then(res => {
                if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
                return res.json();
            })
        ]);
        
        // Preencher dropdown de integrações
        const integrationSelect = document.getElementById('integrationId');
        if (integrationSelect) {
            integrationSelect.innerHTML = `<option value="">Selecione uma Integração</option>` + 
                integrationsResponse.map(integration => 
                    `<option value="${integration.id}">${integration.name}</option>`
                ).join('');
        }
        
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

// Rest of your existing functions...

// Initialize when page loads
document.addEventListener('DOMContentLoaded', () => {
    const campaignForm = document.getElementById('campaignForm');
    if (campaignForm) {
        campaignForm.addEventListener('submit', async (e) => {
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
            let url = `${window.BASE_URL}/api/campaigns`;
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
    }

    loadCampaigns();
    addMessageToForm(); // Add one empty message by default
    
    // Adicionar manipulador do botão cancelar
    const cancelButton = document.createElement('button');
    cancelButton.type = 'button';
    cancelButton.className = 'btn btn-secondary ms-2';
    cancelButton.innerHTML = '<i class="fas fa-times me-1"></i> Cancelar';
    cancelButton.onclick = resetForm;
    
    const submitButton = document.querySelector('button[type="submit"]');
    if (submitButton) {
        submitButton.innerHTML = '<i class="fas fa-plus me-1"></i> Criar Campanha';
        submitButton.parentNode.insertBefore(cancelButton, submitButton.nextSibling);
    }
});
