"""Read Gmail without changing it.

Every mailbox is opened with EXAMINE (read-only) and every fetch uses BODY.PEEK,
so nothing is marked as read, moved or deleted.
"""
import email
import email.utils
import imaplib
import re
from datetime import datetime, timedelta, timezone
from email.header import decode_header, make_header

import irishtime

HOST = "imap.gmail.com"


def _text(value):
    return str(make_header(decode_header(value or ""))).strip()


def _snippet(msg, limit=220):
    plain, html = None, None
    for part in msg.walk():
        kind = part.get_content_type()
        if kind not in ("text/plain", "text/html") or part.get_filename():
            continue
        try:
            text = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
        except Exception:
            continue
        if kind == "text/plain" and plain is None:
            plain = text
        elif kind == "text/html" and html is None:
            html = re.sub(r"<style.*?</style>|<[^>]+>", " ", text, flags=re.S)
    text = plain or html or ""
    return re.sub(r"\s+", " ", text).strip()[:limit]


class Gmail:
    def __init__(self, user, app_password):
        self.user, self.app_password = user, app_password

    def _connect(self):
        conn = imaplib.IMAP4_SSL(HOST)
        conn.login(self.user, self.app_password)
        return conn

    def unread_recent(self, days=1):
        """Unread inbox mail from the last `days` days, as dicts the triage step understands."""
        conn = self._connect()
        try:
            conn.select("INBOX", readonly=True)
            since = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
            _, data = conn.uid("search", None, "UNSEEN", "SINCE", since)
            out = []
            for uid in data[0].split():
                # Only the first 30 KB: enough for headers and a preview, never attachments
                _, parts = conn.uid("fetch", uid, "(BODY.PEEK[]<0.30000>)")
                raw = next((p[1] for p in parts if isinstance(p, tuple)), None)
                if raw is None:
                    continue
                msg = email.message_from_bytes(raw)
                when = email.utils.parsedate_to_datetime(msg["Date"]) if msg["Date"] else None
                if when is None or when.tzinfo is None:
                    when = datetime.now(timezone.utc)
                out.append({
                    "id": msg["Message-ID"] or f"uid-{uid.decode()}",
                    "received": irishtime.to_irish(when).strftime("%Y-%m-%dT%H:%M"),
                    "received_utc": when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M"),
                    "sender": email.utils.parseaddr(msg["From"] or "")[1].lower(),
                    "subject": _text(msg["Subject"]),
                    "snippet": _snippet(msg),
                })
            return out
        finally:
            conn.logout()

    def replied_to(self, last=400):
        """Addresses you have sent mail to, from the most recent `last` messages in Sent."""
        conn = self._connect()
        try:
            sent = self._sent_mailbox(conn)
            conn.select(sent, readonly=True)
            _, data = conn.uid("search", None, "ALL")
            uids = data[0].split()[-last:]
            people = set()
            if uids:
                _, parts = conn.uid("fetch", b",".join(uids), "(BODY.PEEK[HEADER.FIELDS (TO CC)])")
                for p in parts:
                    if isinstance(p, tuple):
                        msg = email.message_from_bytes(p[1])
                        for _, addr in email.utils.getaddresses(msg.get_all("To", []) + msg.get_all("Cc", [])):
                            if addr:
                                people.add(addr.lower())
            people.discard(self.user.lower())
            return people
        finally:
            conn.logout()

    @staticmethod
    def _sent_mailbox(conn):
        # The Sent folder's name depends on the account's language; its \Sent flag doesn't
        _, boxes = conn.list()
        for line in boxes:
            line = line.decode()
            if "\\Sent" in line:
                return line.split(' "/" ')[-1]
        return '"[Gmail]/Sent Mail"'
