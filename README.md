# Smart AI Support & Email Triage Desk

An ultra-fast, multilingual customer support inbox and email triage application powered by [Laya](https://github.com/NandhaKishorM/laya) — the high-speed, non-autoregressive System 1 decision engine.

Evaluates customer intent, mood, cancellation risk, and urgency in a **single forward pass (~32ms)** across 100+ languages without hallucinating text or running slow autoregressive LLM queues.

---

## Architecture Overview

```
                      Inbound Customer Emails & Tickets
                                      │
                                      ▼
                        ┌───────────────────────────┐
                        │    Laya Triage Engine     │
                        │    (32ms Decision Pass)   │
                        └─────────────┬─────────────┘
                                      │
      ┌───────────────────────────────┼──────────────────────────────┐
      ▼                               ▼                              ▼
  Department                      Customer Mood               Cancellation Risk &
  (Billing, Tech, Sales)        (Calm, Annoyed, Upset)         Refund Requests
      │                               │                              │
      └───────────────────────────────┼──────────────────────────────┘
                                      │
                                      ▼
                        ┌───────────────────────────┐
                        │   Automated Rule Engine   │
                        └─────────────┬─────────────┘
                                      │
           ┌──────────────────────────┴──────────────────────────┐
           ▼                                                     ▼
 [Urgent / At-Risk Priority]                             [Fast-Track Refunds]
 Immediate Manager Review                                Billing Quick-Resolution
```

---

## Key Features

1. **Sub-35ms Instant Triage**:
   - Single forward pass non-autoregressive classification using native Laya routers.
   - Instantly categorizes Department (`Billing, Technical, Sales, Cancellation`), Urgency (`0-3`), Customer Mood (`Calm to Very Upset`), and Cancellation Risk (`0-100%`).
2. **Multilingual Auto-Routing**:
   - Built-in script detector automatically routes English, Spanish, German, French, Hindi, Portuguese, and 100+ languages in sub-milliseconds without checkpoint churn.
3. **Automated Priority Escalation**:
   - Unhappy customers or those at risk of canceling are automatically marked as `🚨 URGENT` and moved to the `Urgent / At Risk` queue.
   - Prepares matching multilingual reply drafts ready for one-click review and copy.
4. **Live Gmail IMAP Integration**:
   - Connect your real Gmail inbox directly from the web interface using Google App Passwords.
   - Includes **Sync Recent** for instant import of past emails and a continuous background poller for new incoming unread messages.
5. **Intelligent Email Code Cleaner**:
   - Automatically sanitizes incoming marketing and automated emails by stripping raw CSS stylesheets (`*{ font-family... }`), media queries (`@media...`), scripts, HTML tags, and entity codes.
6. **Newest-First Timeline & Timestamping**:
   - Incoming emails are strictly ordered with newest messages at the very top.
   - Displays clear, formatted dates and times (e.g., `Today at 7:05 PM`, `Yesterday at 4:20 PM`, or `Sep 25 at 11:30 AM`).
7. **Live Glassmorphic Dashboard**:
   - Real-time WebSockets feed incoming tickets to the dashboard without page refreshes.
   - Visual progress gauges, customer mood thermometers, and queue filter tabs (`All`, `Urgent / At Risk`, `Billing`, `Technical`).

---

## Quickstart & Setup

### 1. Prerequisites
- Python 3.10+ (tested on Python 3.12)
- Virtual environment tool (`venv`)

### 2. Installation
```powershell
# Clone the repository
git clone <your-repo-url>
cd layastudy

# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### 3. Running the Server
```powershell
python -m uvicorn server:app --host 127.0.0.1 --port 8000
```
Open [**http://127.0.0.1:8000**](http://127.0.0.1:8000) in your web browser.

---

## Connecting Your Live Gmail Account

You can connect your live Gmail inbox directly through the GUI:

1. **Create a Google App Password**:
   - Open your [Google Account Security](https://myaccount.google.com/security) settings.
   - Verify that **2-Step Verification** is turned ON.
   - Navigate to [App Passwords](https://myaccount.google.com/apppasswords).
   - Generate a 16-character App Password (e.g. `abcd efgh ijkl mnop`).

2. **Connect in the Dashboard**:
   - Click the **"✉️ Connect Gmail"** button in the header.
   - Enter your Gmail address and 16-character App Password.
   - Optionally choose your sync frequency (default: 15 seconds) and whether to import recent emails right away.
   - Click **"Test Connection"** to verify, then click **"Start Live Sync"**.

3. **Managing Sync**:
   - Click **"Sync Recent"** in the top header anytime to pull in the latest 10 emails immediately.
   - The poller will automatically monitor your inbox for new incoming emails and triage them in ~32ms.

---

## API Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/system` | Laya decision engine runtime status and benchmark info. |
| `GET` | `/api/stats` | Real-time counts, language breakdown, and average decision latency. |
| `GET` | `/api/tickets` | Query tickets with optional filters (`queue`, `priority`, `lang`). |
| `POST` | `/api/tickets` | Ingest and evaluate a new ticket/email payload with Laya. |
| `PATCH` | `/api/tickets/{id}/status` | Update a ticket's status (`Open`, `Resolved`). |
| `DELETE` | `/api/tickets` | Clear all tickets from memory. |
| `POST` | `/api/gmail/test` | Test IMAP credentials with Google Mail servers. |
| `POST` | `/api/gmail/connect` | Authenticate Gmail and start the background sync listener. |
| `POST` | `/api/gmail/disconnect`| Disconnect Gmail listener. |
| `POST` | `/api/gmail/sync-recent`| Fetch and triage the latest N emails from Gmail inbox. |
| `GET` | `/api/gmail/status` | Current connection status, total mailbox count, and sync state. |
| `WS` | `/ws` | Real-time WebSocket connection for live dashboard streaming. |

---

## Technology Stack

- **AI Core**: [Laya](https://github.com/NandhaKishorM/laya) (PyTorch, ModernBERT, mmBERT)
- **Backend**: FastAPI, Uvicorn, WebSockets, Python `imaplib` & `email`
- **Frontend**: Vanilla HTML5, CSS3 Glassmorphism, Vanilla ES6 JavaScript (zero build step required)
- **Fonts**: Outfit, Inter, JetBrains Mono
