// JavaScript لصفحات الحضور

document.addEventListener('DOMContentLoaded', function() {
    console.log('Attendance page loaded');
    
    // تحديث الوقت الحالي
    setInterval(() => {
        const now = new Date();
        const timeString = now.toLocaleTimeString('ar-EG');
        console.log('Current time:', timeString);
    }, 60000); // كل دقيقة
});
