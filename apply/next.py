"""Fill the next application from the local queue: one command, one form.

Usage:
    python next.py              # next lead in queue.json
    python next.py 3            # item number 3 from the printed list
    python next.py --list       # just show the queue

The form is filled and left open. Submit is yours to press.
"""

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
QUEUE_PATH = os.path.join(HERE, "queue.json")
APPLIED_PATH = os.path.join(HERE, "applied.json")
LETTER_PATH = os.path.join(HERE, "last_letter.txt")
QUEUE_MAX_AGE_H = 12

sys.path.insert(0, HERE)
import autofill  # noqa: E402


def load_queue():
    if not os.path.exists(QUEUE_PATH):
        return None
    try:
        return json.load(open(QUEUE_PATH, encoding="utf-8"))
    except Exception:
        return None


def refresh():
    print("Queue missing or stale, refreshing from the bot database...")
    import subprocess
    subprocess.run([sys.executable, os.path.join(HERE, "queue_build.py")], cwd=HERE)


def stale(payload):
    try:
        built = time.mktime(time.strptime(payload.get("built_at", ""), "%Y-%m-%d %H:%M"))
    except Exception:
        return True
    return (time.time() - built) / 3600.0 > QUEUE_MAX_AGE_H


def show(items):
    print()
    for i, it in enumerate(items, 1):
        print("%2d. fit %-4s %-22s %s" % (i, it.get("fit"), (it.get("source") or "")[:22],
                                          (it.get("title") or "")[:64]))
    print()


def main():
    args = [a for a in sys.argv[1:]]
    payload = load_queue()
    if payload is None or stale(payload):
        refresh()
        payload = load_queue()
    if not payload or not payload.get("items"):
        print("Nothing in the queue. Run: python queue_build.py")
        return 1
    items = payload["items"]
    if "--list" in args:
        show(items)
        return 0

    wanted = None
    for a in args:
        if a.isdigit():
            wanted = int(a)
    if wanted is None:
        wanted = 1
    if not 1 <= wanted <= len(items):
        show(items)
        print("Pick a number between 1 and %d." % len(items))
        return 1

    item = items[wanted - 1]
    url = item["url"]
    if autofill.is_applied(url):
        print("Already applied:", url)
        items.pop(wanted - 1)
        json.dump(payload, open(QUEUE_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        return 1

    letter = (item.get("letter") or "").strip()
    if letter:
        with open(LETTER_PATH, "w", encoding="utf-8") as f:
            f.write(letter + "\n")
        autofill.save_letter(url, letter)

    print()
    print("Job:   ", (item.get("title") or "")[:80])
    print("Source:", item.get("source"), "| fit:", item.get("fit"))
    print("URL:   ", url)
    print("Letter:", "%d chars" % len(letter) if letter else "none")
    profile = autofill.load_profile()
    cv_path, lane = autofill.pick_cv(profile, title=item.get("title", ""), url=url)
    print("CV:    ", lane, "->", os.path.basename(cv_path))
    print()

    result = autofill.run(url, profile, letter=letter, steps=0, cv_path=cv_path)
    print()
    print("Skipped:", ", ".join(result["skipped"][:10]) or "nothing")
    print()
    answer = input("Did you submit this application? [y/N/q] ").strip().lower()
    if answer == "q":
        print("Queue unchanged.")
        return 0
    if answer in ("y", "yes", "д", "да"):
        count = autofill.mark_applied(url, title=item.get("title", ""))
        items.pop(wanted - 1)
        json.dump(payload, open(QUEUE_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("Marked applied (%d total). Next in queue: %d left." % (count, len(items)))
    else:
        print("Not marked. It stays in the queue.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
