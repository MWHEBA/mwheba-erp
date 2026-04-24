// JavaScript لصفحات الحضور

document.addEventListener('DOMContentLoaded', function() {
    
    // تحديث الوقت الحالي
    setInterval(() => {
        const now = new Date();
        const timeString = now.toLocaleTimeString('en-GB');
    }, 60000); // كل دقيقة
});
