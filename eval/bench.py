"""Score Gemma models on the board against hand labels for overnight email triage.

Runs each model in llama.cpp's server container, one at a time, and asks it to
sort every email into one of four levels. Output: per-model accuracy, the
emails it got wrong, and speed. Usage: python3 bench.py emails.jsonl results/ [model ...]
Pass the model name "device" to score the Gemma server the device itself runs.
"""
import json
import subprocess
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app" / "python"))
import triage  # noqa: E402  the prompt and request the device runs

MODELS = [
    "gemma-3-270m-it-Q8_0.gguf",
    "gemma-3-1b-it-Q4_K_M.gguf",
    "gemma-4-E2B-it-Q4_0.gguf",
]
IMAGE = "ghcr.io/ggml-org/llama.cpp:server"
PORT = 8089  # the device's own Gemma server keeps 8088
DEVICE_PORT = 8088
MODELS_DIR = Path.home() / "models"


def wait_healthy(limit=600):
    start = time.time()
    while time.time() - start < limit:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=5) as r:
                if r.status == 200:
                    return time.time() - start
        except Exception:
            pass
        time.sleep(2)
    raise RuntimeError("server never became healthy")


def start_server(model):
    subprocess.run(["docker", "rm", "-f", "sloth-bench"], capture_output=True)
    subprocess.run(
        ["docker", "run", "-d", "--name", "sloth-bench", "-p", f"{PORT}:8080",
         "-v", f"{MODELS_DIR}:/models:ro", IMAGE,
         "-m", f"/models/{model}", "-c", "1024", "-t", "4", "--jinja",
         "--reasoning-budget", "0",
         "--host", "0.0.0.0", "--port", "8080"],
        check=True, capture_output=True,
    )
    return wait_healthy()


def classify(email, port):
    label, wall, t = triage.classify(email, f"http://127.0.0.1:{port}")
    return label, wall, t.get("prompt_per_second"), t.get("predicted_per_second")


def main():
    emails = [json.loads(l) for l in Path(sys.argv[1]).read_text().splitlines() if l.strip()]
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {}
    for model in sys.argv[3:] or MODELS:
        # Two copies of Gemma 4 E2B don't fit in the board's memory, so "device"
        # reuses the server the app already runs instead of starting another
        device = model == "device"
        load_s = 0.0 if device else start_server(model)
        port = DEVICE_PORT if device else PORT
        rows = []
        for e in emails:
            label, wall, pps, tps = classify(e, port)
            rows.append({"id": e["id"], "want": e["label"], "got": label,
                         "ambiguous": e.get("ambiguous", False),
                         "wall_s": round(wall, 2), "prompt_tps": pps, "gen_tps": tps})
            print(f"{model} #{e['id']}: want={e['label']} got={label} {wall:.1f}s", flush=True)
        if not device:
            subprocess.run(["docker", "rm", "-f", "sloth-bench"], capture_output=True)

        scored = [r for r in rows if not r["ambiguous"]]
        correct = sum(r["want"] == r["got"] for r in scored)
        # The miss that matters: something that needs you today, sorted below "soon"
        missed_today = [r["id"] for r in scored
                        if r["want"] == "needs_today" and r["got"] not in ("needs_today", "soon")]
        false_alarms = [r["id"] for r in scored
                        if r["got"] == "needs_today" and r["want"] in ("fyi", "noise")]
        walls = sorted(r["wall_s"] for r in rows)
        summary[model] = {
            "load_s": round(load_s, 1),
            "accuracy": f"{correct}/{len(scored)}",
            "accuracy_pct": round(100 * correct / len(scored), 1),
            "missed_needs_today": missed_today,
            "false_alarms": false_alarms,
            "median_s_per_email": walls[len(walls) // 2],
            "total_s": round(sum(walls), 1),
            "median_prompt_tps": sorted(r["prompt_tps"] or 0 for r in rows)[len(rows) // 2],
            "confusion": Counter(f"{r['want']}->{r['got']}" for r in scored if r["want"] != r["got"]),
        }
        (out_dir / f"{model}.json").write_text(json.dumps(rows, indent=1))
        print(json.dumps({model: summary[model]}, indent=1), flush=True)
    (out_dir / f"summary-{int(time.time())}.json").write_text(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
