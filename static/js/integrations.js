// Carregar integrações existentes
async function loadIntegrations() {
    try {
        const response = await fetch('/api/integrations');
        const integrations = await response.json();
        
        const list = document.getElementById('integrationsList');
        list.innerHTML = '';
        
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
                                <code>${window.location.origin}${integration.webhook_url}</code>
                                <button class="btn btn-sm btn-outline-secondary ms-2" onclick="copyToClipboard('${window.location.origin}${integration.webhook_url}')">
                                    Copiar
                                </button>
                            </p>
                            <p class="card-text"><small class="text-muted">Criada em: ${integration.created_at}</small></p>
                        </div>
                        <button class="btn btn-danger" onclick="deleteIntegration('${integration.id}')">Excluir</button>
                    </div>
                </div>
            `;
            list.appendChild(div);
        });
    } catch (error) {
        console.error('Erro ao carregar integrações:', error);
        alert('Erro ao carregar integrações. Por favor, tente novamente.');
    }
}

// Copiar URL do webhook para a área de transferência
async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
        alert('URL do webhook copiada para a área de transferência!');
    } catch (err) {
        console.error('Falha ao copiar texto: ', err);
    }
}

// Manipular criação de integração
document.getElementById('integrationForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const name = document.getElementById('integrationName').value;
    
    try {
        const response = await fetch('/api/integrations', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ name })
        });
        
        if (response.ok) {
            alert('Integração criada com sucesso!');
            e.target.reset();
            loadIntegrations();
        } else {
            const data = await response.json();
            alert(`Erro ao criar integração: ${data.error}`);
        }
    } catch (error) {
        console.error('Erro ao criar integração:', error);
        alert('Erro ao criar integração. Por favor, tente novamente.');
    }
});

// Excluir integração
async function deleteIntegration(integrationId) {
    if (!confirm('Tem certeza que deseja excluir esta integração? Isso também excluirá todas as campanhas associadas.')) {
        return;
    }
    
    try {
        const response = await fetch(`/api/integrations/${integrationId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            alert('Integração excluída com sucesso!');
            loadIntegrations();
        } else {
            const data = await response.json();
            alert(`Erro ao excluir integração: ${data.error}`);
        }
    } catch (error) {
        console.error('Erro ao excluir integração:', error);
        alert('Erro ao excluir integração. Por favor, tente novamente.');
    }
}

// Carregar integrações quando a página carregar
document.addEventListener('DOMContentLoaded', loadIntegrations);
