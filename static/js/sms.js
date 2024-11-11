document.getElementById('smsForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const phone = document.getElementById('phone').value;
    const message = document.getElementById('message').value;
    const operator = document.getElementById('operator').value;
    
    try {
        const response = await fetch('/api/send-sms', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ phone, message, operator })
        });
        
        const data = await response.json();
        
        if (data.success) {
            alert('SMS enviado com sucesso! ID da tarefa: ' + data.task_id);
            e.target.reset();
        } else {
            alert('Erro ao enviar SMS: ' + data.message);
        }
    } catch (error) {
        alert('Erro ao enviar SMS: ' + error.message);
    }
});
