"""Build a local application queue from the bot's database on the VPS.

Read-only: no writes to the VPS, no Telegram, no LLM calls.

Usage:
    python queue.py            # refresh queue.json (default 25 items)
    python queue.py 40         # refresh with 40 items
"""

import json
import os
import shlex
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
QUEUE_PATH = os.path.join(HERE, "queue.json")
APPLIED_PATH = os.path.join(HERE, "applied.json")
SKIPPED_PATH = os.path.join(HERE, "skipped.json")

REMOTE = r"""
import json, sqlite3
LIMIT = {limit}
c = sqlite3.connect("file:leads.db?mode=ro", uri=True)
rows = c.execute(
    "SELECT l.url, l.title, l.source, l.fit, k.letter "
    "FROM leads l JOIN kits k ON k.url = l.url "
    "WHERE k.letter IS NOT NULL AND length(k.letter) > 200 "
    "ORDER BY COALESCE(l.fit, 0) DESC, l.id DESC LIMIT ?", (LIMIT,)
).fetchall()
print(json.dumps([
    {{"url": r[0], "title": r[1], "source": r[2], "fit": r[3], "letter": r[4]}}
    for r in rows if r[0]
], ensure_ascii=False))
"""


def load_profile():
    with open(os.path.join(HERE, "profile.json"), encoding="utf-8") as f:
        return json.load(f)


def applied_keys():
    if not os.path.exists(APPLIED_PATH):
        return set()
    try:
        return set(json.load(open(APPLIED_PATH, encoding="utf-8")).keys())
    except Exception:
        return set()


BLOCKED_HOSTS = ("upwork.com", "freelancer.com", "linkedin.com", "fiverr.com",
                 "peopleperhour.com", "toptal.com", "guru.com", "codeable.io", "workana.com")
ATS_HOSTS = ("greenhouse.io", "lever.co", "ashbyhq.com", "workable.com", "recruitee.com",
             "teamtailor.com", "smartrecruiters.com", "jobvite.com", "breezy.hr", "himail")


def classify(url):
    u = (url or "").lower()
    if any(h in u for h in BLOCKED_HOSTS):
        return "blocked"
    if any(h in u for h in ATS_HOSTS):
        return "ats"
    return "other"


def skipped_keys():
    if not os.path.exists(SKIPPED_PATH):
        return set()
    try:
        return set(json.load(open(SKIPPED_PATH, encoding="utf-8")).keys())
    except Exception:
        return set()


def url_key(url):
    import hashlib
    return hashlib.sha1(url.strip().encode("utf-8")).hexdigest()[:16]


def fetch(limit, profile):
    script = REMOTE.format(limit=int(limit))
    key = profile.get("ssh_key") or os.path.expanduser("~/.ssh/vps_opencode")
    host = profile.get("vps") or "root@193.233.19.171"
    ssh_bin = shutil.which("ssh") or r"C:\Windows\System32\OpenSSH\ssh.exe"
    cmd = [
        ssh_bin, "-i", key,
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "ConnectTimeout=12",
        host,
        "cd /root/LeadHunter && ./venv/bin/python -c " + shlex.quote(script),
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    if out.returncode != 0:
        print("SSH failed rc=%s: %s" % (out.returncode, (out.stderr or "").strip()[:200]))
        return None
    body = (out.stdout or "").strip()
    if not body:
        print("Empty response from VPS.")
        return None
    try:
        return json.loads(body)
    except Exception as e:
        print("Bad JSON from VPS:", str(e)[:120])
        return None


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 25
    profile = load_profile()
    print("Fetching up to %d leads from the bot database..." % limit)
    items = fetch(limit, profile)
    if items is None:
        if os.path.exists(QUEUE_PATH):
            print("Keeping the existing queue.json.")
        return 1
    done = applied_keys() | skipped_keys()
    fresh = []
    for it in items:
        if url_key(it["url"]) in done:
            continue
        it["ats"] = classify(it["url"])
        fresh.append(it)
    fresh.sort(key=lambda x: (x["ats"] == "blocked", -(x.get("fit") or 0)))
    payload = {"built_at": time.strftime("%Y-%m-%d %H:%M"), "items": fresh}
    with open(QUEUE_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    blocked = sum(1 for x in fresh if x["ats"] == "blocked")
    print("Queue: %d new of %d (skipped %d applied or dropped, %d blocked platforms)"
          % (len(fresh), len(items), len(items) - len(fresh), blocked))
    for i, it in enumerate(fresh[:10], 1):
        print("  %2d. fit %-4s %s" % (i, it.get("fit"), (it.get("title") or "")[:70]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
