/**
 * DocIntel — Frontend Application Logic
 * 
 * No framework, no build step. Pure JS talking to the FastAPI backend.
 * 
 * State:
 *   activeDocId    — the currently selected document's ID
 *   activeDocName  — filename of the selected document
 *   documents      — array of all uploaded documents
 *   citations      — array of citation objects from the latest query response
 *   isQuerying     — prevents double-sends
 */

const API_BASE = '';  // same origin — FastAPI serves both frontend and API

let activeDocId = null;
let activeDocName = '';
let documents = [];
let citations = [];
let isQuerying = false;
let selectedFile = null;

// ── Initialise ────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  loadDocuments();
  // Show upload view by default
  showUploadView();
});

// ── View switching ────────────────────────────────────────────────────────────
function showUploadView() {
  document.getElementById('upload-view').classList.add('active');
  document.getElementById('chat-view').classList.remove('active');
  activeDocId = null;
  activeDocName = '';
  // Remove active highlight from doc list
  document.querySelectorAll('.doc-item').forEach(el => el.classList.remove('active'));
  // Reset upload state
  resetUploadUI();
}

function showChatView(docId, docName, docMeta) {
  activeDocId = docId;
  activeDocName = docName;
  document.getElementById('upload-view').classList.remove('active');
  document.getElementById('chat-view').classList.add('active');

  // Update header
  document.getElementById('chat-doc-name').textContent = docName;
  document.getElementById('chat-doc-meta').textContent = docMeta || '';
  document.getElementById('welcome-doc-name').textContent = docName;

  // Clear previous messages
  const msgs = document.getElementById('chat-messages');
  msgs.innerHTML = `
    <div id="chat-welcome">
      <div id="chat-welcome-icon">🤖</div>
      <p>I've read <strong id="welcome-doc-name">${escapeHtml(docName)}</strong>. Ask me anything about it!</p>
      <div id="suggested-questions">
        <button class="suggestion-chip" onclick="askSuggestion('What is this document about?')">What is this document about?</button>
        <button class="suggestion-chip" onclick="askSuggestion('What are the key terms and conditions?')">Key terms & conditions</button>
        <button class="suggestion-chip" onclick="askSuggestion('Who are the parties involved?')">Who are the parties?</button>
        <button class="suggestion-chip" onclick="askSuggestion('What are the main obligations?')">Main obligations</button>
      </div>
    </div>`;

  document.getElementById('chat-input').focus();

  // Highlight in sidebar
  document.querySelectorAll('.doc-item').forEach(el => {
    el.classList.toggle('active', el.dataset.docId === docId);
  });
}

// ── Document List ─────────────────────────────────────────────────────────────
async function loadDocuments() {
  try {
    const res = await fetch(`${API_BASE}/documents`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    documents = await res.json();
    renderDocList();
  } catch (err) {
    console.warn('Failed to load documents:', err.message);
  }
}

function renderDocList() {
  const list = document.getElementById('doc-list');
  
  if (!documents || documents.length === 0) {
    list.innerHTML = `
      <div id="doc-list-empty">
        <svg width="40" height="40" viewBox="0 0 40 40" fill="none" opacity="0.3">
          <rect x="8" y="4" width="24" height="32" rx="3" stroke="#a78bfa" stroke-width="2"/>
          <path d="M14 14h12M14 20h8M14 26h10" stroke="#a78bfa" stroke-width="1.5" stroke-linecap="round"/>
        </svg>
        <p>No documents yet.<br/>Upload one to get started.</p>
      </div>`;
    return;
  }

  list.innerHTML = documents.map(doc => {
    const ext = doc.filename.split('.').pop().toUpperCase();
    const icon = ext === 'PDF' ? '📕' : ext === 'DOCX' ? '📘' : '📄';
    const date = doc.uploaded_at ? new Date(doc.uploaded_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '';
    const chunks = doc.chunk_count ? `${doc.chunk_count} chunks` : '';
    const meta = [date, chunks].filter(Boolean).join(' · ');

    return `
      <div class="doc-item ${activeDocId === doc.document_id ? 'active' : ''}" 
           data-doc-id="${doc.document_id}"
           onclick="openDocument('${doc.document_id}', '${escapeAttr(doc.filename)}', '${escapeAttr(meta)}')">
        <div class="doc-item-icon">${icon}</div>
        <div class="doc-item-info">
          <span class="doc-item-name" title="${escapeHtml(doc.filename)}">${escapeHtml(doc.filename)}</span>
          <span class="doc-item-meta">${meta}</span>
        </div>
        <button class="doc-delete-btn" 
                title="Delete document"
                onclick="deleteDocument(event, '${doc.document_id}')">✕</button>
      </div>`;
  }).join('');
}

function openDocument(docId, docName, docMeta) {
  showChatView(docId, docName, docMeta);
}

async function deleteDocument(event, docId) {
  event.stopPropagation();
  if (!confirm('Delete this document and all its vectors?')) return;

  try {
    const res = await fetch(`${API_BASE}/documents/${docId}`, { method: 'DELETE' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    documents = documents.filter(d => d.document_id !== docId);
    renderDocList();
    if (activeDocId === docId) showUploadView();
  } catch (err) {
    alert(`Delete failed: ${err.message}`);
  }
}

// ── File Upload ───────────────────────────────────────────────────────────────
function handleDragOver(e) {
  e.preventDefault();
  document.getElementById('drop-zone').classList.add('drag-over');
}

function handleDragLeave(e) {
  document.getElementById('drop-zone').classList.remove('drag-over');
}

function handleDrop(e) {
  e.preventDefault();
  document.getElementById('drop-zone').classList.remove('drag-over');
  const file = e.dataTransfer.files[0];
  if (file) setSelectedFile(file);
}

function handleFileSelect(e) {
  const file = e.target.files[0];
  if (file) setSelectedFile(file);
}

function setSelectedFile(file) {
  selectedFile = file;
  const allowed = ['pdf', 'txt', 'docx'];
  const ext = file.name.split('.').pop().toLowerCase();
  if (!allowed.includes(ext)) {
    showUploadMessage(`Unsupported file type: .${ext}. Please upload PDF, TXT, or DOCX.`, 'error');
    selectedFile = null;
    return;
  }
  // Show filename
  document.getElementById('drop-text').style.display = 'none';
  document.getElementById('drop-selected').style.display = 'block';
  document.getElementById('selected-filename').textContent = `📎 ${file.name}`;
  // Auto-upload
  uploadFile(file);
}

async function uploadFile(file) {
  const progressWrap = document.getElementById('upload-progress-wrap');
  const progressFill = document.getElementById('upload-progress-fill');
  const statusText = document.getElementById('upload-status-text');
  const msgEl = document.getElementById('upload-message');

  progressWrap.style.display = 'flex';
  msgEl.style.display = 'none';

  // Animate progress bar (fake progress — real upload is one request)
  let pct = 0;
  const progressInterval = setInterval(() => {
    pct = Math.min(pct + Math.random() * 12, 88);
    progressFill.style.width = `${pct}%`;
  }, 200);

  statusText.textContent = 'Uploading and processing document...';

  const formData = new FormData();
  formData.append('file', file);

  try {
    const res = await fetch(`${API_BASE}/documents/upload`, {
      method: 'POST',
      body: formData,
    });

    clearInterval(progressInterval);
    progressFill.style.width = '100%';

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
      throw new Error(err.detail || `Upload failed with status ${res.status}`);
    }

    const data = await res.json();
    statusText.textContent = 'Processing complete!';

    showUploadMessage(
      `✅ <strong>${escapeHtml(data.filename)}</strong> uploaded successfully! Created ${data.chunk_count} chunks. Opening chat...`,
      'success'
    );

    // Add to local list and refresh sidebar
    await loadDocuments();

    // Auto-open the chat after 1.5s
    setTimeout(() => {
      showChatView(
        data.document_id,
        data.filename,
        `${data.chunk_count} chunks`
      );
    }, 1500);

  } catch (err) {
    clearInterval(progressInterval);
    progressFill.style.width = '0%';
    statusText.textContent = '';
    progressWrap.style.display = 'none';
    showUploadMessage(`❌ ${err.message}`, 'error');
    resetUploadUI(false);
  }
}

function showUploadMessage(html, type) {
  const el = document.getElementById('upload-message');
  el.innerHTML = html;
  el.className = type;
  el.style.display = 'block';
}

function resetUploadUI(full = true) {
  selectedFile = null;
  if (full) {
    document.getElementById('upload-progress-wrap').style.display = 'none';
    document.getElementById('upload-progress-fill').style.width = '0%';
    document.getElementById('upload-message').style.display = 'none';
  }
  document.getElementById('drop-text').style.display = 'block';
  document.getElementById('drop-selected').style.display = 'none';
  document.getElementById('file-input').value = '';
}

// ── Chat / Query ──────────────────────────────────────────────────────────────
function handleChatKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendQuestion();
  }
}

function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 140) + 'px';
}

function askSuggestion(q) {
  document.getElementById('chat-input').value = q;
  sendQuestion();
}

async function sendQuestion() {
  if (isQuerying || !activeDocId) return;

  const input = document.getElementById('chat-input');
  const question = input.value.trim();
  if (!question || question.length < 3) return;

  isQuerying = true;
  input.value = '';
  input.style.height = 'auto';
  document.getElementById('chat-send-btn').disabled = true;

  // Remove welcome message if still present
  const welcome = document.getElementById('chat-welcome');
  if (welcome) welcome.remove();

  const msgs = document.getElementById('chat-messages');

  // User bubble
  msgs.insertAdjacentHTML('beforeend', `
    <div class="message-wrap user">
      <span class="message-label">You</span>
      <div class="message-bubble">${escapeHtml(question)}</div>
    </div>`);

  // Loading indicator
  const loadingId = `loading-${Date.now()}`;
  msgs.insertAdjacentHTML('beforeend', `
    <div class="message-wrap assistant loading" id="${loadingId}">
      <span class="message-label">DocIntel AI</span>
      <div class="message-bubble">
        <div class="typing-dots">
          <span></span><span></span><span></span>
        </div>
        Thinking...
      </div>
    </div>`);

  scrollToBottom(msgs);

  try {
    const res = await fetch(`${API_BASE}/documents/${activeDocId}/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, top_k: 6 }),
    });

    const data = await res.json();

    // Remove loading indicator
    document.getElementById(loadingId)?.remove();

    if (!res.ok) {
      throw new Error(data.detail || `HTTP ${res.status}`);
    }

    // Store citations for the modal
    citations = data.citations || [];

    // Render answer
    renderAnswer(msgs, data);

  } catch (err) {
    document.getElementById(loadingId)?.remove();
    msgs.insertAdjacentHTML('beforeend', `
      <div class="message-wrap assistant">
        <span class="message-label">DocIntel AI</span>
        <div class="message-bubble" style="color: var(--error)">
          ⚠️ Error: ${escapeHtml(err.message)}
        </div>
      </div>`);
  } finally {
    isQuerying = false;
    document.getElementById('chat-send-btn').disabled = false;
    input.focus();
    scrollToBottom(msgs);
  }
}

function renderAnswer(msgs, data) {
  const { answer, citations: cits, answer_found } = data;

  // Format the answer text — render [N] as styled inline refs
  let answerHtml = escapeHtml(answer).replace(/\[(\d+)\]/g, (match, n) => {
    const idx = parseInt(n) - 1;
    const cit = cits && cits[idx];
    const page = cit ? `p.${cit.page_number || '?'}` : `ref ${n}`;
    return `<span class="inline-ref" data-citation-idx="${idx}">[${n}]</span>`;
  });

  // Convert plain newlines to <br>
  answerHtml = answerHtml.replace(/\n/g, '<br>');

  // Build citation chips
  let citHtml = '';
  if (cits && cits.length > 0) {
    const chips = cits.map((c, i) => {
      const page = c.page_number ? `Page ${c.page_number}` : `Chunk ${c.chunk_index}`;
      const score = Math.round(c.relevance_score * 100);
      return `<button class="citation-chip" onclick="showCitation(${i})" title="View source excerpt">
        <span class="chip-num">${i + 1}</span>
        ${page} · ${score}% match
      </button>`;
    }).join('');
    citHtml = `<div class="citations-wrap">${chips}</div>`;
  }

  // No-answer badge
  const noAnswerBadge = !answer_found
    ? `<div class="no-answer-badge">⚠️ No relevant information found in this document for this question.</div>`
    : '';

  msgs.insertAdjacentHTML('beforeend', `
    <div class="message-wrap assistant">
      <span class="message-label">DocIntel AI</span>
      <div class="message-bubble">
        ${answerHtml}
        ${noAnswerBadge}
      </div>
      ${citHtml}
    </div>`);
}

// ── Citations Modal ───────────────────────────────────────────────────────────
function showCitation(idx) {
  const cit = citations[idx];
  if (!cit) return;

  const page = cit.page_number ? `Page ${cit.page_number}` : '';
  const chunk = `Chunk #${cit.chunk_index}`;
  const score = `${Math.round(cit.relevance_score * 100)}% relevance`;

  document.getElementById('citation-modal-title').textContent = `Source [${idx + 1}]`;
  document.getElementById('citation-modal-meta').textContent = [page, chunk, score].filter(Boolean).join('  ·  ');
  document.getElementById('citation-modal-text').textContent = cit.excerpt;
  document.getElementById('citation-modal').style.display = 'flex';
}

function closeCitationModal(e) {
  if (!e || e.target === document.getElementById('citation-modal') || e.target === document.getElementById('citation-modal-close')) {
    document.getElementById('citation-modal').style.display = 'none';
  }
}

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    document.getElementById('citation-modal').style.display = 'none';
  }
});

// ── Helpers ───────────────────────────────────────────────────────────────────
function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function escapeAttr(str) {
  if (!str) return '';
  return String(str).replace(/'/g, "\\'").replace(/"/g, '\\"');
}

function scrollToBottom(el) {
  el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
}
