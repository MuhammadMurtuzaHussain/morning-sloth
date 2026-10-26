#!/usr/bin/env python3
"""Run the sloth live for a demo: watch the AI work, and trigger each face on cue.

Runs on your computer and talks to the board over adb. Nothing secret leaves the board.

  python3 tools/demo.py watch          follow the sloth live: email in, Gemma's call, the rules, the face
  python3 tools/demo.py watch --full   the same, with full sender addresses (default shows the domain only)
  python3 tools/demo.py peek           email yourself the "one eye open" demo email
  python3 tools/demo.py awake          email yourself the "wide awake" demo email
  python3 tools/demo.py asleep         mark the demo emails read, so it goes back to sleep
  python3 tools/demo.py emails         print both demo emails to send yourself from your phone
"""
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from faces import FACES  # noqa: E402

APP = "~/ArduinoApps/morning-sloth"
CONTAINER = "morning-sloth-main-1"
EVENTS = f"{APP}/.state/events.jsonl"

BOLD, DIM, RESET = "\033[1m", "\033[2m", "\033[0m"
GREEN, YELLOW, RED, BLUE, GREY = "\033[92m", "\033[93m", "\033[91m", "\033[94m", "\033[90m"
FACE = {  # face name -> (what it means, colour, art key)
    "asleep": ("ASLEEP, nothing needs you", BLUE, "asleep"),
    "peek": ("ONE EYE OPEN, it can wait until the bus", YELLOW, "peek"),
    "awake": ("WIDE AWAKE, it needs you today", RED, "awake"),
}
LEVEL = {"needs_today": ("needs_today", RED), "soon": ("soon", YELLOW), "fyi": ("fyi", GREY),
         "noise": ("noise", GREY), "invalid": ("invalid", GREY)}
EMAILS = {
    "peek": ("Quick question for tomorrow",
             "Could you send me the slides before tomorrow's meeting? No rush tonight."),
    "awake": ("Webinar starting in 10 minutes",
              "The Morning Sloth launch webinar is starting in 10 minutes. Join now."),
}


def adb(*args, stdin=None):
    return subprocess.run(["adb", "shell", *args], stdin=stdin, capture_output=True, text=True)


def art(name):
    """The real matrix face, drawn with blocks (brighter pixel = brighter block)."""
    shades = " ·▒▓█"
    out = []
    for row in FACES[name]:
        cells = [shades[0 if c == "." else min(4, 1 + int(c) // 2)] * 2 for c in row]
        out.append("    " + "".join(cells))
    return "\n".join(out)


def level(name):
    text, colour = LEVEL.get(name, (name, GREY))
    return f"{colour}{BOLD}{text}{RESET}"


class Watcher:
    def __init__(self, full):
        self.full, self.waiting = full, None

    def who(self, sender):
        return sender if self.full or "@" not in sender else "…@" + sender.split("@", 1)[1]

    def say(self, at, icon, text):
        print(f"\r\033[K{GREY}{at}{RESET}  {icon}  {text}", flush=True)

    def tick(self, started):
        while self.waiting is started:
            print(f"\r\033[K{GREY}          …  Gemma is thinking on the board, {time.time() - started:.0f}s{RESET}",
                  end="", flush=True)
            time.sleep(1)

    def handle(self, ev):
        at, kind = ev["at"], ev["event"]
        if kind == "reading":
            self.say(at, "📬", f"new email  {BOLD}{ev['subject']}{RESET}  {GREY}from {self.who(ev['sender'])}{RESET}")
            self.waiting = started = time.time()
            threading.Thread(target=self.tick, args=(started,), daemon=True).start()
        elif kind == "judged":
            self.waiting = None
            self.say(at, "🧠", f"Gemma 4 says  {level(ev['model'])}  {GREY}({ev['seconds']:.0f}s, on the board){RESET}")
            if ev["final"] != ev["model"]:
                why = f"  {GREY}because {ev['rule']}{RESET}" if ev.get("rule") else ""
                self.say(at, "⚖️ ", f"code rules raise it to  {level(ev['final'])}{why}")
            else:
                self.say(at, "⚖️ ", f"code rules agree  {level(ev['final'])}")
        elif kind == "face":
            self.show_face(at, ev["face"])
        elif kind == "pass":
            self.say(at, "📭", f"{GREY}checked Gmail: {ev['unread']} unread, strongest {ev['strongest']}{RESET}")

    def show_face(self, at, face):
        meaning, colour, key = FACE[face]
        self.say(at, "🦥", f"{colour}{BOLD}FLAG → {face}{RESET}  {colour}{meaning}{RESET}")
        print(colour + art(key) + RESET + "\n", flush=True)


def watch(full):
    w = Watcher(full)
    print(f"{BOLD}🦥 Morning Sloth, live{RESET}  {GREY}Ctrl-C to stop{RESET}\n")
    recent = adb(f"tail -n 200 {EVENTS} 2>/dev/null").stdout.splitlines()
    faces = [json.loads(l)["face"] for l in recent if l.startswith("{") and '"event": "face"' in l]
    w.show_face(time.strftime("%H:%M:%S"), faces[-1] if faces else "asleep")
    proc = subprocess.Popen(["adb", "shell", f"tail -n 0 -F {EVENTS} 2>/dev/null"],
                            stdout=subprocess.PIPE, text=True)
    try:
        for line in proc.stdout:
            if line.startswith("{"):
                w.handle(json.loads(line))
    except KeyboardInterrupt:
        pass
    finally:
        proc.terminate()


def send(face):
    with open(HERE / "trigger.py") as script:
        r = adb(f"docker exec -i {CONTAINER} python3 - {face}", stdin=script)
    print((r.stdout + r.stderr).strip())
    return r.returncode


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "watch":
        watch("--full" in sys.argv)
    elif cmd in ("awake", "peek", "asleep"):
        sys.exit(send(cmd))
    elif cmd == "emails":
        for face, (subject, body) in EMAILS.items():
            print(f"{FACE[face][0]}\n  To:      your sloth Gmail address\n  Subject: {subject}\n  Body:    {body}\n")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
