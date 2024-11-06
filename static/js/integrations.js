// Carregar integrações existentes
async function loadIntegrations() {
    const list = document.getElementById('integrationsList');
    
    // Show loading state
    list.innerHTML = `
        <div class="card mb-4">
            <div class="card-body text-center py-4">
                <div class="spinner-border text-primary mb-3" role="status">
                    <span class="visually-hidden">Carregando...</span>
                </div>
                <p class="text-muted mb-0">Carregando integrações...</p>
            </div>
        </div>
    `;
    
    try {
        const response = await fetch('/api/integrations');
        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.message || `HTTP error! status: ${response.status}`);
        }
        
        const integrations = await response.json();
        list.innerHTML = '';
        
        if (integrations.length === 0) {
            list.innerHTML = `
                <div class="alert alert-info" role="alert">
                    <div class="d-flex align-items-center">
                        <i class="fas fa-info-circle fa-lg me-3"></i>
                        <div>
                            <h5 class="alert-heading mb-1">Nenhuma integração encontrada</h5>
                            <p class="mb-0">Crie sua primeira integração usando o formulário acima.</p>
                        </div>
                    </div>
                </div>
            `;
            return;
        }
        
        integrations.forEach(integration => {
            const webhookUrl = `${window.location.origin}${integration.webhook_url}`;
            const div = document.createElement('div');
            div.className = 'card mb-4';
            div.innerHTML = `
                <div class="card-body">
                    <div class="d-flex justify-content-between align-items-start">
                        <div class="flex-grow-1">
                            <h5 class="card-title d-flex align-items-center">
                                ${integration.name}
                                <span class="badge bg-success ms-2">Ativo</span>
                            </h5>
                            <div class="mb-3">
                                <label class="form-label text-muted mb-1">URL do Webhook:</label>
                                <div class="input-group">
                                    <input type="text" class="form-control bg-dark" value="${webhookUrl}" readonly>
                                    <button class="btn btn-outline-primary" onclick="copyToClipboard('${webhookUrl}')">
                                        <i class="fas fa-copy"></i>
                                    </button>
                                </div>
                            </div>
                            <p class="card-text text-muted mb-0">
                                <small>Criada em: ${integration.created_at}</small>
                            </p>
                        </div>
                        <div class="ms-3">
                            <button class="btn btn-danger" onclick="deleteIntegration('${integration.id}')">
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
        console.error('Erro ao carregar integrações:', error);
        list.innerHTML = `
            <div class="alert alert-danger" role="alert">
                <div class="d-flex">
                    <i class="fas fa-exclamation-circle fa-lg me-3"></i>
                    <div>
                        <h5 class="alert-heading mb-1">Erro ao carregar integrações</h5>
                        <p class="mb-2">${error.message}</p>
                        <button class="btn btn-outline-danger btn-sm" onclick="loadIntegrations()">
                            <i class="fas fa-sync-alt me-1"></i>
                            Tentar novamente
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
        <span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
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
            throw new Error(data.message || 'Erro ao criar integração');
        }
        
        showToast('success', 'Integração criada com sucesso!');
        form.reset();
        loadIntegrations();
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
    const confirmDelete = await showConfirmDialog(
        'Excluir Integração',
        'Tem certeza que deseja excluir esta integração? Esta ação não pode ser desfeita.'
    );
    
    if (!confirmDelete) return;
    
    const integrationCard = document.querySelector(`[onclick="deleteIntegration('${integrationId}')"]`).closest('.card');
    const originalContent = integrationCard.innerHTML;
    
    integrationCard.innerHTML = `
        <div class="card-body text-center py-4">
            <div class="spinner-border text-danger mb-3" role="status">
                <span class="visually-hidden">Excluindo...</span>
            </div>
            <p class="text-muted mb-0">Excluindo integração...</p>
        </div>
    `;
    
    try {
        const response = await fetch(`/api/integrations/${integrationId}`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.message || 'Erro ao excluir integração');
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

// Utility function to show toast messages
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
    const toast = new bootstrap.Toast(toastDiv.querySelector('.toast'));
    toast.show();
    
    // Remove toast element after it's hidden
    toastDiv.addEventListener('hidden.bs.toast', () => {
        toastDiv.remove();
    });
}

// Utility function to show confirmation dialog
function showConfirmDialog(title, message) {
    return new Promise((resolve) => {
        const dialogDiv = document.createElement('div');
        dialogDiv.className = 'modal fade';
        dialogDiv.innerHTML = `
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">${title}</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <p>${message}</p>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancelar</button>
                        <button type="button" class="btn btn-danger" id="confirmButton">
                            <i class="fas fa-trash me-1"></i>
                            Excluir
                        </button>
                    </div>
                </div>
            </div>
        `;
        
        document.body.appendChild(dialogDiv);
        const modal = new bootstrap.Modal(dialogDiv);
        
        dialogDiv.querySelector('#confirmButton').addEventListener('click', () => {
            resolve(true);
            modal.hide();
        });
        
        dialogDiv.addEventListener('hidden.bs.modal', () => {
            resolve(false);
            dialogDiv.remove();
        });
        
        modal.show();
    });
}

// Initialize when the page loads
document.addEventListener('DOMContentLoaded', () => {
    loadIntegrations();
});
