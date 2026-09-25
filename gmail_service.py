"""Background Gmail IMAP service integrated with FastAPI.
Allows connecting, testing, and managing live Gmail polling directly from the GUI.
"""

import asyncio
import email
import email.utils
import html
import imaplib
import os
import re
import smtplib
import time
from email.header import decode_header
from email.mime.text import MIMEText
from typing import Optional, Dict, Any, Callable, List


def decode_str(header_value: Optional[str]) -> str:
    """Safely decodes RFC 2047 MIME encoded email headers."""
    if not header_value:
        return ""
    try:
        decoded_fragments = decode_header(header_value)
        text = ""
        for frag, enc in decoded_fragments:
            if isinstance(frag, bytes):
                text += frag.decode(enc or "utf-8", errors="replace")
            else:
                text += str(frag)
        return text
    except Exception:
        return str(header_value)


def clean_email_text(raw_text: str) -> str:
    """Strips all HTML tags, <style> CSS blocks, <script> code, entities,
    and leftover CSS selectors to ensure only clean, human-readable text remains."""
    if not raw_text:
        return ""

    text = raw_text

    # 1. Remove comments
    text = re.sub(r"<!--[\s\S]*?-->", " ", text)

    # 2. Remove entire <style>...</style> and <script>...</script> blocks
    text = re.sub(r"<style[^>]*>[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<script[^>]*>[\s\S]*?</script>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<head[^>]*>[\s\S]*?</head>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<xml[^>]*>[\s\S]*?</xml>", " ", text, flags=re.IGNORECASE)

    # 3. Handle line-break HTML elements
    text = re.sub(r"<br\s*/?>|</p>|</div>|</tr>|</li>|</h1>|</h2>|</h3>", "\n", text, flags=re.IGNORECASE)

    # 4. Strip remaining HTML tags
    text = re.sub(r"<[^>]+>", " ", text)

    # 5. Decode HTML entities (&nbsp;, &amp;, etc.)
    text = html.unescape(text)

    # 6. Remove leftover CSS selectors or CSS block remnants that leaked
    text = re.sub(r"@media[^{]*\{[^{}]*\{[^}]*\}[^}]*\}", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"@[^{]+\{[^}]*\}", " ", text)
    text = re.sub(r"\{[^{}]*:[^{}]*\}", " ", text)
    text = re.sub(r"[*a-zA-Z0-9_\-\s,.:#*!>{}]*\}", " ", text)

    # 7. Clean up non-breaking spaces and zero-width spaces
    text = text.replace("\xa0", " ").replace("\u200c", "").replace("\u200b", "").replace("\ufeff", "")

    # 8. Collapse repeated decorative dashes/underscores/stars
    text = re.sub(r"[-=_*]{4,}", " ", text)

    # 9. Clean up whitespace
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    non_empty = []
    for l in lines:
        if l:
            non_empty.append(l)
        elif non_empty and non_empty[-1] != "":
            non_empty.append("")

    cleaned = "\n".join(non_empty).strip()
    return cleaned if cleaned else raw_text


def extract_body(msg: email.message.Message) -> str:
    """Extracts clean plain text content from a multipart or plain email,
    removing all CSS stylesheets, scripts, and HTML tags."""
    plain_text = ""
    html_text = ""

    try:
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))
                if "attachment" in content_disposition:
                    continue

                if content_type == "text/plain" and not plain_text:
                    payload = part.get_payload(decode=True)
                    if payload:
                        plain_text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                elif content_type == "text/html" and not html_text:
                    payload = part.get_payload(decode=True)
                    if payload:
                        html_text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                raw = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
                if msg.get_content_type() == "text/html":
                    html_text = raw
                else:
                    plain_text = raw
    except Exception as e:
        print(f"[GmailService] Body extraction exception: {e}")

    # Clean both representations
    cleaned_plain = clean_email_text(plain_text)
    cleaned_html = clean_email_text(html_text)

    # Prefer plain text if it contains meaningful content (> 30 chars), otherwise fallback to cleaned HTML
    if len(cleaned_plain) >= 30:
        return cleaned_plain
    elif cleaned_html:
        return cleaned_html
    return cleaned_plain or "No message content."


class GmailService:
    def __init__(self):
        self.email: Optional[str] = os.getenv("GMAIL_EMAIL")
        self.app_password: Optional[str] = os.getenv("GMAIL_APP_PASSWORD")
        self.poll_interval: int = int(os.getenv("POLL_INTERVAL_SECONDS", "15"))
        self.mark_read: bool = os.getenv("MARK_AS_READ", "true").lower() == "true"
        
        self.is_connected: bool = False
        self.is_polling: bool = False
        self.last_poll_time: Optional[float] = None
        self.total_ingested: int = 0
        self.last_error: Optional[str] = None
        self.total_mailbox_count: int = 0
        self.processed_ids: set = set()

        self._task: Optional[asyncio.Task] = None
        self._callback: Optional[Callable] = None

    def test_credentials(self, username: str, app_password: str) -> Dict[str, Any]:
        """Tests IMAP authentication synchronously."""
        clean_user = username.strip()
        clean_pass = app_password.replace(" ", "").strip()
        try:
            mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
            mail.login(clean_user, clean_pass)
            status, count = mail.select("INBOX")
            total_msgs = int(count[0].decode("utf-8")) if count and count[0] else 0
            mail.logout()
            return {
                "success": True,
                "message": f"Successfully connected to Gmail! Found {total_msgs} messages in INBOX.",
                "total_messages": total_msgs
            }
        except imaplib.IMAP4.error as e:
            return {
                "success": False,
                "message": f"Authentication failed: {str(e)}. Make sure 2-Step Verification is active and you use a 16-character App Password."
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Connection error: {str(e)}"
            }

    def fetch_recent_sync(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetches the most recent `limit` emails directly from the end of INBOX sequence."""
        if not self.email or not self.app_password:
            return []

        try:
            mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
            mail.login(self.email, self.app_password)
            status, count = mail.select("INBOX", readonly=True)
            total = int(count[0].decode()) if count and count[0] else 0
            self.total_mailbox_count = total
            if total == 0:
                mail.logout()
                return []

            start_seq = max(1, total - limit + 1)
            end_seq = total
            results = []

            # Loop backwards from newest to oldest
            for seq in range(end_seq, start_seq - 1, -1):
                try:
                    res, msg_data = mail.fetch(str(seq), "(RFC822)")
                    if res != "OK" or not msg_data:
                        continue
                    for part in msg_data:
                        if isinstance(part, tuple):
                            msg = email.message_from_bytes(part[1])
                            msg_id = msg.get("Message-ID", f"seq-{seq}")
                            subject = decode_str(msg.get("Subject", "No Subject"))
                            from_email = decode_str(msg.get("From", "unknown@example.com"))
                            date_header = decode_str(msg.get("Date", ""))
                            ts = time.time()
                            if date_header:
                                try:
                                    ts = email.utils.parsedate_to_datetime(date_header).timestamp()
                                except Exception:
                                    ts = time.time()

                            body = extract_body(msg)
                            if subject or body:
                                results.append({
                                    "id": msg_id,
                                    "from_email": from_email,
                                    "subject": subject,
                                    "body": body,
                                    "date": date_header,
                                    "timestamp": ts
                                })
                except Exception as e:
                    print(f"[GmailService] Error fetching seq {seq}: {e}")

            mail.logout()
            return results
        except Exception as e:
            print(f"[GmailService] Error in fetch_recent_sync: {e}")
            self.last_error = str(e)
            return []

    def _fetch_unread_sync(self) -> List[Dict[str, Any]]:
        """Synchronously connects to IMAP, searches UNSEEN, and fetches new messages."""
        if not self.email or not self.app_password:
            return []

        try:
            mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
            mail.login(self.email, self.app_password)
            status, count = mail.select("INBOX")
            total = int(count[0].decode()) if count and count[0] else 0
            self.total_mailbox_count = total

            # Search for unread emails
            status, search_data = mail.search(None, "UNSEEN")
            if status != "OK" or not search_data or not search_data[0]:
                mail.logout()
                return []

            unread_ids = search_data[0].split()
            # Fetch latest 10 unread if there are many
            recent_ids = unread_ids[-10:] if len(unread_ids) > 10 else unread_ids

            new_emails = []
            for num in recent_ids:
                num_str = num.decode() if isinstance(num, bytes) else str(num)
                if num_str in self.processed_ids:
                    continue

                res, data = mail.fetch(num, "(RFC822)")
                if res != "OK" or not data:
                    continue

                for part in data:
                    if isinstance(part, tuple):
                        msg = email.message_from_bytes(part[1])
                        subject = decode_str(msg.get("Subject", "No Subject"))
                        from_email = decode_str(msg.get("From", "unknown@example.com"))
                        date_header = decode_str(msg.get("Date", ""))
                        ts = time.time()
                        if date_header:
                            try:
                                ts = email.utils.parsedate_to_datetime(date_header).timestamp()
                            except Exception:
                                ts = time.time()

                        body = extract_body(msg)

                        new_emails.append({
                            "from_email": from_email,
                            "subject": subject,
                            "body": body,
                            "date": date_header,
                            "timestamp": ts
                        })
                        self.processed_ids.add(num_str)

                # Optionally mark as read
                if self.mark_read:
                    mail.store(num, "+FLAGS", "\\Seen")

            mail.logout()
            return new_emails
        except Exception as e:
            self.last_error = str(e)
            print(f"[GmailService] IMAP poll error: {e}")
            return []

    async def _poll_loop(self):
        """Asynchronous background loop polling IMAP inbox for new unread messages."""
        while self.is_polling:
            try:
                loop = asyncio.get_running_loop()
                new_emails = await loop.run_in_executor(None, self._fetch_unread_sync)
                self.last_poll_time = time.time()
                self.last_error = None

                if new_emails and self._callback:
                    for email_data in new_emails:
                        self.total_ingested += 1
                        await self._callback(email_data)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.last_error = str(e)
                print(f"[GmailService] Loop exception: {e}")

            await asyncio.sleep(self.poll_interval)

    async def start(
        self,
        username: str,
        app_password: str,
        interval: int = 15,
        mark_read: bool = True,
        callback: Optional[Callable] = None,
        import_recent: int = 10
    ) -> Dict[str, Any]:
        """Validates credentials, imports recent emails if requested, and starts background loop."""
        test_res = self.test_credentials(username, app_password)
        if not test_res["success"]:
            self.last_error = test_res["message"]
            return test_res

        self.email = username.strip()
        self.app_password = app_password.replace(" ", "").strip()
        self.poll_interval = max(5, interval)
        self.mark_read = mark_read
        self._callback = callback
        self.is_connected = True
        self.total_mailbox_count = test_res.get("total_messages", 0)
        self.last_error = None

        imported_count = 0
        # If user has existing emails, import the most recent ones immediately
        if import_recent > 0 and self._callback:
            loop = asyncio.get_running_loop()
            recent_emails = await loop.run_in_executor(None, lambda: self.fetch_recent_sync(import_recent))
            for item in recent_emails:
                try:
                    await self._callback(item)
                    self.total_ingested += 1
                    imported_count += 1
                except Exception as e:
                    print(f"[GmailService] Error dispatching initial recent email: {e}")

        if self._task and not self._task.done():
            self._task.cancel()

        self.is_polling = True
        self._task = asyncio.create_task(self._poll_loop())
        return {
            "success": True,
            "message": f"Connected to Gmail! Imported {imported_count} recent emails and started live monitor every {self.poll_interval}s.",
            "total_messages": self.total_mailbox_count,
            "imported_count": imported_count
        }

    async def stop(self):
        """Stops the background polling loop."""
        self.is_polling = False
        self.is_connected = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

    def get_status(self) -> Dict[str, Any]:
        """Returns the current status of Gmail integration."""
        return {
            "is_connected": self.is_connected,
            "is_polling": self.is_polling,
            "email": self.email,
            "poll_interval": self.poll_interval,
            "mark_read": self.mark_read,
            "last_poll_time": self.last_poll_time,
            "total_ingested": self.total_ingested,
            "last_error": self.last_error,
            "total_mailbox_count": self.total_mailbox_count
        }

    def send_email_sync(self, to_email: str, subject: str, body: str, in_reply_to: Optional[str] = None) -> Dict[str, Any]:
        """Sends an email synchronously via Gmail SMTP (smtp.gmail.com:465 SSL)."""
        if not self.email or not self.app_password:
            return {
                "success": False,
                "message": "Gmail is not connected. Please connect Gmail first via the header button."
            }

        clean_to = to_email.strip()
        # If to_email is in "Name <email@domain>" format, extract the actual email
        email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", clean_to)
        if email_match:
            clean_to = email_match.group(0)

        # Build clean Re: subject
        clean_subj = subject.strip()
        if not clean_subj.lower().startswith("re:"):
            clean_subj = f"Re: {clean_subj}"

        msg = MIMEText(body, "plain", "utf-8")
        msg["From"] = self.email
        msg["To"] = clean_to
        msg["Subject"] = clean_subj
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            msg["References"] = in_reply_to

        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as server:
                server.login(self.email, self.app_password)
                server.send_message(msg)
            return {
                "success": True,
                "message": f"Reply successfully sent to {clean_to} via your Gmail account!",
                "to": clean_to,
                "subject": clean_subj
            }
        except smtplib.SMTPAuthenticationError as e:
            return {"success": False, "message": f"SMTP Authentication failed: {str(e)}"}
        except Exception as e:
            return {"success": False, "message": f"Failed to send email: {str(e)}"}
