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

    // Build step-by-step view based on intermediate steps
    const steps = data.intermediate_steps || [];

    steps.forEach((step, index) => {
        const stepContent = step.step || step.output || '';
        const stepNum = index + 1;

        // Determine step type and show corresponding data
        if (stepContent.includes('Plan:') || stepContent.includes('Required actions:')) {
            // Planning step
            html += buildPlanningStep(stepNum, data.plan, stepContent);
        } else if (stepContent.includes('relevant columns')) {
            // Column search step
            html += buildColumnStep(stepNum, data.relevant_columns);
        } else if (stepContent.includes('relevant values')) {
            // Value search step
            html += buildValueStep(stepNum, data.relevant_values);
        } else if (stepContent.includes('join paths') || stepContent.includes('path')) {
            // Path finding step
            html += buildPathStep(stepNum, data.join_paths);
        } else if (stepContent.includes('Generated SQL')) {
            // SQL generation step
            const sqlMatch = stepContent.match(/Generated SQL.*?:\s*(.+)/);
            const sql = sqlMatch ? sqlMatch[1] : '';
            html += buildSQLStep(stepNum, sql);
        } else {
            // Generic step
            html += buildGenericStep(stepNum, stepContent);
        }
    });

    html += `
            </div>
        </details>
    `;

    return html;
}

// Helper function to build planning step
function buildPlanningStep(stepNum, plan, fullContent) {
    return `
        <details class="step" style="margin: 10px 0; border: 1px solid var(--border-color); border-radius: 4px;">
            <summary style="cursor: pointer; padding: 12px; font-weight: 600; background: var(--card-bg);">
                <span style="color: var(--secondary-color);">Step ${stepNum}: 📋 Planning</span>
            </summary>
            <div style="padding: 12px; background: var(--bg-primary);">
                <div style="margin-bottom: 8px;">
                    <strong>Plan:</strong>
                    <p style="margin: 4px 0; padding: 8px; background: var(--code-bg); border-radius: 4px;">
                        ${escapeHtml(plan || fullContent)}
                    </p>
                </div>
            </div>
        </details>
    `;
}

// Helper function to build column search step
function buildColumnStep(stepNum, columns) {
    if (!columns || columns.length === 0) {
        return buildGenericStep(stepNum, 'Column search completed - no columns found');
    }

    const topColumns = columns.slice(0, 4);
    const hasMore = columns.length > 4;

    return `
        <details class="step" style="margin: 10px 0; border: 1px solid var(--border-color); border-radius: 4px;">
            <summary style="cursor: pointer; padding: 12px; font-weight: 600; background: var(--card-bg);">
                <span style="color: var(--secondary-color);">Step ${stepNum}: 🎯 Relevant Columns</span>
                <span class="step-badge" style="margin-left: 10px; font-weight: normal;">${columns.length} found</span>
                ${hasMore ? `<span style="color: var(--text-secondary); margin-left: 10px; font-weight: normal; font-size: 0.9em;">(showing top 4)</span>` : ''}
            </summary>
            <div style="padding: 12px; background: var(--bg-primary);">
                <table class="step-table" style="width: 100%; border-collapse: collapse;">
                    <thead>
                        <tr style="background: var(--code-bg); text-align: left;">
                            <th style="padding: 8px; border: 1px solid var(--border-color);">Table</th>
                            <th style="padding: 8px; border: 1px solid var(--border-color);">Column</th>
                            <th style="padding: 8px; border: 1px solid var(--border-color);">Type</th>
                            <th style="padding: 8px; border: 1px solid var(--border-color);">Similarity</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${topColumns.map(col => `
                            <tr>
                                <td style="padding: 8px; border: 1px solid var(--border-color);">${escapeHtml(col.table_name || '')}</td>
                                <td style="padding: 8px; border: 1px solid var(--border-color);"><strong>${escapeHtml(col.column_name || '')}</strong></td>
                                <td style="padding: 8px; border: 1px solid var(--border-color); font-size: 0.9em; color: var(--text-secondary);">${escapeHtml(col.data_type || '')}</td>
                                <td style="padding: 8px; border: 1px solid var(--border-color);">${(col.similarity || 0).toFixed(3)}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
                ${hasMore ? `<div style="margin-top: 8px; text-align: center; color: var(--text-secondary); font-size: 0.9em;">... and ${columns.length - 4} more columns</div>` : ''}
            </div>
        </details>
    `;
}

// Helper function to build value search step
function buildValueStep(stepNum, values) {
    if (!values || values.length === 0) {
        return buildGenericStep(stepNum, 'Value search completed - no values found');
    }

    const topValues = values.slice(0, 3);
    const hasMore = values.length > 3;

    return `
        <details class="step" style="margin: 10px 0; border: 1px solid var(--border-color); border-radius: 4px;">
            <summary style="cursor: pointer; padding: 12px; font-weight: 600; background: var(--card-bg);">
                <span style="color: var(--secondary-color);">Step ${stepNum}: 🔎 Relevant Values</span>
                <span class="step-badge" style="margin-left: 10px; font-weight: normal;">${values.length} found</span>
                ${hasMore ? `<span style="color: var(--text-secondary); margin-left: 10px; font-weight: normal; font-size: 0.9em;">(showing top 3)</span>` : ''}
            </summary>
            <div style="padding: 12px; background: var(--bg-primary);">
                <table class="step-table" style="width: 100%; border-collapse: collapse;">
                    <thead>
                        <tr style="background: var(--code-bg); text-align: left;">
                            <th style="padding: 8px; border: 1px solid var(--border-color);">Table</th>
                            <th style="padding: 8px; border: 1px solid var(--border-color);">Column</th>
                            <th style="padding: 8px; border: 1px solid var(--border-color);">Value</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${topValues.map(val => `
                            <tr>
                                <td style="padding: 8px; border: 1px solid var(--border-color);">${escapeHtml(val.table_name || '')}</td>
                                <td style="padding: 8px; border: 1px solid var(--border-color);"><strong>${escapeHtml(val.column_name || '')}</strong></td>
                                <td style="padding: 8px; border: 1px solid var(--border-color); background: var(--code-bg);">${escapeHtml(String(val.value || ''))}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
                ${hasMore ? `<div style="margin-top: 8px; text-align: center; color: var(--text-secondary); font-size: 0.9em;">... and ${values.length - 3} more values</div>` : ''}
            </div>
        </details>
    `;
}

// Helper function to build path finding step
function buildPathStep(stepNum, paths) {
    if (!paths || paths.length === 0) {
        return buildGenericStep(stepNum, 'Path finding completed - no paths found');
    }

    const topPaths = paths.slice(0, 3);
    const hasMore = paths.length > 3;

    return `
        <details class="step" style="margin: 10px 0; border: 1px solid var(--border-color); border-radius: 4px;">
            <summary style="cursor: pointer; padding: 12px; font-weight: 600; background: var(--card-bg);">
                <span style="color: var(--secondary-color);">Step ${stepNum}: 🔗 Join Paths</span>
                <span class="step-badge" style="margin-left: 10px; font-weight: normal;">${paths.length} found</span>
                ${hasMore ? `<span style="color: var(--text-secondary); margin-left: 10px; font-weight: normal; font-size: 0.9em;">(showing top 3)</span>` : ''}
            </summary>
            <div style="padding: 12px; background: var(--bg-primary);">
                ${topPaths.map((path, idx) => `
                    <div style="margin: 8px 0; padding: 10px; background: var(--code-bg); border-radius: 4px; border-left: 3px solid var(--secondary-color);">
                        <strong style="color: var(--secondary-color);">✓ Path ${idx + 1}:</strong>
                        ${path.path && path.path.length > 0
                            ? `<div style="margin-top: 4px; font-family: monospace; font-size: 0.95em;">${escapeHtml(path.path.join(' → '))}</div>`
                            : '<div style="margin-top: 4px; color: var(--text-secondary);">No path found</div>'
                        }
                        ${path.full_path
                            ? `<div style="margin-top: 6px; font-size: 0.85em; color: var(--text-secondary); font-family: monospace; white-space: pre-wrap;">${escapeHtml(path.full_path)}</div>`
                            : ''
                        }
                    </div>
                `).join('')}
                ${hasMore ? `<div style="margin-top: 8px; text-align: center; color: var(--text-secondary); font-size: 0.9em;">... and ${paths.length - 3} more paths</div>` : ''}
            </div>
        </details>
    `;
}

// Helper function to build SQL generation step
function buildSQLStep(stepNum, sql) {
    return `
        <details class="step" style="margin: 10px 0; border: 1px solid var(--border-color); border-radius: 4px;">
            <summary style="cursor: pointer; padding: 12px; font-weight: 600; background: var(--card-bg);">
                <span style="color: var(--secondary-color);">Step ${stepNum}: 💡 SQL Generation</span>
            </summary>
            <div style="padding: 12px; background: var(--bg-primary);">
                <pre style="background: var(--code-bg); padding: 12px; border-radius: 4px; overflow-x: auto;">${escapeHtml(sql)}</pre>
            </div>
        </details>
    `;
}

// Helper function to build generic step
function buildGenericStep(stepNum, content) {
    return `
        <details class="step" style="margin: 10px 0; border: 1px solid var(--border-color); border-radius: 4px;">
            <summary style="cursor: pointer; padding: 12px; font-weight: 600; background: var(--card-bg);">
                <span style="color: var(--secondary-color);">Step ${stepNum}: 📝 Processing</span>
            </summary>
            <div style="padding: 12px; background: var(--bg-primary);">
                <p style="margin: 0;">${escapeHtml(content)}</p>
            </div>
        </details>
    `;
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
