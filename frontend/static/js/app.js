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

    let html = `<div class="answer-text">${escapeHtml(data.answer)}</div>`;

    // Show plan if available
    if (data.plan && data.plan.trim()) {
        html += `
            <div class="plan-display">
                <strong>📋 Execution Plan</strong>
                <p>${escapeHtml(data.plan)}</p>
            </div>
        `;
    }

    // Show final SQL query
    if (data.final_sql) {
        html += `
            <div class="sql-display">
                <strong style="color: var(--success-color)">📝 Generated SQL:</strong>
                <pre>${escapeHtml(data.final_sql)}</pre>
            </div>
        `;
    }

    // Show detailed interaction steps
    html += buildInteractionSteps(data);

    messageDiv.innerHTML = html;
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Build detailed interaction steps with tables
function buildInteractionSteps(data) {
    let html = '';
    const hasSteps = data.intermediate_steps && data.intermediate_steps.length > 0;
    const hasColumns = data.relevant_columns && data.relevant_columns.length > 0;
    const hasValues = data.relevant_values && data.relevant_values.length > 0;
    const hasPaths = data.join_paths && data.join_paths.length > 0;

    if (!hasSteps && !hasColumns && !hasValues && !hasPaths) {
        return '';
    }

    html += `
        <details style="margin-top: 15px;" open>
            <summary style="cursor: pointer; color: var(--text-secondary); padding: 10px; font-weight: 600;">
                🔍 View Detailed Interaction Steps
            </summary>
            <div class="interaction-steps">
    `;

    // Show relevant columns
    if (hasColumns) {
        const topColumns = data.relevant_columns.slice(0, 5);
        const hasMore = data.relevant_columns.length > 5;

        html += `
            <div class="step">
                <span class="step-tool">🎯 Relevant Columns Found</span>
                <div class="step-content">
                    <span class="step-badge">${data.relevant_columns.length} total columns</span>
                    ${hasMore ? `<span style="color: var(--text-secondary); margin-left: 10px;">(showing top 5)</span>` : ''}
                </div>
                <table class="step-table">
                    <thead>
                        <tr>
                            <th>Table</th>
                            <th>Column</th>
                            <th>Similarity</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${topColumns.map(col => `
                            <tr>
                                <td>${escapeHtml(col.table_name || '')}</td>
                                <td>${escapeHtml(col.column_name || '')}</td>
                                <td>${(col.similarity || 0).toFixed(3)}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
                ${hasMore ? `<button class="show-more-btn" onclick="alert('Showing top 5 of ${data.relevant_columns.length} columns')">View All ${data.relevant_columns.length} Columns</button>` : ''}
            </div>
        `;
    }

    // Show relevant values
    if (hasValues) {
        const topValues = data.relevant_values.slice(0, 3);
        const hasMore = data.relevant_values.length > 3;

        html += `
            <div class="step">
                <span class="step-tool">🔎 Relevant Values Found</span>
                <div class="step-content">
                    <span class="step-badge">${data.relevant_values.length} total values</span>
                    ${hasMore ? `<span style="color: var(--text-secondary); margin-left: 10px;">(showing top 3)</span>` : ''}
                </div>
                <table class="step-table">
                    <thead>
                        <tr>
                            <th>Table</th>
                            <th>Column</th>
                            <th>Value</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${topValues.map(val => `
                            <tr>
                                <td>${escapeHtml(val.table_name || '')}</td>
                                <td>${escapeHtml(val.column_name || '')}</td>
                                <td>${escapeHtml(String(val.value || ''))}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
                ${hasMore ? `<button class="show-more-btn" onclick="alert('Showing top 3 of ${data.relevant_values.length} values')">View All ${data.relevant_values.length} Values</button>` : ''}
            </div>
        `;
    }

    // Show join paths
    if (hasPaths) {
        const topPaths = data.join_paths.slice(0, 3);
        const hasMore = data.join_paths.length > 3;

        html += `
            <div class="step">
                <span class="step-tool">🔗 Join Paths Found</span>
                <div class="step-content">
                    <span class="step-badge">${data.join_paths.length} total paths</span>
                    ${hasMore ? `<span style="color: var(--text-secondary); margin-left: 10px;">(showing top 3)</span>` : ''}
                </div>
                <table class="step-table">
                    <thead>
                        <tr>
                            <th>Path</th>
                            <th>Tables</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${topPaths.map(path => `
                            <tr>
                                <td>
                                    <div class="step-path">
                                        ${escapeHtml(path.path ? path.path.join(' → ') : 'N/A')}
                                    </div>
                                </td>
                                <td>${path.path ? path.path.length : 0}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
                ${hasMore ? `<button class="show-more-btn" onclick="alert('Showing top 3 of ${data.join_paths.length} paths')">View All ${data.join_paths.length} Paths</button>` : ''}
            </div>
        `;
    }

    // Show text-based intermediate steps
    if (hasSteps) {
        html += `
            <div class="step">
                <span class="step-tool">📝 Processing Steps</span>
                <div class="step-content">
        `;

        data.intermediate_steps.forEach((step, index) => {
            html += `
                <div style="margin: 8px 0; padding: 8px; background: var(--code-bg); border-radius: 4px;">
                    <strong style="color: var(--secondary-color);">Step ${index + 1}:</strong>
                    ${escapeHtml(String(step.step || step.output || ''))}
                </div>
            `;
        });

        html += `
                </div>
            </div>
        `;
    }

    html += `
            </div>
        </details>
    `;

    return html;
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
