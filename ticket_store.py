"""In-memory ticket store for Laya Autonomous Support & Email Triage Desk.
Clean production store holding live ingested customer emails and tickets.
"""

import time
import uuid
from typing import List, Dict, Any, Optional
from gmail_service import clean_email_text
from rule_engine import RuleEngine


class TicketStore:
    def __init__(self):
        # Starts 100% clean with zero sample or seed tickets
        self.tickets: List[Dict[str, Any]] = []
        self.seen_signatures = set()

    def _sanitize_ticket(self, t: Dict[str, Any]):
        wf = t.get("workflow", {})
        if wf.get("queue") == "Executive Escalations (VIP)":
            wf["queue"] = "Urgent / At Risk"
        if "body" in t:
            t["body"] = clean_email_text(t["body"])
        reply = wf.get("suggested_reply", "")
        # If reply contains broken tags like "<notifications" or single newline squishing, regenerate cleanly
        if "<" in reply.split("\n")[0] or "\n\n" not in reply:
            wf["suggested_reply"] = RuleEngine.regenerate_clean_reply(t)

        triage = t.get("triage", {})
        answers = triage.get("answers", {})
        if not wf.get("action_items"):
            wf["action_items"] = answers.get("action_items") or [
                {"id": 0, "task": "Review customer request and verify account details", "done": False},
                {"id": 1, "task": "Check system status and active records", "done": False},
                {"id": 2, "task": "Send response and confirm resolution", "done": False}
            ]
        if not wf.get("assigned_specialist"):
            wf["assigned_specialist"] = answers.get("assigned_specialist") or {
                "name": "Maya Patel", "role": "Customer Success Specialist", "avatar": "🎧"
            }
        if not wf.get("intent"):
            wf["intent"] = answers.get("intent") or {"choice": "general_inquiry", "label": "General Inquiry"}
        if not wf.get("difficulty"):
            wf["difficulty"] = answers.get("difficulty") or {"choice": "standard", "estimated_time": "⏱️ Standard (~1 hour)"}

    def get_all(self, queue: Optional[str] = None, priority: Optional[str] = None, lang: Optional[str] = None) -> List[Dict[str, Any]]:
        for t in self.tickets:
            self._sanitize_ticket(t)

        result = self.tickets
        if queue and queue != "all":
            result = [t for t in result if t.get("workflow", {}).get("queue", "").lower() == queue.lower()]
        if priority and priority != "all":
            result = [t for t in result if t.get("workflow", {}).get("priority", "").lower() == priority.lower()]
        if lang and lang != "all":
            result = [t for t in result if t.get("triage", {}).get("routing", {}).get("lang", "").lower() == lang.lower()]
        return sorted(result, key=lambda x: x.get("created_at", 0), reverse=True)

    def get_by_id(self, ticket_id: str) -> Optional[Dict[str, Any]]:
        for t in self.tickets:
            if t["id"] == ticket_id:
                self._sanitize_ticket(t)
                return t
        return None

    def add_ticket(self, raw_ticket: Dict[str, Any], triage_result: Dict[str, Any], workflow_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        body = clean_email_text(raw_ticket.get("body", ""))
        sig = f"{raw_ticket.get('from', '')}|{raw_ticket.get('subject', '')}|{body[:60]}"
        if sig in self.seen_signatures:
            return None
        self.seen_signatures.add(sig)

        created_at = float(raw_ticket.get("timestamp") or raw_ticket.get("created_at") or time.time())
        ticket = {
            "id": f"EMAIL-{str(uuid.uuid4())[:6].upper()}",
            "created_at": created_at,
            "date_str": raw_ticket.get("date") or raw_ticket.get("date_str", ""),
            "status": "Escalated" if workflow_result.get("escalation_triggered") else "Open",
            "from": raw_ticket.get("from", "customer@example.com"),
            "subject": raw_ticket.get("subject", "No Subject"),
            "body": body,
            "triage": triage_result,
            "workflow": workflow_result
        }
        self.tickets.append(ticket)
        return ticket

    def update_status(self, ticket_id: str, new_status: str) -> Optional[Dict[str, Any]]:
        ticket = self.get_by_id(ticket_id)
        if ticket:
            ticket["status"] = new_status
            ticket["updated_at"] = time.time()
            return ticket
        return None

    def toggle_action_item(self, ticket_id: str, item_id: int) -> Optional[Dict[str, Any]]:
        ticket = self.get_by_id(ticket_id)
        if not ticket:
            return None
        wf = ticket.setdefault("workflow", {})
        items = wf.setdefault("action_items", [])
        for item in items:
            if item.get("id") == item_id:
                item["done"] = not item.get("done", False)
                break
        ticket["updated_at"] = time.time()
        return ticket

    def apply_quick_action(self, ticket_id: str, action: str) -> Optional[Dict[str, Any]]:
        ticket = self.get_by_id(ticket_id)
        if not ticket:
            return None
        wf = ticket.setdefault("workflow", {})
        logs = wf.setdefault("audit_logs", [])
        
        if action == "approve_refund":
            logs.append(f"💳 Quick Action: Refund approved by agent ({time.strftime('%I:%M %p')})")
            items = wf.setdefault("action_items", [])
            for it in items:
                if "refund" in it.get("task", "").lower() or "transaction" in it.get("task", "").lower():
                    it["done"] = True
            wf["refund_approved"] = True
        elif action == "fast_track":
            wf["priority"] = "Critical"
            wf["escalation_triggered"] = True
            logs.append(f"⚡ Quick Action: Fast-Tracked to senior escalation queue ({time.strftime('%I:%M %p')})")
            wf["assigned_specialist"] = {"name": "Alex Rivera", "role": "Senior Escalations Lead", "avatar": "⚡"}
        elif action == "archive":
            ticket["status"] = "Archived"
            logs.append(f"🔕 Quick Action: Ticket archived ({time.strftime('%I:%M %p')})")
            
        ticket["updated_at"] = time.time()
        return ticket

    def clear(self):
        """Clears all tickets from memory."""
        self.tickets.clear()
        self.seen_signatures.clear()

    def get_stats(self) -> Dict[str, Any]:
        total = len(self.tickets)
        if total == 0:
            return {"total": 0, "avg_latency_ms": 0.0, "churn_risk_count": 0, "queues": {}, "languages": {}}

        latencies = [t.get("triage", {}).get("latency_ms", 32.0) for t in self.tickets]
        avg_latency = round(sum(latencies) / len(latencies), 1) if latencies else 0.0
        
        churn_count = sum(1 for t in self.tickets if t.get("workflow", {}).get("escalation_triggered", False))
        
        queues = {}
        languages = {}
        for t in self.tickets:
            q = t.get("workflow", {}).get("queue", "General")
            if q == "Executive Escalations (VIP)":
                q = "Urgent / At Risk"
            queues[q] = queues.get(q, 0) + 1
            
            l = t.get("triage", {}).get("routing", {}).get("lang", "en").upper()
            languages[l] = languages.get(l, 0) + 1

        return {
            "total": total,
            "avg_latency_ms": avg_latency,
            "churn_risk_count": churn_count,
            "queues": queues,
            "languages": languages
        }
