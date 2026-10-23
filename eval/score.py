"""Score saved model answers against hand labels, with and without the code floors.

Usage: python3 score.py data/emails.jsonl results/gemma-4-E2B-it-Q4_0.gguf.json [data/contacts.json]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app" / "python"))
from floors import apply_floor  # noqa: E402

QUIET = ("fyi", "noise")


def score(rows, emails, label_of):
    scored = [r for r in rows if not r["ambiguous"]]
    got = {r["id"]: label_of(r) for r in rows}
    n = len(scored)
    exact = sum(r["want"] == got[r["id"]] for r in scored)
    wake = sum((r["want"] in QUIET) == (got[r["id"]] in QUIET) for r in scored)
    today = [r for r in scored if r["want"] == "needs_today"]
    caught = sum(got[r["id"]] == "needs_today" for r in today)
    false_wakes = [r["id"] for r in scored if r["want"] in QUIET and got[r["id"]] not in QUIET]
    missed = [r["id"] for r in scored if r["want"] not in QUIET and got[r["id"]] in QUIET]
    print(f"  exact {exact}/{n} ({100 * exact / n:.0f}%), wake-vs-quiet {wake}/{n} ({100 * wake / n:.0f}%), "
          f"needs_today caught {caught}/{len(today)}")
    for label, ids in (("false wakes", false_wakes), ("missed", missed)):
        for i in ids:
            print(f"    {label}: #{i} {emails[i]['sender']} | {emails[i]['subject'][:60]} -> {got[i]}")


def main():
    emails = {e["id"]: e for e in map(json.loads, Path(sys.argv[1]).read_text().splitlines()) if e}
    rows = json.loads(Path(sys.argv[2]).read_text())
    replied = frozenset(json.loads(Path(sys.argv[3]).read_text())["replied_to"]) if len(sys.argv) > 3 else frozenset()
    print("Gemma alone")
    score(rows, emails, lambda r: r["got"])
    print("Gemma + rules (bills, deliveries today, starting now)")
    score(rows, emails, lambda r: apply_floor(emails[r["id"]], r["got"]))
    if replied:
        print(f"Gemma + rules + people you've written to ({len(replied)} addresses)")
        score(rows, emails, lambda r: apply_floor(emails[r["id"]], r["got"], replied))


if __name__ == "__main__":
    main()
