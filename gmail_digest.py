"""Lightweight Gmail digest: read new mail, LLM-classify, send Telegram summary.
Handles LinkedIn jobs, ProductHunt launches, alerts, and general email.
Reads config from .env. Does not mark emails as read."""
import imaplib
import email
import json
import os
import re
import html
from email.header import decode_header
from datetime import datetime, timedelta

from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, ".env"))

GMAIL_USER = os.getenv("GMAIL_USER", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")
OWNER_CHAT_ID = os.getenv("OWNER_CHAT_ID", "")
OR_KEY = os.getenv("OPENROUTER_API_KEY", "")

STATE_FILE = os.path.join(HERE, "gmail_seen.json")
LOOKBACK_DAYS = 3
MAX_EMAILS = 40
BACKFILL_MAX = 600

PROFILE_KEYWORDS = (
    "n8n", "make.com", "zapier", "automation", "workflow", "ai agent", "llm",
    "chatbot", "telegram", "integration", "api", "scraping", "data pipeline",
    "trading", "treasury", "payments", "fintech", "compliance", "risk",
    "operations", "reconciliation", "settlement", "financial analyst",
    "quant", "broker", "algo", "bot",
)

IMPORTANT_CATS = {"ProductHunt", "LinkedIn", "Alert_or_Critical", "Client_or_Partner", "Job_or_Contract"}


def parse_args():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--since", help="Process mail from this date (YYYY-MM-DD)")
    return p.parse_args()


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            return json.load(open(STATE_FILE))
        except Exception:
            pass
    return {"uids": []}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def decode(s):
    if not s:
        return ""
    try:
        parts = decode_header(s)
        return "".join(
            t.decode(c or "utf-8", "replace") if isinstance(t, bytes) else t
            for t, c in parts
        )
    except Exception:
        return str(s)


def parse_from(frm):
    """Extract name and email from a From header."""
    frm = (frm or "").strip()
    m = re.search(r"([^<>\s]+@[^<>\s]+)", frm)
    addr = m.group(1) if m else ""
    name = re.sub(r"\s*<.*>", "", frm).strip(" \"").strip() if frm else ""
    if not name and addr:
        name = addr.split("@")[0]
    return name, addr


def fetch_new(imap, since_date):
    status, data = imap.uid("search", None, f'(SINCE "{since_date}")')
    if status != "OK":
        return []
    uids = data[0].split()
    out = []
    for uid in uids:
        uid = uid.decode()
        typ, msg_data = imap.uid("fetch", uid, "(BODY.PEEK[HEADER])")
        if typ != "OK" or not msg_data or msg_data[0] is None:
            continue
        raw = msg_data[0][1] if isinstance(msg_data[0], tuple) else None
        if not raw:
            continue
        try:
            msg = email.message_from_bytes(raw)
        except Exception:
            continue
        subject = decode(msg.get("Subject", "")).strip() or "(без темы)"
        name, addr = parse_from(decode(msg.get("From", "")))
        if not addr:
            addr = "(без адреса)"
        dt = None
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(msg.get("Date", "") or "")
            if dt and dt.tzinfo is None:
                dt = dt.replace(tzinfo=__import__("datetime").timezone.utc)
        except Exception:
            dt = None
        out.append({"uid": uid, "name": name or "?", "addr": addr,
                    "subject": subject[:140], "raw": raw, "date": dt})
    return out[:MAX_EMAILS if since_date else MAX_EMAILS]


def get_snippet(raw):
    try:
        msg = email.message_from_bytes(raw)
    except Exception:
        return ""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                b = part.get_payload(decode=True)
                if b:
                    body = b.decode(part.get_content_charset() or "utf-8", "replace")
                    break
            elif part.get_content_type() == "text/html" and not body:
                b = part.get_payload(decode=True)
                if b:
                    body = re.sub(r"<[^>]+>", " ", b.decode(part.get_content_charset() or "utf-8", "replace"))
    else:
        b = msg.get_payload(decode=True)
        if b:
            body = b.decode(msg.get_content_charset() or "utf-8", "replace")
    return re.sub(r"\s+", " ", body or "").strip()


def classify(emails, or_key):
    if not emails:
        return []
    from openai import OpenAI
    client = OpenAI(api_key=or_key, base_url="https://openrouter.ai/api/v1")
    system = (
        "You process emails from a founder's inbox. Return ONLY a valid JSON array, one object per email, with fields:\n"
        "- index: int\n"
        "- category: one of ProductHunt | LinkedIn | Client_or_Partner | Job_or_Contract | Alert_or_Critical | Newsletter | Other\n"
        "- importance: high | low\n"
        "- summary: one short line (max 12 words)\n"
        "- action: read | reply | skip\n"
        "- jobs: array of job titles (only for LinkedIn job-recommendation emails; otherwise [])\n"
        "- launches: array of 'Product name - one line' (only for ProductHunt emails; otherwise [])\n"
        "- change: one short string describing what changed (only for Alert_or_Critical: payment, price, plan, terms, security, account, delivery; otherwise \"\")\n"
        "Rules: Alert_or_Critical = payment failures, price/plan/terms changes, security alerts, account changes, delivery issues. "
        "Client_or_Partner/Job_or_Contract that could lead to work or deals are high importance. "
        "ProductHunt and LinkedIn notifications are informational. Do NOT invent facts not present in the email."
    )
    result = []
    batch = 20
    for start in range(0, len(emails), batch):
        part = emails[start:start + batch]
        lines = []
        for j, e in enumerate(part, 1):
            lines.append(f"{start + j}. From: {e['name']} <{e['addr']}> | Subject: {e['subject']} | Snippet: {get_snippet(e['raw'])[:350]}")
        try:
            resp = client.chat.completions.create(
                model="deepseek/deepseek-chat",
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": "\n".join(lines)}],
                temperature=0.1, max_tokens=1600, timeout=90,
            )
            raw = resp.choices[0].message.content or ""
            m = re.search(r"\[.*\]", raw, re.S)
            if m:
                result.extend(json.loads(m.group(0)))
        except Exception as e:
            print(f"[GMAIL] classify batch failed ({start}): {e}")
        print(f"[GMAIL] classified {min(start + batch, len(emails))}/{len(emails)}")
    return result


def profile_match(title):
    t = (title or "").lower()
    return any(k in t for k in PROFILE_KEYWORDS)


def send_tg(text):
    if not TG_BOT_TOKEN or not OWNER_CHAT_ID:
        return
    import requests
    requests.post(
        f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
        json={"chat_id": OWNER_CHAT_ID, "text": text[:4000], "parse_mode": "HTML"},
        timeout=15,
    )


def esc(s):
    return html.escape(str(s or ""))


def main():
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        print("[GMAIL] missing GMAIL_USER/GMAIL_APP_PASSWORD")
        return
    args = parse_args()
    global MAX_EMAILS
    if args.since:
        try:
            since_dt = datetime.strptime(args.since, "%Y-%m-%d")
        except ValueError:
            print(f"[GMAIL] bad --since: {args.since} (use YYYY-MM-DD)")
            return
        since_date = since_dt.strftime("%d-%b-%Y")
        MAX_EMAILS = BACKFILL_MAX
        print(f"[GMAIL] backfill from {args.since}")
    else:
        since_date = (datetime.now() - timedelta(days=LOOKBACK_DAYS)).strftime("%d-%b-%Y")
    state = load_state()
    seen = set(state["uids"])
    try:
        imap = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        imap.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        imap.select("INBOX")
        emails = fetch_new(imap, since_date)
        imap.logout()
    except Exception as e:
        print(f"[GMAIL] imap error: {e}")
        return

    fresh = [e for e in emails if e["uid"] not in seen]
    if not fresh:
        print("[GMAIL] no new emails")
        return
    print(f"[GMAIL] new emails: {len(fresh)}")
    tags = classify(fresh, OR_KEY)
    by_idx = {t.get("index"): t for t in tags if isinstance(t, dict)}

    alerts = []
    launches = []
    linkedin = []
    important = []
    skipped = 0
    for i, e in enumerate(fresh, 1):
        t = by_idx.get(i, {})
        cat = t.get("category", "Other")
        summary = t.get("summary", "")
        action = t.get("action", "skip")
        sender = f"{e['name']} <{e['addr']}>" if e.get("name") else esc(e["addr"])
        dstr = ""
        if e.get("date"):
            try:
                dstr = e["date"].astimezone().strftime("%d.%m %H:%M")
            except Exception:
                dstr = ""
        item = {
            "sender": esc(sender), "subject": esc(e["subject"][:90]),
            "snippet": esc(get_snippet(e["raw"])[:110]),
            "summary": esc(summary), "action": action,
            "importance": t.get("importance", "low"),
            "change": esc(t.get("change", "")),
            "category": cat, "date": esc(dstr),
        }
        if cat == "Alert_or_Critical" or item["change"]:
            alerts.append(item)
        elif cat == "ProductHunt":
            for ln in (t.get("launches", []) or []):
                launches.append({"line": esc(ln), "date": item["date"]})
        elif cat == "LinkedIn":
            for j in (t.get("jobs", []) or []):
                linkedin.append({"title": esc(j), "match": profile_match(j), "date": item["date"]})
            if not t.get("jobs"):
                important.append(item)
        elif cat in ("Client_or_Partner", "Job_or_Contract"):
            important.append(item)
        else:
            skipped += 1

    blocks = []
    if alerts:
        b = "🔴 <b>АЛЕРТЫ / КРИТИЧНОЕ</b>"
        for a in alerts[:20]:
            b += email_line(a)
            if a.get("change"):
                b += f"\n   ⚠️ {a['change']}"
        if len(alerts) > 20:
            b += f"\n… ещё {len(alerts) - 20}"
        blocks.append(b)

    if launches:
        b = "🚀 <b>PRODUCTHUNT</b>"
        for l in launches[:15]:
            d = f" [{l['date']}]" if l.get("date") else ""
            b += f"\n• {l['line']}{d}"
        if len(launches) > 15:
            b += f"\n… ещё {len(launches) - 15}"
        blocks.append(b)

    if linkedin:
        b = "💼 <b>LINKEDIN / ВАКАНСИИ</b>"
        for j in linkedin[:20]:
            mark = "🔥" if j["match"] else "⏭"
            d = f" [{j['date']}]" if j.get("date") else ""
            b += f"\n• {mark} {j['title']}{d}"
        if len(linkedin) > 20:
            b += f"\n… ещё {len(linkedin) - 20}"
        blocks.append(b)

    if important:
        b = "⭐ <b>ВАЖНОЕ</b>"
        for r in important[:15]:
            b += email_line(r)
        if len(important) > 15:
            b += f"\n… ещё {len(important) - 15}"
        blocks.append(b)

    if not blocks:
        print("[GMAIL] nothing important")
        skipped = len(fresh)
    msg = f"📬 <b>Gmail</b> · {len(fresh)} новых"
    if skipped:
        msg += f"\nℹ️ Пропущено: {skipped}"
    msg += "\n\n" + "\n\n".join(blocks)
    send_tg(msg)

    for e in fresh:
        seen.add(e["uid"])
    state["uids"] = sorted(seen)[-2000:]
    save_state(state)
    print(f"[GMAIL] sent digest for {len(fresh)} emails")


def email_line(item):
    line = f"\n▸ <b>{item['sender']}</b> — {item['subject']}"
    if item.get("date"):
        line += f"\n   🕐 {item['date']}"
    if item.get("snippet"):
        line += f"\n   📄 {item['snippet']}"
    if item.get("summary"):
        line += f"\n   💬 {item['summary']}"
    act = {"reply": "➡️ ответить", "read": "➡️ почитать", "skip": "⏭"}.get(item.get("action", ""), "")
    if act:
        line += f"\n   {act}"
    return line


if __name__ == "__main__":
    main()
