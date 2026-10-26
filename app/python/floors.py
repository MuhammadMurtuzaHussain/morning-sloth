"""Code guarantees on top of Gemma's label: a floor the model can raise but never lower,
and one ceiling, for the security alerts that setting up the sloth itself sets off.

Kept deliberately narrow. A broader "a real person wrote" rule caught more but
woke the sloth for 14 emails it shouldn't have, so it was dropped in favour of
"someone you have written to before", taken from Sent mail.
"""
import re
from datetime import datetime, timedelta, timezone

RANK = {"noise": 0, "fyi": 1, "soon": 2, "needs_today": 3}
LEVEL = {v: k for k, v in RANK.items()}

BILLS = r"prepaypower|electricireland|bordgais|energia|revenue\.ie|aib\.ie|boi\.com|revolut"
PAYMENT_FAILED = r"fail|unsuccessful|declined|overdue|unable to charge"
CARRIERS = r"anpost|fedex|dpd|dhl|gls|ups\.com"
DELIVERY_TODAY = r"out for delivery today|deliver[a-z ]{0,20} today"
STARTING_NOW = r"starting in \d+ minutes|we are now live"
# Shared mailboxes you may have written to once but that mostly send bulk mail
ROLE_ADDRESS = r"^(no-?reply|notifications?|hi|hello|info|support|team|yo|accounting|hacktoberfest|devrel)@|unsubscribe"
# Connecting the sloth means turning on 2-Step Verification and creating an app
# password, and Google emails a security alert for each step
ACCOUNT_SECURITY = r"@accounts\.google\.com$"
SETUP_WINDOW = (timedelta(minutes=60), timedelta(minutes=15))


def explain(email, replied_to=frozenset()):
    """(level, reason) from the code rules alone; reason is empty when no rule fired."""
    text = (email["subject"] + " " + email["snippet"]).lower()
    sender = email["sender"].lower()
    level, why = "noise", ""
    if sender in replied_to and not re.search(ROLE_ADDRESS, sender):
        level, why = "soon", "from someone you have written to"
    if re.search(BILLS, sender) and re.search(PAYMENT_FAILED, text):
        level, why = "needs_today", "a bill or payment failed"
    if re.search(CARRIERS, sender) and re.search(DELIVERY_TODAY, text):
        level, why = "needs_today", "a parcel is arriving today"
    if re.search(STARTING_NOW, text):
        level, why = "needs_today", "an event is starting now"
    return level, why


def floor(email, replied_to=frozenset()):
    return explain(email, replied_to)[0]


def from_setup(email, setup_at):
    """A Google security alert about connecting this sloth, not about an intruder."""
    if not re.search(ACCOUNT_SECURITY, email["sender"].lower()):
        return False
    if "morning sloth" in (email["subject"] + " " + email["snippet"]).lower():
        return True
    if setup_at is None or not email.get("received_utc"):
        return False
    received = datetime.fromisoformat(email["received_utc"]).replace(tzinfo=timezone.utc)
    before, after = SETUP_WINDOW
    return setup_at - before <= received <= setup_at + after


def apply_floor(email, model_label, replied_to=frozenset(), setup_at=None):
    level = LEVEL[max(RANK.get(model_label, RANK["fyi"]), RANK[floor(email, replied_to)])]
    if from_setup(email, setup_at):
        level = LEVEL[min(RANK[level], RANK["fyi"])]
    return level
