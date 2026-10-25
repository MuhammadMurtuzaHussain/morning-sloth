"""Morning Sloth: decide which face the LED matrix shows.

Every few minutes: read unread Gmail (read-only), ask Gemma on the board how much
each new email matters, apply the code floors, and keep the strongest level among
mail you still haven't read. Read it on your phone and the sloth goes back to sleep.

Between BUS_FROM and BUS_TO the matrix also counts down to the next bus, from the
timetable in bus_timetable.json, corrected by the live feed when TFI_API_KEY is set.

Settings live in secrets.env next to app.yaml (never committed):
  GMAIL_USER, GMAIL_APP_PASSWORD, QUIET_FROM=00:30, WAKE_AT=07:00, POLL_MINUTES=5,
  BUS_FROM=09:00, BUS_TO=12:00, BUS_WALK_MINUTES=0, TFI_API_KEY, LIVE_MINUTES=2,
  EXTRA_CONTACTS=a@x.com,b@y.com (always count as people you've written to)
With no Gmail settings, it reads fake_inbox.jsonl instead, for testing.
"""
import json
import re
import struct
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from arduino.app_utils import App, Bridge

import bus
import glyphs
import irishtime
import live
from floors import ACCOUNT_SECURITY, apply_floor
from gmail import Gmail
from triage import classify

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / ".state"
FACE_FOR = {"needs_today": "awake", "soon": "peek", "fyi": "asleep", "noise": "asleep"}
RANK = {"noise": 0, "fyi": 1, "invalid": 1, "soon": 2, "needs_today": 3}

def load_settings():
    settings = {"QUIET_FROM": "00:30", "WAKE_AT": "07:00", "POLL_MINUTES": "5",
                "BUS_FROM": "09:00", "BUS_TO": "12:00", "BUS_WALK_MINUTES": "0", "LIVE_MINUTES": "2"}
    path = ROOT / "secrets.env"
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                settings[key.strip()] = value.strip()
    return settings


def gemma_url():
    # Gemma runs in its own container on the board, published on the host's port 8088.
    # From inside this app's container the host is the default gateway.
    for line in Path("/proc/net/route").read_text().splitlines()[1:]:
        fields = line.split()
        if fields[1] == "00000000":
            return f"http://{'.'.join(str(b) for b in struct.pack('<L', int(fields[2], 16)))}:8088"
    return "http://127.0.0.1:8088"


def between(now, start, end):
    hm = now.strftime("%H:%M")
    if start <= end:
        return start <= hm < end
    return hm >= start or hm < end


def setup_anchor(mail):
    """When Google confirmed the app password for this sloth, if that alert is in view."""
    times = [m["received_utc"] for m in mail if m.get("received_utc")
             and re.search(ACCOUNT_SECURITY, m["sender"].lower())
             and "morning sloth" in (m["subject"] + " " + m["snippet"]).lower()]
    return min(times) if times else None


class Sloth:
    def __init__(self):
        self.settings = load_settings()
        self.url = gemma_url()
        STATE_DIR.mkdir(exist_ok=True)
        # Gemma's own answer per email; the rules are applied fresh every pass,
        # so changing a rule never needs Gemma to read the mail again
        self.labels_path = STATE_DIR / "model_labels.json"
        self.labels = json.loads(self.labels_path.read_text()) if self.labels_path.exists() else {}
        self.setup_path = STATE_DIR / "setup.json"
        self.setup_at = json.loads(self.setup_path.read_text())["at"] if self.setup_path.exists() else None
        timetable = ROOT / "bus_timetable.json"
        self.timetable = bus.load(timetable) if timetable.exists() else None
        self.last_bus = "unset"
        # Live changes at our stop, and when they were fetched
        self.live, self.live_at, self.live_ok = None, 0, None
        self.level = "asleep"
        self.last_ok = time.time()
        self.replied_to, self.replied_at = frozenset(), 0
        user, password = self.settings.get("GMAIL_USER"), self.settings.get("GMAIL_APP_PASSWORD")
        self.gmail = Gmail(user, password) if user and password else None
        self.lock = threading.Lock()
        print(f"Gemma at {self.url}; reading {'Gmail as ' + user if self.gmail else 'fake_inbox.jsonl'}", flush=True)

    def unread(self):
        if self.gmail:
            return self.gmail.unread_recent()
        return [json.loads(l) for l in (ROOT / "fake_inbox.jsonl").read_text().splitlines() if l.strip()]

    def refresh_contacts(self):
        if time.time() - self.replied_at < 6 * 3600:
            return
        if self.gmail:
            self.replied_to = frozenset(self.gmail.replied_to())
        elif (ROOT / "contacts.json").exists():
            self.replied_to = frozenset(json.loads((ROOT / "contacts.json").read_text())["replied_to"])
        extra = {a.strip().lower() for a in self.settings.get("EXTRA_CONTACTS", "").split(",") if a.strip()}
        self.replied_to = frozenset(self.replied_to | extra)
        self.replied_at = time.time()
        print(f"{len(self.replied_to)} people you've written to", flush=True)

    def tick(self):
        self.refresh_contacts()
        mail = self.unread()
        with self.lock:
            self.last_ok = time.time()
        anchor = setup_anchor(mail)
        if anchor and anchor != self.setup_at:
            self.setup_at = anchor
            self.setup_path.write_text(json.dumps({"at": anchor}))
        setup_at = datetime.fromisoformat(self.setup_at).replace(tzinfo=timezone.utc) if self.setup_at else None
        final = {}
        for msg in mail:
            key = str(msg["id"])
            fresh = key not in self.labels
            if fresh:
                model, seconds, _ = classify(msg, self.url)
                self.labels[key] = model
                self.labels_path.write_text(json.dumps(self.labels))
            final[key] = apply_floor(msg, self.labels[key], self.replied_to, setup_at)
            if fresh:
                print(f"{seconds:5.1f}s {self.labels[key]:>11} -> {final[key]:<11} "
                      f"{msg['sender']} | {msg['subject'][:50]}", flush=True)
                # Each email takes Gemma half a minute, so wake as soon as one matters
                # instead of after the whole pass
                self.show(max(final.values(), key=RANK.get), raise_only=True)
        top = max(final.values(), key=RANK.get, default="noise")
        self.show(top)
        # Only mail that's still unread can change the face
        self.labels = {k: self.labels[k] for k in final}
        self.labels_path.write_text(json.dumps(self.labels))
        print(f"{len(mail)} unread, strongest: {top} -> {self.level}", flush=True)

    def show(self, label, raise_only=False):
        face = FACE_FOR.get(label, "asleep")
        order = ["asleep", "peek", "awake"]
        with self.lock:
            if not raise_only or order.index(face) > order.index(self.level):
                self.level = face
            self.last_ok = time.time()

    def run(self):
        while True:
            try:
                self.tick()
            except Exception:
                traceback.print_exc()
            time.sleep(60 * float(self.settings["POLL_MINUTES"]))

    def bus_time(self):
        now = irishtime.now()
        return (not between(now, self.settings["QUIET_FROM"], self.settings["WAKE_AT"])
                and between(now, self.settings["BUS_FROM"], self.settings["BUS_TO"]))

    def run_live(self):
        key = self.settings.get("TFI_API_KEY")
        if not key or self.timetable is None:
            return
        tt = self.timetable
        stop, routes, sequences = tt["stop_id"], set(tt.get("route_ids", [])), bus.sequences(tt)
        while True:
            if self.bus_time():
                try:
                    changes = live.at_stop(live.fetch(key), stop, routes, sequences)
                    with self.lock:
                        self.live, self.live_at = changes, time.time()
                    if self.live_ok is not True:
                        print("bus: live times on", flush=True)
                    self.live_ok = True
                except Exception as e:
                    # Never print the request itself: its headers carry the key
                    if self.live_ok is not False:
                        print(f"bus: live feed unavailable ({type(e).__name__}), using the timetable", flush=True)
                    self.live_ok = False
            time.sleep(60 * float(self.settings["LIVE_MINUTES"]))

    def state(self):
        with self.lock:
            if between(irishtime.now(), self.settings["QUIET_FROM"], self.settings["WAKE_AT"]):
                return "off"
            if time.time() - self.last_ok > 30 * 60:
                return "lost"
            return self.level

    def bus_frame(self):
        """A countdown frame while it's bus time, otherwise an empty string."""
        if self.timetable is None or not self.bus_time():
            return ""
        with self.lock:
            changes = self.live if time.time() - self.live_at < 10 * 60 else None
        minutes = bus.minutes_to_leave(self.timetable, irishtime.now(),
                                       int(self.settings["BUS_WALK_MINUTES"]), changes)
        if (minutes, changes is not None) != self.last_bus:
            self.last_bus = (minutes, changes is not None)
            source = "live" if changes is not None else "timetable"
            print(f"bus: {'no more buses today' if minutes is None else f'leave in {minutes} min'} ({source})",
                  flush=True)
        return glyphs.countdown(minutes, changes is not None) if minutes is not None else ""


if __name__ == "__main__":
    sloth = Sloth()
    Bridge.provide("get_state", sloth.state)
    Bridge.provide("get_bus", sloth.bus_frame)
    threading.Thread(target=sloth.run, daemon=True).start()
    threading.Thread(target=sloth.run_live, daemon=True).start()
    App.run()
