/**
 * app.js — Research Merge Orchestrator Chat Frontend
 *
 * REST API Client:
 *  - Checks backend health status via GET /api/status
 *  - Dispatches research requests via POST /api/research with payload: { "message": "..." }
 *  - Supports both standard JSON responses and chunked / SSE streaming responses
 *  - Formats research reports with headings, markdown, and scientific citation tags [N]
 */

// ====================================================================
// Configuration & REST API Endpoints
// ====================================================================
const API_STATUS_URL = "/api/status";
const API_PROCESS_URL = "/api/research";

// ONLY FOR DEBUG PURPOSES
console.log("🔥 ACTIVE API ENDPOINT:", API_PROCESS_URL);

// ====================================================================
// DOM References
// ====================================================================
const statusPill = document.getElementById("statusPill");
const statusDot = document.getElementById("statusDot");
const statusText = document.getElementById("statusText");
const clearBtn = document.getElementById("clearBtn");
const chatLog = document.getElementById("chatLog");
const emptyState = document.getElementById("emptyState");
const textInput = document.getElementById("textInput");
const sendBtn = document.getElementById("sendBtn");
const suggestionsContainer = document.getElementById("suggestionsContainer");

// ====================================================================
// State Variables
// ====================================================================
let isProcessing = false;

// ====================================================================
// UI Helpers
// ====================================================================

/**
 * Updates the API status indicator pill.
 * @param {'online' | 'checking' | 'offline'} state
 * @param {string} label
 */
function setStatus(state, label) {
    statusPill.className = `status-pill ${state}`;
    statusText.textContent = label;
}

/**
 * Checks backend health via GET /api/status.
 */
async function checkApiStatus() {
    try {
        const response = await fetch(API_STATUS_URL, { method: "GET", cache: "no-cache" });
        if (response.ok) {
            setStatus("online", "API Online");
        } else {
            setStatus("offline", `API Error (${response.status})`);
        }
    } catch (err) {
        setStatus("offline", "API Offline");
    }
}

/**
 * Hides empty state hero on first message.
 */
function hideEmptyState() {
    if (emptyState) {
        emptyState.style.display = "none";
    }
}

/**
 * Clears chat history and restores the initial empty state.
 */
function clearChat() {
    chatLog.innerHTML = "";
    if (emptyState) {
        emptyState.style.display = "flex";
        chatLog.appendChild(emptyState);
    }
}

// ====================================================================
// Markdown & Scientific Citation Formatter
// ====================================================================

/**
 * Escapes raw HTML to prevent injection vulnerabilities.
 * @param {string} text
 * @returns {string}
 */
function escapeHtml(text) {
    const map = {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;"
    };
    return text.replace(/[&<>"']/g, (m) => map[m]);
}

/**
 * Formats Markdown synthesis text into structured HTML with citation tags.
 * @param {string} text Raw markdown text.
 * @returns {string} Styled HTML.
 */
function formatMarkdown(text) {
    if (!text) return "";

    let escaped = escapeHtml(text);

    // Code blocks ```...```
    escaped = escaped.replace(/```([\s\S]*?)```/g, "<pre><code>$1</code></pre>");

    // Inline code `...`
    escaped = escaped.replace(/`([^`]+)`/g, "<code>$1</code>");

    // Scientific Citations: [1], [2], [10] etc.
    escaped = escaped.replace(/\[(\d+)\]/g, '<span class="citation-tag">[$1]</span>');

    // Headings (###, ##, #)
    escaped = escaped.replace(/^### (.*$)/gim, "<h3>$1</h3>");
    escaped = escaped.replace(/^## (.*$)/gim, "<h2>$1</h2>");
    escaped = escaped.replace(/^# (.*$)/gim, "<h2>$1</h2>");

    // Markdown links [text](url)
    escaped = escaped.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');

    // URLs to clickable links (if not already inside an <a> tag)
    escaped = escaped.replace(/(^|[^"'])(https?:\/\/[^\s<]+)/g, '$1<a href="$2" target="_blank" rel="noopener noreferrer">$2</a>');

    // Bold **text**
    escaped = escaped.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");

    // Italic *text*
    escaped = escaped.replace(/\*([^*]+)\*/g, "<em>$1</em>");

    // Bullet Lists
    escaped = escaped.replace(/^\s*[-*]\s+(.*$)/gim, "<li>$1</li>");
    escaped = escaped.replace(/(<li>.*<\/li>)/gims, "<ul>$1</ul>");

    // Paragraph breaks
    escaped = escaped.replace(/\n\n+/g, "</p><p>");
    escaped = escaped.replace(/\n/g, "<br/>");

    return `<p>${escaped}</p>`;
}

// ====================================================================
// Message Row Management
// ====================================================================

/**
 * Creates and appends a chat message row to the log.
 * @param {'user' | 'assistant'} role
 * @returns {HTMLElement} The created bubble element.
 */
function createMessageRow(role) {
    hideEmptyState();

    const row = document.createElement("div");
    row.className = `message-row ${role}`;

    const avatar = document.createElement("div");
    avatar.className = "message-avatar";
    avatar.textContent = role === "user" ? "YOU" : "✦";

    const bubble = document.createElement("div");
    bubble.className = "message-bubble";
    bubble.dataset.rawText = "";

    row.appendChild(avatar);
    row.appendChild(bubble);
    chatLog.appendChild(row);
    chatLog.scrollTop = chatLog.scrollHeight;

    return bubble;
}

/**
 * Displays an agent step row in the chat log (e.g., search in progress).
 * @param {string} text
 */
function showAgentStep(text) {
    hideEmptyState();
    const stepRow = document.createElement("div");
    stepRow.className = "agent-step-row";
    stepRow.innerHTML = `<span class="agent-step-spinner"></span><span>${escapeHtml(text)}</span>`;
    chatLog.appendChild(stepRow);
    chatLog.scrollTop = chatLog.scrollHeight;
}

/**
 * Displays animated typing dots indicator.
 */
function showTypingIndicator() {
    removeTypingIndicator();
    const row = document.createElement("div");
    row.id = "typingRow";
    row.className = "message-row assistant";

    const avatar = document.createElement("div");
    avatar.className = "message-avatar";
    avatar.textContent = "✦";

    const bubble = document.createElement("div");
    bubble.className = "message-bubble typing-bubble";
    bubble.innerHTML = "<span></span><span></span><span></span>";

    row.appendChild(avatar);
    row.appendChild(bubble);
    chatLog.appendChild(row);
    chatLog.scrollTop = chatLog.scrollHeight;
}

/**
 * Removes typing dots indicator.
 */
function removeTypingIndicator() {
    const target = document.getElementById("typingRow");
    if (target) {
        target.remove();
    }
}

// ====================================================================
// REST API Request / Response Handler
// ====================================================================

/**
 * Sends prompt to FastAPI REST API endpoint and displays response.
 */
async function sendMessage() {
    const textData = textInput.value.trim();
    if (!textData || isProcessing) {
        return;
    }

    // Append User message
    const userBubble = createMessageRow("user");
    userBubble.textContent = textData;
    textInput.value = "";
    isProcessing = true;
    sendBtn.disabled = true;

    showTypingIndicator();

    try {
        const response = await fetch(API_PROCESS_URL, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ message: textData })
        });

        removeTypingIndicator();

        if (!response.ok) {
            const errorText = await response.text();
            const aiBubble = createMessageRow("assistant");
            aiBubble.innerHTML = `<p style="color: var(--red);"><strong>Request Error (${response.status}):</strong> ${escapeHtml(errorText || response.statusText)}</p>`;
            return;
        }

        // Check if response is streaming (SSE or text/plain stream)
        const contentType = response.headers.get("content-type") || "";

        if (contentType.includes("text/event-stream") || contentType.includes("text/plain")) {
            // Streaming response
            const aiBubble = createMessageRow("assistant");
            let accumulated = "";
            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                const chunk = decoder.decode(value, { stream: true });
                accumulated += chunk;
                aiBubble.innerHTML = formatMarkdown(accumulated);
                chatLog.scrollTop = chatLog.scrollHeight;
            }
        } else {
            // Standard JSON response
            const data = await response.json();
            const aiBubble = createMessageRow("assistant");
            
            // Extract response string from common JSON response structures
            const resultText = (typeof data === "string") 
                ? data 
                : (data.response || data.result || data.content || data.message || data.output || JSON.stringify(data, null, 2));

            aiBubble.innerHTML = formatMarkdown(resultText);
        }

    } catch (error) {
        removeTypingIndicator();
        console.error("REST Request failed:", error);
        const aiBubble = createMessageRow("assistant");
        aiBubble.innerHTML = `<p style="color: var(--red);"><strong>Connection Error:</strong> Could not connect to the backend server (${escapeHtml(error.message)}). Ensure FastAPI is running on port 8000.</p>`;
    } finally {
        isProcessing = false;
        sendBtn.disabled = false;
        chatLog.scrollTop = chatLog.scrollHeight;
        textInput.focus();
    }
}

// ====================================================================
// Event Listeners
// ====================================================================

sendBtn.addEventListener("click", sendMessage);

clearBtn.addEventListener("click", clearChat);

textInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
});

// Suggestion chip quick-fill handlers
if (suggestionsContainer) {
    suggestionsContainer.addEventListener("click", (event) => {
        const chip = event.target.closest(".suggestion-chip");
        if (chip) {
            const prompt = chip.getAttribute("data-prompt");
            if (prompt) {
                textInput.value = prompt;
                sendMessage();
            }
        }
    });
}

// Initial status check and periodic ping
checkApiStatus();
setInterval(checkApiStatus, 15000);
