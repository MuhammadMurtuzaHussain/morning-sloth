"""Ask Gemma, running on the board, how much one email matters this morning.

The eval in ../../eval imports this module, so the prompt scored there is the
prompt the device runs.
"""
import json
import time
import urllib.request

LABELS = ["needs_today", "soon", "fyi", "noise"]

SYSTEM = """You sort one email for a person who sleeps late and does not want to touch their phone in the morning.
They live in Galway, Ireland, are job hunting in cybersecurity, and build hackathon projects.

Pick exactly one level:
- needs_today: they must act or know today. A bill or payment failing, a parcel arriving today, a recruiter asking them to do something, an event starting now, a security problem with their own accounts or code (leaked keys or secrets, a sign-in they did not make).
- soon: a real person wrote to them, or something they signed up for has a deadline in the next few days. Reply or act this week.
- fyi: true but no action needed. Receipts, application received, rejections, delivered parcels, confirmations, service alerts that usually fix themselves.
- noise: marketing, newsletters, job alert digests, social notifications, login codes, account verification links.

Do not trust words like "urgent" or "important" in the subject. Judge what it means for this person.
Answer with JSON only."""

SCHEMA = {
    "type": "object",
    "properties": {"label": {"type": "string", "enum": LABELS}},
    "required": ["label"],
}


def classify(email, base_url, timeout=600):
    """Return (label, seconds, timings). label is 'invalid' if Gemma's answer can't be read."""
    user = (f"Received: {email['received']} (Irish time)\n"
            f"From: {email['sender']}\nSubject: {email['subject']}\n"
            f"Preview: {email['snippet']}")
    body = {
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": user}],
        "temperature": 0,
        "max_tokens": 24,
        # Gemma 4 thinks by default and spends the token budget before answering
        "chat_template_kwargs": {"enable_thinking": False},
        "response_format": {"type": "json_schema", "json_schema": {"schema": SCHEMA}},
    }
    req = urllib.request.Request(f"{base_url}/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        resp = json.loads(r.read())
    seconds = time.time() - t0
    try:
        label = json.loads(resp["choices"][0]["message"]["content"])["label"]
    except Exception:
        label = "invalid"
    return label, seconds, resp.get("timings", {})
