import os
import re
import json
import csv
import sqlite3
import argparse
import time
import html
import asyncio
from datetime import datetime
from io import StringIO

import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError:
    pass

import requests
from openai import OpenAI
from telethon import TelegramClient

GROQ_KEY = os.getenv("GROQ_API_KEY")
OR_KEY = os.getenv("OPENROUTER_API_KEY")

groq_client = OpenAI(api_key=GROQ_KEY, base_url="https://api.groq.com/openai/v1") if GROQ_KEY else None
or_client = OpenAI(api_key=OR_KEY, base_url="https://openrouter.ai/api/v1") if OR_KEY else None

TG_API_ID = int(os.getenv("TG_API_ID", "0"))
TG_API_HASH = os.getenv("TG_API_HASH", "")
TG_SESSION = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lead_hunter.session")

KEYWORDS = [
    "n8n", "python", "scraping", "scraper", "automation", "workflow",
    "freelance", "remote", "contract", "bot", "API", "api",
    "chatbot", "llm", "ai agent", "gpt", "telegram bot",
    "founding engineer", "consultant", "integration", "webhook",
    "zapier", "make", "low-code", "no-code", "RPA", "selenium",
    "beautifulsoup", "crawler", "parser", "data extraction"
]

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "leads.db")
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)

TELEGRAM_SOURCES = [
    {"name": "freelance_ai", "url": "https://t.me/freelance_ai"},
    {"name": "frelanser", "url": "https://t.me/frelanser"},
    {"name": "upwork_talents", "url": "https://t.me/upwork_talents"},
    {"name": "freelance_llm", "url": "https://t.me/freelance_llm"},
    {"name": "python_jobs", "url": "https://t.me/python_jobs"},
    {"name": "ai_automation_gigs", "url": "https://t.me/ai_automation_gigs"},
    {"name": "n8n_community", "url": "https://t.me/n8n_community"},
    {"name": "workflow_gigs", "url": "https://t.me/workflow_gigs"},
    {"name": "remote_jobs_ai", "url": "https://t.me/remote_jobs_ai"},
]


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            source TEXT,
            url TEXT UNIQUE,
            score REAL,
            type TEXT,
            urgency TEXT,
            budget TEXT,
            matched_aspects TEXT,
            reason TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    return conn


def fetch_url(url, timeout=15):
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            )
        }
        sess = requests.Session()
        sess.headers.update(headers)
        resp = sess.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"  [WARN] fetch_url failed for {url}: {e}")
        return ""


def keyword_score(text):
    text_lower = text.lower()
    matched = []
    for kw in KEYWORDS:
        if kw.lower() in text_lower:
            matched.append(kw)
    score = min(round(len(matched) * 1.2, 1), 10)

    urgency = "low"
    urgent_words = ["urgent", "asap", "immediately", "today", "deadline"]
    if any(w in text_lower for w in urgent_words):
        urgency = "high"
    elif len(matched) >= 3:
        urgency = "medium"

    budget_indicated = bool(re.search(r'\$\d+[\d,]*', text))

    lead_type = "job"
    if any(w in text_lower for w in ["freelance", "gig", "project", "contract"]):
        lead_type = "client"
    if any(w in text_lower for w in ["partner", "co-founder", "founding engineer"]):
        lead_type = "partner"

    return {
        "score": score,
        "type": lead_type,
        "urgency": urgency,
        "budget_indicated": budget_indicated,
        "matched_aspects": matched,
        "reason": f"Keyword match: {', '.join(matched) if matched else 'none'}"
    }


def llm_score(title, description):
    text = f"Title: {title}\nDescription: {description}"
    system_prompt = (
        "You are an expert in AI automation (n8n, Python, scraping, LLM, "
        "workflow automation, chatbots). Your task is to score a lead for "
        "relevance. We are looking for: freelance, contract, remote work, "
        "founding engineer, or consultant opportunities in AI automation.\n\n"
        "Return ONLY valid JSON with these fields:\n"
        "- score: 0-10 (how relevant this lead is)\n"
        "- type: \"client\" | \"job\" | \"partner\"\n"
        "- urgency: \"low\" | \"medium\" | \"high\"\n"
        "- budget_indicated: true/false\n"
        "- matched_aspects: list of strings (what makes this relevant)\n"
        "- reason: string explaining the score\n\n"
        "Use 0 for score if the lead is not relevant at all."
    )

    for client, model in [
        (groq_client, "llama-3.3-70b-versatile"),
        (or_client, "meta-llama/llama-3.3-70b-instruct"),
    ]:
        if client is None:
            continue
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text},
                ],
                temperature=0.1,
                max_tokens=300,
            )
            raw = resp.choices[0].message.content.strip()
            raw = re.sub(r'^```(?:json)?\s*', '', raw)
            raw = re.sub(r'\s*```$', '', raw)
            data = json.loads(raw)
            data.setdefault("score", 0)
            data.setdefault("type", "job")
            data.setdefault("urgency", "low")
            data.setdefault("budget_indicated", False)
            data.setdefault("matched_aspects", [])
            data.setdefault("reason", "")
            data["score"] = max(0, min(float(data["score"]), 10))
            return data
        except Exception as e:
            print(f"  [WARN] LLM score failed ({model}): {e}")
            continue

    return keyword_score(text)


def parse_hn_jobs():
    print("[HN] Searching 'Who is hiring' posts via Algolia API...")
    import time as _time
    # Algolia HN Search API — find latest "Who is hiring" post
    raw = fetch_url(
        "https://hn.algolia.com/api/v1/search_by_date?"
        "query=who+is+hiring&tags=story&hitsPerPage=3"
    )
    if not raw:
        print("  [WARN] Algolia API failed, scraping HN front page...")
        _time.sleep(2)
        raw = fetch_url("https://news.ycombinator.com/")
        if raw:
            leads = []
            for match in re.finditer(
                r'<tr class="athing"[^>]*>.*?<span class="titleline"><a[^>]*href="([^"]*)"[^>]*>([^<]+)</a>',
                raw, re.DOTALL
            ):
                url = match.group(1)
                if url.startswith("item?"):
                    url = f"https://news.ycombinator.com/{url}"
                elif url.startswith("/"):
                    url = f"https://news.ycombinator.com{url}"
                title = html.unescape(match.group(2)).strip()
                if any(kw in title.lower() for kw in ["hiring", "job", "remote", "freelance"]):
                    leads.append({"title": title, "url": url, "source": "Hacker News"})
            print(f"  {len(leads)} leads (scraped)")
            return leads
        return []

    leads = []
    try:
        data = json.loads(raw)
        for hit in data.get("hits", []):
            title = hit.get("title", "")
            url = hit.get("url") or hit.get("objectID", "")
            if not url.startswith("http"):
                url = f"https://news.ycombinator.com/item?id={url}"
            if title:
                leads.append({"title": title, "url": url, "source": "Hacker News"})
            # Get the top-level comments for each hiring post (these are the actual jobs)
            _time.sleep(1)
            item_raw = fetch_url(
                f"https://hn.algolia.com/api/v1/items/{hit.get('objectID', '')}"
            )
            if item_raw:
                try:
                    item_data = json.loads(item_raw)
                    for child in item_data.get("children", []):
                        comment_text = (child.get("text", "") or "")[:200]
                        comment_text = re.sub(r'<[^>]+>', '', comment_text).strip()
                        if comment_text:
                            leads.append({
                                "title": comment_text,
                                "url": f"https://news.ycombinator.com/item?id={child.get('id', '')}",
                                "source": "Hacker News"
                            })
                except: pass
    except Exception as e:
        print(f"  [WARN] HN parse error: {e}")
    print(f"  {len(leads)} leads (API)")
    return leads


def parse_reddit_forhire():
    print("[Reddit] Fetching r/forhire...")
    raw = fetch_url("https://www.reddit.com/r/forhire/hot.json")
    if not raw:
        print("  [WARN] Reddit unreachable, trying r/freelance...")
        raw = fetch_url("https://www.reddit.com/r/freelance/hot.json")
    if not raw:
        return []

    leads = []
    try:
        data = json.loads(raw)
        for child in data.get("data", {}).get("children", []):
            post = child.get("data", {})
            title = post.get("title", "")
            url = post.get("url", "")
            if title:
                leads.append({"title": title, "url": url, "source": "Reddit"})
    except Exception as e:
        print(f"  [WARN] Reddit parse error: {e}")
    print(f"  {len(leads)} leads")
    return leads


def parse_telegram_sources():
    if not TG_API_ID or not TG_API_HASH:
        print("[Telegram] TG_API_ID/HASH not set — using web fallback")
        return _parse_telegram_web()

    async def _fetch():
        client = TelegramClient(TG_SESSION, TG_API_ID, TG_API_HASH)
        try:
            await client.start()
        except Exception as e:
            print(f"  [WARN] Telethon auth failed ({e}) — web fallback")
            await client.disconnect()
            return None

        leads = []
        for ch in TELEGRAM_SOURCES:
            try:
                entity = await client.get_entity(ch["name"])
                async for msg in client.iter_messages(entity, limit=10):
                    if msg.text:
                        text = msg.text.strip()[:200]
                        leads.append({
                            "title": text,
                            "url": f"https://t.me/{ch['name']}/{msg.id}",
                            "source": f"Telegram @{ch['name']}"
                        })
                n = sum(1 for l in leads if l.get("source") == f"Telegram @{ch['name']}")
                print(f"  [{ch['name']}] {n} messages")
            except Exception as e:
                print(f"  [WARN] @{ch['name']} failed: {e}")
        await client.disconnect()
        return leads

    try:
        result = asyncio.run(_fetch())
        if result is None:
            return _parse_telegram_web()
        return result
    except Exception as e:
        print(f"  [WARN] Telethon error: {e} — web fallback")
        return _parse_telegram_web()


def _parse_telegram_web():
    print("[Telegram] Fetching from public web previews (t.me/s/)...")
    leads = []
    skip_patterns = re.compile(r'^(Channel (created|photo)|subscribed|\d+:\d+|$)', re.I)
    for ch in TELEGRAM_SOURCES:
        url = f"https://t.me/s/{ch['name']}"
        html_text = fetch_url(url)
        if not html_text:
            continue
        blocks = re.split(r'<div class="tgme_widget_message_text[^"]*"[^>]*>', html_text)
        for block in blocks[1:]:
            text = re.sub(r'<[^>]+>', ' ', block).strip()
            text = html.unescape(text)[:200]
            if text and not skip_patterns.match(text):
                leads.append({
                    "title": text,
                    "url": f"https://t.me/{ch['name']}",
                    "source": f"Telegram @{ch['name']}"
                })
        n = sum(1 for l in leads if l.get("source") == f"Telegram @{ch['name']}")
        print(f"  [{ch['name']}] {n} msgs (web)")
    return leads


def deduplicate(conn, leads):
    c = conn.cursor()
    seen = set()
    for row in c.execute("SELECT url FROM leads"):
        seen.add(row[0])
    return [l for l in leads if l["url"] not in seen]


def store_leads(conn, results):
    c = conn.cursor()
    count = 0
    for r in results:
        try:
            c.execute(
                """INSERT OR IGNORE INTO leads
                   (title, source, url, score, type, urgency, budget, matched_aspects, reason)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    r["title"],
                    r["source"],
                    r["url"],
                    r.get("score", 0),
                    r.get("type", "job"),
                    r.get("urgency", "low"),
                    json.dumps(r.get("budget_indicated", False)),
                    json.dumps(r.get("matched_aspects", [])),
                    r.get("reason", ""),
                )
            )
            if c.rowcount:
                count += 1
        except Exception as e:
            print(f"  [WARN] store failed: {e}")
    conn.commit()
    return count


def generate_html_report(leads):
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(DATA_DIR, f"leads_report_{now}.html")
    rows = ""
    for i, l in enumerate(leads, 1):
        aspects = ", ".join(l.get("matched_aspects", []))
        budget_display = "✅" if l.get("budget_indicated") else "❌"
        rows += f"""
        <tr>
            <td>{i}</td>
            <td>{html.escape(l['title'])}</td>
            <td>{html.escape(l.get('source', ''))}</td>
            <td>{l.get('score', 0)}</td>
            <td>{l.get('type', 'job')}</td>
            <td>{l.get('urgency', 'low')}</td>
            <td>{budget_display}</td>
            <td>{html.escape(aspects)}</td>
            <td><a href="{html.escape(l.get('url', ''))}">link</a></td>
        </tr>"""
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Lead Hunter Pro Report</title>
<style>
  body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
  h1 {{ color: #333; }}
  table {{ border-collapse: collapse; width: 100%; background: #fff; box-shadow: 0 0 10px rgba(0,0,0,0.1); }}
  th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }}
  th {{ background: #2c3e50; color: #fff; }}
  tr:hover {{ background: #f1f1f1; }}
</style>
</head>
<body>
<h1>Lead Hunter Pro Report</h1>
<p>Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | Total: {len(leads)} leads</p>
<table>
<thead><tr>
  <th>#</th><th>Title</th><th>Source</th><th>Score</th><th>Type</th><th>Urgency</th><th>Budget</th><th>Match</th><th>URL</th>
</tr></thead>
<tbody>{rows}</tbody>
</table>
</body>
</html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"[Report] HTML saved: {path}")


def generate_csv_report(leads):
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(DATA_DIR, f"leads_report_{now}.csv")
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["#", "Title", "Source", "Score", "Type", "Urgency",
                     "Budget", "Matched Aspects", "URL", "Reason"])
        for i, l in enumerate(leads, 1):
            w.writerow([
                i, l["title"], l.get("source", ""), l.get("score", 0),
                l.get("type", "job"), l.get("urgency", "low"),
                l.get("budget_indicated", False),
                ", ".join(l.get("matched_aspects", [])),
                l.get("url", ""), l.get("reason", ""),
            ])
    print(f"[Report] CSV saved: {path}")


def print_console(leads):
    sep = "=" * 47
    dash = "-" * 47
    print(f"\n{sep}")
    for i, l in enumerate(leads, 1):
        budget_display = "YES" if l.get("budget_indicated") else "NO"
        aspects = ", ".join(l.get("matched_aspects", []))
        print(f"Lead #{i} | Score: {l.get('score', 0)}/10 | Urgency: {l.get('urgency', 'low')}")
        print(dash)
        print(f"Title:  {l['title'][:80]}")
        print(f"Source: {l.get('source', '?')}")
        print(f"Budget: {budget_display}")
        print(f"Match:  {aspects}")
        print(f"Type:   {l.get('type', 'job')}")
        print(dash)
    print(f"{sep}\n")


def run():
    print("=" * 47)
    print("  Lead Hunter Pro — scanning for opportunities")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 47)

    conn = init_db()

    all_raw = []
    all_raw.extend(parse_hn_jobs())
    all_raw.extend(parse_reddit_forhire())
    all_raw.extend(parse_telegram_sources())

    print(f"\n[Raw] Total leads collected: {len(all_raw)}")

    scored = []
    for i, lead in enumerate(all_raw):
        print(f"  Scoring [{i+1}/{len(all_raw)}]: {lead['title'][:60]}...")
        result = llm_score(lead["title"], lead["title"])
        result["title"] = lead["title"]
        result["url"] = lead["url"]
        result["source"] = lead["source"]
        scored.append(result)

    new_count = store_leads(conn, scored)
    print(f"[DB] New leads stored: {new_count}")

    high_scored = [l for l in scored if l.get("score", 0) >= 6]
    high_scored.sort(key=lambda x: x.get("score", 0), reverse=True)
    print(f"[Filter] High-scoring leads (>=6): {len(high_scored)}")

    if high_scored:
        print_console(high_scored)
        generate_html_report(high_scored)
        generate_csv_report(high_scored)
    else:
        print("[Info] No high-scoring leads found this run.")

    conn.close()
    return high_scored


def main():
    parser = argparse.ArgumentParser(description="Lead Hunter Pro")
    parser.add_argument("--loop", action="store_true", help="Run continuously every 30 min")
    args = parser.parse_args()

    if args.loop:
        print("[Scheduler] Starting loop mode (30 min interval). Press Ctrl+C to stop.")
        try:
            while True:
                run()
                print("[Scheduler] Sleeping 30 minutes...")
                time.sleep(1800)
        except KeyboardInterrupt:
            print("\n[Scheduler] Stopped by user.")
    else:
        run()


if __name__ == "__main__":
    main()
