import os
import re
import json
import csv
import sqlite3
import argparse
import time
import html
import asyncio
import hashlib
import threading
from datetime import datetime
from io import StringIO
from http.server import HTTPServer, BaseHTTPRequestHandler
from collections import OrderedDict


def stable_hash(s):
    """Deterministic hash (Python's hash() is randomized per process)."""
    return hashlib.sha256(s.encode("utf-8", "replace")).hexdigest()[:16]

import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def extract_json(text):
    text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\s*```$', '', text, flags=re.MULTILINE)
    m = re.search(r'\{.*', text, re.DOTALL)
    if m:
        chunk = m.group().rstrip()
        if not chunk.endswith("}"):
            chunk += "}"
        try:
            return json.loads(chunk)
        except json.JSONDecodeError:
            pass
    raise json.JSONDecodeError("No JSON object found", text, 0)


try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError:
    pass

import requests
from openai import OpenAI
from telethon import TelegramClient

GROQ_KEY = os.getenv("GROQ_API_KEY")
OR_KEY = os.getenv("OPENROUTER_API_KEY")
OR_KEY2 = os.getenv("OPENROUTER_API_KEY2")

groq_client = OpenAI(api_key=GROQ_KEY, base_url="https://api.groq.com/openai/v1") if GROQ_KEY else None
or_client = OpenAI(api_key=OR_KEY, base_url="https://openrouter.ai/api/v1") if OR_KEY else None
or_client2 = OpenAI(api_key=OR_KEY2, base_url="https://openrouter.ai/api/v1") if OR_KEY2 else None

TG_API_ID = int(os.getenv("TG_API_ID", "0"))
TG_API_HASH = os.getenv("TG_API_HASH", "")
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")
OWNER_CHAT_ID = os.getenv("OWNER_CHAT_ID", "")
GUEST_BOTS = []
for _pair in (os.getenv("GUEST_BOTS", "") or "").split(","):
    _pair = _pair.strip()
    if ":" in _pair:
        _tok, _chat = _pair.split(":", 1)
        if _tok.strip() and _chat.strip():
            GUEST_BOTS.append((_tok.strip(), _chat.strip()))
TG_SESSION = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lead_hunter.session")

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

HAS_SUPABASE = bool(SUPABASE_URL and SUPABASE_KEY)

def _sb(path, method="GET", data=None, params=None):
    """Raw Supabase REST API call. Returns parsed JSON or None."""
    if not HAS_SUPABASE:
        return None
    base = SUPABASE_URL.rstrip("/")
    if not base.endswith("/rest/v1"):
        base += "/rest/v1"
    url = f"{base}/{path}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    try:
        r = requests.request(method, url, headers=headers, json=data, params=params, timeout=10)
        r.raise_for_status()
        if r.text.strip():
            return r.json()
        return []
    except Exception as e:
        print(f"  [WARN] Supabase API error ({method} {path}): {e}", flush=True)
        return None

KEYWORDS = [
    "n8n", "python", "scraping", "scrape", "scraper", "automation", "workflow",
    "freelance", "contract", "bot", "api",
    "chatbot", "llm", "ai", "gpt", "telegram bot",
    "consultant", "integration", "webhook",
    "zapier", "make", "low-code", "no-code", "selenium",
    "machine learning", "data pipeline", "etl",
    "blockchain", "web3", "crypto", "solana", "rust",
    "fintech", "defi", "smart contract", "solidity",
    "founding engineer", "co-founder",
    "devops", "analyst",
    "ai agent", "langchain", "rag", "vector database",
    "n8n workflow", "ai automation",
    "english", "english speaking", "english required", "fluent english",
    "english proficiency", "good english",
    "trading bot", "algorithmic trading", "automated trading", "quant",
    "e-commerce", "ecommerce", "online store", "shopify",
    "payment", "payments", "crypto payment", "payment gateway",
    "dashboard", "alerts", "alert system", "notification",
    "lead generation", "content automation", "content pipeline",
    "billing", "subscription", "saas", "mvp",
    "telegram", "discord bot", "trading", "investment",
]

EXCLUDE = [
    "senior", "sr.", "team lead", "tech lead", "engineering lead",
    "lead developer", "lead engineer", "lead architect", "lead designer",
    "lead recruiter", "principal", "staff", "head of",
    "director", "vp", "vice president", "manager",
]

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "leads.db")
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)

TELEGRAM_SOURCES = [
    {"name": "remote_python_jobs", "url": "https://t.me/remote_python_jobs"},
    {"name": "pythonpythonjobs", "url": "https://t.me/pythonpythonjobs"},
    {"name": "forpython", "url": "https://t.me/forpython"},
    {"name": "job_python", "url": "https://t.me/job_python"},
    {"name": "pydevjob", "url": "https://t.me/pydevjob"},
    {"name": "python_djangojobs", "url": "https://t.me/python_djangojobs"},
    {"name": "remotejobs", "url": "https://t.me/remotejobs"},
    {"name": "jobstash", "url": "https://t.me/jobstash"},
    {"name": "workingincrypto", "url": "https://t.me/workingincrypto"},
    {"name": "cryptoheadhunter", "url": "https://t.me/cryptoheadhunter"},
    {"name": "opento_crypto", "url": "https://t.me/opento_crypto"},
    {"name": "web30job", "url": "https://t.me/web30job"},
    {"name": "cryptovakansii", "url": "https://t.me/cryptovakansii"},
    {"name": "xCareers", "url": "https://t.me/xCareers"},
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
            sent INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    # migration: description column (used to regenerate applications later)
    try:
        c.execute("ALTER TABLE leads ADD COLUMN description TEXT")
        conn.commit()
    except Exception:
        pass  # column already exists
    conn.commit()

    if HAS_SUPABASE:
        print("[Supabase] Using REST API", flush=True)

    return conn


def fetch_url(url, timeout=15):
    try:
        headers = OrderedDict([
            ("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"),
            ("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"),
            ("Accept-Language", "en-US,en;q=0.9,ru;q=0.8"),
            ("Connection", "keep-alive"),
            ("Upgrade-Insecure-Requests", "1"),
            ("Sec-Fetch-Dest", "document"),
            ("Sec-Fetch-Mode", "navigate"),
            ("Sec-Fetch-Site", "none"),
            ("Sec-Fetch-User", "?1"),
        ])
        sess = requests.Session()
        sess.headers.update(dict(headers))
        resp = sess.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"  [WARN] fetch_url failed for {url}: {e}")
        return ""


SPECIFIC_KW = {"n8n", "python", "scraping", "scrape", "scraper", "llm", "chatbot", "telegram bot", "langchain", "rag",
                "ai agent", "n8n workflow", "selenium", "webhook", "zapier", "make", "low-code", "no-code",
                "english", "english speaking", "english required", "fluent english",
                "english proficiency", "good english",
                "trading bot", "algorithmic trading", "automated trading", "quant",
                "payment", "crypto payment", "payment gateway", "dashboard",
                "telegram", "trading", }
GENERAL_KW = {"freelance", "contract", "consultant", "integration", "bot", "api", "automation",
              "founding engineer", "co-founder", "devops", "analyst", "machine learning",
              "data pipeline", "etl",
              "e-commerce", "ecommerce", "online store", "shopify",
              "alerts", "alert system", "notification", "content automation",
              "content pipeline", "lead generation", "billing", "subscription", "saas", "mvp",
              "discord bot", "investment", "fintech", "crypto", "defi", "ai", "gpt"}

def keyword_score(text, allow_senior=False, kw=None, specific=None, general=None, exclude=None):
    text_lower = text.lower()
    matched = []
    score = 0.0
    kw = kw if kw is not None else KEYWORDS
    specific = specific if specific is not None else SPECIFIC_KW
    general = general if general is not None else GENERAL_KW
    exclude = exclude if exclude is not None else EXCLUDE
    for k in kw:
        if k.lower() in text_lower:
            matched.append(k)
            if k in specific:
                score += 2.0
            elif k in general:
                score += 1.5
            else:
                score += 1.0

    if not allow_senior:
        for ex in exclude:
            if ex.lower() in text_lower:
                score -= 3.0
    score = max(0.0, min(round(score, 1), 10))

    urgency = "low"
    urgent_words = ["urgent", "asap", "immediately", "today", "deadline"]
    if any(w in text_lower for w in urgent_words):
        urgency = "high"
    elif score >= 4:
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
        "reason": f"Keywords: {', '.join(matched[:5])}" if matched else "No keywords"
    }


def _llm_chain():
    """Diversified (client, model) chain. deepseek is primary (stable, cheap);
    qwen goes last because it is frequently rate-limited upstream (429 ->
    empty content) and only worth trying when others fail."""
    chain = []
    if or_client:
        chain += [
            (or_client, "deepseek/deepseek-chat"),
            (or_client, "meta-llama/llama-3.3-70b-instruct"),
            (or_client, "qwen/qwen3.7-flash"),
        ]
    if or_client2:
        chain += [
            (or_client2, "deepseek/deepseek-chat"),
            (or_client2, "qwen/qwen3.7-flash"),
        ]
    if groq_client:
        chain.append((groq_client, "llama-3.3-70b-versatile"))
    seen = set()
    out = []
    for c, m in chain:
        if c is None:
            continue
        k = (id(c), m)
        if k not in seen:
            seen.add(k)
            out.append((c, m))
    return out


def llm_complete(system, user, max_tokens=200, temperature=0.1, timeout=20):
    """Try each (client, model) with one retry; return raw text or None."""
    for client, model in _llm_chain():
        for attempt in range(2):
            try:
                resp = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=timeout,
                )
                raw = (resp.choices[0].message.content or "").strip()
                if raw:
                    return raw
                print(f"  [WARN] LLM empty response ({model})", flush=True)
            except Exception as e:
                print(f"  [WARN] LLM call failed ({model}): {e}", flush=True)
            time.sleep(1)
    return None


def llm_score(title, description, allow_senior=False, prompt=None):
    text = f"Title: {title}\nDescription: {description}"

    kw = keyword_score(text, allow_senior=allow_senior)
    if prompt is None and (kw["score"] < 2 or kw["score"] > 6):
        return kw

    senior_rule = (
        "IMPORTANT: Keep reason short. If the title says Senior, Lead, Principal, Director, VP, or Head Of — set score to 0.\n"
    )
    if prompt is None:
        model_prompt = (
            "You are an expert AI scorer for a solo AI product builder profile. "
            "Perfect matches: telegram bots, trading/quant bots, e-commerce "
            "automation, payment integrations, dashboards, alert systems, "
            "content automation, lead generation, n8n/Python/LLM automation, "
            "crypto/DeFi tooling, MVPs, SaaS tools. We build systems that run "
            "autonomously, priced on value.\n"
            "We are looking for: freelance, contract, remote work, founding "
            "engineer, or consultant opportunities in the above areas. "
            "Traditional web-backend / enterprise / pure frontend roles score LOW.\n"
            "SPECIAL RULE: If the description explicitly REQUIRES ENGLISH LANGUAGE "
            "(good command of english, fluent english, etc.), score MUST be at least 6 "
            "— we accept such jobs even outside the preferred scope.\n\n"
            "Return ONLY valid JSON with these fields:\n"
            "- score: 0-10 (how relevant this lead is)\n"
            "- type: \"client\" | \"job\" | \"partner\"\n"
            "- urgency: \"low\" | \"medium\" | \"high\"\n"
            "- budget_indicated: true/false\n"
            "- matched_aspects: list of strings (what makes this relevant)\n"
            "- reason: one short sentence (max 7 words)\n\n"
            + (senior_rule if not allow_senior else "")
            + "Use 0 for score if the lead is not relevant at all."
        )
    else:
        model_prompt = prompt

    raw = llm_complete(model_prompt, text, max_tokens=200, temperature=0.1, timeout=20)
    if raw is None:
        return keyword_score(text)
    try:
        data = extract_json(raw)
    except json.JSONDecodeError:
        print(f"  [WARN] LLM bad JSON: {raw[:200]}", flush=True)
        return keyword_score(text)
    data.setdefault("score", 0)
    data.setdefault("type", "job")
    data.setdefault("urgency", "low")
    data.setdefault("budget_indicated", False)
    data.setdefault("matched_aspects", [])
    data.setdefault("reason", "")
    data["score"] = max(0, min(float(data["score"]), 10))
    return data


def parse_jobsdb(max_pages=4, fetch_desc=True):
    """JobsDB Thailand: any jobs whose description requires English."""
    print("[JobsDB] Fetching job listings...", flush=True)
    leads = []
    seen = set()
    for page in range(max_pages):
        url = f"https://th.jobsdb.com/jobs?page={page}"
        t = fetch_url(url, timeout=25)
        if not t:
            print(f"  [WARN] JobsDB page {page} failed", flush=True)
            time.sleep(2)
            continue
        chunks = t.split('data-testid="job-card"')
        n = 0
        for chunk in chunks[1:]:
            am = re.search(r'aria-label="([^"]+)"', chunk)
            hm = re.search(r'href="(/job/\d{4,})', chunk)
            if not (am and hm):
                continue
            jid = hm.group(1).split("/")[-1]
            if jid in seen:
                continue
            seen.add(jid)
            title = html.unescape(am.group(1)).strip()[:200]
            leads.append({
                "title": title,
                "url": f"https://th.jobsdb.com/job/{jid}",
                "source": "JobsDB",
                "description": "",
            })
            n += 1
        print(f"  [JobsDB] page {page}: {n} jobs", flush=True)

    if fetch_desc and leads:
        print(f"  [JobsDB] Fetching descriptions for {len(leads)} jobs...", flush=True)
        for i, l in enumerate(leads):
            time.sleep(1.5)  # rate-limit protection (JobsDB bans fast bursts)
            try:
                t = fetch_url(l["url"], timeout=20)
                if t:
                    i0 = t.find('data-automation="jobAdDetails"')
                    if i0 > 0:
                        chunk = t[i0:i0 + 20000]
                        txt = re.sub(r"<[^>]+>", " ", chunk)
                        txt = html.unescape(re.sub(r"\s+", " ", txt)).strip()
                        l["description"] = txt[:1500]
            except Exception as e:
                print(f"  [WARN] JobsDB desc {l['url']}: {e}")
            if (i + 1) % 20 == 0:
                print(f"  [JobsDB] desc {i + 1}/{len(leads)}", flush=True)
    print(f"[JobsDB] Total: {len(leads)} jobs", flush=True)
    return leads


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
            # Only "Who is hiring" posts — skip "Who wants to be hired" (people looking for jobs)
            if "who is hiring" not in title.lower():
                continue
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


def parse_remoteok():
    print("[RemoteOK] Fetching...")
    raw = fetch_url("https://remoteok.com/api?action=get_jobs")
    if not raw:
        return []
    leads = []
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        for job in data[:20] if isinstance(data, list) else []:
            title = job.get("position", "")
            url = job.get("url", "")
            if title:
                leads.append({"title": title, "url": url, "source": "RemoteOK"})
    except Exception as e:
        print(f"  [WARN] RemoteOK error: {e}")
    print(f"  {len(leads)} leads")
    return leads


def parse_remote_co():
    print("[Remotive] Fetching (replaces Remote.co)...")
    raw = fetch_url("https://remotive.com/api/remote-jobs", timeout=20)
    if not raw:
        return []
    leads = []
    try:
        data = json.loads(raw)
        for job in data.get("jobs", [])[:20]:
            title = job.get("title", "")
            url = job.get("url", "")
            if title:
                leads.append({"title": title, "url": url, "source": "Remotive"})
    except Exception as e:
        print(f"  [WARN] Remotive error: {e}")
    print(f"  {len(leads)} leads")
    return leads


def parse_wwr():
    print("[WeWorkRemotely] Fetching RSS...")
    raw = fetch_url("https://weworkremotely.com/remote-jobs.rss")
    if not raw:
        return []
    leads = []
    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(raw)
        for item in root.findall(".//item"):
            def child(tag):
                el = item.find(tag)
                return (el.text or "").strip() if el is not None and el.text else ""
            title = child("title")
            url = child("link") or child("guid")
            desc = child("description")
            apply_links = []
            if desc:
                for lnk in re.findall(r'href="(https?://[^"]+)"', desc):
                    if re.search(
                        r"weworkremotely\.com|facebook\.com|twitter\.com|x\.com|"
                        r"linkedin\.com|youtube\.com|instagram\.com|cloudfront|"
                        r"schema\.org|w3\.org|googleapis\.com",
                        lnk,
                    ):
                        continue
                    if lnk not in apply_links:
                        apply_links.append(lnk)
            if title and url:
                lead = {"title": title[:200], "url": url, "source": "WeWorkRemotely",
                        "description": (desc or "")[:800]}
                if apply_links:
                    lead["apply_links"] = apply_links[:3]
                leads.append(lead)
    except Exception as e:
        print(f"  [WARN] WWR RSS error: {e}")
    print(f"  {len(leads)} leads")
    return leads


def parse_himalayas():
    print("[Himalayas] Fetching...")
    raw = fetch_url("https://himalayas.app/jobs/api?limit=30")
    if not raw:
        return []
    leads = []
    try:
        data = json.loads(raw)
        for job in data.get("jobs", [])[:30]:
            title = job.get("title", "")
            url = job.get("applyUrl", "") or job.get("url", "") or job.get("slug", "")
            desc = " ".join([
                str(job.get("excerpt", "") or ""),
                " ".join(job.get("categories", [])) if isinstance(job.get("categories"), list) else str(job.get("categories", "")),
            ])
            if title:
                leads.append({"title": title[:200], "url": url, "source": "Himalayas",
                              "description": desc[:800]})
    except Exception as e:
        print(f"  [WARN] Himalayas error: {e}")
    print(f"  {len(leads)} leads")
    return leads


def parse_arbeitnow():
    print("[Arbeitnow] Fetching...")
    raw = fetch_url("https://arbeitnow.com/api/job-board-api?limit=30")
    if not raw:
        return []
    leads = []
    try:
        data = json.loads(raw)
        for job in data.get("data", [])[:30]:
            title = job.get("title", "")
            url = job.get("url", "")
            tags = job.get("tags", [])
            desc = job.get("description", "") or ""
            if title:
                leads.append({"title": title[:200], "url": url, "source": "Arbeitnow",
                              "description": (desc + " " + " ".join(tags))[:800]})
    except Exception as e:
        print(f"  [WARN] Arbeitnow error: {e}")
    print(f"  {len(leads)} leads")
    return leads


def parse_jobicy():
    print("[Jobicy] Fetching...")
    raw = fetch_url("https://jobicy.com/api/v2/remote-jobs?count=30")
    if not raw:
        return []
    leads = []
    try:
        data = json.loads(raw)
        for job in data.get("jobs", [])[:30]:
            title = job.get("jobTitle", "")
            url = job.get("url", "")
            desc = " ".join([str(job.get("jobExcerpt", "") or ""), str(job.get("jobDescription", "") or "")])
            if title:
                leads.append({"title": title[:200], "url": url, "source": "Jobicy",
                              "description": desc[:800]})
    except Exception as e:
        print(f"  [WARN] Jobicy error: {e}")
    print(f"  {len(leads)} leads")
    return leads


WEB3CAREER_TOKEN = os.getenv("WEB3CAREER_TOKEN", "")
WEB3CAREER_TAGS = ["ai", "defi", "full-stack", "backend", "python", "crypto"]


def parse_web3career():
    print("[Web3Career] Fetching...")
    if not WEB3CAREER_TOKEN:
        print("  [WARN] no WEB3CAREER_TOKEN set, skipping")
        return []
    leads = []
    seen_urls = set()
    for tag in WEB3CAREER_TAGS:
        try:
            params = {
                "token": WEB3CAREER_TOKEN,
                "tag": tag,
                "remote": "true",
                "limit": 100,
                "show_description": "true",
            }
            resp = requests.get("https://web3.career/api/v1", params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, list):
                continue
            jobs = next((item for item in data if isinstance(item, list)), None)
            if not jobs:
                jobs = data if (data and isinstance(data[0], dict)) else []
            for job in jobs:
                if not isinstance(job, dict):
                    continue
                title = str(job.get("title", "") or "").strip()
                url = str(job.get("apply_url", "") or "").strip()
                if not title or not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                desc_raw = str(job.get("description", "") or "")
                desc = re.sub(r"<[^>]+>", " ", desc_raw)
                desc = re.sub(r"\s+", " ", html.unescape(desc)).strip()[:800]
                tags = str(job.get("tags", "") or "")
                desc = f"{desc} {tags[:200]}"[:800]
                lead = {"title": title[:200], "url": url, "source": "Web3Career",
                        "description": desc, "apply_links": [url]}
                company = str(job.get("company", "") or "").strip()
                if company:
                    lead["company"] = company
                leads.append(lead)
        except Exception as e:
            print(f"  [WARN] Web3Career tag={tag} error: {e}")
    print(f"  {len(leads)} leads")
    return leads


def parse_reddit_forhire():
    print("[Reddit] Fetching r/forhire...")
    import time as _time

    urls_to_try = [
        "https://old.reddit.com/r/forhire/hot.json",
        "https://old.reddit.com/r/freelance/hot.json",
        "https://www.reddit.com/r/forhire/hot.json",
        "https://www.reddit.com/r/freelance/hot.json",
    ]
    raw = ""
    for u in urls_to_try:
        raw = fetch_url(u, timeout=20)
        if raw:
            print(f"  [OK] {u}")
            break
        _time.sleep(1)

    if not raw:
        print("  [WARN] JSON endpoints failed, trying RSS...")
        for u in ["https://www.reddit.com/r/forhire/hot.rss", "https://www.reddit.com/r/freelance/hot.rss"]:
            raw = fetch_url(u, timeout=20)
            if raw:
                print(f"  [OK] {u}")
                break

    if not raw:
        print("  [WARN] All Reddit endpoints failed")
        return []

    leads = []
    try:
        if raw.lstrip().startswith("<"):  # RSS XML
            entries = re.findall(r"<entry>(.*?)</entry>", raw, re.DOTALL)
            for e in entries:
                t = re.search(r"<title>(.*?)</title>", e, re.DOTALL)
                l = re.search(r'<link[^>]*href="(.*?)"', e) or re.search(r'<link[^>]*>(.*?)</link>', e)
                if t:
                    title = html.unescape(re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', t.group(1))).strip()
                    url = html.unescape(l.group(1)) if l else ""
                    # Only [Hiring] posts are opportunities; [For Hire] are freelancers advertising
                    if re.search(r"\[hiring\]", title, re.I) or not re.search(r"\[for\s*hire\]|\[for hire\]", title, re.I):
                        leads.append({"title": title, "url": url, "source": "Reddit"})
        else:  # JSON
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

    # Bot tokens can't read channel history (restricted by Telegram API)
    # So skip Telethon entirely if we only have a bot token
    if TG_BOT_TOKEN:
        print("[Telegram] Bot token detected — bots can't read channels, using web fallback")
        return _parse_telegram_web()

    # Only attempt Telethon with user auth (phone + code)
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
        # Each message has a unique anchor: <a href="https://t.me/channel/123">
        msg_links = re.findall(r'class="tgme_widget_message_date"[^>]*href="(https://t\.me/[^"]+/\d+)"|<a[^>]*href="(https://t\.me/[^"]+/\d+)"[^>]*class="tgme_widget_message_date"', html_text)  # class before OR after href
        msg_links = [g1 or g2 for g1, g2 in msg_links]
        msg_texts = re.split(r'<div class="tgme_widget_message_text[^"]*"[^>]*>', html_text)
        # msg_texts[0] is before first message, msg_texts[1:] correspond to each message
        for idx, block in enumerate(msg_texts[1:]):
            text = re.sub(r'<[^>]+>', ' ', block).strip()
            text = html.unescape(text)[:200]
            if text and not skip_patterns.match(text):
                msg_url = msg_links[idx] if idx < len(msg_links) else f"https://t.me/{ch['name']}"
                leads.append({
                    "title": text,
                    "url": msg_url,
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
    new_leads = []
    for r in results:
        try:
            c.execute(
                """INSERT OR IGNORE INTO leads
                   (title, source, url, score, type, urgency, budget, matched_aspects, reason, description)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                    r.get("description", ""),
                )
            )
            if c.rowcount:
                new_leads.append(r)
        except Exception as e:
            print(f"  [WARN] store failed: {e}")
    conn.commit()

    # Also upsert to Supabase if available (only new leads, don't overwrite sent=True)
    if HAS_SUPABASE:
        for r in new_leads:
            try:
                _sb("leads", "POST", {
                    "title": r["title"],
                    "source": r["source"],
                    "url": r["url"],
                    "score": r.get("score", 0),
                    "type": r.get("type", "job"),
                    "urgency": r.get("urgency", "low"),
                    "budget": json.dumps(r.get("budget_indicated", False)),
                    "matched_aspects": json.dumps(r.get("matched_aspects", [])),
                    "reason": r.get("reason", ""),
                }, params={"on_conflict": "url"})
            except Exception as e:
                print(f"  [WARN] Supabase store failed: {e}")

    print(f"[DB] New leads stored: {len(new_leads)}")
    return new_leads


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


def send_tg_message(text):
    if not TG_BOT_TOKEN or not OWNER_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
        requests.post(url, json={
            "chat_id": OWNER_CHAT_ID,
            "text": text[:4000],
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }, timeout=10)
    except Exception as e:
        print(f"  [WARN] TG send failed: {e}")
    for tok, chat in GUEST_BOTS:
        try:
            url = f"https://api.telegram.org/bot{tok}/sendMessage"
            requests.post(url, json={
                "chat_id": chat,
                "text": text[:4000],
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            }, timeout=10)
        except Exception as e:
            print(f"  [WARN] Guest bot send failed: {e}")


GUESTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "guests.json")


def load_guests():
    """Load guest profiles from guests.json next to the script.
    Each guest: {name, bot_token, chat_id, email, profile, keywords[], exclude[]}."""
    if not os.path.exists(GUESTS_FILE):
        return []
    try:
        with open(GUESTS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            print("  [WARN] guests.json: expected a list", flush=True)
            return []
        guests = []
        for g in data:
            if not g.get("bot_token") or not g.get("chat_id"):
                print(f"  [WARN] Guest {g.get('name', '?')}: missing bot_token/chat_id, skipped", flush=True)
                continue
            guests.append({
                "name": str(g.get("name", "Guest")),
                "bot_token": str(g["bot_token"]).strip(),
                "chat_id": str(g["chat_id"]).strip(),
                "email": str(g.get("email", "")).strip(),
                "profile": str(g.get("profile", "")) or PROFILE_TEXT,
                "keywords": [k.strip() for k in g.get("keywords", []) if str(k).strip()],
                "exclude": [k.strip() for k in g.get("exclude", []) if str(k).strip()],
            })
        return guests
    except Exception as e:
        print(f"  [WARN] guests.json parse error: {e}", flush=True)
        return []


def send_tg_message_to(bot_token, chat_id, text):
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        r = requests.post(url, json={
            "chat_id": chat_id,
            "text": text[:4000],
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"  [WARN] TG send to guest failed: {e}", flush=True)
        return False


def guest_scoring_prompt(guest):
    kw_line = ", ".join(guest.get("keywords", [])) or "none specified"
    return (
        "You are an expert AI scorer for the following freelance profile:\n\n"
        f"{guest.get('profile', '')}\n\n"
        f"Preferred keywords: {kw_line}\n"
        "We are looking for: freelance, contract, remote work, founding "
        "engineer, or consultant opportunities that match this profile.\n\n"
        "Return ONLY valid JSON with these fields:\n"
        "- score: 0-10 (how relevant this lead is)\n"
        "- type: \"client\" | \"job\" | \"partner\"\n"
        "- urgency: \"low\" | \"medium\" | \"high\"\n"
        "- budget_indicated: true/false\n"
        "- matched_aspects: list of strings (what makes this relevant)\n"
        "- reason: one short sentence (max 7 words)\n\n"
        "Use 0 for score if the lead is not relevant to this profile."
    )


def process_guest(guest, all_raw, conn=None):
    """Score the shared raw pool under THIS guest's own profile and deliver
    matches (>=6) plus applications (top-5 of >=8) via the guest's own bot."""
    name = guest.get("name", "Guest")
    print(f"[Guest:{name}] Scoring {len(all_raw)} raw leads under guest profile...", flush=True)
    kw = guest.get("keywords", [])
    exclude = guest.get("exclude", [])
    spec = set(kw)
    scored = []
    for i, lead in enumerate(all_raw):
        if not isinstance(lead, dict) or not lead.get("title"):
            continue
        title = lead["title"][:200]
        desc = lead.get("description") or title
        text = f"Title: {title}\nDescription: {desc}"
        result = keyword_score(text, allow_senior=True, kw=kw, specific=spec,
                               general=set(), exclude=exclude)
        if 2 <= result["score"] <= 6:
            llm = llm_score(title, desc[:2000], allow_senior=True,
                            prompt=guest_scoring_prompt(guest))
            if llm and llm.get("score", 0) >= 0:
                result = llm
        result["title"] = title
        result["url"] = lead.get("url", "")
        result["source"] = lead.get("source", "?")
        result["description"] = desc[:800]
        scored.append(result)

    picked = [l for l in scored if l.get("score", 0) >= 6]
    picked.sort(key=lambda x: x.get("score", 0), reverse=True)
    if not picked:
        print(f"[Guest:{name}] No leads >= 6 this scan.", flush=True)
        return

    sent_urls = set()
    if conn is not None:
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS guest_leads (guest TEXT, url TEXT, title TEXT, "
                "score REAL, source TEXT, created_at TEXT)"
            )
            conn.commit()
            cur = conn.execute("SELECT url FROM guest_leads WHERE guest=?", (name,))
            sent_urls = {r[0] for r in cur if r[0]}
        except Exception as e:
            print(f"  [WARN] guest_leads query error: {e}", flush=True)

    fresh = []
    for l in picked:
        if l.get("url") and l["url"] in sent_urls:
            print(f"  [Guest:{name}] already sent: {l['title'][:60]}", flush=True)
            continue
        fresh.append(l)
    if not fresh:
        print(f"[Guest:{name}] Nothing new for this guest.", flush=True)
        return

    send_fn = lambda t: send_tg_message_to(guest["bot_token"], guest["chat_id"], t)
    leads_to_tg(fresh, send_fn=send_fn)
    send_applications(fresh, send_fn=send_fn,
                      profile_text=guest.get("profile"), email=guest.get("email"))

    if conn is not None:
        try:
            for l in fresh:
                conn.execute(
                    "INSERT INTO guest_leads (guest, url, title, score, source, created_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (name, l.get("url", ""), l["title"], l.get("score", 0),
                     l.get("source", "?"), datetime.now().isoformat())
                )
            conn.commit()
        except Exception as e:
            print(f"  [WARN] guest_leads save error: {e}", flush=True)
    print(f"[Guest:{name}] Delivered {len(fresh)} leads (>=6).", flush=True)


OUTCOME_FILE = os.path.join(DATA_DIR, "outcomes.json")
OUTCOME_ORDER = ["replied", "called", "paid"]


def load_outcomes():
    if os.path.exists(OUTCOME_FILE):
        try:
            with open(OUTCOME_FILE, encoding="utf-8") as f:
                return json.loads(f.read() or "{}")
        except Exception:
            pass
    return {}


def save_outcomes(d):
    try:
        with open(OUTCOME_FILE, "w", encoding="utf-8") as f:
            f.write(json.dumps(d, ensure_ascii=False, indent=1))
    except Exception as e:
        print(f"  [WARN] outcomes save failed: {e}")


def record_outcome(url, status):
    d = load_outcomes()
    d[url] = status
    save_outcomes(d)
    # best-effort PATCH to Supabase (works once `outcome` column exists)
    if HAS_SUPABASE:
        try:
            _sb("leads", "PATCH", {"outcome": status}, params={"url": f"eq.{url}"})
        except Exception:
            pass
    print(f"[Outcome] {url} -> {status}", flush=True)
    # notify owner
    send_tg_message(f"\U0001F4C8 <b>Outcome</b>: <code>{status}</code> for {url[:60]}")


def short_url(url):
    u = url.replace("https://", "").replace("http://", "")
    return u[:50] + ".." if len(u) > 50 else u


def build_queue(conn):
    """All leads sent to TG (sent=1, score>=6) that have no outcome yet,
    sorted by score desc, then title. Used for digest + interactive commands."""
    oc = load_outcomes()
    cur = conn.cursor()
    rows = cur.execute(
        "SELECT title, source, url, score, matched_aspects, reason, description "
        "FROM leads WHERE sent=1 AND score >= 6"
    ).fetchall()
    q = []
    for title, source, url, score, aspects, reason, desc in rows:
        if not url or url in oc:
            continue
        q.append({
            "title": title,
            "source": source,
            "url": url,
            "score": score,
            "matched_aspects": json.loads(aspects) if aspects else [],
            "reason": reason or "",
            "description": desc or "",
        })
    q.sort(key=lambda l: (-l.get("score", 0), l["title"]))
    return q


def prioritize_leads(leads):
    """LLM batch: tag each lead 'today' / 'week' / 'skip'."""
    tags = {}
    if not leads:
        return tags
    chunk = 40
    for i in range(0, len(leads), chunk):
        part = leads[i:i + chunk]
        lines = []
        for idx, l in enumerate(part, 1):
            lines.append(f"{idx}. [{l.get('source','?')}] {l['title'][:100]} (score {l.get('score',0)})")
        prompt = (
            "You are a busy freelance AI product builder. Your ideal work: telegram bots, trading/quant bots, "
            "e-commerce automation, payment integrations, dashboards, alert systems, content automation, "
            "lead generation, n8n/Python/LLM automation, crypto/DeFi tooling, MVPs, SaaS tools. "
            "For each lead below decide: 'today' = strong match, reply ASAP; 'week' = decent, reply within a week; "
            "'skip' = weak, spammy, senior role, or not a fit.\n\n"
            "Return ONLY a JSON object mapping number to tag, e.g. {\"1\": \"today\", \"2\": \"skip\"}.\n\n"
            + "\n".join(lines)
        )
        raw = llm_complete(
            "You classify freelance job leads into today/week/skip.",
            prompt, max_tokens=800, temperature=0.1, timeout=45,
        )
        parsed = {}
        if raw:
            try:
                parsed = extract_json(raw)
            except Exception:
                print(f"  [WARN] prio bad JSON: {raw[:200]}", flush=True)
        for idx, l in enumerate(part, 1):
            t = str(parsed.get(str(idx), "week")).lower()
            if t not in ("today", "week", "skip"):
                t = "week"
            tags[l["url"]] = t
    return tags


def format_queue_lead(i, l, with_url=True):
    score = l.get("score", 0)
    aspects = ", ".join(a.lstrip("#").strip() for a in (l.get("matched_aspects") or []) if a.strip())
    msg = f"{i}. ⭐<b>{score}/10</b> [{l.get('source','?')}] <b>{l['title'][:90].replace('#','')}</b>"
    if aspects:
        msg += f"\n    🏷 {aspects[:120]}"
    if l.get("reason"):
        msg += f"\n    💬 {l['reason'][:120]}"
    if with_url and l.get("url"):
        msg += f"\n    🔗 <a href=\"{l['url']}\">{short_url(l['url'])}</a>"
    return msg


def send_digest(conn):
    """One consolidated digest of all unanswered leads: TOP-5 with ready
    applications, then prioritized lists (today / week / skip)."""
    q = build_queue(conn)
    if not q:
        send_tg_message("✅ Очередь пуста — все отправленные лиды обработаны!")
        return
    tags = prioritize_leads(q)
    today = [l for l in q if tags.get(l["url"]) == "today"]
    week = [l for l in q if tags.get(l["url"]) == "week"]
    skip = [l for l in q if tags.get(l["url"]) == "skip"]

    send_tg_message(
        f"📋 <b>Digest</b>: всего {len(q)} | 🔥 today {len(today)} | 📅 week {len(week)} | ⏭ skip {len(skip)}\n"
        f"Формат: d10 / app N / skip N / next"
    )

    top = sorted(today, key=lambda l: -l.get("score", 0))[:5]
    if top:
        chunks = [f"🔥 <b>ОТВЕТИТЬ СЕГОДНЯ — ТОП {len(top)}</b>\n" + "─" * 25]
        for i, l in enumerate(top, 1):
            reply = generate_application(l, email="onlinebis2016@gmail.com")
            contact = extract_contact(l)
            chunks.append(
                f"\n<b>{i}. {l['title'][:90].replace('#','')}</b> [{l.get('source','?')}] ⭐{l.get('score',0)}/10\n"
                f"<code>{html.escape(reply or '(не сгенерирован)')}</code>\n"
                f"👤 {html.escape(contact)}\n"
                f"🏷 {', '.join((l.get('matched_aspects') or [])[:6])}"
            )
        send_tg_message("\n".join(chunks))

    def group_msg(leads, header):
        if not leads:
            return None
        msg = f"{header} ({len(leads)})\n" + "─" * 25 + "\n"
        for i, l in enumerate(leads, 1):
            msg += f"\n{format_queue_lead(i, l)}"
            if len(msg) > 3000:
                send_tg_message(msg)
                msg = f"{header} (продолжение)\n" + "─" * 25 + "\n"
        return msg or None

    m = group_msg(today[5:], f"📅 <b>ЕЩЁ СЕГОДНЯ (остальные)</b>")
    if m:
        send_tg_message(m)
    m = group_msg(week, f"⏳ <b>НА ЭТОЙ НЕДЕЛЕ</b>")
    if m:
        send_tg_message(m)
    if skip:
        send_tg_message(f"⏭ <b>ПРОПУСТИТЬ</b> ({len(skip)}):\n" + "\n".join(
            f"· {l['title'][:60]}" for l in skip[:15]))


def tg_poll_outcomes():
    """Daemon: watch owner's messages in TG.
    - Reply with replied/called/paid -> outcome for that lead.
    - Plain commands: d10 / app N / skip N / next / digest / queue / help.
    """
    last_update_id = 0
    commands = {
        "replied": "replied",
        "ответ": "replied",
        "answered": "replied",
        "called": "called",
        "созвон": "called",
        "call": "called",
        "paid": "paid",
        "оплачено": "paid",
        "заказ": "paid",
        "deal": "paid",
    }
    while True:
        try:
            url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/getUpdates"
            params = {"timeout": 30, "offset": last_update_id, "allowed_updates": ["message"]}
            r = requests.get(url, params=params, timeout=40)
            data = r.json()
            for upd in data.get("result", []):
                last_update_id = max(last_update_id, upd["update_id"] + 1)
                msg = upd.get("message")
                if not msg:
                    continue
                text = (msg.get("text") or "").strip().lower()
                if not text:
                    continue
                reply = msg.get("reply_to_message")

                if text in commands:
                    if not reply:
                        send_tg_message("Скинь ответом на сообщение с лидом (Reply), например: replied / called / paid")
                        continue
                    orig = reply.get("text") or ""
                    m = re.search(r"https?://[^\s>]+", orig)
                    if not m:
                        send_tg_message("Не нашёл ссылку в сообщении, на которое ты ответил")
                        continue
                    lead_url = m.group(0).rstrip(">").rstrip(".")
                    record_outcome(lead_url, commands[text])
                    continue

                # ---- interactive queue commands (plain messages) ----
                if text in ("help", "/help", "помощь"):
                    send_tg_message(
                        "📖 <b>Команды</b>\n"
                        "• <code>digest</code> — сводка всех неотвеченных лидов\n"
                        "• <code>d10</code> — топ-10 очереди\n"
                        "• <code>app N</code> — готовый отклик на лид №N\n"
                        "• <code>skip N</code> — пропустить лид №N\n"
                        "• <code>next</code> — следующий лид с откликом\n"
                        "• <code>queue</code> — сколько лидов в очереди\n"
                        "• reply <code>replied/called/paid</code> на лид — отметить результат"
                    )
                    continue
                if text in ("digest", "дайджест"):
                    try:
                        c = sqlite3.connect(DB_PATH)
                        send_digest(c)
                        c.close()
                    except Exception as e:
                        print(f"  [WARN] digest failed: {e}", flush=True)
                        send_tg_message(f"⚠️ digest failed: {e}")
                    continue
                if text in ("queue", "очередь"):
                    try:
                        c = sqlite3.connect(DB_PATH)
                        n = len(build_queue(c))
                        c.close()
                        send_tg_message(f"📋 В очереди неотвеченных: {n}")
                    except Exception as e:
                        print(f"  [WARN] queue failed: {e}", flush=True)
                    continue
                if text == "d10" or text == "next" or text.startswith(("app ", "skip ")):
                    try:
                        c = sqlite3.connect(DB_PATH)
                        q = build_queue(c)
                        c.close()
                    except Exception as e:
                        print(f"  [WARN] queue load failed: {e}", flush=True)
                        q = []
                    if not q:
                        send_tg_message("✅ Очередь пуста!")
                        continue
                    if text == "d10":
                        chunks = [f"📋 <b>ТОП-10 из {len(q)}</b>\n" + "─" * 25]
                        for i, l in enumerate(q[:10], 1):
                            chunks.append("\n" + format_queue_lead(i, l))
                        send_tg_message("\n".join(chunks))
                        continue
                    if text == "next":
                        l = q[0]
                        reply_text = generate_application(l, email="onlinebis2016@gmail.com")
                        send_tg_message(
                            f"🎯 <b>СЛЕДУЮЩИЙ</b>\n{format_queue_lead(1, l)}\n\n"
                            f"<code>{html.escape(reply_text or '(не сгенерирован)')}</code>\n"
                            f"👤 {html.escape(extract_contact(l))}"
                        )
                        continue
                    # app N / skip N
                    parts = text.split()
                    if len(parts) == 2 and parts[1].isdigit():
                        idx = int(parts[1]) - 1
                        if idx >= len(q):
                            send_tg_message(f"⚠️ Нет лида №{parts[1]} (всего {len(q)})")
                            continue
                        l = q[idx]
                        if parts[0] == "app":
                            reply_text = generate_application(l, email="onlinebis2016@gmail.com")
                            send_tg_message(
                                f"📝 <b>ОТКЛИК на №{parts[1]}</b>\n"
                                f"{format_queue_lead(1, l)}\n\n"
                                f"<code>{html.escape(reply_text or '(не сгенерирован)')}</code>\n"
                                f"👤 {html.escape(extract_contact(l))}"
                            )
                        elif parts[0] == "skip":
                            record_outcome(l["url"], "skipped")
                            send_tg_message(f"⏭ Пропущен №{parts[1]}: {l['title'][:60]}. Осталось {len(q) - 1}")
                    continue
        except Exception as e:
            print(f"  [WARN] TG poll error: {e}", flush=True)
            time.sleep(10)
        time.sleep(1)


PROFILE_TEXT = """Andrey Mashkin: AI Product Builder, Bangkok (remote worldwide).
- Solo builder, 15+ years in trading & investments (equities, FX, commodities, crypto).
- Built TradeMind Lite: AI trading journal Telegram bot with crypto payments (Plisio).
- Runs 6 algorithmic trading bots (gold, BTC, oil, altcoins) on a small VPS with zero downtime: self-healing health checks, cron dashboards, instant Telegram alerts.
- DeFi trading infrastructure on Hyperliquid and other top DEXs: partial-close accounting, fees optimization, crash recovery.
- Tech: Python, Telegram Bot API, Cloudflare Workers, OpenRouter (various models), n8n, scraping, VPS/Linux, cron, HTML/CSS/JS.
- E-commerce automation: logic, orders, payments.
- Pricing: systems that run without me, priced on value, not hours.
- Contact: onlinebis2016@gmail.com."""


def generate_application(lead, profile_text=None, email=None):
    """Generate a short personalized reply for the given lead (score >= 8)."""
    try:
        profile_text = profile_text or PROFILE_TEXT
        title = lead.get("title", "")
        desc = (lead.get("description") or title)[:1000]
        aspects = ", ".join(lead.get("matched_aspects", [])[:6]) or "none"
        lang = "RU" if re.search(r"[а-яё]", desc) else "EN"
        prompt = (
            "You are an AI assistant writing the FIRST message from a freelance AI product builder "
            "applying to a job/project. Use the profile below.\n\n"
            f"{profile_text}\n\n"
            f"Job title: {title}\n"
            f"Job description: {desc}\n"
            f"Relevant aspects: {aspects}\n\n"
            f"Write a short reply message ({'in Russian' if lang == 'RU' else 'in English'}), "
            "3-6 sentences max, plain text, no markdown, no signature. "
            "PERSONAL: mention 1-2 concrete skills from the profile that directly match this exact job. "
            + (f"Your contact email to include at the end: {email}\n" if email else "")
            + "End with a call to action (e.g. 'Happy to discuss, my email is below'). "
            "Do NOT invent experience. Return ONLY the message text."
        )
        raw = llm_complete(
            "You write short, natural, personalized job-application replies.",
            prompt, max_tokens=250, temperature=0.4, timeout=25,
        )
        if raw:
            return raw[:1500]
    except Exception:
        pass
    return None


def extract_contact(lead):
    """Pull email / tg-username / link out of a lead for manual reply."""
    txt = " ".join([
        lead.get("title", ""),
        lead.get("description", "") or "",
        lead.get("url", ""),
    ])
    contact = []
    m = re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", txt)
    if m:
        contact.append(f"📧 {m.group(0)}")
    m = re.search(r"t\.me/([A-Za-z0-9_]+)", txt)
    if m:
        contact.append(f"✈️ t.me/{m.group(1)}")
    m = re.search(r"@([A-Za-z0-9_]{4,})", txt)
    if m:
        contact.append(f"@{m.group(1)}")
    if lead.get("url"):
        contact.append(f"🔗 {lead.get('url', '')[:200]}")
    for lnk in (lead.get("apply_links") or [])[:2]:
        if lnk != lead.get("url"):
            contact.append(f"🚀 Отклик напрямую: {lnk[:200]}")
    if lead.get("wwr_paid_only"):
        contact.append("⚠️ отклик только через WWR (платный)")
    return " | ".join(contact) or "⚠️ контакт не найден — см. ссылку/описание"


_CAREERS_CACHE = {}
_KNOWN_CAREERS = {
    "dropbox": ["https://www.dropbox.jobs/en/"],
    "tether": ["https://careers.tether.io/"],
    "bybit": ["https://www.bybit.com/en/careers"],
    "platform.sh": ["https://platform.sh/careers"],
    "fin": ["https://fin.ai/"],
}


def extract_company_name(title):
    """'Bybit: Blockchain Risk Control Intern' -> 'Bybit'"""
    m = re.match(r"^([^:]{2,40}):\s", title or "")
    if m:
        return m.group(1).strip()
    m = re.search(r"\bat\s+([A-Za-z0-9.\- ]{2,30})$", title or "")
    if m:
        return m.group(1).strip()
    return (title or "").split()[0][:30]


def careers_candidates(company):
    """Candidate direct-apply URLs for a company name."""
    base = re.sub(r"[^a-z0-9.\-]", "", company.lower())
    if "." in base:
        domain = base
    else:
        domain = base + ".com"
    domain = domain.strip(".-")
    return [
        f"https://{domain}/careers",
        f"https://careers.{domain}",
        f"https://{domain}/company/careers",
        f"https://{domain}/jobs",
        f"https://www.careers.{domain}",
    ]


def url_alive(url):
    """True if page loads and looks like a careers/jobs page."""
    try:
        resp = requests.get(url, timeout=8, allow_redirects=True,
                            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/125.0"})
        if resp.status_code >= 400:
            return False
        text = resp.text[:30000].lower()
        if "career" in text or "job" in text or "open position" in text or "vacan" in text:
            return True
        return len(text) > 500
    except Exception:
        return False


def find_careers_links(company):
    """Find a company's careers page: known map, guess domains, then DuckDuckGo fallback."""
    if not company:
        return []
    if company in _CAREERS_CACHE:
        return _CAREERS_CACHE[company]
    result = []
    for known, links in _KNOWN_CAREERS.items():
        if known in company.lower():
            result = list(links)
            break
    if not result:
        for cand in careers_candidates(company):
            if url_alive(cand):
                result = [cand]
                break
    if not result:
        try:
            q = requests.get(
                f"https://html.duckduckgo.com/html/?q={requests.utils.quote(company + ' careers jobs')}",
                timeout=10,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/125.0"},
            )
            links = re.findall(r'class="result__a"[^>]*href="([^"]+)"', q.text)
            for lnk in links:
                m = re.search(r"(https?://[^&]+)", lnk)
                if not m:
                    continue
                cand = m.group(1).replace("uddg=", "")
                if cand.startswith("http") and url_alive(cand):
                    result = [cand]
                    break
        except Exception:
            pass
    _CAREERS_CACHE[company] = result
    return result


def decorate_wwr_links(lead):
    """For WWR leads without direct apply links: find company careers page,
    else mark as paid-only (WWR apply button is Pro-only)."""
    if lead.get("source") != "WeWorkRemotely" or lead.get("apply_links") or lead.get("wwr_paid_only"):
        return
    company = extract_company_name(lead.get("title", ""))
    links = find_careers_links(company)
    if links:
        lead["apply_links"] = [lnk for lnk in links if lnk != lead.get("url")][:2]
        if not lead["apply_links"]:
            lead.pop("apply_links", None)
    if not lead.get("apply_links"):
        lead["wwr_paid_only"] = True


def send_applications(leads, send_fn=None, profile_text=None, email=None):
    """Send ready-to-copy reply for top leads: score >= 8, max 5 per scan."""
    send_fn = send_fn or send_tg_message
    candidates = sorted(
        [l for l in leads if l.get("score", 0) >= 8],
        key=lambda x: x.get("score", 0), reverse=True,
    )[:5]
    for l in candidates:
        reply = generate_application(l, profile_text=profile_text, email=email)
        if not reply:
            print(f"  [App] No reply generated for: {l['title'][:60]}", flush=True)
            continue
        decorate_wwr_links(l)
        title = l["title"][:70].replace("#", "")
        contact = extract_contact(l)
        msg = (
            f"\U0001F4DD <b>Ответ (score {l.get('score', 0)}/10)</b>\n"
            f"\u2500 {title}\n\n"
            f"<code>{html.escape(reply)}</code>\n\n"
            f"👤 {html.escape(contact)}\n"
            f"Источник: {l.get('source', '?')}"
        )
        send_fn(msg)
        print(f"[App] reply sent for: {title[:60]}", flush=True)
        time.sleep(0.5)


def leads_to_tg(leads, send_fn=None):
    if not leads:
        return
    send_fn = send_fn or send_tg_message

    def clean_aspects(aspects):
        return ", ".join(a.lstrip("#").strip() for a in aspects if a.strip())

    def short_url(url):
        u = url.replace("https://", "").replace("http://", "")
        return u[:50] + ".." if len(u) > 50 else u

    leads_sorted = sorted(leads, key=lambda l: l.get("score", 0), reverse=True)
    top = [l for l in leads_sorted if l.get("score", 0) >= 8]
    rest = [l for l in leads_sorted if l.get("score", 0) < 8]

    chunks = []
    total = len(leads)

    # --- TOP PICKS section ---
    if top:
        msg = f"\U0001F525 <b>TOP PICKS</b> ({len(top)}/{total})\n" + "\u2500" * 25 + "\n"
        for i, l in enumerate(top[:5], 1):
            title = l["title"][:70].replace("#", "")
            aspects = clean_aspects(l.get("matched_aspects", []))
            reason = l.get("reason", "")
            score = l.get("score", 0)
            msg += (
                f"\n\u2B50 <b>{title}</b>\n"
                f"   \U0001F4CA {score}/10  {l.get('source', '?')}\n"
            )
            if l.get("url"):
                msg += f"   \U0001F517 <a href=\"{l.get('url')}\">{short_url(l.get('url'))}</a>\n"
            if aspects:
                msg += f"   \U0001F3F7 {aspects}\n"
            if reason:
                msg += f"   \U0001F4AC {reason}\n"
        if len(top) > 5:
            msg += f"\n   ... +{len(top)-5} more top picks\n"
        chunks.append(msg)

    # --- REST by source ---
    if rest:
        from collections import OrderedDict
        groups = OrderedDict()
        for l in rest:
            src = l.get("source", "Other")
            groups.setdefault(src, []).append(l)

        msg = f"\U0001F50E Other leads ({len(rest)}/{total})\n" + "\u2500" * 25 + "\n"
        for src, group in groups.items():
            msg += f"\n\U0001F4E1 {src} ({len(group)})\n"
            for i, l in enumerate(group[:5], 1):
                title = l["title"][:70].replace("#", "")
                aspects = clean_aspects(l.get("matched_aspects", []))
                urgency_icon = {"high": "\U0001F534", "medium": "\U0001F7E1", "low": "\U0001F7E2"}
                urg = urgency_icon.get(l.get("urgency", "low"), "\u26AA")
                score = l.get("score", 0)
                msg += (
                    f"  {i}. <b>{title}</b>\n"
                    f"     \U0001F4CA {score}/10 {urg} {l.get('urgency', 'low').upper()}\n"
                )
                if l.get("url"):
                    msg += f"     \U0001F517 <a href=\"{l.get('url')}\">{short_url(l.get('url'))}</a>\n"
                if aspects:
                    msg += f"     \U0001F3F7 {aspects}\n"
            if len(group) > 5:
                msg += f"     ... +{len(group)-5} more from {src}\n"
            if len(msg) > 3500:
                chunks.append(msg)
                msg = ""
        if msg:
            chunks.append(msg)

    for c in chunks:
        send_fn(c)
        time.sleep(0.5)


def send_wwr_direct_links(leads):
    """For WWR leads: ensure direct apply links (or paid-only note) and
    notify once for leads that got a new direct link."""
    for l in leads:
        if l.get("source") != "WeWorkRemotely":
            continue
        had = bool(l.get("apply_links")) or l.get("wwr_paid_only")
        decorate_wwr_links(l)
        if had:
            continue
        contact = extract_contact(l)
        if contact and ("🚀 Отклик напрямую" in contact or "⚠️" in contact):
            title = l["title"][:70].replace("#", "")
            send_tg_message(
                f"\u2705 <b>WWR apply info</b>\n\u2500 {title}\n\n{contact}"
            )
            time.sleep(0.5)


def run():
    print("=" * 47, flush=True)
    print("  Lead Hunter Pro — scanning for opportunities", flush=True)
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
    print("=" * 47, flush=True)

    print("[DBG] init_db...", flush=True)
    conn = init_db()
    print("[DBG] DB ready", flush=True)

    all_raw = []
    print("[DBG] parse_hn_jobs...", flush=True)
    all_raw.extend(parse_hn_jobs())
    print("[DBG] parse_reddit...", flush=True)
    all_raw.extend(parse_reddit_forhire())
    print("[DBG] parse_telegram...", flush=True)
    all_raw.extend(parse_telegram_sources())
    print("[DBG] parse_remoteok...", flush=True)
    all_raw.extend(parse_remoteok())
    print("[DBG] parse_remote_co...", flush=True)
    all_raw.extend(parse_remote_co())
    print("[DBG] parse_wwr...", flush=True)
    all_raw.extend(parse_wwr())
    print("[DBG] parse_himalayas...", flush=True)
    all_raw.extend(parse_himalayas())
    print("[DBG] parse_arbeitnow...", flush=True)
    all_raw.extend(parse_arbeitnow())
    print("[DBG] parse_jobicy...", flush=True)
    all_raw.extend(parse_jobicy())
    print("[DBG] parse_web3career...", flush=True)
    all_raw.extend(parse_web3career())
    print("[DBG] parse_jobsdb...", flush=True)
    all_raw.extend(parse_jobsdb())

    print(f"[Raw] Total leads collected: {len(all_raw)}", flush=True)

    # Per-source collection stats (for the end-of-scan TG summary)
    from collections import Counter
    raw_by_source = Counter(l.get("source", "?") for l in all_raw)

    # Pre-dedup: skip scoring leads already known in local DB or Supabase
    known_urls = set()
    try:
        c = conn.cursor()
        for row in c.execute("SELECT url FROM leads"):
            if row[0]:
                known_urls.add(row[0])
    except Exception as e:
        print(f"  [WARN] local known-urls query failed: {e}")
    if HAS_SUPABASE:
        try:
            off = 0
            while True:
                resp = _sb("leads", params={"select": "url", "limit": 1000, "offset": off})
                if not resp:
                    break
                for row in resp:
                    if row.get("url"):
                        known_urls.add(row["url"])
                if len(resp) < 1000:
                    break
                off += 1000
        except Exception as e:
            print(f"  [WARN] Supabase known-urls fetch failed: {e}")
    before = len(all_raw)
    all_raw = [l for l in all_raw if not l.get("url") or l.get("url") not in known_urls]
    skipped = before - len(all_raw)
    if skipped:
        print(f"[Dedup] Skipped {skipped} already-known leads (known_urls={len(known_urls)})", flush=True)

    # Guest profiles: score the same raw pool under each guest's OWN profile
    # and deliver via their own bot (leads >=6, applications for top-5 >=8).
    try:
        for guest in load_guests():
            try:
                process_guest(guest, all_raw, conn=conn)
            except Exception as e:
                print(f"  [WARN] Guest processing failed for {guest.get('name', '?')}: {e}", flush=True)
    except Exception as e:
        print(f"  [WARN] Guests load failed: {e}", flush=True)

    scored = []
    for i, lead in enumerate(all_raw):
        if not isinstance(lead, dict) or not lead.get("title"):
            print(f"  [WARN] Skipping invalid lead #{i}: {lead}", flush=True)
            continue
        title = lead["title"][:200]
        print(f"  Scoring [{i+1}/{len(all_raw)}]: {title[:60]}...", flush=True)
        desc = lead.get("description") or title
        allow_senior = lead.get("source") == "JobsDB"
        result = llm_score(title, desc[:2000], allow_senior=allow_senior)
        result["title"] = title
        result["url"] = lead.get("url", "")
        result["source"] = lead.get("source", "?")
        result["description"] = desc[:800]
        scored.append(result)

    # Debug: show score distribution
    scores = [s.get("score", 0) for s in scored]
    top5 = sorted(scores, reverse=True)[:5]
    avg = sum(scores) / len(scores) if scores else 0
    print(f"[Score] total={len(scores)} avg={avg:.1f} top={top5}", flush=True)

    new_leads = store_leads(conn, scored)

    # Persistent dedup: skip leads already sent in previous runs
    sent_file = os.path.join(DATA_DIR, "sent_hashes.txt")

    # Check Supabase FIRST for already-sent URLs (persists across redeploys)
    supabase_sent_urls = set()
    if HAS_SUPABASE:
        try:
            resp = _sb("leads", params={"select": "url", "sent": "eq.true"})
            if resp is not None:
                supabase_sent_urls = {row["url"] for row in resp}
        except Exception as e:
            print(f"  [WARN] Supabase dedup query failed: {e}")

    sent_hashes = set()
    if os.path.exists(sent_file):
        sent_hashes.update(open(sent_file, encoding="utf-8").read().splitlines())

    # Also read sent URLs from local DB to catch past sends within same deploy
    c2 = conn.cursor()
    sent_urls = set()
    for row in c2.execute("SELECT url FROM leads WHERE sent=1"):
        sent_urls.add(row[0])

    # Merge Supabase sent URLs with local sent URLs
    sent_urls.update(supabase_sent_urls)

    high_scored = [l for l in new_leads if l.get("score", 0) >= 6]
    # Debug: why no high scores?
    if high_scored:
        hs_scores = [h.get("score", 0) for h in high_scored]
        print(f"[Debug] Before filters: {len(high_scored)} leads >=6, scores={sorted(hs_scores, reverse=True)[:10]}", flush=True)
    # Hard filter: remove Senior/Lead/Director/VP titles (JobsDB exempt — English jobs wanted)
    senior_pattern = re.compile(r"\b(senior|sr\.?|principal|staff|director|vp\b|vice president|head of)", re.I)
    # Debug: show what gets filtered
    for l in (high_scored or []):
        if l.get("source") != "JobsDB" and senior_pattern.search(l["title"]):
            print(f"  [Filtered] SENIOR: {l['title'][:70]} score={l.get('score',0)}", flush=True)
    high_scored = [l for l in high_scored if l.get("source") == "JobsDB" or not senior_pattern.search(l["title"])]
    # Remove resumes (#Резюме / resumes)
    high_scored = [l for l in high_scored if not re.search(r"#Резюме|#resume|резюме", l["title"], re.I)]
    unique = []
    for l in high_scored:
        h = stable_hash(l["title"][:60] + l.get("source", ""))
        if h in sent_hashes:
            print(f"  [Dedup] Already sent (hash): {l['title'][:70]} score={l.get('score',0)}", flush=True)
            continue
        if l.get("url") in sent_urls:
            print(f"  [Dedup] Already sent (url): {l['title'][:70]} score={l.get('score',0)}", flush=True)
            continue
        sent_hashes.add(h)
        unique.append(l)
    high_scored = unique
    high_scored.sort(key=lambda x: x.get("score", 0), reverse=True)
    print(f"[Filter] High-scoring leads (>=6): {len(high_scored)}")

    if high_scored:
        print_console(high_scored)
        leads_to_tg(high_scored)
        send_applications(high_scored)
        # Save hashes of sent leads to avoid re-sending after redeploy
        with open(sent_file, "a", encoding="utf-8") as f:
            for l in high_scored:
                h = stable_hash(l["title"][:60] + l.get("source", ""))
                f.write(h + "\n")
        # Mark as sent in local DB
        for l in high_scored:
            c2.execute("UPDATE leads SET sent=1 WHERE url=?", (l.get("url"),))
        conn.commit()
        # Also mark as sent in Supabase
        if HAS_SUPABASE:
            for l in high_scored:
                try:
                    _sb("leads", "PATCH", {"sent": True}, params={"url": f"eq.{l.get('url')}"})
                except Exception as e:
                    print(f"  [WARN] Supabase mark sent failed: {e}")
        generate_html_report(high_scored)
        generate_csv_report(high_scored)
    else:
        print("[Info] No high-scoring leads found this run.")

    guest_stats = []
    try:
        cg = conn.cursor()
        for g, n in cg.execute("SELECT guest, COUNT(*) FROM guest_leads GROUP BY guest"):
            guest_stats.append(f"{g} {n}")
    except Exception:
        pass

    conn.close()

    # Diagnostic summary to owner's TG so silent failures are visible
    try:
        src_lines = []
        for name in sorted(set(list(raw_by_source) + [s.get("source", "?") for s in scored])):
            raw_n = raw_by_source.get(name, 0)
            scored_n = sum(1 for s in scored if s.get("source") == name)
            src_lines.append(f"{name}: raw={raw_n} scored={scored_n}")
        summary = (
            f"\U0001F4CB <b>Scan summary</b> {datetime.now().strftime('%m-%d %H:%M')}\n"
            + "\u2500" * 25 + "\n"
            + "\n".join(src_lines)
            + f"\n\nNew: {len(all_raw)} | dedup-skipped: {skipped} | sent: {len(high_scored)}"
        )
        oc = load_outcomes()
        if oc:
            cnt = {"replied": 0, "called": 0, "paid": 0}
            for v in oc.values():
                if v in cnt:
                    cnt[v] += 1
            summary += f"\n\n\U0001F4CA <b>Outcomes</b>: replied {cnt['replied']} | called {cnt['called']} | paid {cnt['paid']}"
        if guest_stats:
            summary += "\n\n👥 Guests: " + " | ".join(guest_stats)
        send_tg_message(summary)
    except Exception as e:
        print(f"  [WARN] Summary send failed: {e}", flush=True)

    return high_scored


def main():
    parser = argparse.ArgumentParser(description="Lead Hunter Pro")
    parser.add_argument("--loop", action="store_true", help="Run continuously every 4 hours")
    args = parser.parse_args()

    # Health check server for Render (worker health check)
    def health_server():
        class H(BaseHTTPRequestHandler):
            def do_GET(s):
                s.send_response(200)
                s.end_headers()
                s.wfile.write(b"ok")
            def log_message(s, *a): pass
        HTTPServer(("0.0.0.0", 10000), H).serve_forever()
    t = threading.Thread(target=health_server, daemon=True)
    t.start()

    # Outcome tracker: reads owner's replies in TG
    if TG_BOT_TOKEN and OWNER_CHAT_ID:
        to = threading.Thread(target=tg_poll_outcomes, daemon=True)
        to.start()
        print("[Outcome] tracker started", flush=True)

    if args.loop:
        print("[Scheduler] Starting loop mode (4 hour interval).", flush=True)
        try:
            while True:
                try:
                    run()
                except Exception as e:
                    print(f"[ERROR] Run failed: {e}", flush=True)
                    import traceback
                    traceback.print_exc()
                print("[Scheduler] Sleeping 4 hours...", flush=True)
                time.sleep(14400)
        except KeyboardInterrupt:
            print("\n[Scheduler] Stopped by user.", flush=True)
    else:
        run()


if __name__ == "__main__":
    main()
