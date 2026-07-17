// Basic interactives for Metaverse Sherpa Redesign

document.addEventListener('DOMContentLoaded', () => {
    // Add subtle glow effect following mouse cursor on glass cards
    const cards = document.querySelectorAll('.glass-card');
    
    cards.forEach(card => {
        card.addEventListener('mousemove', e => {
            const rect = card.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            
            if (card.classList.contains('active')) {
                card.style.background = `radial-gradient(circle at ${x}px ${y}px, rgba(0, 242, 161, 0.1) 0%, var(--color-surface-container) 50%)`;
            } else {
                card.style.background = `radial-gradient(circle at ${x}px ${y}px, rgba(255, 255, 255, 0.05) 0%, var(--color-surface-container) 50%)`;
            }
        });
        
        card.addEventListener('mouseleave', () => {
            card.style.background = 'var(--color-surface-container)';
        });
    });
});
