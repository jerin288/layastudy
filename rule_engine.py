"""Rule and workflow automation engine for customer support tickets.
Takes raw Laya decision output and triggers actions, escalations,
priority queues, and canned response recommendations.
"""

from typing import Dict, Any, List


class RuleEngine:
    """Evaluates business rules based on Laya's calibrated scores."""

    @staticmethod
    def apply_rules(ticket_data: Dict[str, Any], triage_result: Dict[str, Any]) -> Dict[str, Any]:
        answers = triage_result.get("answers", {})
        routing = triage_result.get("routing", {})
        
        dept = answers.get("department", {}).get("choice", "technical")
        churn_risk = answers.get("churn_risk", {}).get("probability", 0.0)
        frustration_score = answers.get("frustration", {}).get("score", 0)
        urgency_score = answers.get("urgency", {}).get("score", 0)
        refund_requested = answers.get("refund_requested", {}).get("requested", False)
        is_threat = answers.get("is_phishing_or_spam", {}).get("is_threat", False)
        lang = routing.get("lang", "en")
        
        tags: List[str] = [f"Dept:{dept.upper()}"]
        logs: List[str] = []
        priority = "Normal"
        queue = f"{dept.capitalize()} Support"
        escalation_triggered = False
        alert_message = None

        # 1. Security Quarantine Rule
        if is_threat:
            priority = "Critical"
            queue = "Spam & Quarantine"
            tags.append("SECURITY_THREAT")
            tags.append("AUTO_QUARANTINED")
            logs.append("⚠️ Suspicious Email: Flagged as spam or security threat. Moved to quarantine.")
            alert_message = "⚠️ Warning: This email looks like phishing or spam and was quarantined."

        # 2. VIP Churn Prevention Escalation Rule
        elif churn_risk >= 0.70 or frustration_score >= 3:
            priority = "Critical"
            queue = "Urgent / At Risk"
            escalation_triggered = True
            tags.append("CHURN_RISK_HIGH")
            tags.append("PRIORITY_VIP")
            logs.append(f"🚨 Priority Alert: Customer seems very unhappy ({int(churn_risk*100)}% risk). Flagged for urgent manager attention.")
            alert_message = f"⚠️ Urgent: Customer is very unhappy and may cancel ({int(churn_risk*100)}% risk). Please handle with care."

        # 3. Fast-Track Refund Rule
        elif refund_requested and dept in ["billing", "cancellation"]:
            priority = "High"
            queue = "Billing Support"
            tags.append("REFUND_DISPUTE")
            logs.append("💳 Refund Request: Customer asked for a refund. Routed to Billing team for fast processing.")

        # 4. Outage / Critical Technical Rule
        elif dept == "technical" and urgency_score >= 3:
            priority = "Critical"
            queue = "Urgent Tech Support"
            tags.append("PRODUCTION_OUTAGE")
            logs.append("⚡ Urgent Issue: Major technical problem reported. Escalated to senior engineers.")

        # 5. Multilingual Regional Routing
        if lang != "en":
            tags.append(f"Lang:{lang.upper()}")
            logs.append(f"🌐 Language Match: Received in {lang.upper()}. Routed to team members who speak this language.")

        # 6. Generate Canned Response Draft
        suggested_reply = RuleEngine._generate_suggested_reply(ticket_data, dept, churn_risk, refund_requested, lang)

        return {
            "priority": priority,
            "queue": queue,
            "tags": tags,
            "escalation_triggered": escalation_triggered,
            "alert_message": alert_message,
            "audit_logs": logs,
            "suggested_reply": suggested_reply
        }

    @staticmethod
    def _generate_suggested_reply(ticket: Dict[str, Any], dept: str, churn_prob: float, refund: bool, lang: str) -> str:
        name = ticket.get("from", "Customer").split("@")[0].capitalize()
        
        if lang == "es":
            if refund or churn_prob > 0.6:
                return f"Hola {name},\nLamentamos mucho el inconveniente con su cuenta. Ya hemos priorizado su solicitud con el equipo de facturación para procesar el reembolso de inmediato y revisar su suscripción.\nUn agente senior se comunicará en breve."
            return f"Hola {name},\nGracias por contactar con soporte técnico. Hemos recibido su consulta y nuestro equipo ya está revisando su caso.\nAtentamente,\nEquipo de Soporte."
        
        elif lang == "de":
            if refund or churn_prob > 0.6:
                return f"Guten Tag {name},\nvielen Dank für Ihre Nachricht. Es tut uns leid, dass es zu Abrechnungsproblemen gekommen ist. Wir haben Ihre Rückerstattungsanfrage mit höchster Priorität an unser Abrechnungsteam übergeben.\nMit freundlichen Grüßen,\nKundenservice."
            return f"Guten Tag {name},\nvielen Dank für Ihre Anfrage. Unser technischer Support prüft das Problem bereits.\nMit freundlichen Grüßen."

        elif lang == "hi":
            return f"नमस्ते {name},\nआपके संदेश के लिए धन्यवाद। हमें हुई असुविधा के लिए खेद है। हमारी सीनियर बिलिंग टीम आपके रिफंड अनुरोध की प्राथमिकता से जांच कर रही है।"

        else:
            if refund and churn_prob > 0.6:
                return f"Hi {name},\nThank you for getting in touch, and we are so sorry about the billing issue. I have flagged your request directly to our senior billing team to review your refund right away.\nWarm regards,\nCustomer Support Team"
            elif dept == "technical":
                return f"Hi {name},\nThank you for letting us know about this issue. Our technical team is looking into it right now, and we will follow up with an update as soon as possible."
            else:
                return f"Hi {name},\nThank you for reaching out to us. We have received your message and sent it to our {dept.capitalize()} team, who will reply to you shortly."
