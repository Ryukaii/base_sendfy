// Handle form submission
document.getElementById('smsForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const submitButton = e.target.querySelector('button[type="submit"]');
    const originalText = submitButton.innerHTML;
    submitButton.disabled = true;
    submitButton.innerHTML = `<span class="spinner-border spinner-border-sm me-2"></span>Enviando...`;
    
    const phone = document.getElementById('phone').value;
    const message = document.getElementById('message').value;
    
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
        
        showToast('success', 'SMS enviado com sucesso');
        e.target.reset();
        
        // Update credits display
        if (data.credits_remaining !== undefined) {
            const creditsSpan = document.querySelector('.nav-link span');
            if (creditsSpan && creditsSpan.textContent.includes('Créditos:')) {
                creditsSpan.textContent = `Créditos: ${data.credits_remaining}`;
            }
        }
    } catch (error) {
        console.error('Erro:', error);
        showToast('error', error.message || 'Erro ao enviar SMS. Por favor, tente novamente.');
    } finally {
        submitButton.disabled = false;
        submitButton.innerHTML = originalText;
    }
});

// Update showToast function
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
        delay: 5000 // Increase display time for error messages
    });
    toast.show();
    
    // Remove toast element after it's hidden
    toastDiv.addEventListener('hidden.bs.toast', () => {
        toastDiv.remove();
    });
}

// Format phone number as user types
document.getElementById('phone').addEventListener('input', (e) => {
    let value = e.target.value.replace(/\D/g, '');
    if (value.length > 0) {
        if (value.length <= 2) {
            value = `(${value}`;
        } else if (value.length <= 7) {
            value = `(${value.substring(0,2)}) ${value.substring(2)}`;
        } else if (value.length <= 11) {
            value = `(${value.substring(0,2)}) ${value.substring(2,7)}-${value.substring(7)}`;
        } else {
            value = `(${value.substring(0,2)}) ${value.substring(2,7)}-${value.substring(7,11)}`;
        }
    }
    e.target.value = value;
});

// Character counter for message
document.getElementById('message').addEventListener('input', (e) => {
    const maxLength = 160;
    const remaining = maxLength - e.target.value.length;
    const counter = document.getElementById('messageCounter');
    if (counter) {
        counter.textContent = `${remaining} caracteres restantes`;
        counter.className = `small ${remaining < 20 ? 'text-warning' : 'text-muted'}`;
    }
});
