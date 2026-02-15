// ==================== 
// MODERN AGRO MARKETPLACE ADMIN PANEL - JavaScript
// ==================== 

document.addEventListener('DOMContentLoaded', function() {
    // Initialize all components
    initSidebar();
    initSync();
    initNotifications();
    initAnimations();
    initTooltips();
});

// ==================== 
// SIDEBAR
// ==================== 

function initSidebar() {
    const sidebarToggle = document.getElementById('sidebarToggle');
    const sidebar = document.getElementById('sidebar');
    const mainContent = document.getElementById('mainContent');

    if (sidebarToggle) {
        sidebarToggle.addEventListener('click', function() {
            sidebar.classList.toggle('collapsed');
            mainContent.classList.toggle('expanded');
        });
    }

    // Active nav item animation
    const navItems = document.querySelectorAll('.nav-item');
    navItems.forEach(item => {
        item.addEventListener('click', function() {
            navItems.forEach(nav => nav.classList.remove('active'));
            this.classList.add('active');
        });
    });
}

// ==================== 
// SYNC STATUS
// ==================== 

function initSync() {
    const syncBtn = document.getElementById('syncBtn');
    const syncStatus = document.getElementById('syncStatus');

    if (syncBtn) {
        syncBtn.addEventListener('click', async function() {
            // Add spinning animation
            const icon = this.querySelector('i');
            icon.classList.add('fa-spin');
            
            // Simulate sync process
            await simulateSync();
            
            // Remove spinning animation
            setTimeout(() => {
                icon.classList.remove('fa-spin');
                showNotification('Синхронізація завершена успішно', 'success');
            }, 1500);
        });
    }
}

async function simulateSync() {
    return new Promise(resolve => {
        setTimeout(resolve, 1500);
    });
}

// ==================== 
// NOTIFICATIONS
// ==================== 

function initNotifications() {
    const notificationBtn = document.getElementById('notificationBtn');
    
    if (notificationBtn) {
        notificationBtn.addEventListener('click', function() {
            showNotificationPanel();
        });
    }

    // Auto-hide alerts after 5 seconds
    const alerts = document.querySelectorAll('.alert-modern');
    alerts.forEach(alert => {
        setTimeout(() => {
            fadeOutAlert(alert);
        }, 5000);
    });
}

function showNotificationPanel() {
    // Create notification panel
    const panel = document.createElement('div');
    panel.className = 'notification-panel';
    panel.innerHTML = `
        <div class="notification-header">
            <h3>Сповіщення</h3>
            <button class="close-panel" onclick="this.parentElement.parentElement.remove()">
                <i class="fas fa-times"></i>
            </button>
        </div>
        <div class="notification-list">
            <div class="notification-item">
                <div class="notification-icon notification-success">
                    <i class="fas fa-check"></i>
                </div>
                <div class="notification-content">
                    <div class="notification-title">Новий лот додано</div>
                    <div class="notification-time">5 хвилин тому</div>
                </div>
            </div>
            <div class="notification-item">
                <div class="notification-icon notification-info">
                    <i class="fas fa-user"></i>
                </div>
                <div class="notification-content">
                    <div class="notification-title">Новий користувач зареєстрований</div>
                    <div class="notification-time">10 хвилин тому</div>
                </div>
            </div>
            <div class="notification-item">
                <div class="notification-icon notification-warning">
                    <i class="fas fa-exclamation-triangle"></i>
                </div>
                <div class="notification-content">
                    <div class="notification-title">Лот потребує модерації</div>
                    <div class="notification-time">20 хвилин тому</div>
                </div>
            </div>
        </div>
    `;
    
    document.body.appendChild(panel);
    
    // Add styles for notification panel
    const style = document.createElement('style');
    style.textContent = `
        .notification-panel {
            position: fixed;
            right: 20px;
            top: 80px;
            width: 380px;
            background: white;
            border-radius: 16px;
            box-shadow: 0 20px 50px rgba(0, 0, 0, 0.15);
            z-index: 2000;
            animation: slideIn 0.3s ease;
        }
        
        @keyframes slideIn {
            from {
                opacity: 0;
                transform: translateY(-20px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        .notification-header {
            padding: 20px;
            border-bottom: 1px solid #e5e7eb;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        
        .notification-header h3 {
            margin: 0;
            font-size: 18px;
            font-weight: 700;
        }
        
        .close-panel {
            background: none;
            border: none;
            cursor: pointer;
            padding: 8px;
            color: #6b7280;
            transition: all 0.2s;
        }
        
        .close-panel:hover {
            color: #111827;
        }
        
        .notification-list {
            max-height: 400px;
            overflow-y: auto;
        }
        
        .notification-item {
            padding: 16px 20px;
            display: flex;
            gap: 12px;
            border-bottom: 1px solid #f3f4f6;
            transition: all 0.2s;
        }
        
        .notification-item:hover {
            background: #f9fafb;
        }
        
        .notification-icon {
            width: 40px;
            height: 40px;
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            flex-shrink: 0;
        }
        
        .notification-success {
            background: linear-gradient(135deg, #10b981, #059669);
        }
        
        .notification-info {
            background: linear-gradient(135deg, #3b82f6, #2563eb);
        }
        
        .notification-warning {
            background: linear-gradient(135deg, #f59e0b, #d97706);
        }
        
        .notification-content {
            flex: 1;
        }
        
        .notification-title {
            font-weight: 600;
            color: #111827;
            margin-bottom: 4px;
        }
        
        .notification-time {
            font-size: 13px;
            color: #6b7280;
        }
    `;
    document.head.appendChild(style);
    
    // Close on outside click
    setTimeout(() => {
        document.addEventListener('click', function closePanel(e) {
            if (!panel.contains(e.target) && !notificationBtn.contains(e.target)) {
                panel.remove();
                document.removeEventListener('click', closePanel);
            }
        });
    }, 100);
}

function fadeOutAlert(alert) {
    alert.style.transition = 'all 0.3s ease';
    alert.style.opacity = '0';
    alert.style.transform = 'translateY(-10px)';
    
    setTimeout(() => {
        alert.remove();
    }, 300);
}

function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `alert alert-${type} alert-modern`;
    notification.style.position = 'fixed';
    notification.style.top = '20px';
    notification.style.right = '20px';
    notification.style.zIndex = '9999';
    notification.style.minWidth = '300px';
    
    const icon = type === 'success' ? 'check-circle' : 
                 type === 'danger' ? 'exclamation-circle' : 'info-circle';
    
    notification.innerHTML = `
        <i class="fas fa-${icon}"></i>
        <span>${message}</span>
        <button type="button" class="alert-close" onclick="this.parentElement.remove()">
            <i class="fas fa-times"></i>
        </button>
    `;
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
        fadeOutAlert(notification);
    }, 5000);
}

// ==================== 
// ANIMATIONS
// ==================== 

function initAnimations() {
    // Animate cards on scroll
    const observerOptions = {
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px'
    };

    const observer = new IntersectionObserver(function(entries) {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.style.opacity = '0';
                entry.target.style.transform = 'translateY(20px)';
                
                setTimeout(() => {
                    entry.target.style.transition = 'all 0.5s ease';
                    entry.target.style.opacity = '1';
                    entry.target.style.transform = 'translateY(0)';
                }, 100);
                
                observer.unobserve(entry.target);
            }
        });
    }, observerOptions);

    // Observe all cards
    const cards = document.querySelectorAll('.stat-card, .dashboard-card, .lot-card, .info-card');
    cards.forEach((card, index) => {
        card.style.transitionDelay = `${index * 0.1}s`;
        observer.observe(card);
    });

    // Smooth scroll to top
    const scrollButton = document.createElement('button');
    scrollButton.className = 'scroll-to-top';
    scrollButton.innerHTML = '<i class="fas fa-arrow-up"></i>';
    scrollButton.style.cssText = `
        position: fixed;
        bottom: 30px;
        right: 30px;
        width: 50px;
        height: 50px;
        background: linear-gradient(135deg, #10b981, #059669);
        border: none;
        border-radius: 50%;
        color: white;
        font-size: 18px;
        cursor: pointer;
        box-shadow: 0 4px 12px rgba(16, 185, 129, 0.4);
        opacity: 0;
        transform: translateY(20px);
        transition: all 0.3s ease;
        z-index: 1000;
    `;
    
    document.body.appendChild(scrollButton);
    
    window.addEventListener('scroll', function() {
        if (window.pageYOffset > 300) {
            scrollButton.style.opacity = '1';
            scrollButton.style.transform = 'translateY(0)';
        } else {
            scrollButton.style.opacity = '0';
            scrollButton.style.transform = 'translateY(20px)';
        }
    });
    
    scrollButton.addEventListener('click', function() {
        window.scrollTo({
            top: 0,
            behavior: 'smooth'
        });
    });
}

// ==================== 
// TOOLTIPS
// ==================== 

function initTooltips() {
    const tooltipElements = document.querySelectorAll('[title]');
    
    tooltipElements.forEach(element => {
        if (element.title && !element.getAttribute('data-tooltip-initialized')) {
            const title = element.title;
            element.removeAttribute('title');
            element.setAttribute('data-tooltip', title);
            element.setAttribute('data-tooltip-initialized', 'true');
            
            element.addEventListener('mouseenter', showTooltip);
            element.addEventListener('mouseleave', hideTooltip);
        }
    });
}

function showTooltip(e) {
    const text = e.currentTarget.getAttribute('data-tooltip');
    if (!text) return;
    
    const tooltip = document.createElement('div');
    tooltip.className = 'custom-tooltip';
    tooltip.textContent = text;
    tooltip.style.cssText = `
        position: fixed;
        background: #111827;
        color: white;
        padding: 8px 12px;
        border-radius: 6px;
        font-size: 13px;
        font-weight: 500;
        pointer-events: none;
        z-index: 10000;
        white-space: nowrap;
        animation: tooltipFadeIn 0.2s ease;
    `;
    
    document.body.appendChild(tooltip);
    
    const rect = e.currentTarget.getBoundingClientRect();
    const tooltipRect = tooltip.getBoundingClientRect();
    
    tooltip.style.left = `${rect.left + (rect.width / 2) - (tooltipRect.width / 2)}px`;
    tooltip.style.top = `${rect.top - tooltipRect.height - 8}px`;
    
    e.currentTarget._tooltip = tooltip;
    
    // Add animation
    const style = document.createElement('style');
    style.textContent = `
        @keyframes tooltipFadeIn {
            from {
                opacity: 0;
                transform: translateY(5px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
    `;
    if (!document.querySelector('style[data-tooltip-animation]')) {
        style.setAttribute('data-tooltip-animation', 'true');
        document.head.appendChild(style);
    }
}

function hideTooltip(e) {
    if (e.currentTarget._tooltip) {
        e.currentTarget._tooltip.remove();
        delete e.currentTarget._tooltip;
    }
}

// ==================== 
// TABLE INTERACTIONS
// ==================== 

// Confirm before delete/ban actions
document.addEventListener('click', function(e) {
    const banBtn = e.target.closest('.btn-action-danger');
    if (banBtn && banBtn.closest('form')) {
        if (!confirm('Ви впевнені, що хочете виконати цю дію?')) {
            e.preventDefault();
        }
    }
});

// ==================== 
// SEARCH ENHANCEMENTS
// ==================== 

const searchInput = document.querySelector('.search-input');
if (searchInput) {
    // Add search on Enter key
    searchInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            this.closest('form').submit();
        }
    });
    
    // Show clear button when typing
    searchInput.addEventListener('input', function() {
        const clearBtn = this.parentElement.querySelector('.search-clear');
        if (clearBtn) {
            clearBtn.style.display = this.value ? 'block' : 'none';
        }
    });
}

// ==================== 
// LIVE UPDATES (WebSocket simulation)
// ==================== 

function simulateLiveUpdates() {
    setInterval(() => {
        updateSyncStatus();
    }, 30000); // Update every 30 seconds
}

function updateSyncStatus() {
    const syncStatus = document.getElementById('syncStatus');
    if (syncStatus) {
        const statusDot = syncStatus.querySelector('.status-dot');
        statusDot.style.animation = 'none';
        setTimeout(() => {
            statusDot.style.animation = 'pulse 2s infinite';
        }, 10);
    }
}

// Initialize live updates
simulateLiveUpdates();

// ==================== 
// EXPORT FUNCTIONALITY
// ==================== 

document.querySelectorAll('.btn-success').forEach(btn => {
    if (btn.textContent.includes('Експорт')) {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            showNotification('Експорт даних почався...', 'info');
            
            setTimeout(() => {
                showNotification('Дані успішно експортовані!', 'success');
            }, 2000);
        });
    }
});

// ==================== 
// PERFORMANCE MONITORING
// ==================== 

console.log('%c🌾 Agro Marketplace Admin Panel', 'font-size: 20px; color: #10b981; font-weight: bold');
console.log('%cПанель адміністратора готова до роботи!', 'font-size: 14px; color: #6b7280');
console.log('%cВерсія: 2.0 | Синхронізовано з Telegram Bot', 'font-size: 12px; color: #9ca3af');

// ==================== 
// BUTTON FIX - Виправлення кнопок форм
// ==================== 

document.addEventListener('DOMContentLoaded', function() {
    // Виправлення кнопок ban/unban
    const actionForms = document.querySelectorAll('form[action*="ban"], form[action*="unban"]');
    actionForms.forEach(form => {
        form.addEventListener('submit', function(e) {
            const button = this.querySelector('button[type="submit"]');
            if (button && button.classList.contains('btn-action-danger')) {
                if (!confirm('Ви впевнені, що хочете виконати цю дію?')) {
                    e.preventDefault();
                    return false;
                }
            }
        });
    });
    
    // Виправлення експорту
    const exportButtons = document.querySelectorAll('[href*="export"]');
    exportButtons.forEach(btn => {
        btn.addEventListener('click', function(e) {
            showNotification('Завантаження файлу...', 'info');
        });
    });
});

// ==================== 
// FORM VALIDATION
// ==================== 

document.querySelectorAll('form').forEach(form => {
    // Форма логіну працює без додаткової валідації (браузер валідує через required)
    const action = form.getAttribute('action');
    
    // Пропускаємо форми які не потребують JS валідації
    if (!action || 
        action.includes('/login') || 
        action.includes('ban') || 
        action.includes('unban') || 
        action.includes('close')) {
        return;
    }
    
    form.addEventListener('submit', function(e) {
        const requiredInputs = this.querySelectorAll('[required]');
        let isValid = true;
        
        requiredInputs.forEach(input => {
            if (!input.value.trim()) {
                isValid = false;
                input.classList.add('is-invalid');
                
                if (!input.nextElementSibling || !input.nextElementSibling.classList.contains('invalid-feedback')) {
                    const feedback = document.createElement('div');
                    feedback.className = 'invalid-feedback';
                    feedback.textContent = 'Це поле обов\'язкове';
                    input.parentNode.appendChild(feedback);
                }
            } else {
                input.classList.remove('is-invalid');
                const feedback = input.nextElementSibling;
                if (feedback && feedback.classList.contains('invalid-feedback')) {
                    feedback.remove();
                }
            }
        });
        
        if (!isValid) {
            e.preventDefault();
            if (typeof showNotification === 'function') {
                showNotification('Будь ласка, заповніть всі обов\'язкові поля', 'danger');
            }
        }
    });
});

document.querySelectorAll('input[required], textarea[required]').forEach(input => {
    input.addEventListener('input', function() {
        if (this.value.trim()) {
            this.classList.remove('is-invalid');
            const feedback = this.nextElementSibling;
            if (feedback && feedback.classList.contains('invalid-feedback')) {
                feedback.remove();
            }
        }
    });
});

console.log('%c✅ All fixes applied!', 'color: #10b981; font-weight: bold; font-size: 14px');
