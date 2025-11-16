// Interactive Text-to-SQL Frontend Application

// State management
let currentSession = null;
let isProcessing = false;

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    loadSchema();
    setupEventListeners();
});

// Event Listeners
function setupEventListeners() {
    const input = document.getElementById('user-input');
    const sendButton = document.getElementById('send-button');

    // Send on button click
    sendButton.addEventListener('click', sendQuery);

    // Send on Ctrl/Cmd + Enter
    input.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
            e.preventDefault();
            sendQuery();
        }
    });
}

// Load database schema
async function loadSchema() {
    try {
        const response = await fetch('/api/schema');
        const data = await response.json();

        document.getElementById('table-count').textContent = data.tables.length;
        document.getElementById('fk-count').textContent = data.foreign_keys.length;

        const tableList = document.getElementById('table-list');
        tableList.innerHTML = '';

        data.tables.forEach(table => {
            const item = document.createElement('div');
            item.className = 'table-item';
            item.innerHTML = `
                <span class="table-name">${table}</span>
                <span class="column-count">${data.column_count[table]} cols</span>
            `;
            tableList.appendChild(item);
        });

        document.getElementById('schema-loading').classList.add('hidden');
        document.getElementById('schema-content').classList.remove('hidden');
    } catch (error) {
        console.error('Failed to load schema:', error);
        document.getElementById('schema-loading').textContent = 'Failed to load schema';
    }
}

// Use example query
function useExample(query) {
    document.getElementById('user-input').value = query;
    document.getElementById('user-input').focus();
}

// Send query to backend
async function sendQuery() {
    const input = document.getElementById('user-input');
    const question = input.value.trim();

    if (!question || isProcessing) return;

    // Clear input
    input.value = '';

    // Add user message to chat
    addMessage('user', question);

    // Show loading state
    setProcessingState(true);

    try {
        const response = await fetch('/api/query', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                question: question,
                session_id: currentSession
            })
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();

        // Add assistant response
        addAssistantMessage(data);

    } catch (error) {
        console.error('Query failed:', error);
        addMessage('error', `Error: ${error.message}`);
    } finally {
        setProcessingState(false);
    }
}

// Add user message to chat
function addMessage(type, content) {
    const chatMessages = document.getElementById('chat-messages');
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}-message`;

    if (type === 'error') {
        messageDiv.className = 'message error';
    }

    messageDiv.innerHTML = `<p>${escapeHtml(content)}</p>`;
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Add assistant message with SQL and results
function addAssistantMessage(data) {
    const chatMessages = document.getElementById('chat-messages');
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant-message';

    let html = `<p>${escapeHtml(data.answer)}</p>`;

    // Show final SQL query
    if (data.final_sql) {
        html += `
            <div class="sql-display">
                <strong style="color: var(--success-color)">📝 Generated SQL:</strong>
                <pre>${escapeHtml(data.final_sql)}</pre>
            </div>
        `;
    }

    // Show intermediate steps (collapsed by default)
    if (data.intermediate_steps && data.intermediate_steps.length > 0) {
        html += `
            <details style="margin-top: 15px;">
                <summary style="cursor: pointer; color: var(--text-secondary); padding: 10px;">
                    🔍 View Interaction Steps (${data.intermediate_steps.length})
                </summary>
                <div class="interaction-steps">
        `;

        data.intermediate_steps.forEach((step, index) => {
            html += `
                <div class="step">
                    <span class="step-tool">Step ${index + 1}: ${step.tool}</span>
                    <div style="margin-top: 5px; color: var(--text-secondary); font-size: 0.85em;">
                        ${escapeHtml(String(step.output).substring(0, 200))}
                        ${String(step.output).length > 200 ? '...' : ''}
                    </div>
                </div>
            `;
        });

        html += `
                </div>
            </details>
        `;
    }

    messageDiv.innerHTML = html;
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Set processing state
function setProcessingState(processing) {
    isProcessing = processing;
    const sendButton = document.getElementById('send-button');
    const sendText = document.getElementById('send-text');
    const sendLoading = document.getElementById('send-loading');

    if (processing) {
        sendButton.disabled = true;
        sendText.classList.add('hidden');
        sendLoading.classList.remove('hidden');

        // Add typing indicator
        const chatMessages = document.getElementById('chat-messages');
        const typingDiv = document.createElement('div');
        typingDiv.id = 'typing-indicator';
        typingDiv.className = 'message assistant-message';
        typingDiv.innerHTML = '<p>🤔 Thinking and generating SQL...</p>';
        chatMessages.appendChild(typingDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    } else {
        sendButton.disabled = false;
        sendText.classList.remove('hidden');
        sendLoading.classList.add('hidden');

        // Remove typing indicator
        const typingIndicator = document.getElementById('typing-indicator');
        if (typingIndicator) {
            typingIndicator.remove();
        }
    }
}

// Utility: Escape HTML
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Health check (optional)
async function checkHealth() {
    try {
        const response = await fetch('/api/health');
        const data = await response.json();
        console.log('Health check:', data);
    } catch (error) {
        console.error('Health check failed:', error);
    }
}

// Check health on load
checkHealth();
