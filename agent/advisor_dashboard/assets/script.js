let isEscalated = false;

async function updateDashboard() {
    try {
        const res = await fetch('/handoff-status');
        const data = await res.json();

        if (data.active && !isEscalated) {
            isEscalated = true;

            // UI Trigger for Active Alert
            const statusBadge = document.getElementById('status-badge');
            if (statusBadge) {
                statusBadge.innerHTML = '🚨 TRANSFERT ACTIF';
                statusBadge.className = "badge badge-red alert-active";
            }

            const alertSound = document.getElementById('alert-sound');
            if (alertSound) alertSound.play();
        }

        if (data.active) {
            // Update Text Fields
            document.getElementById('client-name').innerText = data.nom + ' ' + data.prenom;
            document.getElementById('client-cin').innerText = data.cin;
            document.getElementById('session-id').innerText = data.session_id;
            document.getElementById('escalate-reason').innerText = data.reason || 'Demande de transfert conseiller';
            document.getElementById('interaction-resume').innerText = data.resume;
            document.getElementById('last-question').innerText = '"' + data.derniere_question + '"';

            // Update Sentiment UI
            const sentimentTag = document.getElementById('sentiment-tag');
            const sentimentIcon = document.getElementById('sentiment-icon');
            const sentimentIndicator = document.getElementById('sentiment-indicator');

            const sentiment = (data.sentiment || 'neutral').toLowerCase();

            // Logic for tags and icons
            if (sentimentTag) {
                sentimentTag.innerText = sentiment.toUpperCase();
                if (['angry', 'distressed'].includes(sentiment)) {
                    sentimentTag.className = "badge badge-red";
                    if (sentimentIndicator) sentimentIndicator.style.background = "#fee2e2";
                    if (sentimentIcon) sentimentIcon.innerText = "⚠️";
                } else if (sentiment === 'positive') {
                    sentimentTag.className = "badge font-bold bg-green-50 text-green-700 border border-green-200";
                    if (sentimentIndicator) sentimentIndicator.style.background = "#f0fdf4";
                    if (sentimentIcon) sentimentIcon.innerText = "😊";
                } else {
                    sentimentTag.className = "badge badge-blue";
                    if (sentimentIndicator) sentimentIndicator.style.background = "#f1f5f9";
                    if (sentimentIcon) sentimentIcon.innerText = "😐";
                }
            }
        }
    } catch (e) {
        console.error("Dashboard Sync Error:", e);
    }
}

// Start polling
setInterval(updateDashboard, 1500);
window.onload = updateDashboard;
