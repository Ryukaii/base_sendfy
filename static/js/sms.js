async function sendSMS() {
    const phone = document.getElementById('phone').value;
    const message = document.getElementById('message').value;
    const submitButton = document.querySelector('button[type="submit"]');
    
    submitButton.disabled = true;
    submitButton.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Enviando...';
    
    try {
        const response = await fetch('/api/send-sms', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ phone, message })
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || 'Erro ao enviar SMS');
        }
        
        showToast('success', 'SMS enviado com sucesso!');
        document.getElementById('smsForm').reset();
        
        // Update credits display
        const creditsDisplay = document.querySelector('.nav-link .credits');
        if (creditsDisplay) {
            creditsDisplay.textContent = data.credits_remaining;
        }
    } catch (error) {
        console.error('Erro:', error);
        showToast('error', error.message || 'Erro ao enviar SMS');
    } finally {
        submitButton.disabled = false;
        submitButton.innerHTML = '<i class="fas fa-paper-plane me-2"></i>Enviar SMS';
    }
}

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

document.getElementById('smsForm').addEventListener('submit', (e) => {
    e.preventDefault();
    sendSMS();
});
