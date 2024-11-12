// Toast Notification Function
function showToast(type, message) {
    const toastDiv = document.createElement('div');
    toastDiv.className = 'fixed bottom-4 right-4 z-50 animate-fade-in';
    toastDiv.innerHTML = `
        <div class="rounded-lg shadow-lg p-4 mb-4 text-sm ${type === 'success' ? 'bg-green-900/50 text-green-400 border border-green-700' : 'bg-red-900/50 text-red-400 border border-red-700'}">
            <div class="flex items-center">
                <i class="fas ${type === 'success' ? 'fa-check-circle' : 'fa-exclamation-circle'} mr-2"></i>
                ${message}
            </div>
        </div>
    `;
    document.body.appendChild(toastDiv);
    
    setTimeout(() => {
        toastDiv.classList.add('animate-fade-out');
        setTimeout(() => toastDiv.remove(), 300);
    }, 3000);
}

function insertVariableEdit(variable) {
    const textarea = document.getElementById('editMessageTemplate');
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const text = textarea.value;
    textarea.value = text.substring(0, start) + variable + text.substring(end);
    textarea.focus();
}

async function loadCampaigns() {
    const list = document.getElementById('campaignsList');
    
    // Show loading state
    list.innerHTML = `
        <div class="bg-surface p-6 rounded-xl border border-surface-light/20 text-center">
            <div class="inline-block animate-spin">
                <i class="fas fa-circle-notch text-primary text-xl"></i>
            </div>
            <p class="mt-2 text-gray-400">Carregando campanhas...</p>
        </div>
    `;
    
    try {
        const [campaignsResponse, integrationsResponse] = await Promise.all([
            fetch('/api/campaigns'),
            fetch('/api/integrations')
        ]);
        
        if (!campaignsResponse.ok || !integrationsResponse.ok) {
            throw new Error('Erro ao carregar dados');
        }
        
        const [campaigns, integrations] = await Promise.all([
            campaignsResponse.json(),
            integrationsResponse.json()
        ]);
        
        const integrationSelect = document.getElementById('integrationId');
        integrationSelect.innerHTML = `
            <option value="" class="bg-background text-gray-500">Selecione uma Integração</option>
            ${integrations.map(integration => 
                `<option value="${integration.id}" class="bg-background text-white">${integration.name}</option>`
            ).join('')}
        `;
        
        list.innerHTML = '';
        
        if (campaigns.length === 0) {
            list.innerHTML = `
                <div class="bg-surface p-6 rounded-xl border border-surface-light/20">
                    <div class="flex items-center text-gray-400">
                        <i class="fas fa-info-circle mr-3 text-xl"></i>
                        <div>
                            <h4 class="font-medium mb-1">Nenhuma campanha encontrada</h4>
                            <p class="text-sm">Crie sua primeira campanha usando o formulário acima.</p>
                        </div>
                    </div>
                </div>
            `;
            return;
        }
        
        campaigns.forEach(campaign => {
            const integration = integrations.find(i => i.id === campaign.integration_id);
            const div = document.createElement('div');
            div.className = 'bg-surface p-6 rounded-xl border border-surface-light/20 hover:shadow-xl transition-all duration-300';
            div.innerHTML = `
                <div class="flex justify-between items-start">
                    <div class="space-y-4">
                        <h3 class="text-lg font-medium text-white">${campaign.name}</h3>
                        <div class="space-y-2">
                            <p class="text-sm text-gray-400">
                                <strong class="text-gray-300">Integração:</strong> ${integration ? integration.name : 'Desconhecida'}
                            </p>
                            <p class="text-sm text-gray-400">
                                <strong class="text-gray-300">Tipo de Evento:</strong> ${campaign.event_type}
                            </p>
                            <div class="mt-3">
                                <strong class="text-gray-300 text-sm">Modelo de Mensagem:</strong>
                                <code class="block mt-2 p-3 rounded-lg bg-background text-sm text-gray-300 font-mono">${campaign.message_template}</code>
                            </div>
                        </div>
                        <p class="text-xs text-gray-500">Criada em: ${campaign.created_at}</p>
                    </div>
                    <div class="flex flex-col gap-2">
                        <button onclick="editCampaign('${campaign.id}')" class="px-3 py-2 rounded-lg bg-primary hover:bg-primary-dark text-white text-sm transition-colors">
                            <i class="fas fa-edit mr-1"></i> Editar
                        </button>
                        <button onclick="deleteCampaign('${campaign.id}')" class="px-3 py-2 rounded-lg bg-red-600 hover:bg-red-700 text-white text-sm transition-colors">
                            <i class="fas fa-trash mr-1"></i> Excluir
                        </button>
                    </div>
                </div>
            `;
            list.appendChild(div);
        });
    } catch (error) {
        console.error('Erro ao carregar dados:', error);
        list.innerHTML = `
            <div class="bg-red-900/50 border border-red-700 rounded-xl p-6">
                <div class="flex items-center text-red-400">
                    <i class="fas fa-exclamation-circle mr-3 text-xl"></i>
                    <div>
                        <h4 class="font-medium mb-2">Erro ao carregar campanhas e integrações</h4>
                        <p class="text-sm mb-3">${error.message}</p>
                        <button onclick="loadCampaigns()" class="px-4 py-2 bg-red-800 hover:bg-red-700 rounded-lg text-sm transition-colors">
                            <i class="fas fa-sync-alt mr-2"></i>Tentar novamente
                        </button>
                    </div>
                </div>
            </div>
        `;
    }
}

async function editCampaign(campaignId) {
    try {
        const response = await fetch('/api/campaigns');
        if (!response.ok) throw new Error('Erro ao carregar campanha');
        
        const campaigns = await response.json();
        const campaign = campaigns.find(c => c.id === campaignId);
        
        if (!campaign) {
            throw new Error('Campanha não encontrada');
        }
        
        // Fill modal form
        document.getElementById('editCampaignId').value = campaignId;
        document.getElementById('editCampaignName').value = campaign.name;
        document.getElementById('editEventType').value = campaign.event_type;
        document.getElementById('editMessageTemplate').value = campaign.message_template;
        
        // Show modal
        document.getElementById('editCampaignModal').classList.remove('hidden');
    } catch (error) {
        console.error('Erro ao carregar campanha para edição:', error);
        showToast('error', error.message);
    }
}

async function updateCampaign() {
    const campaignId = document.getElementById('editCampaignId').value;
    const formData = {
        name: document.getElementById('editCampaignName').value,
        event_type: document.getElementById('editEventType').value,
        message_template: document.getElementById('editMessageTemplate').value
    };
    
    try {
        const response = await fetch(`/api/campaigns/${campaignId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(formData)
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || 'Erro ao atualizar campanha');
        }
        
        // Hide modal
        document.getElementById('editCampaignModal').classList.add('hidden');
        
        showToast('success', 'Campanha atualizada com sucesso!');
        loadCampaigns();
    } catch (error) {
        console.error('Erro ao atualizar campanha:', error);
        showToast('error', error.message);
    }
}

document.getElementById('campaignForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const submitButton = e.target.querySelector('button[type="submit"]');
    const originalText = submitButton.innerHTML;
    submitButton.disabled = true;
    submitButton.innerHTML = `
        <i class="fas fa-circle-notch fa-spin mr-2"></i>
        Criando...
    `;
    
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
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || 'Erro ao criar campanha');
        }
        
        showToast('success', 'Campanha criada com sucesso!');
        e.target.reset();
        loadCampaigns();
    } catch (error) {
        console.error('Erro ao salvar campanha:', error);
        showToast('error', error.message);
    } finally {
        submitButton.disabled = false;
        submitButton.innerHTML = originalText;
    }
});

async function deleteCampaign(campaignId) {
    if (!confirm('Tem certeza que deseja excluir esta campanha?')) {
        return;
    }
    
    const campaignCard = document.querySelector(`[onclick="deleteCampaign('${campaignId}')"]`).closest('.bg-surface');
    const originalContent = campaignCard.innerHTML;
    
    campaignCard.innerHTML = `
        <div class="text-center py-4">
            <div class="inline-block animate-spin">
                <i class="fas fa-circle-notch text-red-400 text-xl"></i>
            </div>
            <p class="mt-2 text-gray-400">Excluindo campanha...</p>
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
        showToast('error', error.message);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    loadCampaigns();
});
