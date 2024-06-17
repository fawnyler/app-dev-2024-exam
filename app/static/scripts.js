document.addEventListener('DOMContentLoaded', function() {
    var descrTextarea = document.getElementById('descr');
    if (descrTextarea) {
        var easyMDE = new EasyMDE({
            element: descrTextarea
        });
    }
});