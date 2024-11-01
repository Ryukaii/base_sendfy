// Modal utility functions
const systemModal = new bootstrap.Modal(document.getElementById('systemModal'));
const confirmModal = new bootstrap.Modal(document.getElementById('confirmModal'));

// Show system message modal
function showMessage(title, message, type = 'info') {
    const modal = document.getElementById('systemModal');
    modal.querySelector('.modal-title').textContent = title;
    modal.querySelector('.modal-body').textContent = message;
    
    // Update modal header style based on message type
    const header = modal.querySelector('.modal-header');
    header.className = 'modal-header';
    header.classList.add(`bg-${type}`);
    
    systemModal.show();
}

// Show confirmation dialog
function showConfirm(message, callback) {
    const modal = document.getElementById('confirmModal');
    modal.querySelector('.modal-body').textContent = message;
    
    const yesButton = document.getElementById('confirmModalYes');
    
    // Remove existing event listeners
    const newButton = yesButton.cloneNode(true);
    yesButton.parentNode.replaceChild(newButton, yesButton);
    
    // Add new event listener
    newButton.addEventListener('click', () => {
        confirmModal.hide();
        callback();
    });
    
    confirmModal.show();
}
