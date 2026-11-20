const sendBtn = document.getElementById('send-btn');
const userInput = document.getElementById('user-input');
const chatDisplay = document.getElementById('chat-display');

const MAX_HISTORY = 10;      // messages sent back to the server for context
const REQUEST_TIMEOUT = 60000; // ms (Render free tier can take a while to wake up)
let history = [];

// Escape HTML, then turn **bold** into <strong>. Safe against injection.
function formatText(text) {
    const escaped = text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
    return escaped
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/^\s*[*-]\s+/gm, '• ');
}

function addMessage(text, className) {
    const div = document.createElement('div');
    div.className = `msg ${className}`;
    if (className.includes('bot-msg') && !className.includes('loading')) {
        div.innerHTML = formatText(text);
    } else {
        div.textContent = text;
    }
    chatDisplay.appendChild(div);
    chatDisplay.scrollTop = chatDisplay.scrollHeight;
    return div;
}

function updateMessage(element, newText, isError = false) {
    element.className = 'msg bot-msg' + (isError ? ' error' : '');
    element.innerHTML = formatText(newText);
    chatDisplay.scrollTop = chatDisplay.scrollHeight;
}

async function handleSend() {
    const text = userInput.value.trim();
    if (!text) return;

    addMessage(text, 'user-msg');
    userInput.value = '';
    userInput.disabled = true;
    sendBtn.disabled = true;

    const loadingBubble = addMessage('MITHI is thinking...', 'bot-msg loading');

    // Reassure the user if the server is slow (cold start)
    const slowTimer = setTimeout(() => {
        loadingBubble.textContent = 'MITHI is waking up, this can take up to a minute...';
    }, 8000);

    const controller = new AbortController();
    const abortTimer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT);

    try {
        const response = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text, history: history.slice(-MAX_HISTORY) }),
            signal: controller.signal
        });

        let data = {};
        try {
            data = await response.json();
        } catch (_) { /* non-JSON response (e.g. 502 page) */ }

        if (!response.ok) {
            updateMessage(
                loadingBubble,
                data.reply || 'Something went wrong on the server. Please try again shortly.',
                true
            );
        } else {
            const reply = data.reply || 'No response received.';
            updateMessage(loadingBubble, reply);
            history.push({ role: 'user', content: text });
            history.push({ role: 'assistant', content: reply });
            history = history.slice(-MAX_HISTORY);
        }
    } catch (error) {
        const msg = error.name === 'AbortError'
            ? 'The request took too long. Please try again.'
            : 'Connection error. Please check your internet and try again.';
        updateMessage(loadingBubble, msg, true);
    } finally {
        clearTimeout(slowTimer);
        clearTimeout(abortTimer);
        userInput.disabled = false;
        sendBtn.disabled = false;
        userInput.focus();
    }
}

sendBtn.addEventListener('click', handleSend);
userInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.isComposing) {
        e.preventDefault();
        handleSend();
    }
});