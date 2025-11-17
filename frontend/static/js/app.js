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

        // Debug: Log the response data to check if path selection data is present
        console.log('📊 Response Data:', {
            has_paths: !!data.join_paths,
            num_paths: data.join_paths?.length || 0,
            selected_indices: data.selected_path_indices,
            reasoning: data.path_selection_reasoning
        });

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

    if (!hasSteps) {
        return '';
    }

    html += `
        <details style="margin-top: 15px;" open>
            <summary style="cursor: pointer; color: var(--text-secondary); padding: 10px; font-weight: 600;">
                🔍 View Detailed Interaction Steps
            </summary>
            <div class="interaction-steps">
    `;

    // Process each step and embed appropriate data
    data.intermediate_steps.forEach((step, index) => {
        const stepContent = String(step.step || step.output || '');
        const stepNum = index + 1;

        html += `<div class="step" style="margin: 15px 0; padding: 15px; background: var(--card-bg); border-radius: 8px; border-left: 4px solid var(--secondary-color);">`;

        // Detect step type and render accordingly
        if (stepContent.includes('Plan:') || stepContent.includes('Required actions:')) {
            // Planning step
            html += `
                <div style="margin-bottom: 10px;">
                    <strong style="color: var(--secondary-color); font-size: 1.05em;">📋 Step ${stepNum}: Planning</strong>
                </div>
                <div style="padding: 10px; background: var(--bg-primary); border-radius: 4px;">
                    ${escapeHtml(stepContent)}
                </div>
            `;
        } else if (stepContent.includes('Found') && stepContent.includes('relevant columns')) {
            // Column search step - embed column table
            html += `
                <div style="margin-bottom: 10px;">
                    <strong style="color: var(--secondary-color); font-size: 1.05em;">🎯 Step ${stepNum}: Relevant Columns</strong>
                </div>
            `;
            if (data.relevant_columns && data.relevant_columns.length > 0) {
                const topColumns = data.relevant_columns.slice(0, 5);
                const hasMore = data.relevant_columns.length > 5;
                html += `
                    <div style="margin-bottom: 8px;">
                        <span class="step-badge">${data.relevant_columns.length} columns found</span>
                        ${hasMore ? `<span style="color: var(--text-secondary); margin-left: 10px; font-size: 0.9em;">(showing top 5)</span>` : ''}
                    </div>
                    <table class="step-table">
                        <thead>
                            <tr>
                                <th>Table</th>
                                <th>Column</th>
                                <th>Type</th>
                                <th>Similarity</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${topColumns.map(col => `
                                <tr>
                                    <td>${escapeHtml(col.table_name || '')}</td>
                                    <td><strong>${escapeHtml(col.column_name || '')}</strong></td>
                                    <td style="font-size: 0.9em; color: var(--text-secondary);">${escapeHtml(col.data_type || '')}</td>
                                    <td>${(col.similarity || 0).toFixed(3)}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                `;
            }
        } else if (stepContent.includes('Found') && stepContent.includes('relevant values')) {
            // Value search step - embed value table
            html += `
                <div style="margin-bottom: 10px;">
                    <strong style="color: var(--secondary-color); font-size: 1.05em;">🔎 Step ${stepNum}: Relevant Values</strong>
                </div>
            `;
            if (data.relevant_values && data.relevant_values.length > 0) {
                const topValues = data.relevant_values.slice(0, 3);
                const hasMore = data.relevant_values.length > 3;
                html += `
                    <div style="margin-bottom: 8px;">
                        <span class="step-badge">${data.relevant_values.length} values found</span>
                        ${hasMore ? `<span style="color: var(--text-secondary); margin-left: 10px; font-size: 0.9em;">(showing top 3)</span>` : ''}
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
                                    <td>${escapeHtml(val.table_name || val.table || '')}</td>
                                    <td><strong>${escapeHtml(val.column_name || val.column || '')}</strong></td>
                                    <td style="background: var(--code-bg); padding: 4px 8px; border-radius: 3px;">${escapeHtml(String(val.value || val.contents || ''))}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                `;
            }
        } else if (stepContent.includes('Found') && stepContent.includes('join paths')) {
            // Path finding step - embed path table with full details
            html += `
                <div style="margin-bottom: 10px;">
                    <strong style="color: var(--secondary-color); font-size: 1.05em;">🔗 Step ${stepNum}: Join Paths</strong>
                </div>
            `;
            if (data.join_paths && data.join_paths.length > 0) {
                const topPaths = data.join_paths.slice(0, 3);
                const hasMore = data.join_paths.length > 3;
                const selectedIndices = data.selected_path_indices || [];

                html += `
                    <div style="margin-bottom: 8px;">
                        <span class="step-badge">${data.join_paths.length} paths found</span>
                        ${hasMore ? `<span style="color: var(--text-secondary); margin-left: 10px; font-size: 0.9em;">(showing top 3)</span>` : ''}
                    </div>
                `;

                topPaths.forEach((path, idx) => {
                    const isUsed = selectedIndices.includes(idx);
                    const statusBadge = isUsed
                        ? '<span style="color: #4caf50; font-weight: bold;">✅ USED</span>'
                        : '<span style="color: var(--text-secondary);">○ Available</span>';
                    const borderColor = isUsed ? '#4caf50' : 'var(--border-color)';
                    const bgColor = isUsed ? 'rgba(76, 175, 80, 0.05)' : 'var(--code-bg)';

                    html += `
                        <div style="margin: 10px 0; padding: 12px; background: ${bgColor}; border-radius: 6px; border-left: 4px solid ${borderColor};">
                            <div style="display: flex; align-items: center; margin-bottom: 8px;">
                                ${statusBadge}
                                <strong style="margin-left: 10px; color: var(--secondary-color);">Path ${idx}:</strong>
                                <span style="margin-left: 10px; font-family: monospace; font-size: 0.95em;">${escapeHtml(path.path ? path.path.join(' → ') : 'N/A')}</span>
                            </div>
                            ${path.full_path ? `
                                <div style="margin-top: 8px; padding: 8px; background: var(--bg-primary); border-radius: 4px; font-family: monospace; font-size: 0.85em; color: var(--text-secondary); line-height: 1.6;">
                                    ${escapeHtml(path.full_path)}
                                </div>
                            ` : ''}
                        </div>
                    `;
                });
            }
        } else if (stepContent.includes('Paths used:') || stepContent.includes('Reasoning:')) {
            // SQL Generation step with path selection
            html += `
                <div style="margin-bottom: 10px;">
                    <strong style="color: var(--secondary-color); font-size: 1.05em;">💡 Step ${stepNum}: SQL Generation</strong>
                </div>
            `;

            // Extract SQL, paths used, and reasoning
            const lines = stepContent.split('\n');
            let sqlLine = '';
            let pathsLine = '';
            let reasoningLine = '';

            lines.forEach(line => {
                if (line.includes('Generated SQL') && line.includes(':')) {
                    sqlLine = line.substring(line.indexOf(':') + 1).trim();
                } else if (line.includes('Paths used:')) {
                    pathsLine = line.substring(line.indexOf(':') + 1).trim();
                } else if (line.includes('Reasoning:')) {
                    reasoningLine = line.substring(line.indexOf(':') + 1).trim();
                }
            });

            if (sqlLine) {
                html += `
                    <div style="margin: 8px 0; padding: 10px; background: var(--code-bg); border-radius: 4px;">
                        <div style="font-size: 0.9em; color: var(--text-secondary); margin-bottom: 4px;">SQL Query:</div>
                        <code style="color: var(--text-primary);">${escapeHtml(sqlLine)}</code>
                    </div>
                `;
            }

            if (pathsLine) {
                html += `
                    <div style="margin: 8px 0; padding: 10px; background: var(--bg-primary); border-radius: 4px;">
                        <div style="font-size: 0.9em; color: var(--text-secondary); margin-bottom: 4px;">Paths Selected:</div>
                        <div>${escapeHtml(pathsLine)}</div>
                    </div>
                `;
            }

            if (reasoningLine) {
                html += `
                    <div style="margin: 8px 0; padding: 10px; background: var(--bg-primary); border-radius: 4px; border-left: 3px solid var(--secondary-color);">
                        <div style="font-size: 0.9em; color: var(--text-secondary); margin-bottom: 4px;">💭 Reasoning:</div>
                        <div>${escapeHtml(reasoningLine)}</div>
                    </div>
                `;
            }
        } else {
            // Generic step
            html += `
                <div style="margin-bottom: 10px;">
                    <strong style="color: var(--secondary-color); font-size: 1.05em;">📝 Step ${stepNum}</strong>
                </div>
                <div style="padding: 10px; background: var(--bg-primary); border-radius: 4px;">
                    ${escapeHtml(stepContent)}
                </div>
            `;
        }

        html += `</div>`;
    });

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
