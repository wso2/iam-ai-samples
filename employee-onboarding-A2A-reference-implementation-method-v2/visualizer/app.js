/**
 * A2A Token Flow Visualizer - JavaScript
 */

// Token storage — Method V2 adds per-agent downscoped tokens
const tokens = {
    orchestrator_actor: null,
    user_delegated: null,
    // Per-agent: downscoped (from orchestrator) + actor (agent's own) + exchanged (final API token)
    hr_downscoped: null, hr_actor: null, hr_exchanged: null,
    it_downscoped: null, it_actor: null, it_exchanged: null,
    booking_downscoped: null, booking_actor: null, booking_exchanged: null,
    payroll_downscoped: null, payroll_actor: null, payroll_exchanged: null
};

let ws = null;
let reconnectAttempts = 0;
const maxReconnectAttempts = 10;
let expectingToken = null;

document.addEventListener('DOMContentLoaded', () => {
    console.log('[Visualizer] Initializing...');
    connect();
    updateAuthStatus();

    window.addEventListener('message', (event) => {
        if (event.origin !== 'http://localhost:8000') return;
        if (event.data && event.data.type === 'AUTH_SUCCESS') {
            localStorage.setItem('orch_token', event.data.token);
            updateAuthStatus();
            showToast('Login successful!');
        }
    });
});

function getToken() {
    return localStorage.getItem('orch_token');
}

function updateAuthStatus() {
    const token = getToken();
    const loginBtn = document.getElementById('login-btn');
    const logoutBtn = document.getElementById('logout-btn');
    const authStatus = document.getElementById('auth-status');
    if (token) {
        if (loginBtn) loginBtn.style.display = 'none';
        if (logoutBtn) logoutBtn.style.display = 'inline-block';
        if (authStatus) { authStatus.textContent = 'Logged in'; authStatus.style.color = '#4CAF50'; }
    } else {
        if (loginBtn) loginBtn.style.display = 'inline-block';
        if (logoutBtn) logoutBtn.style.display = 'none';
        if (authStatus) { authStatus.textContent = 'Not logged in'; authStatus.style.color = '#ef4444'; }
    }
}

function login() {
    window.open('http://localhost:8000/auth/login', 'login', 'width=600,height=700');
}

function logout() {
    localStorage.removeItem('orch_token');
    updateAuthStatus();
    showToast('Logged out');
}

function connect() {
    updateStatus('Connecting...', 'pending');
    ws = new WebSocket('ws://localhost:8200/ws');

    ws.onopen = () => {
        console.log('[WS] Connected');
        updateStatus('Connected', 'connected');
        reconnectAttempts = 0;
    };

    ws.onmessage = (event) => handleLogMessage(event.data);

    ws.onclose = () => {
        updateStatus('Disconnected', 'error');
        if (reconnectAttempts < maxReconnectAttempts) {
            reconnectAttempts++;
            setTimeout(connect, 2000);
        }
    };
}

function updateStatus(text, status) {
    const dot = document.getElementById('status-dot');
    const textEl = document.getElementById('status-text');
    dot.className = 'status-dot ' + status;
    textEl.textContent = text;
}

function isJWT(str) {
    const trimmed = str.trim();
    const parts = trimmed.split('.');
    return parts.length === 3 && trimmed.startsWith('eyJ');
}

function handleLogMessage(message) {
    appendLog(message);
    const trimmedMsg = message.trim();

    if (expectingToken && isJWT(trimmedMsg)) {
        setToken(expectingToken, trimmedMsg);
        expectingToken = null;
        return;
    } else if (expectingToken && !trimmedMsg.includes('[') && !trimmedMsg.includes('=')) {
        expectingToken = null;
    }

    if (message.includes('[ORCHESTRATOR_ACTOR_TOKEN]:')) expectingToken = 'orchestrator_actor';
    if (message.includes('[USER_DELEGATED_TOKEN]:')) expectingToken = 'user_delegated';
    if (message.includes('[SOURCE_TOKEN')) expectingToken = 'user_delegated';

    const agentMap = {
        'HR': 'hr', 'IT': 'it', 'PAYROLL': 'payroll', 'BOOKING': 'booking'
    };

    for (const [key, val] of Object.entries(agentMap)) {
        // Method V2: orchestrator logs downscoped token before forwarding to each agent
        // Payroll agent card name is "Finance & Payroll Agent" → type becomes FINANCE_PAYROLL_AGENT
        if (message.includes(`[${key}_AGENT_DOWNSCOPED_TOKEN]`) ||
            message.includes(`[${val.toUpperCase()}_AGENT_DOWNSCOPED_TOKEN]`) ||
            (val === 'payroll' && message.includes('[FINANCE_PAYROLL_AGENT_DOWNSCOPED_TOKEN]'))) {
            expectingToken = `${val}_downscoped`;
        }
        if (message.includes(`[${key}_AGENT_ACTOR_TOKEN]:`) ||
            (val === 'payroll' && message.includes('[FINANCE_PAYROLL_AGENT_ACTOR_TOKEN]:'))) {
            expectingToken = `${val}_actor`;
        }
        if (message.includes(`[${key}_AGENT_EXCHANGED_TOKEN`) ||
            (val === 'payroll' && message.includes('[FINANCE_PAYROLL_AGENT_EXCHANGED_TOKEN'))) {
            expectingToken = `${val}_exchanged`;
        }
    }

    // Forward Flow
    if (message.includes('auth/login')) animatePathForward('conn-user-wso2');
    if (message.includes('Actor token obtained')) animatePathForward('conn-wso2-orch');
    // Method V2: orchestrator downscopes animate on the orch→agents connector
    if (message.includes('ORCHESTRATOR DOWNSCOPING TOKEN FOR') ||
        message.includes('TOKEN EXCHANGE FOR')) animatePathForward('conn-orch-exchanger');

    // Agent Flows
    if (message.includes('HR_AGENT')) triggerAgentFlow('hr');
    if (message.includes('IT_AGENT') && !message.includes('PAYROLL')) triggerAgentFlow('it');
    if (message.includes('PAYROLL_AGENT')) triggerAgentFlow('payroll');
    if (message.includes('BOOKING_AGENT')) triggerAgentFlow('booking');

    // IT Approval Gate — highlight IT node while waiting for admin
    if (message.includes('Approval pending') || message.includes('waiting for admin')) {
        const itNode = document.getElementById('node-it');
        if (itNode) {
            itNode.style.borderColor = '#f59e0b';
            itNode.title = '⏳ Waiting for admin approval...';
            // Add pulsing badge if not already there
            if (!document.getElementById('it-pending-badge')) {
                const badge = document.createElement('div');
                badge.id = 'it-pending-badge';
                badge.textContent = '⏳ Pending Admin';
                badge.style.cssText = 'position:absolute;top:-22px;left:50%;transform:translateX(-50%);background:#f59e0b;color:#000;font-size:10px;padding:2px 6px;border-radius:4px;white-space:nowrap;animation:pulse 1.5s infinite';
                itNode.style.position = 'relative';
                itNode.appendChild(badge);
            }
        }
    }
    // Clear IT pending badge on approval
    if (message.includes('Approved! Proceeding')) {
        const badge = document.getElementById('it-pending-badge');
        if (badge) badge.remove();
        const itNode = document.getElementById('node-it');
        if (itNode) itNode.style.borderColor = '#4CAF50';
    }

    // IT Approval link received — show clickable URL in response panel (console fallback case)
    if (message.includes('[IT_APPROVAL]')) {
        const urlMatch = message.match(/APPROVE:\s*(https?:\/\/\S+)/);
        if (urlMatch) {
            const url = urlMatch[1];
            // Add as a response step so admin can see the link in the chat panel
            const content = document.getElementById('response-content');
            const placeholder = content.querySelector('.response-placeholder');
            if (placeholder) placeholder.remove();
            const div = document.createElement('div');
            div.className = 'response-message agent';
            div.innerHTML = `
                <div class="response-label">⏳ IT Agent — Admin Approval Required</div>
                <div class="response-text">
                    An IT access request is pending admin approval.<br>
                    <strong>Click to approve:</strong> <a href="${url}" target="_blank" style="color:#4CAF50;word-break:break-all">${url}</a>
                </div>`;
            content.appendChild(div);
            content.scrollTop = content.scrollHeight;
        }
    }

    // IT Provisioning outcome (broadcast by background task after admin approves/rejects)
    if (message.includes('[IT_PROVISIONED]')) {
        // Clear the pending badge if still present
        const badge = document.getElementById('it-pending-badge');
        if (badge) badge.remove();
        const itNode = document.getElementById('node-it');
        const approved = message.includes('✅');
        if (itNode) itNode.style.borderColor = approved ? '#4CAF50' : '#ef4444';

        // Strip the [IT_PROVISIONED] marker and display in response panel
        const resultText = message.replace(/\[IT_PROVISIONED\]\s*/, '').trim();
        addResponseMessage('IT Agent (Provisioning Result)', resultText, 'agent');
        if (approved) triggerAgentFlow('it');
    }

    // Completion
    if (message.toUpperCase().includes('TOKEN FLOW SUMMARY')) {
        console.log('[Visualizer] Triggering Final Response Animation');
        setTimeout(triggerFinalResponse, 100);
    }
}

function animatePathForward(connectorId) {
    const el = document.getElementById(connectorId);
    if (el) {
        el.classList.add('active');
        setTimeout(() => el.classList.remove('active'), 3000);
    }
}

function animatePathReverse(connectorId) {
    const el = document.getElementById(connectorId);
    if (el) {
        el.classList.add('response-active');
        setTimeout(() => el.classList.remove('response-active'), 3000);
    }
}

function triggerAgentFlow(agent) {
    // 1. To Agent
    animatePathForward('conn-exchanger-agents');
    const node = document.getElementById(`node-${agent}`);
    if (node) node.classList.add('active');

    // 2. To API & Return
    setTimeout(() => {
        animatePathForward(`conn-${agent}-api`);
        const apiNode = document.getElementById(`node-${agent}-api`);
        if (apiNode) apiNode.classList.add('active');

        // 3. Response Sequence
        setTimeout(() => {
            // API -> Agent
            animatePathReverse(`conn-${agent}-api`);

            // Agent -> Orchestrator (Implicit through Exchanger Visual)
            setTimeout(() => {
                animatePathReverse('conn-orch-exchanger');
            }, 300);

        }, 400);

    }, 200);
}

function triggerFinalResponse() {
    // New Direct Path: Orchestrator -> User (Bypassing WSO2)
    console.log("Triggering final response direct path");
    const directConn = document.getElementById('conn-orch-user-direct');
    if (directConn) {
        directConn.classList.add('response-active');
        setTimeout(() => directConn.classList.remove('response-active'), 3000);
    }
}

function setToken(type, token) {
    if (!isJWT(token)) return;
    tokens[type] = token;

    if (type === 'orchestrator_actor' || type === 'user_delegated') {
        const card = document.getElementById(`token-${type}`);
        if (card) updateCard(card, token);
    } else {
        const card = document.getElementById(`token-${type}`);
        if (card) {
            card.classList.add('active');
            // Downscoped = orange (orchestrator forwarded), actor = blue, exchanged = green
            if (type.endsWith('_downscoped')) {
                card.style.borderColor = '#FF7300';
                card.style.background = '#fff8f0';
            } else if (type.endsWith('_actor')) {
                card.style.borderColor = '#2196F3';
                card.style.background = '#f0f7ff';
            } else if (type.endsWith('_exchanged')) {
                card.closest('.agent-group').style.borderColor = '#4CAF50';
            }
        }
    }
}

function updateCard(card, token) {
    const valEl = card.querySelector('.token-value');
    valEl.textContent = token.substring(0, 60) + '...';
    card.classList.add('active');
}

function appendLog(message) {
    const logsEl = document.getElementById('logs');
    const entry = document.createElement('div');
    const time = new Date().toLocaleTimeString();
    entry.textContent = `[${time}] ${message}`;
    if (message.includes('TOKEN') || message.startsWith('eyJ')) entry.className = 'log-token';
    else if (message.includes('error') || message.includes('403')) entry.className = 'log-error';
    else if (message.includes('success')) entry.className = 'log-success';

    logsEl.appendChild(entry);
    logsEl.scrollTop = logsEl.scrollHeight;
    while (logsEl.children.length > 500) logsEl.removeChild(logsEl.firstChild);
}

function copyToken(type) {
    const token = tokens[type];
    if (token) {
        navigator.clipboard.writeText(token);
        showToast('Token Copied!');
    }
}

function showToast(msg) {
    const toast = document.getElementById('toast');
    toast.textContent = msg;
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 2000);
}

function clearLogs() {
    document.getElementById('logs').innerHTML = '';
}

function resetAll() {
    Object.keys(tokens).forEach(k => tokens[k] = null);
    document.querySelectorAll('.active').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.response-active').forEach(el => el.classList.remove('response-active'));
    document.querySelectorAll('.token-value').forEach(el => el.textContent = 'Waiting...');
    document.querySelectorAll('.agent-group').forEach(el => el.style.borderColor = '');
    document.querySelectorAll('.token-badge').forEach(el => { el.style.borderColor = ''; el.style.background = ''; });
    document.getElementById('logs').innerHTML = '';
    clearResponses();
}

// ===== Chat Interface Functions =====

async function sendInstruction() {
    const input = document.getElementById('chat-input');
    const message = input.value.trim();

    if (!message) {
        showToast('Please enter an instruction');
        return;
    }

    // Clear input
    input.value = '';

    // Show user message
    addResponseMessage('You', message, 'user');

    // Show loading
    showLoading();

    // Disable send button
    const sendBtn = document.querySelector('.send-btn');
    sendBtn.disabled = true;

    const token = getToken();
    if (!token) {
        hideLoading();
        sendBtn.disabled = false;
        addResponseMessage('Error', 'Please login first. Click the Login button.', 'error');
        showToast('Please login first');
        return;
    }

    try {
        const response = await fetch('http://localhost:8000/api/request', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + token
            },
            body: JSON.stringify({ message })
        });
        const data = await response.json();
        if (response.status === 401) {
            localStorage.removeItem('orch_token');
            updateAuthStatus();
            hideLoading();
            sendBtn.disabled = false;
            addResponseMessage('Error', 'Session expired. Please login again.', 'error');
            showToast('Session expired');
            return;
        }

        hideLoading();

        if (data.status === 'success') {
            // Display responses from each agent
            if (data.responses) {
                let stepNum = 1;
                for (const [agentName, agentResponse] of Object.entries(data.responses)) {
                    addResponseMessage(agentName, agentResponse, 'agent', stepNum++);
                }
            } else if (data.response) {
                addResponseMessage('Orchestrator', data.response, 'agent');
            }
            showToast('Request completed!');
        } else {
            addResponseMessage('Error', data.error || 'Request failed', 'error');
            showToast('Request failed');
        }
    } catch (error) {
        hideLoading();
        addResponseMessage('Error', `Connection failed: ${error.message}`, 'error');
        showToast('Connection error');
    }

    sendBtn.disabled = false;
}


function addResponseMessage(label, text, type, stepNum = null) {
    const content = document.getElementById('response-content');

    // Remove placeholder if exists
    const placeholder = content.querySelector('.response-placeholder');
    if (placeholder) placeholder.remove();

    // Remove any loading indicator
    const loading = content.querySelector('.loading-indicator');
    if (loading) loading.remove();

    const div = document.createElement('div');
    div.className = `response-message ${type}`;

    const labelDiv = document.createElement('div');
    labelDiv.className = 'response-label';
    labelDiv.innerHTML = stepNum
        ? `<span class="step-badge">Step ${stepNum}</span> ${label}`
        : label;

    const textDiv = document.createElement('div');
    textDiv.className = 'response-text';
    textDiv.textContent = text;

    div.appendChild(labelDiv);
    div.appendChild(textDiv);
    content.appendChild(div);

    // Auto-scroll
    content.scrollTop = content.scrollHeight;
}

function showLoading() {
    const content = document.getElementById('response-content');

    // Remove placeholder
    const placeholder = content.querySelector('.response-placeholder');
    if (placeholder) placeholder.remove();

    // Add loading indicator if not exists
    if (!content.querySelector('.loading-indicator')) {
        const loading = document.createElement('div');
        loading.className = 'loading-indicator';
        loading.innerHTML = '<div class="loading-spinner"></div><span>Processing request...</span>';
        content.appendChild(loading);
    }
}

function hideLoading() {
    const loading = document.querySelector('.loading-indicator');
    if (loading) loading.remove();
}

function clearResponses() {
    const content = document.getElementById('response-content');
    content.innerHTML = '<div class="response-placeholder">Send an instruction to see agent responses here...</div>';
}
