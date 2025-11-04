// JavaScript لصفحات الإجازات

document.addEventListener('DOMContentLoaded', function() {
    console.log('Leaves page loaded');
    
    // حساب عدد الأيام تلقائياً
    const startDate = document.querySelector('input[name="start_date"]');
    const endDate = document.querySelector('input[name="end_date"]');
    
    if (startDate && endDate) {
        const calculateDays = () => {
            if (startDate.value && endDate.value) {
                const start = new Date(startDate.value);
                const end = new Date(endDate.value);
                const days = Math.ceil((end - start) / (1000 * 60 * 60 * 24)) + 1;
                
                if (days > 0) {
                    console.log(`عدد الأيام: ${days}`);
                }
            }
        };
        
        startDate.addEventListener('change', calculateDays);
        endDate.addEventListener('change', calculateDays);
    }
});
