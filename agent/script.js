document.addEventListener('DOMContentLoaded', () => {

    // Elements
    const contactsView = document.getElementById('view-contacts');
    const callView = document.getElementById('view-call');

    const callStatus = document.getElementById('call-status');
    const callTimer = document.getElementById('call-timer');
    const callerNameElement = document.getElementById('active-caller-name');
    const dynamicIsland = document.querySelector('.dynamic-island');
    const dashboardContent = document.getElementById('dashboard-content');

    let timerInterval;
    let seconds = 0;

    // ----- Eel Handlers (Called from Python) -----

    // Function to add log to dashboard
    eel.expose(add_log);
    function add_log(text, tag = 'sys') {
        const entry = document.createElement('div');
        entry.className = `log-entry log-${tag}`;
        entry.textContent = text;

        // Auto-scroll to bottom
        dashboardContent.appendChild(entry);
        dashboardContent.scrollTop = dashboardContent.scrollHeight;

        // If it's a "sys" log about call ending, we can trigger UI
        if (text.includes("Fin de l'appel") || text.includes("Raccroché")) {
            showContactsScreen(false); // don't call Python back (prevent loop)
        }
    }

    // Function to update status in phone
    eel.expose(update_phone_status);
    function update_phone_status(status) {
        if (callStatus) callStatus.textContent = status;
    }

    // ----- Navigation Helpers -----
    function showCallScreen(callerName) {
        // Set Caller Name
        callerNameElement.textContent = callerName;
        callStatus.textContent = "Appel en cours...";

        // Switch Views
        contactsView.classList.remove('active');
        callView.classList.add('active');

        // Start Timer
        startTimer();
        callTimer.classList.add('visible');

        // Notify Python to start audio loop
        if (typeof eel !== 'undefined') {
            eel.start_python_call();
        }
    }

    function showContactsScreen(notifyPython = true) {
        // Stop logic
        stopTimer();

        // UI Reset
        callStatus.textContent = "Appel terminé";
        callStatus.style.color = "#ff3b30";

        // Transition back
        setTimeout(() => {
            callView.classList.remove('active');
            contactsView.classList.add('active');

            // Reset Call Colors/Text
            setTimeout(() => {
                callStatus.textContent = "Appel entrant...";
                callStatus.style.color = "rgba(255,255,255,0.6)";
                callTimer.classList.remove('visible');
                callTimer.textContent = "00:00";
            }, 500);

        }, 800);

        // Notify Python to stop audio loop
        if (notifyPython && typeof eel !== 'undefined') {
            eel.stop_python_call();
        }
    }

    // ----- Timer Logic -----
    function startTimer() {
        seconds = 0;
        callTimer.textContent = "00:00";
        clearInterval(timerInterval);
        timerInterval = setInterval(() => {
            seconds++;
            const mins = Math.floor(seconds / 60).toString().padStart(2, '0');
            const secs = (seconds % 60).toString().padStart(2, '0');
            callTimer.textContent = `${mins}:${secs}`;
        }, 1000);
    }

    function stopTimer() {
        clearInterval(timerInterval);
    }

    // ----- Global Access -----
    window.startCall = function (name) {
        showCallScreen(name);
    }

    // ----- Event Listeners -----
    const endCallBtn = document.getElementById('end-call-btn');
    if (endCallBtn) {
        endCallBtn.addEventListener('click', () => {
            showContactsScreen(true);
        });
    }

    // Update Clock
    function updateClock() {
        const now = new Date();
        const timeString = now.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
        const clockElem = document.getElementById('clock-time');
        if (clockElem) clockElem.textContent = timeString;
    }
    setInterval(updateClock, 1000);
    updateClock();

    // Initial greeting
    setTimeout(() => {
        add_log("Neurolists Dashboard v2.0 READY", "sys");
    }, 1000);
});
