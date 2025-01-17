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
                    Nenhuma campanha encontrada. Crie sua primeira campanha usando o botão acima.
                </div>
            `;
            return;
        }
        
        campaignsResponse.forEach(campaign => {
            const integration = integrationsResponse.find(i => i.id === campaign.integration_id);
            const delayText = campaign.delay_amount ? 
                `Atraso: ${campaign.delay_amount} ${campaign.delay_unit}` : 
                'Sem atraso';
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
                                <strong>Atraso:</strong> ${delayText}<br>
                                <strong>Modelo de Mensagem:</strong><br>
                                <code class="d-block p-2 bg-dark rounded mt-2">${campaign.message_template}</code>
                            </p>
                            <p class="card-text"><small class="text-muted">Criada em: ${campaign.created_at}</small></p>
                        </div>
                        <div class="d-flex flex-column gap-2">
                            <button class="btn btn-sm btn-primary" onclick="openCampaignModal('${campaign.id}')">
                                <i class="fas fa-edit me-1"></i> Editar
                            </button>
                            <button class="btn btn-sm btn-danger" onclick="deleteCampaign('${campaign.id}')">
                                <i class="fas fa-trash me-1"></i> Excluir
                            </button>
                            <button class="btn btn-sm btn-info" onclick="window.open('/preview-payment/${campaign.id}', '_blank')">
                                <i class="fas fa-eye me-1"></i> Visualizar
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

function openCampaignModal(campaignId = null) {
    const modal = new bootstrap.Modal(document.getElementById('campaignModal'));
    if (campaignId) {
        editCampaign(campaignId);
    } else {
        resetForm();
    }
    modal.show();
}

function saveCampaign() {
    document.getElementById('campaignForm').dispatchEvent(new Event('submit'));
}

async function editCampaign(campaignId) {
    try {
        const response = await fetch(`/api/campaigns/${campaignId}`);
        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.error || 'Campaign not found');
        }
        
        const campaign = await response.json();
        
        const form = document.getElementById('campaignForm');
        form.dataset.campaignId = campaignId;
        
        document.getElementById('campaignName').value = campaign.name;
        document.getElementById('integrationId').value = campaign.integration_id;
        document.getElementById('eventType').value = campaign.event_type;
        document.getElementById('messageTemplate').value = campaign.message_template;
        document.getElementById('delayAmount').value = campaign.delay_amount || 0;
        document.getElementById('delayUnit').value = campaign.delay_unit || 'minutes';
        
        // Payment page fields
        document.getElementById('paymentPageTitle').value = campaign.payment_page_title || '';
        document.getElementById('paymentPageLogoUrl').value = campaign.payment_page_logo_url || '';
        document.getElementById('paymentPageHeaderColor').value = campaign.payment_page_header_color || '#2FBDAE';
        document.getElementById('paymentPageButtonColor').value = campaign.payment_page_button_color || '#2FBDAE';
        document.getElementById('paymentPageTextColor').value = campaign.payment_page_text_color || '#000000';
        document.getElementById('paymentPageCustomText').value = campaign.payment_page_custom_text || '';
        
        document.getElementById('integrationId').disabled = true;
    } catch (error) {
        console.error('Erro ao carregar campanha para edição:', error);
        showToast('error', `Erro ao carregar dados da campanha: ${error.message}`);
    }
}

document.getElementById('campaignForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const submitButton = document.querySelector('.modal-footer .btn-primary');
    const originalText = submitButton.innerHTML;
    submitButton.disabled = true;
    submitButton.innerHTML = `<span class="spinner-border spinner-border-sm me-2"></span>Salvando...`;
    
    const formData = {
        name: document.getElementById('campaignName').value,
        integration_id: document.getElementById('integrationId').value,
        event_type: document.getElementById('eventType').value,
        message_template: document.getElementById('messageTemplate').value,
        delay_amount: parseInt(document.getElementById('delayAmount').value) || 0,
        delay_unit: document.getElementById('delayUnit').value,
        payment_page_title: document.getElementById('paymentPageTitle').value,
        payment_page_logo_url: document.getElementById('paymentPageLogoUrl').value,
        payment_page_header_color: document.getElementById('paymentPageHeaderColor').value,
        payment_page_button_color: document.getElementById('paymentPageButtonColor').value,
        payment_page_text_color: document.getElementById('paymentPageTextColor').value,
        payment_page_custom_text: document.getElementById('paymentPageCustomText').value
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
        bootstrap.Modal.getInstance(document.getElementById('campaignModal')).hide();
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
    
    // Reset color inputs to defaults
    document.getElementById('paymentPageHeaderColor').value = '#2FBDAE';
    document.getElementById('paymentPageButtonColor').value = '#2FBDAE';
    document.getElementById('paymentPageTextColor').value = '#000000';
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
            loadCampaigns();
        }, 300);
        
        showToast('success', 'Campanha excluída com sucesso!');
    } catch (error) {
        console.error('Erro ao excluir campanha:', error);
        campaignCard.innerHTML = originalContent;
        showToast('error', `Erro ao excluir campanha: ${error.message}`);
    }
}

function previewPaymentPage() {
    const campaignId = document.getElementById('campaignForm').dataset.campaignId;
    if (!campaignId) {
        showToast('error', 'Salve a campanha primeiro para visualizar a página');
        return;
    }
    window.open(`/preview-payment/${campaignId}`, '_blank');
}

document.addEventListener('DOMContentLoaded', () => {
    loadCampaigns();
});
