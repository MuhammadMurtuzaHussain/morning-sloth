"""Change the sloth's face on cue, by emailing yourself. Used by tools/demo.py.

Runs inside the app's container on the board, with the Gmail app password already
there, so nothing secret passes through your Mac:
  adb shell "docker exec -i morning-sloth-main-1 python3 - awake" < tools/trigger.py

  awake   "Webinar starting in 10 minutes": the starting-soon rule always wakes it
  peek    a friendly question from you to you; it counts as "someone you've written
          to" when your own address is in EXTRA_CONTACTS
  asleep  marks only these demo emails as read, so the sloth goes back to sleep
"""
import email.utils
import imaplib
import smtplib
import sys
from email.message import EmailMessage
from pathlib import Path

settings = dict(line.split("=", 1) for line in Path("/app/secrets.env").read_text().splitlines() if "=" in line)
user, password = settings["GMAIL_USER"], settings["GMAIL_APP_PASSWORD"]
MAILS = {
    "awake": ("Webinar starting in 10 minutes",
              "The Morning Sloth launch webinar is starting in 10 minutes. Join now."),
    "peek": ("Quick question for tomorrow",
             "Could you send me the slides before tomorrow's meeting? No rush tonight."),
}
face = sys.argv[1] if len(sys.argv) > 1 else ""

if face in MAILS:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = user, user, MAILS[face][0]
    msg["Date"] = email.utils.formatdate(localtime=False)
    msg.set_content(MAILS[face][1])
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(user, password)
        smtp.send_message(msg)
    print(f"sent '{MAILS[face][0]}'. The face changes in about 1 to 2 minutes.")
elif face == "asleep":
    conn = imaplib.IMAP4_SSL("imap.gmail.com")
    conn.login(user, password)
    conn.select("INBOX")
    marked = 0
    for subject, _ in MAILS.values():
        _, data = conn.uid("search", None, "UNSEEN", "FROM", user, "SUBJECT", f'"{subject}"')
        for uid in data[0].split():
            conn.uid("store", uid, "+FLAGS", "(\\Seen)")
            marked += 1
    conn.logout()
    print(f"marked {marked} demo email(s) read. Asleep within about a minute, if nothing else is unread.")
else:
    sys.exit("usage: awake | peek | asleep")
