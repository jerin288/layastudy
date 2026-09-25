"""FastAPI server for the Autonomous Customer Support & Email Triage Desk.
Integrates Laya's non-autoregressive decision engine with live WebSockets,
REST endpoints, ticket management, and inbound traffic simulation.
"""

import os
import random
import asyncio
import time
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from triage_engine import TriageEngine
from rule_engine import RuleEngine
from ticket_store import TicketStore
from gmail_service import GmailService

app = FastAPI(title="Laya Support Triage Engine", version="1.0.0")

# Core services
triage_engine = TriageEngine()
rule_engine = RuleEngine()
ticket_store = TicketStore()
gmail_service = GmailService()

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: Dict[str, Any]):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)

manager = ConnectionManager()

# Background callback for real incoming Gmail emails
async def on_gmail_received(raw_email: Dict[str, Any]):
    raw = {
        "from": raw_email.get("from_email", "customer@example.com"),
        "subject": raw_email.get("subject", "No Subject"),
        "body": raw_email.get("body", ""),
        "timestamp": raw_email.get("timestamp", time.time()),
        "date": raw_email.get("date", "")
    }
    triage_result = triage_engine.triage(raw)
    workflow_result = rule_engine.apply_rules(raw, triage_result)
    ticket = ticket_store.add_ticket(raw, triage_result, workflow_result)
    if ticket:
        await manager.broadcast({
            "type": "NEW_TICKET",
            "ticket": ticket,
            "source": "gmail",
            "stats": ticket_store.get_stats(),
            "gmail_status": gmail_service.get_status()
        })

# Request Models
class NewTicketRequest(BaseModel):
    subject: str
    body: str
    from_email: Optional[str] = "customer@example.com"

class StatusUpdateRequest(BaseModel):
    status: str

class GmailConnectRequest(BaseModel):
    email: str
    app_password: str
    poll_interval: Optional[int] = 15
    mark_read: Optional[bool] = True
    import_recent: Optional[int] = 10

class GmailSyncRecentRequest(BaseModel):
    limit: Optional[int] = 10

class GmailTestRequest(BaseModel):
    email: str
    app_password: str

@app.get("/api/system")
async def get_system_info():
    return {
        "engine": triage_engine.mode,
        "status": triage_engine.status,
        "device": triage_engine.device,
        "sub_35ms_benchmark": True
    }

@app.get("/api/stats")
async def get_stats():
    return ticket_store.get_stats()

@app.get("/api/tickets")
async def get_tickets(queue: Optional[str] = None, priority: Optional[str] = None, lang: Optional[str] = None):
    return ticket_store.get_all(queue=queue, priority=priority, lang=lang)

@app.get("/api/tickets/{ticket_id}")
async def get_ticket_detail(ticket_id: str):
    ticket = ticket_store.get_by_id(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket

@app.post("/api/tickets")
async def create_ticket(req: NewTicketRequest):
    raw = {
        "from": req.from_email,
        "subject": req.subject,
        "body": req.body
    }
    
    # 1. Run Laya Triage Engine (sub-35ms)
    triage_result = triage_engine.triage(raw)
    
    # 2. Run Automated Rule Engine
    workflow_result = rule_engine.apply_rules(raw, triage_result)
    
    # 3. Store ticket
    ticket = ticket_store.add_ticket(raw, triage_result, workflow_result)
    
    # 4. Broadcast live update to all connected dashboard clients
    await manager.broadcast({
        "type": "NEW_TICKET",
        "ticket": ticket,
        "stats": ticket_store.get_stats()
    })
    
    return ticket

@app.patch("/api/tickets/{ticket_id}/status")
async def update_status(ticket_id: str, req: StatusUpdateRequest):
    ticket = ticket_store.update_status(ticket_id, req.status)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    
    await manager.broadcast({
        "type": "TICKET_UPDATED",
        "ticket": ticket,
        "stats": ticket_store.get_stats()
    })
    return ticket

@app.delete("/api/tickets")
async def clear_tickets():
    ticket_store.clear()
    await manager.broadcast({
        "type": "TICKETS_CLEARED",
        "stats": ticket_store.get_stats()
    })
    return {"success": True, "message": "All tickets cleared."}

# Gmail Ingestion Controls
@app.post("/api/gmail/test")
async def test_gmail_connection(req: GmailTestRequest):
    return gmail_service.test_credentials(req.email, req.app_password)

@app.post("/api/gmail/connect")
async def connect_gmail(req: GmailConnectRequest):
    res = await gmail_service.start(
        username=req.email,
        app_password=req.app_password,
        interval=req.poll_interval or 15,
        mark_read=req.mark_read if req.mark_read is not None else True,
        callback=on_gmail_received,
        import_recent=req.import_recent if req.import_recent is not None else 10
    )
    if res.get("success"):
        await manager.broadcast({
            "type": "GMAIL_STATUS_CHANGED",
            "status": gmail_service.get_status()
        })
    return res

@app.post("/api/gmail/sync-recent")
async def sync_recent_emails(req: GmailSyncRecentRequest):
    if not (gmail_service.email and gmail_service.app_password):
        raise HTTPException(status_code=400, detail="Gmail is not connected. Please connect Gmail first.")

    loop = asyncio.get_running_loop()
    limit = max(1, min(req.limit or 10, 50))
    recent_emails = await loop.run_in_executor(None, lambda: gmail_service.fetch_recent_sync(limit))

    synced_count = 0
    for item in recent_emails:
        raw = {
            "from": item.get("from_email", "customer@example.com"),
            "subject": item.get("subject", "No Subject"),
            "body": item.get("body", ""),
            "timestamp": item.get("timestamp", time.time()),
            "date": item.get("date", "")
        }
        triage_result = triage_engine.triage(raw)
        workflow_result = rule_engine.apply_rules(raw, triage_result)
        ticket = ticket_store.add_ticket(raw, triage_result, workflow_result)
        if ticket:
            synced_count += 1
            gmail_service.total_ingested += 1
            await manager.broadcast({
                "type": "NEW_TICKET",
                "ticket": ticket,
                "source": "gmail",
                "stats": ticket_store.get_stats(),
                "gmail_status": gmail_service.get_status()
            })

    await manager.broadcast({
        "type": "GMAIL_STATUS_CHANGED",
        "status": gmail_service.get_status()
    })

    return {
        "success": True,
        "message": f"Successfully synced {synced_count} emails into the queue.",
        "synced_count": synced_count,
        "total_mailbox_count": gmail_service.total_mailbox_count
    }

@app.post("/api/gmail/disconnect")
async def disconnect_gmail():
    await gmail_service.stop()
    await manager.broadcast({
        "type": "GMAIL_STATUS_CHANGED",
        "status": gmail_service.get_status()
    })
    return {"success": True, "message": "Disconnected Gmail listener."}

@app.get("/api/gmail/status")
async def get_gmail_status():
    return gmail_service.get_status()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Send initial state
        await websocket.send_json({
            "type": "INIT",
            "stats": ticket_store.get_stats(),
            "tickets": ticket_store.get_all()
        })
        while True:
            # Keep-alive receive loop
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)

# Mount static files and frontend index
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
async def serve_index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Laya Support Triage Backend Active. Open /static/index.html."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
