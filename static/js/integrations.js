// Carregar integrações existentes
async function loadIntegrations() {
    const list = document.getElementById('integrationsList');
    list.innerHTML = `
        <div class="text-center py-4">
            <div class="spinner-border text-primary" role="status">
                <span class="visually-hidden">Carregando...</span>
            </div>
            <p class="mt-2">Carregando integrações...</p>
        </div>
    `;
    
    try {
        const response = await fetch('/api/integrations');
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        
        const integrations = await response.json();
        list.innerHTML = '';
        
        if (integrations.length === 0) {
            list.innerHTML = `
                <div class="alert alert-info" role="alert">
                    <i class="fas fa-info-circle me-2"></i>
                    Nenhuma integração encontrada. Crie sua primeira integração usando o formulário acima.
                </div>
            `;
            return;
        }
        
        integrations.forEach(integration => {
            const div = document.createElement('div');
            div.className = 'card mb-3';
            div.innerHTML = `
                <div class="card-body">
                    <div class="d-flex justify-content-between align-items-start">
                        <div>
                            <h5 class="card-title">${integration.name}</h5>
                            <p class="card-text">
                                <strong>URL do Webhook:</strong> 
                                <div class="input-group mb-3">
                                    <input type="text" class="form-control bg-dark" value="${window.location.origin}${integration.webhook_url}" readonly>
                                    <button class="btn btn-outline-secondary" onclick="copyToClipboard('${window.location.origin}${integration.webhook_url}')">
                                        <i class="fas fa-copy"></i>
                                    </button>
                                </div>
                            </p>
                            <p class="card-text"><small class="text-muted">Criada em: ${integration.created_at}</small></p>
                        </div>
                        <button class="btn btn-sm btn-danger" onclick="deleteIntegration('${integration.id}')">
                            <i class="fas fa-trash me-1"></i> Excluir
                        </button>
                    </div>
                </div>
            `;
            list.appendChild(div);
        });
    } catch (error) {
        console.error('Erro ao carregar integrações:', error);
        list.innerHTML = `
            <div class="alert alert-danger" role="alert">
                <i class="fas fa-exclamation-circle me-2"></i>
                Erro ao carregar integrações: ${error.message}
                <button class="btn btn-outline-danger btn-sm ms-3" onclick="loadIntegrations()">
                    <i class="fas fa-sync-alt me-1"></i> Tentar novamente
                </button>
            </div>
        `;
    }
}

// Copiar URL do webhook para a área de transferência
async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
        
        const toastDiv = document.createElement('div');
        toastDiv.className = 'position-fixed bottom-0 end-0 p-3';
        toastDiv.style.zIndex = '5';
        toastDiv.innerHTML = `
            <div class="toast align-items-center text-bg-success border-0" role="alert">
                <div class="d-flex">
                    <div class="toast-body">
                        <i class="fas fa-check-circle me-2"></i>
                        URL do webhook copiada para a área de transferência!
                    </div>
                    <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
                </div>
            </div>
        `;
        document.body.appendChild(toastDiv);
        const toast = new bootstrap.Toast(toastDiv.querySelector('.toast'));
        toast.show();
    } catch (err) {
        console.error('Falha ao copiar texto:', err);
        alert('Não foi possível copiar a URL. Por favor, copie manualmente.');
    }
}

// Manipular criação de integração
document.getElementById('integrationForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const submitButton = e.target.querySelector('button[type="submit"]');
    const originalText = submitButton.innerHTML;
    submitButton.disabled = true;
    submitButton.innerHTML = `
        <span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>
        Criando...
    `;
    
    const name = document.getElementById('integrationName').value;
    
    try {
        const response = await fetch('/api/integrations', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ name })
        });
        
        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.error || 'Erro ao criar integração');
        }
        
        const toastDiv = document.createElement('div');
        toastDiv.className = 'position-fixed bottom-0 end-0 p-3';
        toastDiv.style.zIndex = '5';
        toastDiv.innerHTML = `
            <div class="toast align-items-center text-bg-success border-0" role="alert">
                <div class="d-flex">
                    <div class="toast-body">
                        <i class="fas fa-check-circle me-2"></i>
                        Integração criada com sucesso!
                    </div>
                    <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
                </div>
            </div>
        `;
        document.body.appendChild(toastDiv);
        const toast = new bootstrap.Toast(toastDiv.querySelector('.toast'));
        toast.show();
        
        e.target.reset();
        loadIntegrations();
    } catch (error) {
        console.error('Erro ao criar integração:', error);
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

// Excluir integração
async function deleteIntegration(integrationId) {
    if (!confirm('Tem certeza que deseja excluir esta integração? Isso também excluirá todas as campanhas associadas.')) {
        return;
    }
    
    const integrationCard = document.querySelector(`[onclick="deleteIntegration('${integrationId}')"]`).closest('.card');
    const originalContent = integrationCard.innerHTML;
    
    integrationCard.innerHTML = `
        <div class="card-body text-center">
            <div class="spinner-border text-danger" role="status">
                <span class="visually-hidden">Excluindo...</span>
            </div>
            <p class="mt-2">Excluindo integração...</p>
        </div>
    `;
    
    try {
        const response = await fetch(`/api/integrations/${integrationId}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.error || 'Erro ao excluir integração');
        }
        
        integrationCard.style.transition = 'all 0.3s ease-out';
        integrationCard.style.opacity = '0';
        integrationCard.style.transform = 'translateX(100%)';
        
        setTimeout(() => {
            integrationCard.remove();
            loadIntegrations();
        }, 300);
    } catch (error) {
        console.error('Erro ao excluir integração:', error);
        integrationCard.innerHTML = originalContent;
        alert(`Erro ao excluir integração: ${error.message}`);
    }
}

// Carregar integrações quando a página carregar
document.addEventListener('DOMContentLoaded', () => {
    loadIntegrations();
    
    // Melhorar o botão de submit
    const submitButton = document.querySelector('button[type="submit"]');
    submitButton.innerHTML = '<i class="fas fa-plus me-1"></i> Criar Integração';
});
