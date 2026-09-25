import email.utils
import re
from typing import Dict, Any, List


class RuleEngine:
    """Evaluates business rules based on Laya's calibrated scores."""

    @staticmethod
    def extract_sender_name(from_str: str) -> str:
        """Extracts a clean, human-friendly first name or entity name from an email From header."""
        if not from_str:
            return "there"

        realname, addr = email.utils.parseaddr(from_str)
        lower_addr = addr.lower() if addr else ""

        # Automated / notification addresses should use a polite neutral greeting
        if any(t in lower_addr for t in ["no-reply", "noreply", "alert", "notification", "newsletter", "mailer-daemon", "donotreply", "system"]):
            return "there"

        # Check realname if present
        if realname:
            clean = realname.strip("\"' \t\r\n")
            lower_clean = clean.lower()
            if any(t in lower_clean for t in ["no-reply", "noreply", "notification", "alert", "mailer", "system", "support team"]):
                return "there"
            parts = clean.split()
            if parts:
                first = parts[0].strip(" ,;:<>()\"'")
                if first.isalpha() and len(first) > 1:
                    return first.capitalize()
            return clean

        # If no real name, extract name from address prefix
        if addr and "@" in addr:
            user_part = addr.split("@")[0].strip()
            letters = re.sub(r"[^a-zA-Z]", " ", user_part).strip()
            if letters:
                first = letters.split()[0].capitalize()
                if len(first) > 1 and first.lower() not in ["info", "admin", "service", "help", "billing", "support", "contact"]:
                    return first

        return "there"

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
    def regenerate_clean_reply(ticket: Dict[str, Any]) -> str:
        """Regenerates a clean, polished reply draft for existing tickets."""
        triage = ticket.get("triage", {})
        answers = triage.get("answers", {})
        routing = triage.get("routing", {})
        dept = answers.get("department", {}).get("choice", "technical")
        churn_risk = answers.get("churn_risk", {}).get("probability", 0.0)
        refund_requested = answers.get("refund_requested", {}).get("requested", False)
        lang = routing.get("lang", "en")
        return RuleEngine._generate_suggested_reply(ticket, dept, churn_risk, refund_requested, lang)

    @staticmethod
    def _generate_suggested_reply(ticket: Dict[str, Any], dept: str, churn_prob: float, refund: bool, lang: str) -> str:
        name = RuleEngine.extract_sender_name(ticket.get("from", ""))
        greeting = f"Hi {name}," if name != "there" else "Hi there,"

        if lang == "es":
            if refund or churn_prob > 0.6:
                return (
                    f"Hola{' ' + name if name != 'there' else ''},\n\n"
                    "Lamentamos mucho el inconveniente con su cuenta. Ya hemos priorizado su solicitud con nuestro equipo de facturación para revisar su caso de inmediato.\n\n"
                    "Un agente especializado se comunicará con usted a la brevedad.\n\n"
                    "Atentamente,\n"
                    "Equipo de Soporte"
                )
            return (
                f"Hola{' ' + name if name != 'there' else ''},\n\n"
                "Gracias por comunicarse con nosotros. Hemos recibido su consulta y nuestro equipo ya está revisando su caso.\n\n"
                "Le responderemos tan pronto tengamos una actualización.\n\n"
                "Atentamente,\n"
                "Equipo de Soporte"
            )

        elif lang == "de":
            if refund or churn_prob > 0.6:
                return (
                    f"Guten Tag{' ' + name if name != 'there' else ''},\n\n"
                    "vielen Dank für Ihre Nachricht. Es tut uns leid, dass es zu Unannehmlichkeiten gekommen ist. Wir haben Ihre Anfrage mit höchster Priorität an unser Abrechnungsteam übergeben.\n\n"
                    "Ein Mitarbeiter wird sich in Kürze bei Ihnen melden.\n\n"
                    "Mit freundlichen Grüßen,\n"
                    "Kundenservice-Team"
                )
            return (
                f"Guten Tag{' ' + name if name != 'there' else ''},\n\n"
                "vielen Dank für Ihre Anfrage. Unser Support-Team prüft Ihr Anliegen bereits sorgfältig.\n\n"
                "Wir melden uns schnellstmöglich bei Ihnen zurück.\n\n"
                "Mit freundlichen Grüßen,\n"
                "Kundenservice-Team"
            )

        elif lang == "hi":
            return (
                f"नमस्ते{' ' + name if name != 'there' else ''},\n\n"
                "हमारे सहायता केंद्र से संपर्क करने के लिए धन्यवाद। हमने आपका संदेश प्राप्त कर लिया है और हमारी टीम प्राथमिकता से इसकी जांच कर रही है।\n\n"
                "हम जल्द ही आपसे संपर्क करेंगे।\n\n"
                "सादर,\n"
                "कस्टमर सपोर्ट टीम"
            )

        # English (Default)
        if refund and churn_prob > 0.6:
            return (
                f"{greeting}\n\n"
                "Thank you for reaching out to us, and we sincerely apologize for the inconvenience with your account. "
                "I have forwarded your request directly to our Senior Billing team with high priority so they can process your refund and resolve this immediately.\n\n"
                "A team specialist will follow up with you shortly.\n\n"
                "Best regards,\n"
                "Customer Support Team"
            )
        elif refund:
            return (
                f"{greeting}\n\n"
                "Thank you for contacting us. We have received your refund request and sent it to our Billing team for immediate review.\n\n"
                "We will notify you as soon as the review is complete.\n\n"
                "Best regards,\n"
                "Customer Support Team"
            )
        elif churn_prob > 0.6:
            return (
                f"{greeting}\n\n"
                "Thank you for reaching out to us. We are truly sorry to hear that you have had a frustrating experience, and we want to resolve this for you as quickly as possible. "
                "A senior team member is looking into your case right now.\n\n"
                "We will reach back out to you very soon.\n\n"
                "Warm regards,\n"
                "Customer Support Team"
            )
        elif dept == "technical":
            return (
                f"{greeting}\n\n"
                "Thank you for letting us know about this issue. Our technical team is actively investigating it to get this sorted out for you as quickly as possible.\n\n"
                "We will follow up with an update shortly.\n\n"
                "Best regards,\n"
                "Customer Support Team"
            )
        elif dept == "billing":
            return (
                f"{greeting}\n\n"
                "Thank you for reaching out to our Billing department. We have received your inquiry and are reviewing your account details now.\n\n"
                "We will follow up with you shortly.\n\n"
                "Best regards,\n"
                "Customer Support Team"
            )
        elif dept == "sales":
            return (
                f"{greeting}\n\n"
                "Thank you for contacting our Sales team! We are delighted to assist you with your inquiry.\n\n"
                "A representative will reach out to you shortly with more details.\n\n"
                "Best regards,\n"
                "Sales & Support Team"
            )
        else:
            return (
                f"{greeting}\n\n"
                "Thank you for getting in touch with our support team. We have received your message and are reviewing it.\n\n"
                "We will get back to you with an update as soon as possible.\n\n"
                "Best regards,\n"
                "Customer Support Team"
            )
