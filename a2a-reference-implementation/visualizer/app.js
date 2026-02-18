/**
 * A2A Token Flow Visualizer - JavaScript
 */

// Token storage
const tokens = {
    orchestrator_actor: null,
    user_delegated: null,
    hr_actor: null,
    hr_exchanged: null,
    it_actor: null,
    it_exchanged: null,
    approval_actor: null,
    approval_exchanged: null,
    booking_actor: null,
    booking_exchanged: null
};

let ws = null;
let reconnectAttempts = 0;
const maxReconnectAttempts = 10;
let expectingToken = null;

document.addEventListener('DOMContentLoaded', () => {
    console.log('[Visualizer] Initializing...');
    connect();
});

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
        'HR': 'hr', 'IT': 'it', 'APPROVAL': 'approval', 'BOOKING': 'booking'
    };

    for (const [key, val] of Object.entries(agentMap)) {
        if (message.includes(`[${key}_AGENT_ACTOR_TOKEN]:`)) expectingToken = `${val}_actor`;
        if (message.includes(`[${key}_AGENT_EXCHANGED_TOKEN`)) expectingToken = `${val}_exchanged`;
    }

    // Forward Flow
    if (message.includes('auth/login')) animatePathForward('conn-user-wso2');
    if (message.includes('Actor token obtained')) animatePathForward('conn-wso2-orch');
    if (message.includes('TOKEN EXCHANGE FOR')) animatePathForward('conn-orch-exchanger');

    // Agent Flows
    if (message.includes('HR_AGENT')) triggerAgentFlow('hr');
    if (message.includes('IT_AGENT')) triggerAgentFlow('it');
    if (message.includes('APPROVAL_AGENT')) triggerAgentFlow('approval');
    if (message.includes('BOOKING_AGENT')) triggerAgentFlow('booking');

    // Completion
    if (message.toUpperCase().includes('TOKEN FLOW SUMMARY')) {
        console.log('[Visualizer] Triggering Final Response Animation');
        setTimeout(triggerFinalResponse, 500);
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
            }, 1000);

        }, 1500);

    }, 1000);
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
            card.closest('.agent-group').style.borderColor = '#4CAF50';
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

    try {
        // Send to orchestrator API
        const response = await fetch(`http://localhost:8000/api/chat?message=${encodeURIComponent(message)}`);
        const data = await response.json();

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

async function runDefaultDemo() {
    // Clear previous responses
    clearResponses();

    // Show loading
    showLoading();
    addResponseMessage('You', 'Running full onboarding demo for John Doe as Software Engineer...', 'user');

    const sendBtn = document.querySelector('.send-btn');
    sendBtn.disabled = true;

    try {
        const response = await fetch('http://localhost:8000/api/demo');
        const data = await response.json();

        hideLoading();

        if (data.status === 'success') {
            // Display responses from each agent
            if (data.responses) {
                let stepNum = 1;
                for (const [agentName, agentResponse] of Object.entries(data.responses)) {
                    addResponseMessage(agentName, agentResponse, 'agent', stepNum++);
                }
                addResponseMessage('Summary', `✅ Onboarding complete for ${data.employee} as ${data.role}`, 'agent');
            }
            showToast('Demo completed!');
        } else {
            addResponseMessage('Error', data.error || 'Demo failed', 'error');
            showToast('Demo failed - Please login first');
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
