/**
 * Main JavaScript file for the VRChat World Showcase Bot
 */
document.addEventListener('DOMContentLoaded', function() {
    console.log('VRChat World Showcase Bot web interface loaded');
    
    // Initialize dropdown toggles
    const dropdowns = document.querySelectorAll('.dropdown');
    if (dropdowns) {
        dropdowns.forEach(dropdown => {
            const button = dropdown.querySelector('button');
            const content = dropdown.querySelector('.dropdown-content');
            
            if (button && content) {
                button.addEventListener('click', function(e) {
                    e.stopPropagation();
                    content.classList.toggle('hidden');
                });
            }
        });
        
        // Close dropdowns when clicking outside
        document.addEventListener('click', function() {
            document.querySelectorAll('.dropdown-content').forEach(content => {
                content.classList.add('hidden');
            });
        });
    }
    
    // Handle alert closing
    const closeButtons = document.querySelectorAll('.close-btn');
    if (closeButtons) {
        closeButtons.forEach(button => {
            button.addEventListener('click', function() {
                this.parentElement.style.display = 'none';
            });
        });
    }
    
    // Auto-hide alerts after 5 seconds
    const alerts = document.querySelectorAll('.alert');
    if (alerts) {
        alerts.forEach(alert => {
            setTimeout(() => {
                alert.style.display = 'none';
            }, 5000);
        });
    }
    
    // Back to top button
    const backToTopButton = document.getElementById('backToTop');
    if (backToTopButton) {
        window.addEventListener('scroll', function() {
            if (window.pageYOffset > 300) {
                backToTopButton.classList.add('visible');
            } else {
                backToTopButton.classList.remove('visible');
            }
        });
        
        backToTopButton.addEventListener('click', function(e) {
            e.preventDefault();
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });
    }
});