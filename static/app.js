/**
 * Smart AI Support Desk - Frontend Engine
 * Connects via WebSocket, manages real-time email stream,
 * displays customer mood, urgency levels, and drafts replies.
 */

// State
let tickets = [];
let selectedTicketId = null;
let currentFilter = 'all';
let socket = null;

// DOM Elements
const ticketsListContainer = document.getElementById('tickets-list-container');
const emptyInspectorState = document.getElementById('empty-inspector-state');
const inspectorContent = document.getElementById('inspector-content');
const queueCounter = document.getElementById('queue-counter');

// Stat Elements
const statTotalTickets = document.getElementById('stat-total-tickets');
const statChurnAlerts = document.getElementById('stat-churn-alerts');
const statAvgLatency = document.getElementById('stat-avg-latency');
const statLanguagesCount = document.getElementById('stat-languages-count');
const statLanguagesList = document.getElementById('stat-languages-list');

// Inspector Elements
const inspId = document.getElementById('insp-id');
const inspQueue = document.getElementById('insp-queue');
const inspPriority = document.getElementById('insp-priority');
const inspLang = document.getElementById('insp-lang');
const inspSubject = document.getElementById('insp-subject');
const inspSender = document.getElementById('insp-sender');
const inspDate = document.getElementById('insp-date');
const inspAlertBanner = document.getElementById('insp-alert-banner');
const inspAlertText = document.getElementById('insp-alert-text');
const inspLatency = document.getElementById('insp-latency');
const inspRoutingReason = document.getElementById('insp-routing-reason');
const inspDeptVal = document.getElementById('insp-dept-val');
const inspDeptBar = document.getElementById('insp-dept-bar');
const inspDeptConf = document.getElementById('insp-dept-conf');
const inspChurnVal = document.getElementById('insp-churn-val');
const inspChurnBar = document.getElementById('insp-churn-bar');
const inspChurnStatus = document.getElementById('insp-churn-status');
const inspFrustVal = document.getElementById('insp-frust-val');
const inspFrustSteps = document.getElementById('insp-frust-steps');
const inspUrgencyVal = document.getElementById('insp-urgency-val');
const inspUrgencySteps = document.getElementById('insp-urgency-steps');
const inspRefundVal = document.getElementById('insp-refund-val');
const inspSpamVal = document.getElementById('insp-spam-val');
const inspBodyText = document.getElementById('insp-body-text');
const inspAuditLogs = document.getElementById('insp-audit-logs');
const inspReplyInput = document.getElementById('insp-reply-input');
const btnSendReply = document.getElementById('btn-send-reply');
const replyFeedbackBanner = document.getElementById('reply-feedback-banner');

// Modal Elements
const composeModal = document.getElementById('compose-modal');
const btnOpenCompose = document.getElementById('btn-open-compose');
const btnCloseModal = document.getElementById('btn-close-modal');
const btnCancelCompose = document.getElementById('btn-cancel-compose');
const composeForm = document.getElementById('compose-form');
const composeFrom = document.getElementById('compose-from');
const composeSubject = document.getElementById('compose-subject');
const composeBody = document.getElementById('compose-body');
const btnClearInbox = document.getElementById('btn-clear-inbox');
const btnMarkResolved = document.getElementById('btn-mark-resolved');
const btnCopyReply = document.getElementById('btn-copy-reply');

// Gmail Modal Elements
const btnOpenGmail = document.getElementById('btn-open-gmail');
const gmailModal = document.getElementById('gmail-modal');
const btnCloseGmailModal = document.getElementById('btn-close-gmail-modal');
const gmailConfigForm = document.getElementById('gmail-config-form');
const gmailEmail = document.getElementById('gmail-email');
const gmailPassword = document.getElementById('gmail-password');
const gmailPollInterval = document.getElementById('gmail-poll-interval');
const gmailMarkRead = document.getElementById('gmail-mark-read');
const btnTestGmail = document.getElementById('btn-test-gmail');
const btnDisconnectGmail = document.getElementById('btn-disconnect-gmail');
const btnStartGmailSync = document.getElementById('btn-start-gmail-sync');
const gmailStatusDot = document.getElementById('gmail-status-dot');
const gmailStatusHeading = document.getElementById('gmail-status-heading');
const gmailStatusDetails = document.getElementById('gmail-status-details');
const gmailTestFeedback = document.getElementById('gmail-test-feedback');
const gmailBtnText = document.getElementById('gmail-btn-text');
const gmailIndicatorDot = document.getElementById('gmail-indicator-dot');
const btnSyncRecent = document.getElementById('btn-sync-recent');
const syncRecentBtnText = document.getElementById('sync-recent-btn-text');
const btnModalSyncNow = document.getElementById('btn-modal-sync-now');
const gmailConnectedActions = document.getElementById('gmail-connected-actions');
const modalMailboxCount = document.getElementById('modal-mailbox-count');
const gmailImportRecent = document.getElementById('gmail-import-recent');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
  setupWebSocket();
  setupEventListeners();
  loadTicketsHttp();
  fetchGmailStatus();
});

// WebSocket Connection
function setupWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws`;
  
  socket = new WebSocket(wsUrl);

  socket.onopen = () => {
    console.log('[WS] Connected to Support Desk');
    document.getElementById('system-status-pill').classList.add('status-live');
  };

  socket.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === 'INIT') {
        tickets = data.tickets || [];
        tickets.sort((a, b) => (b.created_at || 0) - (a.created_at || 0));
        updateStats(data.stats);
        renderTicketsList();
        if (tickets.length > 0 && !selectedTicketId) {
          selectTicket(tickets[0].id);
        }
      } else if (data.type === 'NEW_TICKET') {
        tickets.unshift(data.ticket);
        tickets.sort((a, b) => (b.created_at || 0) - (a.created_at || 0));
        updateStats(data.stats);
        if (data.gmail_status) updateGmailUI(data.gmail_status);
        renderTicketsList();
        selectTicket(data.ticket.id);
      } else if (data.type === 'TICKET_UPDATED') {
        const idx = tickets.findIndex(t => t.id === data.ticket.id);
        if (idx !== -1) {
          tickets[idx] = data.ticket;
          renderTicketsList();
          if (selectedTicketId === data.ticket.id) {
            renderInspector(data.ticket);
          }
        }
      } else if (data.type === 'GMAIL_STATUS_CHANGED') {
        updateGmailUI(data.status);
      } else if (data.type === 'TICKETS_CLEARED') {
        tickets = [];
        selectedTicketId = null;
        updateStats(data.stats);
        renderTicketsList();
        emptyInspectorState.classList.remove('hidden');
        inspectorContent.classList.add('hidden');
      }
    } catch (e) {
      console.error('[WS] Parse error', e);
    }
  };

  socket.onclose = () => {
    console.log('[WS] Disconnected. Reconnecting in 3s...');
    setTimeout(setupWebSocket, 3000);
  };
}

// Gmail Status Fetcher
async function fetchGmailStatus() {
  try {
    const res = await fetch('/api/gmail/status');
    if (res.ok) {
      const status = await res.json();
      updateGmailUI(status);
    }
  } catch (err) {
    console.warn('Could not fetch Gmail status', err);
  }
}

// Update Gmail UI Elements
function updateGmailUI(status) {
  if (!status) return;

  if (status.is_polling) {
    btnOpenGmail.classList.add('gmail-connected');
    gmailIndicatorDot.classList.remove('hidden');
    gmailBtnText.innerText = `Gmail (${status.total_ingested})`;
    
    if (btnSyncRecent) btnSyncRecent.classList.remove('hidden');
    if (gmailConnectedActions) gmailConnectedActions.classList.remove('hidden');
    if (modalMailboxCount) modalMailboxCount.innerText = (status.total_mailbox_count || 0).toLocaleString();

    gmailStatusDot.className = 'status-indicator-dot active';
    gmailStatusHeading.innerText = `Active: Connected to ${status.email}`;
    gmailStatusDetails.innerHTML = `
      Connected: <strong>${(status.total_mailbox_count || 0).toLocaleString()}</strong> emails in your Gmail inbox.<br>
      Imported <strong>${status.total_ingested}</strong> email(s) into this screen.<br>
      Checking for new emails every ${status.poll_interval} seconds.
    `;
    
    btnDisconnectGmail.classList.remove('hidden');
    btnStartGmailSync.innerText = 'Save Settings';
    if (status.email && !gmailEmail.value) {
      gmailEmail.value = status.email;
    }
  } else {
    btnOpenGmail.classList.remove('gmail-connected');
    gmailIndicatorDot.classList.add('hidden');
    gmailBtnText.innerText = 'Connect Gmail';
    if (btnSyncRecent) btnSyncRecent.classList.add('hidden');
    if (gmailConnectedActions) gmailConnectedActions.classList.add('hidden');

    if (status.last_error) {
      gmailStatusDot.className = 'status-indicator-dot error';
      gmailStatusHeading.innerText = 'Connection Error';
      gmailStatusDetails.innerText = status.last_error;
    } else {
      gmailStatusDot.className = 'status-indicator-dot';
      gmailStatusHeading.innerText = 'Status: Disconnected';
      gmailStatusDetails.innerText = 'Enter your Gmail address and 16-character App Password below to start receiving and sorting emails automatically.';
    }
    
    btnDisconnectGmail.classList.add('hidden');
    btnStartGmailSync.innerText = 'Start Live Sync';
  }
}

// Manual Sync Trigger
async function triggerSyncRecent(limit = 10) {
  if (syncRecentBtnText) syncRecentBtnText.innerText = 'Fetching...';
  if (btnModalSyncNow) {
    btnModalSyncNow.disabled = true;
    btnModalSyncNow.innerText = 'Fetching emails...';
  }

  try {
    const res = await fetch('/api/gmail/sync-recent', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ limit: limit })
    });
    const data = await res.json();
    if (data.success) {
      showTestFeedback(`✅ ${data.message}`, true);
      await fetchGmailStatus();
      await loadTicketsHttp();
    } else {
      showTestFeedback(`❌ Sync failed: ${data.detail || data.message}`, false);
    }
  } catch (err) {
    showTestFeedback(`❌ Sync error: ${err.message}`, false);
  } finally {
    if (syncRecentBtnText) syncRecentBtnText.innerText = 'Sync Recent';
    if (btnModalSyncNow) {
      btnModalSyncNow.disabled = false;
      btnModalSyncNow.innerText = '📥 Fetch Recent 10 Emails';
    }
  }
}

// Test Gmail Connection Button
async function handleTestGmail() {
  const emailVal = gmailEmail.value.trim();
  const passVal = gmailPassword.value.trim();

  if (!emailVal || !passVal) {
    showTestFeedback('Please enter both your Gmail address and 16-character App Password.', false);
    return;
  }

  btnTestGmail.disabled = true;
  btnTestGmail.innerText = 'Connecting...';
  showTestFeedback('Connecting to Google Mail...', null);

  try {
    const res = await fetch('/api/gmail/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: emailVal, app_password: passVal })
    });
    const data = await res.json();
    if (data.success) {
      showTestFeedback(`✅ ${data.message}`, true);
    } else {
      showTestFeedback(`❌ ${data.message}`, false);
    }
  } catch (err) {
    showTestFeedback(`❌ Connection test failed: ${err.message}`, false);
  } finally {
    btnTestGmail.disabled = false;
    btnTestGmail.innerText = 'Test Connection';
  }
}

function showTestFeedback(message, isSuccess) {
  gmailTestFeedback.classList.remove('hidden', 'test-feedback-success', 'test-feedback-error');
  if (isSuccess === true) {
    gmailTestFeedback.classList.add('test-feedback-success');
  } else if (isSuccess === false) {
    gmailTestFeedback.classList.add('test-feedback-error');
  }
  gmailTestFeedback.innerText = message;
}

// Start / Save Gmail Sync Form
async function handleStartGmailSync(e) {
  e.preventDefault();
  const emailVal = gmailEmail.value.trim();
  const passVal = gmailPassword.value.trim();
  const intervalVal = parseInt(gmailPollInterval.value, 10);
  const markReadVal = gmailMarkRead.checked;
  const importRecentVal = gmailImportRecent ? (gmailImportRecent.checked ? 10 : 0) : 10;

  btnStartGmailSync.disabled = true;
  btnStartGmailSync.innerText = 'Connecting...';

  try {
    const res = await fetch('/api/gmail/connect', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: emailVal,
        app_password: passVal,
        poll_interval: intervalVal,
        mark_read: markReadVal,
        import_recent: importRecentVal
      })
    });
    const data = await res.json();
    if (data.success) {
      showTestFeedback(`🚀 ${data.message}`, true);
      setTimeout(() => {
        gmailModal.classList.add('hidden');
      }, 1200);
      await fetchGmailStatus();
      await loadTicketsHttp();
    } else {
      showTestFeedback(`❌ ${data.message}`, false);
    }
  } catch (err) {
    showTestFeedback(`❌ Error starting sync: ${err.message}`, false);
  } finally {
    btnStartGmailSync.disabled = false;
    btnStartGmailSync.innerText = 'Start Live Sync';
  }
}

// Disconnect Gmail
async function handleDisconnectGmail() {
  btnDisconnectGmail.disabled = true;
  btnDisconnectGmail.innerText = 'Disconnecting...';
  try {
    const res = await fetch('/api/gmail/disconnect', { method: 'POST' });
    if (res.ok) {
      showTestFeedback('Disconnected from Gmail.', false);
      fetchGmailStatus();
    }
  } catch (err) {
    console.error(err);
  } finally {
    btnDisconnectGmail.disabled = false;
    btnDisconnectGmail.innerText = 'Disconnect';
  }
}

// Fallback HTTP Fetch
async function loadTicketsHttp() {
  try {
    const [tRes, sRes] = await Promise.all([
      fetch('/api/tickets'),
      fetch('/api/stats')
    ]);
    if (tRes.ok && sRes.ok) {
      tickets = await tRes.json();
      tickets.sort((a, b) => (b.created_at || 0) - (a.created_at || 0));
      const stats = await sRes.json();
      updateStats(stats);
      renderTicketsList();
      if (tickets.length > 0 && !selectedTicketId) {
        selectTicket(tickets[0].id);
      }
    }
  } catch (err) {
    console.warn('HTTP fetch failed, waiting for WebSocket', err);
  }
}

// Setup Event Listeners
function setupEventListeners() {
  // Gmail Modal listeners
  if (btnOpenGmail) {
    btnOpenGmail.addEventListener('click', () => {
      if (gmailModal) gmailModal.classList.remove('hidden');
      fetchGmailStatus();
    });
  }
  if (btnCloseGmailModal) {
    btnCloseGmailModal.addEventListener('click', () => {
      if (gmailModal) gmailModal.classList.add('hidden');
    });
  }
  if (btnTestGmail) btnTestGmail.addEventListener('click', handleTestGmail);
  if (gmailConfigForm) gmailConfigForm.addEventListener('submit', handleStartGmailSync);
  if (btnDisconnectGmail) btnDisconnectGmail.addEventListener('click', handleDisconnectGmail);
  if (btnSyncRecent) btnSyncRecent.addEventListener('click', () => triggerSyncRecent(10));
  if (btnModalSyncNow) btnModalSyncNow.addEventListener('click', () => triggerSyncRecent(10));

  // Close modals when clicking the dark backdrop
  [composeModal, gmailModal].forEach(m => {
    if (m) {
      m.addEventListener('click', (e) => {
        if (e.target === m) m.classList.add('hidden');
      });
    }
  });

  // Filter pills
  document.querySelectorAll('.filter-pill').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.filter-pill').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentFilter = btn.dataset.filter;
      renderTicketsList();
    });
  });

  // Modal Compose
  btnOpenCompose.addEventListener('click', () => {
    composeModal.classList.remove('hidden');
  });
  btnCloseModal.addEventListener('click', () => {
    composeModal.classList.add('hidden');
  });
  btnCancelCompose.addEventListener('click', () => {
    composeModal.classList.add('hidden');
  });

  // Submit Compose Form
  composeForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('btn-submit-triage');
    btn.disabled = true;
    btn.innerText = 'Analyzing with AI...';

    try {
      const res = await fetch('/api/tickets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          from_email: composeFrom.value,
          subject: composeSubject.value,
          body: composeBody.value
        })
      });
      if (res.ok) {
        const newTicket = await res.json();
        composeModal.classList.add('hidden');
        composeForm.reset();
        selectTicket(newTicket.id);
      }
    } catch (err) {
      alert('Error submitting email: ' + err);
    } finally {
      btn.disabled = false;
      btn.innerText = 'Analyze & Add to Inbox';
    }
  });

  // Clear Inbox Button
  if (btnClearInbox) {
    btnClearInbox.addEventListener('click', async () => {
      if (confirm('Clear all emails from this screen?')) {
        try {
          await fetch('/api/tickets', { method: 'DELETE' });
          tickets = [];
          selectedTicketId = null;
          renderTicketsList();
          emptyInspectorState.classList.remove('hidden');
          inspectorContent.classList.add('hidden');
          updateStats({ total: 0, avg_latency_ms: 0, churn_risk_count: 0, queues: {}, languages: {} });
        } catch (err) {
          console.error(err);
        }
      }
    });
  }

  // Mark Resolved Button
  btnMarkResolved.addEventListener('click', async () => {
    if (!selectedTicketId) return;
    try {
      const res = await fetch(`/api/tickets/${selectedTicketId}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'Resolved' })
      });
      if (res.ok) {
        btnMarkResolved.innerText = 'Solved ✓';
        btnMarkResolved.classList.add('btn-disabled');
      }
    } catch (err) {
      console.error(err);
    }
  });

  // Copy Suggested Reply
  if (btnCopyReply) {
    btnCopyReply.addEventListener('click', () => {
      const textToCopy = inspReplyInput ? inspReplyInput.value : '';
      navigator.clipboard.writeText(textToCopy);
      btnCopyReply.innerText = 'Copied!';
      setTimeout(() => { btnCopyReply.innerText = '📋 Copy'; }, 2000);
    });
  }

  // Send Reply via Gmail
  if (btnSendReply) {
    btnSendReply.addEventListener('click', async () => {
      if (!selectedTicketId) return;
      const text = inspReplyInput ? inspReplyInput.value.trim() : '';
      if (!text) {
        alert('Please enter a reply message before sending.');
        return;
      }

      btnSendReply.disabled = true;
      btnSendReply.innerHTML = '<span>⏳ Sending via Gmail...</span>';
      if (replyFeedbackBanner) {
        replyFeedbackBanner.className = 'reply-feedback-banner hidden';
      }

      try {
        const res = await fetch(`/api/tickets/${selectedTicketId}/reply`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ body: text })
        });
        const data = await res.json();
        if (res.ok && data.success) {
          if (replyFeedbackBanner) {
            replyFeedbackBanner.className = 'reply-feedback-banner reply-feedback-success';
            replyFeedbackBanner.innerText = `✉️ Reply sent successfully via Gmail! Ticket marked as solved.`;
          }
          btnMarkResolved.innerText = 'Solved ✓';
          btnMarkResolved.disabled = true;
          // Update ticket status in local state
          const ticket = tickets.find(t => t.id === selectedTicketId);
          if (ticket) {
            ticket.status = 'Resolved';
            renderTicketsList();
          }
        } else {
          if (replyFeedbackBanner) {
            replyFeedbackBanner.className = 'reply-feedback-banner reply-feedback-error';
            replyFeedbackBanner.innerText = `❌ ${data.detail || data.message || 'Failed to send reply'}`;
          }
        }
      } catch (err) {
        if (replyFeedbackBanner) {
          replyFeedbackBanner.className = 'reply-feedback-banner reply-feedback-error';
          replyFeedbackBanner.innerText = `❌ Error sending reply: ${err.message}`;
        }
      } finally {
        btnSendReply.disabled = false;
        btnSendReply.innerHTML = '<span>✉️ Send Reply via Gmail</span>';
      }
    });
  }
}

// Update Metrics Bar
function updateStats(stats) {
  if (!stats) return;
  statTotalTickets.innerText = stats.total || 0;
  statChurnAlerts.innerText = stats.churn_risk_count || 0;
  statAvgLatency.innerText = `${stats.avg_latency_ms || 32.8} ms`;
  
  if (stats.languages) {
    const langs = Object.keys(stats.languages);
    statLanguagesCount.innerText = `${langs.length} Languages`;
    statLanguagesList.innerText = langs.join(', ');
  }
}

// Format timestamp into clean, natural date & time
function formatDateTime(timestamp) {
  if (!timestamp) return 'Just now';
  const date = new Date(timestamp * 1000);
  if (isNaN(date.getTime())) return 'Just now';

  const now = new Date();
  const isToday = date.toDateString() === now.toDateString();
  const timeStr = date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', hour12: true });

  if (isToday) {
    return `Today at ${timeStr}`;
  }

  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (date.toDateString() === yesterday.toDateString()) {
    return `Yesterday at ${timeStr}`;
  }

  const dateStr = date.toLocaleDateString([], { month: 'short', day: 'numeric' });
  const isThisYear = date.getFullYear() === now.getFullYear();
  if (isThisYear) {
    return `${dateStr} at ${timeStr}`;
  }
  return `${dateStr}, ${date.getFullYear()} at ${timeStr}`;
}

// Render Tickets Queue
function renderTicketsList() {
  let filtered = [...tickets];
  // Strict descending sort: newest items at the very top, older items down
  filtered.sort((a, b) => (b.created_at || 0) - (a.created_at || 0));

  if (currentFilter === 'escalated') {
    filtered = filtered.filter(t => t.workflow?.escalation_triggered);
  } else if (currentFilter === 'billing') {
    filtered = filtered.filter(t => t.triage?.answers?.department?.choice === 'billing');
  } else if (currentFilter === 'technical') {
    filtered = filtered.filter(t => t.triage?.answers?.department?.choice === 'technical');
  }

  queueCounter.innerText = filtered.length;

  if (filtered.length === 0) {
    ticketsListContainer.innerHTML = `
      <div class="empty-inspector" style="padding: 40px 16px;">
        <span style="font-size: 2rem; margin-bottom: 8px; display: block;">📭</span>
        <h4 style="font-size: 0.95rem; margin-bottom: 6px; color: var(--text-main);">Your inbox is empty</h4>
        <p style="font-size: 0.78rem; color: var(--text-dim); line-height: 1.4;">
          Connect your Gmail account above or click <strong>+ New Test Email</strong> to get started.
        </p>
      </div>
    `;
    return;
  }

  ticketsListContainer.innerHTML = filtered.map(t => {
    const isEscalated = t.workflow?.escalation_triggered;
    const dept = t.triage?.answers?.department?.choice || 'Support';
    const lang = t.triage?.routing?.lang?.toUpperCase() || 'EN';
    const churnProb = Math.round((t.triage?.answers?.churn_risk?.probability || 0) * 100);
    const isActive = t.id === selectedTicketId;

    return `
      <div class="ticket-item ${isActive ? 'active' : ''}" onclick="selectTicket('${t.id}')">
        <div class="ticket-item-top">
          <span class="ticket-item-id">${t.id}</span>
          <div class="ticket-item-badges">
            ${t.source === 'gmail' ? '<span class="badge-source-gmail">✉️ GMAIL</span>' : ''}
            ${isEscalated ? '<span class="badge-priority-critical">🚨 URGENT</span>' : ''}
            <span class="badge-lang">${lang}</span>
          </div>
        </div>
        <div class="ticket-item-subject">${escapeHtml(t.subject)}</div>
        <div class="ticket-item-time">🕒 ${formatDateTime(t.created_at)}</div>
        <div class="ticket-item-body">${escapeHtml(t.body)}</div>
        <div class="ticket-item-footer">
          <span>Dept: ${dept.toUpperCase()}</span>
          ${churnProb >= 70 ? `<span class="ticket-churn-tag">Risk: ${churnProb}%</span>` : `<span>${t.status === 'Resolved' ? 'Solved ✓' : t.status}</span>`}
        </div>
      </div>
    `;
  }).join('');
}

// Select Ticket
function selectTicket(ticketId) {
  selectedTicketId = ticketId;
  const ticket = tickets.find(t => t.id === ticketId);
  if (!ticket) return;

  renderTicketsList();
  renderInspector(ticket);
}

// Render Inspector Detail
function renderInspector(ticket) {
  emptyInspectorState.classList.add('hidden');
  inspectorContent.classList.remove('hidden');

  const triage = ticket.triage || {};
  const workflow = ticket.workflow || {};
  const answers = triage.answers || {};
  const routing = triage.routing || {};

  inspId.innerText = ticket.id;
  inspQueue.innerText = workflow.queue || 'General Support';
  inspPriority.innerText = workflow.priority || 'Normal';
  inspPriority.className = `ticket-priority-badge ${workflow.priority === 'Critical' ? 'bg-danger' : ''}`;
  
  const langCode = (routing.lang || 'en').toUpperCase();
  inspLang.innerText = `🌐 ${langCode}`;
  inspSubject.innerText = ticket.subject;
  inspSender.innerText = `From: ${ticket.from}`;
  if (inspDate) {
    inspDate.innerText = `🕒 ${formatDateTime(ticket.created_at)}`;
  }

  // Alert Banner
  if (workflow.alert_message) {
    inspAlertBanner.classList.remove('hidden');
    inspAlertText.innerText = workflow.alert_message;
  } else {
    inspAlertBanner.classList.add('hidden');
  }

  // AI Speed & Model Routing
  inspLatency.innerText = `${triage.latency_ms || 32.4} ms`;
  inspRoutingReason.innerHTML = `
    <strong>Language:</strong> ${langCode} &bull; <strong>Analyzed in:</strong> ${triage.latency_ms || 32.4} ms
  `;

  // Department Gauge
  const deptObj = answers.department || {};
  const deptChoice = deptObj.choice || 'technical';
  const deptConf = Math.round((deptObj.confidence || 0.9) * 100);
  inspDeptVal.innerText = deptChoice.toUpperCase();
  inspDeptBar.style.width = `${deptConf}%`;
  inspDeptConf.innerText = `Confidence: ${deptConf}%`;

  // Churn Risk Gauge
  const churnObj = answers.churn_risk || {};
  const churnProb = Math.round((churnObj.probability || 0) * 100);
  inspChurnVal.innerText = `${churnProb}%`;
  inspChurnBar.style.width = `${churnProb}%`;
  if (churnProb >= 70) {
    inspChurnVal.className = 'text-danger';
    inspChurnStatus.innerText = '🚨 High Risk: Customer might cancel service';
  } else {
    inspChurnVal.className = 'text-muted';
    inspChurnStatus.innerText = 'Low Risk: Customer seems satisfied or neutral';
  }

  // Frustration Steps
  const frustObj = answers.frustration || {};
  const frustScore = frustObj.score || 0;
  const frustLabels = ['Calm (0/3)', 'Concerned (1/3)', 'Annoyed (2/3)', 'Very Upset (3/3)'];
  const frustSubs = ['Polite and friendly inquiry', 'Customer has minor concerns', 'Customer is visibly annoyed', 'Customer is very upset & demands action'];
  inspFrustVal.innerText = frustLabels[frustScore] || 'Calm';
  renderStepDots(inspFrustSteps, frustScore, frustScore >= 2);
  const frustDescEl = document.getElementById('insp-frust-desc');
  if (frustDescEl) frustDescEl.innerText = frustSubs[frustScore] || 'Polite inquiry';

  // Urgency Steps
  const urgObj = answers.urgency || {};
  const urgScore = urgObj.score || 0;
  const urgLabels = ['Routine (0/3)', 'Normal (1/3)', 'High (2/3)', 'Urgent (3/3)'];
  const urgSubs = ['Standard general question', 'Normal customer request', 'Time-sensitive issue', 'Needs immediate priority reply'];
  inspUrgencyVal.innerText = urgLabels[urgScore] || 'Routine';
  renderStepDots(inspUrgencySteps, urgScore, urgScore >= 2);
  const urgDescEl = document.getElementById('insp-urgency-desc');
  if (urgDescEl) urgDescEl.innerText = urgSubs[urgScore] || 'Routine inquiry';

  // Boolean Flags
  const refundObj = answers.refund_requested || {};
  const isRefund = refundObj.requested;
  const refundProb = Math.round((refundObj.probability || 0) * 100);
  inspRefundVal.innerText = isRefund ? `Yes (${refundProb}% sure)` : 'No';
  inspRefundVal.className = isRefund ? 'text-danger' : '';

  const spamObj = answers.is_phishing_or_spam || {};
  const isSpam = spamObj.is_threat;
  const spamProb = Math.round((spamObj.probability || 0) * 100);
  inspSpamVal.innerText = isSpam ? `Spam / Suspicious (${spamProb}%)` : `Safe (${100 - spamProb}%)`;
  inspSpamVal.className = isSpam ? 'text-danger' : '';

  // Email Body
  inspBodyText.innerText = ticket.body;

  // Audit Logs
  const logs = workflow.audit_logs || [];
  inspAuditLogs.innerHTML = logs.map(l => `<li>${escapeHtml(l)}</li>`).join('');

  // Suggested Reply Composer
  if (inspReplyInput) {
    inspReplyInput.value = workflow.suggested_reply || '';
  }
  if (replyFeedbackBanner) {
    replyFeedbackBanner.className = 'hidden';
    replyFeedbackBanner.innerText = '';
  }
  btnMarkResolved.innerText = ticket.status === 'Resolved' ? 'Solved ✓' : 'Mark as Solved';
  btnMarkResolved.disabled = ticket.status === 'Resolved';
}

function renderStepDots(container, activeIndex, isDanger) {
  let html = '';
  for (let i = 0; i < 4; i++) {
    const active = i <= activeIndex ? 'active' : '';
    const danger = (i <= activeIndex && isDanger) ? 'step-danger' : '';
    html += `<span class="step-dot ${active} ${danger}"></span>`;
  }
  container.innerHTML = html;
}

function escapeHtml(text) {
  if (!text) return '';
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}
