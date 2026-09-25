"""Gmail IMAP Listener for Laya Autonomous Support & Email Triage Desk.
Monitors an inbox for unread customer emails, decodes them,
and dispatches them to Laya's sub-35ms triage pipeline in real time.
"""

import os
import sys
import time
import email
import imaplib
import argparse
import urllib.request
import json
import re
from email.header import decode_header
from typing import Optional, Tuple, Dict, Any
from dotenv import load_dotenv

load_dotenv()


def decode_str(header_value: Optional[str]) -> str:
    """Safely decodes RFC 2047 MIME encoded email headers."""
    if not header_value:
        return ""
    decoded_fragments = decode_header(header_value)
    text = ""
    for frag, enc in decoded_fragments:
        if isinstance(frag, bytes):
            text += frag.decode(enc or "utf-8", errors="replace")
        else:
            text += str(frag)
    return text


def extract_body(msg: email.message.Message) -> str:
    """Extracts plain text content from a multipart or plain email."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))
            if "attachment" in content_disposition:
                continue
            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    body = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                    break
            elif content_type == "text/html" and not body:
                payload = part.get_payload(decode=True)
                if payload:
                    html_text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                    # Basic tag stripping
                    body = re.sub(r"<[^>]+>", " ", html_text)
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            body = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
    
    # Clean up whitespace
    return re.sub(r"\s+", " ", body).strip()


class GmailTriageListener:
    def __init__(self, username: str, app_password: str, server_url: str = "http://127.0.0.1:8000/api/tickets", mark_read: bool = True):
        self.username = username.strip()
        self.app_password = app_password.replace(" ", "").strip()
        self.server_url = server_url
        self.mark_read = mark_read
        self.imap_server = "imap.gmail.com"
        self.imap_port = 993

    def connect(self) -> imaplib.IMAP4_SSL:
        """Connects and authenticates to Gmail via IMAP SSL."""
        mail = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)
        mail.login(self.username, self.app_password)
        mail.select("INBOX")
        return mail

    def test_connection(self) -> bool:
        """Verifies Gmail credentials."""
        try:
            print(f"Connecting to {self.imap_server} as {self.username}...")
            mail = self.connect()
            status, count = mail.select("INBOX")
            mail.logout()
            print(f"✅ Success! Connected to Gmail INBOX. Found {count[0].decode('utf-8')} total messages.")
            return True
        except imaplib.IMAP4.error as e:
            print(f"❌ Gmail IMAP Authentication failed: {e}")
            print("\nTip: Ensure 2-Step Verification is enabled and you are using a 16-character App Password, not your regular Google login password.")
            return False
        except Exception as e:
            print(f"❌ Connection error: {e}")
            return False

    def process_unread_emails(self, mail: imaplib.IMAP4_SSL):
        """Searches for unread messages and dispatches them to Laya triage."""
        status, data = mail.search(None, "UNSEEN")
        if status != "OK" or not data[0]:
            return

        msg_ids = data[0].split()
        print(f"\n📬 Detected {len(msg_ids)} new unread email(s) in inbox:")

        for msg_id in msg_ids:
            try:
                res, msg_data = mail.fetch(msg_id, "(RFC822)")
                if res != "OK" or not msg_data:
                    continue

                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)

                subject = decode_str(msg.get("Subject", "No Subject"))
                from_email = decode_str(msg.get("From", "unknown@example.com"))
                body = extract_body(msg)

                if not body and not subject:
                    continue

                print(f"\n--- Ingesting Incoming Email ---")
                print(f"From    : {from_email}")
                print(f"Subject : {subject}")
                print(f"Body    : {body[:100]}..." if len(body) > 100 else f"Body    : {body}")

                # Send to Laya Triage API
                triage_res = self.dispatch_to_laya(from_email, subject, body)
                
                if triage_res:
                    triage = triage_res.get("triage", {})
                    answers = triage.get("answers", {})
                    routing = triage.get("routing", {})
                    workflow = triage_res.get("workflow", {})

                    dept = answers.get("department", {}).get("choice", "technical").upper()
                    churn = int((answers.get("churn_risk", {}).get("probability", 0)) * 100)
                    lang = routing.get("lang", "en").upper()
                    latency = triage.get("latency_ms", 32)
                    escalated = workflow.get("escalation_triggered", False)

                    print(f"⚡ [Laya Triage Pass: {latency}ms]")
                    print(f"   Language: {lang} | Department: {dept} | Churn Risk: {churn}%")
                    if escalated:
                        print(f"   🚨 AUTOMATION TRIGGERED: Auto-escalated to {workflow.get('queue')}")
                    else:
                        print(f"   ✓ Routed to queue: {workflow.get('queue')}")

                # Mark as read if configured
                if self.mark_read:
                    mail.store(msg_id, "+FLAGS", "\\Seen")

            except Exception as e:
                print(f"⚠️ Error processing email ID {msg_id}: {e}")

    def dispatch_to_laya(self, from_email: str, subject: str, body: str) -> Optional[Dict[str, Any]]:
        """Sends ticket payload to the running Laya Triage backend."""
        payload = json.dumps({
            "from_email": from_email,
            "subject": subject,
            "body": body
        }).encode("utf-8")

        req = urllib.request.Request(
            self.server_url,
            data=payload,
            headers={"Content-Type": "application/json"}
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    return json.loads(response.read().decode("utf-8"))
        except Exception as e:
            print(f"❌ Failed to post to Laya server ({self.server_url}): {e}")
            print("   Make sure the server is running on http://127.0.0.1:8000")
        return None

    def start_polling(self, interval_seconds: int = 15):
        """Continuously polls Gmail inbox on a timer."""
        print(f"\n🚀 Laya Gmail Listener started for {self.username}")
        print(f"   Target Server : {self.server_url}")
        print(f"   Polling Every : {interval_seconds} seconds")
        print("   Press CTRL+C to stop.\n")

        while True:
            try:
                mail = self.connect()
                self.process_unread_emails(mail)
                mail.logout()
            except KeyboardInterrupt:
                print("\n🛑 Stopped Gmail listener.")
                break
            except Exception as e:
                print(f"⚠️ Polling loop error: {e}. Retrying in {interval_seconds}s...")

            time.sleep(interval_seconds)


def main():
    parser = argparse.ArgumentParser(description="Connect Gmail to Laya Triage Desk")
    parser.add_argument("--email", help="Gmail address", default=os.getenv("GMAIL_EMAIL"))
    parser.add_argument("--password", help="16-character Google App Password", default=os.getenv("GMAIL_APP_PASSWORD"))
    parser.add_argument("--server", help="Laya Triage Server URL", default=os.getenv("TICKET_SERVER_URL", "http://127.0.0.1:8000/api/tickets"))
    parser.add_argument("--interval", help="Polling interval in seconds", type=int, default=int(os.getenv("POLL_INTERVAL_SECONDS", "15")))
    parser.add_argument("--test", action="store_true", help="Test credentials only and exit")

    args = parser.parse_args()

    email_addr = args.email
    password = args.password

    if not email_addr or not password:
        print("\n=== Laya Triage Desk - Gmail Connection Setup ===\n")
        if not email_addr:
            email_addr = input("Enter your Gmail address: ").strip()
        if not password:
            password = input("Enter your 16-char Google App Password: ").strip()

    if not email_addr or not password:
        print("❌ Error: Both Gmail address and App Password are required.")
        sys.exit(1)

    listener = GmailTriageListener(
        username=email_addr,
        app_password=password,
        server_url=args.server,
        mark_read=os.getenv("MARK_AS_READ", "true").lower() == "true"
    )

    if args.test:
        success = listener.test_connection()
        sys.exit(0 if success else 1)

    # Test connection first before polling
    if listener.test_connection():
        listener.start_polling(interval_seconds=args.interval)


if __name__ == "__main__":
    main()
