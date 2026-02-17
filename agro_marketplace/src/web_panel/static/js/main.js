// Agro Marketplace Admin Panel - main.js
// Auto-dismiss alerts after 5s
document.querySelectorAll('.alert').forEach(a => {
  setTimeout(() => { a.style.opacity = '0'; a.style.transition = 'opacity 0.5s'; setTimeout(() => a.remove(), 500); }, 5000);
});
