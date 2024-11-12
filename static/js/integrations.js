// Carregar integrações existentes
async function loadIntegrations() {
    const list = document.getElementById('integrationsList');
    
    // Show loading state
    list.innerHTML = `
        <div class="bg-surface p-6 rounded-xl border border-surface-light/20 text-center">
            <div class="inline-block animate-spin">
                <i class="fas fa-circle-notch text-primary text-xl"></i>
            </div>
            <p class="mt-2 text-gray-400">Carregando integrações...</p>
        </div>
    `;
    
    try {
        const response = await fetch('/api/integrations');
        if (!response.ok) {
            throw new Error('Erro ao carregar dados');
        }
        
        const integrations = await response.json();
        list.innerHTML = '';
        
        if (integrations.length === 0) {
            list.innerHTML = `
                <div class="bg-surface p-6 rounded-xl border border-surface-light/20">
                    <div class="flex items-center text-gray-400">
                        <i class="fas fa-info-circle mr-3 text-xl"></i>
                        <div>
                            <h4 class="font-medium mb-1">Nenhuma integração encontrada</h4>
                            <p class="text-sm">Crie sua primeira integração usando o formulário acima.</p>
                        </div>
                    </div>
                </div>
            `;
            return;
        }
        
        integrations.forEach(integration => {
            const webhookUrl = `${window.location.origin}${integration.webhook_url}`;
            const div = document.createElement('div');
            div.className = 'bg-surface p-6 rounded-xl border border-surface-light/20 hover:shadow-xl transition-all duration-300';
            div.innerHTML = `
                <div class="flex justify-between items-start">
                    <div class="flex-grow-1 space-y-4">
                        <div class="flex items-center">
                            <h3 class="text-lg font-medium text-white">${integration.name}</h3>
                            <span class="ml-2 px-2 py-1 text-xs font-medium rounded-full bg-green-900/50 text-green-400 border border-green-700">
                                Ativo
                            </span>
                        </div>
                        <div class="space-y-2">
                            <label class="block text-sm font-medium text-gray-400">URL do Webhook:</label>
                            <div class="flex items-center gap-2">
                                <input type="text" class="flex-1 bg-background border border-surface-light rounded-lg p-3 text-gray-300 font-mono text-sm" value="${webhookUrl}" readonly>
                                <button onclick="copyToClipboard('${webhookUrl}')" class="px-3 py-2 rounded-lg bg-primary hover:bg-primary-dark text-white text-sm transition-colors">
                                    <i class="fas fa-copy"></i>
                                </button>
                            </div>
                        </div>
                        <p class="text-xs text-gray-500">Criada em: ${integration.created_at}</p>
                    </div>
                    <button onclick="deleteIntegration('${integration.id}')" class="px-3 py-2 rounded-lg bg-red-600 hover:bg-red-700 text-white text-sm transition-colors">
                        <i class="fas fa-trash mr-1"></i>Excluir
                    </button>
                </div>
            `;
            list.appendChild(div);
        });
    } catch (error) {
        console.error('Erro ao carregar integrações:', error);
        list.innerHTML = `
            <div class="bg-red-900/50 border border-red-700 rounded-xl p-6">
                <div class="flex items-center text-red-400">
                    <i class="fas fa-exclamation-circle mr-3 text-xl"></i>
                    <div>
                        <h4 class="font-medium mb-2">Erro ao carregar integrações</h4>
                        <p class="text-sm mb-3">${error.message}</p>
                        <button onclick="loadIntegrations()" class="px-4 py-2 bg-red-800 hover:bg-red-700 rounded-lg text-sm transition-colors">
                            <i class="fas fa-sync-alt mr-2"></i>Tentar novamente
                        </button>
                    </div>
                </div>
            </div>
        `;
    }
}

// Copiar URL do webhook para a área de transferência
async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
        showToast('success', 'URL do webhook copiada com sucesso!');
    } catch (err) {
        console.error('Falha ao copiar texto:', err);
        showToast('error', 'Não foi possível copiar a URL. Por favor, copie manualmente.');
    }
}

// Manipular criação de integração
document.getElementById('integrationForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const form = e.target;
    const submitButton = form.querySelector('button[type="submit"]');
    const originalText = submitButton.innerHTML;
    const nameInput = document.getElementById('integrationName');
    
    // Disable form during submission
    submitButton.disabled = true;
    nameInput.disabled = true;
    submitButton.innerHTML = `
        <i class="fas fa-circle-notch fa-spin mr-2"></i>
        Criando...
    `;
    
    try {
        const response = await fetch('/api/integrations', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ name: nameInput.value.trim() })
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || 'Erro ao criar integração');
        }
        
        showToast('success', 'Integração criada com sucesso!');
        form.reset();
        await loadIntegrations();
    } catch (error) {
        console.error('Erro ao criar integração:', error);
        showToast('error', error.message);
    } finally {
        submitButton.disabled = false;
        nameInput.disabled = false;
        submitButton.innerHTML = originalText;
    }
});

// Excluir integração
async function deleteIntegration(integrationId) {
    if (!confirm('Tem certeza que deseja excluir esta integração? Esta ação não pode ser desfeita.')) {
        return;
    }
    
    const integrationCard = document.querySelector(`[onclick="deleteIntegration('${integrationId}')"]`).closest('.bg-surface');
    const originalContent = integrationCard.innerHTML;
    
    integrationCard.innerHTML = `
        <div class="text-center py-4">
            <div class="inline-block animate-spin">
                <i class="fas fa-circle-notch text-red-400 text-xl"></i>
            </div>
            <p class="mt-2 text-gray-400">Excluindo integração...</p>
        </div>
    `;
    
    try {
        const response = await fetch(`/api/integrations/${integrationId}`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || 'Erro ao excluir integração');
        }
        
        // Animate removal
        integrationCard.style.transition = 'all 0.3s ease-out';
        integrationCard.style.opacity = '0';
        integrationCard.style.transform = 'translateX(100%)';
        
        setTimeout(() => {
            integrationCard.remove();
            loadIntegrations();
        }, 300);
        
        showToast('success', 'Integração excluída com sucesso!');
    } catch (error) {
        console.error('Erro ao excluir integração:', error);
        integrationCard.innerHTML = originalContent;
        showToast('error', error.message);
    }
}

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

// Initialize when the page loads
document.addEventListener('DOMContentLoaded', () => {
    loadIntegrations();
});