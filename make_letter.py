"""Generate a tailored letter and answers for any job URL, on demand.

Usage (on the VPS, inside /root/LeadHunter):
    ./venv/bin/python make_letter.py <url>
    ./venv/bin/python make_letter.py <url> --json

Prints the letter to stdout (or JSON with letter/answers). Saves the kit so a
second run is instant. Never submits anything.
"""
import contextlib
import json
import re
import sqlite3
import sys

import lead_hunter_pro as H


def from_greenhouse(url):
    m = re.search(r"greenhouse\.io/([^/]+)/jobs/(\d+)", url)
    if not m:
        return None
    board, job_id = m.group(1), m.group(2)
    raw = H.fetch_url("https://boards-api.greenhouse.io/v1/boards/%s/jobs/%s" % (board, job_id))
    if not raw:
        return None
    d = json.loads(raw)
    desc = re.sub(r"<[^>]+>", " ", H.html.unescape(d.get("content") or ""))
    return {"title": (d.get("title") or "")[:200], "description": re.sub(r"\s+", " ", desc).strip()[:6000],
            "url": url, "source": "Greenhouse " + board}


def from_lever(url):
    m = re.search(r"jobs\.lever\.co/([^/]+)/([0-9a-f-]{8,})", url)
    if not m:
        return None
    site, pid = m.group(1), m.group(2)
    raw = H.fetch_url("https://api.lever.co/v0/postings/%s/%s" % (site, pid))
    if not raw:
        return None
    d = json.loads(raw)
    desc = str(d.get("descriptionPlain") or d.get("description") or "")
    return {"title": (d.get("text") or "")[:200], "description": re.sub(r"\s+", " ", desc)[:6000],
            "url": url, "source": "Lever " + site}


def from_ashby(url):
    m = re.search(r"ashbyhq\.com/([^/]+)/", url)
    if not m:
        return None
    board = m.group(1)
    raw = H.fetch_url("https://api.ashbyhq.com/posting-api/job-board/%s" % board)
    if not raw:
        return None
    for job in json.loads(raw).get("jobs", []):
        if (job.get("jobUrl") or "") == url or url.rstrip("/") == (job.get("jobUrl") or "").rstrip("/"):
            desc = str(job.get("descriptionPlain") or job.get("descriptionHtml") or "")
            return {"title": (job.get("title") or "")[:200],
                    "description": re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", desc))[:6000],
                    "url": url, "source": "Ashby " + board}
    return None


def from_page(url):
    raw = H.fetch_url(url)
    if not raw:
        return None
    title = ""
    m = re.search(r"<title[^>]*>(.*?)</title>", raw, re.S | re.I)
    if m:
        title = re.sub(r"\s+", " ", H.html.unescape(m.group(1))).strip()
    title = re.sub(r"^(Job Application for\s+|Apply for\s+)", "", title)
    title = re.sub(r"\s+(at|@)\s+.*$", "", title)[:200]
    body = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
    text = re.sub(r"<[^>]+>", " ", H.html.unescape(body))
    return {"title": title or url, "description": re.sub(r"\s+", " ", text)[:6000],
            "url": url, "source": "page"}


def fetch_lead(url):
    for fn in (from_greenhouse, from_lever, from_ashby, from_page):
        try:
            lead = fn(url)
        except Exception:
            lead = None
        if lead and lead.get("description") and len(lead["description"]) > 200:
            return lead
    return None


def main():
    if len(sys.argv) < 2:
        print("usage: make_letter.py <url> [--json]", file=sys.stderr)
        return 2
    url = sys.argv[1]
    as_json = "--json" in sys.argv[2:]

    conn = sqlite3.connect(H.DB_PATH)
    row = conn.execute("SELECT letter FROM kits WHERE url = ?", (url,)).fetchone()
    if row and row[0]:
        letter, answers = row[0], ""
        if as_json:
            print(json.dumps({"letter": letter, "cached": True}, ensure_ascii=False))
        else:
            print(letter)
        conn.close()
        return 0

    lead = fetch_lead(url)
    if not lead:
        print("could not read the job page", file=sys.stderr)
        return 1

    print("job: " + lead["title"][:80], file=sys.stderr)
    # the bot prints LLM warnings to stdout, keep them out of the letter
    with contextlib.redirect_stdout(sys.stderr):
        kit = H.build_application_kit(lead, email=H.OWNER_EMAIL or None)
    letter = (kit.get("letter") or "").strip()
    answers = kit.get("answers") or {}
    if not letter:
        print("letter generation failed", file=sys.stderr)
        conn.close()
        return 1

    try:
        conn.execute(
            "INSERT OR REPLACE INTO kits (url, letter, answers, audit) VALUES (?, ?, ?, ?)",
            (url, letter, json.dumps(answers, ensure_ascii=False),
             json.dumps({"ok": kit.get("audit_ok"), "problems": kit.get("audit_problems") or []},
                        ensure_ascii=False)),
        )
        conn.commit()
    except Exception as e:
        print("kit not saved: " + str(e)[:80], file=sys.stderr)
    conn.close()

    if as_json:
        print(json.dumps({"letter": letter, "answers": answers,
                          "audit_ok": kit.get("audit_ok"),
                          "audit_problems": kit.get("audit_problems") or [],
                          "title": lead["title"], "source": lead["source"]}, ensure_ascii=False))
    else:
        print(letter)
    return 0


if __name__ == "__main__":
    sys.exit(main())
